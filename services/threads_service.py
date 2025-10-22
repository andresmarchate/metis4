import logging
from logging import handlers
import hashlib
import numpy as np
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from hdbscan import HDBSCAN
from sklearn.naive_bayes import MultinomialNB
from sklearn.feature_extraction.text import TfidfVectorizer
from io import BytesIO
import openpyxl
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from datetime import datetime
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION
from services.nlp_service import process_query, decompress_embedding
from services.cache_service import get_cached_result, cache_result
from fuzzywuzzy import fuzz
import re
import torch
import os
from collections import Counter
import requests

# Configuración inicial de PyTorch
torch.cuda.empty_cache()
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

# Configuración de logging
logger = logging.getLogger('email_search_app.threads_service')
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

# Conexión a MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]
feedback_collection = db['feedback']

# Carga del modelo de embeddings
logger.info("Cargando modelo de embeddings: 'paraphrase-multilingual-MiniLM-L12-v2'")
embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
logger.info("Modelo de embeddings cargado exitosamente")

# Inicialización de herramientas de clasificación
bayesian_filter = MultinomialNB()
filter_weights = {'summary': 0.2, 'terms': 0.2, 'subject': 0.2, 'thread_id': 0.2, 'names': 0.2}
tfidf_vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')

# URL de la API del LLM
LLM_API_URL = "http://localhost:11434/api/generate"

def generate_synonyms(term):
    """Genera sinónimos para un término usando un LLM y los limpia."""
    prompt = f"Genera sinónimos para el término '{term}' en español."
    payload = {
        "model": "mistral-custom",
        "prompt": prompt,
        "stream": False,
        "temperature": 0.3,
        "num_predict": 10
    }
    try:
        response = requests.post(LLM_API_URL, json=payload)
        response.raise_for_status()
        result = response.json()['response']
        synonyms = re.findall(r'(?<=: ).*?(?=\n|$)', result)
        cleaned_synonyms = [syn.strip().lower() for syn in synonyms if syn.strip().lower() != term.lower()]
        logger.debug(f"Sinónimos limpios para '{term}': {cleaned_synonyms}")
        return cleaned_synonyms
    except Exception as e:
        logger.error(f"Error generando sinónimos para '{term}': {e}")
        return []

