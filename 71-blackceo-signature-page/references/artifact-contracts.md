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

Mockup architecture (Update Plan Item 5, Decision 2 option (i)): two stage IDs carry the mockup definition.
`visual-mockup` is the internal layout-proof stage: its artifacts are the page visual bible and a layout proof
render with solid-block image slots, both internal production artifacts, never the client-facing mockup.
`final-mockups` is the single client-judged mockup stage: it finalizes the layout proof per section with real
photography in every slot (supplied assets placed as files, never generated) and opens only after the image
generation chain (`image-inventory-prompts`, `image-generation-qc`, `image-map-upload`) has closed, which the
gate enforces through the contract's `depends_on`. The stage enumeration above is regenerated from
`references/stage-contract.json` whenever the stage list changes; the two files must always enumerate identical
stage IDs in identical order.

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
      "asset_file": "generated/Image-01.png",
      "filename": "Image-01.png",
      "status": "ready"
    }
  ]
}
```

Required fields are validated by `scripts/validate_image_manifest.py`.

### Delivered image filename convention (Update Plan Item 26, proposal P6)

One convention, ruled 2026-10-15: the manifest and the inventory carry
the three-digit internal ID (`IMG-001`); the delivered file carries the
two-digit name derived from that ID, `Image-NN.png` (`IMG-001` is
delivered as `Image-01.png`, `IMG-012` as `Image-12.png`, `IMG-123` as
`Image-123.png`). The `id` field is the internal ID; the `filename`
field is the delivered name; `asset_file` points at the saved master,
which the generation route saves under that same delivered name. The
internal ID never ships as a delivered filename (`IMG-001.png` is not a
delivered name), and the three-digit delivered form (`Image-001.png`)
is not used. `scripts/validate_image_manifest.py` carries the mapping
check: an entry whose `filename` is not exactly the delivered name for
its `id`, or whose `prompt_file` / `asset_file` carries a different
trailing number, fails by name, so every delivered file maps to
exactly one internal ID and one receipt.

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
(`gate`: `brand-fonts` or `layout-references`, plus its `reason`). The gate's layout gate resolves each
layout reference in order (the supplied or bundled original file, then the approved house default
registered in `assets/page-references/substitutions.json`, Item 17) and consumes a recorded waiver only
for a reference with no resolution; an absence with neither a resolution nor a recorded waiver fails
the gate, naming the reference.

Supplied-asset size checks (Item 19): when intake is given `--supplied-assets <declarations.json>` (a list, or an
object with an `assets` list), `scripts/write_intake.py` measures every declared supplied asset and records one
entry per asset in `supplied_asset_size_checks`. A declaration names the Item 3 supplied entry it aligns with
(`id`, a `source` beginning with `supplied`, and the asset `file`) and its slot: either an explicit `slot_px`
(`{width, height}`, the rendered size) or a `slot_ratio` (`"47:50"`) with a `slot_layout_width_px` (the layout
width; the rendered size is the layout size scaled by the named constant `DISPLAY_DENSITY_FACTOR` = 2 in
write_intake.py). `--section-plan <section-plan.json>` fills a ratio or layout width a declaration omits, from
the section's `slot_aspect_ratios` / `slot_layout_widths`. Each record carries `id`, `source`, `file`,
`asset_px` (the true dimensions measured from the file bytes, never from prose), `slot_px`,
`display_density_factor`, and `verdict` (`OK` or `UNDERSIZED`); an UNDERSIZED record also carries
`shortfall_px`. The verdict never blocks a run and never substitutes, upscales, or regenerates the asset; an
UNDERSIZED verdict prints as a named line at intake, in `REPORT.md`, and in the close evidence of every stage
that places supplied assets (`scripts/stage_gate.py`, `SUPPLIED_PLACING_STAGES`).

Funnel handoff (update plan Item 32): `funnel_handoff` records the signature page's own handoff contract:
the Convert and Flow form's identity (`form.name` and `form.form_id`), the `behavior` (`form_pop`: the page's
primary CTA pops the named form), and the `step_order` (`signature_page`, `product_selection_page`,
`order_form_page`). A run with no form identity records `funnel_handoff` as `status: "missing_input"` with
`missing: "form_identity"` and the recorded `reason`: the explicit missing input, never a silent placeholder
such as a `#join` link. The copy manifest's primary CTA entry carries the matching `form_pop` handoff type
(see "Copy manifest CTA entries" below), `scripts/validate_handoff.py` verifies the built page against this
record at the responsive-html stage, and the funnel-completion receipt proves the pop live at install (see
"Delivery receipts" below).

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
artifact's base name (`IMG-007`, `Image-03`, `part-03`,
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

## Copy manifest and the button handoff (`copy/copy-manifest.json`)

