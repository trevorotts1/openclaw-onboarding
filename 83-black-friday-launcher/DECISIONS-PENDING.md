# Decisions — what is decided and what is still open

`launcher_core/constants.py:DECIDED` is the machine-readable record of the
owner decisions implemented here; `SEAMS` is what remains open. No open seam
carries a value anywhere in this build.

---

## Decided

### 1. Entitlement: a declaration the skill carries plus a fail-closed attestation gate

**Owner decision.** Brand Management membership qualifies WITHOUT a new $497
purchase. Everyone else buys at $497. School of AI membership alone does not
qualify. ZHC qualifies only together with Brand Management.

**Code.** `entitlement-declaration.json` carries the rules.
`launcher_core/entitlement.py` verifies that declaration (including that the
rules were not silently flipped), then verifies the run's attestation. A
missing, unknown or unqualified basis fails with a named code before any page
is planned: `AF-LAUNCH-ENTITLEMENT-UNKNOWN`, `-NOT-QUALIFIED`,
`-PURCHASE-UNVERIFIED`, `-DECLARATION`, `-PRICE-CONTRADICTION`.

**Ceiling.** Nothing charges, creates an entitlement or calls a billing API;
`no_billing`, `creates_entitlements` and `calls_billing_api` are asserted false
in the declaration. A membership attestation carries no purchase reference — a
membership is not a purchase event — and the gate rejects one that does.

### 2. Council advice is included in launch planning

**Owner decision.** Council advice is INCLUDED. A not-ready result is recorded
and the build continues. It is advice, never permission.

**Code.** `launcher_core/council.py:planning_step` invokes Skill 77 through its
documented offline entry point (`77-council-of-wise-elders/scripts/doctor.mjs`,
which performs no network and no writes) and records the result in the launch
record (`route.launch_record`), the manifest and the receipt. `blocks_build` and
`is_permission` are literal `false`, so no caller can turn advice into a gate.
Tests inject a stub runner; no live paid session is required or started.

**Ceiling.** The default runner reports readiness only. Producing actual advice
needs the owner's live Council path; until then the record says
`advice_state: pending_live_session`.

### 3. Native Convert and Flow checkout mapping

**Owner decision.** Use the native checkout mappings. Checkout stays the native
form installed by Skill 06 and is still NOT a dispatch adapter.

**Code.** `launcher_core/checkout.py` reads
`79-signature-order-form/references/checkout.schema.json`, maps the launch's own
verified facts onto the contract's field names, and calls the real
`79-signature-order-form/scripts/validate_checkout.py:validate_request` as a
live binding probe. `routes/adapters.py:NATIVE_SURFACES["checkout"]` carries the
contract, the validator and `dispatch_adapter: False`. `adapter_for("checkout")`
still refuses.

**Ceiling.** `folded_levels` has three main offers and no selection page; the
S79 contract's two modes (`combined_single_offer`, `post_selection`) express
neither, so that launch shape records `checkout_mode_state: contract_gap`
instead of an invented mode. Fields a launch does not supply stay in `unknown`.

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

**Ceiling.** The mode does not decide how the order form presents three levels;
that is recorded in the checkout mapping as an open contract gap, not guessed.

---

## Still open

### A. `distribution_run_target`

**Decision:** installed into the customer's own OpenClaw/999 environment, or run
inside BlackCEO's environment.

**Code seam:** `registration.json:distribution` (`status: open_decision`,
`chosen_target: null`) and `SKILL.md` entry. The Launcher is enabled in 999 regardless of this decision
(`registration.json:enablement.enabled_in_999: true`); `launcher_core/dependencies.py`
reports `enabled_in_999` from that record plus the dependency check.

**Ceiling:** a renamed or relocated install layout is detected and the package
fails closed instead of guessing a path.

### B. `cross_sales_teaching_source`

**Decision:** which cross-sale teaching content ships. The inclusion itself is
settled: the relationship surface is present.

**Code seam:** `launcher_core/route.py:launch_record` records the offer
relationships (`complements` / `included_in` / `requires`) and marks
`cross_sales.teaching.state` as `"pending"`. `routes/build_time.py` surfaces the
same record on the `thank_you` page. `checks.py` refuses a package that claims a
teaching state other than `pending`, or that turns cross-sales into a route
node.

**Ceiling:** no teaching content, no page and no offer is invented. When the
owner supplies the material, the teaching state changes in one place.
