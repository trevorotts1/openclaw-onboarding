# Anthology Engine (Skill 59) -- Changelog

## Unreleased (2026-07-09)

Integration branch consolidating the Anthology Engine feature units (U5, U6, U7, U8,
U9, U10, U19, U20, U21) under one Unreleased heading. Version intentionally left
unbumped (see skill-version.txt / SKILL.md) until the release cut.

### Snapshot: eight tag->notification release workflows built + snapshot contract updated (2026-07-10)

Closes the release-bus gap: the engine EMITS `anthology-release-*` / `anthology-delivered`
tags, but the GHL automation that turned a release tag into the author's email + SMS did not
exist. Built the eight per-stage tag->notification workflows in the operator's OWN template
location `2HIKGNgsixWx0yds7Qnx` (folder `Anthology Engine`) via the Skill 44 caf Convert and
Flow Firebase build rail, and recorded them in the snapshot contract so a re-cut snapshot
carries them.

Added:
- `config/anthology-snapshot-contract.json` -> `workflows.release_notifications`: the eight
  release-notification workflows as a CONTRACT DESCRIPTION (not a banned workflow JSON export)
  -- `Anthology Release: Avatar / Tone / Outline & Blurb / Chapter / Rewrite / Cover Picks /
  Final Chapter` and `Anthology: Book Delivered`, each a contact_tag trigger on one release
  slug -> producer-branded email (per-stage PDF-view + Doc-edit links from
  `field-map.json deliverable_fields`) -> link-only SMS. Plus `workflows.copy_law`
  ("editors" never "AI", zero em-dashes, `{{ custom_values.producer }}` merge),
  `workflows.publish_state_note`, and `workflows.per_client_sms_phone_flag` (Gap G15).
- `references/anthology-snapshot-guide.md`: Section 1 item 5 and Section 2 item 5 now
  describe the eight workflows, the per-stage links, the copy law, the publish + enable order
  (LIVE avatar/tone/outline first), and the SMS phone-number requirement.

Changed:
- `snapshot_version` bumped `anthology-engine-snapshot-20260710` ->
  `anthology-engine-snapshot-20260710-r2`: the first `-20260710` cut PREDATED these eight
  workflows and is STALE. The snapshot MUST be RE-CUT (or push-updated) so it carries them.

Notes:
- The drift gate `scripts/qc-snapshot-contract.sh` does not assert the `workflows` block, and
  no new tag slugs were introduced (the eight slugs were already in `tags.slugs`), so the gate
  and the hardcoded `EXPECTED_TAG_SLUGS` / `LIVE_SLUGS` are unaffected.
- Publish state: the caf Firebase rail builds these as drafts with triggers created ACTIVE;
  each needs one Publish toggle in the Convert and Flow UI to fire live.

### U9: S9 assembly transitions + brand-new Grand Finale + ordering data

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

### U10 / B4: chapter-rewrite preservation + LARGE_TEXT alignment (Gaps G10, G11)

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

### Integration note (field-map key count)

U10 above describes its isolated delta (19 -> 23 keys). Merged with U8's cover-style
block, the field-map now carries **28** provisioning keys: 19 base + 4 G10 rewrite +
5 U8 cover-style (four `anthology_cover_sample{1..4}_url` LARGE_TEXT + one
`anthology_cover_choice` SINGLE_OPTIONS). The cover-choice SINGLE_OPTIONS field IS in
the provisioning inventory (U8); the universal-review decision field remains out of it.

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
