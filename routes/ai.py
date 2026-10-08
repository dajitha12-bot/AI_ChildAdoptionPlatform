from flask import Blueprint, request, jsonify, session
from datetime import datetime
from services.ai_agent import process_ai_query
from utils.auth import get_current_user
from utils.decorators import login_required

ai_bp = Blueprint('ai', __name__, url_prefix='/api/ai')

@ai_bp.route('/ask', methods=['POST'])
@login_required
def ask_ai():
    user = get_current_user()
    user_id = str(user['_id']) if user else None

    data = request.get_json() or {}
    question = data.get('question', '').strip()
    language = data.get('language', user.get('language', 'English') if user else 'English')

    if not question:
        return jsonify({'error': 'Question cannot be empty.'}), 400

    result = process_ai_query(user_id, question, target_lang=language)

    return jsonify({
        'question': question,
        'response': result.get('response', ''),
        'agencies': result.get('agencies', []),
        'language': language,
        'timestamp': datetime.now().strftime("%I:%M %p")
    })

@ai_bp.route('/agency-search', methods=['POST'])
@login_required
def agency_search():
    """
    POST /api/ai/agency-search
    Performs intent extraction, executes safe MongoDB query, returns grounded agency list + AI explanation.
    """
    user = get_current_user()
    user_id = str(user['_id']) if user else None

    data = request.get_json() or {}
    question = data.get('question', '').strip()
    language = data.get('language', user.get('language', 'English') if user else 'English')

    if not question:
        return jsonify({'error': 'Question cannot be empty.'}), 400

    result = process_ai_query(user_id, question, target_lang=language)

    return jsonify({
        'question': question,
        'response': result.get('response', ''),
        'agencies': result.get('agencies', []),
        'language': language,
        'timestamp': datetime.now().strftime("%I:%M %p")
    })
