import elasticsearch
from sentence_transformers import SentenceTransformer
import numpy as np

# Configuración de Elasticsearch
es = elasticsearch.Elasticsearch(["http://localhost:9200"])

#embedding_model = SentenceTransformer('all-MiniLM-L6-v2')  # Ejemplo, ajusta según tu modelo
embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')  # Ejemplo, ajusta según tu modelo

INDEX_NAME = 'email_index'

# Definir el mapeo del índice con 'embedding' como dense_vector
mapping = {
    "mappings": {
        "properties": {
            "message_id": {"type": "keyword"},
            "body": {"type": "text"},
            "subject": {"type": "text"},
            "from": {"type": "keyword"},
            "embedding": {
                "type": "dense_vector",
                "dims": 384  # Ajusta según las dimensiones de tu modelo (e.g., 384 para MiniLM)
            }
        }
    }
}

# Crear el índice si no existe
if not es.indices.exists(index=INDEX_NAME):
    es.indices.create(index=INDEX_NAME, body=mapping)

# Función para indexar correos
def index_email(email):
    embedding = embedding_model.encode(email['body']).tolist()  # Convertir a lista de floats
    doc = {
        'message_id': email['message_id'],
        'body': email['body'],
        'subject': email.get('subject', ''),
        'from': email.get('from', ''),
        'embedding': embedding  # Almacenar como lista de floats
    }
    es.index(index=INDEX_NAME, id=email['message_id'], body=doc)

# Ejemplo de uso
emails = [
    {'message_id': '1', 'body': 'Negociación con Ana Guerrero sobre precio de venta de la casa', 'from': 'Ana Guerrero'}
]
for email in emails:
    index_email(email)
