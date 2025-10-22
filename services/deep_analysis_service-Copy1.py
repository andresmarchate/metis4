# Artifact ID: e5f8d4b2-9c3e-4f1a-b7d6-2a4c8f7e3d9b
# Version: c3a7e9f1-6b2d-4e9a-a3c4-8f1d7b5e2f0c
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
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]

# In-memory context store (session-based)
context_store = defaultdict(list)

def aggregate_email_data(theme_ids):
    """Fetch email data for given theme IDs."""
    logger.info(f"Aggregating email data for theme IDs: {theme_ids}")
    try:
        # Fetch themes from previous analysis (simulated via email lookup)
        email_ids = set()
        for theme_id in theme_ids:
            # Assume theme_id maps to email indices (from analysis_service.py)
            emails = emails_collection.find(
                {'index': {'$in': emails_collection.distinct('index', {'theme_id': theme_id})}},
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
            )
            for email in emails:
                email_ids.add(email['index'])

        # Fetch full email data
        emails = list(emails_collection.find(
            {'index': {'$in': list(email_ids)}},
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
            logger.warning("No emails found for theme IDs: %s", theme_ids)
            return []

        # Format email data
        email_data = []
        for email in emails:
            email_data.append({
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
            })

        logger.info(f"Aggregated {len(email_data)} emails for themes")
        return email_data
    except Exception as e:
        logger.error(f"Error aggregating email data: {str(e)}", exc_info=True)
        return []

def initialize_deep_analysis(session_id, theme_ids):
    """Initialize deep analysis context for given themes."""
    logger.info(f"Initializing deep analysis for session: {session_id}, themes: {theme_ids}")
    try:
        email_data = aggregate_email_data(theme_ids)
        if not email_data:
            return {"error": "No email data found for selected themes"}

        # Store initial context
        context_store[session_id] = [{
            "role": "system",
            "content": f"Estás analizando correos electrónicos relacionados con los temas seleccionados. Aquí está el contexto inicial de los correos:\n{json.dumps(email_data, ensure_ascii=False, indent=2)}"
        }]

        return {"status": "Context initialized", "message": "Ready for prompt queries"}
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

        # Prepare LLM prompt
        llm_prompt = f"""
        Eres un asistente avanzado que analiza correos electrónicos para proporcionar respuestas detalladas y razonadas. Usa el contexto proporcionado de los correos para responder al siguiente prompt de manera precisa, explicando tu razonamiento y ofreciendo alternativas si la pregunta es abierta. Devuelve la respuesta en español, en formato JSON con los siguientes campos:
        - "response": La respuesta principal al prompt.
        - "reasoning": Explicación detallada de cómo llegaste a la respuesta.
        - "alternatives": Lista de respuestas alternativas (si aplica, o lista vacía).
        - "references": Lista de índices de correos utilizados (si aplica).

        Contexto:
        {json.dumps(context_store[session_id][-1]["content"], ensure_ascii=False, indent=2)}

        Prompt:
        {prompt}
        """

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
                "alternatives": [],
                "references": []
            }

        # Append LLM response to context
        context_store[session_id].append({
            "role": "assistant",
            "content": json.dumps(result, ensure_ascii=False)
        })

        return result
    except Exception as e:
        logger.error(f"Error processing prompt: {str(e)}", exc_info=True)
        return {
            "response": "Error al procesar el prompt.",
            "reasoning": str(e),
            "alternatives": [],
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