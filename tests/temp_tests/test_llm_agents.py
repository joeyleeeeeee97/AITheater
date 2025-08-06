import asyncio
import os
import sys
import logging
from typing import List

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
# A list of models to test concurrently.
# LiteLLM will use the corresponding environment variables for keys (e.g., OPENAI_API_KEY, GEMINI_API_KEY)
MODELS_TO_TEST = [
    "gpt-4-turbo",
    "gemini/gemini-1.5-pro-latest",
    "deepseek/deepseek-chat",
    "groq/llama3-8b-8192",
    "anthropic/claude-3-haiku-20240307" # Added Claude as another provider
]

async def test_single_agent(model_name: str, player_id: int):
    """
    A self-contained function to test a single agent with a specific model.
    Returns the model's response or an error message.
    """
    logging.info(f"[Test for {model_name}]: Starting...")
    
    # 1. Instantiate the Agent
    agent = RoleAgent(player_id=player_id, model_name=model_name)

    # 2. Simulate GAME_START
    game_start_payload = GameStartPayload(
        game_id=f"test_game_{model_name}",
        player_id=player_id,
        role="Merlin",
        total_players=len(MODELS_TO_TEST),
        game_rules="This is a test of The Resistance: Avalon.",
        role_context="You are Merlin. You know who the minions are.",
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
        recipient_id=f"PLAYER_{player_id}",
        payload=action_request_payload
    )

    # 4. Await and return the agent's response
    response_message = await agent.receive_message(action_message)
    
    if response_message and response_message.msg_type == MessageType.ACTION_RESPONSE:
        statement = response_message.payload.action_data.statement
        logging.info(f"[Test for {model_name}]: Received response.")
        return model_name, statement
    else:
        logging.error(f"[Test for {model_name}]: Failed to get a valid response.")
        return model_name, "Error: No valid response received."


async def main():
    """
    Runs connectivity tests for all specified LLM agents concurrently.
    """
    print("--- Independent LLM Agent Connectivity Test ---")
    print(f"Testing {len(MODELS_TO_TEST)} models concurrently...")
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

    # Create a list of concurrent tasks
    tasks = [test_single_agent(model, i) for i, model in enumerate(MODELS_TO_TEST)]
    
    # Run all tests in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    print("\n--- Test Results ---")
    all_passed = True
    for result in results:
        if isinstance(result, Exception):
            print(f"❌ A test failed with an exception: {result}")
            all_passed = False
        else:
            model_name, statement = result
            print(f"✅ Model: {model_name}")
            print(f"   Response: '{statement[:100]}...'") # Print first 100 chars
            if "Error:" in statement:
                all_passed = False

    print("\n--- Summary ---")
    if all_passed:
        print("✅ All agents connected to their respective LLMs and responded successfully.")
    else:
        print("❌ Some agents failed to connect or respond. Check the logs above for details.")


if __name__ == "__main__":
    # Check for required dependencies
    try:
        import litellm
        from dotenv import load_dotenv
    except ImportError as e:
        print(f"Missing dependency: {e.name}")
        print("Please ensure you have run './.venv/bin/pip install litellm python-dotenv'")
    else:
        # Add anthropic for the new test case
        try:
            import anthropic
        except ImportError:
            print("Claude model is in the test list. Please run './.venv/bin/pip install anthropic'")
        
        asyncio.run(main())
