from flask import Blueprint, request, jsonify, Response, stream_with_context
from utils.database import db
from models.db_models import ChatSession, Customer, LoanApplication, KYCRecord
from agents.master_agent import IntentType, ConversationStage
from utils.agent_factory import get_master_agent
from utils.chat_utils import (
    get_session_id, log_chat_event, initialize_user_session, 
    update_session_activity, get_bank_context, 
    determine_worker_from_stage, get_workflow_stage_details,
    serialize_state
)
from utils.llm_factory import get_llm_service
import json
import os
import uuid
from datetime import datetime
from flask import current_app

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/chat', methods=['POST'])
def chat():
    try:
        session_id = get_session_id(request)

        # Parse input
        if request.content_type and 'multipart/form-data' in request.content_type:
            user_input = (request.form.get('message') or '').strip()
        else:
            data = request.get_json(silent=True) or {}
            user_input = (data.get('message') or '').strip()

        if not user_input:
            return jsonify({
                'message': 'Please type a message to get started.',
                'worker': 'none', 'action': 'none',
                'stage': 'collecting_details',
                'workflow_progress': 0,
                'suggestions': ['I need a personal loan',
                                'Tell me about home loans',
                                'What documents do I need?']
            })

        # Get or create session
        db_session = initialize_user_session(session_id)
        db_session.interaction_count += 1
        user_master_agent = get_master_agent()

        stored_state = db_session.get_state()
        if "stage" in stored_state and isinstance(stored_state["stage"], str):
            try:
                stored_state["stage"] = ConversationStage(stored_state["stage"])
            except ValueError:
                pass
        
        user_master_agent.state = stored_state

        user_sessions = getattr(current_app, 'user_sessions', {})
        if session_id not in user_sessions:
            user_sessions[session_id] = db_session
            current_app.user_sessions = user_sessions
        
        # We need a plain dict `session` to work like the user's pseudo code if needed, but we'll adapt to models
        setattr(db_session, 'master_agent', user_master_agent)

        llm_service = get_llm_service()
        gemini_mode = os.getenv("LLM_MODE", "disabled").lower().strip()
        if db_session.failure_count >= 3:
            gemini_mode = "disabled"

        response = None

        # ── CORE AGENT LOGIC ──────────────────────────────────────────────
        # All conversational and workflow logic is now handled internally by MasterAgent
        extracted = user_master_agent.extract_entities_from_text(user_input)
        if extracted:
            user_master_agent.update_entities(extracted)
            user_master_agent.recalculate_missing_fields()
        
        response = user_master_agent.handle(user_input)

        # Safety: response must always be a valid dict with message
        if not isinstance(response, dict):
            response = {}
        if not response.get('message'):
            response['message'] = _get_contextual_fallback(
                user_master_agent.state)

        # Persist state and add session info
        db_session.set_state(serialize_state(user_master_agent.state))
        db_session.stage = user_master_agent.state["stage"].value if hasattr(user_master_agent.state["stage"], 'value') else user_master_agent.state["stage"]
        db.session.commit()
        
        response['session_id'] = session_id
        response['interaction_count'] = db_session.interaction_count

        # Log to CSV/DB
        try:
            log_chat_event(session_id, 'message', {
                'role': 'user', 'text': user_input, 'status': None, 'details': {}
            })
            log_chat_event(session_id, 'message', {
                'role': 'assistant',
                'text': response.get('message', '')[:500],
                'status': None,
                'details': {'stage': response.get('stage'),
                            'worker': response.get('worker')}
            })
        except Exception:
            pass

        resp = jsonify(response)
        resp.headers['X-Session-ID'] = session_id
        return resp

    except Exception as e:
        import traceback
        print(f"[CHAT] UNHANDLED EXCEPTION: {e}")
        print(traceback.format_exc())
        return jsonify({
            'message': ("I'm here to help with your loan application. "
                        "Please tell me the loan amount you're looking for."),
            'worker': 'none',
            'action': 'none',
            'stage': 'collecting_details',
            'workflow_progress': 0,
            'suggestions': ['I need ₹5 lakh personal loan',
                            'I want a home loan',
                            'Tell me what you offer']
        })


