---
name: motion-video-plus
description: Produces finished motion-graphics videos through a proven deterministic pipeline: an LLM writes scene animation as HTML/JS exposing window.__setTime(t), headless Chromium renders it frame by frame at 30fps, FFmpeg stitches frames with a Fish Audio TTS voiceover into an MP4. Scene-based manifests scale from 30 seconds to 2 hours. Use for promo videos, explainers, brand films, and any motion-graphics video. Do not use for AI video-model generation (Skill 67 kie-video) or documentary montage (Skill 47 movie-producer).
version: 1.0.0
---

# Motion Video Plus: Skill 72

This is the canonical motion-graphics video production skill. It turns a script and a brand bible into a finished MP4 through a pipeline that was proven on a real 30-second, 6-scene LiveConvo.chat promo: 909 frames rendered at about 0.5 seconds per frame, stitched with a Fish Audio voiceover.

## The pipeline in one paragraph

A model writes deterministic HTML/JS animation for each scene. Every animation exposes `window.__setTime(t)`, a pure function of time t in seconds that sets every element's style, with no CSS transitions and no timer-driven motion. Headless Chromium opens the page, seeks to each frame time, calls `__setTime(t)`, and screenshots at 30 frames per second. FFmpeg encodes each scene's frames, joins scenes with crossfades, lays one continuous music bed over the final assembly with sidechain ducking under the voiceover, adds beat-synced UI sounds, and delivers the MP4. No AI video model is involved at any step.

## Route boundaries first

Use this skill when the request is a motion-graphics video: kinetic typography, animated explainers, brand promos, product films built from code-driven animation.

Route elsewhere when the assignment is specifically:

- **Skill 67 `kie-video`**: AI video-model generation (Kie.ai), for footage-style or generative clips.
- **Skill 47 `movie-producer`**: OpenMontage documentary-montage or VSL/talking-head pipelines.
- **Skill 27 / video-editor**: hands-on editing of existing footage.

If the owner explicitly asks for this motion-graphics pipeline, use it even when the finished video later hands off to another rail for distribution.

## Proven stack only

FFmpeg, headless Chromium, a Node frame driver (`playwright-core`), Fish Audio TTS. These four are proven. Diffusion Studio, Hyperframes, and Remotion are UNTESTED alternatives: they are documented in `references/untested-alternatives.md` and must never be presented as verified.

## Model-agnostic by rule

This skill never assumes which model writes the animation code. At the start of every run, ASK the operator which model to use for animation authoring (their current model, GLM 5.3, DeepSeek, whatever they name). Record the choice in the run manifest. Never hardcode Opus 5.5 or any other model.

## Read only what the current stage needs

Start with `references/authority-map.md`, then use:

- Animation contract (what the model must write): `references/animation-contract.md`
- Manifest schema (scene order, durations, fps, resolution): `references/manifest-schema.json`
- Brand bible template (palette, type, logo, motion grammar, voice, sound): `references/brand-bible-template.md`
- Fish Audio TTS rules, models, pricing: `references/fish-audio-tts.md`
- Untested alternatives (read-only awareness): `references/untested-alternatives.md`
- Example 30-second, 6-scene manifest: `assets/example-manifest.json`

## Governing production order

`intake -> brand bible -> script -> model selection -> scene animation code -> preview gate -> voiceover -> full render -> assembly -> QC -> delivery`

Each stage's detail lives in `INSTRUCTIONS.md`. The two hard gates:

1. **Preview gate.** Low-res previews (960x540 at 15fps) for every scene must be approved by the operator before any full-quality render starts. Nobody iterates on a full render.
2. **QC gate.** `scripts/qc.sh` must pass before delivery: frame counts match the manifest, no missing or zero-byte frames, blackdetect and freezedetect sweeps clean, audio duration equals video duration, plus a contact sheet for the human 30-second review.

## The 15 design decisions and where they live

1. **Proven stack only.** This file and `references/untested-alternatives.md`.
2. **Model-agnostic.** `INSTRUCTIONS.md` step 4 asks and records the model choice.
3. **Scene-based architecture.** `references/manifest-schema.json`, `assets/example-manifest.json`; one HTML file per scene plus a manifest.
4. **Parallel chunked rendering with auto-resume.** `scripts/render.js`: fresh headless browser every few hundred frames (Chromium died at frame 809 of 909 in testing from memory exhaustion), resumes from the last completed frame, never restarts a finished chunk.
5. **Per-scene frame cleanup.** `scripts/render.js` and `scripts/assemble.sh` delete each scene's PNGs right after its segment encodes, in a finally/trap so cleanup runs even on failure. 30 seconds produced 359MB of PNGs; a 2-hour video would need about 86GB without cleanup.
6. **Segments.** 5-minute segments are the standard; preflight upgrades to 15-minute segments on strong systems only. `scripts/assemble.sh` joins segments with crossfades and lays ONE continuous music bed over the final assembly, never per-segment music.
7. **Chunked voiceover.** `scripts/tts.py`: one Fish Audio request per scene (2,000 to 4,000 chars, split at scene or paragraph boundaries, never mid-sentence), same reference voice on every request, temperature 0.3 to 0.5, sequential requests with exponential backoff on 429. Audio-first timing: each chunk's measured duration sets its scene's timeline. Default model `s2.1-pro`; `drama-3-preview` is opt-in with a served-model verification check (see `references/fish-audio-tts.md`).
8. **Fast low-res previews.** `scripts/render.js --preview`; required gate in `INSTRUCTIONS.md`.
9. **Three-layer sound design from the first draft.** `scripts/assemble.sh`: voiceover, music bed ducked via FFmpeg sidechain compression, beat-synced UI sounds.
10. **Automated QC plus contact sheet.** `scripts/qc.sh`.
11. **Brand bible per brand.** `references/brand-bible-template.md`, loaded on every run.
12. **Per-environment storage root.** Resolved in `scripts/render.js` and `INSTRUCTIONS.md`: Mac uses `~/Downloads/openclaw-master-files/motion-videos/`; Docker VPS uses a persistent volume such as `/data/motion-videos`, never ephemeral container storage. Layout `motion-videos/<video-name>/` keeps the final MP4, animation sources, voiceover audio, script text, and manifest. Frame PNGs are always deleted.
13. **Headless only.** Every script launches Chromium headless; browsers close in finally blocks; `scripts/sweep-chromium.sh` kills orphans and reports memory freed at the end of every run.
14. **Preflight.** `scripts/preflight.js`: cores, free RAM, free disk, 20-frame calibration render for the true per-frame rate, workers = min(cores minus 2, RAM budget at about 500MB per browser, scene count), wall-clock and peak-disk estimates; says plainly when the segment route is required instead of dying halfway.
15. **Bright, human design defaults.** No dark-style designs, no generic AI-polished look. Real brand assets, real typography. Encoded here, in `INSTRUCTIONS.md`, and in the brand bible template.

## What the operator provides

1. The video script (or a brief the script is written from).
2. The brand bible file for the brand (or the facts to build one from the template).
3. The animation-code model choice (step 4 of INSTRUCTIONS.md).
4. A Fish Audio API key in `FISH_AUDIO_API_KEY` and a voice reference id.
5. Preview approval before full render.

## What the skill never does

- Never opens a visible browser window.
- Never renders full quality before preview approval.
- Never stores API keys in the skill directory or in repo files.
- Never claims an untested renderer is proven.
- Never uses an Anthropic model in the pipeline.
