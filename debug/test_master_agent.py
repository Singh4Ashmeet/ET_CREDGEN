import sys
import os
import json
import logging

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Force UTF-8 for Windows console
sys.stdout.reconfigure(encoding='utf-8')

# Import Agents using new structure
from agents.master_agent import MasterAgent, ConversationStage
from agents.underwriting_agent import UnderwritingAgent
from agents.sales_agent import SalesAgent
from agents.fraud_agent import FraudAgent

# Configure logging
logging.basicConfig(level=logging.ERROR)

def print_state_change(old_state, new_state):
    """Prints only what changed in the state."""
    changes = []
    
    # Check stage change
    if old_state.get('stage') != new_state.get('stage'):
        try:
            # Handle Enum if present
            s1 = old_state.get('stage').value if hasattr(old_state.get('stage'), 'value') else old_state.get('stage')
            s2 = new_state.get('stage').value if hasattr(new_state.get('stage'), 'value') else new_state.get('stage')
            changes.append(f"Stage: {s1} -> {s2}")
        except:
             changes.append(f"Stage: {old_state.get('stage')} -> {new_state.get('stage')}")

    # Check entity changes
    old_ents = old_state.get('entities', {})
    new_ents = new_state.get('entities', {})
    for k, v in new_ents.items():
        if v and v != old_ents.get(k):
             changes.append(f"Entity Captured [{k}]: {v}")

    if changes:
        print("\n[SYSTEM STATE UPDATE]")
        for change in changes:
            print(f"  > {change}")

def main():
    print("="*60)
    print("CREDGEN LOAN BOT - CONSOLE DEBUG MODE")
    print("="*60)
    print("Simulates full conversation flow with all agents active.")
    print("Type 'exit' to quit.\n")

    # Initialize Agents
    print("[INIT] Initializing Agents...")
    try:
        master = MasterAgent()
        uw = UnderwritingAgent()
        sales = SalesAgent()
        fraud = FraudAgent()
        print("[INIT] All Agents Loaded Successfully.\n")
    except Exception as e:
        print(f"[CRITICAL ERROR] Failed to load agents: {e}")
        return

    # Helper to track state changes
    import copy
    last_state = copy.deepcopy(master.state)

    while True:
        try:
            user_input = input("\nUser: ").strip()
        except EOFError:
            break
            
        if user_input.lower() in {"exit", "quit"}:
            print("Exiting test...")
            break

        if not user_input:
            continue

        print("-" * 60)
        
        # 1. Master Agent Handling
        response = master.handle(user_input)
        
        # Display Core Bot Response
        print(f"CredGen Bot: {response.get('message')}")

        # Show Intent
        print(f"\n[ORCHESTRATION]")
        print(f"  > Intent Detected: {response.get('intent')} (Confidence: {response.get('confidence', 0):.2f})")
        
        worker = response.get("worker")
        print(f"  > Routing: {worker}")

        # Detect and Print State Changes
        current_state = copy.deepcopy(master.state)
        print_state_change(last_state, current_state)
        last_state = current_state

        # 2. Worker Agent Logic Simulation (Mimicking app.py orchestration)
        
        # --- FRAUD CHECK ---
        if worker == "fraud":
            print("\n[WORKER: FRAUD AGENT]")
            print("  > Triggered: Performing document and identity verification...")
            
            fraud_result = fraud.perform_fraud_check(master.state["entities"])
            
            print(f"  > Analysis: Fraud Score = {fraud_result['fraud_score']}, Flag = {fraud_result['fraud_flag']}")
            if fraud_result.get('ml_result'):
                print(f"  > ML Model: Anomaly Score = {fraud_result['ml_result'].get('anomaly_score', 0):.4f}")
            
            # Update Master State
            master.set_fraud_result(
                fraud_score=fraud_result["fraud_score"],
                fraud_flag=fraud_result["fraud_flag"],
            )
            print("  > Action: Updated Master State with Fraud Result.")

        # --- UNDERWRITING ---
        if worker == "underwriting":
            print("\n[WORKER: UNDERWRITING AGENT]")
            print("  > Triggered: Assessing creditworthiness...")
            
            # Pass fraud score if available, else 0
            fraud_score = 0
            # If we had a previous fraud check, we could grab it, but typically UW runs after/independently
            
            uw_result = uw.perform_underwriting(master.state["entities"])
            
            status = "APPROVED" if uw_result["approval_status"] else "REJECTED"
            print(f"  > Decision: {status}")
            print(f"  > Risk Score: {uw_result.get('risk_score')}")
            print(f"  > Reason: {uw_result.get('reason')}")
            
            if uw_result["approval_status"]:
                 print(f"  > Interest Rate: {uw_result.get('interest_rate')}%")

            # Update Master State
            master.set_underwriting_result(
                risk_score=uw_result["risk_score"],
                approval_status=uw_result["approval_status"],
                interest_rate=uw_result.get("interest_rate"),
            )
            print("  > Action: Updated Master State with Underwriting Decision.")

        # --- SALES / OFFERS ---
        if worker == "sales":
            print("\n[WORKER: SALES AGENT]")
            print("  > Triggered: Generating/Negotiating Offer...")
            
            is_negotiation = response.get('intent') == 'negotiate_terms'
            
            offer = sales.generate_offer(
                master_agent_state=master.state,
                negotiation_request=is_negotiation
            )
            
            print(f"  > Offer Generated: {offer.get('message')}")
            
            # Update Master State
            master.set_offer(offer)
            print("  > Action: Offer presented to user.")

        # --- DOCUMENTATION ---
        if worker == "documentation":
             print("\n[WORKER: DOCS AGENT]")
             print("  > Triggered: Generating Sanction Letter PDFs...")
             # In a real app we'd call the PDF generator here
             print("  > Action: [SIMULATED] PDF generated and sent to user.")

        print("-" * 60)

if __name__ == "__main__":
    main()
