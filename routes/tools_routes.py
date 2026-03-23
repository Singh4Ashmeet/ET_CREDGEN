from flask import Blueprint, request, jsonify
import re
import requests

tools_bp = Blueprint('tools', __name__)

@tools_bp.route('/tools/emi-calculator', methods=['GET'])
def emi_calculator():
    try:
        amount = float(request.args.get('amount', 0))
        rate = float(request.args.get('rate', 0))
        tenure = float(request.args.get('tenure', 0))

        if amount <= 0 or rate <= 0 or tenure <= 0:
            return jsonify({'error': 'Invalid inputs'}), 400

        monthly_rate = rate / 12 / 100
        emi = amount * monthly_rate * ((1 + monthly_rate)**tenure) / (((1 + monthly_rate)**tenure) - 1)
        
        total_payable = emi * tenure
        total_interest = total_payable - amount

        return jsonify({
            'monthly_emi': round(emi, 2),
            'total_payable': round(total_payable, 2),
            'total_interest': round(total_interest, 2),
            'principal': amount,
            'rate': rate,
            'tenure_months': tenure
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@tools_bp.route('/tools/validate-field', methods=['POST'])
def validate_field():
    data = request.get_json()
    field = data.get('field')
    value = data.get('value', '').strip()

    if not field or not value:
        return jsonify({'valid': False, 'hint': 'Missing field or value'}), 400

    if field == 'pan':
        # 5 chars, 4 digits, 1 char
        pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$'
        if re.match(pattern, value.upper()):
            return jsonify({'valid': True})
        return jsonify({'valid': False, 'hint': 'Format: ABCDE1234F'})

    elif field == 'aadhaar':
        # 12 digits
        clean_val = value.replace(' ', '').replace('-', '')
        if clean_val.isdigit() and len(clean_val) == 12:
            return jsonify({'valid': True})
        return jsonify({'valid': False, 'hint': 'Must be 12 digits'})

    elif field == 'phone':
        # Indian mobile: 10 digits, starts with 6-9
        pattern = r'^[6-9]\d{9}$'
        if re.match(pattern, value):
            return jsonify({'valid': True})
        return jsonify({'valid': False, 'hint': 'Invalid mobile number'})

    elif field == 'pincode':
        # 6 digits
        if value.isdigit() and len(value) == 6:
            # Optional: Call API
            try:
                resp = requests.get(f"https://api.postalpincode.in/pincode/{value}", timeout=2)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and data[0]['Status'] == 'Success':
                        po = data[0]['PostOffice'][0]
                        city = po.get('District', '')
                        state = po.get('State', '')
                        return jsonify({
                            'valid': True,
                            'details': {'city': city, 'state': state, 'district': city}
                        })
            except:
                pass # Fallback to just valid format
            return jsonify({'valid': True})
        return jsonify({'valid': False, 'hint': 'Must be 6 digits'})

    return jsonify({'valid': False, 'hint': 'Unknown field'})
