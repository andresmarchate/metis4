import base64
import mimetypes
import os
from PyPDF2 import PdfReader
from PyPDF2.errors import FileNotDecryptedError
import pytesseract
from PIL import Image
from docx import Document as DocxDocument
import openpyxl
import json
import re
from pymongo import MongoClient, TEXT, ASCENDING
from pymongo.errors import OperationFailure
from bson import Binary, ObjectId
import hashlib
import requests
from collections import OrderedDict
from sentence_transformers import SentenceTransformer
import numpy as np
import zlib
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import RefreshError
import time
import random
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import argparse
import logging
from json_repair import repair_json
import imaplib
import email
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
import pickle
from bs4 import BeautifulSoup
from elasticsearch import Elasticsearch

# Configuración del logging
logging.basicConfig(filename='email_insertion.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Conectar a MongoDB
client = MongoClient('localhost', 27017)
db = client['email_database_metis2']
emails_collection = db['emails']
users_collection = db['users']

# Cargar modelo de embeddings en la CPU
embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2', device='cpu')

# Configuración de Tesseract
pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

# Archivo y configuración del caché
cache_file = 'mistral_cache.pkl'
cache_limit = 1000

# Cargar caché
if os.path.exists(cache_file):
    with open(cache_file, 'rb') as f:
        response_cache = pickle.load(f)
    if not isinstance(response_cache, OrderedDict):
        response_cache = OrderedDict(response_cache)
else:
    response_cache = OrderedDict()

# Archivo para el modelo bayesiano
bayesian_model_file = 'bayesian_advertisement_model.pkl'

# Lista de remitentes cualificados
qualified_senders = [
    'ayuntamiento@',
    'agenciatributaria@',
    'trafico@',
    # Añadir más según sea necesario
]

# Configuración de Elasticsearch desde config.py
from config import ELASTICSEARCH_HOST, ELASTICSEARCH_PORT

es = Elasticsearch([{'host': ELASTICSEARCH_HOST, 'port': ELASTICSEARCH_PORT, 'scheme': 'http'}])

def parse_email_date(date_str):
    date_str = date_str.strip()
    iso_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$')
    malformed_iso_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}T fell asleep waiting\d{2}:\d{2}$')
    partial_tz_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}$')
    minimal_date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    
    if iso_pattern.match(date_str):
        try:
            return datetime.fromisoformat(date_str)
        except ValueError as e:
            logging.error(f"Failed to parse ISO 8601 date: {date_str}, error: {e}")
            return None
    
    if malformed_iso_pattern.match(date_str):
        try:
            date_str_with_tz = f"{date_str}+00:00"
            return datetime.fromisoformat(date_str_with_tz)
        except ValueError:
            return None
    
    if partial_tz_pattern.match(date_str):
        try:
            date_str_with_tz = f"{date_str}:00"
            return datetime.fromisoformat(date_str_with_tz)
        except ValueError:
            return None
    
    if minimal_date_pattern.match(date_str):
        try:
            date_str_with_time = f"{date_str}T00:00:00+00:00"
            return datetime.fromisoformat(date_str_with_time)
        except ValueError:
            return None
    
    date_str_clean = re.sub(r'\s+\([A-Za-z]+\)$', '', date_str)
    try:
        return parsedate_to_datetime(date_str_clean)
    except (ValueError, TypeError):
        return None

def migrate_date_formats(dry_run=False):
    logging.info("Starting date format migration...")
    try:
        cursor = emails_collection.find({}, {'_id': 1, 'message_id': 1, 'index': 1, 'date': 1})
        total_updated = 0
        total_skipped = 0
        total_processed = 0
        iso_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$')
        
        for doc in cursor:
            total_processed += 1
            doc_id = str(doc['_id'])
            message_id = doc.get('message_id', 'unknown')
            index = doc.get('index', 'unknown')
            raw_date = doc.get('date', '')
            
            if not raw_date or raw_date == 'Unknown':
                total_skipped += 1
                continue
            
            if iso_pattern.match(raw_date):
                try:
                    datetime.fromisoformat(raw_date)
                    total_skipped += 1
                    continue
                except ValueError:
                    pass
            
            parsed_date = parse_email_date(raw_date)
            if not parsed_date:
                total_skipped += 1
                continue
            iso_date = parsed_date.isoformat()
            if not dry_run:
                result = emails_collection.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'date': iso_date}}
                )
                if result.modified_count > 0:
                    total_updated += 1
            else:
                total_updated += 1
        
        logging.info(f"Date migration completed: {total_updated} documents updated, {total_skipped} documents skipped, {total_processed} documents processed")
    except Exception as e:
        logging.error(f"Error during date migration: {e}")

def initialize_collection():
    existing_indexes = {index['name'] for index in emails_collection.list_indexes()}
    
    try:
        for index in emails_collection.list_indexes():
            if index['name'] != '_id_' and 'text' in index['key']:
                emails_collection.drop_index(index['name'])
    except Exception:
        pass

    if 'text_index' not in existing_indexes:
        emails_collection.create_index([
            ('from', TEXT),
            ('to', TEXT),
            ('subject', TEXT),
            ('body', TEXT),
            ('headers_text', TEXT),
            ('attachments', TEXT),
            ('attachments_content', TEXT),
            ('summary', TEXT),
            ('relevant_terms_array', TEXT),
            ('semantic_domain', TEXT)
        ], name='text_index', default_language='spanish')
    if 'date_index' not in existing_indexes:
        emails_collection.create_index([('date', ASCENDING)], name='date_index')
    if 'message_id_1' not in existing_indexes:
        emails_collection.create_index([('message_id', ASCENDING)], unique=True, name='message_id_1')
    if 'common_filters_index' not in existing_indexes:
        emails_collection.create_index([
            ('from', ASCENDING),
            ('to', ASCENDING),
            ('date', ASCENDING),
            ('relevant_terms.semantic_domain', ASCENDING)
        ], name='common_filters_index')
    if 'parent_thread_index' not in existing_indexes:
        emails_collection.create_index([('parent_thread_id', ASCENDING)], name='parent_thread_index')
    if 'index_1' not in existing_indexes:
        emails_collection.create_index([('index', ASCENDING)], unique=True, sparse=True, name='index_1')
    if 'classification_index' not in existing_indexes:
        emails_collection.create_index([
            ('requires_response', ASCENDING),
            ('urgent', ASCENDING),
            ('important', ASCENDING),
            ('advertisement', ASCENDING),
            ('responded', ASCENDING)
        ], name='classification_index')

def get_credentials_from_db(username, mailbox_id):
    user = users_collection.find_one({"username": username})
    if not user:
        logging.error(f"Usuario {username} no encontrado")
        return None
    mailbox = next((mb for mb in user['mailboxes'] if mb['mailbox_id'] == mailbox_id), None)
    if not mailbox:
        logging.error(f"Buzón {mailbox_id} no encontrado para usuario {username}")
        return None
    
    if mailbox['type'] == 'gmail':
        if 'credentials' not in mailbox or not mailbox['credentials']:
            logging.info(f"No se encontraron credenciales para {mailbox_id}, iniciando autorización...")
            return authorize_and_save_credentials(username, mailbox_id)
        
        creds_data = mailbox['credentials']
        required_fields = ['client_id', 'client_secret', 'token_uri', 'refresh_token']
        missing_fields = [field for field in required_fields if field not in creds_data or not creds_data[field]]
        if missing_fields:
            logging.error(f"Faltan campos requeridos en las credenciales para {mailbox_id}: {missing_fields}")
            return authorize_and_save_credentials(username, mailbox_id)
        
        try:
            creds = Credentials(
                token=creds_data.get('access_token'),
                refresh_token=creds_data['refresh_token'],
                token_uri=creds_data['token_uri'],
                client_id=creds_data['client_id'],
                client_secret=creds_data['client_secret'],
                scopes=creds_data.get('scopes', ['https://www.googleapis.com/auth/gmail.readonly'])
            )
            if not creds.valid:
                try:
                    creds.refresh(Request())
                    update_credentials_in_db(username, mailbox_id, creds)
                    logging.info(f"Credenciales refrescadas exitosamente para {mailbox_id}")
                except RefreshError as e:
                    logging.error(f"Error al refrescar token para {mailbox_id}: {e}")
                    if 'invalid_grant' in str(e):
                        logging.info(f"Refresh token inválido para {mailbox_id}, iniciando reautorización interactiva...")
                        return authorize_and_save_credentials(username, mailbox_id)
                    raise
            return creds
        except Exception as e:
            logging.error(f"Error al construir o validar credenciales para {mailbox_id}: {e}")
            return authorize_and_save_credentials(username, mailbox_id)
    elif mailbox['type'] == 'imap':
        if 'credentials' not in mailbox:
            logging.error(f"No se encontraron credenciales para {mailbox_id}")
            return None
        return {
            'server': mailbox['credentials'].get('server'),
            'port': mailbox['credentials'].get('port'),
            'encryption': mailbox['credentials'].get('encryption'),
            'username': mailbox['credentials'].get('username'),
            'password': mailbox['credentials'].get('password')
        }
    else:
        logging.error(f"Tipo de buzón no soportado: {mailbox['type']}")
        return None

