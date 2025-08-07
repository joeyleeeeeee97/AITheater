import os
import json
import logging
import google.generativeai as genai
import re
import asyncio
import sys

# --- Logging Setup ---
# Plain formatter for console
plain_formatter = logging.Formatter('%(message)s')
# Detailed formatter for debug log
debug_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')

# Logger for user-facing info (console)
script_logger = logging.getLogger("script_flow")
script_logger.setLevel(logging.INFO)
script_logger.propagate = False
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(plain_formatter)
script_logger.addHandler(console_handler)

# Logger for detailed debug messages
debug_logger = logging.getLogger("debug")
debug_logger.setLevel(logging.DEBUG)
debug_logger.propagate = False
debug_file_handler = logging.FileHandler('script_writer_debug.log', mode='w')
debug_file_handler.setFormatter(debug_formatter)
debug_logger.addHandler(debug_file_handler)
# --- End Logging Setup ---

def split_log_into_chunks(game_log: str) -> list[str]:
    """Splits the game log into logical chunks based on game phases."""
    # Regex to split by major phase markers
    # The (?=...) is a positive lookahead to keep the delimiter at the start of the next chunk
    delimiters = r"(?=(?:--- Starting Quest|--- Vote Results|--- Quest Results|--- The Final Assassination|--- Post-Game ---))"
    chunks = re.split(delimiters, game_log)
    # Filter out any empty strings that might result from the split
    return [chunk.strip() for chunk in chunks if chunk.strip()]

async def process_chunk(chunk: str, model: genai.GenerativeModel, chunk_index: int, protocol: str) -> list:
    """Sends a single chunk to the LLM and returns the parsed JSON."""
    debug_logger.info(f"--- Processing Chunk {chunk_index} ---")
    
    prompt = f"""
You are a professional screenwriter and audio drama director. Your task is to convert a raw text log from a game of "The Resistance: Avalon" into a structured JSON script. You MUST adhere strictly to the JSON protocol provided.

**JSON SCRIPTING PROTOCOL:**
---
{protocol}
---

**ADDITIONAL INSTRUCTIONS:**

1.  **Analyze the Log Chunk:** Read the provided game log chunk and identify all distinct events.
2.  **Track State:** Keep track of the `current_leader`, `proposed_team`, and the cumulative `quest_dashboard_state` as you process the log.
3.  **Generate JSON:** For each event, create a JSON object that strictly follows the protocol. Ensure `game_state` and `quest_dashboard_state` are present and accurate for **every single event**.
4.  **Create Narrative:** Write compelling, narrative `content` for a voice actor, adding parenthetical performance notes like `(dramatically)` or `(triumphantly)`.
5.  **Summarize:** Write a concise `summary` for each event.

Your entire output for the chunk must be a single, valid JSON array of event objects.

**GAME LOG CHUNK TO ADAPT:**
---
{chunk}
---
""".strip()
    debug_logger.debug(f"REQUEST PAYLOAD for Chunk {chunk_index}:\n{prompt}")

    try:
        response = await model.generate_content_async(prompt)
        script_text = "".join(part.text for part in response.parts)
        debug_logger.debug(f"RAW RESPONSE for Chunk {chunk_index}:\n{script_text}")
        
        if script_text.strip().startswith("```json"):
            script_text = script_text.strip()[7:-3].strip()
            
        parsed_json = json.loads(script_text)
        debug_logger.info(f"Successfully parsed response for Chunk {chunk_index}. Found {len(parsed_json)} events.")
        return parsed_json
    except Exception as e:
        debug_logger.error(f"Failed to process chunk: {chunk[:100]}... Error: {e}")
        return [] # Return an empty list for the failed chunk


async def create_script_from_log(log_file_path: str, output_file_path: str, protocol_path: str):
    """
    Reads a raw game log, splits it into chunks, processes them in parallel,
    and saves the resulting structured JSON script.
    """
    script_logger.info(f"Starting script generation from log file: {log_file_path}")

    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            game_log = f.read()
        with open(protocol_path, 'r', encoding='utf-8') as f:
            protocol = f.read()
    except FileNotFoundError as e:
        script_logger.error(f"File not found: {e.filename}")
        return

    # Validate that the log file is complete before proceeding
    if "--- Post-Game ---" not in game_log:
        script_logger.error("Log file appears to be incomplete. Missing '--- Post-Game ---' marker. Aborting script generation.")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        script_logger.error("GEMINI_API_KEY environment variable not set.")
        return
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-1.5-pro-latest')

    chunks = split_log_into_chunks(game_log)
    debug_logger.info(f"Log split into {len(chunks)} chunks.")

    tasks = [process_chunk(chunk, model, i, protocol) for i, chunk in enumerate(chunks)]
    results = await asyncio.gather(*tasks)
    
    final_script = [item for sublist in results for item in sublist] # Flatten the list of lists
    
    debug_logger.info(f"Successfully processed all chunks. Total events: {len(final_script)}")

    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(final_script, f, indent=2)
    script_logger.info(f"Successfully generated and saved the final script to: {output_file_path}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Convert a game log to a structured JSON script using an LLM.")
    parser.add_argument("log_file", help="Path to the input game log file (inside outputs/ dir).", nargs='?')
    parser.add_argument("output_file", help="Path for the output JSON script file (inside outputs/ dir).", nargs='?')
    parser.add_argument("--protocol", default="prompts/script_protocol.md", help="Path to the script protocol definition file.")
    args = parser.parse_args()

    # Handle absolute vs. relative paths
    log_path = args.log_file if os.path.isabs(args.log_file) else os.path.join("outputs", args.log_file)
    output_path = args.output_file if os.path.isabs(args.output_file) else os.path.join("outputs", args.output_file)

    # A simple check to avoid double-prefixing if the user provides a path like "outputs/file.log"
    if log_path.startswith("outputs/outputs/"):
        log_path = log_path.replace("outputs/outputs/", "outputs/", 1)
    if output_path.startswith("outputs/outputs/"):
        output_path = output_path.replace("outputs/outputs/", "outputs/", 1)

    asyncio.run(create_script_from_log(log_path, output_path, args.protocol))
