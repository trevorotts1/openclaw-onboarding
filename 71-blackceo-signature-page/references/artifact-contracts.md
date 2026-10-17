# Artifact Contracts

These are private production contracts for deterministic scripts and handoffs. They do not replace the detailed SOP.

## Recommended project output tree

```text
project/
  private/
    workflow-state.json
    internal-copy.md
    copy-manifest.json
    page-visual-bible.md
    image-map.json
    qc/
  public/
    public-copy.md
    html/
  wireframes/
    desktop/
    mobile/
  mockups/
    desktop/
    mobile/
  images/
    prompts/
    generated/
  review/
    desktop-wireframes.pdf
    mobile-wireframes.pdf
    desktop-mockups.pdf
    mobile-mockups.pdf
```

## Workflow-state JSON

Use the exact ordered stage IDs defined in `references/stage-contract.json` (enforced by `scripts/stage_gate.py`).

```json
{
  "workflow_id": "client-page-001",
  "page_version": "standard",
  "current_stage": "copy",
  "stages": {
    "intake": {"status": "ready", "attempts": 0},
    "copy": {"status": "working", "attempts": 0},
    "font-action-plan": {"status": "blocked", "attempts": 0},
    "desktop-wireframe": {"status": "blocked", "attempts": 0},
    "mobile-tablet": {"status": "blocked", "attempts": 0},
    "visual-mockup": {"status": "blocked", "attempts": 0},
    "image-inventory-prompts": {"status": "blocked", "attempts": 0},
    "image-generation-qc": {"status": "blocked", "attempts": 0},
    "image-map-upload": {"status": "blocked", "attempts": 0},
    "final-mockups": {"status": "blocked", "attempts": 0},
    "responsive-html": {"status": "blocked", "attempts": 0},
    "ghl-install-test": {"status": "blocked", "attempts": 0},
    "publish-verify": {"status": "blocked", "attempts": 0},
    "automation-wiring": {"status": "blocked", "attempts": 0}
  }
}
```

`attempts` counts focused repair attempts after failure. Valid range is 0-3.

The workflow has FOURTEEN stage IDs. The last, `automation-wiring`, is conditional (Item 31): it is required only
when the intake records `publish_target: "ghl"` and `automation_scope: "workflows"`. When it does not apply, the
gate records the stage with status `not_applicable` and a reason citing the intake values (also printed in
REPORT.md); a `not_applicable` stage is complete for report purposes and is never silently absent. The gate's own
state file (`private/state.json`) uses the same stage IDs and records `not_applicable` entries the same way.

## Image-map JSON

Each image entry is one intended generated master asset. Crops/exports can point to a `master_id` rather than pretending to be separately generated images.

```json
{
  "images": [
    {
      "id": "IMG-001",
      "source_passage": "Hero promise and opening emotional beat",
      "job": "Hero authority and aspiration",
      "scene": "Specific visual scene description",
      "people": "Black woman entrepreneur, fictional",
      "shot_plan": "Three-quarter environmental portrait, subject right third",
      "style_grade": "Selected page Art Direction plus compatible Secret Sauce",
      "text_mode": "no-generated-text",
      "references": [],
      "technical_plan": "Engine-supported wide landscape master",
      "prompt_file": "prompts/IMG-001.md",
      "asset_file": "generated/IMG-001.png",
      "filename": "IMG-001.png",
      "status": "ready"
    }
  ]
}
```

Required fields are validated by `scripts/validate_image_manifest.py`.

## Intake (`intake.json`)

Written by the intake stage with `scripts/write_intake.py`: `page_version` (standard or long-form), `brand_owner`,
`brand_file`, `creative_direction` (null means `SECRET_SAUCE_ONLY`), `image_cap`, `image_engine` (`kie` default or
`agnes`), `test_run`, and `copy_version` (`standard` or `long-form`). `copy_version` is a required intake decision
(Amendment 6, Items 18/19): it selects the ONE copy guide, copy spec, and emotional-quality extract the copy stage
reads; see "Copy selection record" below. `stage_gate.py` reads `image_engine` to accept the Agnes image route.

