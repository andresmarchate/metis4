import redis
import json
import logging
from logging import handlers
from config import REDIS_HOST, REDIS_PORT, REDIS_DB, CACHE_TTL

# Configurar logging
logger = logging.getLogger('email_search_app.cache_service')
logger.setLevel(logging.DEBUG)
file_handler = handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Conectar a Redis
logger.info("Conectando a Redis: %s:%s", REDIS_HOST, REDIS_PORT)
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
logger.info("Conexión a Redis establecida")

def get_cached_result(query_hash):
    logger.info("Buscando en caché para query_hash: %s", query_hash)
    try:
        cached = redis_client.get(query_hash)
        if cached:
            logger.debug("Resultado encontrado en caché: %s", query_hash)
            return json.loads(cached)
        logger.debug("No se encontró resultado en caché para: %s", query_hash)
        return None
    except redis.RedisError as e:
        logger.error("Error al acceder al caché: %s", str(e), exc_info=True)
        return None

def cache_result(query_hash, result):
    logger.info("Almacenando resultado en caché para query_hash: %s", query_hash)
    try:
        redis_client.setex(query_hash, CACHE_TTL, json.dumps(result))
        logger.debug("Resultado almacenado en caché")
    except redis.RedisError as e:
        logger.error("Error al guardar en caché: %s", str(e), exc_info=True)