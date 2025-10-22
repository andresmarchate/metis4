# Artifact ID: 648e64f0-9604-4a3d-b203-f661abe13070
# Version: p4q5r6s7-t8u9-v0w1-x2y3-z4a5b6c7d8
import logging
from logging import handlers
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION
from services.nlp_service import call_ollama_api, normalize_text
from services.cache_service import get_cached_result, cache_result
import json
from collections import defaultdict, Counter
import time
import re
import math

# Configure logging
logger = logging.getLogger('email_search_app.deep_analysis_service')
logger.setLevel(logging.DEBUG)
file_handler = handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
for handler in logger.handlers[:]:
    logger.removeHandler(handler)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]
themes_collection = db['themes']

# In-memory context store with expiration
context_store = defaultdict(list)
CONTEXT_TTL = 3600  # 1 hour
context_timestamps = {}

def clean_context_store():
    """Remove expired contexts to free memory."""
    current_time = time.time()
    expired_sessions = [sid for sid, ts in context_timestamps.items() if current_time - ts > CONTEXT_TTL]
    for sid in expired_sessions:
        logger.debug(f"Cleaning expired context for session: {sid}")
        context_store.pop(sid, None)
        context_timestamps.pop(sid, None)

def extract_prompt_terms(prompt):
    """Extract relevant terms from prompt using Ollama."""
    logger.info(f"Extracting terms from prompt: {prompt[:50]}...")
    cache_key = f"prompt_terms:{hash(prompt)}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        logger.debug(f"Retrieved cached prompt terms: {cache_key}")
        return cached_result

    llm_prompt = f"""
Analiza el siguiente prompt y extrae los términos relevantes con su frecuencia, contexto y tipo, similar a la estructura de 'relevant_terms' en los correos electrónicos. Devuelve el resultado en formato JSON con el formato: {{term: {{frequency: int, context: str, type: str}}}}.

Prompt:
{prompt}

Ejemplo de respuesta:
```json
{{
  "visita": {{ "frequency": 2, "context": "Evento programado", "type": "acción" }},
  "dia": {{ "frequency": 1, "context": "Tiempo especificado", "type": "temporal" }}
}}
```
"""
    try:
        response = call_ollama_api(llm_prompt)
        cleaned_response = response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:].strip()
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3].strip()
        terms = json.loads(cleaned_response)
        cache_result(cache_key, terms)
        return terms
    except Exception as e:
        logger.error(f"Error extracting prompt terms: {str(e)}")
        words = re.findall(r'\w+', normalize_text(prompt))
        stopwords = set(['de', 'la', 'el', 'los', 'las', 'y', 'en', 'a', 'que', 'con', 'por', 'para'])
        terms = {word: {"frequency": count, "context": "Extraído del prompt", "type": "keyword"}
                 for word, count in Counter([w for w in words if w not in stopwords and len(w) > 3]).items()}
        cache_result(cache_key, terms)
        return terms

def compute_term_frequencies(emails):
    """Compute term frequencies across all emails in a theme."""
    term_freq = defaultdict(lambda: {'total': 0, 'relevant': 0})
    total_emails = len(emails)
    for email in emails:
        email_terms = email.get('relevant_terms', {})
        for term, meta in email_terms.items():
            term_freq[term]['total'] += meta['frequency']
            term_freq[term]['relevant'] += meta['frequency']  # Assume all emails in theme are potentially relevant
    return term_freq, total_emails

def bayesian_relevance_score(email, prompt_terms, term_freq, total_emails):
    """Compute Bayesian relevance probability for an email."""
    email_terms = email.get('relevant_terms', {})
    overlapping_terms = set(prompt_terms.keys()) & set(email_terms.keys())
    if not overlapping_terms:
        return 0.0

    p_relevant = 0.5
    p_not_relevant = 1 - p_relevant

    log_prob_relevant = 0.0
    log_prob_not_relevant = 0.0
    for term in overlapping_terms:
        freq_in_email = email_terms[term]['frequency']
        p_term_relevant = (term_freq[term]['relevant'] + 1) / (sum(t['relevant'] for t in term_freq.values()) + len(term_freq))
        p_term_not_relevant = (1 + 1) / (total_emails + len(term_freq))
        log_prob_relevant += math.log(p_term_relevant) * freq_in_email
        log_prob_not_relevant += math.log(p_term_not_relevant) * freq_in_email

    try:
        log_p_relevant_terms = log_prob_relevant + math.log(p_relevant) - log_prob_not_relevant - math.log(p_not_relevant)
        p_relevant_terms = 1 / (1 + math.exp(-log_p_relevant_terms))
    except OverflowError:
        p_relevant_terms = 0.0
    return p_relevant_terms

