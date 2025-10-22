from googleapiclient.discovery import build
from email.mime.text import MIMEText
import base64
import logging

logger = logging.getLogger('email_search_app.gmail_service')
logger.setLevel(logging.DEBUG)
file_handler = logging.handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

def create_draft(service, user_id, email, proposed_action):
    """Create a draft email in Gmail."""
    try:
        message = MIMEText(proposed_action)
        message['to'] = email['from']
        message['from'] = user_id
        message['subject'] = f"Re: {email['subject']}"
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        draft = service.users().drafts().create(userId='me', body={'message': {'raw': raw}}).execute()
        logger.info(f"Draft created in Gmail for email: {email['subject']}")
        return draft
    except Exception as e:
        logger.error(f"Error creating Gmail draft: {str(e)}", exc_info=True)
        raise