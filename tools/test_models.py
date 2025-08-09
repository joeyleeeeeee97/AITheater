import asyncio
import yaml
import litellm
import os
import logging
from openai import AsyncOpenAI

# Suppress verbose litellm logging for this test
logging.basicConfig(level=logging.WARNING) 
litellm.suppress_debug_info = True

# --- Model-specific configurations for OpenAI-compatible endpoints ---
MODEL_CONFIG = {
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY"
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "api_key_env": "MOONSHOT_API_KEY"
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY"
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY"
    }
    # Anthropic and Gemini do not have standard OpenAI-compatible endpoints,
    # so they will be tested via the standard litellm method.
}

async def test_model_litellm(model_name: str):
    """Sends a simple test message to a model using standard litellm."""
    print(f"Testing model (litellm): {model_name} ... ", end="", flush=True)
    try:
        response = await litellm.acompletion(
            model=model_name,
            messages=[{"role": "user", "content": "hi"}],
            timeout=30
        )
        if response.choices and response.choices[0].message.content:
            print("✅ SUCCESS")
            return True
        else:
            print("❌ FAILED (Empty Response)")
            return False
    except Exception as e:
        print(f"❌ FAILED\n   Error: {e}")
        return False

async def test_model_openai_client(model_name: str, config: dict):
    """Sends a test message using an OpenAI-compatible client."""
    print(f"Testing model (OpenAI client): {model_name} ... ", end="", flush=True)
    api_key = os.getenv(config["api_key_env"])
    if not api_key:
        print(f"❌ FAILED\n   Error: Environment variable {config['api_key_env']} not set.")
        return False
        
    try:
        # The model name for the API call is the part after the '/'
        api_model_name = model_name.split('/')[-1]

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=config["base_url"],
        )
        response = await client.chat.completions.create(
            model=api_model_name,
            messages=[{'role': 'user', 'content': 'hi'}],
            timeout=30
        )
        if response.choices and response.choices[0].message.content:
            print("✅ SUCCESS")
            return True
        else:
            print("❌ FAILED (Empty Response)")
            return False
    except Exception as e:
        print(f"❌ FAILED\n   Error: {e}")
        return False

async def main():
    """Main function to read config and test all models."""
    config_path = "config.yaml"
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found.")
        return

    print("--- Starting Model Connectivity Test ---")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    player_setup = config.get("player_setup", [])
    if not player_setup:
        print("No players found in config.yaml under 'player_setup'.")
        return
        
    model_names = sorted(list(set(player.get("model") for player in player_setup if player.get("model"))))
    
    if not model_names:
        print("No model names found in the player setup.")
        return

    print(f"Found {len(model_names)} unique models to test: {model_names}\n")
    
    tasks = []
    for model in model_names:
        provider = model.split('/')[0]
        if provider in MODEL_CONFIG:
            tasks.append(test_model_openai_client(model, MODEL_CONFIG[provider]))
        else:
            tasks.append(test_model_litellm(model))
            
    results = await asyncio.gather(*tasks)
    
    print("\n--- Test Summary ---")
    for model, success in zip(model_names, results):
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"- {model}: {status}")
        
    if all(results):
        print("\nAll models are configured correctly!")
    else:
        print("\nSome models failed the connectivity test. Please check your API keys and model names in the environment variables and config.yaml.")

if __name__ == "__main__":
    asyncio.run(main())
