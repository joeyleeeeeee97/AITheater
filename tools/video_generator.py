import os
import yaml
from moviepy.editor import *
from PIL import Image
import numpy as np
import json

class VideoGenerator:
    def __init__(self, config_path="layout.yaml"):
        print("Initializing AI Director...")
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Load configs into attributes for easy access
        self.layout = self.config
        self.resolution = self.layout.get("resolution", [1920, 1080])
        self.font_path = self.layout.get("font_path")
        self.avatar_dir = self.layout.get("avatar_dir", "assets/player_avatars")
        
        # Create a quick lookup map for avatars
        player_avatars_config = self.layout.get("player_avatars", [])
        self.avatar_map = {p["player_id"]: p["avatar_file"] for p in player_avatars_config}

    def _create_player_avatar(self, player_id, is_speaking=False):
        """Creates a single, complete avatar element (border, image, tag)."""
        player_info = next((p for p in self.layout.get("player_positions", []) if p['player_id'] == player_id), None)
        if not player_info:
            return []

        pos = player_info.get("position")
        avatar_cfg = self.layout.get("avatar", {})
        model_tag_cfg = self.layout.get("model_tag", {})

        # Avatar Image
        avatar_filename = self.avatar_map.get(player_id, "default.png")
        avatar_path = os.path.join(self.avatar_dir, avatar_filename)
        if not os.path.exists(avatar_path):
            print(f"Warning: Avatar for player {player_id} not found at {avatar_path}. Skipping.")
            return []

        with Image.open(avatar_path) as img:
            img_rgba = img.convert("RGBA")
            avatar_array = np.array(img_rgba)
        
        avatar_clip = (ImageClip(avatar_array)
                       .resize(width=avatar_cfg.get("size")[0], height=avatar_cfg.get("size")[1])
                       .set_position(pos))

        # Border
        border_width = avatar_cfg.get("border_width", 0)
        border_color = avatar_cfg.get("border_color_speaking") if is_speaking else avatar_cfg.get("border_color_default")
        border_size = (avatar_cfg.get("size")[0] + 2 * border_width, avatar_cfg.get("size")[1] + 2 * border_width)
        border_pos = (pos[0] - border_width, pos[1] - border_width)
        border_clip = (ColorClip(size=border_size, color=border_color)
                       .set_position(border_pos))

        # Player ID Tag
        id_text = f"Player {player_id}"
        id_offset = model_tag_cfg.get("offset_from_avatar", [0, 0])
        id_pos = (pos[0] + id_offset[0], pos[1] + id_offset[1])
        id_tag_clip = (TextClip(id_text, fontsize=model_tag_cfg.get("font_size"),
                                  color=model_tag_cfg.get("color"), font=self.font_path)
                         .set_position(id_pos))

        return [border_clip, avatar_clip, id_tag_clip]

    def _create_info_panel_clip(self, event, duration):
        """Creates a styled information panel clip for a given event's summary."""
        panel_cfg = self.layout.get("info_panel", {})
        # Use a default style, assuming all summaries are presented similarly.
        # The style can be customized further in layout.yaml if needed.
        style = panel_cfg.get("system_message_style", {})
        
        text = event.get("summary") # Always use the summary field
        if not text: return None

        bg_clip = (ColorClip(size=panel_cfg.get("size"), color=panel_cfg.get("background_color"))
                   .set_opacity(panel_cfg.get("opacity"))
                   .set_duration(duration))

        text_clip = (TextClip(text, fontsize=style.get("font_size"), color=style.get("text_color"),
                              font=self.font_path, size=(panel_cfg.get("size")[0] - 40, None),
                              method='caption', align=style.get("text_alignment"))
                     .set_duration(duration))

        return CompositeVideoClip([bg_clip, text_clip], size=panel_cfg.get("size")).set_position(panel_cfg.get("position"))

    def _create_subtitle_clip(self, subtitle_info):
        """Creates a styled subtitle clip."""
        subtitle_cfg = self.layout.get("subtitle_area", {})
        
        duration = (subtitle_info['end_ms'] - subtitle_info['start_ms']) / 1000.0
        text = subtitle_info['text']

        bg_clip = (ColorClip(size=subtitle_cfg.get("size"), color=subtitle_cfg.get("background_color"))
                   .set_opacity(subtitle_cfg.get("opacity"))
                   .set_duration(duration))

        text_clip = (TextClip(text, fontsize=subtitle_cfg.get("font_size"), color=subtitle_cfg.get("text_color"),
                              font=self.font_path, size=(subtitle_cfg.get("size")[0] - 40, None),
                              method='caption', align=subtitle_cfg.get("text_alignment"))
                     .set_duration(duration))

        return CompositeVideoClip([bg_clip, text_clip], size=subtitle_cfg.get("size")).set_position(subtitle_cfg.get("position"))

    def render_video(self, script_path, metadata_path, subtitle_path, output_path, max_events=None):
        print("--- Starting Video Generation ---")
        
        with open(script_path, 'r') as f:
            script_data = json.load(f)
        with open(metadata_path, 'r') as f:
            metadata = {item['event_index']: item for item in json.load(f)}
        
        # Subtitles are optional
        subtitles = []
        if subtitle_path and os.path.exists(subtitle_path):
            with open(subtitle_path, 'r') as f:
                subtitles = json.load(f)
        else:
            print("Warning: Subtitle file not found or not provided. Rendering without subtitles.")

        if max_events:
            script_data = script_data[:max_events]
            print(f"Rendering a partial video with the first {max_events} events.")

        # --- Calculate Total Duration from Metadata ---
        total_duration = 0
        for i, _ in enumerate(script_data):
            audio_info = metadata.get(i)
            if audio_info:
                total_duration += audio_info["duration_ms"] / 1000.0
            else:
                # If an event in the script has no audio, it won't be in the video.
                print(f"Warning: No audio metadata for event {i}. It will be skipped in the video.")

        # --- Create Base Scene ---
        print("Composing base scene with all players...")
        background_clip = ImageClip(self.layout.get("background_image")).resize(width=self.resolution[0], height=self.resolution[1]).set_duration(total_duration)
        
        base_player_elements = []
        for player_info in self.layout.get("player_positions", []):
            player_elements = self._create_player_avatar(player_info['player_id'], is_speaking=False)
            for clip in player_elements:
                base_player_elements.append(clip.set_duration(total_duration))
        
        # --- Create Dynamic Clips & Audio Track ---
        print("Generating dynamic event layers (highlights, panels)...")
        dynamic_clips = []
        audio_clips = []
        current_time = 0

        for i, event in enumerate(script_data):
            audio_info = metadata.get(i)
            if not audio_info:
                continue # Skip events that have no audio
            
            duration = audio_info["duration_ms"] / 1000.0
            audio_clips.append(AudioFileClip(audio_info["file_path"]).set_start(current_time))
            
            # Add speaking highlight ONLY for player speech events
            if event["event_type"] == "PLAYER_SPEECH":
                speaker_id = event.get("player_id")
                if speaker_id is not None:
                    highlight_elements = self._create_player_avatar(speaker_id, is_speaking=True)
                    for clip in highlight_elements:
                        dynamic_clips.append(clip.set_start(current_time).set_duration(duration))

            # Add info panel for all events that have a summary
            info_panel_clip = self._create_info_panel_clip(event, duration)
            if info_panel_clip:
                dynamic_clips.append(info_panel_clip.set_start(current_time))

            current_time += duration

        # --- Add Subtitle Clips ---
        if subtitles:
            print("Adding subtitle layer...")
            for sub in subtitles:
                start_time = sub['start_ms'] / 1000.0
                # Ensure subtitles don't go past the total duration
                if start_time < total_duration:
                    subtitle_clip = self._create_subtitle_clip(sub)
                    dynamic_clips.append(subtitle_clip.set_start(start_time))


        # --- Final Composition ---
        print("Composing final video...")
        final_audio = CompositeAudioClip(audio_clips)
        
        final_video = CompositeVideoClip([background_clip] + base_player_elements + dynamic_clips, size=self.resolution)
        final_video = final_video.set_audio(final_audio).set_duration(total_duration)

        print(f"Rendering video... Total duration: {total_duration:.2f}s")
        final_video.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24)
        print(f"--- Video generation complete! Saved to {output_path} ---")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a video from a script, metadata, and subtitles.")
    parser.add_argument("script_file", help="Path to the input JSON script file (inside outputs/ dir).")
    parser.add_argument("metadata_file", help="Path to the audio metadata JSON file (inside outputs/ dir).")
    parser.add_argument("subtitle_file", help="Path to the subtitle JSON file (inside outputs/ dir).")
    parser.add_argument("output_file", help="Path for the output video file (inside outputs/ dir).")
    parser.add_argument("max_events", nargs='?', type=int, help="Optional: Maximum number of events to render.")
    args = parser.parse_args()

    output_dir = "outputs"
    
    # Prepend outputs/ directory to paths if they are not absolute
    script_path = args.script_file if os.path.isabs(args.script_file) else os.path.join(output_dir, args.script_file)
    metadata_path = args.metadata_file if os.path.isabs(args.metadata_file) else os.path.join(output_dir, args.metadata_file)
    subtitle_path = args.subtitle_file if os.path.isabs(args.subtitle_file) else os.path.join(output_dir, args.subtitle_file)
    output_path = args.output_file if os.path.isabs(args.output_file) else os.path.join(output_dir, args.output_file)

    if not os.path.exists(script_path) or not os.path.exists(metadata_path):
         print(f"Error: Ensure script file ({script_path}) and metadata file ({metadata_path}) exist.")
    else:
        print(f"Using script: {script_path}")
        print(f"Using metadata: {metadata_path}")
        if os.path.exists(subtitle_path):
            print(f"Using subtitles: {subtitle_path}")

        director = VideoGenerator()
        director.render_video(
            script_path=script_path,
            metadata_path=metadata_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            max_events=args.max_events
        )
