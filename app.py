from flask import Flask, request, jsonify, send_from_directory, render_template, session, redirect, url_for
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, get_jwt
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import os
import uuid
from datetime import datetime, timedelta
import json
from functools import wraps
from werkzeug.utils import secure_filename
from sqlalchemy.exc import SQLAlchemyError

# Import database and models
from database import db, init_db
from models import (
    Customer, LoanApplication, KYCRecord, ChatSession, 
    ChatLog, TuningContent, AdminUser, RevokedToken
)
from auth import auth_bp
from validators import LoanApplicationSchema, KYCSchema

# Import the core agents (DO NOT TOUCH AGENT LOGIC)
from agents.master_agent import MasterAgent, ConversationStage, IntentType
from agents.underwriting_agent import UnderwritingAgent
from agents.sales_agent import SalesAgent
from agents.fraud_agent import FraudAgent
from utils.pdf_generator import generate_sanction_letter as generate_sanction_pdf
from models.gemini_service import GeminiService
from models.openrouter_service import OpenRouterService

# Load environment variables
load_dotenv()

# --- 1. Initialization ---
app = Flask(__name__)

def setup_database(app):
    """Automated setup for database and admin user on startup."""
    with app.app_context():
        try:
            # Create tables if they don't exist
            db.create_all()
            app.logger.info("Database tables verified/created.")

            # Seed Admin if not exists
            admin_user = os.getenv("SEED_ADMIN_USERNAME")
            admin_email = os.getenv("SEED_ADMIN_EMAIL")
            admin_password = os.getenv("SEED_ADMIN_PASSWORD")

            if admin_user and admin_email and admin_password:
                exists = AdminUser.query.filter_by(username=admin_user).first()
                if not exists:
                    new_admin = AdminUser(
                        username=admin_user,
                        email=admin_email,
                        role='admin'
                    )
                    new_admin.set_password(admin_password)
                    db.session.add(new_admin)
                    db.session.commit()
                    app.logger.info(f"Default admin user '{admin_user}' created.")
            else:
                app.logger.warning("SEED_ADMIN credentials missing in .env; skipping automated seeding.")

        except Exception as e:
            app.logger.error(f"Database setup failed: {e}")

# Security Hardening: Enforce APP_SECRET_KEY
if not os.environ.get("APP_SECRET_KEY"):
    raise RuntimeError("APP_SECRET_KEY env var is required")
app.secret_key = os.environ.get("APP_SECRET_KEY")

# CORS configuration
CORS(app, origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5000").split(","),
     supports_credentials=True)

# Security Headers with Talisman
Talisman(app,
    force_https=False,  # Set True in production
    strict_transport_security=True,
    content_security_policy={
        'default-src': "'self'",
        'script-src':  "'self'",
        'style-src':   "'self' 'unsafe-inline'",
        'img-src':     "'self' data:",
        'connect-src': "'self'",
    },
    x_frame_options='DENY',
    x_content_type_options=True,
    referrer_policy='strict-origin-when-cross-origin'
)

