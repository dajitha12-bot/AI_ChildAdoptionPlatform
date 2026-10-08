import re
import os
import random
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file, current_app
from werkzeug.utils import secure_filename
from datetime import datetime, timezone
from bson.objectid import ObjectId
from database.mongodb import db
from utils.auth import get_current_user, hash_password
from utils.decorators import adopter_required, login_required
from services.notification_service import get_user_notifications, create_notification, get_unread_count
from services.agency_service import get_freshness_status
from services.ai_agent import process_ai_query

adopter_bp = Blueprint('adopter', __name__, url_prefix='/adopter')

JOURNEY_STAGES = [
    'REGISTRATION',
    'PROFILE_COMPLETED',
    'REQUEST_SENT',
    'TRUST_REVIEW',
    'SUBMITTED',
    'UNDER_REVIEW',
    'APPROVED',
    'FURTHER_PROCESS',
    'COMPLETED'
]

@adopter_bp.route('/dashboard')
@adopter_required
def dashboard():
    user = get_current_user()
    user_id = str(user['_id'])

    req = db.adoption_requests.find_one({'adopter_id': user_id})

    journey = None
    if req:
        journey = db.journeys.find_one({'request_id': req.get('request_id')})

    trust = None
    if req and req.get('trust_id'):
        try:
            trust = db.trusts.find_one({'_id': ObjectId(req['trust_id'])})
        except Exception:
            trust = db.trusts.find_one({'_id': req['trust_id']})

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    status_str = req.get('status', 'REGISTRATION') if req else 'REGISTRATION'
    journey_stage = journey.get('current_stage', 'PROFILE_COMPLETED' if user.get('family_info') else 'REGISTRATION') if journey else ('PROFILE_COMPLETED' if user.get('family_info') else 'REGISTRATION')
    trust_name = trust.get('trust_name', 'Not Selected Yet') if trust else 'Not Selected'
    latest_update = notifications[0].get('message') if notifications else 'Account registered successfully.'

    return render_template(
        'adopter/dashboard.html',
        user=user,
        request=req,
        trust=trust,
        journey=journey,
        status_str=status_str,
        journey_stage=journey_stage,
        trust_name=trust_name,
        latest_update=latest_update,
        notifications=notifications,
        unread_count=unread_count,
        JOURNEY_STAGES=JOURNEY_STAGES
    )

@adopter_bp.route('/profile', methods=['GET', 'POST'])
@adopter_required
def profile():
    user = get_current_user()
    user_id = str(user['_id'])

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
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
            'name': name,
            'email': email,
            'phone': phone,
            'address': address,
            'language': language,
            'family_info': {
                'marital_status': marital_status,
                'occupation': occupation,
                'annual_income': annual_income
            },
            'preferences': {
                'location': preferred_location,
                'age_group': preferred_age_group,
                'languages': [language]
            },
            'updated_at': datetime.now(timezone.utc).isoformat()
        }

        if new_password:
            update_data['password_hash'] = hash_password(new_password)

        try:
            db.users.update_one({'_id': ObjectId(user_id)}, {'$set': update_data})
        except Exception:
            db.users.update_one({'_id': user_id}, {'$set': update_data})

        req = db.adoption_requests.find_one({'adopter_id': user_id})
        if req:
            journey = db.journeys.find_one({'request_id': req.get('request_id')})
            if journey and journey.get('current_stage') == 'REGISTRATION':
                db.journeys.update_one(
                    {'request_id': req.get('request_id')},
                    {'$set': {'profile_completed': True, 'current_stage': 'PROFILE_COMPLETED', 'updated_at': datetime.now(timezone.utc).isoformat()}}
                )

        flash('Profile and adoption preferences updated successfully!', 'success')
        return redirect(url_for('adopter.profile'))

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)
    return render_template('adopter/profile.html', user=user, notifications=notifications, unread_count=unread_count)

