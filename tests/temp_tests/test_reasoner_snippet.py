from litellm import completion
import os
from dotenv import load_dotenv

# Load environment variables from .env file, which sets DEEPSEEK_API_KEY
load_dotenv()

print("--- Testing deepseek/deepseek-reasoner with your snippet ---")

try:
    resp = completion(
        model="deepseek/deepseek-reasoner",
        messages=[{"role": "user", "content": "Tell me a joke."}]
    )

    # The user specifically asked for the 'reasoning_content' attribute.
    # We will try to access it, but add a check in case it doesn't exist.
    if hasattr(resp.choices[0].message, 'reasoning_content'):
        print("\n--- Reasoning Content ---")
        print(resp.choices[0].message.reasoning_content)
    else:
        print("\n--- Full Message Content (reasoning_content not found) ---")
        print(resp.choices[0].message.content)

except Exception as e:
    print(f"\n--- An error occurred ---")
    print(e)

