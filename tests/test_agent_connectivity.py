import asyncio
import os
import sys
import logging
from typing import List

# Ensure the project root is in the system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
# A list of models to test. This can be updated as needed.
# LiteLLM will use the corresponding environment variables for keys.
MODELS_TO_TEST = [
    "gpt-4-turbo",
    "gemini/gemini-1.5-pro-latest",
    "anthropic/claude-3-haiku-20240307",
    "xai/grok-4-latest",
    "deepseek/deepseek-chat",
]

async def test_single_agent(model_name: str, player_id: int):
    """
    A self-contained function to test a single agent with a specific model.
    Returns the model's response or an error message.
    """
    logging.info(f"[Test for {model_name}]: Starting...")
    
    try:
        agent = RoleAgent(player_id=player_id, model_name=model_name)

        game_start_payload = GameStartPayload(
            game_id=f"test_game_{model_name}",
            player_id=player_id,
            role="Merlin",
            total_players=len(MODELS_TO_TEST),
            game_rules="This is a test of The Resistance: Avalon.",
            role_context="You are Merlin.",
            initial_personal_info={"known_info": "Player 3 is a Minion."}
        )
        start_message = BaseMessage(
            msg_type=MessageType.GAME_START,
            sender_id="GM_SIMULATOR",
            recipient_id=f"PLAYER_{player_id}",
            payload=game_start_payload
        )
        await agent.receive_message(start_message)
        logging.info(f"[Test for {model_name}]: Agent initialized.")

        action_request_payload = ActionRequest(
            action_type="PARTICIPATE_DISCUSSION",
            description="It is your turn to speak.",
            available_options=[],
            constraints={},
            history_segment="This is the first turn of the game."
        )
        action_message = BaseMessage(
            msg_type=MessageType.ACTION_REQUEST,
            sender_id="GM_SIMULATOR",
            recipient_id=f"PLAYER_{player_id}",
            payload=action_request_payload
        )

        response_message = await agent.receive_message(action_message)
        
        if response_message and response_message.msg_type == MessageType.ACTION_RESPONSE:
            statement = response_message.payload.action_data.statement
            logging.info(f"[Test for {model_name}]: Received response.")
            return model_name, statement
        else:
            logging.error(f"[Test for {model_name}]: Failed to get a valid response.")
            return model_name, "Error: No valid response received."
    except Exception as e:
        logging.error(f"[Test for {model_name}]: An exception occurred: {e}", exc_info=True)
        return model_name, f"Error: An exception occurred - {e}"


async def main():
    """
    Runs connectivity tests for all specified LLM agents concurrently.
    """
    print("--- LLM Agent Connectivity Test ---")
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

    tasks = [test_single_agent(model, i) for i, model in enumerate(MODELS_TO_TEST)]
    results = await asyncio.gather(*tasks)
    
    print("\n--- Test Results ---")
    all_passed = True
    for model_name, statement in results:
        is_error = "Error:" in statement
        if is_error:
            all_passed = False
            print(f"❌ Model: {model_name}")
            print(f"   Response: {statement}")
        else:
            print(f"✅ Model: {model_name}")
            print(f"   Response: '{statement[:100].strip()}...'")

    print("\n--- Summary ---")
    if all_passed:
        print("✅ All agents connected and responded successfully.")
    else:
        print("❌ Some agents failed to connect or respond. Check the logs above for details.")


if __name__ == "__main__":
    asyncio.run(main())
