import json
import logging
import os
import tempfile
from typing import List, Dict, Any, Optional
import re

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _get_word_level_timestamps_whisper(audio_path: str, text: str) -> List[Dict[str, Any]]:
    """Use Whisper for accurate word-level timestamp alignment."""
    try:
        import whisper
        import torch
        
        # Load Whisper model (using small model for speed, can use larger for accuracy)
        model = whisper.load_model("base")
        
        # Transcribe with word-level timestamps, using the script as a prompt
        result = model.transcribe(
            audio_path,
            word_timestamps=True,
            initial_prompt=text,
            verbose=False
        )
        
        word_timings = []
        if "segments" in result:
            for segment in result["segments"]:
                if "words" in segment:
                    for word_info in segment["words"]:
                        word_timings.append({
                            "word": word_info["word"].strip(),
                            "start_ms": int(word_info["start"] * 1000),
                            "end_ms": int(word_info["end"] * 1000)
                        })
        
        return word_timings
        
    except ImportError:
        logging.warning("Whisper not available, falling back to speech_recognition")
        return _get_word_level_timestamps_sr(audio_path, text)
    except Exception as e:
        logging.error(f"Whisper transcription failed: {e}")
        return _fallback_word_timing(text, 0, 5000)  # 5 second fallback

def _get_word_level_timestamps_sr(audio_path: str, text: str) -> List[Dict[str, Any]]:
    """Use speech_recognition with pocketsphinx for word-level alignment."""
    try:
        import speech_recognition as sr
        from pydub import AudioSegment
        
        # Convert to WAV if needed
        audio = AudioSegment.from_file(audio_path)
        
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            audio.export(temp_wav.name, format="wav")
            
            r = sr.Recognizer()
            with sr.AudioFile(temp_wav.name) as source:
                audio_data = r.record(source)
            
            # Try to get word-level timing with pocketsphinx
            try:
                # This requires pocketsphinx with word timing support
                result = r.recognize_sphinx(audio_data, show_all=True)
                if hasattr(result, 'words'):
                    word_timings = []
                    for word_info in result.words:
                        word_timings.append({
                            "word": word_info.word,
                            "start_ms": int(word_info.start_time * 1000),
                            "end_ms": int(word_info.end_time * 1000)
                        })
                    return word_timings
            except:
                pass
            
            os.unlink(temp_wav.name)
            
    except ImportError:
        logging.warning("speech_recognition not available")
    except Exception as e:
        logging.error(f"Speech recognition failed: {e}")
    
    # Fallback to estimated timing
    duration_ms = _get_audio_duration_ms(audio_path)
    return _fallback_word_timing(text, 0, duration_ms)

def _get_audio_duration_ms(audio_path: str) -> int:
    """Get audio duration in milliseconds."""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(audio_path)
        return len(audio)
    except:
        try:
            import librosa
            y, sr = librosa.load(audio_path)
            return int(len(y) / sr * 1000)
        except:
            return 5000  # 5 second fallback

def _fallback_word_timing(text: str, start_ms: int, duration_ms: int) -> List[Dict[str, Any]]:
    """Fallback word timing based on speech rate (more accurate than character count)."""
    words = text.split()
    if not words:
        return []
    
    # Average speaking rate: 150-200 words per minute
    # Use 175 WPM as baseline, adjust for text complexity
    avg_wpm = 175
    
    # Adjust WPM based on text characteristics
    avg_word_length = sum(len(w) for w in words) / len(words)
    if avg_word_length > 6:  # Complex words
        avg_wpm *= 0.8
    elif avg_word_length < 4:  # Simple words
        avg_wpm *= 1.2
    
    # Calculate timing
    total_speaking_time_ms = (len(words) / avg_wpm) * 60 * 1000
    
    # If calculated time exceeds available time, adjust
    if total_speaking_time_ms > duration_ms * 0.9:  # Leave 10% buffer
        time_per_word = (duration_ms * 0.9) / len(words)
    else:
        time_per_word = total_speaking_time_ms / len(words)
    
    word_timings = []
    current_time = start_ms
    
    for word in words:
        # Adjust timing based on word characteristics
        word_duration = time_per_word
        if any(p in word for p in '.!?;:'):
            word_duration *= 1.3  # Pause for punctuation
        elif len(word) > 8:
            word_duration *= 1.2  # Longer words take more time
        
        word_timings.append({
            "word": word,
            "start_ms": int(current_time),
            "end_ms": int(current_time + word_duration)
        })
        current_time += word_duration
    
    return word_timings

