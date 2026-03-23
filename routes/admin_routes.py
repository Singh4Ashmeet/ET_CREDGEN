from flask import Blueprint, request, jsonify, Response, stream_with_context
from database import db
from db_models import LoanApplication, Customer, KYCRecord, FraudCheck, UnderwritingResult, ChatSession, TuningContent
from utils.auth_utils import require_role
from sqlalchemy import func, desc, case, text
from datetime import datetime, timedelta
import csv
import io

import csv
import io
import os

admin_bp = Blueprint('admin', __name__)

APPLICATIONS_CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'csv', 'applications.csv')

def read_csv(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, mode='r', encoding='utf-8') as f:
        return list(csv.DictReader(f))

@admin_bp.route('/admin/analytics/summary', methods=['GET'])
def admin_analytics_summary():
    try:
        rows = read_csv(APPLICATIONS_CSV)
        from datetime import date
        today = date.today().isoformat()

        total = len(rows)
        approved = sum(1 for r in rows
                       if r.get('status','').lower() == 'approved')
        rejected = sum(1 for r in rows
                       if r.get('status','').lower() == 'rejected')
        pending  = sum(1 for r in rows
                       if r.get('status','').lower()
                       in ('pending','initiated',''))

        approved_today = sum(
            1 for r in rows
            if r.get('status','').lower() == 'approved'
            and r.get('timestamp','').startswith(today))

        # Avg loan amount
        amounts = []
        for r in rows:
            try:
                amt = float(str(r.get('loan_amount', 0)
                                 ).replace(',',''))
                if amt > 0:
                    amounts.append(amt)
            except:
                pass
        avg_amount = sum(amounts) / len(amounts) if amounts else 0

        # Approval rate
        decided = approved + rejected
        approval_rate = (approved / decided * 100) if decided > 0 else 0

        # By status counts
        status_counts = {}
        for r in rows:
            s = r.get('status', 'pending').lower() or 'pending'
            status_counts[s] = status_counts.get(s, 0) + 1

        # Daily counts last 30 days
        from collections import defaultdict
        daily = defaultdict(int)
        for r in rows:
            ts = r.get('timestamp', '')
            if ts:
                day = ts[:10]  # YYYY-MM-DD
                daily[day] += 1
        daily_counts = [{'date': k, 'count': v}
                        for k, v in sorted(daily.items())[-30:]]

        return jsonify({
            'total_applications':  total,
            'approved_today':      approved_today,
            'rejected_today':      rejected,
            'approval_rate_pct':   round(approval_rate, 1),
            'avg_loan_amount':     round(avg_amount, 0),
            'avg_risk_score':      0,
            'applications_by_status': status_counts,
            'applications_by_loan_type': {},
            'daily_counts':        daily_counts,
        })
    except Exception as e:
        import traceback
        print(f"[ADMIN] analytics error: {e}\n{traceback.format_exc()}")
        return jsonify({
            'total_applications': 0, 'approved_today': 0,
            'rejected_today': 0, 'approval_rate_pct': 0,
            'avg_loan_amount': 0, 'avg_risk_score': 0,
            'applications_by_status': {},
            'applications_by_loan_type': {},
            'daily_counts': []
        })

@admin_bp.route('/admin/analytics/funnel', methods=['GET'])
@require_role('admin')
def admin_analytics_funnel():
    # Keep DB funnel for now if needed, or return empty if transitioning
    return jsonify({
        'initiated': 0,
        'kyc_completed': 0,
        'fraud_checked': 0,
        'underwritten': 0,
        'offer_presented': 0,
        'approved': 0
    })

