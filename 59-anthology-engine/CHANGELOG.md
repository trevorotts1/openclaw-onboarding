# Anthology Engine (Skill 59) -- Changelog

## 0.1.0 (2026-07-07) -- initial skeleton (Wave 1, unit W1.1)

Establishes the certified house layout and the interface contracts every other
build unit authors against. This unit ships the orchestrator scaffold; the module
logic (ledger, router, adapters, gates, guards, QC) lands from sibling Wave 1 and
Wave 2 units and is wired by the serial integrator.

Added:
- SKILL.md runbook: S0 to S9, the four layers and their code-contract boundaries,
  the silence doctrine, the Skill 54 call contract via anthology-engine-entry.sh,
  and the sibling boundaries versus Skills 53 and 54.
- ENGINE-MANIFEST.json: the single source of truth (draft for the integrator to
  finalize) with the S0 to S9 stage machine, the gate table, the AF-AE-* autofail
  table with the enforcing script and py_symbol per code, the engine-owned prompt
  pins (ae-01 to ae-04, sha256 pending from W1.18), the field-map reference, and the
  complete 32-row shipped-script inventory with purpose and exit-code contract.
- INSTRUCTIONS.md (operator), HOW-TO-USE.md (producer, Convert and Flow naming),
  MASTERDOC.md (the SACRED floors mirrored from PRD Section 3, rule to code), and
  REPAIRS.md (the legacy defect register).
- anthology-engine-entry.sh: the ONE sanctioned entry, four fail-closed gates
  (deps, model-map pre-gate, run-dir bypass scan, enforcement hash pin), a run-scoped
  nonce, then dispatch of a stage runner.
- install.sh, preflight.sh (engine tier-map resolver plus a --check pre-gate),
  verify.sh (read-only self-verify scoped to this unit's artifacts), verify-deps.sh.
- config/: engine-config.template.json, model-map.template.json (five tiers, no
  Anthropic-family id, ollama-cloud baseUrl slotting), field-map.json (the exact PRD
  Section 6 keys, the ONLY place field keys are spelled), the three sanctioned
  nudge templates (em-dash-free, fence-free), and the pdf-house-style scaffolds
  (house.css at the 14-point floor plus seven per-deliverable templates for W1.12).
- scripts/stage_s0_intake.py through scripts/stage_s9_assembly.py: ten thin stage
  dispatchers, each carrying its ordered wiring contract (--plan), a fixed
  exit-code classification, and a --self-test.

Doctrine held throughout: nothing Anthropic-family in any file; credentials by
label only; Convert and Flow naming; contact_id keying; move in silence.
