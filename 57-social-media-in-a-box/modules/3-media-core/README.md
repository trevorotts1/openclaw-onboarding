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
deterministic math validator (`AF-SM-STORYBOARD`) → Kie.ai Sora → poll → download.

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

## Ledger discipline (`AF-SM-MEDIA-LEDGER` / `AF-SM-CAROUSEL-FLOOR`)

One SQLite row per slide/job; states `pending → generating → qc → edit → complete | failed |
timeout`. Poll every **30s**; **≥10 complete** (9 LinkedIn) or **120-poll** timeout; assemble a
carousel only with **≥2** completed images. Every fail/timeout branch alerts the configured channel.
The ledger + manifest survive session limits — any mode resumes from ledger state.

```
python3 scripts/ledger.py summary --db working/media/ledger.db --run <brand>_<YYYY-Www> --assert-floor 2
python3 scripts/ledger.py --self-test
```