The copy manifest records the copy stage's selection and inventory:
`copy_version`, `page_version`, `offer_name`, `cta_destination` (the
page's CTA destination, with a `cta_destination_note` where the
destination needs one), `sections` (the ordered section ids and
names every downstream stage renders), and, where the run records it,
`deviation_notes` (see the Copy selection record above).

The button handoff is pinned here (update plan Item 8), after a
determination from the code:

- The downstream page build consumes `copy/public-copy.md`. Each
  button is a Markdown link carrying the exact label and the
  destination, e.g. `[Build My AI Workforce](#join)`, with the
  microcopy as the plain line beneath it. This is the renderer's
  source for button labels and destinations: `validate_page.py`'s
  copy-parity check reads the public file's Markdown link labels and
  requires them in the built page, and both v6 guides state the rule
  ("The public button gets only its supplied wording, not 'CTA
  BUTTON'"; the markers are stripped by the public-copy handoff).
- The full marker forms (`[CTA BUTTON: ...]`, `[CTA MICROCOPY: ...]`)
  live only in `copy/internal-manuscript.md`, where
  `validate_copy_structure.py` reads them for the spec's CTA map.
  `validate_public_copy.py` FAILS any public file containing the
  literal `CTA BUTTON` production marker. No stage brief may ask for
  markers in the public file.
- CTA inventory: the manifest carries a `ctas` array, one entry per
  CTA on the page: `{"section": "1", "label": "Build My AI
  Workforce"}`, with an optional per-entry `destination` overriding
  the manifest's `cta_destination`. The action plan (font-action-plan
  stage) repeats this inventory as its CTA table.
- The gate check is `gate:copy_handoff` (a copy stage validator): the
  declared CTA set is the manifest's `ctas` when it carries one, else
  the manuscript's `[CTA BUTTON: ...]` markers with the manifest's
  `cta_destination`; when both inventories exist they must agree
  exactly. Every declared CTA must resolve, in `copy/public-copy.md`,
  a Markdown link with its exact label and its destination. An
  undeclared prose link (the Section 12 in-letter link) is not a CTA
  and is never counted. A run that declares no CTAs anywhere passes
  vacuously; a production run's closed copy always declares them,
  because the spec's CTA map requires the buttons.

## Font map (`font-action-plan/font-map.json`)

Written by the font-action-plan stage (SOP Stage 3). The gate check is
`gate:brand_fonts` in `scripts/stage_gate.py`; this section documents the
shape that check reads, field by field, plus the evidence blocks the
downstream stages and the bible reviewer consume. A worker given only
this section must be able to produce a font map the gate accepts with no
shape improvisation.

```json
{
  "artifact": "font-map",
  "stage": "font-action-plan",
  "brand_id": "blackceo",
  "run_brand_file": "brand.json",
  "fonts": {
    "display": "Fraunces",
    "body": "Newsreader",
    "accent": "Libre Franklin"
  },
  "fonts_source": "derived",
  "font_rationale": "<why each of the three faces fits this page's copy and audience>",
  "font_reviewer": "<the designated reviewer: the visual-mockup stage's independent bible reviewer>",
  "families": {
    "display": {
      "family": "Fraunces",
      "role": "display",
      "provider": "Google Fonts",
      "css2_request": "https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,100..900;1,9..144,100..900&display=swap",
      "weights_used": [500, 600, 650, 700],
      "italics_used": true,
      "axes_used": {"opsz": "9..144 (set to the rendered size)", "wght": "500..900 as mapped per element"},
      "fallback_stack": ["Fraunces", "Georgia", "Times New Roman", "serif"]
    },
    "body": {
      "family": "Newsreader",
      "role": "body",
      "provider": "Google Fonts",
      "css2_request": "https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,200..800;1,6..72,200..800&display=swap",
      "weights_used": [400, 500, 700],
      "italics_used": true,
      "axes_used": {"opsz": "6..72 (set to the rendered size)", "wght": "400..700 as mapped per element"},
      "fallback_stack": ["Newsreader", "Georgia", "Times New Roman", "serif"]
    },
    "accent": {
      "family": "Libre Franklin",
      "role": "accent",
      "provider": "Google Fonts",
      "css2_request": "https://fonts.googleapis.com/css2?family=Libre+Franklin:ital,wght@0,100..900;1,100..900&display=swap",
      "weights_used": [700, 800],
      "italics_used": false,
      "axes_used": {"wght": "700..800 as mapped per element"},
      "fallback_stack": ["Libre Franklin", "Franklin Gothic Medium", "Trebuchet MS", "sans-serif"]
    }
  },
  "typography": [
    {
      "element": "hero_headline",
      "role": "display",
      "serves": "<which copy this element sets>",
      "sizes": {
        "desktop": {"px": 68, "line_height": 1.02},
        "tablet": {"px": 54, "line_height": 1.05},
        "mobile": {"px": 38, "line_height": 1.1}
      },
      "weight": 700,
      "style": "uppercase as written in the copy",
      "letter_spacing": "-0.01em",
      "colors": {"on_cream": "#1A1A2E", "on_navy": "#F5F0E8"},
      "wrapping": "<wrap behavior; never truncated>"
    }
  ],
  "breakpoints": {"desktop": "1440px wireframe canvas", "tablet": "768-1024px", "mobile": "390px baseline canvas"},
  "derivation_record": {
    "policy": "font_policy.when_brand_fonts_missing = derive-document (run brand file)",
    "brand_fonts_status": "<which roles were MUST_SUPPLY, or that the brand file supplied all three>",
    "supply_route": "Google Fonts by default, per SOP Stage 3A",
    "availability_check": "<performed while preparing the map (SOP Stage 3B): the CSS2 response for each css2_request>",
    "banned_fonts_check": {"banned_in_brand_file": ["<from the brand file>"], "faces_used": ["<the three families>"], "result": "<no intersection, or the failure>"}
  },
  "fallback_behavior": {
    "loading": "<display=swap behavior: text renders in the fallback stack, no invisible-text hold>",
    "proof_rule": "A fallback rendering is never labeled an exact-font proof (SOP Stage 3B); loading proof is document.fonts.load() plus glyph inspection once HTML exists",
    "stacks": "Recorded per family under families; every stack ends in a generic family and none is generic-only"
  },
  "palette_binding": {"<ground/text colors>": "<values and measured contrast pairs, with any prohibited pair named>"},
  "longest_copy_fit": {"longest_headline": "<text, character count, and fit result>", "longest_cta_label": "<text, character count, and fit result>", "longest_paragraph": "<character count and fit result>", "longest_word": "<word, rendered width at mobile body size, and fit result>"}
}
```

