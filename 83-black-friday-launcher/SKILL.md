---
name: black-friday-launcher
description: >
  Composes the Black Friday launch from the separate page skills through the
  signature launch contracts. Validates the launch intake fail-closed behind an
  entitlement attestation gate, compiles the doc 02 route graph (including the
  folded_levels shape), maps the native Skill 79 checkout contract, runs a
  Council planning step (a Skill 77 package check unless a live Council session returns advice), produces the 7FigurePreneur shape without a
  product-selection page, dispatches page requests through Skill 49, and
  assembles the delivered package with a manifest, a receipt and executable
  completeness checks. Enabled in 999: installed from CONTROL/bundled-skills.txt,
  with a dependency preflight that verifies every dependency before it reports
  ready. Offline core only: no live payment, no entitlement creation, no paid
  model session.
version: 0.2.13
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
   validator as a live probe. Checkout is the native Convert and Flow form and is never a dispatch adapter.
   Skill 06 cannot install that form, an order bump or a one-click step today (S06-02), so a checkout
   design is not an installed checkout; see the tracked items below.
4. **Council planning** (`launcher_core/council.py`). Invokes Skill 77 through
   its documented offline entry point, records the result in the launch record
   and the receipt, and continues whatever it says: advice never blocks and is
   never permission. Without a live Council session this is a package check only: the record and receipt carry council_session_held false and a client summary saying no Council advice was obtained; council_required=True refuses without a session.
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

## Read order

Read in this order. Each step names the file, so nothing here depends on guessing a path.

1. This file, then `DISPATCH.md` (dispatch, designs, pictures and delivery in full) and
   `DECISIONS-PENDING.md` (what is decided, what is open).
2. For the pages: `49-signature-funnel` (launch record, gates, dispatch), then the page skills 71, 78, 79,
   80, 81 and 82 that Skill 49 calls.
3. For the launch automations (emails, texts, reminders, workflows): `50-email-engine` writes the DRAFT-ONLY
   build plans, then `44-convert-and-flow-operator/automation-templates/launch-c/plan_reader.py` reads them,
   and `44-convert-and-flow-operator/tools/siglaunch/` is the pipeline that builds and receipts them. See
   "Launch mode" below. Skill 83 depends on Skill 44 and Skill 50 for this reason.
   The machine-readable record of that dependency is `skill.json` and `registration.json` `depends_on`
   plus the `launcher_core/dependencies.json` preflight.

## Entry

Run from this skill's folder. The interpreter needs `jsonschema` (see `requirements.txt`); do not use
`python3 -I`, which hides it.

```
python3 -m launcher_core.cli route        --intake intake.json
python3 -m launcher_core.cli plan         --plan <launch-plan.json> [--deliveries <dir>]
python3 -m launcher_core.cli dispatch     --intake intake.json --out <run-dir> \
                 --approval <approval.json> --client <client-ref> --worker <worker-ref> \
                 [--adapters <adapters.json>] [--adapter-inputs <inputs.json>] \
                 [--parallel N] [--scoped-approvals <array.json>] \
                 [--landing-pages landing,sales] [--extra-page downsell_2]
python3 -m launcher_core.cli questions
python3 -m launcher_core.cli assemble     --intake intake.json --pieces <run-dir>/pieces --out <package-dir> \
                 (--launch-plan <launch-plan.json> [--deliveries <deliveries.json>] | --page-only) \
                 [--allow-no-designs]
python3 -m launcher_core.cli check        --manifest <package-dir>/package-manifest.json --root <package-dir>
python3 -m launcher_core.cli seams
python3 -m launcher_core.cli dependencies [--root <repo>]
```

`plan` validates a shared launch plan's calendar and completeness. `dispatch`
turns an intake into a Skill 49 launch record and builds every page, recording
the approver and the builder as two distinct identities. `questions` prints the
picture questions a client is asked, as data.

`assemble` needs exactly one of `--launch-plan` or `--page-only`; with neither it fails
(`AF-LAUNCH-PLAN-REQUIRED`). `--page-only` labels the package page-only: it carries no Black Friday calendar
and no planned email, text or automation. `--allow-no-designs` is for plan-only packages and is recorded as
`designs_required: false`.

Run the shipped checks with `bash verify.sh` (exit 0 pass, non-zero fail).

## Worked examples

`fixtures/` carries the two owner-specified shapes, never merged; they hold intakes only, so the page results
come from `dispatch` (or from `fixtures/run_fixtures.py`, which builds build-plan stand-ins).

```
python3 -m launcher_core.cli assemble --intake fixtures/elevation/intake.json \
    --pieces <run-dir>/pieces --out <package-dir> --page-only
```

- **Elevation** (no-price 12-section page -> separate three-level selection -> native order form) routes,
  assembles and passes the fixture runner's completeness checks offline.
- **7FigurePreneur** (three levels folded into the signature page -> native order form, no selection page)
  routes and assembles through the settled `folded_levels` mode with its three distinct offers intact, but it
  is **delivery-blocked**: the Skill 79 contract names no checkout mode for `folded_levels`
  (`checkout_mode_state: contract_gap`, `AF-LAUNCH-CHECKOUT-MODE`), so `check` fails the package until
  Skill 79 names a mode. The fixture runner asserts that block; it is not a green build.

