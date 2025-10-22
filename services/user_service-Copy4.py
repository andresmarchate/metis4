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

def add_mailbox(data):
    """Add a new mailbox to the user's account using a data dictionary."""
    logger.info("Adding mailbox for user: %s, mailbox_id: %s, type: %s", 
                current_user.username, data.get('mailbox_id'), data.get('type'))
    try:
        mailbox_id = data.get('mailbox_id')
        mailbox_type = data.get('type')
        logger.debug(f"Extracted mailbox_id: {mailbox_id}, type: {mailbox_type}")

        # Validar campos básicos
        if not mailbox_id or not mailbox_type:
            logger.warning("Missing mailbox_id or type")
            return {'error': 'mailbox_id y type son requeridos'}

        if mailbox_type not in ['gmail', 'imap']:
            logger.warning(f"Unsupported mailbox type: {mailbox_type}")
            return {'error': 'Tipo de buzón no soportado'}

        new_mailbox = {
            'mailbox_id': mailbox_id,
            'type': mailbox_type,
            'credentials': {}
        }

        if mailbox_type == 'gmail':
            client_id = data.get('client_id')
            client_secret = data.get('client_secret')
            if not client_id or not client_secret:
                logger.warning("Missing client_id or client_secret for Gmail")
                return {'error': 'Client ID y Client Secret son requeridos para Gmail'}
            new_mailbox['credentials'] = {
                'client_id': client_id,
                'client_secret': client_secret
            }
        elif mailbox_type == 'imap':
            required_fields = ['server', 'port', 'encryption', 'username', 'password']
            for field in required_fields:
                value = data.get(field)
                if not value or (isinstance(value, str) and value.strip() == ''):
                    logger.warning(f"Field {field} is missing or empty")
                    return {'error': f'El campo {field} es requerido y no puede estar vacío'}

            # Validar que el puerto sea un número entero positivo
            port_value = data.get('port')
            try:
                port = int(port_value)
                if port <= 0:
                    logger.warning(f"Invalid port value: {port_value} (must be positive)")
                    return {'error': 'El puerto debe ser un número entero positivo'}
            except (ValueError, TypeError):
                logger.warning(f"Invalid port value: {port_value} (must be an integer)")
                return {'error': 'El puerto debe ser un número entero válido'}

            # Almacenar la contraseña en texto plano
            plain_password = data.get('password')
            new_mailbox['credentials'] = {
                'server': data.get('server'),
                'port': port,  # Guardar como entero
                'encryption': data.get('encryption'),
                'username': data.get('username'),
                'password': plain_password  # Contraseña en texto plano
            }

            # Campos opcionales para SMTP
            smtp_fields = ['smtp_server', 'smtp_port', 'smtp_encryption', 'smtp_username', 'smtp_password']
            if all(field in data for field in smtp_fields):
                plain_smtp_password = data.get('smtp_password')
                new_mailbox['credentials'].update({
                    'smtp_server': data.get('smtp_server'),
                    'smtp_port': data.get('smtp_port'),
                    'smtp_encryption': data.get('smtp_encryption'),
                    'smtp_username': data.get('smtp_username'),
                    'smtp_password': plain_smtp_password  # Contraseña SMTP en texto plano
                })
                logger.debug("SMTP credentials added")

        # Insertar en la base de datos
        logger.debug("Attempting to insert mailbox into database")
        users_collection.update_one(
            {"username": current_user.username},
            {"$push": {"mailboxes": new_mailbox}}
        )
        current_user.mailboxes.append(new_mailbox)
        logger.debug("Mailbox added successfully to database")
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