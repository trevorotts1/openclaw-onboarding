# Decisions — what is decided and what is still open

`launcher_core/constants.py:DECIDED` is the machine-readable record of the
owner decisions implemented here; `SEAMS` is what remains open. No open seam
carries a value anywhere in this build.

---

## Decided

### 1. There is no account-entitlement question and no admission gate

**Owner order (2026-11-08).** A client must never be asked to self-classify their account before a page
can be built. The question, the carried rules, the read-back and the build refusal are all removed.

**Code.** `launcher_core/entitlement.py` and `entitlement-declaration.json` are deleted. The intake no
longer requires or verifies anything of the kind: the normalized record carries
`entitlement = {"state": "unknown", "basis": null, "qualifies": null, "requires_purchase": false,
"billing": "none"}`, and nothing consumes it as a permission. `checks.py` no longer refuses a package for
want of an attestation. The shared question bank no longer offers the question and
`shared-utils/client_intake/launcher_intake.py` no longer requires an answer for it.

**Ceiling.** No entitlement is created, inferred or stored, and no billing API is called. A legacy intake
that still carries an `entitlement_attestation` key keeps validating; the value is ignored, never read.
Spend caps, approval refs and QC gates are untouched.

### 2. Council advice is included in launch planning

**Owner decision.** Council advice is INCLUDED. A not-ready result is recorded
and the build continues. It is advice, never permission.

**Code.** `launcher_core/council.py:planning_step` invokes Skill 77 through its
documented offline entry point (`77-council-of-wise-elders/scripts/doctor.mjs`,
which performs no network and no writes) and records the result in the launch
record (`route.launch_record`), the manifest and the receipt. `blocks_build` and
`is_permission` are literal `false`, so no caller can turn advice into a gate.
Tests inject a stub runner; no live paid session is required or started.

**Honest label (CON-16).** Without a live session the step is a package check,
not advice, and every record says so: `council_session_held: false`,
`advice_state: pending_live_session`, and a `client_summary` reading "No Council
advice was obtained ... This is not a Council review." The status value
`ready_no_advice` means only "the Skill 77 package is installed and intact"; the
verify log's `DOCTOR: PASS` is that package check and nothing more
(`doctor.mjs` is covered by Skill 77's manifest hash, so it is left unchanged). Callers that need real
advice pass `council_required=True` to `planning_step`, which refuses with
`AF-LAUNCH-COUNCIL-REQUIRED` unless a session returned advice.

**Ceiling.** The default runner reports readiness only. Producing actual advice
needs the owner's live Council path (recommended: submit the launch summary
through the Command Center council API, advice staying non-blocking); until then
the record says `council_session_held: false`.

### 2b. A second downsell (`downsell_2`) is refused by name

**Decision.** The interview can name a second downsell but neither the intake nor
the Skill 49 record has a slot with its own offer and price, so a `downsell_2`
page would be built with no price fact. This release refuses it:
`constants.UNSUPPORTED_OFFER_ROLES["downsell_2"]` is "a second downsell is not
supported in this release". A priced slot (its own offer, price and hash entry)
is the alternative and is not built here.

### 3. Native Convert and Flow checkout mapping

**Owner decision.** Use the native checkout mappings. Checkout stays the native
form installed by Skill 06 and is still NOT a dispatch adapter.

**Code.** `launcher_core/checkout.py` reads
`79-signature-order-form/references/checkout.schema.json`, maps the launch's own
verified facts onto the contract's field names, and calls the real
`79-signature-order-form/scripts/validate_checkout.py:validate_request` as a
live binding probe. `routes/adapters.py:NATIVE_SURFACES["checkout"]` carries the
contract, the validator and `dispatch_adapter: False`. `adapter_for("checkout")`
still refuses. The per-offer realisation lives in
`launcher_core/checkout_instances.py`: `build()` emits ONE S79
`combined_single_offer` request per (main offer, price choice), and the real S78
`emit_binding_plan` maps one native target to each instance.

**Ceiling.** `multiple_options` and `folded_levels` share one realisation,
`per_offer_instances`: each main price choice gets its own native
`combined_single_offer` order form with its own page id, its own bump
applicability and its own S79 validator verdict, so `checkout_mode_state` is
`resolved` rather than a contract gap. Only the page in front of the checkout
differs (the selection page or the folded signature page), and `selection_ref`
is always null. Missing native ids, terms, consent, capability/fulfillment
references or bump component facts are recorded as a rejected instance
(`AF-LAUNCH-CHECKOUT-REJECTED`), never defaulted. Fields a launch does not
supply stay in `unknown`.

### 4. Verified offer facts only

**Owner decision.** Reuse verified offer facts; never invent commercial
defaults. Anything not supplied stays explicitly unknown, never zero and never a
guessed price.

**Code.** `launcher_core/intake.py`: a price must be a positive integer in minor
units with a real currency; a level must be `{"state": "supplied"}` with named
deliverables or `{"state": "unknown"}`; `assert_no_commercial_defaults` refuses
any commercial provenance that is a default. `launcher_core/checks.py`
re-verifies the recorded `offer_facts` at `check` time
(`AF-LAUNCH-OFFER-DEFAULTED`, `AF-LAUNCH-OFFER-PRICE`).

