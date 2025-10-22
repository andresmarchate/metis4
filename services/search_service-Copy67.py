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
import json

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

logger.info("Cargando modelo de embeddings: %s", 'paraphrase-multilingual-MiniLM-L12-v2')
embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
logger.info("Modelo de embeddings cargado exitosamente")

DOMAIN_SYNONYMS = {
    "informacion_juridica": ["legal", "derecho", "judicial", "juzgado", "procedimiento", "notaria", "abogado", "procurador", "escritura", "registro"],
    "ofertas_viaje": ["turismo", "vacaciones", "reserva", "viaje", "booking", "vuelo"],
    "negocios": ["comercial", "empresa", "propuesta", "negocio", "inversión"],
    "promociones": ["ofertas", "descuentos", "publicidad"],
    "tecnico": ["soporte", "incidencia", "tecnologia"],
    "personal": ["privado", "familiar"],
    "general": [],
    "negociaciones": ["venta", "compra", "acuerdo", "transaccion", "negociacion", "precio"],
    "negociaciones_inmobiliarias": ["venta", "compra", "inmueble", "condominio", "hipoteca", "vivienda", "extincion", "escritura", "registro"]
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
        logger.debug("Similitud de coseno calcula: %s", similarity)
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
    if logger.isEnabledFor(logging.DEBUG):
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
        logger.info("Devolviendo %d direcciones formateadas", len(formatted_addresses))  # Aggregate: count only
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
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Ejecutando pipeline MongoDB: {pipeline}")
        start_time = datetime.now()
        emails = list(emails_collection.aggregate(pipeline))
        logger.info(f"Pipeline MongoDB ejecutado: {len(emails)} emails encontrados en {(datetime.now() - start_time).total_seconds():.2f}s")  # Aggregate: count + time
        if not emails:
            logger.warning("No se encontraron correos. Verificando datos en la colección...")  # Reduced: no per-sample log
            sample_emails = list(emails_collection.find(
                {'mailbox_id': {'$in': user_mailboxes}, '$or': [
                    {'from': {'$regex': email1_escaped, '$options': 'i'}},
                    {'to': {'$regex': email1_escaped, '$options': 'i'}}
                ]},
                {'from': 1, 'to': 1, 'date': 1}
            ).limit(5))
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Muestra de correos para email1: {len(sample_emails)} items")
            sample_emails = list(emails_collection.find(
                {'mailbox_id': {'$in': user_mailboxes}, '$or': [
                    {'from': {'$regex': email2_escaped, '$options': 'i'}},
                    {'to': {'$regex': email2_escaped, '$options': 'i'}}
                ]},
                {'from': 1, 'to': 1, 'date': 1}
            ).limit(5))
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Muestra de correos para email2: {len(sample_emails)} items")
        results = []
        for email in emails:  # Loop: no per-item log
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
        logger.info(f"Devolviendo {len(results)} correos de conversación procesados")
        return results
    except Exception as e:
        logger.error(f"Error al buscar correos de conversación: {str(e)}", exc_info=True)
        return []

def get_email_by_id(identifier, is_index=False):
    logger.info("Obteniendo correo con identifier: %s, is_index: %s", identifier, is_index)
    try:
        query_field = 'index' if is_index else 'message_id'
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Buscando en campo: {query_field}")
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
        if not email['message_id'] or email['message_id'] == 'N/A':
            logger.error("Campo 'message_id' no válido en correo: index=%s", email['index'])
            return None
        from_field = email.get('from', '')
        from_email = email.get('from_email', '') or extract_email(from_field)
        if logger.isEnabledFor(logging.DEBUG):
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
        if logger.isEnabledFor(logging.DEBUG):
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
        if logger.isEnabledFor(logging.DEBUG):
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
        elif intent == 'ofertas_viaje':
            conditions['semantic_domain'] = {'$in': DOMAIN_SYNONYMS.get('ofertas_viaje', ['viaje'])}
        elif intent == 'negociaciones_inmobiliarias':
            conditions['semantic_domain'] = {'$in': DOMAIN_SYNONYMS.get('negociaciones_inmobiliarias', ['inmueble'])}
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
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Condiciones de filtrado finales para bulk feedback: %s", final_conditions)
        start_time = datetime.now()
        cursor = emails_collection.find(final_conditions, {'message_id': 1}).limit(1000)
        message_ids = [email['message_id'] for email in cursor if 'message_id' in email]
        logger.info(f"Found {len(message_ids)} emails for bulk feedback in {(datetime.now() - start_time).total_seconds():.2f}s")  # Aggregate
        affected_count = 0
        for message_id in message_ids:  # Loop: no per-save log
            try:
                save_feedback(query, message_id.lower(), False)
                affected_count += 1
            except Exception as e:
                logger.error("Error saving feedback for message_id %s: %s", message_id, str(e))
        logger.info("Bulk feedback completed: %d emails affected in %s seconds", affected_count, (datetime.now() - start_time).total_seconds())
        return affected_count
    except Exception as e:
        logger.error("Error in bulk feedback: %s", str(e), exc_info=True)
        return 0

def extract_components(explanation):
    components = {
        'text': 0.0,
        'domain': 0.0,
        'semantic': 0.0,
        'temporal': 0.0,
        'text_details': []
    }
  
    def recurse(expl, path=""):
        nonlocal components
        if 'value' in expl and expl['value'] > 0:
            desc = expl.get('description', '')
            current_path = f"{path} -> {desc}"
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Procesando: {current_path}, value={expl['value']}")
          
            if 'weight' in desc:
                match = re.search(r'weight\(([^:]+):([^ ]+) in \d+\)', desc)
                if match:
                    field, term = match.groups()
                    score = expl['value']
                    components['text'] += score
                    components['text_details'].append({
                        'field': field,
                        'term': term,
                        'score': score
                    })
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Texto detectado en {current_path}: field={field}, term={term}, score={score}")
          
            elif 'terms' in desc and 'semantic_domain' in desc:
                components['domain'] += expl['value']
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Dominio detectado en {current_path}: score={expl['value']}")
          
            elif 'script_score' in desc:
                components['semantic'] += expl['value']
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Semántico detectado en {current_path}: score={expl['value']}")
          
            elif 'range' in desc and 'date' in desc:
                components['temporal'] += expl['value']
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Temporal detectado en {current_path}: score={expl['value']}")
          
            for i, detail in enumerate(expl.get('details', [])):
                recurse(detail, f"{current_path} -> detail[{i}]")
  
    recurse(explanation)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Componentes extraídos: text={components['text']}, domain={components['domain']}, semantic={components['semantic']}, temporal={components['temporal']}")
    return components

def build_explanation(total_score, components, email):
    explanation = f"La puntuación total de {total_score:.2f} del correo se compone de la suma de:\n"
    contributions = []
  
    original_sum = components['text'] + components['domain'] + components['semantic'] + components['temporal']
  
    if original_sum == 0:
        explanation += "- No se encontraron componentes específicos. La puntuación puede basarse en factores generales de la consulta.\n"
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Explicación construida: {explanation}")
        return explanation
  
    scaling_factor = total_score / original_sum if original_sum > 0 else 1.0
  
    if components['text'] > 0:
        text_score = components['text'] * scaling_factor
        terms_set = set(detail['term'] for detail in components['text_details'])
        field_scores = {}
        for detail in components['text_details']:
            field = detail['field']
            score = detail['score'] * scaling_factor
            if field not in field_scores:
                field_scores[field] = 0.0
            field_scores[field] += score
      
        contributions.append(f"- {text_score:.2f} puntos de coincidencias de texto")
        sub_explanation = f" - Coincidencia de texto ({text_score:.2f} puntos), proveniente de términos como \"{', '.join(terms_set)}\" en:\n"
        for field, score in field_scores.items():
            if field == 'subject':
                sub_explanation += f" - Asunto: {score:.2f} puntos\n"
            elif field == 'body':
                sub_explanation += f" - Cuerpo: {score:.2f} puntos\n"
            elif field == 'summary':
                sub_explanation += f" - Descripción: {score:.2f} puntos\n"
            elif field == 'relevant_terms_array':
                sub_explanation += f" - Términos relevantes: {score:.2f} puntos\n"
            else:
                sub_explanation += f" - {field}: {score:.2f} puntos\n"
        contributions.append(sub_explanation)
  
    if components['domain'] > 0:
        domain_score = components['domain'] * scaling_factor
        contributions.append(f"- {domain_score:.2f} puntos del dominio semántico '{email['semantic_domain']}', que mide la relación del correo con un contexto temático específico")
  
    if components['semantic'] > 0:
        semantic_score = components['semantic'] * scaling_factor
        contributions.append(f"- {semantic_score:.2f} puntos de similitud semántica")
  
    if components['temporal'] > 0:
        temporal_score = components['temporal'] * scaling_factor
        contributions.append(f"- {temporal_score:.2f} puntos por proximidad temporal al rango especificado")
  
    explanation += '\n'.join(contributions) + '\n'
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Explicación construida: {explanation}")
    return explanation

def is_complex_query(processed_query, term_groups, intent, query_embedding):
    """Determina si la consulta requiere el modo full (complejo) o light (simple)."""
    num_terms = sum(len(group) for group in term_groups or [])
    has_semantic = bool(query_embedding)
    has_metadata = bool(processed_query.get('metadata_filters', {}))
    return num_terms > 3 or intent != 'general' or has_semantic or has_metadata

def process_hits_light(hits, page, results_per_page, min_relevance=25):
    """Procesa hits en modo light: formato simple sin explain full."""
    results = []
    scores = [hit['_score'] for hit in hits]
    mean_score = np.mean(scores) if scores else 0
    for hit in hits:  # Loop: no per-hit log
        source = hit['_source']
        total_score = hit['_score']
        relevance = int(100 / (1 + np.exp(-0.5 * (total_score - mean_score))))
        if relevance < min_relevance:
            continue
        results.append({
            'message_id': source['message_id'],
            'index': source.get('index', 'N/A'),
            'from': source.get('from', 'N/A'),
            'to': source.get('to', 'N/A'),
            'subject': source.get('subject', ''),
            'date': source.get('date', ''),
            'summary': source.get('summary', 'Sin resumen'),
            'relevant_terms': source.get('relevant_terms_array', []),
            'total_score': total_score,
            'relevance': relevance,
            'explanation': 'Búsqueda por keywords + cribado bayesiano. Coincidencias en asunto, cuerpo y términos relevantes.',
            'semantic_domain': source.get('semantic_domain', 'desconocido')
        })
    # Paginación
    start = (page - 1) * results_per_page
    return results[start:start + results_per_page]

def search_emails(processed_query, intent, term_groups, query_embedding, min_relevance=25, page=1, results_per_page=25, filters=None, filter_only=False, user=None, get_all_ids=False):
    """
    Función principal de búsqueda: Flujo end-to-end con logs trace.
    Integra parse, ES retrieval, filtros, ranking, cache (aumentado sin reducir existing).
    """
    start_time = datetime.now()
    logger.info("=== SEARCH FLOW START: Intent=%s, Term_groups=%s, Query_emb=%s, Min_rel=%s, Page=%s, Filters=%s, Filter_only=%s, User=%s, Get_all_ids=%s ===", 
                intent, term_groups, bool(query_embedding), min_relevance, page, filters, filter_only, user.username if user else 'None', get_all_ids)  # Nuevo: Inicio flujo full context
    
    logger.info("Buscando correos para intent: %s, term_groups: %s, min_relevance: %s, page: %s, filters: %s, filter_only: %s, user: %s, get_all_ids: %s",
                intent, term_groups, min_relevance, page, filters, filter_only, user.username if user else 'None', get_all_ids)
    if not user:
        logger.error("Usuario no proporcionado para búsqueda de correos")
        logger.info("=== SEARCH FLOW END: Error - No user, 0 results in %.2fs ===", (datetime.now() - start_time).total_seconds())  # Nuevo: End con error
        return {'results': [], 'totalResults': 0, 'filter_counts': {'remove': {}, 'add': {}}, 'all_email_ids': []}
    user_mailboxes = [mailbox['mailbox_id'] for mailbox in user.mailboxes]
    if not user_mailboxes:
        logger.warning(f"No se encontraron buzones para el usuario: {user.username}")
        logger.info("=== SEARCH FLOW END: Warning - No mailboxes, 0 results in %.2fs ===", (datetime.now() - start_time).total_seconds())
        return {'results': [], 'totalResults': 0, 'filter_counts': {'remove': {}, 'add': {}}, 'all_email_ids': []}
    try:
        feedback_weights = get_feedback_weights(user.username)
        logger.debug("Pesos de retroalimentación obtenidos en %s segundos", (datetime.now() - start_time).total_seconds())
        filters = filters or []
        remove_filters = [f for f in filters if f.get('action') == 'remove']
        add_filters = [f for f in filters if f.get('action') == 'add']
        filter_counts = {
            'remove': {','.join(f['terms']).lower(): 0 for f in remove_filters},
            'add': {','.join(f['terms']).lower(): 0 for f in add_filters}
        }
        # Ruta híbrida: Light para queries simples
        if not is_complex_query(processed_query, term_groups, intent, query_embedding) and not filter_only:
            logger.info("Usando modo light para query simple")
            # 1. Extraer todos los términos
            all_terms = [term for group in term_groups for term in group] if term_groups else []
            query_str = ' '.join(all_terms)
            # 2. Query ES light (solo multi_match, sin script_score ni domains)
            base_query_light = {
                "query": {
                    "multi_match": {
                        "query": query_str,
                        "fields": ["subject^3", "body^2", "summary^1.5", "relevant_terms_array^1"],
                        "type": "cross_fields"
                    }
                },
                "filter": [{"terms": {"mailbox_id": user_mailboxes}}],
                "size": results_per_page * 5 # Pequeño para eficiencia
            }
            # Añadir metadata filters
            metadata_filters = processed_query.get('metadata_filters', {})
            for key, value in metadata_filters.items():
                if key == 'from':
                    if '@' in value:
                        base_query_light["query"]["bool"]["must"].append({"match": {"from": value}})
                    else:
                        base_query_light["query"]["bool"]["must"].append({"multi_match": {"query": value, "fields": ["from", "from_email"]}})
                elif key == 'to':
                    if '@' in value:
                        base_query_light["query"]["bool"]["must"].append({"match": {"to": value}})
                    else:
                        base_query_light["query"]["bool"]["must"].append({"multi_match": {"query": value, "fields": ["to", "to_email"]}})
                elif key == 'subject':
                    base_query_light["query"]["bool"]["must"].append({"match": {"subject": value}})
                elif key == 'date_range':
                    base_query_light["filter"].append({"range": {"date": {"gte": value['start'], "lte": value['end']}}})
            # Aplica remove/add
            if remove_filters:
                base_query_light["query"]["bool"]["must_not"] = []
                for f in remove_filters:
                    for term in f['terms']:
                        base_query_light["query"]["bool"]["must_not"].append({
                            "multi_match": {"query": term, "fields": ["subject", "body", "summary", "relevant_terms_array", "from", "to"], "type": "cross_fields"}
                        })
            if add_filters:
                base_query_light["query"]["bool"]["must"] = base_query_light["query"]["bool"]["must"] or []
                for f in add_filters:
                    for term in f['terms']:
                        base_query_light["query"]["bool"]["must"].append({
                            "multi_match": {"query": term, "fields": ["subject", "body", "summary", "relevant_terms_array", "from", "to"], "type": "cross_fields"}
                        })
            # Ejecutar
            es_results = es.search(index='email_index', body=base_query_light)
            hits = es_results['hits']['hits']
            logger.info(f"Retrieved %d raw hits from ES in light mode", len(hits))  # Nuevo: Retrieval flow
            # 3. Cribado Bayesian
            filtered_hits = []
            for hit in hits:  # Loop: no per-hit log
                msg_id = hit['_source']['message_id']
                weight = feedback_weights.get(msg_id, 1.0)
                if weight >= 0.5: # Threshold para cribado
                    hit['_source']['bayesian_score'] = weight
                    filtered_hits.append(hit)
            logger.info(f"Applied Bayesian filter: %d docs remaining post-feedback", len(filtered_hits))  # Nuevo: Post-filter flow
            # 4. Ordenar por score * bayesian
            filtered_hits.sort(key=lambda h: h['_score'] * h['_source'].get('bayesian_score', 1.0), reverse=True)
            paginated_results = process_hits_light(filtered_hits, page, results_per_page, min_relevance)
            total_filtered_results = len(filtered_hits)
            all_email_ids = [r['message_id'] if r['message_id'] != 'N/A' else r['index'] for r in paginated_results]
            # Conteos simples
            for f in remove_filters + add_filters:
                terms_key = ','.join(f['terms']).lower()
                count_query = {"query": {"match_all": {}}, "filter": [{"terms": {"mailbox_id": user_mailboxes}}]}
                for term in f['terms']:
                    count_query["query"]["bool"]["must"] = count_query["query"]["bool"]["must"] or []
                    count_query["query"]["bool"]["must"].append({"multi_match": {"query": term, "fields": ["subject", "body", "summary", "relevant_terms_array", "from", "to"]}})
                if f['action'] == 'remove':
                    count_query["query"]["bool"]["must_not"] = [{"match": {"_id": "dummy"}}] # Placeholder, adjust if needed
                count_result = es.count(index='email_index', body=count_query)
                filter_counts[f['action']][terms_key] = count_result['count']
            logger.info(f"Modo light: %s resultados en %s segundos", len(paginated_results), (datetime.now() - start_time).total_seconds())
            logger.info("=== SEARCH FLOW END (Light Mode): %d results, avg relevance N/A, in %.2fs ===", len(paginated_results), (datetime.now() - start_time).total_seconds())  # Nuevo: End light
            return {
                'results': paginated_results,
                'totalResults': total_filtered_results,
                'filter_counts': filter_counts,
                'all_email_ids': all_email_ids
            }
        # Modo full: Código original intacto
        logger.info("Usando modo full para query compleja")
        if query_embedding:
            query_vector = np.frombuffer(zlib.decompress(query_embedding), dtype=np.float32).tolist()
            if len(query_vector) != 384:
                logger.error("Dimensión del vector de consulta incorrecta: %d (esperado: 384)", len(query_vector))
                raise ValueError("Dimensión del embedding no coincide con el modelo MiniLM-L12-v2")
            logger.debug("Query vector descomprimido y convertido a lista en %s segundos", (datetime.now() - start_time).total_seconds())
        else:
            query_vector = None
            logger.debug("No se proporcionó query_embedding")
        # Consulta base
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
        if term_groups and not filter_only:
            for group in term_groups:
                group_should = {
                    "bool": {
                        "should": [],
                        "minimum_should_match": 1
                    }
                }
                for term in group:
                    term_boost = 4 if term == group[0] else 1
                    group_should["bool"]["should"].append({
                        "multi_match": {
                            "query": term,
                            "fields": ["body^2", "summary^1.5", "relevant_terms_array^1", "subject^3"],
                            "type": "cross_fields",
                            "boost": term_boost
                        }
                    })
                base_query["query"]["bool"]["must"].append(group_should)
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
            base_query["query"]["bool"]["minimum_should_match"] = 0
        if intent != 'general' and not filter_only:
            related_domains = DOMAIN_SYNONYMS.get(intent, [intent])
            base_query["query"]["bool"]["should"].append({
                "terms": {"semantic_domain": related_domains, "boost": 1.5}
            })
            base_query["query"]["bool"]["minimum_should_match"] = 0
        metadata_filters = processed_query.get('metadata_filters', {})
        for key, value in metadata_filters.items():
            if key == 'from':
                if '@' in value:
                    base_query["query"]["bool"]["must"].append({
                        "match": {"from": {"query": value, "boost": 3}}
                    })
                else:
                    base_query["query"]["bool"]["must"].append({
                        "multi_match": {
                            "query": value,
                            "fields": ["from", "from_email"],
                            "boost": 3
                        }
                    })
            elif key == 'to':
                if '@' in value:
                    base_query["query"]["bool"]["must"].append({
                        "match": {"to": {"query": value, "boost": 3}}
                    })
                else:
                    base_query["query"]["bool"]["must"].append({
                        "multi_match": {
                            "query": value,
                            "fields": ["to", "to_email"],
                            "boost": 3
                        }
                    })
            elif key == 'subject':
                base_query["query"]["bool"]["must"].append({
                    "match": {"subject": {"query": value, "boost": 2}}
                })
            elif key == 'date_range':
                base_query["query"]["bool"]["filter"].append({
                    "range": {
                        "date": {
                            "gte": value['start'],
                            "lte": value['end'],
                            "boost": 3
                        }
                    }
                })
        # Consulta principal para obtener todos los resultados relevantes
        es_query = {
            "query": {
                "bool": {
                    "must": base_query["query"]["bool"]["must"].copy(),
                    "filter": base_query["query"]["bool"]["filter"].copy(),
                    "should": base_query["query"]["bool"]["should"].copy(),
                    "must_not": base_query["query"]["bool"]["must_not"].copy(),
                    "minimum_should_match": base_query["query"]["bool"]["minimum_should_match"]
                }
            },
            "sort": [
                {"_score": {"order": "desc"}}
            ],
            "size": 10000, # Ajusta este valor según el máximo esperado de resultados
            "explain": True
        }
        # Filtros "remove"
        for filter in remove_filters:
            for term in filter.get('terms', []):
                es_query["query"]["bool"]["must_not"].append({
                    "multi_match": {
                        "query": term,
                        "fields": ["body", "summary", "relevant_terms_array", "subject", "from", "to"],
                        "type": "cross_fields"
                    }
                })
        # Consulta para filtros "add"
        add_query = {
            "query": {
                "bool": {
                    "must": [{"terms": {"mailbox_id": user_mailboxes}}],
                    "must_not": [],
                    "should": [],
                    "minimum_should_match": 0
                }
            },
            "size": 10000, # Ajusta este valor según el máximo esperado
            "explain": True
        }
        for filter in add_filters:
            for term in filter.get('terms', []):
                add_query["query"]["bool"]["must"].append({
                    "multi_match": {
                        "query": term,
                        "fields": ["body", "summary", "relevant_terms_array", "subject", "from", "to"],
                        "type": "cross_fields",
                        "boost": 2
                    }
                })
        # Ejecutar consultas
        start_time = datetime.now()
        es_results = es.search(index='email_index', body=es_query)
        total_results = es_results['hits']['total']['value']
        es_hits = es_results['hits']['hits']
        logger.info(f"Retrieved %d raw hits from ES in full mode (total: %d)", len(es_hits), total_results)  # Nuevo: Retrieval flow
        add_hits = []
        if add_filters:
            add_results = es.search(index='email_index', body=add_query)
            add_hits = add_results['hits']['hits']
            logger.info(f"Retrieved %d additional hits from add filters", len(add_hits))
        # Combinar resultados eliminando duplicados
        combined_hits = es_hits + [hit for hit in add_hits if hit['_id'] not in {hit['_id'] for hit in es_hits}]
        logger.info(f"Combined hits post-add: %d total raw docs", len(combined_hits))  # Nuevo: Post-combine
        # Procesar todos los resultados
        results = []
        for hit in combined_hits:  # Loop: no per-hit log, aggregate in extract/build
            explanation = hit['_explanation']
            total_score = hit['_score']
            components = extract_components(explanation)
            semantic_domain = hit['_source'].get('semantic_domain', 'desconocido')
          
            explanation_text = build_explanation(total_score, components, hit['_source'])
          
            results.append({
                'message_id': hit['_source']['message_id'],
                'index': hit['_source'].get('index', 'N/A'),
                'from': hit['_source'].get('from', 'N/A'),
                'to': hit['_source'].get('to', 'N/A'),
                'subject': hit['_source'].get('subject', ''),
                'date': hit['_source'].get('date', ''),
                'summary': hit['_source'].get('summary', 'Sin resumen'),
                'relevant_terms': hit['_source'].get('relevant_terms_array', []),
                'total_score': total_score,
                'explanation': explanation_text,
                'semantic_domain': semantic_domain
            })
        # Normalización sigmoide para relevancia
        scores = [email['total_score'] for email in results]
        mean_score = np.mean(scores) if scores else 0
        for email in results:  # Loop: no per-email log
            relevance = int(100 / (1 + np.exp(-0.5 * (email['total_score'] - mean_score))))
            email['relevance'] = relevance
        # Filtrar y ordenar por relevancia
        min_score_threshold = 1.0
        ranked_results = [email for email in results if email['relevance'] >= min_relevance and email['total_score'] >= min_score_threshold]
        ranked_results.sort(key=lambda x: x['relevance'], reverse=True)
        logger.info(f"Ranked results: %d docs post-relevance filter, avg relevance %.2f", len(ranked_results), np.mean([r['relevance'] for r in ranked_results]) if ranked_results else 0)  # Nuevo: Ranking flow
        # Generar all_email_ids a partir de ranked_results
        all_email_ids = [
            email['message_id'] if email['message_id'] != 'N/A' else email['index']
            for email in ranked_results
        ]
        # Aplicar paginación después de ordenar
        start = (page - 1) * results_per_page
        end = start + results_per_page
        paginated_results = ranked_results[start:end]
        total_filtered_results = len(ranked_results) # Total de resultados después de filtros
        # Actualizar conteos de filtros
        for filter in remove_filters:
            terms_key = ','.join(filter['terms']).lower()
            count_query = {
                "query": {
                    "bool": {
                        "must": base_query["query"]["bool"]["must"].copy(),
                        "filter": base_query["query"]["bool"]["filter"].copy(),
                        "should": base_query["query"]["bool"]["should"].copy(),
                        "must_not": base_query["query"]["bool"]["must_not"].copy(),
                        "minimum_should_match": base_query["query"]["bool"]["minimum_should_match"]
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
            count_result = es.count(index='email_index', body=count_query)
            filter_counts['remove'][terms_key] = count_result['count']
        for filter in add_filters:
            terms_key = ','.join(filter['terms']).lower()
            count_query = {
                "query": {
                    "bool": {
                        "must": [{"terms": {"mailbox_id": user_mailboxes}}],
                        "should": [],
                        "must_not": []
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
            count_result = es.count(index='email_index', body=count_query)
            filter_counts['add'][terms_key] = count_result['count']
        logger.info(f"Devolviendo %s correos relevantes de %s totales en %s segundos", len(paginated_results), total_filtered_results, (datetime.now() - start_time).total_seconds())
        logger.info("=== SEARCH FLOW END (Full Mode): %d results, avg relevance %.2f, in %.2fs ===", len(paginated_results), np.mean([r['relevance'] for r in paginated_results]) if paginated_results else 0, (datetime.now() - start_time).total_seconds())  # Nuevo: End full
        return {
            'results': paginated_results,
            'totalResults': total_filtered_results,
            'filter_counts': filter_counts,
            'all_email_ids': all_email_ids
        }
    except Exception as e:
        logger.error("Error al buscar correos: %s", str(e), exc_info=True)
        logger.info("=== SEARCH FLOW END: Exception - 0 results in %.2fs ===", (datetime.now() - start_time).total_seconds())  # Nuevo: End exception
        return {'results': [], 'totalResults': 0, 'filter_counts': {'remove': {}, 'add': {}}, 'all_email_ids': []}

def get_filter_emails(query_terms, filter, user, page=1, results_per_page=25):
    logger.info("Obteniendo correos para filtro: %s con términos de consulta: %s, user: %s, page: %s, results_per_page: %s",
                filter, query_terms, user.username if user else 'None', page, results_per_page)
    if not user:
        logger.error("Usuario no proporcionado para obtener correos de filtro")
        return {'results': [], 'totalResults': 0}
    user_mailboxes = [mailbox['mailbox_id'] for mailbox in user.mailboxes]
    if not user_mailboxes:
        logger.warning(f"No se encontraron buzones para el usuario: {user.username}")
        return {'results': [], 'totalResults': 0}
    terms = filter['terms']
    action = filter['action']
    es_query = {
        "query": {
            "bool": {
                "must": [],
                "filter": [{"terms": {"mailbox_id": user_mailboxes}}],
                "should": [],
                "must_not": []
            }
        },
        "size": min(results_per_page, 100),
        "from": (page - 1) * results_per_page
    }
    if action == 'remove':
        for term in terms:
            es_query["query"]["bool"]["must"].append({
                "multi_match": {
                    "query": term,
                    "fields": ["body", "summary", "relevant_terms_array", "subject", "from", "to"],
                    "type": "cross_fields"
                }
            })
    elif action == 'add':
        for term in terms:
            es_query["query"]["bool"]["must"].append({
                "multi_match": {
                    "query": term,
                    "fields": ["body", "summary", "relevant_terms_array", "subject", "from", "to"],
                    "type": "cross_fields"
                }
            })
        es_query["query"]["bool"]["minimum_should_match"] = 0
    try:
        start_time = datetime.now()
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Consulta para get_filter_emails: {json.dumps(es_query, indent=2)}")
        es_results = es.search(index='email_index', body=es_query)
        logger.info(f"Filter search completed: %d hits in %.2fs", len(es_results['hits']['hits']), (datetime.now() - start_time).total_seconds())  # Aggregate
        total_results = es_results['hits']['total']['value']
        hits = es_results['hits']['hits']
        results = []
        for hit in hits:  # Loop: minimal log
            source = hit['_source']
            index_value = source.get('index', 'N/A')
            message_id = source.get('message_id', 'N/A')
            if logger.isEnabledFor(logging.DEBUG) and message_id == 'N/A':
                logger.warning(f"Correo sin message_id válido: index={index_value}")
            if message_id == 'N/A':
                continue
            results.append({
                'index': str(index_value),
                'message_id': str(message_id),
                'date': source.get('date', ''),
                'from': source.get('from', 'N/A'),
                'to': source.get('to', 'N/A'),
                'subject': source.get('subject', ''),
                'description': source.get('summary', 'Sin resumen'),
                'relevant_terms': source.get('relevant_terms_array', [])
            })
        logger.info(f"Devolviendo {len(results)} correos de un total de {total_results} para el filtro {action}")
        return {'results': results, 'totalResults': total_results}
    except Exception as e:
        logger.error(f"Error al obtener correos para filtro: {str(e)}", exc_info=True)
        return {'results': [], 'totalResults': 0}
