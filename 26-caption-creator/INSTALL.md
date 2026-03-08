# Installation Guide - Caption Creator Skill

## Teach Yourself Protocol (TYP) - Mandatory Read Order

Before you run any commands in this skill:

1. Discover every Markdown file in this skill folder (including subfolders):
   ```bash
   cd "$(dirname "$0")" 2>/dev/null || true
   find . -name "*.md" | sort
   ```
2. Read every discovered `.md` file.
3. Use this read order:
   1) `SKILL.md`
   2) `INSTALL.md`
   3) `INSTRUCTIONS.md` and `EXAMPLES.md` (and any `*-full.md`)
   4) `CORE_UPDATES.md`

Conflict rule:
- If any generic wrapper guidance conflicts with this skill folder, this skill folder wins.


## System Requirements

### Minimum Requirements
- Python 3.8 or higher
- 4GB RAM (8GB recommended)
- 2GB free disk space
- Internet connection (for model downloads)

### Recommended Specifications
- Python 3.10+
- 16GB RAM
- NVIDIA GPU with CUDA support
- 10GB free disk space

## Quick Install

```bash
# Install all dependencies
pip install openai-whisper moviepy opencv-python

# Optional: Install ffsubsync for synchronization
pip install ffsubsync

# Optional: Install additional fonts
pip install fonttools
```

## Step-by-Step Installation

### 1. Install Python Dependencies

```bash
# Core dependencies
pip install openai-whisper moviepy opencv-python pillow numpy

# For better performance
pip install torch torchvision torchaudio

# Optional enhancements
pip install pysubs2  # Advanced subtitle manipulation
pip install langcodes  # Language code handling
pip install ffmpeg-python  # FFmpeg Python bindings
```

### 2. Install FFmpeg

FFmpeg is required for video processing.

#### macOS
```bash
# Using Homebrew
brew install ffmpeg

# Verify installation
ffmpeg -version
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt-get update
sudo apt-get install ffmpeg

# Verify installation
ffmpeg -version
```

#### Windows
1. Download from https://ffmpeg.org/download.html
2. Extract to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to your PATH environment variable
4. Verify: `ffmpeg -version` in Command Prompt

### 3. Download Whisper Models

Models are downloaded automatically on first use, or you can pre-download:

```bash
# Download specific model
whisper --model base --language en dummy.mp3 2>/dev/null || true

# Available models (smaller = faster, larger = more accurate)
# tiny (39 MB) - fastest, least accurate
# base (74 MB) - good for testing
# small (244 MB) - balanced
# medium (769 MB) - good accuracy
# large (1550 MB) - best accuracy
# large-v2/v3 - latest versions
```

### 4. Verify Installation

```bash
# Test transcription
python -c "import whisper; model = whisper.load_model('base'); print('Whisper OK')"

# Test video processing
python -c "from moviepy.editor import VideoFileClip; print('MoviePy OK')"

# Test OpenCV
python -c "import cv2; print('OpenCV OK')"
```

## Optional Dependencies

### GPU Acceleration (Recommended)

```bash
# For NVIDIA GPUs
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Verify CUDA is available
python -c "import torch; print(torch.cuda.is_available())"
```

### Font Support

```bash
# Install additional fonts
pip install fonttools fontconfig

# On macOS
brew install fontconfig

# On Linux
sudo apt-get install fontconfig
```

### Advanced Audio Processing

```bash
# For better audio extraction
pip install pydub
brew install portaudio  # macOS
sudo apt-get install portaudio19-dev  # Linux
```

## Development Installation

For contributing or modifying the skill:

```bash
# Clone or navigate to the skill directory
cd /Users/trevorotts2021macair/clawd/skills/caption-creator

# Install in editable mode
pip install -e .

# Install development dependencies
pip install pytest black flake8 mypy

# Run tests
pytest Scripts/tests/
```

## Troubleshooting

### Common Installation Issues

#### "No module named 'whisper'"
```bash
# Reinstall whisper
pip uninstall whisper openai-whisper
pip install openai-whisper
```

#### FFmpeg not found
```bash
# macOS
brew reinstall ffmpeg
which ffmpeg

# Add to PATH if needed
export PATH="/usr/local/bin:$PATH"
```

#### CUDA/GPU issues
```bash
# Check CUDA version
nvcc --version

# Install matching PyTorch version
# For CUDA 11.8:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

#### Permission errors
```bash
# Use --user flag
pip install --user openai-whisper moviepy opencv-python

# Or use virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate  # Windows
pip install openai-whisper moviepy opencv-python
```

### Verification Script

Save this as `verify_install.py` and run it:

```python
#!/usr/bin/env python3
"""Verify Caption Creator installation."""

import sys

def check_import(module_name, package_name=None):
    """Check if a module can be imported."""
    try:
        __import__(module_name)
        print(f"✓ {package_name or module_name}")
        return True
    except ImportError as e:
        print(f"✗ {package_name or module_name}: {e}")
        return False

def main():
    print("Checking Caption Creator dependencies...\n")
    
    checks = [
        ("whisper", "openai-whisper"),
        ("moviepy", "moviepy"),
        ("cv2", "opencv-python"),
        ("PIL", "pillow"),
        ("numpy", "numpy"),
    ]
    
    all_passed = True
    for module, package in checks:
        if not check_import(module, package):
            all_passed = False
    
    # Check FFmpeg
    import subprocess
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        print("✓ ffmpeg")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ ffmpeg: not found in PATH")
        all_passed = False
    
    # Check GPU
    try:
        import torch
        if torch.cuda.is_available():
            print(f"✓ CUDA available ({torch.cuda.get_device_name(0)})")
        else:
            print("⚠ CUDA not available (CPU mode)")
    except ImportError:
        pass
    
    print()
    if all_passed:
        print("✓ All required dependencies installed!")
        return 0
    else:
        print("✗ Some dependencies are missing. Please install them.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

Run with:
```bash
python verify_install.py
```

## Uninstallation

```bash
# Remove pip packages
pip uninstall openai-whisper moviepy opencv-python pillow

# Remove downloaded models
rm -rf ~/.cache/whisper

# Remove skill directory (if needed)
rm -rf /Users/trevorotts2021macair/clawd/skills/caption-creator
```

## Next Steps

After installation:
1. Read the [SKILL.md](SKILL.md) for usage instructions
2. Check [EXAMPLES.md](EXAMPLES.md) for practical examples
3. Run the verification script to ensure everything works
4. Try processing a test video

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Verify your Python version: `python --version`
3. Check installed packages: `pip list`
4. Review error messages carefully
