import asyncio
import os
import sys
import json

# Ensure the src directory is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import RoleAgent, BaseMessage, MessageType, ActionRequest, GameStartPayload

# --- Configuration ---
ASSASSIN_ID = 2
MORGANA_ID = 5
MODEL = "gemini/gemini-2.5-pro" 

async def run_coordinated_quest_test():
    """
    Simulates a specific game scenario to test the coordinated quest execution logic
    for both the Assassin and Morgana.
    """
    print("--- Starting Coordinated Quest Logic Test ---")
    
    # --- Step 1: Load Context Files ---
    try:
        prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts')
        with open(os.path.join(prompt_path, 'rules.md'), 'r', encoding='utf-8') as f:
            game_rules = f.read()
        # Assassin prompts
        with open(os.path.join(prompt_path, 'roles', 'assassin.md'), 'r', encoding='utf-8') as f:
            assassin_role_context = f.read()
        with open(os.path.join(prompt_path, 'action', 'quest', 'assassin.md'), 'r', encoding='utf-8') as f:
            assassin_quest_prompt = f.read()
        # Morgana prompts
        with open(os.path.join(prompt_path, 'roles', 'morgana.md'), 'r', encoding='utf-8') as f:
            morgana_role_context = f.read()
        with open(os.path.join(prompt_path, 'action', 'quest', 'morgana.md'), 'r', encoding='utf-8') as f:
            morgana_quest_prompt = f.read()
    except FileNotFoundError as e:
        print(f"❌ ERROR: Could not load a required prompt file: {e}")
        return

    # --- Step 2: Initialize Agents ---
    try:
        assassin_agent = RoleAgent(player_id=ASSASSIN_ID, model_name=MODEL)
        morgana_agent = RoleAgent(player_id=MORGANA_ID, model_name=MODEL)
    except Exception as e:
        print(f"❌ ERROR: Failed to initialize RoleAgent. Is the API key for '{MODEL}' set in .env?")
        print(f"   Details: {e}")
        return

    # --- Step 3: Initialize Agents' Context in Parallel ---
    print("Initializing agents with GAME_START context...")
    
    assassin_start_payload = GameStartPayload(
        game_id="test_game_001", player_id=ASSASSIN_ID, role="Assassin", total_players=7,
        game_rules=game_rules, role_context=assassin_role_context,
        initial_personal_info={"known_info": f"You are a Minion of Mordred. Your fellow evil teammate is Player {MORGANA_ID} (Morgana)."}
    )
    morgana_start_payload = GameStartPayload(
        game_id="test_game_001", player_id=MORGANA_ID, role="Morgana", total_players=7,
        game_rules=game_rules, role_context=morgana_role_context,
        initial_personal_info={"known_info": f"You are a Minion of Mordred. Your fellow evil teammate is Player {ASSASSIN_ID} (Assassin)."}
    )

    await asyncio.gather(
        assassin_agent.receive_message(BaseMessage(msg_type=MessageType.GAME_START, sender_id="GM_TESTER", recipient_id=f"PLAYER_{ASSASSIN_ID}", payload=assassin_start_payload)),
        morgana_agent.receive_message(BaseMessage(msg_type=MessageType.GAME_START, sender_id="GM_TESTER", recipient_id=f"PLAYER_{MORGANA_ID}", payload=morgana_start_payload))
    )
    print("Agents' context initialized.")
    print("-" * 20)

    # --- Step 4: Send EXECUTE_QUEST Action Request to Both Agents ---
    print(f"Simulating scenario: Quest team is [Morgana ({MORGANA_ID}), Assassin ({ASSASSIN_ID})].")
    print("Quest requires 1 fail card.")
    print("Expected outcome: Assassin plays FAIL, Morgana plays SUCCESS.")
    print("-" * 20)

    constraints = {
        "team": [MORGANA_ID, ASSASSIN_ID],
        "evil_teammates_on_quest": [MORGANA_ID, ASSASSIN_ID],
        "fails_needed": 1
    }
    simulated_history = "[SYSTEM] Quest 1 Result: SUCCEEDED. Team was [0, 6]. Fail cards played: 0."

    assassin_action_payload = ActionRequest(action_type="EXECUTE_QUEST", description=assassin_quest_prompt, available_options=['success', 'fail'], constraints=constraints, history_segment=simulated_history)
    morgana_action_payload = ActionRequest(action_type="EXECUTE_QUEST", description=morgana_quest_prompt, available_options=['success', 'fail'], constraints=constraints, history_segment=simulated_history)

    assassin_msg = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM_TESTER", recipient_id=f"PLAYER_{ASSASSIN_ID}", payload=assassin_action_payload)
    morgana_msg = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM_TESTER", recipient_id=f"PLAYER_{MORGANA_ID}", payload=morgana_action_payload)

    assassin_response, morgana_response = await asyncio.gather(
        assassin_agent.receive_message(assassin_msg),
        morgana_agent.receive_message(morgana_msg)
    )

    # --- Step 5: Analyze and Report Results ---
    def get_action_and_reasoning(response):
        if response and response.payload and hasattr(response.payload, 'action_data'):
            return response.payload.action_data.action, response.payload.action_data.reasoning
        return "error", "N/A - LLM call likely failed"

    assassin_action, assassin_reasoning = get_action_and_reasoning(assassin_response)
    morgana_action, morgana_reasoning = get_action_and_reasoning(morgana_response)

    print(f"Assassin's chosen action: '{assassin_action}'")
    print(f"Assassin's stated reasoning: '{assassin_reasoning}'")
    print("-" * 10)
    print(f"Morgana's chosen action: '{morgana_action}'")
    print(f"Morgana's stated reasoning: '{morgana_reasoning}'")
    print("-" * 20)

    # --- Final Verdict ---
    assassin_pass = assassin_action == "fail"
    morgana_pass = morgana_action == "success"

    if assassin_pass and morgana_pass:
        print("✅✅✅ PASS: Both agents followed the coordination protocol correctly.")
    else:
        print("❌❌❌ FAIL: The coordination protocol was violated.")
        if not assassin_pass:
            print(f"  - FAIL: Assassin should have played 'fail' but played '{assassin_action}'.")
        if not morgana_pass:
            print(f"  - FAIL: Morgana should have played 'success' but played '{morgana_action}'.")

if __name__ == "__main__":
    asyncio.run(run_coordinated_quest_test())
