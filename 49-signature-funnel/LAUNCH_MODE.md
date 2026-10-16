# Skill 49 — `signature_launch` mode

Skill 49 organizes the launch; the other skills build each piece.

Skill 49 has two modes. The mode is chosen explicitly on every new run;
nothing silently switches.

| Mode | What it is |
|---|---|
| `legacy_signature_funnel` | The historical pipeline: SACRED 12-section hero, derived U1/D1/U2/D2/thank-you pages, 3/5/7-step funnels, the locked-brief intake (`intake/sf-intake-questions.json`), fail-closed provers, signed PROCESS-CERTIFICATE. Behavior is unchanged; its golden fixtures are the regression contract (acceptance A34). |
| `signature_launch` | The launch coordinator added by the Signature Launch build: guided intake and plan approval first, a deterministic route graph compiled from the approved plan, then one idempotent page request per role dispatched to the specialist skills (71 landing, 78 product selection, 79 checkout, 80 upsell 1 and upsell 2 as separate invocations, 81 downsell, 82 thank-you). The bump is a component on checkout, never a page. There is no second downsell in this profile. |

## Entry

```bash
# legacy (default, unchanged)
bash signature-funnel-entry.sh --run-dir <RUN_DIR>

# launch mode (explicit)
bash signature-funnel-entry.sh --mode signature_launch --run-dir <RUN_DIR>
```

A launch run dir holds `launch.json` (the approved launch record),
`approval.json` (the plan-approval record), and `launch-request.json`
(`mode`, client/worker identity refs, copy profile, write target, any
scoped approvals). The legacy path refuses a launch-mode run dir rather
than running it through the old pipeline. The entry script is not a
pinned enforcement file; no pinned file changed for launch mode, so the
hash-pin still verifies the untouched legacy core.

## Launch-mode toolchain (`scripts/`)

| Script | Job |
|---|---|
| `launch_intake.py` | Guided interview state machine (doc 03): durable session, per-field provenance ledger, deterministic recommendation rules, plan assembly, plain-language summary, pause/resume. Question bank: `intake/launch-questions.json`. |
| `validate_launch_plan.py` | Domain-law plan validator plus `assert_plan_build_approved`, the plan-approval gate (hash binding, client identity, no worker self-approval, revocation/expiry, separate approval types). |
| `compile_launch_route.py` | Deterministic route compiler/validator/resolver. One source produces `route-graph.json`, a readable route table, and machine test cases. Graph hash = SHA-256 of the emitted file bytes. |
| `dispatch_launch.py` | Turns an approved plan into specialist page requests (idempotent dispatch keys), optionally executing them through consumer adapters (`launch-adapters.example.json`). Emission is not execution: the manifest says `emitted_not_executed` until a consumer really answers with a valid result. |
| `collect_launch_receipts.py` | Aggregates page results into a launch checkpoint: request echo required, self-review never counts as independent review, weakest proof class reported. |
| `legacy_adapter.py` | Migrates a legacy LOCKED brief into a launch-mode draft (status `collecting`, no plan approval — the legacy lock is not one), with a mapping report that names every unmapped field (notably the second downsell, which has no launch counterpart). Legacy files are never edited. |

## Contracts

Canonical schemas live in `shared-utils/signature_launch/domain/`
(launch, offer, route-graph, approval, page-request, page-result,
progress, purchase-event v1.1); the skill carries its own copies of the
launch and route-graph schemas under `schema/`. Money is integer minor
units; an unknown price is `null` with status `unknown`, never zero. A
recommendation is a proposal state, never an approval; approval binds to
the exact plan hash and revision.

## What launch mode does not do

It does not process payments, send email, call image providers over
HTTP, or handle browser credentials. Native products/prices/orders are
S44/S06/S79 surfaces; email is S50's plan consumed by S44; images follow
the S63 policy and the selected provider's receipts. The launch DAG —
approved domain/brand → copy/profile → approved local artifacts → S44
provisioning → S06 native install → S44 workflow wiring → integrated
test → activation approval — is enforced by the dispatch write targets
and scoped approvals, not by this skill reaching into other systems.
