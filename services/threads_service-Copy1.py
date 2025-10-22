# Artifact ID: daf59535-bcd6-417d-bf04-4ef50433faef
# Version: e7f8g9h0-i1j2-k3l4-m5n6-o7p8q9r0
import logging
from logging import handlers
import hashlib
import pickle
import numpy as np
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from sklearn.naive_bayes import MultinomialNB
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity
from io import BytesIO
import openpyxl
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from datetime import datetime
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION
from services.nlp_service import process_query
from services.cache_service import get_cached_result, cache_result

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
embedding_model = SentenceTransformer('distiluse-base-multilingual-cased-v2')

def analyze_threads(query):
    """
    Analyze thematic conversation threads based on a natural language query.
    Returns a list of threads, each with a label and sorted emails.
    """
    logger.info(f"Analyzing threads for query: {query}")
    try:
        # Check cache
        cache_key = f"threads:{query}"
        query_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
        logger.debug(f"Generated query_hash: {query_hash}")
        cached_result = get_cached_result(query_hash)
        if cached_result:
            logger.info(f"Returning cached threads for query_hash: {query_hash}")
            return cached_result.get('threads', [])

        # Process query
        processed_query, intent, terms, query_embedding = process_query(query)
        # Fallback intent for advertising-related queries
        if 'publicidad' in terms and intent == 'medicina_y_salud':
            intent = 'publicidad'
            logger.debug(f"Overriding intent to 'publicidad' due to term 'publicidad'")
        logger.debug(f"Processed query: intent={intent}, terms={terms}")

        # Fetch candidate emails
        emails = fetch_relevant_emails(query, terms, query_embedding)
        logger.debug(f"Fetched {len(emails)} candidate emails")
        if not emails:
            logger.warning("No relevant emails found")
            return []

        # Score emails with Bayesian classifier
        scored_emails = score_emails(emails, terms)
        
        # Filter emails with relevance score > 0.5
        relevant_emails = [email for email in scored_emails if email['relevance_score'] > 0.5]
        logger.debug(f"Filtered to {len(relevant_emails)} relevant emails")
        if not relevant_emails:
            logger.warning("No emails passed relevance threshold")
            return []

        # Cluster into threads
        threads = cluster_threads(relevant_emails)
        logger.debug(f"Clustered into {len(threads)} threads")
        
        # Cache result
        cache_result(query_hash, {'threads': threads})
        logger.info(f"Returning {len(threads)} thematic threads")
        return threads
    except Exception as e:
        logger.error(f"Error analyzing threads: {str(e)}", exc_info=True)
        raise

def fetch_relevant_emails(query, terms, query_embedding):
    """
    Fetch emails from MongoDB that match query terms.
    """
    logger.debug(f"Fetching emails with terms: {terms}")
    try:
        # Build MongoDB query requiring all terms
        pipeline = [
            {
                '$match': {
                    '$and': [
                        {
                            '$or': [
                                {'subject': {'$regex': term, '$options': 'i'}},
                                {'summary': {'$regex': term, '$options': 'i'}},
                                {'body': {'$regex': term, '$options': 'i'}},
                                {'relevant_terms': term}
                            ]
                        } for term in terms
                    ]
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
                    'in_reply_to': 1,
                    'references': 1,
                    'embedding': 1,
                    'relevant_terms': 1
                }
            },
            {'$limit': 50}  # Reduce limit for performance
        ]
        
        emails = list(emails_collection.aggregate(pipeline))
        logger.debug(f"Fetched {len(emails)} candidate emails")

        # Skip semantic similarity filtering due to invalid embeddings
        logger.warning("Skipping semantic similarity filtering due to invalid embeddings")
        return emails
    except Exception as e:
        logger.error(f"Error fetching emails: {str(e)}", exc_info=True)
        raise

