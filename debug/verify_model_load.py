import sys
import os
import io
import contextlib

# Force UTF-8
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Add current directory to path
sys.path.append(os.getcwd())

@contextlib.contextmanager
def suppress_output():
    """Suppress stdout and stderr."""
    with open(os.devnull, 'w', encoding='utf-8') as fnull:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = fnull
        sys.stderr = fnull
        try:
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

def check_agents():
    results = []

    # --- 1. Master Agent Check ---
    try:
        with suppress_output():
            from agents.master_agent import MasterAgent
            master = MasterAgent()
        
        if master.intent_model is not None:
             results.append("[PASS] Master Agent loaded")
        else:
             results.append("[FAIL] Master Agent model missing — using rule-based fallback")
    except ImportError as e:
        results.append(f"[FAIL] Master Agent import error: {e}")
    except Exception as e:
        results.append(f"[FAIL] Master Agent initialization error: {e}")

    # --- 2. Fraud Detection Check ---
    try:
        with suppress_output():
            from agents.fraud_agent import FraudAgent
            fraud = FraudAgent()
        
        if fraud.pipeline is not None and fraud.model_loaded:
             results.append("[PASS] Fraud Agent loaded")
        else:
             results.append("[FAIL] Fraud Agent model missing — using rule-based only")
    except Exception as e:
        results.append(f"[FAIL] Fraud Agent initialization error: {e}")

    # --- 3. Underwriting Agent Check ---
    try:
        with suppress_output():
            from agents.underwriting_agent import UnderwritingAgent
            underwriting = UnderwritingAgent()
        
        model_type = "Unknown"
        if hasattr(underwriting, 'model'):
             model_type = type(underwriting.model).__name__

        if model_type != 'MockModel':
             results.append(f"[PASS] Underwriting Agent loaded (Model: {model_type})")
        else:
             results.append(f"[FAIL] Underwriting Agent model missing — using rule-based fallback (Type: {model_type})")
    except Exception as e:
        results.append(f"[FAIL] Underwriting Agent initialization error: {e}")

    # --- 4. Gemini Service Check ---
    try:
        with suppress_output():
            from models.gemini_service import GeminiService
            gemini = GeminiService()
        
        api_key = os.getenv("GEMINI_API_KEY")
        if gemini.is_available():
             results.append(f"[PASS] Gemini Service loaded (API Key Present)")
        else:
             results.append(f"[FAIL] Gemini Service not configured — API Key {'Present' if api_key else 'Missing'} or invalid")
    except Exception as e:
         results.append(f"[FAIL] Gemini Service initialization error: {e}")

    # --- Print Clean Report ---
    print("\nStarting System Component Verification...\n")
    print("="*60)
    for res in results:
        print(res)
    print("="*60 + "\n")

if __name__ == "__main__":
    check_agents()
