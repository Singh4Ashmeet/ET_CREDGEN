import os
import logging
from pathlib import Path
from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from utils.database import db, init_db
from models.db_models import AdminUser, RevokedToken
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── APP FACTORY ──────────────────────────────────────────────────────

def create_app():
    app = Flask(__name__, static_folder=None)

    # --- Configuration ---
    app.config['SECRET_KEY'] = os.getenv('APP_SECRET_KEY', 'dev-secret-key-change-me')
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'jwt-secret-change-me')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(
        minutes=int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 30))
    )
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(
        days=int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 7))
    )
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB upload limit

    # Upload folder
    upload_folder = os.path.join(os.path.dirname(__file__), 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = upload_folder

    # --- Database ---
    init_db(app)

    # --- Extensions ---
    CORS(app, resources={r"/*": {
        "origins": os.getenv('ALLOWED_ORIGINS', '*').split(','),
        "expose_headers": ["X-Session-ID"]
    }})

    jwt = JWTManager(app)

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        jti = jwt_payload["jti"]
        return RevokedToken.is_revoked(jti)

    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        storage_uri="memory://",
        default_limits=["500 per hour"]
    )

    # --- Register Blueprints ---
    from routes.auth_routes import auth_bp
    from routes.chat_routes import chat_bp
    from routes.admin_routes import admin_bp
    from routes.workflow_routes import workflow_bp
    from routes.tools_routes import tools_bp
    from routes.status_routes import status_bp
    from routes.document_routes import document_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(workflow_bp)
    app.register_blueprint(tools_bp)
    app.register_blueprint(status_bp)
    app.register_blueprint(document_bp)

    # --- CSV Helper ---
    APPLICATIONS_CSV = os.path.join(os.path.dirname(__file__), 'csv', 'applications.csv')

    def read_csv(file_path):
        import csv
        if not os.path.exists(file_path):
            return []
        with open(file_path, mode='r', encoding='utf-8') as f:
            return list(csv.DictReader(f))

    @app.route('/admin/debug/applications')
    def debug_applications():
        rows = read_csv(APPLICATIONS_CSV)
        return jsonify({
            'count': len(rows),
            'first_row': rows[0] if rows else None,
            'csv_path': APPLICATIONS_CSV,
            'file_exists': os.path.exists(APPLICATIONS_CSV)
        })

    # --- Static File Serving ---
    frontend_dir = os.path.join(os.path.dirname(__file__), 'frontend')

    @app.route('/')
    def serve_landing():
        return send_from_directory(frontend_dir, 'index.html')

    @app.route('/status')
    @app.route('/status.html')
    def serve_status():
        return send_from_directory(frontend_dir, 'status.html')

    @app.route('/admin/login')
    @app.route('/admin/login.html')
    def serve_admin_login():
        return send_from_directory(os.path.join(frontend_dir, 'admin'), 'login.html')

    @app.route('/admin/dashboard')
    @app.route('/admin/dashboard.html')
    def serve_admin_dashboard():
        return send_from_directory(os.path.join(frontend_dir, 'admin'), 'dashboard.html')

    # Serve any file from frontend/ and frontend/admin/
    @app.route('/admin/<path:filename>')
    def serve_admin_static(filename):
        admin_dir = os.path.join(frontend_dir, 'admin')
        if os.path.isfile(os.path.join(admin_dir, filename)):
            return send_from_directory(admin_dir, filename)
        return jsonify({"error": "Not found"}), 404

    @app.route('/fraud/test')
    def test_fraud():
        """Visit this URL to test fraud agent directly."""
        try:
            dummy = {
                'loan_amount': 700000, 'tenure': 24, 'age': 26,
                'income': 75000, 'credit_score': 700, 'num_active_loans': 0,
                'num_closed_loans': 2, 'employment_type': 'salaried',
                'pan': 'QWERT1234Y', 'aadhaar': '098765432112',
                'name': 'Ashmeet Singh', 'phone': '9876543210',
                'address': 'WZ-168 Old Sahib Pura New Delhi',
                'pincode': '110018',
            }
            from utils.agent_factory import get_fraud_agent
            fraud_agent_instance = get_fraud_agent()
            print("[TEST] Running fraud check with dummy data...")
            result = fraud_agent_instance.perform_fraud_check(dummy)
            print(f"[TEST] Result: {result}")
            return jsonify({'status': 'ok', 'result': result})
        except Exception as e:
            import traceback
            return jsonify({
                'status': 'error',
                'error': str(e),
                'traceback': traceback.format_exc()
            }), 500

    @app.route('/<path:filename>')
    def serve_static(filename):
        filepath = os.path.join(frontend_dir, filename)
        if os.path.isfile(filepath):
            return send_from_directory(frontend_dir, filename)
        return jsonify({"error": "Not found"}), 404

    # --- Global Error Handlers ---
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error"}), 500

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429

    # --- Create Tables & Seed Admin ---
    with app.app_context():
        db.create_all()
        _seed_admin_user()

    return app


def _seed_admin_user():
    """Create default admin user if none exists."""
    try:
        if AdminUser.query.count() == 0:
            username = os.getenv('SEED_ADMIN_USERNAME', 'admin')
            email = os.getenv('SEED_ADMIN_EMAIL', 'admin@credgen.in')
            password = os.getenv('SEED_ADMIN_PASSWORD', 'admin@123')

            admin = AdminUser(
                username=username,
                email=email,
                role='admin',
                is_active=True
            )
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()
            logger.info(f"Seeded admin user: {username}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Admin seeding error: {e}")

# ─── ENTRY POINT ──────────────────────────────────────────────────────

if __name__ == '__main__':
    app = create_app()

    print("[STARTUP] Pre-warming ML models...")
    try:
        from utils.agent_factory import get_fraud_agent, get_underwriting_agent
        fraud_agent = get_fraud_agent()
        underwriting_agent = get_underwriting_agent()
        _dummy = {'loan_amount': 100000, 'tenure': 24, 'age': 30, 'income': 50000,
                  'credit_score': 700, 'num_active_loans': 0, 'employment_type': 'salaried',
                  'pan': 'ABCDE1234F', 'aadhaar': '123456789012', 'name': 'Test User',
                  'address': 'Test Address', 'pincode': '400001', 'purpose': 'personal'}
        fraud_agent.perform_fraud_check(_dummy)
        underwriting_agent.perform_underwriting(_dummy)
        print("[STARTUP] Models pre-warmed successfully.")
    except Exception as e:
        print(f"[STARTUP] Pre-warm skipped (non-fatal): {e}")

    port = int(os.getenv('PORT', 5000))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True,
        use_reloader=False,    # prevents torchvision/ML reload crashes
        threaded=True
    )
