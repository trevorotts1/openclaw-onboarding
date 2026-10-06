# KIE.AI Video Models Reference (dated snapshot, NOT authoritative)

> **Status: historical snapshot, not a complete guide.** This table was written before the KIE catalog moved on and has no verification date. Model names and availability below may be out of date. Do not use it to pick a model; it holds no prices.
>
> - **Which model to use (policy owner):** Skill 67 (`67-kie-video`: `models.json` and `scripts/select_video_model.py`).
> - **What the live catalog offers and costs now:** Skill 74 (`74-kie-live-adapter`). Price: `python3 74-kie-live-adapter/scripts/kie_live_adapter.py price --model <id>` (live `pricingDesc`; fallback snapshot `74-kie-live-adapter/references/kie-model-registry.json`). Limits, durations, resolutions: `kie_live_adapter.py validate` or that registry.
> - **This file contains no prices and no numeric model limits on purpose**, so there is exactly one price authority.
> - **KIE rules (endpoints, rate limit, credit preflight, saving results, client's own key):** `07-kie-setup/references/kie-common-rules.md`.
> - If anything here disagrees with Skill 67, Skill 74, or the rules file above, they win.
> - **Sora is prohibited** by the Video department (`23-ai-workforce-blueprint/templates/role-library/video/ai-video-generator-specialist.md`). The Sora section below is kept only as history and is never a recommendation.

## Text-to-Video Generation Models

### Veo 3.1 Series (Google)

| Model | Best For |
|-------|----------|
| **Veo 3.1 Fast** | Rapid iteration, social media content, cost-effective B-roll |
| **Veo 3.1 Quality** | Premium cinematic B-roll, professional visuals, smoother motion |

**Features:**
- Native audio generation (ambient sound, effects)
- Start & End Frame control for smooth transitions
- Multi-image reference for visual consistency
- Extend feature for longer clips
- Strong prompt adherence

---

### Sora 2 Series (OpenAI) - PROHIBITED, history only

The Video department prohibits Sora. Do not recommend, select, or generate with it. Retained only so old notes still make sense.

| Model | Best For |
|-------|----------|
| **Sora 2** | Creative control, narrative-driven content |
| **Sora 2 Pro** | Enhanced quality with richer visual/audio details |
| **Sora 2 Storyboard** | Precise frame-by-frame creative control, storyboard-based generation |

**Features:**
- Strong physics consistency
- Excellent for narrative sequences
- Creative control tools
- Storyboard integration (Storyboard variant)

---

### Kling 3.0

| Model | Best For |
|-------|----------|
| **Kling 3.0** | High-quality video generation, alternative to Veo |

**Features:**
- Competitive quality to Veo and Sora
- Good motion consistency
- Suitable for various video styles

---

### Wan 2.6

| Model | Best For |
|-------|----------|
| **Wan 2.6** | General video creation, diverse content types |

**Features:**
- Versatile video generation
- Good for experimentation
- Alternative style outputs

---

## Specialized Models

### Seed Dance Models

| Model | Best For |
|-------|----------|
| **Seed Dance** | Dance/movement-focused video generation, human motion |

**Features:**
- Specialized for human movement and dance
- Better motion capture for figures in motion
- Good for fitness, dance, or action content

---

### Runway Aleph

| Model | Best For |
|-------|----------|
| **Runway Aleph** | Video-to-video editing, object manipulation |

**Features:**
- In-context video model for multi-task editing
- Object add/remove
- Relighting
- Style changes
- Angle modifications

---

## Video Enhancement/Upscaling

### Topaz Video AI (via KIE.AI)

| Model | Best For |
|-------|----------|
| **Topaz Video Upscaler** | AI video upscaling, quality enhancement |

**Features:**
- Upscales low-resolution footage
- Denoising
- Frame interpolation (smooth slow-motion)
- Stabilization
- Face enhancement

**When to Use:**
- Upscaling old/low-res training footage
- Improving video quality before editing
- Creating multiple resolution versions

**Note:** Topaz is a premium tool. For free local upscaling, use **video2x** (`pip install video2x`)

---

## Model Selection Guide

### For B-Roll Generation:

Do not choose from this file. Ask Skill 67's selector, then price the pick with Skill 74: `python3 74-kie-live-adapter/scripts/kie_live_adapter.py price --model <id>`.

```bash
python3 ~/.openclaw/skills/67-kie-video/scripts/select_video_model.py "<what the B-roll clip shows, length, vertical or horizontal>"
```

If the user names a model, that explicit pick wins. Announce provider, model and estimated USD (from that price command) and get approval before any paid generation.

### For Video Enhancement:

| Task | Recommended Tool |
|------|------------------|
| **Upscale to 4K** | Topaz Video Upscaler (via KIE.AI) or video2x (free local) |
| **Denoise** | Topaz or video2x |
| **Frame interpolation** | Topaz or video2x |

---

## KIE.AI Platform Details

Prices, credit conversion, rate limits and endpoints are owned by `07-kie-setup/references/kie-common-rules.md` (rules) and Skill 74 (live catalog and `pricingDesc`). They are not restated here so they cannot drift.

**Technical Details (see the rules file for the authority):**
- All tasks are asynchronous (receive a task id, then check for completion).
- Generated media is kept by KIE for a limited time and download URLs expire, so save results immediately (rules file).
- A credit preflight (estimated cost x 1.30) runs before a paid batch (rules file).

**Integration Note:**
This skill ships no KIE client and no KIE script. The agent generates B-roll clips through Skill 67 (model choice and dispatch, using the client's own KIE key), then uses this skill to assemble them with the talking head video.

---

## Workflow Integration

When the agent runs the B-roll workflow:

1. **Analyze** the talking head video with `analyze-video.sh`
2. **Select** the model for each clip with Skill 67 (`select_video_model.py`), and get the live price from Skill 74
3. **Generate** the B-roll through Skill 67 after the owner approves the estimated cost
4. **Merge** the B-roll using `merge-broll.sh` with the original video
