import logging
from logging import handlers
import numpy as np
from sklearn.cluster import KMeans
from sentence_transformers import SentenceTransformer, util
from sklearn.metrics import silhouette_score
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

# Fallback for SUMMARY_CACHE_TTL
try:
    from config import SUMMARY_CACHE_TTL
except ImportError:
    SUMMARY_CACHE_TTL = CACHE_TTL if 'CACHE_TTL' in globals() else 604800  # 7 days

# Configure logging
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

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]
themes_collection = db['themes']

# Load embedding model
embedding_model = SentenceTransformer('distiluse-base-multilingual-cased-v2')

def truncate_text(text, max_length=1000):
    """Truncate text to a maximum length to reduce memory usage."""
    return text[:max_length] if text and len(text) > max_length else text

def encode_texts_with_batch(texts, batch_size=16, use_cpu_fallback=True):
    """Encode texts in batches with fallback to CPU if CUDA fails."""
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        logger.debug(f"Encoding batch of {len(batch)} texts")
        try:
            # Attempt GPU encoding
            batch_embeddings = embedding_model.encode(batch, convert_to_numpy=True, batch_size=batch_size, device='cuda')
            embeddings.append(batch_embeddings)
        except RuntimeError as e:
            if 'CUDA' in str(e) and use_cpu_fallback:
                logger.warning(f"CUDA error during encoding, falling back to CPU: {str(e)}")
                # Move model to CPU
                embedding_model.to('cpu')
                batch_embeddings = embedding_model.encode(batch, convert_to_numpy=True, batch_size=batch_size, device='cpu')
                embeddings.append(batch_embeddings)
                # Move model back to GPU
                embedding_model.to('cuda')
            else:
                logger.error(f"Encoding failed: {str(e)}")
                raise
    return np.vstack(embeddings)

def extract_keywords(text, top_n=5):
    """Extract top N keywords from text, ignoring stopwords."""
    if not text:
        return []
    words = re.findall(r'\w+', normalize_text(text))
    stopwords = set(['de', 'la', 'el', 'los', 'las', 'y', 'en', 'a', 'que', 'con', 'por', 'para'])
    words = [w for w in words if w not in stopwords and len(w) > 3]
    return [word for word, _ in Counter(words).most_common(top_n)]

def generate_tfidf_summary(texts):
    """Generate a fallback summary by combining keywords into a sentence."""
    if not texts:
        return ["No hay contenido suficiente para generar un resumen."]
    combined_text = ' '.join(texts)
    keywords = extract_keywords(combined_text, top_n=5)
    if not keywords:
        return ["Sin resumen disponible."]
    return [f"Tema relacionado con {', '.join(keywords)}."]

def generate_theme_title_and_summary(emails):
    """Generate a human-readable title and structured summary for a theme using LLM."""
    logger.info(f"Generating title and summary for theme with {len(emails)} emails")
    cache_key = f"theme_summary:{'_'.join(sorted([email['index'] for email in emails]))}"
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
    """Determine status based on keywords and recency."""
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
    """Analyze emails and group them by themes, filtered by user's mailboxes."""
    logger.info(f"Analyzing themes for {len(email_ids)} emails with IDs: {email_ids[:5]}... for user: {user.username}")
    try:
        email_ids = [str(id) for id in email_ids]
        user_mailboxes = [mailbox['mailbox_id'] for mailbox in user.mailboxes]
        if not user_mailboxes:
            logger.warning(f"No mailboxes found for user: {user.username}")
            return []

        # Find emails that belong to the user's mailboxes
        emails = list(emails_collection.find(
            {'index': {'$in': email_ids}, 'mailbox_id': {'$in': user_mailboxes}},
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
            logger.warning("No emails found for provided indices in user's mailboxes")
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
        for email in emails:
            subject = email.get('subject', '') * 3
            sender = email.get('from', '') * 2
            summary = email.get('summary', '')
            text = f"{subject} {sender} {summary}"
            normalized_text = truncate_text(normalize_text(text), max_length=1000)
            if normalized_text:
                texts.append(normalized_text)
                valid_emails.append(email)
            else:
                logger.warning(f"Empty normalized text for email: index={email['index']}")

        if not texts:
            logger.error("No valid texts generated for clustering")
            return []

        logger.debug("Generating embeddings for texts")
        embeddings = encode_texts_with_batch(texts, batch_size=16)

        n_emails = len(valid_emails)
        min_clusters = 2
        max_clusters = min(max(3, int(np.sqrt(n_emails))), 10)
        best_n_clusters = min_clusters
        best_silhouette = -1

        if n_emails >= 4:
            for n_clusters in range(min_clusters, max_clusters + 1):
                kmeans = KMeans(n_clusters=n_clusters, random_state=42)
                labels = kmeans.fit_predict(embeddings)
                silhouette = silhouette_score(embeddings, labels)
                logger.debug(f"Silhouette score for {n_clusters} clusters: {silhouette}")
                if silhouette > best_silhouette:
                    best_silhouette = silhouette
                    best_n_clusters = n_clusters

        logger.debug(f"Using {best_n_clusters} clusters for {n_emails} emails")
        kmeans = KMeans(n_clusters=best_n_clusters, random_state=42)
        labels = kmeans.fit_predict(embeddings)
        centroids = kmeans.cluster_centers_

        themes = {}
        similarity_threshold = 0.3
        for label, email, text, embedding in zip(labels, valid_emails, texts, embeddings):
            centroid = centroids[label]
            similarity = util.cos_sim(embedding, centroid).item()
            if similarity >= similarity_threshold:
                if label not in themes:
                    themes[label] = {'emails': [], 'texts': []}
                themes[label]['emails'].append(email)
                themes[label]['texts'].append(text)
            else:
                logger.debug(f"Excluding email as outlier: index={email['index']}, similarity={similarity}")

        result = []
        for label, data in themes.items():
            theme_emails = data['emails']
            theme_texts = data['texts']
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
                ]
            }

            # Store theme in MongoDB with user_id
            themes_collection.insert_one({
                'theme_id': theme_id,
                'title': title_and_summary['title'],
                'summary': title_and_summary['summary'],
                'email_indices': [email['index'] for email in theme_emails],
                'user_id': user.username,
                'created_at': datetime.datetime.utcnow()
            })

            result.append(theme)
            logger.debug(f"Theme {label}: {theme['title']}, {len(theme['emails'])} emails")

        logger.info(f"Analysis completed: {len(result)} themes identified")
        return result
    except Exception as e:
        logger.error(f"Error analyzing themes: {str(e)}", exc_info=True)
        return []