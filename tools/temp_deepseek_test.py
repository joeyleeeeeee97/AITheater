import asyncio
import litellm
import os
import logging

# Suppress verbose litellm logging for this test
logging.basicConfig(level=logging.WARNING) 
litellm.suppress_debug_info = True

async def test_deepseek():
    """Tests connectivity to the Deepseek model."""
    model_name = "deepseek/deepseek-reasoner" # Using the model name you provided
    print(f"--- Testing Deepseek Connectivity ---")
    print(f"Attempting to connect to: {model_name}")
    
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ FAILED: DEEPSEEK_API_KEY environment variable is not set.")
        return

    try:
        response = await litellm.acompletion(
            model=model_name,
            messages=[{"role": "user", "content": "hi, this is a test."}],
            timeout=30
        )
        if response.choices and response.choices[0].message.content:
            print("✅ SUCCESS: Received a valid response from the model.")
            print(f"Response: {response.choices[0].message.content}")
        else:
            print("❌ FAILED (Empty Response)")
            print(f"Full Response Object: {response}")
    except Exception as e:
        print(f"❌ FAILED: An error occurred.")
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_deepseek())
