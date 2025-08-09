import os
from litellm import completion
import asyncio

async def test_dashscope():
    print("--- Testing Dashscope API Key ---")
    try:
        os.environ['DASHSCOPE_API_KEY'] = "sk-564ad252fa6d442a961de833e28a900e"
        response = await asyncio.to_thread(
            completion,
            model="dashscope/qwen-turbo", 
            messages=[
               {"role": "user", "content": "hello from litellm"}
           ],
            stream=False  # Use False for a single response object
        )
        if response.choices and response.choices[0].message.content:
            print("✅ SUCCESS: Received a valid response from the model.")
            print(f"Response: {response.choices[0].message.content}")
        else:
            print("❌ FAILED: Received an empty or invalid response.")
            print(f"Full Response Object: {response}")

    except Exception as e:
        print(f"❌ FAILED: An error occurred.")
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_dashscope())