Delivery fields (Item 31, Amendment 4): `publish_target` (`ghl`, `vercel-embed`, or `vercel`), `automation_scope`
(`none` or `workflows`), and `credentials`: for each of the three delivery credentials (`pit`, `location_id`,
`firebase_refresh_token`) the VARIABLE NAME and a presence BOOLEAN, never a value. Intake refuses, in writing, a
workflows scope on a non-GHL target, a GHL target without the PIT or location ID present, and a workflows scope
without the Firebase token unless a choice is recorded (`firebase_backstop_declared: true`, or the scope dropped
with `automation_scope_dropped` recorded).

Layout waivers (Items 13/14): `layout_waivers` records each waiver the intake writer was given
(`gate`: `brand-fonts` or `layout-references`, plus its `reason`). The gate's layout gate consumes the matching
recorded waiver only; an absence with no recorded waiver fails the gate.

### Launch-context import and the `signature_launch_landing` profile (S71-02)

`write_intake.py --launch-context <page-request.json>` imports the approved Signature Launch context for the
run and activates the `signature_launch_landing` profile. The page-request is validated against the frozen 1.0
schema vendored at `references/page-request.schema.json` (byte-identical to S49's candidate PR #2137 at commit
a2bd2c5a; SHA-256 af0bb5738421f99dc9c6a7ba5a8618c2f6991fad061c7fc826b29caf229d847c). Optional companions are
validated the same way: `--launch-record <launch.json>` (`references/launch.schema.json`, SHA-256
b8e93f92b5d863fa31966b056e8905a1ace14808073892725dd4b3a5b04865a3) and `--route-graph <file>`
(`references/route-graph.schema.json`, SHA-256 be055305fd96787b89a52cada50362e4eaa580dadbe7db8d1f5dd47b9ad99d27).
Validation is performed by `scripts/launch_context.py`, which interprets the vendored schema documents so the
checks cannot drift from the frozen contracts. Any violation refuses the import with the violation named and
writes nothing: a schema violation, a page role other than `landing`, an `assigned_skill` other than 71, a
launch record whose identity, brand, or route fields disagree with the request, a launch record not in status
`approved` or `building`, a route graph whose SHA-256 differs from the request's `route_graph_hash` (stale
routing), or a brand file whose hash differs from the approved `brand_hash`.

