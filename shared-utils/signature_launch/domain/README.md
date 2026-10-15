# Signature Launch — shared domain contracts

Owner: **Skill 49 (Signature Launch Coordinator)**. These schemas are the
canonical, provider-neutral domain contracts for a Signature Launch. Every
room that produces or consumes launch data validates against the copies here;
Skill 49 also ships the launch + route-graph schemas inside the skill
(`49-signature-funnel/schema/`) for its own scripts.

| File | Contract |
|---|---|
| `launch.schema.json` | The approved-domain launch record: identity, journey mode, offers with per-fact provenance, extras flags, brand + route-graph hashes, plan-approval reference, lifecycle status. |
| `offer.schema.json` | One offer: slot (main/bump/upsell_1/downsell_1/upsell_2), deliverables, exclusions, entitlements, requires/excludes, price choices in integer minor units (unknown is null + status `unknown`, never zero). |
| `route-graph.schema.json` | The compiled route graph: nodes by role, guarded edges (paid edges carry `verified_*` guards), and the pending/failed-payment retention rule. |
| `approval.schema.json` | Scoped approval record: one type per authorization (plan build, paid budget, test location, live payment test, customer sends, publication, batch merge, release, rollout) — never inferred from one another. |
| `page-request.schema.json` / `page-result.schema.json` | The dispatch contract between the coordinator and each specialist page skill, and the result the skill returns (request echo, independent review, proof class L0–L5). |
| `progress.schema.json` | The evidence-derived progress sample the watchdog publishes per room. |
| `purchase-event.schema.json` | **v1.1** — normalized purchase event. Adds OPTIONAL `contact_ref` (CR-S44-001, S49 ruling 2026-10-15): an opaque native contact ID, never PII, the auditable binding for the A21 suppression recheck and fulfillment. Producers emitting it stamp `1.1`; v1.0 events stay valid and the v1.0 schema is preserved beside it as `purchase-event.v1.0.schema.json`. |

Rules that bind every consumer:

- Money is integer minor units with an explicit currency. No float dollars,
  no hardcoded two-decimal assumption (doc 02 §3).
- A recommendation is a proposal state, never an approval. Approval binds to
  the exact plan hash + revision (doc 03).
- The route graph is compiled deterministically from the approved launch
  record by `49-signature-funnel/scripts/compile_launch_route.py`; its hash is
  the SHA-256 of the exact emitted file bytes and is recorded in the launch
  record and in every page request.
- The bump is a component on checkout, never a route node. There is no second
  downsell in this profile. Pending/failed payment retains state — it never
  traverses a paid edge and is never a decline.

Schema changes are versioned here first; consumers pin `schema_version`.
