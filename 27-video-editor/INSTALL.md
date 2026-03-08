# 📦 Installation Guide

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


**Video Editor Skill (Client-Generic)**

---

## Requirements

- Python 3.8+
- FFmpeg (system dependency)
- 4GB+ RAM recommended
- GPU optional (for faster Whisper transcription)

---

## Quick Install

### Step 1: Install System Dependencies

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
1. Download from https://ffmpeg.org/download.html
2. Add to PATH
3. Verify: `ffmpeg -version`

### Step 2: Install Python Dependencies

```bash
pip install yt-dlp moviepy scenedetect opencv-python
```

### Step 3: Install Optional Tools (Recommended)

```bash
# Whisper for transcription
pip install openai-whisper

# Auto-editor for silence removal
pip install auto-editor

# ffsubsync for subtitle sync
pip install ffsubsync

# Additional utilities
pip install numpy pillow requests tqdm
```

### Step 4: Verify Installation

```bash
python scripts/video_editor.py --version
```

---

## Full Installation (All Features)

```bash
# Core tools
pip install yt-dlp moviepy scenedetect opencv-python

# AI/ML tools
pip install openai-whisper torch torchvision torchaudio

# Audio processing
pip install pydub librosa

# Subtitle tools
pip install ffsubsync

# Video processing
pip install auto-editor

# Utilities
pip install numpy pandas pillow requests tqdm colorama
```

---

## Manual Tool Installation

### yt-dlp
```bash
pip install -U yt-dlp
```

Verify:
```bash
yt-dlp --version
```

### MoviePy
```bash
pip install moviepy
```

Note: MoviePy requires ImageMagick for some features:
- macOS: `brew install imagemagick`
- Ubuntu: `sudo apt install imagemagick`

### PySceneDetect
```bash
pip install scenedetect
```

Verify:
```bash
scenedetect --version
```

### Whisper (OpenAI)
```bash
pip install -U openai-whisper
```

Or install from source:
```bash
pip install git+https://github.com/openai/whisper.git
```

Models will download on first use (~1-3GB depending on model size).

### Auto-Editor
```bash
pip install auto-editor
```

Verify:
```bash
auto-editor --version
```

### ffsubsync
```bash
pip install ffsubsync
```

Verify:
```bash
ffsubsync --version
```

---

## GPU Acceleration (Optional)

### For Whisper (faster transcription)

**CUDA (NVIDIA):**
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**macOS Metal (M1/M2/M3):**
```bash
pip install torch torchvision torchaudio
```

Verify GPU is available:
```python
import torch
print(torch.cuda.is_available())  # True = GPU acceleration active
```

---

## Troubleshooting

### "ffmpeg not found"
Install FFmpeg and ensure it's in your PATH:
```bash
which ffmpeg  # Should return path
ffmpeg -version  # Should show version info
```

### "ImageMagick not found" (MoviePy)
**macOS:**
```bash
brew install imagemagick
```

**Ubuntu:**
```bash
sudo apt install imagemagick
```

**Edit MoviePy config:**
```python
from moviepy.config import change_settings
change_settings({"IMAGEMAGICK_BINARY": "/usr/local/bin/convert"})
```

### Whisper model download fails
Download manually:
```bash
whisper --model large-v3 dummy.mp3  # Will download model
```

Models are stored in:
- macOS/Linux: `~/.cache/whisper/`
- Windows: `%USERPROFILE%\.cache\whisper\`

### Permission denied errors
```bash
chmod +x scripts/*.py
```

### Module not found errors
Ensure you're in the correct directory:
```bash
cd /Users/trevorotts2021macair/clawd/skills/video-editor
python -m pip install -e .
```

---

## Test Your Installation

Run the test suite:
```bash
python scripts/video_editor.py test
```

This will:
1. Check all dependencies
2. Download a test video
3. Run through the full pipeline
4. Generate test output

---

## Docker Alternative

If you prefer containerization:

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg

RUN pip install yt-dlp moviepy scenedetect opencv-python \
    openai-whisper auto-editor ffsubsync

WORKDIR /workspace
COPY . .

ENTRYPOINT ["python", "scripts/video_editor.py"]
```

Build and run:
```bash
docker build -t video-editor .
docker run -v $(pwd):/workspace video-editor --help
```

---

## Directory Setup

Create working directories:
```bash
mkdir -p ~/VideoProjects/{downloads,clips,exports,templates}
```

Set in config:
```json
{
  "download_path": "~/VideoProjects/downloads",
  "clip_path": "~/VideoProjects/clips",
  "export_path": "~/VideoProjects/exports"
}
```

---

## Update Tools

Update all tools:
```bash
pip install -U yt-dlp moviepy scenedetect opencv-python
pip install -U openai-whisper auto-editor ffsubsync
```

---

## Getting Help

- Check SKILL.md for usage examples
- See EXAMPLES.md for tutorials
- Visit tool documentation in references/

**Common Commands Reference:**
```bash
# Download
yt-dlp "URL" -o video.mp4

# Scene detect
scenedetect -i video.mp4 detect-content list-scenes

# Whisper transcribe
whisper video.mp4 --model large-v3 --language en

# Remove silence
auto-editor video.mp4 --edit audio:threshold=4%
```

---

**Installation Complete!** 🎉

Next: Check out EXAMPLES.md to start creating content.
