"""
Smart Child Adoption Support Platform - Single Monolithic Application (app.py)
All backend logic, database connections, authentication, email dispatch, AI assistance,
and Flask routes are consolidated into this single file using pure `@app.route` decorators.
"""
import os
import io
import re
import csv
import smtplib
import imaplib
import email
import logging
import certifi
from functools import wraps
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    session, jsonify, Response
)
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
import mongomock
from bson.objectid import ObjectId

# Load environment variables
load_dotenv()

# ====================================================
# 1. APPLICATION & CONFIGURATION SETUP
# ====================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
template_folder = os.path.join(BASE_DIR, 'templates')
static_folder = os.path.join(BASE_DIR, 'static')

app = Flask(
    __name__,
    template_folder=template_folder,
    static_folder=static_folder
)

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'smart_child_adoption_secret_key_2026_dev')
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/smart_adoption')
    MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'smart_adoption')

    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

    SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    SMTP_FROM = os.getenv('SMTP_FROM', os.getenv('SMTP_USERNAME', ''))

    IMAP_HOST = os.getenv('IMAP_HOST', 'imap.gmail.com')
    IMAP_PORT = int(os.getenv('IMAP_PORT', '993'))
    IMAP_USERNAME = os.getenv('IMAP_USERNAME', '')
    IMAP_PASSWORD = os.getenv('IMAP_PASSWORD', '')

app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
logger = logging.getLogger(__name__)

# ====================================================
# 2. DATABASE CONNECTION & MONGOMOCK FALLBACK
# ====================================================
_client = None
_db = None

def init_db(app_instance=None):
    """Initializes MongoDB Atlas connection with automatic MongoMock fallback."""
    global _client, _db
    if _db is not None:
        return _db

    try:
        client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=3000, tlsCAFile=certifi.where())
        client.admin.command('ping')
        _client = client
        _db = client[Config.MONGO_DB_NAME]
        logger.info(f"Connected to MongoDB Atlas: {Config.MONGO_DB_NAME}")
    except Exception as e:
        logger.warning(f"Connecting to MongoMock in-memory database ({e}).")
        _client = mongomock.MongoClient()
        _db = _client[Config.MONGO_DB_NAME]

    return _db

def get_db():
    global _db
    if _db is None:
        init_db()
    return _db

class DatabaseProxy:
    """Proxy allowing `db.users.find()` style queries directly on database."""
    def __getattr__(self, name):
        return getattr(get_db(), name)

    def __getitem__(self, name):
        return get_db()[name]

db = DatabaseProxy()
init_db(app)


# ====================================================
# 3. AUTHENTICATION & SESSION MANAGEMENT HELPERS
# ====================================================
def hash_password(password):
    return generate_password_hash(password)

def verify_password(password_hash, password):
    return check_password_hash(password_hash, password)

def login_user_session(user_doc):
    session.clear()
    session['user_id'] = str(user_doc['_id'])
    session['role'] = user_doc.get('role', 'adopter')
    session['name'] = user_doc.get('name', '')
    session['email'] = user_doc.get('email', '')
    if user_doc.get('role') == 'trust':
        trust = db.trusts.find_one({'email': user_doc.get('email')}) or db.trusts.find_one({'user_id': str(user_doc['_id'])})
        if trust:
            session['trust_id'] = str(trust['_id'])

def logout_user_session():
    session.clear()

def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    try:
        user = db.users.find_one({'_id': ObjectId(user_id)})
    except Exception:
        user = db.users.find_one({'_id': user_id})
    return user

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def adopter_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'adopter':
            flash('Adopter access required.', 'danger')
            return redirect(url_for('login', role='adopter'))
        return f(*args, **kwargs)
    return decorated_function

def trust_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'trust':
            flash('Trust agency access required.', 'danger')
            return redirect(url_for('login', role='trust'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('System Admin access required.', 'danger')
            return redirect(url_for('login', role='admin'))
        return f(*args, **kwargs)
    return decorated_function


# ====================================================
# 4. NOTIFICATION HELPERS
# ====================================================
def create_notification(user_id, message, notif_type='general', related_id=None):
    notif_doc = {
        'user_id': str(user_id),
        'message': message,
        'type': notif_type,
        'related_id': related_id,
        'is_read': False,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    return db.notifications.insert_one(notif_doc).inserted_id

def get_user_notifications(user_id, limit=20):
    query = {'user_id': str(user_id)}
    notifications = list(db.notifications.find(query).sort('created_at', -1).limit(limit))
    for n in notifications:
        n['_id'] = str(n['_id'])
    return notifications

def get_unread_count(user_id):
    return db.notifications.count_documents({'user_id': str(user_id), 'is_read': False})

def mark_notification_read(notif_id):
    try:
        db.notifications.update_one({'_id': ObjectId(notif_id)}, {'$set': {'is_read': True}})
    except Exception:
        db.notifications.update_one({'_id': notif_id}, {'$set': {'is_read': True}})

def mark_all_read(user_id):
    db.notifications.update_many({'user_id': str(user_id)}, {'$set': {'is_read': True}})


# ====================================================
# 5. EMAIL DISPATCH HELPERS (SMTP & SIMULATION LOGGING)
# ====================================================
def _log_email(user_id, recipient_email, email_type, subject, status, error_message=""):
    log_doc = {
        'user_id': str(user_id) if user_id else None,
        'email': recipient_email,
        'email_type': email_type,
        'subject': subject,
        'status': status,
        'sent_at': datetime.now(timezone.utc).isoformat(),
        'error_message': error_message
    }
    try:
        db.email_logs.insert_one(log_doc)
    except Exception as e:
        logger.error(f"Failed to record email log: {e}")

def send_smtp_email(to_email, subject, body_text, email_type='GENERAL', user_id=None):
    if not to_email:
        return False, "No recipient email address provided."

    # Simulation fallback mode if credentials are not configured in environment
    if not Config.SMTP_USERNAME or not Config.SMTP_PASSWORD:
        msg = f"[SIMULATION] Real SMTP credentials not set. Email to {to_email} logged as SENT_SIMULATED."
        logger.info(msg)
        _log_email(user_id, to_email, email_type, subject, 'SENT_SIMULATED', 'SMTP credentials not configured in environment')
        return True, msg

    try:
        msg = MIMEMultipart()
        msg['From'] = Config.SMTP_FROM or Config.SMTP_USERNAME
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))

        server = smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=10)
        server.starttls()
        server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()

        _log_email(user_id, to_email, email_type, subject, 'SENT')
        return True, f"Email sent successfully to {to_email}"
    except Exception as e:
        err_msg = str(e)
        logger.error(f"SMTP email sending failed to {to_email}: {err_msg}")
        _log_email(user_id, to_email, email_type, subject, 'FAILED', err_msg)
        return False, f"SMTP Error: {err_msg}"

def send_registration_email(user_name, user_email, user_id=None):
    subject = "Registration Successful – Smart Child Adoption Platform"
    body = f"Hello {user_name},\n\nYour account has been successfully registered on Smart Child Adoption Support Platform.\n\nThank you,\nSmart Child Adoption Support Team"
    return send_smtp_email(user_email, subject, body, email_type='REGISTRATION', user_id=user_id)

def send_approval_email(user_name, user_email, trust_name, user_id=None):
    subject = "Adoption Request Approved – Smart Child Adoption Platform"
    body = f"Hello {user_name},\n\nYour adoption request submitted to {trust_name} has been approved for the next stage.\n\nThank you,\nSmart Child Adoption Support Team"
    return send_smtp_email(user_email, subject, body, email_type='APPROVAL', user_id=user_id)

def send_status_update_email(user_name, user_email, new_status, trust_name, user_id=None):
    subject = f"Adoption Status Update: {new_status} – Smart Child Adoption Platform"
    body = f"Hello {user_name},\n\nYour adoption application with {trust_name} has been updated to: {new_status}.\n\nThank you,\nSmart Child Adoption Support Team"
    return send_smtp_email(user_email, subject, body, email_type='STATUS_UPDATE', user_id=user_id)

def send_application_submitted_email(applicant_email, application_id, agency_name, user_id=None):
    subject = f"Application Submitted – {application_id}"
    body = f"Dear Applicant,\n\nYour adoption application ({application_id}) has been submitted to {agency_name}.\n\nCurrent Status: SUBMITTED\n\nThank you,\nSmart Child Adoption Support Platform"
    return send_smtp_email(applicant_email, subject, body, email_type='APPLICATION_SUBMITTED', user_id=user_id)

def send_application_status_update_email(applicant_email, application_id, agency_name, new_status, user_id=None):
    subject = f"Application Status Updated – {application_id}"
    now_str = datetime.now().strftime("%d %b %Y, %I:%M %p")
    body = f"Dear Applicant,\n\nYour adoption application ({application_id}) with {agency_name} status has been updated to: {new_status}.\n\nLast Updated: {now_str}\n\nThank you,\nSmart Child Adoption Support Platform"
    return send_smtp_email(applicant_email, subject, body, email_type='APPLICATION_STATUS_UPDATE', user_id=user_id)

