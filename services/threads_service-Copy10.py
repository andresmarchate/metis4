import logging
from logging import handlers
import hashlib
import numpy as np
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.naive_bayes import MultinomialNB
from sklearn.feature_extraction.text import TfidfVectorizer
from io import BytesIO
import openpyxl
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from datetime import datetime, timedelta
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION
from services.nlp_service import process_query, decompress_embedding
from services.cache_service import get_cached_result, cache_result
from fuzzywuzzy import fuzz
import re
import torch
import os
from collections import Counter

torch.cuda.empty_cache()  # Libera memoria caché
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"  # Optimiza la asignación

# Configure logger
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

# Initialize MongoDB and embedding model
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]
feedback_collection = db['feedback']
embedding_model = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')

# Bayesian filter and weights
bayesian_filter = MultinomialNB()
filter_weights = {'summary': 0.2, 'terms': 0.2, 'subject': 0.2, 'thread_id': 0.2, 'names': 0.2}
tfidf_vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')

def analyze_threads(query, user=None):
    """
    Analyze thematic conversation threads based on a natural language query for the given user.
    Returns a list of threads, each with a label and sorted emails.
    """
    logger.info(f"Analyzing threads for query: {query}, user: {user.username if user else 'None'}")
    try:
        # Check cache
        cache_key = f"threads:{user.username if user else 'anonymous'}:{query}"
        query_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
        logger.debug(f"Generated query_hash: {query_hash}")
        cached_result = get_cached_result(query_hash)
        if cached_result:
            logger.info(f"Returning cached threads for query_hash: {query_hash}")
            return cached_result.get('threads', [])

        # Process query
        processed_query, intent, terms, query_embedding, names = process_query(query, return_names=True)
        logger.debug(f"Processed query: intent={intent}, terms={terms}, names={names}")

        # Flatten terms list
        flat_terms = [term for group in terms for term in group]
        logger.debug(f"Flattened terms: {flat_terms}")

        # Fetch candidate emails for the user
        emails = fetch_relevant_emails(query, flat_terms, names, query_embedding, user)
        logger.debug(f"Fetched {len(emails)} candidate emails")
        if not emails:
            logger.warning("No relevant emails found for user")
            return []

        # Generate embeddings for emails
        email_texts = [f"{email.get('subject', '')} {email.get('summary', '')} {email.get('body', '')}" for email in emails]
        email_embeddings = embedding_model.encode(email_texts, convert_to_tensor=True)
        logger.debug(f"Generated email embeddings, device: {email_embeddings.device}")

        # Decompress query embedding
        logger.debug(f"Type of query_embedding before decompression: {type(query_embedding)}")
        query_embedding_decompressed = decompress_embedding(query_embedding)
        if query_embedding_decompressed is None:
            logger.error("Failed to decompress query embedding")
            raise ValueError("Query embedding decompression failed")
        logger.debug(f"Type of query_embedding after decompression: {type(query_embedding_decompressed)}")

        # Convert to tensor
        query_embedding_tensor = torch.tensor(query_embedding_decompressed, dtype=torch.float32).unsqueeze(0)
        logger.debug(f"query_embedding_tensor initial device: {query_embedding_tensor.device}")

        # Move tensors to CPU and convert to NumPy
        query_embedding_np = query_embedding_tensor.cpu().numpy()
        email_embeddings_np = email_embeddings.cpu().numpy()
        logger.debug("Converted tensors to NumPy arrays on CPU")

        # Compute cosine similarity using NumPy arrays
        similarities = cosine_similarity(query_embedding_np, email_embeddings_np).flatten()
        logger.debug(f"Computed similarities: min={similarities.min()}, max={similarities.max()}")

        # Filter emails with similarity above threshold
        similarity_threshold = 0.65  # Aumentado para mayor precisión
        filtered_indices = np.where(similarities > similarity_threshold)[0]
        filtered_emails = [emails[i] for i in filtered_indices]
        filtered_embeddings = email_embeddings_np[filtered_indices]
        logger.debug(f"Filtered to {len(filtered_emails)} emails with similarity > {similarity_threshold}")

        if not filtered_emails:
            logger.warning("No emails passed similarity threshold")
            return []

        # Cluster into threads with improved coherence
        threads = cluster_threads(filtered_emails, filtered_embeddings)
        logger.debug(f"Clustered into {len(threads)} threads")

        # Cache result
        cache_result(query_hash, {'threads': threads})
        logger.info(f"Returning {len(threads)} thematic threads")
        return threads
    except Exception as e:
        logger.error(f"Error analyzing threads: {str(e)}", exc_info=True)
        raise