Field mapping into `intake.json`: the request's `copy_profile` fills `copy_version` when it names `standard`
or `long-form` (a conflicting `--copy-version` flag is refused); the launch record's `image_provider` fills
`image_engine` (`kie` or `agnes`; `other_explicit` is refused, because this skill's intake cannot record it);
the request's `test_only` sets `test_run`. The intake then carries `launch_profile: "signature_launch_landing"`
and a `launch` block with the mapped context: launch ID and revision, tenant and location, request ID and
`input_hash`, page ID and role, `approval_ref`, brand ref/hash with the hash-check outcome, route graph
ref/hash and whether the graph was placed, offer refs, copy profile, allowed write target, journey mode and
image provider when the launch record was supplied, and the approved next role derived from the route graph
(the landing node's `interest_submitted` edge; `free_entry` only for a `free_entry` journey ending at the
terminal `thank_you` node, the same rule the S71-05 handoff applies).

Artifacts the import places in the run: `page-request.json` at the run root (verbatim; the S71-05 handoff
reads it there), `launch.json` at the run root when the record was supplied (the handoff reads `journey_mode`
there), the route graph at the request's `route_graph_ref` when supplied, `launch/popup-config.json` (the
branded interest popup's config in the S71-07 component's shape: component `interest-popup` 1.0.0, the fixed
field set `first_name`, `last_name`, `email`, `phone` with its native field map, and the consent statements),
and `launch/design-tokens.css` when the shared tokens component is present in the tree (the component's
`tokens_to_css()` output for the run's brand; absent values are recorded as missing, never substituted).
Consent statements arrive only through `--consent-statements` (a JSON list of `{id, text, required}` objects
in the component's config shape) and are carried verbatim; the import never invents statement text, and when
none are supplied the config records `consent_source: null` with an empty list. No frozen 1.0 schema carries
consent statements today: the launch schema has no communication/consent group, so this input is the carrier
until a schema revision adds one.

Profile effects while the profile is active: `stage_gate.py` engages the no-offer-pricing gate (S71-03) for
the copy stage's `validate_public_copy.py` run by appending `--no-offer-pricing`; if the validator on disk
does not support the flag, the copy stage fails closed naming the missing gate rather than validating without
it. Produced pages include `shared-utils/signature_launch/design/design.css` (SHA-256
68f6084ba8e86cb32622bbf799b49b16a518c4c348481dcbe2f992200cda2cce per the S71-07 component record) and the
run's tokens CSS; both are recorded in the intake `launch.design_assets` block. REPORT.md names the active
profile and its launch. The profile's routing inputs are the placed `page-request.json`, `launch.json`, and
route graph; routing decisions themselves belong to the S71-05 handoff at report time.

## Stage receipts and Review Receipt v2

A stage receipt `private/receipts/<stage>.json` carries `status`,
`author_agent`, `author_session` (the session that authored the stage's
work), `started_at`, `finished_at`, and where the contract requires them,
`cost` and `transport`. It never carries scores: Review Receipt v1 (a
`scores` object in the receipt) is retired, and the gate fails close on
any receipt that still presents one, naming the migration.

Scores live in per-item review files, one per reviewed item:
`private/reviews/<stage>/<item-id>.review.json`, where `<item-id>` is the
artifact's base name (`IMG-007`, `Image-003`, `part-03`,
`compare-1440-01`, `page-visual-bible`), or `stage` for single-artifact
stages. When covered files in different folders share a base name (a
desktop and a mobile `part-01.png`), the item id is disambiguated with
the folder name: `desktop-part-01`, `mobile-part-01`. When covered
files share a folder and a base name but differ by suffix (the page
visual bible's `page-visual-bible.json` and `page-visual-bible.md`),
the item id is disambiguated with the suffix instead:
`page-visual-bible-json`, `page-visual-bible-md`. One review file
never evidences two different artifacts. Each file contains exactly:

```json
{
  "item": "IMG-007",
  "artifact": "image-inventory-prompts/IMG-007.txt",
  "artifact_sha256": "<sha256 of the artifact bytes, computed by the writer>",
  "author_session": "<session that authored the artifact>",
  "reviewer_session": "<session that reviewed it, stamped from the environment>",
  "reviewed_at": "2026-10-13T00:00:00+00:00",
  "criteria": {"fidelity": {"score": 9, "note": "<evidence, at least 40 characters>"}},
  "verdict": "pass",
  "automatic_failures": [],
  "repair_attempt": 0,
  "specific_defects": [],
  "performed_check": "<what the reviewer actually did, in the reviewer's own words>",
  "next_current_artifact": "<the artifact this review advances or blocks>",
  "independent_review": true
}
```

The last six fields are the SOP's evidentiary fields (Amendment 6, Item 2
delta): `automatic_failures` (list, empty allowed, absence not allowed),
`repair_attempt` (integer 0 to 3, the focused repair attempt this review
follows), `specific_defects` (list of named defects, required non-empty on
a fail verdict), `performed_check` (what the reviewer actually did,
distinct from the criterion notes), `next_current_artifact`, and
`independent_review`, which the writer computes from the two sessions.

Review files are created only by `scripts/write_review.py`, run from the
reviewing session (`OPENCLAW_SESSION_ID`, else `CLAUDE_CODE_SESSION_ID`,
else `CLAUDE_SESSION_ID`). If no session id exists in the environment,
the review is still written, with `reviewer_session` recorded as
`UNKNOWN` and `independent_review` false, and a warning on stderr: the
limitation is reported, never simulated, and the run's review mode can
never be INDEPENDENT for that work. A missing artifact or missing
criteria remains a hard failure. At close the gate recomputes every
artifact hash, requires `reviewer_session` to differ from the author
sessions on record, validates the evidentiary fields, applies the
stage's `min_scores` per artifact (every criterion at or above `each`,
and where `average` is set, each item's own criterion mean must reach
it, with zero recorded automatic failures; cross-file pooling is not
allowed, Amendment 6 Item 12 delta), and records the review files' own
hashes into `private/state.json` at close, so a review edited after
close fails the next dependency check like a changed artifact.

