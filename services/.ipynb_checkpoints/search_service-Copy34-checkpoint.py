import unicodedata
import zlib
import numpy as np
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION, ELASTICSEARCH_HOST, ELASTICSEARCH_PORT
from sentence_transformers import SentenceTransformer, util
from services.feedback_service import get_feedback_weights, save_feedback
import logging
from logging import handlers
import re
from statistics import mean
from datetime import datetime
from dateutil.parser import parse as parse_date
from elasticsearch import Elasticsearch

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

# Conectar a Elasticsearch
logger.info("Conectando a Elasticsearch: %s:%s", ELASTICSEARCH_HOST, ELASTICSEARCH_PORT)
es = Elasticsearch([{'host': ELASTICSEARCH_HOST, 'port': ELASTICSEARCH_PORT, 'scheme': 'http'}])
logger.info("Conexión a Elasticsearch establecida")

# Cargar modelo de embeddings
logger.info("Cargando modelo de embeddings: paraphrase-multilingual-MiniLM-L12-v2")
embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
logger.info("Modelo de embeddings cargado exitosamente")

# Diccionario de sinónimos para dominios semánticos
DOMAIN_SYNONYMS = {
    "informacion_juridica": ["legal", "derecho", "judicial", "juzgado", "procedimiento"],
    "viajes": ["turismo", "vacaciones", "reserva", "viaje"],
    "negocios": ["comercial", "empresa", "propuesta"],
    "promociones": ["ofertas", "descuentos", "publicidad"],
    "tecnico": ["soporte", "incidencia", "tecnologia"],
    "personal": ["privado", "familiar"],
    "general": [],
    "negociaciones": ["venta", "compra", "acuerdo", "transaccion", "negociacion", "precio"]
}

def normalize_text(text):
    """Normaliza texto eliminando diacríticos y convirtiendo a minúsculas."""
    if not text or not isinstance(text, str):
        return text
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if unicodedata.category(c) != 'Mn')
    return text.lower()

def cosine_similarity(emb1, emb2, compressed=True):
    """Calcula la similitud coseno entre dos embeddings."""
    logger.debug("Calculando similitud de coseno, compressed=%s", compressed)
    if emb1 is None or emb2 is None:
        logger.warning("Uno o ambos embeddings son None")
        return 0.0
    try:
        if compressed:
            emb1_array = np.frombuffer(zlib.decompress(emb1), dtype=np.float32)
            emb2_array = np.frombuffer(zlib.decompress(emb2), dtype=np.float32)
        else:
            emb1_array = np.array(emb1, dtype=np.float32)
            emb2_array = np.array(emb2, dtype=np.float32)
        similarity = util.cos_sim(emb1_array, emb2_array).item()
        logger.debug("Similitud de coseno calculada: %s", similarity)
        return similarity
    except Exception as e:
        logger.error("Error al calcular similitud de coseno: %s", str(e), exc_info=True)
        return 0.0

def extract_email(text):
    """Extrae una dirección de correo de un texto usando regex."""
    if not text or not isinstance(text, str):
        return None
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text, re.IGNORECASE)
    return email_match.group(0) if email_match else None

def format_email_field(name, email):
    """Formatea nombre y correo en 'Nombre <email>' o '<email>'."""
    logger.debug("Formateando campo de correo: name=%s, email=%s", name, email)
    if email:
        name = name.strip() if name else ''
        return f"{name} <{email}>" if name else f"<{email}>"
    return 'N/A'

