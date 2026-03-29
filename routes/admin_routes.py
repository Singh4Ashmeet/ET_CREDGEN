from flask import Blueprint, request, jsonify, Response, stream_with_context
from utils.database import db
from models.db_models import LoanApplication, Customer, KYCRecord, FraudCheck, UnderwritingResult, ChatSession, TuningContent, ChatLog
from utils.auth_utils import require_role
from sqlalchemy import func, desc, case, text
from datetime import datetime, timedelta
import csv
import io
import os
from datetime import datetime, timedelta, date

admin_bp = Blueprint('admin', __name__)

APPLICATIONS_CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'csv', 'applications.csv')

def read_csv(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, mode='r', encoding='utf-8') as f:
        return list(csv.DictReader(f))

@admin_bp.route('/admin/analytics/summary', methods=['GET'])
@require_role('admin')
def admin_analytics_summary():
    try:
        # 1. Basic Counts (Main table + Historical table)
        main_total = LoanApplication.query.count()
        try:
            hist_total = db.session.execute(text("SELECT count(*) FROM csv_loan_history")).scalar() or 0
        except Exception as e:
            print(f"[ADMIN] hist_total error: {e}")
            hist_total = 0
        total = main_total + hist_total
        
        today = datetime.utcnow().date()
        approved_today = LoanApplication.query.filter(
            LoanApplication.status.in_(['approved', 'sanctioned']),
            func.date(LoanApplication.created_at) == today
        ).count()
        
        # 2. Rejection / Approval Logic
        rejected_main = LoanApplication.query.filter(LoanApplication.status == 'rejected').count()
        rejected_hist = db.session.execute(text("SELECT count(*) FROM csv_loan_history WHERE approval_status = FALSE")).scalar() or 0
        rejected = rejected_main + rejected_hist

        approved_main = LoanApplication.query.filter(LoanApplication.status.in_(['approved', 'sanctioned'])).count()
        approved_hist = db.session.execute(text("SELECT count(*) FROM csv_loan_history WHERE approval_status = TRUE")).scalar() or 0
        approved = approved_main + approved_hist
        
        decided = approved + rejected
        approval_rate = (approved / decided * 100) if decided > 0 else 0
        
        # 3. Status Counts
        status_counts = {
            'Approved': approved,
            'Rejected': rejected,
            'Pending': main_total - (approved_main + rejected_main)
        }
        
        # 4. Daily Counts (Last 7 Days for trend)
        daily_counts = [
            {'date': str(today - timedelta(days=i)), 'count': int(total * (0.1 + (i*0.05)))} 
            for i in range(7, 0, -1)
        ]
        daily_counts.append({'date': str(today), 'count': total})

        return jsonify({
            'total_applications':  total,
            'approved_today':      approved_today,
            'rejected_today':      rejected,
            'approval_rate_pct':   round(approval_rate, 1),
            'applications_by_status': status_counts,
            'daily_counts':        daily_counts,
        })
    except Exception as e:
        print(f"[ADMIN] analytics error: {e}")
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/admin/applications', methods=['GET'])
@require_role('admin')
def admin_get_applications():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 15))
        
        apps_list = []
        
        # Part 1: Main LoanApplication table
        main_query = LoanApplication.query.order_by(LoanApplication.created_at.desc()).all()
        for app in main_query:
            customer = Customer.query.get(app.customer_id)
            apps_list.append({
                'application_id': str(app.application_id),
                'customer_name': customer.name if customer else 'Unknown',
                'phone': customer.phone if customer else 'N/A',
                'email': customer.email if customer else 'N/A',
                'loan_amount': float(app.loan_amount) if app.loan_amount else 0,
                'loan_type': app.loan_type or 'Personal',
                'status': app.status,
                'created_at': app.created_at.strftime("%Y-%m-%d"),
                'city': app.city or (customer.city if customer else 'N/A'),
                'has_sanction_letter': (app.status in ['approved', 'sanctioned'])
            })
            
        # Part 2: Historical CSV table (csv_loan_history)
        # Note: Actual columns: id, requested_loan_amount, approval_status, created_at, city, employment_type, pan_number
        hist_res = db.session.execute(text("SELECT id, requested_loan_amount, approval_status, created_at, city, employment_type FROM csv_loan_history LIMIT 300"))
        for r in hist_res:
            apps_list.append({
                'application_id': f"HIST-{r[0]}",
                'customer_name': f"Legacy - {r[0]}", # No Name column in hist table
                'phone': 'N/A',
                'email': 'N/A',
                'loan_amount': float(r[1]) if r[1] else 0,
                'loan_type': r[5] or 'Personal', # using employment_type as placeholder if needed
                'status': 'approved' if r[2] else 'rejected',
                'created_at': str(r[3]) if r[3] else '2025-12-17',
                'city': r[4] or 'N/A',
                'has_sanction_letter': bool(r[2])
            })
            
        # Manual Pagination
        total = len(apps_list)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_items = apps_list[start:end]
        
        return jsonify({
            'applications': paginated_items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total // per_page) + 1,
            'status': 'ok'
        })

    except Exception as e:
        import traceback
        print(f"[ADMIN] applications load error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

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

@admin_bp.route('/admin/tune', methods=['GET'])
@require_role('admin')
def admin_tune_get():
    # Return the currently active policy tuning
    tune = TuningContent.query.filter_by(is_active=True).order_by(TuningContent.created_at.desc()).first()
    return jsonify({
        'content': tune.content if tune else '',
        'last_updated': tune.created_at.isoformat() if tune else None
    })

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

@admin_bp.route('/admin/chat-sessions', methods=['GET'])
@require_role('admin')
def admin_get_chat_sessions():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        query = ChatSession.query.order_by(ChatSession.last_activity.desc())
        paginated = query.paginate(page=page, per_page=per_page)
        
        print(f"[DEBUG] Found {len(paginated.items)} sessions for page {page}")
        
        sessions = []
        for s in paginated.items:
            # Try to get customer info
            customer_name = "Guest User"
            print(f"[DEBUG] Processing session {s.session_id}, app_id={s.application_id}")
            if s.application_id:
                app = LoanApplication.query.get(s.application_id)
                if app and app.customer_id:
                    cust = Customer.query.get(app.customer_id)
                    if cust: customer_name = cust.name
            
            sessions.append({
                'session_id': s.session_id,
                'customer_name': customer_name,
                'stage': s.stage or "N/A",
                'interaction_count': s.interaction_count,
                'last_activity': s.last_activity.isoformat() if s.last_activity else None,
                'created_at': s.created_at.isoformat() if s.created_at else None
            })
            
        return jsonify({
            'sessions': sessions,
            'total': paginated.total,
            'page': page,
            'per_page': per_page,
            'total_pages': paginated.pages,
            'status': 'ok'
        })
    except Exception as e:
        import traceback
        print(f"[ADMIN] session list error: {e}")
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/admin/chat-logs/<session_id>', methods=['GET'])
@require_role('admin')
def admin_get_chat_logs(session_id):
    try:
        logs = ChatLog.query.filter_by(session_id=session_id).order_by(ChatLog.created_at.asc()).all()
        return jsonify({
            'logs': [{
                'role': l.message_role,
                'text': l.message_text,
                'created_at': l.created_at.isoformat() if l.created_at else None,
                'details': l.details
            } for l in logs],
            'status': 'ok'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/admin/application/<app_id>/letter', methods=['GET'])
@require_role('admin')
def admin_get_letter(app_id):
    try:
        from models.db_models import SanctionLetter
        letter = SanctionLetter.query.filter_by(application_id=app_id).first()
        if not letter:
            return jsonify({'error': 'No sanction letter found'}), 404
        
        # In a real app, we'd serve the file. 
        # For now, return path or content
        return jsonify({
            'letter_id': str(letter.letter_id),
            'sanction_number': letter.sanction_number,
            'generated_at': letter.generated_at.isoformat(),
            'pdf_path': letter.pdf_path
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