@adopter_bp.route('/agencies')
@adopter_required
def verified_agencies_alias():
    return verified_trusts()

@adopter_bp.route('/trusts')
@adopter_required
def verified_trusts():
    """Single Page: India-Wide Verified Adoption Agencies Directory & Dynamic Application System."""
    user = get_current_user()
    user_id = str(user['_id'])

    state_filter = request.args.get('state', '').strip()
    district_filter = request.args.get('district', '').strip()
    city_filter = request.args.get('city', '').strip()
    language_filter = request.args.get('language', '').strip()
    agency_type_filter = request.args.get('agency_type', '').strip()
    search_query = request.args.get('search', '').strip()
    sort_by = request.args.get('sort', 'name').strip()
    apply_trust_id = request.args.get('apply_trust_id', '').strip()
    submitted_app_id = request.args.get('submitted_app_id', '').strip()

    query = {
        'verified': True,
        'status': {'$in': ['ACTIVE', 'Verified']}
    }

    if state_filter:
        query['state'] = {'$regex': re.escape(state_filter), '$options': 'i'}
    if district_filter:
        query['district'] = {'$regex': re.escape(district_filter), '$options': 'i'}
    if city_filter:
        query['city'] = {'$regex': re.escape(city_filter), '$options': 'i'}
    if language_filter:
        query['languages'] = {'$regex': re.escape(language_filter), '$options': 'i'}
    if agency_type_filter:
        query['agency_type'] = {'$regex': re.escape(agency_type_filter), '$options': 'i'}
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

    if sort_by == 'state':
        trusts_cursor.sort(key=lambda x: (x.get('state', ''), x.get('trust_name', '')))
    elif sort_by == 'recently_verified':
        trusts_cursor.sort(key=lambda x: x.get('last_verified') or '', reverse=True)
    else: # name A-Z
        trusts_cursor.sort(key=lambda x: x.get('trust_name', ''))

    available_states = sorted(list(set([s for s in db.trusts.distinct('state') if s])))
    available_districts = sorted(list(set([d for d in db.trusts.distinct('district') if d])))
    available_cities = sorted(list(set([c for c in db.trusts.distinct('city') if c])))

    application = db.adoption_applications.find_one({'adopter_id': user_id})
    if not application:
        req = db.adoption_requests.find_one({'adopter_id': user_id})
        if req:
            application = {
                'application_id': req.get('request_id'),
                'trust_id': req.get('trust_id'),
                'applicant_name': user.get('name'),
                'applicant_email': user.get('email'),
                'status': req.get('status', 'SUBMITTED'),
                'created_at': req.get('created_at'),
                'updated_at': req.get('updated_at')
            }

    journey = None
    applied_trust = None
    if application:
        app_id = application.get('application_id')
        journey = db.journeys.find_one({'request_id': app_id})
        if application.get('trust_id'):
            try:
                applied_trust = db.trusts.find_one({'_id': ObjectId(application['trust_id'])})
            except Exception:
                applied_trust = db.trusts.find_one({'_id': application['trust_id']})

    target_trust = None
    if apply_trust_id:
        try:
            target_trust = db.trusts.find_one({'_id': ObjectId(apply_trust_id)})
        except Exception:
            target_trust = db.trusts.find_one({'_id': apply_trust_id})

    selected_trust_id = application.get('trust_id') if application else None

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'adopter/trusts.html',
        user=user,
        trusts=trusts_cursor,
        selected_trust_id=selected_trust_id,
        application=application,
        journey=journey,
        applied_trust=applied_trust,
        target_trust=target_trust,
        available_states=available_states,
        available_districts=available_districts,
        available_cities=available_cities,
        apply_trust_id=apply_trust_id,
        submitted_app_id=submitted_app_id,
        notifications=notifications,
        unread_count=unread_count
    )