Field semantics the gate depends on:

- `fonts` (required object): exactly the three role keys `display`,
  `body`, `accent`, each holding ONE family-name string and nothing
  else. `gate:brand_fonts` collects EVERY string under this key
  recursively and tests each one as a used font family: it fails on any
  `TREVOR_MUST_SUPPLY` / `CLIENT_MUST_SUPPLY` placeholder, on any family
  absent from the brand file's `fonts` values (unless the derive path
  below applies), and on any family in the brand file's `banned_fonts`.
  Rationale, fallback stacks, and banned-list discussion therefore live
  OUTSIDE this subtree by design (stacks under `families`, discussion
  under `derivation_record`). If the `fonts` key is absent, the gate
  falls back to collecting every string in the whole file, which no
  real map survives: the key is load-bearing, not decorative.
- `fonts_source`, `font_rationale`, `font_reviewer` (top-level strings):
  the derivation documentation fields, named identically to the visual
  bible's three fields so the visual-mockup stage lifts them verbatim
  into `visual-mockup/page-visual-bible.json`. On the derive path (the
  brand file's fonts are still MUST_SUPPLY placeholders and its
  `font_policy.when_brand_fonts_missing` is `"derive-document"`),
  `gate:brand_fonts` requires all three: `fonts_source` equal to
  `"derived"`, a non-empty `font_rationale`, and `font_reviewer` naming
  the designated reviewer. `font_reviewer` in the font map names the
  reviewer designate (the visual-mockup stage's independent bible
  reviewer) and records NO approval; where and when the approval itself
  is recorded is pinned in "Derived-font approval: the pinned rule"
  below. When the brand file supplies the fonts, `fonts_source` is
  `"brand"` and the other two fields may be omitted.
- `families` (object by role): the loading record per family. The
  variant-request format is `css2_request`: the Google Fonts CSS2 API
  URL naming the family and the selected variants (the `ital`, `opsz`,
  and `wght` axes with the exact ranges the typography map uses),
  ending `display=swap`. Availability is confirmed against the live
  CSS2 response while the map is prepared (SOP Stage 3B) and recorded
  in `derivation_record.availability_check`; a stylesheet declaration
  alone is never loading evidence. `weights_used` and `italics_used`
  record the real variants the map calls for (no faux bold or italic),
  `axes_used` records the axis ranges as mapped per element, and
  `fallback_stack` is the ordered fallback list for the role.
- `typography` (array, one entry per page element): `element`, `role`,
  `serves` (the copy it sets, including the longest real instance),
  `sizes` for desktop/tablet/mobile (`px` and `line_height`), `weight`,
  and where they apply `style`, `letter_spacing`, `colors`, `wrapping`,
  `measure`, `alignment`, and a `fit_check` for constrained elements
  (CTA labels are fit-checked against the longest real label at mobile
  width; buttons stay at least 56px high at every width).
