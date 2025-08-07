import os
import subprocess
import sys
from datetime import datetime

# --- Configuration ---
PYTHON_EXEC = sys.executable # Use the same python that is running this script
# Get the absolute path to the project root directory (which is one level up from this script)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BASE_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")

def run_step(command: list, step_name: str):
    """
    Runs a command as a subprocess, streams its output in real-time,
    and handles errors.
    The script to run (command[1]) is assumed to be relative to the project root.
    """
    print(f"--- Running Step: {step_name} ---")
    
    # Make the script path absolute
    command[1] = os.path.join(PROJECT_ROOT, command[1])
    
    print(f"Executing command: {' '.join(command)}\n")
    
    try:
        # Use Popen to stream output in real-time
        # Set the current working directory to the project root
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Redirect stderr to stdout
            text=True,
            encoding='utf-8',
            bufsize=1, # Line-buffered
            cwd=PROJECT_ROOT 
        )

        # Stream the output line by line
        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                print(line, end='', flush=True)
        
        # Wait for the process to finish and get the exit code
        process.wait() 
        
        # Final check on the return code
        if process.returncode != 0:
            print(f"\n--- ERROR: Step '{step_name}' failed with return code {process.returncode}. ---")
            print("--- Aborting pipeline. ---")
            return False

        print(f"\n--- Step '{step_name}' completed successfully. ---\n")
        return True

    except FileNotFoundError:
        print(f"--- ERROR: Command not found for step '{step_name}' ---")
        print(f"The first part of the command '{command[0]}' was not found.")
        print("Please ensure the script paths are correct relative to the project root.")
        return False
    except Exception as e:
        print(f"\nAn unexpected error occurred during step '{step_name}': {e}")
        return False


def main(input_log_file: str, output_video_file: str, stt_engine: str = 'google'):
    """Runs the full video generation pipeline."""
    
    # --- Path Setup ---
    # Ensure the base output directory exists
    os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)
    
    # Define paths for all intermediate and final files
    # Make all paths absolute from the project root
    script_file = os.path.join(BASE_OUTPUT_DIR, "final_script.json")
    audio_dir = os.path.join(BASE_OUTPUT_DIR, "generated_audio")
    metadata_file = os.path.join(BASE_OUTPUT_DIR, "audio_metadata.json")
    subtitle_file = os.path.join(BASE_OUTPUT_DIR, "subtitles.json")
    
    # Ensure the audio directory is clean
    os.makedirs(audio_dir, exist_ok=True)
    for f in os.listdir(audio_dir):
        os.remove(os.path.join(audio_dir, f))
    print(f"Cleaned audio directory: {audio_dir}")

    # --- Pipeline Steps ---
    
    # 1. Script Writing (Skipped, assuming it's already generated)
    # cmd_script = [
    #     PYTHON_EXEC, "tools/script_writer.py",
    #     input_log_file,
    #     script_file
    # ]
    # if not run_step(cmd_script, "Script Generation"):
    #     return
    print("--- Skipping Step: Script Generation (using existing file) ---\\n")

    # 2. Audio Generation
    cmd_audio = [
        PYTHON_EXEC, "tools/audio_generator.py",
        script_file,
        audio_dir,
        metadata_file
    ]
    if not run_step(cmd_audio, "Audio Generation"):
        return

    # 3. Subtitle Generation
    cmd_subtitle = [
        PYTHON_EXEC, "tools/subtitle_generator.py",
        metadata_file,
        subtitle_file,
        "--stt_engine", stt_engine
    ]
    if not run_step(cmd_subtitle, "Subtitle Generation"):
        return

    # 4. Video Generation
    cmd_video = [
        PYTHON_EXEC, "tools/video_generator.py",
        script_file,
        metadata_file,
        subtitle_file,
        output_video_file
    ]
    if not run_step(cmd_video, "Video Generation"):
        return
        
    print("--- Pipeline Finished ---")
    print(f"✅ Final video successfully generated at: {output_video_file}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="One-click script to run the entire AI Theater video generation pipeline.")
    parser.add_argument("input_log", help="Path to the input game log file (e.g., outputs/game_output.log).")
    parser.add_argument("output_video", nargs='?', help="Path for the final output video file (e.g., outputs/final_video.mp4).")
    parser.add_argument("--stt_engine", default="google", choices=["google", "whisper"], help="The STT engine to use for generating subtitles.")
    args = parser.parse_args()

    # If output_video is not provided, create a default name
    if not args.output_video:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"final_video_{timestamp}.mp4"
        final_output_path = os.path.join(BASE_OUTPUT_DIR, output_filename)
    else:
        # If the user provides a relative path, make it absolute from the CWD
        # This is the standard behavior for command-line arguments.
        final_output_path = os.path.abspath(args.output_video)

    # Also ensure the input log path is absolute
    absolute_input_log = os.path.abspath(args.input_log)

    main(absolute_input_log, final_output_path, args.stt_engine)