@admin_bp.route('/admin/applications', methods=['GET'])
def admin_get_applications():
    try:
        # Read from CSV (existing data layer)
        rows = read_csv(APPLICATIONS_CSV)
        print(f"[ADMIN] Raw CSV rows: {len(rows)}")
        if rows:
            print(f"[ADMIN] CSV columns: {list(rows[0].keys())}")

        # Query params for filtering
        status_filter   = request.args.get('status', '').strip()
        page            = int(request.args.get('page', 1))
        per_page        = int(request.args.get('per_page', 20))

        # Normalize each row — map CSV column names to expected fields
        # The CSV uses: timestamp, session_id, full_name, phone, email,
        #               city, loan_amount, status, rejection_reason,
        #               attached_files
        applications = []
        for row in rows:
            # Handle both old and new column name formats
            app_entry = {
                'application_id': row.get('session_id',
                                  row.get('application_id', 'N/A')),
                'customer_name':  row.get('full_name',
                                  row.get('customer_name',
                                  row.get('name', 'Unknown'))),
                'phone':          row.get('phone', 'N/A'),
                'email':          row.get('email', 'N/A'),
                'loan_amount':    row.get('loan_amount',
                                  row.get('amount', 0)),
                'loan_type':      row.get('loan_type',
                                  row.get('type', 'personal')),
                'status':         row.get('status', 'pending'),
                'created_at':     row.get('timestamp',
                                  row.get('created_at',
                                  row.get('date', 'N/A'))),
                'rejection_reason': row.get('rejection_reason', ''),
                'city':           row.get('city', 'N/A'),
            }
            # Filter by status if provided
            if (status_filter and status_filter.lower() != 'all'
                    and app_entry['status'].lower()
                    != status_filter.lower()):
                continue
            applications.append(app_entry)

        # Sort by date descending (newest first)
        applications.sort(
            key=lambda x: x.get('created_at', ''), reverse=True)

        # Paginate
        total = len(applications)
        start = (page - 1) * per_page
        end   = start + per_page
        page_items = applications[start:end]

        print(f"[ADMIN] Returning {len(page_items)} of {total} applications")

        return jsonify({
            'applications': page_items,
            'total':        total,
            'page':         page,
            'per_page':     per_page,
            'total_pages':  max(1, (total + per_page - 1) // per_page),
            'status':       'ok'
        })

    except Exception as e:
        import traceback
        print(f"[ADMIN] /admin/applications error: {e}")
        print(traceback.format_exc())
        return jsonify({
            'applications': [],
            'total': 0, 'page': 1,
            'per_page': 20, 'total_pages': 1,
            'error': str(e)
        }), 500

@admin_bp.route('/admin/export/applications', methods=['GET'])
def export_applications_csv():
    try:
        import csv, io
        rows = read_csv(APPLICATIONS_CSV)
        status_filter = request.args.get('status','').lower()

        output = io.StringIO()
        fieldnames = ['timestamp','session_id','full_name','phone',
                      'email','city','loan_amount','status',
                      'rejection_reason']
        writer = csv.DictWriter(output, fieldnames=fieldnames,
                                extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            if (status_filter and status_filter != 'all'
                    and row.get('status','').lower()
                    != status_filter):
                continue
            writer.writerow(row)

        from flask import Response
        from datetime import datetime as dt
        filename = f"applications_{dt.now().strftime('%Y%m%d')}.csv"
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition':
                    f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/admin/applications/<app_id>', methods=['GET'])
def get_application_detail(app_id):
    # Search in CSV
    rows = read_csv(APPLICATIONS_CSV)
    for row in rows:
        if row.get('session_id') == app_id or row.get('application_id') == app_id:
            return jsonify({
                'application_id': app_id,
                'customer_name': row.get('full_name', row.get('customer_name', 'Unknown')),
                'phone': row.get('phone', 'N/A'),
                'email': row.get('email', 'N/A'),
                'loan_amount': row.get('loan_amount', 0),
                'status': row.get('status', 'pending'),
                'created_at': row.get('timestamp', row.get('created_at', 'N/A')),
                'rejection_reason': row.get('rejection_reason', ''),
                'city': row.get('city', 'N/A')
            })
    return jsonify({"error": "Not found"}), 404

@admin_bp.route('/admin/tune', methods=['POST'])
@require_role('admin')
def admin_tune_post():
    data = request.get_json()
    content = data.get('content')
    if not content: return jsonify({'error': 'No content'}), 400

    try:
        # Inactivate old ones? Or just add new? Prompt says "existing bank context editor, unchanged"
        # I'll just add new active one.
        new_tune = TuningContent(content=content, type='policy', is_active=True)
        db.session.add(new_tune)
        db.session.commit()
        return jsonify({'msg': 'Tuning added'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
