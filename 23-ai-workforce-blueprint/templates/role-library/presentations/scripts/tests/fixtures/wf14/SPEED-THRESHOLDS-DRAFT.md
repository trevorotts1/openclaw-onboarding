# WF14 speed acceptance thresholds — DRAFT (prep, NOT acceptance)

Status: draft prepared on ONB base 2244b00fe against the hermetic harness
template (test_wf14_perf_baseline.py). These numbers describe the PREP
FIXTURE (fixed sleep per slide, no engine/provider/render), not the product.
They become acceptance thresholds only after re-measurement against the
completed W5 candidate (frozen package + installed consumer) per
HOW-TO-EXECUTE.md W6 deps. Nothing here counts as WF14 acceptance.

## Measured on this box (Darwin arm64, Python 3.14.7)

Harness: tests/test_wf14_perf_baseline.py, ULTRA_WIDTH=8,
SMALL_WORK_S=0.02 (6 slides), LARGE_WORK_S=0.005 (100 slides).
Self-test: 4 passed.

| deck | serial wall | ultra wall (w=8) | speedup |
|---|---|---|---|
| small (6) | 0.139s | 0.026s | 5.40x |
| large (100) | 0.593s | 0.077s | 7.66x |

Stage p50/p95 on the fixture track the nominal sleep (~0.006s large);
first-draft latency is ~one unit in both modes (fixture has no dependency
chain — the A→C unlock delta that PRES-036 measured does not exist here).

## Draft acceptance thresholds (to confirm on the W5 candidate)

1. Direction: ultra wall < serial wall on the large deck, every run.
   Prep bound holds with wide margin (0.077s vs 0.593s).
2. Speedup floor on the large deck: >= 2.0x at width 8 on real units.
   Prep fixture shows 7.66x; real units carry engine overhead, so the
   floor is set far below the fixture number on purpose. Confirm, do not
   assume, against the W5 candidate.
3. Exactness: both modes emit every ordinal exactly once, in input order,
   with artifact count == deck size. No tolerance — same bar as
   QC-PRES-001/014.
4. Check-3 metrics present for both modes: wall, spend (provider calls +
   nominal exec seconds), stage p50/p95, first-draft latency, QC quality
   (exit, artifact presence, phase statuses). Missing metric = fail, per
   the PRES-036 lesson.
5. Stability: 3 successive runs per mode; direction must hold 3/3 and the
   spread must sit below the serial-vs-ultra delta (noise floor check,
   cf. PRES-036 benchmark-stability 3/3 + noise 0.02–0.11s).
6. QC quality parity: ultra artifacts pass the same QC battery as serial
   (no quality-for-speed trade). Real-suite numbers replace this line once
   the W5 candidate exists.

## Explicit non-claims

- Fixture sleeps are not engine units; no provider spend, no render, no
  I/O contention. Real p50/p95/first-draft numbers will differ.
- No host-matrix leg (Mac/Docker profiles) runs here; that belongs to
  W6 WF23 + the WF14 installed-integration gate.
- QC-PRES-055 check 2 (matrix scope) is NOT exercised by this harness.