def update_credentials_in_db(username, mailbox_id, creds):
    users_collection.update_one(
        {"username": username, "mailboxes.mailbox_id": mailbox_id},
        {"$set": {
            "mailboxes.$.credentials.access_token": creds.token,
            "mailboxes.$.credentials.refresh_token": creds.refresh_token,
            "mailboxes.$.credentials.token_expiry": creds.expiry.isoformat() if creds.expiry else None,
            "mailboxes.$.credentials.client_id": creds.client_id,
            "mailboxes.$.credentials.client_secret": creds.client_secret,
            "mailboxes.$.credentials.token_uri": creds.token_uri,
            "mailboxes.$.credentials.scopes": creds.scopes,
        }}
    )
    logging.info(f"Credenciales actualizadas en MongoDB para {mailbox_id}")

def authorize_and_save_credentials(username, mailbox_id):
    user = users_collection.find_one({"username": username})
    mailbox = next((mb for mb in user['mailboxes'] if mb['mailbox_id'] == mailbox_id), None)
    if not mailbox or 'credentials' not in mailbox:
        logging.error(f"Datos de autorización incompletos para {mailbox_id}")
        return None
    
    creds_data = mailbox['credentials']
    required_fields = ['client_id', 'client_secret']
    if not all(field in creds_data for field in required_fields):
        logging.error(f"Faltan campos requeridos en las credenciales de {mailbox_id}: {required_fields}")
        return None
    
    client_config = {
        "installed": {
            "client_id": creds_data['client_id'],
            "client_secret": creds_data['client_secret'],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080"]
        }
    }
    try:
        flow = InstalledAppFlow.from_client_config(
            client_config,
            scopes=[
                'https://www.googleapis.com/auth/gmail.readonly',
                'https://www.googleapis.com/auth/gmail.compose'
            ],
            redirect_uri="http://localhost:8080"
        )
        creds = flow.run_local_server(
            host='localhost',
            port=8080,
            prompt='consent',
            open_browser=True,
            access_type='offline'
        )
        if not creds.refresh_token:
            logging.error(f"No se obtuvo un refresh_token para {mailbox_id} durante la autorización")
            return None
        update_credentials_in_db(username, mailbox_id, creds)
        logging.info(f"Nuevas credenciales obtenidas y guardadas para {mailbox_id}")
        return creds
    except Exception as e:
        logging.error(f"Error durante la autorización interactiva para {mailbox_id}: {e}")
        return None

def build_service(creds):
    return build('gmail', 'v1', credentials=creds)

def text_optimization(text):
    text = text.lower()
    text = re.sub('<[^<]+?>', '', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:10000]

def text_optimization_attachments(text):
    text = text.lower()
    text = re.sub('<[^<]+?>', '', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:1000]

def generate_embedding(subject, body, summary):
    text = f"{subject or ''} {body or ''} {summary or ''}".strip()
    if not text:
        return None
    try:
        embedding = embedding_model.encode(text).tolist()
        return Binary(zlib.compress(np.array(embedding, dtype=np.float32).tobytes()))
    except Exception as e:
        logging.error(f"Error al generar embedding: {e}")
        return None

def infer_domain_heuristically(subject, body):
    text = f"{subject} {body}".lower()
    if "encuesta" in text or "feedback" in text or "satisfacción" in text:
        return "feedback", 0.7
    elif "viaje" in text or "reserva" in text or "hotel" in text:
        return "viajes", 0.7
    elif "negocio" in text or "propuesta" in text or "contrato" in text:
        return "negocios", 0.7
    elif "promoción" in text or "oferta" in text or "descuento" in text:
        return "promociones", 0.7
    elif "técnico" in text or "soporte" in text or "incidencia" in text:
        return "técnico", 0.7
    else:
        return "general", 0.5

def classify_heuristically(response_text):
    classifications = {
        'requires_response': False,
        'urgent': False,
        'important': False,
        'advertisement': False
    }
    if re.search(r'"requires_response"\s*:\s*true', response_text, re.IGNORECASE):
        classifications['requires_response'] = True
    if re.search(r'"urgent"\s*:\s*true', response_text, re.IGNORECASE):
        classifications['urgent'] = True
    if re.search(r'"important"\s*:\s*true', response_text, re.IGNORECASE):
        classifications['important'] = True
    if re.search(r'"advertisement"\s*:\s*true', response_text, re.IGNORECASE):
        classifications['advertisement'] = True
    return classifications

def is_likely_json(text):
    text = text.strip()
    if not text or len(text) < 2:
        return False
    if (text.startswith('{') and text.endswith('}')) or (text.startswith('[') and text.endswith(']')):
        content = text[1:-1].strip()
        return bool(content and (':' in text or ',' in text or (text.startswith('[') and len(content) > 0)))
    return False

def extract_json_from_text(text):
    if isinstance(text, list):
        for item in text:
            if is_likely_json(item):
                return item
            elif '{' in item:
                partial_json = item[item.index('{'):] + '}'
                if is_likely_json(partial_json):
                    return partial_json
        return None
    json_pattern = re.compile(r'(\{[^{}]*\}|\[[^\[\]]*\])', re.DOTALL)
    matches = json_pattern.findall(text)
    if matches:
        for match in sorted(matches, key=len, reverse=True):
            if is_likely_json(match):
                return match
    if '{' in text and '}' not in text:
        partial_json = text[text.index('{'):] + '}'
        if is_likely_json(partial_json):
            return partial_json
    return None

def clean_json(raw_string):
    cleaned = re.sub(r'\t', ' ', raw_string)
    cleaned = re.sub(r'//.*$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^\s*[\r\n]+', '', cleaned, flags=re.MULTILINE)
    if not cleaned.startswith('{'):
        cleaned = '{' + cleaned
    brace_count = cleaned.count('{') - cleaned.count('}')
    if brace_count > 0:
        cleaned += '}' * brace_count
    cleaned = re.sub(r'(\w+)\s*:', r'"\1":', cleaned)
    cleaned = re.sub(r',\s*([\]}])', r'\1', cleaned)
    return "\n".join([line.strip() for line in cleaned.splitlines() if line.strip()])

def safe_parse_json(response_text, message_id, subject):
    if isinstance(response_text, list):
        for item in response_text:
            parsed = safe_parse_json(item, message_id, subject)
            if parsed and "error" not in parsed:
                return parsed
        return {"error": "No valid JSON in list", "original": str(response_text[:200])}
    
    response_text = response_text.strip()
    if not response_text:
        logging.error(f"Respuesta vacía para message_id {message_id}, subject '{subject}'")
        return {"error": "Empty response"}

    if not is_likely_json(response_text):
        possible_json = extract_json_from_text(response_text)
        if not possible_json:
            logging.error(f"No se encontró JSON válido en la respuesta para message_id {message_id}, subject '{subject}': {response_text[:200]}")
            return {"error": "No valid JSON found", "original": response_text[:200]}
        response_text = possible_json

    attempts = [
        response_text,
        clean_json(response_text),
        repair_json(response_text),
        f'{{"error": "Reparación fallida", "original": "{response_text[:200]}"}}'
    ]
    
    for i, attempt in enumerate(attempts):
        try:
            parsed = json.loads(attempt)
            if i > 0:
                logging.info(f"Reparación exitosa en intento {i+1} para message_id {message_id}, subject '{subject}'")
            return parsed
        except json.JSONDecodeError as e:
            if i == len(attempts) - 1:
                logging.error(f"Fallo total al parsear JSON para message_id {message_id}, subject '{subject}': {e}. Respuesta: {response_text[:500]}")
                return {"error": "Parse failure", "original": response_text[:200]}
            continue

