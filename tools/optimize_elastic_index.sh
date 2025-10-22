#!/bin/bash

# Paso 1: Verificar que Elasticsearch está corriendo
echo "Verificando que Elasticsearch esté corriendo en localhost:9200..."
curl -s -X GET "http://localhost:9200" > /dev/null
if [ $? -ne 0 ]; then
    echo "Error: Elasticsearch no está corriendo en localhost:9200. Inícialo primero."
    exit 1
fi
echo "Elasticsearch está activo."

# Paso 2: Eliminar el índice existente (opcional, cuidado con los datos)
echo "Eliminando el índice 'email_index' existente (si existe)..."
curl -X DELETE "http://localhost:9200/email_index"
echo "Índice eliminado o no existía."

# Paso 3: Crear el nuevo índice con el analizador en español
echo "Creando el nuevo índice 'email_index' con analizador en español..."
curl -X PUT "http://localhost:9200/email_index" -H 'Content-Type: application/json' -d'
{
  "settings": {
    "analysis": {
      "analyzer": {
        "spanish_analyzer": {
          "type": "spanish",
          "stopwords": "_spanish_"
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "body": {"type": "text", "analyzer": "spanish_analyzer"},
      "summary": {"type": "text", "analyzer": "spanish_analyzer"},
      "subject": {"type": "text", "analyzer": "spanish_analyzer"},
      "relevant_terms_array": {"type": "text", "analyzer": "spanish_analyzer"},
      "semantic_domain": {"type": "keyword"},
      "mailbox_id": {"type": "keyword"},
      "message_id": {"type": "keyword"},
      "embedding": {"type": "dense_vector", "dims": 768}
    }
  }
}'
echo "Índice creado con éxito."

# Paso 4: Verificar que el índice se creó correctamente
echo "Verificando la creación del índice..."
curl -s -X GET "http://localhost:9200/email_index/_settings" > /dev/null
if [ $? -eq 0 ]; then
    echo "El índice 'email_index' se creó correctamente."
else
    echo "Error: No se pudo crear el índice. Revisa los logs de Elasticsearch."
    exit 1
fi

echo "Optimización completada. Ahora necesitas reindexar los datos desde MongoDB."
