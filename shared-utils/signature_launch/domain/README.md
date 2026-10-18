# Signature Launch — shared domain contracts

Owner: **Skill 49 (Signature Launch Coordinator)**. These schemas are the
canonical, provider-neutral domain contracts for a Signature Launch. Every
room that produces or consumes launch data validates against the copies here;
Skill 49 also ships the launch + route-graph schemas inside the skill
(`49-signature-funnel/schema/`) for its own scripts.

| File | Contract |
|---|---|
| `launch.schema.json` | **v1.2** — the approved-domain launch record: identity, journey mode, offers with per-fact provenance, extras flags, brand + route-graph hashes, plan-approval reference, lifecycle status. Adds OPTIONAL `prompt_policy_id` (Q12 prompt-policy reconciliation, S49): the governing prompt policy's registry-minted name, carried top level beside `brand_ref`/`brand_hash` and bound by the plan document hash; never null, absent when no policy governs. Records carrying it stamp `1.1`; v1.0 records stay valid and the v1.0 schema is preserved beside it as `launch.v1.0.schema.json`. Adds OPTIONAL `delivery_bindings` (S82-DEC-DELIVERYURL-01, S49): a per-entitlement delivery binding keyed by entitlement_id, each entry stating `delivery_kind` (`access` / `download` / `schedule_included_service`) and `delivery_url` (an https destination or null), bound by the plan document hash and read by Skill 44's fulfillment-map producer (CR-S82-003) for granted entitlements; an entitlement with no entry is unbound and keeps the producer's pre-binding behavior exactly, and a binding naming an entitlement no offer grants fails validation (R-DB-1). Records carrying bindings stamp `1.2`; v1.1 records stay valid and the v1.1 schema is preserved beside it as `launch.v1.1.schema.json`. Skill 49's copy in `49-signature-funnel/schema/` advances identically. |
| `offer.schema.json` | One offer: slot (main/bump/upsell_1/downsell_1/upsell_2), deliverables, exclusions, entitlements, requires/excludes, price choices in integer minor units (unknown is null + status `unknown`, never zero). |
| `route-graph.schema.json` | The compiled route graph: nodes by role, guarded edges (paid edges carry `verified_*` guards), and the pending/failed-payment retention rule. |
| `approval.schema.json` | Scoped approval record: one type per authorization (plan build, paid budget, test location, live payment test, customer sends, publication, batch merge, release, rollout) — never inferred from one another. |
| `page-request.schema.json` / `page-result.schema.json` | The dispatch contract between the coordinator and each specialist page skill, and the result the skill returns (request echo, independent review, proof class L0–L5). `page-request.schema.json` is **v1.1**: adds OPTIONAL `prompt_policy_id`, stamped by `dispatch_launch.build_requests` from the launch record when the record names one. Producers emitting it stamp `1.1`; fieldless requests stay valid 1.0 documents and the v1.0 schema is preserved beside it as `page-request.v1.0.schema.json`. `page-result.schema.json` stays 1.0 regardless of the request's version. |
| `progress.schema.json` | The evidence-derived progress sample the watchdog publishes per room. |
| `purchase-event.schema.json` | **v1.2** — normalized purchase event. Adds OPTIONAL `parent_order_ref` (CR-S44-003, S49 ruling 2026-10-17): the opaque provider order identity of the initial order, populated only when the provider's native read-back on a later extra-purchase event actually carries it; never synthesized, derived, required, or load-bearing for dedupe, grants, or revocations. Producers emitting it stamp `1.2`; v1.1 (which added OPTIONAL `contact_ref`, CR-S44-001) and v1.0 events stay valid, and the earlier schemas are preserved beside it as `purchase-event.v1.1.schema.json` and `purchase-event.v1.0.schema.json`. |
| `prompt-policy-registry.schema.json` / `prompt-policy-registry.json` | The prompt-policy registry (Q13). The schema file is the FORMAT for the one registry artifact; the JSON file is the registry itself, one document holding every prompt-policy entry (identity and lifecycle, doctrine, applicability, per-model maxima, counting convention, ratio enum sources, reference-role vocabulary, cap-status vocabulary, divergence records, budget-decision citation). Format single writer: **Skill 49 only**. Entry CONTENT is owned by the doctrine owners (Skills 71 and 63) and is written by Skill 49 only from their reconciled, owner-approved text. Citation rule: every budget decision in a prompt record cites the entry's `policy_id` AND its `entry_hash`; a decision missing either is not acceptable to Skill 49's aggregator. An `active` entry is immutable once written; any correction is made only by supersession (a new entry naming the old `policy_id` in `supersedes`, the old entry marked `superseded`), so a citation always resolves to the exact entry it cited. The registry ships with its first minted entry (`kie-rule-12-band`); later entries are added only by supersession under the format's rules. |

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
