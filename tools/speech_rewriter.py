import os
import yaml
import logging
import google.generativeai as genai
import re
import asyncio
import sys
import argparse
from typing import List, Dict, Any, Tuple

# --- Logging Setup ---
plain_formatter = logging.Formatter('%(message)s')
debug_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')

rewrite_logger = logging.getLogger("rewrite_flow")
rewrite_logger.setLevel(logging.INFO)
rewrite_logger.propagate = False
if not rewrite_logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(plain_formatter)
    rewrite_logger.addHandler(console_handler)

debug_logger = logging.getLogger("rewrite_debug")
debug_logger.setLevel(logging.DEBUG)
debug_logger.propagate = False
if not debug_logger.handlers:
    debug_file_handler = logging.FileHandler('speech_rewriter_debug.log', mode='w')
    debug_file_handler.setFormatter(debug_formatter)
    debug_logger.addHandler(debug_file_handler)
# --- End Logging Setup ---

def load_player_identities(config_path: str) -> Dict[str, str]:
    """Loads player ID to model name mapping from the config file."""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        player_map = {
            str(p['player_id']): p['model'] 
            for p in config.get('player_setup', [])
        }
        rewrite_logger.info(f"Loaded model identities: {player_map}")
        return player_map
    except Exception as e:
        rewrite_logger.error(f"Could not read or parse config.yaml: {e}")
        return {}

async def rewrite_speech(speech: str, player_id: str, model_identity: str, model: genai.GenerativeModel) -> str:
    """
    [LLM Call] Rewrites dialogue to be more conversational and model-aware.
    """
    prompt = f"""
You are a master script doctor for a show where AI models play the game of Avalon.
Your task is to rewrite the following dialogue, spoken by a specific AI model, to be more conversational, engaging, and natural-sounding.

**CONTEXT:**
- **Speaker's AI Identity:** Player {player_id} is the "{model_identity}" model.
- **Your Goal:** Inject personality, humor, and "in-jokes" related to the speaker's AI identity. The tone should be witty and self-aware.

**CRITICAL RULES:**
1.  **DO NOT** change the core meaning, strategic intent, or key information. The rewritten speech must convey the exact same facts and arguments.
2.  **Inject Personality:** Make it sound like an AI with a distinct personality. For example, Grok might be bombastic, GPT might be corporate but polished, Claude might be philosophical, and Deepseek might sound like an older, respected model.
3.  **Add In-Jokes:** Weave in subtle (or not-so-subtle) jokes about the AI world.
    - *Example Joke:* A Deepseek model might say to a GPT model, "Careful, I was running circles around your ancestors."
    - *Example Joke:* A Grok model might say something arrogant like, "My logic is undeniable, unlike some other models I could mention."
4.  **Make it Conversational:** Use contractions (I'm, don't), break up long sentences, and make it flow well when spoken aloud.
5.  **Output ONLY the rewritten text.** Do not add explanations or quote marks.

**DIALOGUE TO REWRITE:**
---
**Original Text (from Player {player_id}, the "{model_identity}"):**
"{speech}"
---

**Your Rewritten, Model-Aware Dialogue:**
""".strip()
    debug_logger.debug(f"REQUEST for Speech Rewrite:\n{prompt}")
    try:
        response = await model.generate_content_async(prompt)
        rewritten_text = "".join(part.text for part in response.parts).strip()
        debug_logger.debug(f"RAW RESPONSE from Rewrite: {rewritten_text}")
        
        if rewritten_text.startswith('"') and rewritten_text.endswith('"'):
            rewritten_text = rewritten_text[1:-1]
            
        return rewritten_text
    except Exception as e:
        debug_logger.error(f"Failed to REWRITE speech for Player {player_id}: {speech[:100]}... Error: {e}")
        return speech # Return original speech on failure

