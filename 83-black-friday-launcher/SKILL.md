---
name: black-friday-launcher
description: >
  Composes the Black Friday launch from the separate page skills through the
  signature launch contracts. Validates the launch intake fail-closed behind an
  entitlement attestation gate, compiles the doc 02 route graph (including the
  folded_levels shape), maps the native Skill 79 checkout contract, records
  Council advice in planning, produces the 7FigurePreneur shape without a
  product-selection page, dispatches page requests through Skill 49, and
  assembles the delivered package with a manifest, a receipt and executable
  completeness checks. Enabled in 999: installed from CONTROL/bundled-skills.txt,
  with a dependency preflight that verifies every dependency before it reports
  ready. Offline core only: no live payment, no entitlement creation, no paid
  model session.
version: 0.2.3
priority: HIGH
---

# Black Friday Launcher (skill 83)

The number **83 is assigned** (LAUNCH-04, 2026-10-18; the availability evidence
is recorded in `registration.json:number_assignment`). It lives in exactly one
constant, `launcher_core/constants.py:SKILL_NUMBER`; every other reference
derives `SKILL_DIR_NAME` from it, so a rename is one edit.

Dependency trees are resolved by **slug**, not by number:
`launcher_core.constants.resolve_skill_dir` accepts `<slug>` (a 999 package) or
`<number>-<slug>` (this repository), prefers the numeric form when both exist,
and fails closed with `SkillResolutionError` naming the slug. No consumer spells
a numbered directory, so the same code runs in both layouts.

## What it does

1. **Intake** (`launcher_core/intake.py`). Validates a launch intake. Required
   fields are only those the pages genuinely cannot be built without. Nothing
   commercial defaults: a missing price is an error, never zero and never free;
   a level is supplied or explicitly unknown. The entitlement attestation is
   verified by `launcher_core/entitlement.py` against the declaration the skill
   carries, so an unknown entitlement state never builds.
2. **Route compilation** (`launcher_core/route.py`). Emits the route graph from
   doc 02 section 4 (`contracts/49-signature-funnel/schema/route-graph.schema.json`):
   `single_simple` skips Product Selection; `multiple_options` inserts it;
   `folded_levels` folds N >= 2 distinct main offers into the signature page and
   goes straight to checkout with no selection page; U1/D1/U2 branch on
   accept/decline; a pending or failed payment grants no access.
3. **Checkout mapping** (`launcher_core/checkout.py`). Binds the real Skill 79
   order-form contract to the launch's verified facts and calls the S79
   validator as a live probe. Checkout is the native Convert and Flow form
   installed by Skill 06 and is never a dispatch adapter.
4. **Council planning** (`launcher_core/council.py`). Invokes Skill 77 through
   its documented offline entry point, records the result in the launch record
   and the receipt, and continues whatever it says: advice never blocks and is
   never permission.
5. **Package and receipt assembly** (`launcher_core/package.py`). Every enabled
   route node must arrive with a valid shared page-result. Writes
   `package-manifest.json`, `receipt.json`, `council-advice.json` and
   `checkout-mapping.json`. Receipt evidence is Skill 49's own store, read,
   never duplicated.
6. **Completeness checks** (`launcher_core/checks.py`). Fail when a required
   piece is missing or blocked, when an artifact is absent or its hash drifted,
   when a bound path does not resolve or is placeholder-shaped, when a price,
   level or entitlement was defaulted, when the entitlement is unattested, when
   Council advice is recorded as blocking, or when checkout is not the native
   contract.
7. **999 dependency package** (`launcher_core/dependencies.py`). Lists every
   dependency and reports which are present and which are missing. The skill is
   enabled in 999: `registration.json` records `enablement.enabled_in_999: true`,
   the 999 installers link it from `CONTROL/bundled-skills.txt` and install
   `requirements.txt` (jsonschema) on macOS and Windows, and the preflight
   reports `enabled_in_999=True` only while every required dependency is present.

## Entry

```
python3 -m launcher_core.cli route        --intake intake.json
python3 -m launcher_core.cli assemble     --intake intake.json --pieces <dir> --out <run-dir>
python3 -m launcher_core.cli check        --manifest <run-dir>/package-manifest.json --root <run-dir>
python3 -m launcher_core.cli seams
python3 -m launcher_core.cli dependencies [--root <repo>]
```

Run the shipped checks with `bash verify.sh` (exit 0 pass, non-zero fail).

## Worked examples

`fixtures/` carries the two owner-specified shapes, never merged. Elevation
(no-price 12-section page -> separate three-level selection -> native order
form) builds green offline. 7FigurePreneur (three levels folded into the
signature page -> native order form, no selection page) now builds green too
through the settled `folded_levels` mode, with its three distinct offers intact.
`python3 -I fixtures/run_fixtures.py` proves both.

## What this build does not do

- It does not build pages. It composes whatever page-result Skills 71, 78, 79,
  80, 81 and 82 return.
- It does not charge, create an entitlement or call a billing API.
- It does not start a live Council session.
- It does not choose a distribution target (`registration.json:distribution`
  stays an open decision; enabling in 999 does not depend on it).
- It does not invent cross-sale teaching content: the surface is present, the
  teaching is marked pending.
- It ships no `/path/to` binding: `check` fails any placeholder-shaped path.

## Decisions

`DECISIONS-PENDING.md` records the five decisions implemented here and the two
seams still open (`distribution_run_target`, `cross_sales_teaching_source`).
