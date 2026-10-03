# Skill 72 Operator / Agent Instructions

## Trigger

Use Skill 72 when a client asks for a motion-graphics video: an animated promo, explainer, brand film, or kinetic-typography piece built from code-driven animation.

Do not use Skill 72 when the request clearly names AI video-model generation (Skill 67 `kie-video`), documentary montage or VSL pipelines (Skill 47 `movie-producer`), or hands-on editing of existing footage (video-editor).

## Execution

Follow these stages in order. Do not skip the four hard gates.

### What parallelizes and what stays sequential

Parallelize every stage; the units inside each stage are independent. Scene animation files build in parallel once the brief is locked (stage 5). Spot-check stills render for all scenes concurrently (stage 6). TTS chunks fetch concurrently with bounded parallelism (stage 9). Score and SFX synthesis overlaps the frame render (stage 13). What STAYS sequential is the decision chain: script, then voiceover durations, then scene timing, then animation. Never start a stage that depends on a decision an earlier stage has not made yet.

### 1. Pre-production

Work through `references/pre-production/` in order:

1. **Studio setup** (`01-studio-setup.md`): toolchain and secrets check, once per machine.
2. **House rules** (`02-house-rules.md`): the render contract, the look rules, the sound rules, the critique loop.
3. **Brand assets** (`03-brand-assets.md`): collect the real logo, typefaces, palette, product UI, and voice reference. Fill the brand bible from `references/brand-bible-template.md`.
4. **One-liner** (`04-the-one-liner.md`): one sentence the whole video must earn.
5. **Steal the grammar** (`05-steal-the-grammar.md`): if the operator names a reference video, take its grammar, never its content, logos, or characters.
6. **Director's brief** (`06-directors-brief.md`): write it from `references/directors-brief-template.md` and get the operator's explicit approval. No animation code, no voiceover, no renders until the brief is approved.

Write the run folder now:

`<storage-root>/<video-name>/` containing `manifest.json`, `script.txt`, `scenes/`, `audio/`, the brand bible, and the approved brief.

### 2. Brand bible

Load the filled `<brand>-brand-bible.md` on this run and every later run for the brand. Bright, human defaults: no dark-style designs, no generic AI-polished look.

### 3. Storage root

Resolve per environment, never hardcode: Mac uses `~/Downloads/openclaw-master-files/motion-videos/`; Docker VPS uses a persistent volume such as `/data/motion-videos`, never ephemeral container storage. Record the resolved path in the manifest.

### 4. Animation-code model selection (model-agnostic rule)

ASK the operator which model writes the animation code: their current model, GLM 5.3, DeepSeek, or whatever they name. Record the choice in `manifest.json` as `animation_model`. Never assume Opus 5.5 or any other model. Then hand the chosen model `references/animation-contract.md`, `references/motion-grammar.md`, the brand bible, and the approved director's brief.

### 5. Scene animation code (grammar-constrained)

Build all scene files in parallel once the director's brief (stage 1) is approved and art direction is locked: scenes are independent units, so draft them concurrently and unify afterward. One HTML file per scene honoring `references/animation-contract.md` AND `references/motion-grammar.md`: `window.__setTime(t)` as a pure function of t, no CSS transitions, no timer-driven motion, seeded randomness only, springs-only motion using the named presets, visual hits 2 frames before the beat, masked-word typography, all assets local.

Lock the BPM in the director's brief now (manifest `music_bpm`, default 120). The beat grid is pure BPM math: `scripts/beat-grid.py` derives it from the synthesis parameters, so animation authoring proceeds against the theoretical grid WITHOUT waiting for the synthesized WAV. Audio synthesis and animation are parallel branches off the locked BPM, not sequential steps.

Then lint every scene file:

```bash
python3 scripts/lint-grammar.py scenes/scene-01.html
```

The linter flags violations; it never auto-fixes. Fix what it flags before moving on.

### 6. Preview gate (HARD GATE)

Render every scene at 960x540, 15fps, all scenes concurrently (one render.js process per scene, backgrounded up to the preflight worker count):

```bash
for s in scene-01 scene-02 scene-03 scene-04 scene-05 scene-06; do
  node scripts/render.js --manifest run/manifest.json --scene $s --outdir work/preview/$s --preview &
done
wait
```

Render spot-check stills for all scenes concurrently the same way:

```bash
for s in scene-01 scene-02 scene-03 scene-04 scene-05 scene-06; do
  node scripts/render.js --still 2.0 --manifest run/manifest.json --scene $s --outdir work/review &
done
wait
```

Assemble a rough preview cut and get the operator's explicit approval per scene. Nobody iterates on a full render. Changes go back to step 5.

### 7. Critique gate (HARD GATE)

Build the review bundle and hand it to a fresh critic: an agent that did NOT write the animation.

```bash
bash scripts/critique-bundle.sh --video work/preview-cut.mp4 --outdir review/r1 \
  --beats work/audio/beats.json
```

