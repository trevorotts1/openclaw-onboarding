# Assembly (MG-022)

How finished scene segments become one deliverable: `scripts/assemble.py`
is the implementation; `scripts/assemble.sh` is a thin compatibility
wrapper that delegates to it with the historical command line. The
pre-repair shell implementation and its four defects are preserved as
reproductions under `tests/evidence/mg022/repro/`
(D-ASSEMBLE-TUPLE, D-ASSEMBLE-SINGLE-SCENE-FILTER, D-ASSEMBLE-AUDIO-INDEX,
D-ASSEMBLE-SHORTEST-SFX-DRIFT).

## Consuming the plan

Assembly consumes the MG-021 compiled plan and nothing else:

- Scene order, placed ranges and source ranges come from the canonical
  timeline plus sidecar scene records. The assembler never recomputes a
  scene start from durations.
- Transition lengths come from the sidecar handles (exactly one owner
  per overlap, per the compiler's contract). Between handle-linked
  scenes the join is an xfade whose offset is the accumulated placed
  length minus the handle frames; scenes without a handle butt-join
  with concat.
- Narration and SFX placements come from the sidecar in samples at
  48000 Hz. Total length is the plan's `total_frames` /
  `total_samples`, enforced by construction and then verified.
- A mismatch between media and plan is an assembly failure with the
  plan as the reference: a segment shorter than its consumed source
  range, or a narration file shorter than its placed segment, fails
  with a named error instead of being silently padded, stretched or
  cut. `-shortest` is never used anywhere: it derives the output
  length from the shortest stream rather than from the plan, which is
  how the old script concealed its drift.

## The input registry

Every ffmpeg input is registered exactly once in an `InputRegistry`,
in this order: scenes in plan order, narration segments, music, SFX
placements (one input per placement, so a reused sound file is still
independently trimmable), and finally a lavfi silence canvas when any
placement starts after sample 0. The registry assigns the actual
ffmpeg input index; the filter graph is built exclusively from those
indexes. The old script addressed voiceover as `[0:a]` and SFX by
their position in an audio-only list while the segment inputs
occupied the low indexes; that class of error is now impossible by
construction, and the graph tests pin the indexes for a two-segment
job.

## Filter-graph discipline

- Every segment is normalized before joining: trimmed to the plan's
  source range in frames, scaled to the job canvas, forced to the
  plan fps, rebased to `AVTB`, converted to `yuv420p`.
- Every chain terminates in a real filter with an explicit output
  label, including the single-scene case (`trim=end_frame` plus
  `format` into `[vout]`). The old single-scene graph was
  `"[0:v][vout];"`, two labels with no filter between them.
- Audio placement is sample-exact: each source is resampled to
  48000 Hz, formatted to stereo fltp, trimmed to its declared sample
  length, padded to the program length, and, when it starts after 0,
  spliced behind a trimmed slice of the silence canvas. SFX lengths
  come from the sound file itself, capped at the program end.
- A stream that feeds two branches is split explicitly: with ducking
  declared, the narration stem goes through `asplit=2` so one copy
  enters the final mix and the other keys the sidechain compressor.

## Error handling

ffmpeg and the helper synthesizers run as argument arrays with
checked return codes. A failure leaves `ffmpeg.log` (full command and
stderr) in the workdir and prints a structured JSON finding to stderr
with one of these codes; there is never a traceback:

| Exit | Code | Meaning |
|---|---|---|
| 2 | ASSEMBLE_USAGE | required flags missing for the chosen mode |
| 3 | ASSEMBLE_INPUT_MISSING | a named file does not exist |
| 4 | ASSEMBLE_PLAN_INVALID / ASSEMBLE_PLAN_INCONSISTENT | plan malformed or timeline/sidecar/media disagree |
| 4 | ASSEMBLE_MEDIA_SHORTER_THAN_PLAN / ASSEMBLE_NARRATION_SHORTER_THAN_PLAN | media cannot fill the plan |
| 4 | ASSEMBLE_NARRATION_EXCEEDS_PICTURE | legacy bridge: voiceover longer than the compiled picture |
| 5 | ASSEMBLE_FFMPEG_FAILED | ffmpeg or a synthesizer exited non-zero; log retained |
| 6 | ASSEMBLE_VERIFY_FAILED | output probe disagrees with the plan |

On success the assembler writes `assemble-probe.json` into the
workdir: expected vs decoded frame count, duration, stream map, the
SHA-256 of the decoded last frame, the full input registry, and any
warnings. Acceptance evidence under `tests/evidence/mg022/` is
produced by `verify_acceptance.py`, which re-counts frames
independently and checks narration segment presence by tone band
energy (a segment-presence proof, not a speech intelligibility check).

## The MG-023 seam (landed)

MG-023 landed the policy layer this seam waited for. In plan mode
the assembler no longer takes the registry's declarations literally:
`scripts/audio_policy.py` resolves them exactly once at plan load
into a resolved audio plan (modes none / inherited / own from the
timeline's `audio_owner`; source resolution, exclusions, mix
defaults, and the loudness target), and everything downstream
consumes only the resolved plan. The full policy, its defaults, its
measured loudness finish, its encoded-output verification, and its
failure vocabulary live in `references/audio-policy.md` (records:
`references/audio-policy.schema.json`).

What the registry still declares, now as inputs to that policy:

- `musicVolume`: a fixed gain on the music stem (1.0 when undeclared).
- `ducking`: `{threshold, ratio, attack, release}` for the sidechain
  compressor, or null for no ducking. When the key is absent and
  narration and music coexist in own mode, the policy default
  applies (the legacy bridge's parameters, adopted as policy).

The one signal-path rule already fixed by the directive and
enforced here: the ducking key is the narration stem alone, never
the narration-plus-SFX mix the old script used.

## Legacy bridge mode

`assemble.sh` invokes `--legacy` mode, which accepts the pre-V2
manifest shape: segments at `<workdir>/scenes/<id>/<id>.mp4`, one
continuous voiceover, music from a manifest `music_bed`, a prebuilt
`--score`, or synthesis via `synth-score.py` / `beat-grid.py`, and
SFX from `--sfx-dir`, synthesis via `synth-sfx.py`, or the manifest
`sfx` map when `synth_sfx` is false. The bridge compiles that shape
into the same job model the plan path consumes (fixed 0.5s fades, the
historical bridge rule) and finishes with the historical loudnorm
pass (`loudnorm=I=-14:TP=-1:LRA=11`). Plan mode instead finishes
with MG-023's measured two-pass loudnorm and encoded-output
verification; the bridge's finish is a frozen compatibility
behavior, not the V2 loudness policy.

Deliberate corrections over the old script, each forced by a
reproduced defect:

- Scene tuples are unpacked explicitly (the old script passed the
  tuple itself to ffmpeg and died with a TypeError on any input).
- Music is resolved exactly once. The old script re-read
  `music_bed` from the manifest after synthesis and silently
  discarded the synthesized score (D-ASSEMBLE-MUSIC-RESET).
- SFX events are placed on the compiled (faded) timeline from each
  scene's placed start, not on raw accumulated durations.
- A voiceover longer than the compiled picture fails with
  ASSEMBLE_NARRATION_EXCEEDS_PICTURE instead of being cut by
  `-shortest`.
- Ducking is keyed on the narration stem (see the seam note above);
  the legacy parameters (music volume 0.35, threshold 0.02, ratio 8,
  attack 20, release 400) remain the bridge's declared values. MG-023
  adopted the ducking parameters as the V2 policy default for own
  mode; the bridge's 0.35 music volume and its historical loudnorm
  finish stay bridge-only (the measured loudness finish lives on
  the plan path; see `references/audio-policy.md`).
