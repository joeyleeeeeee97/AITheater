import os
import json
import logging
import asyncio
import re
from dotenv import load_dotenv
from google.cloud import texttospeech
from mutagen.mp3 import MP3
import yaml

# --- Initial Setup ---
# Load environment variables from .env file
load_dotenv()

# Set Google Cloud credentials from the path in .env
gcp_path = os.getenv("GCP_CREDENTIALS_PATH")
if gcp_path and os.path.exists(gcp_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = gcp_path
else:
    print(f"Warning: GCP credentials path not found at '{gcp_path}'. TTS generation will likely fail.")

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Voice Mapping (The "Voice Actor Cast") ---
# A curated list of high-quality, distinct voices for each player.
VOICE_MAPPING = {
    0: "en-US-Studio-O",      # A clear, professional female voice.
    1: "en-US-WaveNet-D",     # A deep, mature male voice.
    2: "en-US-WaveNet-F",     # A standard female voice.
    3: "en-US-Neural2-I",     # A friendly, younger-sounding female voice.
    4: "en-US-Studio-M",      # A deep, authoritative male voice (different from narrator).
    5: "en-US-Neural2-A",     # A calm, standard male voice.
    6: "en-US-WaveNet-B",     # A straightforward, standard male voice.
    "NARRATOR": "en-US-Neural2-J" # Your specified female narrator voice.
}

class AudioGenerator:
    def __init__(self, config_path="data/layout.yaml"):
        print("Initializing Audio Generator...")
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

    async def generate_audio_for_event(self, event: dict, index: int, client: texttospeech.TextToSpeechAsyncClient, output_dir: str) -> dict:
        """Generates a single audio file for any event with content."""
        event_type = event.get("event_type")
        text_content = event.get("content")

        if not text_content:
            logging.warning(f"Skipping event {index} ({event_type}) due to missing content.")
            return None

        # Clean the text by removing performance notes
        clean_text = re.sub(r'\(.*?\)', '', text_content).strip()
        if not clean_text:
            logging.info(f"Skipping event {index} as it contains only performance notes or is empty.")
            return None

        # Determine the voice to use from the config
        voice_mapping = self.config.get("voice_mapping", {})
        if not voice_mapping:
            logging.error("Voice mapping not found in config file. Aborting.")
            return None

        if event_type == "PLAYER_SPEECH":
            player_id = event.get("player_id")
            if player_id is None:
                logging.warning(f"Skipping PLAYER_SPEECH event {index} due to missing player_id.")
                return None
            # YAML keys are strings, so we convert player_id
            voice_name = voice_mapping.get(str(player_id), "en-US-Standard-A")
            logging_name = f"Player {player_id}"
        else:
            player_id = "NARRATOR" # For metadata purposes
            voice_name = voice_mapping.get("NARRATOR", "en-US-Standard-A")
            logging_name = "Narrator"

        output_filename = f"event_{index:03d}.mp3"
        output_filepath = os.path.join(output_dir, output_filename)

        logging.info(f"Generating audio for event {index} ({logging_name}) -> {output_filename}")

        synthesis_input = texttospeech.SynthesisInput(text=clean_text)
        voice = texttospeech.VoiceSelectionParams(language_code=voice_name.split('-')[0] + '-' + voice_name.split('-')[1], name=voice_name)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

        try:
            request = texttospeech.SynthesizeSpeechRequest(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            response = await client.synthesize_speech(request=request)

            with open(output_filepath, "wb") as out:
                out.write(response.audio_content)

            # Get audio duration
            audio = MP3(output_filepath)
            duration_ms = int(audio.info.length * 1000)

            # Return metadata without word timings
            return {
                "event_index": index,
                "player_id": player_id,
                "file_path": output_filepath,
                "duration_ms": duration_ms,
                "text": clean_text # Include the spoken text for subtitle generation
            }
        except Exception as e:
            logging.error(f"Failed to generate audio for event {index}. Error: {e}")
            return None

    async def generate_all_audio(self, script_file: str, output_dir: str, metadata_file: str):
        """Main function to generate all audio and the metadata file."""
        logging.info(f"Starting audio generation from script: {script_file}")

        try:
            with open(script_file, 'r', encoding='utf-8') as f:
                final_script = json.load(f)
        except FileNotFoundError:
            logging.error(f"Final script file not found: {script_file}")
            return

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logging.info(f"Created output directory: {output_dir}")

        client = texttospeech.TextToSpeechAsyncClient()
        
        tasks = [
            self.generate_audio_for_event(event, i, client, output_dir)
            for i, event in enumerate(final_script)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Filter out None results from non-speech events or failures
        audio_metadata = [res for res in results if res is not None]
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(audio_metadata, f, indent=2)
            
        logging.info(f"Audio generation complete. Metadata saved to: {metadata_file}")
        logging.info(f"Generated {len(audio_metadata)} audio files in '{output_dir}'.")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate audio files from a JSON script.")
    parser.add_argument("script_file", help="Path to the input JSON script file (inside outputs/ dir).", nargs='?')
    parser.add_argument("output_dir", help="Directory to save the generated audio files (inside outputs/ dir).", default="generated_audio", nargs='?')
    parser.add_argument("metadata_file", help="Path for the output audio metadata JSON file (inside outputs/ dir).", nargs='?')
    args = parser.parse_args()

    output_dir_name = args.output_dir
    
    # Handle absolute vs. relative paths, and avoid double-prefixing
    script_path = args.script_file if os.path.isabs(args.script_file) else os.path.join("outputs", args.script_file)
    if script_path.startswith("outputs/outputs/"):
        script_path = script_path.replace("outputs/outputs/", "outputs/", 1)

    output_path = args.output_dir if os.path.isabs(args.output_dir) else os.path.join("outputs", args.output_dir)
    if output_path.startswith("outputs/outputs/"):
        output_path = output_path.replace("outputs/outputs/", "outputs/", 1)

    metadata_path = args.metadata_file if os.path.isabs(args.metadata_file) else os.path.join("outputs", args.metadata_file)
    if metadata_path.startswith("outputs/outputs/"):
        metadata_path = metadata_path.replace("outputs/outputs/", "outputs/", 1)

    # Ensure the user has set up Google Cloud credentials
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print("\nERROR: GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.")
        print("Please follow the setup instructions in the design document.")
    else:
        audio_gen = AudioGenerator()
        asyncio.run(audio_gen.generate_all_audio(script_path, output_path, metadata_path))