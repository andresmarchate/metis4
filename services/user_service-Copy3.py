import logging
from logging import handlers
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME
from flask_login import current_user
from flask_bcrypt import Bcrypt

# Configure logging
logger = logging.getLogger('email_search_app.user_service')
logger.setLevel(logging.DEBUG)
file_handler = handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
users_collection = db['users']

bcrypt = Bcrypt()

def get_user_data():
    """Return user data for the authenticated user."""
    logger.info("Fetching user data for user: %s", current_user.username)
    try:
        user_data = {
            'username': current_user.username,
            'mailboxes': current_user.mailboxes
        }
        logger.debug(f"User data: {user_data}")
        return user_data
    except Exception as e:
        logger.error(f"Error fetching user data: {str(e)}", exc_info=True)
        return {'error': str(e)}

def add_mailbox(mailbox_id, client_id, client_secret):
    """Add a new mailbox to the user's account."""
    logger.info("Adding mailbox for user: %s, mailbox_id: %s", current_user.username, mailbox_id)
    try:
        new_mailbox = {
            'mailbox_id': mailbox_id,
            'type': 'gmail',
            'credentials': {
                'client_id': client_id,
                'client_secret': client_secret
            }
        }
        users_collection.update_one(
            {"username": current_user.username},
            {"$push": {"mailboxes": new_mailbox}}
        )
        current_user.mailboxes.append(new_mailbox)
        logger.debug("Mailbox added successfully")
        return {'success': True}
    except Exception as e:
        logger.error(f"Error adding mailbox: {str(e)}", exc_info=True)
        return {'error': str(e)}

def change_password(current_password, new_password):
    """Change the user's password."""
    logger.info("Changing password for user: %s", current_user.username)
    try:
        user_data = users_collection.find_one({"username": current_user.username})
        if not bcrypt.check_password_hash(user_data['password_hash'], current_password):
            return {'error': 'Contraseña actual incorrecta'}
        new_password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        users_collection.update_one(
            {"username": current_user.username},
            {"$set": {"password_hash": new_password_hash}}
        )
        logger.debug("Password changed successfully")
        return {'success': True}
    except Exception as e:
        logger.error(f"Error changing password: {str(e)}", exc_info=True)
        return {'error': str(e)}