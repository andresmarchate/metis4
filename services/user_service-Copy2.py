# Artifact ID: 2b3c4d5e-6f7g-8h9i-0j1k-l2m3n4o5p6q7
# Version: n7o8p9q0-r1s2-3456-n9o0-p1q2r3s4t5
import logging
from logging import handlers

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

def get_user_data():
    """Return static user data."""
    logger.info("Fetching user data")
    try:
        user_data = {
            'name': 'Andrés Marchante Tirado',
            'mailbox': 'Gmail',
            'email': 'andres.m.tirado@gmail.com'
        }
        logger.debug(f"User data: {user_data}")
        return user_data
    except Exception as e:
        logger.error(f"Error fetching user data: {str(e)}", exc_info=True)
        return {'error': str(e)}
