import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

def audit_supabase():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("Error: DATABASE_URL not found in .env file.")
        return

    # Ensure the protocol is correct for psycopg2/SQLAlchemy
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # Query to list all tables in the public schema
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        tables = [t[0] for t in cur.fetchall()]
        
        if not tables:
            print("No tables found in the Supabase public schema.")
            return

        print(f"{'Table Name':<30} | {'Row Count':<10}")
        print("-" * 43)
        
        total_records = 0
        for table in tables:
            cur.execute(f"SELECT count(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"{table:<30} | {count:<10}")
            total_records += count
            
        print("-" * 43)
        print(f"{'TOTAL RECORDS':<30} | {total_records:<10}")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error connecting to Supabase: {e}")

if __name__ == "__main__":
    audit_supabase()
