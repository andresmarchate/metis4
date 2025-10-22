# Artifact ID: daf59535-bcd6-417d-bf04-4ef50433faef
# Version: w8x9y0z1-a2b3-c4d5-e6f7-g8h9i0j1
import logging
from logging import handlers
import hashlib
import pickle
import numpy as np
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from sklearn.naive_bayes import MultinomialNB
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from io import BytesIO
import openpyxl
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from datetime import datetime, timedelta
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION
from services.nlp_service import process_query
from services.cache_service import get_cached_result, cache_result
from fuzzywuzzy import fuzz
import re

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
embedding_model = SentenceTransformer('distiluse-base-multilingual-cased-v2')

# Bayesian filter and weights
bayesian_filter = MultinomialNB()
filter_weights = {'summary': 0.2, 'terms': 0.2, 'subject': 0.2, 'thread_id': 0.2, 'names': 0.2}
tfidf_vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')

def analyze_threads(query, user_id=None):
    """
    Analyze thematic conversation threads based on a natural language query.
    Returns a list of threads, each with a label and sorted emails.
    """
    logger.info(f"Analyzing threads for query: {query}")
    try:
        # Check cache
        cache_key = f"threads:{query}:{user_id or 'anonymous'}"
        query_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
        logger.debug(f"Generated query_hash: {query_hash}")
        cached_result = get_cached_result(query_hash)
        if cached_result:
            logger.info(f"Returning cached threads for query_hash: {query_hash}")
            return cached_result.get('threads', [])

        # Process query
        processed_query, intent, terms, query_embedding, names = process_query(query, return_names=True)
        logger.debug(f"Processed query: intent={intent}, terms={terms}, names={names}")

        # Fetch candidate emails
        emails = fetch_relevant_emails(query, terms, names, query_embedding)
        logger.debug(f"Fetched {len(emails)} candidate emails")
        if not emails:
            logger.warning("No relevant emails found")
            return []

        # Score emails with multi-factor scoring
        scored_emails = score_emails(emails, terms, names, query)
        
        # Filter top 100 emails
        top_emails = sorted(scored_emails, key=lambda x: x['confidence_score'], reverse=True)[:100]
        logger.debug(f"Filtered to {len(top_emails)} top emails")
        if not top_emails:
            logger.warning("No emails passed relevance threshold")
            return []

        # Cluster into threads
        threads = cluster_threads(top_emails)
        logger.debug(f"Clustered into {len(threads)} threads")
        
        # Cache result
        cache_result(query_hash, {'threads': threads})
        logger.info(f"Returning {len(threads)} thematic threads")
        return threads
    except Exception as e:
        logger.error(f"Error analyzing threads: {str(e)}", exc_info=True)
        raise

def fetch_relevant_emails(query, terms, names, query_embedding):
    """
    Fetch emails from MongoDB with multi-factor scoring.
    """
    logger.debug(f"Fetching emails with terms: {terms}, names: {names}")
    try:
        # Build MongoDB query for initial filtering
        pipeline = [
            {
                '$match': {
                    '$or': [
                        {'subject': {'$regex': '|'.join(terms), '$options': 'i'}},
                        {'summary': {'$regex': '|'.join(terms), '$options': 'i'}},
                        {'body': {'$regex': '|'.join(terms), '$options': 'i'}},
                        {'relevant_terms': {'$in': terms}}
                    ] + ([{'from': {'$regex': '|'.join(names), '$options': 'i'}}, {'to': {'$regex': '|'.join(names), '$options': 'i'}}] if names else [])
                }
            },
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
            {'$limit': 1000}  # Initial limit for performance
        ]
        
        emails = list(emails_collection.aggregate(pipeline))
        logger.debug(f"Fetched {len(emails)} candidate emails")
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

def score_subject_similarity(subject1, subject2, vectorizer):
    """Compute TF-IDF similarity between two subjects."""
    if not subject1 or not subject2:
        return 0.0
    norm_subj1 = normalize_subject(subject1) or "default_subject"
    norm_subj2 = normalize_subject(subject2) or "default_subject"
    if norm_subj1 == norm_subj2:
        return 1.0
    vectors = vectorizer.transform([norm_subj1, norm_subj2])
    return cosine_similarity(vectors[0], vectors[1])[0][0]

def score_content_similarity(email1, email2, vectorizer):
    """Compute TF-IDF similarity between email summaries."""
    text1 = f"{email1.get('summary', '')} {email1.get('body', '')}".strip() or "default_text"
    text2 = f"{email2.get('summary', '')} {email2.get('body', '')}".strip() or "default_text"
    vectors = vectorizer.transform([text1, text2])
    return cosine_similarity(vectors[0], vectors[1])[0][0]

def parse_date(date_str):
    """Parse email date string to datetime."""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return datetime.utcnow()