def process_api_response(response, message_id, subject, expected_keys):
    if response is None or isinstance(response, (str, int, float)):
        logging.error(f"Respuesta inválida para message_id {message_id}, subject '{subject}': {response}")
        return None
    if isinstance(response, list):
        for item in response:
            if isinstance(item, dict) and all(key in item for key in expected_keys):
                return item
            elif isinstance(item, str):
                try:
                    parsed_item = json.loads(item)
                    if isinstance(parsed_item, dict) and all(key in parsed_item for key in expected_keys):
                        return parsed_item
                except json.JSONDecodeError:
                    continue
        logging.warning(f"No se encontró un JSON válido en la lista para message_id {message_id}, subject '{subject}': {response}")
        return None
    if isinstance(response, dict):
        if "error" in response:
            logging.warning(f"Respuesta con error para message_id {message_id}, subject '{subject}': {response}")
            return None
        if all(key in response for key in expected_keys):
            return response
        logging.error(f"Respuesta no contiene claves esperadas {expected_keys} para message_id {message_id}, subject '{subject}': {response}")
    return None

def infer_semantic_domain(subject, body, attachments_content, message_id):
    text = f"{subject or ''} {body or ''} {' '.join(attachments_content) or ''}".strip()
    if not text:
        return 'general', 0.5

    prompt = f"""
    Analiza el siguiente texto de un correo electrónico y determina el dominio semántico más adecuado (ejemplo: "viajes", "negocios", "personal", "promociones", "técnico", "general").
    Devuelve EXCLUSIVAMENTE un objeto JSON con:
    - "semantic_domain": El dominio semántico identificado (cadena vacía si no se puede determinar).
    - "confidence": Valor entre 0 y 1 que indica la confianza en la selección.

    Texto:
    {text[:2000]}
    """

    response = call_mistral_api(prompt)
    parsed_response = safe_parse_json(response, message_id, subject)
    processed_response = process_api_response(parsed_response, message_id, subject, ['semantic_domain', 'confidence'])
    if processed_response:
        return processed_response['semantic_domain'] or 'general', processed_response['confidence']
    logging.warning(f"No se pudo inferir dominio semántico para message_id {message_id}, subject '{subject}'. Usando heurística.")
    return infer_domain_heuristically(subject, body)

def classify_email(email, message_id, top_senders):
    subject = email.get('subject', '')
    body = email.get('body', '')
    attachments_content = ' '.join(email.get('attachments_content', []))
    from_ = email.get('from', '')

    text = f"{subject} {body} {attachments_content}".strip()
    if not text:
        return {'requires_response': False, 'urgent': False, 'important': False, 'advertisement': False}

    # Verificar encabezados para urgencia e importancia
    headers = email.get('headers', {})
    priority = headers.get('X-Priority', '').lower()
    importance = headers.get('Importance', '').lower()
    is_urgent = 'high' in priority or 'urgent' in priority or 'high' in importance
    is_important = 'high' in priority or 'high' in importance

    # Determinar si el remitente es cualificado o frecuente
    is_qualified_sender = any(qs in from_.lower() for qs in qualified_senders)
    is_top_sender = from_ in top_senders

    # Prompt mejorado para Mistral
    prompt = f"""
    Analiza el siguiente texto de un correo electrónico y clasifica sus características. Devuelve EXCLUSIVAMENTE un objeto JSON con:
    - "requires_response": Booleano, verdadero si el correo solicita una respuesta explícita.
    - "urgent": Booleano, verdadero si el correo indica urgencia o requiere acción inmediata.
    - "important": Booleano, verdadero si el correo es importante o contiene información trascendente.
    - "advertisement": Booleano, verdadero si el correo parece publicidad, ofertas, promociones, etc.

    Considera lo siguiente al clasificar:
    - Publicidad: Busca ofertas, precios, mensajes impactantes, tiempos limitados, incentivos para comprar, etc.
    - Urgencia: Busca palabras como "urgente", "inmediato", "pronto", o plazos cortos.
    - Importancia: Busca decisiones trascendentes, información crítica, o temas de alta relevancia.

    Texto:
    {text[:2000]}
    """

    response = call_mistral_api(prompt)
    parsed_response = safe_parse_json(response, message_id, subject)
    mistral_classifications = process_api_response(parsed_response, message_id, subject, ['requires_response', 'urgent', 'important', 'advertisement'])

    if mistral_classifications:
        # Clasificación de publicidad con modelo bayesiano
        if os.path.exists(bayesian_model_file):
            with open(bayesian_model_file, 'rb') as f:
                bayesian_model = pickle.load(f)
            text_vector = bayesian_model['vectorizer'].transform([text])
            bayesian_prob = bayesian_model['classifier'].predict_proba(text_vector)[0][1]  # Probabilidad de ser publicidad
            mistral_ad_prob = 1 if mistral_classifications['advertisement'] else 0
            avg_ad_prob = (mistral_ad_prob + bayesian_prob) / 2
            mistral_classifications['advertisement'] = avg_ad_prob >= 0.8
        else:
            logging.warning(f"Modelo bayesiano no encontrado para message_id {message_id}, subject '{subject}'. Usando solo Mistral para publicidad.")

        # Ajustar urgencia e importancia
        if is_urgent or (mistral_classifications['urgent'] and (is_qualified_sender or is_top_sender)):
            mistral_classifications['urgent'] = True
        if is_important or (mistral_classifications['important'] and (is_qualified_sender or is_top_sender)):
            mistral_classifications['important'] = True

        # Publicidad no puede ser urgente ni importante
        if mistral_classifications['advertisement']:
            mistral_classifications['urgent'] = False
            mistral_classifications['important'] = False

        return mistral_classifications

    logging.warning(f"No se pudo clasificar correo para message_id {message_id}, subject '{subject}'. Usando heurística.")
    return classify_heuristically(response)

def check_responded_status(service, user_id, msg, message_id, mailbox_id):
    try:
        headers = {header['name']: header['value'] for header in msg['payload']['headers']}
        in_reply_to = headers.get('In-Reply-To')
        thread_id = msg.get('threadId')

        if in_reply_to:
            results = service.users().messages().list(userId='me', q=f"from:{mailbox_id} in_reply_to:{in_reply_to}", maxResults=1).execute()
            if results.get('messages', []):
                return True

        if thread_id:
            thread = service.users().threads().get(userId='me', id=thread_id).execute()
            messages = thread.get('messages', [])
            msg_date = headers.get('Date')
            if not msg_date:
                return False
            parsed_date = parse_email_date(msg_date)
            if not parsed_date:
                return False
            msg_timestamp = parsed_date.timestamp()
            for thread_msg in messages:
                thread_headers = {h['name']: h['value'] for h in thread_msg['payload']['headers']}
                thread_from = thread_headers.get('From', '')
                thread_date = thread_headers.get('Date', '')
                if mailbox_id in thread_from.lower() and thread_date:
                    parsed_thread_date = parse_email_date(thread_date)
                    if parsed_thread_date and parsed_thread_date.timestamp() > msg_timestamp:
                        return True
        return False
    except HttpError as e:
        if e.resp.status == 401:
            raise
        logging.error(f"Error al verificar estado de respuesta para message_id {message_id}: {e}")
        return False
    except Exception as e:
        logging.error(f"Error inesperado al verificar estado de respuesta para message_id {message_id}: {e}")
        return False

def process_email_with_mistral(email, message_id):
    subject = email.get('subject', '')
    from_ = email.get('from', '')
    to = email.get('to', '')
    body = email.get('body', '')
    attachments = ' '.join([a for a in email.get('attachments', []) if a is not None])
    attachments_content = ' '.join([c for c in email.get('attachments_content', []) if c is not None])

    optimized_text = f"{text_optimization(subject)} {text_optimization(from_)} {text_optimization(to)} {text_optimization(body)} {text_optimization(attachments)} {text_optimization_attachments(attachments_content)}"

    prompt = f"""
    Analiza el siguiente texto de un correo electrónico y devuelve EXCLUSIVAMENTE un objeto JSON válido con:
    1. "summary": Un resumen con temas clave, nombres propios y términos específicos del dominio. Este resumen debe estar en el mismo idioma que el texto del correo.
    2. "relevant_terms": Un diccionario donde las claves son términos relevantes y los valores son objetos con:
       - "frequency": Número entero de veces que aparece.
       - "context": Breve descripción de su significado o uso.
       - "type": "acción", "nombre_propio", "url" o "definición_temporal".
    
    Texto:
    {optimized_text}
    """

    response = call_mistral_api(prompt)
    parsed_response = safe_parse_json(response, message_id, subject)
    processed_response = process_api_response(parsed_response, message_id, subject, ['summary', 'relevant_terms'])
    if processed_response:
        summary = processed_response.get("summary", "Resumen no disponible")
        relevant_terms = processed_response.get("relevant_terms", {})
        if not isinstance(relevant_terms, dict):
            relevant_terms = {}
        return summary, relevant_terms
    logging.warning(f"No se pudo procesar respuesta para message_id {message_id}, subject '{subject}'. Usando predeterminados.")
    return "Resumen no disponible", {}

