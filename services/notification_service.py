from datetime import datetime, timezone
from bson.objectid import ObjectId
from database.mongodb import db

def create_notification(user_id, message, notif_type='general'):
    """Creates an in-app notification in MongoDB."""
    notification = {
        'user_id': str(user_id),
        'message': message,
        'type': notif_type,
        'is_read': False,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    result = db.notifications.insert_one(notification)
    return str(result.inserted_id)

def get_user_notifications(user_id, limit=20):
    """Retrieves notifications for a specific user sorted by latest first."""
    notifications = list(db.notifications.find({'user_id': str(user_id)}).sort('created_at', -1).limit(limit))
    for n in notifications:
        n['_id'] = str(n['_id'])
    return notifications

def get_unread_count(user_id):
    """Gets total unread notifications count for badge."""
    return db.notifications.count_documents({'user_id': str(user_id), 'is_read': False})

def mark_notification_read(notification_id):
    """Marks a single notification as read."""
    try:
        db.notifications.update_one(
            {'_id': ObjectId(notification_id)},
            {'$set': {'is_read': True}}
        )
    except Exception:
        db.notifications.update_one(
            {'_id': notification_id},
            {'$set': {'is_read': True}}
        )

def mark_all_read(user_id):
    """Marks all notifications for a user as read."""
    db.notifications.update_many(
        {'user_id': str(user_id)},
        {'$set': {'is_read': True}}
    )
