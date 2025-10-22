import zlib
import numpy as np
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION
from sentence_transformers import SentenceTransformer, util
from services.feedback_service import get_feedback_weights
import logging
from logging import handlers
import re

# Configurar logging
logger = logging.getLogger('email_search_app.search_service')
logger.setLevel(logging.DEBUG)
file_handler = handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Conectar a MongoDB
logger.info("Conectando a MongoDB: %s", MONGO_URI)
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]
logger.info("Conexión a MongoDB establecida")

# Cargar modelo de embeddings
logger.info("Cargando modelo de embeddings: paraphrase-multilingual-MiniLM-L12-v2")
embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
logger.info("Modelo de embeddings cargado exitosamente")

def cosine_similarity(emb1, emb2):
    logger.debug("Calculando similitud de coseno")
    if emb1 is None or emb2 is None:
        logger.warning("Uno o ambos embeddings son None")
        return 0.0
    try:
        emb1_array = np.frombuffer(zlib.decompress(emb1), dtype=np.float32)
        emb2_array = np.frombuffer(zlib.decompress(emb2), dtype=np.float32)
        similarity = util.cos_sim(emb1_array, emb2_array).item()
        logger.debug("Similitud de coseno calculada: %s", similarity)
        return similarity
    except Exception as e:
        logger.error("Error al calcular similitud de coseno: %s", str(e), exc_info=True)
        return 0.0

def format_email_field(name, email):
    """Helper function to format name and email into 'Name <email>' or '<email>'."""
    if email:
        return f"{name} <{email}>" if name else f"<{email}>"
    return 'N/A'

def get_email_by_id(message_id):
    logger.info("Obteniendo correo con message_id: %s", message_id)
    try:
        email = emails_collection.find_one(
            {'message_id': message_id},
            {
                'from': 1, 'to': 1, 'subject': 1, 'date': 1, 'body': 1,
                'attachments': 1, 'attachments_content': 1, 'summary': 1,
                'relevant_terms': 1, 'semantic_domain': 1, 'urls': 1, 'message_id': 1, 
                'from_email': 1, 'to_email': 1, '_id': 0  # Include possible separate email fields
            }
        )
        if not email:
            logger.warning("Correo no encontrado: %s", message_id)
            return None

        # Parse 'from' field
        from_field = email.get('from', '')
        from_email = email.get('from_email', '')  # Check for separate email field
        from_match = re.match(r'(.*)<(.+)>', from_field) if isinstance(from_field, str) else None
        if from_match:
            from_name, from_email_from_field = from_match.groups()
            email['from'] = format_email_field(from_name.strip(), from_email_from_field.strip())
        elif from_email:  # Use separate email field if available
            email['from'] = format_email_field(from_field.strip() if from_field else '', from_email.strip())
        elif from_field and '@' in from_field:
            email['from'] = format_email_field('', from_field.strip())
        else:
            email['from'] = 'N/A'

        # Parse 'to' field
        to_field = email.get('to', '')
        to_email = email.get('to_email', '')  # Check for separate email field
        to_match = re.match(r'(.*)<(.+)>', to_field) if isinstance(to_field, str) else None
        if to_match:
            to_name, to_email_from_field = to_match.groups()
            email['to'] = format_email_field(to_name.strip(), to_email_from_field.strip())
        elif to_email:  # Use separate email field if available
            email['to'] = format_email_field(to_field.strip() if to_field else '', to_email.strip())
        elif to_field and '@' in to_field:
            email['to'] = format_email_field('', to_field.strip())
        else:
            email['to'] = 'N/A'

        logger.debug("Correo encontrado: %s", email)
        return email
    except Exception as e:
        logger.error("Error al obtener correo: %s", str(e), exc_info=True)
        return None