def _create_subtitle_chunks(word_timings: List[Dict[str, Any]], max_words_per_chunk: int = 6) -> List[Dict[str, Any]]:
    """Group words into subtitle chunks for optimal readability."""
    if not word_timings:
        return []
    
    chunks = []
    current_chunk_words = []
    chunk_start_ms = word_timings[0]["start_ms"]
    
    for i, word_timing in enumerate(word_timings):
        current_chunk_words.append(word_timing["word"])
        
        # Determine if we should break the chunk
        is_punctuation_break = any(p in word_timing["word"] for p in '.!?')
        is_comma_break = ',' in word_timing["word"] and len(current_chunk_words) >= 3
        is_max_words = len(current_chunk_words) >= max_words_per_chunk
        is_last_word = i == len(word_timings) - 1
        
        should_break = is_punctuation_break or is_comma_break or is_max_words or is_last_word
        
        if should_break:
            chunk_text = " ".join(current_chunk_words).strip()
            if chunk_text:
                # Ensure minimum display time (1 second per chunk)
                min_duration = 1000
                chunk_duration = word_timing["end_ms"] - chunk_start_ms
                end_time = word_timing["end_ms"]
                
                if chunk_duration < min_duration and not is_last_word:
                    end_time = chunk_start_ms + min_duration
                
                chunks.append({
                    "text": chunk_text,
                    "start_ms": chunk_start_ms,
                    "end_ms": end_time
                })
            
            # Reset for next chunk
            current_chunk_words = []
            if not is_last_word:
                chunk_start_ms = word_timings[i + 1]["start_ms"]
    
    return chunks

def generate_precise_subtitles(metadata_file: str, subtitle_file: str, use_whisper: bool = True):
    """
    Generates precise word-level subtitles using speech recognition for accurate timing.
    """
    logging.info(f"Reading audio metadata from: {metadata_file}")
    try:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            audio_metadata = json.load(f)
    except FileNotFoundError:
        logging.error(f"Metadata file not found: {metadata_file}")
        return
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in metadata file: {e}")
        return

    all_subtitles = []
    current_time_ms = 0

    for item in audio_metadata:
        try:
            duration_ms = int(item.get("duration_ms", 0))
            text = str(item.get("text", "")).strip()
            event_index = item.get("event_index")
            audio_path = item.get("file_path", "")

            if not text or duration_ms <= 0:
                current_time_ms += duration_ms
                continue

            # Get accurate word-level timestamps
            if use_whisper and os.path.exists(audio_path):
                logging.info(f"Using Whisper for precise timing on event {event_index}")
                word_timings = _get_word_level_timestamps_whisper(audio_path, text)
            elif os.path.exists(audio_path):
                logging.info(f"Using speech recognition for timing on event {event_index}")
                word_timings = _get_word_level_timestamps_sr(audio_path, text)
            else:
                logging.warning(f"Audio file not found: {audio_path}, using fallback timing")
                word_timings = _fallback_word_timing(text, 0, duration_ms)
            
            # Adjust word timings to absolute time
            for word_timing in word_timings:
                word_timing["start_ms"] += current_time_ms
                word_timing["end_ms"] += current_time_ms
            
            # Create subtitle chunks with precise timing
            subtitle_chunks = _create_subtitle_chunks(word_timings)
            
            # Add chunks to subtitles
            for i, chunk in enumerate(subtitle_chunks):
                all_subtitles.append({
                    "event_index": event_index,
                    "chunk_index": i,
                    "start_ms": chunk["start_ms"],
                    "end_ms": chunk["end_ms"],
                    "text": chunk["text"],
                    "word_count": len(chunk["text"].split()),
                    "source": "whisper" if use_whisper and os.path.exists(audio_path) else "fallback"
                })
            
            # If no chunks created, add full text as fallback
            if not subtitle_chunks:
                all_subtitles.append({
                    "event_index": event_index,
                    "chunk_index": 0,
                    "start_ms": current_time_ms,
                    "end_ms": current_time_ms + duration_ms,
                    "text": text,
                    "word_count": len(text.split()),
                    "source": "fallback"
                })
            
            current_time_ms += duration_ms
            
        except (ValueError, TypeError) as e:
            logging.warning(f"Skipping invalid metadata item {item}: {e}")
            continue

    logging.info(f"Generated {len(all_subtitles)} precise subtitle entries.")
    
    try:
        with open(subtitle_file, 'w', encoding='utf-8') as f:
            json.dump(all_subtitles, f, indent=2, ensure_ascii=False)
        logging.info(f"Precise subtitles successfully saved to: {subtitle_file}")
    except IOError as e:
        logging.error(f"Failed to save subtitles: {e}")

# Backward compatibility
def generate_simple_subtitles(metadata_file: str, subtitle_file: str):
    """Legacy function for backward compatibility."""
    generate_precise_subtitles(metadata_file, subtitle_file, use_whisper=True)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate sentence-level subtitles from audio metadata.")
    parser.add_argument("metadata_file", help="Path to the input audio metadata JSON file.")
    parser.add_argument("subtitle_file", help="Path for the output subtitle JSON file.")
    args = parser.parse_args()

    generate_simple_subtitles(args.metadata_file, args.subtitle_file)
