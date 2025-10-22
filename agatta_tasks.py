import logging
from pymongo import MongoClient, ASCENDING
from datetime import datetime, timedelta
import hashlib
import json
import re
import requests
import time
import random
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION, MONGO_TODOS_COLLECTION, MONGO_USERS_COLLECTION
from collections import OrderedDict
from services.nlp_service import detect_language  # Asumiendo que existe esta función

# Configuración del logging
logging.basicConfig(filename='agatta_tasks.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Conectar a MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]
tasks_collection = db[MONGO_TODOS_COLLECTION]
users_collection = db[MONGO_USERS_COLLECTION]

# Configuración de Ollama
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral-custom"
OLLAMA_TEMPERATURE = 0.7
OLLAMA_MAX_TOKENS = 512
OLLAMA_CONTEXT_SIZE = 32768

# Caché para respuestas de Ollama
response_cache = OrderedDict()
cache_limit = 1000

def call_mistral_api(prompt):
    prompt_hash = hashlib.md5(prompt.encode('utf-8')).hexdigest()
    if prompt_hash in response_cache:
        response_cache.move_to_end(prompt_hash)
        return response_cache[prompt_hash]

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "temperature": OLLAMA_TEMPERATURE,
        "num_predict": OLLAMA_MAX_TOKENS,
        "num_ctx": OLLAMA_CONTEXT_SIZE
    }
    
    max_retries = 3
    base_delay = 2
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()['response']
            if len(response_cache) >= cache_limit:
                response_cache.popitem(last=False)
            response_cache[prompt_hash] = result
            return result
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1 * base_delay)
                logging.warning(f"Intento {attempt + 1} fallido al contactar con Ollama: {e}. Reintentando en {delay:.2f} segundos...")
                time.sleep(delay)
            else:
                logging.error(f"Error al contactar con Ollama tras {max_retries} intentos: {e}")
                return f'{{"error": "API failure", "message": "{str(e)}"}}'

def safe_parse_json(response, task_id):
    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        logging.error(f"Error al parsear JSON para task_id {task_id}: {str(e)}. Respuesta: {response}")
        return response.strip()

def get_majority_language(thread_emails):
    """Detecta el idioma predominante en el hilo de correos."""
    languages = [detect_language(email.get("body", "")) for email in thread_emails]
    language_count = {}
    for lang in languages:
        language_count[lang] = language_count.get(lang, 0) + 1
    majority_lang = max(language_count, key=language_count.get, default="es")
    return majority_lang

def generate_thread_summary(message_id, user_email):
    thread_emails = get_thread_emails(message_id)
    if not thread_emails:
        return "Hilo no encontrado"

    thread_text = "\n".join([f"De: {e.get('from', 'Desconocido')} Para: {e.get('to', 'Desconocido')} - {e.get('body', '')}" for e in thread_emails if e])
    majority_lang = get_majority_language(thread_emails)

    prompt = f"""
    Genera un resumen conciso de 20 palabras del siguiente hilo de correos en {majority_lang}.
    El usuario propietario del buzón es {user_email}, quien envía correos salientes y recibe correos entrantes.
    Identifica claramente quién envía y recibe cada correo para evitar confusiones en los roles.
    Devuelve EXCLUSIVAMENTE un objeto JSON con la clave 'summary'.
    Ejemplo: {{"summary": "Fernando preguntó sobre SIEM, Andres respondió explicando."}}
    Hilo:
    {thread_text[:2000]}
    """

    response = call_mistral_api(prompt)
    parsed_response = safe_parse_json(response, message_id)
    if isinstance(parsed_response, dict) and "summary" in parsed_response:
        return parsed_response["summary"]
    return "Error en el resumen"

