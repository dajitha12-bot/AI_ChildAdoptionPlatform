from flask import Blueprint, render_template, request, redirect, url_for, flash, session, Response, jsonify
from datetime import datetime, timezone
from bson.objectid import ObjectId
from database.mongodb import db
from utils.auth import get_current_user, hash_password
from utils.decorators import admin_required
from services.notification_service import get_user_notifications, create_notification, get_unread_count
from services.agency_service import get_freshness_status, import_agencies_from_csv, export_agencies_to_csv, validate_url, validate_email

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
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
        adopter = None
        try:
            adopter = db.users.find_one({'_id': ObjectId(r['adopter_id'])})
        except Exception:
            adopter = db.users.find_one({'_id': r['adopter_id']})
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

@admin_bp.route('/trust-data-management')
@admin_required
def trust_data_management():
    """Main India-Wide Trust Data Management page for Admin."""
    user = get_current_user()
    user_id = str(user['_id'])

    all_agencies = list(db.trusts.find().sort('trust_name', 1))

    # Metric counts & freshness calculations
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

@admin_bp.route('/trust/add', methods=['POST'])
@admin_required
def add_agency():
    """Add a new adoption agency (Admin action)."""
    trust_name = request.form.get('trust_name', '').strip()
    state = request.form.get('state', '').strip()
    district = request.form.get('district', '').strip()
    city = request.form.get('city', '').strip()
    address = request.form.get('address', '').strip()
    phone = request.form.get('phone', '').strip()
    email = validate_email(request.form.get('email', ''))
    website = validate_url(request.form.get('website', ''))
    agency_type = request.form.get('agency_type', 'Specialized Adoption Agency (SAA)').strip()
    verification_source = request.form.get('verification_source', 'Official CARA / Government Registry').strip()
    source_url = validate_url(request.form.get('source_url', ''))

    languages_str = request.form.get('languages', 'English, Tamil')
    languages = [l.strip() for l in languages_str.split(',') if l.strip()]

    mark_verified = request.form.get('mark_verified') == 'on'
    now_iso = datetime.now(timezone.utc).isoformat()

    agency_doc = {
        'trust_name': trust_name,
        'state': state,
        'district': district,
        'city': city,
        'address': address,
        'location': f"{city}, {state}" if city else state,
        'phone': phone,
        'email': email,
        'website': website,
        'languages': languages,
        'agency_type': agency_type,
        'verified': mark_verified,
        'verification_source': verification_source,
        'source_url': source_url,
        'last_verified': now_iso if mark_verified else None,
        'status': 'ACTIVE' if mark_verified else 'PENDING_REVIEW',
        'description': f"Official {agency_type} operating in {city}, {state}.",
        'created_at': now_iso,
        'updated_at': now_iso
    }

    db.trusts.insert_one(agency_doc)
    flash(f"✓ Agency '{trust_name}' added successfully. Status: {'ACTIVE (Verified)' if mark_verified else 'PENDING_REVIEW'}.", 'success')
    return redirect(url_for('admin.trust_data_management'))

@admin_bp.route('/trust/update/<agency_id>', methods=['POST'])
@admin_required
def update_agency(agency_id):
    """Update existing agency details."""
    try:
        agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception:
        agency = db.trusts.find_one({'_id': agency_id})

    if not agency:
        flash('Agency record not found.', 'danger')
        return redirect(url_for('admin.trust_data_management'))

    trust_name = request.form.get('trust_name', '').strip()
    state = request.form.get('state', '').strip()
    district = request.form.get('district', '').strip()
    city = request.form.get('city', '').strip()
    address = request.form.get('address', '').strip()
    phone = request.form.get('phone', '').strip()
    email = validate_email(request.form.get('email', ''))
    website = validate_url(request.form.get('website', ''))
    agency_type = request.form.get('agency_type', 'Specialized Adoption Agency (SAA)').strip()
    verification_source = request.form.get('verification_source', '').strip()
    source_url = validate_url(request.form.get('source_url', ''))

    languages_str = request.form.get('languages', 'English, Tamil')
    languages = [l.strip() for l in languages_str.split(',') if l.strip()]

    update_dict = {
        'trust_name': trust_name,
        'state': state,
        'district': district,
        'city': city,
        'address': address,
        'location': f"{city}, {state}" if city else state,
        'phone': phone,
        'email': email,
        'website': website,
        'languages': languages,
        'agency_type': agency_type,
        'verification_source': verification_source,
        'source_url': source_url,
        'updated_at': datetime.now(timezone.utc).isoformat()
    }

    db.trusts.update_one({'_id': agency['_id']}, {'$set': update_dict})
    flash(f"Agency '{trust_name}' updated successfully.", 'success')
    return redirect(url_for('admin.trust_data_management'))

