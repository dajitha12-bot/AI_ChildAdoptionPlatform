import os
from flask import Flask, render_template, session
from config import Config
from database.mongodb import init_db
from utils.auth import get_current_user
from services.notification_service import get_unread_count

from routes.auth import auth_bp
from routes.adopter import adopter_bp
from routes.trust import trust_bp
from routes.admin import admin_bp
from routes.ai import ai_bp
from routes.notifications import notif_bp
from routes.api_agencies import api_agencies_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize Database
    init_db(app)

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(adopter_bp)
    app.register_blueprint(trust_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(notif_bp)
    app.register_blueprint(api_agencies_bp)

    @app.context_processor
    def inject_global_vars():
        user = get_current_user()
        unread_count = 0
        if user:
            unread_count = get_unread_count(str(user['_id']))
        return dict(current_user=user, unread_count=unread_count)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('index.html', error_msg="Page Not Found"), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('index.html', error_msg="Internal Server Error"), 500

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
