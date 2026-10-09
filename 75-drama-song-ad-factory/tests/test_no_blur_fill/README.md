# tests/test_no_blur_fill — DEL-14 proof (PKG-05-U3)

Blur fill is never used. Full height is reached by crop-in of the source
frame only (Trevor order 2026-10-09, mass swarm item C via relita; 13:31 plan
authorization).

What this suite proves, in order:

1. **Red on blur fill.** A blur-fill render attempt (the gblur + alphamerge
   mask chain from the spot-2 incident) is produced on disk; the suite proves
   the trap (it measures full height by size alone, which is why geometry can
   never be the only gate) and then that every real refusal fires: the QC gate
   refuses the PASS record that would ship it (`FILL_CLAIM_MEASURED`,
   structural -> BLOCKED), the fill-claim scanner names the chain, and
   `build_argv` can only ever emit `scale` + `crop`. The rotation fill
   (sideways frames + a rotation tag, so a player stands them up) is refused
   by measurement: its stored frames are not full height
   (`OUTPUT_NOT_FULL_HEIGHT`), and an upright full-height file wearing the
   same tag is refused as `ROTATED_FILL`. The source-level scanner refuses
   any core script that carries the chain (planted-copy control included).
2. **Green on crop-in.** `no_blur_fill.render` scales the source until it
   covers 9:16 and crops the overflow (uniform zoom, centred on the subject
   via `--center-x`); the output measures 1080x1920, passes `verify_output`
   and passes the QC gate.
3. **Refusal gates fire.** `qc_gate.fill_claim` + the `no_blur_fill` check in
   `scripts/core/qc_gate.py`, and `no_blur_fill.build_argv`, which can
   only ever emit `scale` + `crop` — no pad, no blur, no stretch.

Run:

```bash
python3 tests/test_no_blur_fill/test_fill_claim_gate.py
python3 tests/test_no_blur_fill/test_pipeline_refusal.py
# or the whole folder:
python3 -m pytest tests/test_no_blur_fill/ -q
```

The media-backed cases need `ffmpeg` + `ffprobe` and skip with a stated
reason when they are absent (never a fabricated green). Everything else is
stdlib-only and runs on the CI runner. Temp files land under the system temp
directory with a `PKG-05-U3-` prefix and are removed by the test itself;
empty `HOME` is safe.
