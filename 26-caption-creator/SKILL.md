---
name: caption-creator
description: Add professional captions burned into a video or export an SRT subtitle file — uses Whisper for local speech-to-text and FFmpeg for rendering. Supports minimal, full, and animated caption styles.
---

# Caption Creator (Skill 26)

Add professional captions to a video (burned into the video), or export an SRT subtitle file.

This skill is intentionally simple and reliable. It is built on:
- **Whisper** (local speech-to-text)
- **FFmpeg** (video rendering)

## What you get

- **Generate a captioned video** with one command (minimal, full, or animated style)
- **Export SRT subtitles** from any video

## Files in this skill

- `Scripts/generate-captions.sh` - transcribe with Whisper, then burn captions into a new video
- `Scripts/export-srt.sh` - export a properly named SRT file (respects `--output`)
- `Scripts/animated_captions.py` - creates an animated style using FFmpeg drawtext

## Requirements

1. **Python 3**
2. **FFmpeg** installed and available in your terminal as `ffmpeg`
3. **Whisper CLI** installed (from the `openai-whisper` Python package)

## Quick start

### 1) Export an SRT file

```bash
~/.openclaw/skills/caption-creator/Scripts/export-srt.sh \
  --input "video.mp4" \
  --output "captions.srt" \
  --model medium
```

### 2) Create a captioned video (burn-in captions)

```bash
~/.openclaw/skills/caption-creator/Scripts/generate-captions.sh \
  --input "video.mp4" \
  --output "video_captioned.mp4" \
  --style minimal \
  --model medium
```

## Caption styles

`generate-captions.sh` supports:

| Style | What it looks like | Best for |
|------|---------------------|----------|
| `minimal` | smaller captions, simple outline | clean professional videos |
| `full` | larger captions with stronger background/outline | maximum readability |
| `animated` | animated captions (Python + FFmpeg drawtext) | high-energy social clips |

## Whisper models

You can pick the Whisper model with `--model`:

- `tiny`, `base`, `small` = faster, lower accuracy
- `medium`, `large` = slower, higher accuracy

Example:

```bash
~/.openclaw/skills/caption-creator/Scripts/export-srt.sh \
  --input "video.mp4" \
  --output "captions.srt" \
  --model base
```

## Output notes

- `export-srt.sh` writes the SRT file to the exact path you pass in `--output`.
- `generate-captions.sh` creates a new video file at the path you pass in `--output`.

## Core updates policy

Follow `CORE_UPDATES.md` for the only core files this skill is allowed to update.
