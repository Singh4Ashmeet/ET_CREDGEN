import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from utils.database import db
from models.db_models import AdminUser
import os
from dotenv import load_dotenv

load_dotenv()

app = create_app()

def reset_admin():
    with app.app_context():
        username = os.getenv('SEED_ADMIN_USERNAME', 'admin')
        password = os.getenv('SEED_ADMIN_PASSWORD', 'admin@123')
        email = os.getenv('SEED_ADMIN_EMAIL', 'admin@credgen.in')

        admin = AdminUser.query.filter_by(username=username).first()
        if admin:
            print(f"Updating existing admin user: {username}")
            admin.set_password(password)
            admin.email = email
            admin.is_active = True
        else:
            print(f"Creating new admin user: {username}")
            admin = AdminUser(
                username=username,
                email=email,
                role='admin',
                is_active=True
            )
            admin.set_password(password)
            db.session.add(admin)
        
        db.session.commit()
        print("Admin user updated successfully.")

if __name__ == "__main__":
    reset_admin()