def fetch_relevant_emails(query, terms, names, query_embedding, user):
    """
    Fetch emails from MongoDB with stricter initial filtering, filtered by user's mailboxes.
    """
    logger.debug(f"Fetching emails with terms: {terms}, names: {names}, user: {user.username if user else 'None'}")
    try:
        if not user:
            raise ValueError("User must be provided for email fetching")

        user_mailboxes = [mailbox['mailbox_id'] for mailbox in user.mailboxes]
        if not user_mailboxes:
            logger.warning(f"No mailboxes found for user: {user.username}")
            return []

        # Build MongoDB query with stricter filtering
        logger.debug(f"Building MongoDB pipeline with terms: {terms}")
        match_conditions = {
            'mailbox_id': {'$in': user_mailboxes},
            '$and': [
                {
                    '$or': [
                        {'subject': {'$regex': '|'.join(terms), '$options': 'i'}},
                        {'summary': {'$regex': '|'.join(terms), '$options': 'i'}},
                        {'body': {'$regex': '|'.join(terms), '$options': 'i'}},
                        {'relevant_terms': {'$in': terms}}
                    ]
                }
            ]
        }
        
        if names:
            match_conditions['$and'].append({
                '$or': [
                    {'from': {'$regex': '|'.join(names), '$options': 'i'}},
                    {'to': {'$regex': '|'.join(names), '$options': 'i'}}
                ]
            })

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
            {'$limit': 500}  # Reducido para mejorar rendimiento
        ]
        
        emails = list(emails_collection.aggregate(pipeline))
        logger.debug(f"Fetched {len(emails)} candidate emails for user")
        return emails
    except Exception as e:
        logger.error(f"Error fetching emails: {str(e)}", exc_info=True)
        raise

def normalize_subject(subject):
    """Normalize email subject by removing 'Re:', 'Fwd:', and extra spaces."""
    if not subject:
        return ""
    subject = re.sub(r'^(re:|fwd:|\[re\]|\[fwd\])\s*', '', subject, flags=re.IGNORECASE)
    subject = re.sub(r'\s+', ' ', subject).strip()
    return subject.lower()

def parse_date(date_str):
    """Parse email date string to datetime."""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return datetime.utcnow()

def cluster_threads(emails, embeddings):
    """
    Cluster emails into thematic threads with improved semantic, temporal, and structural coherence.
    """
    logger.debug("Clustering emails into thematic threads")
    try:
        if len(emails) <= 1:
            logger.debug("Single email detected, returning as individual thread")
            return [{'thread_id': 'single', 'label': 'Hilo Individual', 'emails': emails}]

        # Compute similarity matrix with semantic embeddings
        sim_matrix = cosine_similarity(embeddings)
        logger.debug(f"Similarity matrix shape: {sim_matrix.shape}")

        # Adjust similarity with temporal and structural factors
        for i in range(len(emails)):
            for j in range(i + 1, len(emails)):
                # Temporal factor
                date_i = parse_date(emails[i].get('date', ''))
                date_j = parse_date(emails[j].get('date', ''))
                time_diff = abs((date_i - date_j).total_seconds())
                temporal_factor = np.exp(-time_diff / (86400 * 5))  # Decay ajustado a 5 días

                # Structural factor (thread_id, in_reply_to, references)
                structural_factor = 1.0
                if emails[i].get('thread_id') and emails[i].get('thread_id') == emails[j].get('thread_id'):
                    structural_factor += 0.4  # Más peso a thread_id
                if emails[i].get('in_reply_to') == emails[j].get('index') or emails[j].get('in_reply_to') == emails[i].get('index'):
                    structural_factor += 0.6  # Mayor peso a respuestas directas
                if emails[i].get('references') and emails[j].get('index') in emails[i].get('references', []):
                    structural_factor += 0.5

                sim_matrix[i, j] *= temporal_factor * min(structural_factor, 1.8)  # Cap ajustado
                sim_matrix[j, i] = sim_matrix[i, j]

        # Hierarchical clustering with refined threshold
        clustering = AgglomerativeClustering(n_clusters=None, distance_threshold=0.35, linkage='average')
        labels = clustering.fit_predict(1 - sim_matrix)  # Convert similarity to distance
        logger.debug(f"Clustering labels: {set(labels)}")

        # Group emails by cluster labels
        threads = {}
        for label, email in zip(labels, emails):
            if label not in threads:
                threads[label] = []
            threads[label].append(email)

        # Merge small threads and format
        formatted_threads = merge_small_threads(threads, embeddings[labels])
        logger.debug(f"Final number of threads after merging: {len(formatted_threads)}")

        return formatted_threads
    except Exception as e:
        logger.error(f"Error clustering threads: {str(e)}", exc_info=True)
        raise