@adopter_bp.route('/apply-agency', methods=['POST'])
@adopter_required
def apply_agency():
    """Handles dynamic application submission with file upload & SMTP email confirmation."""
    user = get_current_user()
    user_id = str(user['_id'])

    trust_id = request.form.get('trust_id', '').strip()
    applicant_name = request.form.get('applicant_name', '').strip()
    applicant_email = request.form.get('applicant_email', '').strip().lower()
    phone = request.form.get('phone', '').strip()
    date_of_birth = request.form.get('date_of_birth', '').strip()
    address = request.form.get('address', '').strip()
    state = request.form.get('state', '').strip()
    district = request.form.get('district', '').strip()
    city = request.form.get('city', '').strip()
    language = request.form.get('language', 'English').strip()

    family_status = request.form.get('family_status', '').strip()
    family_members = request.form.get('family_members', '').strip()
    occupation = request.form.get('occupation', '').strip()
    preferences = request.form.get('preferences', '').strip()
    remarks = request.form.get('remarks', '').strip()

    errors = []
    if not trust_id:
        errors.append("Please select a valid adoption agency.")
    if not applicant_name:
        errors.append("Full Name is required.")
    if not applicant_email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', applicant_email):
        errors.append("Please enter a valid email address.")
    if not phone or not re.match(r'^\+?[0-9\s\-]{7,15}$', phone):
        errors.append("Please enter a valid phone number (7-15 digits).")
    if not date_of_birth:
        errors.append("Date of Birth is required.")
    if not address:
        errors.append("Address is required.")
    if not state or not district or not city:
        errors.append("State, District, and City are required.")

    trust = None
    if trust_id:
        try:
            trust = db.trusts.find_one({'_id': ObjectId(trust_id)})
        except Exception:
            trust = db.trusts.find_one({'_id': trust_id})

    if not trust or not trust.get('verified') or trust.get('status') not in ['ACTIVE', 'Verified']:
        errors.append("The selected adoption agency is not an active verified trust.")

    ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
    MAX_FILE_SIZE = 5 * 1024 * 1024

    uploaded_files = {}
    doc_fields = [
        ('identity_proof', 'Identity Proof', True),
        ('address_proof', 'Address Proof', True),
        ('supporting_doc', 'Supporting Document', False),
        ('additional_doc', 'Additional Document', False)
    ]

    for field_key, field_label, is_required in doc_fields:
        file_obj = request.files.get(field_key)
        if is_required and (not file_obj or not file_obj.filename):
            errors.append(f"{field_label} is required.")
        elif file_obj and file_obj.filename:
            ext = file_obj.filename.rsplit('.', 1)[-1].lower() if '.' in file_obj.filename else ''
            if ext not in ALLOWED_EXTENSIONS:
                errors.append(f"{field_label} file format must be PDF, JPG, JPEG, or PNG.")
            file_obj.seek(0, 2)
            size = file_obj.tell()
            file_obj.seek(0)
            if size > MAX_FILE_SIZE:
                errors.append(f"{field_label} file size must be less than 5MB.")
            uploaded_files[field_key] = (file_obj, field_label)

    if errors:
        for err in errors:
            flash(err, 'danger')
        return redirect(url_for('adopter.verified_trusts', apply_trust_id=trust_id))

    upload_dir = os.path.join(current_app.root_path, 'uploads', 'documents')
    os.makedirs(upload_dir, exist_ok=True)

    application_id = f"APP-{datetime.now().year}-{random.randint(10000, 99999)}"

    documents_metadata = []
    for field_key, (file_obj, field_label) in uploaded_files.items():
        sec_filename = secure_filename(file_obj.filename)
        unique_filename = f"{field_key}_{application_id}_{int(datetime.now().timestamp())}_{sec_filename}"
        full_path = os.path.join(upload_dir, unique_filename)
        file_obj.save(full_path)

        documents_metadata.append({
            'document_type': field_label,
            'file_name': file_obj.filename,
            'file_reference': f"uploads/documents/{unique_filename}",
            'uploaded_at': datetime.now(timezone.utc).isoformat()
        })

    now_iso = datetime.now(timezone.utc).isoformat()

    app_doc = {
        'application_id': application_id,
        'adopter_id': user_id,
        'trust_id': str(trust['_id']),
        'trust_name': trust.get('trust_name'),
        'applicant_name': applicant_name,
        'applicant_email': applicant_email,
        'phone': phone,
        'date_of_birth': date_of_birth,
        'address': address,
        'state': state,
        'district': district,
        'city': city,
        'language': language,
        'family_status': family_status,
        'family_members': family_members,
        'occupation': occupation,
        'preferences': preferences,
        'remarks': remarks,
        'documents': documents_metadata,
        'status': 'SUBMITTED',
        'created_at': now_iso,
        'updated_at': now_iso
    }

    existing_app = db.adoption_applications.find_one({'adopter_id': user_id})
    if existing_app:
        db.adoption_applications.update_one({'_id': existing_app['_id']}, {'$set': app_doc})
    else:
        db.adoption_applications.insert_one(app_doc)

    req_doc = {
        'request_id': application_id,
        'adopter_id': user_id,
        'trust_id': str(trust['_id']),
        'applicant_email': applicant_email,
        'status': 'SUBMITTED',
        'created_at': now_iso,
        'updated_at': now_iso
    }
    db.adoption_requests.update_one({'adopter_id': user_id}, {'$set': req_doc}, upsert=True)

    journey_doc = {
        'request_id': application_id,
        'adopter_id': user_id,
        'registration': True,
        'profile_completed': True,
        'request_sent': True,
        'trust_review': False,
        'approved': False,
        'further_process': False,
        'completed': False,
        'current_stage': 'SUBMITTED',
        'updated_at': now_iso
    }
    db.journeys.update_one({'request_id': application_id}, {'$set': journey_doc}, upsert=True)

    create_notification(
        user_id,
        f"Your adoption application ({application_id}) has been submitted to {trust.get('trust_name')}. Status: SUBMITTED.",
        notif_type='request_sent'
    )

    from services.email_service import send_application_submitted_email
    email_sent, email_feedback = send_application_submitted_email(
        applicant_email, application_id, trust.get('trust_name'), user_id=user_id
    )

    if email_sent:
        flash(f"✓ APPLICATION SUBMITTED! Application ID: {application_id}. Confirmation email sent to {applicant_email}.", 'success')
    else:
        flash(f"Application submitted successfully ({application_id}), but the confirmation email could not be sent.", 'warning')

    return redirect(url_for('adopter.verified_trusts', submitted_app_id=application_id))

