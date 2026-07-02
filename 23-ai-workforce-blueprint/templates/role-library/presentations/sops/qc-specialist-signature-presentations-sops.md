# SOPs Mirror -- QC Specialist (Signature Presentations)

**Source:** presentations/qc-specialist-signature-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: `51-signature-presentation/MASTERDOC.md`. QC-pattern authority: `presentations/qc-specialist-presentations.md` (AUTO-FAIL battery first, average >= 8.5 with a 7.0 per-item floor, mandatory `qc_independence` provenance, <=3 rework loops then loop-4 escalation, reviewer != author). Lockstep authority: `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` (P-SP-INTAKE / P-SP-STRUCTURE / P-SP-P3-HYGIENE) + the MASTER QC ruleset Section 5 (AF-SP-* rows).

> Runtime models: client-provider tiers ONLY (`qwen3-vl:235b-cloud` primary / DeepSeek fallback, client keys). NEVER Anthropic (`claude-*`), NEVER the operator's keys. Reviewer is a separate instance from the author (no self-grading).

### SOP 9.1 -- Intake QC (P-SP-INTAKE)

**When to run:** after the Architect writes `sp_intake.json`, before authoring.

**Inputs:** `working/copy/sp_intake.json`; `prove_sp_intake.py`.

**Steps:** run the deterministic prover (exit 0 required); then semantically verify the 8 answers are real (not placeholder) and the frame fits the client; write the QC report WITH the `qc_independence` block.

**Outputs:** the intake QC verdict.

**Failure mode:** AF-SP-8Q-MISSING, AF-SP-8Q-SPLIT, AF-SP-FRAME-UNSET, AF-SP-TYPE-MISMATCH, AF-SP-OFFER-UNDECLARED.

### SOP 9.2 -- Structure QC (P-SP-STRUCTURE)

**When to run:** after the Architect writes `sp_structure.json`, before prompts/render.

**Inputs:** `working/copy/sp_structure.json`; `prove_sp_structure.py`.

**Steps:** run the prover (exit 0 required); then verify the arc reads as the frame intends, Movement+Message+Methodology are present, the tone ladder holds, and (for The Quest) the ending is Example-3-grade.

**Outputs:** the structure QC verdict.

**Failure mode:** AF-SP-SLIDE-FLOOR, AF-SP-PHASE-RANGE, AF-SP-PHASE-ORDER, AF-SP-PHASE-LABEL, AF-SP-IMG-SUGGESTION, AF-SP-CASESTUDY-CAP, AF-SP-TEACH-STEPS, AF-SP-HOOK, AF-SP-QUADRANT.

### SOP 9.3 -- Phase-3 No-Pitch QC (P-SP-P3-HYGIENE)

**When to run:** before Copy QC.

**Inputs:** `working/copy/sp_structure.json` + `sp_intake.json` (offer-token ledger); `prove_sp_no_pitch.py`.

**Steps:** run the prover (exit 0 required); then semantically confirm the teaching band teaches (no offer name, no price, no enroll/scarcity CTA) and the final teaching step bridges without pitching (may promise what comes next, may not name a price or product).

**Outputs:** the Phase-3 hygiene verdict.

**Failure mode:** AF-SP-P3-PITCH.

### SOP 9.4 -- Rework Loop and Escalation

**When to run:** on any fail.

**Steps:** loop back to the author automatically with a per-item work order for up to 3 attempts; on the 4th consecutive failure, escalate to the owner. Never waive an auto-fail; an auto-fail vetoes scoring before any average is computed.

**Outputs:** a rework work order (fail) or a pass verdict with the `qc_independence` provenance block.

**Failure mode:** escalation without the loop-3 attempts logged; a report missing the `qc_independence` block (refused); grading with the author's model.
