import sys
import requests
import json
from tabulate import tabulate
from config import FLASK_DEBUG
import logging
from logging import handlers

# Configurar logging
logger = logging.getLogger('email_search_app.cli')
logger.setLevel(logging.DEBUG)
file_handler = handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# URL del servidor Flask
API_URL = 'http://localhost:5000/api/search'

def search_emails(query):
    logger.info("Ejecutando consulta desde CLI: %s", query)
    try:
        response = requests.post(API_URL, json={'query': query})
        response.raise_for_status()
        results = response.json()
        logger.debug("Resultados recibidos: %s", results)

        if not results:
            logger.info("No se encontraron resultados para la consulta")
            print("No se encontraron resultados.")
            return

        table = [
            [
                r['index'],
                r['message_id'][:8] + '...',
                r['date'],
                r['from'],
                r['to'],
                r['subject'],
                r['description'][:50] + ('...' if len(r['description']) > 50 else ''),
                ', '.join(r['relevant_terms']),
                r['relevance'],
                r['explanation']
            ] for r in results
        ]

        headers = ['Índice', 'ID', 'Fecha', 'Remitente', 'Destinatario', 'Asunto', 'Descripción', 'Términos', 'Relevancia', 'Explicación']
        print(tabulate(table, headers=headers, tablefmt='grid'))
        logger.info("Resultados mostrados en formato tabular")
    except requests.RequestException as e:
        logger.error("Error al conectar con el servidor: %s", str(e), exc_info=True)
        print(f"Error al conectar con el servidor: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error("Error al procesar la respuesta: %s", str(e), exc_info=True)
        print(f"Error al procesar la respuesta: {str(e)}")

if __name__ == '__main__':
    logger.info("Iniciando ejecución de CLI")
    if len(sys.argv) < 2:
        logger.error("Uso incorrecto: se requiere una consulta")
        print("Uso: python cli.py \"consulta\"")
        sys.exit(1)
    
    query = ' '.join(sys.argv[1:])
    search_emails(query)
    logger.info("Finalizando ejecución de CLI")