def extract_email_from_input(input_str):
    """Extrae dirección de correo de una entrada de autocompletado."""
    if not input_str or not isinstance(input_str, str):
        return None
    match = re.search(r'<([^>]+@[^>]+)>', input_str, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    email = extract_email(input_str)
    return email.lower() if email else None

def get_email_addresses(prefix='', limit=50, user=None):
    """Obtiene direcciones de correo únicas de 'from' y 'to' para autocompletado."""
    logger.info("Obteniendo direcciones de correo únicas con prefijo: %s, límite: %s, user: %s", prefix, limit, user.username if user else 'None')
    try:
        if not user:
            raise ValueError("Se requiere un usuario para obtener las direcciones de correo")

        user_mailboxes = [mailbox['mailbox_id'] for mailbox in user.mailboxes]
        if not user_mailboxes:
            logger.warning(f"No se encontraron buzones para el usuario: {user.username}")
            return []

        from_addresses = emails_collection.distinct('from', {'mailbox_id': {'$in': user_mailboxes}})
        to_addresses = emails_collection.distinct('to', {'mailbox_id': {'$in': user_mailboxes}})
        
        all_addresses = set()
        for address in from_addresses + to_addresses:
            if not address or address == 'N/A':
                continue
            sub_addresses = [addr.strip() for addr in address.split(',') if addr.strip()]
            all_addresses.update(sub_addresses)
        
        formatted_addresses = []
        for address in all_addresses:
            match = re.match(r'(.*?)\s*(?:<(.+?)>)?$', address, re.IGNORECASE) if isinstance(address, str) else None
            if match:
                name, email = match.groups()
                name = name.strip() if name else ''
                email = email or extract_email(address)
                if email:
                    formatted = format_email_field(name, email)
                    if prefix and not normalize_text(formatted).startswith(normalize_text(prefix)):
                        continue
                    formatted_addresses.append(formatted)
        
        formatted_addresses = sorted(set(formatted_addresses))[:limit]
        logger.debug("Devolviendo %d direcciones formateadas", len(formatted_addresses))
        return formatted_addresses
    except Exception as e:
        logger.error("Error al obtener direcciones de correo: %s", str(e), exc_info=True)
        return []

def get_conversation_emails(email1, email2, start_date, end_date, user=None):
    """Obtiene correos bidireccionales entre email1 y email2 en un rango de fechas."""
    logger.info(f"Buscando correos bidireccionales entre email1: {email1}, email2: {email2}, desde {start_date} hasta {end_date}, user: {user.username if user else 'None'}")
    try:
        if not user:
            logger.error("Usuario no proporcionado para obtener correos de conversación")
            return []

        user_mailboxes = [mailbox['mailbox_id'] for mailbox in user.mailboxes]
        if not user_mailboxes:
            logger.warning(f"No se encontraron buzones para el usuario: {user.username}")
            return []

        email1_addr = extract_email_from_input(email1)
        email2_addr = extract_email_from_input(email2)
        if not email1_addr or not email2_addr:
            logger.warning("Dirección de correo inválida: email1=%s, email2=%s", email1, email2)
            return []

        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError as e:
            logger.error(f"Formato de fecha inválido: {str(e)}")
            return []

        email1_escaped = re.escape(email1_addr)
        email2_escaped = re.escape(email2_addr)

        pipeline = [
            {
                '$match': {
                    'mailbox_id': {'$in': user_mailboxes},
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
                    '_id': 0
                }
            }
        ]
        logger.debug(f"Ejecutando pipeline MongoDB: {pipeline}")

        emails = list(emails_collection.aggregate(pipeline))

        if not emails:
            logger.debug("No se encontraron correos. Verificando datos en la colección...")
            sample_emails = list(emails_collection.find(
                {'mailbox_id': {'$in': user_mailboxes}, '$or': [
                    {'from': {'$regex': email1_escaped, '$options': 'i'}},
                    {'to': {'$regex': email1_escaped, '$options': 'i'}}
                ]},
                {'from': 1, 'to': 1, 'date': 1}
            ).limit(5))
            logger.debug(f"Muestra de correos para email1: {sample_emails}")
            sample_emails = list(emails_collection.find(
                {'mailbox_id': {'$in': user_mailboxes}, '$or': [
                    {'from': {'$regex': email2_escaped, '$options': 'i'}},
                    {'to': {'$regex': email2_escaped, '$options': 'i'}}
                ]},
                {'from': 1, 'to': 1, 'date': 1}
            ).limit(5))
            logger.debug(f"Muestra de correos para email2: {sample_emails}")

        results = []
        for email in emails:
            email['index'] = str(email.get('index', 'N/A'))
            email['message_id'] = str(email.get('message_id', 'N/A'))
            results.append({
                'index': email['index'],
                'message_id': email['message_id'],
                'from': email.get('from', 'N/A'),
                'to': email.get('to', 'N/A'),
                'subject': email.get('subject', ''),
                'date': email.get('date', ''),
                'description': email.get('summary', 'Sin resumen')
            })

        logger.debug(f"Devolviendo {len(results)} correos de conversación")
        return results
    except Exception as e:
        logger.error(f"Error al buscar correos de conversación: {str(e)}", exc_info=True)
        return []

def get_email_by_id(identifier, is_index=False):
    """Obtiene un correo por su 'index' o 'message_id'."""
    logger.info("Obteniendo correo con identifier: %s, is_index: %s", identifier, is_index)
    try:
        query_field = 'index' if is_index else 'message_id'
        email = emails_collection.find_one(
            {query_field: str(identifier)},
            {
                'message_id': 1,
                'index': 1,
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
                'from_email': 1,
                'to_email': 1,
                '_id': 0
            }
        )
        if not email:
            logger.warning("Correo no encontrado: %s=%s", query_field, identifier)
            return None

        email['index'] = str(email.get('index', 'N/A'))
        email['message_id'] = str(email.get('message_id', 'N/A'))
        if email['index'] == 'N/A' or not email['index']:
            logger.error("Campo 'index' no válido en correo: message_id=%s", email['message_id'])

        from_field = email.get('from', '')
        from_email = email.get('from_email', '') or extract_email(from_field)
        logger.debug("Procesando from_email_field: from_field=%s, email=%s", from_field, from_email)
        from_match = re.match(r'(.*)<(.+)>', from_field, re.IGNORECASE) if isinstance(from_field, str) else None
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
        logger.debug("Procesando to_email_field: to_field=%s, to_email=%s", to_field, to_email)
        to_match = re.match(r'(.*)<(.+)>', to_field, re.IGNORECASE) if isinstance(to_field, str) else None
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

        logger.debug("Correo procesado: from=%s, to=%s, index=%s, message_id=%s", email['from'], email['to'], email['index'], email['message_id'])
        return email
    except Exception as e:
        logger.error("Error al obtener correo: %s", str(e), exc_info=True)
        return None

def submit_bulk_feedback(query, filter_data, processed_query, intent, terms, query_embedding):
    """Procesa retroalimentación masiva para correos basados en filtros."""
    logger.info("Procesando retroalimentación masiva para query: %s, filter: %s", query, filter_data)
    try:
        action = filter_data.get('action')
        filter_terms = filter_data.get('terms', [])
        normalized_terms = [normalize_text(term) for term in filter_terms]

        text_query = {
            '$text': {
                '$search': ' '.join(terms),
                '$language': 'spanish'
            }
        } if terms else {}

        conditions = {'message_id': {'$exists': True}}
        if intent == 'negociaciones':
            conditions['semantic_domain'] = {'$in': DOMAIN_SYNONYMS.get('negociaciones', ['negociaciones'])}
        elif intent == 'informacion_juridica':
            conditions['semantic_domain'] = {'$in': DOMAIN_SYNONYMS.get('informacion_juridica', ['legal'])}

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
        else:
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

        final_conditions = {**text_query, **conditions}
        logger.debug("Condiciones de filtrado finales para bulk feedback: %s", final_conditions)

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

def search_emails(processed_query, intent, terms, query_embedding, min_relevance=25, page=1, results_per_page=25, filters=None, filter_only=False, user=None):
    """
    Busca correos usando Elasticsearch y MongoDB con búsqueda semántica mejorada.
    
    :param processed_query: Consulta procesada.
    :param intent: Intención de la consulta.
    :param terms: Términos de búsqueda.
    :param query_embedding: Embedding de la consulta (comprimido).
    :param min_relevance: Relevancia mínima para filtrar resultados.
    :param page: Página de resultados.
    :param results_per_page: Número de resultados por página.
    :param filters: Filtros adicionales.
    :param filter_only: Si es True, solo aplica filtros sin búsqueda.
    :param user: Usuario autenticado para filtrar por buzones.
    :return: Diccionario con resultados, total de resultados y conteos de filtros.
    """
    logger.info("Buscando correos para intent: %s, terms: %s, min_relevance: %s, page: %s, filters: %s, filter_only: %s, user: %s",
                intent, terms, min_relevance, page, filters, filter_only, user.username if user else 'None')

    if not user:
        logger.error("Usuario no proporcionado para búsqueda de correos")
        return {'results': [], 'totalResults': 0, 'filter_counts': {'remove': {}, 'add': {}}}

    user_mailboxes = [mailbox['mailbox_id'] for mailbox in user.mailboxes]
    if not user_mailboxes:
        logger.warning(f"No se encontraron buzones para el usuario: {user.username}")
        return {'results': [], 'totalResults': 0, 'filter_counts': {'remove': {}, 'add': {}}}

    try:
        feedback_weights = get_feedback_weights(user.username)
        logger.debug("Pesos de retroalimentación obtenidos: %s", feedback_weights)

        filters = filters or []
        remove_filters = [f['terms'] for f in filters if f['action'] == 'remove']
        add_filters = [f['terms'] for f in filters if f['action'] == 'add']
        filter_counts = {
            'remove': {','.join(term).lower(): 0 for term in remove_filters},
            'add': {','.join(term).lower(): 0 for term in add_filters}
        }

        # Construir consulta para Elasticsearch
        es_query = {
            "query": {
                "bool": {
                    "should": [],
                    "filter": [{"terms": {"mailbox_id": user_mailboxes}}],
                    "minimum_should_match": 1
                }
            }
        }

        # Añadir búsqueda textual con ponderación
        if terms and not filter_only:
            for term in terms:
                es_query['query']['bool']['should'].append({
                    "multi_match": {
                        "query": term,
                        "fields": ["body^1", "summary^2", "relevant_terms_array^3", "subject^2"],
                        "type": "cross_fields",
                        "operator": "or"
                    }
                })

        # Añadir dominio semántico como 'should'
        if intent != 'general' and not filter_only:
            related_domains = DOMAIN_SYNONYMS.get(intent, [intent])
            es_query['query']['bool']['should'].append({
                "terms": {"semantic_domain": related_domains, "boost": 1.5}
            })

        # Añadir filtros de metadatos como 'should'
        metadata_filters = processed_query.get('metadata_filters', {})
        for key, value in metadata_filters.items():
            if key in ['from', 'to', 'subject']:
                es_query['query']['bool']['should'].append({
                    "match": {key: {"query": value, "boost": 2}}
                })
            elif key == 'date_range':
                es_query['query']['bool']['filter'].append({
                    "range": {
                        "date": {
                            "gte": value['start'],
                            "lte": value['end']
                        }
                    }
                })

        # Añadir búsqueda vectorial
        if query_embedding and not filter_only:
            query_vector = np.frombuffer(zlib.decompress(query_embedding), dtype=np.float32).tolist()
            es_query['query']['bool']['should'].append({
                "script_score": {
                    "query": {"match_all": {}},
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                        "params": {"query_vector": query_vector}
                    },
                    "boost": 3  # Mayor peso para similitud semántica
                }
            })

        # Si es filter_only, ajustar la consulta
        if filter_only and filters:
            filter_action = filters[0]['action']
            filter_terms = filters[0]['terms']
            terms_key = ','.join(filter_terms).lower()
            normalized_terms = [normalize_text(term) for term in filter_terms]
            es_query['query']['bool']['must'] = [{
                "multi_match": {
                    "query": " ".join(normalized_terms),
                    "fields": ["subject", "relevant_terms_array", "summary", "from", "to"],
                    "type": "best_fields"
                }
            }]

        # Ejecutar búsqueda en Elasticsearch
        logger.debug(f"Consulta Elasticsearch: {es_query}")
        es_results = es.search(
            index='email_index',
            body=es_query,
            size=results_per_page * 2,
            from_=(page-1) * results_per_page
        )
        total_results = es_results['hits']['total']['value']
        es_hits = es_results['hits']['hits']
        logger.info(f"Resultados de Elasticsearch: {len(es_hits)} hits, max_score: {max([hit['_score'] for hit in es_hits], default=0)}")

        # Verificar calidad y fallback a MongoDB
        THRESHOLD = 0.5
        if not es_hits or max([hit['_score'] for hit in es_hits if '_score' in hit], default=0) < THRESHOLD:
            logger.info("Resultados de Elasticsearch insuficientes, usando MongoDB como fallback")
            text_query = {
                '$text': {
                    '$search': ' '.join(terms),
                    '$language': 'spanish'
                }
            } if terms and not filter_only else {}
            conditions = {'message_id': {'$exists': True}, 'mailbox_id': {'$in': user_mailboxes}}
            if intent != 'general':
                related_domains = DOMAIN_SYNONYMS.get(intent, [intent])
                conditions['semantic_domain'] = {'$in': related_domains}
            pipeline = [
                {'$match': {**text_query, **conditions}},
                {'$sort': {'score': {'$meta': 'textScore'}} if text_query else {'date': -1}},
                {'$limit': results_per_page * 2}
            ]
            results = list(emails_collection.aggregate(pipeline))
            logger.info(f"Resultados de MongoDB: {len(results)} documentos")
        else:
            message_ids = [hit['_source']['message_id'] for hit in es_hits]
            results = list(emails_collection.find(
                {'message_id': {'$in': message_ids}},
                {
                    'message_id': 1, 'index': 1, 'from': 1, 'to': 1, 'subject': 1, 'date': 1, 'body': 1,
                    'summary': 1, 'relevant_terms': 1, 'relevant_terms_array': 1, 'semantic_domain': 1,
                    'embedding': 1, '_id': 0
                }
            ))
            score_map = {hit['_source']['message_id']: (hit['_score'], hit['_source']['embedding']) for hit in es_hits}
            for email in results:
                email['es_score'], email['es_embedding'] = score_map.get(email['message_id'], (0, None))

        # Aplicar filtros de eliminación e inclusión
        filtered_results = []
        for email in results:
            email['index'] = str(email.get('index', 'N/A'))
            email['message_id'] = str(email.get('message_id', 'N/A'))
            if email['index'] == 'N/A' or not email['index']:
                logger.error("Campo 'index' no válido en correo: message_id=%s", email['message_id'])

            exclude = False
            for remove_terms in remove_filters:
                normalized_terms = [normalize_text(term) for term in remove_terms]
                terms_key = ','.join(remove_terms).lower()
                if any(re.search(term, f"{email.get('subject', '')} {email.get('summary', '')} {email.get('from', '')} {email.get('to', '')}", re.IGNORECASE) for term in normalized_terms):
                    exclude = True
                    filter_counts['remove'][terms_key] += 1
                    break
            if not exclude:
                filtered_results.append(email)

        for add_terms in add_filters:
            add_es_query = {
                "query": {
                    "bool": {
                        "must": [{
                            "multi_match": {
                                "query": " ".join(add_terms),
                                "fields": ["subject", "relevant_terms_array", "summary", "from", "to"],
                                "type": "best_fields"
                            }
                        }],
                        "filter": [{"terms": {"mailbox_id": user_mailboxes}}]
                    }
                }
            }
            add_results = es.search(index='email_index', body=add_es_query, size=results_per_page)
            add_message_ids = [hit['_source']['message_id'] for hit in add_results['hits']['hits']]
            add_emails = list(emails_collection.find(
                {'message_id': {'$in': add_message_ids}},
                {
                    'message_id': 1, 'index': 1, 'from': 1, 'to': 1, 'subject': 1, 'date': 1, 'body': 1,
                    'summary': 1, 'relevant_terms': 1, 'relevant_terms_array': 1, 'semantic_domain': 1,
                    'embedding': 1, '_id': 0
                }
            ))
            terms_key = ','.join(add_terms).lower()
            filter_counts['add'][terms_key] = len(add_emails)
            for email in add_emails:
                if email['message_id'] not in [r['message_id'] for r in filtered_results]:
                    email['index'] = str(email.get('index', 'N/A'))
                    email['message_id'] = str(email.get('message_id', 'N/A'))
                    filtered_results.append(email)

        # Calcular relevancia
        ranked_results = []
        relevance_scores = []
        for email in filtered_results:
            # Similitud semántica
            if 'es_embedding' in email and email['es_embedding']:
                semantic_score = cosine_similarity(query_embedding, email['es_embedding'], compressed=False)
            else:
                semantic_score = cosine_similarity(query_embedding, email.get('embedding'), compressed=True)
            
            # Puntuación textual
            text_score = email.get('es_score', 0) if not filter_only else 0
            
            # Puntuación por términos relevantes
            term_score = 0
            if 'relevant_terms' in email:
                for term in terms:
                    normalized_term = normalize_text(term)
                    for key, value in email['relevant_terms'].items():
                        if normalized_term in normalize_text(key):
                            term_score += value.get('frequency', 1) * 0.1  # Ajuste por frecuencia
            
            feedback_weight = feedback_weights.get(email['message_id'], 1.0)
            relevance = int((0.6 * semantic_score + 0.3 * text_score + 0.1 * term_score + 0.05 * feedback_weight) * 100)
            if relevance < min_relevance and not filter_only:
                continue

            email_text = normalize_text(f"{email.get('subject', '')} {email.get('summary', '')}")
            query_terms = [normalize_text(term) for term in terms]
            keyword_matches = sum(1 for term in query_terms if term in email_text)
            if len(query_terms) > 1 and keyword_matches < len(query_terms) * 0.5 and not filter_only:
                continue

            email_terms = [term for term in email.get('relevant_terms', {}).keys() if term.lower() in [t.lower() for t in terms]] if not filter_only else []
            explanation_parts = []
            semantic_percentage = int(semantic_score * 100)
            if semantic_score > 0.7:
                explanation_parts.append(f"alta similitud semántica ({semantic_percentage}%)")
            elif semantic_score > 0.3:
                explanation_parts.append(f"similitud semántica moderada ({semantic_percentage}%)")
            if text_score > 0:
                explanation_parts.append(f"coincidencia textual (puntuación: {text_score:.2f})")
            if term_score > 0:
                explanation_parts.append(f"términos relevantes (puntuación: {term_score:.2f})")
            if feedback_weight != 1.0:
                explanation_parts.append(f"ajustado por retroalimentación ({'negativa' if feedback_weight < 1.0 else 'positiva'})")
            explanation = "Seleccionado por: " + ", ".join(explanation_parts)

            from_field = email.get('from', '')
            to_field = email.get('to', '')
            from_email = extract_email(from_field)
            to_email = extract_email(to_field)
            from_match = re.match(r'(.*)<(.+)>', from_field, re.IGNORECASE) if isinstance(from_field, str) else None
            if from_match:
                from_name, from_email_from_field = from_match.groups()
                email['from'] = format_email_field(from_name, from_email_from_field)
            elif from_email:
                from_name = from_field if from_field and not extract_email(from_field) else ''
                email['from'] = format_email_field(from_name, from_email)
            else:
                email['from'] = 'N/A'

            to_match = re.match(r'(.*)<(.+)>', to_field, re.IGNORECASE) if isinstance(to_field, str) else None
            if to_match:
                to_name, to_email_from_field = to_match.groups()
                email['to'] = format_email_field(to_name, to_email_from_field)
            elif to_email:
                to_name = to_field if to_field and not extract_email(to_field) else ''
                email['to'] = format_email_field(to_name, to_email)
            else:
                email['to'] = 'N/A'

            ranked_results.append({
                'index': email['index'],
                'message_id': email['message_id'],
                'date': email.get('date', ''),
                'from': email['from'],
                'to': email['to'],
                'subject': email.get('subject', ''),
                'description': email.get('summary', 'Sin resumen'),
                'relevant_terms': email_terms,
                'relevance': relevance,
                'explanation': explanation
            })

        ranked_results.sort(key=lambda x: x['relevance'], reverse=True)
        total_filtered_results = len(ranked_results)
        start_idx = (page - 1) * results_per_page
        end_idx = start_idx + results_per_page
        paginated_results = ranked_results[start_idx:end_idx]

        logger.info("Devolviendo %s correos relevantes de %s totales", len(paginated_results), total_filtered_results)
        return {
            'results': paginated_results,
            'totalResults': total_filtered_results,
            'filter_counts': filter_counts
        }
    except Exception as e:
        logger.error("Error al buscar correos: %s", str(e), exc_info=True)
        return {'results': [], 'totalResults': 0, 'filter_counts': {'remove': {}, 'add': {}}}