def score_emails(emails, terms):
    """
    Score emails using a Bayesian classifier based on text content.
    """
    logger.debug("Scoring emails with Bayesian classifier")
    try:
        # Prepare text data
        texts = [
            f"{email.get('subject', '')} {email.get('summary', '')} {email.get('body', '')}"
            for email in emails
        ]
        
        # Vectorize text
        vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
        X = vectorizer.fit_transform(texts)
        
        # Create pseudo-labels (1 if all terms present, 0 otherwise)
        y = [1 if all(term.lower() in text.lower() for term in terms) else 0 for text in texts]
        
        # Check if single class
        unique_labels = set(y)
        if len(unique_labels) == 1:
            label = unique_labels.pop()
            logger.debug(f"Single class detected: {label}")
            for email in emails:
                email['relevance_score'] = 1.0 if label == 1 else 0.0
            return emails
        
        # Train Bayesian classifier
        classifier = MultinomialNB()
        classifier.fit(X, y)
        
        # Predict probabilities
        probabilities = classifier.predict_proba(X)
        if probabilities.shape[1] == 1:
            logger.warning("Classifier returned single probability column; using fallback scoring")
            for email, text in zip(emails, texts):
                email['relevance_score'] = 1.0 if all(term.lower() in text.lower() for term in terms) else 0.0
        else:
            for email, prob in zip(emails, probabilities[:, 1]):
                email['relevance_score'] = prob
        
        return emails
    except Exception as e:
        logger.error(f"Error scoring emails: {str(e)}", exc_info=True)
        logger.warning("Falling back to term-based scoring")
        for email, text in zip(emails, texts):
            email['relevance_score'] = 1.0 if all(term.lower() in text.lower() for term in terms) else 0.0
        return emails

def cluster_threads(emails):
    """
    Cluster emails into thematic threads using metadata (reply chains).
    """
    logger.debug("Clustering emails into thematic threads")
    try:
        # Group by reply chains using metadata
        reply_chains = {}
        for email in emails:
            chain_id = email.get('in_reply_to') or email.get('index')
            if chain_id not in reply_chains:
                reply_chains[chain_id] = []
            reply_chains[chain_id].append(email)
        
        # Skip embedding-based clustering due to invalid embeddings
        clusters = {'cluster_0': [email for email in emails if not email.get('in_reply_to')]}
        
        # Merge reply chains and clusters
        threads = []
        thread_id = 0
        
        # Process reply chains
        for chain_id, chain_emails in reply_chains.items():
            if len(chain_emails) > 1:  # Only consider chains with replies
                label = generate_thread_label(chain_emails)
                threads.append({
                    'thread_id': f"thread_{thread_id}",
                    'label': label,
                    'emails': sorted(format_emails(chain_emails), key=lambda x: x['date'])
                })
                thread_id += 1
        
        # Process clusters
        for cluster_id, cluster_emails in clusters.items():
            if cluster_emails:
                label = generate_thread_label(cluster_emails)
                threads.append({
                    'thread_id': cluster_id,
                    'label': label,
                    'emails': sorted(format_emails(cluster_emails), key=lambda x: x['date'])
                })
        
        return threads
    except Exception as e:
        logger.error(f"Error clustering threads: {str(e)}", exc_info=True)
        raise

def generate_thread_label(emails):
    """
    Generate a label for a thread based on dominant terms.
    """
    try:
        # Combine relevant terms
        all_terms = []
        for email in emails:
            terms = email.get('relevant_terms', [])
            if terms:
                all_terms.extend(terms)
        
        if not all_terms:
            return "Hilo Sin Etiqueta"
        
        # Count term frequency
        from collections import Counter
        term_counts = Counter(all_terms)
        top_terms = [term for term, count in term_counts.most_common(3)]
        return "Hilo: " + ", ".join(top_terms)
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
            'pending_points': pending_points
        })
    return formatted

def extract_points(email, point_type):
    """
    Extract resolved or pending points from email body or summary using regex.
    """
    try:
        text = f"{email.get('summary', '')} {email.get('body', '')}".lower()
        import re
        if point_type == 'resolved':
            pattern = r'resolved:.*?[.!?]'
        else:  # pending
            pattern = r'pending:.*?[.!?]'
        
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
            wb.remove(wb.active)  # Remove default sheet
            for thread in threads:
                label = thread.get('label', 'Hilo')[:31].replace(':', '_')  # Excel sheet name limit
                ws = wb.create_sheet(label)
                ws.append(['Índice', 'Fecha', 'Remitente', 'Destinatarios', 'Asunto', 'Resumen', 'Puntos Resueltos', 'Puntos Pendientes'])
                for email in thread.get('emails', []):
                    ws.append([
                        email['index'],
                        email['date'],
                        email['from'],
                        email['to'],
                        email['subject'],
                        email['summary'],
                        email['resolved_points'],
                        email['pending_points']
                    ])
            wb.save(buffer)
        else:  # PDF
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            elements = []
            for thread in threads:
                label = thread.get('label', 'Hilo')
                data = [['Índice', 'Fecha', 'Remitente', 'Destinatarios', 'Asunto', 'Resumen', 'Puntos Resueltos', 'Puntos Pendientes']]
                for email in thread.get('emails', []):
                    data.append([
                        email['index'],
                        email['date'],
                        email['from'],
                        email['to'],
                        email['subject'],
                        email['summary'],
                        email['resolved_points'],
                        email['pending_points']
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