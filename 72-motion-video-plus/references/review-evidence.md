# Review evidence bundles (MG-031)

How visual review evidence is generated for Skill 72 V2, what the
coverage record means, and how downstream items consume it. The
implementation is `scripts/critique_bundle.py`;
`scripts/critique-bundle.sh` is a thin wrapper that keeps the
historical invocation working.

## Why this replaced the old assembler

The legacy `critique-bundle.sh` built its contact strip as one 8x8
tile of a 2 fps sampling and its phone strip as one 6x6 tile of a
1 fps sampling: the first 32 and 36 seconds of the video,
respectively. A five-minute VSL's remaining minutes were never seen
by any critic. The per-beat sheet silently capped at 64 beats, the
safe-zone image was a single frame at t=1s, artifact names were
fixed (`contact.jpg`, `phone.jpg`), so two jobs sharing a directory
overwrote each other, and no ffmpeg failure changed the exit status:
the script ended by listing the output directory, so a bundle with
missing sheets still reported success. MG-031 replaces all of it.

## Building a bundle

```
python3 scripts/critique_bundle.py build \
  --video preview.mp4 --outdir review/job-123 \
  --timeline timeline.json --sidecar timeline-sidecar.json \
  --review-record preview.review.json \
  --interval 5 --destination 360x640 --destination 1920x1080
```

- `--video` and `--outdir` are required. `--job-id` defaults to the
  compiled timeline's job id, then the review record's, then the
  video's filename stem (sanitized to filename-safe characters).
- `--timeline` is the canonical compiled timeline document (the
  `timeline` half of the MG-021 compiler output). It supplies scene
  boundaries, compiled events (reveal starts, proof states, hold
  starts, cues), fps, and the declared total frame count.
- `--sidecar` is the MG-021 `TimelineSidecar`. It supplies caption
  ranges; each caption's first frame is a text swap sample. The
  compiled sidecar's range tracks carry no scene id, so the builder
  attributes the containing scene from the timeline placement.
- `--review-record` is an MG-024 `preview.review.json` sidecar. Its
  engine, label, and source/props/preview hashes are bound into the
  coverage record, so a reviewer can prove the bundle describes the
  exact artifact the preview gate saw. The label is carried
  honestly: a bundle built over a `rough_layout_only` artifact says
  so in its record. MG-031 records evidence; it never upgrades
  rough evidence into motion evidence (that refusal belongs to the
  MG-024 gate).
- `--beats` accepts the beat grid JSON (`{"beat_times": [...]}`,
  the `scripts/beat-grid.py` output shape); each beat becomes a
  targeted sample.
- A timeline, sidecar, or review record whose job id disagrees with
  the requested job id stops the build with exit 9
  (`MG_FOREIGN_JOB`). A timeline fps that contradicts the probed
  video is a schema error (exit 2). A probed frame count that
  contradicts the timeline total makes the verdict incomplete.

## Bundle layout

```
<outdir>/
  <job>__coverage.json        the canonical coverage record
  coverage.json               plain-name copy (see collision rule)
  <job>__metrics.json         probed duration, frames, fps, loudness
  metrics.json                plain-name copy (same rule)
  frames/full/<job>__f<frame>.png          one PNG per sampled frame
  frames/dest-<W>x<H>/<job>__f<frame>.png  per declared destination
  sheets/<job>__samples__p<NN>.png         interval sheets, paginated
  sheets/<job>__targeted__p<NN>.png        targeted sheets, paginated
```

Every artifact name carries the job id. The per-job coverage record
is canonical and collision-proof; the plain `coverage.json` copy is
written only when the directory has none or the existing one names
the same job, so a neighboring job's record is never overwritten.
In the normal per-job bundle directory both names exist and are
identical.

## Sampling policy

- Interval samples at frames `0, step, 2*step, ...` with
  `step = round(interval_seconds * fps)` (at least 1; default
  interval 5 s). The largest unsampled gap never exceeds the
  declared interval, and there is no cap on the number of samples:
  length is answered with pagination, never truncation.
- Targeted samples, all required: the first and last frame of every
  scene; every compiled proof, hold-start, and reveal-start event;
  every cue event (targeted, not required); every text swap; the
  final frame of the runtime; every caller-supplied beat.
- Extraction decodes the video once, selecting all planned frames
  in a single pass, and verifies the produced count and each
  frame's dimensions against the probed geometry before any frame
  is reported. Frames are extracted
...[truncated 6656 chars]