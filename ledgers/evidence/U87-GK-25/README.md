# U87 / GK-25 — 4-phase SACRED process-fidelity restoration — evidence

**Status: 5 of 6 blockers closed honestly. The 6th (prompt-floor) could NOT be
closed honestly within this pass's scope — see "BLOCKER 5" below. GK-25's
binary acceptance (spec:2085, three conjunctive clauses) therefore does NOT
yet clear. This directory documents the honest state, not a false "done."**

## Root cause (unchanged from the original judge ticket)

golden-quest was hand-assembled (`run_method: provers-direct`) and never
actually run through the department engine's `deck-intake-driver.py`
turn-gate. Everything that follows repairs that, one blocker at a time,
using REAL prover output captured from THIS repo at each step — nothing
below is hand-written or inferred.

## What changed in the fixture

- `working/copy/intake.json` (new) — produced by a REAL
  `deck-intake-driver.py --run-dir <golden-quest> --next` / `--answer`
  replay of the standard flow: `presentation_type=signature`, then the
  conditional follow-up `signature_source=from_scratch` (golden-quest is a
  from-scratch persona per its own README — this is the honest answer, not
  a placeholder). This is the file `build_deck.py`'s `_sp_active` switch and
  `prove_sp_routing.py` actually read; golden-quest never carried it before.
- `sp_intake.json` / `working/copy/sp_intake.json` (replaced) — produced by
  a REAL `deck-intake-driver.py --signature --next` / `--answer` replay:
  `interview_choice=in-depth`, then q1..q8 and `frame_selection=quest`
  answered ONE AT A TIME, reusing golden-quest's EXISTING answer text
  verbatim (GK-D3's replay path — no client answer discarded, none
  reworded). The final answer auto-finalized through the real turn-gate,
  which stamped a genuine, HMAC-signed, strictly-ascending
  `turn_ledger_provenance` block — see `working/interview/sp_intake_ledger.json`
  (`status: complete`, `turns: 10`) and `working/interview/sp_answers/*.txt`
  for the per-question record the driver itself wrote.
- `working/copy/arc_allocation.json` (new) — a genuine per-slide
  converting-arc allocation for all 103 slides, deterministically derived
  from `sp_structure.json`'s own `phase`/`label_slide`/`tags` fields (see
  its `provenance` field). Not a stub: it reproduces the exact
  Avatar 1-11 / Story 12-24 / Teaching 25-60 / Pitch 61-103 bands the
  README already documents, plus per-slide hook/case-study/label flags
  pulled straight from the existing, already-legitimate structure ledger.
- `broken-variants/sp_structure_D_phase_reordered.json` (new) — the real
  golden-quest deck with slide 40 flipped from phase `teaching` to `avatar`
  (a phase re-appearing out of order), exactly the judge's own scratch
  recipe. `broken-variants/REJECTION-RESULTS.json` gained the `D_phase_reordered`
  entry with the real captured output.
- `README.md` — added `prove_sp_routing.py` to the Reproduce recipe (it was
  missing, so the documented recipe could not surface the routing failure),
  added the `prove-deck.py`-writes warning, and documented the driver
  replay + the prompt-floor gap.

## Receipts (phase order, monotonic timestamps — all captured from a single,
## uninterrupted run against this repo; see the per-file `.timestamp` /
## `.exitcode` / `.out` / `.err` / `.json` siblings for raw output)

| # | Phase | Receipt file(s) | Result |
|---|---|---|---|
| 1 | P-SP-CLAIM (routing, ahead of intake) | `01-routing.*` | **PASS** (exit 0) |
| 2 | P-SP-INTAKE (8 Questions + pacing) | `02-sp-intake.*`, `02-sp-intake-post-grace-window-2026-09-01.*` | **PASS** (exit 0), incl. `--as-of 2026-09-01` — proves the pass is earned, not grandfathered through `GRACE_WINDOW_UNTIL = 2026-08-15` |
| 3 | P-SP-STRUCTURE (4-phase contract) | `03-structure.*` | **PASS** (exit 0) — unchanged from before this fix; was never one of the five blockers |
| 4 | Phase 3 — converting arc (`_chk_arc` preflight) | `04-arc.*` | **PASS** (exit 0) |
| 5 | P-SP-P3-HYGIENE (no-pitch) | `05-no-pitch.*` | **PASS** (exit 0) |
| 6 | prompt-floor | `06-prompt-floor-NOT-CLOSED.*` | **FAIL-CLOSED** (exit 3) — see BLOCKER 5 below. Named honestly in the filename; not silently omitted. |
| supplementary | fail-first: phase-order check has teeth (clause 3) | `07-failfirst-phase-order-variant-D.*` | rejected — `AF-SP-PHASE-ORDER` (exit 2), as required |
| supplementary | certificate issuance (isolated copy only) | `08-certificate-isolated-proof.*` | **PASS** (exit 0) on `<scratchpad>/deckrun/gq-iso`, a throwaway copy — never run against this tracked path (`prove-deck.py` writes; see README warning) |

Timestamps run `2026-07-16T17:08:08.969524Z` → `17:08:25.490317Z`,
strictly ascending, one continuous session, no gaps.

