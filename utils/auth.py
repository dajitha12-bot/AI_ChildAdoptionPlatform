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

    if user.get('role') == 'trust':
        user_id_str = str(user['_id'])
        trust_doc = db.trusts.find_one({'user_id': user_id_str})
        if not trust_doc:
            trust_doc = db.trusts.find_one({'email': user.get('email')})
        if not trust_doc and user.get('trust_id'):
            try:
                trust_doc = db.trusts.find_one({'_id': ObjectId(user.get('trust_id'))})
            except Exception:
                trust_doc = db.trusts.find_one({'_id': user.get('trust_id')})

        if trust_doc:
            session['trust_id'] = str(trust_doc['_id'])
        elif user.get('trust_id'):
            session['trust_id'] = str(user.get('trust_id'))

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