@admin_bp.route('/trust/verify/<agency_id>', methods=['POST'])
@admin_required
def verify_agency(agency_id):
    """Marks an agency record as verified after admin inspection of official source."""
    try:
        agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception:
        agency = db.trusts.find_one({'_id': agency_id})

    if not agency:
        flash('Agency not found.', 'danger')
        return redirect(url_for('admin.trust_data_management'))

    verification_source = request.form.get('verification_source') or agency.get('verification_source') or 'Official CARA Registry'
    source_url = request.form.get('source_url') or agency.get('source_url') or ''
    now_iso = datetime.now(timezone.utc).isoformat()

    db.trusts.update_one({'_id': agency['_id']}, {'$set': {
        'verified': True,
        'status': 'ACTIVE',
        'verification_source': verification_source,
        'source_url': source_url,
        'last_verified': now_iso,
        'updated_at': now_iso
    }})

    # If linked to a user account, notify trust user
    if agency.get('user_id'):
        create_notification(agency['user_id'], "Your trust agency has been verified and activated by Admin.", notif_type='trust_verified')

    flash(f"✓ Agency '{agency.get('trust_name')}' marked as VERIFIED and ACTIVE.", 'success')
    return redirect(url_for('admin.trust_data_management'))

@admin_bp.route('/trust/deactivate/<agency_id>', methods=['POST'])
@admin_required
def deactivate_agency(agency_id):
    """Deactivates an agency, immediately excluding it from adopter search results."""
    try:
        agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception:
        agency = db.trusts.find_one({'_id': agency_id})

    if not agency:
        flash('Agency not found.', 'danger')
        return redirect(url_for('admin.trust_data_management'))

    now_iso = datetime.now(timezone.utc).isoformat()
    db.trusts.update_one({'_id': agency['_id']}, {'$set': {
        'status': 'INACTIVE',
        'verified': False,
        'updated_at': now_iso
    }})

    flash(f"Agency '{agency.get('trust_name')}' DEACTIVATED and removed from adopter search directory.", 'warning')
    return redirect(url_for('admin.trust_data_management'))

@admin_bp.route('/trust/reactivate/<agency_id>', methods=['POST'])
@admin_required
def reactivate_agency(agency_id):
    """Reactivates an inactive agency."""
    try:
        agency = db.trusts.find_one({'_id': ObjectId(agency_id)})
    except Exception:
        agency = db.trusts.find_one({'_id': agency_id})

    if not agency:
        flash('Agency not found.', 'danger')
        return redirect(url_for('admin.trust_data_management'))

    now_iso = datetime.now(timezone.utc).isoformat()
    db.trusts.update_one({'_id': agency['_id']}, {'$set': {
        'status': 'ACTIVE',
        'verified': True,
        'last_verified': now_iso,
        'updated_at': now_iso
    }})

    flash(f"✓ Agency '{agency.get('trust_name')}' REACTIVATED.", 'success')
    return redirect(url_for('admin.trust_data_management'))

@admin_bp.route('/trust/import-csv', methods=['POST'])
@admin_required
def import_csv():
    """Import agency records from CSV file."""
    if 'csv_file' not in request.files:
        flash('No CSV file attached.', 'danger')
        return redirect(url_for('admin.trust_data_management'))

    file = request.files['csv_file']
    if file.filename == '':
        flash('Please select a valid CSV file.', 'danger')
        return redirect(url_for('admin.trust_data_management'))

    res = import_agencies_from_csv(file.stream)
    if res.get('success'):
        flash(f"✓ CSV Import Completed: {res.get('successful_count')} inserted, {res.get('skipped_count')} updated, {res.get('failed_count')} failed.", 'success')
    else:
        flash(f"CSV Import Error: {res.get('error')}", 'danger')

    return redirect(url_for('admin.trust_data_management'))

@admin_bp.route('/trust/export-csv')
@admin_required
def export_csv():
    """Export agency records to CSV download."""
    csv_data = export_agencies_to_csv()
    filename = f"verified_adoption_agencies_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

