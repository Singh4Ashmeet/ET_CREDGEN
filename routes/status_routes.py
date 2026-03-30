from flask import Blueprint, request, jsonify
from utils.database import db
from models.db_models import LoanApplication, Customer, KYCRecord, SanctionLetter
from sqlalchemy import desc

status_bp = Blueprint('status', __name__)

@status_bp.route('/application/status', methods=['GET'])
def check_status():
    phone = request.args.get('phone')
    pan = request.args.get('pan')
    
    if not phone or not pan:
        return jsonify({'error': 'Phone and PAN required'}), 400
        
    # Join Customer, KYCRecord, LoanApplication
    # We want the *latest* application for this customer who matches this PAN
    
    # 1. Find Customer by phone
    customer = Customer.query.filter_by(phone=phone).first()
    if not customer:
        return jsonify({'error': 'No application found'}), 404
        
    # 2. Check if PAN matches any KYC record for this customer?
    # Or just check if there is an application linked to a KYC record with this PAN?
    
    # Safer: Find Application -> KYC -> PAN
    application = LoanApplication.query.join(Customer).join(KYCRecord).filter(
        Customer.phone == phone,
        KYCRecord.pan_no == pan
    ).order_by(desc(LoanApplication.created_at)).first()
    
    if not application:
        return jsonify({'error': 'No application found matching these details'}), 404
        
    response = {
        'application_id': application.application_id,
        'status': application.status,
        'stage': 'unknown', # Map internal status to stage if possible
        'loan_amount': application.loan_amount,
        'created_at': application.created_at,
        'last_updated': application.updated_at,
        'rejection_reason': application.rejection_reason
    }
    
    # Add offer summary if exists
    if application.offers:
        latest_offer = application.offers[-1] # Assuming order or last
        response['offer_summary'] = {
            'amount': latest_offer.loan_amount,
            'rate': latest_offer.interest_rate,
            'tenure': latest_offer.tenure_months,
            'emi': latest_offer.monthly_emi
        }
        
    # Add sanction letter URL if exists
    if application.sanction_letter:
        response['sanction_letter_url'] = f"/documentation/download/{application.sanction_letter.letter_id}"
        
    return jsonify(response)
