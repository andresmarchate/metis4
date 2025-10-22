import logging
from logging import handlers
import numpy as np
from sklearn.cluster import KMeans
from sentence_transformers import SentenceTransformer
from services.nlp_service import normalize_text, call_ollama_api
from services.cache_service import get_cached_result, cache_result
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION, SUMMARY_CACHE_TTL
import re
from collections import Counter
import uuid
import json

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
embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

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

def generate_llm_summary(email):
    """Generate a summary using Mistral LLM via Ollama."""
    logger.info(f"Generando resumen LLM para correo: {email['message_id']}")
    cache_key = f"summary:{email['message_id']}"
    cached_summary = get_cached_result(cache_key)
    if cached_summary:
        logger.debug(f"Resumen obtenido del caché para {email['message_id']}")
        return cached_summary

    # Prepare input text
    text = f"{email.get('subject', '')} {email.get('body', '')} {email.get('summary', '')}"
    text = normalize_text(text)[:1000]  # Truncate to ~1000 chars
    if not text:
        logger.warning(f"Texto vacío para correo: {email['message_id']}")
        return generate_tfidf_summary([text])

    prompt = f"""
    Resuma este correo en 1-2 frases en español, enfocándose en el tema principal e intención. 
    Devuelva el resumen como una lista de puntos en formato JSON: ["frase1", "frase2"]. 
    Si solo hay una frase, devuelva ["frase"]. Ejemplo: ["Discusión sobre almuerzo", "Planificación de reunión"].
    
    Correo:
    {text}
    """

    try:
        response = call_ollama_api(prompt)
        cleaned_response = response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:].strip()
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3].strip()
        summary = json.loads(cleaned_response)
        if not isinstance(summary, list) or not all(isinstance(s, str) for s in summary):
            logger.warning(f"Respuesta LLM inválida para {email['message_id']}: {cleaned_response}")
            return generate_tfidf_summary([text])
        logger.debug(f"Resumen LLM generado: {summary}")
        cache_result(cache_key, summary, ttl=SUMMARY_CACHE_TTL)
        return summary
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error al generar resumen LLM para {email['message_id']}: {str(e)}")
        return generate_tfidf_summary([text])

def determine_status(emails):
    """Determine status based on keywords and recency."""
    status_keywords = {
        'resuelto': 'Resolved',
        'pendiente': 'Pending Action',
        'en curso': 'Ongoing',
        'acción requerida': 'Pending Action',
        'finalizado': 'Resolved'
    }
    latest_date = max(email['date'] for email in emails)
    recent_threshold = '2025-05-01'
    for email in emails:
        content = (email.get('body', '') + ' ' + email.get('summary', '')).lower()
        for keyword, status in status_keywords.items():
            if keyword in content:
                return status
    return 'Ongoing' if latest_date > recent_threshold else 'Inactive'

def analyze_themes(email_ids):
    """Analyze emails and group them by themes."""
    logger.info(f"Analizando temas para {len(email_ids)} correos")
    try:
        # Fetch emails
        emails = list(emails_collection.find(
            {'message_id': {'$in': email_ids}},
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
        if not emails:
            logger.warning("No se encontraron correos para analizar")
            return []

        # Prepare texts for clustering
        texts = [
            normalize_text(
                f"{email.get('subject', '')} {email.get('body', '')} {email.get('summary', '')}"
            ) for email in emails
        ]
        embeddings = embedding_model.encode(texts, convert_to_numpy=True)

        # Determine number of clusters
        n_clusters = min(max(3, int(np.sqrt(len(emails)))), 5)
        logger.debug(f"Usando {n_clusters} clústeres para {len(emails)} correos")

        # Perform clustering
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        labels = kmeans.fit_predict(embeddings)

        # Group emails by cluster
        themes = {}
        for label, email, text in zip(labels, emails, texts):
            if label not in themes:
                themes[label] = {'emails': [], 'texts': []}
            themes[label]['emails'].append(email)
            themes[label]['texts'].append(text)

        # Generate theme details
        result = []
        for label, data in themes.items():
            theme_emails = data['emails']
            theme_texts = data['texts']
            keywords = extract_keywords(' '.join(theme_texts))
            # Use LLM summary for the theme
            representative_email = max(theme_emails, key=lambda e: len(e.get('body', '') + e.get('summary', '')))
            theme = {
                'theme_id': str(uuid.uuid4()),
                'title': ', '.join(keywords) or 'Tema sin título',
                'summary': generate_llm_summary(representative_email),
                'status': determine_status(theme_emails),
                'emails': [
                    {
                        'message_id': email['message_id'],
                        'index': email.get('index', 'N/A'),
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