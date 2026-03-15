# Video Editor Instructions

This guide explains how to use the scripts in this skill to create social clips and B-roll edits.

## Before you start

1. Make sure you completed `INSTALL.md`.
2. Open a terminal.
3. Go into the skill folder.

```bash
cd video-editor
```

4. Make the scripts executable (one-time).

```bash
chmod +x scripts/*.sh
```

## Workflow A: Make a social clip (most common)

This is the "Opus Clip" style workflow: cut a moment, resize it for the platform, and add captions.

### Step 1: Download the source video (optional)

If your video is already on your computer, skip to Step 2.

```bash
./scripts/download.sh \
  --url "https://www.youtube.com/watch?v=VIDEO_ID" \
  --output input.mp4
```

What you should see:
- The download will run for a bit.
- At the end it prints `Downloaded: input.mp4`.

### Step 2: Create the clip (cut + resize + captions)

```bash
./scripts/social-clip.sh \
  --input input.mp4 \
  --start 00:00:30 \
  --duration 30 \
  --platform tiktok \
  --output clip-captioned-vertical.mp4
```

What you should see:
- "Step 1: Cutting clip..."
- "Step 2: Resizing for tiktok..."
- "Step 3: Adding captions..."
- "Done: clip-captioned-vertical.mp4"

If you want the clip without captions:

```bash
./scripts/social-clip.sh \
  --input input.mp4 \
  --start 00:00:30 \
  --duration 30 \
  --platform tiktok \
  --output clip-vertical.mp4 \
  --skip-caption
```

## Workflow B: Add captions to an existing video

```bash
./scripts/caption.sh \
  --input input.mp4 \
  --output input-captioned.mp4 \
  --model medium
```

Notes:
- Faster captions: use `--model small`.
- Higher accuracy (slower): use `--model large`.

## Workflow C: Plan a B-roll edit (analyze + suggestions)

1. Run analysis.

```bash
./scripts/analyze-video.sh \
  --input talking-head.mp4 \
  --output analysis.json
```

2. Open `analysis.json` and look for suggested timestamps.

Important notes about analysis:
- Results vary by content and PySceneDetect version.
- Treat the timestamps as suggestions, not a strict rule.

## Workflow D: Merge B-roll into a talking-head video

1. Make sure you have your B-roll clips as separate files (MP4 recommended).
2. Choose insertion times in seconds.
3. Run the merge.

```bash
./scripts/merge-broll.sh \
  --main talking-head.mp4 \
  --broll "broll1.mp4,broll2.mp4" \
  --insert-at "12,38" \
  --output final-with-broll.mp4
```

**Before running the merge, validate your timestamps:**
```bash
# Get the total duration of your main video
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 talking-head.mp4
```
Make sure every timestamp in `--insert-at` is less than the video duration. If a timestamp exceeds the video length, the merge will fail or produce misaligned output.

**Dry run (check without rendering):**
```bash
./scripts/merge-broll.sh \
  --main talking-head.mp4 \
  --broll "broll1.mp4,broll2.mp4" \
  --insert-at "12,38" \
  --output final-with-broll.mp4 \
  --dry-run
```
Use `--dry-run` first to verify the merge plan before committing to a full render.

Notes:
- By default, the main video's audio is kept continuous.
- The merge uses `moviepy` via `scripts/broll_merge.py`.
- If merge fails with a timestamp error, re-check that all insert times are within the video duration.

## Workflow E: Use the guided B-roll workflow

This is a guided helper that:
- analyzes the video
- extracts audio
- prints suggested insertion points
- tells you where to drop your generated B-roll files

```bash
./scripts/broll-workflow.sh \
  --input talking-head.mp4 \
  --output final.mp4 \
  --num-broll 3
```

## Core updates

Do not edit other OpenClaw core files from this skill.

If you need to update your global docs, use `CORE_UPDATES.md`.