## Copy selection record (copy stage)

`intake.json` carries `copy_version` (`standard` or `long-form`), a
required intake decision. The copy stage's `copy_selection` block in
`references/stage-contract.json` maps that value to exactly one governing
set: the selected guide (`references/BlackCEO-Signature-Landing-Page-Standard-v6.md`
or `references/BlackCEO-Signature-Landing-Page-Long-Form-v6.md`), its copy
spec (`references/copy-specs/standard-v6.json` or
`references/copy-specs/long-form-v6.json`), and the selected guide's
emotional-quality chapter extract
(`references/copy-specs/standard-emotional-quality.md` or
`references/copy-specs/long-form-emotional-quality.md`). The one-guide
rule is layer-scoped: the selected guide governs copy structure, while
the Production and QC SOP and the Image Intelligence Guide v5 remain in
the copy stage's reads as linked documents governing their own layers.

The copy stage receipt records the selection it actually used:

```json
"copy_selection": {
  "copy_version": "standard",
  "guide": "references/BlackCEO-Signature-Landing-Page-Standard-v6.md",
  "spec": "references/copy-specs/standard-v6.json",
  "emotional_quality": "references/copy-specs/standard-emotional-quality.md"
}
```

`scripts/validate_copy_structure.py` (a copy stage validator) checks the
public copy against the selected spec. The copy reviewer reads the
selected spec, the selected guide's emotional-quality material, the
internal manuscript, and the public copy.

## Delivery receipts (Items 5, 31, 32, 34)

