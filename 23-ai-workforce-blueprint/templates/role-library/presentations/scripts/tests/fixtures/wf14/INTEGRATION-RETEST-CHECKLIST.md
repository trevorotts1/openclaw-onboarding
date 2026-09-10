# WF14 integration-retest checklist — prep (NOT acceptance)

Run this checklist only against the completed W5 candidate (WF21 frozen
package + installed ONB consumer + CC compat, after WF22 changes). Running
it against ONB base 2244b00fe or any older package proves nothing and
counts as nothing per HOW-TO-EXECUTE.md W6 deps.

## 0. Gate: exact W5 inputs pinned

The W5 candidate must name the exact content it froze. Expected inputs
(live ledger + run/waves/W4/completion.json as of 2026-09-10; re-read
both live before starting — PRES-035 repair and PRES-049 staging may
have moved since prep):

- WF13: 16ff7ce1f6f581f7e45d26daf0413d25e0b043fb (033 QC_PASSED),
  0ff4b615bbb5ce671b7d5f1cfcc30323187795ef (034 QC_PASSED),
  ba2dead07b4f308442cfed67b7048fc81da28f6c (035 REPAIR_REQUIRED at prep —
  MUST be resolved before it can be an input),
  8d2d4097facf357e80acf86deed27d27a815b1b8 (039 QC_PASSED),
  16313110d8baaa2019e123ebcdac63f10fb9c3db (043 QC_PASSED)
- WF16: staging content-sha256
  4cad34944ba28dc4e8648ac137a17bfb9c53d2e63b3899301bc18d2a188e4391
  (staging-only at prep, PRES-049 IN_PROGRESS — QC-PRES-049 checks 1–3
  close in W5 WF21, not here)
- WF19: 7fe7fbf2d98f8d5721a18540d54397e015b9ad34 (053 QC_PASSED),
  f5bdb0f6b658533a0b48e8805e8fa0ad9e706bbf (054 QC_PASSED)
- WF20: 48d3acd77b33924f88d3ef4f0eae369eee32b822 (050 QC_PASSED),
  3bad5012aa7a217c1467c22e7bb78b24a10e461f (051 QC_PASSED),
  d86ad2b14065c31a518f1d6238c913737397a53a (052 QC_PASSED)

Refuse to start if any pinned input is not QC_PASSED in the live ledger
at run time, or if the frozen package digest does not match the W5
candidate record. Record every SHA actually used.

## 1. Fixture decks

- tests/fixtures/wf14/perf_small_slides.json (6 slides) and
  perf_large_slides.json (100 slides): ordinals contiguous 1..N,
  every slide carries slide/scene/nonempty copy (slides.schema.json
  floor). Re-validate with test_wf14_perf_baseline.py before measuring.

## 2. Serial-vs-Ultra timing

- Run the harness template against the INSTALLED package (not this
  prep copy): serial (workers=1) vs Ultra width on the identical large
  fixture; capture wall, spend, stage p50/p95, first-draft latency,
  QC quality for both modes (QC-PRES-036 check-3 shape).
- Apply SPEED-THRESHOLDS-DRAFT.md: direction every run, speedup floor,
  exactness, metrics present, 3/3 stability vs noise floor, QC parity.
  Replace draft numbers with measured W5-candidate numbers; do not
  carry the fixture sleeps forward as results.

## 3. QC-PRES-055 check 2 — matrix scope

> "Mac/Hostinger Docker/Contabo Docker fresh/upgrade/restart matrix
> plus connected CC/GHL acceptance uses exact released artifacts and
> scoped authorized resources; no source-only or mocked claim counts
> as live."

- Timing + integration legs run on each matrix cell with the exact
  released artifacts; per-cell receipts name OS/image/interpreter/font
  versions and output hashes (cf. QC-PRES-043 check 1 shape).
- Source-only or fixture-server-only runs are prep, never acceptance.

## 4. Evidence

- Save real commands, fixtures, source/host identity, raw logs, and
  the independent verdict under run/evidence/WF14-prep/<candidateSHA>/
  (prep) — acceptance evidence goes to the WF14 acceptance lane when
  W6 opens it, never self-approved.
