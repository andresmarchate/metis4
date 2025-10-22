# Artifact ID: a3b4c5d6-e7f8-g9h0-i1j2-k3l4m5n6o7
# Version: f9g0h1i2-j3k4-l5m6-n7o8-p9q0r1s2t3
from pymongo import MongoClient
from sklearn.naive_bayes import MultinomialNB
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from fuzzywuzzy import fuzz
import numpy as np
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION
import logging
from datetime import datetime

# Configure logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Initialize MongoDB and TF-IDF
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]
feedback_collection = db['feedback']
tfidf_vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')

def extract_features(email, terms, names, query):
    """
    Extract features for Bayesian filter training.
    """
    text = f"{email.get('subject', '')} {email.get('summary', '')} {email.get('body', '')}".strip()
    text_vector = tfidf_vectorizer.transform([text])
    query_vector = tfidf_vectorizer.transform([query])
    
    summary_score = cosine_similarity(query_vector, text_vector)[0][0]
    terms_count = sum(1 for term in terms if term.lower() in email.get('relevant_terms', []))
    terms_score = terms_count / max(len(terms), 1)
    subject_score = cosine_similarity(query_vector, tfidf_vectorizer.transform([email.get('subject', '')]))[0][0]
    thread_count = emails_collection.count_documents({'thread_id': email.get('thread_id')})
    thread_score = min(thread_count / 10, 1.0) if email.get('thread_id') else 0.0
    name_score = max(
        [fuzz.partial_ratio(name.lower(), email.get('from', '').lower()) / 100 for name in names] +
        [fuzz.partial_ratio(name.lower(), email.get('to', '').lower()) / 100 for name in names]
    ) if names else 0.0
    
    return [summary_score, terms_score, subject_score, thread_score, name_score]

def initialize_bayesian_filter():
    """
    Initialize Bayesian filter with supervised learning using 80/20 split.
    """
    logger.info("Initializing Bayesian filter")
    try:
        # First pass: Collect texts and validate data
        texts = []
        queries = []
        groups_data = []
        group_count = 0
        
        # Group emails by thread_id or subject
        groups = emails_collection.aggregate([
            {
                '$group': {
                    '_id': {'$ifNull': ['$thread_id', '$subject']},
                    'emails': {'$push': '$$ROOT'},
                    'count': {'$sum': 1}
                }
            },
            {'$match': {'count': {'$gte': 2}}}  # Only groups with multiple emails
        ])
        
        for group in groups:
            group_count += 1
            emails = group['emails']
            if len(emails) < 2:
                logger.debug(f"Skipping group with {len(emails)} emails")
                continue
            
            # Simulate query
            query = emails[0].get('subject', '') or ' '.join(emails[0].get('relevant_terms', [])) or "default_query"
            terms = emails[0].get('relevant_terms', [])
            queries.append(query)
            
            # Collect texts
            for email in emails:
                text = f"{email.get('subject', '')} {email.get('summary', '')} {email.get('body', '')}".strip()
                subject = email.get('subject', '').strip()
                if text:
                    texts.append(text)
                if subject:
                    texts.append(subject)
                if not text and not subject:
                    logger.debug(f"Email {email.get('index', 'N/A')} has no text content")
            
            # Store group data
            groups_data.append({'emails': emails, 'query': query, 'terms': terms})
        
        logger.info(f"Processed {group_count} groups, collected {len(texts)} texts, {len(queries)} queries")
        
        # Fit TF-IDF vectorizer
        if texts or queries:
            all_texts = texts + queries
            tfidf_vectorizer.fit(all_texts)
            logger.info("TF-IDF vectorizer fitted with corpus")
        else:
            logger.warning("No valid texts or queries found, using fallback corpus")
            tfidf_vectorizer.fit(["default_text"])  # Fallback to ensure fitting
        
        # Second pass: Extract features and train filter
        bayesian_filter = MultinomialNB()
        features = []
        labels = []
        
        for group_data in groups_data:
            emails = group_data['emails']
            query = group_data['query']
            terms = group_data['terms']
            names = []  # Assume no names for initialization
            
            # Split 80/20
            train_size = int(0.8 * len(emails))
            train_emails = emails[:train_size]
            test_emails = emails[train_size:]
            
            # Training data (assume relevant)
            for email in train_emails:
                feature_vector = extract_features(email, terms, names, query)
                features.append(feature_vector)
                labels.append(1)  # Relevant
            
            # Test data (assume some irrelevant)
            for email in test_emails:
                feature_vector = extract_features(email, terms, names, query)
                features.append(feature_vector)
                labels.append(0)  # Irrelevant for testing
        
        # Train filter
        if features:
            features = np.array(features)
            labels = np.array(labels)
            bayesian_filter.fit(features, labels)
            logger.info("Bayesian filter trained with initial data")
            
            # Store initial weights
            feature_importance = np.abs(bayesian_filter.feature_log_prob_[1] - bayesian_filter.feature_log_prob_[0])
            total = feature_importance.sum()
            if total > 0:
                weights = {
                    'summary': feature_importance[0] / total,
                    'terms': feature_importance[1] / total,
                    'subject': feature_importance[2] / total,
                    'thread_id': feature_importance[3] / total,
                    'names': feature_importance[4] / total
                }
                feedback_collection.update_one(
                    {'type': 'weights'},
                    {'$set': {'weights': weights, 'timestamp': datetime.utcnow()}},
                    upsert=True
                )
                logger.info(f"Initial weights stored: {weights}")
            else:
                logger.warning("Feature importance sum is zero, weights not stored")
        else:
            logger.warning("No sufficient data for training")
    except Exception as e:
        logger.error(f"Error initializing Bayesian filter: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    initialize_bayesian_filter()