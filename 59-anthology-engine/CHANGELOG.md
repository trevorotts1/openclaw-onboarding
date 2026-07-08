# Anthology Engine (Skill 59) -- Changelog

## Unreleased (2026-07-08) -- pipeline auto-create via Skill 6 browser control

provision_pipeline no longer STOPS-only when the standard "Anthology Engine"
pipeline is absent: GoHighLevel / Convert and Flow has NO public API to create
a pipeline (the UI is the only create surface), so a LIVE run now attempts ONE
browser-control creation through Skill 6's pipeline builder
(06-ghl-install-pages/tools/ghl_pipeline_builder.py, invoked as a subprocess
in exact-name mode with the 9 standard stages from the field-map contract --
the Skill 54 sibling-skill convention), then RE-READS the location's pipelines
and binds ONLY what the API read surface shows. This fulfills PRD 3.12
(locked): the standard pipeline is AUTO-PROVISIONED, never a manual operator
step by default.

Fail-closed contract (unchanged exit codes 0/2/3/5):
- A failed, lying (rc 0 but nothing readable), or unavailable walk STOPS with
  the same honest AF-AE-PIPELINE-UI-CREATE operator surface as before, now
  carrying the attempt receipt (attempted/rc/detail). NOTHING is stamped.
- An unreachable post-create verify read is HELD (exit 3, retryable) with
  nothing stamped; the re-run re-reads and binds by name (idempotent).
- Dry runs never invoke the browser. ANTHOLOGY_PIPELINE_BROWSER_CREATE=0
  restores the STOP-only behavior.
- Self-test additions: bind-on-verified-read, fail-closed STOP, lying-builder
  STOP, verify-read HELD, opt-out, dry-run-no-attempt, missing-builder
  receipt, and the exact --no-dry-run --exact-name argv (all with a MOCKED
  creator -- the self-test never launches a browser).

NOTE: the Skill 6 pipeline walk itself is RESEARCH-SEEDED (SELECTORS-LIVE-
pipeline.md), not yet live-locked; the first live creation run is a separate,
explicitly-operator-scheduled step.

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
