# Caption Creator (Skill 26) - Instructions

## What this skill does

The Caption Creator skill helps you do two things:

1. **Export an SRT subtitle file** from a video (good for YouTube uploads and editors)
2. **Create a new captioned video** where the captions are burned into the video

It uses Whisper for transcription and FFmpeg for rendering.

## Before you start (one-time setup)

### Step 1: Install FFmpeg

#### On macOS

1. Open the Terminal app.
2. Run:

```bash
brew install ffmpeg
```

3. Verify it works:

```bash
ffmpeg -version
```

#### On Ubuntu / Debian

1. Open Terminal.
2. Run:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

3. Verify it works:

```bash
ffmpeg -version
```

### Step 2: Install Whisper (the CLI)

1. Open Terminal.
2. Run:

```bash
pip install --upgrade openai-whisper
```

3. Verify Whisper works:

```bash
whisper --help
```

## Install the skill

1. Download or locate `caption-creator.skill`.
2. Install it:

```bash
The .skill file is an archive. No CLI command needed - install by following SKILL.md, INSTALL.md, and CORE_UPDATES.md instructions.
```

3. Confirm the folder exists:

```bash
ls -la ~/.openclaw/skills/caption-creator
```

You should see files like `SKILL.md`, `INSTALL.md`, `Scripts/`, and `CORE_UPDATES.md`.

## How to use the skill

### Option A: Export subtitles (SRT)

1. Pick the video you want to transcribe (example: `video.mp4`).
2. Run:

```bash
~/.openclaw/skills/caption-creator/Scripts/export-srt.sh \
  --input "video.mp4" \
  --output "captions.srt" \
  --model medium
```

3. After it finishes, you will have:
- `captions.srt` in the location you specified

### Option B: Create a captioned video (burn-in captions)

1. Pick the video you want to caption (example: `video.mp4`).
2. Choose a style: `minimal`, `full`, or `animated`.
3. Run:

```bash
~/.openclaw/skills/caption-creator/Scripts/generate-captions.sh \
  --input "video.mp4" \
  --output "video_captioned.mp4" \
  --style minimal \
  --model medium
```

4. After it finishes, you will have:
- `video_captioned.mp4`

## Choosing a Whisper model

- Faster, lower accuracy: `tiny`, `base`, `small`
- Slower, higher accuracy: `medium`, `large`

Example (fast):

```bash
~/.openclaw/skills/caption-creator/Scripts/export-srt.sh \
  --input "video.mp4" \
  --output "captions.srt" \
  --model base
```

## Core updates policy

This skill has a strict policy for what core files it is allowed to update.

1. Open `CORE_UPDATES.md`.
2. Follow it exactly.

Do not add instructions in other files that expand core file updates beyond what `CORE_UPDATES.md` allows.