def analyze_threads(query, user=None):
    """Analiza hilos temáticos basados en una consulta."""
    logger.info(f"Analyzing threads for query: {query}, user: {user.username if user else 'None'}")
    try:
        cache_key = f"threads:{user.username if user else 'anonymous'}:{query}"
        query_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
        logger.debug(f"Generated query_hash: {query_hash}")
        cached_result = get_cached_result(query_hash)
        if cached_result:
            logger.info(f"Returning cached threads for query_hash: {query_hash}")
            return cached_result.get('threads', [])

        processed_query, intent, terms, query_embedding, names = process_query(query, return_names=True)
        logger.debug(f"Processed query: intent={intent}, terms={terms}, names={names}")

        term_synonyms = {}
        for group in terms:
            for term in group:
                synonyms = generate_synonyms(term)
                term_synonyms[term] = synonyms

        expanded_terms = []
        for group in terms:
            expanded_group = group.copy()
            for term in group:
                expanded_group.extend(term_synonyms.get(term, []))
            expanded_terms.append(list(set(expanded_group)))
        logger.debug(f"Expanded terms: {expanded_terms}")

        emails = fetch_relevant_emails_with_synonyms(query, expanded_terms, names, query_embedding, user)
        logger.debug(f"Fetched {len(emails)} candidate emails")
        if not emails:
            logger.warning("No relevant emails found for user")
            return []

        email_texts = [f"{email.get('subject', '')} {email.get('summary', '')} {email.get('body', '')}" for email in emails]
        email_embeddings = embedding_model.encode(email_texts, convert_to_tensor=True)
        logger.debug(f"Generated email embeddings, device: {email_embeddings.device}, dimension: {email_embeddings.shape[1]}")
        if email_embeddings.shape[1] != 384:
            logger.error(f"Dimensión de email_embeddings incorrecta: {email_embeddings.shape[1]} (esperado: 384)")
            raise ValueError("Dimensión de email_embeddings no coincide con el modelo MiniLM-L12-v2")

        query_embedding_decompressed = decompress_embedding(query_embedding)
        if query_embedding_decompressed is None:
            logger.error("Failed to decompress query embedding")
            raise ValueError("Query embedding decompression failed")
        query_embedding_tensor = torch.tensor(query_embedding_decompressed, dtype=torch.float32).unsqueeze(0)

        query_embedding_np = query_embedding_tensor.cpu().numpy()
        email_embeddings_np = email_embeddings.cpu().numpy()
        similarities = cosine_similarity(query_embedding_np, email_embeddings_np).flatten()
        logger.debug(f"Computed similarities: min={similarities.min()}, max={similarities.max()}, mean={np.mean(similarities)}")

        similarity_threshold = 0.4
        filtered_emails_with_scores = []
        for i, email in enumerate(emails):
            text = f"{email.get('subject', '')} {email.get('summary', '')} {email.get('body', '')}"
            term_matches = sum(1 for group in expanded_terms if any(term in text.lower() for term in group))
            concordance = term_matches / len(expanded_terms) if expanded_terms else 0
            if term_matches == len(expanded_terms) and similarities[i] > similarity_threshold:
                filtered_emails_with_scores.append((email, concordance, similarities[i]))
            logger.debug(f"Email {i}: similarity={similarities[i]}, term_matches={term_matches}/{len(expanded_terms)}")

        if len(filtered_emails_with_scores) < 5:
            logger.warning("No suficientes emails con todos los términos, relajando búsqueda")
            for required_matches in range(len(expanded_terms) - 1, 0, -1):
                for i, email in enumerate(emails):
                    if any(e == email for e, _, _ in filtered_emails_with_scores):
                        continue
                    text = f"{email.get('subject', '')} {email.get('summary', '')} {email.get('body', '')}"
                    term_matches = sum(1 for group in expanded_terms if any(term in text.lower() for term in group))
                    concordance = term_matches / len(expanded_terms) if expanded_terms else 0
                    if term_matches >= required_matches and similarities[i] > similarity_threshold:
                        filtered_emails_with_scores.append((email, concordance, similarities[i]))
                if len(filtered_emails_with_scores) >= 5:
                    break

        if not filtered_emails_with_scores:
            logger.warning("No emails found even after relaxing the search")
            return []

        filtered_emails = [email for email, _, _ in filtered_emails_with_scores]
        filtered_embeddings = email_embeddings_np[[i for i, email in enumerate(emails) if email in filtered_emails]]
        logger.debug(f"Filtered to {len(filtered_emails)} emails")

        threads = cluster_threads(filtered_emails, filtered_embeddings)
        logger.debug(f"Clustered into {len(threads)} threads")

        for thread in threads:
            thread_emails = thread['emails']
            if len(thread_emails) > 1:
                thread_embeddings = [filtered_embeddings[filtered_emails.index(email)] for email in thread_emails]
                pairwise_similarities = cosine_similarity(thread_embeddings)
                coherence = np.mean(pairwise_similarities[np.triu_indices(len(thread_emails), k=1)])
                thread['coherence'] = float(coherence)
            else:
                thread['coherence'] = 1.0

        serializable_threads = []
        for thread in threads:
            serializable_thread = {
                'thread_id': thread['thread_id'],
                'label': thread['label'],
                'coherence': float(thread['coherence']),
                'emails': [
                    {
                        **{k: v for k, v in email.items() if k != '_id'},
                        'concordance': float(next((conc for e, conc, sim in filtered_emails_with_scores if e == email), 0)),
                        'similarity': float(next((sim for e, conc, sim in filtered_emails_with_scores if e == email), 0)),
                        'confidence_score': float(email.get('confidence_score', 0.0)),
                        'resolved_points': extract_points(email, 'resolved'),
                        'pending_points': extract_points(email, 'pending')
                    }
                    for email in thread['emails']
                ]
            }
            serializable_threads.append(serializable_thread)

        cache_result(query_hash, {'threads': serializable_threads})
        logger.info(f"Returning {len(threads)} thematic threads")
        return serializable_threads
    except Exception as e:
        logger.error(f"Error analyzing threads: {str(e)}", exc_info=True)
        raise

