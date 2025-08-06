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

Analyze the provided game log **CHUNK**. For each event, create a JSON object with a consistent structure.

**CRITICAL INSTRUCTIONS:**

1.  **Unified Event Structure**: Convert every logical event into a JSON object. **ALL** events must include `event_type`, `summary`, and `content`.
    *   Valid `event_type` values are: "GAME_START", "ROLE_ANNOUNCEMENT", "TEAM_PROPOSAL", "PLAYER_SPEECH", "VOTE_RESULT", "QUEST_RESULT", "ASSASSINATION_PHASE", "GAME_OVER", "PLAYER_ELIMINATED", "SCENE_START", "MVP_VOTING_START", "MVP_SPEECH", "MVP_RESULT".
    *   `player_id` should be included where applicable.

2.  **Create a `role_map`**: The **very first event** in your output must be a `ROLE_ANNOUNCEMENT`. This event's JSON object **must** contain a `role_map` field, which is an object mapping every player ID (as a string) to their role (e.g., `{{ "0": "Merlin", "1": "Percival", ... }}`). This is essential for the final video production.

3.  **Create Narrative Content (`content`)**:
    *   For **non-player events**, write a narrative `content` string to be read by a narrator.
    *   For **`PLAYER_SPEECH` and `MVP_SPEECH` events**, rewrite the `content` to include inline, parenthetical performance notes for the voice actor.
    *   **Inject Emotion into ALL `content`**: Add performance notes like `(somberly)` or `(triumphantly)` to guide the tone.

4.  **Create Concise Summaries (`summary`)**:
    *   For **ALL** events, create a concise, third-person `summary` (under 10 words).

5.  **Specific Event Handling & Data Structure**:
    *   **`SCENE_START`**: Must include a `leader_id` field.
    *   **`TEAM_PROPOSAL`**: Must include a `team` field (an array of player IDs).
    *   **`VOTE_RESULT`**: Aggregate all individual votes into one event. Must include `approve_votes` and `reject_votes` fields (arrays of player IDs). **DO NOT** create `PLAYER_SPEECH` events for individual votes.
    *   **`QUEST_RESULT`**: Must include `quest_number`, `team`, and `result` ("SUCCESS" or "FAILURE").
    *   **`MVP_SPEECH`**: Must include `player_id` and `role`.
    *   **`MVP_RESULT`**: Must include `mvp_player_id` and a `votes` object mapping player IDs to who they voted for.

---
**EXAMPLE 1: ROLE ANNOUNCEMENT (CRITICAL!)**

*   **Original Log Lines:**
    ```
    The roles for this game were:
    Player 0: Merlin
    Player 1: Percival
    ...
    ```
*   **Your JSON Output:**
    ```json
    {{{{
      "event_type": "ROLE_ANNOUNCEMENT",
      "role_map": {{{{ 
        "0": "Merlin",
        "1": "Percival",
        "2": "Servant",
        "3": "Mordred",
        "4": "Morgana",
        "5": "Minion",
        "6": "Servant"
      }}}},
      "summary": "Roles have been assigned.",
      "content": "(with anticipation) The identities for this game have been sealed. Knights and traitors walk among us."
    }}}} 
    ```

**EXAMPLE 2: QUEST RESULT (CRITICAL!)**

*   **Original Log Lines:**
    ```
    --- Quest Results ---
    Quest 1 was a SUCCESS.
    The team was [Player 0, Player 1].
    ```
*   **Your JSON Output:**
    ```json
    {{{{
      "event_type": "QUEST_RESULT",
      "quest_number": 1,
      "team": ["0", "1"],
      "result": "SUCCESS",
      "summary": "Quest 1 succeeded.",
      "content": "(triumphantly) The results are in for the first quest. It is a success! A victory for the loyal servants of Arthur."
    }}}} 
    ```

**EXAMPLE 3: VOTE RESULT (CRITICAL!)**

*   **Original Log Lines:**
    ```
    Player 0 votes 'approve'.
    Player 1 votes 'reject'.
    --- Vote Results ---
    Team proposed by Player 2 was: REJECTED
    ```
*   **Your JSON Output:**
    ```json
    {{{{
      "event_type": "VOTE_RESULT",
      "approve_votes": ["0"],
      "reject_votes": ["1"],
      "summary": "Team Rejected.",
      "content": "(dramatically) The votes are in. The team is rejected. An approval from player 0, and a rejection from player 1."
    }}}} 
    ```
    
**EXAMPLE 4: MVP SPEECH**

*   **Original Log Line:** `Player 1 (Merlin) says: I think Player 5 was the MVP...`
*   **Your JSON Output:**
    ```json
    {{{{
      "event_type": "MVP_SPEECH",
      "player_id": "1",
      "role": "Merlin",
      "summary": "MERLIN 1 gives their MVP nomination.",
      "content": "(reflectively) I believe Player 5 was the MVP. Their logic was undeniable."
    }}}} 
    ```
---

Your goal is to create a performable, structured script. The entire output for the given chunk must be a single, valid JSON array.

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

    # Handle absolute vs. relative paths
    log_path = args.log_file if os.path.isabs(args.log_file) else os.path.join("outputs", args.log_file)
    output_path = args.output_file if os.path.isabs(args.output_file) else os.path.join("outputs", args.output_file)

    # A simple check to avoid double-prefixing if the user provides a path like "outputs/file.log"
    if log_path.startswith("outputs/outputs/"):
        log_path = log_path.replace("outputs/outputs/", "outputs/", 1)
    if output_path.startswith("outputs/outputs/"):
        output_path = output_path.replace("outputs/outputs/", "outputs/", 1)

    asyncio.run(create_script_from_log(log_path, output_path))