def aggregate_email_data(theme_ids, max_emails=5, prompt_terms=None):
    """Fetch top 5 most relevant emails based on Bayesian relevance."""
    logger.info(f"Aggregating email data for theme IDs: {theme_ids}")
    clean_context_store()
    try:
        themes = list(themes_collection.find(
            {'theme_id': {'$in': theme_ids}},
            {'email_indices': 1, 'theme_id': 1, '_id': 0}
        ))
        if not themes:
            logger.warning(f"No themes found in collection for IDs: {theme_ids}")
            return []

        email_indices = set()
        found_theme_ids = set(theme['theme_id'] for theme in themes)
        missing_theme_ids = set(theme_ids) - found_theme_ids
        if missing_theme_ids:
            logger.warning(f"Missing theme IDs in collection: {missing_theme_ids}")

        for theme in themes:
            email_indices.update(theme.get('email_indices', []))
            logger.debug(f"Theme {theme['theme_id']}: found {len(theme.get('email_indices', []))} email indices")

        if not email_indices:
            logger.warning(f"No email indices found for theme IDs: {theme_ids}")
            return []

        emails = list(emails_collection.find(
            {'index': {'$in': list(email_indices)}},
            {
                'message_id': 1,
                'index': 1,
                'from': 1,
                'to': 1,
                'subject': 1,
                'date': 1,
                'body': 1,
                'summary': 1,
                'attachments_content': 1,
                'relevant_terms': 1,
                '_id': 0
            }
        ))

        if not emails:
            logger.warning(f"No emails found for indices: {list(email_indices)}")
            return []

        # Compute term frequencies for Bayesian scoring
        term_freq, total_emails = compute_term_frequencies(emails)

        # Rank emails by Bayesian relevance if prompt terms provided
        if prompt_terms:
            ranked_emails = []
            for email in emails:
                score = bayesian_relevance_score(email, prompt_terms, term_freq, total_emails)
                ranked_emails.append((email, score))
            ranked_emails = sorted(ranked_emails, key=lambda x: x[1], reverse=True)[:max_emails]
            emails = [email for email, _ in ranked_emails]
        else:
            emails = emails[:max_emails]  # Fallback: Take first 5 if no prompt terms

        email_data = []
        for email in emails:
            email_entry = {
                'index': str(email.get('index', 'N/A')),
                'message_id': str(email.get('message_id', 'N/A')),
                'from': email.get('from', 'N/A'),
                'to': email.get('to', 'N/A'),
                'subject': email.get('subject', ''),
                'date': email.get('date', ''),
                'body': email.get('body', ''),
                'summary': email.get('summary', ''),
                'attachments': email.get('attachments_content', ''),
                'relevant_terms': email.get('relevant_terms', {})
            }
            email_data.append(email_entry)
            logger.debug(f"Email data aggregated: {email_entry['index']}, subject: {email_entry['subject']}")

        logger.info(f"Aggregated {len(email_data)} emails for themes")
        return email_data
    except Exception as e:
        logger.error(f"Error aggregating email data: {str(e)}", exc_info=True)
        return []

def initialize_deep_analysis(session_id, theme_ids):
    """Initialize deep analysis context for given themes."""
    logger.info(f"Initializing deep analysis for session: {session_id}, themes: {theme_ids}")
    clean_context_store()
    try:
        valid_themes = themes_collection.find(
            {'theme_id': {'$in': theme_ids}},
            {'theme_id': 1, '_id': 0}
        ).distinct('theme_id')
        logger.debug(f"Found valid theme IDs: {valid_themes}")

        if not valid_themes:
            logger.warning(f"No valid themes found for IDs: {theme_ids}")
            return {"error": "Invalid or non-existent theme IDs"}

        missing_theme_ids = set(theme_ids) - set(valid_themes)
        if missing_theme_ids:
            logger.warning(f"Some theme IDs not found: {missing_theme_ids}")

        email_data = aggregate_email_data(theme_ids)
        if not email_data:
            logger.warning(f"No email data found for themes: {theme_ids}")
            return {"error": "No email data found for selected themes"}

        context_store[session_id] = [{
            "role": "system",
            "content": f"Estás analizando correos electrónicos relacionados con los temas seleccionados. Aquí está el contexto inicial de los correos:\n{json.dumps(email_data, ensure_ascii=False)}"
        }]
        context_timestamps[session_id] = time.time()
        logger.debug(f"Stored context for session {session_id}: {len(email_data)} emails")

        return {"status": "Context initialized", "session_id": session_id, "email_data": email_data}
    except Exception as e:
        logger.error(f"Error initializing deep analysis: {str(e)}", exc_info=True)
        return {"error": str(e)}

