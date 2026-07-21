---
name: video-editor
description: Local video editing using FFmpeg, yt-dlp, Whisper, and PySceneDetect — download videos, cut clips, resize for social platforms, auto-caption, merge B-roll, and run full social-clip workflows without cloud video editors.
---

# Video Editor (Local Opus Clip Alternative)

Edit existing videos locally using simple, predictable scripts.

This skill is built around a small set of shell scripts (FFmpeg, yt-dlp, Whisper, PySceneDetect) plus a couple Python helpers for B-roll merging and text overlays.

## What you can do

- Download a video from a URL (YouTube and many other sites)
- Cut a clip by timestamp
- Resize/reframe for TikTok, Reels, Shorts, Instagram square, YouTube, LinkedIn
- Auto-generate captions with Whisper and burn them into the video
- Run a full "social clip" workflow (cut + resize + caption)
- Analyze a video for scene changes and suggested B-roll insertion points
- Merge B-roll into a talking-head video while keeping the original audio continuous

## Requirements

- FFmpeg installed (`ffmpeg` command)
- Python 3 (for Whisper + scenedetect + the B-roll merge helper)
- Tools installed via pip:
  - `yt-dlp`
  - `scenedetect`
  - `openai-whisper`
  - `moviepy` (used by the B-roll merge helper)

See `INSTALL.md` for step-by-step setup.

## File structure

```
27-video-editor/
├── SKILL.md
├── INSTALL.md
├── INSTRUCTIONS.md
├── EXAMPLES.md
├── CORE_UPDATES.md
├── BROLL-WORKFLOW.md
├── scripts/
│   ├── download.sh           # Download a video via yt-dlp
│   ├── cut.sh                # Cut a clip by start time + duration
│   ├── resize.sh             # Resize/reframe for social platforms
│   ├── caption.sh            # Whisper captions + burn-in
│   ├── social-clip.sh        # cut + resize + caption in one command
│   ├── analyze-video.sh      # Scene detection + suggested B-roll points
│   ├── extract-audio.sh      # Extract audio (aac, mp3, or wav)
│   ├── merge-broll.sh        # Merge B-roll into main video (calls Python helper)
│   ├── broll-workflow.sh     # Guided end-to-end B-roll workflow
│   ├── broll_merge.py        # Python helper used by merge-broll.sh
│   └── text-overlay.py       # Optional: add a basic text overlay
└── references/
    ├── platform-specs.md
    ├── ffmpeg-vs-moviepy.md
    └── kie-ai-models.md
```

## Quick start (most common workflow)

1. Download a video.

```bash
./scripts/download.sh \
  --url "https://www.youtube.com/watch?v=VIDEO_ID" \
  --output input.mp4
```

2. Turn it into a TikTok/Reels/Shorts clip (cut + resize + captions).

```bash
./scripts/social-clip.sh \
  --input input.mp4 \
  --start 00:00:30 \
  --duration 30 \
  --platform tiktok \
  --output clip-captioned-vertical.mp4
```

3. (Optional) Skip captions if you want a clean clip.

```bash
./scripts/social-clip.sh \
  --input input.mp4 \
  --start 00:00:30 \
  --duration 30 \
  --platform tiktok \
  --output clip-vertical.mp4 \
  --skip-caption
```

## B-roll workflow (talking head to professional B-roll cut)

- Read `BROLL-WORKFLOW.md` for the full, detailed SOP.
- Use `./scripts/broll-workflow.sh` to stage a project folder, analyze the video, extract audio, and print suggested insertion points.

### Merge inputs are probed before anything renders

`merge-broll.sh` validates every input before it does any work: each of `--main`
and every `--broll` clip must be a non-empty file that `ffprobe` reports a video
stream for, and every `--insert-at` value must be a non-negative number inside the
main video's duration. A failure exits non-zero with a named error
(`AF-MERGE-INPUT-MISSING`, `AF-MERGE-INPUT-EMPTY`, `AF-MERGE-INPUT-NOT-VIDEO`,
`AF-MERGE-TIMESTAMP-RANGE`, `AF-MERGE-ARITY`, `AF-MERGE-PREREQ-MISSING`) and
renders nothing.

`broll-workflow.sh` declares the expected B-roll paths in a
`broll-manifest.json` rather than creating empty files at them, so a clip you have
not generated yet is genuinely absent instead of being a zero-byte `.mp4` the merge
would read.

Rehearse before you render:

```bash
./scripts/merge-broll.sh --main talking-head.mp4 --broll "b1.mp4,b2.mp4" \
  --insert-at "12,38" --output final.mp4 --dry-run
```

`--dry-run` runs every probe and every timestamp check, prints the merge plan and
exits without rendering.

## Notes about analysis output

`analyze-video.sh` relies on PySceneDetect.

- The number of scenes and suggested insertion points can vary depending on:
  - the content
  - the detection method you choose
  - the PySceneDetect version
- Treat the JSON output as helpful suggestions, not a guaranteed structure for downstream automation.
