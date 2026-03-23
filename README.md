# ET_CREDGEN - AI Loan Assistant

ET_CREDGEN is an advanced AI-powered loan origination assistant. It guides users through the loan application process, including KYC verification, fraud checks, underwriting, and sanction letter generation.

## Features

- **Conversational Interface:** Natural language interaction powered by Gemini or OpenRouter.
- **Streaming Responses:** Real-time token streaming with typing indicators (SSE).
- **Session Persistence:** Resume applications across devices/sessions using phone number.
- **Async Workflow:** Non-blocking fraud checks and underwriting using background threads.
- **Document Upload:** Inline document upload with validation.
- **Tools:** Integrated EMI Calculator and smart input validation.
- **Admin Dashboard:** Comprehensive analytics, application management, and policy tuning.
- **Security:** JWT Authentication, Rate Limiting, Security Headers.

## Architecture

The backend is refactored into Flask Blueprints:
- `routes/chat_routes.py`: Chat logic, streaming, session management.
- `routes/workflow_routes.py`: Async agents (Fraud, Underwriting, Sales, Docs).
- `routes/admin_routes.py`: Admin analytics and management.
- `routes/document_routes.py`: File handling.
- `routes/status_routes.py`: Application status tracking.
- `routes/tools_routes.py`: Helper tools (EMI, Validation).

## Setup

1.  **Environment Variables:**
    Copy `.env.example` to `.env` and fill in the required keys.
    ```bash
    cp .env.example .env
    ```

2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the Application:**
    ```bash
    python app.py
    ```

4.  **Access the App:**
    -   Customer Chat: `http://localhost:5000/frontend/index.html`
    -   Status Tracker: `http://localhost:5000/frontend/status.html`
    -   Admin Panel: `http://localhost:5000/frontend/admin.html`

## Configuration

See `.env.example` for all configuration options, including API keys and feature toggles.

## License

MIT
