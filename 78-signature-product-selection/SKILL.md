---
name: signature-product-selection
description: Build the specificity-led Product Selection page (the order page: the page where a buyer chooses between packages, with its desktop and mobile wireframes and mockups) for a Signature Launch with multiple meaningful packages or tiers. Normalizes approved offers into an accurate comparison matrix (included, not included, limited, conditional), an optional evidence-backed recommendation, accessible selection UI model, and a validated selection.json intent that preserves the native product/price mapping into Skill 79 checkout. Invoke only when the approved launch has multiple meaningful choices; one simple offer skips this skill entirely and uses Skill 79 combined explanation/checkout mode. Never collects payment, never trusts a URL price, never invents tiers, prices, popularity, or savings claims.
version: 0.2.5
---

# Signature Product Selection (Skill 78) - the order page (package selection)

Status: the plan builder, page-result emitter and image route are wired into
Skill 49 dispatch (product_selection) and Skill 83. The runtime descriptor
(`runtime-manifest.json`) still states the honest installation proof level: a
descriptor is not an installation, and no native page, route or price is
claimed installed in any tenant by this skill. Engineering history: the packet
v1.0 spec `08_SKILL_78_PRODUCT_SELECTION_SPEC.md`; version 0.2.0 added the
production session store, the runtime adapter and the on-disk broken fixture
set on top of the 0.1.0 checkpoint accepted as placed (PR #2143 at bf56760f).
"Order page" in a request means this page: the page that lets a buyer choose
between packages. The order form that takes payment is Skill 79 (checkout).

## Invocation boundary

- Journey mode `multiple_options` only. `single_simple` returns a decline
  result directing the caller to Skill 79 combined mode; it never renders a
  fake one-button selection page.
- An explicitly requested standalone comparison page may run with its own
  approved brief.
- Input offers must be approved. Unknown price is never zero, never free.
- Selection output is `selection.json`: intent only, never payment evidence.

## What it produces

Clean page copy model, comparison matrix, selection UI model, selection-state
contract, responsive HTML/CSS (later tasks), asset list, native binding plan,
a page result in the shared doc 02 contract shapes, and, when the launch asks
for them, the page's wireframes and mockups (next section).

## Wireframes and mockups (desktop and mobile)

This page gets its four image stages from Skill 71's shared image service, never
from a pipeline of its own. `scripts/run_image_stages.py` is the one call
the service expects from the owning skill:

1. `71 shared_page_service.py --page-version product-selection` admits the page
   as `page_role` `product_selection` and writes `intake.json`.
2. `scripts/emit_section_manuscript.py` turns the approved plan into the page's
   five sections (copy form `product-selection`, 71
   `references/copy-specs/product-selection-v1.json`): 1 Bridge headline,
   2 How to choose, 3 Packages (one card and one Choose button per approved
   offer), 4 Compare, 5 Questions and trust. Every fact is the plan's; the two
   sentences the plan has no field for are authored (`copy.json`) or derived from
   the plan's own matrix, and the manifest says which.
3. `71 build_production_request.py --copy-version product-selection` and
   `71 stage_executor.py` make the desktop wireframe, mobile wireframe and the
   visual mockup (desktop and mobile), then the one long PDF per stage and the
   overview boards on the paid provider. `final-mockups` waits for the client's
   approval of the Design Board (`page_role` `product_selection`).

Everything taught for every page type applies unchanged because it is Skill 71's
route: the client's brand colours only, the Design Board first, annotated
build-spec wireframes (numbered section chips, type specs, labelled image
plates, filled buttons, never grey line work), design style A, B or C (style B
package images are circle PNGs with transparent corners), composition variety,
the hypersaturated grade, references for structure only. Each approved package
gets one image plate (`PKG-n`), so the Design Board's image grid is never empty.
Free proof: `run_image_stages.py ... --preflight` composes and checks every
prompt with no provider call. A paid run is the same command with the inputs
naming `kie` and `--allow-paid` added by hand; dispatch never passes it.

## Scripts (stdlib only, fail-closed)

- `scripts/build_selection_plan.py` - validate a launch catalog and emit the
  normalized selection plan (matrix + UI model), or decline single-offer use.
- `scripts/validate_selection_content.py` - claim and specificity checks on
  authored selection copy against the approved catalog.
- `scripts/validate_selection_binding.py` - check that a selection.json intent
  preserves the approved native product/price mapping for Skill 79, rejects
  query-string price authority, cross-tenant IDs, and stale revisions.
- `scripts/selection_session.py` - session bridge core: opaque reference,
  TTL, resume with revalidation, reconfirm-on-change, idempotent confirm.
- `scripts/selection_session_store.py` - production session storage: the
  core's semantics persisted in tenant-scoped SQLite (one database per
  tenant, fail-closed reads, fail-loud writes). See
  `references/session-storage-contract.md`.
- `scripts/selection_runtime.py` - the runtime adapter: one fail-closed
  request envelope dispatching to the shipped modules (plan, preview,
  select, binding, page result, session actions). See
  `references/runtime-adapter-contract.md` and `runtime-manifest.json`.
- `scripts/render_selection_preview.py` - local-only responsive HTML preview
  from a plan (default, selected, error, reconfirm states), using
  `components/selection-ui/selection.css`.
- `scripts/emit_section_manuscript.py` - the approved plan as the five-section
  order page manuscript and manifest for Skill 71's image pipeline.
- `scripts/run_image_stages.py` - the order page's wireframes and mockups,
  through Skill 71's shared image service (`--inputs none` is refused: the order page always gets its images).
- `scripts/emit_binding_plan.py` - the explicit per-price-choice binding plan
  consumed by S79 and S06.
- `scripts/emit_page_result.py` - page result emitter (Path A follow-on
  after PR #2158): writes the bare packet page-result 1.0 document
  (schema/page-result.schema.json, doc 02 section 6) to the `--output`
  file path, echoing `page_id` and `input_hash` from the request and
  carrying no `outcome` field. The plan outcome remains in Skill 78's
  own selection-result profile (schema/selection-result.schema.json,
  via `emit_selection_result()`). Honest L1 proof.
- `scripts/selection_core.py` - the shared normalization/validation core the
  wrappers call. No wrapper duplicates its logic.

References: `references/selection-copy-profile.md`,
`references/selection-ui-contract.md`, `references/binding-plan-contract.md`,
`references/asset-integration.md`, `references/session-storage-contract.md`,
`references/runtime-adapter-contract.md`. Negative cases ship as inspectable
files under `fixtures/broken/` with their expected violation codes pinned by
`tests/test_broken_fixtures.py`.

Exit codes follow house convention: 0 pass, 2 violation, 3 fail-closed error.
Every script carries `--self-test` with VALID + VIOLATION fixtures.

## Delegation seams (never forked)

- Native product/price creation and read-back: S44 / S06.
- Installation of the custom presentation and native click actions: S06.
- Checkout, combined single-offer mode, order bump, offer price display
  component: Skill 79 (S78 reviews price display facts, does not own it).
- Shared design tokens and brand loader: Skill 71. Comparison matrix
  component: this skill (doc 16).
- Images: only through the selected shared provider adapter (S63 / Skills
  66/74 policy and transport). No hand-rolled provider, GHL, or payment code.
