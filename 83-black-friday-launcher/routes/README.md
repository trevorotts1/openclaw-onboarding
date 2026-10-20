# Launcher routes (`83-black-friday-launcher/routes/`)

LAUNCH-02 route-invariant and adapter-wiring layer. No `SKILL.md`, intake,
package or receipt files live here; core-branch files are untouched.

## Modules

| File | Job |
|---|---|
| `substrate.py` | Loads the real Skill 49/71/78/80/81/82 modules from their real tree paths. Nothing is copied. |
| `build_time.py` | Build-time page generation. Takes only the approved launch record; no purchase/event/navigation input. |
| `route_law.py` | Canonical verified-payment graph invariants and buyer-time navigation over the compiled graph. |
| `adapters.py` | Role → real module/entry wiring, signature contract report, bound dispatch config. Checkout carries the Skill 79 contract and validator as a native surface. |
| `tests/test_routes.py` | Stdlib `unittest` checks; each invariant has a mutation test that fails when violated. |

## Route law encoded

- landing → product_selection (`multiple_options` only) or checkout on a verified contact submit.
- `folded_levels` compiles landing → checkout with N ≥ 2 distinct main offers and **no** product_selection node.
- checkout → U1 on a verified main payment; checkout has no decline edge.
- U1 → U2 or thank-you on a verified U1 payment; U1 decline → D1 or thank-you.
- D1 → the SAME canonical U2 or thank-you on a verified D1 payment; D1 decline → thank-you.
- U2 → thank-you on payment or decline.
- Pending, failed and requires-customer-action retain state: no acceptance edge, no decline edge, no entitlement.
- Tab close is abandonment, never a decline or purchase.
- Bump is a checkout component, never a route node, and a bump-only purchase never qualifies for U2.
- U1 and D1 are mutually exclusive; U1 disabled forces D1 and U2 disabled.
- `payment_succeeded` requires `payment_verified=True`.
- Disabled pages are absent; every enabled page has an independent build unit.

D1 entry is additionally checked by the real S81 `check_entry_guard`; its
refusal codes (`D1-GUARD-NO-EXPLICIT-U1-DECLINE`,
`D1-GUARD-U1-ALREADY-ACCEPTED`, `D1-GUARD-NO-VERIFIED-MAIN-PURCHASE`,
`D1-GUARD-D1-DISABLED`, `D1-GUARD-D1-ENABLED-WITHOUT-U1`,
`D1-GUARD-U2-ENABLED-WITHOUT-U1`) are produced by that module, not re-listed
as launcher logic.

## Adapter wiring

| Role | Real entry point |
|---|---|
| landing | `49-signature-funnel/scripts/landing_bridge.py::bridge` → S71 `launch_context.prepare_import` + `page_result.build_and_write` |
| product_selection | `78-signature-product-selection/scripts/build_selection_plan.py::build_plan` then `emit_page_result.py::emit` |
| upsell_1 / upsell_2 | `49-signature-funnel/scripts/upsell_wrapper.py::main` → `80-signature-upsell/components/adapters/produce.py::main` |
| downsell_1 | `49-signature-funnel/scripts/downsell_wrapper.py::main` → `81-signature-downsell/validators/*` (pinned by the wrapper) |
| thank_you | `49-signature-funnel/scripts/translate_thank_you_result.py::main` → S82 `run_manifest.build_run_manifest` + `thank_you_resolver.resolve_order_view` |
| checkout | **native S79 order form installed by Skill 06; never a dispatch adapter for the form.** Its page design (wireframes and mockups) has a design-only adapter, `49-signature-funnel/scripts/checkout_wrapper.py`, wired by `build_dispatch_config(checkout_design=...)` |
| bump | **checkout component; never a route node** |

`build_dispatch_config` binds real absolute paths and refuses `/path/to`,
`<...>` and missing files. It is not the example manifest: no placeholder is
ever emitted as executable configuration.

## Recorded contract discrepancies (no shims)

- **D-01** Skill 71 has no `landing_bridge.py`. Its real entry points are
  `launch_context.prepare_import` and `page_result.build_and_write`; the
  dispatch adapter is S49's bridge, which calls both.
- **D-02** Skill 81 ships no executable consumer. S49's `downsell_wrapper.py`
  is the runtime wrapper and loads the pinned S81 validators.
- **D-03** The example product_selection command embeds a literal
  `<per-launch: ...>` launch-record path. The builder refuses it and binds the
  caller's real path.
- **D-04** The example upsell entries omit `--route-graph`; the builder passes
  `{work_dir}/route-graph.json` explicitly.
- **D-05** The native checkout form is intentionally not a dispatch adapter; only the page's design stages have one (design-only).
- **D-06** The example manifest contains `/path/to` and `<dispatch run session
  id>` placeholders; the builder refuses them.

## Seams

`DECISIONS-PENDING.md` names the two choices still open:
`distribution_run_target` and `cross_sales_teaching_source`. The ids are
`launcher_core/constants.py:SEAM_IDS`; each choice has exactly one id.

Every other choice is now DECIDED and carried by code, not by a seam:
`entitlement_declaration_and_attestation` (`launcher_core/entitlement.py`),
`council_included_in_launch_planning` (`launcher_core/council.py`),
`native_converted_and_flow_checkout_mapping` (`launcher_core/checkout.py` plus
this `adapters.py`), `verified_offer_facts_only` (`launcher_core/intake.py` and
`launcher_core/checks.py`) and `folded_levels_journey_mode` (`launcher_core/route.py`
plus the real S49 `compile_launch_route.py`). The Council planning record is
advice: it never blocks a build and is never permission.

## Run

```bash
TMPDIR=/Volumes/mac\ mini\ m4/Downloads/BLACKCEO_RECOVERY_2026-10-18/tmp \
python3 -I -m unittest discover \
  -s 83-black-friday-launcher/routes/tests -v
```
