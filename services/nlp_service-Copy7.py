import hashlib
import json
import re
import requests
import zlib
import numpy as np
from sentence_transformers import SentenceTransformer
from config import OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TEMPERATURE, OLLAMA_MAX_TOKENS, OLLAMA_CONTEXT_SIZE, EMBEDDING_MODEL_NAME
import logging
from logging import handlers
import unicodedata
from langdetect import detect
from dateutil.parser import parse as date_parse
from dateutil.relativedelta import relativedelta
from datetime import datetime

# Configurar logging
logger = logging.getLogger('email_search_app.nlp_service')
logger.setLevel(logging.DEBUG)
file_handler = handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Cargar el modelo de embeddings
logger.info("Cargando modelo de embeddings: %s", EMBEDDING_MODEL_NAME)
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
logger.info("Modelo de embeddings cargado exitosamente")

# Caché en memoria para respuestas de Ollama
response_cache = {}
CACHE_LIMIT = 1000

# Diccionario dinámico de sinónimos expandido
SYNONYMS = {
    "reservas": ["booking", "reservations", "reservaciones", "reserva"],
    "viaje": ["trip", "travel", "journey", "vuelo"],
    "correos": ["emails", "messages", "mail"],
    "notaria": ["notary", "notario", "escribanía"],
    "abogado": ["lawyer", "attorney", "letrado"],
    "procurador": ["solicitor", "procurer", "representante"],
    "vivienda": ["housing", "home", "property", "inmueble"],
    "extincion": ["termination", "extinction", "cancelación"],
    "condominio": ["condominium", "co-ownership", "comunidad"],
    "juzgado": ["court", "tribunal", "juzgado"],
    "compra": ["purchase", "buy", "adquisición"],
    "venta": ["sale", "sell", "disposición"],
    "hipoteca": ["mortgage", "préstamo", "financiación"],
    "procedimiento": ["procedure", "proceso", "trámite"],
    "escritura": ["deed", "escritura", "documento"],
    "registro": ["registry", "registro", "inscripción"]
}

def normalize_text(text):
    """Normaliza el texto: convierte a minúsculas, elimina acentos y limpia caracteres especiales."""
    logger.debug("Normalizando texto: %s", text[:50] + '...' if len(text) > 50 else text)
    if not text or not isinstance(text, str):
        logger.warning("Texto inválido recibido para normalización")
        return ""
    try:
        text = text.lower()
        text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        logger.debug("Texto normalizado: %s", text[:50] + '...' if len(text) > 50 else text)
        return text
    except Exception as e:
        logger.error("Error al normalizar texto: %s", str(e), exc_info=True)
        return text

def call_ollama_api(prompt):
    """Llama a la API de Ollama para procesar el prompt."""
    logger.info("Llamando a la API de Ollama con prompt: %s", prompt[:50] + '...' if len(prompt) > 50 else prompt)
    prompt_hash = hashlib.md5(prompt.encode('utf-8')).hexdigest()
    
    if prompt_hash in response_cache:
        logger.debug("Respuesta obtenida del caché para prompt_hash: %s", prompt_hash)
        return response_cache[prompt_hash]

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "temperature": OLLAMA_TEMPERATURE,
        "num_predict": OLLAMA_MAX_TOKENS,
        "num_ctx": OLLAMA_CONTEXT_SIZE
    }

    try:
        logger.debug("Enviando solicitud a Ollama con payload: %s", payload)
        response = requests.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        result = response.json()['response']
        logger.debug("Respuesta de Ollama: %s", result[:100] + '...' if len(result) > 100 else result)
        
        if len(response_cache) >= CACHE_LIMIT:
            response_cache.pop(list(response_cache.keys())[0])
        response_cache[prompt_hash] = result
        logger.debug("Respuesta almacenada en caché para prompt_hash: %s", prompt_hash)
        return result
    except requests.RequestException as e:
        logger.error("Error al contactar con Ollama: %s", str(e), exc_info=True)
        return f"Error: {str(e)}"

