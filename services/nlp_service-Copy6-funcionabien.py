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

# Diccionario dinámico de sinónimos (ejemplo básico, puede expandirse)
SYNONYMS = {
    "reservas": ["booking", "reservations", "reservaciones"],
    "viaje": ["trip", "travel", "journey"],
    "correos": ["emails", "messages", "mail"],
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

def extract_temporal_entities(query):
    """Extrae entidades temporales de la consulta y las convierte a formato ISO 8601."""
    logger.debug("Extrayendo entidades temporales de: %s", query)
    try:
        date_patterns = [
            r"(?:desde|hasta|en)\s*(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s*(\d{4})",
            r"(?:desde|hasta|en)\s*(\d{1,2})\s*(de)?\s*(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s*(de)?\s*(\d{4})",
        ]
        months = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
            "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
        }
        ranges = {"start": None, "end": None}
        
        for pattern in date_patterns:
            for match in re.finditer(pattern, query.lower()):
                if "desde" in query.lower():
                    if len(match.groups()) == 2:  # Mes y año
                        month, year = match.groups()
                        ranges["start"] = f"{year}-{months[month]:02d}-01"
                    elif len(match.groups()) == 5:  # Día, mes, año
                        day, _, month, _, year = match.groups()
                        ranges["start"] = f"{year}-{months[month]:02d}-{int(day):02d}"
                elif "hasta" in query.lower():
                    if len(match.groups()) == 2:
                        month, year = match.groups()
                        dt = datetime.strptime(f"{year}-{months[month]:02d}-01", "%Y-%m-%d")
                        ranges["end"] = (dt + relativedelta(months=1) - relativedelta(days=1)).strftime("%Y-%m-%d")
                    elif len(match.groups()) == 5:
                        day, _, month, _, year = match.groups()
                        ranges["end"] = f"{year}-{months[month]:02d}-{int(day):02d}"
                else:  # Sin "desde" ni "hasta", asumimos evento
                    if len(match.groups()) == 2:
                        month, year = match.groups()
                        ranges["start"] = f"{year}-{months[month]:02d}-01"
                        ranges["end"] = (datetime.strptime(ranges["start"], "%Y-%m-%d") + relativedelta(months=1) - relativedelta(days=1)).strftime("%Y-%m-%d")
        
        if not ranges["end"] and ranges["start"]:
            ranges["end"] = datetime.now().strftime("%Y-%m-%d")
        logger.debug("Entidades temporales extraídas: %s", ranges)
        return ranges
    except Exception as e:
        logger.error("Error al extraer entidades temporales: %s", str(e), exc_info=True)
        return {"start": None, "end": None}

def expand_terms(terms):
    """Expande términos con sinónimos."""
    expanded = set(terms)
    for term in terms:
        synonyms = SYNONYMS.get(term.lower(), [])
        expanded.update(synonyms)
    logger.debug("Términos expandidos: %s", expanded)
    return list(expanded)

def process_query(query, return_names=False):
    """Procesa una consulta en lenguaje natural y devuelve intención, términos, condiciones, embedding y opcionalmente nombres."""
    logger.info("Procesando consulta: %s, return_names=%s", query, return_names)
    query = query.lower().strip()
    if not query:
        logger.warning("Consulta vacía recibida")
        result = {"intent": "general", "terms": [], "conditions": {}, "metadata_filters": {}}
        return (result, "general", [], None, []) if return_names else (result, "general", [], None)

    prompt = f"""
    Analiza la siguiente consulta en lenguaje natural y devuelve EXCLUSIVAMENTE un objeto JSON con:
    - "intent": La intención principal (ejemplo: "ofertas_viaje", "general"). Para consultas sobre viajes, usa "ofertas_viaje".
    - "terms": Lista de términos relevantes (palabras clave, nombres propios, conceptos).
    - "conditions": Diccionario con condiciones específicas (ejemplo: {{"estado": "abiertos"}}).
    - "metadata_filters": Diccionario con filtros de metadatos (ejemplo: {{"from": "Juan", "date_range": {{"start": "2025-02-01", "end": "2025-05-31"}}}}).
    - "names": Lista de nombres propios de personas.

    **Instrucciones**:
    1. Identifica la intención basándote en el propósito. Usa "ofertas_viaje" para temas de viajes/reservas.
    2. Extrae términos relevantes y no los expandas aquí (se hará después).
    3. Detecta condiciones explícitas (fechas, estados) y refléjalas en "conditions" o "metadata_filters".
    4. Identifica filtros como "from", "to", "subject", y rangos de fechas en "metadata_filters".
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

    # Post-procesamiento
    if "viaje" in query or "reserva" in query:
        intent = "ofertas_viaje"
    
    # Extracción de entidades temporales
    temporal_ranges = extract_temporal_entities(query)
    if temporal_ranges["start"] or temporal_ranges["end"]:
        metadata_filters["date_range"] = {
            "start": temporal_ranges["start"] or "1970-01-01",
            "end": temporal_ranges["end"] or datetime.now().strftime("%Y-%m-%d")
        }

    # Expansión de términos con sinónimos
    terms = expand_terms(terms)

    # Post-procesamiento de nombres
    if not names:
        name_pattern = r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b'
        potential_names = re.findall(name_pattern, query)
        exclude = {'los angeles', 'tesla', 'ryanair', 'glovo', 'milán'}
        names = [name for name in potential_names if name.lower() not in exclude]

    # Eliminar términos genéricos
    terms = [term for term in terms if term not in ['correos', 'correo', 'email', 'emails']]

    embedding = generate_embedding(query)
    if embedding is None:
        logger.warning("No se pudo generar embedding, usando búsqueda solo por texto")
        embedding = None

    logger.info("Consulta procesada: intent=%s, terms=%s, conditions=%s, metadata_filters=%s, names=%s", intent, terms, conditions, metadata_filters, names)
    result = {"intent": intent, "terms": terms, "conditions": conditions, "metadata_filters": metadata_filters}
    return (result, intent, terms, embedding, names) if return_names else (result, intent, terms, embedding)

def detect_language(text):
    """Detecta el idioma del texto proporcionado."""
    try:
        if not text or len(text.strip()) < 5:
            return 'es'
        return detect(text)
    except Exception as e:
        return 'es'