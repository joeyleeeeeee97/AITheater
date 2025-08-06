#!/usr/bin/env python3
"""
Enhanced video generation script with precise subtitle timing.
This script demonstrates how to use the improved video generator.
"""

import os
import sys
import logging
from tools.subtitle_generator import generate_precise_subtitles
from tools.video_generator import VideoGenerator

def main():
    """Generate video with precise subtitles."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    
    # File paths
    script_file = "outputs/final_script.json"
    metadata_file = "outputs/audio_metadata.json"
    subtitle_file = "outputs/precise_subtitles.json"
    output_video = "outputs/enhanced_video.mp4"
    config_file = "data/layout.yaml"
    
    # Check if input files exist
    required_files = [script_file, metadata_file, config_file]
    missing_files = [f for f in required_files if not os.path.exists(f)]
    
    if missing_files:
        logger.error(f"Missing required files: {missing_files}")
        return False
    
    try:
        # Step 1: Generate precise subtitles using Whisper
        logger.info("🔄 Generating precise subtitles with Whisper...")
        generate_precise_subtitles(metadata_file, subtitle_file, use_whisper=True)
        
        if not os.path.exists(subtitle_file):
            logger.error("Failed to generate subtitle file")
            return False
        
        logger.info(f"✅ Precise subtitles saved to: {subtitle_file}")
        
        # Step 2: Generate video with enhanced generator
        logger.info("🔄 Generating video with enhanced generator...")
        generator = VideoGenerator(config_path=config_file)
        
        success = generator.render_video(
            script_path=script_file,
            metadata_path=metadata_file,
            subtitle_path=subtitle_file,
            output_path=output_video,
            max_events=None  # Process all events
        )
        
        if success:
            logger.info(f"🎉 Enhanced video generated successfully: {output_video}")
            
            # Show video info
            if os.path.exists(output_video):
                file_size = os.path.getsize(output_video) / (1024 * 1024)  # MB
                logger.info(f"📊 Video file size: {file_size:.1f} MB")
            
            return True
        else:
            logger.error("❌ Video generation failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error during video generation: {e}")
        import traceback
        traceback.print_exc()
        return False

def generate_test_video(max_events: int = 5):
    """Generate a test video with limited events for quick testing."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    
    logger.info(f"🧪 Generating test video with {max_events} events...")
    
    # File paths for test
    script_file = "outputs/final_script.json"
    metadata_file = "outputs/audio_metadata.json"
    subtitle_file = "outputs/test_subtitles.json"
    output_video = f"outputs/test_video_{max_events}_events.mp4"
    config_file = "data/layout.yaml"
    
    try:
        # Create limited metadata for faster processing
        import json
        with open(metadata_file, 'r') as f:
            full_metadata = json.load(f)
        
        # Limit metadata to max_events
        limited_metadata = full_metadata[:max_events]
        limited_metadata_file = f"outputs/limited_metadata_{max_events}.json"
        
        with open(limited_metadata_file, 'w') as f:
            json.dump(limited_metadata, f, indent=2)
        
        logger.info(f"Created limited metadata with {len(limited_metadata)} events")
        
        # Generate subtitles for limited events only
        generate_precise_subtitles(limited_metadata_file, subtitle_file, use_whisper=True)
        
        # Generate video
        generator = VideoGenerator(config_path=config_file)
        success = generator.render_video(
            script_path=script_file,
            metadata_path=limited_metadata_file,
            subtitle_path=subtitle_file,
            output_path=output_video,
            max_events=max_events
        )
        
        if success:
            logger.info(f"🎉 Test video generated: {output_video}")
            return True
        else:
            logger.error("❌ Test video generation failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test generation error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate enhanced video with precise subtitles")
    parser.add_argument("--test", type=int, metavar="N", help="Generate test video with N events")
    parser.add_argument("--full", action="store_true", help="Generate full video")
    args = parser.parse_args()
    
    if args.test:
        success = generate_test_video(args.test)
    elif args.full:
        success = main()
    else:
        # Default: generate test video with 5 events
        print("No option specified. Generating test video with 5 events.")
        print("Use --full for complete video or --test N for N events")
        success = generate_test_video(5)
    
    sys.exit(0 if success else 1)