def generate_embedding(text):
    """Genera un embedding comprimido para el texto proporcionado."""
    logger.info("Generando embedding para texto: %s", text[:50] + '...' if len(text) > 50 else text)
    if not text:
        logger.warning("Texto vacío recibido para generar embedding")
        return None
    try:
        embedding = embedding_model.encode(text).tolist()
        compressed_embedding = zlib.compress(np.array(embedding, dtype=np.float32).tobytes())
        logger.debug("Embedding generado y comprimido")
        return compressed_embedding
    except Exception as e:
        logger.error("Error al generar embedding: %s", str(e), exc_info=True)
        return None

def decompress_embedding(compressed_embedding):
    """Descomprime un embedding comprimido y lo convierte en un array numérico."""
    logger.debug("Descomprimiendo embedding")
    try:
        decompressed = zlib.decompress(compressed_embedding)
        embedding = np.frombuffer(decompressed, dtype=np.float32)
        logger.debug("Embedding descomprimido correctamente, longitud: %d", len(embedding))
        return embedding
    except Exception as e:
        logger.error("Error al descomprimir embedding: %s", str(e), exc_info=True)
        return None

def extract_temporal_entities(query):
    """Extrae entidades temporales y distingue entre fechas de cabecera y cuerpo."""
    logger.debug("Extrayendo entidades temporales de: %s", query)
    try:
        date_patterns = [
            r"(?:desde|hasta|en|recibido\s*en|enviado\s*en)\s*(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s*(\d{4})",
            r"(?:desde|hasta|en|recibido\s*en|enviado\s*en)\s*(\d{1,2})\s*(de)?\s*(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s*(de)?\s*(\d{4})",
            r"fecha\s*(\d{1,2})[-/\s](\d{1,2})[-/\s](\d{4})"  # Para fechas mencionadas en el cuerpo
        ]
        months = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
            "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
        }
        header_ranges = {"start": None, "end": None}
        body_dates = []

        for pattern in date_patterns:
            for match in re.finditer(pattern, query.lower()):
                if any(k in query.lower() for k in ["recibido en", "enviado en", "desde", "hasta"]):
                    # Fechas de cabecera
                    if "desde" in query.lower():
                        if len(match.groups()) == 2:  # Mes y año
                            month, year = match.groups()
                            header_ranges["start"] = f"{year}-{months[month]:02d}-01"
                        elif len(match.groups()) == 5:  # Día, mes, año
                            day, _, month, _, year = match.groups()
                            header_ranges["start"] = f"{year}-{months[month]:02d}-{int(day):02d}"
                    elif "hasta" in query.lower():
                        if len(match.groups()) == 2:
                            month, year = match.groups()
                            dt = datetime.strptime(f"{year}-{months[month]:02d}-01", "%Y-%m-%d")
                            header_ranges["end"] = (dt + relativedelta(months=1) - relativedelta(days=1)).strftime("%Y-%m-%d")
                        elif len(match.groups()) == 5:
                            day, _, month, _, year = match.groups()
                            header_ranges["end"] = f"{year}-{months[month]:02d}-{int(day):02d}"
                    else:  # "recibido en" o "enviado en"
                        if len(match.groups()) == 2:
                            month, year = match.groups()
                            header_ranges["start"] = f"{year}-{months[month]:02d}-01"
                            header_ranges["end"] = (datetime.strptime(header_ranges["start"], "%Y-%m-%d") + relativedelta(months=1) - relativedelta(days=1)).strftime("%Y-%m-%d")
                        elif len(match.groups()) == 5:
                            day, _, month, _, year = match.groups()
                            date_str = f"{year}-{months[month]:02d}-{int(day):02d}"
                            header_ranges["start"] = date_str
                            header_ranges["end"] = date_str
                else:
                    # Fechas en el cuerpo
                    if len(match.groups()) == 3:  # Día, mes, año numérico
                        day, month, year = match.groups()
                        body_dates.append(f"{year}-{int(month):02d}-{int(day):02d}")
                    elif len(match.groups()) == 5:
                        day, _, month, _, year = match.groups()
                        body_dates.append(f"{year}-{months[month]:02d}-{int(day):02d}")
                    elif len(match.groups()) == 2:
                        month, year = match.groups()
                        body_dates.append(f"{year}-{months[month]:02d}-01")

        if not header_ranges["end"] and header_ranges["start"]:
            header_ranges["end"] = datetime.now().strftime("%Y-%m-%d")
        logger.debug("Entidades temporales extraídas - Cabecera: %s, Cuerpo: %s", header_ranges, body_dates)
        return header_ranges, body_dates
    except Exception as e:
        logger.error("Error al extraer entidades temporales: %s", str(e), exc_info=True)
        return {"start": None, "end": None}, []