The critic follows `references/critique-protocol.md`: scores the 8 criteria with evidence, minimum 3 rounds, every score must reach 8+ before sign-off. The animation author fixes the 3 worst problems per round and re-renders the preview. The gate opens only on a SHIP verdict. No full render before it.

### 8. Determinism gate (HARD GATE)

Every scene's animation must be a pure function of t. Verify before the full render:

```bash
node scripts/verify-determinism.js --manifest run/manifest.json --scene scene-01
```

Probe frames rendered cold must match the same frames rendered after seeking elsewhere. On drift, fix the cause (timers, unseeded randomness, GPU-layer tricks) and re-verify. `scripts/qc.sh` re-checks this at the end as a backstop.

### 9. Voiceover

Write one TTS chunk per scene (2,000 to 4,000 chars, never mid-sentence). Then:

```bash
export FISH_AUDIO_API_KEY=...
python3 scripts/tts.py --manifest run/manifest.json --outdir work/audio
```

Default model `s2.1-pro`. `drama-3-preview` is opt-in only; `tts.py` verifies the served model from response metadata and stops on mismatch (see `references/fish-audio-tts.md`). Requests fire concurrently (default 5 at a time, the starter-tier limit; tune with `--max-workers`), each with exponential backoff on 429; chunks are reassembled in scene order. Audio-first timing is unchanged: the measured durations still set scene timing, concurrency only changes how the chunks are fetched.

### 10. Audio-first timing

Read `work/audio/durations.json`. Set each scene's `duration_seconds` in the manifest to its chunk's measured duration. The animation renders to the audio, not the other way around. The beat grid is used INSIDE scenes for motion and SFX sync; the voiceover stays the master clock.

### 11. Preflight

```bash
node scripts/preflight.js --manifest run/manifest.json --max-hours 8
```

It calibrates with 20 real frames and recommends the worker count and segment length (5-minute standard; 15-minute only on strong systems). If it refuses, follow its advice: free disk, shorten, or take the segment route. Never hardcode worker counts.

### 12. Full render

One `render.js` process per scene, in parallel up to the preflight worker count. Each process chunks its browser every few hundred frames and supports `--resume`:

```bash
node scripts/render.js --manifest run/manifest.json --scene scene-01 --outdir work/scenes/scene-01 --resume
```

Segments encode per scene; PNGs are deleted right after each segment encodes.

### 13. Synthesized sound and assembly

Kick off score and SFX synthesis as soon as the BPM is locked and scene durations are known (end of stage 10), overlapping the frame render (stage 12). They do not depend on the frames:

```bash
DUR=$(python3 -c "import json; print(sum(json.load(open('work/audio/durations.json')).values()))")
BPM=$(python3 -c "import json; print(json.load(open('run/manifest.json')).get('music_bpm', 120))")
python3 scripts/synth-score.py --bpm $BPM --duration $DUR --seed 7 --outdir work/audio &
python3 scripts/synth-sfx.py --seed 7 --outdir work/audio/sfx &
wait
python3 scripts/beat-grid.py --params work/audio/score-params.json --out work/audio/beats.json
```

Then pass the pre-synthesized inputs to `assemble.sh` so it reuses them instead of re-synthesizing:

```bash
bash scripts/assemble.sh --manifest run/manifest.json --workdir work \
  --voiceover work/audio/voiceover.mp3 \
  --score work/audio/score.wav --beats work/audio/beats.json --sfx-dir work/audio/sfx \
  --out <storage-root>/<video-name>/<video-name>.mp4
```

If you skip the early synthesis, `assemble.sh` synthesizes the same deterministic outputs itself. Unless the manifest names a supplied `music_bed` track, the score and UI sounds are synthesized originals either way.

Crossfaded joins, one continuous score over the final assembly, sidechain ducking under the voiceover, beat-synced UI sounds, finished at -14 LUFS integrated. If only the mix changes later, re-mux without re-rendering:

```bash
node scripts/render.js --mux work/audio/mix2.mp3 --video final.mp4 --out final2.mp4
```

Review helpers: `node scripts/render.js --still 12.5 --manifest ... --scene ... --outdir work/review` for a timestamped still; `--cliprange 10,15` for a short motion-check clip; `--beatsheet --beats work/audio/beats.json --video final.mp4` for the per-beat sheet.

### 14. QC gate (HARD GATE)

```bash
bash scripts/qc.sh --manifest run/manifest.json --workdir work --final <storage-root>/<video-name>/<video-name>.mp4
```

Frame counts, zero-byte sweep, blackdetect, freezedetect, determinism re-check, audio equals video duration, contact sheet plus per-beat sheet. Review the sheets yourself: the 30-second human review. Then `bash scripts/sweep-chromium.sh` to clear orphans.

### 15. Delivery

Deliver the MP4 from `<storage-root>/<video-name>/` along with the contact sheet. Keep the animation sources, voiceover audio, script text, manifest, beats.json, score params, and the review log in the folder. Frame PNGs are always deleted.

## Maintenance check

`bash verify.sh` is for installation/update verification. It is not part of every normal video job.