def _get_contextual_fallback(state: dict) -> str:
    """Always returns a relevant non-empty message based on current stage."""
    from agents.master_agent import ConversationStage
    
    current_stage = state.get('stage', ConversationStage.COLLECTING_DETAILS)
    if isinstance(current_stage, str):
        try:
           current_stage = ConversationStage(current_stage)
        except:
           pass
           
    stage = current_stage
    entities = state.get('entities', {})
    missing = list(state.get('missing_fields', []))

    if stage == ConversationStage.COLLECTING_DETAILS:
        field_questions = {
            'loan_amount': "What loan amount are you looking for? (e.g., ₹5 lakh, ₹10 lakh)",
            'purpose':     "What will you use this loan for? (personal use, home, education, business)",
            'name':        "Could you share your full name?",
            'age':         "What is your age?",
            'employment_type': "Are you salaried, self-employed, or a business owner?",
            'income':      "What is your monthly income?",
            'phone':       "Could you share your 10-digit mobile number?",
            'email':       "What is your email address?",
            'tenure':      "For how many months/years would you like the loan?"
        }
        for field in ['loan_amount','purpose','name','age','employment_type','income','tenure','phone','email']:
            if field in missing:
                return field_questions.get(field, "Please provide " + field)
        return "Great! I have all your basic details. Let me guide you to the next step."

    elif stage == ConversationStage.KYC_COLLECTION:
        kyc_missing = list(state.get('missing_kyc_fields', []))
        kyc_questions = {
            'pan':     "Please share your PAN card number (e.g., ABCDE1234F).",
            'aadhaar': "Please provide your 12-digit Aadhaar number.",
            'address': "What is your current residential address?",
            'pincode': "What is your 6-digit pincode?",
        }
        for field in ['pan', 'aadhaar', 'address', 'pincode']:
            if field in kyc_missing:
                return kyc_questions[field]
        return ("All KYC details collected! Running security verification now...")

    elif stage == ConversationStage.FRAUD_CHECK:
        return "Running security checks on your application. This takes a moment..."

    elif stage == ConversationStage.UNDERWRITING:
        return "Assessing your creditworthiness. Almost there..."

    elif stage == ConversationStage.OFFER_PRESENTATION:
        offer = state.get('offer', state.get('current_offer', {}))
        if offer:
            emi = offer.get('monthly_emi', 0)
            rate = offer.get('interest_rate', 0)
            amount = offer.get('loan_amount', 0) or entities.get('loan_amount', 0)
            return (f"Great news! You're approved for ₹{amount:,} at {rate}% p.a. "
                    f"Your monthly EMI would be ₹{emi:,.0f}. "
                    f"Would you like to accept this offer?")
        return "Your loan offer is ready! Shall I show you the details?"

    elif stage == ConversationStage.DOCUMENTATION:
        return ("Your offer has been accepted! Generating your sanction letter now. "
                "You can download it once ready.")

    elif stage == ConversationStage.CLOSED:
        return "Your loan application is complete. Your sanction letter is ready to download!"

    return ("I'm here to help with your loan. "
            "What amount are you looking for?")

@chat_bp.route('/session/resume', methods=['GET'])
def resume_session():
    phone = request.args.get('phone')
    if not phone:
        return jsonify({'resumed': False}), 400
        
    session = db.session.query(ChatSession).join(LoanApplication).join(Customer).filter(
        Customer.phone == phone,
        ChatSession.expires_at > datetime.utcnow()
    ).order_by(ChatSession.last_activity.desc()).first()
    
    if session:
        return jsonify({
            'resumed': True,
            'session_id': session.session_id,
            'stage': session.stage,
            'progress': session.state.get('workflow_progress', 0),
            'summary_of_collected_info': session.state.get('entities', {})
        })
    return jsonify({'resumed': False})

@chat_bp.route('/session/state', methods=['GET'])
def get_session_state():
    session_id = request.headers.get('X-Session-ID')
    if not session_id:
        return jsonify({'error': 'No session ID'}), 400
        
    session = ChatSession.query.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
        
    return jsonify({
        'stage': session.stage,
        'entities': session.state.get('entities', {}),
        'progress': session.state.get('workflow_progress', 0)
    })

@chat_bp.route('/session/reset', methods=['DELETE'])
def reset_session():
    session_id = request.headers.get('X-Session-ID')
    if session_id:
        ChatSession.query.filter_by(session_id=session_id).delete()
        db.session.commit()
    return jsonify({'message': 'Session reset'})
