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

def call_ollama_api(prompt):
    """Llama a la API de Ollama para procesar el prompt."""
    logger.info("Llamando a la API de Ollama con prompt: %s", prompt[:50] + '...' if len(prompt) > 50 else prompt)
    prompt_hash = hashlib.md5(prompt.encode('utf-8')).hexdigest()
    
    # Verificar caché
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
        
        # Almacenar en caché
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

def process_query(query):
    """Procesa una consulta en lenguaje natural y devuelve la intención, términos relevantes y embedding."""
    logger.info("Procesando consulta: %s", query)
    query = query.lower().strip()
    if not query:
        logger.warning("Consulta vacía recibida")
        return {"intent": "general", "terms": [], "embedding": None}

    prompt = f"""
    Analiza la siguiente consulta en lenguaje natural y devuelve EXCLUSIVAMENTE un objeto JSON con:
    - "intent": La intención principal de la consulta (ejemplo: "estado_proyecto", "ofertas_viaje", "general").
    - "terms": Lista de términos relevantes (palabras clave, nombres propios, conceptos).
    - "conditions": Diccionario con condiciones específicas (ejemplo: {{"precio_max": "100€"}}).
    
    **Instrucciones**:
    1. Identifica la intención principal basándote en el propósito de la consulta.
    2. Extrae términos relevantes (nombres propios, palabras clave, conceptos específicos).
    3. Detecta condiciones explícitas (como precios, fechas, cantidades) y devuélvelas en "conditions".
    4. Devuelve solo un objeto JSON válido, sin comentarios ni texto adicional.
    5. Ejemplo:
    {{
        "intent": "ofertas_viaje",
        "terms": ["viaje", "vuelo", "hotel"],
        "conditions": {{"precio_max": "100€"}}
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
        
        embedding = generate_embedding(query)
        
        logger.info("Consulta procesada: intent=%s, terms=%s, conditions=%s", intent, terms, conditions)
        return {
            "intent": intent,
            "terms": terms,
            "conditions": conditions,
            "embedding": embedding
        }
    except json.JSONDecodeError as e:
        logger.error("Error al parsear respuesta de Ollama: %s", str(e), exc_info=True)
        return {
            "intent": "general",
            "terms": re.findall(r'\b\w+\b', query),
            "conditions": {},
            "embedding": generate_embedding(query)
        }
    except Exception as e:
        logger.error("Error al procesar consulta: %s", str(e), exc_info=True)
        return {"intent": "general", "terms": [], "conditions": {}, "embedding": None}