def fetch_relevant_emails_with_synonyms(query, expanded_terms, names, query_embedding, user):
    """Obtiene correos relevantes desde MongoDB basados en términos expandidos y nombres."""
    logger.debug(f"Fetching emails with expanded terms: {expanded_terms}, names: {names}, user: {user.username if user else 'None'}")
    try:
        if not user:
            raise ValueError("User must be provided for email fetching")

        user_mailboxes = [mailbox['mailbox_id'] for mailbox in user.mailboxes]
        if not user_mailboxes:
            logger.warning(f"No mailboxes found for user: {user.username}")
            return []

        term_conditions = []
        for group in expanded_terms:
            group_condition = [
                {'$or': [
                    {'subject': {'$regex': term, '$options': 'i'}},
                    {'summary': {'$regex': term, '$options': 'i'}},
                    {'body': {'$regex': term, '$options': 'i'}},
                    {'relevant_terms': term}
                ]} for term in group
            ]
            term_conditions.append({'$or': group_condition})

        match_conditions = {
            'mailbox_id': {'$in': user_mailboxes},
            '$and': term_conditions
        }

        if names:
            name_conditions = [
                {'from': {'$regex': name, '$options': 'i'}},
                {'to': {'$regex': name, '$options': 'i'}}
            ]
            match_conditions['$and'].append({'$or': name_conditions})

        pipeline = [
            {'$match': match_conditions},
            {
                '$project': {
                    'index': 1,
                    'from': 1,
                    'to': 1,
                    'subject': 1,
                    'date': 1,
                    'summary': 1,
                    'body': 1,
                    'thread_id': 1,
                    'in_reply_to': 1,
                    'references': 1,
                    'relevant_terms': 1
                }
            },
            {'$limit': 500}
        ]

        emails = list(emails_collection.aggregate(pipeline))
        for email in emails:
            email.pop('_id', None)
        logger.debug(f"Fetched {len(emails)} candidate emails for user")
        return emails
    except Exception as e:
        logger.error(f"Error fetching emails: {str(e)}", exc_info=True)
        raise

def normalize_subject(subject):
    """Normaliza el asunto del correo eliminando prefijos como 're:' o 'fwd:'."""
    if not subject:
        return ""
    subject = re.sub(r'^(re:|fwd:|\[re\]|\[fwd\])\s*', '', subject, flags=re.IGNORECASE)
    subject = re.sub(r'\s+', ' ', subject).strip()
    return subject.lower()

def parse_date(date_str):
    """Convierte una cadena de fecha en un objeto datetime."""
    if not date_str:
        logger.warning("Fecha vacía, usando UTC now")
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            logger.warning(f"No se pudo parsear la fecha: {date_str}, usando UTC now")
            return datetime.utcnow()

def cluster_threads(emails, embeddings):
    """Agrupa correos en hilos temáticos usando HDBSCAN."""
    logger.debug(f"Clustering {len(emails)} emails into thematic threads")
    try:
        if not emails or not isinstance(emails, list):
            logger.warning("Empty or invalid emails list provided")
            return []
        if embeddings is None or embeddings.size == 0:
            logger.warning("Invalid or empty embeddings array provided")
            return []
        if len(emails) != embeddings.shape[0]:
            logger.error(f"Mismatch between emails ({len(emails)}) and embeddings ({embeddings.shape[0]})")
            raise ValueError("Emails and embeddings length mismatch")

        if len(emails) <= 1:
            return [{
                'thread_id': 'single',
                'label': 'Hilo Individual',
                'emails': emails
            }]

        threads_by_id = {}
        emails_to_cluster = []
        for i, email in enumerate(emails):
            thread_id = email.get('thread_id')
            if thread_id:
                if thread_id not in threads_by_id:
                    threads_by_id[thread_id] = []
                threads_by_id[thread_id].append(email)
            else:
                emails_to_cluster.append((i, email))

        if emails_to_cluster:
            cluster_indices, cluster_emails = zip(*emails_to_cluster) if emails_to_cluster else ([], [])
            cluster_embeddings = embeddings[list(cluster_indices)] if cluster_indices else np.array([])
            if cluster_embeddings.size > 0:
                cosine_dist = 1 - cosine_similarity(cluster_embeddings)
                cosine_dist = cosine_dist.astype(np.float64)
                cosine_dist = (cosine_dist + cosine_dist.T) / 2
                np.fill_diagonal(cosine_dist, 0)
                clustering = HDBSCAN(min_cluster_size=2, metric='precomputed')
                labels = clustering.fit_predict(cosine_dist)
                for label, email in zip(labels, cluster_emails):
                    if label != -1:
                        thread_id = f"cluster_{label}"
                        if thread_id not in threads_by_id:
                            threads_by_id[thread_id] = []
                        threads_by_id[thread_id].append(email)

        formatted_threads = []
        for thread_id, thread_emails in threads_by_id.items():
            if len(thread_emails) >= 2 or not emails_to_cluster:
                base_title = generate_thread_label(thread_emails)
                formatted_threads.append({
                    'thread_id': thread_id,
                    'label': f"{base_title} ({len(thread_emails)} emails)",
                    'emails': sorted(thread_emails, key=lambda x: parse_date(x.get('date', '')))
                })

        return merge_small_threads(formatted_threads, embeddings)
    except Exception as e:
        logger.error(f"Error clustering threads: {str(e)}", exc_info=True)
        raise

