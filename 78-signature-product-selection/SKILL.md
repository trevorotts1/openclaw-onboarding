---
name: signature-product-selection
description: Build the specificity-led Product Selection page (the order page: the page where a buyer chooses between packages, with its desktop and mobile wireframes and mockups) for a Signature Launch with multiple meaningful packages or tiers. Normalizes approved offers into an accurate comparison matrix (included, not included, limited, conditional), an optional evidence-backed recommendation, accessible selection UI model, and a validated selection.json intent that preserves the native product/price mapping into Skill 79 checkout. Invoke only when the approved launch has multiple meaningful choices; one simple offer skips this skill entirely and uses Skill 79 combined explanation/checkout mode. Never collects payment, never trusts a URL price, never invents tiers, prices, popularity, or savings claims.
version: 0.2.9
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

- Journey mode `multiple_options` only. `check_invocation` (in
  `scripts/selection_core.py`) returns `decline_single_offer` for
  `single_simple`, and for any launch with a single main offer whatever its
  journey mode claims, directing the caller to Skill 79 combined mode; it never
  renders a fake one-button selection page.
- An explicitly requested standalone comparison page may run with its own
  approved brief.
- Any other journey mode (`folded_levels`, `free_entry`, ...) has no selection
  page in its route graph: `check_invocation` returns `decline` and
  `validate_catalog` refuses it (`S78-JOURNEY-MODE-DECLINE`).
- The one exception is the route that builds no selection page:
  `route="per_offer_targets"` (one native checkout target per approved price
  choice, `emit_binding_plan.py`). `check_invocation(launch, route=...)` and
  `validate_catalog(launch, route=...)` accept any journey mode with several
  main offers for that route, so a consumer states the route and never rewrites
  `journey_mode`. A single main offer is declined on every route.
- Input offers must be approved. Unknown price is never zero, never free. A
  `recommended_unapproved` price is covered only when the launch record is
  `approved`/`building` and carries a `plan_approval_ref` (the plan approval
  binds every stated price; an optional `approval_verifier` callable can veto
  the ref). Anywhere else it is `S78-UNAPPROVED-PRICE`.
- Selection output is `selection.json`: intent only, never payment evidence.

## Native ids and the 78 to 79 handoff

- Outside `test_only`, `emit_binding_plan.py` refuses a null or blank native
  product/price id on the catalog or on any target (`S78-BINDING-INCOMPLETE`);
  `build_selection` refuses it as `S78-MISSING-NATIVE-MAPPING`. The ids are
  created or read back by Skill 06's installer, under its own scoped approval,
  and written back into `launch.json`; this skill only consumes them.
- The realised route is `per_offer_instances` (owner decision,
  `83-black-friday-launcher/DECISIONS-PENDING.md`, section "Ceiling"): for
  `multiple_options` Skill 83 emits ONE Skill 79 `combined_single_offer` order
  form per (main offer, price choice), each with its own page id, and this
  skill's `emit_binding_plan.py` maps one native target to each instance.
  `selection_ref` is always null. Skill 79 is NOT called in a post-selection
  mode on this route.
- Fixture-only, not part of the done claim: `79-signature-order-form/scripts/
  selection_flow.py::selection_from_intent` (the adapter from a `selection.json`
  intent to Skill 79's `Selection`: `amount_minor_snapshot` becomes
  `amount_minor`; `revision` feeds both the launch and the offer revision; it
  refuses an intent with no native price id), the session bridge and the
  `post-selection-checkout.html` draft. No wired route calls them; see
  `runtime-manifest.json` `done_claim.not_counted`.
- The fixture adapter above also carries `billing_type` and the schedule rows `{sequence, due,
  amount_minor}` (the checkout schema's row shape) so the checkout can show them. Time crosses the
  seam as one shape: the session store keeps epoch seconds for its TTL but hands Skill 79 a
  timezone-aware ISO-8601 `expires_at` (`selection_session.to_iso`); Skill 79 compares instants and
  refuses an integer, naive or junk time by name.

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

## Design direction (Skill 45)

Design direction = Skill 71 structure + Skill 45 card/rules via `design_prose.py`. The order page's images follow the same direction. The page's sections are Skill 71's; its look comes from the client's chosen Skill 45 style card (a registered `FN-` id, optional) and the design library's funnel page rules, composed into `design-prose.json` by `shared-utils/signature_launch/design_prose.py` and passed to Skill 71 as `--design-prose`. The file records the sha256 of every Skill 45 file it read, so a hand-typed file, an edited one, or one built against rules that have since changed is refused (`design_prose.check_design_prose`). Skill 45 is only read, never written.

## Scripts (stdlib only, fail-closed)

- `scripts/build_selection_plan.py` - validate a launch catalog and emit the
  normalized selection plan (matrix + UI model), or decline single-offer use.
- `scripts/validate_selection_content.py` - claim and specificity checks on
  authored selection copy against the approved catalog.
- `scripts/validate_selection_binding.py` - check that a selection.json intent
  preserves the approved native product/price mapping for Skill 79, rejects
  query-string price authority, cross-tenant IDs, and stale revisions.
  `validate_plan()` runs the same check over every mapping of an emitted
  binding plan; `emit_binding_plan.py` calls it on each plan it returns, so no
  plan the checkout-time validator would refuse is ever emitted.
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

## Python dependency: jsonschema (operator note, never for the client)

`verify.sh` (its schema validation step) imports `jsonschema`. On a Homebrew or Debian Python (externally managed, PEP 668) pip refuses a plain or
`--user` install, so the package lives in the shared pydeps folder `<root>/pydeps/py<major>.<minor>/`
(`$OC_PYDEPS_DIR` as-is, else `$OPENCLAW_ROOT`, else `/data/.openclaw` when it exists, else `$HOME/.openclaw`;
`$HOME/.claude/pydeps/py<X.Y>/` is also looked up), installed with `pip install --target`. The file puts that folder on
`sys.path` itself before it imports, so plain `python3` works: no venv, no activation step. Never use
`--break-system-packages`, never create a venv, never tell the client. If the import fails, check with
`bash update-skills.sh --check` and run the one sanctioned fix from `83-black-friday-launcher`:
`python3 -m launcher_core.cli dependencies --install`.