def send_matching_completed_email(applicant_email, application_id, agency_name, user_id=None):
    subject = f"Child-Family Matching Completed – {application_id}"
    now_str = datetime.now().strftime("%d %b %Y, %I:%M %p")
    body = f"Dear Applicant,\n\nYour child-family matching process with {agency_name} has been completed and authorized by the Trust Board.\n\nCompletion Date: {now_str}\n\nThank you,\nSmart Child Adoption Support Platform"
    return send_smtp_email(applicant_email, subject, body, email_type='MATCHING_COMPLETED', user_id=user_id)

def fetch_recent_emails(user_email=None, limit=10):
    query = {}
    if user_email:
        query['email'] = user_email
    logs = list(db.email_logs.find(query).sort('sent_at', -1).limit(limit))
    result_emails = []
    for log in logs:
        result_emails.append({
            'subject': log.get('subject', ''),
            'recipient': log.get('email', ''),
            'email_type': log.get('email_type', ''),
            'status': log.get('status', ''),
            'sent_at': log.get('sent_at', ''),
            'source': 'PLATFORM_LOG'
        })
    return result_emails

def find_trust_related_emails(user_email):
    if not user_email:
        return []
    logs = list(db.email_logs.find({'email': user_email}).sort('sent_at', -1).limit(5))
    return [{'subject': log.get('subject', ''), 'type': log.get('email_type', ''), 'status': log.get('status', ''), 'date': log.get('sent_at', '')} for log in logs]


# ====================================================
# 6. AGENCY DATASET HELPERS (Validation, Indexing, CSV)
# ====================================================
def create_agency_indexes():
    try:
        db.trusts.create_index([("state", 1)])
        db.trusts.create_index([("district", 1)])
        db.trusts.create_index([("city", 1)])
        db.trusts.create_index([("agency_type", 1)])
        db.trusts.create_index([("status", 1)])
        db.trusts.create_index([("verified", 1)])
        db.trusts.create_index([("trust_name", 1)])
        logger.info("MongoDB agency indexes verified.")
    except Exception as e:
        logger.warning(f"Index creation note: {e}")

def get_freshness_status(last_verified_str):
    if not last_verified_str:
        return {'status': 'Review Due', 'badge_class': 'badge-warning text-dark', 'days_ago': 999}
    try:
        if isinstance(last_verified_str, datetime):
            lv_date = last_verified_str
        else:
            lv_date = datetime.fromisoformat(last_verified_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        delta_days = (now - lv_date).days
        if delta_days <= 30:
            return {'status': 'Verified', 'badge_class': 'bg-success text-white', 'days_ago': delta_days}
        else:
            return {'status': 'Review Due', 'badge_class': 'badge-warning text-dark', 'days_ago': delta_days}
    except Exception:
        return {'status': 'Verified', 'badge_class': 'bg-success text-white', 'days_ago': 0}

def validate_url(url):
    if not url: return ""
    url = url.strip()
    if not url.startswith(('http://', 'https://')): return f"https://{url}"
    return url

def validate_email(email_str):
    if not email_str: return ""
    email_str = email_str.strip().lower()
    return email_str if re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email_str) else ""

def import_agencies_from_csv(file_stream):
    successful_count = skipped_count = failed_count = 0
    errors = []
    try:
        content = file_stream.read().decode('utf-8-sig')
        csv_reader = csv.DictReader(io.StringIO(content))
        now_iso = datetime.now(timezone.utc).isoformat()
        for row_idx, row in enumerate(csv_reader, start=2):
            try:
                trust_name = (row.get('agency_name') or row.get('trust_name') or '').strip()
                if not trust_name:
                    failed_count += 1
                    errors.append(f"Row {row_idx}: Missing required Agency Name.")
                    continue
                state = (row.get('state') or 'Tamil Nadu').strip()
                district = (row.get('district') or '').strip()
                city = (row.get('city') or district or '').strip()
                address = (row.get('public_address') or row.get('address') or '').strip()
                phone = (row.get('phone') or row.get('public_phone') or '').strip()
                email_addr = validate_email(row.get('email') or row.get('public_email') or '')
                website = validate_url(row.get('website') or row.get('source_url') or '')
                agency_type = (row.get('agency_type') or 'Specialized Adoption Agency (SAA)').strip()
                verification_source = (row.get('verification_source') or 'Official CARA / Government Registry').strip()
                source_url = validate_url(row.get('source_url') or website or '')
                lang_str = row.get('languages') or 'English, Tamil'
                languages = [l.strip() for l in lang_str.split(',') if l.strip()] if isinstance(lang_str, str) else ['English', 'Tamil']
                is_verified = str(row.get('verified', '')).strip().lower() in ['true', '1', 'yes', 'verified']
                last_verified = row.get('last_verified') or (now_iso if is_verified else None)

                existing = db.trusts.find_one({
                    'trust_name': {'$regex': f"^{re.escape(trust_name)}$", '$options': 'i'},
                    'state': {'$regex': f"^{re.escape(state)}$", '$options': 'i'},
                    'city': {'$regex': f"^{re.escape(city)}$", '$options': 'i'}
                })
                agency_doc = {
                    'trust_name': trust_name, 'state': state, 'district': district, 'city': city,
                    'address': address, 'location': f"{city}, {state}" if city else state,
                    'phone': phone, 'email': email_addr, 'website': website, 'languages': languages,
                    'agency_type': agency_type, 'verified': is_verified, 'verification_source': verification_source,
                    'source_url': source_url, 'last_verified': last_verified, 'status': 'ACTIVE' if is_verified else 'PENDING_REVIEW',
                    'updated_at': now_iso
                }
                if existing:
                    db.trusts.update_one({'_id': existing['_id']}, {'$set': agency_doc})
                    skipped_count += 1
                else:
                    agency_doc['created_at'] = now_iso
                    db.trusts.insert_one(agency_doc)
                    successful_count += 1
            except Exception as row_err:
                failed_count += 1
                errors.append(f"Row {row_idx}: {row_err}")
        return {'success': True, 'successful_count': successful_count, 'skipped_count': skipped_count, 'failed_count': failed_count, 'errors': errors}
    except Exception as e:
        return {'success': False, 'error': str(e), 'successful_count': 0, 'skipped_count': 0, 'failed_count': 0, 'errors': [str(e)]}

def export_agencies_to_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Agency ID', 'Agency Name', 'State', 'District', 'City', 'Address', 'Phone', 'Email', 'Website', 'Languages', 'Agency Type', 'Verified', 'Verification Source', 'Source URL', 'Last Verified', 'Status', 'Freshness Status'])
    agencies = list(db.trusts.find().sort('trust_name', 1))
    for a in agencies:
        freshness = get_freshness_status(a.get('last_verified'))
        langs = ", ".join(a.get('languages', [])) if isinstance(a.get('languages'), list) else str(a.get('languages', ''))
        writer.writerow([str(a['_id']), a.get('trust_name', ''), a.get('state', ''), a.get('district', ''), a.get('city', ''), a.get('address', ''), a.get('phone', ''), a.get('email', ''), a.get('website', ''), langs, a.get('agency_type', ''), 'TRUE' if a.get('verified') else 'FALSE', a.get('verification_source', ''), a.get('source_url', ''), a.get('last_verified', ''), a.get('status', ''), freshness['status']])
    return output.getvalue()


# ====================================================
# 7. BILINGUAL AI ADOPTION ASSISTANT ENGINE
# ====================================================
SYSTEM_PROMPT = """You are an AI Adoption Support Assistant for a child adoption support platform in India.
Your persona: You provide simple, neutral, empathetic, and trustworthy guidance to prospective adopters and platform users.
You do NOT make legal or eligibility decisions.
"""

KNOWN_LOCATIONS = ['madurai', 'chennai', 'coimbatore', 'trichy', 'mumbai', 'pune', 'bengaluru', 'delhi', 'kochi', 'kolkata', 'hyderabad', 'ahmedabad', 'tamil nadu', 'maharashtra', 'karnataka', 'kerala', 'west bengal', 'telangana', 'gujarat']
KNOWN_LANGUAGES = ['tamil', 'english', 'hindi', 'marathi', 'kannada', 'malayalam', 'telugu', 'bengali', 'gujarati']

def _extract_search_preferences(question: str, user_context: dict):
    q_lower = question.lower()
    found_loc = next((loc for loc in KNOWN_LOCATIONS if loc in q_lower), None)
    found_lang = next((lang for lang in KNOWN_LANGUAGES if lang in q_lower), None)
    user = user_context.get('user') or {}
    prefs = user.get('preferences') or {}
    if not found_loc:
        found_loc = prefs.get('location') or user.get('address')
    if not found_lang:
        user_langs = prefs.get('languages') or [user.get('language')]
        found_lang = user_langs[0] if user_langs and user_langs[0] else None
    return {'location': found_loc, 'language': found_lang}

def _build_grounded_agency_query(question: str, prefs: dict):
    query = {'verified': True, 'status': {'$in': ['ACTIVE', 'Verified']}}
    location = prefs.get('location')
    language = prefs.get('language')
    if location:
        loc_pattern = f".*{re.escape(location.strip())}.*"
        query['$or'] = [{'state': {'$regex': loc_pattern, '$options': 'i'}}, {'district': {'$regex': loc_pattern, '$options': 'i'}}, {'city': {'$regex': loc_pattern, '$options': 'i'}}, {'location': {'$regex': loc_pattern, '$options': 'i'}}]
    if language:
        query['languages'] = {'$regex': f".*{re.escape(language.strip())}.*", '$options': 'i'}
    return query

