# Skill 78 selection handoff and binding plan contract (S78-05, S78-06)

## selection.json

Schema: schema/selection.schema.json. It records tenant, location, launch,
revision, chosen internal offer and price choice, the approved native
product and price IDs, currency, the approved amount snapshot, billing type
and schedule, quantity, selected-at, source page, and an opaque session
reference. It is intent, never payment evidence. It contains no email,
phone, card data, or provider secret.

## Session bridge

- The bridge key is an opaque, short-lived, server-side reference
  (selection_session.py models it; production storage is tenant-scoped per
  doc 02 section 11). Default TTL in the model: 1800 seconds.
- Resume revalidates against the current approved catalog. Outcomes:
  resumed; reconfirm_required (material terms changed, with previous and
  current values shown to the visitor); expired (helpful restart message,
  no package silently selected).
- Confirm revalidates exactly as resume does: the current approved launch
  is a required input, and changed or unapproved terms return
  reconfirm_required, never a confirmed draft for stale terms. Confirm is
  then idempotent per session: repeated CTA clicks return the same
  draft reference and create no second draft order.
- A reference from another tenant or launch resolves to nothing.

## Binding plan

Emitter: scripts/emit_binding_plan.py. One mapping per selectable price
choice: internal offer and price choice, native product and price IDs,
checkout target reference, currency and approved amount. Routes:
platform_native_selection, or per_offer_targets (one native checkout target
per approved product/price, all produced by S79; multiple instances, not a
new skill or duplicate catalog). Consumers: S79 and S06. S78 never edits
S79's checkout implementation; changes travel as change requests under
~/workspace/signature-launch/handoffs/change-requests/.

## Checkout-side duties (recorded here so the seam is testable)

S79 loads the validated selection, visibly confirms package, schedule,
quantity and price, and offers an explicit change-package path. Missing or
expired selection shows a recovery choice. Native quote and read-back are
authoritative over every snapshot in selection.json (acceptance A05 closes
at L3 only when each offer is clicked in an authorized test session and
checkout displays the correct selection).
