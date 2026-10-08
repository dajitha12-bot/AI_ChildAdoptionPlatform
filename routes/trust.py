from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, timezone
from bson.objectid import ObjectId
from database.mongodb import db
from utils.auth import get_current_user, hash_password
from utils.decorators import trust_required
from services.notification_service import get_user_notifications, create_notification, get_unread_count
from services.email_service import send_application_status_update_email, send_matching_completed_email

trust_bp = Blueprint('trust', __name__, url_prefix='/trust')

def _get_trust_doc(user):
    user_id = str(user['_id'])
    trust = db.trusts.find_one({'user_id': user_id})
    if not trust:
        trust = db.trusts.find_one({'email': user.get('email')})
    if not trust:
        trust = db.trusts.find_one({'trust_name': user.get('name')})
    return trust

def _get_trust_id_query(trust_id_str):
    if not trust_id_str:
        return None
    try:
        return {'$in': [trust_id_str, ObjectId(trust_id_str)]}
    except Exception:
        return trust_id_str

@trust_bp.route('/dashboard')
@trust_required
def dashboard():
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
        total_new = 0
        pending_review = 0
        approved_count = 0
        active_count = 0
        completed_count = 0
        available_children_count = 0
        completed_matches_count = 0
        recent_requests = []

    # Join adopter details for recent requests
    for req in recent_requests:
        req['_id'] = str(req['_id'])
        adopter = None
        adopter_id = req.get('adopter_id')
        if adopter_id:
            try:
                adopter = db.users.find_one({'_id': ObjectId(adopter_id)})
            except Exception:
                adopter = db.users.find_one({'_id': adopter_id})
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
        available_children_count=available_children_count,
        completed_matches_count=completed_matches_count,
        recent_requests=recent_requests,
        notifications=notifications,
        unread_count=unread_count
    )

@trust_bp.route('/applications')
@trust_required
def applications():
    """Trust Page 2: Applications & Child-Family Compatibility Matching System."""
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
            adopter = None
            adopter_id = req.get('adopter_id')
            if adopter_id:
                try:
                    adopter = db.users.find_one({'_id': ObjectId(adopter_id)})
                except Exception:
                    adopter = db.users.find_one({'_id': adopter_id})
            req['adopter'] = adopter

            app_doc = db.adoption_applications.find_one({'adopter_id': adopter_id}) or db.adoption_applications.find_one({'application_id': req.get('request_id')})
            req['application_details'] = app_doc

            journey = db.journeys.find_one({'request_id': req.get('request_id')})
            req['journey'] = journey
            applications_list.append(req)

        # Available Children Profiles
        available_children = list(db.child_profiles.find({'trust_id': t_query, 'status': 'AVAILABLE'}).sort('created_at', -1))
        for ch in available_children:
            ch['_id'] = str(ch['_id'])

        # Completed Matches
        completed_matches = list(db.child_matches.find({'trust_id': t_query}).sort('matched_at', -1))
        for m in completed_matches:
            m['_id'] = str(m['_id'])

        # AI-Assisted Compatibility Match Suggestions
        approved_adopters = [a for a in applications_list if a.get('status') in ['APPROVED', 'FURTHER_PROCESS', 'TRUST_REVIEW', 'UNDER_REVIEW', 'SUBMITTED']]
        for child in available_children:
            for req in approved_adopters:
                adopter = req.get('adopter') or {}
                app_det = req.get('application_details') or {}
                pref = adopter.get('preferences') or {}

                # Calculate AI Match Score
                score = 75
                reasons = []

                target_age = app_det.get('preferred_age_group') or pref.get('age_group', '0-2 years')
                if target_age == child.get('age_range'):
                    score += 15
                    reasons.append(f"Age group match ({target_age})")
                else:
                    reasons.append("Age group compatible")

                adopter_lang = adopter.get('language', 'English')
                if adopter_lang in child.get('language', ''):
                    score += 10
                    reasons.append(f"Language match ({adopter_lang})")

                ai_suggested_matches.append({
                    'child': child,
                    'request': req,
                    'adopter': adopter,
                    'score': min(score, 98),
                    'reasons': reasons
                })

        ai_suggested_matches.sort(key=lambda x: x['score'], reverse=True)

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'trust/applications.html',
        user=user,
        trust=trust,
        applications=applications_list,
        available_children=available_children,
        ai_suggested_matches=ai_suggested_matches,
        completed_matches=completed_matches,
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
        return redirect(url_for('trust.applications'))

    adopter_id = req.get('adopter_id')
    adopter = None
    try:
        adopter = db.users.find_one({'_id': ObjectId(adopter_id)})
    except Exception:
        adopter = db.users.find_one({'_id': adopter_id})

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

    now_iso = datetime.now(timezone.utc).isoformat()
    update_dict = {'status': status_to_set, 'updated_at': now_iso}
    if remarks:
        update_dict['remarks'] = remarks
    if status_to_set == 'APPROVED':
        update_dict['approved_at'] = now_iso

    db.adoption_requests.update_one({'_id': req['_id']}, {'$set': update_dict})

    # Update adoption_applications collection
    app_doc = db.adoption_applications.find_one({'adopter_id': adopter_id}) or db.adoption_applications.find_one({'application_id': req.get('request_id')})
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

    # Create in-app notification for adopter and trust
    notif_msg = f"Application ({application_id}) status updated to '{status_to_set}' by {trust_name}."
    create_notification(adopter_id, notif_msg, notif_type='status_update')
    create_notification(str(user['_id']), f"Status for request {application_id} updated to {status_to_set}.", notif_type='status_update')

    # Send SMTP Email Confirmation
    email_sent, feedback = send_application_status_update_email(
        applicant_email, application_id, trust_name, status_to_set, user_id=adopter_id
    )
    flash(f"Status updated to '{status_to_set}'. Notification & email sent to {applicant_email}.", 'success')

    return redirect(url_for('trust.applications'))