def call_mistral_api(prompt):
    prompt_hash = hashlib.md5(prompt.encode('utf-8')).hexdigest()
    if prompt_hash in response_cache:
        response_cache.move_to_end(prompt_hash)
        return response_cache[prompt_hash]

    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "mistral-custom",
        "prompt": prompt,
        "stream": False,
        "temperature": 0.7,
        "num_predict": 512,
        "num_ctx": 32768
    }
    
    max_retries = 3
    base_delay = 2
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()['response']
            if len(response_cache) >= cache_limit:
                response_cache.popitem(last=False)
            response_cache[prompt_hash] = result
            with open(cache_file, 'wb') as f:
                pickle.dump(response_cache, f)
            return result
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1 * base_delay)
                logging.warning(f"Intento {attempt + 1} fallido al contactar con la API: {e}. Reintentando en {delay:.2f} segundos...")
                time.sleep(delay)
            else:
                logging.error(f"Error al contactar con la API tras {max_retries} intentos: {e}")
                return f'{{"error": "API failure", "message": "{str(e)}"}}'

def normalize_subject(subject):
    """Normaliza el asunto eliminando prefijos como RE:, FWD:, etc."""
    prefixes = ['re:', 'fwd:', 'fw:', 'rv:']
    subject_lower = subject.lower()
    for prefix in prefixes:
        if subject_lower.startswith(prefix):
            subject = subject[len(prefix):].strip()
            break
    return subject

def find_thread_by_subject(subject, mailbox_id):
    """Busca un hilo existente basado en el asunto normalizado"""
    normalized_subject = normalize_subject(subject)
    existing_thread = emails_collection.find_one({
        'mailbox_id': mailbox_id,
        'subject': {'$regex': f"^{re.escape(normalized_subject)}", '$options': 'i'}
    })
    if existing_thread:
        return existing_thread.get('parent_thread_id')
    return None

def calculate_similarity(embedding1, embedding2):
    """Calcula la similitud cosino entre dos embeddings"""
    if embedding1 is None or embedding2 is None:
        return 0.0
    emb1 = np.frombuffer(zlib.decompress(embedding1), dtype=np.float32)
    emb2 = np.frombuffer(zlib.decompress(embedding2), dtype=np.float32)
    return np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

def find_similar_thread(email_embedding, from_, to, mailbox_id, threshold=0.8):
    """Busca un hilo similar basado en la similitud de embeddings y coincidencia de remitentes/destinatarios"""
    cursor = emails_collection.find({'mailbox_id': mailbox_id, 'embedding': {'$ne': None}})
    for doc in cursor:
        similarity = calculate_similarity(email_embedding, doc['embedding'])
        if similarity > threshold and (doc['from'] == from_ or doc['to'] == to):
            return doc.get('parent_thread_id')
    return None

def review_existing_emails(username, mailbox_id=None, force_update_elastic=False):
    query = {'mailbox_id': mailbox_id} if mailbox_id else {'from': username}
    cursor = emails_collection.find(query)
    top_senders = get_top_senders(mailbox_id)
    for doc in cursor:
        message_id = doc.get('message_id', 'unknown')
        subject = doc.get('subject', '')
        from_ = doc.get('from', '')
        to = doc.get('to', '')
        body = doc.get('body', '')
        attachments_content = doc.get('attachments_content', [])
        headers = doc.get('headers', {})

        email_dict = {
            'subject': subject,
            'from': from_,
            'to': to,
            'body': body,
            'attachments_content': attachments_content,
            'headers': headers
        }

        updates = {}
        
        # Revisar y corregir resumen y términos relevantes
        summary, relevant_terms = process_email_with_mistral(email_dict, message_id)
        updates['summary'] = summary
        updates['relevant_terms'] = relevant_terms
        updates['relevant_terms_array'] = list(relevant_terms.keys())

        # Revisar y corregir dominio semántico
        if doc.get('semantic_domain') == 'general' and doc.get('domain_confidence') == 0.5:
            semantic_domain, confidence = infer_semantic_domain(subject, body, attachments_content, message_id)
            updates['semantic_domain'] = semantic_domain
            updates['domain_confidence'] = confidence

        # Revisar y corregir clasificaciones
        if any(key not in doc or not isinstance(doc[key], bool) for key in ['requires_response', 'urgent', 'important', 'advertisement']):
            classifications = classify_email(email_dict, message_id, top_senders)
            updates['requires_response'] = bool(classifications.get('requires_response', False))
            updates['urgent'] = bool(classifications.get('urgent', False))
            updates['important'] = bool(classifications.get('important', False))
            updates['advertisement'] = bool(classifications.get('advertisement', False))

        # Revisar y corregir embedding
        if 'embedding' not in doc or doc['embedding'] is None:
            embedding = generate_embedding(subject, body, summary)
            updates['embedding'] = embedding

        # Revisar y corregir hilo
        current_parent_thread_id = doc.get('parent_thread_id')
        if not current_parent_thread_id or current_parent_thread_id == message_id:
            thread_by_subject = find_thread_by_subject(subject, mailbox_id)
            if thread_by_subject:
                updates['parent_thread_id'] = thread_by_subject
            else:
                embedding = updates.get('embedding', doc.get('embedding'))
                similar_thread = find_similar_thread(embedding, from_, to, mailbox_id)
                if similar_thread:
                    updates['parent_thread_id'] = similar_thread

        if updates or force_update_elastic:
            emails_collection.update_one(
                {'_id': doc['_id']},
                {'$set': updates}
            )
            logging.info(f"Updated metadata for message_id {message_id}: {list(updates.keys())}")

            # Sincronizar con Elasticsearch, incluyendo mailbox_id
            es_doc = {
                'message_id': message_id,
                'mailbox_id': mailbox_id,
                'body': body,
                'summary': summary,
                'relevant_terms_array': updates.get('relevant_terms_array', doc.get('relevant_terms_array', [])),
                'subject': subject,
                'from': from_,
                'to': to,
                'date': doc.get('date', 'unknown'),
                'semantic_domain': updates.get('semantic_domain', doc.get('semantic_domain', 'general')),
                'embedding': np.frombuffer(zlib.decompress(updates.get('embedding', doc.get('embedding'))), dtype=np.float32).tolist() if updates.get('embedding', doc.get('embedding')) else []
            }
            
            if 'es_doc_id' in doc:
                try:
                    es.update(index='email_index', id=doc['es_doc_id'], body={'doc': es_doc})
                except Exception as e:
                    logging.error(f"Error al actualizar documento en Elasticsearch para message_id {message_id}: {e}")
            else:
                res = es.index(index='email_index', body=es_doc)
                es_doc_id = res['_id']
                emails_collection.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'es_doc_id': es_doc_id}}
                )

def download_attachment(service, user_id, msg_id, part):
    try:
        attachment = service.users().messages().attachments().get(userId=user_id, messageId=msg_id, id=part['body']['attachmentId']).execute()
        file_data = base64.urlsafe_b64decode(attachment['data'].encode('UTF-8'))
        filename = part.get('filename', 'unnamed_attachment')
        path = f'./attachments/{filename}'
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(file_data)
        return path
    except HttpError as e:
        if e.resp.status == 401:
            raise
        logging.error(f"Error downloading attachment: {e}")
        return None
    except Exception as e:
        logging.error(f"Error downloading attachment: {e}")
        return None

def save_attachment(part):
    filename = part.get_filename()
    if not filename:
        filename = 'unnamed_attachment'
    path = f'./attachments/{filename}'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(part.get_payload(decode=True))
    return path

