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
You are an AI data processing service. Your sole function is to convert a raw game log into a perfectly structured JSON output. You MUST adhere strictly to the JSON protocol provided. Any deviation will cause a system failure.

**JSON SCRIPTING PROTOCOL:**
---
{protocol}
---

**CRITICAL INSTRUCTIONS:**

1.  **State Change Detection**: The `game_state` and `quest_dashboard_state` objects are **OPTIONAL**. You MUST ONLY include them in an event's JSON if their values have CHANGED in that event. For subsequent events where the state is the same, OMIT these keys.
2.  **Narrative Content (`content`)**: For player speeches and narrator lines, inject parenthetical performance notes like `(dramatically)` or `(triumphantly)` to guide the tone.
3.  **Specific Event Formatting**:
    *   **`VOTE_RESULT`**: The `summary` MUST be in the format: "Approved: [player_ids] Rejected: [player_ids]". The `content` MUST narrate who voted which way.

---
**HIGH-QUALITY EXAMPLES (Follow this format and quality):**

*   **Event 1: A leader proposes a team (State CHANGES)**
    ```json
    {{
      "event_type": "TEAM_PROPOSAL",
      "player_id": 4,
      "team": [4, 0, 1],
      "summary": "Leader 4 proposes a team.",
      "content": "(decisively) As leader, I propose a team of players 4, 0, and 1.",
      "game_state": {{ "current_leader": 4, "proposed_team": [4, 0, 1] }}
    }}
    ```

*   **Event 2: A player discusses the team (State does NOT change)**
    ```json
    {{
      "event_type": "PLAYER_SPEECH",
      "player_id": 5,
      "summary": "Player 5 supports the team.",
      "content": "(supportively) I agree with that team. It seems logical."
    }}
    ```

*   **Event 3: A quest is completed (State CHANGES)**
    ```json
    {{
      "event_type": "QUEST_RESULT",
      "quest_number": 1,
      "team": [0, 6],
      "result": "SUCCESS",
      "summary": "Quest 1 succeeded.",
      "content": "(triumphantly) The results are in for the first quest. It is a success!",
      "game_state": {{ "current_leader": 1, "proposed_team": null }},
      "quest_dashboard_state": [
        {{ "quest_number": 1, "team": [0, 6], "result": "SUCCESS" }}
      ]
    }}
    ```
---

**Final Review Mandate:** Before outputting your response, perform a final validation pass on the entire JSON array you have generated. Ensure every object strictly adheres to all rules and examples provided. Your final output must be only the validated JSON.

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
    # if "--- Post-Game ---" not in game_log:
    #     script_logger.error("Log file appears to be incomplete. Missing '--- Post-Game ---' marker. Aborting script generation.")
    #     return

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