The `ghl-install-test` receipt carries a structured `install` block, verified by `scripts/validate_install.py`:
`target` (`kind`: `ghl` or `vercel-embed`, `funnel_or_site_id`, `page_id_or_url`), `journey_checks` (`cta_clicks`
with a destination and `ok` each; `form_submit_test` with `performed`, the designated `test_contact_id`, and
`submissions_count` exactly 1 when performed, or a named `not_applicable_reason`; `popup_open_close` and
`mobile_keyboard_scroll` with `ok`), `sales_check` (`mode` `test` or `not_applicable`, `live_charge_made` always
false), `founder_photo` (source plus SHA-256, checked against the brand file's recorded hashes), and, for the
vercel-embed route only, `embedded_checks` (`iframe_sizing`, `popup_visibility`, `scroll_behavior`, each `ok`,
`performed_in: "ghl_embed"`). Evidence screenshots `ghl-install-test/evidence/desktop.png` and
`ghl-install-test/evidence/mobile.png` are required artifacts.

The funnel-completion sub-stage (Item 32) writes `ghl-install-test/funnel-completion.json` (per-object receipt:
`funnel`, `steps`, `forms`, `popups`, `click_actions`, `order_forms`, `products`, `payment`, each object with
its Amendment 5A `rail`, `created`, and `existence_check`) and `ghl-install-test/clickthrough.json` (the live
journey record), verified by `scripts/validate_funnel_completion.py` against
`references/funnel-completion-checklist.md`. When the sub-stage does not apply, the receipt file records
`status: "not_applicable"` with a reason citing the intake. The hand-off `handoff/automation-handoff.json`
(Item 31, IDs only) is recorded at this stage's close; its SHA-256 is stored in state and publish-verify
verifies the file is unchanged. The hand-off is produced at close by `scripts/automation_handoff.py`
(the R71H emitter, `references/automation-handoff.md` section "The producer"), which also writes
`handoff/emission-record.json` (the hand-off's hash, its origin, and the envelope state) and, when the
run carries the launch wiring inputs, the dispatch envelope `handoff/automation-request.json`.

The `publish-verify` receipt carries `public_url`; its validator fetches the URL and writes
`publish-verify/fetch-record.json` (`url`, `final_url`, `status`, `bytes`, `fetched_at`, `checks`,
`build_marker`, `verdict`: `pass`, `fail`, or `blocked`). A blocked verdict means the network could not be
reached: the stage stays open and the receipt records status `blocked`. Owner waivers for the publish rules
(Item 6) are recorded in the receipt's `publish_waivers` (`rule`, `reason`, `approved_by: "owner"`) and print
in REPORT.md. The publish close also verifies the automation hand-off against the hash locked in state at
`ghl-install-test` close: a changed file refuses naming both hashes, a missing file refuses by name, and on
a GHL run a missing locked hash refuses by name (there is nothing to verify the carried file against).

The `automation-wiring` receipt (Item 31) carries `workflows` (each with `workflow_id`, `name`, `trigger`,
`build_method`, Skill 44 `qc` evidence, and a `readback`), `form_exceptions` (forms with a
`no_workflow_reason`), `conversational` (per derived trigger: `trigger`, `source_id`, `workflow_id`, and the
Skill 38 `playbook`), `conversational_overrides` (owner-approved exceptions), `conversational_not_present`
(trigger classes with no instance in this funnel), and `ghl_pack_version`. The full contract is
`references/automation-handoff.md`. The receipt is filed by `scripts/automation_handoff.py` from the
recorded dispatch outcome (the R71H seam's receipt filing, packet section 4): it also carries the dispatch
binding (`request_id`, `request_version`, `handoff_sha256`, `outcome`), each workflow's `mechanism`
alongside its `trigger`, and the QC evidence's WF item count (`qc.wf_items`, verbatim). A refused dispatch
files the same receipt with status `blocked` and the verbatim reason in `dispatch_refusal`; the stage stays
open and the refusal prints in REPORT.md. A failed dispatch files status `fail` with its reason in
`dispatch_failure`.

A completed run ships `deliverables/` under the fixed manifest in `references/deliverables-manifest.md`
(Item 34), verified by `scripts/check_deliverables.py`: `manifest.json` indexes every file in the folder
exactly, and `provenance.json` records identifiers only (`run_id`, `github`, `vercel`, `ghl`).

## Section plan (`<stage>/section-plan.json`, wireframe stages)

Both wireframe stages (`desktop-wireframe`, `mobile-tablet`) produce a
`section-plan.json` in their stage folder: an ordered array of sections,
each:

```json
{
  "section_id": "<id, matching the copy manifest's section ids>",
  "copy_block_ids": ["<copy block ids this section renders>"],
  "image_slot_ids": ["<inventory slot ids placed in this section>"],
  "reference_traits": []
}
```

`reference_traits` is filled by the trait-mapping work that builds on this
spine; an empty array is acceptable until then. `scripts/validate_wireframe.py`
enforces, deterministically: section ids equal the copy manifest's ids in
the same order, each exactly once; slot ids match
`desktop-wireframe/image-inventory.json` in both directions; part PNGs are
consecutively numbered; part widths are 1440px (desktop) or 390px
(mobile) within 2px; and any aspect ratio the plan assigns a slot matches
the inventory's declared ratio for that slot.

## Generation receipt (stage `image-generation-qc`)

The stage receipt `private/receipts/image-generation-qc.json` carries a `transport` block and a `cost`
block. `scripts/stage_gate.py` refuses to close the stage without them. The full example and field
meanings are in `references/kie-generation-route.md` section 3. Summary: `transport.skill` is
`74-kie-live-adapter` (policy `66-kie-image`) or `63-agnes-image`; Skill 74 receipts need `mode: "active"`,
and one task per generated file with a real `task_id`, `model_id`, `model_source`,
`requested_ratio`, `generated_ratio`, `preflight_ok: true` and `budget_exit: 0`.

## Review-PDF manifest

The manifest is the authority for page order. Do not rely on lexicographic filename sorting.

```json
{
  "category": "desktop-wireframes",
  "output": "desktop-wireframes.pdf",
  "pages": [
    {"path": "../wireframes/desktop/part-01.png", "label": "Part 01"},
    {"path": "../wireframes/desktop/part-02.png", "label": "Part 02"}
  ]
}
```

Allowed categories:

- `desktop-wireframes`
- `mobile-wireframes`
- `desktop-mockups`
- `mobile-mockups`

`combine_review_pdf.py` writes the PDF plus an adjacent JSON receipt containing page order and SHA-256 hashes. `validate_review_pdf.py` checks the expected page count and receipt.

## Item state (itemized stages)

**Item state (itemized stages: image-inventory-prompts,
image-generation-qc).** Producer: `scripts/stage_gate.py` (`close-item`,
`block-item`). Consumer: `scripts/stage_gate.py` (fan-in at stage close),
`scripts/swarm_runner.py`. Location: `private/state.json` under
`items.<stage>.<item-id>`, plus one JSON line per transition in
`private/run-events.jsonl`. Item ids are the inventory ids from
`desktop-wireframe/image-inventory.json` (`IMG-001`, ...). A closed item
records `status`, `closed_at`, `artifact_hashes` (SHA-256 of the item's
artifact at close), `review` (the item's Review Receipt v2 path),
`review_item`, and `review_hash`. A blocked item records `status`,
`blocked_reason`, `blocked_at`. An item is done only when the gate closed
it; worker self-report never writes item state.

## Browser hygiene receipt (Item 33)

**Browser hygiene receipt (Item 33).** Per browser-using stage
(`ghl-install-test`, `publish-verify`, and `automation-wiring` when
the backstop runs), `<stage>/browser-hygiene.json`, written by the
stage gate's reaper pass from `private/browser-sessions.jsonl`:
`{stage, sessions_opened, sessions_closed, orphans_found,
orphans_reaped, unaccounted, headed_launches,
owner_override_headed, sessions: [{name, engine, binding, unit,
closed_by}], updated_at}`. The stage cannot close with
`unaccounted` above zero, or with `headed_launches` above zero
without the owner override recorded in the receipt.

## Run events and the runs index (Item 25)

Every run carries `private/run-events.jsonl`: one JSON line per event
(`run_initialized`, `stage_closed`, `stage_blocked`, `item_closed`,
`item_blocked`, `report_generated`, `pin_drift`), written only by
`scripts/stage_gate.py` and `scripts/swarm_runner.py` through the gate's
emission helper. The full schema is `references/run-events-schema.md`
(with `references/run-events.schema.json`); `REPORT.json` beside
`REPORT.md` follows `references/report-json.schema.json`. Environment
contract: `SKILL71_RUNS_INDEX` (path of the box-level append-only index
the shipper drains), `SKILL71_RUNS_SHIP_URL` and
`SKILL71_RUNS_SHIP_TOKEN_FILE` (the Command Center ingestion endpoint
and its token file; the token value is read at ship time and never
printed or stored in a run), and `SKILL71_RUNS_SPOOL` (the fallback
spool directory `scripts/ship_run_events.py` drains with exactly-once
semantics). Event payloads carry identifiers, statuses, scores, costs,
and hashes only: never prompts, page copy, image bytes, or credential
values.