`python3 fixtures/run_fixtures.py` proves both. These packages hold build plans, not page bytes.

## Launch mode (Skill 49/83)

For a request such as "set up the Black Friday automations", the launch path is a pipeline of four named
steps, all DRAFT-ONLY (nothing is sent and nothing goes live):

1. **Reader.** `python3 44-convert-and-flow-operator/automation-templates/launch-c/plan_reader.py
   --launch-plan <plan.json> --build-plan <skill-50-build-plan.json> --out automation-builds.json` reads the
   launch plan and the Skill 50 build plans into one automation-build document. A missing page URL, text set,
   build plan or an email-count mismatch blocks the build.
2. **Build command.** The `44-convert-and-flow-operator/tools/siglaunch/` receiver validates the request and
   drives the governed build through Skill 44's engine, then reads the saved graph back.
3. **QC.** `44-convert-and-flow-operator/qc-built-workflow.sh <workflow-id> --json` checks the built workflow;
   a build that fails QC is not delivered.
4. **Receipt.** The `siglaunch` receiver issues the receipt for the build. Skill 83 reads delivery results
   through `assemble --launch-plan <plan> --deliveries <deliveries.json>` and requires every planned email,
   text and automation to be delivered before the package counts as a full launch.

Skill 83 builds pages; it does not build workflows itself. See Skill 44's own SKILL.md and INSTRUCTIONS.md for
the same four steps from the other side.

## Pictures, spend and design approvals

Skill 83 asks the client the picture questions (`python3 -m launcher_core.cli questions`), records the answers
in the intake's `image_plan`, and carries one shared image-inputs file to every page, so no page is drawn in a
different style, for a different owner or under a different spend limit. Never build an `image_plan` from
guesswork and never skip the picture step. Full rules are in `DISPATCH.md`.

**`image_plan` fields** (`launcher_core/image_plan.py`): `design_style` (A Block, B Circle or C Hybrid),
`design_style_source`, `brand_file` and `brand_owner` (both required, never defaulted), `image_cap`,
`image_provider` (only `kie` can draw today; `agnes` and `other_explicit` are refused by name),
`paid_render_approval_ref`, `design_prose_ref` and `visual_bible_ref` (creative direction). An unknown field is
refused.

**Never-default spend rule.** Money is never defaulted and never inferred. A practice run (the intake's top-level `test_only` flag; it is not an `image_plan` field) draws
placeholders and costs nothing. A paid run needs the client's own ceiling (`image_cap`) AND a recorded
paid approval record (`paid_render_approval_ref`), or it stops before anything is sent
(`AF-LAUNCH-IMAGE-PLAN-CAP`, `AF-LAUNCH-IMAGE-PLAN-APPROVAL`). Design style and provider may be defaulted but
are always flagged `to_confirm`. The decided replacement is a money cap (`cap_minor` plus currency, with a
per-image price table) backed by a verified `paid_asset_budget` approval record. It was decided 2026-11-02
(ENF-05, IMG-03, IMG-05) and is not yet in the code; the never-default rule is the same either way.

**Design approval gates.** (1) The plan approval record passed as `--approval` is carried to Skill 49's gate
unchanged; a worker cannot approve its own plan, and a plan changed after approval is refused. (2) Skill 71's
`gate:intake_design_style` closes only on a recorded style (`client_choice` or `recommended_accepted`); a
defaulted style stays a proposal until the client confirms it. (3) The design board and the final mockups
are recorded `awaiting_client_approval` until the client approves them.

**Final mockups.** A delivered launch holds, for every page, desktop and mobile wireframes and mockups,
review PDFs and an overview board (AF-LAUNCH-PAGE-DESIGNS), with real pictures: placeholder pictures fail a
package that is not `test_only`. The decided Black Friday deliverable is finished pages with real images
(final mockups closed on the paid run), with layout proofs as an explicit first approval checkpoint
(IMG-01); a stub package is labeled "images only, render pending" and is never a finished delivery.

## Tracked items (not built here)

Each item is tracked, not forgotten. Where Skill 83 does not do something, the owner and the place it is
tracked are named.

| Not done by Skill 83 | Tracked in |
| --- | --- |
| Build pages (it composes the page-results Skills 71, 78, 79, 80, 81 and 82 return) | permanent boundary |
| Charge, create an entitlement or call a billing API | permanent boundary; membership and purchase truth is PRD-12 |
| Start a live Council session; Council advice is a readiness record until then | CON-16 |
| Install the native order form, bump and one-click steps (Skill 06 has no such step) | S06-02, CHK-19 |
| Name a checkout mode for `folded_levels` (delivery stays blocked) | Skill 79 contract gap, `AF-LAUNCH-CHECKOUT-MODE` |
| Choose a distribution target | open seam `distribution_run_target` in `DECISIONS-PENDING.md` |
| Cross-sale teaching content (the surface is present, the teaching is marked pending) | open seam `cross_sales_teaching_source` |
| Build automations or workflows | Skill 44 and Skill 50 (see "Launch mode"); S44-25 |
| Ship a `/path/to` binding (`check` fails any placeholder-shaped path) | enforced by `check` |

## Decisions

`DECISIONS-PENDING.md` records the five decisions implemented here and the two
seams still open (`distribution_run_target`, `cross_sales_teaching_source`).
