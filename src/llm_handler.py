import os
import asyncio
import litellm
from openai import AsyncOpenAI
from typing import List, Dict, Optional

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
    # Models not in this list (anthropic, gemini, xai) will use the standard litellm call.
}

async def unified_llm_call(model_name: str, messages: List[Dict], timeout: int = 600) -> Optional[str]:
    """
    A centralized function to call any LLM, handling different provider conventions.
    Includes a retry mechanism for transient errors.
    Returns the content of the response or None if an error occurs after all retries.
    """
    provider = model_name.split('/')[0]
    max_retries = 3
    retry_delay = 30  # seconds

    for attempt in range(max_retries):
        try:
            if provider in MODEL_CONFIG:
                # --- Use OpenAI-compatible client ---
                config = MODEL_CONFIG[provider]
                api_key = os.getenv(config["api_key_env"])
                if not api_key:
                    print(f"Error: Environment variable {config['api_key_env']} not set for {model_name}.")
                    return None

                api_model_name = model_name.split('/')[-1]
                client = AsyncOpenAI(api_key=api_key, base_url=config["base_url"])
                
                response = await client.chat.completions.create(
                    model=api_model_name,
                    messages=messages,
                    timeout=timeout
                )
                return response.choices[0].message.content
            
            else:
                # --- Use standard litellm acompletion ---
                response = await litellm.acompletion(
                    model=model_name,
                    messages=messages,
                    timeout=timeout
                )
                return response.choices[0].message.content

        except Exception as e:
            print(f"LLM call to {model_name} failed on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                print("All retries failed.")
                return None
    return None # Should be unreachable, but as a fallback