def analyze_attachment(file_path):
    if not file_path:
        return "No se pudo descargar el adjunto"
    mime = mimetypes.guess_type(file_path)[0]
    if mime == 'text/plain':
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    elif mime == 'application/pdf':
        try:
            reader = PdfReader(file_path)
            return "".join(page.extract_text() for page in reader.pages)
        except Exception:
            return "Error al analizar PDF"
    elif mime.startswith('image/'):
        try:
            return pytesseract.image_to_string(Image.open(file_path))
        except Exception:
            return "Error en OCR"
    elif mime == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        try:
            doc = DocxDocument(file_path)
            return '\n'.join(paragraph.text for paragraph in doc.paragraphs)
        except Exception:
            return "Error al analizar Word"
    elif mime == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
        try:
            workbook = openpyxl.load_workbook(file_path)
            sheet = workbook.active
            return '\n'.join(', '.join(str(cell) for cell in row) for row in sheet.iter_rows(values_only=True))
        except Exception:
            return "Error al analizar Excel"
    return "Tipo de archivo no soportado"

def extract_urls(text):
    url_pattern = re.compile(r'https?://\S+')
    return [{'action': 'visit', 'description': 'Link encontrado', 'url': url} for url in url_pattern.findall(text)]

def get_top_senders(mailbox_id):
    pipeline = [
        {'$match': {'mailbox_id': mailbox_id}},
        {'$group': {'_id': '$from', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 10}
    ]
    top_senders = [doc['_id'] for doc in emails_collection.aggregate(pipeline)]
    return top_senders

def get_email_body(payload):
    body = ''
    def extract_from_parts(parts):
        nonlocal body
        for part in parts:
            mime_type = part.get('mimeType', '')
            data = part.get('body', {}).get('data')
            if mime_type == 'text/plain' and data:
                try:
                    decoded = base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8', errors='ignore')
                    if decoded.strip():  # Solo aceptar si tiene contenido útil
                        body = decoded
                        return True
                except Exception as e:
                    logging.error(f"Error decoding text/plain: {e}")
            elif mime_type == 'text/html' and not body and data:
                try:
                    html_content = base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8', errors='ignore')
                    soup = BeautifulSoup(html_content, 'html.parser')
                    text = soup.get_text()
                    if text.strip():  # Guardar como fallback si tiene contenido
                        body = text
                except Exception as e:
                    logging.error(f"Error decoding text/html: {e}")
            elif 'parts' in part:  # Recursividad para partes anidadas
                if extract_from_parts(part['parts']):
                    return True
        return False

    if 'parts' in payload:
        extract_from_parts(payload['parts'])
    elif payload.get('body', {}).get('data'):
        try:
            body = base64.urlsafe_b64decode(payload['body']['data'].encode('ASCII')).decode('utf-8', errors='ignore')
        except Exception as e:
            logging.error(f"Error decoding single-part body: {e}")
    
    return body.strip() if body.strip() else ''

def process_and_insert_email(msg, service, user_id, mailbox_id, dry_run=False, force_update_elastic=False):
    try:
        headers = {header['name']: header['value'] for header in msg['payload']['headers']}
        subject = headers.get('Subject', 'No Subject')
        from_ = headers.get('From', 'Unknown')
        to = headers.get('To', 'Unknown')
        raw_date = headers.get('Date', 'Unknown')
        message_id = headers.get('Message-ID', hashlib.sha256(f"{subject}{from_}{to}{raw_date}".encode('utf-8')).hexdigest())
        gmail_message_id = msg['id']
        in_reply_to = headers.get('In-Reply-To')
        references = headers.get('References')
        thread_id = msg.get('threadId', None)
        index = hashlib.sha256(message_id.encode('utf-8')).hexdigest()
        
        existing_email = emails_collection.find_one({'$or': [{'message_id': message_id}, {'index': index}]})
        parsed_date = parse_email_date(raw_date)
        date = parsed_date.isoformat() if parsed_date else 'unknown'
        
        body = get_email_body(msg['payload'])
        headers_text = '\n'.join(f"{h['name']}: {h['value']}" for h in msg['payload']['headers'])

        attachments = []
        attachments_content = []
        if 'parts' in msg['payload']:
            for part in msg['payload']['parts']:
                if part.get('filename') and part.get('body', {}).get('attachmentId'):
                    attachments.append(part['filename'])
                    attachment_path = download_attachment(service, user_id, msg['id'], part)
                    attachments_content.append(analyze_attachment(attachment_path))

        email_dict = {
            'subject': subject,
            'from': from_,
            'to': to,
            'body': body,
            'attachments': attachments,
            'attachments_content': attachments_content,
            'headers': headers
        }
        
        summary, relevant_terms = process_email_with_mistral(email_dict, message_id)
        semantic_domain, domain_confidence = infer_semantic_domain(subject, body, attachments_content, message_id)
        top_senders = get_top_senders(mailbox_id)
        classifications = classify_email(email_dict, message_id, top_senders)
        responded = check_responded_status(service, user_id, msg, message_id, mailbox_id)

        relevant_terms_array = list(relevant_terms.keys())
        embedding = generate_embedding(subject, body, summary)
        urls = extract_urls(f"{headers_text}\n{subject}\n{from_}\n{to}\n{body}\n{' '.join(attachments_content)}")
        
        # Reconstrucción avanzada de hilos
        parent_thread_id = thread_id if thread_id else in_reply_to or message_id
        if not parent_thread_id or parent_thread_id == message_id:
            thread_by_subject = find_thread_by_subject(subject, mailbox_id)
            if thread_by_subject:
                parent_thread_id = thread_by_subject
            else:
                similar_thread = find_similar_thread(embedding, from_, to, mailbox_id)
                if similar_thread:
                    parent_thread_id = similar_thread

        email_document = {
            'from': from_,
            'to': to,
            'subject': subject,
            'date': date,
            'body': body,
            'headers_text': headers_text,
            'attachments': attachments,
            'attachments_content': attachments_content,
            'message_id': message_id,
            'gmail_message_id': gmail_message_id,
            'in_reply_to': in_reply_to,
            'references': references,
            'parent_thread_id': parent_thread_id,
            'urls': urls,
            'summary': summary,
            'relevant_terms': relevant_terms,
            'relevant_terms_array': relevant_terms_array,
            'embedding': embedding,
            'semantic_domain': semantic_domain,
            'domain_confidence': domain_confidence,
            'index': index,
            'requires_response': bool(classifications.get('requires_response', False)),
            'urgent': bool(classifications.get('urgent', False)),
            'important': bool(classifications.get('important', False)),
            'advertisement': bool(classifications.get('advertisement', False)),
            'responded': bool(responded),
            'mailbox_id': mailbox_id
        }
        
        if dry_run:
            action = "update" if existing_email else "insert"
            logging.info(f"[DRY RUN] Would {action} email - message_id: {message_id}, index: {index}, date: {date}, subject: {subject}, mailbox_id: {mailbox_id}")
        else:
            if existing_email:
                emails_collection.update_one(
                    {'$or': [{'message_id': message_id}, {'index': index}]},
                    {'$set': email_document}
                )
                logging.info(f"Updated email with message_id: {message_id} for mailbox {mailbox_id}")
            else:
                emails_collection.insert_one(email_document)
                logging.info(f"Inserted email with message_id: {message_id} for mailbox {mailbox_id}")

            # Sincronizar con Elasticsearch, incluyendo mailbox_id
            es_doc = {
                'message_id': message_id,
                'mailbox_id': mailbox_id,
                'body': body,
                'summary': summary,
                'relevant_terms_array': relevant_terms_array,
                'subject': subject,
                'from': from_,
                'to': to,
                'date': date,
                'semantic_domain': semantic_domain,
                'embedding': np.frombuffer(zlib.decompress(embedding), dtype=np.float32).tolist() if embedding else []
            }
            if force_update_elastic or not existing_email:
                res = es.index(index='email_index', body=es_doc)
                es_doc_id = res['_id']
                emails_collection.update_one(
                    {'message_id': message_id},
                    {'$set': {'es_doc_id': es_doc_id}}
                )
            else:
                if 'es_doc_id' in existing_email:
                    es.update(index='email_index', id=existing_email['es_doc_id'], body={'doc': es_doc}, ignore=[404])
                else:
                    res = es.index(index='email_index', body=es_doc)
                    es_doc_id = res['_id']
                    emails_collection.update_one(
                        {'message_id': message_id},
                        {'$set': {'es_doc_id': es_doc_id}}
                    )
    except HttpError as e:
        if e.resp.status == 401:
            raise
        logging.error(f"Error procesando mensaje {message_id} para mailbox {mailbox_id}: {e}")
    except Exception as e:
        logging.error(f"Error procesando mensaje {message_id} para mailbox {mailbox_id}: {e}")

def fix_empty_bodies(username, mailbox_id):
    creds = get_credentials_from_db(username, mailbox_id)
    if not creds:
        logging.error(f"No se pudieron obtener credenciales para {mailbox_id}")
        return
    service = build_service(creds)
    
    # Buscar correos con body vacío o ausente
    cursor = emails_collection.find({
        'mailbox_id': mailbox_id,
        '$or': [{'body': ''}, {'body': {'$exists': False}}]
    })
    total_fixed = 0
    
    for doc in cursor:
        message_id = doc.get('message_id')
        gmail_message_id = doc.get('gmail_message_id')
        
        # Si no hay gmail_message_id, intentar recuperarlo usando message_id
        if not gmail_message_id:
            logging.info(f"No se encontró gmail_message_id para message_id {message_id}. Intentando recuperar por Message-ID.")
            try:
                # Buscar el mensaje en Gmail usando rfc822msgid
                results = service.users().messages().list(
                    userId='me',
                    q=f"rfc822msgid:{message_id}",
                    maxResults=1
                ).execute()
                messages = results.get('messages', [])
                if messages:
                    gmail_message_id = messages[0]['id']
                    # Actualizar el documento con el gmail_message_id encontrado
                    emails_collection.update_one(
                        {'_id': doc['_id']},
                        {'$set': {'gmail_message_id': gmail_message_id}}
                    )
                    logging.info(f"Encontrado y actualizado gmail_message_id para message_id {message_id}: {gmail_message_id}")
                else:
                    logging.warning(f"No se encontró mensaje para Message-ID {message_id} en Gmail. Saltando.")
                    continue
            except HttpError as e:
                logging.error(f"Error al buscar mensaje por Message-ID {message_id}: {e}")
                continue
        
        # Recuperar el mensaje y reparar el body
        try:
            msg = service.users().messages().get(userId='me', id=gmail_message_id).execute()
            new_body = get_email_body(msg['payload'])
            
            if new_body:
                # Preparar actualizaciones para MongoDB
                updates = {'body': new_body}
                summary = doc.get('summary', 'Resumen no disponible')
                updates['embedding'] = generate_embedding(doc['subject'], new_body, summary)
                
                # Actualizar en MongoDB
                emails_collection.update_one(
                    {'_id': doc['_id']},
                    {'$set': updates}
                )
                
                # Preparar documento para Elasticsearch
                es_doc = {
                    'message_id': message_id,
                    'mailbox_id': mailbox_id,
                    'body': new_body,
                    'summary': summary,
                    'relevant_terms_array': doc.get('relevant_terms_array', []),
                    'subject': doc['subject'],
                    'from': doc['from'],
                    'to': doc['to'],
                    'date': doc['date'],
                    'semantic_domain': doc.get('semantic_domain', 'general'),
                    'embedding': np.frombuffer(zlib.decompress(updates['embedding']), dtype=np.float32).tolist() if updates['embedding'] else []
                }
                
                # Sincronizar con Elasticsearch
                if 'es_doc_id' in doc:
                    try:
                        es.update(index='email_index', id=doc['es_doc_id'], body={'doc': es_doc}, ignore=[404])
                        logging.info(f"Actualizado documento en Elasticsearch para message_id {message_id}")
                    except Exception as e:
                        logging.error(f"Error al actualizar en Elasticsearch para message_id {message_id}: {e}")
                else:
                    res = es.index(index='email_index', body=es_doc)
                    es_doc_id = res['_id']
                    emails_collection.update_one(
                        {'_id': doc['_id']},
                        {'$set': {'es_doc_id': es_doc_id}}
                    )
                    logging.info(f"Insertado nuevo documento en Elasticsearch para message_id {message_id}")
                
                total_fixed += 1
                logging.info(f"Corregido body para message_id {message_id}")
            else:
                logging.warning(f"No se pudo extraer body para message_id {message_id} desde Gmail")
        except HttpError as e:
            logging.error(f"Error al recuperar mensaje {gmail_message_id}: {e}")
        except Exception as e:
            logging.error(f"Error al procesar message_id {message_id}: {e}")
    
    logging.info(f"Corrección completada: {total_fixed} correos actualizados para {mailbox_id}")

def connect_to_imap(creds):
    try:
        if creds['encryption'] == 'SSL/TLS':
            imap = imaplib.IMAP4_SSL(creds['server'], creds['port'])
        else:
            imap = imaplib.IMAP4(creds['server'], creds['port'])
        imap.login(creds['username'], creds['password'])
        return imap
    except Exception as e:
        logging.error(f"Error al conectar a IMAP: {e}")
        return None

def fetch_and_process_emails_imap(imap, folders, username, mailbox_id, desired_max_results=5000, dry_run=False, date_start=None, force_update_elastic=False):
    for folder in folders:
        try:
            imap.select(folder)
            if date_start:
                since_date = date_start.strftime('%d-%b-%Y')
                status, messages = imap.search(None, f'(SINCE "{since_date}")')
            else:
                status, messages = imap.search(None, 'ALL')
            message_ids = messages[0].split()
            total_fetched = 0
            for msg_id in message_ids:
                if total_fetched >= desired_max_results:
                    break
                status, msg_data = imap.fetch(msg_id, '(RFC822)')
                if status != 'OK':
                    continue
                raw_email = msg_data[0][1]
                email_message = email.message_from_bytes(raw_email)
                process_and_insert_email_imap(email_message, username, mailbox_id, dry_run=dry_run, force_update_elastic=force_update_elastic)
                total_fetched += 1
            logging.info(f"Processed {total_fetched} emails from folder {folder} for {mailbox_id}")
        except Exception as e:
            logging.error(f"Error al procesar carpeta {folder} para {mailbox_id}: {e}")

def process_and_insert_email_imap(email_message, username, mailbox_id, dry_run=False, force_update_elastic=False):
    subject = email_message['Subject'] or 'No Subject'
    from_ = email_message['From'] or 'Unknown'
    to = email_message['To'] or 'Unknown'
    raw_date = email_message['Date'] or 'Unknown'
    message_id = email_message['Message-ID'] or hashlib.sha256(f"{subject}{from_}{to}{raw_date}".encode('utf-8')).hexdigest()
    in_reply_to = email_message.get('In-Reply-To')
    references = email_message.get('References')
    index = hashlib.sha256(message_id.encode('utf-8')).hexdigest()
    
    parsed_date = parse_email_date(raw_date)
    date = parsed_date.isoformat() if parsed_date else 'unknown'
    
    body = ''
    attachments = []
    attachments_content = []
    if email_message.is_multipart():
        for part in email_message.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain':
                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
            elif content_type == 'text/html' and not body:
                html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                soup = BeautifulSoup(html_content, 'html.parser')
                body = soup.get_text()
            elif part.get_filename():
                attachments.append(part.get_filename())
                attachment_path = save_attachment(part)
                attachments_content.append(analyze_attachment(attachment_path))
    else:
        body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
    
    email_dict = {
        'subject': subject,
        'from': from_,
        'to': to,
        'body': body,
        'attachments': attachments,
        'attachments_content': attachments_content,
        'headers': dict(email_message.items())
    }
    
    summary, relevant_terms = process_email_with_mistral(email_dict, message_id)
    semantic_domain, domain_confidence = infer_semantic_domain(subject, body, attachments_content, message_id)
    top_senders = get_top_senders(mailbox_id)
    classifications = classify_email(email_dict, message_id, top_senders)
    responded = False

    relevant_terms_array = list(relevant_terms.keys())
    embedding = generate_embedding(subject, body, summary)
    headers_text = str(email_message.items())
    urls = extract_urls(f"{headers_text}\n{subject}\n{from_}\n{to}\n{body}\n{' '.join(attachments_content)}")
    
    # Reconstrucción avanzada de hilos para IMAP
    parent_thread_id = in_reply_to or message_id
    if not in_reply_to:
        thread_by_subject = find_thread_by_subject(subject, mailbox_id)
        if thread_by_subject:
            parent_thread_id = thread_by_subject
        else:
            similar_thread = find_similar_thread(embedding, from_, to, mailbox_id)
            if similar_thread:
                parent_thread_id = similar_thread

    email_document = {
        'from': from_,
        'to': to,
        'subject': subject,
        'date': date,
        'body': body,
        'headers_text': headers_text,
        'attachments': attachments,
        'attachments_content': attachments_content,
        'message_id': message_id,
        'in_reply_to': in_reply_to,
        'references': references,
        'parent_thread_id': parent_thread_id,
        'urls': urls,
        'summary': summary,
        'relevant_terms': relevant_terms,
        'relevant_terms_array': relevant_terms_array,
        'embedding': embedding,
        'semantic_domain': semantic_domain,
        'domain_confidence': domain_confidence,
        'index': index,
        'requires_response': bool(classifications.get('requires_response', False)),
        'urgent': bool(classifications.get('urgent', False)),
        'important': bool(classifications.get('important', False)),
        'advertisement': bool(classifications.get('advertisement', False)),
        'responded': bool(responded),
        'mailbox_id': mailbox_id
    }
    
    if dry_run:
        logging.info(f"[DRY RUN] Would insert/update email - message_id: {message_id}, index: {index}, date: {date}, subject: {subject}, mailbox_id: {mailbox_id}")
    else:
        existing_email = emails_collection.find_one({'$or': [{'message_id': message_id}, {'index': index}]})
        if existing_email:
            emails_collection.update_one(
                {'$or': [{'message_id': message_id}, {'index': index}]},
                {'$set': email_document}
            )
            logging.info(f"Updated email with message_id: {message_id} for mailbox {mailbox_id}")
        else:
            emails_collection.insert_one(email_document)
            logging.info(f"Inserted email with message_id: {message_id} for mailbox {mailbox_id}")

        # Sincronizar con Elasticsearch, incluyendo mailbox_id
        es_doc = {
            'message_id': message_id,
            'mailbox_id': mailbox_id,
            'body': body,
            'summary': summary,
            'relevant_terms_array': relevant_terms_array,
            'subject': subject,
            'from': from_,
            'to': to,
            'date': date,
            'semantic_domain': semantic_domain,
            'embedding': np.frombuffer(zlib.decompress(embedding), dtype=np.float32).tolist() if embedding else []
        }
        if force_update_elastic or not existing_email:
            res = es.index(index='email_index', body=es_doc)
            es_doc_id = res['_id']
            emails_collection.update_one(
                {'message_id': message_id},
                {'$set': {'es_doc_id': es_doc_id}}
            )
        else:
            if 'es_doc_id' in existing_email:
                es.update(index='email_index', id=existing_email['es_doc_id'], body={'doc': es_doc}, ignore=[404])
            else:
                res = es.index(index='email_index', body=es_doc)
                es_doc_id = res['_id']
                emails_collection.update_one(
                    {'message_id': message_id},
                    {'$set': {'es_doc_id': es_doc_id}}
                )

def train_bayesian_model(service, user_id, mailbox_id):
    logging.info(f"Iniciando entrenamiento del modelo bayesiano para mailbox {mailbox_id}...")
    promo_messages = service.users().messages().list(userId='me', labelIds=['CATEGORY_PROMOTIONS'], maxResults=1000).execute().get('messages', [])
    non_promo_messages = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1000).execute().get('messages', [])

    logging.info(f"Obtenidos {len(promo_messages)} correos de 'Promotions' y {len(non_promo_messages)} de 'Inbox' para entrenamiento.")

    texts = []
    labels = []

    for msg in promo_messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
        body = get_email_body(msg_data['payload'])
        texts.append(body)
        labels.append(1)
        logging.info(f"Procesado correo de 'Promotions' con ID {msg['id']}")

    for msg in non_promo_messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
        body = get_email_body(msg_data['payload'])
        texts.append(body)
        labels.append(0)
        logging.info(f"Procesado correo de 'Inbox' con ID {msg['id']}")

    logging.info(f"Total de correos para entrenamiento: {len(texts)} (publicidad: {labels.count(1)}, no publicidad: {labels.count(0)})")

    vectorizer = CountVectorizer()
    classifier = MultinomialNB()
    model = make_pipeline(vectorizer, classifier)
    model.fit(texts, labels)

    with open(bayesian_model_file, 'wb') as f:
        pickle.dump({'vectorizer': vectorizer, 'classifier': classifier}, f)
    logging.info(f"Modelo bayesiano entrenado y guardado exitosamente para mailbox {mailbox_id}.")