- `derivation_record`, `fallback_behavior`, `palette_binding`,
  `longest_copy_fit`, `breakpoints`: the evidence blocks. The gate does
  not read them; the bible reviewer and the wireframe stages do. The
  banned-fonts rule binds the fallback stacks as well as the three
  faces, as a contract requirement enforced by review, not by the
  gate: no stack may name a banned family, and no stack may be a
  generic-only stack (the brand file's banned `sans-serif-only`
  pattern). The bible reviewer checks the stacks recorded under
  `families` against the brand file's `banned_fonts`; `gate:brand_fonts`
  itself reads neither `families` nor `fallback_stack` and tests only
  the strings under `fonts`.

An intake-recorded layout waiver for the `brand-fonts` gate (see
"Intake" above) excuses the `gate:brand_fonts` check for the run; an
unrecorded absence is never a waiver.

## Derived-font approval: the pinned rule (update plan Item 7)

One rule governs derived-font approval. The font policy, the stage
contract, and SOP Stage 3 all state it in this substance:

- WHO: the reviewer is the visual-mockup stage's independent bible
  reviewer (the reviewer of `page-visual-bible`, a session different
  from the font map's author; Review Receipt v2 independence applies).
- WHERE: the approval is recorded exactly once, in the visual bible
  (`visual-mockup/page-visual-bible.json`): `fonts_source` `"derived"`,
  `font_rationale`, and `font_reviewer` naming that reviewer's
  session, lifted verbatim from the font map. The bible's Review
  Receipt v2 is the approval evidence. `validate_visual_direction.py`
  requires the three fields in the bible when the brand file's
  `font_policy.requires_reviewer` is true, and the gate's
  publish-verify rules refuse to close a run whose bible
  `font_reviewer` is a placeholder or the font map author's own
  session.
- WHEN: at the visual bible review (the visual-mockup stage). No
  approval is recorded at the font-action-plan stage: that stage's
  `review_required` stays false, and the font map's `font_reviewer`
  names the designated reviewer only, as a forward reference, never as
  a claim that approval has happened.
- THE GATE'S PART: `gate:brand_fonts` checks the families and, on the
  derive path, the documentation fields in the font map. It checks no
  approval, because none exists yet at that stage. Derived fonts
  documented this way are never blocked (the Brand Law carve-out); an
  undocumented derivation fails the font stage until the documentation
  exists.

## Action plan (`font-action-plan/action-plan.md`)

Written by the font-action-plan stage beside the font map (SOP Stage
3C). The gate checks the file for existence as a stage artifact; its
required content is contract here and enforced by review. Required
content:

1. Header: the run facts the plan serves (page_version, copy_version,
   creative_direction, image engine and cap, test_run, publish_target,
   automation_scope) and the companion font map named.
2. The visitor-action spec:
   - The ONE visitor action on the page, stated in one sentence. Every
     CTA on the page performs this action, with the section-specific
     label the closed copy prescribes.
   - The mechanism, chosen from the three the SOP names: an on-page
     form, a button-triggered popup, or a separate page or destination
     reached by link, with the reason grounded in the closed copy. The
     plan never invents a form, popup, or flow the copy does not
     prescribe.
   - The CTA inventory: every CTA on the page, with its section, its
     verbatim label, and its destination. Destinations come from the
     copy manifest (see "Copy manifest and the button handoff" for the
     pinned source rule).
   - The Section 12 in-letter link rule: the founder letter's inline
     link is a prose text link inside the letter's invitation
     paragraph. It is set in letter body type with link styling, is
     never styled as a button, is never counted as a CTA, and never
     appears in the CTA inventory. Downstream checkers treat it as
     prose copy, not as a button (the subject of update plan Items 1
     and 2).
   - The actual success destination and what a successful action
     produces, recorded from the copy.
   - Behavior spec: link/button semantics and keyboard focus (the
     visible focus treatment); pointer and touch behavior (including
     the button height floor); close behavior and return to scroll
     position, or an explicit not-applicable with the reason (no
     popup or overlay exists to close); mobile scrolling; loading and
     error handling, including the placeholder rule (a placeholder
     destination is a named missing input owned by a named stage,
     never papered over, and a page whose CTAs still point at a
     placeholder is never presented as production); and behavior when
     scripts fail (all copy readable and every CTA working with
     scripting disabled).
3. The motion specification: reveals, hover and press behavior, and
   the reduced-motion rule (`prefers-reduced-motion: reduce` disables
   reveals and transitions entirely; content is visible by default, so
   a script failure can never leave a blank section).
4. The production plan for the remaining stages, in stage-contract
   order: per stage, who builds it, what gets built, and the gate
   before it closes.
5. Type decisions in brief: the three faces, sizes, and binding color
   rules in summary, pointing at the font map for the full record.

## Copy manifest CTA entries (update plan Item 32)

`copy/copy-manifest.json` carries one entry per CTA in the copy under
`ctas`, so button behavior is specified where button copy is specified:

```json
"ctas": [
  {"section": "1", "label": "Claim Your Seat", "handoff_type": "form_pop", "primary": true},
  {"section": "5", "label": "See how it works", "handoff_type": "in_page_anchor"}
]
```

`handoff_type` is one of `form_pop` (the button pops the Convert and Flow
form intake names in `funnel_handoff`), `in_page_anchor`, or
`external_link`. Exactly one entry may carry `primary: true`, and the
primary entry's type is `form_pop`: the signature page's primary CTA pops
the named form, which leads to the product selection page and then the
order form page. `scripts/validate_copy_structure.py` fails a manifest
whose CTA entries lack a valid handoff type, mark more than one primary,
or give the primary another type; `scripts/validate_handoff.py` consumes
the primary entry at the responsive-html stage.

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
`references/funnel-completion-checklist.md`. When intake records the funnel handoff form (update plan
Item 32), the receipt gains the page-side proof lines: the receipt's `forms` array carries the named form,
the click-through's `primary_cta` record shows the primary CTA opening it (`opened_form_id`, `ok`), and the
form's landed test submission records `routed_to_step`, the product selection step it routes to. When the sub-stage does not apply, the receipt file records
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

## Wireframe artifact (spec image set; stages `desktop-wireframe`, `mobile-tablet`)

A wireframe is a designed, annotated build spec rendered as images, in
the client's brand colors: never an HTML render, never a screenshot of
a web page. Each wireframe stage delivers one spec image set in its
stage folder:

- section slices: `<stage>/section-*.png`, one slice per section of the
  stage's `section-plan.json`, in plan order, each at the stage's full
  page width (1440px desktop, 390px mobile) and its section's native
  height;
- the stitched full-page PNG: `<stage>/wireframe-full.png`, the slices
  assembled in section order into one full-page image;
- the combined PDF: `<stage>/wireframe.pdf`, the same slices in the
  same order.

The stitched PNG and the combined PDF match the slices section for
section: every section appears exactly once, in order, in each form. A
private assembly map records the slice order and each slice's file. The
set is produced by the pinned production method and carries the
per-section build record defined in "Production method and per-section
build record" below (`production-record.json`): per-section generation
inputs, native-aspect outputs, and the pre-stitching text-QC record.

### Part naming (human-facing letters, machine numbers)

Each section slice is one part of the wireframe export, and every part
carries two names for the same file:

- the human-facing name is lettered: the first slice in section order
  is Part-A, the second is Part-B, and later slices continue with
  consecutive letters in section order. Lettered names appear only
  where a human reads the export: human-facing exports and listings,
  including the Review-PDF manifest's page `label` values. A Part
  letter never becomes a page heading.
- the machine name is numeric: the slice's file name in its stage
  folder (`section-01.png` for the first slice, `section-02.png` for
  the second, and so on). The stage contract's artifact globs,
  validator output, and review item ids use machine names only: a
  review item id is derived from the file's base name exactly as the
  Review Receipt v2 section above prescribes, never from the Part
  letter.

The private assembly map is where the two names meet. It carries one
entry per slice, in section order, recording the machine name (the
file), the human-facing name (its Part letter), and the number and
name of the section the slice carries. When a part name is ambiguous,
the assembly map is the authority for which file a Part letter means.

Letters restart per wireframe: the desktop wireframe's first slice
and the mobile wireframe's first slice are both Part-A, under
different stage folders, and the folder name disambiguates them (the
same folder-disambiguation rule the review vocabulary applies to
same-named files in different folders). The stitched
`wireframe-full.png` and the combined `wireframe.pdf` are single
files and carry no part name.

Every section slice carries, printed on the sheet: the section's number
and name, against the selected copy guide's section standard; the
printed type specs for the section's elements (heading, body and CTA
sizes); every image slot as a deliberate placeholder labeled with its
aspect ratio and its art direction (what the image must show) — the
slot ids are the plan's `image_slot_ids`, and the labeled ratio is the
ratio the inventory declares for that slot; the run's real copy, and
CTA chips showing the real button text with their microcopy specs; and
the section's behavior notes. One header strip, carried at the head of
the stitched sheet (on its first slice), states the page width and the
content width. The annotations are production markings on a private
build spec: they are not page copy, and they never carry into the
mockup stages or the HTML.

