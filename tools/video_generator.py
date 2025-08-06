"""
M1-Optimized Video Generator for AITheater
Optimized for Apple Silicon with hardware acceleration and memory efficiency
"""

import os
import yaml
import json
import logging
import gc
import multiprocessing
import platform
import subprocess
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import *


@dataclass
class M1OptimizationConfig:
    """Configuration for M1-specific optimizations"""
    use_videotoolbox: bool = True
    use_metal: bool = True
    max_memory_mb: int = 8192  # 8GB limit for 16GB system
    optimal_batch_size: int = 3
    encoding_preset: str = "ultrafast"
    target_resolution: Tuple[int, int] = (1920, 1080)  # 保持原始分辨率
    bitrate: str = "3000k"  # 提高码率以保证质量
    fps: int = 24
    threads: int = 8  # M1 has 8 cores (4 performance + 4 efficiency)


class MemoryManager:
    """Memory management for 16GB M1 Mac"""
    def __init__(self, max_memory_mb: int = 8192):
        self.max_memory_mb = max_memory_mb
        self.logger = logging.getLogger(__name__)
        
    def check_memory(self) -> float:
        """Check current memory usage"""
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            return memory_mb
        except ImportError:
            return 0
    
    def optimize_if_needed(self) -> bool:
        """Trigger optimization if memory usage is high"""
        current_mb = self.check_memory()
        if current_mb > self.max_memory_mb * 0.8:  # 80% threshold
            self.logger.warning(f"High memory usage: {current_mb:.1f}MB, triggering cleanup")
            gc.collect()
            return True
        return False


