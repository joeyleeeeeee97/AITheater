import os
import yaml
import sys

# Ensure the project root is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.video_generator import VideoGenerator

def create_layout_preview(config_path="layout.yaml"):
    """
    Generates a static image preview by directly calling the VideoGenerator's
    scene creation method, ensuring the preview is always 1:1 with the video.
    """
    print("--- Generating Layout Preview using VideoGenerator ---")
    
    # --- Load Config ---
    print(f"Loading layout configuration from: {config_path}")
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"ERROR: Configuration file not found at {config_path}")
        return

    # --- Use VideoGenerator to create a scene ---
    # Initialize the generator, which loads all necessary configs
    video_gen = VideoGenerator(config_path=config_path)

    # Define an example scenario to preview
    example_scenario = {
        "duration": 1, # Duration for the clip, 1 second is enough for a frame
        "leader_id": 3,
        "speaking_id": 3,
        "proposed_team_info": {
            "team": [3, 1, 5],
            "duration": 1 # This duration is for the text clip itself
        },
        "history_lines": [
            "Quest 1 [0, 2, 4] -> SUCCESS",
            "Quest 2 [1, 3, 5, 6] -> FAIL"
        ]
    }
    
    print("Creating a preview scene with an example leader, speaker, and proposal...")
    # Create a single, representative scene clip
    # We need a mock role_map for the preview to work
    mock_role_map = {str(i): "ROLE" for i in range(7)}
    preview_clip = video_gen._create_scene_clip(
        duration=example_scenario["duration"],
        leader_id=example_scenario["leader_id"],
        speaking_id=example_scenario["speaking_id"],
        proposed_team_info=example_scenario["proposed_team_info"],
        history_lines=example_scenario["history_lines"],
        game_phase="mvp", # Show the MVP name format
        role_map=mock_role_map
    )

    # --- Save the preview image ---
    output_path = config.get("output_preview_path", "outputs/layout_preview.png")
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    print(f"Saving frame to: {output_path}")
    preview_clip.save_frame(output_path)
    
    print("\nSuccess! Layout preview has been updated using the main video logic.")


if __name__ == "__main__":
    # Since this script now depends on the main video generator,
    # we ensure any potential import errors are caught gracefully.
    try:
        from moviepy.editor import *
    except ImportError:
        print("ERROR: Missing dependencies. Please run:")
        print("pip install moviepy==1.0.3 Pillow==9.5.0 PyYAML requests numpy")
    else:
        create_layout_preview()