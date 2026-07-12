# SOPs Mirror -- Signature Presentation Architect

**Source:** presentations/signature-presentation-architect.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: `51-signature-presentation/MASTERDOC.md` (Prime Directives 1-14). Lockstep authority: `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` (phases P-SP-INTAKE / P-SP-STRUCTURE / P-SP-P3-HYGIENE) + `universal-sops/presentation-slide-craft/SOP-SLIDE-06-EXTENSION-AND-SYNC.md`.

> Engine cross-reference: this role OWNS the Signature Presentation methodology (the Trevor Otts 4-phase arc). Every SOP below is machine-enforced by a fail-closed prover: `51-signature-presentation/scripts/prove_sp_intake.py`, `prove_sp_structure.py`, `prove_sp_no_pitch.py`, wired into `scripts/build_deck.py` as the `_chk_sp_intake` / `_chk_sp_structure` / `_chk_sp_no_pitch` preflight wrappers (which DEFER for every non-signature deck).

### SOP 9.1 -- The 8 Questions (asked ONE at a time via the REQUIRED driver turn-gate, recorded as ONE atomic block)

**When to run:** first, before any authoring. Routed from the Brainstorming Buddy "signature presentation" trigger.

**Inputs:** the client conversation; `51-signature-presentation/intake/sp-8-questions.json` (the spec); the REQUIRED turn-gate `deck-intake-driver.py --signature --next` / `--answer <ID> "<TEXT>"`.

**Steps:** interview the owner choice-first (QUICK vs IN-DEPTH), then ask q1..q8 + the frame-selection question ONE AT A TIME through the turn-gate — never free-form and never a wall of questions (dumping two or more questions in one turn, or opening with no quick-vs-in-depth choice, is the `AF-INTAKE-BATCH` conversation autofail, a QC/Healer scan that NEVER gates the build); the driver auto-assembles the answers into ONE atomic RECORD at `working/copy/sp_intake.json` on the final validated answer (that assembled record is what `prove_sp_intake.py` validates as `AF-SP-8Q-SPLIT` — a record-layer gate only, it says nothing about conversation pacing); set `deck_type: signature_presentation` in `working/copy/intake.json`; seed `offer_token_ledger` from q7 (the offer question).

**Outputs:** `working/copy/sp_intake.json` (clears `prove_sp_intake.py`).

**Hand to:** SOP 9.2.

**Failure mode:** Conversation layer: AF-INTAKE-BATCH. Record layer: AF-SP-8Q-MISSING, AF-SP-8Q-SPLIT, AF-SP-OFFER-UNDECLARED, AF-SP-TYPE-MISMATCH.

### SOP 9.2 -- Frame Selection and Template Load

**When to run:** after SOP 9.1, in the same intake block.

**Inputs:** the frame-selection answer; `51-signature-presentation/frame-templates/{rulebook,vault,quest,original}.md`.

**Steps:** lock `signature_frame` to exactly one of rulebook|vault|quest|original; load that frame template (devices, refrain policy, tone ladder, close).

**Outputs:** the locked frame in `sp_intake.json`.

**Hand to:** SOP 9.3.

**Failure mode:** AF-SP-FRAME-UNSET.

### SOP 9.3 -- Four-Phase Arc and Labels

**When to run:** after the frame is locked.

**Inputs:** the frame template; the SACRED structure contract `51-signature-presentation/structure/sp_structure.json`.

**Steps:** build `working/copy/sp_structure.json` with the 4 phases contiguous-from-slide-1 in the order avatar->story->teaching->pitch, a label slide per phase, a non-empty `suggested_image` on every slide, at most 2 CASE_STUDY-tagged slides, 3 to 7 teaching steps, one central hook + four DISTINCT section hooks, and the N.E.E.I.T. + 4-Quadrant markers in the required phases.

**Outputs:** `working/copy/sp_structure.json` (clears `prove_sp_structure.py`).

**Hand to:** SOP 9.4.

**Failure mode:** AF-SP-PHASE-RANGE, AF-SP-PHASE-ORDER, AF-SP-PHASE-LABEL, AF-SP-IMG-SUGGESTION, AF-SP-CASESTUDY-CAP, AF-SP-TEACH-STEPS, AF-SP-HOOK, AF-SP-QUADRANT.

### SOP 9.4 -- Expansion-to-100 Math

**When to run:** during structure build.

**Inputs:** the phase floors (avatar 11 / story 13 / teaching 36 / pitch 40); any logged client-exact count.

**Steps:** expand to >=100 slides on the phase floors (the bands are floors, not fixed spans). The Mode-A 90-slide cap is N/A for `deck_type: signature_presentation` (see Director SOP 9.4 signature branch and Edge Case 17.3 carve-out). A `client_overrode_slide_floor` + `client_exact_slide_count` is honored EXACTLY and recorded on the certificate.

**Outputs:** the final slide count in `sp_structure.json`.

**Hand to:** SOP 9.5.

**Failure mode:** AF-SP-SLIDE-FLOOR.

### SOP 9.5 -- Handoff to Copywriter / Hook Lab / phase-authors

**When to run:** after the structure clears the prover.

**Inputs:** the locked `sp_structure.json` + frame contract.

**Steps:** hand off to the Slide Copywriter and Hook Lab; the Phase-3 no-pitch prover (P-SP-P3-HYGIENE) guards the teaching band before Copy QC.

**Outputs:** the deck flows into the existing pipeline through Delivery.

**Hand to:** Slide Copywriter, Hook Lab, then the existing pipeline; QC by the QC Specialist (Signature Presentations).

**Failure mode:** AF-SP-P3-PITCH (a q7 offer/product name, a price token, or an enroll/scarcity CTA in the teaching band, or a non-contiguous Phase-3->Phase-4 bridge).
