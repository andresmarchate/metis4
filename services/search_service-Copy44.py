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

client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]

es = Elasticsearch([{'host': ELASTICSEARCH_HOST, 'port': ELASTICSEARCH_PORT, 'scheme': 'http'}])

embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

DOMAIN_SYNONYMS = {
    "informacion_juridica": ["legal", "derecho", "judicial", "juzgado", "procedimiento"],
    "viajes": ["turismo", "vacaciones", "reserva", "viaje"],
    "negocios": ["comercial", "empresa", "propuesta"],
    "promociones": ["ofertas", "descuentos", "publicidad"],
    "tecnico": ["soporte", "incidencia", "tecnologia"],
    "personal": ["privado", "familiar"],
    "general": [],
    "negociaciones": ["venta", "compra", "acuerdo", "transaccion", "negociacion", "precio"],
    "negociaciones_inmobiliarias": ["venta", "compra", "inmueble", "condominio", "hipoteca"]
}

def normalize_text(text):
    if not text or not isinstance(text, str):
        return text
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if unicodedata.category(c) != 'Mn')
    return text.lower()

def cosine_similarity(emb1, emb2, compressed=True):
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
    if not text or not isinstance(text, str):
        return None
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text, re.IGNORECASE)
    return email_match.group(0) if email_match else None

def format_email_field(name, email):
    logger.debug("Formateando campo de correo: name=%s, email=%s", name, email)
    if email:
        name = name.strip() if name else ''
        return f"{name} <{email}>" if name else f"<{email}>"
    return 'N/A'

