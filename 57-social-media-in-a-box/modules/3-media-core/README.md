# Module 3 — Media core

**Source:** `03-image-generator` (26) + `04-video-creator` (16) + `part6-carousel-image` (52) +
`part9-podcast-image` (28). **Prompts:** 05–08, 11–14 (baked). **Ledger:** `scripts/ledger.py`
(local SQLite, NO n8n data table). **Phase:** P4.

## Lanes (parallel; no shared dependency until publish)

### Image
Visual Prompt Architect (05) → Kie.ai GPT Image 2.5 sunburst (`gpt-image-2-5-sunburst-text-to-image`, Skill 66 id, AGENTS.md N43) → **Prompt-Doctor** retry on 422 (06, shorten /
remove banned words, preserve intent) → vision QC → winner staged → SeedDream resizes 9:16 / 16:9
when a Reel/Story/TikTok/Short post type demands. The Gemini grid selector (07, returns a single
digit 0–3; `AF-SM-GRID-DIGIT`) applies only when a provider returns a multi-image collage; GPT Image
2.5 returns one image, so it is normally skipped. Midjourney is no longer used (F29).

### Video
Storyboard Architect (08; **3–7 scenes, sum EXACTLY 25.0s**, max 1.5 spoken words/sec) →
deterministic math validator (`AF-SM-STORYBOARD`) → the Skill 67 (kie-video) model selector (a 25 second single clip resolves to a long-clip model such as `wan/3-0-video`; no Sora, no model named in this skill) → poll → download.

### Carousel image (the QC loop)
GPT Image 2.5 sunburst generate (12; 3:4, 2K, typographic `textOnImage`; 3:4 is the N43 substitution for 4:5) → **Gemini QC bot** casual-viewer
test (11; verbatim in both QC 1 and QC 2) → FAIL → **SeedDream 4.5 edit** from the QC feedback (13,
Instagram center-crop safety) → **QC 2** → final fallback strips ALL text (13 fallback) → ledger
update. The QC output is `Good` or the JSON-safe 4-field fix set (`AF-SM-QC-JSON`).

### Podcast cover + audio (C3, v0.2.0)
1:1 art (14; GPT Image 2.5 sunburst, same id and payload as Skill 58 `generate_cover.sh`; 1400×1400 JPEG, `AF-SM-PODCAST-COVER`), one retry, fail → notification + empty-URL
return. **v0.2.0 folds the AUDIO episode in** (merge plan C3): `--mode podcast` runs prompt 17
(1,500–2,000-word `[emotion]`-tagged script) → Fish-Audio S2 TTS → ffprobe 600–900 s / ≥128 kbps
(`AF-SM-PODCAST-SCRIPT` / `AF-SM-PODCAST-DURATION`) → local Podbean API call (no n8n), with the
cover as its media sub-step. Unconfigured Fish-Audio/Podbean → `PODCAST_DEFERRED` labeled skip,
never a failure. (Supersedes the v0.1.0 cover-only boundary / PRD Open Decision D3.)

### Thumbnails (C7, v0.2.0)
Platform-optimized thumbnail generation is a media-core **sub-step on the image lane** (merge plan
C7): the same Visual-Prompt-Architect → Kie.ai → Gemini-judge chain renders the platform's
thumbnail crop (YouTube 1280×720 focus; FB/IG link-card crop) as an extra ledger job — same SQLite
states, same fail/timeout alerts, same `AF-SM-MEDIA-LEDGER` terminal-state gate. No separate
pipeline, no new prover: a thumbnail is a media job like any other. (Its content-side sibling —
FB/IG **Stories captions** — ships as reformatter output banded by `AF-SM-STORIES-CAPTION` ≤250.)

## KIE dispatch contract (every paid image, edit and video job)

Policy owners: Skill 66 (image) and Skill 67 (video). Mechanics: Skill 74 (`74-kie-live-adapter/scripts/kie_live_adapter.py`). Rules: `07-kie-setup/references/kie-common-rules.md` (it wins on any conflict). The social image default is GPT Image 2.5 Sunburst (rule 13 keeps it at the newest GPT Image generation, resolved with `latest-family --family gpt-image`); Nano Banana is never primary. Per job, in order, each step fail-closed:

1. Route: model id from the policy owner (`gpt-image-2-5-sunburst-text-to-image`, or `-image-to-image` with a reference; video through the Skill 67 selector). Never a model id from memory.
2. Expand the seed prompt (prompt 05) to 95 to 100 percent of the model maxLength; check with `prompt-budget --model ID --check --prompt-file F` (exit 3 means add the printed characters, exit 4 means cut them).
3. `validate --model ID --payload input.json` against the live schema (registry fallback).
4. `preflight --model ID` (balance must cover price x 1.30; this skill's preflight floor of 200 credits also applies). Estimates come from `price --model ID`, never a table in this skill.
5. `run --request req.json --save-dir DIR --mode active --json` (createTask, poll, save before the links expire). `submit` never picks or changes a model; on `skipped` or `fail` the caller applies its own documented fallback and records it.
6. Visual QC (Gemini loop), then the finished file goes to the GHL Media Library and only the CDN URL is used downstream.

Podcast cover: the 2K output is larger than the band, so resize to exactly 1400x1400 JPEG (RGB, under 500 KB) before `AF-SM-PODCAST-COVER`. Skill 35 accepts 1400 to 3000 px for Podbean; 1400x1400 satisfies both. The `image_prompt_*` bands in `config/bands.json` limit the authored seed only; the transmitted prompt follows step 2.

## Ledger discipline (`AF-SM-MEDIA-LEDGER` / `AF-SM-CAROUSEL-FLOOR`)

One SQLite row per slide/job; states `pending → generating → qc → edit → complete | failed |
timeout`. Poll every **30s**; **≥10 complete** (9 LinkedIn) or **120-poll** timeout; assemble a
carousel only with **≥2** completed images. Every fail/timeout branch alerts the configured channel.
The ledger + manifest survive session limits — any mode resumes from ledger state.

```
python3 scripts/ledger.py summary --db working/media/ledger.db --run <brand>_<YYYY-Www> --assert-floor 2
python3 scripts/ledger.py --self-test
```
