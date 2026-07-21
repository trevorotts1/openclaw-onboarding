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

---

## Optional alternative generator: Agnes Video 2.0

**KIE.ai (VEO) stays the default/primary video provider for this skill** (`--provider kieai`); the
Runway, Pika, mock, and local paths are unchanged. Agnes Video 2.0 is an **additional option** an
agent MAY choose for the raw clip — it adds a path, it does not replace or reword anything above.

Agnes ships as its **own skill** (the same way KIE.ai setup is its own skill, Skill 07). This skill's
`scripts/` generators are not modified, so there is **no `--provider agnes` flag**. To use Agnes,
generate the raw clip with the Agnes Video skill, then bring the resulting `.mp4` back into this skill
for assembly, audio mixing, resize/crop, and export.

- **Model / endpoint:** `agnes-video-v2.0`, `POST https://apihub.agnes-ai.com/v1/videos` — asynchronous:
  create the task, then poll `GET https://apihub.agnes-ai.com/agnesapi?video_id=<VIDEO_ID>`.
- **Source of truth for the delivered clip** is the response `seconds`, `size`, and
  `metadata.size_mapping` — never the requested `width`/`height`/`num_frames` (Agnes normalizes them).
- **Credential:** the fleet already provisions `AGNES_AI_API_KEY` (endpoint `apihub.agnes-ai.com/v1`).
  Confirm it is **SET** before choosing Agnes — never print or echo the value. If it is not set, stay
  on the default `--provider kieai` (VEO) path.

### Tier behavior — operator-set, never hardcoded

Which Agnes plan a box is on (free / enterprise / a paid Token Plan) is an **account property this SOP
cannot know statically**. Read it from an **operator-set config value** (for example `AGNES_TIER`, via
`openclaw config get AGNES_TIER`) and do **not** bake per-tier image/video limits into skill logic:

- Agnes publishes its quotas as **non-contractual, mutable reference values** and names the account
  console as the final authority, so a hardcoded ceiling would be fabricated data.
- Where a limit is **unverified**, respect the **account's own rate limiting**: treat an HTTP `429`
  (with exponential backoff) and the console's Usage / Billing page as the live ceiling, not a number
  written in this doc.
- Cost note (evidence-backed): for **image/video** workloads the paid Token Plan tiers do **not** raise
  media throughput — only the text-request quota scales with tier — so paying up buys no extra video
  volume for this skill's use case.
