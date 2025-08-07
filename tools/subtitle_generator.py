import json
import logging
import os
import time
from typing import List, Dict, Any

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Faster-Whisper Timing Generation (Optimized and Robust) ---

# Global variable to hold the loaded Whisper model.
WHISPER_MODEL = None

def load_whisper_model(model_size: str = "medium"):
    """Loads the faster-whisper model into a global variable."""
    global WHISPER_MODEL
    if WHISPER_MODEL is None:
        try:
            from faster_whisper import WhisperModel
            logging.info(f"Loading faster-whisper model ('{model_size}')... This may take a moment.")
            # For M1 Mac, using CPU with int8 quantization is a good balance.
            WHISPER_MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
            logging.info("Faster-whisper model loaded successfully.")
        except ImportError:
            logging.error("faster-whisper is not installed. Please run: pip install faster-whisper")
            WHISPER_MODEL = "UNAVAILABLE"
        except Exception as e:
            logging.error(f"Failed to load faster-whisper model: {e}")
            WHISPER_MODEL = "UNAVAILABLE"

def _validate_transcription(original_text: str, transcribed_words: List[str]) -> bool:
    """Performs a sanity check on the transcription quality."""
    if not transcribed_words:
        return False
    original_words = set(word.lower().strip(".,!?\"'") for word in original_text.split())
    matched_words = sum(1 for word in transcribed_words if word.lower().strip(".,!?\"'") in original_words)
    match_ratio = matched_words / len(transcribed_words)
    if match_ratio < 0.5:
        logging.warning(f"Validation failed. Match ratio: {match_ratio:.2f}. "
                        f"Original: '{original_text}', Transcribed: '{" ".join(transcribed_words)}"'")
        return False
    return True

def _get_word_level_timestamps_whisper(audio_path: str, text: str, max_retries: int = 2) -> List[Dict[str, Any]]:
    """Use the pre-loaded faster-whisper model for alignment."""
    if WHISPER_MODEL is None or WHISPER_MODEL == "UNAVAILABLE":
        logging.error("Whisper model is not available. Cannot process audio.")
        return []

    for attempt in range(max_retries + 1):
        try:
            segments, _ = WHISPER_MODEL.transcribe(
                audio_path,
                language="en",
                word_timestamps=True,
                initial_prompt=text
            )
            
            word_timings = []
            transcribed_words = []
            for segment in segments:
                for word in segment.words:
                    clean_word = word.word.strip()
                    if not clean_word: continue
                    transcribed_words.append(clean_word)
                    word_timings.append({
                        "word": clean_word,
                        "start_ms": int(word.start * 1000),
                        "end_ms": int(word.end * 1000)
                    })

            if _validate_transcription(text, transcribed_words):
                return word_timings
            else:
                logging.warning(f"Attempt {attempt + 1}/{max_retries + 1} failed validation for {os.path.basename(audio_path)}.")

        except Exception as e:
            logging.error(f"Faster-whisper transcription for {os.path.basename(audio_path)} on attempt {attempt + 1} failed: {e}")
        
        if attempt < max_retries:
            time.sleep(2)

    logging.error(f"All {max_retries + 1} attempts failed for {os.path.basename(audio_path)}.")
    return []

def _get_word_level_timestamps_google(audio_path: str, text: str) -> List[Dict[str, Any]]:
    """Use Google Cloud Speech-to-Text for word-level timestamps."""
    try:
        from google.cloud import speech
    except ImportError:
        logging.error("Google Cloud Speech-to-Text library not found. Please run: pip install google-cloud-speech")
        return []

    client = speech.SpeechClient()

    with open(audio_path, "rb") as audio_file:
        content = audio_file.read()

    audio = speech.RecognitionAudio(content=content)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="en-US",
        enable_word_time_offsets=True,
    )

    try:
        response = client.recognize(config=config, audio=audio)
        word_timings = []
        for result in response.results:
            for word_info in result.alternatives[0].words:
                word_timings.append({
                    "word": word_info.word,
                    "start_ms": word_info.start_time.total_seconds() * 1000,
                    "end_ms": word_info.end_time.total_seconds() * 1000,
                })
        return word_timings
    except Exception as e:
        logging.error(f"Google STT transcription for {os.path.basename(audio_path)} failed: {e}")
        return []


