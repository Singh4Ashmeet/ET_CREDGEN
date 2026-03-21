# ET_CREDGEN — AI-Powered Loan Assistant

ET_CREDGEN is a complete, AI-driven loan processing system with a conversational frontend, multi-agent backend, and a secure PostgreSQL data layer.

## 🚀 Quick Start (Automated Setup)

Running the application now automatically initializes your database tables and seeds the default admin account.

1.  **Clone & Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Environment Configuration**:
    Copy `.env.example` to `.env` and fill in your credentials.
    ```bash
    cp .env.example .env
    ```
    *Note: Ensure `DATABASE_URL` points to an existing PostgreSQL database (e.g., `postgresql://user:pass@localhost:5432/credgen`).*

3.  **Run the App**:
    ```bash
    python app.py
    ```
    On startup, the system will:
    - Create all necessary PostgreSQL tables.
    - Create the default admin account using your `SEED_ADMIN_*` environment variables.

## 🔐 Security Features

- **JWT Authentication**: Secure admin access with access/refresh token rotation.
- **Security Hardening**: Flask-Talisman enforced CSP, HSTS, and XSS protection.
- **Password Safety**: High-entropy PBKDF2 hashing for all admin credentials.
- **Rate Limiting**: Protection against brute-force attacks on login endpoints.

## 🛠️ Components

- **Frontend**: Conversational UI (HTML/JS) and Admin Dashboard.
- **Agents**: Master, Fraud, Underwriting, Sales, and Documentation agents.
- **Data Layer**: PostgreSQL with SQLAlchemy ORM and Marshmallow validation.
- **LLM Services**: Integrated with Gemini and OpenRouter.

## 📊 Administration

- **Login**: `/auth/login` (POST) to get your JWT.
- **Dashboard**: Access protected administrative routes using your JWT.
- **Tuning**: Dynamically update system prompts and policies via the Tuning API.

## 📂 Project Structure

- `app.py`: Main Flask application with automated setup.
- `models.py`: Database schema and ORM definitions.
- `auth.py`: JWT authentication blueprint.
- `validators.py`: Data integrity and validation schemas.
- `agents/`: Intelligent agent logic (Master, Fraud, etc.).
- `database.py`: Database connection and pooling configuration.

---
*For manual migrations or legacy data imports, refer to [MIGRATIONS.md](MIGRATIONS.md).*