def fetch_and_process_emails(service, labels, username, mailbox_id, desired_max_results=5000, dry_run=False, train_advertisement=False, date_start=None, force_update_elastic=False):
    if train_advertisement:
        train_bayesian_model(service, 'me', mailbox_id)
        return

    for label in labels:
        messages = []
        page_token = None
        total_fetched = 0
        max_retries = 5
        base_delay = 2

        while total_fetched < desired_max_results:
            retries = 0
            while retries <= max_retries:
                try:
                    query = f"label:{label}"
                    if date_start:
                        since_date = date_start.strftime('%Y/%m/%d')
                        query += f" after:{since_date}"
                    results = service.users().messages().list(
                        userId='me',
                        q=query,
                        maxResults=min(500, desired_max_results - total_fetched),
                        pageToken=page_token
                    ).execute()
                    messages.extend(results.get('messages', []))
                    total_fetched += len(results.get('messages', []))
                    page_token = results.get('nextPageToken')
                    logging.info(f"Fetched {len(results.get('messages', []))} messages from {label} for {mailbox_id}. Total: {total_fetched}")
                    break
                except HttpError as e:
                    if e.resp.status in [401, 429, 503]:
                        if e.resp.status == 401 or 'invalid_grant' in str(e):
                            logging.info(f"Error de autenticación (401 o invalid_grant) detectado para {mailbox_id}, intentando reautorizar...")
                            creds = get_credentials_from_db(username, mailbox_id)
                            if not creds:
                                logging.error(f"No se pudieron obtener credenciales válidas para {mailbox_id}")
                                return
                            service = build_service(creds)
                            logging.info(f"Servicio reconstruido con nuevas credenciales para {mailbox_id}")
                            continue
                        elif e.resp.status == 429:
                            retries += 1
                            delay = min(base_delay * 2 ** (retries - 1), 32)
                            time.sleep(delay + random.uniform(0, 0.1 * delay))
                        elif e.resp.status == 503:
                            retries += 1
                            delay = min(base_delay * 2 ** (retries - 1), 32)
                            logging.warning(f"Error 503 para {label} en {mailbox_id}, reintentando en {delay:.2f} segundos...")
                            time.sleep(delay + random.uniform(0, 0.1 * delay))
                    else:
                        logging.error(f"Error fetching messages for {label} in {mailbox_id}: {e}")
                        return
                except Exception as e:
                    logging.error(f"Unexpected error fetching messages for {mailbox_id}: {e}")
                    return
            if not page_token:
                break

        for i, message in enumerate(messages, 1):
            logging.info(f"Processing message {i}/{len(messages)} from {label} for {mailbox_id}...")
            retries = 0
            while retries <= max_retries:
                try:
                    msg = service.users().messages().get(userId='me', id=message['id']).execute()
                    process_and_insert_email(msg, service, 'me', mailbox_id, dry_run=dry_run, force_update_elastic=force_update_elastic)
                    break
                except HttpError as e:
                    if e.resp.status in [401, 429, 503]:
                        if e.resp.status == 401 or 'invalid_grant' in str(e):
                            logging.info(f"Error de autenticación (401 o invalid_grant) detectado al procesar mensaje para {mailbox_id}, intentando reautorizar...")
                            creds = get_credentials_from_db(username, mailbox_id)
                            if not creds:
                                logging.error(f"No se pudieron obtener credenciales válidas para {mailbox_id}")
                                break
                            service = build_service(creds)
                            logging.info(f"Servicio reconstruido con nuevas credenciales para {mailbox_id}")
                            continue
                        elif e.resp.status in [429, 503]:
                            retries += 1
                            delay = min(base_delay * 2 ** (retries - 1), 32)
                            time.sleep(delay + random.uniform(0, 0.1 * delay))
                    else:
                        logging.error(f"Error processing message {message['id']} for {mailbox_id}: {e}")
                        break
                except Exception as e:
                    logging.error(f"Unexpected error processing message {message['id']} for {mailbox_id}: {e}")
                    break

