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
- **Slides:** 101 (≥100 floor; no client-exact override).
  - Avatar 1–11 (11) · Story 12–24 (13) · Teaching 25–60 (36) · Pitch 61–101 (41)
  - Contiguous, in order; bridge is contiguous (last teaching 60 → first pitch 61).
- **Teaching:** the *Wayfinder Blueprint* — 3 Quests, **5 steps** (within 3–7).
- **Case studies:** exactly **2** (slides 39, 51), within the ≤2 cap.
- **Hooks:** 1 central chorus + 4 distinct section hooks (one per phase).
- **Markers:** N.E.E.I.T. + 4-Quadrant on Avatar/Story/Pitch; Movement + Message +
  Methodology present.
- **Offer (q7):** *The Called Collective* + *The Wayfinder VIP Intensive* — named
  only in Phase 4; **forbidden and absent** in Phase 3 (no price / product / CTA).

## Files

| File | Purpose |
|---|---|
| `sp_intake.json` | Runtime intake record (8 Questions in one block + Quest frame + offer ledger) |
| `sp_structure.json` | Deck copy ledger (101 slides: slide/phase/label_slide/title/body/suggested_image/tags) |
| `slides_copy.md` | Human-readable copy ledger |
| `working/copy/*.json` | Run-dir mirrors consumed by the provers (`--run-dir`) |
| `working/checkpoints/*.json` | Declared plan + attestations + client reports (governed run) |
| `working/prover_results.json` | Captured PASS output of the three SP provers |
| `delivery/golden-quest-FINAL/PROCESS-CERTIFICATE.{json,md}` | Issued process certificate |
| `broken-variants/` | Deliberately-broken decks + `REJECTION-RESULTS.json` proving fail-closed |

## Reproduce

```bash
SP=51-signature-presentation/scripts
GQ=51-signature-presentation/examples/golden-quest
python3 $SP/prove_sp_intake.py    $GQ/sp_intake.json                 # PASS (exit 0)
python3 $SP/prove_sp_structure.py --deck $GQ/sp_structure.json       # PASS (exit 0)
python3 $SP/prove_sp_no_pitch.py  --run-dir $GQ                      # PASS (exit 0)
python3 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/prove-deck.py \
        --run-dir $GQ                                                # certificate issued (exit 0)
```

`run_method`: **provers-direct.** The canonical entry
(`presentation-canonical-entry.sh` → `run_signature_deck.py`) drives every pipeline
phase including `P4-RENDER` (paid kie.ai image generation gated by a balance
preflight) before reaching `prove-deck.py` at `P9-DELIVER`; that render step cannot
run cleanly/appropriately in this environment, so the three SP gates + `prove-deck.py`
were run directly — the sanctioned way to prove structure and issue the certificate
without rendering.

## Broken variants (fail-closed proof)

| Variant | Defect | Prover | Verdict |
|---|---|---|---|
| A | 99 slides | `prove_sp_structure` | rejected — `AF-SP-SLIDE-FLOOR` (exit 2) |
| B | 3 case studies | `prove_sp_structure` | rejected — `AF-SP-CASESTUDY-CAP` (exit 2) |
| C | price + enroll CTA + offer name in Phase 3 | `prove_sp_no_pitch` | rejected — `AF-SP-CTA/PRICE/PITCH-IN-TEACH` (exit 2) |
| E2E | structure gate failed → phase unattested | `prove-deck` | **no certificate** — `AF-PROCESS-INTEGRITY` (exit 9) |