def process_deep_analysis_prompt(session_id, prompt):
    """Process a prompt using the stored context and LLM."""
    logger.info(f"Processing prompt for session: {session_id}, prompt: {prompt[:50]}...")
    clean_context_store()
    try:
        if session_id not in context_store or not context_store[session_id]:
            return {"error": "No active context found. Please initialize analysis first."}

        # Extract prompt terms
        prompt_terms = extract_prompt_terms(prompt)
        if not prompt_terms:
            logger.warning("No terms extracted from prompt, using all emails")
            email_data = json.loads(context_store[session_id][0]["content"].split('\n', 1)[1])
        else:
            # Re-aggregate emails with prompt terms
            theme_ids = [theme['theme_id'] for theme in themes_collection.find(
                {'email_indices': {'$in': [email['index'] for email in json.loads(context_store[session_id][0]["content"].split('\n', 1)[1])]}},
                {'theme_id': 1}
            )]
            email_data = aggregate_email_data(theme_ids, prompt_terms=prompt_terms)

        context_store[session_id] = [{
            "role": "system",
            "content": f"Estás analizando correos electrónicos relacionados con los temas seleccionados. Aquí está el contexto inicial de los correos:\n{json.dumps(email_data, ensure_ascii=False)}"
        }]

        context_store[session_id].append({
            "role": "user",
            "content": prompt
        })

        cache_key = f"deep_analysis:{session_id}:{hash(prompt)}"
        cached_result = get_cached_result(cache_key)
        if cached_result:
            logger.debug(f"Retrieved cached deep analysis result: {cache_key}")
            return cached_result

        llm_prompt = f"""
Eres un asistente avanzado que analiza correos electrónicos para proporcionar respuestas detalladas y razonadas. Usa EXCLUSIVAMENTE el contexto proporcionado de los correos para responder al siguiente prompt de manera precisa. Sigue estas instrucciones:
- **Respuesta**: Proporciona una respuesta clara y específica al prompt, basada únicamente en el contenido de los correos (máximo 200 palabras).
- **Razonamiento**: Explica detalladamente (mínimo 100 palabras) cómo llegaste a la respuesta, citando información específica de los correos (por ejemplo, asunto, resumen, cuerpo). Indica qué correos usaste y por qué.
- **Alternativas**: Si el prompt es abierto, proporciona al menos una respuesta alternativa basada en los correos. Si no aplica, explica por qué no hay alternativas.
- **Referencias**: Lista los índices de los correos usados para la respuesta (campo 'index' del contexto).
Devuelve la respuesta en español, en formato JSON con los campos: "response", "reasoning", "alternatives", "references".

Contexto:
{json.dumps(context_store[session_id][0]["content"], ensure_ascii=False)}

Prompt:
{prompt}

Ejemplo de respuesta:
{{
  "response": "Se planificaron almuerzos para el equipo el 10 de junio.",
  "reasoning": "Basado en el correo con índice '123', el asunto 'Almuerzo equipo' menciona una reunión el 10 de junio. El resumen indica confirmación de asistencia. El correo '456' complementa con detalles logísticos.",
  "alternatives": ["Podría planificarse para el 11 de junio si hay conflictos."],
  "references": ["123", "456"]
}}
"""
        logger.debug(f"Constructed LLM prompt: {llm_prompt[:500]}...")
        response = call_ollama_api(llm_prompt)
        cleaned_response = response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:].strip()
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3].strip()

        try:
            result = json.loads(cleaned_response)
            if not all(key in result for key in ['response', 'reasoning', 'alternatives', 'references']):
                raise ValueError("Invalid LLM response format")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Invalid LLM response: {str(e)}")
            result = {
                "response": "Error al procesar la respuesta del modelo.",
                "reasoning": f"No se pudo parsear la respuesta: {str(e)}",
                "alternatives": ["Revisar el contexto manualmente."],
                "references": []
            }

        if result['references']:
            enriched_references = []
            for ref_index in result['references']:
                email = next((e for e in email_data if e['index'] == ref_index), None)
                if email:
                    enriched_references.append({
                        'index': email['index'],
                        'subject': email['subject'],
                        'date': email['date'],
                        'from': email['from'],
                        'to': email['to'],
                        'summary': email['summary']
                    })
            result['references'] = enriched_references

        if not result['alternatives']:
            result['alternatives'] = ["No se identificaron alternativas debido a la especificidad del prompt."]

        context_store[session_id].append({
            "role": "assistant",
            "content": json.dumps(result, ensure_ascii=False)
        })
        context_timestamps[session_id] = time.time()
        cache_result(cache_key, result)

        logger.debug(f"Processed prompt result: {json.dumps(result, ensure_ascii=False)}")
        return result
    except Exception as e:
        logger.error(f"Error processing prompt: {str(e)}", exc_info=True)
        return {
            "response": "Error al procesar el prompt.",
            "reasoning": str(e),
            "alternatives": ["Revisar el contexto manualmente."],
            "references": []
        }

def reset_deep_analysis_context(session_id):
    """Reset the context for a given session."""
    logger.info(f"Resetting context for session: {session_id}")
    clean_context_store()
    try:
        if session_id in context_store:
            del context_store[session_id]
            context_timestamps.pop(session_id, None)
            return {"status": "Context reset successfully"}
        return {"status": "No context found for session"}
    except Exception as e:
        logger.error(f"Error resetting context: {str(e)}", exc_info=True)
        return {"error": str(e)}