import os
import json
import logging
import google.generativeai as genai
import re
import asyncio
import sys
from typing import List, Dict, Any

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
    delimiters = r"(?=(?:--- Starting Quest|--- Vote Results|--- Quest Results|--- The Final Assassination|--- Game Over ---|--- MVP Selection Phase ---|--- Post-Game ---))"
    chunks = re.split(delimiters, game_log)
    return [chunk.strip() for chunk in chunks if chunk.strip()]

async def structure_chunk(chunk: str, model: genai.GenerativeModel, protocol: str) -> List[Dict[str, Any]]:
    """
    [LLM Call #1] Converts a raw log chunk into a structured JSON array.
    This step focuses ONLY on structuring the data, NOT on modifying content.
    """
    prompt = f"""
You are a data transformation AI. Your only job is to convert a raw text log into a structured JSON array based on the provided protocol.

**JSON SCRIPTING PROTOCOL:**
---
{protocol}
---

**CRITICAL RULE:**
You MUST copy all player speeches, narrator lines, and reasoning text into the `content` field **VERBATIM**. Do NOT summarize, edit, rephrase, or omit any part of the original text. The content must be a perfect, one-to-one copy.

**GAME LOG CHUNK TO STRUCTURE:**
---
{chunk}
---

**OUTPUT:**
Produce only the validated JSON array.
""".strip()
    debug_logger.debug(f"REQUEST for Structuring:\n{prompt}")
    try:
        response = await model.generate_content_async(prompt)
        script_text = "".join(part.text for part in response.parts)
        debug_logger.debug(f"RAW RESPONSE from Structuring:\n{script_text}")
        
        if script_text.strip().startswith("```json"):
            script_text = script_text.strip()[7:-3].strip()
            
        return json.loads(script_text)
    except Exception as e:
        debug_logger.error(f"Failed to STRUCTURE chunk: {chunk[:100]}... Error: {e}")
        return []

async def enrich_event_content(event: Dict[str, Any], model: genai.GenerativeModel) -> Dict[str, Any]:
    """
    [LLM Call #2] Enriches a single event's content with a parenthetical performance note.
    This step ONLY adds a prefix and does not alter the original content.
    """
    # Only enrich events that represent speech
    if event.get("event_type") not in ["PLAYER_SPEECH", "NARRATOR_SPEECH", "TEAM_PROPOSAL", "MVP_SPEECH"]:
        return event

    original_content = event.get("content", "")
    if not original_content:
        return event

    prompt = f"""
You are a script editor. Your only task is to add a single, parenthetical performance note (e.g., "(angrily)") to the beginning of the provided text.

**CRITICAL RULE:**
You MUST NOT change, add, or remove any part of the original text. Your entire output should be ONLY the performance note.

**EXAMPLE:**
- Input Text: "I would never betray you."
- Your Output: (pleadingly)

**TEXT TO ANALYZE:**
---
{original_content}
---

**OUTPUT:**
(Your single performance note here)
""".strip()
    debug_logger.debug(f"REQUEST for Enrichment:\n{prompt}")
    try:
        response = await model.generate_content_async(prompt)
        performance_note = "".join(part.text for part in response.parts).strip()
        debug_logger.debug(f"RAW RESPONSE from Enrichment: {performance_note}")

        # Basic validation for the note format
        if performance_note.startswith("(") and performance_note.endswith(")"):
            event["content"] = f"{performance_note} {original_content}"
        else:
            debug_logger.warning(f"Received malformed performance note: {performance_note}. Using original content.")

        return event
    except Exception as e:
        debug_logger.error(f"Failed to ENRICH content: {original_content[:100]}... Error: {e}")
        return event # Return original event on failure

