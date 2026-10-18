# Native Action States - Skill 81 (D1 purchase and decline UX)

Status: build candidate, S81 room. Governing sources: packet 11 sections 6 and 7; packet 02 sections 4 and 8; packet 16 section 1 (the extra-offer action/disclosure component is shared, owned by S79/S06 - S81 consumes it and never copies a second charge implementation).

## Action binding

- Use the shared transactional action component with a product-bound native one-click action when the valid payment context supports it.
- Every CTA on the page (all 8 sections) points to the SAME guarded product/action mapping.
- Exact terms sit adjacent to the action: amount due now, currency, one-time / recurring / trial terms, renewal if any. Strong copy never removes the need for clarity, and recurring disclosures are never hidden in miniature footer type.

## States

| State | Behavior |
|---|---|
| `idle` | CTAs enabled; decline action visible. |
| `processing` | Repeat purchase attempts disabled while a result is pending. Double-click cannot double-charge. |
| `succeeded` (verified native evidence) | Record transaction/order relation and incremental entitlements, then route: SAME canonical U2 when enabled (entry context `from_downsell_1`), else final thank-you. Never create a D1-specific duplicate U2. |
| `failed` | Stay on D1 in a recoverable state. Offer retry / customer-action recovery, or an explicit "continue without this extra" choice. A failure is NEVER recorded as acceptance or decline. The original order remains valid. |
| `pending` / `requires_customer_action` | Stay on D1. Not an acceptance, not a decline. |
| `unknown_outcome` (timeout) | Reconcile from native records BEFORE any retry. A timeout is not a decline and never justifies a second blind charge. |
| `expired_or_unsupported_context` | Use the approved checkout fallback, or block the paid action and offer safe continuation. Never fabricate a payment token. |
| `explicit_decline` | The visitor clicks the visible decline action (for example "No thanks, continue with my current order"). No charge, no removal of existing access. Route to final thank-you. The original order and any bump are preserved. |
| `abandoned` | Tab closed or session left. D1 stays unpurchased; base-order fulfillment proceeds independently. Abandonment is never recorded as a fabricated decline event. |

## Vocabulary mapping: result-schema UI state terms and native action states

Two state vocabularies exist in this package and they are NOT interchangeable. The result-extension schema (`schemas/downsell-result-extension.schema.json`, in the `ui_states_ref` description) names the UI preview states a page result must point at. This document names the native action states the shared component actually behaves in. Neither list is renamed to match the other; the table below is the explicit mapping between them. A checker working from one list and a builder working from the other must both use this table, or states fall between the lists.

Schema UI state term (from `ui_states_ref`) and its native action state counterpart in this document:

| Schema term | Native counterpart | Notes |
|---|---|---|
| `default` | `idle` | The state before any action: CTAs enabled, decline action visible. |
| `focus` | No counterpart in this document | Focus is a visual keyboard-focus preview state. It is named in the design profile (`references/design-profile.md`, rule 6) as a required preview, but the native action has no transactional focus state. |
| `selected` | No counterpart in this document | Selected is a visual preview state that exists only where the component has a selection analogue (design profile rule 6). The native action states have no selected state. |
| `loading` | `processing` | The pending lockout state: repeat purchase attempts disabled while a result is pending. |
| `error` | `failed` | Direct counterpart for a failed attempt that stays recoverable on D1. Note the native vocabulary splits other error-shaped outcomes out separately: `pending` / `requires_customer_action`, `unknown_outcome`, and `expired_or_unsupported_context` are their own native states, not part of `failed`. |
| `completed` | `succeeded` | Renders only from verified native success evidence; a redirect or a clicked button is not completion. |
| `pending` | `pending` / `requires_customer_action` | One combined row in the states table above: not an acceptance, not a decline. |
| `expired-context` | `expired_or_unsupported_context` | Use the approved checkout fallback, or block the paid action and offer safe continuation. |

Native action states with NO schema UI state term:

| Native state | Schema counterpart | Notes |
|---|---|---|
| `unknown_outcome` | None | The timeout state has no term in the schema list. It must still be designed, previewed, and reconciled from native records before any retry; its absence from the schema list is not permission to omit it. |
| `explicit_decline` | None | Decline is a routed outcome in the native vocabulary (carried in the result extension by `decline_action_ref` and `route_result.decline_target`, not by the UI state list). |
| `abandoned` | None | Session abandonment has no schema term. It is never recorded as a fabricated decline event. |

## Entry guards (spec 11 section 10, doc 02 section 4)

D1 renders only when ALL hold: verified original (main) purchase exists; U1 was explicitly declined (a declared decline event, not a failed/pending U1 payment); D1 is enabled; U1 was not accepted. Direct access without an eligible original purchase, and access by an accepted-U1 buyer, are refused and routed safely (accepted U1 is mutually exclusive with D1).

## entry_guard_ref

The request schema requires `entry_guard_ref` (string, minLength 1) but does not say what it refers to; this section is the definition. The token otherwise appears only in the shipped request fixture (value "TEST-ENTRY-GUARD") and in the install wrapper's required-field list.

`entry_guard_ref` names the evidence record the entry guard consumes. It does not name a verdict, and it does not name the guard state itself. The ref is a name, never evidence: `check_entry_guard` (in `validators/validate_downsell.py`) computes the guard from the record the ref names.

The record the ref names carries the journey facts the guard reads: a verified main purchase (`main_purchased_verified`) and the U1 outcome (`u1_event`), where `u1_event` qualifies only as the literal "explicit_decline" (a failed or pending U1 payment never qualifies), alongside `u1_accepted`. The enabled flags the guard also reads (U1, D1, U2 enabled) are launch facts, not journey facts: they are sourced from the launch record's extras under route law (D1 and U2 cannot remain enabled when U1 is disabled), not from the record this ref names.

## Event handoff to S44

The GHL adapter may report a D1 purchase as an upsell-type purchase. S44 distinguishes D1 using the verified product/page/slot mapping, never an invented native `downsell_purchased` trigger. Downsell is a business role, not necessarily a separate vendor transaction type.
