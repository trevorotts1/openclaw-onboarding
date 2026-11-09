# Worked-example fixtures

Two owner-specified shapes, kept separate and never merged
(`06-black-friday-launcher/REQUIREMENTS.md` §2; takeover doc lines 50-55).

| Fixture | Shape | Status |
|---|---|---|
| `elevation/intake.json` | 12-section no-price signature page → **separate** three-level product selection → native order form | routes, assembles and passes the completeness checks offline |
| `seven-figure-preneur/intake.json` | three levels **folded into** the signature page → native order form, **no** product selection page | routes and assembles (`folded_levels`) with three accepted per-offer checkout instances; the completeness checks pass offline |

`run_fixtures.py` builds both packages from the real S49 compiler, the real
adapter map, the launcher's package completeness checks and the Skill 79
checkout contract. The Council planning step is stubbed so no live session is
started.

## The 7FigurePreneur shape

The three folded levels are three **distinct main offers** and stay that way.
The settled `folded_levels` journey mode compiles `landing → checkout` with no
`product_selection` node and no `selection_validated` edge, in both the
launcher's route layer and the real S49 `compile_launch_route.py`. The example
is not relabelled `single_simple`, does not gain a selection page, and keeps its
three separate prices.

**One order form per level, not blocked.** The Skill 79 contract's
`combined_single_offer` mode is realised once per main price choice by
`launcher_core/checkout_instances.py`, so this shape records
`checkout_mode_state: resolved` with `realisation: per_offer_instances` and
`checkout.delivery_blocked: false`. Each of the three levels carries its own page
id, its own bump applicability and its own S79 validator verdict, and the real
S78 `emit_binding_plan` maps one native target to each instance. The fixture
runner asserts the three accepted instances, not a block. Facts the launch does
not supply are still never defaulted: a missing native id, terms, consent,
capability/fulfillment reference or bump component fact is recorded as a rejected
instance (`AF-LAUNCH-CHECKOUT-REJECTED`).

The fixture also carries one offer relationship (`BUMP.included_in =
["MAIN-B","MAIN-C"]`) so the cross-sale surface on the thank-you page is
exercised. No cross-sale teaching content exists and none is invented: the
record says `teaching.state = "pending"`.

## No account declaration

Neither fixture carries an account-entitlement attestation, because the client is never asked to
declare one. Both build with `entitlement.state = "unknown"` and nothing blocks on it.

## Provenance — no invented prices or level contents

Every amount is copied from a repository fixture that already marks itself
TEST ONLY. Nothing here is a product price.

- Elevation main offers `9700 / 19700 / 49700` USD: MAIN-ESS / MAIN-PRO /
  MAIN-ELITE in `78-signature-product-selection/fixtures/golden-three-option/launch.json`
  (`source_kind: test_fixture`, `test_only: true`; cumulative deliverables).
- Bump `2700`, U1 `6700`, D1 `3700`, U2 `4700` USD: the BUMP / U1 / D1 / U2
  offers in `49-signature-funnel/scripts/fixtures/launch-example.json`.
- 7FigurePreneur main offers `9700 / 19700 / 29700` USD: MAIN-A / MAIN-B /
  MAIN-C in the same S49 fixture. Names are TEST ONLY level labels; **no level
  contents are claimed or supplied**.
- `copy_profile: "standard"` is one of the two profiles the real S71 launcher
  maps (`71-blackceo-signature-page/scripts/launch_context.py:578`); Elevation
  is the 12-section standard page. `long-form` is the other.
- `brand.hash` and `approval.hash` are SHA-256 of the literal strings
  `TEST-ONLY-BRAND` and `TEST-ONLY-APPROVAL`. They are fixture identities, not
  hashes of any real asset or approval.

## What the fixture run proves

For each shape:

1. the intake is valid and fail-closed, with a qualified entitlement attestation;
2. the route graph is byte-for-byte the real S49 compiler's graph;
3. every route invariant holds (verified guards, U1/D1/U2 law, no decline edge
   at checkout, one canonical U2, no bump node);
4. every enabled page has an independent build unit with
   `buyer_action_required: false`;
5. checkout is the native S79 surface, not a dispatch adapter, and its mapping
   is bound to the real S79 contract;
6. the Council planning step is recorded and cannot block;
7. the cross-sale surface rides on the thank-you page with teaching pending;
8. a package assembled from those build units is self-contained and passes every completeness
   check for BOTH shapes. 7FigurePreneur carries three accepted `combined_single_offer` checkout
   instances, one per folded level, and its manifest records `delivery_blocked: false`.

Plus, for 7FigurePreneur: no `product_selection` page exists in the route, and a
not-ready Council result neither fails the build nor changes the compiled graph.

The packaged artifact per page is that page's **build plan**, not page copy.
Page bytes remain the assigned skill's output; producing them needs the paid
page pipeline and is outside this offline task.

## Run

```bash
TMPDIR=<scratch-dir> python3 fixtures/run_fixtures.py
```

Use a plain `python3` that can import `jsonschema` (`requirements.txt`); `python3 -I` hides user
site-packages and makes the Skill 79 validator report unavailable, which is the failure `verify.sh` removed.

The fixtures hold intakes only. To assemble one through the CLI, give `assemble` the page results from
`dispatch` and one of `--launch-plan` or `--page-only`:

```bash
python3 -m launcher_core.cli assemble --intake fixtures/elevation/intake.json \
    --pieces <run-dir>/pieces --out <package-dir> --page-only
```

Outputs land in a fresh directory under `TMPDIR`; the worktree stays clean.