## Section plan (`<stage>/section-plan.json`, wireframe stages)

Both wireframe stages (`desktop-wireframe`, `mobile-tablet`) produce a
`section-plan.json` in their stage folder: an ordered array of sections,
each:

```json
{
  "section_id": "<id, matching the copy manifest's section ids>",
  "section_number": 1,
  "section_name": "<the section's printed name>",
  "copy_block_ids": ["<copy block ids this section renders>"],
  "image_slot_ids": ["<inventory slot ids placed in this section>"],
  "slot_labels": {"<slot id>": {"aspect_ratio": "<inventory ratio>",
                                 "art_direction": "<what the image must show>"}},
  "type_specs": {"h1": "<size>", "h2": "<size>", "body": "<size>", "cta": "<size>"},
  "behavior_notes": "<the section's printed behavior note>",
  "header_strip": {"page_width_px": 1440, "content_width_px": 1200},
  "reference_traits": []
}
```

`header_strip` is carried on the first section only (it heads the
stitched sheet, on its first slice). The annotation fields
(`section_number`, `section_name`, `type_specs`, `behavior_notes`,
`header_strip`) and the per-slot labels are the Item 15 trait record
the wireframe validator checks (see the enforcement paragraph below).

`reference_traits` is filled by the trait-mapping work that builds on this
spine; an empty array is acceptable until then. `scripts/validate_wireframe.py`
enforces, deterministically: section ids equal the copy manifest's ids in
the same order, each exactly once; slot ids match
`desktop-wireframe/image-inventory.json` in both directions; the spec
image set's form (one `section-*.png` slice per planned section, slice
widths 1440px (desktop) or 390px (mobile) within 2px, the stitched
`wireframe-full.png` and the combined `wireframe.pdf` present); and any
aspect ratio the plan assigns a slot matches the inventory's declared
ratio for that slot.

