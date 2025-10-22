import logging
from logging import handlers
import numpy as np
from hdbscan import HDBSCAN
from sentence_transformers import SentenceTransformer, util
import re
from collections import Counter
from pymongo import MongoClient
from services.nlp_service import normalize_text, call_ollama_api
from services.cache_service import get_cached_result, cache_result
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION, CACHE_TTL
import uuid
import json
import datetime
import torch
from datetime import datetime as dt

try:
    from config import SUMMARY_CACHE_TTL
except ImportError:
    SUMMARY_CACHE_TTL = CACHE_TTL if 'CACHE_TTL' in globals() else 604800

logger = logging.getLogger('email_search_app.analysis_service')
logger.setLevel(logging.DEBUG)
file_handler = handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]
themes_collection = db['themes']

embedding_model = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')

def truncate_text(text, max_length=1000):
    return text[:max_length] if text and len(text) > max_length else text

def encode_texts_with_batch(texts, batch_size=16, use_cpu_fallback=True):
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        logger.debug(f"Encoding batch of {len(batch)} texts")
        try:
            batch_embeddings = embedding_model.encode(batch, convert_to_numpy=True, batch_size=batch_size, device='cuda')
            embeddings.append(batch_embeddings)
        except RuntimeError as e:
            if 'CUDA' in str(e) and use_cpu_fallback:
                logger.warning(f"CUDA error during encoding, falling back to CPU: {str(e)}")
                embedding_model.to('cpu')
                batch_embeddings = embedding_model.encode(batch, convert_to_numpy=True, batch_size=batch_size, device='cpu')
                embeddings.append(batch_embeddings)
                embedding_model.to('cuda')
            else:
                logger.error(f"Encoding failed: {str(e)}")
                raise
    return np.vstack(embeddings)

def extract_keywords(text, top_n=5):
    if not text:
        return []
    words = re.findall(r'\w+', normalize_text(text))
    stopwords = set(['de', 'la', 'el', 'los', 'las', 'y', 'en', 'a', 'que', 'con', 'por', 'para'])
    words = [w for w in words if w not in stopwords and len(w) > 3]
    return [word for word, _ in Counter(words).most_common(top_n)]

def generate_tfidf_summary(texts):
    if not texts:
        return ["No hay contenido suficiente para generar un resumen."]
    combined_text = ' '.join(texts)
    keywords = extract_keywords(combined_text, top_n=5)
    if not keywords:
        return ["Sin resumen disponible."]
    return [f"Tema relacionado con {', '.join(keywords)}."]