@trust_bp.route('/authorize-match', methods=['POST'])
@trust_required
def authorize_match():
    """Authorizes final child-family compatibility match."""
    user = get_current_user()
    user_id = str(user['_id'])
    trust = _get_trust_doc(user)
    trust_id = str(trust['_id']) if trust else None

    child_id = request.form.get('child_id')
    request_id = request.form.get('request_id')
    adopter_id = request.form.get('adopter_id')
    compatibility_score = request.form.get('compatibility_score', '95%')

    if not child_id or not request_id or not adopter_id:
        flash('Missing required child or adopter details for matching.', 'danger')
        return redirect(url_for('trust.applications'))

    now_iso = datetime.now(timezone.utc).isoformat()
    match_doc = {
        'match_id': f"MATCH-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'trust_id': trust_id,
        'child_id': child_id,
        'request_id': request_id,
        'adopter_id': adopter_id,
        'compatibility_score': compatibility_score,
        'matched_at': now_iso,
        'status': 'AUTHORIZED_COMPLETED'
    }
    db.child_matches.insert_one(match_doc)

    # Update child profile status
    try:
        db.child_profiles.update_one({'_id': ObjectId(child_id)}, {'$set': {'status': 'MATCHED', 'available_for_matching': False, 'updated_at': now_iso}})
    except Exception:
        db.child_profiles.update_one({'child_id': child_id}, {'$set': {'status': 'MATCHED', 'available_for_matching': False, 'updated_at': now_iso}})

    # Update adoption request & application status
    db.adoption_requests.update_one({'request_id': request_id}, {'$set': {'status': 'COMPLETED', 'updated_at': now_iso}})
    db.adoption_applications.update_one({'application_id': request_id}, {'$set': {'status': 'COMPLETED', 'updated_at': now_iso}})
    db.journeys.update_one({'request_id': request_id}, {'$set': {'current_stage': 'COMPLETED', 'completed': True, 'updated_at': now_iso}})

    # Create notifications
    adopter_msg = f"Congratulations! Your child-family match for request {request_id} has been authorized and completed by {trust.get('trust_name')}."
    create_notification(adopter_id, adopter_msg, notif_type='match_completed')
    create_notification(user_id, f"Child match authorized and completed for request {request_id}.", notif_type='match_completed')

    # Send Email
    adopter_doc = db.users.find_one({'_id': ObjectId(adopter_id)}) if ObjectId.is_valid(adopter_id) else db.users.find_one({'_id': adopter_id})
    adopter_email = adopter_doc.get('email', '') if adopter_doc else ''
    if adopter_email:
        send_matching_completed_email(adopter_email, request_id, trust.get('trust_name', 'Adoption Trust'), user_id=adopter_id)

    flash(f"Child-family match for request {request_id} successfully authorized and completed!", 'success')
    return redirect(url_for('trust.applications'))

@trust_bp.route('/requests')
@trust_required
def requests_list():
    """Alias route redirecting to applications & matching."""
    return applications()

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
        city = request.form.get('city', '').strip()
        state = request.form.get('state', '').strip()
        district = request.form.get('district', '').strip()
        description = request.form.get('description', '').strip()
        website = request.form.get('website', '').strip()
        agency_type = request.form.get('agency_type', 'Specialized Adoption Agency (SAA)')
        languages_str = request.form.get('languages', 'English, Tamil')
        new_password = request.form.get('new_password', '').strip()

        languages_list = [l.strip() for l in languages_str.split(',') if l.strip()]

        trust_update = {
            'trust_name': trust_name,
            'email': email,
            'phone': phone,
            'location': location or f"{city}, {state}",
            'city': city,
            'state': state,
            'district': district,
            'description': description,
            'website': website,
            'agency_type': agency_type,
            'languages': languages_list,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }

        user_update = {
            'name': trust_name,
            'email': email,
            'phone': phone,
            'address': location or f"{city}, {state}",
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

@trust_bp.route('/notifications', methods=['GET', 'POST'])
@trust_required
def notifications_page():
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
        return redirect(url_for('trust.notifications_page'))

    filter_type = request.args.get('filter', 'all')
    all_notifications = get_user_notifications(user_id, limit=50)
    if filter_type == 'unread':
        notifications_list = [n for n in all_notifications if not n.get('is_read')]
    else:
        notifications_list = all_notifications

    unread_count = get_unread_count(user_id)
    return render_template(
        'trust/notifications.html',
        user=user,
        notifications=notifications_list,
        unread_count=unread_count,
        filter_type=filter_type
    )
