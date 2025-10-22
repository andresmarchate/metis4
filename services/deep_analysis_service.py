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
        # Fallback: Extract keywords manually
        words = re.findall(r'\w+', normalize_text(prompt))
        stopwords = set(['de', 'la', 'el', 'los', 'las', 'y', 'en', 'a', 'que', 'con', 'por', 'para'])
        terms = {word: {"frequency": count, "context": "Extraído del prompt", "type": "keyword"}
                 for word, count in Counter([w for w in words if w not in stopwords and len(w) > 3]).items()}
        cache_result(cache_key, terms)
        return terms

def aggregate_email_data(theme_ids, max_emails=5, prompt_terms=None, user=None):
    """Fetch top 5 most relevant emails based on term frequency overlap, filtered by user's mailboxes."""
    logger.info(f"Aggregating email data for theme IDs: {theme_ids}, user: {user.username if user else 'None'}")
    clean_context_store()
    try:
        if not user:
            raise ValueError("User must be provided for email aggregation")

        user_mailboxes = [mailbox['mailbox_id'] for mailbox in user.mailboxes]
        if not user_mailboxes:
            logger.warning(f"No mailboxes found for user: {user.username}")
            return []

        themes = list(themes_collection.find(
            {'theme_id': {'$in': theme_ids}, 'user_id': user.username},
            {'email_indices': 1, 'theme_id': 1, '_id': 0}
        ))
        if not themes:
            logger.warning(f"No themes found for user {user.username} with IDs: {theme_ids}")
            return []

        email_indices = set()
        for theme in themes:
            email_indices.update(theme.get('email_indices', []))

        if not email_indices:
            logger.warning(f"No email indices found for themes: {theme_ids}")
            return []

        emails = list(emails_collection.find(
            {'index': {'$in': list(email_indices)}, 'mailbox_id': {'$in': user_mailboxes}},
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
            logger.warning(f"No emails found for indices: {list(email_indices)} in user's mailboxes")
            return []

        # Rank emails by relevance if prompt terms provided
        if prompt_terms:
            ranked_emails = []
            for email in emails:
                email_terms = email.get('relevant_terms', {})
                score = 0
                for term in prompt_terms:
                    if term in email_terms:
                        score += prompt_terms[term]['frequency'] * email_terms[term]['frequency']
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

def initialize_deep_analysis(session_id, theme_ids, user):
    """Initialize deep analysis context for given themes and user."""
    logger.info(f"Initializing deep analysis for session: {session_id}, themes: {theme_ids}, user: {user.username}")
    clean_context_store()
    try:
        valid_themes = themes_collection.find(
            {'theme_id': {'$in': theme_ids}, 'user_id': user.username},
            {'theme_id': 1, '_id': 0}
        ).distinct('theme_id')
        logger.debug(f"Found valid theme IDs: {valid_themes}")

        if not valid_themes:
            logger.warning(f"No valid themes found for user {user.username} with IDs: {theme_ids}")
            return {"error": "Invalid or non-existent theme IDs"}

        missing_theme_ids = set(theme_ids) - set(valid_themes)
        if missing_theme_ids:
            logger.warning(f"Some theme IDs not found for user {user.username}: {missing_theme_ids}")

        email_data = aggregate_email_data(theme_ids, user=user)
        if not email_data:
            logger.warning(f"No email data found for themes: {theme_ids} for user {user.username}")
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

def process_deep_analysis_prompt(session_id, prompt, user):
    """Process a prompt using the stored context and LLM for the given user."""
    logger.info(f"Processing prompt for session: {session_id}, prompt: {prompt[:50]}..., user: {user.username}")
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
            email_data = aggregate_email_data(theme_ids, prompt_terms=prompt_terms, user=user)

        context_store[session_id] = [{
            "role": "system",
            "content": f"Estás analizando correos electrónicos relacionados con los temas seleccionados. Aquí está el contexto inicial de los correos:\n{json.dumps(email_data, ensure_ascii=False)}"
        }]

        context_store[session_id].append({
            "role": "user",
            "content": prompt
        })

        cache_key = f"deep_analysis:{user.username}:{session_id}:{hash(prompt)}"
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