def extract_sender_recipient(query):
    """Extrae remitente y destinatario con soporte para nombres y direcciones de correo."""
    sender_patterns = [
        r"correo\s*(enviado\s*por|de)\s+([\w\s]+(?:@[\w\.-]+)?)",  # "correo enviado por Juan" o "correo de juan@example.com"
        r"enviado\s*por\s+([\w\s]+(?:@[\w\.-]+)?)"
    ]
    recipient_patterns = [
        r"correo\s*(recibido\s*por|para)\s+([\w\s]+(?:@[\w\.-]+)?)",  # "correo recibido por Juan" o "correo para juan@example.com"
        r"recibido\s*por\s+([\w\s]+(?:@[\w\.-]+)?)"
    ]
    
    sender = None
    recipient = None
    
    for pattern in sender_patterns:
        match = re.search(pattern, query.lower())
        if match:
            sender = match.group(2).strip()
            break
    
    for pattern in recipient_patterns:
        match = re.search(pattern, query.lower())
        if match:
            recipient = match.group(2).strip()
            break
    
    # Extraer email si está presente, o dejar como nombre
    sender_email = re.search(r'[\w\.-]+@[\w\.-]+', sender) if sender else None
    sender = sender_email.group(0) if sender_email else sender
    recipient_email = re.search(r'[\w\.-]+@[\w\.-]+', recipient) if recipient else None
    recipient = recipient_email.group(0) if recipient_email else recipient
    
    logger.debug(f"Extracted sender: {sender}, recipient: {recipient}")
    return sender, recipient

def expand_terms(terms):
    """Expande cada término con sus sinónimos, devolviendo una lista de listas."""
    expanded_groups = []
    for term in terms:
        synonyms = SYNONYMS.get(term.lower(), [])
        group = [term] + synonyms
        expanded_groups.append(group)
    logger.debug("Grupos de términos expandidos: %s", expanded_groups)
    return expanded_groups

