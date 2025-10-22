import unicodedata
import zlib
import numpy as np
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION
from sentence_transformers import SentenceTransformer, util
from services.feedback_service import get_feedback_weights, save_feedback
import logging
from logging import handlers
import re
from statistics import mean

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

def normalize_text(text):
    """Normaliza texto eliminando diacríticos y convirtiendo a minúsculas."""
    if not text or not isinstance(text, str):
        return text
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if unicodedata.category(c) != 'Mn')
    return text.lower()

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
    logger.debug("Formatting email field: name=%s, email=%s", name, email)
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
                'from': 1,
                'to': 1,
                'subject': 1,
                'date': 1,
                'body': 1,
                'attachments': 1,
                'attachments_content': 1,
                'summary': 1,
                'relevant_terms': 1,
                'semantic_domain': 1,
                'urls': 1,
                'message_id': 1,
                'from_email': 1,
                'to_email': 1,
                '_id': 0
            }
        )
        if not email:
            logger.warning("Correo no encontrado: %s", message_id)
            return None

        from_field = email.get('from', '')
        from_email = email.get('from_email', '') or extract_email(from_field)
        logger.debug("Processing from_email_field: from_field=%s, email=%s", from_field, from_email)
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
        logger.debug("Processing to_email_field: to_field=%s, to_email=%s", to_field, to_email)
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

        logger.debug("Correo procesado: from=%s, to=%s", email['from'], email['to'])
        return email
    except Exception as e:
        logger.error("Error al obtener correo: %s", str(e), exc_info=True)
        return None

def submit_bulk_feedback(query, filter_data, processed_query, intent, terms, query_embedding):
    logger.info("Procesando retroalimentación masiva para query: %s, filter: %s", query, filter_data)
    try:
        action = filter_data.get('action')
        filter_terms = filter_data.get('terms', [])
        normalized_terms = [normalize_text(term) for term in filter_terms]

        # Construir consulta de búsqueda similar a search_emails
        text_query = {
            '$text': {
                '$search': ' '.join(terms),
                '$language': 'spanish'
            }
        } if terms else {}

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

        # Aplicar condiciones del filtro según la acción
        if action == 'remove':
            filter_conditions = [
                {
                    '$or': [
                        {'subject': {'$regex': term, '$options': 'i'}},
                        {'relevant_terms_array': {'$regex': term, '$options': 'i'}},
                        {'summary': {'$regex': term, '$options': 'i'}},
                        {'from': {'$regex': term, '$options': 'i'}},
                        {'to': {'$regex': term, '$options': 'i'}}
                    ]
                } for term in normalized_terms
            ]
        else:  # action == 'add'
            filter_conditions = [
                {
                    '$or': [
                        {'subject': {'$regex': term, '$options': 'i'}},
                        {'relevant_terms_array': {'$regex': term, '$options': 'i'}},
                        {'summary': {'$regex': term, '$options': 'i'}},
                        {'from': {'$regex': term, '$options': 'i'}},
                        {'to': {'$regex': term, '$options': 'i'}}
                    ]
                } for term in normalized_terms
            ]

        if filter_conditions:
            conditions['$and'] = conditions.get('$and', []) + filter_conditions

        # Combinar resultado de text_query y filtrado
        final_conditions = {**text_query, **conditions}
        logger.debug("Condiciones de filtrado finales para bulk feedback: %s", final_conditions)

        # Obtener message_ids de los correos que coincidan con el filtro final
        cursor = emails_collection.find(final_conditions, {'message_id': 1})
        message_ids = [email['message_id'] for email in cursor if 'message_id' in email]
        logger.debug("Encontrados %d correos para retroalimentación masiva", len(message_ids))

        affected_count = 0
        for message_id in message_ids:
            try:
                save_feedback(query, message_id.lower(), False)
                affected_count += 1
                logger.debug("Retroalimentación guardada para message_id: %s", message_id)
            except Exception as e:
                logger.error("Error al guardar retroalimentación para message_id %s: %s", message_id, str(e))

        logger.info("Retroalimentación masiva completada: %d correos afectados", affected_count)
        return affected_count
    except Exception as e:
        logger.error("Error en retroalimentación masiva: %s", str(e), exc_info=True)
        return 0

