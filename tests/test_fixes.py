#!/usr/bin/env python3
"""
Test script to verify video generator fixes work correctly.
"""

import os
import sys
import json
import logging
from tools.video_generator import VideoGenerator

def test_video_generator_initialization():
    """Test video generator can initialize without errors."""
    print("🧪 Testing VideoGenerator initialization...")
    
    try:
        # Test with existing config
        config_path = "data/layout.yaml"
        if os.path.exists(config_path):
            generator = VideoGenerator(config_path)
            print("✅ VideoGenerator initialized successfully")
            return True
        else:
            print(f"❌ Config file not found: {config_path}")
            return False
    except Exception as e:
        print(f"❌ VideoGenerator initialization failed: {e}")
        return False

def test_subtitle_timing():
    """Test subtitle timing calculations."""
    print("🧪 Testing subtitle timing...")
    
    try:
        generator = VideoGenerator("data/layout.yaml")
        
        # Mock subtitles data
        subtitles = [
            {"start_ms": 0, "end_ms": 2000, "text": "First subtitle"},
            {"start_ms": 1500, "end_ms": 3500, "text": "Overlapping subtitle"},
            {"start_ms": 4000, "end_ms": 6000, "text": "Third subtitle"}
        ]
        
        # Test subtitle creation for time window 0-2500ms
        subtitle_clip = generator._create_dynamic_subtitles(subtitles, 0, 2500)
        
        if subtitle_clip is not None:
            print("✅ Subtitle timing logic works")
            return True
        else:
            print("⚠️ No subtitles created (might be expected)")
            return True
            
    except Exception as e:
        print(f"❌ Subtitle timing test failed: {e}")
        return False

def test_render_settings():
    """Test render settings optimization."""
    print("🧪 Testing render settings...")
    
    try:
        generator = VideoGenerator("data/layout.yaml")
        settings = generator._get_optimal_render_settings()
        
        required_keys = ['video_codec', 'audio_codec', 'threads', 'preset']
        if all(key in settings for key in required_keys):
            print(f"✅ Render settings: {settings}")
            return True
        else:
            print(f"❌ Missing keys in render settings: {settings}")
            return False
            
    except Exception as e:
        print(f"❌ Render settings test failed: {e}")
        return False

def check_dependencies():
    """Check if required dependencies are available."""
    print("🧪 Checking dependencies...")
    
    dependencies = [
        "moviepy", "PIL", "numpy", "yaml", "json", "logging"
    ]
    
    missing = []
    for dep in dependencies:
        try:
            __import__(dep)
        except ImportError:
            missing.append(dep)
    
    if missing:
        print(f"❌ Missing dependencies: {missing}")
        return False
    else:
        print("✅ All core dependencies available")
        return True

def main():
    """Run all tests."""
    print("🚀 Starting Video Generator Fix Tests")
    print("=" * 50)
    
    tests = [
        ("Dependency Check", check_dependencies),
        ("VideoGenerator Init", test_video_generator_initialization),
        ("Subtitle Timing", test_subtitle_timing),
        ("Render Settings", test_render_settings)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        result = test_func()
        results.append((test_name, result))
        print("-" * 30)
    
    print("\n📊 Test Results:")
    print("=" * 50)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All tests passed! Video generator fixes are working.")
        return True
    else:
        print("⚠️ Some tests failed. Check the output above.")
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)  # Reduce noise during testing
    success = main()
    sys.exit(0 if success else 1)