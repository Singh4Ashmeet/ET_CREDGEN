import sys
import os

# Add current directory to path so we can import agents
sys.path.append(os.path.abspath(os.curdir))

from agents.master_agent import MasterAgent, IntentType, ConversationStage


def test_chat():
    agent = MasterAgent()

    print(f"Current Stage: {agent.state['stage']}")

    while True:
        user_input = input("User: ")
        if user_input.lower() in ('exit', 'quit'):
            break

        print(f"\n[DEBUG] Input: {user_input}")

        # Manually extract entities and update state (simulating routes/chat_routes.py logic)
        extracted = agent.extract_entities_from_text(user_input)
        if extracted:
            print(f"[DEBUG] Extracted: {extracted}")
            agent.update_entities(extracted)
            agent.recalculate_missing_fields()

        response = agent.handle(user_input)

        print(f"Bot: {response.get('message')}")
        print(f"Stage: {agent.state['stage']}")
        print(f"Remaining: {agent.state.get('missing_fields')}")
        print("-" * 30)


if __name__ == "__main__":
    test_chat()