def find_all_speeches(log_content: str) -> List[Tuple[str, str, Tuple[int, int]]]:
    """
    Finds all speeches, statements, and reasonings in the log file.
    Returns a list of tuples: (player_id, text_to_rewrite, (start_index, end_index))
    """
    # This regex now captures multiple patterns:
    # 1. Player X (Role) says: ...
    # 2. Leader X ... Reasoning: ...
    # 3. Reasoning: ... (following a leader statement)
    # 4. MVP/Assassin ... Reasoning: ...
    # It captures the player ID from various contexts.
    pattern = re.compile(
        r"(?:Player (\d+) \([\w\s]+\) says: |Leader (\d+) initially proposed team:.*?Reasoning: |Leader (\d+) has finalized the team to:.*?Reasoning: |\(Leader: Player (\d+)\)|Player (\d+) voted for Player \d+\. Reasoning: |(Assassin) \(\w+\) proposes to assassinate Player \d+\. Reasoning: |(MVP) \([\w\s]+\) says: )"
        r"([\s\S]*?)"
        r"(?=\n(?:---|\Z|Player \d+|Leader \d+|Vote Results|Quest Execution|Assassin|MVP))"
    )
    
    matches = []
    last_leader_id = None

    # Find explicit leader IDs first to handle standalone "Reasoning:" blocks
    leader_ids = {m.start(): m.group(1) for m in re.finditer(r"\(Leader: Player (\d+)\)", log_content)}
    
    # Find all speech blocks
    for match in pattern.finditer(log_content):
        groups = match.groups()
        player_id = next((g for g in groups[:7] if g is not None), None)
        speech_text = groups[7].strip()
        
        # Handle special cases for Assassin/MVP
        if player_id == "Assassin":
            assassin_id_search = re.search(r"Player (\d+) is assigned role: Assassin", log_content)
            if assassin_id_search: player_id = assassin_id_search.group(1)
        elif player_id == "MVP":
            mvp_id_search = re.search(r"The MVP is Player (\d+)", log_content)
            if mvp_id_search: player_id = mvp_id_search.group(1)

        # Find the closest preceding leader ID for context
        current_pos = match.start()
        closest_leader_pos = max([pos for pos in leader_ids if pos < current_pos], default=-1)
        if closest_leader_pos != -1:
            last_leader_id = leader_ids[closest_leader_pos]

        if player_id is None:
            player_id = last_leader_id

        if speech_text and player_id:
            # The text to rewrite is the speech itself. We need start/end of the speech part.
            speech_start = match.start(8)
            speech_end = match.end(8)
            matches.append((player_id, speech_text, (speech_start, speech_end)))

    # A second pass for simple "Reasoning:" blocks that might be missed
    reasoning_pattern = re.compile(r"Reasoning: ([\s\S]*?)(?=\n(?:---|\Z|Player \d+|Leader \d+))")
    for match in reasoning_pattern.finditer(log_content):
        # Check if this block is already captured
        is_captured = any(m[2][0] <= match.start(1) <= m[2][1] for m in matches)
        if not is_captured:
            current_pos = match.start()
            closest_leader_pos = max([pos for pos in leader_ids if pos < current_pos], default=-1)
            if closest_leader_pos != -1:
                player_id = leader_ids[closest_leader_pos]
                text = match.group(1).strip()
                if text:
                     matches.append((player_id, text, match.span(1)))

    # Sort matches by their start index to process them in order
    matches.sort(key=lambda x: x[2][0])
    return matches


async def rewrite_speeches_in_log(input_log_path: str, output_log_path: str, config_path: str):
    """
    Reads a game log, rewrites all player speeches with model-aware personality, and saves to a new file.
    """
    rewrite_logger.info(f"Starting model-aware speech rewriting for log file: {input_log_path}")
    
    player_identities = load_player_identities(config_path)
    if not player_identities:
        rewrite_logger.error("Could not proceed without player identities.")
        return

    try:
        with open(input_log_path, 'r', encoding='utf-8') as f:
            game_log = f.read()
    except FileNotFoundError:
        rewrite_logger.error(f"Input file not found: {input_log_path}")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        rewrite_logger.error("GEMINI_API_KEY environment variable not set.")
        return
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-1.5-pro-latest')

    speech_matches = find_all_speeches(game_log)
    
    if not speech_matches:
        rewrite_logger.warning("No speeches found in the log file. Please check the regex pattern.")
        return

    rewrite_logger.info(f"Found {len(speech_matches)} speeches/reasonings to rewrite. Processing with Gemini 1.5 Pro...")

    tasks = []
    for player_id, speech_text, _ in speech_matches:
        if player_id in player_identities:
            model_identity = player_identities[player_id]
            tasks.append(rewrite_speech(speech_text, player_id, model_identity, model))
        else:
            tasks.append(asyncio.sleep(0, result=speech_text)) # Keep original if no identity

    rewritten_speeches = await asyncio.gather(*tasks)

    rewrite_logger.info("All speeches have been rewritten. Replacing them in the log...")

    # Replace from the end to the beginning to not mess up indices
    modified_log = game_log
    for i in range(len(speech_matches) - 1, -1, -1):
        _, _, (start, end) = speech_matches[i]
        new_speech = rewritten_speeches[i]
        modified_log = modified_log[:start] + new_speech + modified_log[end:]

    with open(output_log_path, 'w', encoding='utf-8') as f:
        f.write(modified_log)
        
    rewrite_logger.info(f"Successfully saved the rewritten log to: {output_log_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rewrite speeches in a game log with AI model personality.")
    parser.add_argument("input_file", help="Path to the input game log file.")
    parser.add_argument("output_file", help="Path for the output rewritten log file.")
    parser.add_argument("--config", default="config.yaml", help="Path to the config file with player identities.")
    args = parser.parse_args()

    try:
        import yaml
    except ImportError:
        print("PyYAML is not installed. Please install it using: pip install PyYAML")
        sys.exit(1)

    asyncio.run(rewrite_speeches_in_log(args.input_file, args.output_file, args.config))