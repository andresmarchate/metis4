from pymongo import MongoClient
from bson.objectid import ObjectId, InvalidId
from config import MONGO_URI, MONGO_DB_NAME, MONGO_TODOS_COLLECTION, MONGO_USERS_COLLECTION, MONGO_EMAILS_COLLECTION
from services.nlp_service import detect_language
from services.gmail_service import create_draft as create_gmail_draft
from services.imap_service import create_draft as create_imap_draft
from insert_emails import get_credentials_from_db, call_mistral_api
from googleapiclient.discovery import build
from services.cache_service import get_cached_result, cache_result
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

def get_header_value(headers, name):
    logger.debug(f"Extracting header: {name}")
    for header in headers:
        if header['name'].lower() == name.lower():
            logger.debug(f"Found header {name}: {header['value']}")
            return header['value']
    logger.debug(f"Header {name} not found, returning None")
    return None

def get_agatta_stats(username):
    logger.debug(f"Calculating AGATTA stats for user: {username}")
    total_todos = todos_collection.count_documents({"username": username})
    completed_todos = todos_collection.count_documents({"username": username, "completed": True})
    stats = {
        "total_todos": total_todos,
        "completed": completed_todos
    }
    logger.debug(f"Stats calculated: total_todos={total_todos}, completed={completed_todos}")
    return stats

def mark_task_completed(task_id):
    logger.debug(f"Attempting to mark task as completed: {task_id}")
    try:
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

def get_agatta_todos(username, completed=None, page=1, page_size=100):
    query = {"username": username}
    if completed is not None:
        query["completed"] = completed
    todos = todos_collection.find(query).sort("date", -1).skip((page - 1) * page_size).limit(page_size)
    return {"todos": list(todos), "total": todos_collection.count_documents(query)}

def create_draft(task_id, user):
    try:
        todo = todos_collection.find_one({"_id": ObjectId(task_id), "username": user.username})
        if not todo:
            return {'error': 'TODO no encontrado'}
        
        email = emails_collection.find_one({"message_id": todo['message_id']})
        if not email:
            return {'error': 'Correo asociado no encontrado'}
        
        language = detect_language(email['body'])
        
        prompt = f"""
        Genera una respuesta formal y coherente en {language} basada en la siguiente acción propuesta:
        Acción propuesta: {todo['proposed_action']}
        Asunto del correo: {email['subject']}
        Cuerpo del correo: {email['body'][:500]}
        """
        response = call_mistral_api(prompt)
        draft_content = response.strip()
        
        mailbox_id = email['mailbox_id']
        
        user_data = users_collection.find_one({"username": user.username})
        mailbox = next((mb for mb in user_data['mailboxes'] if mb['mailbox_id'] == mailbox_id), None)
        if not mailbox:
            return {'error': 'Buzón no encontrado'}
        
        draft_metadata = {
            'parent_thread_id': email.get('parent_thread_id', email['message_id'])  # Usar message_id como fallback
        }
        
        if mailbox['type'] == 'gmail':
            creds = get_credentials_from_db(user.username, mailbox_id)
            if not creds:
                return {'error': 'Credenciales no encontradas'}
            service = build('gmail', 'v1', credentials=creds)
            draft = create_gmail_draft(service, user.username, email, draft_content, metadata=draft_metadata)
        elif mailbox['type'] == 'imap':
            creds = get_credentials_from_db(user.username, mailbox_id)
            if not creds:
                return {'error': 'Credenciales no encontradas'}
            draft = create_imap_draft(creds, email, draft_content, metadata=draft_metadata)
        else:
            return {'error': 'Tipo de buzón no soportado'}
        
        return {'success': True, 'draft_id': draft['id']}
    except Exception as e:
        logger.error(f"Error creating draft: {str(e)}", exc_info=True)
        return {'error': str(e)}

def get_gmail_service(username, mailbox_id):
    creds = get_credentials_from_db(username, mailbox_id)
    if not creds:
        logger.error(f"No credentials found for mailbox: {mailbox_id}")
        return None
    return build('gmail', 'v1', credentials=creds)