def process_user_mailboxes(username, mailbox_id=None, dry_run=False, review=False, populate=False, train_advertisement=False, num_emails=5000, date_start=None, force_update_elastic=False, fix_empty=False):
    user = users_collection.find_one({"username": username})
    if not user:
        logging.error(f"Usuario {username} no encontrado")
        return
    
    mailboxes = user['mailboxes']
    if mailbox_id:
        mailboxes = [mb for mb in mailboxes if mb['mailbox_id'] == mailbox_id]
        if not mailboxes:
            logging.error(f"Buzón {mailbox_id} no encontrado para usuario {username}")
            return
    
    for mailbox in mailboxes:
        mailbox_id = mailbox['mailbox_id']
        if mailbox['type'] == 'gmail':
            creds = get_credentials_from_db(username, mailbox_id)
            if not creds:
                continue
            service = build_service(creds)
            if train_advertisement:
                train_bayesian_model(service, 'me', mailbox_id)
            elif review:
                review_existing_emails(username, mailbox_id, force_update_elastic=force_update_elastic)
            elif populate:
                populate_thread_fields(service, 'me', mailbox_id)
            elif fix_empty:
                fix_empty_bodies(username, mailbox_id)
            else:
                migrate_date_formats(dry_run=dry_run)
                fetch_and_process_emails(service, ['INBOX', 'SENT'], username, mailbox_id, desired_max_results=num_emails, dry_run=dry_run, train_advertisement=train_advertisement, date_start=date_start, force_update_elastic=force_update_elastic)
        elif mailbox['type'] == 'imap':
            creds = get_credentials_from_db(username, mailbox_id)
            if not creds:
                continue
            imap = connect_to_imap(creds)
            if not imap:
                continue
            if review:
                review_existing_emails(username, mailbox_id, force_update_elastic=force_update_elastic)
            elif populate:
                populate_thread_fields_imap(imap, username, mailbox_id)
            elif fix_empty:
                logging.warning(f"Corrección de cuerpos vacíos no implementada para IMAP en mailbox {mailbox_id}")
            else:
                migrate_date_formats(dry_run=dry_run)
                fetch_and_process_emails_imap(imap, ['INBOX', 'Sent'], username, mailbox_id, desired_max_results=num_emails, dry_run=dry_run, date_start=date_start, force_update_elastic=force_update_elastic)
                imap.logout()
        else:
            logging.error(f"Tipo de buzón no soportado: {mailbox['type']}")

