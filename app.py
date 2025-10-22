import logging
from logging import handlers
from flask import Flask, request, jsonify, render_template, send_file, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from services.search_service import search_emails, get_email_by_id, submit_bulk_feedback, get_email_addresses, get_conversation_emails, get_filter_emails
from services.nlp_service import process_query
from services.feedback_service import save_feedback, train_relevance_model
from services.cache_service import get_cached_result, cache_result, clear_cache
from services.analysis_service import analyze_themes
from services.deep_analysis_service import initialize_deep_analysis, process_deep_analysis_prompt, reset_deep_analysis_context
from services.deep_conversation_analysis_service import DeepConversationAnalysisService
from services.dashboard_service import get_dashboard_metrics, get_email_list, get_thread_emails
from services.user_service import get_user_data, add_mailbox, change_password, update_agatta_config
from services.threads_service import analyze_threads, export_threads, process_feedback
from services.agatta_service import get_agatta_stats, mark_task_completed, create_draft, get_draft_count, get_outbox_count, get_draft_emails, get_outbox_emails, get_gmail_service
from services.dashboard_service import get_agatta_todos
import hashlib
import uuid
import json
from io import BytesIO
import subprocess

logger = logging.getLogger('email_search_app')
logger.setLevel(logging.DEBUG)

file_handler = handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))

logger.handlers = []
logger.addHandler(file_handler)
logger.addHandler(console_handler)

for name in logging.root.manager.loggerDict:
    if name.startswith('email_search_app'):
        child_logger = logging.getLogger(name)
        child_logger.handlers = []
        child_logger.addHandler(file_handler)
        child_logger.addHandler(console_handler)

logger.info("Iniciando aplicación Flask...")

app = Flask(__name__, template_folder='templates')
app.secret_key = 'your-secret-key'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

bcrypt = Bcrypt(app)

from config import MONGO_URI, MONGO_DB_NAME
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
users_collection = db['users']
themes_collection = db['themes']
emails_collection = db['emails']

class User(UserMixin):
    def __init__(self, username, password_hash, mailboxes):
        self.username = username
        self.password_hash = password_hash
        self.mailboxes = mailboxes

    def get_id(self):
        return self.username

@login_manager.user_loader
def load_user(username):
    user_data = users_collection.find_one({"username": username})
    if user_data:
        return User(user_data['username'], user_data['password_hash'], user_data.get('mailboxes', []))
    return None

deep_conversation_service = DeepConversationAnalysisService()

