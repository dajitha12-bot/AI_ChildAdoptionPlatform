from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, timezone
from bson.objectid import ObjectId
from database.mongodb import db
from utils.auth import get_current_user, hash_password
from utils.decorators import trust_required
from services.notification_service import get_user_notifications, create_notification, get_unread_count
from services.email_service import send_approval_email, send_status_update_email

trust_bp = Blueprint('trust', __name__, url_prefix='/trust')

def _get_trust_doc(user):
    user_id = str(user['_id'])
    trust = db.trusts.find_one({'user_id': user_id})
    if not trust:
        trust = db.trusts.find_one({'email': user.get('email')})
    return trust

@trust_bp.route('/dashboard')
@trust_required
def dashboard():
    user = get_current_user()
    user_id = str(user['_id'])
    trust = _get_trust_doc(user)
    trust_id = str(trust['_id']) if trust else None

    # Calculate dashboard statistics
    if trust_id:
        total_new = db.adoption_requests.count_documents({'trust_id': trust_id, 'status': 'REQUEST_SENT'})
        pending_review = db.adoption_requests.count_documents({'trust_id': trust_id, 'status': 'TRUST_REVIEW'})
        approved_count = db.adoption_requests.count_documents({'trust_id': trust_id, 'status': 'APPROVED'})
        active_count = db.adoption_requests.count_documents({'trust_id': trust_id, 'status': {'$in': ['TRUST_REVIEW', 'APPROVED', 'FURTHER_PROCESS']}})
        completed_count = db.adoption_requests.count_documents({'trust_id': trust_id, 'status': 'COMPLETED'})
        recent_requests = list(db.adoption_requests.find({'trust_id': trust_id}).sort('updated_at', -1).limit(5))
    else:
        total_new = 0
        pending_review = 0
        approved_count = 0
        active_count = 0
        completed_count = 0
        recent_requests = []

    # Join adopter details for recent requests
    for req in recent_requests:
        req['_id'] = str(req['_id'])
        adopter = None
        try:
            adopter = db.users.find_one({'_id': ObjectId(req['adopter_id'])})
        except Exception:
            adopter = db.users.find_one({'_id': req['adopter_id']})
        req['adopter'] = adopter

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'trust/dashboard.html',
        user=user,
        trust=trust,
        total_new=total_new,
        pending_review=pending_review,
        approved_count=approved_count,
        active_count=active_count,
        completed_count=completed_count,
        recent_requests=recent_requests,
        notifications=notifications,
        unread_count=unread_count
    )

@trust_bp.route('/profile', methods=['GET', 'POST'])
@trust_required
def profile():
    user = get_current_user()
    user_id = str(user['_id'])
    trust = _get_trust_doc(user)

    if request.method == 'POST':
        trust_name = request.form.get('trust_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        location = request.form.get('location', '').strip()
        description = request.form.get('description', '').strip()
        languages_str = request.form.get('languages', 'English, Tamil')
        new_password = request.form.get('new_password', '').strip()

        languages_list = [l.strip() for l in languages_str.split(',') if l.strip()]

        trust_update = {
            'trust_name': trust_name,
            'email': email,
            'phone': phone,
            'location': location,
            'description': description,
            'languages': languages_list,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }

        user_update = {
            'name': trust_name,
            'email': email,
            'phone': phone,
            'address': location,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        if new_password:
            user_update['password_hash'] = hash_password(new_password)

        if trust:
            db.trusts.update_one({'_id': trust['_id']}, {'$set': trust_update})

        try:
            db.users.update_one({'_id': ObjectId(user_id)}, {'$set': user_update})
        except Exception:
            db.users.update_one({'_id': user_id}, {'$set': user_update})

        flash('Trust profile updated successfully!', 'success')
        return redirect(url_for('trust.profile'))

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)
    return render_template('trust/profile.html', user=user, trust=trust, notifications=notifications, unread_count=unread_count)

@trust_bp.route('/requests')
@trust_required
def requests_list():
    user = get_current_user()
    user_id = str(user['_id'])
    trust = _get_trust_doc(user)
    trust_id = str(trust['_id']) if trust else None

    requests_cursor = list(db.adoption_requests.find({'trust_id': trust_id}).sort('updated_at', -1)) if trust_id else []

    for req in requests_cursor:
        req['_id'] = str(req['_id'])
        adopter = None
        try:
            adopter = db.users.find_one({'_id': ObjectId(req['adopter_id'])})
        except Exception:
            adopter = db.users.find_one({'_id': req['adopter_id']})
        req['adopter'] = adopter

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'trust/requests.html',
        user=user,
        trust=trust,
        requests=requests_cursor,
        notifications=notifications,
        unread_count=unread_count
    )

