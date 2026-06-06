---
name: video-creator
description: Create videos from text prompts, scripts, images, and existing clips using Python scripts — supports text-to-video, image-to-video, clip assembly, audio mixing, export/resize, and template-based video production. Requires ffmpeg and imagemagick.
---

# Video Creator (Skill 25)

Create videos from text prompts, simple scripts, images, and existing clips.

This skill is a set of **Python scripts** you run directly. It does not add a chat command.

---

## What you can do

- **Text to video** (AI provider or mock placeholder)
- **Script to video** (scene-based)
- **Image to video** (Ken Burns, zoom, pan)
- **Assemble clips** (with transitions)
- **Add / remove / extract / mix audio**
- **Export / resize / crop / re-encode**
- **Template-based videos**
- **Avatar-style videos** (basic)

---

## Files

- `INSTALL.md` - install steps and dependencies
- `INSTRUCTIONS.md` - exact CLI usage (copied from `-h`)
- `EXAMPLES.md` - copy/paste workflows using existing scripts
- `CORE_UPDATES.md` - what core OpenClaw files this skill is allowed to update

Scripts live in `scripts/`.

---

## Quick start

1. Install dependencies (see `INSTALL.md`).
2. Go into the skill folder:
   ```bash
   cd "$HOME/.openclaw/skills/video-creator"
   ```
3. Generate a test video without any API keys:
   ```bash
   python3 scripts/text_to_video.py "A calm ocean at sunrise" --provider mock --duration 5 --output output/test.mp4
   ```

---

## API keys (optional)

- KIE.ai uses: `KIE_API_KEY`
- Runway uses: `RUNWAY_API_KEY`
- Pika uses: `PIKA_API_KEY`

If you do not have keys, use `--provider mock` (text) or `--provider local` (image).
