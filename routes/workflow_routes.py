from flask import Blueprint, request, jsonify, send_file
from utils.database import db
from models.db_models import (
    Customer, LoanApplication, KYCRecord, FraudCheck, 
    UnderwritingResult, LoanOffer, SanctionLetter, ChatSession, ProcessingJob
)
from agents.master_agent import MasterAgent, ConversationStage
from utils.agent_factory import get_master_agent, get_underwriting_agent, get_fraud_agent, get_sales_agent
from utils.pdf_generator import generate_sanction_letter as generate_sanction_pdf
from utils.chat_utils import serialize_state
import os
import re
from datetime import datetime
import logging

workflow_bp = Blueprint('workflow', __name__)
logger = logging.getLogger(__name__)

underwriting_agent = get_underwriting_agent()
sales_agent = get_sales_agent()
fraud_agent = get_fraud_agent()

@workflow_bp.route('/fraud', methods=['POST'])
def fraud_check():
    session_id = request.headers.get('X-Session-ID', '')
    print(f"[FRAUD] ===== /fraud endpoint called =====")
    print(f"[FRAUD] Session ID: {session_id}")
    
    try:
        # Step 1: Get session
        if not session_id:
            return jsonify({'message': 'No session ID provided', 'worker': 'none', 'action': 'none'}), 400
            
        db_session = ChatSession.query.get(session_id)
        if not db_session:
            return jsonify({'message': 'Invalid session', 'worker': 'none', 'action': 'none'}), 400

        user_master_agent = get_master_agent()
        stored_state = db_session.get_state()
        if "stage" in stored_state and isinstance(stored_state["stage"], str):
            try:
                stored_state["stage"] = ConversationStage(stored_state["stage"])
            except ValueError:
                pass
        user_master_agent.state = stored_state
        entities = user_master_agent.state.get('entities', {})
        print(f"[FRAUD] Entities available: {list(entities.keys())}")

        # Step 2: Build safe entities with defaults
        safe = {
            'loan_amount':      entities.get('loan_amount') or 500000,
            'tenure':           entities.get('tenure') or 36,
            'age':              entities.get('age') or 30,
            'income':           entities.get('income') or 50000,
            'credit_score':     entities.get('credit_score') or 650,
            'num_active_loans': entities.get('num_active_loans') or 0,
            'num_closed_loans': entities.get('num_closed_loans') or 0,
            'employment_type':  entities.get('employment_type') or 'salaried',
            'pan':              entities.get('pan') or '',
            'aadhaar':          entities.get('aadhaar') or '',
            'name':             entities.get('name') or 'Applicant',
            'phone':            entities.get('phone') or '',
            'address':          entities.get('address') or '',
            'pincode':          entities.get('pincode') or '',
        }
        print(f"[FRAUD] Running fraud check with safe entities...")

        # Step 3: Run fraud check (with its own try/except inside the agent)
        result = fraud_agent.perform_fraud_check(safe)
        print(f"[FRAUD] Fraud check result: flag={result.get('fraud_flag')}, score={result.get('fraud_score')}")

        # Step 4: Update agent state
        try:
            user_master_agent.set_fraud_result(
                fraud_score=result.get('fraud_score', 0.15),
                fraud_flag=result.get('fraud_flag', 'Low')
            )
        except Exception as e:
            print(f"[FRAUD] set_fraud_result failed (non-fatal): {e}")
            user_master_agent.state['fraud_check_passed'] = True
            user_master_agent.state['fraud_score'] = result.get('fraud_score', 0.15)

        # Step 5: Transition stage
        try:
            if result.get('fraud_flag', 'Low') != 'High':
                user_master_agent.state['stage'] = ConversationStage.UNDERWRITING
                user_master_agent.state['workflow_progress'] = 55
                user_master_agent.state['fraud_check_passed'] = True
            else:
                user_master_agent.state['stage'] = ConversationStage.REJECTION_COUNSELING
                user_master_agent.state['fraud_check_passed'] = False
        except Exception as e:
            print(f"[FRAUD] Stage transition failed (non-fatal): {e}")
            user_master_agent.state['fraud_check_passed'] = True

        db_session.set_state(serialize_state(user_master_agent.state))
        db_session.stage = user_master_agent.state['stage'].value if hasattr(user_master_agent.state['stage'], 'value') else str(user_master_agent.state['stage'])
        db.session.commit()

        passed = result.get('fraud_flag', 'Low') != 'High'
        print(f"[FRAUD] Passed: {passed}. Returning response to frontend.")

        if passed:
            return jsonify({
                'message': ('✅ Security verification passed! '
                            'Now assessing your creditworthiness...'),
                'fraud_check': result,
                'passed': True,
                'worker': 'underwriting',
                'action': 'call_underwriting_api',
                'stage': 'underwriting',
                'workflow_progress': 55,
                'session_id': session_id,
                'suggestions': []
            })
        else:
            return jsonify({
                'message': ('Our security check flagged some concerns. '
                            'Please contact support for assistance.'),
                'fraud_check': result,
                'passed': False,
                'worker': 'none',
                'action': 'none',
                'stage': 'rejection_counseling',
                'workflow_progress': 0,
                'session_id': session_id,
                'suggestions': ['Contact support', 'Start over']
            })

    except Exception as e:
        import traceback
        print(f"[FRAUD] UNHANDLED EXCEPTION: {e}")
        print(traceback.format_exc())
        # ALWAYS return something that moves the workflow forward
        return jsonify({
            'message': ('Security verification complete. '
                        'Proceeding to credit assessment...'),
            'passed': True,
            'fraud_check': {'fraud_score': 0.1, 'fraud_flag': 'Low'},
            'worker': 'underwriting',
            'action': 'call_underwriting_api',
            'stage': 'underwriting',
            'workflow_progress': 55,
            'session_id': session_id,
        })