def merge_small_threads(threads, embeddings):
    """Fusiona hilos pequeños con hilos más grandes basados en similitud."""
    formatted_threads = []
    for thread in threads:
        if len(thread['emails']) < 2 and len(threads) > 1:
            thread_embedding = np.mean([embeddings[i] for i, e in enumerate(embeddings) if e in thread['emails']], axis=0)
            best_match = None
            best_similarity = 0.7
            for other_thread in threads:
                if other_thread != thread and len(other_thread['emails']) >= 2:
                    other_embedding = np.mean([embeddings[i] for i, e in enumerate(embeddings) if e in other_thread['emails']], axis=0)
                    similarity = cosine_similarity(thread_embedding.reshape(1, -1), other_embedding.reshape(1, -1)).item()
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = other_thread
            if best_match:
                best_match['emails'].extend(thread['emails'])
                best_match['label'] = f"{generate_thread_label(best_match['emails'])} ({len(best_match['emails'])} emails)"
                continue
        formatted_threads.append(thread)
    return formatted_threads

def generate_thread_label(emails):
    """Genera una etiqueta para un hilo basada en los asuntos o términos relevantes."""
    try:
        original_subjects = [email.get('subject', '').strip() for email in emails]
        normalized_subjects = [normalize_subject(subj) for subj in original_subjects]
        
        valid_indices = [i for i, norm_subj in enumerate(normalized_subjects) if norm_subj]
        if valid_indices:
            unique_norm_subjs = set(normalized_subjects[i] for i in valid_indices)
            if len(unique_norm_subjs) == 1:
                base_title = original_subjects[valid_indices[0]]
            else:
                all_terms = []
                for email in emails:
                    all_terms.extend(email.get('relevant_terms', []))
                term_counts = Counter(all_terms)
                top_terms = [term for term, _ in term_counts.most_common(3)]
                base_title = "Hilo: " + ", ".join(top_terms)
        else:
            all_terms = []
            for email in emails:
                all_terms.extend(email.get('relevant_terms', []))
            term_counts = Counter(all_terms)
            top_terms = [term for term, _ in term_counts.most_common(3)]
            base_title = "Hilo: " + ", ".join(top_terms) if top_terms else "Hilo Sin Asunto"
        
        return base_title
    except Exception as e:
        logger.error(f"Error generating thread label: {str(e)}", exc_info=True)
        return "Hilo Sin Etiqueta"

def format_emails(emails):
    """Formatea los correos para su inclusión en los hilos."""
    formatted = []
    for email in emails:
        resolved_points = extract_points(email, 'resolved')
        pending_points = extract_points(email, 'pending')
        formatted.append({
            'index': email.get('index', 'N/A'),
            'date': email.get('date', ''),
            'from': email.get('from', 'Desconocido'),
            'to': email.get('to', 'Desconocido'),
            'subject': email.get('subject', 'Sin Asunto'),
            'summary': email.get('summary', 'Sin Resumen'),
            'resolved_points': resolved_points,
            'pending_points': pending_points,
            'confidence_score': float(email.get('confidence_score', 0.0))
        })
    return formatted

def extract_points(email, point_type):
    """Extrae puntos resueltos o pendientes del correo."""
    try:
        text = f"{email.get('summary', '')} {email.get('body', '')}".lower()
        pattern = r'resolved:.*?[.!?]' if point_type == 'resolved' else r'pending:.*?[.!?]'
        matches = re.findall(pattern, text, re.IGNORECASE)
        return '; '.join(match.strip() for match in matches) or 'None'
    except Exception:
        logger.error(f"Error extracting {point_type} points", exc_info=True)
        return 'None'