def process_ai_query(question: str, user_context: dict = None, target_lang: str = 'English'):
    if not user_context: user_context = {}
    prefs = _extract_search_preferences(question, user_context)
    agency_query = _build_grounded_agency_query(question, prefs)
    matched_agencies = list(db.trusts.find(agency_query).limit(5))
    for a in matched_agencies:
        a['_id'] = str(a['_id'])
        a['freshness'] = get_freshness_status(a.get('last_verified'))

    req = user_context.get('request')
    journey = user_context.get('journey')
    app_status = req.get('status', 'No Active Application') if req else 'No Active Application'
    journey_stage = journey.get('current_stage', 'Registration') if journey else 'Registration'

    q_lower = question.lower()
    if 'tamil' in q_lower or target_lang.lower() == 'tamil':
        response_text = f"வணக்கம்! உங்கள் தற்போதைய விண்ணப்ப நிலை: {app_status} (நிலை: {journey_stage})."
        if matched_agencies:
            response_text += "\n\nஅங்கீகரிக்கப்பட்ட தத்தெடுப்பு முகமைகள்:\n"
            for ag in matched_agencies:
                response_text += f"• {ag.get('trust_name')} - {ag.get('city')}, {ag.get('state')} (தொலைபேசி: {ag.get('phone', 'N/A')})\n"
        response_text += "\nகுறிப்பு: அதிகாரப்பூர்வ தகவல்களுக்கு CARA அல்லது அங்கீகரிக்கப்பட்ட முகமையை தொடர்பு கொள்ளவும்."
    else:
        response_text = f"Hello! Your current adoption application status is: {app_status} (Stage: {journey_stage})."
        if matched_agencies:
            response_text += "\n\nVerified Adoption Agencies matching your profile/query:\n"
            for ag in matched_agencies:
                response_text += f"• {ag.get('trust_name')} - {ag.get('city')}, {ag.get('state')} (Phone: {ag.get('phone', 'N/A')})\n"
        response_text += "\nAdministrative Next Step: Keep your profile updated and check your adoption journey timeline regularly.\n\nNote: Please confirm official adoption procedures with the authorized adoption trust or relevant government authority."

    return {'response': response_text, 'agencies': matched_agencies, 'preferences': prefs}


# ====================================================
# 8. GLOBAL CONTEXT PROCESSOR
# ====================================================
@app.context_processor
def inject_global_vars():
    user = get_current_user()
    unread_count = 0
    if user:
        unread_count = get_unread_count(str(user['_id']))
    return dict(current_user=user, unread_count=unread_count)


# ====================================================
# 9. ROOT & ERROR ROUTES
# ====================================================
@app.route('/', endpoint='index')
def index():
    return render_template('index.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('index.html', error_msg="Page Not Found"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('index.html', error_msg="Internal Server Error"), 500


# ====================================================
# 10. AUTHENTICATION ROUTES (@app.route)
# ====================================================
@app.route('/login', methods=['GET', 'POST'], endpoint='login')
@app.route('/login', methods=['GET', 'POST'], endpoint='auth.login')
def login():
    verified_trust_accounts = list(db.trusts.find({'verified': True}))
    for trust_item in verified_trust_accounts:
        trust_item['_id'] = str(trust_item['_id'])
    verified_trust_accounts.sort(key=lambda x: x.get('trust_name', ''))

    if request.method == 'POST':
        email_input = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        selected_role = request.form.get('role', 'adopter')

        if not email_input or not password:
            flash('Please enter both email and password.', 'danger')
            return render_template('auth/login.html', selected_role=selected_role, email=email_input, verified_trust_accounts=verified_trust_accounts)

        user = db.users.find_one({'email': email_input})
        if not user or not verify_password(user.get('password_hash', ''), password):
            flash('Invalid email or password.', 'danger')
            return render_template('auth/login.html', selected_role=selected_role, email=email_input, verified_trust_accounts=verified_trust_accounts)

        if selected_role and user.get('role') != selected_role:
            flash(f'Role mismatch. This account is registered as "{user.get("role")}".', 'warning')
            return render_template('auth/login.html', selected_role=selected_role, email=email_input, verified_trust_accounts=verified_trust_accounts)

        login_user_session(user)
        flash(f'Welcome back, {user.get("name")}!', 'success')

        role = user.get('role')
        if role == 'adopter':
            return redirect(url_for('adopter_dashboard'))
        elif role == 'trust':
            return redirect(url_for('trust_dashboard'))
        elif role == 'admin':
            return redirect(url_for('admin_dashboard'))

    selected_role = request.args.get('role', 'adopter')
    return render_template('auth/login.html', selected_role=selected_role, verified_trust_accounts=verified_trust_accounts)

@app.route('/register', methods=['GET', 'POST'], endpoint='register')
@app.route('/register', methods=['GET', 'POST'], endpoint='auth.register')
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email_input = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', 'adopter')
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        language = request.form.get('language', 'English')
        trust_name = request.form.get('trust_name', '').strip()
        location = request.form.get('location', '').strip()

        if not name or not email_input or not password:
            flash('Please fill in all required fields.', 'danger')
            return render_template('auth/register.html', role=role)

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html', role=role)

        if db.users.find_one({'email': email_input}):
            flash('An account with this email address already exists.', 'danger')
            return render_template('auth/register.html', role=role)

        now_iso = datetime.now(timezone.utc).isoformat()
        user_doc = {
            'name': name, 'email': email_input, 'password_hash': hash_password(password),
            'role': role, 'phone': phone, 'address': address, 'language': language,
            'preferences': {'location': location if role == 'trust' else '', 'languages': [language]},
            'created_at': now_iso, 'updated_at': now_iso
        }
        user_id = db.users.insert_one(user_doc).inserted_id

        if role == 'trust':
            trust_doc = {
                'user_id': str(user_id), 'trust_name': trust_name or name, 'email': email_input,
                'phone': phone, 'location': location or address, 'city': location or address,
                'state': 'Tamil Nadu', 'verified': False, 'status': 'PENDING_REVIEW',
                'created_at': now_iso, 'updated_at': now_iso
            }
            db.trusts.insert_one(trust_doc)

        send_registration_email(name, email_input, user_id=user_id)
        create_notification(str(user_id), 'Welcome to Smart Child Adoption Platform!', notif_type='registration')
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login', role=role))

    role = request.args.get('role', 'adopter')
    return render_template('auth/register.html', role=role)

@app.route('/logout', endpoint='logout')
@app.route('/logout', endpoint='auth.logout')
def logout():
    logout_user_session()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))