Update Plan Item 15 adds the wireframe trait checks to the same
validator. Each section's plan entry also carries its printed
annotations as data: `section_number` (its 1-based position) and
`section_name` (W1); `type_specs` with `h1`, `h2`, `body`, and `cta`
entries (W2); `behavior_notes` (W6); and, on the first section only,
`header_strip` with `page_width_px` (the stage width) and
`content_width_px` (W5). Each slot carries its label in the section's
`image_slots` list (`{slot_id, aspect_ratio, art_direction}`) or its
`slot_labels` map: the aspect ratio must match the inventory's declared
ratio and the art direction must state what the image must show (W3).
The validator measures every slice's colors against the run's brand
palette (resolved from `--brand`, else the run's pinned
`private/brand.json`, else `intake.json`'s `brand_file`, else the
skill's own brand file): neutral pixels (the black-and-white plates and
text) are always allowed, and a slice fails W4 by name when no brand
palette color measures present or when more than a quarter of its
chromatic pixels measure off-palette. Each trait failure prints one
named line per section or slot. The plan entry is the annotation
record; the reviewer verifies the record against the printed sheet by
eye (the validator does no OCR).

## Mockup section generation record (`final-mockups/generation-record.json`)

The `final-mockups` stage (the single client-judged mockup) carries one
section generation record, `final-mockups/generation-record.json`:

```json
{
  "stage": "final-mockups",
  "sections": [
    {"section_id": "hero",
     "slots": [{"slot_id": "IMG-001", "source": "generated",
                "file": "image-generation-qc/Image-001.png"},
               {"slot_id": "IMG-002", "source": "supplied",
                "file": "final-mockups/assets/logo.png",
                "supplied_asset": true,
                "sha256": "<sha256 of the filed bytes>"}]}
  ]
}
```

Every slot in `desktop-wireframe/image-inventory.json` appears in the
record exactly once, in the section the wireframe section plan assigns
it to. `scripts/validate_mockup_slots.py` (a `final-mockups` validator,
re-run by the stage gate at close) enforces trait M1 (real photography
in every slot; zero placeholder slots): a `generated` entry traces
only when its file is on disk and is the slot's generated asset (the
image-map entry for the slot when the map records one, else the
generation stage's `Image-NNN` file matching the slot's `IMG-NNN` id);
a `supplied` entry traces only when the inventory entry is a supplied
entry (Item 3) and the entry carries the Item 3 supplied-asset record
(`supplied_asset: true` plus the sha256 of the filed bytes, verified
against the bytes on disk), and a supplied slot traced as `generated`
fails (supplied assets are placed as files, never generated). Any slot
tracing to neither fails the close by name. Mockup traits bind at
`final-mockups` only: the `visual-mockup` layout proof's solid-block
slots are by design and are never scored by this gate.

## Production method and per-section build record (`<stage>/production-record.json`; Item 13)

Wireframe spec images (stages `desktop-wireframe`, `mobile-tablet`) and
mockup section images (stage `final-mockups`) are produced by one pinned
method (SOP Stage 4D and Stage 11C):

