# Artifact ID: a4697495-cd3e-4603-ac01-01546d5d7a8e
# Version: d7e8f9g0-h1i2-3456-d9e0-f1g2h3i4j5
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION
import uuid
from datetime import datetime
from typing import List, Dict, Any
import logging
import re

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
        self.sessions = {}  # In-memory session storage (replace with Redis in production)
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

    def initialize_conversation_analysis(self, email1: str, email2: str, start_date: str, end_date: str, theme_ids: List[str] = None) -> Dict[str, Any]:
        """
        Initialize deep conversation analysis for two email addresses and a date range.
        Returns a session ID, themes, and email data.
        """
        logger.info(f"Initializing conversation analysis: email1={email1}, email2={email2}, start_date={start_date}, end_date={end_date}, theme_ids={theme_ids}")
        
        try:
            # Validate inputs
            if not email1 or not email2 or not start_date or not end_date:
                raise ValueError("Missing required parameters: email1, email2, start_date, end_date")
            
            # Extract email addresses
            email1_addr = self.extract_email_from_input(email1)
            email2_addr = self.extract_email_from_input(email2)
            if not email1_addr or not email2_addr:
                raise ValueError(f"Invalid email addresses: email1={email1}, email2={email2}")

            # Parse dates
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            except ValueError as e:
                raise ValueError(f"Invalid date format: {str(e)}")

            # Escape special regex characters
            email1_escaped = re.escape(email1_addr)
            email2_escaped = re.escape(email2_addr)

            # Fetch emails using MongoDB aggregation
            pipeline = [
                {
                    '$match': {
                        '$or': [
                            {
                                'from': {'$regex': f'\\b{email1_escaped}\\b', '$options': 'i'},
                                'to': {'$regex': f'\\b{email2_escaped}\\b', '$options': 'i'}
                            },
                            {
                                'from': {'$regex': f'\\b{email2_escaped}\\b', '$options': 'i'},
                                'to': {'$regex': f'\\b{email1_escaped}\\b', '$options': 'i'}
                            }
                        ]
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
                },
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
                        '_id': 0
                    }
                }
            ]
            logger.debug(f"Ejecutando pipeline MongoDB: {pipeline}")
            emails = list(self.emails_collection.aggregate(pipeline))
            logger.info(f"Found {len(emails)} emails for conversation analysis")

            if not emails:
                return {"status": "No emails found", "session_id": None, "themes": [], "email_data": []}

            # Generate themes
            themes = self._generate_conversation_themes(emails, theme_ids)
            logger.info(f"Generated {len(themes)} themes")

            # Create session
            session_id = str(uuid.uuid4())
            self.sessions[session_id] = {
                "email1": email1_addr,
                "email2": email2_addr,
                "start_date": start_date,
                "end_date": end_date,
                "themes": themes,
                "emails": [{"message_id": e["message_id"], "index": e["index"]} for e in emails]
            }

            # Format email data for frontend
            email_data = [{
                "index": str(email["index"]),
                "message_id": str(email["message_id"]),
                "from": email["from"],
                "to": email["to"],
                "subject": email["subject"],
                "date": email["date"],
                "summary": email["summary"]
            } for email in emails]

            return {
                "status": "Context initialized",
                "session_id": session_id,
                "themes": themes,
                "email_data": email_data
            }

        except Exception as e:
            logger.error(f"Error initializing conversation analysis: {str(e)}")
            return {"error": str(e)}

    def _generate_conversation_themes(self, emails: List[Dict], theme_ids: List[str] = None) -> List[Dict[str, Any]]:
        """
        Generate themes from conversation emails, optionally filtered by theme_ids.
        Returns all themes if theme_ids don't match.
        """
        themes = []
        try:
            # Group emails by subject
            subject_groups = {}
            for email in emails:
                subject = email["subject"] or "No Subject"
                if subject not in subject_groups:
                    subject_groups[subject] = []
                subject_groups[subject].append(email)

            # Create themes from subject groups
            for subject, group in subject_groups.items():
                theme_id = str(uuid.uuid4())
                theme = {
                    "theme_id": theme_id,
                    "title": subject[:50],
                    "summary": {
                        "tema": subject,
                        "involucrados": list(set([email["from"] for email in group] + [email["to"] for email in group])),
                        "historia": f"Conversación sobre {subject} con {len(group)} correos.",
                        "proximos_pasos": "Revisar detalles en los correos.",
                        "puntos_claves": [email["summary"] or "No summary" for email in group]
                    },
                    "status": "Activo",
                    "emails": [
                        {
                            "index": str(email["index"]),
                            "message_id": str(email["message_id"]),
                            "from": email["from"],
                            "to": email["to"],
                            "date": email["date"],
                            "subject": email["subject"],
                            "description": email["summary"] or email["body"][:100]
                        } for email in group
                    ]
                }
                logger.debug(f"Generated theme: {theme_id}, title: {subject[:50]}")
                # Include theme if no theme_ids provided or if theme_id matches
                if not theme_ids or theme_id in theme_ids:
                    themes.append(theme)
                else:
                    logger.debug(f"Theme {theme_id} not included; theme_ids provided: {theme_ids}")

            if not themes and theme_ids:
                logger.warning(f"No themes matched provided theme_ids: {theme_ids}. Including all themes.")
                for subject, group in subject_groups.items():
                    theme_id = str(uuid.uuid4())
                    theme = {
                        "theme_id": theme_id,
                        "title": subject[:50],
                        "summary": {
                            "tema": subject,
                            "involucrados": list(set([email["from"] for email in group] + [email["to"] for email in group])),
                            "historia": f"Conversación sobre {subject} con {len(group)} correos.",
                            "proximos_pasos": "Revisar detalles en los correos.",
                            "puntos_claves": [email["summary"] or "No summary" for email in group]
                        },
                        "status": "Activo",
                        "emails": [
                            {
                                "index": str(email["index"]),
                                "message_id": str(email["message_id"]),
                                "from": email["from"],
                                "to": email["to"],
                                "date": email["date"],
                                "subject": email["subject"],
                                "description": email["summary"] or email["body"][:100]
                            } for email in group
                        ]
                    }
                    themes.append(theme)

            logger.debug(f"Total themes generated: {len(themes)}")
            return themes

        except Exception as e:
            logger.error(f"Error generating themes: {str(e)}")
            return []

    def reset_conversation_context(self, session_id: str) -> Dict[str, str]:
        """
        Reset the conversation analysis context for a given session.
        """
        logger.info(f"Resetting conversation context for session: {session_id}")
        try:
            if session_id in self.sessions:
                del self.sessions[session_id]
                return {"status": "Context reset"}
            else:
                return {"error": "Session not found"}
        except Exception as e:
            logger.error(f"Error resetting conversation context: {str(e)}")
            return {"error": str(e)}