def process_query(query, return_names=False):
    """Procesa una consulta en lenguaje natural y devuelve intención, grupos de términos, condiciones, embedding y opcionalmente nombres."""
    logger.info("Procesando consulta: %s, return_names=%s", query, return_names)
    query = query.lower().strip()
    if not query:
        logger.warning("Consulta vacía recibida")
        result = {"intent": "general", "term_groups": [], "conditions": {}, "metadata_filters": {}}
        return (result, "general", [], None, []) if return_names else (result, "general", [], None)

    prompt = f"""
    Analiza la siguiente consulta en lenguaje natural y devuelve EXCLUSIVAMENTE un objeto JSON con:
    - "intent": La intención principal (ejemplo: "ofertas_viaje", "informacion_juridica", "negociaciones_inmobiliarias", "general").
    - "terms": Lista de términos relevantes (palabras clave, nombres propios, conceptos).
    - "conditions": Diccionario con condiciones específicas (ejemplo: {{"estado": "abiertos"}}).
    - "metadata_filters": Diccionario con filtros de metadatos (ejemplo: {{"from": "juan@example.com", "to": "maria@example.com", "date_range": {{"start": "2025-01-01", "end": "2025-12-31"}}}}).
    - "names": Lista de nombres propios de personas.

    **Instrucciones**:
    1. Identifica la intención: "ofertas_viaje" para viajes/reservas, "informacion_juridica" para temas legales (juzgados, abogados, procedimientos), "negociaciones_inmobiliarias" para bienes raíces (compra, venta, condominio, extinción).
    2. Extrae términos relevantes (no los expandas aquí).
    3. Detecta condiciones explícitas (fechas, estados) y refléjalas en "conditions" o "metadata_filters".
    4. Identifica filtros como "from" (remitente), "to" (destinatario), "subject", y rangos de fechas en "metadata_filters".
    5. Extrae nombres propios de personas en "names".
    6. Devuelve solo JSON válido, sin comentarios.

    Consulta:
    {query}
    """

    response = call_ollama_api(prompt)
    try:
        cleaned_response = response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:].strip()
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3].strip()
        result = json.loads(cleaned_response)
        
        intent = result.get('intent', 'general')
        terms = result.get('terms', [])
        conditions = result.get('conditions', {})
        metadata_filters = result.get('metadata_filters', {})
        names = result.get('names', [])
    except json.JSONDecodeError as e:
        logger.error("Error al parsear respuesta de Ollama: %s", str(e))
        intent = "general"
        terms = re.findall(r'\b\w+\b', query)
        conditions = {}
        metadata_filters = {}
        names = []
    except Exception as e:
        logger.error("Error al procesar respuesta de Ollama: %s", str(e), exc_info=True)
        intent = "general"
        terms = re.findall(r'\b\w+\b', query)
        conditions = {}
        metadata_filters = {}
        names = []

    # Post-procesamiento para intención: más restrictivo
    if any(word in query for word in ["viaje", "reserva", "vuelo"]):
        intent = "ofertas_viaje"
    elif any(word in query for word in ["juzgado", "abogado", "notaria", "procurador", "procedimiento"]):
        intent = "informacion_juridica"
    elif "extincion" in query and any(word in query for word in ["condominio", "vivienda", "inmueble", "compra", "venta", "hipoteca"]):
        intent = "negociaciones_inmobiliarias"

    # Extracción de entidades temporales
    header_ranges, body_dates = extract_temporal_entities(query)
    if header_ranges["start"] or header_ranges["end"]:
        metadata_filters["date_range"] = {
            "start": header_ranges["start"] or "1970-01-01",
            "end": header_ranges["end"] or datetime.now().strftime("%Y-%m-%d")
        }
    if body_dates:
        terms.extend(body_dates)  # Añadir fechas del cuerpo como términos de búsqueda

    # Extracción de remitente y destinatario
    sender, recipient = extract_sender_recipient(query)
    if sender:
        metadata_filters["from"] = sender
    if recipient:
        metadata_filters["to"] = recipient

    # Expansión de términos con sinónimos como grupos
    term_groups = expand_terms(terms)

    # Post-procesamiento de nombres
    if not names:
        name_pattern = r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b'
        potential_names = re.findall(name_pattern, query)
        exclude = {'los angeles', 'tesla', 'ryanair', 'glovo', 'milán', 'campanilla'}
        names = [name for name in potential_names if name.lower() not in exclude]

    # Eliminar términos genéricos
    term_groups = [[term for term in group if term not in ['correos', 'correo', 'email', 'emails']] for group in term_groups]

    embedding = generate_embedding(query)
    if embedding is None:
        logger.warning("No se pudo generar embedding, usando búsqueda solo por texto")
        embedding = None

    logger.info("Consulta procesada: intent=%s, term_groups=%s, conditions=%s, metadata_filters=%s, names=%s", intent, term_groups, conditions, metadata_filters, names)
    result = {"intent": intent, "term_groups": term_groups, "conditions": conditions, "metadata_filters": metadata_filters}
    return (result, intent, term_groups, embedding, names) if return_names else (result, intent, term_groups, embedding)

def detect_language(text):
    """Detecta el idioma del texto proporcionado."""
    try:
        if not text or len(text.strip()) < 5:
            return 'es'
        return detect(text)
    except Exception as e:
        return 'es'