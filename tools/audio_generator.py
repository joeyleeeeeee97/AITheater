import os
import json
import logging
import asyncio
import re
from dotenv import load_dotenv
from google.cloud import texttospeech_v1beta1 as texttospeech
from mutagen.mp3 import MP3

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
VOICE_MAPPING = {
    0: "en-US-Wavenet-D",  # A deep, mature male voice.
    1: "en-US-Wavenet-F",  # A standard female voice.
    2: "en-US-Wavenet-C",  # A different female voice.
    3: "en-US-Wavenet-A",  # A standard male voice.
    4: "en-US-Wavenet-B",  # A different male voice.
    5: "en-US-Wavenet-E",  # A softer male voice.
    6: "en-US-Wavenet-J",  # A younger female voice.
    "NARRATOR": "en-US-Casual-K" # A casual, male narrator voice.
}

def clean_and_create_ssml(text: str) -> (str, list):
    """
    Removes performance notes and creates an SSML string with word marks.
    Returns the SSML string and a list of the words.
    """
    # First, remove any performance notes
    clean_text = re.sub(r'\(.*?\)', '', text).strip()
    
    # Split the text into words and punctuation
    words = re.findall(r"[\w']+|[.,!?;]", clean_text)
    
    # Create the SSML string
    ssml_text = "<speak>"
    for i, word in enumerate(words):
        ssml_text += f'<mark name="{i}"/>{word} '
    ssml_text += "</speak>"
    
    return ssml_text, words

async def generate_audio_for_event(event: dict, index: int, client: texttospeech.TextToSpeechAsyncClient, output_dir: str) -> dict:
    """Generates a single audio file for any event with content."""
    event_type = event.get("event_type")
    text_content = event.get("content")

    if not text_content:
        logging.warning(f"Skipping event {index} ({event_type}) due to missing content.")
        return None

    # Determine the voice to use
    if event_type == "PLAYER_SPEECH":
        player_id = event.get("player_id")
        if player_id is None:
            logging.warning(f"Skipping PLAYER_SPEECH event {index} due to missing player_id.")
            return None
        voice_name = VOICE_MAPPING.get(player_id, "en-US-Standard-A") # Default for players
        logging_name = f"Player {player_id}"
    else:
        player_id = "NARRATOR" # For metadata purposes
        voice_name = VOICE_MAPPING["NARRATOR"]
        logging_name = "Narrator"

    ssml_text, text_words = clean_and_create_ssml(text_content)
    
    if not text_words:
        logging.info(f"Skipping event {index} as it contains only performance notes or is empty.")
        return None

    output_filename = f"event_{index:03d}.mp3"
    output_filepath = os.path.join(output_dir, output_filename)

    logging.info(f"Generating audio for event {index} ({logging_name}) -> {output_filename}")

    synthesis_input = texttospeech.SynthesisInput(ssml=ssml_text)
    voice = texttospeech.VoiceSelectionParams(language_code=voice_name.split('-')[0] + '-' + voice_name.split('-')[1], name=voice_name)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

    try:
        request = texttospeech.SynthesizeSpeechRequest(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
            enable_time_pointing=[texttospeech.SynthesizeSpeechRequest.TimepointType.SSML_MARK]
        )
        response = await client.synthesize_speech(request=request)

        with open(output_filepath, "wb") as out:
            out.write(response.audio_content)

        # Get audio duration
        audio = MP3(output_filepath)
        duration_ms = int(audio.info.length * 1000)

        # Extract word timings from SSML marks
        words = []
        for point in response.timepoints:
            word_index = int(point.mark_name)
            words.append({
                "word": text_words[word_index],
                "time_ms": point.time_seconds * 1000
            })

        return {
            "event_index": index,
            "player_id": player_id,
            "file_path": output_filepath,
            "duration_ms": duration_ms,
            "words": words
        }
    except Exception as e:
        logging.error(f"Failed to generate audio for event {index}. Error: {e}")
        return None

async def main(script_file: str, output_dir: str, metadata_file: str):
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
        generate_audio_for_event(event, i, client, output_dir)
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
    
    # Prepend outputs/ directory to all paths
    script_path = os.path.join("outputs", args.script_file if args.script_file else "final_script.json")
    output_path = os.path.join("outputs", output_dir_name)
    metadata_path = os.path.join("outputs", args.metadata_file if args.metadata_file else "audio_metadata.json")

    # Ensure the user has set up Google Cloud credentials
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print("\nERROR: GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.")
        print("Please follow the setup instructions in the design document.")
    else:
        asyncio.run(main(script_path, output_path, metadata_path))