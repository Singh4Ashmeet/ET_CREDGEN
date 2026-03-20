# CREDGEN AI – Loan Assistant Chatbot

**CREDGEN AI** is an intelligent, conversational system designed to streamline the loan application process for financial institutions. By leveraging advanced AI agents and natural language processing, CREDGEN AI handles everything from initial customer interaction to fraud detection, underwriting, and final document generation.

## 🚀 Key Features

*   **🤖 Conversational Loan Applications:** Guides users through the loan process using natural language, making it feel like chatting with a human agent.
*   **📄 Document Processing:** Intelligent parsing and analysis of uploaded documents (IDs, bank statements, income proofs).
*   **🛡️ Real-time Fraud Detection:** Automated risk analysis using ML models (PyOD) to instantly flag suspicious activities.
*   **⚡ Instant Underwriting:** Real-time credit scoring and risk assessment using XGBoost models to provide immediate preliminary decisions.
*   **💰 Dynamic Loan Offers:** Generates personalized loan terms, interest rates, and repayment plans based on the applicant's risk profile.
*   **📝 Automatic Document Generation:** Instantly creates official sanction letters and loan agreements (PDFs) upon offer acceptance.
*   **🧠 Flexible AI Engine:** Uses a "Master Agent" that can switch between **Google Gemini Pro** and **OpenRouter (Gemma 2)** for natural language understanding, while keeping deterministic logic for financial calculations.
*   **🏦 Bank Personalization:** Admins can "tune" the chatbot by describing their bank's specific services, offers, and policies, which are instantly injected into the AI's context.

## 🏗️ Architecture

The system is built on a **Multi-Agent Architecture** orchestrated by a central **Master Agent**:

1.  **Master Agent:** The brain of the system. Detects user intent and routes tasks to specialized workers.
2.  **AI/LLM Service:** Integration with **Google Gemini** and **OpenRouter**, allowing the system to use the best available LLM for conversation.
3.  **Underwriting Agent:** Analyzes financial data to compute risk scores and approval status.
4.  **Sales Agent:** Manages negotiations and generates tailored loan offers.
5.  **Fraud Agent:** Performs security checks and anomaly detection.
6.  **Documentation Agent:** Generates legal documents and PDFs.

## 🛠️ Tech Stack

*   **Backend:** Python 3.x, Flask
*   **AI/LLM:** Google Gemini Pro, OpenRouter (Gemma 2)
*   **Machine Learning:** Scikit-learn, XGBoost, PyOD
*   **NLP:** Sentence-Transformers, HuggingFace Transformers
*   **Data Processing:** Pandas, NumPy
*   **PDF Generation:** ReportLab
*   **Frontend:** HTML5, CSS3, JavaScript (Vanilla)

## 📋 Prerequisites

*   Python 3.9 or higher
*   Google Cloud API Key (for Gemini) OR OpenRouter API Key

## ⚙️ Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/merxzexv/CRED_GEN.git
    cd CRED_GEN
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    # Windows
    python -m venv venv
    venv\Scripts\activate

    # macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up Environment Variables:**
    Create a `.env` file in the root directory and add the following configuration:

    ```env
    # Flask Security
    APP_SECRET_KEY=your_super_secret_key_here

    # LLM Configuration
    LLM_PROVIDER="gemini"          # Options: "gemini" or "openrouter"
    LLM_SYSTEM_PROMPT="You are CredGen, a helpful loan assistant."
    LLM_MODE="enabled"             # Options: enabled, disabled, hybrid

    # API Keys (Fill at least one)
    GEMINI_API_KEY=your_google_gemini_key
    OPENROUTER_API_KEY=your_openrouter_key
    ```

## 🚀 Usage

1.  **Start the Flask development server:**
    ```bash
    python app.py
    ```

2.  **Access the application:**
    Open your browser and navigate to:
    *   **Main App:** `http://localhost:5000`
    *   **Chat Widget Demo:** `http://localhost:5000/widget.html`

## 📂 Project Structure

```
credgen_last/
├── agents/             # Core logic for specialized agents (Sales, Underwriting, Fraud, etc.)
├── csv/                # File-based database for applications, logs, and users
├── data/               # Raw data and ML model artifacts
├── frontend/           # Static frontend files (HTML, CSS, JS)
├── models/             # ML model definitions and Gemini service wrapper
├── utils/              # Helper utilities (PDF generation, etc.)
├── uploads/            # Directory for user-uploaded documents
├── app.py              # Main Flask application entry point
├── requirements.txt    # Python dependencies
└── README.md           # Project documentation
```

## 🔌 Integration

To embed the CREDGEN AI bot on any website, simply add the following script before the closing `</body>` tag:

```html
<script src="https://your-domain.com/frontend/widget-ui.js"></script>
<script src="https://your-domain.com/frontend/chat.js"></script>
```

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