@admin_bp.route('/trust/download-template')
def download_template():
    """Download sample CSV template."""
    template_path = os.path.join(os.path.dirname(__file__), '..', 'seed', 'agencies_template.csv')
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return Response(content, mimetype="text/csv", headers={"Content-disposition": "attachment; filename=adoption_agencies_template.csv"})
    else:
        sample_csv = 'agency_name,state,district,city,public_address,phone,email,website,languages,agency_type,verified,verification_source,source_url,last_verified,status\n"Example Agency","Tamil Nadu","Madurai","Madurai","Address","+91 9876543210","contact@example.org","https://example.org","Tamil, English","Specialized Adoption Agency (SAA)",true,"CARA","https://cara.wcd.gov.in","2026-09-01T00:00:00Z","ACTIVE"\n'
        return Response(sample_csv, mimetype="text/csv", headers={"Content-disposition": "attachment; filename=adoption_agencies_template.csv"})

@admin_bp.route('/profile', methods=['GET', 'POST'])
@admin_required
def profile():
    user = get_current_user()
    user_id = str(user['_id'])

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        new_password = request.form.get('new_password', '').strip()

        update_data = {
            'name': name,
            'email': email,
            'phone': phone,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }

        if new_password:
            update_data['password_hash'] = hash_password(new_password)

        try:
            db.users.update_one({'_id': ObjectId(user_id)}, {'$set': update_data})
        except Exception:
            db.users.update_one({'_id': user_id}, {'$set': update_data})

        flash('Admin profile updated successfully!', 'success')
        return redirect(url_for('admin.profile'))

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)
    return render_template('admin/profile.html', user=user, notifications=notifications, unread_count=unread_count)

@admin_bp.route('/trust-verification')
@admin_required
def trust_verification():
    """Alias pointing to trust data management for compatibility."""
    return redirect(url_for('admin.trust_data_management'))

@admin_bp.route('/trust-action/<trust_id>', methods=['POST'])
@admin_required
def trust_action(trust_id):
    action = request.form.get('action', '').lower()
    if action == 'verify':
        return verify_agency(trust_id)
    elif action == 'suspend' or action == 'deactivate':
        return deactivate_agency(trust_id)
    else:
        return deactivate_agency(trust_id)

@admin_bp.route('/monitoring')
@admin_required
def monitoring():
    user = get_current_user()
    user_id = str(user['_id'])

    total_users = db.users.count_documents({})
    adopter_count = db.users.count_documents({'role': 'adopter'})
    trust_user_count = db.users.count_documents({'role': 'trust'})

    req_pending = db.adoption_requests.count_documents({'status': 'TRUST_REVIEW'})
    req_approved = db.adoption_requests.count_documents({'status': 'APPROVED'})
    req_completed = db.adoption_requests.count_documents({'status': 'COMPLETED'})
    req_rejected = db.adoption_requests.count_documents({'status': 'REJECTED'})

    ai_usage_count = db.ai_conversations.count_documents({})
    email_logs_count = db.email_logs.count_documents({})
    email_success_count = db.email_logs.count_documents({'status': {'$in': ['SENT', 'SENT_SIMULATED']}})

    recent_email_logs = list(db.email_logs.find().sort('sent_at', -1).limit(10))
    recent_ai_queries = list(db.ai_conversations.find().sort('created_at', -1).limit(10))

    notifications = get_user_notifications(user_id, limit=5)
    unread_count = get_unread_count(user_id)

    return render_template(
        'admin/monitoring.html',
        user=user,
        total_users=total_users,
        adopter_count=adopter_count,
        trust_user_count=trust_user_count,
        req_pending=req_pending,
        req_approved=req_approved,
        req_completed=req_completed,
        req_rejected=req_rejected,
        ai_usage_count=ai_usage_count,
        email_logs_count=email_logs_count,
        email_success_count=email_success_count,
        recent_email_logs=recent_email_logs,
        recent_ai_queries=recent_ai_queries,
        notifications=notifications,
        unread_count=unread_count
    )


@admin_bp.route('/notifications', methods=['GET', 'POST'])
@admin_required
def notifications_page():
    """Admin Notifications Page (4th Admin Main Page)."""
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
    if filter_type == 'unread':
        notifications_list = [n for n in all_notifications if not n.get('is_read')]
    else:
        notifications_list = all_notifications

    unread_count = get_unread_count(user_id)
    return render_template(
        'admin/notifications.html',
        user=user,
        notifications=notifications_list,
        unread_count=unread_count,
        filter_type=filter_type
    )