class AssetManager:
    """Efficient asset loading and caching with lazy loading"""
    def __init__(self, config: Dict, resolution: Tuple[int, int]):
        self.config = config
        self.resolution = resolution
        self.logger = logging.getLogger(__name__)
        self._cache = {}
        self._font_cache = {}
        
    @lru_cache(maxsize=32)
    def get_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Cached font loading"""
        font_path = self.config.get("font_path")
        try:
            return ImageFont.truetype(font_path, size)
        except OSError as e:
            self.logger.error(f"Failed to load font: {e}")
            return ImageFont.load_default()
    
    def load_background(self) -> ImageClip:
        """Lazy load background image"""
        if 'background' not in self._cache:
            bg_path = self.config.get("background_image")
            if bg_path and os.path.exists(bg_path):
                # Load at target resolution to save memory
                self._cache['background'] = ImageClip(bg_path).resized(
                    new_size=self.resolution
                )
            else:
                # Create solid color background as fallback
                self._cache['background'] = ColorClip(
                    size=self.resolution, 
                    color=(30, 30, 30), 
                    duration=1
                )
        return self._cache['background']
    
    def load_avatar(self, player_id: int) -> Optional[ImageClip]:
        """Lazy load player avatar"""
        cache_key = f"avatar_{player_id}"
        if cache_key not in self._cache:
            avatar_cfg = self.config.get("avatar", {})
            avatar_size = tuple(avatar_cfg.get("size", [75, 75]))
            avatar_dir = self.config.get("avatar_dir", "assets/player_avatars")
            
            # Get avatar mapping
            player_avatars = self.config.get("player_avatars", [])
            avatar_map = {p["player_id"]: p["avatar_file"] for p in player_avatars}
            avatar_filename = avatar_map.get(player_id, "default.png")
            avatar_path = os.path.join(avatar_dir, avatar_filename)
            
            try:
                if os.path.exists(avatar_path):
                    # Load and resize in one operation to save memory
                    avatar_img = Image.open(avatar_path).convert("RGBA").resize(
                        avatar_size, Image.Resampling.LANCZOS
                    )
                    self._cache[cache_key] = ImageClip(
                        np.array(avatar_img), 
                        duration=1
                    )
                else:
                    # Create placeholder
                    placeholder = Image.new('RGBA', avatar_size, (128, 128, 128, 255))
                    self._cache[cache_key] = ImageClip(
                        np.array(placeholder), 
                        duration=1
                    )
            except Exception as e:
                self.logger.error(f"Failed to load avatar for player {player_id}: {e}")
                return None
                
        return self._cache[cache_key]
    
    def clear_cache(self):
        """Clear asset cache to free memory"""
        self._cache.clear()
        gc.collect()


class VideoEncoderM1:
    """M1-optimized video encoder with hardware acceleration"""
    def __init__(self, m1_config: M1OptimizationConfig):
        self.config = m1_config
        self.logger = logging.getLogger(__name__)
        self._detect_capabilities()
        
    def _detect_capabilities(self):
        """Detect M1 hardware acceleration capabilities"""
        self.has_videotoolbox = False
        self.has_metal = platform.system() == 'Darwin' and platform.processor() == 'arm'
        
        if platform.system() == 'Darwin':
            try:
                result = subprocess.run(
                    ['ffmpeg', '-hide_banner', '-encoders'], 
                    capture_output=True, text=True, timeout=5
                )
                if 'h264_videotoolbox' in result.stdout:
                    self.has_videotoolbox = True
                    self.logger.info("VideoToolbox hardware acceleration available")
            except:
                pass
                
    def get_encoding_params(self) -> Dict[str, Any]:
        """Get optimized encoding parameters for M1"""
        params = {
            'fps': self.config.fps,
            'threads': self.config.threads,
            'preset': self.config.encoding_preset,
            'bitrate': self.config.bitrate,
            'audio_codec': 'aac',
            'temp_audiofile': 'temp-audio.m4a',
            'remove_temp': True,
            'write_logfile': False,
            'verbose': False
        }
        
        if self.has_videotoolbox and self.config.use_videotoolbox:
            params['codec'] = 'h264_videotoolbox'
            # VideoToolbox specific optimizations
            params['ffmpeg_params'] = [
                '-profile:v', 'baseline',  # Simpler profile for faster encoding
                '-level', '4.0',
                '-allow_sw', '1',  # Allow software fallback
                '-realtime', '1'   # Optimize for realtime encoding
            ]
        else:
            params['codec'] = 'libx264'
            params['ffmpeg_params'] = [
                '-profile:v', 'baseline',
                '-level', '4.0',
                '-tune', 'zerolatency'  # Optimize for low latency
            ]
            
        return params


class SceneCompositor:
    """Efficient scene composition with minimal memory usage"""
    def __init__(self, asset_manager: AssetManager, layout_config: Dict):
        self.assets = asset_manager
        self.layout = layout_config
        self.resolution = tuple(layout_config.get("resolution", [1280, 720]))
        self.logger = logging.getLogger(__name__)
        
    def create_event_clip(self, event: Dict, audio_path: str, duration: float,
                         subtitles: List[Dict], start_time_ms: int) -> Optional[VideoClip]:
        """Create optimized event clip with minimal layers"""
        try:
            # Load audio
            if not os.path.exists(audio_path):
                self.logger.warning(f"Audio file not found: {audio_path}")
                return None
                
            audio_clip = AudioFileClip(audio_path)
            
            # Start with background
            layers = [self.assets.load_background().with_duration(duration)]
            
            # Add avatars efficiently
            player_positions = self.layout.get("player_positions", [])
            speaking_player = self._get_speaking_player(event)
            
            for player_info in player_positions:
                player_id = player_info['player_id']
                position = tuple(player_info.get("position", [0, 0]))
                
                avatar = self.assets.load_avatar(player_id)
                if avatar:
                    avatar_clip = avatar.with_duration(duration).with_position(position)
                    layers.append(avatar_clip)
                    
                    # Add speaking indicator if needed
                    if player_id == speaking_player:
                        layers.append(self._create_speaking_indicator(
                            position, duration
                        ))
            
            # Add subtitles
            subtitle_clips = self._create_subtitle_clips(
                subtitles, start_time_ms, int(duration * 1000)
            )
            layers.extend(subtitle_clips)
            
            # Composite with minimal operations
            video_clip = CompositeVideoClip(layers, size=self.resolution)
            video_clip = video_clip.with_duration(duration).with_audio(audio_clip)
            
            return video_clip
            
        except Exception as e:
            self.logger.error(f"Failed to create event clip: {e}")
            return None
    
    def _get_speaking_player(self, event: Dict) -> Optional[int]:
        """Extract speaking player ID"""
        try:
            player_id = event.get("player_id")
            if player_id is not None:
                if isinstance(player_id, str) and player_id.isdigit():
                    return int(player_id)
                elif isinstance(player_id, int):
                    return player_id
        except:
            pass
        return None
    
    def _create_speaking_indicator(self, position: Tuple[int, int], 
                                  duration: float) -> ColorClip:
        """Create speaking border"""
        avatar_cfg = self.layout.get("avatar", {})
        avatar_size = tuple(avatar_cfg.get("size", [75, 75]))
        border_width = avatar_cfg.get("border_width", 6)
        border_color = avatar_cfg.get("border_color_speaking", [255, 215, 0])
        
        border_size = (
            avatar_size[0] + 2 * border_width,
            avatar_size[1] + 2 * border_width
        )
        border_pos = (
            position[0] - border_width,
            position[1] - border_width
        )
        
        return ColorClip(
            size=border_size,
            color=border_color,
            duration=duration
        ).with_position(border_pos)
    
    def _create_subtitle_clips(self, subtitles: List[Dict], 
                              event_start_ms: int, 
                              event_duration_ms: int) -> List[TextClip]:
        """Create subtitle clips efficiently"""
        clips = []
        event_end_ms = event_start_ms + event_duration_ms
        
        relevant_subtitles = [
            s for s in subtitles 
            if s['start_ms'] < event_end_ms and s['end_ms'] > event_start_ms
        ]
        
        if not relevant_subtitles:
            return []
        
        sub_cfg = self.layout.get("subtitle_area", {})
        font_size = sub_cfg.get("font_size", 36)
        text_color = sub_cfg.get("text_color", "white")
        position = sub_cfg.get("position", ["center", 950])
        
        for sub in relevant_subtitles:
            try:
                text = sub.get('text', '').strip()
                if not text:
                    continue
                
                clip_start_sec = max(0, (sub['start_ms'] - event_start_ms) / 1000.0)
                clip_duration_sec = (sub['end_ms'] - sub['start_ms']) / 1000.0
                
                if clip_duration_sec <= 0:
                    continue
                
                subtitle_clip = TextClip(
                    text=text,
                    font_size=font_size,
                    color=text_color,
                    method='caption'
                ).with_position(position).with_start(clip_start_sec).with_duration(clip_duration_sec)
                
                clips.append(subtitle_clip)
                
            except Exception as e:
                self.logger.error(f"Failed to create subtitle: {e}")
                
        return clips


class M1VideoGenerator:
    """Main M1-optimized video generator"""
    
    def __init__(self, config_path: str = "data/layout.yaml", 
                 target_resolution: Optional[Tuple[int, int]] = None):
        """Initialize M1-optimized video generator
        
        Args:
            config_path: Path to layout configuration
            target_resolution: Override resolution for speed (e.g., (1280, 720))
        """
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Load configuration
        with open(config_path, 'r') as f:
            self.layout_config = yaml.safe_load(f)
        
        # M1-specific configuration
        self.m1_config = M1OptimizationConfig()
        if target_resolution:
            self.m1_config.target_resolution = target_resolution
            self.layout_config["resolution"] = list(target_resolution)
        else:
            # Use configured or default to 720p for speed
            res = self.layout_config.get("resolution", [1280, 720])
            self.m1_config.target_resolution = tuple(res)
            
        self.resolution = self.m1_config.target_resolution
        
        # Initialize components
        self.memory_manager = MemoryManager(self.m1_config.max_memory_mb)
        self.asset_manager = AssetManager(self.layout_config, self.resolution)
        self.encoder = VideoEncoderM1(self.m1_config)
        self.compositor = SceneCompositor(self.asset_manager, self.layout_config)
        
        self.logger.info(f"M1 Video Generator initialized")
        self.logger.info(f"Resolution: {self.resolution}")
        self.logger.info(f"Hardware acceleration: VideoToolbox={self.encoder.has_videotoolbox}")
        
    def render_video(self, script_path: str, metadata_path: str, 
                    subtitle_path: str, output_path: str,
                    max_events: Optional[int] = None) -> bool:
        """Render video with M1 optimizations"""
        self.logger.info("Starting M1-optimized video generation")
        start_memory = self.memory_manager.check_memory()
        
        try:
            # Load input files
            with open(script_path, 'r') as f:
                script_data = json.load(f)
            with open(metadata_path, 'r') as f:
                metadata_list = json.load(f)
            with open(subtitle_path, 'r') as f:
                subtitles = json.load(f)
            
            # Convert metadata to dict
            metadata = {item['event_index']: item for item in metadata_list}
            
            # Limit events if requested
            if max_events:
                script_data = script_data[:max_events]
            
            total_events = len(script_data)
            self.logger.info(f"Processing {total_events} events")
            
            # Process events in optimized batches
            clips = []
            current_time_ms = 0
            batch_size = self.m1_config.optimal_batch_size
            
            for i in range(0, total_events, batch_size):
                batch = script_data[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (total_events + batch_size - 1) // batch_size
                
                self.logger.info(f"Processing batch {batch_num}/{total_batches}")
                
                # Check memory before processing batch
                self.memory_manager.optimize_if_needed()
                
                # Process batch
                for j, event in enumerate(batch):
                    event_idx = i + j
                    audio_info = metadata.get(event_idx)
                    
                    if not audio_info or audio_info.get("duration_ms", 0) <= 0:
                        continue
                    
                    duration_ms = audio_info["duration_ms"]
                    duration_sec = duration_ms / 1000.0
                    audio_path = audio_info.get("file_path", "")
                    
                    # Create event clip
                    clip = self.compositor.create_event_clip(
                        event, audio_path, duration_sec,
                        subtitles, current_time_ms
                    )
                    
                    if clip:
                        clips.append(clip)
                        current_time_ms += duration_ms
                    
                    # Progress update
                    progress = ((event_idx + 1) / total_events) * 100
                    self.logger.info(f"Progress: {progress:.1f}%")
                
                # Clear caches periodically
                if batch_num % 5 == 0:
                    self.asset_manager.clear_cache()
                    gc.collect()
            
            if not clips:
                self.logger.error("No clips generated")
                return False
            
            # Concatenate clips
            self.logger.info(f"Concatenating {len(clips)} clips...")
            final_video = concatenate_videoclips(clips)
            
            # Render with M1 optimizations
            self.logger.info(f"Rendering video (duration: {final_video.duration:.1f}s)...")
            encoding_params = self.encoder.get_encoding_params()
            
            final_video.write_videofile(
                output_path,
                **encoding_params,
                logger='bar'
            )
            
            # Cleanup
            final_video.close()
            for clip in clips:
                if hasattr(clip, 'close'):
                    clip.close()
            
            # Report performance
            end_memory = self.memory_manager.check_memory()
            memory_used = end_memory - start_memory
            self.logger.info(f"✅ Video generated successfully: {output_path}")
            self.logger.info(f"Memory used: {memory_used:.1f}MB")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Video generation failed: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Command-line interface"""
    import argparse
    import sys
    import time
    
    parser = argparse.ArgumentParser(
        description="M1-Optimized Video Generator for AITheater",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
M1 Optimization Features:
  - Hardware-accelerated encoding with VideoToolbox
  - Memory-efficient processing for 16GB systems  
  - Optimized for Apple Silicon architecture
  - Configurable quality/speed tradeoffs

Examples:
  # Standard quality (720p)
  python video_generator_m1.py script.json metadata.json subtitles.json output.mp4
  
  # High speed mode (480p)
  python video_generator_m1.py script.json metadata.json subtitles.json output.mp4 --fast
  
  # Custom resolution
  python video_generator_m1.py script.json metadata.json subtitles.json output.mp4 --resolution 640 360
        """
    )
    
    parser.add_argument("script_file", help="Path to script JSON file")
    parser.add_argument("metadata_file", help="Path to metadata JSON file")
    parser.add_argument("subtitle_file", help="Path to subtitle JSON file")
    parser.add_argument("output_file", help="Path for output video file")
    parser.add_argument("--config", default="data/layout.yaml", help="Layout config file")
    parser.add_argument("--max-events", type=int, help="Limit number of events")
    parser.add_argument("--resolution", nargs=2, type=int, metavar=('WIDTH', 'HEIGHT'),
                       help="Override output resolution (e.g., 1280 720)")
    parser.add_argument("--fast", action="store_true", 
                       help="Fast mode: 480p resolution for maximum speed")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    # Set resolution based on mode
    if args.fast:
        resolution = (640, 360)  # 360p for maximum speed
        print(" Fast mode enabled: 360p resolution")
    elif args.resolution:
        resolution = tuple(args.resolution)
        print(f" Custom resolution: {resolution[0]}x{resolution[1]}")
    else:
        resolution = None  # Use config default
    
    # Validate input files
    for filepath in [args.script_file, args.metadata_file, args.subtitle_file]:
        if not os.path.exists(filepath):
            print(f"❌ Error: File not found: {filepath}")
            sys.exit(1)
    
    if not os.path.exists(args.config):
        print(f"❌ Error: Config file not found: {args.config}")
        sys.exit(1)
    
    # Initialize generator
    try:
        print(" Initializing M1-optimized video generator...")
        generator = M1VideoGenerator(
            config_path=args.config,
            target_resolution=resolution
        )
        
        # Start timing
        start_time = time.time()
        
        # Generate video
        success = generator.render_video(
            script_path=args.script_file,
            metadata_path=args.metadata_file,
            subtitle_path=args.subtitle_file,
            output_path=args.output_file,
            max_events=args.max_events
        )
        
        # Report results
        elapsed = time.time() - start_time
        
        if success:
            print(f"✅ Video generated successfully: {args.output_file}")
            print(f"⏱️  Time taken: {elapsed:.1f} seconds")
            
            # Calculate performance metrics
            if os.path.exists(args.output_file):
                from moviepy.editor import VideoFileClip
                video = VideoFileClip(args.output_file)
                duration = video.duration
                video.close()
                
                ratio = duration / elapsed if elapsed > 0 else 0
                print(f" Performance: {ratio:.2f}:1 (video:render time)")
        else:
            print("❌ Video generation failed")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
