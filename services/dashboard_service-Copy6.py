# Artifact ID: 1a2b3c4d-5e6f-7g8h-9i0j-k1l2m3n4o5p6
# Version: v7w8x9y0-z1a2-3456-v9w0-x1y2z3a4b5
import logging
from logging import handlers
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION
from services.cache_service import get_cached_result, cache_result
from datetime import datetime, timedelta
import re

# Configure logging
logger = logging.getLogger('email_search_app.dashboard_service')
logger.setLevel(logging.DEBUG)
file_handler = handlers.RotatingFileHandler('app.log', maxBytes=10_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s:%(funcName)s] %(message)s'))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
emails_collection = db[MONGO_EMAILS_COLLECTION]

USER_EMAIL = 'andres.m.tirado@gmail.com'

def extract_email(text):
    """Extract email address from a string using regex."""
    if not text or not isinstance(text, str):
        return None
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text, re.IGNORECASE)
    return email_match.group(0) if email_match else None

def format_email_field(name, email):
    """Helper function to format name and email into 'Name <email>' or '<email>'."""
    logger.debug("Formatting email field: name=%s, email=%s", name, email)
    if email:
        name = name.strip() if name else ''
        return f"{name} <{email}>" if name else f"<{email}>"
    return 'N/A'

def format_email_address(address):
    """Format a single email address field."""
    if not address or not isinstance(address, str):
        return 'N/A'
    match = re.match(r'(.*?)\s*(?:<(.+?)>)?$', address, re.IGNORECASE)
    if match:
        name, email = match.groups()
        email = email or extract_email(address)
        return format_email_field(name, email)
    return format_email_field('', extract_email(address)) if extract_email(address) else 'N/A'

def get_dashboard_metrics():
    """Compute dashboard metrics for the user."""
    logger.info("Computing dashboard metrics")
    cache_key = f"dashboard_metrics:{USER_EMAIL}"
    cached_result = get_cached_result(cache_key)
    if cached_result:
        logger.debug(f"Retrieved cached dashboard metrics: {cache_key}")
        return cached_result

    try:
        now = datetime.utcnow()
        periods = {
            'day': {'start': now - timedelta(days=1), 'days': 1},
            'week': {'start': now - timedelta(weeks=1), 'days': 7},
            'month': {'start': now - timedelta(days=30), 'days': 30},
            'year': {'start': now - timedelta(days=365), 'days': 365}
        }

        metrics = {
            'received': {},
            'sent': {},
            'top_senders': {},
            'top_recipients': {},
            'requires_response': {},
            'urgent': {},
            'important': {},
            'advertisement': {},
            'emei': {}
        }

        for period_name, period_info in periods.items():
            start_date = period_info['start']
            days = period_info['days']

            # Base match criteria
            base_match = {
                'to': {'$regex': f'\\b{re.escape(USER_EMAIL)}\\b', '$options': 'i'},
                '$expr': {
                    '$gte': [{'$toDate': '$date'}, start_date]
                }
            }

            # Received emails
            received_count = emails_collection.count_documents(base_match)
            metrics['received'][period_name] = received_count

            # Sent emails
            sent_count = emails_collection.count_documents({
                'from': {'$regex': f'\\b{re.escape(USER_EMAIL)}\\b', '$options': 'i'},
                '$expr': {
                    '$gte': [{'$toDate': '$date'}, start_date]
                }
            })
            metrics['sent'][period_name] = sent_count

            # Top 10 senders
            senders_pipeline = [
                {'$match': base_match},
                {'$group': {
                    '_id': '$from',
                    'count': {'$sum': 1}
                }},
                {'$sort': {'count': -1}},
                {'$limit': 10}
            ]
            senders = list(emails_collection.aggregate(senders_pipeline))
            metrics['top_senders'][period_name] = [
                {'sender': format_email_address(s['_id']), 'count': s['count']}
                for s in senders
            ]

            # Top 10 recipients
            recipients_pipeline = [
                {'$match': {
                    'from': {'$regex': f'\\b{re.escape(USER_EMAIL)}\\b', '$options': 'i'},
                    '$expr': {
                        '$gte': [{'$toDate': '$date'}, start_date]
                    }
                }},
                {'$project': {
                    'to': {'$split': ['$to', ',']}
                }},
                {'$unwind': '$to'},
                {'$group': {
                    '_id': {'$trim': {'input': '$to'}},
                    'count': {'$sum': 1}
                }},
                {'$sort': {'count': -1}},
                {'$limit': 10}
            ]
            recipients = list(emails_collection.aggregate(recipients_pipeline))
            metrics['top_recipients'][period_name] = [
                {'recipient': format_email_address(r['_id']), 'count': r['count']}
                for r in recipients
            ]

            # Classification counts
            for classification in ['requires_response', 'urgent', 'important', 'advertisement']:
                count = emails_collection.count_documents({
                    'to': {'$regex': f'\\b{re.escape(USER_EMAIL)}\\b', '$options': 'i'},
                    '$expr': {
                        '$gte': [{'$toDate': '$date'}, start_date]
                    },
                    classification: True
                })
                metrics[classification][period_name] = count

            # EMEI calculation (normalized per day)
            responded_count = emails_collection.count_documents({
                'to': {'$regex': f'\\b{re.escape(USER_EMAIL)}\\b', '$options': 'i'},
                '$expr': {
                    '$gte': [{'$toDate': '$date'}, start_date]
                },
                'responded': True
            })
            requires_response_count = metrics['requires_response'][period_name]
            total_emails = received_count + sent_count
            emei_raw = total_emails * (responded_count / requires_response_count if requires_response_count > 0 else 0)
            emei_normalized = emei_raw / days
            metrics['emei'][period_name] = round(emei_normalized, 2) if requires_response_count > 0 else 0

        # Validate cumulative counts (except EMEI, which is normalized)
        for metric in ['received', 'sent', 'requires_response', 'urgent', 'important', 'advertisement']:
            counts = metrics[metric]
            if not (counts['year'] >= counts['month'] >= counts['week'] >= counts['day']):
                logger.warning(f"Non-cumulative counts detected for {metric}: {counts}")

        cache_result(cache_key, metrics)
        logger.info("Dashboard metrics computed successfully")
        return metrics
    except Exception as e:
        logger.error(f"Error computing dashboard metrics: {str(e)}", exc_info=True)
        return {
            'error': str(e),
            'received': {},
            'sent': {},
            'top_senders': {},
            'top_recipients': {},
            'requires_response': {},
            'urgent': {},
            'important': {},
            'advertisement': {},
            'emei': {}
        }

