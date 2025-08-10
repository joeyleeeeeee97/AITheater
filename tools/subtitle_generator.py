import json
import logging
import os
import time
from typing import List, Dict, Any

# --- Constants ---
SUBTITLE_CACHE_DIR = "outputs/subtitles"
CACHE_FILE = os.path.join(SUBTITLE_CACHE_DIR, "cache.json")

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Faster-Whisper Model Management ---
WHISPER_MODEL = None

def load_whisper_model(model_size: str = "medium"):
    """Loads the faster-whisper model into a global variable to avoid reloading."""
    global WHISPER_MODEL
    if WHISPER_MODEL is None:
        try:
            from faster_whisper import WhisperModel
            logging.info(f"Loading faster-whisper model ('{model_size}')... This may take a moment.")
            WHISPER_MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
            logging.info("Faster-whisper model loaded successfully.")
        except ImportError:
            logging.error("faster-whisper is not installed. Please run: pip install faster-whisper")
            WHISPER_MODEL = "UNAVAILABLE"
        except Exception as e:
            logging.error(f"Failed to load faster-whisper model: {e}")
            WHISPER_MODEL = "UNAVAILABLE"

# --- Core Transcription Logic ---

def get_word_level_timestamps_whisper(audio_path: str, text: str) -> List[Dict[str, Any]]:
    """Use the pre-loaded faster-whisper model for transcription and alignment."""
    if WHISPER_MODEL is None or WHISPER_MODEL == "UNAVAILABLE":
        logging.error("Whisper model is not available. Cannot process audio.")
        return []

    try:
        segments, _ = WHISPER_MODEL.transcribe(
            audio_path,
            language="en",
            word_timestamps=True,
            initial_prompt=text
        )
        
        word_timings = []
        for segment in segments:
            for word in segment.words:
                clean_word = word.word.strip()
                if not clean_word: continue
                word_timings.append({
                    "word": clean_word,
                    "start_ms": int(word.start * 1000),
                    "end_ms": int(word.end * 1000)
                })
        return word_timings
    except Exception as e:
        logging.error(f"Faster-whisper transcription for {os.path.basename(audio_path)} failed: {e}")
        return []

def create_subtitle_chunks(word_timings: List[Dict[str, Any]], max_words_per_chunk: int = 6) -> List[Dict[str, Any]]:
    """Group words into subtitle chunks for better readability."""
    if not word_timings: return []
    chunks, current_chunk_words = [], []
    chunk_start_ms = word_timings[0]["start_ms"]
    for i, word_timing in enumerate(word_timings):
        current_chunk_words.append(word_timing["word"])
        is_punctuation_break = any(p in word_timing["word"] for p in '.!?')
        is_comma_break = ',' in word_timing["word"] and len(current_chunk_words) >= 3
        is_max_words_reached = len(current_chunk_words) >= max_words_per_chunk
        is_last_word = i == len(word_timings) - 1
        
        if is_punctuation_break or is_comma_break or is_max_words_reached or is_last_word:
            chunk_text = " ".join(current_chunk_words).strip()
            if chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "start_ms": chunk_start_ms,
                    "end_ms": word_timing["end_ms"]
                })
            current_chunk_words = []
            if not is_last_word:
                chunk_start_ms = word_timings[i + 1]["start_ms"]
    return chunks

# --- Main Process Flow ---

