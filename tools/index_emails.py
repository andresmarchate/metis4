import elasticsearch
from sentence_transformers import SentenceTransformer
from pymongo import MongoClient
import logging
import numpy as np
import zlib

# Configuración del logging
logging.basicConfig(filename='index_emails.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Conexión a MongoDB
MONGO_URI = 'mongodb://localhost:27017'
MONGO_DB_NAME = 'email_database_metis2'
MONGO_EMAILS_COLLECTION = 'emails'

client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]

# Configuración de Elasticsearch
es = elasticsearch.Elasticsearch(["http://localhost:9200"])

# Cargar el modelo de embeddings
embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

INDEX_NAME = 'email_index'

# Definir el mapeo del índice
mapping = {
    "mappings": {
        "properties": {
            "message_id": {"type": "keyword"},
            "mailbox_id": {"type": "keyword"},
            "body": {"type": "text"},
            "subject": {"type": "text"},
            "from": {"type": "keyword"},
            "to": {"type": "keyword"},
            "date": {"type": "date"},
            "summary": {"type": "text"},
            "relevant_terms_array": {"type": "keyword"},
            "semantic_domain": {"type": "keyword"},
            "embedding": {
                "type": "dense_vector",
                "dims": 384
            }
        }
    }
}

# Crear el índice (se asume que se ha eliminado previamente con DELETE)
es.indices.create(index=INDEX_NAME, body=mapping)
logging.info(f"Índice {INDEX_NAME} creado con el mapeo actualizado.")

# Función para indexar todos los correos
def index_all_emails():
    logging.info("Iniciando indexación de todos los correos...")
    emails = emails_collection.find()
    for email in emails:
        try:
            # Obtener o generar embedding
            embedding = email.get('embedding')
            if embedding:
                embedding = np.frombuffer(zlib.decompress(embedding), dtype=np.float32).tolist()
            else:
                text = f"{email.get('subject', '')} {email.get('body', '')}"
                embedding = embedding_model.encode(text).tolist()

            # Documento para Elasticsearch
            es_doc = {
                'message_id': email.get('message_id', ''),
                'mailbox_id': email.get('mailbox_id', ''),
                'body': email.get('body', ''),
                'subject': email.get('subject', ''),
                'from': email.get('from', ''),
                'to': email.get('to', ''),
                'date': email.get('date', ''),
                'summary': email.get('summary', 'Sin resumen'),
                'relevant_terms_array': email.get('relevant_terms_array', []),
                'semantic_domain': email.get('semantic_domain', 'general'),
                'embedding': embedding
            }
            es.index(index=INDEX_NAME, id=email.get('message_id'), body=es_doc)
            logging.info(f"Indexado correo con message_id: {email.get('message_id')}")
        except Exception as e:
            logging.error(f"Error al indexar correo con message_id {email.get('message_id')}: {e}")

if __name__ == "__main__":
    index_all_emails()