async def generate_game_review(game_log: str, model: genai.GenerativeModel) -> List[Dict[str, Any]]:
    """
    Generates a final game review using a two-step map/reduce process.
    """
    script_logger.info("Generating final game review...")
    
    # Step 1: Map - Extract key turning points from the entire log
    map_prompt = f"""
You are a game analyst. Read the entire Avalon game log and identify the 3-5 most critical turning points that decided the game's outcome.

For each turning point, provide a single, concise sentence.

**ENTIRE GAME LOG:**
---
{game_log}
---

**OUTPUT (one sentence per line):**
- [Turning Point 1]
- [Turning Point 2]
- [Turning Point 3]
...
""".strip()
    debug_logger.debug(f"REQUEST for Review (Map Phase):\n{map_prompt}")
    try:
        map_response = await model.generate_content_async(map_prompt)
        key_moments = "".join(part.text for part in map_response.parts)
        debug_logger.debug(f"RAW RESPONSE from Review (Map Phase):\n{key_moments}")
    except Exception as e:
        debug_logger.error(f"Failed to extract key moments for review. Error: {e}")
        return []

    # Step 2: Reduce - Generate the final commentary based on the key moments
    reduce_prompt = f"""
You are a master storyteller and game analyst for Avalon. Based on the key turning points provided below, deliver a final, conclusive "Game Review" narration.

**INSTRUCTIONS:**
1.  **Adopt a Narrator's Tone**: Write in a thoughtful, dramatic, and analytical style.
2.  **Weave a Narrative**: Use the key moments as your guide to tell the story of how the game was won and lost.
3.  **Evaluate Strategy**: Briefly comment on the overall strategy of both teams.
4.  **Conclude Powerfully**: End with a final thought that summarizes the game's theme.
5.  **DO NOT** simply list the turning points. Integrate them into a flowing narrative.

**KEY TURNING POINTS:**
---
{key_moments}
---

**OUTPUT:**
Provide only the narrator's speech as a single block of text. Do not add any other formatting.
""".strip()
    debug_logger.debug(f"REQUEST for Review (Reduce Phase):\n{reduce_prompt}")
    try:
        reduce_response = await model.generate_content_async(reduce_prompt)
        review_text = "".join(part.text for part in reduce_response.parts)
        debug_logger.debug(f"RAW RESPONSE from Review (Reduce Phase):\n{review_text}")
        
        if review_text:
            # Also parse roles for a final recap
            roles_text = "The roles were not found."
            roles_section_match = re.search(r"The roles for this game were:\s*([\s\S]*?)\s*---", game_log, re.DOTALL)
            if roles_section_match:
                roles_text = roles_section_match.group(1).strip().replace("\n", "... ")

            return [
                {"event_type": "NARRATOR_SPEECH", "summary": "Narrator recaps the roles.", "content": f"(solemnly) And so, our tale comes to an end. Let us remember the parts our players held... {roles_text}"},
                {"event_type": "NARRATOR_SPEECH", "summary": "Narrator gives a final game review.", "content": review_text}
            ]
        return []
    except Exception as e:
        debug_logger.error(f"Failed to generate final review commentary. Error: {e}")
        return []

async def create_script_from_log(log_file_path: str, output_file_path: str, protocol_path: str):
    """
    Reads a raw game log and creates a structured, enriched JSON script.
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

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        script_logger.error("GEMINI_API_KEY environment variable not set.")
        return
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    pro_model = genai.GenerativeModel('models/gemini-2.5-pro')

    chunks = split_log_into_chunks(game_log)
    script_logger.info(f"Log split into {len(chunks)} chunks for processing.")
    
    final_script = []
    for i, chunk in enumerate(chunks):
        script_logger.info(f"--- Processing Chunk {i+1}/{len(chunks)} ---")
        
        # Step 1: Pure Structuring
        script_logger.info("Step 1: Structuring raw text to JSON...")
        structured_events = await structure_chunk(chunk, model, protocol)
        if not structured_events:
            script_logger.warning(f"Chunk {i+1} yielded no structured events. Skipping.")
            continue
        
        # Step 2: Focused Enrichment
        script_logger.info(f"Step 2: Enriching {len(structured_events)} events with performance notes...")
        enrichment_tasks = [enrich_event_content(event, model) for event in structured_events]
        enriched_events = await asyncio.gather(*enrichment_tasks)
        
        final_script.extend(enriched_events)

    script_logger.info(f"Successfully processed all chunks. Total events from log: {len(final_script)}")

    # --- Add Final Game Review ---
    if "--- Game Over ---" in game_log:
        review_events = await generate_game_review(game_log, pro_model)
        if review_events:
            # Enrich the final review events as well
            enrichment_tasks = [enrich_event_content(event, model) for event in review_events]
            enriched_review_events = await asyncio.gather(*enrichment_tasks)
            final_script.extend(enriched_review_events)
            script_logger.info(f"Added {len(enriched_review_events)} enriched review events to the script.")

    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(final_script, f, indent=2, ensure_ascii=False)
    script_logger.info(f"Successfully generated and saved the final script to: {output_file_path}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Convert a game log to a structured JSON script using an LLM.")
    parser.add_argument("log_file", help="Path to the input game log file (inside outputs/ dir).", nargs='?')
    parser.add_argument("output_file", help="Path for the output JSON script file (inside outputs/ dir).", nargs='?')
    parser.add_argument("--protocol", default="prompts/script_protocol.md", help="Path to the script protocol definition file.")
    args = parser.parse_args()

    if not args.log_file or not args.output_file:
        parser.error("the following arguments are required: log_file, output_file")

    # Handle absolute vs. relative paths
    log_path = args.log_file if os.path.isabs(args.log_file) else os.path.join("outputs", args.log_file)
    output_path = args.output_file if os.path.isabs(args.output_file) else os.path.join("outputs", args.output_file)

    # A simple check to avoid double-prefixing if the user provides a path like "outputs/file.log"
    if log_path.startswith("outputs/outputs/"):
        log_path = log_path.replace("outputs/outputs/", "outputs/", 1)
    if output_path.startswith("outputs/outputs/"):
        output_path = output_path.replace("outputs/outputs/", "outputs/", 1)

    asyncio.run(create_script_from_log(log_path, output_path, args.protocol))