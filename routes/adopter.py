"""
Adopter Routes (Adopter Portal - 4 Main Pages + Profile & Journey)
Handles adopter dashboard, searching verified trusts, application submissions, AI assistant, and notifications.
"""
import re
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file, current_app
from werkzeug.utils import secure_filename
from datetime import datetime, timezone
from bson.objectid import ObjectId
from database.mongodb import db
from utils.auth import get_current_user, hash_password
from utils.decorators import adopter_required
from services.notification_service import get_user_notifications, create_notification, get_unread_count
from services.agency_service import get_freshness_status
from services.ai_agent import process_ai_query
from services.email_service import send_application_submitted_email

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

# Helper function to find trust document safely
def _find_trust_by_id(trust_id_str):
    if not trust_id_str:
        return None
    try:
        trust = db.trusts.find_one({'_id': ObjectId(trust_id_str)})
    except Exception:
        trust = db.trusts.find_one({'_id': trust_id_str})
    return trust


# ----------------------------------------------------
# ADOPTER PAGE 1: Dashboard
# ----------------------------------------------------
@adopter_bp.route('/dashboard')
@adopter_required
def dashboard():
    """Adopter Dashboard showing status, selected trust, journey stage, and notifications."""
    user = get_current_user()
    user_id = str(user['_id'])

    # Step 1: Query adoption request for logged in user
    req = db.adoption_requests.find_one({'adopter_id': user_id})

    # Step 2: Query journey and selected trust details
    journey = db.journeys.find_one({'request_id': req.get('request_id')}) if req else None
    trust = _find_trust_by_id(req.get('trust_id')) if req and req.get('trust_id') else None

    # Step 3: Fetch adopter notifications
    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    # Step 4: Prepare display strings
    status_str = req.get('status', 'REGISTRATION') if req else 'REGISTRATION'
    journey_stage = journey.get('current_stage', 'PROFILE_COMPLETED' if user.get('family_info') else 'REGISTRATION') if journey else 'REGISTRATION'
    trust_name = trust.get('trust_name', 'Not Selected') if trust else 'Not Selected'
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


# ----------------------------------------------------
# ADOPTER PAGE 2: Trust Directory & Application Form
# ----------------------------------------------------
@adopter_bp.route('/trusts')
@adopter_required
def verified_trusts():
    """Displays verified adoption agencies directory and dynamic application form."""
    user = get_current_user()
    user_id = str(user['_id'])

    # Step 1: Read search and filter parameters
    state_filter = request.args.get('state', '').strip()
    district_filter = request.args.get('district', '').strip()
    city_filter = request.args.get('city', '').strip()
    language_filter = request.args.get('language', '').strip()
    agency_type_filter = request.args.get('agency_type', '').strip()
    search_query = request.args.get('search', '').strip()
    apply_trust_id = request.args.get('apply_trust_id', '').strip()

    # Step 2: Build MongoDB query for verified active trusts
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

    # Step 3: Fetch matching trusts
    trusts_cursor = list(db.trusts.find(query))
    for t in trusts_cursor:
        t['_id'] = str(t['_id'])
        t['freshness'] = get_freshness_status(t.get('last_verified'))
    trusts_cursor.sort(key=lambda x: x.get('trust_name', ''))

    # Unique filter options for dropdowns
    available_states = sorted(list(set([s for s in db.trusts.distinct('state') if s])))
    available_districts = sorted(list(set([d for d in db.trusts.distinct('district') if d])))
    available_cities = sorted(list(set([c for c in db.trusts.distinct('city') if c])))

    # Step 4: Check if adopter has an existing application
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

    journey = db.journeys.find_one({'request_id': application.get('application_id')}) if application else None
    applied_trust = _find_trust_by_id(application.get('trust_id')) if application and application.get('trust_id') else None
    target_trust = _find_trust_by_id(apply_trust_id) if apply_trust_id else None

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'adopter/trusts.html',
        user=user,
        trusts=trusts_cursor,
        application=application,
        journey=journey,
        applied_trust=applied_trust,
        target_trust=target_trust,
        available_states=available_states,
        available_districts=available_districts,
        available_cities=available_cities,
        apply_trust_id=apply_trust_id,
        notifications=notifications,
        unread_count=unread_count
    )