def score_emails(emails, terms, names, query):
    """
    Score emails based on summary, terms, subject, thread_id, and names.
    """
    logger.debug("Scoring emails with multi-factor approach")
    try:
        # Prepare text data
        texts = [f"{email.get('subject', '')} {email.get('summary', '')} {email.get('body', '')}" for email in emails]
        query_vector = tfidf_vectorizer.fit_transform([query])
        text_vectors = tfidf_vectorizer.transform(texts)
        
        # Compute scores
        for email, text_vector in zip(emails, text_vectors):
            scores = {}
            # Summary score (TF-IDF similarity)
            scores['summary'] = cosine_similarity(query_vector, text_vector)[0][0]
            
            # Relevant terms score (count matches)
            terms_count = sum(1 for term in terms if term.lower() in email.get('relevant_terms', []))
            scores['terms'] = terms_count / max(len(terms), 1)
            
            # Subject score (TF-IDF similarity)
            subject_vector = tfidf_vectorizer.transform([email.get('subject', '')])
            scores['subject'] = cosine_similarity(query_vector, subject_vector)[0][0]
            
            # Thread-ID score (group coherence)
            thread_id = email.get('thread_id', '')
            thread_count = sum(1 for e in emails if e.get('thread_id') == thread_id)
            scores['thread_id'] = min(thread_count / 10, 1.0) if thread_id else 0.0
            
            # Names score (fuzzy matching)
            if names:
                name_scores = []
                for name in names:
                    from_score = fuzz.partial_ratio(name.lower(), email.get('from', '').lower()) / 100
                    to_score = fuzz.partial_ratio(name.lower(), email.get('to', '').lower()) / 100
                    name_scores.extend([from_score, to_score])
                scores['names'] = max(name_scores) if name_scores else 0.0
            else:
                scores['names'] = 0.0
            
            # Confidence index
            confidence = sum(filter_weights[factor] * score for factor, score in scores.items())
            email['confidence_score'] = confidence
            email['factor_scores'] = scores
        
        return emails
    except Exception as e:
        logger.error(f"Error scoring emails: {str(e)}", exc_info=True)
        raise

def cluster_threads(emails):
    """
    Cluster emails into thematic threads using metadata and semantic similarity.
    """
    logger.debug("Clustering emails into thematic threads")
    try:
        # Initialize vectorizer for subject similarity
        subject_vectorizer = TfidfVectorizer(max_features=500, stop_words='english')
        
        # Collect subjects for fitting
        subjects = [normalize_subject(email.get('subject', '')) or "default_subject" for email in emails]
        logger.debug(f"Collected {len(subjects)} subjects for vectorizer fitting")
        subject_vectorizer.fit(subjects)
        logger.debug("Subject vectorizer fitted")
        
        # Step 1: Group by header-based relationships
        reply_chains = {}
        for email in emails:
            # Primary key: references or thread_id
            refs = email.get('references', []) or [email.get('thread_id', '')] if email.get('thread_id') else []
            in_reply_to = email.get('in_reply_to', '')
            chain_id = None
            
            # Check references
            for ref in refs:
                if ref:
                    chain_id = ref
                    break
            
            # Fallback to in_reply_to
            if not chain_id and in_reply_to:
                chain_id = in_reply_to
            
            # Fallback to subject-based key
            if not chain_id:
                chain_id = normalize_subject(email.get('subject', '')) or email.get('index', '')
            
            if chain_id not in reply_chains:
                reply_chains[chain_id] = []
            reply_chains[chain_id].append(email)
            logger.debug(f"Email {email.get('index', 'N/A')}: chain_id={chain_id}, thread_id={email.get('thread_id', '')}, in_reply_to={in_reply_to}, refs={refs[:2]}")
        
        # Step 2: Merge chains by subject similarity and temporal proximity
        threads = []
        processed_chains = set()
        similarity_threshold = 0.8
        time_window = timedelta(days=7)
        
        for chain_id, chain_emails in reply_chains.items():
            if chain_id in processed_chains:
                continue
            
            current_thread = chain_emails.copy()
            processed_chains.add(chain_id)
            
            # Compare with other chains
            for other_id, other_emails in reply_chains.items():
                if other_id in processed_chains or other_id == chain_id:
                    continue
                
                # Check subject similarity
                chain_subject = normalize_subject(chain_emails[0].get('subject', ''))
                other_subject = normalize_subject(other_emails[0].get('subject', ''))
                subj_sim = score_subject_similarity(chain_subject, other_subject, subject_vectorizer)
                
                # Check temporal proximity
                chain_date = parse_date(chain_emails[0].get('date', ''))
                other_date = parse_date(other_emails[0].get('date', ''))
                time_diff = abs(chain_date - other_date)
                
                # Check content similarity as tiebreaker
                content_sim = score_content_similarity(chain_emails[0], other_emails[0], tfidf_vectorizer)
                
                if subj_sim > similarity_threshold and time_diff <= time_window and content_sim > 0.5:
                    current_thread.extend(other_emails)
                    processed_chains.add(other_id)
                    logger.debug(f"Merged chains: {chain_id} with {other_id}, subj_sim={subj_sim:.2f}, time_diff={time_diff}, content_sim={content_sim:.2f}")
            
            threads.append(current_thread)
        
        # Step 3: Format threads
        formatted_threads = []
        thread_id = 0
        for thread_emails in threads:
            if thread_emails:
                label = generate_thread_label(thread_emails)
                formatted_threads.append({
                    'thread_id': f"thread_{thread_id}",
                    'label': label,
                    'emails': sorted(format_emails(thread_emails), key=lambda x: x['date'])
                })
                thread_id += 1
                logger.debug(f"Thread {thread_id}: {label}, {len(thread_emails)} emails")
        
        return formatted_threads
    except Exception as e:
        logger.error(f"Error clustering threads: {str(e)}", exc_info=True)
        raise

