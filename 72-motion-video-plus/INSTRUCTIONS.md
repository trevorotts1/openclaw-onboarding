# Skill 72 Operator / Agent Instructions

## Trigger

Use Skill 72 when a client asks for a motion-graphics video: an animated promo, explainer, brand film, or kinetic-typography piece built from code-driven animation.

Do not use Skill 72 when the request clearly names AI video-model generation (Skill 67 `kie-video`), documentary montage or VSL pipelines (Skill 47 `movie-producer`), or hands-on editing of existing footage (video-editor).

## Execution

Follow these stages in order. Do not skip the two hard gates.

### 1. Intake

Collect: the video script (or a brief to write it from), the brand (or the facts to build its bible), target length, and delivery resolution. Write the run folder:

`<storage-root>/<video-name>/` containing `manifest.json`, `script.txt`, `scenes/`, `audio/`, and the brand bible.

### 2. Brand bible

Copy `references/brand-bible-template.md` to `<brand>-brand-bible.md` and fill every section. Load it on this run and every later run for the brand. Bright, human defaults: no dark-style designs, no generic AI-polished look.

### 3. Storage root

Resolve per environment, never hardcode: Mac uses `~/Downloads/openclaw-master-files/motion-videos/`; Docker VPS uses a persistent volume such as `/data/motion-videos`, never ephemeral container storage. Record the resolved path in the manifest.

### 4. Animation-code model selection (model-agnostic rule)

ASK the operator which model writes the animation code: their current model, GLM 5.3, DeepSeek, or whatever they name. Record the choice in `manifest.json` as `animation_model`. Never assume Opus 5.5 or any other model. Then hand the chosen model `references/animation-contract.md` plus the brand bible and the scene breakdown.

### 5. Scene animation code

One HTML file per scene honoring `references/animation-contract.md`: `window.__setTime(t)` as a pure function of t, no CSS transitions, no timer-driven motion, seeded randomness only, all assets local. Verify each scene exposes `__setTime` and `__sceneDuration` before any render.

### 6. Preview gate (HARD GATE)

Render every scene at 960x540, 15fps:

```bash
node scripts/render.js --manifest run/manifest.json --scene scene-01 --outdir work/preview/scene-01 --preview
```

Assemble a rough preview cut and get the operator's explicit approval per scene. Nobody iterates on a full render. Changes go back to step 5.

### 7. Voiceover

Write one TTS chunk per scene (2,000 to 4,000 chars, never mid-sentence). Then:

```bash
export FISH_AUDIO_API_KEY=...
python3 scripts/tts.py --manifest run/manifest.json --outdir work/audio
```

Default model `s2.1-pro`. `drama-3-preview` is opt-in only; `tts.py` verifies the served model from response metadata and stops on mismatch (see `references/fish-audio-tts.md`). Sequential requests, exponential backoff on 429.

### 8. Audio-first timing

Read `work/audio/durations.json`. Set each scene's `duration_seconds` in the manifest to its chunk's measured duration. The animation renders to the audio, not the other way around.

### 9. Preflight

```bash
node scripts/preflight.js --manifest run/manifest.json --max-hours 8
```

It calibrates with 20 real frames and recommends the worker count and segment length (5-minute standard; 15-minute only on strong systems). If it refuses, follow its advice: free disk, shorten, or take the segment route. Never hardcode worker counts.

### 10. Full render

One `render.js` process per scene, in parallel up to the preflight worker count. Each process chunks its browser every few hundred frames and supports `--resume`:

```bash
node scripts/render.js --manifest run/manifest.json --scene scene-01 --outdir work/scenes/scene-01 --resume
```

Segments encode per scene; PNGs are deleted right after each segment encodes.

### 11. Assembly

```bash
bash scripts/assemble.sh --manifest run/manifest.json --workdir work \
  --voiceover work/audio/voiceover.mp3 --out <storage-root>/<video-name>/<video-name>.mp4
```

Crossfaded joins, one continuous music bed over the final assembly, sidechain ducking under the voiceover, beat-synced UI sounds.

### 12. QC gate (HARD GATE)

```bash
bash scripts/qc.sh --manifest run/manifest.json --workdir work --final <storage-root>/<video-name>/<video-name>.mp4
```

Frame counts, zero-byte sweep, blackdetect, freezedetect, audio equals video duration, contact sheet. Review the contact sheet yourself: the 30-second human review. Then `bash scripts/sweep-chromium.sh` to clear orphans.

### 13. Delivery

Deliver the MP4 from `<storage-root>/<video-name>/` along with the contact sheet. Keep the animation sources, voiceover audio, script text, and manifest in the folder. Frame PNGs are always deleted.

## Maintenance check

`bash verify.sh` is for installation/update verification. It is not part of every normal video job.
