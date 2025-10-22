import logging
from logging import handlers
import numpy as np
from sklearn.cluster import KMeans
from sentence_transformers import SentenceTransformer, util
from services.nlp_service import normalize_text, call_ollama_api
from services.cache_service import get_cached_result, cache_result
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION, CACHE_TTL
import re
from collections import Counter
import uuid
import json
from sklearn.metrics import silhouette_score

# Fallback for SUMMARY_CACHE_TTL if not defined
try:
    from config import SUMMARY_CACHE_TTL
except ImportError:
    SUMMARY_CACHE_TTL = CACHE_TTL if 'CACHE_TTL' in globals() else 604800  # Default to 7 days

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

# Load embedding model
embedding_model = SentenceTransformer('distiluse-base-multilingual-cased-v2')

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
    logger.info(f"Generando título y resumen para tema con {len(emails)} correos")
    # Create a unique cache key based on email indices
    cache_key = f"theme_summary:{'_'.join(sorted([email['index'] for email in emails]))}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        logger.debug(f"Resultado de título y resumen obtenido del caché: {cache_key}")
        return cached_result

    # Concatenate email content (subject, from, summary) for context, excluding body
    combined_text = ""
    senders = set()
    recipients = set()
    for email in emails:
        combined_text += f"Subject: {email.get('subject', '')}\n"
        combined_text += f"From: {email.get('from', '')}\n"
        combined_text += f"Summary: {email.get('summary', '')}\n\n"
        senders.add(email.get('from', 'N/A'))
        recipients.add(email.get('to', 'N/A'))

    # Truncate to avoid LLM input limits
    combined_text = normalize_text(combined_text)[:2000]
    if not combined_text:
        logger.warning("Texto combinado vacío para el tema")
        return {
            'title': 'Tema sin título',
            'summary': generate_tfidf_summary([''])
        }

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
        if not isinstance(result, dict) or 'title' not in result or 'summary' not in result:
            logger.warning(f"Respuesta LLM inválida para tema: {cleaned_response}")
            return {
                'title': ', '.join(extract_keywords(combined_text)) or 'Tema sin título',
                'summary': generate_tfidf_summary([combined_text])
            }
        logger.debug(f"Título y resumen generados: {result}")
        # Cache result without ttl parameter
        try:
            cache_result(cache_key, result)
        except Exception as cache_error:
            logger.error(f"Error al cachear título y resumen: {str(cache_error)}")
        return result
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error al generar título y resumen para tema: {str(e)}")
        return {
            'title': ', '.join(extract_keywords(combined_text)) or 'Tema sin título',
            'summary': generate_tfidf_summary([combined_text])
        }

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
        logger.warning("No se encontraron fechas válidas en los correos")
        return 'Unknown'
    recent_threshold = '2025-05-01'
    for email in emails:
        content = (email.get('body', '') + ' ' + email.get('summary', '')).lower()
        for keyword, status in status_keywords.items():
            if keyword in content:
                return status
    return 'Ongoing' if latest_date > recent_threshold else 'Inactive'

def analyze_themes(email_ids):
    """Analyze emails and group them by themes."""
    logger.info(f"Analizando temas para {len(email_ids)} correos con IDs: {email_ids[:5]}...")
    try:
        # Convert email_ids to strings
        email_ids = [str(id) for id in email_ids]
        
        # Fetch emails by index
        emails = list(emails_collection.find(
            {'index': {'$in': email_ids}},
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
        logger.info(f"Encontrados {len(emails)} correos para análisis")

        if not emails:
            logger.warning("No se encontraron correos para los índices proporcionados")
            return []

        # Ensure index and message_id are strings
        for email in emails:
            email['index'] = str(email.get('index', 'N/A'))
            email['message_id'] = str(email.get('message_id', 'N/A'))
            if email['index'] == 'N/A' or not email['index']:
                logger.error("Campo 'index' no válido en correo: message_id={email['message_id']}")
            if email['message_id'] == 'N/A' or not email['message_id']:
                logger.error("Campo 'message_id' no válido en correo: index={email['index']}")

        # Prepare texts for clustering with weighted subject and sender, excluding body
        texts = []
        valid_emails = []
        for email in emails:
            subject = email.get('subject', '') * 3  # Weight subject higher
            sender = email.get('from', '') * 2     # Weight sender higher
            text = f"{subject} {sender} {email.get('summary', '')}"
            normalized_text = normalize_text(text)
            if normalized_text:
                texts.append(normalized_text)
                valid_emails.append(email)
            else:
                logger.warning(f"Texto vacío después de normalización para correo: index={email['index']}")

        if not texts:
            logger.error("No se generaron textos válidos para clustering")
            return []

        # Generate embeddings
        logger.debug("Generando embeddings para los textos")
        embeddings = embedding_model.encode(texts, convert_to_numpy=True)

        # Determine optimal number of clusters using silhouette score
        n_emails = len(valid_emails)
        min_clusters = 2
        max_clusters = min(max(3, int(np.sqrt(n_emails))), 10)  # Up to 10 clusters
        best_n_clusters = min_clusters
        best_silhouette = -1

        if n_emails >= 4:  # Need at least 4 samples for silhouette score
            for n_clusters in range(min_clusters, max_clusters + 1):
                kmeans = KMeans(n_clusters=n_clusters, random_state=42)
                labels = kmeans.fit_predict(embeddings)
                silhouette = silhouette_score(embeddings, labels)
                logger.debug(f"Silhouette score for {n_clusters} clusters: {silhouette}")
                if silhouette > best_silhouette:
                    best_silhouette = silhouette
                    best_n_clusters = n_clusters

        logger.debug(f"Usando {best_n_clusters} clústeres para {n_emails} correos")

        # Perform clustering
        kmeans = KMeans(n_clusters=best_n_clusters, random_state=42)
        labels = kmeans.fit_predict(embeddings)
        centroids = kmeans.cluster_centers_

        # Filter outliers based on cosine similarity to centroid
        themes = {}
        similarity_threshold = 0.3  # Adjust based on testing
        for label, email, text, embedding in zip(labels, valid_emails, texts, embeddings):
            centroid = centroids[label]
            similarity = util.cos_sim(embedding, centroid).item()
            if similarity >= similarity_threshold:
                if label not in themes:
                    themes[label] = {'emails': [], 'texts': []}
                themes[label]['emails'].append(email)
                themes[label]['texts'].append(text)
            else:
                logger.debug(f"Excluyendo correo como outlier: index={email['index']}, similarity={similarity}")

        # Generate theme details
        result = []
        for label, data in themes.items():
            theme_emails = data['emails']
            theme_texts = data['texts']
            if not theme_emails:
                continue
            title_and_summary = generate_theme_title_and_summary(theme_emails)
            theme = {
                'theme_id': str(uuid.uuid4()),
                'title': title_and_summary['title'],
                'summary': title_and_summary['summary'],
                'status': determine_status(theme_emails),
                'emails': [
                    {
                        'message_id': email['message_id'],
                        'index': email['index'],
                        'date': email['date'],
                        'from': email.get('from', 'N/A'),
                        'subject': email.get('subject', ''),
                        'description': email.get('summary', 'Sin resumen')
                    } for email in theme_emails
                ]
            }
            result.append(theme)
            logger.debug(f"Tema {label}: {theme['title']}, {len(theme['emails'])} correos")

        logger.info(f"Análisis completado: {len(result)} temas identificados")
        return result
    except Exception as e:
        logger.error(f"Error al analizar temas: {str(e)}", exc_info=True)
        return []