import os
import pickle
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_FEEDBACK_COLLECTION, FEEDBACK_MODEL_PATH, FEEDBACK_MIN_SAMPLES
from sentence_transformers import SentenceTransformer
import numpy as np
import logging
from logging import handlers

# Configurar logging
logger = logging.getLogger('email_search_app.feedback_service')
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
logger.info("Conectando a MongoDB para feedback: %s", MONGO_URI)
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
feedback_collection = db[MONGO_FEEDBACK_COLLECTION]
logger.info("Conexión a MongoDB para feedback establecida")

# Cargar modelo de embeddings
logger.info("Cargando modelo de embeddings para feedback")
embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
logger.info("Modelo de embeddings para feedback cargado")

def load_relevance_model():
    logger.info("Cargando modelo de relevancia desde: %s", FEEDBACK_MODEL_PATH)
    if os.path.exists(FEEDBACK_MODEL_PATH):
        with open(FEEDBACK_MODEL_PATH, 'rb') as f:
            model = pickle.load(f)
            logger.debug("Modelo de relevancia cargado: %s", model)
            return model
    logger.debug("No se encontró modelo de relevancia, inicializando vacío")
    return {}

def save_relevance_model(model):
    logger.info("Guardando modelo de relevancia en: %s", FEEDBACK_MODEL_PATH)
    try:
        os.makedirs(os.path.dirname(FEEDBACK_MODEL_PATH), exist_ok=True)
        with open(FEEDBACK_MODEL_PATH, 'wb') as f:
            pickle.dump(model, f)
        logger.debug("Modelo de relevancia guardado")
    except Exception as e:
        logger.error("Error al guardar modelo de relevancia: %s", str(e), exc_info=True)

def save_feedback(query, message_id, is_relevant):
    """Guarda la retroalimentación del usuario en MongoDB."""
    logger.info("Guardando retroalimentación: query=%s, message_id=%s, is_relevant=%s", query, message_id, is_relevant)
    try:
        if not message_id:
            logger.error("message_id vacío o no proporcionado para retroalimentación")
            raise ValueError("message_id cannot be empty")
        feedback = {
            'query': query,
            'message_id': message_id,
            'is_relevant': is_relevant,
            'timestamp': {'$date': '2025-06-02T19:47:00Z'}  # Actualizar con fecha actual en producción
        }
        feedback_collection.insert_one(feedback)
        logger.debug("Retroalimentación guardada exitosamente: %s", feedback)
    except Exception as e:
        logger.error("Error al guardar retroalimentación: %s", str(e), exc_info=True)

def get_feedback_weights():
    logger.info("Obteniendo pesos de retroalimentación")
    model = load_relevance_model()
    logger.debug("Pesos de retroalimentación: %s", model)
    return model

def train_relevance_model():
    logger.info("Entrenando modelo de relevancia")
    try:
        feedback_count = feedback_collection.count_documents({})
        logger.debug("Número de retroalimentaciones: %s", feedback_count)
        if feedback_count < FEEDBACK_MIN_SAMPLES:
            logger.warning("No hay suficientes retroalimentaciones: %s/%s", feedback_count, FEEDBACK_MIN_SAMPLES)
            return

        from services.search_service import get_email_by_id
        feedbacks = feedback_collection.find()
        model = {}

        for feedback in feedbacks:
            if 'message_id' not in feedback:
                logger.warning("Feedback document lacks message_id: %s", feedback)
                continue
            message_id = feedback['message_id']
            is_relevant = feedback['is_relevant']
            
            email = get_email_by_id(message_id)
            if not email:
                logger.warning("Correo no encontrado para feedback: %s", message_id)
                continue

            weight = 0.5 if not is_relevant else 1.0
            model[message_id] = weight
            logger.debug("Asignado peso %s a message_id: %s", weight, message_id)

        save_relevance_model(model)
        logger.info("Modelo de relevancia reentrenado")
    except Exception as e:
        logger.error("Error al entrenar modelo de relevancia: %s", str(e), exc_info=True)