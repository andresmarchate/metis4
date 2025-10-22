from pymongo import MongoClient
from bson.objectid import ObjectId, InvalidId
from config import MONGO_URI, MONGO_DB_NAME, MONGO_TODOS_COLLECTION, MONGO_USERS_COLLECTION, MONGO_EMAILS_COLLECTION
from services.nlp_service import detect_language
from services.gmail_service import create_draft as create_gmail_draft
from services.imap_service import create_draft as create_imap_draft
from insert_emails import get_credentials_from_db, call_mistral_api
from googleapiclient.discovery import build
import logging

logger = logging.getLogger('email_search_app.agatta_service')
logger.setLevel(logging.DEBUG)
file_handler = logging.handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
todos_collection = db[MONGO_TODOS_COLLECTION]
users_collection = db[MONGO_USERS_COLLECTION]
emails_collection = db[MONGO_EMAILS_COLLECTION]

def get_agatta_stats(username):
    total_todos = todos_collection.count_documents({"username": username})
    completed_todos = todos_collection.count_documents({"username": username, "completed": True})
    return {
        "total_todos": total_todos,
        "completed": completed_todos
    }

def mark_task_completed(task_id):
    logger.debug(f"Attempting to mark task as completed: {task_id}")
    try:
        # Convertir task_id a ObjectId si es una cadena
        if isinstance(task_id, str):
            task_id = ObjectId(task_id)
        result = todos_collection.update_one(
            {"_id": task_id},
            {"$set": {"completed": True}}
        )
        if result.modified_count > 0:
            logger.info(f"Task {task_id} marked as completed")
            return {"success": True}
        else:
            logger.warning(f"Task not found: {task_id}")
            return {"error": "Task not found"}
    except InvalidId:
        logger.error(f"Invalid task_id: {task_id}")
        return {"error": "Invalid task_id"}
    except Exception as e:
        logger.error(f"Unexpected error marking task as completed: {str(e)}", exc_info=True)
        return {"error": str(e)}

def get_agatta_todos(username):
    todos = todos_collection.find({"username": username})
    return list(todos)

def create_draft(task_id, user):
    """Create a draft email based on the proposed action of a TODO."""
    try:
        todo = todos_collection.find_one({"_id": ObjectId(task_id), "username": user.username})
        if not todo:
            return {'error': 'TODO no encontrado'}
        
        # Obtener el correo asociado al TODO
        email = emails_collection.find_one({"message_id": todo['message_id']})
        if not email:
            return {'error': 'Correo asociado no encontrado'}
        
        # Detectar el idioma del último correo del hilo
        language = detect_language(email['body'])
        
        # Generar la respuesta utilizando Ollama
        prompt = f"""
        Genera una respuesta formal y coherente en {language} basada en la siguiente acción propuesta:
        Acción propuesta: {todo['proposed_action']}
        Asunto del correo: {email['subject']}
        Cuerpo del correo: {email['body'][:500]}
        """
        response = call_mistral_api(prompt)
        draft_content = response.strip()
        
        # Obtener el buzón del último correo
        mailbox_id = email['mailbox_id']
        
        # Recuperar las credenciales del buzón
        user_data = users_collection.find_one({"username": user.username})
        mailbox = next((mb for mb in user_data['mailboxes'] if mb['mailbox_id'] == mailbox_id), None)
        if not mailbox:
            return {'error': 'Buzón no encontrado'}
        
        if mailbox['type'] == 'gmail':
            creds = get_credentials_from_db(user.username, mailbox_id)
            if not creds:
                return {'error': 'Credenciales no encontradas'}
            service = build('gmail', 'v1', credentials=creds)
            draft = create_gmail_draft(service, user.username, email, draft_content)
        elif mailbox['type'] == 'imap':
            creds = get_credentials_from_db(user.username, mailbox_id)
            if not creds:
                return {'error': 'Credenciales no encontradas'}
            draft = create_imap_draft(creds, email, draft_content)
        else:
            return {'error': 'Tipo de buzón no soportado'}
        
        return {'success': True, 'draft_id': draft['id']}
    except Exception as e:
        logger.error(f"Error creating draft: {str(e)}", exc_info=True)
        return {'error': str(e)}