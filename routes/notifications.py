from flask import Blueprint, jsonify, session, request
from utils.auth import get_current_user
from utils.decorators import login_required
from services.notification_service import get_user_notifications, get_unread_count, mark_notification_read, mark_all_read

notif_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')

@notif_bp.route('/', methods=['GET'])
@login_required
def list_notifications():
    user = get_current_user()
    if not user:
        return jsonify({'notifications': [], 'unread_count': 0})
    user_id = str(user['_id'])
    notifs = get_user_notifications(user_id, limit=20)
    count = get_unread_count(user_id)
    return jsonify({'notifications': notifs, 'unread_count': count})

@notif_bp.route('/mark-read/<notif_id>', methods=['POST'])
@login_required
def mark_read(notif_id):
    mark_notification_read(notif_id)
    return jsonify({'success': True})

@notif_bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all():
    user = get_current_user()
    if user:
        mark_all_read(str(user['_id']))
    return jsonify({'success': True})
