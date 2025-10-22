# Artifact ID: 648e64f0-9604-4a3d-b203-f661abe13070
# Version: e2f3g4h5-9i6j-7k8l-m9n0-1o2p3q4r5s6t
import logging
from logging import handlers
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION
from services.nlp_service import call_ollama_api, normalize_text
import json
from collections import defaultdict

# Configure logging
logger = logging.getLogger('email_search_app.deep_analysis_service')
logger.setLevel(logging.DEBUG)
file_handler = handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
# Remove existing handlers to prevent duplicates
for handler in logger.handlers[:]:
    logger.removeHandler(handler)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]
themes_collection = db['themes']

# In-memory context store (session-based)
context_store = defaultdict(list)

def aggregate_email_data(theme_ids):
    """Fetch email data for given theme IDs from themes collection."""
    logger.info(f"Aggregating email data for theme IDs: {theme_ids}")
    try:
        # Fetch theme documents from themes collection
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

        # Fetch full email data
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

        # Format email data
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
                'relevant_terms': email.get('relevant_terms', [])
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
    try:
        # Validate theme IDs
        valid_themes = themes_collection.find(
            {'theme_id': {'$in': theme_ids}},
            {'theme_id': 1, '_id': 0}
        ).distinct('theme_id')
        logger.debug(f"Found valid theme IDs: {valid_themes}")

        if not valid_themes:
            logger.warning(f"No valid themes found for IDs: {theme_ids}")
            return {"error": "Invalid or non-existent theme IDs"}

        # Check for missing theme IDs
        missing_theme_ids = set(theme_ids) - set(valid_themes)
        if missing_theme_ids:
            logger.warning(f"Some theme IDs not found: {missing_theme_ids}")

        email_data = aggregate_email_data(theme_ids)
        if not email_data:
            logger.warning(f"No email data found for themes: {theme_ids}")
            return {"error": "No email data found for selected themes"}

        # Store initial context
        context_store[session_id] = [{
            "role": "system",
            "content": f"Estás analizando correos electrónicos relacionados con los temas seleccionados. Aquí está el contexto inicial de los correos:\n{json.dumps(email_data, ensure_ascii=False, indent=2)}"
        }]
        logger.debug(f"Stored context for session {session_id}: {len(email_data)} emails")

        return {"status": "Context initialized", "message": "Ready for prompt queries", "email_data": email_data}
    except Exception as e:
        logger.error(f"Error initializing deep analysis: {str(e)}", exc_info=True)
        return {"error": str(e)}

def process_deep_analysis_prompt(session_id, prompt):
    """Process a prompt using the stored context and LLM."""
    logger.info(f"Processing prompt for session: {session_id}, prompt: {prompt[:50]}...")
    try:
        if session_id not in context_store or not context_store[session_id]:
            return {"error": "No active context found. Please initialize analysis first."}

        # Append user prompt to context
        context_store[session_id].append({
            "role": "user",
            "content": prompt
        })

        # Prepare LLM prompt with escaped curly braces
        llm_prompt = f"""
Eres un asistente avanzado que analiza correos electrónicos para proporcionar respuestas detalladas y razonadas. Usa EXCLUSIVAMENTE el contexto proporcionado de los correos para responder al siguiente prompt de manera precisa. Sigue estas instrucciones:
- **Respuesta**: Proporciona una respuesta clara y específica al prompt, basada únicamente en el contenido de los correos (máximo 200 palabras).
- **Razonamiento**: Explica detalladamente (mínimo 100 palabras) cómo llegaste a la respuesta, citando información específica de los correos (por ejemplo, asunto, resumen, cuerpo). Indica qué correos usaste y por qué.
- **Alternativas**: Si el prompt es abierto, proporciona al menos una respuesta alternativa basada en los correos. Si no aplica, explica por qué no hay alternativas.
- **Referencias**: Lista los índices de los correos usados para la respuesta (campo 'index' del contexto).
Devuelve la respuesta en español, en formato JSON con los campos: "response", "reasoning", "alternatives", "references".

Contexto:
{json.dumps(context_store[session_id][0]["content"], ensure_ascii=False, indent=2)}

Prompt:
{prompt}

Ejemplo de respuesta:
```json
{{
  "response": "Se planificaron almuerzos para el equipo el 10 de junio.",
  "reasoning": "Basado en el correo con índice '123', el asunto 'Almuerzo equipo' menciona una reunión el 10 de junio. El resumen indica confirmación de asistencia. El correo '456' complementa con detalles logísticos.",
  "alternatives": ["Podría planificarse para el 11 de junio si hay conflictos."],
  "references": ["123", "456"]
}}
```
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

        # Enrich references with email metadata
        if result['references']:
            email_data = json.loads(context_store[session_id][0]["content"].split('\n', 1)[1])
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

        # Ensure alternatives if none provided
        if not result['alternatives']:
            result['alternatives'] = ["No se identificaron alternativas debido a la especificidad del prompt."]

        # Append LLM response to context
        context_store[session_id].append({
            "role": "assistant",
            "content": json.dumps(result, ensure_ascii=False)
        })

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
    try:
        if session_id in context_store:
            del context_store[session_id]
            return {"status": "Context reset successfully"}
        return {"status": "No context found for session"}
    except Exception as e:
        logger.error(f"Error resetting context: {str(e)}", exc_info=True)
        return {"error": str(e)}