@adopter_bp.route('/apply-agency', methods=['POST'])
@adopter_required
def apply_agency():
    """Handles submission of adoption application to selected agency."""
    user = get_current_user()
    user_id = str(user['_id'])
    trust_id = request.form.get('trust_id', '').strip()

    if not trust_id:
        flash('Please select an adoption agency to apply.', 'danger')
        return redirect(url_for('adopter.verified_trusts'))

    trust = _find_trust_by_id(trust_id)
    if not trust:
        flash('Selected adoption agency not found.', 'danger')
        return redirect(url_for('adopter.verified_trusts'))

    # Collect form inputs
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

    # Insert Application Document
    app_doc = {
        'application_id': app_id,
        'adopter_id': user_id,
        'trust_id': str(trust['_id']),
        'trust_name': trust.get('trust_name'),
        'applicant_name': applicant_name,
        'applicant_email': applicant_email,
        'phone': phone,
        'address': address,
        'state': state,
        'district': district,
        'city': city,
        'language': language,
        'marital_status': family_status,
        'occupation': occupation,
        'preferences': preferences,
        'status': 'SUBMITTED',
        'created_at': now_iso,
        'updated_at': now_iso
    }

    # Delete previous request/application if re-applying
    db.adoption_applications.delete_many({'adopter_id': user_id})
    db.adoption_requests.delete_many({'adopter_id': user_id})
    db.journeys.delete_many({'adopter_id': user_id})

    db.adoption_applications.insert_one(app_doc)

    # Insert Adoption Request
    req_doc = {
        'request_id': app_id,
        'adopter_id': user_id,
        'trust_id': str(trust['_id']),
        'status': 'SUBMITTED',
        'created_at': now_iso,
        'updated_at': now_iso
    }
    db.adoption_requests.insert_one(req_doc)

    # Insert Journey Stage Tracking Document
    journey_doc = {
        'request_id': app_id,
        'adopter_id': user_id,
        'registration': True,
        'profile_completed': True,
        'request_sent': True,
        'trust_review': True,
        'approved': False,
        'further_process': False,
        'completed': False,
        'current_stage': 'SUBMITTED',
        'updated_at': now_iso
    }
    db.journeys.insert_one(journey_doc)

    # Create Notifications for Adopter and Trust
    create_notification(user_id, f"Application {app_id} submitted to {trust.get('trust_name')}.", notif_type='application')
    if trust.get('user_id'):
        create_notification(str(trust['user_id']), f"New adoption application ({app_id}) received from {applicant_name}.", notif_type='application')

    # Dispatch SMTP Email Confirmation
    send_application_submitted_email(applicant_email, app_id, trust.get('trust_name'), user_id=user_id)

    flash(f"Application {app_id} submitted successfully to {trust.get('trust_name')}! Confirmation email sent.", 'success')
    return redirect(url_for('adopter.verified_trusts'))


# ----------------------------------------------------
# ADOPTER PAGE 3: AI Adoption Assistant
# ----------------------------------------------------
@adopter_bp.route('/ai-assistant', methods=['GET', 'POST'])
@adopter_required
def ai_assistant():
    """Bilingual AI Adoption Guidance Assistant."""
    user = get_current_user()
    user_id = str(user['_id'])

    req = db.adoption_requests.find_one({'adopter_id': user_id})
    journey = db.journeys.find_one({'request_id': req.get('request_id')}) if req else None
    trust = _find_trust_by_id(req.get('trust_id')) if req and req.get('trust_id') else None

    user_context = {
        'user': user,
        'request': req,
        'journey': journey,
        'trust': trust
    }

    ai_messages = []
    if request.method == 'POST':
        question = request.form.get('question', '').strip()
        if question:
            answer = process_ai_query(question, user_context)
            ai_messages.append({'role': 'user', 'content': question})
            ai_messages.append({'role': 'assistant', 'content': answer})

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'adopter/ai_assistant.html',
        user=user,
        ai_messages=ai_messages,
        notifications=notifications,
        unread_count=unread_count
    )


# ----------------------------------------------------
# ADOPTER PAGE 4: Notifications
# ----------------------------------------------------
@adopter_bp.route('/notifications', methods=['GET', 'POST'])
@adopter_required
def notifications_page():
    """Adopter Notifications Management."""
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


# ----------------------------------------------------
# ADOPTER PROFILE & JOURNEY TIMELINE VIEWS
# ----------------------------------------------------
@adopter_bp.route('/profile', methods=['GET', 'POST'])
@adopter_required
def profile():
    """Adopter profile details and family info editor."""
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

        flash('Profile updated successfully!', 'success')
        return redirect(url_for('adopter.profile'))

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)
    return render_template('adopter/profile.html', user=user, notifications=notifications, unread_count=unread_count)


@adopter_bp.route('/journey')
@adopter_required
def journey():
    """Adopter 5-stage adoption journey timeline."""
    user = get_current_user()
    user_id = str(user['_id'])

    req = db.adoption_requests.find_one({'adopter_id': user_id})
    journey_doc = db.journeys.find_one({'request_id': req.get('request_id')}) if req else None
    trust = _find_trust_by_id(req.get('trust_id')) if req and req.get('trust_id') else None

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'adopter/journey.html',
        user=user,
        request=req,
        journey=journey_doc,
        trust=trust,
        notifications=notifications,
        unread_count=unread_count,
        JOURNEY_STAGES=JOURNEY_STAGES
    )