def search_emails(processed_query, intent, terms, query_embedding, min_relevance=25, page=1, results_per_page=25, filters=None, filter_only=False):
    logger.info("Buscando correos para intent: %s, terms: %s, min_relevance: %s, page: %s, filters: %s, filter_only: %s",
                intent, terms, min_relevance, page, filters, filter_only)
    try:
        feedback_weights = get_feedback_weights()
        logger.debug("Pesos de retroalimentación obtenidos: %s", feedback_weights)

        filters = filters or []
        remove_filters = [f['terms'] for f in filters if f['action'] == 'remove']
        add_filters = [f['terms'] for f in filters if f['action'] == 'add']

        # Almacenar conteos de filtros
        filter_counts = {
            'remove': {tuple(terms): 0 for terms in remove_filters},
            'add': {tuple(terms): 0 for terms in add_filters}
        }

        if filter_only:
            # For filter modal, return emails matching the filter within the query context
            if not filters:
                logger.warning("No filters provided for filter_only mode")
                return {'results': [], 'totalResults': 0, 'filter_counts': {'remove': {}, 'add': {}}}

            results = []
            result_ids = set()
            filter_action = filters[0]['action']
            filter_terms = filters[0]['terms']

            # Build query conditions
            text_query = {
                '$text': {
                    '$search': ' '.join(terms),
                    '$language': 'spanish'
                }
            } if terms else {}

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

            # Apply filter conditions
            normalized_terms = [normalize_text(term) for term in filter_terms]
            if filter_action == 'remove':
                # For "remove" filters in modal, show emails that match the filter terms
                filter_conditions = [
                    {
                        '$or': [
                            {'subject': {'$regex': term, '$options': 'i'}},
                            {'relevant_terms_array': {'$regex': term, '$options': 'i'}},
                            {'summary': {'$regex': term, '$options': 'i'}},
                            {'from': {'$regex': term, '$options': 'i'}},
                            {'to': {'$regex': term, '$options': 'i'}}
                        ]
                    } for term in normalized_terms
                ]
            else:  # 'add'
                filter_conditions = [
                    {
                        '$or': [
                            {'subject': {'$regex': term, '$options': 'i'}},
                            {'relevant_terms_array': {'$regex': term, '$options': 'i'}},
                            {'summary': {'$regex': term, '$options': 'i'}},
                            {'from': {'$regex': term, '$options': 'i'}},
                            {'to': {'$regex': term, '$options': 'i'}}
                        ]
                    } for term in normalized_terms
                ]

            if filter_conditions:
                conditions['$and'] = conditions.get('$and', []) + filter_conditions

            # Combine text query and filter conditions
            final_conditions = {**text_query, **conditions}
            logger.debug("Filter modal conditions: %s", final_conditions)

            pipeline = [
                {'$match': final_conditions},
                {'$sort': {'date': -1}},
                {'$project': {
                    'message_id': 1,
                    'from': 1,
                    'to': 1,
                    'subject': 1,
                    'date': 1,
                    'body': 1,
                    'summary': 1,
                    'relevant_terms': 1,
                    'relevant_terms_array': 1,
                    'semantic_domain': 1,
                    'embedding': 1
                }}
            ]
            filter_results = list(emails_collection.aggregate(pipeline))
            filter_counts[filter_action][tuple(filter_terms)] = len(filter_results)
            logger.debug("Filtro %s %s devolvió %s correos", filter_action, filter_terms, len(filter_results))
            results.extend(filter_results)
            total_results = len(filter_results)
        else:
            # Normal search with query and filters
            text_query = {
                '$text': {
                    '$search': ' '.join(terms),
                    '$language': 'spanish'
                }
            } if terms else {}

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

            # Aplicar filtros de eliminación
            for remove_terms in remove_filters:
                normalized_terms = [normalize_text(term) for term in remove_terms]
                conditions['$and'] = conditions.get('$and', []) + [
                    {
                        '$nor': [
                            {'subject': {'$regex': term, '$options': 'i'}},
                            {'relevant_terms_array': {'$regex': term, '$options': 'i'}},
                            {'summary': {'$regex': term, '$options': 'i'}},
                            {'from': {'$regex': term, '$options': 'i'}},
                            {'to': {'$regex': term, '$options': 'i'}}
                        ]
                    } for term in normalized_terms
                ]

            logger.debug("Condiciones de búsqueda: %s", conditions)

            pipeline = [
                {'$match': {**text_query, **conditions}},
                {'$sort': {'score': {'$meta': 'textScore'}} if text_query else {'date': -1}},
                {'$project': {
                    'message_id': 1,
                    'from': 1,
                    'to': 1,
                    'subject': 1,
                    'date': 1,
                    'body': 1,
                    'summary': 1,
                    'relevant_terms': 1,
                    'relevant_terms_array': 1,
                    'semantic_domain': 1,
                    'embedding': 1,
                    'score': {'$meta': 'textScore'} if text_query else 1
                }}
            ]
            logger.debug("Pipeline de MongoDB: %s", pipeline)

            results = list(emails_collection.aggregate(pipeline))
            total_results = emails_collection.count_documents({**text_query, **conditions})
            logger.info("Encontrados %s correos en total", total_results)

            # Calcular correos eliminados por cada filtro de eliminación
            for remove_terms in remove_filters:
                remove_conditions = {**text_query, 'message_id': {'$exists': True}}
                normalized_terms = [normalize_text(term) for term in remove_terms]
                remove_conditions['$and'] = [
                    {
                        '$or': [
                            {'subject': {'$regex': term, '$options': 'i'}},
                            {'relevant_terms_array': {'$regex': term, '$options': 'i'}},
                            {'summary': {'$regex': term, '$options': 'i'}},
                            {'from': {'$regex': term, '$options': 'i'}},
                            {'to': {'$regex': term, '$options': 'i'}}
                        ]
                    } for term in normalized_terms
                ]
                remove_count = emails_collection.count_documents(remove_conditions)
                filter_counts['remove'][tuple(remove_terms)] = remove_count
                logger.debug("Filtro de eliminación %s eliminó %s correos", remove_terms, remove_count)

            # Procesar filtros de ampliación
            additional_results = []
            for add_terms in add_filters:
                add_conditions = {'message_id': {'$exists': True}}
                normalized_terms = [normalize_text(term) for term in add_terms]
                add_conditions['$and'] = [
                    {
                        '$or': [
                            {'subject': {'$regex': term, '$options': 'i'}},
                            {'relevant_terms_array': {'$regex': term, '$options': 'i'}},
                            {'summary': {'$regex': term, '$options': 'i'}},
                            {'from': {'$regex': term, '$options': 'i'}},
                            {'to': {'$regex': term, '$options': 'i'}}
                        ]
                    } for term in normalized_terms
                ]
                add_pipeline = [
                    {'$match': add_conditions},
                    {'$sort': {'date': -1}},
                    {'$project': {
                        'message_id': 1,
                        'from': 1,
                        'to': 1,
                        'subject': 1,
                        'date': 1,
                        'body': 1,
                        'summary': 1,
                        'relevant_terms': 1,
                        'relevant_terms_array': 1,
                        'semantic_domain': 1,
                        'embedding': 1
                    }}
                ]
                add_results = list(emails_collection.aggregate(add_pipeline))
                filter_counts['add'][tuple(add_terms)] = len(add_results)
                logger.debug("Filtro de ampliación %s añadió %s correos", add_terms, len(add_results))
                additional_results.extend(add_results)

            # Combinar resultados y eliminar duplicados
            result_ids = {email['message_id'] for email in results}
            for add_email in additional_results:
                if add_email['message_id'] not in result_ids:
                    results.append(add_email)
                    result_ids.add(add_email['message_id'])

        ranked_results = []
        relevance_scores = []
        semantic_scores = []
        text_scores = []

        for email in results:
            if 'message_id' not in email:
                logger.warning("Documento de correo sin message_id: %s", email)
                continue
            logger.debug("Correo con score: message_id=%s, score=%s", email['message_id'], email.get('score', 'N/A'))
            semantic_score = cosine_similarity(query_embedding, email.get('embedding'))
            text_score = email.get('score', 0) if not filter_only else 0
            semantic_scores.append(semantic_score)
            text_scores.append(text_score)

        max_semantic_score = max(semantic_scores, default=1) or 1
        min_semantic_score = min(semantic_scores, default=0)
        max_text_score = max(text_scores, default=1) or 1
        min_text_score = min(text_scores, default=0)

        filtered_count = 0
        for idx, email in enumerate(results, start=1):
            if 'message_id' not in email:
                continue

            semantic_score = cosine_similarity(query_embedding, email.get('embedding'))
            text_score = email.get('score', 0) if not filter_only else 0

            if max_semantic_score != min_semantic_score:
                normalized_semantic_score = (semantic_score - min_semantic_score) / (max_semantic_score - min_semantic_score)
            else:
                normalized_semantic_score = semantic_score if max_semantic_score > 0 else 0
            if max_text_score != min_text_score:
                normalized_text_score = (text_score - min_text_score) / (max_text_score - min_text_score)
            else:
                normalized_text_score = text_score if max_text_score > 0 else 0

            feedback_weight = feedback_weights.get(email['message_id'], 1.0)
            relevance = int((0.7 * normalized_semantic_score + 0.2 * normalized_text_score + 0.1 * feedback_weight) * 100)
            relevance_scores.append(relevance)

            logger.debug("Correo message_id=%s: semantic_score=%s (normalized=%s), text_score=%s (normalized=%s), feedback_weight=%s, relevance=%s, min_relevance=%s",
                         email['message_id'], semantic_score, normalized_semantic_score, text_score, normalized_text_score, feedback_weight, relevance, min_relevance)

            if relevance < min_relevance and not filter_only:
                filtered_count += 1
                logger.debug("Correo filtrado por relevancia baja: message_id=%s, relevance=%s < min_relevance=%s", email['message_id'], relevance, min_relevance)
                continue

            email_terms = [term for term in email.get('relevant_terms', {}).keys() if term.lower() in [t.lower() for t in terms]] if not filter_only else []

            explanation_parts = []
            semantic_percentage = int(normalized_semantic_score * 100)
            if normalized_semantic_score > 0.7:
                explanation_parts.append(f"alta similitud semántica ({semantic_percentage}%)")
            elif normalized_semantic_score > 0.3:
                explanation_parts.append(f"similitud semántica moderada ({semantic_percentage}%)")
            else:
                explanation_parts.append(f"similitud semántica baja ({semantic_percentage}%)")

            if text_score > 0 and not filter_only:
                explanation_parts.append(f"coincidencia textual con {', '.join(email_terms) or 'términos relacionados'} (puntuación: {text_score:.2f})")
            else:
                explanation_parts.append(f"coincidencia textual mínima (puntuación: {text_score})")

            if 'semantic_domain' in email and email['semantic_domain'] == intent and not filter_only:
                explanation_parts.append(f"dominio semántico '{intent}'")

            if feedback_weight != 1.0:
                explanation_parts.append(f"ajustado por retroalimentación ({'negativa' if feedback_weight < 1.0 else 'positiva'})")

            if filter_only:
                explanation_parts = [f"coincidencia con términos de filtro: {', '.join(filter_terms)}"]

            explanation = "Seleccionado por: " + ", ".join(explanation_parts)

            from_field = email.get('from', '')
            to_field = email.get('to', '')
            from_email = email.get('from_email', '') or extract_email(from_field)
            to_email = email.get('to_email', '') or extract_email(to_field)
            logger.debug("Processing email fields: from_field=%s, from_email=%s, to_field=%s, to_email=%s", from_field, from_email, to_field, to_email)

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

            logger.debug("Email formatted: from=%s, to=%s", email['from'], email['to'])

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

        if relevance_scores:
            logger.info("Distribución de relevancia: min=%s, max=%s, promedio=%s",
                        min(relevance_scores), max(relevance_scores), mean(relevance_scores))
            if not filter_only:
                logger.info("Correos filtrados por relevancia baja: %s de %s totales", filtered_count, total_results)
        else:
            logger.info("No se encontraron correos para calcular distribución de relevancia")

        ranked_results.sort(key=lambda x: x['relevance'], reverse=True)
        total_filtered_results = len(ranked_results)

        start_idx = (page - 1) * results_per_page
        end_idx = start_idx + results_per_page
        paginated_results = ranked_results[start_idx:end_idx]

        logger.info("Devolviendo %s correos relevantes de %s totales", len(paginated_results), total_filtered_results)
        return {
            'results': paginated_results,
            'totalResults': total_filtered_results,
            'filter_counts': {
                'remove': {', '.join(terms): count for terms, count in filter_counts['remove'].items()},
                'add': {', '.join(terms): count for terms, count in filter_counts['add'].items()}
            }
        }
    except Exception as e:
        logger.error("Error al buscar correos: %s", str(e), exc_info=True)
        return {'results': [], 'totalResults': 0, 'filter_counts': {'remove': {}, 'add': {}}}