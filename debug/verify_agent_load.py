import sys
import os
import contextlib

# Add project root to sys.path
# This ensures we can import agents, models, utils from anywhere
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Force UTF-8 encoding for Windows terminals
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

@contextlib.contextmanager
def suppress_output():
    """Context manager to suppress stdout and stderr to keep the report clean."""
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

def verify_agents():
    print(f"\nVerifying Agents in Project: {os.path.basename(project_root)}\n")
    print("="*60)
    
    results = []

    # --- 1. Master Agent Check ---
    try:
        with suppress_output():
            from agents.master_agent import MasterAgent
            master = MasterAgent()
        
        if master.intent_model is not None:
             results.append("[PASS] Master Agent loaded successfully")
        else:
             results.append("[FAIL] Master Agent loaded but Model missing (using rule-based fallback)")
    except ImportError as e:
        results.append(f"[FAIL] Master Agent Import Error: {e}")
    except Exception as e:
        results.append(f"[FAIL] Master Agent Initialization Error: {e}")

    # --- 2. Fraud Agent Check ---
    try:
        with suppress_output():
            from agents.fraud_agent import FraudAgent
            fraud = FraudAgent()
        
        if fraud.pipeline is not None and fraud.model_loaded:
             results.append("[PASS] Fraud Agent loaded successfully (LOF Model active)")
        else:
             results.append("[FAIL] Fraud Agent loaded but LOF Model missing (using rule-based only)")
    except Exception as e:
        results.append(f"[FAIL] Fraud Agent Initialization Error: {e}")

    # --- 3. Underwriting Agent Check ---
    try:
        with suppress_output():
            from agents.underwriting_agent import UnderwritingAgent
            underwriting = UnderwritingAgent()
        
        model_type = "Unknown"
        if hasattr(underwriting, 'model'):
             model_type = type(underwriting.model).__name__

        if model_type != 'MockModel':
             results.append(f"[PASS] Underwriting Agent loaded successfully (Model: {model_type})")
        else:
             results.append(f"[FAIL] Underwriting Agent using Fallback Mock Model (Type: {model_type})")
    except Exception as e:
        results.append(f"[FAIL] Underwriting Agent Initialization Error: {e}")

    # --- 4. Gemini Service Check ---
    try:
        with suppress_output():
            from models.gemini_service import GeminiService
            gemini = GeminiService()
        
        api_key = os.getenv("GEMINI_API_KEY")
        if gemini.is_available():
             results.append(f"[PASS] Gemini Service configured and ready")
        else:
             status = "Missing or Invalid API Key" if not api_key else "API Key present but service unavailable"
             results.append(f"[FAIL] Gemini Service not available: {status}")
    except Exception as e:
         results.append(f"[FAIL] Gemini Service Initialization Error: {e}")

    # --- Print Final Report ---
    for res in results:
        print(res)
    print("="*60 + "\n")

if __name__ == "__main__":
    verify_agents()
