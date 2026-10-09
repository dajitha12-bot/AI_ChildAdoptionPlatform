"""
Authentication Routes (Login and Register)
Provides role-based login and registration for Adopter, Trust, and Admin roles.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timezone
from database.mongodb import db
from utils.auth import hash_password, verify_password, login_user_session, logout_user_session
from services.email_service import send_registration_email
from services.notification_service import create_notification

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handles User & Trust Login with 1-Click Trust Chooser."""
    # Step 1: Fetch verified trust accounts for the Trust quick login dropdown
    verified_trust_accounts = list(db.trusts.find({'verified': True}))
    for trust_item in verified_trust_accounts:
        trust_item['_id'] = str(trust_item['_id'])
    verified_trust_accounts.sort(key=lambda x: x.get('trust_name', ''))

    # Step 2: Process Login Form Submission
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        selected_role = request.form.get('role', 'adopter')

        # Check required fields
        if not email or not password:
            flash('Please enter both email and password.', 'danger')
            return render_template('auth/login.html', selected_role=selected_role, email=email, verified_trust_accounts=verified_trust_accounts)

        # Check user in MongoDB database
        user = db.users.find_one({'email': email})
        if not user or not verify_password(user.get('password_hash', ''), password):
            flash('Invalid email or password.', 'danger')
            return render_template('auth/login.html', selected_role=selected_role, email=email, verified_trust_accounts=verified_trust_accounts)

        # Check role match
        if selected_role and user.get('role') != selected_role:
            flash(f'Role mismatch. This account is registered as "{user.get("role")}".', 'warning')
            return render_template('auth/login.html', selected_role=selected_role, email=email, verified_trust_accounts=verified_trust_accounts)

        # Save session & redirect to dashboard based on role
        login_user_session(user)
        flash(f'Welcome back, {user.get("name")}!', 'success')

        role = user.get('role')
        if role == 'adopter':
            return redirect(url_for('adopter.dashboard'))
        elif role == 'trust':
            return redirect(url_for('trust.dashboard'))
        elif role == 'admin':
            return redirect(url_for('admin.dashboard'))

    # GET Request: Render login page
    selected_role = request.args.get('role', 'adopter')
    return render_template('auth/login.html', selected_role=selected_role, verified_trust_accounts=verified_trust_accounts)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handles User & Trust Registration."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', 'adopter')
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        language = request.form.get('language', 'English')

        # Additional fields if registering a Trust account
        trust_name = request.form.get('trust_name', '').strip()
        location = request.form.get('location', '').strip()

        # Validation checks
        if not name or not email or not password:
            flash('Please fill in all required fields.', 'danger')
            return render_template('auth/register.html', role=role)

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html', role=role)

        # Check if email is already registered
        existing_user = db.users.find_one({'email': email})
        if existing_user:
            flash('An account with this email address already exists.', 'danger')
            return render_template('auth/register.html', role=role)

        # Create user document
        now_iso = datetime.now(timezone.utc).isoformat()
        user_doc = {
            'name': name,
            'email': email,
            'password_hash': hash_password(password),
            'role': role,
            'phone': phone,
            'address': address,
            'language': language,
            'preferences': {
                'location': location if role == 'trust' else '',
                'languages': [language]
            },
            'created_at': now_iso,
            'updated_at': now_iso
        }

        user_result = db.users.insert_one(user_doc)
        user_id = user_result.inserted_id

        # If Trust registration, insert into trusts collection
        if role == 'trust':
            trust_doc = {
                'user_id': str(user_id),
                'trust_name': trust_name or name,
                'email': email,
                'phone': phone,
                'location': location or address,
                'city': location or address,
                'state': 'Tamil Nadu',
                'verified': False,
                'status': 'PENDING_REVIEW',
                'created_at': now_iso,
                'updated_at': now_iso
            }
            db.trusts.insert_one(trust_doc)

        # Send welcome email and in-app notification
        send_registration_email(name, email, user_id=user_id)
        create_notification(str(user_id), 'Welcome to Smart Child Adoption Platform!', notif_type='registration')

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login', role=role))

    role = request.args.get('role', 'adopter')
    return render_template('auth/register.html', role=role)


@auth_bp.route('/logout')
def logout():
    """Logs out user and clears session."""
    logout_user_session()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))
