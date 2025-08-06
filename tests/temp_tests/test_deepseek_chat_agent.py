import asyncio
import os
import sys
import logging

# Ensure the project root is in the system path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from src.agent import (
    RoleAgent,
    BaseMessage,
    MessageType,
    GameStartPayload,
    ActionRequest
)

# Load environment variables from .env file
load_dotenv()

# --- Test Configuration ---
# Testing the standard deepseek-chat model as requested.
MODEL_TO_TEST = "deepseek/deepseek-chat"
TEST_PLAYER_ID = 0

async def test_deepseek_chat_agent():
    """
    A self-contained function to test the deepseek-chat agent.
    """
    print(f"--- Focused Test for: {MODEL_TO_TEST} ---")
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

    # 1. Instantiate the Agent
    agent = RoleAgent(player_id=TEST_PLAYER_ID, model_name=MODEL_TO_TEST)

    # 2. Simulate GAME_START
    game_start_payload = GameStartPayload(
        game_id=f"test_game_{MODEL_TO_TEST}",
        player_id=TEST_PLAYER_ID,
        role="Merlin",
        total_players=1,
        game_rules="This is a test of The Resistance: Avalon.",
        role_context="You are Merlin. You know who the minions are.",
        initial_personal_info={"known_info": "Player 3 is a Minion."}
    )
    start_message = BaseMessage(
        msg_type=MessageType.GAME_START,
        sender_id="GM_SIMULATOR",
        recipient_id=f"PLAYER_{TEST_PLAYER_ID}",
        payload=game_start_payload
    )
    await agent.receive_message(start_message)
    logging.info(f"Agent for {MODEL_TO_TEST} initialized.")

    # 3. Simulate ACTION_REQUEST
    action_request_payload = ActionRequest(
        action_type="PARTICIPATE_DISCUSSION",
        description="It is your turn to speak. What do you say?",
        available_options=[],
        constraints={},
        history_segment="This is the first turn of the game."
    )
    action_message = BaseMessage(
        msg_type=MessageType.ACTION_REQUEST,
        sender_id="GM_SIMULATOR",
        recipient_id=f"PLAYER_{TEST_PLAYER_ID}",
        payload=action_request_payload
    )

    # 4. Await and verify the agent's response
    response_message = await agent.receive_message(action_message)
    
    print("\n--- Test Result ---")
    if response_message and response_message.msg_type == MessageType.ACTION_RESPONSE:
        statement = response_message.payload.action_data.statement
        if "Error:" not in statement:
            print(f"✅ Model: {MODEL_TO_TEST}")
            print(f"   Response: '{statement[:150]}...'\n")
            print("\n✅ Test Passed: Agent connected and responded successfully.")
        else:
            print(f"❌ Model: {MODEL_TO_TEST}")
            print(f"   Response contained an error: {statement}")
            print("\n❌ Test Failed: Agent responded with an error.")
    else:
        print(f"❌ Model: {MODEL_TO_TEST}")
        print("\n❌ Test Failed: Did not receive a valid ACTION_RESPONSE from the agent.")


if __name__ == "__main__":
    asyncio.run(test_deepseek_chat_agent())
