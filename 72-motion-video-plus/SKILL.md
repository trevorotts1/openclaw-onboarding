---
name: motion-video-plus
description: Produces finished motion-graphics videos through a proven deterministic pipeline: an LLM writes scene animation as HTML/JS exposing window.__setTime(t), headless Chromium renders it frame by frame at 30fps, FFmpeg stitches frames with a Fish Audio TTS voiceover into an MP4. Scene-based manifests scale from 30 seconds to 2 hours. Use for promo videos, explainers, brand films, and any motion-graphics video. Do not use for AI video-model generation (Skill 67 kie-video) or documentary montage (Skill 47 movie-producer).
version: 1.0.0
---

# Motion Video Plus: Skill 72

This is the canonical motion-graphics video production skill. It turns a script and a brand bible into a finished MP4 through a pipeline that was proven on a real 30-second, 6-scene LiveConvo.chat promo: 909 frames rendered at about 0.5 seconds per frame, stitched with a Fish Audio voiceover.

## The pipeline in one paragraph

A model writes deterministic HTML/JS animation for each scene. Every animation exposes `window.__setTime(t)`, a pure function of time t in seconds that sets every element's style, with no CSS transitions and no timer-driven motion. Headless Chromium opens the page, seeks to each frame time, calls `__setTime(t)`, and screenshots at 30 frames per second. FFmpeg encodes each scene's frames, joins scenes with crossfades, lays one continuous synthesized music bed over the final assembly with sidechain ducking under the voiceover, adds beat-synced synthesized UI sounds, finishes at -14 LUFS, and delivers the MP4. No AI video model is involved at any step.

Parallelize every stage, not just the frame render: scene animation files are built in parallel once the brief is locked, TTS chunks are fetched concurrently, spot-check stills render for all scenes at once, and the score and SFX synthesize while frames render. What stays sequential is the decision chain: script, voiceover durations, scene timing, animation. Measured on the reference box (12 CPU, 24GB RAM), a 5-minute video ran 85 minutes with only the frame render parallelized. With every stage parallelized the warm-pipeline target is about 30 minutes: script 5, TTS plus animation 7, render 10 to 11 at 8 workers (measured 0.56 seconds per frame per worker), assembly plus QC plus mux 5. Add about 4 minutes in a fresh environment.

One honest note: the pipeline technique was proven on that 30-second promo. Treat your first full run through the 15 stages as this skill's shakedown run.

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
- Motion grammar (the design constitution: banned cliches, spring presets, beat-led hits, masked type, safe zones): `references/motion-grammar.md`
- Critique protocol (fresh-critic scoring, 8 criteria, failure-mode checklist): `references/critique-protocol.md`
- Director's brief template: `references/directors-brief-template.md`
- Pre-production chapters (studio setup through the approved brief): `references/pre-production/`
- Manifest schema (scene order, durations, fps, resolution): `references/manifest-schema.json`
- Beat grid schema: `references/beats-schema.json`
- Brand bible template (palette, type, logo, motion grammar, voice, sound): `references/brand-bible-template.md`
- Fish Audio TTS rules, models, pricing: `references/fish-audio-tts.md`
- Untested alternatives (read-only awareness): `references/untested-alternatives.md`
- Example 30-second, 6-scene manifest: `assets/example-manifest.json`

## Governing production order

`pre-production -> brand bible -> script -> model selection -> grammar-constrained scene animation -> preview gate -> critique gate -> determinism gate -> voiceover -> audio-first timing -> preflight -> full render -> synth sound and assembly -> QC gate -> delivery`

Each stage's detail lives in `INSTRUCTIONS.md`. The four hard gates:

1. **Preview gate.** Low-res previews (960x540 at 15fps) for every scene must be approved by the operator before any full-quality render starts. Nobody iterates on a full render.
2. **Critique gate.** A fresh critic (an agent that did not write the animation) scores the 8 criteria in `references/critique-protocol.md` with evidence. Minimum 3 rounds; every score must reach 8+ before the full render.
3. **Determinism gate.** `scripts/verify-determinism.js` must pass for every scene: probe frames rendered cold must match the same frames rendered after seeking elsewhere. No pixel drift.
4. **QC gate.** `scripts/qc.sh` must pass before delivery: frame counts match the manifest, no missing or zero-byte frames, blackdetect and freezedetect sweeps clean, determinism re-check, audio duration equals video duration, contact sheet plus per-beat sheet for the human 30-second review.

## The 15 design decisions and where they live