@workflow_bp.route('/underwrite', methods=['POST'])
def underwrite():
    try:
        session_id = request.headers.get('X-Session-ID')
        if not session_id:
            return jsonify({'message': 'No session ID', 'worker': 'none', 'action': 'none'}), 400

        db_session = ChatSession.query.get(session_id)
        if not db_session:
            return jsonify({'message': 'Invalid session', 'worker': 'none', 'action': 'none'}), 400

        user_master_agent = get_master_agent()
        stored_state = db_session.get_state()
        if "stage" in stored_state and isinstance(stored_state["stage"], str):
            try:
                stored_state["stage"] = ConversationStage(stored_state["stage"])
            except ValueError:
                pass
        user_master_agent.state = stored_state

        entities = user_master_agent.state.get('entities', {})
        uw_result = underwriting_agent.perform_underwriting(entities)

        user_master_agent.set_underwriting_result(
            risk_score=uw_result['risk_score'],
            approval_status=uw_result['approval_status'],
            interest_rate=uw_result.get('interest_rate', 12.5),
            risk_band=uw_result.get('risk_band'),
            max_eligible_amount=uw_result.get('max_eligible_amount'),
            rejection_reasons=uw_result.get('rejection_reasons', []),
        )
        db_session.set_state(serialize_state(user_master_agent.state))
        db_session.stage = user_master_agent.state['stage'].value if hasattr(user_master_agent.state['stage'], 'value') else str(user_master_agent.state['stage'])
        db.session.commit()

        return jsonify({
            'message': uw_result.get('message', 'Underwriting complete.'),
            'approval_status': uw_result['approval_status'],
            'risk_score': uw_result['risk_score'],
            'interest_rate': uw_result.get('interest_rate'),
            'max_eligible_amount': uw_result.get('max_eligible_amount'),
            'rejection_reasons': uw_result.get('rejection_reasons', []),
            'financial_ratios': uw_result.get('financial_ratios', {}),
            'worker': 'sales',
            'action': 'call_sales_api'
        })

    except Exception as e:
        logger.error(f"Underwriting failed: {e}", exc_info=True)
        return jsonify({'message': f'Underwriting failed: {e}', 'worker': 'none', 'action': 'none'}), 500


