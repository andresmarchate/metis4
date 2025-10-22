from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION
import uuid
from datetime import datetime
from typing import List, Dict, Any
import logging
import re
from services.nlp_service import normalize_text, call_ollama_api
from services.cache_service import get_cached_result, cache_result
from collections import Counter, defaultdict
import json
import time

# Configure logging
logger = logging.getLogger('email_search_app.deep_conversation_analysis_service')
logger.setLevel(logging.DEBUG)
file_handler = logging.handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

class DeepConversationAnalysisService:
    def __init__(self):
        logger.info("Conectando a MongoDB: %s", MONGO_URI)
        self.client = MongoClient(MONGO_URI)
        self.db = self.client[MONGO_DB_NAME]
        self.emails_collection = self.db[MONGO_EMAILS_COLLECTION]
        self.themes_collection = self.db['themes']
        self.sessions = {}  # In-memory session storage
        self.context_store = defaultdict(list)  # Context store for prompts
        self.context_timestamps = {}  # Timestamps for context expiration
        self.CONTEXT_TTL = 3600  # 1 hour
        logger.info("Conexión a MongoDB establecida")

    def extract_email_from_input(self, input_str):
        """Extract email address from input (e.g., 'ANDRES <andres.m.tirado@gmail.com>')."""
        if not input_str or not isinstance(input_str, str):
            return None
        match = re.search(r'<([^>]+@[^>]+)>', input_str, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', input_str, re.IGNORECASE)
        return email_match.group(0).lower() if email_match else None

    def initialize_conversation_analysis(self, email1: str, email2: str, start_date: str, end_date: str, theme_ids: List[str] = None, user=None) -> Dict[str, Any]:
        """
        Initialize deep conversation analysis for two email addresses and a date range for the given user.
        Uses MongoDB themes collection to filter emails by theme_ids.
        """
        logger.info(f"Initializing conversation analysis: email1={email1}, email2={email2}, start_date={start_date}, end_date={end_date}, theme_ids={theme_ids}, user={user.username if user else 'None'}")
        
        try:
            if not user:
                raise ValueError("User must be provided for conversation analysis")

            user_mailboxes = [mailbox['mailbox_id'] for mailbox in user.mailboxes]
            if not user_mailboxes:
                logger.warning(f"No mailboxes found for user: {user.username}")
                return {"error": "No mailboxes found for user"}

            # Validate inputs
            if not email1 or not email2 or not start_date or not end_date:
                raise ValueError("Missing required parameters: email1, email2, start_date, end_date")
            
            # Extract email addresses
            email1_addr = self.extract_email_from_input(email1)
            email2_addr = self.extract_email_from_input(email2)
            if not email1_addr or not email2_addr:
                raise ValueError(f"Invalid email addresses: {email1}, {email2}")

            # Parse dates
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            except ValueError as e:
                raise ValueError(f"Invalid date format: {str(e)}")

            # Fetch themes from MongoDB for the user
            selected_themes = []
            email_indices = set()
            if theme_ids:
                themes = list(self.themes_collection.find(
                    {'theme_id': {'$in': theme_ids}, 'user_id': user.username},
                    {'theme_id': 1, 'title': 1, 'summary': 1, 'email_indices': 1, '_id': 0}
                ))
                logger.debug(f"Found {len(themes)} themes in MongoDB for theme_ids: {theme_ids} and user: {user.username}")
                if not themes:
                    logger.warning(f"No themes found in MongoDB for theme_ids: {theme_ids} and user: {user.username}")
                    themes = []

                for theme in themes:
                    selected_themes.append({
                        "theme_id": theme["theme_id"],
                        "title": theme["title"],
                        "summary": theme["summary"],
                        "status": "Activo",
                        "emails": [{"index": str(idx), "message_id": "", "from": "", "to": "", "date": "", "subject": "", "description": ""} for idx in theme["email_indices"]]
                    })
                    email_indices.update(str(idx) for idx in theme["email_indices"])
            else:
                logger.info("No theme_ids provided, fetching all emails for conversation")
                email_indices = None

            # Fetch emails using MongoDB, filtered by user's mailboxes
            pipeline = [
                {
                    '$match': {
                        '$or': [
                            {
                                'from': {'$regex': f'\\b{re.escape(email1_addr)}\\b', '$options': 'i'},
                                'to': {'$regex': f'\\b{re.escape(email2_addr)}\\b', '$options': 'i'}
                            },
                            {
                                'from': {'$regex': f'\\b{re.escape(email2_addr)}\\b', '$options': 'i'},
                                'to': {'$regex': f'\\b{re.escape(email1_addr)}\\b', '$options': 'i'}
                            }
                        ],
                        'mailbox_id': {'$in': user_mailboxes}
                    }
                },
                {
                    '$addFields': {
                        'parsedDate': {
                            '$toDate': '$date'
                        }
                    }
                },
                {
                    '$match': {
                        'parsedDate': {
                            '$gte': start_dt,
                            '$lte': end_dt
                        }
                    }
                }
            ]

            if email_indices:
                pipeline.insert(0, {
                    '$match': {
                        'index': {'$in': list(email_indices)}
                    }
                })

            pipeline.extend([
                {
                    '$sort': {'parsedDate': -1}
                },
                {
                    '$project': {
                        'message_id': 1,
                        'index': 1,
                        'from': 1,
                        'to': 1,
                        'subject': 1,
                        'date': 1,
                        'summary': 1,
                        'body': 1,
                        'relevant_terms': 1,
                        '_id': 0
                    }
                }
            ])

            logger.debug(f"Ejecutando pipeline MongoDB: {json.dumps(pipeline, default=str)}")
            emails = list(self.emails_collection.aggregate(pipeline))
            logger.info(f"Found {len(emails)} emails for conversation analysis")

            if not emails:
                logger.warning("No emails found matching criteria for user")
                return {"status": "No emails found", "session_id": None, "themes": selected_themes, "email_data": []}

            # Update selected_themes with actual email data
            for theme in selected_themes:
                theme_emails = []
                for theme_email in theme["emails"]:
                    email = next((e for e in emails if str(e["index"]) == theme_email["index"]), None)
                    if email:
                        theme_emails.append({
                            "index": str(email["index"]),
                            "message_id": str(email["message_id"]),
                            "from": email.get("from", "N/A"),
                            "to": email.get("to", "N/A"),
                            "date": email.get("date", ""),
                            "subject": email.get("subject", ""),
                            "description": email.get("summary", "") or email.get("body", "")[:100]
                        })
                theme["emails"] = theme_emails

            # Create session
            session_id = str(uuid.uuid4())
            self.sessions[session_id] = {
                "email1": email1_addr,
                "email2": email2_addr,
                "start_date": start_date,
                "end_date": end_date,
                "themes": selected_themes,
                "emails": [{"message_id": e["message_id"], "index": str(e["index"])} for e in emails],
                "selected_theme_ids": theme_ids or [],
                "user": user  # Almacenar el objeto completo del usuario
            }

            # Format email data for frontend
            email_data = [{
                "index": str(email["index"]),
                "message_id": str(email["message_id"]),
                "from": email.get("from", "N/A"),
                "to": email.get("to", "N/A"),
                "subject": email.get("subject", ""),
                "date": email.get("date", ""),
                "summary": email.get("summary", "")
            } for email in emails]

            logger.info(f"Initialized session with {len(emails)} emails for themes: {theme_ids}")
            return {
                "status": "Context initialized",
                "session_id": session_id,
                "themes": selected_themes,
                "email_data": email_data
            }

        except Exception as e:
            logger.error(f"Error initializing conversation analysis: {str(e)}", exc_info=True)
            return {"error": str(e)}

    def clean_context_store(self):
        """Remove expired contexts to free memory."""
        current_time = time.time()
        expired_sessions = [sid for sid, ts in self.context_timestamps.items() if current_time - ts > self.CONTEXT_TTL]
        for sid in expired_sessions:
            logger.debug(f"Cleaning expired context for session: {sid}")
            self.context_store.pop(sid, None)
            self.context_timestamps.pop(sid, None)

    def extract_prompt_terms(self, prompt):
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
  "acuerdo": {{ "frequency": 1, "context": "Decisiones tomadas", "type": "acción" }},
  "conversación": {{ "frequency": 1, "context": "Intercambio de correos", "type": "concepto" }}
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

    def aggregate_email_data(self, session_id: str, theme_id: str, max_emails: int = 5, prompt_terms: Dict[str, Dict] = None) -> List[Dict]:
        """Fetch top 5 most relevant emails for a theme based on term frequency overlap for the user's mailboxes."""
        logger.info(f"Aggregating email data for session_id: {session_id}, theme_id: {theme_id}")
        self.clean_context_store()
        try:
            if session_id not in self.sessions:
                logger.warning(f"Session not found: {session_id}")
                return []

            session = self.sessions[session_id]
            theme = next((t for t in session["themes"] if t["theme_id"] == theme_id), None)
            if not theme:
                logger.warning(f"Theme not found in session: {theme_id}")
                return []

            email_indices = [email["index"] for email in theme["emails"]]
            if not email_indices:
                logger.warning(f"No email indices found for theme: {theme_id}")
                return []

            user = session.get('user')  # Obtener directamente el objeto usuario
            if not user:
                logger.error("User not found in session data")
                return []

            user_mailboxes = [mailbox['mailbox_id'] for mailbox in user.mailboxes]
            emails = list(self.emails_collection.find(
                {'index': {'$in': email_indices}, 'mailbox_id': {'$in': user_mailboxes}},
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
                logger.warning(f"No emails found for indices: {email_indices} in user's mailboxes")
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
                emails = emails[:max_emails]

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

            logger.info(f"Aggregated {len(email_data)} emails for theme")
            return email_data
        except Exception as e:
            logger.error(f"Error aggregating email data: {str(e)}")
            return []

    def process_conversation_prompt(self, session_id: str, prompt: str, user) -> Dict[str, Any]:
        """
        Process a prompt for the conversation analysis session for the given user.
        Analyzes emails within the selected theme to answer the prompt.
        """
        logger.info(f"Processing prompt for session_id: {session_id}, prompt: {prompt[:50]}..., user: {user.username}")
        self.clean_context_store()
        try:
            if session_id not in self.sessions:
                return {"error": "Session not found"}

            session = self.sessions[session_id]
            if not session["themes"]:
                return {"error": "No themes available in session"}

            if not session["selected_theme_ids"]:
                return {"error": "No theme selected for analysis"}

            theme_id = session["selected_theme_ids"][0]
            logger.debug(f"Using theme_id: {theme_id} for prompt processing")

            # Extract prompt terms
            prompt_terms = self.extract_prompt_terms(prompt)
            if not prompt_terms:
                logger.warning("No terms extracted from prompt, using all emails")
                email_data = self.aggregate_email_data(session_id, theme_id)
            else:
                email_data = self.aggregate_email_data(session_id, theme_id, prompt_terms=prompt_terms)

            if not email_data:
                return {
                    "response": "No se encontraron correos para procesar la consulta.",
                    "reasoning": "No hay correos relevantes para el tema seleccionado.",
                    "alternatives": [],
                    "references": []
                }

            # Initialize context
            self.context_store[session_id] = [{
                "role": "system",
                "content": f"Estás analizando correos electrónicos relacionados con un tema de conversación. Aquí está el contexto inicial de los correos:\n{json.dumps(email_data, ensure_ascii=False)}"
            }]
            self.context_store[session_id].append({
                "role": "user",
                "content": prompt
            })
            self.context_timestamps[session_id] = time.time()

            cache_key = f"deep_conversation_analysis:{user.username}:{session_id}:{hash(prompt)}"
            cached_result = get_cached_result(cache_key)
            if cached_result:
                logger.debug(f"Retrieved cached deep conversation analysis result: {cache_key}")
                return cached_result

            llm_prompt = f"""
Eres un asistente avanzado que analiza correos electrónicos para proporcionar respuestas detalladas y razonadas. Usa EXCLUSIVAMENTE el contexto proporcionado de los correos para responder al siguiente prompt de manera precisa. Sigue estas instrucciones:
- **Respuesta**: Proporciona una respuesta clara y específica al prompt, basada únicamente en el contenido de los correos (máximo 200 palabras).
- **Razonamiento**: Explica detalladamente (mínimo 100 palabras) cómo llegaste a la respuesta, citando información específica de los correos (por ejemplo, asunto, resumen, cuerpo). Indica qué correos usaste y por qué.
- **Alternativas**: Si el prompt es abierto, proporciona al menos una respuesta alternativa basada en los correos. Si no aplica, explica por qué no hay alternativas.
- **Referencias**: Lista los índices de los correos usados para la respuesta (campo 'index' del contexto).
Devuelve la respuesta en español, en formato JSON con los campos: "response", "reasoning", "alternatives", "references".

Contexto:
{json.dumps(self.context_store[session_id][0]["content"], ensure_ascii=False)}

Prompt:
{prompt}

Ejemplo de respuesta:
{{
  "response": "Se acordó una reunión el 10 de junio para discutir el proyecto.",
  "reasoning": "Basado en el correo con índice '123', el asunto 'Reunión proyecto' menciona un acuerdo para reunirse el 10 de junio. El resumen indica confirmación de asistencia. El correo '456' complementa con detalles logísticos.",
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

            self.context_store[session_id].append({
                "role": "assistant",
                "content": json.dumps(result, ensure_ascii=False)
            })
            self.context_timestamps[session_id] = time.time()
            cache_result(cache_key, result)

            logger.info(f"Prompt processed successfully for session_id: {session_id}")
            return result
        except Exception as e:
            logger.error(f"Error processing conversation prompt: {str(e)}")
            return {
                "response": "Error al procesar la consulta.",
                "reasoning": f"Ocurrió un error inesperado: {str(e)}",
                "alternatives": [],
                "references": []
            }

    def reset_conversation_context(self, session_id: str) -> Dict[str, str]:
        """
        Reset the conversation analysis context for a given session.
        """
        logger.info(f"Resetting conversation context for session: {session_id}")
        try:
            if session_id in self.sessions:
                del self.sessions[session_id]
            if session_id in self.context_store:
                del self.context_store[session_id]
                self.context_timestamps.pop(session_id, None)
            return {"status": "Context reset"}
        except Exception as e:
            logger.error(f"Error resetting conversation context: {str(e)}")
            return {"error": str(e)}