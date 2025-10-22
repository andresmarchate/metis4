import zlib
import numpy as np
from elasticsearch import Elasticsearch, helpers
from pymongo import MongoClient
import logging

# Configuración del logging
logging.basicConfig(filename='reindex.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Conexión a MongoDB
MONGO_URI = 'mongodb://localhost:27017'
MONGO_DB_NAME = 'email_database_metis2'
MONGO_EMAILS_COLLECTION = 'emails'

client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]

# Conexión a Elasticsearch
es = Elasticsearch([{'host': 'localhost', 'port': 9200, 'scheme': 'http'}])

def index_emails():
    """Reindexa todos los correos de MongoDB a Elasticsearch con los campos actualizados."""
    logging.info("Iniciando reindexación de correos...")
    emails = emails_collection.find()
    actions = []
    
    for email in emails:
        # Procesar el embedding (descomprimir desde Binary a lista de flotantes)
        embedding = email.get('embedding')
        if embedding:
            try:
                embedding = np.frombuffer(zlib.decompress(embedding), dtype=np.float32).tolist()
                if len(embedding) != 384:
                    logging.warning(f"Embedding de longitud incorrecta ({len(embedding)}) para message_id {email['message_id']}")
                    embedding = None
            except Exception as e:
                logging.error(f"Error al descomprimir embedding para message_id {email['message_id']}: {e}")
                embedding = None
        else:
            embedding = None

        # Documento para Elasticsearch con todos los campos del mapeo
        es_doc = {
            'message_id': email.get('message_id', ''),
            'mailbox_id': email.get('mailbox_id', ''),
            'body': email.get('body', ''),
            'summary': email.get('summary', ''),
            'relevant_terms_array': email.get('relevant_terms_array', []),
            'subject': email.get('subject', ''),
            'from': email.get('from', ''),
            'to': email.get('to', ''),
            'date': email.get('date', ''),
            'semantic_domain': email.get('semantic_domain', ''),
            'embedding': embedding
        }

        action = {
            "_index": "email_index",
            "_id": email.get('message_id'),
            "_source": es_doc
        }
        actions.append(action)

    # Indexación masiva
    try:
        helpers.bulk(es, actions)
        logging.info(f"Reindexados {len(actions)} correos con éxito.")
    except helpers.BulkIndexError as e:
        logging.error(f"{len(e.errors)} documentos fallaron al indexarse.")
        for error in e.errors:
            logging.error(f"Error en documento {error['index']['_id']}: {error['index']['error']}")

if __name__ == "__main__":
    index_emails()
