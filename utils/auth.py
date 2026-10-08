from werkzeug.security import generate_password_hash, check_password_hash
from flask import session
from bson.objectid import ObjectId
from database.mongodb import db

def hash_password(password: str) -> str:
    return generate_password_hash(password)

def verify_password(password_hash: str, password: str) -> bool:
    if not password_hash or not password:
        return False
    return check_password_hash(password_hash, password)

def login_user_session(user: dict):
    session.clear()
    session['user_id'] = str(user['_id'])
    session['user_name'] = user.get('name', '')
    session['user_email'] = user.get('email', '')
    session['role'] = user.get('role', '')

def logout_user_session():
    session.clear()

def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    try:
        user = db.users.find_one({'_id': ObjectId(user_id)})
        if not user:
            user = db.users.find_one({'_id': user_id})
        return user
    except Exception:
        return db.users.find_one({'_id': user_id})