@app.route('/')
def index():
    logger.info("Accediendo a la página principal")
    try:
        if current_user.is_authenticated:
            return render_template('index.html')
        return redirect(url_for('login'))
    except Exception as e:
        logger.error(f"Error rendering index page: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_data = users_collection.find_one({"username": username})
        if user_data and bcrypt.check_password_hash(user_data['password_hash'], password):
            user = User(user_data['username'], user_data['password_hash'], user_data.get('mailboxes', []))
            login_user(user)
            flash('Inicio de sesión exitoso')
            return redirect(url_for('index'))
        flash('Credenciales inválidas')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if users_collection.find_one({"username": username}):
            flash('El usuario ya existe')
            return redirect(url_for('register'))
        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        users_collection.insert_one({"username": username, "password_hash": password_hash, "mailboxes": []})
        flash('Usuario registrado exitosamente')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada')
    return redirect(url_for('login'))

@app.route('/api/search', methods=['POST'])
@login_required
def search():
    logger.info("Procesando solicitud de búsqueda en /api/search")
    try:
        data = request.get_json()
        logger.debug(f"Datos recibidos: {data}")
        query = data.get('query', '').strip()
        min_relevance = data.get('minRelevance', 10)
        page = data.get('page', 1)
        results_per_page = int(data.get('resultsPerPage', 25))
        clear_cache_flag = data.get('clearCache', False)
        filters = data.get('filters', [])

        if not query:
            logger.warning("Consulta vacía recibida")
            return jsonify({'error': 'Consulta vacía'}), 400

        cache_key = f"{current_user.username}:{query}:{min_relevance}:{page}:{results_per_page}:{str(filters)}"
        query_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
        logger.debug(f"Query hash generado: {query_hash}")

        if clear_cache_flag:
            logger.info(f"Limpiando caché para query_hash: {query_hash}")
            clear_cache(query_hash)
            theme_cache_key = f"{current_user.username}:themes:{hashlib.md5(query.encode('utf-8')).hexdigest()}"
            clear_cache(theme_cache_key)
            logger.info(f"Limpiando caché de temas para query_hash: {theme_cache_key}")

        cached_result = get_cached_result(query_hash)
        if cached_result and not clear_cache_flag:
            logger.info(f"Resultado obtenido del caché para query_hash: {query_hash}")
            return jsonify(cached_result)

        logger.debug(f"Procesando consulta con NLP: {query}")
        processed_query, intent, term_groups, embedding = process_query(query)
        logger.debug(f"Resultado del procesamiento NLP: processed_query={processed_query}, intent={intent}, term_groups={term_groups}")

        logger.debug(f"Buscando correos para intent: {intent}, term_groups: {term_groups}")
        results = search_emails(
            processed_query=processed_query,
            intent=intent,
            term_groups=term_groups,
            query_embedding=embedding,
            min_relevance=min_relevance,
            page=page,
            results_per_page=results_per_page,
            filters=filters,
            user=current_user,
            get_all_ids=True
        )
        logger.info(f"Encontrados {len(results['results'])} correos relevantes de {results['totalResults']} totales")

        normalized_filter_counts = {'add': {}, 'remove': {}}
        for action in ['add', 'remove']:
            for terms_key, count in results['filter_counts'].get(action, {}).items():
                normalized_key = ','.join(term.lower().strip() for term in terms_key.split(','))
                normalized_filter_counts[action][normalized_key] = count
                logger.debug(f"Normalizando términos para acción '{action}': {terms_key} -> {normalized_key}")
        logger.debug(f"Normalized filter_counts: {normalized_filter_counts}")

        response_data = {
            'results': results['results'],
            'totalResults': results['totalResults'],
            'filter_counts': normalized_filter_counts,
            'all_email_ids': results['all_email_ids']
        }

        cache_result(query_hash, response_data)
        logger.info(f"Resultados almacenados en caché para query_hash: {query_hash}")
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Error al procesar la consulta: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error al procesar la consulta: {str(e)}'}), 500

@app.route('/api/filter_emails', methods=['POST'])
@login_required
def filter_emails():
    logger.info("Obteniendo correos para filtro en /api/filter_emails")
    try:
        data = request.get_json()
        logger.debug(f"Datos recibidos: {data}")
        query = data.get('query', '').strip()
        filter_data = data.get('filter')
        page = data.get('page', 1)
        results_per_page = data.get('results_per_page', 25)

        if not query or not filter_data or 'action' not in filter_data or 'terms' not in filter_data:
            logger.warning("Faltan datos requeridos: query o filter (action, terms)")
            return jsonify({'error': 'Faltan datos requeridos: query o filter (action, terms)'}), 400

        processed_query, _, term_groups, _ = process_query(query)
        logger.debug(f"Procesamiento de NLP para filter_emails: term_groups={term_groups}")

        result = get_filter_emails(term_groups, filter_data, current_user, page=page, results_per_page=results_per_page)

        logger.info(f"Encontrados {len(result['results'])} correos para el filtro")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error al obtener correos filtrados: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error al obtener correos filtrados: {str(e)}'}), 500

@app.route('/api/email', methods=['GET'])
@login_required
def get_email():
    logger.info("Obteniendo detalles del correo")
    try:
        identifier = request.args.get('identifier') or request.args.get('index') or request.args.get('message_id')
        is_index = request.args.get('is_index', 'true').lower() == 'true' if 'identifier' in request.args else bool(request.args.get('index'))

        if not identifier:
            logger.warning("No se proporcionó identifier, index ni message_id")
            return jsonify({'error': 'Se requiere identifier, index o message_id'}), 400
        
        logger.debug(f"Buscando correo con identifier: {identifier}, is_index: {is_index}")
        email = get_email_by_id(identifier, is_index=is_index)
        if not email:
            logger.warning(f"No se encontró el correo con identifier: {identifier} (is_index: {is_index})")
            return jsonify({'error': f'Correo no encontrado para {identifier}'}), 404
        logger.debug(f"Correo encontrado: {email}")
        return jsonify(email)
    except Exception as e:
        logger.error(f"Error al obtener el correo: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error al obtener el correo: {str(e)}'}), 500

@app.route('/api/agatta/draft_details', methods=['GET'])
@login_required
def get_draft_details():
    logger.info("Received draft details request")
    try:
        draft_id = request.args.get('draft_id')
        if not draft_id:
            logger.warning("Missing draft_id in request")
            return jsonify({'error': 'draft_id es requerido'}), 400
        
        logger.debug(f"Fetching draft details for draft_id: {draft_id}")
        user = users_collection.find_one({"username": current_user.username})
        active_mailboxes = [mb for mb in user["mailboxes"] if mb.get("agatta_config", {}).get("enabled", False) and mb["type"] == "gmail"]
        
        for mailbox in active_mailboxes:
            service = get_gmail_service(current_user.username, mailbox["mailbox_id"])
            if service:
                try:
                    draft = service.users().drafts().get(userId='me', id=draft_id).execute()
                    message = draft['message']
                    headers = message['payload'].get('headers', [])
                    
                    def get_header_value(headers, name):
                        for header in headers:
                            if header['name'].lower() == name.lower():
                                return header['value']
                        return None
                    
                    email_data = {
                        'index': draft['id'],
                        'from': get_header_value(headers, 'From') or 'Yo',
                        'to': get_header_value(headers, 'To') or 'N/A',
                        'subject': get_header_value(headers, 'Subject') or 'Sin Asunto',
                        'date': message.get('internalDate', 'N/A'),
                        'body': message.get('snippet', 'N/A')
                    }
                    logger.debug(f"Draft details retrieved: {email_data}")
                    return jsonify(email_data)
                except Exception as e:
                    logger.error(f"Error fetching draft {draft_id} for mailbox {mailbox['mailbox_id']}: {str(e)}")
        
        logger.warning(f"Draft not found: {draft_id}")
        return jsonify({'error': 'Draft not found'}), 404
    except Exception as e:
        logger.error(f"Error getting draft details: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/feedback', methods=['POST'])
@login_required
def feedback():
    logger.info("Procesando feedback")
    try:
        data = request.get_json()
        logger.debug(f"Datos de feedback recibidos: {data}")
        query = data.get('query', '')
        message_id = data.get('message_id', '')
        is_relevant = data.get('is_relevant', False)
        user_id = current_user.username

        if not query or not message_id:
            logger.warning("Faltan query o message_id en el feedback")
            return jsonify({'error': 'Faltan query o message_id'}), 400
        save_feedback(query, message_id, is_relevant, user_id)
        train_relevance_model(user_id)
        logger.info(f"Feedback guardado para message_id: {message_id}, user_id: {user_id}")
        return jsonify({'message': 'Feedback guardado'})
    except Exception as e:
        logger.error(f"Error al guardar feedback: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error al guardar feedback: {str(e)}'}), 500

@app.route('/api/feedback/validate', methods=['POST'])
@login_required
def validate_feedback_endpoint():
    logger.info("Received validate feedback request")
    try:
        data = request.get_json()
        logger.debug(f"Received feedback data: {data}")
        email_index = data.get('email_index')
        query = data.get('query')
        if not email_index or not query:
            logger.warning("Missing email_index or query in validate feedback request")
            return jsonify({'error': 'Email index and query are required'}), 400
        process_feedback(email_index, query, 'validate', current_user)
        logger.info(f"Validate feedback processed for email_index: {email_index}")
        return jsonify({'message': 'Feedback processed'})
    except Exception as e:
        logger.error(f"Error processing validate feedback: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/feedback/reject', methods=['POST'])
@login_required
def reject_feedback_endpoint():
    logger.info("Received reject feedback request")
    try:
        data = request.get_json()
        logger.debug(f"Received feedback data: {data}")
        email_index = data.get('email_index')
        query = data.get('query')
        if not email_index or not query:
            logger.warning("Missing email_index or query in reject feedback request")
            return jsonify({'error': 'Email index and query are required'}), 400
        process_feedback(email_index, query, 'reject', current_user)
        logger.info(f"Reject feedback processed for email_index: {email_index}")
        return jsonify({'message': 'Feedback processed'})
    except Exception as e:
        logger.error(f"Error processing reject feedback: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/bulk_feedback', methods=['POST'])
@login_required
def bulk_feedback():
    logger.info("Procesando feedback masivo")
    try:
        data = request.get_json()
        logger.debug(f"Datos de feedback masivo: {data}")
        query = data.get('query', '')
        filter_data = data.get('filter', {})

        if not query or not filter_data or 'action' not in filter_data or 'terms' not in filter_data:
            logger.warning("Faltan query o datos de filtro en feedback masivo")
            return jsonify({'error': 'Faltan query o datos de filtro (action, terms)'}), 400

        processed_query, intent, term_groups, embedding = process_query(query)
        logger.debug(f"Procesamiento de NLP para bulk feedback: processed_query={processed_query}, intent={intent}, term_groups={term_groups}")

        affected_count = submit_bulk_feedback(
            query=query,
            filter_data=filter_data,
            processed_query=processed_query,
            intent=intent,
            terms=term_groups,
            query_embedding=embedding
        )
        train_relevance_model(current_user.username)
        cache_key = f"{current_user.username}:{query}:{str(filter_data)}"
        query_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
        clear_cache(query_hash)
        logger.info(f"Caché limpiado para query_hash: {query_hash}")

        logger.info(f"Feedback masivo procesado, {affected_count} correos afectados")
        return jsonify({'message': 'Feedback masivo guardado', 'affected_count': affected_count})
    except Exception as e:
        logger.error(f"Error al guardar feedback masivo: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error al guardar feedback masivo: {str(e)}'}), 500

@app.route('/api/analyze_themes', methods=['POST'])
@login_required
def analyze_themes_endpoint():
    logger.info("Procesando análisis de temas")
    try:
        data = request.get_json()
        logger.debug(f"Datos recibidos: {data}")
        email_ids = data.get('email_ids', [])

        if not email_ids:
            logger.warning("Lista de IDs de correos vacía")
            return jsonify({'error': 'No se proporcionaron IDs de correos'}), 400

        if not isinstance(email_ids, list) or not all(isinstance(id, str) for id in email_ids):
            logger.warning("Formato inválido de email_ids")
            return jsonify({'error': 'email_ids debe ser una lista de strings'}), 400

        user_mailboxes = [mailbox['mailbox_id'] for mailbox in current_user.mailboxes]
        emails = list(emails_collection.find(
            {
                '$or': [
                    {'index': {'$in': email_ids}},
                    {'message_id': {'$in': email_ids}}
                ],
                'mailbox_id': {'$in': user_mailboxes}
            },
            {'index': 1, '_id': 0}
        ))
        email_indices = [email['index'] for email in emails if 'index' in email]

        if not email_indices:
            logger.warning("No se encontraron correos con los IDs proporcionados")
            return jsonify({'error': 'No se encontraron correos con los IDs proporcionados'}), 404

        cache_key = f"theme_summary:{'_'.join(sorted(email_indices))}"
        query_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
        cached_result = get_cached_result(query_hash)
        if cached_result:
            logger.info(f"Resultado obtenido del caché para query_hash: {query_hash}")
            return jsonify(cached_result)

        logger.debug(f"Llamando a analyze_themes con {len(email_indices)} índices y user: {current_user.username}")
        themes = analyze_themes(email_indices, user=current_user)
        logger.info(f"Devolviendo {len(themes)} temas")

        if not themes:
            logger.warning("No se generaron temas, posible error en el análisis")
            return jsonify({'error': 'No se pudieron generar temas, revise los registros del servidor'}), 500

        cache_result(query_hash, {'themes': themes})
        return jsonify({'themes': themes})
    except Exception as e:
        logger.error(f"Error al analizar temas: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error al analizar temas: {str(e)}'}), 500

@app.route('/api/email_addresses', methods=['GET'])
@login_required
def get_email_addresses_endpoint():
    logger.info("Obteniendo direcciones de correo únicas")
    try:
        prefix = request.args.get('prefix', '').strip()
        limit = int(request.args.get('limit', 50))
        if limit > 100:
            logger.warning("Límite de direcciones excedido: %d, ajustando a 100", limit)
            limit = 100

        logger.debug(f"Buscando direcciones con prefijo: {prefix}, límite: {limit}")
        addresses = get_email_addresses(prefix=prefix, limit=limit, user=current_user)
        logger.info(f"Devolviendo {len(addresses)} direcciones de correo")
        return jsonify({'addresses': addresses})
    except Exception as e:
        logger.error(f"Error al obtener direcciones de correo: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error al obtener direcciones: {str(e)}'}), 500

@app.route('/api/conversation_emails', methods=['POST'])
@login_required
def get_conversation_emails_endpoint():
    logger.info("Obteniendo correos de conversación")
    try:
        data = request.get_json()
        logger.debug(f"Datos recibidos: {data}")
        email1 = data.get('email1', '').strip()
        email2 = data.get('email2', '').strip()
        start_date = data.get('start_date', '')
        end_date = data.get('end_date', '')

        if not email1 or not email2 or not start_date or not end_date:
            logger.warning("Faltan parámetros requeridos: email1, email2, start_date, end_date")
            return jsonify({'error': 'Faltan parámetros requeridos'}), 400

        logger.debug(f"Buscando correos entre email1: {email1}, email2: {email2}, desde {start_date} hasta {end_date}")
        results = get_conversation_emails(email1, email2, start_date, end_date, user=current_user)
        logger.info(f"Encontrados {len(results)} correos de conversación")

        return jsonify({
            'results': results,
            'totalResults': len(results)
        })
    except Exception as e:
        logger.error(f"Error al obtener correos de conversación: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error al obtener correos: {str(e)}'}), 500

@app.route('/api/deep_analysis_init', methods=['POST'])
@login_required
def deep_analysis_init():
    logger.info("Received deep analysis initialization request")
    try:
        data = request.get_json()
        if not data or 'theme_ids' not in data:
            logger.warning("Invalid deep analysis init request: missing theme_ids")
            return jsonify({"error": "Theme IDs are required"}), 400
        theme_ids = data.get('theme_ids', [])
        if not theme_ids:
            logger.warning("No theme IDs provided")
            return jsonify({"error": "No theme IDs provided"}), 400

        session_id = str(uuid.uuid4())
        logger.debug(f"Initializing deep analysis with session_id: {session_id}, theme_ids: {theme_ids}, user: {current_user.username}")
        result = initialize_deep_analysis(session_id, theme_ids, user=current_user)

        if "error" in result:
            logger.error(f"Deep analysis initialization failed: {result['error']}")
            return jsonify(result), 400

        logger.info(f"Deep analysis initialized: session_id={session_id}")
        return jsonify({"session_id": session_id, **result})
    except Exception as e:
        logger.error(f"Error initializing deep analysis: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/deep_analysis_prompt', methods=['POST'])
@login_required
def deep_analysis_prompt():
    logger.info("Received deep analysis prompt request")
    try:
        data = request.get_json()
        if not data or 'session_id' not in data or 'prompt' not in data:
            logger.warning("Invalid deep analysis prompt request: missing required fields")
            return jsonify({"error": "Session ID and prompt are required"}), 400

        session_id = data.get('session_id')
        prompt = data.get('prompt')

        logger.debug(f"Processing prompt for session_id: {session_id}, prompt: {prompt[:50]}..., user: {current_user.username}")
        result = process_deep_analysis_prompt(session_id, prompt, user=current_user)

        if "error" in result:
            logger.error(f"Deep analysis prompt processing failed: {result['error']}")
            return jsonify(result), 400

        logger.info(f"Deep analysis prompt processed successfully")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error processing deep analysis prompt: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/deep_analysis_reset', methods=['POST'])
@login_required
def deep_analysis_reset():
    logger.info("Received deep analysis reset request")
    try:
        data = request.get_json()
        if not data or 'session_id' not in data:
            logger.warning("Invalid deep analysis reset request: missing session_id")
            return jsonify({"error": "Session ID is required"}), 400

        session_id = data.get('session_id')
        logger.debug(f"Resetting context for session_id: {session_id}")
        result = reset_deep_analysis_context(session_id)

        if "error" in result:
            logger.error(f"Deep analysis reset failed: {result['error']}")
            return jsonify(result), 400

        logger.info(f"Deep analysis context reset: session_id={session_id}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error resetting deep analysis context: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/deep_conversation_analysis_init', methods=['POST'])
@login_required
def deep_conversation_analysis_init():
    logger.info("Received deep conversation analysis initialization request")
    try:
        data = request.get_json()
        logger.debug(f"Datos recibidos: {data}")
        email1 = data.get('email1', '').strip()
        email2 = data.get('email2', '').strip()
        start_date = data.get('start_date', '')
        end_date = data.get('end_date', '')
        theme_ids = data.get('theme_ids', [])

        if not email1 or not email2 or not start_date or not end_date:
            logger.warning("Invalid deep conversation analysis init request: missing required fields")
            return jsonify({"error": "Email1, Email2, start_date, and end_date are required"}), 400

        logger.debug(f"Initializing deep conversation analysis with email1: {email1}, email2: {email2}, start_date: {start_date}, end_date: {end_date}, theme_ids: {theme_ids}, user: {current_user.username}")
        result = deep_conversation_service.initialize_conversation_analysis(
            email1, email2, start_date, end_date, theme_ids, user=current_user
        )

        if "error" in result:
            logger.error(f"Deep conversation analysis initialization failed: {result['error']}")
            return jsonify(result), 400

        logger.info(f"Deep conversation analysis initialized: session_id={result.get('session_id')}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error initializing deep conversation analysis: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/deep_conversation_analysis_prompt', methods=['POST'])
@login_required
def deep_conversation_analysis_prompt():
    logger.info("Received deep conversation analysis prompt request")
    try:
        data = request.get_json()
        if not data or 'session_id' not in data or 'prompt' not in data:
            logger.warning("Invalid deep conversation analysis prompt request: missing required fields")
            return jsonify({"error": "Session ID and prompt are required"}), 400

        session_id = data.get('session_id')
        prompt = data.get('prompt')

        logger.debug(f"Processing prompt for session_id: {session_id}, prompt: {prompt[:50]}..., user: {current_user.username}")
        result = deep_conversation_service.process_conversation_prompt(session_id, prompt, user=current_user)

        if "error" in result:
            logger.error(f"Deep conversation analysis prompt processing failed: {result['error']}")
            return jsonify(result), 400

        logger.info(f"Deep conversation analysis prompt processed successfully")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error processing deep conversation analysis prompt: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/deep_conversation_analysis_reset', methods=['POST'])
@login_required
def deep_conversation_analysis_reset():
    logger.info("Received deep conversation analysis reset request")
    try:
        data = request.get_json()
        if not data or 'session_id' not in data:
            logger.warning("Invalid deep conversation analysis reset request: missing session_id")
            return jsonify({"error": "Session ID is required"}), 400

        session_id = data.get('session_id')
        logger.debug(f"Resetting context for session_id: {session_id}")
        result = deep_conversation_service.reset_conversation_context(session_id)

        if "error" in result:
            logger.error(f"Deep conversation analysis reset failed: {result['error']}")
            return jsonify(result), 400

        logger.info(f"Deep conversation analysis context reset: session_id={session_id}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error resetting deep conversation analysis context: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/debug/themes', methods=['GET'])
@login_required
def debug_themes():
    logger.info("Fetching themes for debugging")
    try:
        themes = list(themes_collection.find(
            {'user_id': current_user.username},
            {'theme_id': 1, 'title': 1, 'email_indices': 1, 'created_at': 1, '_id': 0}
        ))
        logger.info(f"Found {len(themes)} themes for user {current_user.username}")
        return jsonify({'themes': themes})
    except Exception as e:
        logger.error(f"Error fetching themes for debug: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashboard_metrics', methods=['GET'])
@login_required
def dashboard_metrics():
    logger.info("Received dashboard metrics request")
    try:
        metrics = get_dashboard_metrics()
        logger.info("Dashboard metrics retrieved successfully")
        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Dashboard metrics error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/user_data', methods=['GET'])
@login_required
def user_data():
    logger.info("Received user data request")
    try:
        data = get_user_data()
        logger.info("User data retrieved successfully")
        return jsonify(data)
    except Exception as e:
        logger.error(f"User data error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/email_list', methods=['POST'])
@login_required
def email_list():
    logger.info("Received email list request")
    try:
        data = request.get_json(force=True)
        logger.debug(f"Raw POST body: {json.dumps(data, ensure_ascii=False)}")
        metric = data.get('metric')
        period = data.get('period')
        sender = data.get('sender')
        recipient = data.get('recipient')
        if not metric or not period:
            logger.warning("Missing metric or period in email list request")
            return jsonify({'error': 'Missing metric or period'}), 400
        result = get_email_list(metric, period, sender, recipient, data)
        logger.info("Email list retrieved successfully")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching email list: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/thread_emails', methods=['POST'])
@login_required
def thread_emails():
    logger.info("Received thread emails request")
    try:
        data = request.get_json(force=True)
        todo_id = data.get('todo_id')
        if not todo_id:
            logger.warning("Missing todo_id in thread emails request")
            return jsonify({'error': 'Missing todo_id'}), 400
        result = get_thread_emails(todo_id)
        logger.info("Thread emails retrieved successfully")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching thread emails: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/clear_cache', methods=['POST'])
@login_required
def clear_cache_endpoint():
    logger.info("Received cache clear request")
    try:
        data = request.get_json()
        cache_key = data.get('cache_key', '')
        if not cache_key:
            logger.warning("No cache_key provided, clearing all caches for user")
            clear_cache(None, user=current_user)
            return jsonify({'message': 'All caches cleared successfully for user'})
        else:
            logger.info(f"Clearing cache for key: {cache_key}")
            clear_cache(cache_key, user=current_user)
            return jsonify({'message': f'Cache cleared for key: {cache_key}'})
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error clearing cache: {str(e)}'}), 500

@app.route('/api/threads', methods=['POST'])
@login_required
def analyze_threads_endpoint():
    logger.info("Received thread analysis request")
    try:
        data = request.get_json()
        logger.debug(f"Received thread data: {data}")
        query = data.get('query', '').strip()
        if not query:
            logger.warning("Empty query received in thread analysis request")
            return jsonify({'error': 'Missing query'}), 400
        threads = analyze_threads(query, user=current_user)
        logger.info(f"Returning {len(threads)} thematic threads")
        return jsonify({'threads': threads})
    except Exception as e:
        logger.error(f"Error analyzing threads: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/export_threads', methods=['POST'])
@login_required
def export_threads_endpoint():
    logger.info("Received export threads request")
    try:
        data = request.get_json()
        logger.debug(f"Received export data: {data}")
        threads = data.get('threads', [])
        format_type = data.get('format', 'excel').lower()
        if not threads:
            logger.warning("No threads provided for export")
            return jsonify({'error': 'No threads provided'}), 400
        if format_type not in ['excel', 'pdf']:
            logger.warning(f"Invalid export format: {format_type}")
            return jsonify({'error': 'Invalid format, reward excel or pdf'}), 400
        file_content = export_threads(threads, format_type)
        filename = f"threads_export.{format_type}"
        logger.info(f"Exporting threads as {filename}")
        return send_file(
            file_content,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if format_type == 'excel' else 'application/pdf'
        )
    except Exception as e:
        logger.error(f"Error exporting threads: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/add_mailbox', methods=['POST'])
@login_required
def add_mailbox_endpoint():
    logger.info("Received add mailbox request")
    try:
        data = request.get_json()
        logger.debug(f"Received mailbox data: {data}")
        
        mailbox_id = data.get('mailbox_id')
        mailbox_type = data.get('type')
        
        if not mailbox_id or not mailbox_type:
            logger.warning("Missing mailbox_id or type")
            return jsonify({'error': 'mailbox_id y type son requeridos'}), 400
        
        if mailbox_type not in ['gmail', 'imap']:
            logger.warning(f"Unsupported mailbox type: {mailbox_type}")
            return jsonify({'error': 'Tipo de buzón no soportado'}), 400
        
        if mailbox_type == 'gmail':
            client_id = data.get('client_id')
            client_secret = data.get('client_secret')
            if not client_id or not client_secret:
                logger.warning("Missing client_id or client_secret for Gmail")
                return jsonify({'error': 'Client ID y Client Secret son requeridos para Gmail'}), 400
        elif mailbox_type == 'imap':
            required_fields = ['server', 'port', 'encryption', 'username', 'password']
            missing_fields = [field for field in required_fields if not data.get(field)]
            if missing_fields:
                logger.warning(f"Missing IMAP fields: {missing_fields}")
                return jsonify({'error': f'Todos los campos IMAP son requeridos. Faltan: {", ".join(missing_fields)}'}), 400
        
        result = add_mailbox(data)
        
        if 'error' in result:
            return jsonify(result), 400
        logger.info(f"Mailbox added successfully for user: {current_user.username}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error adding mailbox: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/change_password', methods=['POST'])
@login_required
def change_password_endpoint():
    logger.info("Received change password request")
    try:
        data = request.get_json()
        logger.debug(f"Received password data: {data}")
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        if not current_password or not new_password:
            logger.warning("Missing required fields in change password request")
            return jsonify({'error': 'Missing required fields'}), 400
        result = change_password(current_password, new_password)
        if 'error' in result:
            return jsonify(result), 400
        logger.info(f"Password changed successfully for user: {current_user.username}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error changing password: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/remove_refresh_token', methods=['POST'])
@login_required
def remove_refresh_token():
    data = request.get_json()
    mailbox_id = data.get('mailbox_id')
    if not mailbox_id:
        return jsonify({'error': 'mailbox_id es requerido'}), 400
    try:
        result = users_collection.update_one(
            {"username": current_user.username, "mailboxes.mailbox_id": mailbox_id},
            {"$unset": {"mailboxes.$.credentials.refresh_token": ""}}
        )
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Buzón no encontrado'}), 404
    except Exception as e:
        logger.error(f"Error removing refresh token: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/update_credentials', methods=['POST'])
@login_required
def update_credentials():
    data = request.get_json()
    mailbox_id = data.get('mailbox_id')
    client_id = data.get('client_id')
    client_secret = data.get('client_secret')
    if not all([mailbox_id, client_id, client_secret]):
        return jsonify({'error': 'mailbox_id, client_id y client_secret son requeridos'}), 400
    try:
        result = users_collection.update_one(
            {"username": current_user.username, "mailboxes.mailbox_id": mailbox_id, "mailboxes.type": "gmail"},
            {"$set": {
                "mailboxes.$.credentials.client_id": client_id,
                "mailboxes.$.credentials.client_secret": client_secret
            }}
        )
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Buzón Gmail no encontrado'}), 404
    except Exception as e:
        logger.error(f"Error updating credentials: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/remove_mailbox', methods=['POST'])
@login_required
def remove_mailbox():
    data = request.get_json()
    mailbox_id = data.get('mailbox_id')
    if not mailbox_id:
        return jsonify({'error': 'mailbox_id es requerido'}), 400
    try:
        result = users_collection.update_one(
            {"username": current_user.username},
            {"$pull": {"mailboxes": {"mailbox_id": mailbox_id}}}
        )
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Buzón no encontrado'}), 404
    except Exception as e:
        logger.error(f"Error removing mailbox: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/start_insertion', methods=['POST'])
@login_required
def start_insertion():
    data = request.get_json()
    mailbox_id = data.get('mailbox_id')
    if not mailbox_id:
        return jsonify({'error': 'mailbox_id es requerido'}), 400
    try:
        subprocess.Popen(['python', 'insert_emails.py', current_user.username, '-mailbox', mailbox_id])
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error starting insertion: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_logs', methods=['GET'])
@login_required
def get_logs():
    try:
        with open('email_insertion.log', 'r') as f:
            logs = f.read()
        return logs
    except FileNotFoundError:
        return 'No logs available', 404
    except Exception as e:
        logger.error(f"Error getting logs: {str(e)}", exc_info=True)
        return str(e), 500

@app.route('/api/update_agatta_config', methods=['POST'])
@login_required
def update_agatta_config_endpoint():
    logger.info("Received update AGATTA config request")
    try:
        data = request.get_json()
        logger.debug(f"Received AGATTA config data: {data}")
        mailbox_id = data.get('mailbox_id')
        agatta_config = data.get('agatta_config')
        if not mailbox_id or not agatta_config:
            logger.warning("Missing mailbox_id or agatta_config")
            return jsonify({'error': 'mailbox_id y agatta_config son requeridos'}), 400
        result = update_agatta_config(mailbox_id, agatta_config)
        if 'error' in result:
            return jsonify(result), 400
        logger.info(f"AGATTA config updated successfully for mailbox: {mailbox_id}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error updating AGATTA config: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/agatta/todos', methods=['GET'])
@login_required
def agatta_todos():
    logger.info("Received get AGATTA todos request")
    try:
        completed = request.args.get('completed', default='all')
        if completed == 'true':
            completed_filter = True
        elif completed == 'false':
            completed_filter = False
        else:
            completed_filter = None
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 10))
        result = get_agatta_todos(current_user.username, completed=completed_filter, page=page, page_size=page_size)
        logger.info("AGATTA todos retrieved successfully")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting AGATTA todos: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/agatta/complete_task', methods=['POST'])
@login_required
def complete_task():
    logger.info("Received complete task request")
    try:
        data = request.get_json()
        task_id = data.get('task_id')
        if not task_id:
            logger.warning("Missing task_id")
            return jsonify({'error': 'task_id es requerido'}), 400
        result = mark_task_completed(task_id)
        if 'error' in result:
            return jsonify(result), 400
        logger.info(f"Task {task_id} marked as completed")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error completing task: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/agatta/stats', methods=['GET'])
@login_required
def agatta_stats():
    logger.info("Received get AGATTA stats request")
    try:
        stats = get_agatta_stats(current_user.username)
        logger.info("AGATTA stats retrieved successfully")
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting AGATTA stats: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/agatta/create_draft', methods=['POST'])
@login_required
def create_draft_endpoint():
    logger.info("Received create draft request")
    try:
        data = request.get_json()
        task_id = data.get('task_id')
        if not task_id:
            logger.warning("Missing task_id")
            return jsonify({'error': 'task_id es requerido'}), 400
        result = create_draft(task_id, current_user)
        if 'error' in result:
            return jsonify(result), 400
        logger.info(f"Draft created for task {task_id}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error creating draft: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/agatta/draft_count', methods=['GET'])
@login_required
def get_draft_count_endpoint():
    logger.info("Received draft count request")
    try:
        count = get_draft_count(current_user.username)
        logger.info(f"Draft count retrieved: {count}")
        return jsonify({'draft_count': count})
    except Exception as e:
        logger.error(f"Error getting draft count: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/agatta/outbox_count', methods=['GET'])
@login_required
def get_outbox_count_endpoint():
    logger.info("Received outbox count request")
    try:
        count = get_outbox_count(current_user.username)
        logger.info(f"Outbox count retrieved: {count}")
        return jsonify({'outbox_count': count})
    except Exception as e:
        logger.error(f"Error getting outbox count: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/agatta/draft_emails', methods=['GET'])
@login_required
def get_draft_emails_endpoint():
    logger.info("Received draft emails request")
    try:
        emails = get_draft_emails(current_user.username)
        logger.info(f"Draft emails retrieved: {len(emails)}")
        return jsonify({'emails': emails})
    except Exception as e:
        logger.error(f"Error getting draft emails: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/agatta/outbox_emails', methods=['GET'])
@login_required
def get_outbox_emails_endpoint():
    logger.info("Received outbox emails request")
    try:
        emails = get_outbox_emails(current_user.username)
        logger.info(f"Outbox emails retrieved: {len(emails)}")
        return jsonify({'emails': emails})
    except Exception as e:
        logger.error(f"Error getting outbox emails: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/clear_theme_cache', methods=['POST'])
@login_required
def clear_theme_cache():
    logger.info("Procesando solicitud de borrado de caché de temas")
    try:
        data = request.get_json()
        logger.debug(f"Datos recibidos: {data}")
        email_ids = data.get('emailIds', [])
        if not email_ids:
            logger.warning("No se proporcionaron email IDs para borrar el caché")
            return jsonify({'error': 'No email IDs provided'}), 400
        cache_key = f"theme_summary:{'_'.join(sorted(email_ids))}"
        logger.debug(f"Clave de caché generada para borrar: {cache_key}")
        clear_cache(cache_key)
        logger.info(f"Caché borrado para la clave: {cache_key}")
        return jsonify({'message': 'Cache cleared successfully'}), 200
    except Exception as e:
        logger.error(f"Error al borrar el caché de temas: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error clearing theme cache: {str(e)}'}), 500

if __name__ == '__main__':
    logger.info("Iniciando servidor Flask en puerto 5000")
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        logger.critical(f"Error al iniciar el servidor: {str(e)}", exc_info=True)
    finally:
        logger.info("Finalizando ejecución del servidor")