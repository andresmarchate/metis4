import imaplib
from email.message import EmailMessage
import logging

logger = logging.getLogger('email_search_app.imap_service')
logger.setLevel(logging.DEBUG)
file_handler = logging.handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

def create_draft(creds, email, proposed_action, metadata=None):
    """Create a draft email in an IMAP mailbox."""
    try:
        imap = imaplib.IMAP4_SSL(creds['server'], creds['port'])
        imap.login(creds['username'], creds['password'])
        imap.select('Drafts')
        
        msg = EmailMessage()
        msg['To'] = email['from']
        msg['From'] = creds['username']
        msg['Subject'] = f"Re: {email['subject']}"
        msg.set_content(proposed_action)
        
        # Configurar encabezados para asociar al hilo si hay metadata o message_id
        if metadata and 'parent_thread_id' in metadata and email.get('message_id'):
            msg['In-Reply-To'] = email['message_id']
            msg['References'] = f"{email['message_id']} {metadata['parent_thread_id']}"
        elif email.get('message_id'):
            msg['In-Reply-To'] = email['message_id']
            msg['References'] = email['message_id']
        
        imap.append('Drafts', None, None, msg.as_bytes())
        imap.logout()
        logger.info(f"Draft created in IMAP for email: {email['subject']}")
        return {'id': 'IMAP_DRAFT'}  # IMAP does not return a draft ID like Gmail
    except Exception as e:
        logger.error(f"Error creating IMAP draft: {str(e)}", exc_info=True)
        raise