- per-section generation via the KIE.ai GPT-image route
  (`references/kie-generation-route.md`: Skill 66 policy, Skill 74
  transport), with the exact model resolved from the model registry at
  build time; the skill text pins the method, never a model name;
- generation inputs per section: for a mockup section, the approved
  wireframe section slice is the layout reference; for a wireframe
  section, the section plan and the run's copy; in both cases the page
  visual bible (palette, fonts, grade) is the style input;
- each section generated at its native aspect: the stage's full page
  width and the section's own height;
- assembly by deterministic code, never by hand:
  `scripts/stitch_sections.py` stitches the slices into the full-page
  PNG in record order and writes `stitch-receipt.json`;
  `scripts/combine_review_pdf.py` combines the same slices into the
  combined PDF from a manifest whose pages are the slices in record order;
- text-fidelity QC before stitching: every section is read at native
  resolution and its words checked against the section's real copy; a
  section with any garbled word fails that section and is regenerated
  before stitching, and a garbled section is never accepted into the
  combined artifact.

Every stage folder that delivers a section image set carries a
`production-record.json`, validated by
`scripts/validate_production_record.py` (the stitcher runs the same check
and refuses to stitch a record that does not pass):

```json
{
  "artifact": "wireframe | mockup",
  "stage": "<stage id>",
  "page_width": 1440,
  "stitched_output": "wireframe-full.png",
  "pdf_output": "wireframe.pdf",
  "sections": [
    {
      "section_id": "<id, matching the section plan>",
      "slice": "section-01.png",
      "width": 1440,
      "height": 900,
      "generation": {
        "route": "kie-gpt-image",
        "model_id": "<id resolved from the registry at build time>",
        "model_source": "latest-family | explicit-request | department-pin | legacy-ratio-route",
        "layout_reference": "<approved wireframe section slice (mockup) or section plan (wireframe)>",
        "style_input": "<page visual bible file>",
        "native_aspect": "1440x900"
      },
      "text_qc": {
        "checked_at_native_resolution": true,
        "expected_text": "<the section's real copy>",
        "readback_text": "<the words read off the generated section at native resolution>",
        "garbled_words": [],
        "verdict": "pass",
        "attempts": 1
      }
    }
  ]
}
```

Field rules: `sections` is in section order and names every slice exactly
once; `width`/`height` are the slice's actual pixel dimensions and
`generation.native_aspect` equals them; `text_qc.garbled_words` is the set
of read-back tokens that do not appear in `expected_text` (the validator
recomputes it, so a record cannot claim a pass over garbled text);
`text_qc.attempts` counts the section's generations, so a section that
failed the QC leg and was regenerated records `attempts` of 2 or more.
A section whose recomputed garble set is non-empty, whose verdict is not
`pass`, or whose text-QC record is missing fails validation by name, and
the stitcher produces nothing from such a record.

## Hybrid board (`final-mockups/hybrid-board.png`; Item 12)

At mockup close, stage `final-mockups` produces one hybrid board as a
standard deliverable: a single sheet carrying three panels (the hybrid
traits H1/H2 of the Item 14 trait checklist):

- the mockup-fidelity desktop panel: the approved desktop mockup
  artifact itself, scaled to panel width;
- the mockup-fidelity mobile panel: the approved mobile mockup artifact
  itself, scaled to panel width;