def generate_proposed_action(message_id, user_email):
    email = emails_collection.find_one({"message_id": message_id})
    if not email:
        return "Correo no encontrado"

    thread_emails = get_thread_emails(message_id)
    last_email = max(thread_emails, key=lambda x: x["date"]) if thread_emails else email
    majority_lang = get_majority_language(thread_emails)

    prompt = f"""
    Sugiere una acción a realizar en {majority_lang} basada en este correo y su hilo.
    El usuario propietario del buzón es {user_email}, quien envía correos salientes y recibe correos entrantes.
    Identifica claramente los roles: si el último correo (De: {last_email.get('from', 'Desconocido')}, Fecha: {last_email.get('date', 'Sin fecha')}) es del usuario, no sugieras acciones, retorna {{"action": "Ninguna acción pendiente"}}.
    Devuelve EXCLUSIVAMENTE un objeto JSON con la clave 'action'.
    Ejemplo: {{"action": "Revisar la explicación de Andres sobre SIEM."}}
    Correo:
    Asunto: {email.get('subject', 'Sin asunto')}
    De: {email.get('from', 'Desconocido')}
    Para: {email.get('to', 'Desconocido')}
    Cuerpo: {email.get('body', '')[:1000]}
    """

    response = call_mistral_api(prompt)
    parsed_response = safe_parse_json(response, message_id)
    if isinstance(parsed_response, dict) and "action" in parsed_response:
        return parsed_response["action"]
    return "Error en la acción propuesta"

def assign_parent_thread_id(thread_emails):
    if not thread_emails:
        return None
    
    for email in thread_emails:
        if email.get("parent_thread_id"):
            return email["parent_thread_id"]
    
    sorted_emails = sorted(thread_emails, key=lambda x: x["date"])
    parent_thread_id = sorted_emails[0]["message_id"]
    
    for email in thread_emails:
        emails_collection.update_one(
            {"message_id": email["message_id"]},
            {"$set": {"parent_thread_id": parent_thread_id}}
        )
    
    logging.info(f"Asignado parent_thread_id {parent_thread_id} al hilo con {len(thread_emails)} correos")
    return parent_thread_id

def get_thread_emails(message_id):
    email = emails_collection.find_one({"message_id": message_id})
    if not email:
        return []

    thread_emails = []
    parent_thread_id = email.get("parent_thread_id", None)
    
    if parent_thread_id:
        thread_emails = list(emails_collection.find({"parent_thread_id": parent_thread_id}))
    
    if not thread_emails or len(thread_emails) == 1:
        if email.get("in_reply_to"):
            parent = emails_collection.find_one({"message_id": email["in_reply_to"]})
            if parent:
                thread_emails.append(parent)
        replies = list(emails_collection.find({"in_reply_to": message_id}))
        thread_emails.extend(replies)
        if not thread_emails:
            thread_emails = [email]
    
    if len(thread_emails) <= 1:
        cleaned_subject = re.sub(r'^(Re:|Fwd:)\s*', '', email['subject'], flags=re.IGNORECASE).strip()
        thread_emails = list(emails_collection.find({
            "subject": {"$regex": f"^(Re:|Fwd:)?\s*{re.escape(cleaned_subject)}", "$options": "i"},
            "mailbox_id": email['mailbox_id']
        }))
    
    if thread_emails:
        assign_parent_thread_id(thread_emails)
    
    return thread_emails

def get_users_with_agatta_enabled():
    users_with_agatta = []
    for user in users_collection.find():
        active_mailboxes = [
            {"mailbox_id": mb["mailbox_id"], "auto_reply_mode": mb.get("agatta_config", {}).get("auto_reply_mode", "none")}
            for mb in user.get("mailboxes", []) if mb.get("agatta_config", {}).get("enabled", False)
        ]
        if active_mailboxes:
            users_with_agatta.append({
                "username": user["username"],
                "active_mailboxes": active_mailboxes
            })
    return users_with_agatta

