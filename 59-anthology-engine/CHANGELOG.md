# Anthology Engine (Skill 59) -- Changelog

## Unreleased -- U10 / B4: chapter-rewrite preservation + LARGE_TEXT alignment (Gaps G10, G11)

Rewrite-preservation build. A chapter rewrite no longer overwrites the base chapter
fields; the original and every rewrite now coexist in Convert and Flow. The field-map
also stops lying about the field dataType. Repo-only; no live GHL write.

Changed:
- `config/field-map.json`: added two rewrite-preservation deliverable pairs,
  `rewrite1` (`contact.anthology_chapter_rewrite1_doc_url` / `_pdf_url`) and `rewrite2`
  (`..._rewrite2_doc_url` / `_pdf_url`), plus their four provisioning rows (G10). The
  base `chapter` pair keeps the original; a rewrite lands in its own pair. Flipped every
  free-text key from `TEXT` to `LARGE_TEXT` (19 -> 23 keys) to match live and the
  every-text-field-is-multi-line law (G11). `total_keys` 19 -> 23. SINGLE_OPTIONS fields
  (review decision, cover choice) are deliberately not in this map.
- `scripts/caf_delivery.py`: `FieldMap.deliverable_for_rewrite(n)` + a `rewrite_number`
  arg on `deliverable_for_artifact_type()`; a `rewrite` artifact now routes to
  `rewrite1`/`rewrite2` by the participant's rewrite_count and REFUSES a slot-less or
  out-of-budget rewrite, so the base chapter is never overwritten. Self-test updated.
- `scripts/stage_s8_deliver.py`: reads the ledger rewrite_count and routes the rewrite
  to its preservation slot; writes it with byte-for-byte read-back; surfaces the count +
  `contact.anthology_rewrite_count` control field.
- `scripts/stage_s6_rewrite.py`: now delivers the rewrite (via S8) into rewrite1/rewrite2;
  the strike-gate step's budget-exhausting exit 4 is treated as the *legal final rewrite*
  at authoring time (previously it wrongly blocked the second rewrite). The hard
  "no third rewrite" refusal remains owned by `anthology_state` at the request gate.
- `scripts/anthology_registry.py`: create-default dataType `TEXT` -> `LARGE_TEXT`;
  self-test asserts the 23-key inventory and that a fresh location provisions LARGE_TEXT.
- `scripts/provision-anthology-client.sh`: operator surfaces say 23 keys / LARGE_TEXT.
- `tests/test_rewrite_preservation.py` (new): mock-GHL proof that the original survives
  both rewrites with read-back, a fresh location provisions LARGE_TEXT, and a third
  rewrite is refused by the real ledger with the count surfaced.

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