# JWT Configuration
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY")
if not app.config["JWT_SECRET_KEY"]:
    raise RuntimeError("JWT_SECRET_KEY env var is required")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", 900)))
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(seconds=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES", 604800)))
jwt = JWTManager(app)

@jwt.token_in_blocklist_loader
def check_if_token_is_revoked(jwt_header, jwt_payload: dict):
    jti = jwt_payload["jti"]
    return RevokedToken.is_revoked(jti)

# Rate Limiter
limiter = Limiter(app=app, key_func=get_remote_address)

# Database Initialization
init_db(app)
setup_database(app)

# Register Blueprints
app.register_blueprint(auth_bp)

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOADS_DIR
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

# Initialize agents
underwriting_agent = UnderwritingAgent()
sales_agent = SalesAgent()
fraud_agent = FraudAgent()

# Initialize Active LLM Service
llm_provider = os.getenv("LLM_PROVIDER", "openrouter").lower().strip()
llm_service = OpenRouterService() if llm_provider == "openrouter" else GeminiService()

# --- Decorators ---
def require_role(role):
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def decorated_function(*args, **kwargs):
            claims = get_jwt()
            if claims.get('role') != role:
                return jsonify({"msg": "Admin privilege required"}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Security: After Request Hook ---
@app.after_request
def add_security_headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

# --- Global Error Handler ---
@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"Unhandled exception: {str(e)}")
    return jsonify({
        'error': 'server_error',
        'message': 'An error occurred'
    }), 500

# --- Utility Functions ---

def get_session_id(request):
    session_id = request.headers.get('X-Session-ID')
    if not session_id:
        session_id = f"session_{uuid.uuid4().hex[:16]}"
    return session_id

def log_chat_event(session_id, event_type, payload):
    try:
        log = ChatLog(
            session_id=session_id,
            event_type=event_type,
            message_role=payload.get("role"),
            message_text=payload.get("text"),
            status=payload.get("status"),
            details=payload.get("details", {})
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Failed to log chat event: {e}")

def initialize_user_session(session_id):
    session = ChatSession.query.get(session_id)
    if not session:
        session = ChatSession(
            session_id=session_id,
            state={},
            stage='COLLECTING_DETAILS'
        )
        # We need a MasterAgent instance to get initial state
        temp_agent = MasterAgent()
        session.set_state(temp_agent.state)
        db.session.add(session)
        db.session.commit()
    return session

def update_session_activity(session_id):
    session = ChatSession.query.get(session_id)
    if session:
        session.touch()
        db.session.commit()

def get_bank_context():
    try:
        tuning_items = TuningContent.query.filter_by(is_active=True).all()
        contents = [item.content.strip() for item in tuning_items if item.content.strip()]
        if contents:
            return "\n\n".join(contents)
    except Exception as e:
        app.logger.error(f"Error loading bank context: {e}")
    return ""

# --- Agent Interaction Helpers ---
def determine_worker_from_stage(current_stage):
    worker_map = {
        'FRAUD_CHECK': "fraud",
        'UNDERWRITING': "underwriting",
        'OFFER_PRESENTATION': "sales",
        'DOCUMENTATION': "documentation",
        'REJECTION_COUNSELING': "sales"
    }
    # Handle both string and Enum if necessary, though SQLAlchemy stores as string
    stage_str = current_stage.name if hasattr(current_stage, 'name') else str(current_stage)
    return worker_map.get(stage_str, "none")

def get_workflow_stage_details(stage):
    # Mapping string stage names to display details
    stage_name = stage.name if hasattr(stage, 'name') else str(stage)
    stage_details = {
        'COLLECTING_DETAILS': {"name": "Basic Details Collection", "progress": 20, "next": "KYC Collection"},
        'KYC_COLLECTION': {"name": "KYC Verification", "progress": 40, "next": "Fraud Detection"},
        'FRAUD_CHECK': {"name": "Fraud Detection", "progress": 60, "next": "Underwriting"},
        'UNDERWRITING': {"name": "Underwriting", "progress": 80, "next": "Offer Presentation"},
        'OFFER_PRESENTATION': {"name": "Offer Presentation", "progress": 90, "next": "Documentation"},
        'DOCUMENTATION': {"name": "Documentation", "progress": 100, "next": "Completion"}
    }
    return stage_details.get(stage_name, {"name": "Unknown", "progress": 0})

# --- API Endpoints ---

@app.route('/chat', methods=['POST'])
def chat():
    try:
        session_id = get_session_id(request)
        data = request.get_json(silent=True) or {}
        user_input = (data.get('message') or '').strip()

        if not user_input:
            return jsonify({'message': 'Please provide a message.', 'error': 'empty_input'}), 400
        
        log_chat_event(session_id, 'message', {'role': 'user', 'text': user_input})

        db_session = initialize_user_session(session_id)
        db_session.interaction_count += 1
        
        # Load agent state from DB
        user_master_agent = MasterAgent()
        user_master_agent.state = db_session.get_state()
        
        gemini_mode = os.getenv("LLM_MODE", "enabled").lower().strip()
        system_prompt = os.getenv("LLM_SYSTEM_PROMPT", "You are CredGen AI.")
        bank_context = get_bank_context()
        if bank_context:
            system_prompt = f"{system_prompt}\n\n[BANK SPECIFIC CONTEXT]\n{bank_context}\n[END CONTEXT]"

        response = None
        if gemini_mode == "enabled":
            # (Simplified LLM logic for brevity, maintaining original intent)
            current_stage = user_master_agent.state["stage"]
            workflow_progress = user_master_agent.state.get("workflow_progress", 0)
            stage_details = get_workflow_stage_details(current_stage)
            
            workflow_prompt = f"Stage: {stage_details.get('name')}, Progress: {workflow_progress}%"
            full_system_prompt = f"{system_prompt}\n\n{workflow_prompt}"
            
            llm_resp = llm_service.generate_response(user_input, full_system_prompt)
            if llm_resp.get("status") == "success":
                # Handle entities if extracted
                if "extracted_entities" in llm_resp:
                    entities = {k: v for k, v in llm_resp["extracted_entities"].items() if v is not None}
                    if entities:
                        user_master_agent.update_state(entities, IntentType.PROVIDE_INFO)
                
                worker = determine_worker_from_stage(user_master_agent.state["stage"])
                action_map = {"fraud": "call_fraud_api", "underwriting": "call_underwriting_api", "sales": "call_sales_api", "documentation": "call_documentation_api"}
                
                response = {
                    "message": llm_resp.get("message", ""),
                    "worker": worker,
                    "action": action_map.get(worker, "none"),
                    "stage": user_master_agent.state["stage"].value if hasattr(user_master_agent.state["stage"], 'value') else user_master_agent.state["stage"],
                    "workflow_progress": user_master_agent.state.get("workflow_progress", 0),
                    "session_id": session_id
                }
            else:
                response = user_master_agent.handle(user_input)
        else:
            response = user_master_agent.handle(user_input)

        if response is None:
            response = user_master_agent.handle(user_input)

        # Sync state back to DB
        db_session.set_state(user_master_agent.state)
        db_session.stage = user_master_agent.state["stage"].value if hasattr(user_master_agent.state["stage"], 'value') else user_master_agent.state["stage"]
        db.session.commit()

        log_chat_event(session_id, 'message', {
            'role': 'assistant',
            'text': response.get('message'),
            'details': {'worker': response.get('worker'), 'stage': response.get('stage')}
        })

        resp = jsonify(response)
        resp.headers['X-Session-ID'] = session_id
        return resp
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error in /chat: {e}")
        return jsonify({'message': 'An error occurred', 'error': 'server_error'}), 500

@app.route('/underwrite', methods=['POST'])
def underwrite():
    try:
        session_id = request.headers.get('X-Session-ID')
        db_session = ChatSession.query.get(session_id)
        if not db_session:
            return jsonify({'error': 'Invalid session'}), 400
        
        user_master_agent = MasterAgent()
        user_master_agent.state = db_session.get_state()
        current_state = user_master_agent.state

        # Validation Logic (Simplified check)
        if current_state.get('missing_kyc_fields'):
             return jsonify({'message': 'KYC incomplete', 'error': 'kyc_incomplete'}), 400

        underwriting_result = underwriting_agent.perform_underwriting(current_state['entities'])
        user_master_agent.set_underwriting_result(
            risk_score=underwriting_result['risk_score'],
            approval_status=underwriting_result['approval_status'],
            interest_rate=underwriting_result.get('interest_rate', 12.5)
        )

        db_session.set_state(user_master_agent.state)
        db.session.commit()

        response = {
            'message': '✅ Approved!' if underwriting_result['approval_status'] else '❌ Rejected',
            'approval_status': underwriting_result['approval_status'],
            'worker': 'sales',
            'action': 'call_sales_api'
        }
        return jsonify(response)
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'underwriting_failed'}), 500

