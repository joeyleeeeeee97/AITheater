#!/usr/bin/env python3
"""
Test script specifically for avatar highlighting functionality.
"""

import json
import logging
from tools.subtitle_generator import generate_precise_subtitles
from tools.video_generator import VideoGenerator

def test_avatar_highlighting():
    """Test avatar highlighting with specific player speech events."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    
    logger.info("🧪 Testing avatar highlighting with player speech events...")
    
    # Read full metadata
    with open("outputs/audio_metadata.json", 'r') as f:
        full_metadata = json.load(f)
    
    # Find events with numeric player_ids
    player_events = []
    for item in full_metadata:
        player_id = item.get("player_id")
        if isinstance(player_id, str) and player_id.isdigit():
            player_events.append(item)
            if len(player_events) >= 3:  # Test with 3 player events
                break
    
    if not player_events:
        logger.error("No player speech events found!")
        return False
    
    logger.info(f"Found {len(player_events)} player speech events:")
    for event in player_events:
        logger.info(f"  Event {event['event_index']}: Player {event['player_id']} - '{event['text'][:50]}...'")
    
    # Create test metadata file
    test_metadata_file = "outputs/avatar_test_metadata.json"
    with open(test_metadata_file, 'w') as f:
        json.dump(player_events, f, indent=2)
    
    # Generate subtitles
    subtitle_file = "outputs/avatar_test_subtitles.json"
    generate_precise_subtitles(test_metadata_file, subtitle_file, use_whisper=True)
    
    # Create test script data (player events should trigger highlighting)
    test_script = []
    for i, event in enumerate(player_events):
        test_script.append({
            "event_index": i,
            "event_type": "PLAYER_SPEECH",
            "player_id": event["player_id"],
            "text": event["text"]
        })
    
    script_file = "outputs/avatar_test_script.json"
    with open(script_file, 'w') as f:
        json.dump(test_script, f, indent=2)
    
    # Generate video
    output_video = "outputs/avatar_highlight_test.mp4"
    generator = VideoGenerator(config_path="data/layout.yaml")
    
    success = generator.render_video(
        script_path=script_file,
        metadata_path=test_metadata_file,
        subtitle_path=subtitle_file,
        output_path=output_video,
        max_events=len(player_events)
    )
    
    if success:
        logger.info(f"🎉 Avatar highlight test video generated: {output_video}")
        logger.info("Check the video to see if player avatars are highlighted with gold borders!")
        return True
    else:
        logger.error("❌ Avatar highlight test failed")
        return False

if __name__ == "__main__":
    test_avatar_highlighting()