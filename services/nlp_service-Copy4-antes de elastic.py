# Artifact ID: a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5
# Version: r0s1t2u3-v4w5-x6y7-z8a9-b0c1d2e3
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

def process_query(query, return_names=False):
    """Procesa una consulta en lenguaje natural y devuelve intención, términos, condiciones, embedding y opcionalmente nombres."""
    logger.info("Procesando consulta: %s, return_names=%s", query, return_names)
    query = query.lower().strip()
    if not query:
        logger.warning("Consulta vacía recibida")
        result = {"intent": "general", "terms": [], "conditions": {}}
        return (result, "general", [], None, []) if return_names else (result, "general", [], None)

    prompt = f"""
    Analiza la siguiente consulta en lenguaje natural y devuelve EXCLUSIVAMENTE un objeto JSON con:
    - "intent": La intención principal de la consulta (ejemplo: "ofertas_viaje", "inversiones", "medicina_y_salud", "general").
    - "terms": Lista de términos relevantes (palabras clave, nombres propios, conceptos).
    - "conditions": Diccionario con condiciones específicas (ejemplo: {{"precio_max": "100€"}}).
    - "names": Lista de nombres propios de personas (ejemplo: ["Teresa Goñi", "Juan Pérez"]).
    
    **Instrucciones**:
    1. Identifica la intención principal basándote en el propósito de la consulta.
    2. Extrae términos relevantes (nombres propios, palabras clave, conceptos específicos).
    3. Detecta condiciones explícitas (como precios, fechas, cantidades) y devuélvelas en "conditions".
    4. Identifica nombres propios de personas en "names", excluyendo nombres de lugares o empresas.
    5. Devuelve solo un objeto JSON válido, sin comentarios ni texto adicional.
    6. Ejemplo:
    {{
        "intent": "ofertas_viaje",
        "terms": ["viaje", "vuelo", "hotel"],
        "conditions": {{"precio_max": "100€"}},
        "names": ["Teresa Goñi"]
    }}

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
        names = result.get('names', [])
    except json.JSONDecodeError as e:
        logger.error("Error al parsear respuesta de Ollama: %s", str(e))
        intent = "general"
        terms = re.findall(r'\b\w+\b', query)
        conditions = {}
        names = []
    except Exception as e:
        logger.error("Error al procesar respuesta de Ollama: %s", str(e), exc_info=True)
        intent = "general"
        terms = re.findall(r'\b\w+\b', query)
        conditions = {}
        names = []

    # Post-process intent
    query_lower = query.lower()
    if any(word in query_lower for word in ["etoro", "inversion", "trading", "acciones"]):
        intent = "inversiones"
    elif any(word in query_lower for word in ["vuelo", "viaje", "hotel", "oferta"]):
        intent = "ofertas_viaje"
    elif any(word in query_lower for word in ["medicina", "medico", "salud", "farmacia"]):
        intent = "medicina_y_salud"

    # Post-process names with regex fallback
    if not names:
        # Match capitalized words, likely names (e.g., "Teresa Goñi")
        name_pattern = r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b'
        potential_names = re.findall(name_pattern, query)
        # Filter out known places/companies
        exclude = {'los angeles', 'tesla', 'ryanair', 'glovo'}
        names = [name for name in potential_names if name.lower() not in exclude]

    # Remove generic terms
    terms = [term for term in terms if term not in ['correos', 'correo', 'email', 'emails']]

    embedding = generate_embedding(query)
    if embedding is None:
        logger.warning("No se pudo generar embedding, usando búsqueda solo por texto")
        embedding = None

    logger.info("Consulta procesada: intent=%s, terms=%s, conditions=%s, names=%s", intent, terms, conditions, names)
    result = {"intent": intent, "terms": terms, "conditions": conditions}
    return (result, intent, terms, embedding, names) if return_names else (result, intent, terms, embedding)

def detect_language(text):
    """Detecta el idioma del texto proporcionado."""
    try:
        if not text or len(text.strip()) < 5:  # Si el texto es vacío o muy corto
            return 'es'  # Español por defecto
        return detect(text)
    except Exception as e:
        return 'es'  # Español por defecto en caso de error