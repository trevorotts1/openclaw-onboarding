---
name: storyboard-writer
description: Create video storyboards matching AI model capabilities. Plans video structure based on model duration limits (Veo 8s, Kling, Seedance, etc.) and generates segment prompts. Model choice is owned by Skill 67 (KIE Video).
---

# Storyboard Writer

Plan a video before generating any clips.

This skill:
- matches your storyboard to the model's clip duration limits
- calculates how many clips you need for a target runtime
- estimates cost using bundled fallback numbers (not live pricing)
- exports a storyboard to JSON and Markdown

## Before Running - Collect These from the User

Ask the user ONE AT A TIME before calling the script:

1. **What is the video about?** (topic - required)
2. **How long should it be?** (seconds - default: 60s social, 300s YouTube)
3. **What platform?** YouTube / TikTok / Instagram / General
4. **Budget limit?** (optional - if given, use cheapest model that fits)
5. **Preferred model?** (optional - if none given, do not recommend from platform: run Skill 67's selector, see below)

**Model choice (policy owner: Skill 67, `67-kie-video`):**
- If the user names a model, use that model. An explicit pick always wins.
- If the user names none, do NOT pick from this skill's snapshot. Run Skill 67's selector and use its answer:
  `python3 ~/.openclaw/skills/67-kie-video/scripts/select_video_model.py "<the user's video request>"`
- The selector returns a model from Skill 67's registry (`67-kie-video/models.json`). Plan clip lengths from that model's `duration_window_seconds` in the registry. If the snapshot (`scripts/model-database.json`) has a matching id, you may use it as a convenience for clip math only.
- Budget-first requests: ask Skill 67 for the cheapest model that fits, and get the price with `python3 74-kie-live-adapter/scripts/kie_live_adapter.py price --model <id>` (Skill 74, live `pricingDesc`; fallback snapshot `74-kie-live-adapter/references/kie-model-registry.json`). Never quote a price from this skill's snapshot as current.
- **Sora is never a default and never an option.** The Video department prohibits OpenAI Sora (`23-ai-workforce-blueprint/templates/role-library/video/ai-video-generator-specialist.md`, the "PROHIBITED - SORA" rule). The Sora rows in the snapshot are historical data only.
- Every paid generation needs a Rule Zero announcement (provider, model, estimated USD) and owner approval before it runs. KIE rules (endpoints, rate limit, credit preflight, client's own key): `07-kie-setup/references/kie-common-rules.md`.

**Important:** The script generates segment structure and timing. You (the agent) are responsible for writing the actual creative prompt for each segment based on topic, style, tone, and narrative arc. Do not use the template placeholders as final output - replace them with specific, visual, production-ready descriptions.

## Quick Start

### Example: 5-minute video plan with Veo 3.1 (planning ids come from the snapshot; the model itself is chosen per Skill 67)

```bash
python3 scripts/create_storyboard.py --duration 300 --model veo-3-1 --topic "Product Demo" --output product_demo
```

### Example: 5-minute video plan with Kling 3.0 (10s clips)

```bash
python3 scripts/create_storyboard.py --duration 300 --model kling-3 --topic "Tutorial" --output tutorial
```

## Model data (dated snapshot, not authoritative)

Durations and indicative prices in `scripts/model-database.json` are a dated snapshot (last verified 2024-01-15). They are NOT the source of truth for which models exist, what they cost today, or which one to use:
- Which model to use (policy): Skill 67 (`67-kie-video`: `models.json` and `scripts/select_video_model.py`).
- What the live KIE catalog offers and costs now: `python3 74-kie-live-adapter/scripts/kie_live_adapter.py price --model <id>` (Skill 74). The price fields in the JSON are fallback constants for the cost estimate only.
- If the snapshot disagrees with Skill 67 or Skill 74, Skill 67 and Skill 74 win.

To see the model IDs this skill supports:

```bash
python3 -c "from scripts.model_database import list_models; print('\n'.join(list_models()))"
```

## What gets generated

Running `create_storyboard.py` writes two files:
- `<output>.json`
- `<output>.md`

## Included files

| File | Purpose |
|------|---------|
| `scripts/create_storyboard.py` | Main storyboard generator |
| `scripts/model_database.py` | Loads model durations and pricing from JSON |
| `scripts/model-database.json` | Dated, non-authoritative snapshot of model durations and indicative prices (live catalog: Skill 74, policy: Skill 67) |