def extract_email_from_input(input_str):
    if not input_str or not isinstance(input_str, str):
        return None
    match = re.search(r'<([^>]+@[^>]+)>', input_str, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    email = extract_email(input_str)
    return email.lower() if email else None

def get_email_addresses(prefix='', limit=50, user=None):
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

        email['summary'] = email.get('summary', 'Sin resumen')
        email['relevant_terms'] = email.get('relevant_terms', [])

        logger.debug("Correo procesado: from=%s, to=%s, index=%s, message_id=%s", email['from'], email['to'], email['index'], email['message_id'])
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
        logger.debug("Found %d emails for bulk feedback", len(message_ids))

        affected_count = 0
        for message_id in message_ids:
            try:
                save_feedback(query, message_id.lower(), False)
                affected_count += 1
                logger.debug("Feedback saved for message_id: %s", message_id)
            except Exception as e:
                logger.error("Error saving feedback for message_id %s: %s", message_id, str(e))

        logger.info("Bulk feedback completed: %d emails affected", affected_count)
        return affected_count
    except Exception as e:
        logger.error("Error in bulk feedback: %s", str(e), exc_info=True)
        return 0

def extract_scores(explanation):
    """Extrae detalles de texto, puntuación de dominio y semántica de la explicación de Elasticsearch."""
    text_details = []
    domain_score = 0.0
    semantic_score = 0.0
    
    def recurse(expl):
        nonlocal text_details, domain_score, semantic_score
        if 'value' in expl and expl['value'] > 0:
            desc = expl.get('description', '')
            logger.debug(f"Procesando descripción: {desc}, value={expl['value']}")
            
            # Coincidencias de texto
            if 'weight' in desc:
                match = re.search(r'weight\(([^:]+):([^ ]+) in \d+\)', desc)
                if match:
                    field, term = match.groups()
                    text_details.append({
                        'field': field,
                        'term': term,
                        'score': expl['value']
                    })
                    logger.debug(f"Texto: field={field}, term={term}, score={expl['value']}")
            
            # Puntuación de dominio
            elif 'terms' in desc and 'semantic_domain' in desc:
                domain_score += expl['value']
                logger.debug(f"Dominio: score={expl['value']}")
            
            # Puntuación semántica
            elif 'script_score' in desc:
                semantic_score += expl['value']
                logger.debug(f"Semántico: score={expl['value']}")
            
            # Recursar en detalles anidados
            for detail in expl.get('details', []):
                recurse(detail)
    
    recurse(explanation)
    logger.debug(f"Resultados extraídos: text_details={text_details}, domain_score={domain_score}, semantic_score={semantic_score}")
    return text_details, domain_score, semantic_score

def search_emails(processed_query, intent, terms, query_embedding, min_relevance=25, page=1, results_per_page=25, filters=None, filter_only=False, user=None):
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
        remove_filters = [f for f in filters if f.get('action') == 'remove']
        add_filters = [f for f in filters if f.get('action') == 'add']
        filter_counts = {
            'remove': {','.join(f['terms']).lower(): 0 for f in remove_filters},
            'add': {','.join(f['terms']).lower(): 0 for f in add_filters}
        }

        if query_embedding:
            query_vector = np.frombuffer(zlib.decompress(query_embedding), dtype=np.float32).tolist()
        else:
            query_vector = None

        # Consulta base sin filtros "remove"
        base_query = {
            "query": {
                "bool": {
                    "must": [],
                    "filter": [{"terms": {"mailbox_id": user_mailboxes}}],
                    "should": [],
                    "must_not": [],
                    "minimum_should_match": 0
                }
            }
        }

        if terms and not filter_only:
            base_query["query"]["bool"]["must"].append({
                "multi_match": {
                    "query": " ".join(terms),
                    "fields": ["body^1", "summary^2", "relevant_terms_array^3", "subject^2"],
                    "type": "cross_fields",
                    "operator": "and"
                }
            })

        if intent != 'general' and not filter_only:
            related_domains = DOMAIN_SYNONYMS.get(intent, [intent])
            base_query["query"]["bool"]["should"].append({
                "terms": {"semantic_domain": related_domains, "boost": 1.5}
            })
            base_query["query"]["bool"]["minimum_should_match"] = 1

        if query_vector and not filter_only:
            base_query["query"]["bool"]["should"].append({
                "script_score": {
                    "query": {"match_all": {}},
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                        "params": {"query_vector": query_vector}
                    },
                    "boost": 5
                }
            })
            base_query["query"]["bool"]["minimum_should_match"] = 1

        metadata_filters = processed_query.get('metadata_filters', {})
        for key, value in metadata_filters.items():
            if key in ['from', 'to', 'subject']:
                base_query["query"]["bool"]["must"].append({
                    "match": {key: {"query": value, "boost": 2}}
                })
            elif key == 'date_range':
                base_query["query"]["bool"]["filter"].append({
                    "range": {
                        "date": {
                            "gte": value['start'],
                            "lte": value['end']
                        }
                    }
                })

        # Consulta principal con filtros aplicados
        es_query = {
            "query": base_query["query"].copy(),
            "size": results_per_page,
            "from": (page - 1) * results_per_page,
            "explain": True
        }

        for filter in remove_filters:
            for term in filter.get('terms', []):
                es_query["query"]["bool"]["must_not"].append({
                    "multi_match": {
                        "query": term,
                        "fields": ["body", "summary", "relevant_terms_array", "subject", "from", "to"],
                        "type": "cross_fields"
                    }
                })
        for filter in add_filters:
            for term in filter.get('terms', []):
                es_query["query"]["bool"]["should"].append({
                    "multi_match": {
                        "query": term,
                        "fields": ["body", "summary", "relevant_terms_array", "subject", "from", "to"],
                        "type": "cross_fields",
                        "boost": 2
                    }
                })
            es_query["query"]["bool"]["minimum_should_match"] = 1

        logger.debug(f"Consulta Elasticsearch: {es_query}")
        es_results = es.search(index='email_index', body=es_query)
        total_results = es_results['hits']['total']['value']
        es_hits = es_results['hits']['hits']
        logger.info(f"Resultados de Elasticsearch: {len(es_hits)} hits, total: {total_results}, max_score: {max([hit['_score'] for hit in es_hits], default=0)}")

        # Conteo de filtros "remove" basado en la consulta base
        for filter in remove_filters:
            terms_key = ','.join(filter['terms']).lower()
            count_query = {
                "query": {
                    "bool": {
                        "must": base_query["query"]["bool"].get("must", []),
                        "filter": base_query["query"]["bool"].get("filter", []),
                        "should": base_query["query"]["bool"].get("should", []),
                        "must_not": base_query["query"]["bool"].get("must_not", []),
                        "minimum_should_match": base_query["query"]["bool"].get("minimum_should_match", 0)
                    }
                }
            }
            for term in filter['terms']:
                count_query["query"]["bool"]["must"].append({
                    "multi_match": {
                        "query": term,
                        "fields": ["body", "summary", "relevant_terms_array", "subject", "from", "to"],
                        "type": "cross_fields"
                    }
                })
            try:
                count_result = es.count(index='email_index', body=count_query)
                filter_counts['remove'][terms_key] = count_result['count']
            except Exception as e:
                logger.error(f"Error al contar correos para filtro remove {terms_key}: {str(e)}")
                filter_counts['remove'][terms_key] = 0

        # Conteo de filtros "add" sobre resultados finales
        for filter in add_filters:
            terms_key = ','.join(filter['terms']).lower()
            filter_counts['add'][terms_key] = sum(
                1 for hit in es_hits
                if any(term.lower() in ' '.join([hit['_source'].get(field, '').lower() for field in ["body", "summary", "relevant_terms_array", "subject", "from", "to"]]) for term in filter['terms'])
            )

        results = []
        for hit in es_hits:
            explanation = hit['_explanation']
            logger.debug(f"Explicación para message_id {hit['_source']['message_id']}: {explanation}")
            text_details, domain_score, semantic_score = extract_scores(explanation)
            total_score = hit['_score']
            semantic_domain = hit['_source'].get('semantic_domain', 'desconocido')
            
            logger.debug(f"Detalles: message_id={hit['_source']['message_id']}, text_details={text_details}, domain_score={domain_score}, semantic_score={semantic_score}, total_score={total_score}")
            
            results.append({
                'message_id': hit['_source']['message_id'],
                'index': hit['_source'].get('index', 'N/A'),
                'from': hit['_source'].get('from', 'N/A'),
                'to': hit['_source'].get('to', 'N/A'),
                'subject': hit['_source'].get('subject', ''),
                'date': hit['_source'].get('date', ''),
                'summary': hit['_source'].get('summary', 'Sin resumen'),
                'relevant_terms': hit['_source'].get('relevant_terms_array', []),
                'text_details': text_details,
                'domain_score': domain_score,
                'semantic_score': semantic_score,
                'total_score': total_score,
                'semantic_domain': semantic_domain
            })

        ranked_results = []
        max_score = max([hit['total_score'] for hit in results], default=1) or 1
        for email in results:
            relevance = int((email['total_score'] / max_score) * 100) if max_score > 0 else 0
            if relevance >= min_relevance or filter_only:
                explanation = f"La puntuación total de {email['total_score']:.2f} del correo se compone de:\n"
                
                if email['domain_score'] > 0:
                    explanation += f"- {email['domain_score']:.2f} puntos del dominio semántico, que mide la relación del correo con un contexto temático específico: {email['semantic_domain']}.\n"
                
                if email['text_details']:
                    text_score = sum(detail['score'] for detail in email['text_details'])
                    explanation += f"- {text_score:.2f} puntos de la coincidencia de texto, que proviene de la búsqueda de términos como "
                    terms_set = set(detail['term'] for detail in email['text_details'])
                    explanation += f"\"{', '.join(terms_set)}\" en campos como "
                    
                    field_scores = {}
                    for detail in email['text_details']:
                        field = detail['field']
                        field_scores[field] = field_scores.get(field, 0.0) + detail['score']
                    
                    field_explanations = []
                    for field, score in field_scores.items():
                        if field == 'subject':
                            field_explanations.append(f"el asunto (\"{email['subject']}\") ({score:.2f} puntos)")
                        elif field == 'summary':
                            field_explanations.append(f"la descripción (que menciona \"{email['summary']}\") ({score:.2f} puntos)")
                        elif field == 'relevant_terms_array':
                            field_explanations.append(f"los términos relevantes (que incluyen palabras clave relacionadas: {', '.join(email['relevant_terms'])}) ({score:.2f} puntos)")
                        else:
                            field_explanations.append(f"{field} ({score:.2f} puntos)")
                    
                    explanation += ', '.join(field_explanations) + ".\n"
                
                if email['semantic_score'] > 0:
                    explanation += f"- {email['semantic_score']:.2f} puntos de la similitud semántica, calculada mediante la comparación del contenido del correo con la consulta.\n"
                
                if not (email['text_details'] or email['domain_score'] > 0 or email['semantic_score'] > 0):
                    explanation += "- No se encontraron detalles específicos para esta puntuación. Es posible que la relevancia se base en factores generales de la consulta.\n"
                
                if not explanation.strip().endswith('.'):
                    explanation += "."
                
                ranked_results.append({
                    'index': str(email.get('index', 'N/A')),
                    'message_id': str(email.get('message_id', 'N/A')),
                    'date': email.get('date', ''),
                    'from': email.get('from', 'N/A'),
                    'to': email.get('to', 'N/A'),
                    'subject': email.get('subject', ''),
                    'description': email.get('summary', 'Sin resumen'),
                    'relevant_terms': email.get('relevant_terms', []),
                    'relevance': relevance,
                    'explanation': explanation
                })

        ranked_results.sort(key=lambda x: x['relevance'], reverse=True)
        total_filtered_results = total_results if not filter_only else len(ranked_results)
        paginated_results = ranked_results[:results_per_page]

        logger.info("Devolviendo %s correos relevantes de %s totales", len(paginated_results), total_filtered_results)
        return {
            'results': paginated_results,
            'totalResults': total_filtered_results,
            'filter_counts': filter_counts
        }
    except Exception as e:
        logger.error("Error al buscar correos: %s", str(e), exc_info=True)
        return {'results': [], 'totalResults': 0, 'filter_counts': {'remove': {}, 'add': {}}}