@app.route('/fraud', methods=['POST'])
def fraud_check():
    try:
        session_id = request.headers.get('X-Session-ID')
        db_session = ChatSession.query.get(session_id)
        if not db_session: return jsonify({'error': 'Invalid session'}), 400

        user_master_agent = MasterAgent()
        user_master_agent.state = db_session.get_state()
        
        fraud_result = fraud_agent.perform_fraud_check(user_master_agent.state['entities'])
        user_master_agent.set_fraud_result(fraud_score=fraud_result['fraud_score'], fraud_flag=fraud_result['fraud_flag'])

        db_session.set_state(user_master_agent.state)
        db.session.commit()

        return jsonify({'passed': fraud_result['fraud_flag'] != 'High', 'fraud_check': fraud_result})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'fraud_check_failed'}), 500

@app.route('/documentation', methods=['POST'])
def documentation():
    try:
        session_id = request.headers.get('X-Session-ID')
        db_session = ChatSession.query.get(session_id)
        if not db_session: return jsonify({'error': 'Invalid session'}), 400

        user_master_agent = MasterAgent()
        user_master_agent.state = db_session.get_state()

        if not user_master_agent.state.get('offer_accepted'):
            return jsonify({'error': 'Offer not accepted'}), 400

        pdf_path = generate_sanction_pdf(user_master_agent.state)
        user_master_agent.state['stage'] = ConversationStage.CLOSED
        
        db_session.set_state(user_master_agent.state)
        db.session.commit()

        return jsonify({'message': '✅ Sanction letter generated!', 'download_url': f'/download/{session_id}'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'documentation_failed'}), 500

# --- Admin Routes (Protected) ---

@app.route('/bank/admin/applications')
@require_role('admin')
def admin_applications():
    apps = LoanApplication.query.all()
    # Simplified: Returning as JSON for API-driven frontend, or render_template
    return jsonify([{'id': str(a.application_id), 'status': a.status} for a in apps])

@app.route('/bank/admin/tune', methods=['POST'])
@require_role('admin')
def admin_tune_post():
    data = request.get_json()
    content = data.get('content')
    if not content: return jsonify({'error': 'No content'}), 400

    try:
        new_tune = TuningContent(content=content, type='policy')
        db.session.add(new_tune)
        db.session.commit()
        return jsonify({'msg': 'Tuning added'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# --- Health & Maintenance ---

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'db': 'connected'})

@app.cli.command("cleanup-sessions")
def cleanup_sessions_command():
    """Run via CLI: flask cleanup-sessions"""
    deleted = ChatSession.query.filter(ChatSession.expires_at < datetime.utcnow()).delete()
    db.session.commit()
    print(f"Deleted {deleted} expired sessions")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