def analyze_emails_for_tasks(username, mailbox_id, days_back=30):
    cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
    query = {
        "date": {"$gte": cutoff_date},
        "requires_response": True,
        "completed": {"$ne": True},
        "mailbox_id": mailbox_id,
        "advertisement": {"$ne": True}  # Excluir correos de publicidad
    }
    user_email = next((mb["mailbox_id"] for mb in users_collection.find_one({"username": username})["mailboxes"] if mb["mailbox_id"] == mailbox_id), None)
    
    for email in emails_collection.find(query):
        # Saltar correos enviados por el usuario
        if email["from"] == user_email:
            logging.info(f"No se crea tarea para {email.get('subject', 'Sin asunto')}: correo enviado por el usuario {username}")
            continue
        
        thread_emails = get_thread_emails(email["message_id"])
        if thread_emails:
            last_email = max(thread_emails, key=lambda x: x["date"])
            if last_email["from"] == user_email:
                logging.info(f"No se crea tarea para {email.get('subject', 'Sin asunto')}: último correo enviado por el usuario {username}")
                continue  # No crear tarea si el último correo es del usuario
        
        proposed_action = generate_proposed_action(email["message_id"], user_email)
        if proposed_action == "Ninguna acción pendiente":
            logging.info(f"No se crea tarea para {email.get('subject', 'Sin asunto')}: no hay acción pendiente")
            continue
        
        task = {
            "username": username,
            "message_id": email["message_id"],
            "mailbox_id": mailbox_id,
            "subject": email.get("subject", "Sin asunto"),
            "from": email.get("from", "Desconocido"),
            "date": email["date"],
            "due_date": (datetime.fromisoformat(email["date"]) + timedelta(days=7)).isoformat(),
            "completed": False,
            "suggested_completed": email.get("responded", False),
            "draft_id": None,
            "thread_summary": generate_thread_summary(email["message_id"], user_email),
            "proposed_action": proposed_action,
            "parent_thread_id": email.get("parent_thread_id", None)
        }
        
        tasks_collection.update_one(
            {"message_id": email["message_id"]},
            {"$set": task},
            upsert=True
        )
        logging.info(f"Tarea generada para correo: {email.get('subject', 'Sin asunto')} en buzón {mailbox_id} de usuario {username}")
    
    # Revisar y completar TODOs existentes después del procesamiento
    review_and_complete_todos(username, mailbox_id)

def review_and_complete_todos(username, mailbox_id):
    user_email = next((mb["mailbox_id"] for mb in users_collection.find_one({"username": username})["mailboxes"] if mb["mailbox_id"] == mailbox_id), None)
    todos = tasks_collection.find({"username": username, "mailbox_id": mailbox_id, "completed": False})
    for todo in todos:
        thread_emails = get_thread_emails(todo["message_id"])
        if not thread_emails:
            continue
        last_email = max(thread_emails, key=lambda x: x["date"])
        if last_email["from"] == user_email:
            tasks_collection.update_one(
                {"_id": todo["_id"]},
                {"$set": {"completed": True}}
            )
            logging.info(f"TODO {todo['_id']} marcado como completado: último correo enviado por el usuario {username}")
        elif len(thread_emails) == 1 and thread_emails[0]["from"] == user_email:
            tasks_collection.update_one(
                {"_id": todo["_id"]},
                {"$set": {"completed": True}}
            )
            logging.info(f"TODO {todo['_id']} marcado como completado: único correo enviado por el usuario {username}")

def process_all_users():
    users_with_agatta = get_users_with_agatta_enabled()
    for user in users_with_agatta:
        username = user["username"]
        active_mailboxes = user["active_mailboxes"]
        logging.info(f"Procesando usuario: {username} con buzones activos: {active_mailboxes}")
        for mailbox in active_mailboxes:
            mailbox_id = mailbox["mailbox_id"]
            analyze_emails_for_tasks(username, mailbox_id)

if __name__ == "__main__":
    try:
        client.server_info()
        logging.info("Conexión a MongoDB establecida correctamente")
    except Exception as e:
        logging.error(f"Error al conectar a MongoDB: {e}")
        exit(1)
    
    process_all_users()