## Blocker-by-blocker

**BLOCKER 1 — routing / missing `intake.json`: CLOSED.** Real driver replay
(standard flow) produced `working/copy/intake.json` with
`deck_type: signature_presentation`. `prove_sp_routing.py --run-dir` now
exits 0 (receipt `01-routing.json`).

**BLOCKER 2 — arc receipt absent: CLOSED.** `working/copy/arc_allocation.json`
built by deterministic projection of `sp_structure.json`'s real per-slide
phase data (not invented). `_chk_arc` now returns `''` (PASS) — verified by
importing `build_deck.py`'s own checker function directly (receipt
`04-arc.out`).

**BLOCKER 3 — the grace-window time bomb: CLOSED, and this is the real work
of the unit.** The old `sp_intake.json` had no `turn_ledger_provenance` and
recorded `asked_all_at_once: true` with no ledger behind it — it passed
`prove_sp_intake.py` ONLY via the dated grace-window exemption
(`GRACE_WINDOW_UNTIL = 2026-08-15`), and would have started failing
`AF-SP-INTAKE-UNPACED` on 2026-08-16. The new `sp_intake.json` carries a
genuine turn-ledger provenance block — strictly-ascending turn ids, one per
question, valid HMAC signature — produced by walking the REAL
`--signature --next`/`--answer` turn-gate ten times (choice + q1..q8 +
frame), one question per call, each answer read back and validated before
the next question was ever surfaced. Receipt `02-sp-intake-post-grace-window-2026-09-01.json`
proves this PASSES on 2026-09-01 — three weeks past the old cutoff — on its
own merits, not by exemption.

**BLOCKER 4 — no archived reordered fixture: CLOSED.** Added
`broken-variants/sp_structure_D_phase_reordered.json` (slide 40:
`teaching` → `avatar`, applied to the real deck) and its rejection entry.
Receipt `07-failfirst-phase-order-variant-D.out`: exit 2,
`AF-SP-PHASE-ORDER`, naming the exact bad sequence — the specific check
spec:2085 clause 3 names, not `AF-SP-PHASE-RANGE`/no-pitch/process-integrity
(which A/B/C/E2E already prove and which are NOT the phase-order check).

**BLOCKER 5 — prompt-floor: NOT CLOSED. Reported honestly, not fabricated.**
golden-quest's own README documents that this fixture never ran `P4-RENDER`
(paid kie.ai image generation) — the three SP gates + `prove-deck.py` were
run directly instead, "the sanctioned way to prove structure and issue the
certificate without rendering." Because of that, `working/prompts/` does
not exist on this fixture, and `prove_pres_prompt_floor.py --dir
<golden-quest>` genuinely, correctly fails closed: `FAIL-CLOSED:
.../working/prompts is not a directory` (exit 3 — receipt
`06-prompt-floor-NOT-CLOSED.err`). There is no image-prompt content to
grade. Two ways exist to close this, and this pass deliberately does
neither:
  1. **Fabricate a pass** — write fake or synthetic prompt files just to
     clear `prove_pres_prompt_floor.py`. Refused: this is exactly the kind
     of forged evidence GK-25 exists to prevent, and it was called out by
     name as a risk on this unit.
  2. **Author real prompts** — write genuine, doctrine-compliant
     9,000-18,000-character image prompts for some or all of golden-quest's
     103 slides so a real `working/prompts/slide-*.txt` set exists to
     grade. This is a legitimate way to close the gap, but it is a large,
     separate body of creative authoring work (potentially 1M+ characters
     across 103 slides), not a natural side effect of an intake replay, and
     arguably out of scope for a "process-fidelity of the 4-phase SACRED
     order" unit — the prompt-floor gate belongs to `P4-RENDER`, a
     different, already-documented-as-skipped phase of this fixture.
  Recommendation: file this as its own follow-up unit — either run
  golden-quest through the full canonical pipeline including `P4-RENDER` in
  an environment where the paid kie.ai preflight is viable and archive the
  real resulting prompts + floor receipt, or get an owner ruling on
  whether GK-25's spec:2083 "prompt-floor receipts" clause should be
  descoped for a fixture that intentionally never renders (mirroring the
  already-accepted `run_method: provers-direct` precedent for the same
  reason).

**Documentation defect: CLOSED.** `README.md`'s Reproduce recipe now
includes `prove_sp_routing.py` and a `prove-deck.py`-writes warning.

## Net result

GK-25's binary acceptance is conjunctive across all three spec:2085
clauses and all six spec:2083 receipts. With 5 of 6 receipts genuinely
closed and 1 of 6 honestly reported as not closeable in this pass, the
unit **still does not clear** and must not be marked `verified`. This
archive exists to make that state legible and auditable — not to claim
a false "done." A fresh judge (!= writer) re-grade is owed before any
merge, per GK-25's own acceptance rule.

No client or human names. No secret values were printed. `prove-deck.py`
was run ONLY against an isolated scratch copy, never this tracked path —
`git status --short` in this clone is confirmed clean of any
`delivery/golden-quest-FINAL/` changes.