def get_draft_count(username):
    logger.debug(f"Fetching draft count for user: {username}")
    user = users_collection.find_one({"username": username})
    if not user:
        logger.warning(f"User not found: {username}")
        return 0
    active_mailboxes = [mb for mb in user["mailboxes"] if mb.get("agatta_config", {}).get("enabled", False) and mb["type"] == "gmail"]
    total_drafts = 0
    for mailbox in active_mailboxes:
        service = get_gmail_service(username, mailbox["mailbox_id"])
        if service:
            try:
                drafts = service.users().drafts().list(userId='me').execute()
                total_drafts += len(drafts.get('drafts', []))
                logger.debug(f"Draft count for mailbox {mailbox['mailbox_id']}: {len(drafts.get('drafts', []))}")
            except Exception as e:
                logger.error(f"Error fetching drafts for mailbox {mailbox['mailbox_id']}: {str(e)}")
    logger.info(f"Total draft count for user {username}: {total_drafts}")
    return total_drafts

def get_outbox_count(username):
    logger.debug(f"Fetching outbox count for user: {username}")
    user = users_collection.find_one({"username": username})
    if not user:
        logger.warning(f"User not found: {username}")
        return 0
    active_mailboxes = [mb for mb in user["mailboxes"] if mb.get("agatta_config", {}).get("enabled", False) and mb["type"] == "gmail"]
    total_outbox = 0
    for mailbox in active_mailboxes:
        service = get_gmail_service(username, mailbox["mailbox_id"])
        if service:
            try:
                drafts = service.users().drafts().list(userId='me').execute()
                total_outbox += len(drafts.get('drafts', []))
                logger.debug(f"Outbox count for mailbox {mailbox['mailbox_id']}: {len(drafts.get('drafts', []))}")
            except Exception as e:
                logger.error(f"Error fetching outbox for mailbox {mailbox['mailbox_id']}: {str(e)}")
    logger.info(f"Total outbox count for user {username}: {total_outbox}")
    return total_outbox

def get_draft_emails(username):
    cache_key = f"drafts:{username}"
    logger.debug(f"Checking cache for draft emails with key: {cache_key}")
    cached_drafts = get_cached_result(cache_key)
    if cached_drafts:
        logger.info(f"Returning {len(cached_drafts)} cached draft emails for user: {username}")
        return cached_drafts

    logger.debug(f"Fetching draft emails for user: {username} from Gmail")
    user = users_collection.find_one({"username": username})
    if not user:
        logger.warning(f"User not found: {username}")
        return []
    active_mailboxes = [mb for mb in user["mailboxes"] if mb.get("agatta_config", {}).get("enabled", False) and mb["type"] == "gmail"]
    draft_emails = []
    for mailbox in active_mailboxes:
        service = get_gmail_service(username, mailbox["mailbox_id"])
        if service:
            try:
                drafts = service.users().drafts().list(userId='me').execute()
                for draft in drafts.get('drafts', []):
                    draft_msg = service.users().drafts().get(userId='me', id=draft['id']).execute()
                    message = draft_msg['message']
                    headers = message['payload'].get('headers', [])
                    email_data = {
                        'index': draft['id'],
                        'from': 'Yo',
                        'to': get_header_value(headers, 'To') or 'N/A',
                        'subject': get_header_value(headers, 'Subject') or 'Sin Asunto',
                        'date': message.get('internalDate', 'N/A'),
                        'summary': 'Borrador'
                    }
                    draft_emails.append(email_data)
                    logger.debug(f"Draft email added: {draft['id']} with subject: {email_data['subject']}")
            except Exception as e:
                logger.error(f"Error fetching draft emails for mailbox {mailbox['mailbox_id']}: {str(e)}")
    logger.info(f"Fetched {len(draft_emails)} draft emails for user {username}, caching result")
    cache_result(cache_key, draft_emails)
    return draft_emails

def get_outbox_emails(username):
    logger.debug(f"Fetching outbox emails for user: {username}")
    return get_draft_emails(username)  # En Gmail, outbox y drafts son lo mismo