def export_threads(threads, format_type):
    """Exporta los hilos a Excel o PDF."""
    logger.info(f"Exporting threads to format: {format_type}")
    try:
        buffer = BytesIO()
        if format_type == 'excel':
            wb = openpyxl.Workbook()
            wb.remove(wb.active)
            for thread in threads:
                label = thread.get('label', 'Hilo')[:31].replace(':', '_')
                ws = wb.create_sheet(label)
                ws.append(['Índice', 'Fecha', 'Remitente', 'Destinatarios', 'Asunto', 'Resumen', 'Puntos Resueltos', 'Puntos Pendientes', 'Confianza', 'Concordancia', 'Coherencia'])
                for email in thread.get('emails', []):
                    ws.append([
                        email['index'],
                        email['date'],
                        email['from'],
                        email['to'],
                        email['subject'],
                        email['summary'],
                        email['resolved_points'],
                        email['pending_points'],
                        email['confidence_score'],
                        email.get('concordance', 0),
                        thread.get('coherence', 0)
                    ])
            wb.save(buffer)
        else:
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            elements = []
            for thread in threads:
                label = thread.get('label', 'Hilo')
                data = [['Índice', 'Fecha', 'Remitente', 'Destinatarios', 'Asunto', 'Resumen', 'Puntos Resueltos', 'Puntos Pendientes', 'Confianza', 'Concordancia', 'Coherencia']]
                for email in thread.get('emails', []):
                    data.append([
                        email['index'],
                        email['date'],
                        email['from'],
                        email['to'],
                        email['subject'],
                        email['summary'],
                        email['resolved_points'],
                        email['pending_points'],
                        email['confidence_score'],
                        email.get('concordance', 0),
                        thread.get('coherence', 0)
                    ])
                table = Table(data)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                elements.append(table)
            doc.build(elements)
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"Error exporting threads: {str(e)}", exc_info=True)
        raise

def process_feedback(email_index, query, action, user):
    """Procesa retroalimentación del usuario sobre la relevancia de un correo."""
    logger.info(f"Processing feedback: email_index={email_index}, action={action}, user={user.username}")
    try:
        feedback_collection.insert_one({
            'email_index': email_index,
            'query': query,
            'action': action,
            'user_id': user.username,
            'timestamp': datetime.utcnow()
        })
        
        email = emails_collection.find_one({'index': email_index, 'mailbox_id': {'$in': [mailbox['mailbox_id'] for mailbox in user.mailboxes]}})
        if not email:
            logger.error(f"Email not found for user: {email_index}")
            return
        
        processed_query, _, terms, _, names = process_query(query, return_names=True)
        
        text = f"{email.get('subject', '')} {email.get('summary', '')} {email.get('body', '')}"
        text_vector = tfidf_vectorizer.transform([text or "default_text"])
        summary_score = cosine_similarity(tfidf_vectorizer.transform([query or "default_query"]), text_vector)[0][0]
        terms_count = sum(1 for term in terms for t in term if t.lower() in email.get('relevant_terms', []))
        terms_score = terms_count / max(len([t for g in terms for t in g]), 1)
        subject_score = cosine_similarity(tfidf_vectorizer.transform([query or "default_query"]), tfidf_vectorizer.transform([email.get('subject', '') or "default_subject"]))[0][0]
        thread_count = emails_collection.count_documents({'thread_id': email.get('thread_id'), 'mailbox_id': {'$in': [mailbox['mailbox_id'] for mailbox in user.mailboxes]}})
        thread_score = min(thread_count / 10, 1.0) if email.get('thread_id') else 0.0
        name_score = max(
            [fuzz.partial_ratio(name.lower(), email.get('from', '').lower()) / 100 for name in names] +
            [fuzz.partial_ratio(name.lower(), email.get('to', '').lower()) / 100 for name in names]
        ) if names else 0.0
        
        features = np.array([[summary_score, terms_score, subject_score, thread_score, name_score]])
        label = 1 if action == 'validate' else 0
        
        bayesian_filter.partial_fit(features, [label], classes=[0, 1])
        
        global filter_weights
        try:
            feature_importance = np.abs(bayesian_filter.feature_log_prob_[1] - bayesian_filter.feature_log_prob_[0])
            total = feature_importance.sum()
            if total > 0:
                filter_weights = {
                    'summary': feature_importance[0] / total,
                    'terms': feature_importance[1] / total,
                    'subject': feature_importance[2] / total,
                    'thread_id': feature_importance[3] / total,
                    'names': feature_importance[4] / total
                }
                feedback_collection.update_one(
                    {'type': 'weights', 'user_id': user.username},
                    {'$set': {'weights': filter_weights, 'timestamp': datetime.utcnow()}},
                    upsert=True
                )
                logger.debug(f"Updated weights for user {user.username}: {filter_weights}")
            else:
                logger.warning("Feature importance sum is zero, weights not updated")
        except AttributeError:
            logger.warning("Classifier not yet fitted, skipping weight update")
    except Exception as e:
        logger.error(f"Error processing feedback: {str(e)}", exc_info=True)
        raise