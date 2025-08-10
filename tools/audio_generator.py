import os
import json
import logging
import asyncio
import re
from dotenv import load_dotenv
from google.cloud import texttospeech
from mutagen.mp3 import MP3
import yaml
from pydub import AudioSegment
import io

# --- Initial Setup ---
load_dotenv()
gcp_path = os.getenv("GCP_CREDENTIALS_PATH")
if gcp_path and os.path.exists(gcp_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = gcp_path
else:
    print(f"Warning: GCP credentials path not found at '{gcp_path}'.")

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def split_text_by_bytes(text: str, limit: int = 4500) -> list[str]:
    """
    Splits text into chunks that are under the byte limit, splitting at the nearest space.
    """
    if text.encode('utf-8').__len__() <= limit:
        return [text]

    chunks = []
    while text.encode('utf-8').__len__() > limit:
        # Find a split point near the limit
        split_at = limit
        # Find the last space before the limit
        last_space = text.rfind(' ', 0, split_at)
        if last_space != -1:
            split_at = last_space
        
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    chunks.append(text)
    return chunks

class AudioGenerator:
    def __init__(self, config_path="data/layout.yaml"):
        print("Initializing Audio Generator...")
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        self.voice_mapping = self.config.get("voice_mapping", {})
        if not self.voice_mapping:
            raise ValueError("Voice mapping is missing from the layout configuration.")

    async def _generate_single_audio_chunk(self, text_chunk: str, voice_params: dict, audio_config: dict, client: texttospeech.TextToSpeechAsyncClient) -> bytes:
        """Generates audio for a small text chunk."""
        synthesis_input = texttospeech.SynthesisInput(text=text_chunk)
        request = texttospeech.SynthesizeSpeechRequest(
            input=synthesis_input,
            voice=voice_params,
            audio_config=audio_config
        )
        response = await client.synthesize_speech(request=request)
        return response.audio_content

    async def generate_audio_for_event(self, event: dict, index: int, client: texttospeech.TextToSpeechAsyncClient, output_dir: str) -> dict:
        """Generates a single audio file for an event, handling long text by splitting it."""
        event_type = event.get("event_type")
        text_content = event.get("content")

        if not text_content:
            return None

        clean_text = re.sub(r'\(.*\)', '', text_content).strip()
        if not clean_text:
            return None

        player_id_events = ["PLAYER_SPEECH", "TEAM_PROPOSAL", "CONFIRM_TEAM", "MVP_SPEECH", "player_speech", "team_proposal", "mvp_vote"]
        
        player_id = event.get("player_id")
        if event_type in player_id_events:
            if player_id is None:
                logging.warning(f"Skipping {event_type} event {index} due to missing player_id.")
                return None
            voice_name = self.voice_mapping.get(str(player_id), "en-US-Standard-A")
            logging_name = f"Player {player_id}"
        else:
            player_id = "NARRATOR"
            voice_name = self.voice_mapping.get("NARRATOR", "en-US-Standard-A")
            logging_name = "Narrator"

        output_filename = f"event_{index:03d}.mp3"
        output_filepath = os.path.join(output_dir, output_filename)

        logging.info(f"Generating audio for event {index} ({logging_name}) -> {output_filename}")

        voice_params = texttospeech.VoiceSelectionParams(language_code=voice_name.split('-')[0] + '-' + voice_name.split('-')[1], name=voice_name)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

        try:
            text_chunks = split_text_by_bytes(clean_text)
            
            combined_audio = AudioSegment.empty()
            
            audio_tasks = [self._generate_single_audio_chunk(chunk, voice_params, audio_config, client) for chunk in text_chunks if chunk]
            audio_contents = await asyncio.gather(*audio_tasks)
            
            for content in audio_contents:
                combined_audio += AudioSegment.from_file(io.BytesIO(content), format="mp3")

            combined_audio.export(output_filepath, format="mp3")

            audio = MP3(output_filepath)
            duration_ms = int(audio.info.length * 1000)

            return {
                "event_index": index,
                "player_id": player_id,
                "file_path": output_filepath,
                "duration_ms": duration_ms,
                "text": clean_text
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
        
        audio_metadata = [res for res in results if res is not None]
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(audio_metadata, f, indent=2)
            
        logging.info(f"Audio generation complete. Metadata saved to: {metadata_file}")
        logging.info(f"Generated {len(audio_metadata)} audio files in '{output_dir}'.")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate audio files from a JSON script.")
    parser.add_argument("script_file", help="Path to the input JSON script file.")
    parser.add_argument("output_dir", help="Directory to save the generated audio files.", default="generated_audio")
    parser.add_argument("metadata_file", help="Path for the output audio metadata JSON file.")
    args = parser.parse_args()

    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print("\nERROR: GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.")
    else:
        try:
            import pydub
        except ImportError:
            print("pydub is not installed. Please run: pip install pydub")
        else:
            audio_gen = AudioGenerator()
            asyncio.run(audio_gen.generate_all_audio(args.script_file, args.output_dir, args.metadata_file))