@trust_bp.route('/request/action/<req_id>', methods=['POST'])
@trust_required
def request_action(req_id):
    user = get_current_user()
    trust = _get_trust_doc(user)
    trust_id = session.get('trust_id') or (str(trust['_id']) if trust else None)
    
    action = request.form.get('action', '').lower() # approve / reject / status_update
    new_status = request.form.get('new_status', 'APPROVED')
    remarks = request.form.get('remarks', '').strip()

    try:
        req = db.adoption_requests.find_one({'_id': ObjectId(req_id)})
    except Exception:
        req = db.adoption_requests.find_one({'_id': req_id})

    if not req:
        flash('Adoption request not found.', 'danger')
        return redirect(url_for('trust.requests_list'))

    # CRITICAL SECURITY RULE: Verify application belongs to the logged-in trust
    if not trust_id or str(req.get('trust_id')) != trust_id:
        flash('Unauthorized access: You are not authorized to access or process this application.', 'danger')
        return redirect(url_for('trust.requests_list'))

    adopter_id = req.get('adopter_id')
    adopter = None
    try:
        adopter = db.users.find_one({'_id': ObjectId(adopter_id)})
    except Exception:
        adopter = db.users.find_one({'_id': adopter_id})

    adopter_name = adopter.get('name', 'Adopter') if adopter else 'Adopter'
    adopter_email = adopter.get('email', '') if adopter else ''
    trust_name = trust.get('trust_name', 'Adoption Trust') if trust else 'Adoption Trust'

    if action == 'approve':
        status_to_set = 'APPROVED'
        stage_to_set = 'APPROVED'
    elif action == 'reject':
        status_to_set = 'REJECTED'
        stage_to_set = 'REJECTED'
    else:
        status_to_set = new_status
        stage_to_set = new_status

    # Update MongoDB request status
    now_iso = datetime.now(timezone.utc).isoformat()
    update_dict = {'status': status_to_set, 'updated_at': now_iso}
    if remarks:
        update_dict['remarks'] = remarks
    if status_to_set == 'APPROVED':
        update_dict['approved_at'] = now_iso

    db.adoption_requests.update_one({'_id': req['_id']}, {'$set': update_dict})
    
    # Also update adoption_applications collection
    app_doc = db.adoption_applications.find_one({'adopter_id': adopter_id})
    if not app_doc:
        app_doc = db.adoption_applications.find_one({'application_id': req.get('request_id')})

    if app_doc:
        db.adoption_applications.update_one({'_id': app_doc['_id']}, {'$set': update_dict})
        applicant_email = app_doc.get('applicant_email') or adopter_email
        application_id = app_doc.get('application_id') or req.get('request_id')
    else:
        applicant_email = adopter_email
        application_id = req.get('request_id', 'APP-2026-00001')

    # Update journey timeline stage
    journey_update = {
        'current_stage': stage_to_set,
        'updated_at': now_iso
    }
    if status_to_set == 'APPROVED':
        journey_update['approved'] = True
    elif status_to_set == 'FURTHER_PROCESS':
        journey_update['further_process'] = True
    elif status_to_set == 'COMPLETED':
        journey_update['completed'] = True

    db.journeys.update_one({'request_id': req.get('request_id')}, {'$set': journey_update})

    # Create in-app notification for adopter
    notif_msg = f"Your adoption request ({application_id}) has been updated to: {status_to_set} by {trust_name}."
    create_notification(adopter_id, notif_msg, notif_type='status_update')

    # MANDATORY SMTP Email Workflow (Section 10 Format)
    from services.email_service import send_application_status_update_email
    email_sent, email_feedback = send_application_status_update_email(
        applicant_email, application_id, trust_name, status_to_set, user_id=adopter_id
    )
    flash(f"Status updated to '{status_to_set}'. Notification & email sent to {applicant_email}.", 'success' if email_sent else 'info')

    return redirect(url_for('trust.requests_list'))

@trust_bp.route('/applications')
@trust_required
def applications():
    user = get_current_user()
    user_id = str(user['_id'])
    trust = _get_trust_doc(user)
    trust_id = str(trust['_id']) if trust else None

    applications_cursor = list(db.adoption_requests.find({'trust_id': trust_id}).sort('updated_at', -1)) if trust_id else []

    for req in applications_cursor:
        req['_id'] = str(req['_id'])
        adopter = None
        try:
            adopter = db.users.find_one({'_id': ObjectId(req['adopter_id'])})
        except Exception:
            adopter = db.users.find_one({'_id': req['adopter_id']})
        req['adopter'] = adopter

        journey = db.journeys.find_one({'request_id': req.get('request_id')})
        req['journey'] = journey

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'trust/applications.html',
        user=user,
        trust=trust,
        applications=applications_cursor,
        notifications=notifications,
        unread_count=unread_count
    )