# ====================================================
# 11. ADOPTER PORTAL ROUTES (@app.route)
# ====================================================
JOURNEY_STAGES = ['REGISTRATION', 'PROFILE_COMPLETED', 'REQUEST_SENT', 'TRUST_REVIEW', 'SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'FURTHER_PROCESS', 'COMPLETED']

def _find_trust_by_id(trust_id_str):
    if not trust_id_str: return None
    try: return db.trusts.find_one({'_id': ObjectId(trust_id_str)})
    except Exception: return db.trusts.find_one({'_id': trust_id_str})

@app.route('/adopter/dashboard', endpoint='adopter_dashboard')
@app.route('/adopter/dashboard', endpoint='adopter.dashboard')
@adopter_required
def adopter_dashboard():
    user = get_current_user()
    user_id = str(user['_id'])
    req = db.adoption_requests.find_one({'adopter_id': user_id})
    journey = db.journeys.find_one({'request_id': req.get('request_id')}) if req else None
    trust = _find_trust_by_id(req.get('trust_id')) if req and req.get('trust_id') else None
    notifications = get_user_notifications(user_id, limit=5)
    unread_count_val = get_unread_count(user_id)
    status_str = req.get('status', 'REGISTRATION') if req else 'REGISTRATION'
    journey_stage = journey.get('current_stage', 'PROFILE_COMPLETED' if user.get('family_info') else 'REGISTRATION') if journey else 'REGISTRATION'
    trust_name = trust.get('trust_name', 'Not Selected') if trust else 'Not Selected'
    latest_update = notifications[0].get('message') if notifications else 'Account registered successfully.'

    return render_template('adopter/dashboard.html', user=user, request=req, trust=trust, journey=journey, status_str=status_str, journey_stage=journey_stage, trust_name=trust_name, latest_update=latest_update, notifications=notifications, unread_count=unread_count_val, JOURNEY_STAGES=JOURNEY_STAGES)

@app.route('/adopter/trusts', endpoint='adopter_verified_trusts')
@app.route('/adopter/trusts', endpoint='adopter.verified_trusts')
@adopter_required
def adopter_verified_trusts():
    user = get_current_user()
    user_id = str(user['_id'])
    state_filter = request.args.get('state', '').strip()
    district_filter = request.args.get('district', '').strip()
    city_filter = request.args.get('city', '').strip()
    language_filter = request.args.get('language', '').strip()
    agency_type_filter = request.args.get('agency_type', '').strip()
    search_query = request.args.get('search', '').strip()
    apply_trust_id = request.args.get('apply_trust_id', '').strip()

    query = {'verified': True, 'status': {'$in': ['ACTIVE', 'Verified']}}
    if state_filter: query['state'] = {'$regex': re.escape(state_filter), '$options': 'i'}
    if district_filter: query['district'] = {'$regex': re.escape(district_filter), '$options': 'i'}
    if city_filter: query['city'] = {'$regex': re.escape(city_filter), '$options': 'i'}
    if language_filter: query['languages'] = {'$regex': re.escape(language_filter), '$options': 'i'}
    if agency_type_filter: query['agency_type'] = {'$regex': re.escape(agency_type_filter), '$options': 'i'}
    if search_query:
        query['$or'] = [
            {'trust_name': {'$regex': re.escape(search_query), '$options': 'i'}},
            {'city': {'$regex': re.escape(search_query), '$options': 'i'}},
            {'district': {'$regex': re.escape(search_query), '$options': 'i'}},
            {'state': {'$regex': re.escape(search_query), '$options': 'i'}}
        ]

    trusts_cursor = list(db.trusts.find(query))
    for t in trusts_cursor:
        t['_id'] = str(t['_id'])
        t['freshness'] = get_freshness_status(t.get('last_verified'))
    trusts_cursor.sort(key=lambda x: x.get('trust_name', ''))

    available_states = sorted(list(set([s for s in db.trusts.distinct('state') if s])))
    available_districts = sorted(list(set([d for d in db.trusts.distinct('district') if d])))
    available_cities = sorted(list(set([c for c in db.trusts.distinct('city') if c])))

    application = db.adoption_applications.find_one({'adopter_id': user_id})
    if not application:
        req = db.adoption_requests.find_one({'adopter_id': user_id})
        if req:
            application = {'application_id': req.get('request_id'), 'trust_id': req.get('trust_id'), 'applicant_name': user.get('name'), 'applicant_email': user.get('email'), 'status': req.get('status', 'SUBMITTED'), 'created_at': req.get('created_at'), 'updated_at': req.get('updated_at')}

    journey = db.journeys.find_one({'request_id': application.get('application_id')}) if application else None
    applied_trust = _find_trust_by_id(application.get('trust_id')) if application and application.get('trust_id') else None
    target_trust = _find_trust_by_id(apply_trust_id) if apply_trust_id else None
    notifications = get_user_notifications(user_id, limit=5)
    unread_count_val = get_unread_count(user_id)

    return render_template('adopter/trusts.html', user=user, trusts=trusts_cursor, application=application, journey=journey, applied_trust=applied_trust, target_trust=target_trust, available_states=available_states, available_districts=available_districts, available_cities=available_cities, apply_trust_id=apply_trust_id, notifications=notifications, unread_count=unread_count_val)

@app.route('/adopter/apply-agency', methods=['POST'], endpoint='adopter_apply_agency')
@app.route('/adopter/apply-agency', methods=['POST'], endpoint='adopter.apply_agency')
@adopter_required
def adopter_apply_agency():
    user = get_current_user()
    user_id = str(user['_id'])
    trust_id = request.form.get('trust_id', '').strip()
    if not trust_id:
        flash('Please select an adoption agency to apply.', 'danger')
        return redirect(url_for('adopter_verified_trusts'))

    trust = _find_trust_by_id(trust_id)
    if not trust:
        flash('Selected adoption agency not found.', 'danger')
        return redirect(url_for('adopter_verified_trusts'))

    applicant_name = request.form.get('applicant_name', '').strip() or user.get('name')
    applicant_email = request.form.get('applicant_email', '').strip().lower() or user.get('email')
    phone = request.form.get('phone', '').strip() or user.get('phone')
    address = request.form.get('address', '').strip()
    state = request.form.get('state', '').strip()
    district = request.form.get('district', '').strip()
    city = request.form.get('city', '').strip()
    language = request.form.get('language', 'English')
    family_status = request.form.get('family_status', 'Married')
    occupation = request.form.get('occupation', '')
    preferences = request.form.get('preferences', '')

    now_iso = datetime.now(timezone.utc).isoformat()
    app_id = f"APP-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    app_doc = {'application_id': app_id, 'adopter_id': user_id, 'trust_id': str(trust['_id']), 'trust_name': trust.get('trust_name'), 'applicant_name': applicant_name, 'applicant_email': applicant_email, 'phone': phone, 'address': address, 'state': state, 'district': district, 'city': city, 'language': language, 'marital_status': family_status, 'occupation': occupation, 'preferences': preferences, 'status': 'SUBMITTED', 'created_at': now_iso, 'updated_at': now_iso}

    db.adoption_applications.delete_many({'adopter_id': user_id})
    db.adoption_requests.delete_many({'adopter_id': user_id})
    db.journeys.delete_many({'adopter_id': user_id})

    db.adoption_applications.insert_one(app_doc)
    db.adoption_requests.insert_one({'request_id': app_id, 'adopter_id': user_id, 'trust_id': str(trust['_id']), 'status': 'SUBMITTED', 'created_at': now_iso, 'updated_at': now_iso})
    db.journeys.insert_one({'request_id': app_id, 'adopter_id': user_id, 'registration': True, 'profile_completed': True, 'request_sent': True, 'trust_review': True, 'approved': False, 'further_process': False, 'completed': False, 'current_stage': 'SUBMITTED', 'updated_at': now_iso})

    create_notification(user_id, f"Application {app_id} submitted to {trust.get('trust_name')}.", notif_type='application')
    if trust.get('user_id'):
        create_notification(str(trust['user_id']), f"New adoption application ({app_id}) received from {applicant_name}.", notif_type='application')

    send_application_submitted_email(applicant_email, app_id, trust.get('trust_name'), user_id=user_id)
    flash(f"Application {app_id} submitted successfully to {trust.get('trust_name')}! Confirmation email sent.", 'success')
    return redirect(url_for('adopter_verified_trusts'))

@app.route('/adopter/ai-assistant', methods=['GET', 'POST'], endpoint='adopter_ai_assistant')
@app.route('/adopter/ai-assistant', methods=['GET', 'POST'], endpoint='adopter.ai_assistant')
@adopter_required
def adopter_ai_assistant():
    user = get_current_user()
    user_id = str(user['_id'])
    req = db.adoption_requests.find_one({'adopter_id': user_id})
    journey = db.journeys.find_one({'request_id': req.get('request_id')}) if req else None
    trust = _find_trust_by_id(req.get('trust_id')) if req and req.get('trust_id') else None
    user_context = {'user': user, 'request': req, 'journey': journey, 'trust': trust}

    ai_messages = []
    if request.method == 'POST':
        question = request.form.get('question', '').strip()
        if question:
            res = process_ai_query(question, user_context)
            ai_messages.append({'role': 'user', 'content': question})
            ai_messages.append({'role': 'assistant', 'content': res.get('response', '')})

    notifications = get_user_notifications(user_id, limit=5)
    unread_count_val = get_unread_count(user_id)
    return render_template('adopter/ai_assistant.html', user=user, ai_messages=ai_messages, notifications=notifications, unread_count=unread_count_val)

@app.route('/adopter/notifications', methods=['GET', 'POST'], endpoint='adopter_notifications')
@app.route('/adopter/notifications', methods=['GET', 'POST'], endpoint='adopter.notifications_page')
@adopter_required
def adopter_notifications():
    user = get_current_user()
    user_id = str(user['_id'])

    if request.method == 'POST':
        notif_id = request.form.get('notif_id')
        if request.form.get('action') == 'mark_all':
            mark_all_read(user_id)
            flash('All notifications marked as read.', 'success')
        elif notif_id:
            mark_notification_read(notif_id)
            flash('Notification marked as read.', 'success')
        return redirect(url_for('adopter_notifications'))

    filter_type = request.args.get('filter', 'all')
    all_notifs = get_user_notifications(user_id, limit=50)
    notifs_list = [n for n in all_notifs if not n.get('is_read')] if filter_type == 'unread' else all_notifs
    unread_count_val = get_unread_count(user_id)
    return render_template('adopter/notifications.html', user=user, notifications=notifs_list, unread_count=unread_count_val, filter_type=filter_type)

@app.route('/adopter/profile', methods=['GET', 'POST'], endpoint='adopter_profile')
@app.route('/adopter/profile', methods=['GET', 'POST'], endpoint='adopter.profile')
@adopter_required
def adopter_profile():
    user = get_current_user()
    user_id = str(user['_id'])
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email_input = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        language = request.form.get('language', 'English')
        new_password = request.form.get('new_password', '').strip()

        marital_status = request.form.get('marital_status', '')
        occupation = request.form.get('occupation', '')
        annual_income = request.form.get('annual_income', '')
        preferred_location = request.form.get('preferred_location', '')
        preferred_age_group = request.form.get('preferred_age_group', '')

        update_data = {
            'name': name, 'email': email_input, 'phone': phone, 'address': address, 'language': language,
            'family_info': {'marital_status': marital_status, 'occupation': occupation, 'annual_income': annual_income},
            'preferences': {'location': preferred_location, 'age_group': preferred_age_group, 'languages': [language]},
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        if new_password: update_data['password_hash'] = hash_password(new_password)
        try: db.users.update_one({'_id': ObjectId(user_id)}, {'$set': update_data})
        except Exception: db.users.update_one({'_id': user_id}, {'$set': update_data})
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('adopter_profile'))

    notifications = get_user_notifications(user_id, limit=5)
    unread_count_val = get_unread_count(user_id)
    return render_template('adopter/profile.html', user=user, notifications=notifications, unread_count=unread_count_val)

@app.route('/adopter/journey', endpoint='adopter_journey')
@app.route('/adopter/journey', endpoint='adopter.journey')
@adopter_required
def adopter_journey():
    user = get_current_user()
    user_id = str(user['_id'])
    req = db.adoption_requests.find_one({'adopter_id': user_id})
    journey_doc = db.journeys.find_one({'request_id': req.get('request_id')}) if req else None
    trust = _find_trust_by_id(req.get('trust_id')) if req and req.get('trust_id') else None
    notifications = get_user_notifications(user_id, limit=5)
    unread_count_val = get_unread_count(user_id)

    return render_template('adopter/journey.html', user=user, request=req, journey=journey_doc, trust=trust, notifications=notifications, unread_count=unread_count_val, JOURNEY_STAGES=JOURNEY_STAGES)


# ====================================================
# 12. TRUST AGENCY PORTAL ROUTES (@app.route)
# ====================================================
def _get_trust_doc(user):
    user_id = str(user['_id'])
    trust = db.trusts.find_one({'user_id': user_id})
    if not trust: trust = db.trusts.find_one({'email': user.get('email')})
    if not trust: trust = db.trusts.find_one({'trust_name': user.get('name')})
    return trust

def _get_trust_id_query(trust_id_str):
    if not trust_id_str: return None
    try: return {'$in': [trust_id_str, ObjectId(trust_id_str)]}
    except Exception: return trust_id_str

@app.route('/trust/dashboard', endpoint='trust_dashboard')
@app.route('/trust/dashboard', endpoint='trust.dashboard')
@trust_required
def trust_dashboard():
    user = get_current_user()
    user_id = str(user['_id'])
    trust = _get_trust_doc(user)
    trust_id = str(trust['_id']) if trust else None

    if trust_id:
        t_query = _get_trust_id_query(trust_id)
        total_new = db.adoption_requests.count_documents({'trust_id': t_query, 'status': {'$in': ['SUBMITTED', 'REQUEST_SENT', 'NEW']}})
        pending_review = db.adoption_requests.count_documents({'trust_id': t_query, 'status': {'$in': ['TRUST_REVIEW', 'UNDER_REVIEW']}})
        approved_count = db.adoption_requests.count_documents({'trust_id': t_query, 'status': 'APPROVED'})
        active_count = db.adoption_requests.count_documents({'trust_id': t_query, 'status': {'$in': ['SUBMITTED', 'REQUEST_SENT', 'TRUST_REVIEW', 'UNDER_REVIEW', 'APPROVED', 'FURTHER_PROCESS']}})
        completed_count = db.adoption_requests.count_documents({'trust_id': t_query, 'status': 'COMPLETED'})
        available_children_count = db.child_profiles.count_documents({'trust_id': t_query, 'status': 'AVAILABLE'})
        completed_matches_count = db.child_matches.count_documents({'trust_id': t_query})
        recent_requests = list(db.adoption_requests.find({'trust_id': t_query}).sort('updated_at', -1).limit(5))
    else:
        total_new = pending_review = approved_count = active_count = completed_count = 0
        available_children_count = completed_matches_count = 0
        recent_requests = []

    for req in recent_requests:
        req['_id'] = str(req['_id'])
        adopter_id = req.get('adopter_id')
        adopter = None
        if adopter_id:
            try: adopter = db.users.find_one({'_id': ObjectId(adopter_id)})
            except Exception: adopter = db.users.find_one({'_id': adopter_id})
        req['adopter'] = adopter

    notifications = get_user_notifications(user_id, limit=5)
    unread_count_val = get_unread_count(user_id)
    return render_template('trust/dashboard.html', user=user, trust=trust, total_new=total_new, pending_review=pending_review, approved_count=approved_count, active_count=active_count, completed_count=completed_count, available_children_count=available_children_count, completed_matches_count=completed_matches_count, recent_requests=recent_requests, notifications=notifications, unread_count=unread_count_val)

@app.route('/trust/applications', endpoint='trust_applications')
@app.route('/trust/applications', endpoint='trust.applications')
@trust_required
def trust_applications():
    user = get_current_user()
    user_id = str(user['_id'])
    trust = _get_trust_doc(user)
    trust_id = str(trust['_id']) if trust else None

    applications_list = []
    available_children = []
    ai_suggested_matches = []
    completed_matches = []

    if trust_id:
        t_query = _get_trust_id_query(trust_id)
        applications_cursor = list(db.adoption_requests.find({'trust_id': t_query}).sort('updated_at', -1))
        for req in applications_cursor:
            req['_id'] = str(req['_id'])
            adopter_id = req.get('adopter_id')
            adopter = None
            if adopter_id:
                try: adopter = db.users.find_one({'_id': ObjectId(adopter_id)})
                except Exception: adopter = db.users.find_one({'_id': adopter_id})
            req['adopter'] = adopter
            app_doc = db.adoption_applications.find_one({'adopter_id': adopter_id}) or db.adoption_applications.find_one({'application_id': req.get('request_id')})
            req['application_details'] = app_doc
            req['journey'] = db.journeys.find_one({'request_id': req.get('request_id')})
            applications_list.append(req)

        available_children = list(db.child_profiles.find({'trust_id': t_query, 'status': 'AVAILABLE'}).sort('created_at', -1))
        for ch in available_children: ch['_id'] = str(ch['_id'])

        completed_matches = list(db.child_matches.find({'trust_id': t_query}).sort('matched_at', -1))
        for m in completed_matches: m['_id'] = str(m['_id'])

        approved_adopters = [a for a in applications_list if a.get('status') in ['APPROVED', 'FURTHER_PROCESS', 'TRUST_REVIEW', 'UNDER_REVIEW', 'SUBMITTED']]
        for child in available_children:
            for req in approved_adopters:
                adopter = req.get('adopter') or {}
                app_det = req.get('application_details') or {}
                pref = adopter.get('preferences') or {}
                score = 75
                reasons = []
                target_age = app_det.get('preferred_age_group') or pref.get('age_group', '0-2 years')
                if target_age == child.get('age_range'):
                    score += 15
                    reasons.append(f"Age group match ({target_age})")
                else: reasons.append("Age group compatible")
                adopter_lang = adopter.get('language', 'English')
                if adopter_lang in child.get('language', ''):
                    score += 10
                    reasons.append(f"Language match ({adopter_lang})")
                ai_suggested_matches.append({'child': child, 'request': req, 'adopter': adopter, 'score': min(score, 98), 'reasons': reasons})
        ai_suggested_matches.sort(key=lambda x: x['score'], reverse=True)

    notifications = get_user_notifications(user_id, limit=5)
    unread_count_val = get_unread_count(user_id)
    return render_template('trust/applications.html', user=user, trust=trust, applications=applications_list, available_children=available_children, ai_suggested_matches=ai_suggested_matches, completed_matches=completed_matches, notifications=notifications, unread_count=unread_count_val)

@app.route('/trust/request/action/<req_id>', methods=['POST'], endpoint='trust_request_action')
@app.route('/trust/request/action/<req_id>', methods=['POST'], endpoint='trust.request_action')
@trust_required
def trust_request_action(req_id):
    user = get_current_user()
    trust = _get_trust_doc(user)
    action = request.form.get('action', '').lower()
    new_status = request.form.get('new_status', 'APPROVED')
    remarks = request.form.get('remarks', '').strip()

    try: req = db.adoption_requests.find_one({'_id': ObjectId(req_id)})
    except Exception: req = db.adoption_requests.find_one({'_id': req_id})

    if not req:
        flash('Adoption request not found.', 'danger')
        return redirect(url_for('trust_applications'))

    adopter_id = req.get('adopter_id')
    adopter = None
    if adopter_id:
        try: adopter = db.users.find_one({'_id': ObjectId(adopter_id)})
        except Exception: adopter = db.users.find_one({'_id': adopter_id})

    adopter_email = adopter.get('email', '') if adopter else ''
    trust_name = trust.get('trust_name', 'Adoption Trust') if trust else 'Adoption Trust'
    status_to_set = 'APPROVED' if action == 'approve' else ('REJECTED' if action == 'reject' else new_status)

    now_iso = datetime.now(timezone.utc).isoformat()
    update_dict = {'status': status_to_set, 'updated_at': now_iso}
    if remarks: update_dict['remarks'] = remarks

    db.adoption_requests.update_one({'_id': req['_id']}, {'$set': update_dict})
    app_doc = db.adoption_applications.find_one({'adopter_id': adopter_id}) or db.adoption_applications.find_one({'application_id': req.get('request_id')})
    if app_doc:
        db.adoption_applications.update_one({'_id': app_doc['_id']}, {'$set': update_dict})
        applicant_email = app_doc.get('applicant_email') or adopter_email
        application_id = app_doc.get('application_id') or req.get('request_id')
    else:
        applicant_email = adopter_email
        application_id = req.get('request_id', 'APP-2026-00001')

    db.journeys.update_one({'request_id': req.get('request_id')}, {'$set': {'current_stage': status_to_set, 'updated_at': now_iso}})
    create_notification(adopter_id, f"Application ({application_id}) status updated to '{status_to_set}' by {trust_name}.", notif_type='status_update')
    create_notification(str(user['_id']), f"Status for request {application_id} updated to {status_to_set}.", notif_type='status_update')
    send_application_status_update_email(applicant_email, application_id, trust_name, status_to_set, user_id=adopter_id)
    flash(f"Status updated to '{status_to_set}'. Notification & email sent to {applicant_email}.", 'success')
    return redirect(url_for('trust_applications'))

@app.route('/trust/authorize-match', methods=['POST'], endpoint='trust_authorize_match')
@app.route('/trust/authorize-match', methods=['POST'], endpoint='trust.authorize_match')
@trust_required
def trust_authorize_match():
    user = get_current_user()
    user_id = str(user['_id'])
    trust = _get_trust_doc(user)
    trust_id = str(trust['_id']) if trust else None

    child_id = request.form.get('child_id')
    request_id = request.form.get('request_id')
    adopter_id = request.form.get('adopter_id')
    compatibility_score = request.form.get('compatibility_score', '95%')

    if not child_id or not request_id or not adopter_id:
        flash('Missing child or adopter details for matching.', 'danger')
        return redirect(url_for('trust_applications'))

    now_iso = datetime.now(timezone.utc).isoformat()
    match_doc = {'match_id': f"MATCH-{datetime.now().strftime('%Y%m%d%H%M%S')}", 'trust_id': trust_id, 'child_id': child_id, 'request_id': request_id, 'adopter_id': adopter_id, 'compatibility_score': compatibility_score, 'matched_at': now_iso, 'status': 'AUTHORIZED_COMPLETED'}
    db.child_matches.insert_one(match_doc)

    try: db.child_profiles.update_one({'_id': ObjectId(child_id)}, {'$set': {'status': 'MATCHED', 'available_for_matching': False, 'updated_at': now_iso}})
    except Exception: db.child_profiles.update_one({'child_id': child_id}, {'$set': {'status': 'MATCHED', 'available_for_matching': False, 'updated_at': now_iso}})

    db.adoption_requests.update_one({'request_id': request_id}, {'$set': {'status': 'COMPLETED', 'updated_at': now_iso}})
    db.adoption_applications.update_one({'application_id': request_id}, {'$set': {'status': 'COMPLETED', 'updated_at': now_iso}})
    db.journeys.update_one({'request_id': request_id}, {'$set': {'current_stage': 'COMPLETED', 'completed': True, 'updated_at': now_iso}})

    create_notification(adopter_id, f"Child-family match for request {request_id} has been authorized and completed.", notif_type='match_completed')
    create_notification(user_id, f"Child match authorized and completed for request {request_id}.", notif_type='match_completed')

    adopter_doc = db.users.find_one({'_id': ObjectId(adopter_id)}) if ObjectId.is_valid(adopter_id) else db.users.find_one({'_id': adopter_id})
    if adopter_doc and adopter_doc.get('email'):
        send_matching_completed_email(adopter_doc['email'], request_id, trust.get('trust_name', 'Adoption Trust'), user_id=adopter_id)

    flash(f"Child-family match for request {request_id} authorized successfully!", 'success')
    return redirect(url_for('trust_applications'))

@app.route('/trust/profile', methods=['GET', 'POST'], endpoint='trust_profile')
@app.route('/trust/profile', methods=['GET', 'POST'], endpoint='trust.profile')
@trust_required
def trust_profile():
    user = get_current_user()
    user_id = str(user['_id'])
    trust = _get_trust_doc(user)

    if request.method == 'POST':
        trust_name = request.form.get('trust_name', '').strip()
        email_input = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        location = request.form.get('location', '').strip()
        city = request.form.get('city', '').strip()
        state = request.form.get('state', '').strip()
        description = request.form.get('description', '').strip()
        website = request.form.get('website', '').strip()
        languages_str = request.form.get('languages', 'English, Tamil')
        new_password = request.form.get('new_password', '').strip()
        languages_list = [l.strip() for l in languages_str.split(',') if l.strip()]

        trust_update = {'trust_name': trust_name, 'email': email_input, 'phone': phone, 'location': location or f"{city}, {state}", 'city': city, 'state': state, 'description': description, 'website': website, 'languages': languages_list, 'updated_at': datetime.now(timezone.utc).isoformat()}
        user_update = {'name': trust_name, 'email': email_input, 'phone': phone, 'address': location or f"{city}, {state}", 'updated_at': datetime.now(timezone.utc).isoformat()}
        if new_password: user_update['password_hash'] = hash_password(new_password)

        if trust: db.trusts.update_one({'_id': trust['_id']}, {'$set': trust_update})
        try: db.users.update_one({'_id': ObjectId(user_id)}, {'$set': user_update})
        except Exception: db.users.update_one({'_id': user_id}, {'$set': user_update})

        flash('Trust profile updated successfully!', 'success')
        return redirect(url_for('trust_profile'))

    notifications = get_user_notifications(user_id, limit=5)
    unread_count_val = get_unread_count(user_id)
    return render_template('trust/profile.html', user=user, trust=trust, notifications=notifications, unread_count=unread_count_val)

@app.route('/trust/notifications', methods=['GET', 'POST'], endpoint='trust_notifications')
@app.route('/trust/notifications', methods=['GET', 'POST'], endpoint='trust.notifications_page')
@trust_required
def trust_notifications():
    user = get_current_user()
    user_id = str(user['_id'])
    if request.method == 'POST':
        notif_id = request.form.get('notif_id')
        if request.form.get('action') == 'mark_all':
            mark_all_read(user_id)
            flash('All notifications marked as read.', 'success')
        elif notif_id:
            mark_notification_read(notif_id)
            flash('Notification marked as read.', 'success')
        return redirect(url_for('trust_notifications'))

    filter_type = request.args.get('filter', 'all')
    all_notifs = get_user_notifications(user_id, limit=50)
    notifs_list = [n for n in all_notifs if not n.get('is_read')] if filter_type == 'unread' else all_notifs
    unread_count_val = get_unread_count(user_id)
    return render_template('trust/notifications.html', user=user, notifications=notifs_list, unread_count=unread_count_val, filter_type=filter_type)


# ====================================================
# 13. SYSTEM ADMIN PORTAL ROUTES (@app.route)
# ====================================================
@app.route('/admin/dashboard', endpoint='admin_dashboard')
@app.route('/admin/dashboard', endpoint='admin.dashboard')
@admin_required
def admin_dashboard():
    user = get_current_user()
    user_id = str(user['_id'])
    total_adopters = db.users.count_documents({'role': 'adopter'})
    total_trusts = db.trusts.count_documents({})
    verified_trusts_count = db.trusts.count_documents({'verified': True})
    pending_trusts_count = db.trusts.count_documents({'verified': False})
    active_requests = db.adoption_requests.count_documents({'status': {'$in': ['REQUEST_SENT', 'TRUST_REVIEW', 'APPROVED', 'FURTHER_PROCESS']}})
    approved_requests = db.adoption_requests.count_documents({'status': 'APPROVED'})
    completed_cases = db.adoption_requests.count_documents({'status': 'COMPLETED'})
    recent_trusts = list(db.trusts.find().sort('created_at', -1).limit(5))
    recent_requests = list(db.adoption_requests.find().sort('updated_at', -1).limit(5))

    for r in recent_requests:
        r['_id'] = str(r['_id'])
        adopter_id = r.get('adopter_id')
        adopter = None
        if adopter_id:
            try: adopter = db.users.find_one({'_id': ObjectId(adopter_id)})
            except Exception: adopter = db.users.find_one({'_id': adopter_id})
        r['adopter'] = adopter

    notifications = get_user_notifications(user_id, limit=5)
    unread_count_val = get_unread_count(user_id)
    return render_template('admin/dashboard.html', user=user, total_adopters=total_adopters, total_trusts=total_trusts, verified_trusts_count=verified_trusts_count, pending_trusts_count=pending_trusts_count, active_requests=active_requests, approved_requests=approved_requests, completed_cases=completed_cases, recent_trusts=recent_trusts, recent_requests=recent_requests, notifications=notifications, unread_count=unread_count_val)

@app.route('/admin/trust-data-management', endpoint='admin_trust_data_management')
@app.route('/admin/trust-data-management', endpoint='admin.trust_data_management')
@app.route('/admin/trust-verification', endpoint='admin.trust_verification')
@admin_required
def admin_trust_data_management():
    user = get_current_user()
    user_id = str(user['_id'])
    all_agencies = list(db.trusts.find().sort('trust_name', 1))
    total_agencies = len(all_agencies)
    verified_agencies = pending_verification = review_due_count = inactive_agencies = 0

    for a in all_agencies:
        a['_id'] = str(a['_id'])
        freshness = get_freshness_status(a.get('last_verified'))
        a['freshness'] = freshness
        if a.get('verified') and a.get('status') in ['ACTIVE', 'Verified']: verified_agencies += 1
        else: pending_verification += 1
        if freshness['status'] == 'Review Due': review_due_count += 1
        if a.get('status') in ['INACTIVE', 'DEACTIVATED', 'Suspended', 'Rejected']: inactive_agencies += 1

    notifications = get_user_notifications(user_id, limit=5)
    unread_count_val = get_unread_count(user_id)
    return render_template('admin/trust_data_management.html', user=user, agencies=all_agencies, total_agencies=total_agencies, verified_agencies=verified_agencies, pending_verification=pending_verification, review_due_count=review_due_count, inactive_agencies=inactive_agencies, notifications=notifications, unread_count=unread_count_val)

@app.route('/admin/trusts', endpoint='admin_trusts_alias')
@app.route('/admin/trusts', endpoint='admin.trusts_alias')
@admin_required
def admin_trusts_alias():
    return admin_trust_data_management()

@app.route('/admin/trust/add', methods=['POST'], endpoint='admin_add_trust')
@app.route('/admin/trust/add', methods=['POST'], endpoint='admin.add_trust')
@admin_required
def admin_add_trust():
    trust_name = request.form.get('trust_name', '').strip()
    email_input = request.form.get('email', '').strip().lower()
    phone = request.form.get('phone', '').strip()
    state = request.form.get('state', '').strip()
    district = request.form.get('district', '').strip()
    city = request.form.get('city', '').strip()
    address = request.form.get('public_address', '').strip() or request.form.get('address', '').strip()
    website = request.form.get('website', '').strip()
    agency_type = request.form.get('agency_type', 'Specialized Adoption Agency (SAA)')
    verification_source = request.form.get('verification_source', 'Central Adoption Resource Authority (CARA)')
    source_url = request.form.get('source_url', '').strip()
    languages_str = request.form.get('languages', 'English, Tamil')

    if not trust_name or not email_input:
        flash('Trust Name and Email are required.', 'danger')
        return redirect(url_for('admin_trust_data_management'))

    now_iso = datetime.now(timezone.utc).isoformat()
    languages_list = [l.strip() for l in languages_str.split(',') if l.strip()]

    trust_doc = {'trust_name': trust_name, 'email': email_input, 'phone': phone, 'state': state, 'district': district, 'city': city, 'public_address': address, 'address': address, 'location': f"{city}, {state}", 'website': website, 'agency_type': agency_type, 'languages': languages_list, 'verification_source': verification_source, 'source_url': source_url, 'verified': True, 'status': 'ACTIVE', 'last_verified': now_iso, 'created_at': now_iso, 'updated_at': now_iso}
    user_doc = {'name': trust_name, 'email': email_input, 'password_hash': hash_password('Trust@123'), 'role': 'trust', 'phone': phone, 'address': f"{city}, {state}", 'language': 'English', 'created_at': now_iso, 'updated_at': now_iso}
    user_id = db.users.insert_one(user_doc).inserted_id
    trust_doc['user_id'] = str(user_id)
    db.trusts.insert_one(trust_doc)
    flash(f'Trust "{trust_name}" added successfully with password Trust@123!', 'success')
    return redirect(url_for('admin_trust_data_management'))

@app.route('/admin/trust/verify/<trust_id>', methods=['POST'], endpoint='admin_verify_trust')
@app.route('/admin/trust/verify/<trust_id>', methods=['POST'], endpoint='admin.verify_trust')
@admin_required
def admin_verify_trust(trust_id):
    action = request.form.get('action', 'verify')
    now_iso = datetime.now(timezone.utc).isoformat()
    try: query = {'_id': ObjectId(trust_id)}
    except Exception: query = {'_id': trust_id}

    if action == 'deactivate':
        db.trusts.update_one(query, {'$set': {'status': 'INACTIVE', 'verified': False, 'updated_at': now_iso}})
        flash('Agency deactivated.', 'warning')
    else:
        db.trusts.update_one(query, {'$set': {'status': 'ACTIVE', 'verified': True, 'last_verified': now_iso, 'updated_at': now_iso}})
        flash('Agency verified and activated successfully!', 'success')
    return redirect(url_for('admin_trust_data_management'))

@app.route('/admin/monitoring', endpoint='admin_monitoring')
@app.route('/admin/monitoring', endpoint='admin.monitoring')
@admin_required
def admin_monitoring():
    user = get_current_user()
    user_id = str(user['_id'])
    email_logs = list(db.email_logs.find().sort('sent_at', -1).limit(20))
    for log in email_logs: log['_id'] = str(log['_id'])
    notifications = get_user_notifications(user_id, limit=5)
    unread_count_val = get_unread_count(user_id)
    return render_template('admin/monitoring.html', user=user, email_logs=email_logs, notifications=notifications, unread_count=unread_count_val)

@app.route('/admin/notifications', methods=['GET', 'POST'], endpoint='admin_notifications')
@app.route('/admin/notifications', methods=['GET', 'POST'], endpoint='admin.notifications_page')
@admin_required
def admin_notifications():
    user = get_current_user()
    user_id = str(user['_id'])
    if request.method == 'POST':
        notif_id = request.form.get('notif_id')
        if request.form.get('action') == 'mark_all':
            mark_all_read(user_id)
            flash('All notifications marked as read.', 'success')
        elif notif_id:
            mark_notification_read(notif_id)
            flash('Notification marked as read.', 'success')
        return redirect(url_for('admin_notifications'))

    filter_type = request.args.get('filter', 'all')
    all_notifs = get_user_notifications(user_id, limit=50)
    notifs_list = [n for n in all_notifs if not n.get('is_read')] if filter_type == 'unread' else all_notifs
    unread_count_val = get_unread_count(user_id)
    return render_template('admin/notifications.html', user=user, notifications=notifs_list, unread_count=unread_count_val, filter_type=filter_type)

@app.route('/admin/profile', methods=['GET', 'POST'], endpoint='admin_profile')
@app.route('/admin/profile', methods=['GET', 'POST'], endpoint='admin.profile')
@admin_required
def admin_profile():
    user = get_current_user()
    user_id = str(user['_id'])
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email_input = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        update_data = {'name': name, 'email': email_input, 'phone': phone, 'updated_at': datetime.now(timezone.utc).isoformat()}
        try: db.users.update_one({'_id': ObjectId(user_id)}, {'$set': update_data})
        except Exception: db.users.update_one({'_id': user_id}, {'$set': update_data})
        flash('Admin profile updated.', 'success')
        return redirect(url_for('admin_profile'))

    notifications = get_user_notifications(user_id, limit=5)
    unread_count_val = get_unread_count(user_id)
    return render_template('admin/profile.html', user=user, notifications=notifications, unread_count=unread_count_val)


# ====================================================
# 14. REST API ROUTES (@app.route)
# ====================================================
@app.route('/api/notifications', methods=['GET'], endpoint='api_list_notifications')
@app.route('/api/notifications', methods=['GET'], endpoint='notifications.list_notifications')
@login_required
def api_list_notifications():
    user = get_current_user()
    if not user: return jsonify({'notifications': [], 'unread_count': 0})
    user_id = str(user['_id'])
    return jsonify({'notifications': get_user_notifications(user_id, limit=20), 'unread_count': get_unread_count(user_id)})

@app.route('/api/notifications/mark-read/<notif_id>', methods=['POST'], endpoint='api_mark_notification_read')
@app.route('/api/notifications/mark-read/<notif_id>', methods=['POST'], endpoint='notifications.mark_read')
@login_required
def api_mark_notification_read(notif_id):
    mark_notification_read(notif_id)
    return jsonify({'success': True})

@app.route('/api/notifications/mark-all-read', methods=['POST'], endpoint='api_mark_all_notifications_read')
@app.route('/api/notifications/mark-all-read', methods=['POST'], endpoint='notifications.mark_all')
@login_required
def api_mark_all_notifications_read():
    user = get_current_user()
    if user: mark_all_read(str(user['_id']))
    return jsonify({'success': True})

@app.route('/api/agencies', methods=['GET'], endpoint='api_get_agencies')
@app.route('/api/agencies', methods=['GET'], endpoint='api_agencies.api_get_agencies')
def api_get_agencies():
    state = request.args.get('state', '').strip()
    district = request.args.get('district', '').strip()
    city = request.args.get('city', '').strip()
    language = request.args.get('language', '').strip()
    agency_type = request.args.get('agency_type', '').strip()
    search = request.args.get('search', '').strip()

    query = {'verified': True, 'status': {'$in': ['ACTIVE', 'Verified']}}
    if state: query['state'] = {'$regex': re.escape(state), '$options': 'i'}
    if district: query['district'] = {'$regex': re.escape(district), '$options': 'i'}
    if city: query['city'] = {'$regex': re.escape(city), '$options': 'i'}
    if language: query['languages'] = {'$regex': re.escape(language), '$options': 'i'}
    if agency_type: query['agency_type'] = {'$regex': re.escape(agency_type), '$options': 'i'}
    if search:
        query['$or'] = [
            {'trust_name': {'$regex': re.escape(search), '$options': 'i'}},
            {'city': {'$regex': re.escape(search), '$options': 'i'}},
            {'district': {'$regex': re.escape(search), '$options': 'i'}},
            {'state': {'$regex': re.escape(search), '$options': 'i'}}
        ]

    agencies = list(db.trusts.find(query).sort('trust_name', 1))
    result = []
    for a in agencies:
        result.append({
            'id': str(a['_id']), 'agency_name': a.get('trust_name'), 'state': a.get('state'),
            'district': a.get('district'), 'city': a.get('city'), 'public_address': a.get('address') or a.get('location'),
            'phone': a.get('phone'), 'email': a.get('email'), 'website': a.get('website'),
            'languages': a.get('languages'), 'agency_type': a.get('agency_type'), 'verified': a.get('verified'),
            'verification_source': a.get('verification_source'), 'source_url': a.get('source_url'),
            'last_verified': a.get('last_verified'), 'freshness': get_freshness_status(a.get('last_verified'))
        })
    return jsonify({'count': len(result), 'agencies': result})

@app.route('/api/agencies/<agency_id>', methods=['GET'], endpoint='api_get_agency_detail')
@app.route('/api/agencies/<agency_id>', methods=['GET'], endpoint='api_agencies.api_get_agency_detail')
def api_get_agency_detail(agency_id):
    try: agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception: agency = db.trusts.find_one({'_id': agency_id})

    if not agency or not agency.get('verified') or agency.get('status') not in ['ACTIVE', 'Verified']:
        return jsonify({'error': 'Active verified agency record not found.'}), 404

    return jsonify({
        'id': str(agency['_id']), 'agency_name': agency.get('trust_name'), 'state': agency.get('state'),
        'district': agency.get('district'), 'city': agency.get('city'), 'public_address': agency.get('address') or agency.get('location'),
        'phone': agency.get('phone'), 'email': agency.get('email'), 'website': agency.get('website'),
        'languages': agency.get('languages'), 'agency_type': agency.get('agency_type'), 'verified': agency.get('verified'),
        'verification_source': agency.get('verification_source'), 'source_url': agency.get('source_url'),
        'last_verified': agency.get('last_verified'), 'freshness': get_freshness_status(agency.get('last_verified'))
    })

@app.route('/api/admin/agencies', methods=['POST'], endpoint='api_admin_add_agency')
@app.route('/api/admin/agencies', methods=['POST'], endpoint='api_agencies.api_admin_add_agency')
@admin_required
def api_admin_add_agency():
    data = request.get_json() or request.form
    trust_name = data.get('agency_name') or data.get('trust_name') or ''
    if not trust_name: return jsonify({'error': 'Agency name is required.'}), 400
    now_iso = datetime.now(timezone.utc).isoformat()
    mark_verified = bool(data.get('verified'))
    agency_doc = {
        'trust_name': trust_name.strip(), 'state': (data.get('state') or 'Tamil Nadu').strip(),
        'district': (data.get('district') or '').strip(), 'city': (data.get('city') or '').strip(),
        'address': (data.get('address') or '').strip(), 'location': f"{data.get('city')}, {data.get('state')}",
        'phone': (data.get('phone') or '').strip(), 'email': validate_email(data.get('email', '')),
        'website': validate_url(data.get('website', '')), 'languages': data.get('languages', ['English', 'Tamil']),
        'agency_type': (data.get('agency_type') or 'Specialized Adoption Agency (SAA)').strip(),
        'verified': mark_verified, 'verification_source': (data.get('verification_source') or 'Official CARA Registry').strip(),
        'source_url': validate_url(data.get('source_url', '')), 'last_verified': now_iso if mark_verified else None,
        'status': 'ACTIVE' if mark_verified else 'PENDING_REVIEW', 'created_at': now_iso, 'updated_at': now_iso
    }
    res = db.trusts.insert_one(agency_doc)
    agency_doc['_id'] = str(res.inserted_id)
    return jsonify({'success': True, 'agency': agency_doc}), 201

@app.route('/api/admin/agencies/<agency_id>', methods=['PUT'], endpoint='api_admin_update_agency')
@app.route('/api/admin/agencies/<agency_id>', methods=['PUT'], endpoint='api_agencies.api_admin_update_agency')
@admin_required
def api_admin_update_agency(agency_id):
    try: agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception: agency = db.trusts.find_one({'_id': agency_id})
    if not agency: return jsonify({'error': 'Agency not found.'}), 404
    data = request.get_json() or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    update_doc = {'updated_at': now_iso}
    for field in ['trust_name', 'state', 'district', 'city', 'address', 'phone', 'email', 'website', 'agency_type', 'verification_source', 'source_url']:
        if field in data: update_doc[field] = data[field]
    if 'languages' in data: update_doc['languages'] = data['languages']
    db.trusts.update_one({'_id': agency['_id']}, {'$set': update_doc})
    return jsonify({'success': True, 'updated_id': agency_id})

@app.route('/api/admin/agencies/<agency_id>/verify', methods=['POST'], endpoint='api_admin_verify_agency')
@app.route('/api/admin/agencies/<agency_id>/verify', methods=['POST'], endpoint='api_agencies.api_admin_verify_agency')
@admin_required
def api_admin_verify_agency(agency_id):
    try: agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception: agency = db.trusts.find_one({'_id': agency_id})
    if not agency: return jsonify({'error': 'Agency not found.'}), 404
    data = request.get_json() or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    db.trusts.update_one({'_id': agency['_id']}, {'$set': {
        'verified': True, 'status': 'ACTIVE',
        'verification_source': data.get('verification_source') or agency.get('verification_source') or 'Official CARA Registry',
        'source_url': data.get('source_url') or agency.get('source_url') or '',
        'last_verified': now_iso, 'updated_at': now_iso
    }})
    return jsonify({'success': True, 'message': 'Agency verified and activated.'})

@app.route('/api/admin/agencies/<agency_id>/deactivate', methods=['POST'], endpoint='api_admin_deactivate_agency')
@app.route('/api/admin/agencies/<agency_id>/deactivate', methods=['POST'], endpoint='api_agencies.api_admin_deactivate_agency')
@admin_required
def api_admin_deactivate_agency(agency_id):
    try: agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception: agency = db.trusts.find_one({'_id': agency_id})
    if not agency: return jsonify({'error': 'Agency not found.'}), 404
    now_iso = datetime.now(timezone.utc).isoformat()
    db.trusts.update_one({'_id': agency['_id']}, {'$set': {'status': 'INACTIVE', 'verified': False, 'updated_at': now_iso}})
    return jsonify({'success': True, 'message': 'Agency deactivated.'})

@app.route('/api/admin/agencies/<agency_id>/reactivate', methods=['POST'], endpoint='api_admin_reactivate_agency')
@app.route('/api/admin/agencies/<agency_id>/reactivate', methods=['POST'], endpoint='api_agencies.api_admin_reactivate_agency')
@admin_required
def api_admin_reactivate_agency(agency_id):
    try: agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception: agency = db.trusts.find_one({'_id': agency_id})
    if not agency: return jsonify({'error': 'Agency not found.'}), 404
    now_iso = datetime.now(timezone.utc).isoformat()
    db.trusts.update_one({'_id': agency['_id']}, {'$set': {'status': 'ACTIVE', 'verified': True, 'last_verified': now_iso, 'updated_at': now_iso}})
    return jsonify({'success': True, 'message': 'Agency reactivated.'})

@app.route('/api/admin/agencies/import', methods=['POST'], endpoint='api_admin_import_csv')
@app.route('/api/admin/agencies/import', methods=['POST'], endpoint='api_agencies.api_admin_import_csv')
@admin_required
def api_admin_import_csv():
    if 'csv_file' not in request.files: return jsonify({'error': 'No csv_file parameter provided.'}), 400
    file = request.files['csv_file']
    res = import_agencies_from_csv(file.stream)
    return jsonify(res)

@app.route('/api/admin/agencies/export', methods=['GET'], endpoint='api_admin_export_csv')
@app.route('/api/admin/agencies/export', methods=['GET'], endpoint='api_agencies.api_admin_export_csv')
@admin_required
def api_admin_export_csv():
    csv_data = export_agencies_to_csv()
    return Response(csv_data, mimetype="text/csv", headers={"Content-disposition": "attachment; filename=adoption_agencies_export.csv"})

@app.route('/api/ai/ask', methods=['POST'], endpoint='api_ask_ai')
@app.route('/api/ai/ask', methods=['POST'], endpoint='ai.ask_ai')
@login_required
def api_ask_ai():
    user = get_current_user()
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    language = data.get('language', user.get('language', 'English') if user else 'English')
    if not question: return jsonify({'error': 'Question cannot be empty.'}), 400
    result = process_ai_query(question, target_lang=language)
    return jsonify({'question': question, 'response': result.get('response', ''), 'agencies': result.get('agencies', []), 'language': language, 'timestamp': datetime.now().strftime("%I:%M %p")})

@app.route('/api/ai/agency-search', methods=['POST'], endpoint='api_agency_search')
@app.route('/api/ai/agency-search', methods=['POST'], endpoint='ai.agency_search')
@login_required
def api_agency_search():
    user = get_current_user()
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    language = data.get('language', user.get('language', 'English') if user else 'English')
    if not question: return jsonify({'error': 'Question cannot be empty.'}), 400
    result = process_ai_query(question, target_lang=language)
    return jsonify({'question': question, 'response': result.get('response', ''), 'agencies': result.get('agencies', []), 'language': language, 'timestamp': datetime.now().strftime("%I:%M %p")})


# ====================================================
# 15. MAIN SERVER EXECUTION
# ====================================================
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
