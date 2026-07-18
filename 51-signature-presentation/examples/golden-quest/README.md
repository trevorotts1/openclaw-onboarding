# Golden Quest — Signature Presentation regression sample

A reusable **golden regression sample** for the Skill 51 Signature Presentation
pipeline: a complete, methodology-faithful **Quest-frame** deck that PASSES all
three SP provers and drives `prove-deck.py` to a process certificate.

- **Fictional subject:** *The Wayfinder* — a purpose & identity coach archetype
  (the Quest archetype from the MASTERDOC). No real names, brands, URLs, or private
  details ship. Method attribution: the Trevor Otts Signature Presentation method.
- **Frame:** The Quest (`signature_frame: quest`) — named Blueprint of Quests, a
  recurring motif hashtag (`#StillCalled`), riddle + definition-pair (*morning vs
  mourning*) + literary passage (Frost) devices, and the Directive-13 poetic
  **fill-in-the-blank manifesto** close (`I AM CALLED. I AM CAPABLE. I AM ______.`).
- **Slides:** 103 (≥100 floor; no client-exact override).
  - Avatar 1–11 (11) · Story 12–24 (13) · Teaching 25–60 (36) · Pitch 61–103 (43)
  - Contiguous, in order; bridge is contiguous (last teaching 60 → first pitch 61).
- **Teaching:** the *Wayfinder Blueprint* — 3 Quests, **5 steps** (within 3–7).
- **Case studies:** exactly **2** (slides 39, 51), within the ≤2 cap.
- **Hooks:** 1 central chorus (on 4 dedicated pure-typography slides: 2, 63, 93, 100) + 4 distinct section hooks (one per phase).
- **Markers:** N.E.E.I.T. + 4-Quadrant on Avatar/Story/Pitch; Movement + Message +
  Methodology present.
- **Offer (q7):** *The Called Collective* + *The Wayfinder VIP Intensive* — named
  only in Phase 4; **forbidden and absent** in Phase 3 (no price / product / CTA).

## Files

| File | Purpose |
|---|---|
| `sp_intake.json` | Runtime intake record (8 Questions in one block + Quest frame + offer ledger) — driver-produced, carries `turn_ledger_provenance` |
| `sp_structure.json` | Deck copy ledger (103 slides: slide/phase/label_slide/title/body/suggested_image/tags) |
| `slides_copy.md` | Human-readable copy ledger |
| `working/copy/intake.json` | Type-picker record (`deck_type: signature_presentation` + derived legacy fields) — driver-produced; this is what `build_deck.py`'s `_sp_active` switch and `prove_sp_routing.py` actually read |
| `working/copy/arc_allocation.json` | Per-slide converting-arc allocation (`_chk_arc` preflight receipt) — derived from `sp_structure.json`'s own phase/tag data, not a stub |
| `working/copy/*.json` | Run-dir mirrors consumed by the provers (`--run-dir`) |
| `working/interview/` | The real turn-gate ledgers (`intake_ledger.json`, `sp_intake_ledger.json`), per-question answer files, and `intake_transcript.json` from the `deck-intake-driver.py` replay |
| `working/checkpoints/*.json` | Declared plan + attestations + client reports (governed run) |
| `working/prover_results.json` | Captured PASS output of the three SP provers |
| `delivery/golden-quest-FINAL/PROCESS-CERTIFICATE.{json,md}` | Issued process certificate |
| `broken-variants/` | Deliberately-broken decks + `REJECTION-RESULTS.json` proving fail-closed |

## Reproduce

```bash
SP=51-signature-presentation/scripts
GQ=51-signature-presentation/examples/golden-quest
python3 $SP/prove_sp_routing.py   --run-dir $GQ                      # PASS (exit 0) -- P-SP-CLAIM, ahead of intake
python3 $SP/prove_sp_intake.py    $GQ/sp_intake.json                 # PASS (exit 0)
python3 $SP/prove_sp_structure.py --deck $GQ/sp_structure.json       # PASS (exit 0)
python3 $SP/prove_sp_no_pitch.py  --run-dir $GQ                      # PASS (exit 0)
python3 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/prove-deck.py \
        --run-dir $GQ                                                # certificate issued (exit 0) -- see WARNING below
```

**WARNING — `prove-deck.py` WRITES.** It re-stamps `certified_at` and
`certificate_sha` on `delivery/golden-quest-FINAL/PROCESS-CERTIFICATE.{json,md}`
on every run (confirmed via sha256 of all fixture files before/after: those two
files are the ONLY ones touched). Never run it against this tracked path — copy
the fixture to a scratch dir first and run it there, or `git checkout --` the two
certificate files afterward if you do run it in-tree.

`run_method`: **provers-direct, PLUS a real `deck-intake-driver.py` run for the
intake leg (GK-25/U87).** The canonical entry (`presentation-canonical-entry.sh`
→ `run_signature_deck.py`) drives every pipeline phase including `P4-RENDER`
(paid kie.ai image generation gated by a balance preflight) before reaching
`prove-deck.py` at `P9-DELIVER`; that render step cannot run cleanly/
appropriately in this environment, so the three SP gates + `prove_sp_routing.py`
+ `prove-deck.py` were run directly against structure/copy that predates this
fixture's driver-run repair — the sanctioned way to prove structure and issue
the certificate without rendering. The ONE exception: `sp_intake.json` /
`working/copy/intake.json` are NOT hand-assembled. They are the real output of
replaying this fixture's own q1-q8 + frame answers through
`deck-intake-driver.py --signature --next/--answer` (the SACRED one-question-
at-a-time turn-gate) plus the standard `--next/--answer` flow for
`presentation_type`/`signature_source` — see `working/interview/` for the
resulting ledgers, per-question answer files, and transcript, and
`working/copy/sp_intake.json`'s `turn_ledger_provenance` block for the signed,
strictly-ascending turn ledger `prove_sp_intake.py`'s `AF-SP-INTAKE-UNPACED`
gate verifies. `working/copy/arc_allocation.json` is likewise real, not a stub:
it is deterministically derived from this fixture's own `sp_structure.json`
per-slide phase/tag data (see its own `provenance` field). **`prompt-floor`
receipts are NOT present** — this fixture never ran `P4-RENDER`, so
`working/prompts/` does not exist and `prove_pres_prompt_floor.py --dir` fails
closed (exit 3, "not a directory") on it; that is an honest, correctly-reported
gap, not an oversight (see `ledgers/evidence/U87-GK-25/README.md`).

## Broken variants (fail-closed proof)

| Variant | Defect | Prover | Verdict |
|---|---|---|---|
| A | 99 slides | `prove_sp_structure` | rejected — `AF-SP-SLIDE-FLOOR` (exit 2) |
| B | 3 case studies | `prove_sp_structure` | rejected — `AF-SP-CASESTUDY-CAP` (exit 2) |
| C | price + enroll CTA + offer name in Phase 3 | `prove_sp_no_pitch` | rejected — `AF-SP-CTA/PRICE/PITCH-IN-TEACH` (exit 2) |
| D | slide 40 flipped `teaching` → `avatar` (phase re-appears out of order) | `prove_sp_structure` | rejected — `AF-SP-PHASE-ORDER` (exit 2) |
| E2E | structure gate failed → phase unattested | `prove-deck` | **no certificate** — `AF-PROCESS-INTEGRITY` (exit 9) |
