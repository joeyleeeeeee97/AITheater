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

async def process_chunk(chunk: str, model: genai.GenerativeModel, chunk_index: int) -> list:
    """Sends a single chunk to the LLM and returns the parsed JSON."""
    debug_logger.info(f"--- Processing Chunk {chunk_index} ---")
    
    prompt = f"""
You are a professional screenwriter and audio drama director. Your task is to convert a raw text log from a game of "The Resistance: Avalon" into a structured JSON script suitable for automated voice narration and video generation.

Analyze the provided game log **CHUNK**. For each event, create a JSON object with a consistent structure, including detailed performance notes for narration and speech.

**CRITICAL INSTRUCTIONS:**

1.  **Unified Event Structure**: Convert every line or logical event in the log into a JSON object. **ALL** events must include `event_type`, `summary`, and `content`.
    *   Valid `event_type` values are: "GAME_START", "ROLE_ANNOUNCEMENT", "TEAM_PROPOSAL", "PLAYER_SPEECH", "VOTE_RESULT", "QUEST_RESULT", "ASSASSINATION_PHASE", "GAME_OVER", "PLAYER_ELIMINATED", "SCENE_START".
    *   `player_id` should be included where applicable (e.g., for `PLAYER_SPEECH`).

2.  **Create Narrative Content (`content`)**:
    *   For **non-player events** (like `GAME_START`, `VOTE_RESULT`, `QUEST_RESULT`), you must write a narrative `content` string. This should be read by a narrator to tell the story of the game.
    *   For **`PLAYER_SPEECH` events**, rewrite the `content` to include inline, parenthetical performance notes for the voice actor.
    *   **Inject Emotion into ALL `content`**: Based on the context, add performance notes to guide the tone. For example, a failed `QUEST_RESULT` could be `(somberly)`, the `ASSASSINATION_PHASE` could be `(with tense, dramatic music beginning to build)`, and a final victory could be `(triumphantly)`.

3.  **Create Concise Summaries (`summary`)**:
    *   For **ALL** events, create a concise, third-person `summary`. This text will be displayed on-screen in an information panel for the audience. It should be a simple statement of fact.

**EXAMPLE 1: NARRATOR EVENT**

*   **Original Log Line:** `--- Quest Results --- The quest fails. Required 1 fail, got 1.`
*   **Your JSON Output:**
    ```json
    {{
      "event_type": "QUEST_RESULT",
      "summary": "Quest Failed (1 fail vote submitted).",
      "content": "(somberly) The results of the quest are in... and it has failed. The forces of evil have successfully sabotaged this endeavor."
    }}
    ```

**EXAMPLE 2: PLAYER SPEECH EVENT**

*   **Original Log Line:** `Player 5 (Minion) says: For the sake of getting that clear result, I will be voting to approve this team.`
*   **Your JSON Output:**
    ```json
    {{
      "event_type": "PLAYER_SPEECH",
      "player_id": 5,
      "summary": "Player 5 (Minion) votes 'approve' to gather more information.",
      "content": "For the sake of getting that clear result, (decisively) I will be voting to approve this team."
    }}
    ```

Your goal is to make the `content` field a performable script for a narrator or voice actor. The entire output for the given chunk must be a single, valid JSON array.

**GAME LOG CHUNK TO ADAPT:**
---
{chunk}
---
"""
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


async def create_script_from_log(log_file_path: str, output_file_path: str):
    """
    Reads a raw game log, splits it into chunks, processes them in parallel,
    and saves the resulting structured JSON script.
    """
    script_logger.info(f"Starting script generation from log file: {log_file_path}")

    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            game_log = f.read()
    except FileNotFoundError:
        script_logger.error(f"Log file not found: {log_file_path}")
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

    tasks = [process_chunk(chunk, model, i) for i, chunk in enumerate(chunks)]
    results = await asyncio.gather(*tasks)
    
    final_script = [item for sublist in results for item in sublist] # Flatten the list of lists
    
    debug_logger.info(f"Successfully processed all chunks. Total events: {len(final_script)}")

    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(final_script, f, indent=2)
    script_logger.info(f"Successfully generated and saved the final script to: {output_file_path}")

if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Convert a game log to a structured JSON script using an LLM.")
    parser.add_argument("log_file", help="Path to the input game log file (inside outputs/ dir).", nargs='?')
    parser.add_argument("output_file", help="Path for the output JSON script file (inside outputs/ dir).", nargs='?')
    args = parser.parse_args()

    # Prepend outputs/ directory to paths if they are not absolute
    log_path = args.log_file if os.path.isabs(args.log_file) else os.path.join("outputs", args.log_file)
    output_path = args.output_file if os.path.isabs(args.output_file) else os.path.join("outputs", args.output_file)

    asyncio.run(create_script_from_log(log_path, output_path))