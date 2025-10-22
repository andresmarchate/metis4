import logging
from logging import handlers
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_EMAILS_COLLECTION
from services.cache_service import get_cached_result, cache_result
from datetime import datetime, timedelta
import re
import base64
import urllib.parse
from flask_login import current_user

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

def format_email_field_with_fallback(field, email_field):
    """Format email field with fallback to email_field, mimicking search_service.py logic."""
    logger.debug("Input to format_email_field_with_fallback: field=%s, email_field=%s", field, email_field)
    if not field or not isinstance(field, str):
        logger.debug("Field is empty or not a string, returning 'N/A'")
        return 'N/A'
    email = email_field or extract_email(field)
    logger.debug("Extracted email: %s", email)
    match = re.match(r'(.*)\s*<(.*@.*)>', field, re.IGNORECASE) if isinstance(field, str) else None
    if match:
        name, email_from_field = match.groups()
        logger.debug("Regex match: name=%s, email_from_field=%s", name, email_from_field)
        formatted = format_email_field(name, email_from_field)
        logger.debug("Formatted output: %s", formatted)
        return formatted
    elif email:
        name = field if field and not extract_email(field) else ''
        formatted = format_email_field(name, email)
        logger.debug("Using extracted email: name=%s, email=%s, formatted=%s", name, email, formatted)
        return formatted
    elif field and '@' in field:
        formatted = format_email_field('', field)
        logger.debug("Field contains email: formatted=%s", formatted)
        return formatted
    logger.debug("No valid email found, returning 'N/A'")
    return 'N/A'