**Ceiling.** Only the four operational defaults in `PERMITTED_DEFAULTS` exist
(`test_only`, `allowed_write_target`, `locale`, `automation_execution`), and
each is recorded in `provenance` as `default: <reason>`.

### 5. `folded_levels` journey mode

**Owner decision (settled shape).** The 7FigurePreneur shape folds three levels
into the signature page and goes straight to the native order form, with no
selection page.

**Code.** `launcher_core/constants.py:JOURNEY_MODES` and
`49-signature-funnel/scripts/compile_launch_route.py:expected_roles` both accept
`folded_levels`: `landing -> checkout` with no `product_selection` node and no
`selection_validated` edge. `route_law` derives the same edge set.
`single_simple`, `multiple_options` and `free_entry` are unchanged, and the
Elevation shape still compiles exactly as it did.

**Ceiling.** The mode does not decide the page copy in front of the checkout.
The order form itself is decided: one native `combined_single_offer` instance
per main price choice (§3), so each of the three levels reaches its own order
form with no selection page.

---

## Still open — owner decisions

Neither seam carries a value anywhere in this build: `launcher_core/constants.py:SEAMS` names both, and no
code path invents a target or teaching content. Each is an owner decision, not a builder gap.

### A. `distribution_run_target`

**Owner decision (open).** Installed into the customer's own OpenClaw/999 environment, or run inside
BlackCEO's environment. Only the owner can pick.

**Blocks:** the distribution step — installing the build into a named environment — and any claim that a
run happened in a named environment. `assemble` builds the local package either way; that is listed under
**Does not block** below.
`registration.json:distribution` stays `status: open_decision` with `chosen_target: null` until the owner
names one; no code may fill it in.

**Does not block:** the build, `assemble`, `check`, the shipped tests, or enablement in 999 —
`registration.json:enablement.enabled_in_999` is already true and `launcher_core/dependencies.py` derives
`enabled_in_999` from that record plus the dependency check, never from this seam.

**Code seam:** `registration.json:distribution` (`status: open_decision`,
`chosen_target: null`) and `SKILL.md` entry. The Launcher is enabled in 999 regardless of this decision
(`registration.json:enablement.enabled_in_999: true`); `launcher_core/dependencies.py`
reports `enabled_in_999` from that record plus the dependency check.

**Ceiling:** a renamed or relocated install layout is detected and the package
fails closed instead of guessing a path.

### B. `cross_sales_teaching_source`

**Owner decision (open).** Which cross-sale teaching content ships. The inclusion itself is settled: the
relationship surface is present. The owner supplies the material.

**Blocks:** any delivered teaching content. `checks.py` refuses a package whose
`cross_sales.teaching.state` is anything but `"pending"` (`AF-LAUNCH-CROSS-SALES`), so a run cannot claim
teaching copy it does not have.

**Does not block:** building and delivering the `thank_you` page. The offer relationships
(`complements` / `included_in` / `requires`) are recorded and surfaced there with the teaching state
`pending`.

**Code seam:** `launcher_core/route.py:launch_record` records the offer
relationships (`complements` / `included_in` / `requires`) and marks
`cross_sales.teaching.state` as `"pending"`. `routes/build_time.py` surfaces the
same record on the `thank_you` page. `checks.py` refuses a package that claims a
teaching state other than `pending`, or that turns cross-sales into a route
node.

**Ceiling:** no teaching content, no page and no offer is invented. When the
owner supplies the material, the teaching state changes in one place.

## Open question (not a seam; no build is blocked on it)

**Image vision evidence, one canonical shape.** SOP-GIP-02 asks for a non-null `vision_api_response` per image in
`qc/vision_qc_log.json`; Skill 71's Review Receipt v2 carries the scores and models. `check` now demands both
(`AF-G-VISION` for the log, `AF-LAUNCH-IMAGE-QC` for the receipt). Question for the owner: should one of the two
shapes become the only one, with the other derived from it?

## Carried to owners (after this unit merges)

The Council label and the downsell_2 refusal text land here as constants and tests. These edits sit in
files other units own, so they are carried to those owners. The receipt.json label, the by-name intake
refusal and the SKILL.md wording land with them once this unit has merged. No advice is obtained from a
live Council session until the owner supplies the live path.

- C1 U-launcher-core-01, `launcher_core/package.py`: receipt council block gains `council_session_held` (is True) and `client_summary` (default `COUNCIL_NO_ADVICE_SUMMARY`).
- C2 U-launcher-core-01, `tests/test_assemble_binding.py`: receipt.json asserts both keys (fresh and legacy council dict).
- C3 U-products-01, `launcher_core/intake.py`: refuse a role in `UNSUPPORTED_OFFER_ROLES` by name before the generic `OFFER_ROLES` check.
- C4 U-products-01, `tests/test_intake_validation.py`: a priced downsell_2 offer is refused with "a second downsell is not supported in this release".
- C5 U-products-05, `shared-utils/client_intake/launcher_intake.py`: an answers-file downsell_2 (not "none") is refused with the same text.
- C6 U-products-05, `shared-utils/client_intake/tests/test_launcher_intake.py`: refusal and "none" pass-through tests.
- C7 U-launcher-core-07, `SKILL.md`: description line 8 and step 4 say package check, no advice without a live session.
