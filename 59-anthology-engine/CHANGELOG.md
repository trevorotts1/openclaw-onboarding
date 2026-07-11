# Anthology Engine (Skill 59) -- Changelog

## Unreleased (2026-07-09)

Integration branch consolidating the Anthology Engine feature units (U5, U6, U7, U8,
U9, U10, U19, U20, U21) under one Unreleased heading. Version intentionally left
unbumped (see skill-version.txt / SKILL.md) until the release cut.

### E9: per-Doc Drive credential broker implemented end-to-end (skill-version 0.1.3 -> 0.1.4, 2026-07-11)

Closes the E9 gap where the per-Doc Google Drive broker path was unimplemented on pure
client boxes: `drive_adapter.broker_stub` raised "not yet implemented via the broker"
for the per-Doc ops and `drive-tree-provision.provision` raised in broker mode, so a
client box (which holds NO Google key) dead-ended mid-run at S0 (participant tree) and
S7/S8 (cover upload, Doc create/share, confirm-then-pull). Now the WHOLE S0..S8 Drive
path runs through the n8n credential broker.

Added / changed:
- `scripts/drive_adapter.py`: implemented the four per-Doc broker actions
  (`broker_create_doc`, `broker_upload_media` [`upload_pdf`], `broker_share`
  [`share_doc_edit`], `broker_pull_doc_text`) plus `broker_provision_participant_tree`
  (`create_participant_tree`). `deliver_doc` / `deliver_media` / `do_share` /
  `pull_doc_text` now SELECT the broker whenever `broker_configured()` (else the local
  SA on the operator's own box), normalizing every broker response to the local-SA shape
  so the stage runners consume either path identically. Split `_broker_post` into a
  classify-friendly `_broker_request` + the fail-loud `_broker_post`. Removed the
  `broker_stub`/`BROKER_STUB_ACTIONS` dead end; added `BROKER_DOC_ACTIONS`,
  `BROKER_PARTICIPANT_ACTION`, `BROKER_REQUIRED_ACTIONS`.
- SHORT preflight: `broker_capabilities()` + `broker_preflight()` + a `broker-preflight`
  CLI that probes the broker's `capabilities` (with a side-effect-free `probe:true`
  fallback for an older broker) and HOLDs (exit 3) naming any missing REQUIRED action.
  Wired into `provision-anthology-client.sh` STEP 5 so an under-provisioned (stale)
  broker HOLDs at provisioning by name (AF-AE-BROKER-ACTIONS-MISSING) instead of
  dead-ending mid-run.
- `scripts/drive-tree-provision.py`: the per-participant `provision` path is now brokered
  (`create_participant_tree`) instead of raising in broker mode.
- `config/n8n/anthology-drive-broker.workflow.json`: the route template now dispatches
  `create_participant_tree`, `create_doc`, `upload_pdf`, `share_doc_edit`,
  `pull_doc_text`, and `capabilities`/`probe` (via a Switch router). The per-Doc branches
  use Drive-scope-only endpoints (`files.create` + `uploadType=media` update +
  `files.export`), so the single Google Drive OAuth2 credential suffices (no Documents
  scope). Ships INACTIVE; operator imports/activates it (README updated).
- Tests: `tests/test_drive_broker_per_doc.py` (per-Doc routing, base64 relay, byte-exact
  pull, participant tree, preflight capability/probe HOLD-by-name) and
  `tests/test_drive_broker_workflow.py` (route-template structure/contract) added;
  `tests/test_drive_broker.py` stub assertion updated. drive_adapter + drive-tree
  self-tests extended.
- LIVE (operator, NOT in this repo change): import + activate the workflow in n8n,
  connect the Google Drive credential + set `ANTHOLOGY_DRIVE_BROKER_TOKEN` /
  `ANTHOLOGY_DRIVE_ROOT_FOLDER`, then confirm `drive_adapter.py broker-preflight` exits 0
  on a client box. No live n8n/Drive write is performed by this branch.

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

### Release bus: the chapter / rewrite / cover producer gates are now LIVE

Promotes the s5 (chapter), s6 (rewrite) and s7 (cover) producer RELEASE gates from
wired-ahead to LIVE, so a committed board-door producer approve fires the
`anthology-release-chapter` / `-rewrite` / `-cover` tag through the SAME release bus
as the avatar / tone / outline gates. The release-tag slugs were already defined in
`gate_engine.py` (`GATE_RELEASE_SLUG`) and seeded in the snapshot contract; only the
`GATE_BY_CURSOR` entry + the sole writer's gate vocabulary were missing.

Changed:
- `scripts/gate_engine.py`: `GATE_BY_CURSOR` now maps the producer-review cursors
  `s5_chapter` -> `s5_producer`, `s6_rewrite` -> `s6_producer`, `s7_cover` ->
  `s7_producer` (board-door producer gates, actions approve/hold/exclude/escalate).
  `release_slug_for` fires each stage's slug on a committed BOARD approve and nothing
  else. Self-test extended to prove all three fire on approve and never on
  hold/exclude/escalate, the token door, or an uncommitted decision.
- `scripts/anthology_state.py`: adds `s5_producer` / `s6_producer` / `s7_producer` to
  `APPROVAL_GATES` as RELEASE-ONLY producer gates. A committed producer approve is
  recorded append-only so the release tag can fire, but owns NO cursor edge -- the
  pipeline advance stays with the stage runners + the `s5_participant` gate (no
  title-lock / rewrite-budget / chapter-freeze guard applies). Existing gate edges,
  the rewrite budget, and the S9 assembly rules are untouched.
- `scripts/stage_s5_chapter.py` / `stage_s6_rewrite.py` / `stage_s7_cover.py`: docstring
  + wiring notes describing the now-live board-door producer release gate for each
  stage's artifact.

Added:
- `tests/test_release_bus_producer_gates.py`: 12 hermetic tests -- pure
  `release_slug_for` proofs plus end-to-end walks through the real gate machine
  proving each producer approve fires its tag (release-only, cursor unchanged) and
  hold/exclude/token-door never release; the three original live gates regress clean.

The snapshot contract's WIRED-AHEAD -> LIVE status flip + the tag->notification GHL
workflow are owned by the concurrent snapshot unit landed just above (this change is
engine-only).

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
