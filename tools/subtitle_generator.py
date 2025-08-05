import json
import os
import logging

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def group_words_into_lines(words: list, max_words_per_line: int = 10) -> list:
    """Groups words into subtitle lines with start and end times."""
    if not words:
        return []

    lines = []
    current_line = []
    for i, word_info in enumerate(words):
        current_line.append(word_info)
        
        # Group into lines of `max_words_per_line` or if it's the last word
        if len(current_line) >= max_words_per_line or i == len(words) - 1:
            start_time = current_line[0]['time_ms']
            # The end time for a line is the start time of the next word, or the end of the audio clip
            # For simplicity, we'll make the end time the start of the last word in the line.
            # A more accurate end time would require knowing the duration of the last word.
            end_time = current_line[-1]['time_ms'] 
            text = " ".join([w['word'] for w in current_line])
            
            lines.append({
                "text": text,
                "start_ms": start_time,
                "end_ms": end_time + 500  # Add a small buffer to the end time
            })
            current_line = []
            
    return lines

def main(metadata_file: str, subtitle_file: str):
    """Generates subtitles from the audio metadata file."""
    logging.info(f"Reading audio metadata from: {metadata_file}")
    try:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            audio_metadata = json.load(f)
    except FileNotFoundError:
        logging.error(f"Audio metadata file not found: {metadata_file}")
        return

    all_subtitles = []
    global_time_offset = 0

    for event in audio_metadata:
        event_index = event.get("event_index")
        words = event.get("words", [])
        duration_ms = event.get("duration_ms", 0)

        if not words:
            logging.warning(f"No word timings found for event {event_index}. Skipping.")
            global_time_offset += duration_ms # Still need to account for its duration
            continue

        lines = group_words_into_lines(words)

        for line in lines:
            # Make timestamps global relative to the start of the whole video
            line['start_ms'] += global_time_offset
            line['end_ms'] += global_time_offset
            all_subtitles.append(line)
            
        # Add the duration of the current event to the offset for the next one
        global_time_offset += duration_ms

    logging.info(f"Generated {len(all_subtitles)} subtitle lines.")

    with open(subtitle_file, 'w', encoding='utf-8') as f:
        json.dump(all_subtitles, f, indent=2)

    logging.info(f"Subtitles successfully saved to: {subtitle_file}")


if __name__ == "__main__":
    output_dir = "outputs"
    metadata_files = sorted([f for f in os.listdir(output_dir) if f.startswith("audio_metadata") and f.endswith(".json")])

    if not metadata_files:
        print("Error: No metadata files found in the 'outputs' directory.")
    else:
        latest_metadata = os.path.join(output_dir, metadata_files[-1])
        
        print(f"Using metadata: {latest_metadata}")

        # Default output path
        subtitle_path = os.path.join(output_dir, "subtitles.json")

        main(latest_metadata, subtitle_path)