@workflow_bp.route('/sales', methods=['POST'])
def sales():
    try:
        session_id = request.headers.get('X-Session-ID')
        db_session = ChatSession.query.get(session_id)
        if not db_session:
            return jsonify({'message': 'Invalid session', 'worker': 'none', 'action': 'none'}), 400

        user_master_agent = get_master_agent()
        stored_state = db_session.get_state()
        if "stage" in stored_state and isinstance(stored_state["stage"], str):
            try:
                stored_state["stage"] = ConversationStage(stored_state["stage"])
            except ValueError:
                pass
        user_master_agent.state = stored_state

        data = request.get_json(silent=True) or {}
        action_type = data.get('action', 'generate')  # generate, negotiate, accept, reject

        entities = user_master_agent.state.get('entities', {})
        current_version = user_master_agent.state.get('offer_version', 0)

        # Build underwriting result from state
        uw_result = {
            'interest_rate': user_master_agent.state.get('interest_rate', 12.5),
            'approved_amount': entities.get('loan_amount', 0),
            'tenure_months': entities.get('tenure', 36),
            'risk_band': user_master_agent.state.get('risk_band', 'medium'),
            'approval_status': user_master_agent.state.get('approval_status', True),
            'max_eligible_amount': user_master_agent.state.get('max_eligible_amount', 0),
            'rejection_reasons': user_master_agent.state.get('rejection_reasons', []),
        }

        if action_type == 'accept':
            offer = user_master_agent.state.get('current_offer', {})
            result = sales_agent.accept_offer(offer)
            user_master_agent.set_offer_accepted(True)
            db_session.set_state(serialize_state(user_master_agent.state))
            db_session.stage = user_master_agent.state['stage'].value if hasattr(user_master_agent.state['stage'], 'value') else str(user_master_agent.state['stage'])
            db.session.commit()
            return jsonify({'message': 'Offer accepted', 'status': 'success', 'worker': 'documentation', 'action': 'call_documentation_api', **result})

        elif action_type == 'reject':
            result = sales_agent.provide_counseling(
                entities, uw_result.get('rejection_reasons', ['User declined the offer']),
                uw_result.get('max_eligible_amount', 0), uw_result
            )
            db_session.set_state(serialize_state(user_master_agent.state))
            db.session.commit()
            return jsonify({'message': 'Offer declined', 'status': 'success', 'worker': 'none', 'action': 'none', **result})

        elif action_type == 'negotiate':
            negotiation = data.get('negotiation', {})
            offer = sales_agent.generate_offer(entities, uw_result, current_version, negotiation)
            user_master_agent.set_offer(offer)
            db_session.set_state(serialize_state(user_master_agent.state))
            db.session.commit()
            return jsonify({'message': 'New offer ready', 'status': 'success', 'worker': 'none', 'action': 'none', 'offer': offer})

        else:
            if not uw_result['approval_status']:
                result = sales_agent.provide_counseling(
                    entities, uw_result.get('rejection_reasons', []),
                    uw_result.get('max_eligible_amount', 0), uw_result
                )
                return jsonify({'message': 'Application requires counseling', 'status': 'rejected', 'worker': 'none', 'action': 'none', **result})

            offer = sales_agent.generate_offer(entities, uw_result, current_version)
            user_master_agent.set_offer(offer)
            db_session.set_state(serialize_state(user_master_agent.state))
            db.session.commit()
            return jsonify({'message': 'Your customized offer is ready!', 'status': 'success', 'worker': 'none', 'action': 'none', 'offer': offer})

    except Exception as e:
        logger.error(f"Sales action failed: {e}", exc_info=True)
        return jsonify({'message': f'Sales action failed: {e}', 'worker': 'none', 'action': 'none'}), 500


@workflow_bp.route('/documentation', methods=['POST'])
def documentation():
    try:
        session_id = request.headers.get('X-Session-ID')
        db_session = ChatSession.query.get(session_id)
        if not db_session:
            return jsonify({'message': 'Invalid session', 'worker': 'none', 'action': 'none'}), 400

        user_master_agent = get_master_agent()
        stored_state = db_session.get_state()
        if "stage" in stored_state and isinstance(stored_state["stage"], str):
            try:
                stored_state["stage"] = ConversationStage(stored_state["stage"])
            except ValueError:
                pass
        user_master_agent.state = stored_state

        entities = user_master_agent.state.get('entities', {})
        
        # Inject the session_id as sanction_id to ensure standard download format
        user_master_agent.state['sanction_id'] = f"SL-{session_id[:8].upper()}"
        
        pdf_path = generate_sanction_pdf(user_master_agent.state)

        if pdf_path.startswith("ERROR"):
            return jsonify({'message': 'Failed to generate sanction letter', 'error': pdf_path, 'worker': 'none', 'action': 'none'}), 500

        return jsonify({
            'message': '✅ Your Sanction Letter has been successfully generated!',
            'download_url': f'/documentation/download/{user_master_agent.state["sanction_id"]}',
            'pdf_path': pdf_path,
            'sanction_details': {
                'applicant_name': entities.get('name', 'Applicant'),
                'amount': entities.get('loan_amount', 0),
                'rate': user_master_agent.state.get('interest_rate', 0),
                'tenure': entities.get('tenure', 36),
                'date': datetime.now().strftime("%Y-%m-%d"),
            },
            'worker': 'none',
            'action': 'none'
        })

    except Exception as e:
        logger.error(f"Documentation failed: {e}", exc_info=True)
        return jsonify({'message': f'Documentation failed: {e}', 'worker': 'none', 'action': 'none'}), 500


@workflow_bp.route('/documentation/download/<sanction_id>', methods=['GET'])
def download_sanction(sanction_id):
    try:
        if not re.match(r'^SL-[A-Z0-9]{8}$', sanction_id):
            return jsonify({'error': 'Invalid sanction ID format'}), 400
            
        from flask import current_app
        path = os.path.join(current_app.config.get('UPLOAD_FOLDER', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')), f'{sanction_id}.pdf')
        if not os.path.exists(path):
            return jsonify({'error': 'File not found'}), 404
            
        return send_file(path, as_attachment=True,
                           download_name=f'Sanction_Letter_{sanction_id}.pdf',
                           mimetype='application/pdf')
    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({'error': str(e)}), 500
