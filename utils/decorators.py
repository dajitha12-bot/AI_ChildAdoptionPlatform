from functools import wraps
from flask import session, redirect, url_for, flash, request

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))
            user_role = session.get('role')
            if user_role not in roles:
                flash('Unauthorized access: You do not have permission to view this page.', 'danger')
                # Redirect to appropriate dashboard based on user's actual role
                if user_role == 'adopter':
                    return redirect(url_for('adopter.dashboard'))
                elif user_role == 'trust':
                    return redirect(url_for('trust.dashboard'))
                elif user_role == 'admin':
                    return redirect(url_for('admin.dashboard'))
                else:
                    return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def adopter_required(f):
    return role_required('adopter')(f)

def trust_required(f):
    return role_required('trust')(f)

def admin_required(f):
    return role_required('admin')(f)