def search_emails(processed_query, intent, terms, query_embedding):
    logger.info("Buscando correos para intent: %s, terms: %s", intent, terms)
    try:
        feedback_weights = get_feedback_weights()
        logger.debug("Pesos de retroalimentación obtenidos: %s", feedback_weights)

        text_query = {
            '$text': {
                '$search': ' '.join(terms + [intent]),
                '$language': 'spanish'
            }
        }
        
        conditions = {}
        if intent == 'ofertas_viaje':
            conditions['semantic_domain'] = 'viajes'
            if 'precio_max' in processed_query.get('conditions', {}):
                precio_max = processed_query.get('conditions').get('precio_max', '')
                if precio_max:
                    precio_regex = r'\b\d+\s*(?:€|euros)\b'
                    conditions['$or'] = [
                        {'body': {'$regex': precio_regex}},
                        {'attachments_content': {'$regex': precio_regex}}
                    ]
        logger.debug("Condiciones de búsqueda: %s", conditions)

        pipeline = [
            {'$match': {**text_query, **conditions}},
            {'$sort': {'score': {'$meta': 'textScore'}}},
            {'$limit': 50}
        ]
        logger.debug("Pipeline de MongoDB: %s", pipeline)

        results = list(emails_collection.aggregate(pipeline))
        logger.info("Encontrados %s correos en la búsqueda inicial", len(results))
        
        ranked_results = []
        for idx, email in enumerate(results, 1):
            semantic_score = cosine_similarity(query_embedding, email.get('embedding'))
            text_score = email.get('score', 0) if '$meta' in email else 0
            feedback_weight = feedback_weights.get(email['message_id'], 1.0)
            relevance = min(100, int((0.6 * semantic_score + 0.3 * text_score + 0.1 * feedback_weight) * 100))
            
            email_terms = [term for term in email.get('relevant_terms', {}).keys() if term in terms]
            
            # Improved explanation logic
            explanation_parts = []
            semantic_percentage = int(semantic_score * 100)
            if semantic_score > 0.7:
                explanation_parts.append(f"alta similitud semántica ({semantic_percentage}%)")
            elif semantic_score > 0.3:
                explanation_parts.append(f"similitud semántica moderada ({semantic_percentage}%)")
            else:
                explanation_parts.append(f"similitud semántica baja ({semantic_percentage}%)")

            if text_score > 0:
                explanation_parts.append(f"coincidencia textual con {', '.join(email_terms)}")
            else:
                explanation_parts.append(f"coincidencia textual mínima (puntuación: {text_score})")

            if email['semantic_domain'] == intent:
                explanation_parts.append(f"dominio semántico '{intent}'")

            if feedback_weight != 1.0:
                explanation_parts.append(f"ajustado por retroalimentación ({'negativa' if feedback_weight < 1.0 else 'positiva'})")

            explanation = "Seleccionado por: " + ", ".join(explanation_parts)

            logger.debug("Correo message_id=%s: semantic_score=%s, text_score=%s, feedback_weight=%s, relevance=%s, explanation=%s",
                         email['message_id'], semantic_score, text_score, feedback_weight, relevance, explanation)
            
            # Format 'from' and 'to' fields for search results
            from_field = email.get('from', '')
            to_field = email.get('to', '')
            from_email = email.get('from_email', '')  # Check for separate email field
            to_email = email.get('to_email', '')  # Check for separate email field

            from_match = re.match(r'(.*)<(.+)>', from_field) if isinstance(from_field, str) else None
            if from_match:
                from_name, from_email_from_field = from_match.groups()
                email['from'] = format_email_field(from_name.strip(), from_email_from_field.strip())
            elif from_email:
                email['from'] = format_email_field(from_field.strip() if from_field else '', from_email.strip())
            elif from_field and '@' in from_field:
                email['from'] = format_email_field('', from_field.strip())
            else:
                email['from'] = 'N/A'

            to_match = re.match(r'(.*)<(.+)>', to_field) if isinstance(to_field, str) else None
            if to_match:
                to_name, to_email_from_field = to_match.groups()
                email['to'] = format_email_field(to_name.strip(), to_email_from_field.strip())
            elif to_email:
                email['to'] = format_email_field(to_field.strip() if to_field else '', to_email.strip())
            elif to_field and '@' in to_field:
                email['to'] = format_email_field('', to_field.strip())
            else:
                email['to'] = 'N/A'

            ranked_results.append({
                'index': idx,
                'message_id': email['message_id'],
                'date': email['date'],
                'from': email['from'],
                'to': email['to'],
                'subject': email['subject'],
                'description': email.get('summary', 'Sin resumen'),
                'relevant_terms': email_terms,
                'relevance': relevance,
                'explanation': explanation
            })
        
        ranked_results.sort(key=lambda x: x['relevance'], reverse=True)
        logger.info("Devolviendo %s correos más relevantes", len(ranked_results[:10]))
        return ranked_results[:10]
    except Exception as e:
        logger.error("Error al buscar correos: %s", str(e), exc_info=True)
        return []