def get_email_list(metric, period):
    """Fetch list of emails for a specific metric and period."""
    logger.info(f"Fetching email list for metric: {metric}, period: {period}")
    try:
        now = datetime.utcnow()
        periods = {
            'day': now - timedelta(days=1),
            'week': now - timedelta(weeks=1),
            'month': now - timedelta(days=30),
            'year': now - timedelta(days=365)
        }
        start_date = periods.get(period, now)

        match_criteria = {
            '$expr': {
                '$gte': [{'$toDate': '$date'}, start_date]
            }
        }

        if metric == 'received':
            match_criteria['to'] = {'$regex': f'\\b{re.escape(USER_EMAIL)}\\b', '$options': 'i'}
        elif metric == 'sent':
            match_criteria['from'] = {'$regex': f'\\b{re.escape(USER_EMAIL)}\\b', '$options': 'i'}
        else:
            match_criteria['to'] = {'$regex': f'\\b{re.escape(USER_EMAIL)}\\b', '$options': 'i'}
            match_criteria[metric] = True

        pipeline = [
            {'$match': match_criteria},
            {
                '$project': {
                    '_id': 0,
                    'from': 1,
                    'to': 1,
                    'subject': 1,
                    'date': 1,
                    'summary': 1,
                    'urgent': 1,
                    'important': 1,
                    'advertisement': 1,
                    'requires_response': 1,
                    'responded': 1
                }
            },
            {'$limit': 100}
        ]

        emails = list(emails_collection.aggregate(pipeline))
        
        # Format from and to fields
        for email in emails:
            email['from'] = format_email_address(email.get('from', ''))
            email['to'] = format_email_address(email.get('to', ''))

        logger.info(f"Fetched {len(emails)} emails for metric: {metric}, period: {period}")
        return {'emails': emails}
    except Exception as e:
        logger.error(f"Error fetching email list: {str(e)}", exc_info=True)
        return {'error': str(e), 'emails': []}