1. **Proven stack only.** This file and `references/untested-alternatives.md`.
2. **Model-agnostic.** `INSTRUCTIONS.md` step 4 asks and records the model choice.
3. **Scene-based architecture.** `references/manifest-schema.json`, `assets/example-manifest.json`; one HTML file per scene plus a manifest.
4. **Parallel chunked rendering with auto-resume.** `scripts/render.js`: fresh headless browser every few hundred frames (Chromium died at frame 809 of 909 in testing from memory exhaustion), resumes from the last completed frame, never restarts a finished chunk.
5. **Per-scene frame cleanup.** `scripts/render.js` and `scripts/assemble.sh` delete each scene's PNGs right after its segment encodes, in a finally/trap so cleanup runs even on failure. 30 seconds produced 359MB of PNGs; a 2-hour video would need about 86GB without cleanup.
6. **Segments.** 5-minute segments are the standard; preflight upgrades to 15-minute segments on strong systems only. `scripts/assemble.sh` joins segments with crossfades and lays ONE continuous music bed over the final assembly, never per-segment music.
7. **Chunked voiceover.** `scripts/tts.py`: one Fish Audio request per scene (2,000 to 4,000 chars, split at scene or paragraph boundaries, never mid-sentence), same reference voice on every request, temperature 0.3 to 0.5, requests fired CONCURRENTLY with bounded parallelism (default 5, the starter-tier concurrent limit, tunable with `--max-workers`), exponential backoff on 429 per request, results reassembled in scene order. Audio-first timing is unchanged: each chunk's measured duration still sets its scene's timeline. Default model `s2.1-pro`; `drama-3-preview` is opt-in with a served-model verification check (see `references/fish-audio-tts.md`).
8. **Fast low-res previews.** `scripts/render.js --preview`; required gate in `INSTRUCTIONS.md`.
9. **Three-layer sound design from the first draft.** `scripts/assemble.sh`: voiceover, music bed ducked via FFmpeg sidechain compression, beat-synced UI sounds. The music bed and UI sounds are synthesized in code by default (`scripts/synth-score.py`, `scripts/synth-sfx.py`); a supplied track is the only exception. Final mix lands at -14 LUFS integrated.
10. **Automated QC plus contact sheet.** `scripts/qc.sh`.
11. **Brand bible per brand.** `references/brand-bible-template.md`, loaded on every run.
12. **Per-environment storage root.** Resolved in `scripts/render.js` and `INSTRUCTIONS.md`: Mac uses `~/Downloads/openclaw-master-files/motion-videos/`; Docker VPS uses a persistent volume such as `/data/motion-videos`, never ephemeral container storage. Layout `motion-videos/<video-name>/` keeps the final MP4, animation sources, voiceover audio, script text, and manifest. Frame PNGs are always deleted.
13. **Headless only.** Every script launches Chromium headless; browsers close in finally blocks; `scripts/sweep-chromium.sh` kills orphans and reports memory freed at the end of every run.
14. **Preflight.** `scripts/preflight.js`: cores, free RAM, free disk, 20-frame calibration render for the true per-frame rate (reference baseline 0.56s per frame per worker on the 12-CPU/24GB box, refined per machine), workers = min(cores minus 2, RAM budget at about 500MB per browser, scene count, load-proven cap). The calibration measures system load with one browser active and caps workers before projected load goes critical; a worker count is never recommended from core count alone. Wall-clock and peak-disk estimates; says plainly when the segment route is required instead of dying halfway.
15. **Bright, human design defaults.** No dark-style designs, no generic AI-polished look. Real brand assets, real typography. Encoded here, in `INSTRUCTIONS.md`, and in the brand bible template.

## Adapted systems (borrowed concepts, original implementation)

Six systems were adapted from an analysis of a third-party motion-reel kit. The concepts are standard practice; every file below is our own original implementation. Nothing from that kit was copied verbatim.

1. **Motion grammar.** `references/motion-grammar.md` plus `scripts/lint-grammar.py`: banned-cliche list, springs-only motion with our named presets (`weighty`, `panel`, `snap`, `drift`), visual hits leading the beat by 2 frames, masked-word typography rules, 9:16 and 16:9 safe zones.
2. **Critique system.** `references/critique-protocol.md` plus `scripts/critique-bundle.sh`: a fresh critic scores our 8 criteria with evidence, minimum 3 rounds until every score is 8+, plus our known-failure-modes checklist.
3. **Synthesized sound as the default.** `scripts/synth-score.py` (original score in code), `scripts/beat-grid.py` (derived beat grid), `scripts/synth-sfx.py` (pops, clicks, whooshes, thumps), mixed in `scripts/assemble.sh` to -14 LUFS with sidechain ducking. No stock music, no licensing.
4. **Determinism verification.** `scripts/verify-determinism.js`: probe frames rendered cold versus after seeking elsewhere; fails the gate on pixel drift.
5. **Review tooling.** In `scripts/render.js`: `--still`, `--cliprange`, `--mux` (re-mux audio without re-rendering), `--beatsheet` (per-beat contact sheet). Bundled for critics by `scripts/critique-bundle.sh`.
6. **Pre-production workflow.** `references/pre-production/` (six chapters: studio setup, house rules, brand assets, one-liner, steal-the-grammar, director's brief) plus `references/directors-brief-template.md`, wired as the first stages of `INSTRUCTIONS.md`.

## Fleet rendering is frontier, not a promise

Frame ranges are independent units, so splitting a render across multiple machines is architecturally free: 4 boxes at 8 workers each is roughly a 3-minute frame render, about 20 minutes total for a 5-minute video. This has never been tested. It is future work, not a capability the skill offers today. Never present it as one. See `references/untested-alternatives.md`.

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
