from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.mime.text import MIMEText
import base64
import re
import logging

# Configuración del logging
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

def extract_email_address(text):
    """Extrae la dirección de correo electrónico de un texto usando una expresión regular."""
    if not text or not isinstance(text, str):
        logger.warning(f"Campo 'from' inválido o vacío: {text}")
        return None
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text, re.IGNORECASE)
    if email_match:
        return email_match.group(0)
    logger.warning(f"No se pudo extraer una dirección de correo válida de: {text}")
    return None

def create_draft(service, user_id, email, proposed_action, metadata=None):
    """Crea un borrador de correo en Gmail."""
    try:
        # Extraer la dirección de correo del campo 'from'
        to_address = extract_email_address(email['from'])
        if not to_address:
            raise ValueError(f"No se pudo extraer una dirección de correo válida del campo 'from': {email['from']}")

        # Crear el mensaje con la dirección extraída
        message = MIMEText(proposed_action)
        message['to'] = to_address
        message['from'] = user_id
        message['subject'] = f"Re: {email['subject']}"

        # Configurar threadId si está disponible
        thread_id = None
        if metadata and 'parent_thread_id' in metadata:
            thread_id = metadata['parent_thread_id']
        elif 'thread_id' in email:
            thread_id = email['thread_id']

        # Codificar el mensaje
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        draft_body = {'message': {'raw': raw}}

        if thread_id:
            draft_body['message']['threadId'] = thread_id

        # Crear el borrador usando la API de Gmail
        draft = service.users().drafts().create(userId='me', body=draft_body).execute()
        logger.info(f"Borrador creado en Gmail para el correo: {email['subject']}")
        return draft

    except HttpError as error:
        logger.error(f"Error al crear el borrador en Gmail: {error}")
        raise
    except ValueError as ve:
        logger.error(f"Error de validación al crear el borrador: {str(ve)}")
        raise
    except Exception as e:
        logger.error(f"Error inesperado al crear el borrador: {str(e)}", exc_info=True)
        raise