@adopter_bp.route('/document/<app_id>/<int:doc_idx>')
@login_required
def view_document(app_id, doc_idx):
    """Secure document viewer endpoint."""
    user = get_current_user()
    user_id = str(user['_id'])

    app_doc = db.adoption_applications.find_one({'application_id': app_id})
    if not app_doc:
        flash('Application document record not found.', 'danger')
        return redirect(url_for('adopter.verified_trusts'))

    if user['role'] == 'adopter' and app_doc.get('adopter_id') != user_id:
        flash('Unauthorized document access.', 'danger')
        return redirect(url_for('adopter.verified_trusts'))

    try:
        docs = app_doc.get('documents', [])
        if doc_idx < 0 or doc_idx >= len(docs):
            flash('Document index out of range.', 'danger')
            return redirect(url_for('adopter.verified_trusts'))

        target_doc = docs[doc_idx]
        file_ref = target_doc.get('file_reference')
        abs_path = os.path.join(current_app.root_path, file_ref)

        if os.path.exists(abs_path):
            return send_file(abs_path)
        else:
            flash('Document file not found on server.', 'danger')
            return redirect(url_for('adopter.verified_trusts'))
    except Exception as e:
        flash(f'Error retrieving document: {e}', 'danger')
        return redirect(url_for('adopter.verified_trusts'))