def generate_thread_label(emails):
    """
    Generate a label for a thread based on dominant terms and subject.
    """
    try:
        # Combine subjects and terms
        subjects = [normalize_subject(email.get('subject', '')) for email in emails]
        all_terms = []
        for email in emails:
            all_terms.extend(email.get('relevant_terms', []))
        
        # Use TF-IDF for subjects
        top_terms = []
        if subjects and any(subjects):
            subject_vectorizer = TfidfVectorizer(max_features=500, stop_words='english')
            subject_vectors = subject_vectorizer.fit_transform([s for s in subjects if s])
            feature_names = subject_vectorizer.get_feature_names_out()
            top_indices = np.argsort(subject_vectors.sum(axis=0).A1)[-3:]
            top_terms.extend(feature_names[i] for i in top_indices)
        
        # Add dominant terms
        from collections import Counter
        term_counts = Counter(all_terms)
        top_terms.extend([term for term, _ in term_counts.most_common(3)])
        
        # Clean and combine
        unique_terms = list(dict.fromkeys(top_terms))[:3]
        return "Hilo: " + ", ".join(unique_terms) if unique_terms else "Hilo Sin Etiqueta"
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
        import re
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

def process_feedback(email_index, query, action, user_id):
    """
    Process user feedback (validate/reject) and update Bayesian filter.
    """
    logger.info(f"Processing feedback: email_index={email_index}, action={action}")
    try:
        # Store feedback
        feedback_collection.insert_one({
            'email_index': email_index,
            'query': query,
            'action': action,
            'user_id': user_id or 'anonymous',
            'timestamp': datetime.utcnow()
        })
        
        # Retrieve email
        email = emails_collection.find_one({'index': email_index})
        if not email:
            logger.error(f"Email not found: {email_index}")
            return
        
        # Extract features
        processed_query, _, terms, _, names = process_query(query, return_names=True)
        
        text = f"{email.get('subject', '')} {email.get('summary', '')} {email.get('body', '')}"
        text_vector = tfidf_vectorizer.transform([text or "default_text"])
        summary_score = cosine_similarity(tfidf_vectorizer.transform([query or "default_query"]), text_vector)[0][0]
        terms_count = sum(1 for term in terms if term.lower() in email.get('relevant_terms', []))
        terms_score = terms_count / max(len(terms), 1)
        subject_score = cosine_similarity(tfidf_vectorizer.transform([query or "default_query"]), tfidf_vectorizer.transform([email.get('subject', '') or "default_subject"]))[0][0]
        thread_count = emails_collection.count_documents({'thread_id': email.get('thread_id')})
        thread_score = min(thread_count / 10, 1.0) if email.get('thread_id') else 0.0
        name_score = max(
            [fuzz.partial_ratio(name.lower(), email.get('from', '').lower()) / 100 for name in names] +
            [fuzz.partial_ratio(name.lower(), email.get('to', '').lower()) / 100 for name in names]
        ) if names else 0.0
        
        # Feature vector
        features = np.array([[summary_score, terms_score, subject_score, thread_score, name_score]])
        label = 1 if action == 'validate' else 0
        
        # Incremental training
        bayesian_filter.partial_fit(features, [label], classes=[0, 1])
        
        # Update weights
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
                    {'type': 'weights'},
                    {'$set': {'weights': filter_weights, 'timestamp': datetime.utcnow()}},
                    upsert=True
                )
                logger.debug(f"Updated weights: {filter_weights}")
            else:
                logger.warning("Feature importance sum is zero, weights not updated")
        except AttributeError:
            logger.warning("Classifier not yet fitted, skipping weight update")
    except Exception as e:
        logger.error(f"Error processing feedback: {str(e)}", exc_info=True)
        raise