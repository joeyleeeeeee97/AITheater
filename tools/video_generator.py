import os
import yaml
from moviepy import *
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
import threading
from concurrent.futures import ThreadPoolExecutor
import traceback

class VideoGenerator:
    def __init__(self, config_path="layout.yaml"):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        self.logger.info("Initializing Enhanced Video Generator...")
        
        try:
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Config file not found: {config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML config: {e}")
        
        self.layout = self.config
        self.resolution = tuple(self.layout.get("resolution", [1920, 1080]))
        self.font_path = self.layout.get("font_path")
        self.avatar_dir = self.layout.get("avatar_dir", "assets/player_avatars")
        
        # Validate required paths
        if not self.font_path or not os.path.exists(self.font_path):
            raise FileNotFoundError(f"Font file not found: {self.font_path}")
        if not os.path.exists(self.avatar_dir):
            raise FileNotFoundError(f"Avatar directory not found: {self.avatar_dir}")
        
        player_avatars_config = self.layout.get("player_avatars", [])
        self.avatar_map = {p["player_id"]: p["avatar_file"] for p in player_avatars_config}

        # Thread-safe caches
        self.asset_cache = {}
        self.scene_cache = {}
        self.font_cache = {}
        self._cache_lock = threading.Lock()
        
        self._preload_assets()
        self.logger.info("Enhanced Video Generator initialized successfully.")

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Thread-safe font loading with error handling."""
        with self._cache_lock:
            if size not in self.font_cache:
                try:
                    self.font_cache[size] = ImageFont.truetype(self.font_path, size)
                except OSError as e:
                    self.logger.error(f"Failed to load font: {e}")
                    # Use default font as fallback
                    self.font_cache[size] = ImageFont.load_default()
            return self.font_cache[size]

    def _preload_assets(self):
        """Preload and cache all static assets with error handling."""
        try:
            # Load background
            bg_path = self.layout.get("background_image")
            if not bg_path or not os.path.exists(bg_path):
                raise FileNotFoundError(f"Background image not found: {bg_path}")
            
            self.asset_cache['background'] = ImageClip(bg_path).resized(
                new_size=self.resolution
            )
            
            self.asset_cache['players'] = {}
            avatar_cfg = self.layout.get("avatar", {})
            avatar_size = tuple(avatar_cfg.get("size", [75, 75]))
            border_width = avatar_cfg.get("border_width", 6)
            
            for player_info in self.layout.get("player_positions", []):
                p_id = player_info['player_id']
                pos = tuple(player_info.get("position", [0, 0]))
                self.asset_cache['players'][p_id] = {'pos': pos}

                # Load avatar with error handling
                avatar_filename = self.avatar_map.get(p_id, "default.png")
                avatar_path = os.path.join(self.avatar_dir, avatar_filename)
                
                try:
                    if os.path.exists(avatar_path):
                        avatar_img = Image.open(avatar_path).convert("RGBA").resize(avatar_size)
                        self.asset_cache['players'][p_id]['avatar_clip'] = (
                            ImageClip(np.array(avatar_img), duration=1)
                            .resized(new_size=avatar_size)
                            .with_position(pos)
                        )
                    else:
                        self.logger.warning(f"Avatar not found for player {p_id}: {avatar_path}")
                        # Create placeholder avatar
                        placeholder = Image.new('RGBA', avatar_size, (128, 128, 128, 255))
                        self.asset_cache['players'][p_id]['avatar_clip'] = (
                            ImageClip(np.array(placeholder), duration=1)
                            .resized(new_size=avatar_size)
                            .with_position(pos)
                        )
                except Exception as e:
                    self.logger.error(f"Failed to load avatar for player {p_id}: {e}")
                    continue

                # Create speaking border
                border_size = (avatar_size[0] + 2 * border_width, avatar_size[1] + 2 * border_width)
                border_pos = (pos[0] - border_width, pos[1] - border_width)
                border_color = avatar_cfg.get("border_color_speaking", [255, 215, 0])
                
                self.asset_cache['players'][p_id]['border_speaking'] = (
                    ColorClip(size=border_size, color=border_color, duration=1)
                    .with_position(border_pos)
                )
                
        except Exception as e:
            self.logger.error(f"Asset preloading failed: {e}")
            raise

    def _create_base_scene(self, duration: float) -> CompositeVideoClip:
        """Creates the static background scene with avatars for specified duration."""
        clips = [self.asset_cache['background'].with_duration(duration)]
        
        for p_id, assets in self.asset_cache['players'].items():
            if 'avatar_clip' in assets:
                clips.append(assets['avatar_clip'].with_duration(duration))
                
        return CompositeVideoClip(clips, size=self.resolution)
    
    def _create_subtitle_clips(self, subtitles: List[Dict], event_start_ms: int, event_duration_ms: int) -> List[TextClip]:
        """
        Creates a list of TextClips for all subtitle chunks within an event's timeframe.
        """
        clips = []
        event_end_ms = event_start_ms + event_duration_ms

        # Find all subtitles that overlap with the current event
        relevant_subtitles = [
            s for s in subtitles 
            if s['start_ms'] < event_end_ms and s['end_ms'] > event_start_ms
        ]

        if not relevant_subtitles:
            return []

        sub_cfg = self.layout.get("subtitle_area", {})
        font_size = sub_cfg.get("font_size", 36)
        text_color = sub_cfg.get("text_color", "white")
        box_size = sub_cfg.get("size", [1800, 100])
        position = sub_cfg.get("position", ["center", 950])

        for sub in relevant_subtitles:
            try:
                text = sub.get('text', '').strip()
                if not text:
                    continue

                # Calculate clip's start and duration relative to the event clip
                clip_start_sec = (sub['start_ms'] - event_start_ms) / 1000.0
                clip_duration_sec = (sub['end_ms'] - sub['start_ms']) / 1000.0

                # Ensure start time is not negative
                if clip_start_sec < 0:
                    clip_duration_sec += clip_start_sec
                    clip_start_sec = 0
                
                if clip_duration_sec <= 0:
                    continue

                self.logger.info(f"Creating subtitle clip: '{text}' at {clip_start_sec:.2f}s for {clip_duration_sec:.2f}s")

                subtitle_clip = TextClip(
                    text=text,
                    font_size=font_size,
                    color=text_color,
                    size=box_size,
                    method='caption'
                ).with_position(position).with_start(clip_start_sec).with_duration(clip_duration_sec)
                
                clips.append(subtitle_clip)

            except Exception as e:
                self.logger.error(f"Failed to create subtitle clip for text '{sub.get('text')}': {e}")
                continue
        
        return clips
    
    def _create_model_tag(self, player_id: int, duration: float) -> Optional[TextClip]:
        """Create model name tag under player avatar."""
        try:
            model_cfg = self.layout.get("model_tag", {})
            player_pos = self.asset_cache['players'][player_id]['pos']
            
            # Calculate text position
            offset = model_cfg.get("offset_from_avatar", [0, 95])
            text_pos = (player_pos[0] + offset[0], player_pos[1] + offset[1])
            
            # Create text (simple Player ID for now)
            text = f"Player {player_id}"
            
            # Ensure text position is within video bounds
            safe_x = max(10, min(text_pos[0] - 50, self.resolution[0] - 110))  # Center text under avatar
            safe_y = min(text_pos[1], self.resolution[1] - 60)  # Keep above bottom edge
            
            text_clip = TextClip(
                text=text,
                font_size=model_cfg.get("font_size", 24),  # Smaller for better fit
                color=model_cfg.get("color", "#E0E0E0"),
                size=(100, 40)  # Fixed size to prevent clipping
            ).with_position((safe_x, safe_y)).with_duration(duration)
            
            return text_clip
            
        except Exception as e:
            self.logger.warning(f"Failed to create model tag for player {player_id}: {e}")
            return None
    
    def _create_leader_tag(self, player_id: int, duration: float) -> Optional[TextClip]:
        """Create special red leader tag."""
        try:
            leader_cfg = self.layout.get("leader_tag", {})
            player_pos = self.asset_cache['players'][player_id]['pos']
            
            # Calculate text position
            offset = leader_cfg.get("offset_from_avatar", [-50, 95])
            text_pos = (player_pos[0] + offset[0], player_pos[1] + offset[1])
            
            # Create leader text
            text_format = leader_cfg.get("format", "Leader - Player {player_id}")
            text = text_format.format(player_id=player_id)
            
            text_clip = TextClip(
                text=text,
                font_size=leader_cfg.get("font_size", 22),  # Smaller for longer text
                color=leader_cfg.get("color", "#FF4136"),  # Red
                size=(300, 50)  # Wider for "Leader - Player X" text
            ).with_position((max(10, min(text_pos[0], self.resolution[0] - 310)), 
                           min(text_pos[1], self.resolution[1] - 60))).with_duration(duration)  # Ensure within bounds
            
            return text_clip
            
        except Exception as e:
            self.logger.warning(f"Failed to create leader tag for player {player_id}: {e}")
            return None
    
    def _determine_leader(self, event: Dict[str, Any]) -> Optional[int]:
        """Determine if there's a leader from the event context."""
        # Look for leader information in the event text or context
        text = event.get("text", "").lower()
        
        # Simple pattern matching for leader detection
        if "leader" in text:
            # Try to extract player number mentioned with leader
            import re
            leader_match = re.search(r"player (\d+).*leader", text)
            if leader_match:
                return int(leader_match.group(1))
        
        return None

    def render_video(self, script_path: str, metadata_path: str, subtitle_path: str, 
                    output_path: str, max_events: Optional[int] = None) -> bool:
        """Render video with enhanced error handling and precise subtitle timing."""
        self.logger.info("Starting Enhanced Video Generation")
        
        try:
            # Load and validate input files
            script_data = self._load_json_file(script_path)
            metadata_list = self._load_json_file(metadata_path)
            subtitles = self._load_json_file(subtitle_path)
            
            # Convert metadata to dict for faster lookup
            metadata = {item['event_index']: item for item in metadata_list}
            
            if max_events:
                script_data = script_data[:max_events]
                self.logger.info(f"Processing {max_events} events (limited)")
            
            # Process events and create clips with proper timing
            final_clips = []
            current_time_ms = 0
            
            for i, event in enumerate(script_data):
                try:
                    audio_info = metadata.get(i)
                    if not audio_info or audio_info.get("duration_ms", 0) <= 0:
                        continue

                    duration_ms = audio_info["duration_ms"]
                    duration_sec = duration_ms / 1000.0
                    
                    # Load audio with error handling
                    audio_path = audio_info.get("file_path", "")
                    if not os.path.exists(audio_path):
                        self.logger.warning(f"Audio file not found: {audio_path}")
                        current_time_ms += duration_ms
                        continue
                        
                    audio_clip = AudioFileClip(audio_path)
                    
                    # Create base scene for this event
                    base_clip = self.asset_cache['background'].with_duration(duration_sec)
                    visual_layers = [base_clip]
                    
                    # Determine leader for this event
                    leader_id = self._determine_leader(event)
                    
                    # Add all player avatars with text labels
                    for p_id, assets in self.asset_cache['players'].items():
                        if 'avatar_clip' in assets:
                            avatar = assets['avatar_clip'].with_duration(duration_sec)
                            visual_layers.append(avatar)
                            
                            # Add appropriate text label (leader or normal)
                            if leader_id is not None and p_id == leader_id:
                                # Add red leader tag
                                leader_tag = self._create_leader_tag(p_id, duration_sec)
                                if leader_tag:
                                    visual_layers.append(leader_tag)
                            else:
                                # Add normal model tag
                                model_tag_text = self._create_model_tag(p_id, duration_sec)
                                if model_tag_text:
                                    visual_layers.append(model_tag_text)
                    
                    # Add speaking indicators with proper layering
                    speaking_id = self._get_speaking_player_id(event)
                    if speaking_id is not None and speaking_id in self.asset_cache['players']:
                        player_assets = self.asset_cache['players'][speaking_id]
                        
                        # Add speaking border OVER the avatar
                        if 'border_speaking' in player_assets:
                            border_clip = player_assets['border_speaking'].with_duration(duration_sec)
                            visual_layers.append(border_clip)
                        
                        # Re-add speaking player's avatar on top of border
                        if 'avatar_clip' in player_assets:
                            speaking_avatar = player_assets['avatar_clip'].with_duration(duration_sec)
                            visual_layers.append(speaking_avatar)
                    
                    # Add subtitle clips for this event
                    subtitle_clips = self._create_subtitle_clips(subtitles, current_time_ms, duration_ms)
                    if subtitle_clips:
                        self.logger.info(f"Adding {len(subtitle_clips)} subtitle clips to visual layers for event {i}")
                        visual_layers.extend(subtitle_clips)

                    # Composite all layers
                    event_clip = CompositeVideoClip(visual_layers, size=self.resolution)
                    event_clip = event_clip.with_duration(duration_sec).with_audio(audio_clip)
                    final_clips.append(event_clip)
                    
                    current_time_ms += duration_ms
                    
                except Exception as e:
                    self.logger.error(f"Failed to process event {i}: {e}")
                    traceback.print_exc()
                    continue

            if not final_clips:
                self.logger.error("No valid clips were generated")
                return False

            self.logger.info(f"Concatenating {len(final_clips)} event clips...")
            final_video = concatenate_videoclips(final_clips)

            # Render with optimized settings
            self.logger.info(f"Rendering video... Duration: {final_video.duration:.2f}s")
            
            try:
                # Determine optimal codec and settings
                render_settings = self._get_optimal_render_settings()
                
                final_video.write_videofile(
                    output_path, 
                    fps=24, 
                    codec=render_settings['video_codec'], 
                    audio_codec=render_settings['audio_codec'], 
                    threads=render_settings['threads'],
                    preset=render_settings['preset'],
                    logger='bar',
                    temp_audiofile='temp-audio.m4a',
                    remove_temp=True
                )
                
                self.logger.info(f"Video generation complete! Saved to {output_path}")
                return True
                
            except Exception as render_error:
                self.logger.error(f"Rendering failed: {render_error}")
                return False
                
            finally:
                # Always cleanup resources
                self._cleanup_resources(final_video, final_clips)
            
        except Exception as e:
            self.logger.error(f"Video generation failed: {e}")
            traceback.print_exc()
            return False
    
    def _load_json_file(self, filepath: str) -> Any:
        """Load and validate JSON file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {filepath}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {filepath}: {e}")
    
    def _get_speaking_player_id(self, event: Dict[str, Any]) -> Optional[int]:
        """Extract speaking player ID with error handling."""
        try:
            player_id_str = event.get("player_id")
            if player_id_str is not None:
                # Handle both PLAYER_SPEECH events and direct player_id
                if isinstance(player_id_str, str) and player_id_str.isdigit():
                    return int(player_id_str)
                elif isinstance(player_id_str, int):
                    return player_id_str
            # For NARRATOR or other non-numeric IDs, no highlighting
        except (ValueError, TypeError):
            pass
        return None
    
    def _get_optimal_render_settings(self) -> Dict[str, Any]:
        """Determine optimal rendering settings based on system capabilities."""
        import platform
        
        settings = {
            'video_codec': 'libx264',
            'audio_codec': 'aac',
            'threads': min(8, os.cpu_count() or 4),
            'preset': 'medium'
        }
        
        system = platform.system()
        
        # Use hardware acceleration on macOS if available
        if system == 'Darwin':
            try:
                # Test if videotoolbox is available
                import subprocess
                result = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], 
                                      capture_output=True, text=True, timeout=5)
                if 'h264_videotoolbox' in result.stdout:
                    settings['video_codec'] = 'h264_videotoolbox'
                    settings['preset'] = 'fast'
            except:
                pass  # Fallback to libx264
        
        # Adjust threads based on system load
        try:
            import psutil
            available_memory_gb = psutil.virtual_memory().available / (1024**3)
            if available_memory_gb < 4:
                settings['threads'] = min(4, settings['threads'])
                settings['preset'] = 'fast'
            elif available_memory_gb > 16:
                settings['threads'] = min(12, os.cpu_count() or 8)
        except ImportError:
            pass  # psutil not available, use defaults
        
        self.logger.info(f"Using render settings: {settings}")
        return settings
    
    def _cleanup_resources(self, final_video, final_clips):
        """Clean up video resources to prevent memory leaks."""
        try:
            if final_video:
                final_video.close()
                
            if final_clips:
                for clip in final_clips:
                    try:
                        if hasattr(clip, 'close'):
                            clip.close()
                    except:
                        pass
                        
        except Exception as e:
            self.logger.warning(f"Cleanup warning: {e}")

if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(
        description="Enhanced Video Generator with precise subtitle timing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python video_generator.py script.json metadata.json subtitles.json output.mp4
  python video_generator.py script.json metadata.json subtitles.json output.mp4 --max_events 10
  python video_generator.py script.json metadata.json subtitles.json output.mp4 --config custom_layout.yaml
        """
    )
    
    parser.add_argument("script_file", help="Path to the input JSON script file")
    parser.add_argument("metadata_file", help="Path to the audio metadata JSON file")
    parser.add_argument("subtitle_file", help="Path to the subtitle JSON file")
    parser.add_argument("output_file", help="Path for the output video file")
    parser.add_argument("--max_events", type=int, help="Maximum number of events to render")
    parser.add_argument("--config", default="data/layout.yaml", help="Path to layout config file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Validate input files
    missing_files = []
    for filepath in [args.script_file, args.metadata_file, args.subtitle_file]:
        if not os.path.exists(filepath):
            missing_files.append(filepath)
    
    if missing_files:
        print(f"Error: Missing input files: {', '.join(missing_files)}")
        sys.exit(1)
    
    if not os.path.exists(args.config):
        print(f"Error: Config file not found: {args.config}")
        sys.exit(1)
    
    try:
        generator = VideoGenerator(config_path=args.config)
        success = generator.render_video(
            script_path=args.script_file,
            metadata_path=args.metadata_file,
            subtitle_path=args.subtitle_file,
            output_path=args.output_file,
            max_events=args.max_events
        )
        
        if success:
            print(f"✅ Video generation completed successfully: {args.output_file}")
            sys.exit(0)
        else:
            print("❌ Video generation failed")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        logging.exception("Fatal error during video generation")
        sys.exit(1)