- a section guide column matching the mockups (H2): the sections
  numbered and named in order, each with a mini wireframe thumbnail
  (the section's approved desktop wireframe slice, scaled down) and
  its typography specs (heading, body, CTA), drawn from the run's
  typography spec record (`font-action-plan/font-map.json`).

The board is composed deterministically by
`scripts/build_hybrid_board.py` from the already-approved artifacts
named in the board record, `final-mockups/hybrid-board.json` — never
by a new generation pass and never by hand:

```json
{
  "board_output": "hybrid-board.png",
  "desktop_panel": {"source": "final-mockups/<stitched desktop mockup png>",
                    "sha256": "<sha256 of that file's bytes>"},
  "mobile_panel": {"source": "final-mockups/<stitched mobile mockup png>",
                   "sha256": "<sha256 of that file's bytes>"},
  "guide": {
    "typography_source": "font-action-plan/font-map.json",
    "sections": [
      {"number": 1, "section_id": "<id, matching the section plan>",
       "name": "<section name>",
       "wireframe_thumbnail": "desktop-wireframe/section-01.png",
       "sha256": "<sha256 of the thumbnail's bytes>",
       "type_specs": {"heading": "...", "body": "...", "cta": "..."}}
    ]
  }
}
```

Field rules: every source is run-relative and byte-pinned by its
sha256, so a panel or thumbnail is the approved artifact or the record
fails by name; the guide's sections are numbered consecutively from 1
and, when the stage's `production-record.json` or the desktop
wireframe `section-plan.json` is present, their section ids equal that
record's ids in order (the guide matches the mockups). The composer
refuses a record that does not pass `scripts/validate_hybrid_board.py`
(the same check, run with `--check-board`, also requires the composed
board and the composer's receipt,
`final-mockups/hybrid-board-receipt.json`, to match the record: every
input hash and the board's own sha256). The composer is the board's
deterministic production step; trait-gate enforcement at the stage
gate is Item 15's, as with the wireframe set.

The board is the artifact the mockup approval is recorded against:
the stage contract's `final-mockups` entry names
`final-mockups/hybrid-board.png` as its `approval_artifact`, the
board is in the stage's review cover (review item `hybrid-board`),
and the stage receipt records
`approval_artifact: "final-mockups/hybrid-board.png"`.

## Parity evidence (stage `responsive-html`; Update Plan Item 16)

The approved final mockup is the design source of truth for the
responsive-html stage: the live page is built to match it, and the
stage's closing evidence is the parity record against it, produced by
`scripts/compare_sheet.py` into `responsive-html/compare/`:

- the side-by-side parity sheets: `compare-1440-*.png` and
  `compare-390-*.png`, each sheet carrying the mockup render on the
  left and the built page render on the right at that width;
- the structural drift table: `compare-report.json`, whose `drift`
  block records, per width (1440 and 390), the section count on both
  sides, the named drift failures, and one row per section carrying
  both sides' section signature, image-placement class, and
  heading-to-body font-size ratio with its measured drift.

The stage contract requires all three records as artifacts, and
`scripts/stage_gate.py` refuses the close unless the sheets at both
widths are present and the drift table's status is `pass`: named drift
failures (section count, section order, image-placement class,
heading-to-body ratio beyond tolerance), a skipped drift pass, or an
unavailable one each block close by name.

## Generation receipt (stage `image-generation-qc`)

The stage receipt `private/receipts/image-generation-qc.json` carries a `transport` block and a `cost`
block. `scripts/stage_gate.py` refuses to close the stage without them. The full example and field
meanings are in `references/kie-generation-route.md` section 3. Summary: `transport.skill` is
`74-kie-live-adapter` (policy `66-kie-image`) or `63-agnes-image`; Skill 74 receipts need `mode: "active"`,
and one task per generated file with a real `task_id`, `model_id`, `model_source`,
`requested_ratio`, `generated_ratio`, `preflight_ok: true` and `budget_exit: 0`.

## Supplied-asset record (Item 3)

An inventory entry in `desktop-wireframe/image-inventory.json` whose
`source` begins with `supplied` (for example `supplied-logo`,
`supplied-founder-photo`) names an existing asset requiring no
generation. No prompt is authored for it and no generation task ever
runs for it; the asset is never generated and never substituted.

At stage `image-inventory-prompts`, the entry's per-image TXT file
(`image-inventory-prompts/IMG-NNN.txt`) is a supplied-asset record in
this fixed plain-text format:

```text
SUPPLIED ASSET RECORD
Image: IMG-012
Source: supplied-founder-photo
SHA-256: <the asset sha256 recorded on the inventory entry>
Aspect ratio: <the aspect ratio recorded on the inventory entry>
This asset is supplied by the owner as an existing asset; it is not a generation prompt.
Generation: NONE. No generation was performed for this asset, and none is permitted; the supplied asset is never generated and never substituted.
```

`scripts/validate_prompt.py` validates the file as a record, not as a
prompt: the record must name the image id, carry the asset sha256
recorded on the inventory entry, carry the inventory aspect ratio,
declare itself supplied, and carry an explicit no-generation
declaration; every missing or mismatched field fails by name. A
passing record prints a PASS line naming the exception. Supplied
entries are exempt from style-selection governance:
`scripts/stage_gate.py` does not require a selection record to govern
them.

At stage `image-generation-qc`, the file placed in the stage folder
is the supplied asset itself. Its `transport.tasks` entry in the
stage receipt takes the supplied-asset form instead of a Skill 74
task:

```json
{"file": "image-generation-qc/Image-012.png", "supplied_asset": true, "sha256": "<sha256 of the filed bytes>"}
```

The gate verifies the recorded sha256 against the actual bytes on
disk, and against the sha256 recorded on the inventory entry when the
entry records one. A supplied item whose filed bytes do not match
fails by name.

## Review-PDF manifest

The manifest is the authority for page order. Do not rely on lexicographic filename sorting.

```json
{
  "category": "desktop-wireframes",
  "output": "desktop-wireframes.pdf",
  "pages": [
    {"path": "../desktop-wireframe/section-01.png", "label": "Part-A"},
    {"path": "../desktop-wireframe/section-02.png", "label": "Part-B"}
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
