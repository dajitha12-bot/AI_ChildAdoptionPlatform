"""
Admin Routes (System Administrator Portal - 4 Main Pages)
Handles admin dashboard, trust management, platform health monitoring, and system notifications.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, Response
from datetime import datetime, timezone
from bson.objectid import ObjectId
from database.mongodb import db
from utils.auth import get_current_user, hash_password
from utils.decorators import admin_required
from services.notification_service import get_user_notifications, create_notification, get_unread_count
from services.agency_service import get_freshness_status, import_agencies_from_csv, export_agencies_to_csv, validate_url, validate_email

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ----------------------------------------------------
# ADMIN PAGE 1: Dashboard
# ----------------------------------------------------
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """Admin Dashboard showing high-level platform stats."""
    user = get_current_user()
    user_id = str(user['_id'])

    # Count platform metrics
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
            try:
                adopter = db.users.find_one({'_id': ObjectId(adopter_id)})
            except Exception:
                adopter = db.users.find_one({'_id': adopter_id})
        r['adopter'] = adopter

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'admin/dashboard.html',
        user=user,
        total_adopters=total_adopters,
        total_trusts=total_trusts,
        verified_trusts_count=verified_trusts_count,
        pending_trusts_count=pending_trusts_count,
        active_requests=active_requests,
        approved_requests=approved_requests,
        completed_cases=completed_cases,
        recent_trusts=recent_trusts,
        recent_requests=recent_requests,
        notifications=notifications,
        unread_count=unread_count
    )


# ----------------------------------------------------
# ADMIN PAGE 2: Trust Directory Management
# ----------------------------------------------------
@admin_bp.route('/trust-data-management')
@admin_required
def trust_data_management():
    """Admin Page 2: Manage adoption agency dataset."""
    user = get_current_user()
    user_id = str(user['_id'])

    all_agencies = list(db.trusts.find().sort('trust_name', 1))

    total_agencies = len(all_agencies)
    verified_agencies = 0
    pending_verification = 0
    review_due_count = 0
    inactive_agencies = 0

    for a in all_agencies:
        a['_id'] = str(a['_id'])
        freshness = get_freshness_status(a.get('last_verified'))
        a['freshness'] = freshness

        if a.get('verified') and a.get('status') in ['ACTIVE', 'Verified']:
            verified_agencies += 1
        else:
            pending_verification += 1

        if freshness['status'] == 'Review Due':
            review_due_count += 1

        if a.get('status') in ['INACTIVE', 'DEACTIVATED', 'Suspended', 'Rejected']:
            inactive_agencies += 1

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'admin/trust_data_management.html',
        user=user,
        agencies=all_agencies,
        total_agencies=total_agencies,
        verified_agencies=verified_agencies,
        pending_verification=pending_verification,
        review_due_count=review_due_count,
        inactive_agencies=inactive_agencies,
        notifications=notifications,
        unread_count=unread_count
    )


@admin_bp.route('/trusts')
@admin_required
def trusts_alias():
    return trust_data_management()


@admin_bp.route('/trust/add', methods=['POST'])
@admin_required
def add_trust():
    """Adds a new adoption agency to dataset."""
    trust_name = request.form.get('trust_name', '').strip()
    email = request.form.get('email', '').strip().lower()
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

    if not trust_name or not email:
        flash('Trust Name and Email are required.', 'danger')
        return redirect(url_for('admin.trust_data_management'))

    now_iso = datetime.now(timezone.utc).isoformat()
    languages_list = [l.strip() for l in languages_str.split(',') if l.strip()]

    trust_doc = {
        'trust_name': trust_name,
        'email': email,
        'phone': phone,
        'state': state,
        'district': district,
        'city': city,
        'public_address': address,
        'address': address,
        'location': f"{city}, {state}",
        'website': website,
        'agency_type': agency_type,
        'languages': languages_list,
        'verification_source': verification_source,
        'source_url': source_url,
        'verified': True,
        'status': 'ACTIVE',
        'last_verified': now_iso,
        'created_at': now_iso,
        'updated_at': now_iso
    }

    # Create associated user account for trust login
    user_doc = {
        'name': trust_name,
        'email': email,
        'password_hash': hash_password('Trust@123'),
        'role': 'trust',
        'phone': phone,
        'address': f"{city}, {state}",
        'language': 'English',
        'created_at': now_iso,
        'updated_at': now_iso
    }
    user_id = db.users.insert_one(user_doc).inserted_id
    trust_doc['user_id'] = str(user_id)

    db.trusts.insert_one(trust_doc)
    flash(f'Trust "{trust_name}" added successfully with password Trust@123!', 'success')
    return redirect(url_for('admin.trust_data_management'))


@admin_bp.route('/trust/verify/<trust_id>', methods=['POST'])
@admin_required
def verify_trust(trust_id):
    """Verifies or activates a trust agency."""
    action = request.form.get('action', 'verify')
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        t_obj_id = ObjectId(trust_id)
        query = {'_id': t_obj_id}
    except Exception:
        query = {'_id': trust_id}

    if action == 'deactivate':
        db.trusts.update_one(query, {'$set': {'status': 'INACTIVE', 'verified': False, 'updated_at': now_iso}})
        flash('Agency deactivated.', 'warning')
    else:
        db.trusts.update_one(query, {'$set': {'status': 'ACTIVE', 'verified': True, 'last_verified': now_iso, 'updated_at': now_iso}})
        flash('Agency verified and activated successfully!', 'success')

    return redirect(url_for('admin.trust_data_management'))


# ----------------------------------------------------
# ADMIN PAGE 3: Platform Monitoring & Health
# ----------------------------------------------------
@admin_bp.route('/monitoring')
@admin_required
def monitoring():
    """Admin Page 3: Live platform monitoring & email logs."""
    user = get_current_user()
    user_id = str(user['_id'])

    email_logs = list(db.email_logs.find().sort('sent_at', -1).limit(20))
    for log in email_logs:
        log['_id'] = str(log['_id'])

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'admin/monitoring.html',
        user=user,
        email_logs=email_logs,
        notifications=notifications,
        unread_count=unread_count
    )


# ----------------------------------------------------
# ADMIN PAGE 4: Admin Notifications
# ----------------------------------------------------
@admin_bp.route('/notifications', methods=['GET', 'POST'])
@admin_required
def notifications_page():
    """Admin Notifications Management."""
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
        return redirect(url_for('admin.notifications_page'))

    filter_type = request.args.get('filter', 'all')
    all_notifications = get_user_notifications(user_id, limit=50)
    notifications_list = [n for n in all_notifications if not n.get('is_read')] if filter_type == 'unread' else all_notifications

    unread_count = get_unread_count(user_id)
    return render_template(
        'admin/notifications.html',
        user=user,
        notifications=notifications_list,
        unread_count=unread_count,
        filter_type=filter_type
    )


@admin_bp.route('/profile', methods=['GET', 'POST'])
@admin_required
def profile():
    user = get_current_user()
    user_id = str(user['_id'])

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()

        update_data = {
            'name': name,
            'email': email,
            'phone': phone,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        try:
            db.users.update_one({'_id': ObjectId(user_id)}, {'$set': update_data})
        except Exception:
            db.users.update_one({'_id': user_id}, {'$set': update_data})

        flash('Admin profile updated.', 'success')
        return redirect(url_for('admin.profile'))

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)
    return render_template('admin/profile.html', user=user, notifications=notifications, unread_count=unread_count)
