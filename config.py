import os
from dotenv import load_dotenv

# Cargar variables de entorno desde un archivo .env
load_dotenv()

# Configuración de MongoDB
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'email_database_metis2')
MONGO_EMAILS_COLLECTION = 'emails'
MONGO_FEEDBACK_COLLECTION = 'feedback'
MONGO_TODOS_COLLECTION = 'agatta_todos'
MONGO_USERS_COLLECTION = 'users'

# Configuración de Redis (para caché)
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
CACHE_TTL = int(os.getenv('CACHE_TTL', 3600))  # Tiempo de vida del caché en segundos (1 hora)
SUMMARY_CACHE_TTL = int(os.getenv('SUMMARY_CACHE_TTL', 604800))  # TTL para resúmenes LLM (7 días)

# Configuración de Ollama (para el modelo mistral-custom)
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434/api/generate')
OLLAMA_MODEL = 'mistral-custom'
OLLAMA_TEMPERATURE = float(os.getenv('OLLAMA_TEMPERATURE', 0.7))
OLLAMA_MAX_TOKENS = int(os.getenv('OLLAMA_MAX_TOKENS', 512))
OLLAMA_CONTEXT_SIZE = int(os.getenv('OLLAMA_CONTEXT_SIZE', 32768))

# Configuración del modelo de embeddings
EMBEDDING_MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'

# Configuración del modelo de aprendizaje de refuerzo
FEEDBACK_MODEL_PATH = os.getenv('FEEDBACK_MODEL_PATH', './models/feedback_model.pkl')
FEEDBACK_MIN_SAMPLES = int(os.getenv('FEEDBACK_MIN_SAMPLES', 10))  # Mínimo de muestras para reentrenar

# Configuración de Flask
FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'your-secret-key')  # Cambiar en producción
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True') == 'True'

# Directorio para archivos estáticos y plantillas
STATIC_DIR = 'static'
TEMPLATES_DIR = 'templates'

# Configuración de Elasticsearch
ELASTICSEARCH_HOST = os.getenv('ELASTICSEARCH_HOST', 'localhost')
ELASTICSEARCH_PORT = int(os.getenv('ELASTICSEARCH_PORT', 9200))

# Configuración de índices de MongoDB (para referencia, no se crean aquí)
INDEXES = {
    'text_index': [
        ('from', 'text'),
        ('to', 'text'),
        ('subject', 'text'),
        ('body', 'text'),
        ('headers_text', 'text'),
        ('attachments', 'text'),
        ('attachments_content', 'text'),
        ('summary', 'text'),
        ('relevant_terms', 'text'),
        ('semantic_domain', 'text')
    ],
    'date_index': [('date', 1)],
    'message_id_1': [('message_id', 1)],
    'common_filters_index': [
        ('from', 1),
        ('to', 1),
        ('date', 1),
        ('semantic_domain', 1)
    ]
}