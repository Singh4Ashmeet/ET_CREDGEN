from flask import request
import uuid
from datetime import datetime
from utils.database import db
from models.db_models import ChatSession, ChatLog, LoanApplication, Customer, TuningContent
from agents.master_agent import MasterAgent, IntentType, ConversationStage
import logging
from enum import Enum

logger = logging.getLogger(__name__)

def serialize_state(state):
    """Recursively convert Enums and sets to values for JSON serialization."""
    if isinstance(state, dict):
        return {k: serialize_state(v) for k, v in state.items()}
    elif isinstance(state, (list, set, tuple)):
        return [serialize_state(i) for i in state]
    elif isinstance(state, Enum):
        return state.value
    return state

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
        logger.error(f"Failed to log chat event: {e}")

def initialize_user_session(session_id):
    session = ChatSession.query.get(session_id)
    if not session:
        session = ChatSession(
            session_id=session_id,
            state={},
            stage=ConversationStage.GREETING.value  # Start at GREETING, not COLLECTING_DETAILS
        )
        # We need a MasterAgent instance to get initial state
        temp_agent = MasterAgent()
        session.set_state(serialize_state(temp_agent.state))
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
        logger.error(f"Error loading bank context: {e}")
    return ""

def _normalize_stage(current_stage) -> str:
    """Get uppercase name from stage (handles both Enum and string)."""
    if hasattr(current_stage, 'name'):
        return current_stage.name  # Enum → e.g. 'COLLECTING_DETAILS'
    s = str(current_stage).upper()
    return s

def determine_worker_from_stage(current_stage):
    worker_map = {
        'FRAUD_CHECK': "fraud",
        'UNDERWRITING': "underwriting",
        'OFFER_PRESENTATION': "sales",
        'DOCUMENTATION': "documentation",
        'REJECTION_COUNSELING': "sales"
    }
    stage_str = _normalize_stage(current_stage)
    return worker_map.get(stage_str, "none")

def get_workflow_stage_details(stage):
    stage_name = _normalize_stage(stage)
    stage_details = {
        'GREETING': {"name": "Greeting", "progress": 5, "next": "Basic Details"},
        'COLLECTING_DETAILS': {"name": "Basic Details Collection", "progress": 20, "next": "KYC Collection"},
        'KYC_COLLECTION': {"name": "KYC Verification", "progress": 40, "next": "Fraud Detection"},
        'FRAUD_CHECK': {"name": "Fraud Detection", "progress": 60, "next": "Underwriting"},
        'UNDERWRITING': {"name": "Underwriting", "progress": 80, "next": "Offer Presentation"},
        'OFFER_PRESENTATION': {"name": "Offer Presentation", "progress": 90, "next": "Documentation"},
        'REJECTION_COUNSELING': {"name": "Rejection Counseling", "progress": 90, "next": "Closed"},
        'DOCUMENTATION': {"name": "Documentation", "progress": 100, "next": "Completion"},
        'CLOSED': {"name": "Completed", "progress": 100, "next": "Done"},
    }
    return stage_details.get(stage_name, {"name": "Unknown", "progress": 0})