@adopter_bp.route('/select-trust/<trust_id>', methods=['POST'])
@adopter_required
def select_trust(trust_id):
    """Redirects select-trust calls to the single page application workflow."""
    return redirect(url_for('adopter.verified_trusts', apply_trust_id=trust_id))


@adopter_bp.route('/journey')
@adopter_required
def journey():
    user = get_current_user()
    user_id = str(user['_id'])

    req = db.adoption_requests.find_one({'adopter_id': user_id})
    journey_doc = None
    trust = None

    if req:
        journey_doc = db.journeys.find_one({'request_id': req.get('request_id')})
        if req.get('trust_id'):
            try:
                trust = db.trusts.find_one({'_id': ObjectId(req['trust_id'])})
            except Exception:
                trust = db.trusts.find_one({'_id': req['trust_id']})

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'adopter/journey.html',
        user=user,
        request=req,
        journey=journey_doc,
        trust=trust,
        JOURNEY_STAGES=JOURNEY_STAGES,
        notifications=notifications,
        unread_count=unread_count
    )

@adopter_bp.route('/ai-assistant', methods=['GET', 'POST'])
@adopter_required
def ai_assistant():
    user = get_current_user()
    user_id = str(user['_id'])

    if 'ai_messages' not in session:
        session['ai_messages'] = [{
            'sender': 'agent',
            'text': f"Hello {user.get('name', 'User')}! I am your AI Adoption Support Assistant. I can help explain your application status, adoption procedures, verified trusts in Tamil Nadu, or recent email updates.\n\nHow can I guide your adoption journey today?",
            'timestamp': datetime.now().strftime("%I:%M %p"),
            'agencies': []
        }]

    current_lang = request.args.get('lang') or request.form.get('language') or user.get('language', 'English')

    if request.method == 'POST':
        if request.form.get('clear_chat'):
            session['ai_messages'] = [{
                'sender': 'agent',
                'text': f"Hello {user.get('name', 'User')}! Chat history cleared. How can I assist your adoption journey today?",
                'timestamp': datetime.now().strftime("%I:%M %p"),
                'agencies': []
            }]
            session.modified = True
            return redirect(url_for('adopter.ai_assistant', lang=current_lang))

        question = request.form.get('question', '').strip()
        if question:
            session['ai_messages'].append({
                'sender': 'user',
                'text': question,
                'timestamp': datetime.now().strftime("%I:%M %p"),
                'agencies': []
            })

            res = process_ai_query(user_id, question, target_lang=current_lang)

            session['ai_messages'].append({
                'sender': 'agent',
                'text': res.get('response', ''),
                'timestamp': res.get('timestamp', datetime.now().strftime("%I:%M %p")),
                'agencies': res.get('agencies', [])
            })

            session.modified = True
            return redirect(url_for('adopter.ai_assistant', lang=current_lang))

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'adopter/ai_assistant.html',
        user=user,
        messages=session.get('ai_messages', []),
        current_lang=current_lang,
        notifications=notifications,
        unread_count=unread_count
    )

@adopter_bp.route('/ai-assistant/chat', methods=['POST'])
@adopter_required
def ai_assistant_chat():
    user = get_current_user()
    user_id = str(user['_id'])

    data = request.get_json() or {}
    question = data.get('question', '').strip()
    language = data.get('language', user.get('language', 'English'))

    if not question:
        return jsonify({'error': 'Please enter a valid question.'}), 400

    result = process_ai_query(user_id, question, target_lang=language)
    return jsonify(result)


# ==================================================
# PUBLIC REST API ENDPOINTS FOR AGENCIES
# ==================================================

