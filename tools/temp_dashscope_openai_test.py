import os
from openai import OpenAI

print("--- Testing Dashscope API Key via OpenAI Client ---")

try:
    client = OpenAI(
        api_key="sk-564ad252fa6d442a961de833e28a900e",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    completion = client.chat.completions.create(
        model="qwen-plus",
        messages=[
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user', 'content': 'Who are you?'}
            ]
    )
    print("✅ SUCCESS: Received a valid response from the model.")
    print(f"Response: {completion.choices[0].message.content}")
except Exception as e:
    print(f"❌ FAILED: An error occurred.")
    print(f"Error Message: {e}")