def populate_thread_fields(service, user_id, mailbox_id):
    logging.info(f"Iniciando población de campos de hilo para mailbox {mailbox_id}...")
    cursor = emails_collection.find({'mailbox_id': mailbox_id}, {'message_id': 1, 'gmail_message_id': 1, '_id': 0})
    for doc in cursor:
        message_id = doc['message_id']
        gmail_message_id = doc.get('gmail_message_id', None)
        if not gmail_message_id:
            logging.warning(f"No se encontró gmail_message_id para message_id {message_id}. Intentando recuperar por Message-ID.")
            try:
                results = service.users().messages().list(userId=user_id, q=f"rfc822msgid:{message_id}", maxResults=1).execute()
                messages = results.get('messages', [])
                if messages:
                    gmail_message_id = messages[0]['id']
                    emails_collection.update_one(
                        {'message_id': message_id},
                        {'$set': {'gmail_message_id': gmail_message_id}}
                    )
                else:
                    logging.warning(f"No se encontró mensaje para Message-ID {message_id}. Usando message_id como parent_thread_id.")
                    emails_collection.update_one(
                        {'message_id': message_id},
                        {'$set': {'parent_thread_id': message_id}}
                    )
                    continue
            except HttpError as e:
                logging.error(f"Error al buscar mensaje por Message-ID {message_id}: {e}")
                continue
        
        try:
            msg = service.users().messages().get(userId=user_id, id=gmail_message_id).execute()
            headers = {header['name']: header['value'] for header in msg['payload']['headers']}
            in_reply_to = headers.get('In-Reply-To')
            references = headers.get('References')
            thread_id = msg.get('threadId', None)
            parent_thread_id = thread_id if thread_id else in_reply_to or message_id

            emails_collection.update_one(
                {'message_id': message_id},
                {'$set': {
                    'in_reply_to': in_reply_to,
                    'references': references,
                    'parent_thread_id': parent_thread_id
                }}
            )
            logging.info(f"Actualizados campos de hilo para message_id {message_id}")
        except HttpError as e:
            logging.warning(f"No se pudo recuperar mensaje {gmail_message_id} desde Gmail: {e}. Usando message_id como parent_thread_id.")
            emails_collection.update_one(
                {'message_id': message_id},
                {'$set': {'parent_thread_id': message_id}}
            )
    logging.info(f"Población de campos de hilo completada para mailbox {mailbox_id}.")

def populate_thread_fields_imap(imap, username, mailbox_id):
    logging.info(f"Iniciando población de campos de hilo para mailbox {mailbox_id}...")
    cursor = emails_collection.find({'mailbox_id': mailbox_id}, {'message_id': 1, '_id': 0})
    for doc in cursor:
        message_id = doc['message_id']
        try:
            imap.select('INBOX')
            status, messages = imap.search(None, f'(HEADER Message-ID "{message_id}")')
            if status == 'OK' and messages[0]:
                msg_id = messages[0].split()[0]
                status, msg_data = imap.fetch(msg_id, '(RFC822)')
                if status == 'OK':
                    raw_email = msg_data[0][1]
                    email_message = email.message_from_bytes(raw_email)
                    in_reply_to = email_message.get('In-Reply-To')
                    references = email_message.get('References')
                    parent_thread_id = in_reply_to or message_id

                    emails_collection.update_one(
                        {'message_id': message_id},
                        {'$set': {
                            'in_reply_to': in_reply_to,
                            'references': references,
                            'parent_thread_id': parent_thread_id
                        }}
                    )
                    logging.info(f"Actualizados campos de hilo para message_id {message_id}")
                else:
                    emails_collection.update_one(
                        {'message_id': message_id},
                        {'$set': {'parent_thread_id': message_id}}
                    )
            else:
                emails_collection.update_one(
                    {'message_id': message_id},
                    {'$set': {'parent_thread_id': message_id}}
                )
        except Exception as e:
            logging.warning(f"No se pudo procesar mensaje {message_id} desde IMAP: {e}. Usando message_id como parent_thread_id.")
            emails_collection.update_one(
                {'message_id': message_id},
                {'$set': {'parent_thread_id': message_id}}
            )
    logging.info(f"Población de campos de hilo completada para mailbox {mailbox_id}.")

def main():
    parser = argparse.ArgumentParser(description="Procesar e insertar correos en MongoDB.")
    parser.add_argument('username', help="Nombre de usuario")
    parser.add_argument('-mailbox', help="ID del buzón específico (opcional)")
    parser.add_argument('-dryrun', action='store_true', help="Modo dry run sin cambios en la base de datos")
    parser.add_argument('-review', action='store_true', help="Revisar y corregir correos existentes")
    parser.add_argument('-populate', action='store_true', help="Poblar campos de hilo para correos existentes")
    parser.add_argument('-train_advertisement', action='store_true', help="Entrenar modelo bayesiano para publicidad")
    parser.add_argument('-fix_empty', action='store_true', help="Corrige correos existentes con body vacío")
    parser.add_argument('-num_emails', type=int, default=5000, help="Número de correos a procesar (default: 5000)")
    parser.add_argument('-date_start', help="Fecha de inicio para procesar correos (formato: YYYY-MM-DD)", type=lambda s: datetime.strptime(s, '%Y-%m-%d'))
    parser.add_argument('-force_update_elastic', action='store_true', help="Forzar la actualización de documentos en Elasticsearch")
    args = parser.parse_args()

    initialize_collection()
    process_user_mailboxes(
        args.username,
        args.mailbox,
        dry_run=args.dryrun,
        review=args.review,
        populate=args.populate,
        train_advertisement=args.train_advertisement,
        num_emails=args.num_emails,
        date_start=args.date_start,
        force_update_elastic=args.force_update_elastic,
        fix_empty=args.fix_empty
    )
    logging.info("Procesamiento de correos completado.")

if __name__ == '__main__':
    main()