@adopter_bp.route('/api/agencies', methods=['GET'])
def api_get_agencies():
    """GET /api/agencies - Returns active verified adoption agencies list in JSON."""
    state = request.args.get('state', '').strip()
    district = request.args.get('district', '').strip()
    city = request.args.get('city', '').strip()
    language = request.args.get('language', '').strip()
    agency_type = request.args.get('agency_type', '').strip()
    search = request.args.get('search', '').strip()

    query = {'verified': True, 'status': {'$in': ['ACTIVE', 'Verified']}}

    if state:
        query['state'] = {'$regex': re.escape(state), '$options': 'i'}
    if district:
        query['district'] = {'$regex': re.escape(district), '$options': 'i'}
    if city:
        query['city'] = {'$regex': re.escape(city), '$options': 'i'}
    if language:
        query['languages'] = {'$regex': re.escape(language), '$options': 'i'}
    if agency_type:
        query['agency_type'] = {'$regex': re.escape(agency_type), '$options': 'i'}
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
            'id': str(a['_id']),
            'agency_name': a.get('trust_name'),
            'state': a.get('state'),
            'district': a.get('district'),
            'city': a.get('city'),
            'public_address': a.get('address') or a.get('location'),
            'phone': a.get('phone'),
            'email': a.get('email'),
            'website': a.get('website'),
            'languages': a.get('languages'),
            'agency_type': a.get('agency_type'),
            'verified': a.get('verified'),
            'verification_source': a.get('verification_source'),
            'source_url': a.get('source_url'),
            'last_verified': a.get('last_verified'),
            'freshness': get_freshness_status(a.get('last_verified'))
        })

    return jsonify({'count': len(result), 'agencies': result})

@adopter_bp.route('/api/agencies/<agency_id>', methods=['GET'])
def api_get_agency_detail(agency_id):
    """GET /api/agencies/<agency_id> - Returns public details of a single agency."""
    try:
        agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception:
        agency = db.trusts.find_one({'_id': agency_id})

    if not agency or not agency.get('verified') or agency.get('status') not in ['ACTIVE', 'Verified']:
        return jsonify({'error': 'Active verified agency record not found.'}), 404

    return jsonify({
        'id': str(agency['_id']),
        'agency_name': agency.get('trust_name'),
        'state': agency.get('state'),
        'district': agency.get('district'),
        'city': agency.get('city'),
        'public_address': agency.get('address') or agency.get('location'),
        'phone': agency.get('phone'),
        'email': agency.get('email'),
        'website': agency.get('website'),
        'languages': agency.get('languages'),
        'agency_type': agency.get('agency_type'),
        'verified': agency.get('verified'),
        'verification_source': agency.get('verification_source'),
        'source_url': agency.get('source_url'),
        'last_verified': agency.get('last_verified'),
        'freshness': get_freshness_status(agency.get('last_verified'))
    })


@adopter_bp.route('/notifications', methods=['GET', 'POST'])
@adopter_required
def notifications_page():
    """Adopter Notifications Page (4th Adopter Main Page)."""
    user = get_current_user()
    user_id = str(user['_id'])

    if request.method == 'POST':
        notif_id = request.form.get('notif_id')
        if request.form.get('action') == 'mark_all':
            from services.notification_service import mark_all_read
            mark_all_read(user_id)
            flash('All notifications marked as read.', 'success')
        elif notif_id:
            from services.notification_service import mark_notification_read
            mark_notification_read(notif_id)
            flash('Notification marked as read.', 'success')
        return redirect(url_for('adopter.notifications_page'))

    filter_type = request.args.get('filter', 'all')
    all_notifications = get_user_notifications(user_id, limit=50)
    if filter_type == 'unread':
        notifications_list = [n for n in all_notifications if not n.get('is_read')]
    else:
        notifications_list = all_notifications

    unread_count = get_unread_count(user_id)
    return render_template(
        'adopter/notifications.html',
        user=user,
        notifications=notifications_list,
        unread_count=unread_count,
        filter_type=filter_type
    )
