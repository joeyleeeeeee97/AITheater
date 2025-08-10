import os
import json
import logging
import google.generativeai as genai
import re
import asyncio
import sys
import argparse
from typing import List, Dict, Any

# --- Logging Setup ---
plain_formatter = logging.Formatter('%(message)s')
debug_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
script_logger = logging.getLogger("script_flow")
script_logger.setLevel(logging.INFO)
script_logger.propagate = False
if not script_logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(plain_formatter)
    script_logger.addHandler(console_handler)
debug_logger = logging.getLogger("debug")
debug_logger.setLevel(logging.DEBUG)
debug_logger.propagate = False
if not debug_logger.handlers:
    debug_file_handler = logging.FileHandler('script_writer_debug.log', mode='w')
    debug_file_handler.setFormatter(debug_formatter)
    debug_logger.addHandler(debug_file_handler)
# --- End Logging Setup ---

async def structure_chunk_with_llm(chunk: str, protocol: str, model: genai.GenerativeModel) -> List[Dict[str, Any]]:
    """
    Uses LLM to structure a chunk based on the provided, explicit protocol.
    """
    prompt = f"""
You are a data transformation AI. Your only job is to convert the following raw text log chunk into a structured JSON array based on the provided protocol.

**JSON SCRIPTING PROTOCOL:**
---
{protocol}
---

**CRITICAL RULES:**
1.  You **MUST** strictly adhere to the JSON structure defined in the protocol.
2.  For any event initiated by a player (like PLAYER_SPEECH, TEAM_PROPOSAL, LEADER_DECISION), you **MUST** extract the `player_id` from the text (e.g., "Player 3 says...") and include it in the JSON object.
3.  Copy all speeches, narrator lines, and reasoning text into the `content` field **VERBATIM**.

**GAME LOG CHUNK TO STRUCTURE:**
---
{chunk}
---

**OUTPUT:**
Produce only the validated JSON array.
""".strip()

    try:
        response = await model.generate_content_async(prompt)
        script_text = "".join(part.text for part in response.parts)
        if script_text.strip().startswith("```json"):
            script_text = script_text.strip()[7:-3].strip()
        return json.loads(script_text)
    except Exception as e:
        debug_logger.error(f"Failed to STRUCTURE chunk: {chunk[:100]}... Error: {e}")
        return []

async def create_script_from_log(log_file_path: str, output_file_path: str, protocol_path: str):
    script_logger.info(f"Starting script generation from log file: {log_file_path}")
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            game_log = f.read()
        with open(protocol_path, 'r', encoding='utf-8') as f:
            protocol = f.read()
    except FileNotFoundError as e:
        script_logger.error(f"File not found: {e.filename}")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        script_logger.error("GEMINI_API_KEY environment variable not set.")
        return
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-2.5-flash')

    delimiters = r"(?=--- Starting Quest|--- Team Building Attempt|--- Team Discussion|--- Leader's Final Decision|--- The Final Assassination|--- MVP Selection ---)"
    chunks = re.split(delimiters, game_log)
    
    final_script = []
    script_logger.info(f"Log split into {len(chunks)} chunks for processing.")

    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        
        script_logger.info(f"--- Processing Chunk {i+1}/{len(chunks)} ---")
        
        structured_events = await structure_chunk_with_llm(chunk, protocol, model)
        
        if not structured_events:
            continue
        
        final_script.extend(structured_events)

    script_logger.info(f"Successfully processed all chunks. Total events: {len(final_script)}")

    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(final_script, f, indent=2, ensure_ascii=False)
    script_logger.info(f"Successfully generated and saved the final script to: {output_file_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert a game log to a structured JSON script using an LLM.")
    parser.add_argument("log_file", help="Path to the input game log file.")
    parser.add_argument("output_file", help="Path for the output JSON script file.")
    parser.add_argument("--protocol", default="prompts/script_protocol.md", help="Path to the script protocol definition file.")
    args = parser.parse_args()
    asyncio.run(create_script_from_log(args.log_file, args.output_file, args.protocol))
