#!/usr/bin/env python3
"""
Installation script for video generator dependencies.
This script installs the required packages for precise subtitle timing.
"""

import subprocess
import sys
import importlib
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REQUIRED_PACKAGES = [
    ("whisper", "openai-whisper"),
    ("torch", "torch"),
    ("pydub", "pydub"),
    ("librosa", "librosa"),
    ("speech_recognition", "SpeechRecognition"),
    ("moviepy", "moviepy"),
    ("PIL", "Pillow"),
    ("yaml", "PyYAML"),
    ("numpy", "numpy"),
    ("psutil", "psutil")
]

OPTIONAL_PACKAGES = [
    ("pocketsphinx", "pocketsphinx"),  # For speech recognition fallback
]

def check_package(package_name: str) -> bool:
    """Check if a package is installed."""
    try:
        importlib.import_module(package_name)
        return True
    except ImportError:
        return False

def install_package(pip_name: str) -> bool:
    """Install a package using pip."""
    try:
        logger.info(f"Installing {pip_name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install {pip_name}: {e}")
        return False

def install_ffmpeg():
    """Install ffmpeg (required for moviepy and pydub)."""
    logger.info("Checking ffmpeg installation...")
    try:
        subprocess.check_call(["ffmpeg", "-version"], 
                            stdout=subprocess.DEVNULL, 
                            stderr=subprocess.DEVNULL)
        logger.info("✅ ffmpeg is already installed")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("⚠️ ffmpeg not found. Please install it manually:")
        logger.warning("  macOS: brew install ffmpeg")
        logger.warning("  Ubuntu: sudo apt update && sudo apt install ffmpeg")
        logger.warning("  Windows: Download from https://ffmpeg.org/download.html")
        return False

def main():
    """Main installation function."""
    logger.info("🚀 Starting video generator dependency installation")
    
    # Check ffmpeg first
    ffmpeg_ok = install_ffmpeg()
    
    # Install required packages
    failed_packages = []
    
    for package_name, pip_name in REQUIRED_PACKAGES:
        if check_package(package_name):
            logger.info(f"✅ {package_name} is already installed")
        else:
            logger.info(f"📦 Installing {package_name}...")
            if not install_package(pip_name):
                failed_packages.append(pip_name)
    
    # Install optional packages (don't fail if these don't work)
    for package_name, pip_name in OPTIONAL_PACKAGES:
        if check_package(package_name):
            logger.info(f"✅ {package_name} (optional) is already installed")
        else:
            logger.info(f"📦 Installing optional package {package_name}...")
            install_package(pip_name)  # Don't track failures for optional packages
    
    # Summary
    if failed_packages:
        logger.error(f"❌ Failed to install: {', '.join(failed_packages)}")
        logger.error("Please install these packages manually using:")
        for pkg in failed_packages:
            logger.error(f"  pip install {pkg}")
        return False
    
    if not ffmpeg_ok:
        logger.warning("⚠️ Please install ffmpeg manually for full functionality")
    
    logger.info("🎉 Installation complete!")
    logger.info("You can now use the enhanced video generator with precise subtitles")
    
    # Test import
    try:
        from tools.video_generator import VideoGenerator
        from tools.subtitle_generator import generate_precise_subtitles
        logger.info("✅ Video generator modules imported successfully")
    except ImportError as e:
        logger.error(f"❌ Failed to import video generator modules: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)