def merge_small_threads(threads, embeddings):
    """Merge small threads with high similarity to improve coherence."""
    formatted_threads = []
    thread_list = [(label, emails) for label, emails in threads.items()]
    
    for i, (label, thread_emails) in enumerate(thread_list):
        if len(thread_emails) < 2 and len(thread_list) > 1:  # Merge threads con menos de 2 correos
            best_match_idx = -1
            best_similarity = 0.75  # Umbral más alto para merging
            thread_embedding = np.mean(embeddings[labels == label], axis=0)
            
            for j, (other_label, other_emails) in enumerate(thread_list):
                if i != j and len(other_emails) >= 2:
                    other_embedding = np.mean(embeddings[labels == other_label], axis=0)
                    similarity = cosine_similarity(thread_embedding.reshape(1, -1), other_embedding.reshape(1, -1)).item()
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match_idx = j
            
            if best_match_idx != -1:
                thread_list[best_match_idx][1].extend(thread_emails)
                continue
        
        base_title = generate_thread_label(thread_emails)
        formatted_threads.append({
            'thread_id': f"thread_{label}",
            'label': f"{base_title} ({len(thread_emails)} emails)",
            'emails': sorted(format_emails(thread_emails), key=lambda x: parse_date(x['date']))
        })
        logger.debug(f"Thread {label}: {base_title}, {len(thread_emails)} emails")

    return formatted_threads

def generate_thread_label(emails):
    """
    Generate a base title for the thread based on subjects and dominant terms.
    """
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
    """
    Format emails for thread output, including resolved/pending points.
    """
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
            'confidence_score': email.get('confidence_score', 0.0)
        })
    return formatted

def extract_points(email, point_type):
    """
    Extract resolved or pending points from email body or summary using regex.
    """
    try:
        text = f"{email.get('summary', '')} {email.get('body', '')}".lower()
        pattern = r'resolved:.*?[.!?]' if point_type == 'resolved' else r'pending:.*?[.!?]'
        matches = re.findall(pattern, text, re.IGNORECASE)
        return '; '.join(match.strip() for match in matches) or 'None'
    except Exception:
        logger.error(f"Error extracting {point_type} points", exc_info=True)
        return 'None'

def export_threads(threads, format_type):
    """
    Export threads to Excel or PDF format.
    """
    logger.info(f"Exporting threads to format: {format_type}")
    try:
        buffer = BytesIO()
        if format_type == 'excel':
            wb = openpyxl.Workbook()
            wb.remove(wb.active)
            for thread in threads:
                label = thread.get('label', 'Hilo')[:31].replace(':', '_')
                ws = wb.create_sheet(label)
                ws.append(['Índice', 'Fecha', 'Remitente', 'Destinatarios', 'Asunto', 'Resumen', 'Puntos Resueltos', 'Puntos Pendientes', 'Confianza'])
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
                        email['confidence_score']
                    ])
            wb.save(buffer)
        else:  # PDF
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            elements = []
            for thread in threads:
                label = thread.get('label', 'Hilo')
                data = [['Índice', 'Fecha', 'Remitente', 'Destinatarios', 'Asunto', 'Resumen', 'Puntos Resueltos', 'Puntos Pendientes', 'Confianza']]
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
                        email['confidence_score']
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
    """
    Process user feedback (validate/reject) and update Bayesian filter for the given user.
    """
    logger.info(f"Processing feedback: email_index={email_index}, action={action}, user: {user.username}")
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
        terms_count = sum(1 for term in terms if term.lower() in email.get('relevant_terms', []))
        terms_score = terms_count / max(len(terms), 1)
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