def process_single_audio_file(item: Dict[str, Any], cache: Dict) -> bool:
    """
    Processes a single audio file, generating its individual subtitle file.
    Returns True if a new subtitle file was generated, False if skipped due to cache.
    """
    audio_path = item.get("file_path", "")
    event_index = item.get("event_index")
    text = str(item.get("text", "")).strip()
    duration_ms = int(item.get("duration_ms", 0))
    
    if not all([audio_path, os.path.exists(audio_path), text, duration_ms > 0]):
        logging.warning(f"Skipping event {event_index} due to missing data or file.")
        return False

    individual_subtitle_path = os.path.join(SUBTITLE_CACHE_DIR, f"event_{event_index:03d}.json")
    
    # Caching logic
    try:
        mtime = os.path.getmtime(audio_path)
        size = os.path.getsize(audio_path)
        cache_entry = cache.get(audio_path)
        if cache_entry and cache_entry['mtime'] == mtime and cache_entry['size'] == size and os.path.exists(individual_subtitle_path):
            logging.info(f"Cache hit for event {event_index}. Skipping.")
            return False
    except OSError:
        logging.warning(f"Could not read metadata for {audio_path}. Forcing re-processing.")

    logging.info(f"Cache miss for event {event_index}. Processing...")
    
    word_timings = get_word_level_timestamps_whisper(audio_path, text)
    
    if not word_timings:
        logging.warning(f"Whisper failed for event {event_index}. Creating fallback subtitle.")
        subtitle_chunks = [{
            "event_index": event_index,
            "chunk_index": 0,
            "start_ms": 0,
            "end_ms": duration_ms,
            "text": text,
            "word_count": len(text.split()),
            "source": "fallback"
        }]
    else:
        subtitle_chunks_relative = create_subtitle_chunks(word_timings)
        subtitle_chunks = []
        for i, chunk in enumerate(subtitle_chunks_relative):
            subtitle_chunks.append({
                "event_index": event_index,
                "chunk_index": i,
                "start_ms": chunk["start_ms"],
                "end_ms": chunk["end_ms"],
                "text": chunk["text"],
                "word_count": len(chunk["text"].split()),
                "source": "faster-whisper-medium"
            })

    with open(individual_subtitle_path, 'w', encoding='utf-8') as f:
        json.dump(subtitle_chunks, f, indent=2, ensure_ascii=False)
        
    # Update cache
    cache[audio_path] = {'mtime': mtime, 'size': size}
    return True

def assemble_final_subtitles(audio_metadata: List[Dict[str, Any]], final_subtitle_file: str):
    """
    Assembles individual subtitle files into a single, final file with absolute timestamps.
    """
    logging.info("Assembling final subtitle file...")
    all_subtitles = []
    current_time_ms = 0

    for item in audio_metadata:
        event_index = item.get("event_index")
        duration_ms = int(item.get("duration_ms", 0))
        individual_subtitle_path = os.path.join(SUBTITLE_CACHE_DIR, f"event_{event_index:03d}.json")

        if os.path.exists(individual_subtitle_path):
            try:
                with open(individual_subtitle_path, 'r', encoding='utf-8') as f:
                    individual_subtitles = json.load(f)
                
                for sub in individual_subtitles:
                    # Adjust timestamps to be absolute
                    sub["start_ms"] += current_time_ms
                    sub["end_ms"] += current_time_ms
                    all_subtitles.append(sub)
            except (json.JSONDecodeError, IOError) as e:
                logging.error(f"Could not read or parse individual subtitle for event {event_index}: {e}")
        else:
            logging.warning(f"Individual subtitle file not found for event {event_index}. It will be missing from the final output.")
            
        current_time_ms += duration_ms

    logging.info(f"Generated {len(all_subtitles)} final subtitle entries.")
    with open(final_subtitle_file, 'w', encoding='utf-8') as f:
        json.dump(all_subtitles, f, indent=2, ensure_ascii=False)
    logging.info(f"Precise subtitles successfully saved to: {final_subtitle_file}")

def main(metadata_file: str, subtitle_file: str):
    """Main function to drive the subtitle generation and assembly process."""
    os.makedirs(SUBTITLE_CACHE_DIR, exist_ok=True)

    try:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            audio_metadata = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"Failed to read or parse metadata file: {e}")
        return

    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}

    load_whisper_model()
    if WHISPER_MODEL == "UNAVAILABLE":
        return

    # --- Generation Phase ---
    for item in audio_metadata:
        process_single_audio_file(item, cache)

    # --- Save Cache ---
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2)
        
    # --- Assembly Phase ---
    assemble_final_subtitles(audio_metadata, subtitle_file)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate subtitles using a cached, modular approach.")
    parser.add_argument("metadata_file", help="Path to the input audio metadata JSON file.")
    parser.add_argument("subtitle_file", help="Path for the final output subtitle JSON file.")
    args = parser.parse_args()

    main(args.metadata_file, args.subtitle_file)