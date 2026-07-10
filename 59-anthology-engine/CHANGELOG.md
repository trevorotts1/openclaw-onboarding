# Anthology Engine (Skill 59) -- Changelog

## Unreleased (2026-07-09) -- U9: S9 assembly transitions + brand-new Grand Finale + ordering data

Adds the three assembly-finale pieces the current engine did not do. All LLM calls
mocked in tests; no live model, no ledger schema change (the sole writer is untouched).

Added:
- `assets/prompts/ae-05-inter-chapter-transition.md`: the editors' 150-300 word
  bridge for one seam, naming the NEXT chapter's LOCKED title verbatim, zero
  em-dashes, "editors" never "AI". Pinned in ENGINE-MANIFEST.json.
- `assets/prompts/ae-06-grand-finale.md`: a BRAND-NEW closing chapter with its own
  title, transitioned in from the last co-author, referencing every included
  chapter, ending with a `## Where Do You Go From Here` action-steps section,
  14-point floor, zero em-dashes, "editors" never "AI". Pinned in ENGINE-MANIFEST.json.
- `scripts/stage_s9_assembly_logic.py`: `write_transitions` (N-1 bridges, one per
  seam) and `write_finale` (the Grand Finale, written only after the set is
  finalized/approved/ordered); `compile_manuscript` now interleaves the bridges and
  appends the finale as sentinel-wrapped INSERTIONS in the compiled edition only,
  leaving every frozen chapter byte-untouched. Two provers: `prove_transitions`
  (exactly N-1 seams, each names the next locked title, zero em-dashes, byte-diff
  proves no frozen chapter changed) and `prove_finale` (references every chapter,
  action-steps section, 14pt floor, zero em-dashes). `build_ordering_view` /
  `ordering_view` expose the proposed order + a one-line rationale per slot for the
  Command Center assembly cockpit (U9c). New CLI subcommands: `transitions`,
  `finale`, `ordering`, and a standalone dual `prove`.
- `tests/test_s9_assembly_transitions_finale.py`: 17 hermetic tests exercising both
  provers end-to-end (mocked router) plus their negative (fail-catch) paths.

Changed:
- `scripts/stage_s9_assembly.py`: on the producer's "Confirm the finalized set &
  order" (request `confirm_order`), writes the transitions + Grand Finale and passes
  them to `compile_manuscript`; persists the cockpit ordering view to the run dir.
- `scripts/qc-tier1-anthology.py`: widened the stage-tag leak detector to `ae-0[1-6]`
  so a leaked ae-05/ae-06 tag is caught in deliverables too (33-check self-test green).
- `ENGINE-MANIFEST.json`: registered the two new pins; S9 row records the two new
  provers and persona `ae-01..06`.

## 0.1.1 (2026-07-08) -- intake-transform comment scrub (guard-prompt-pins)

Patch fix, no runtime behavior change.

Changed:
- `config/hooks/transforms/anthology-intake.mjs`: reworded the CONTRACT comment so
  it no longer contains a token matching the Airtable base-id shape (`app` + 14
  base62 chars). The token was an incidental camelCase code-identifier (a gateway
  hook-mapping function name) referenced in documentation, NOT any Airtable base id,
  and never a runtime value -- but the shipped `guard-prompt-pins.py` runtime-surface
  scan (check 4a, AF-AE-PROMPT-PIN) matched its shape and failed W5.8. The comment
  now describes the same dist/hooks-*.js hook-mapping applier without the matching
  token. The transform still resolves its router purely from environment
  (`ANTHOLOGY_INTAKE_ROUTER` / `ANTHOLOGY_SCRIPTS_DIR`) and never carries a base id;
  the engine reaches its state base by the `ANTHOLOGY_STATE_BASE_ID` label only.

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
