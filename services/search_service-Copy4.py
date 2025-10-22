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

def extract_email(text):
    """Extract email address from a string using regex."""
    if not text or not isinstance(text, str):
        return None
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    return email_match.group(0) if email_match else None

def format_email_field(name, email):
    """Helper function to format name and email into 'Name <email>' or '<email>'."""
    if email:
        name = name.strip() if name else ''
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
                'from_email': 1, 'to_email': 1, '_id': 0
            }
        )
        if not email:
            logger.warning("Correo no encontrado: %s", message_id)
            return None

        from_field = email.get('from', '')
        from_email = email.get('from_email', '') or extract_email(from_field)
        from_match = re.match(r'(.*)<(.+)>', from_field) if isinstance(from_field, str) else None
        if from_match:
            from_name, from_email_from_field = from_match.groups()
            email['from'] = format_email_field(from_name, from_email_from_field)
        elif from_email:
            from_name = from_field if from_field and not extract_email(from_field) else ''
            email['from'] = format_email_field(from_name, from_email)
        elif from_field and '@' in from_field:
            email['from'] = format_email_field('', from_field)
        else:
            email['from'] = 'N/A'

        to_field = email.get('to', '')
        to_email = email.get('to_email', '') or extract_email(to_field)
        to_match = re.match(r'(.*)<(.+)>', to_field) if isinstance(to_field, str) else None
        if to_match:
            to_name, to_email_from_field = to_match.groups()
            email['to'] = format_email_field(to_name, to_email_from_field)
        elif to_email:
            to_name = to_field if to_field and not extract_email(to_field) else ''
            email['to'] = format_email_field(to_name, to_email)
        elif to_field and '@' in to_field:
            email['to'] = format_email_field('', to_field)
        else:
            email['to'] = 'N/A'

        logger.debug("Correo encontrado: %s", email)
        return email
    except Exception as e:
        logger.error("Error al obtener correo: %s", str(e), exc_info=True)
        return None

def search_emails(processed_query, intent, terms, query_embedding, min_relevance=25, page=1, results_per_page=25):
    logger.info("Buscando correos para intent: %s, terms: %s, min_relevance: %s, page: %s", intent, terms, min_relevance, page)
    try:
        feedback_weights = get_feedback_weights()
        logger.debug("Pesos de retroalimentación obtenidos: %s", feedback_weights)

        text_query = {
            '$text': {
                '$search': ' '.join(terms),
                '$language': 'spanish'
            }
        }

        conditions = {'message_id': {'$exists': True}}
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
        elif intent == 'inversiones':
            conditions['semantic_domain'] = 'finanzas'
        elif intent == 'medicina_y_salud':
            conditions['semantic_domain'] = 'salud'

        logger.debug("Condiciones de búsqueda: %s", conditions)

        # Obtener todos los resultados para calcular relevancia
        pipeline = [
            {'$match': {**text_query, **conditions}},
            {'$sort': {'score': {'$meta': 'textScore'}}}
        ]
        logger.debug("Pipeline de MongoDB: %s", pipeline)

        results = list(emails_collection.aggregate(pipeline))
        total_results = emails_collection.count_documents({**text_query, **conditions})
        logger.info("Encontrados %s correos en total", total_results)

        ranked_results = []
        max_text_score = max((email.get('score', 0) for email in results if '$meta' in email), default=1) or 1  # Avoid division by zero
        for idx, email in enumerate(results, start=1):
            if 'message_id' not in email:
                logger.warning("Documento de correo sin message_id: %s", email)
                continue

            semantic_score = cosine_similarity(query_embedding, email.get('embedding'))
            text_score = email.get('score', 0) if '$meta' in email else 0
            # Normalize text_score to range [0, 1]
            normalized_text_score = text_score / max_text_score if max_text_score > 0 else 0
            feedback_weight = feedback_weights.get(email['message_id'], 1.0)
            # Adjusted weights to prioritize semantic similarity
            relevance = min(100, int((0.8 * semantic_score + 0.1 * normalized_text_score + 0.1 * feedback_weight) * 100))

            logger.debug("Correo message_id=%s: semantic_score=%s, text_score=%s (normalized=%s), feedback_weight=%s, relevance=%s",
                         email['message_id'], semantic_score, text_score, normalized_text_score, feedback_weight, relevance)

            # Filtrar por relevancia mínima
            if relevance < min_relevance:
                continue

            email_terms = [term for term in email.get('relevant_terms', {}).keys() if term in terms]

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

            if 'semantic_domain' in email and email['semantic_domain'] == intent:
                explanation_parts.append(f"dominio semántico '{intent}'")

            if feedback_weight != 1.0:
                explanation_parts.append(f"ajustado por retroalimentación ({'negativa' if feedback_weight < 1.0 else 'positiva'})")

            explanation = "Seleccionado por: " + ", ".join(explanation_parts)

            logger.debug("Correo message_id=%s: semantic_score=%s, text_score=%s, feedback_weight=%s, relevance=%s, explanation=%s",
                         email['message_id'], semantic_score, text_score, feedback_weight, relevance, explanation)

            from_field = email.get('from', '')
            to_field = email.get('to', '')
            from_email = email.get('from_email', '') or extract_email(from_field)
            to_email = email.get('to_email', '') or extract_email(to_field)

            from_match = re.match(r'(.*)<(.+)>', from_field) if isinstance(from_field, str) else None
            if from_match:
                from_name, from_email_from_field = from_match.groups()
                email['from'] = format_email_field(from_name, from_email_from_field)
            elif from_email:
                from_name = from_field if from_field and not extract_email(from_field) else ''
                email['from'] = format_email_field(from_name, from_email)
            elif from_field and '@' in from_field:
                email['from'] = format_email_field('', from_field)
            else:
                email['from'] = 'N/A'

            to_match = re.match(r'(.*)<(.+)>', to_field) if isinstance(to_field, str) else None
            if to_match:
                to_name, to_email_from_field = to_match.groups()
                email['to'] = format_email_field(to_name, to_email_from_field)
            elif to_email:
                to_name = to_field if to_field and not extract_email(to_field) else ''
                email['to'] = format_email_field(to_name, to_email)
            elif to_field and '@' in to_field:
                email['to'] = format_email_field('', to_field)
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

        # Ordenar por relevancia y paginar
        ranked_results.sort(key=lambda x: x['relevance'], reverse=True)
        total_filtered_results = len(ranked_results)

        # Aplicar paginación
        start_idx = (page - 1) * results_per_page
        end_idx = start_idx + results_per_page
        paginated_results = ranked_results[start_idx:end_idx]

        logger.info("Devolviendo %s correos relevantes de %s totales", len(paginated_results), total_filtered_results)
        return {'results': paginated_results, 'totalResults': total_filtered_results}
    except Exception as e:
        logger.error("Error al buscar correos: %s", str(e), exc_info=True)
        return {'results': [], 'totalResults': 0}