def get_dashboard_metrics():
    """Compute dashboard metrics for the authenticated user."""
    logger.info("Computing dashboard metrics for user: %s", current_user.username)
    cache_key = f"dashboard_metrics:{current_user.username}"
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

        # Obtener los buzones del usuario autenticado
        user_mailboxes = [mailbox['mailbox_id'] for mailbox in current_user.mailboxes]
        if not user_mailboxes:
            logger.warning("No mailboxes found for user: %s", current_user.username)
            return {
                'received': {p: 0 for p in periods},
                'sent': {p: 0 for p in periods},
                'top_senders': {p: [] for p in periods},
                'top_recipients': {p: [] for p in periods},
                'requires_response': {p: 0 for p in periods},
                'urgent': {p: 0 for p in periods},
                'important': {p: 0 for p in periods},
                'advertisement': {p: 0 for p in periods},
                'emei': {p: 0 for p in periods}
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

            # Base match criteria for received emails
            base_match = {
                'mailbox_id': {'$in': user_mailboxes},
                'to': {'$in': user_mailboxes},
                '$expr': {
                    '$gte': [{'$toDate': '$date'}, start_date]
                }
            }

            # Received emails
            received_count = emails_collection.count_documents(base_match)
            metrics['received'][period_name] = received_count

            # Sent emails
            sent_count = emails_collection.count_documents({
                'mailbox_id': {'$in': user_mailboxes},
                'from': {'$in': user_mailboxes},
                '$expr': {
                    '$gte': [{'$toDate': '$date'}, start_date]
                }
            })
            metrics['sent'][period_name] = sent_count

            # Top 10 senders
            senders_pipeline = [
                {'$match': base_match},
                {'$group': {
                    '_id': {
                        'from': '$from',
                        'from_email': {'$ifNull': ['$from_email', '']}
                    },
                    'count': {'$sum': 1}
                }},
                {'$sort': {'count': -1}},
                {'$limit': 10}
            ]
            senders = list(emails_collection.aggregate(senders_pipeline))
            logger.debug("Raw senders data: %s", senders)
            metrics['top_senders'][period_name] = [
                {
                    'sender': format_email_field_with_fallback(s['_id']['from'], s['_id']['from_email']),
                    'count': s['count']
                }
                for s in senders
            ]
            logger.debug("Formatted top_senders for %s: %s", period_name, metrics['top_senders'][period_name])

            # Top 10 recipients
            recipients_pipeline = [
                {'$match': {
                    'mailbox_id': {'$in': user_mailboxes},
                    'from': {'$in': user_mailboxes},
                    '$expr': {
                        '$gte': [{'$toDate': '$date'}, start_date]
                    }
                }},
                {'$project': {
                    'to_array': {'$split': ['$to', ',']},
                    'to_email_array': {'$ifNull': ['$to_email', '']}
                }},
                {'$unwind': '$to_array'},
                {'$group': {
                    '_id': {
                        'to': {'$trim': {'input': '$to_array'}},
                        'to_email': '$to_email_array'
                    },
                    'count': {'$sum': 1}
                }},
                {'$sort': {'count': -1}},
                {'$limit': 10}
            ]
            recipients = list(emails_collection.aggregate(recipients_pipeline))
            logger.debug("Raw recipients data: %s", recipients)
            metrics['top_recipients'][period_name] = [
                {
                    'recipient': format_email_field_with_fallback(r['_id']['to'], r['_id']['to_email']),
                    'count': r['count']
                }
                for r in recipients
            ]
            logger.debug("Formatted top_recipients for %s: %s", period_name, metrics['top_recipients'][period_name])

            # Classification counts
            for classification in ['requires_response', 'urgent', 'important', 'advertisement']:
                count = emails_collection.count_documents({
                    'mailbox_id': {'$in': user_mailboxes},
                    'to': {'$in': user_mailboxes},
                    '$expr': {
                        '$gte': [{'$toDate': '$date'}, start_date]
                    },
                    classification: True
                })
                metrics[classification][period_name] = count

            # EMEI calculation (normalized per day)
            responded_count = emails_collection.count_documents({
                'mailbox_id': {'$in': user_mailboxes},
                'to': {'$in': user_mailboxes},
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

def get_email_list(metric, period, sender=None, recipient=None, raw_body=None):
    """Fetch list of emails for a specific metric and period, filtered by user's mailboxes."""
    logger.info(f"Received email list request: metric={metric}, period={period}, sender={sender}, recipient={recipient}")
    if raw_body:
        logger.debug(f"Raw POST body: {raw_body}")
    try:
        user_mailboxes = [mailbox['mailbox_id'] for mailbox in current_user.mailboxes]
        if not user_mailboxes:
            logger.warning("No mailboxes found for user: %s", current_user.username)
            return {'emails': []}

        # Decode sender or recipient if Base64-encoded
        if sender:
            try:
                sender = urllib.parse.unquote(base64.b64decode(sender).decode('utf-8'))
                logger.debug("Decoded sender: %s", sender)
            except Exception as e:
                logger.error(f"Error decoding sender: {str(e)}")
                sender = None
        if recipient:
            try:
                recipient = urllib.parse.unquote(base64.b64decode(recipient).decode('utf-8'))
                logger.debug("Decoded recipient: %s", recipient)
            except Exception as e:
                logger.error(f"Error decoding recipient: {str(e)}")
                recipient = None

        now = datetime.utcnow()
        periods = {
            'day': now - timedelta(days=1),
            'week': now - timedelta(weeks=1),
            'month': now - timedelta(days=30),
            'year': now - timedelta(days=365)
        }
        start_date = periods.get(period, now)

        match_criteria = {
            'mailbox_id': {'$in': user_mailboxes},
            '$expr': {
                '$gte': [{'$toDate': '$date'}, start_date]
            }
        }

        if sender:
            formatted_sender = format_email_field_with_fallback(sender, '')
            email_only = extract_email(sender) or ''
            match_criteria['to'] = {'$in': user_mailboxes}
            match_criteria['from'] = {
                '$regex': f'^{re.escape(formatted_sender)}$|^{re.escape(email_only)}$',
                '$options': 'i'
            }
            logger.debug("Sender filter applied: formatted=%s, email=%s", formatted_sender, email_only)
        elif recipient:
            formatted_recipient = format_email_field_with_fallback(recipient, '')
            email_only = extract_email(recipient) or ''
            match_criteria['from'] = {'$in': user_mailboxes}
            match_criteria['to'] = {
                '$regex': f'^{re.escape(formatted_recipient)}$|^{re.escape(email_only)}$|.*, *{re.escape(formatted_recipient)}(?:,|$)|.*, *{re.escape(email_only)}(?:,|$)',
                '$options': 'i'
            }
            logger.debug("Recipient filter applied: formatted=%s, email=%s", formatted_recipient, email_only)
        else:
            if metric == 'received':
                match_criteria['to'] = {'$in': user_mailboxes}
            elif metric == 'sent':
                match_criteria['from'] = {'$in': user_mailboxes}
            else:
                match_criteria['to'] = {'$in': user_mailboxes}
                match_criteria[metric] = True

        logger.debug("Final match criteria: %s", match_criteria)

        pipeline = [
            {'$match': match_criteria},
            {
                '$project': {
                    '_id': 0,
                    'index': 1,
                    'from': 1,
                    'to': 1,
                    'from_email': {'$ifNull': ['$from_email', '']},
                    'to_email': {'$ifNull': ['$to_email', '']},
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
        logger.debug("Raw email list data: %s", [{k: v for k, v in email.items() if k in ['index', 'from', 'to', 'from_email', 'to_email', 'subject']} for email in emails])

        for email in emails:
            email['index'] = str(email.get('index', 'N/A'))
            if email['index'] == 'N/A' or not email['index']:
                logger.warning("Invalid or missing index for email: from=%s, subject=%s", email.get('from'), email.get('subject'))
            email['from'] = format_email_field_with_fallback(email.get('from', ''), email.get('from_email', ''))
            to_field = email.get('to', '')
            to_email = email.get('to_email', '')
            if ',' in to_field:
                to_fields = [t.strip() for t in to_field.split(',')]
                formatted_tos = [format_email_field_with_fallback(t, to_email) for t in to_fields]
                email['to'] = ', '.join(formatted_tos)
            else:
                email['to'] = format_email_field_with_fallback(to_field, to_email)
            logger.debug("Formatted email: index=%s, from=%s, to=%s, subject=%s", email['index'], email['from'], email['to'], email.get('subject', ''))

        logger.info(f"Fetched {len(emails)} emails for metric: {metric}, period: {period}")
        return {'emails': emails}
    except Exception as e:
        logger.error(f"Error fetching email list: {str(e)}", exc_info=True)
        return {'error': str(e), 'emails': []}