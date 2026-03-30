import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from utils.database import db
from models.db_models import Customer, LoanApplication, ChatLog, TuningContent, ChatSession
import csv
import json
from datetime import datetime

# Initialize app
app = create_app()

def migrate():
    with app.app_context():
        # CSV paths
        CSV_DIR = "csv"
        APPLICATIONS_CSV = os.path.join(CSV_DIR, "applications.csv")
        CHAT_LOGS_CSV = os.path.join(CSV_DIR, "chat_logs.csv")
        TUNING_CSV = os.path.join(CSV_DIR, "tuning_content.csv")

        try:
            # 1. Migrate Applications and Customers
            if os.path.exists(APPLICATIONS_CSV):
                print("Migrating applications...")
                with open(APPLICATIONS_CSV, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    row_count = 0
                    for row in reader:
                        phone = row.get('phone')
                        if not phone: continue
                        
                        customer = Customer.query.filter_by(phone=phone).first()
                        if not customer:
                            customer = Customer(
                                name=row.get('full_name', 'Unknown'),
                                phone=phone,
                                email=row.get('email')
                            )
                            db.session.add(customer)
                            db.session.flush()

                        # Check if session exists for application
                        session_id = row.get('session_id')
                        if session_id:
                            session = ChatSession.query.get(session_id)
                            if not session:
                                session = ChatSession(session_id=session_id)
                                db.session.add(session)
                                db.session.flush()

                        app_date = datetime.fromisoformat(row.get('timestamp')).date() if row.get('timestamp') else datetime.utcnow().date()
                        
                        application = LoanApplication(
                            customer_id=customer.customer_id,
                            loan_amount=float(row.get('loan_amount', 0)) if row.get('loan_amount') else 0,
                            city=row.get('city'),
                            status=row.get('status', 'initiated'),
                            rejection_reason=row.get('rejection_reason'),
                            application_date=app_date
                        )
                        db.session.add(application)
                        row_count += 1
                db.session.commit()
                print(f"Successfully migrated {row_count} applications.")
                os.rename(APPLICATIONS_CSV, APPLICATIONS_CSV + ".bak")

            # 2. Migrate Chat Logs
            if os.path.exists(CHAT_LOGS_CSV):
                print("Migrating chat logs...")
                with open(CHAT_LOGS_CSV, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    row_count = 0
                    for row in reader:
                        session_id = row.get('session_id')
                        if not session_id: continue

                        # Ensure session exists
                        session = ChatSession.query.get(session_id)
                        if not session:
                            session = ChatSession(session_id=session_id)
                            db.session.add(session)
                            db.session.flush()

                        details_raw = row.get('details', '{}')
                        try:
                             # Some CSVs escape JSON strings with extra quotes
                            if details_raw.startswith('"') and details_raw.endswith('"'):
                                details_raw = details_raw[1:-1].replace('""', '"')
                            details = json.loads(details_raw)
                        except:
                            details = {}

                        log = ChatLog(
                            session_id=session_id,
                            event_type=row.get('event_type'),
                            message_role=row.get('message_role'),
                            message_text=row.get('message_text'),
                            status=row.get('status'),
                            details=details,
                            created_at=datetime.fromisoformat(row.get('timestamp')) if row.get('timestamp') else datetime.utcnow()
                        )
                        db.session.add(log)
                        row_count += 1
                        if row_count % 50 == 0:
                            print(f"Adding row {row_count}...")

                db.session.commit()
                print(f"Successfully migrated {row_count} chat logs.")
                os.rename(CHAT_LOGS_CSV, CHAT_LOGS_CSV + ".bak")

            # 3. Migrate Tuning Content
            if os.path.exists(TUNING_CSV):
                print("Migrating tuning content...")
                with open(TUNING_CSV, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    row_count = 0
                    for row in reader:
                        content = TuningContent(
                            type='policy', # Default to policy
                            content=row.get('content', ''),
                            filename=row.get('filename'),
                            created_at=datetime.fromisoformat(row.get('timestamp')) if row.get('timestamp') else datetime.utcnow()
                        )
                        db.session.add(content)
                        row_count += 1
                db.session.commit()
                print(f"Successfully migrated {row_count} tuning records.")
                os.rename(TUNING_CSV, TUNING_CSV + ".bak")

            print("Migration completed successfully.")

        except Exception as e:
            db.session.rollback()
            print(f"Error during migration: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    migrate()