def _create_subtitle_chunks(word_timings: List[Dict[str, Any]], max_words_per_chunk: int = 6) -> List[Dict[str, Any]]:
    """Group words into subtitle chunks."""
    if not word_timings: return []
    chunks, current_chunk_words = [], []
    chunk_start_ms = word_timings[0]["start_ms"]
    for i, word_timing in enumerate(word_timings):
        current_chunk_words.append(word_timing["word"])
        is_punctuation = any(p in word_timing["word"] for p in '.!?')
        is_comma = ',' in word_timing["word"] and len(current_chunk_words) >= 3
        is_max_words = len(current_chunk_words) >= max_words_per_chunk
        is_last = i == len(word_timings) - 1
        if is_punctuation or is_comma or is_max_words or is_last:
            chunk_text = " ".join(current_chunk_words).strip()
            if chunk_text:
                end_time = word_timing["end_ms"]
                if (end_time - chunk_start_ms) < 1000 and not is_last:
                    end_time = chunk_start_ms + 1000
                chunks.append({"text": chunk_text, "start_ms": chunk_start_ms, "end_ms": end_time})
            current_chunk_words = []
            if not is_last: chunk_start_ms = word_timings[i + 1]["start_ms"]
    return chunks

def generate_precise_subtitles(metadata_file: str, subtitle_file: str, stt_engine: str = 'google'):
    """Generates precise subtitles using a specified STT engine."""
    logging.info(f"Reading audio metadata from: {metadata_file}")
    try:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            audio_metadata = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"Failed to read or parse metadata file: {e}")
        return

    if stt_engine == 'whisper':
        load_whisper_model()
        if WHISPER_MODEL == "UNAVAILABLE":
            logging.error("Cannot proceed with subtitle generation as Whisper model failed to load.")
            return

    all_subtitles = []
    current_time_ms = 0
    for item in audio_metadata:
        duration_ms = int(item.get("duration_ms", 0))
        text = str(item.get("text", "")).strip()
        audio_path = item.get("file_path", "")
        event_index = item.get("event_index")

        if text and duration_ms > 0 and os.path.exists(audio_path):
            logging.info(f"Processing event {event_index} with {stt_engine}...")
            if stt_engine == 'google':
                word_timings = _get_word_level_timestamps_google(audio_path, text)
            elif stt_engine == 'whisper':
                word_timings = _get_word_level_timestamps_whisper(audio_path, text)
            else:
                logging.error(f"Unsupported STT engine: {stt_engine}")
                word_timings = []

            if word_timings:
                for timing in word_timings:
                    timing["start_ms"] += current_time_ms
                    timing["end_ms"] += current_time_ms
                
                subtitle_chunks = _create_subtitle_chunks(word_timings)
                
                for i, chunk in enumerate(subtitle_chunks):
                    all_subtitles.append({
                        "event_index": event_index,
                        "chunk_index": i,
                        "start_ms": chunk["start_ms"],
                        "end_ms": chunk["end_ms"],
                        "text": chunk["text"],
                        "word_count": len(chunk["text"].split()),
                        "source": f"{stt_engine}-stt"
                    })
            else:
                logging.warning(f"No subtitles generated for event {event_index}.")
        else:
            logging.warning(f"Skipping event {event_index} due to missing text, duration, or audio file.")

        current_time_ms += duration_ms

    logging.info(f"Generated {len(all_subtitles)} final subtitle entries.")
    
    try:
        with open(subtitle_file, 'w', encoding='utf-8') as f:
            json.dump(all_subtitles, f, indent=2, ensure_ascii=False)
        logging.info(f"Precise subtitles successfully saved to: {subtitle_file}")
    except IOError as e:
        logging.error(f"Failed to save final subtitles: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate subtitles using a specified STT engine.")
    parser.add_argument("metadata_file", help="Path to the input audio metadata JSON file.")
    parser.add_argument("subtitle_file", help="Path for the output subtitle JSON file.")
    parser.add_argument("--stt_engine", default="google", choices=["google", "whisper"], help="The STT engine to use for generating subtitles.")
    args = parser.parse_args()

    generate_precise_subtitles(args.metadata_file, args.subtitle_file, args.stt_engine)