def generate_theme_title_and_summary(emails):
    logger.info(f"Generating title and summary for theme with {len(emails)} emails")
    email_indices = [email['index'] for email in emails]
    logger.debug(f"Email indices for cache key: {email_indices}")
    cache_key = f"theme_summary:{'_'.join(sorted(email_indices))}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        logger.debug(f"Retrieved cached title and summary: {cache_key}")
        return cached_result

    combined_text = ""
    senders = set()
    recipients = set()
    for email in emails:
        combined_text += f"Subject: {email.get('subject', '')}\n"
        combined_text += f"From: {email.get('from', '')}\n"
        combined_text += f"To: {email.get('to', '')}\n"
        combined_text += f"Date: {email.get('date', '')}\n"
        combined_text += f"Summary: {email.get('summary', '')}\n\n"
        senders.add(email.get('from', 'N/A'))
        recipients.add(email.get('to', 'N/A'))

    combined_text = truncate_text(normalize_text(combined_text), max_length=2000)
    if not combined_text:
        logger.warning("Empty combined text for theme")
        result = {
            'title': 'Tema sin título',
            'summary': generate_tfidf_summary([''])
        }
        cache_result(cache_key, result)
        return result

    prompt = f"""
    Analiza el siguiente conjunto de correos electrónicos y genera un título y un resumen descriptivo en español.
    - **Título**: Una frase corta (máximo 15 palabras) que resuma el tema principal del hilo de correos.
    - **Resumen**: Un objeto JSON con los siguientes campos:
      - "tema": Describe en 1-2 frases de qué trata el tema.
      - "involucrados": Lista de personas o entidades involucradas (remitentes y destinatarios).
      - "historia": Resume en 2-3 frases qué ha ocurrido hasta ahora en el hilo.
      - "proximos_pasos": Describe en 1-2 frases qué se espera que ocurra a continuación.
      - "puntos_claves": Lista de 3-5 puntos clave o decisiones importantes del tema.
    Asegúrate de que el título y el resumen sean específicos y representativos del contenido del tema.
    Devuelve el resultado en formato JSON: {{"title": "...", "summary": {{"tema": "...", "involucrados": [...], "historia": "...", "proximos_pasos": "...", "puntos_claves": [...]}}}}

    Correos:
    {combined_text}
    """

    try:
        response = call_ollama_api(prompt)
        cleaned_response = response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:].strip()
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3].strip()

        result = json.loads(cleaned_response)
        if not all(key in result for key in ['title', 'summary']) or not all(
            k in result['summary'] for k in ['tema', 'involucrados', 'historia', 'proximos_pasos', 'puntos_claves']
        ):
            raise ValueError("Invalid response format")
        cache_result(cache_key, result)
        return result
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Error parsing LLM response: {str(e)}")
        result = {
            'title': ', '.join(extract_keywords(combined_text)) or 'Tema sin título',
            'summary': {
                "tema": "Error en análisis",
                "involucrados": list(senders.union(recipients)),
                "historia": "No se pudo generar una narrativa debido a un error en el análisis.",
                "proximos_pasos": "Revisar los correos manualmente.",
                "puntos_claves": ["Error en procesamiento de datos."]
            }
        }
        cache_result(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Error generating theme title and summary: {str(e)}", exc_info=True)
        result = {
            'title': ', '.join(extract_keywords(combined_text)) or 'Tema sin título',
            'summary': {
                "tema": "Error en análisis",
                "involucrados": list(senders.union(recipients)),
                "historia": f"No se pudo generar una narrativa: {str(e)}",
                "proximos_pasos": "Revisar los correos manualmente.",
                "puntos_claves": ["Error en procesamiento de datos."]
            }
        }
        cache_result(cache_key, result)
        return result

def determine_status(emails):
    status_keywords = {
        'resuelto': 'Resolved',
        'pendiente': 'Pending Action',
        'en curso': 'Ongoing',
        'acción requerida': 'Pending Action',
        'finalizado': 'Resolved'
    }
    try:
        latest_date = max(email['date'] for email in emails if email.get('date'))
    except ValueError:
        logger.warning("No valid dates found in emails")
        return 'Unknown'
    recent_threshold = '2025-05-01'
    for email in emails:
        content = (email.get('body', '') + ' ' + email.get('summary', '')).lower()
        for keyword, status in status_keywords.items():
            if keyword in content:
                return status
    return 'Ongoing' if latest_date > recent_threshold else 'Inactive'

def analyze_themes(email_ids, user):
    logger.info(f"Analyzing themes for {len(email_ids)} emails with IDs: {email_ids[:5]}... for user: {user.username}")
    try:
        email_ids = [str(id) for id in email_ids]
        user_mailboxes = [mailbox['mailbox_id'] for mailbox in user.mailboxes]
        if not user_mailboxes:
            logger.warning(f"No mailboxes found for user: {user.username}")
            return []

        emails = list(emails_collection.find(
            {
                '$or': [
                    {'index': {'$in': email_ids}},
                    {'message_id': {'$in': email_ids}}
                ],
                'mailbox_id': {'$in': user_mailboxes}
            },
            {
                'message_id': 1,
                'index': 1,
                'from': 1,
                'to': 1,
                'subject': 1,
                'date': 1,
                'body': 1,
                'summary': 1,
                'relevant_terms': 1,
                '_id': 0
            }
        ))
        logger.info(f"Found {len(emails)} emails for analysis")

        if not emails:
            logger.warning("No emails found for provided IDs in user's mailboxes")
            return []

        for email in emails:
            email['index'] = str(email.get('index', 'N/A'))
            email['message_id'] = str(email.get('message_id', 'N/A'))
            if email['index'] == 'N/A' or not email['index']:
                logger.error(f"Invalid 'index' field in email: message_id={email['message_id']}")
            if email['message_id'] == 'N/A' or not email['message_id']:
                logger.error(f"Invalid 'message_id' field in email: index={email['index']}")

        texts = []
        valid_emails = []
        dates = []
        for email in emails:
            subject = email.get('subject', '') * 2
            sender = email.get('from', '') * 1
            recipient = email.get('to', '') * 1
            summary = email.get('summary', '') * 1
            body_excerpt = email.get('body', '')[:200] * 2
            date_str = email.get('date', '')
            text = f"{subject} {sender} {recipient} {summary} {body_excerpt}"
            normalized_text = truncate_text(normalize_text(text), max_length=1000)
            if normalized_text:
                texts.append(normalized_text)
                valid_emails.append(email)
                dates.append(dt.fromisoformat(date_str.replace('Z', '+00:00')) if date_str and 'T' in date_str else None)
            else:
                logger.warning(f"Empty normalized text for email: index={email['index']}")

        if not texts:
            logger.error("No valid texts generated for clustering")
            return []

        logger.debug("Generating embeddings for texts")
        embeddings = encode_texts_with_batch(texts, batch_size=16)

        logger.debug(f"Starting HDBSCAN clustering with {len(valid_emails)} emails")
        clusterer = HDBSCAN(min_cluster_size=2, min_samples=1, cluster_selection_epsilon=0.5)
        labels = clusterer.fit_predict(embeddings)
        logger.debug(f"Found {len(set(labels) - {-1})} clusters, {list(labels).count(-1)} noise points")

        themes = {}
        for label, email, text, embedding in zip(labels, valid_emails, texts, embeddings):
            if label != -1:  # Exclude noise points
                if label not in themes:
                    themes[label] = {'emails': [], 'texts': [], 'embeddings': []}
                themes[label]['emails'].append(email)
                themes[label]['texts'].append(text)
                themes[label]['embeddings'].append(embedding)
            else:
                logger.debug(f"Email marked as noise: index={email['index']}")

        similarity_threshold = 0.85
        time_threshold = timedelta(days=30)
        refined_themes = {}
        for label, data in themes.items():
            theme_emails = data['emails']
            theme_embeddings = np.array(data['embeddings'])
            centroid = theme_embeddings.mean(axis=0)
            earliest_date = min(
                dt.fromisoformat(email['date'].replace('Z', '+00:00')) 
                for email in theme_emails 
                if email.get('date') and 'T' in email['date']
            ) if any(email.get('date') for email in theme_emails) else None

            filtered_emails = []
            for email, embedding in zip(theme_emails, theme_embeddings):
                similarity = util.cos_sim(embedding, centroid).item()
                email_date = dt.fromisoformat(email['date'].replace('Z', '+00:00')) if email.get('date') and 'T' in email['date'] else None
                time_diff = abs((email_date - earliest_date).days) if email_date and earliest_date else float('inf')
                if similarity >= similarity_threshold and (time_diff <= time_threshold.days or time_diff == float('inf')):
                    filtered_emails.append(email)
                else:
                    logger.debug(f"Excluded email from theme {label}: index={email['index']}, similarity={similarity:.3f}, time_diff={time_diff} days")

            if len(filtered_emails) >= 2:
                refined_themes[label] = filtered_emails
                logger.debug(f"Theme {label} refined to {len(filtered_emails)} emails")
            else:
                logger.debug(f"Theme {label} discarded: insufficient emails after filtering ({len(filtered_emails)})")

        result = []
        for label, theme_emails in refined_themes.items():
            if not theme_emails:
                continue
            title_and_summary = generate_theme_title_and_summary(theme_emails)
            theme_id = str(uuid.uuid4())
            theme = {
                'theme_id': theme_id,
                'title': title_and_summary['title'],
                'summary': title_and_summary['summary'],
                'status': determine_status(theme_emails),
                'emails': [
                    {
                        'message_id': email['message_id'],
                        'index': email['index'],
                        'date': email['date'],
                        'from': email.get('from', 'N/A'),
                        'to': email.get('to', 'N/A'),
                        'subject': email.get('subject', ''),
                        'description': email.get('summary', 'Sin resumen')
                    } for email in theme_emails
                ],
                'similarity_score': float(np.mean([util.cos_sim(e, centroid).item() for e in theme_embeddings]))
            }

            themes_collection.insert_one({
                'theme_id': theme_id,
                'title': title_and_summary['title'],
                'summary': title_and_summary['summary'],
                'email_indices': [email['index'] for email in theme_emails],
                'user_id': user.username,
                'created_at': datetime.datetime.utcnow(),
                'similarity_score': theme['similarity_score']
            })

            result.append(theme)
            logger.debug(f"Theme {label}: {theme['title']}, {len(theme['emails'])} emails, similarity={theme['similarity_score']:.3f}")

        logger.info(f"Analysis completed: {len(result)} themes identified")
        return result
    except Exception as e:
        logger.error(f"Error analyzing themes: {str(e)}", exc_info=True)
        return []