# Native Order-Summary Integration Contract (S82-05, offline half)

**Status: OFFLINE HALF BUILT. The live half is a named blocker, listed at
the bottom of this document. Nothing in this file claims a live native
order read exists.**

Spec: packet doc 12 sections 2, 3, 5 and 10; doc 18 unit A13 (final
summary and access exactly reflect purchases). Adapter implementation:
`scripts/purchase_event_adapter.py`; tests: `tests/test_event_adapter.py`.

## The preference rule

When the native (Convert and Flow / GoHighLevel) Order Summary has been
**verified for the selected funnel**, S82 prefers it as the displayed
summary: it is the platform's own rendering of the same transaction the
buyer just completed.

Any custom S82 content around it — explanatory copy, access blocks,
next-step blocks — must read **the same validated snapshot** the native
summary represents. Custom content may never invent an item the native
summary does not contain, drop an item it does contain, or restate an
amount from any source other than that snapshot (spec 12 section 3:
"Custom explanatory content must read the same validated snapshot; it
may not invent items the native summary does not contain").

Until the native summary is verified for a funnel, S82 renders its own
summary from the validated snapshot alone — the snapshot, not the
native UI, is the purchase truth either way.

## The adapter boundary

```text
S44 / vendor order events                 S82
(normalized purchase events,        ┌──────────────────────────────┐
 packet purchase-event shape)  ───► │ purchase_event_adapter.py    │
                                    │ events in -> ONE verified    │
                                    │ snapshot per native order    │
                                    └──────────────┬───────────────┘
                                                   ▼
                                    thank_you_resolver.resolve_order_view
                                    (unchanged; the one purchase-truth owner)
```

- **In:** a list of normalized purchase events in the packet
  purchase-event shape (`reference/schemas/purchase-event.schema.json`
  in the packet): `schema_version`, tenant/location/launch identity,
  `provider`, `event_id`, `event_type`, `native_order_ref`,
  `native_transaction_ref`, `occurred_at` / `received_at`, the
  event-level `payment_status`, `line_items`, `evidence_ref`,
  `test_only`. Per line, the fixture extension used across this skill's
  tests may add `payment_status` (or `status`), `display_name`,
  `billing`, and `event_id`; per-line payment truth comes from the
  line's own status field when present, otherwise from the event's
  `payment_status`.
- **Out:** one verified normalized purchase snapshot per native order —
  exactly the shape `thank_you_resolver.resolve_order_view` already
  consumes. The adapter is a *producer* of snapshots; it owns no
  purchase truth of its own and never edits the resolver's rules.

### What the adapter guarantees

1. **One stream, one identity.** All events in a call must share one
   tenant/location/launch identity. A mixed-tenant or mixed-launch
   stream is rejected outright (`mixed_identity_stream`) — events are
   never sorted into the "probably right" tenant.
2. **Grouping is by native order only.** Events are grouped by
   `native_order_ref` under that single identity, producing one
   snapshot per order. A later extra (U1/D1/U2) attaches to an order's
   snapshot **only** when its event carries that same native order
   reference — the native order/transaction relationship is the proof
   of same journey (spec 12 section 5). One initial order can contain
   main plus bump in a single event; later extras arrive as further
   events under the same order and are appended.
3. **Email never groups anything.** The adapter has no email (or any
   contact-identity) input at all. Two orders bought by the same person
   stay two snapshots; returning-buyer historical entitlements are
   never folded into the current journey's view (spec 12 section 5:
   "Do not group every purchase sharing an email address").
4. **Redelivery is safe.** An identical repeated event (same
   `event_id`, identical content) is deduplicated. The same `event_id`
   redelivered with different content raises
   (`conflicting_event_redelivery`) — the adapter never guesses which
   delivery was true. Line-level merging reuses the resolver's own
   `deduplicate_line_items`, so identical lines collapse and
   conflicting lines raise identically there too.
5. **Provenance is exact.** Each snapshot line carries its own
   `event_id`: the line's own extension value when present, otherwise
   the deterministic `<event_id>::<native_line_ref>` of its source
   event (one event can carry several lines; the resolver's O-01
   provenance check requires one event ID per line). The snapshot's
   `event_ids` manifest is exactly those line event IDs, so adapter
   output passes the O-01 cross-check unchanged.
6. **Verified means evidenced.** A snapshot is marked `verified` only
   when **every** contributing event carries a non-empty
   `evidence_ref` (and a provider). With
   `require_live_evidence=True` (production mode) the adapter refuses
   the stream outright if any event is `test_only`, comes from a
   test-marked provider, or lacks an `evidence_ref` — test evidence
   can never be promoted into a production snapshot. In test mode,
   TEST ONLY events produce snapshots with `test_only: true`, exactly
   like the existing fixtures.
7. **Amounts and entitlements come only from event lines.** Display
   names and billing terms come from the line's extension fields, or
   from an explicitly supplied offer catalog, or — as a display-only
   fallback — the offer ID itself with an empty one-time billing
   block. Amounts, currencies, slots, and entitlement IDs are never
   defaulted or invented.

## What stays blocked (live half — L3/L4 pending, NOT faked)

The following stay open until the named dependencies land; per spec 12
section 10, a missing live order-read path remains a named blocker,
not a fake successful sample receipt:

- **L3 — installed native product mappings from S79 / S80 / S81.**
  The installed skills' native product/price IDs for bump, U1, D1, and
  U2 must exist so vendor events can be mapped to internal offer IDs
  and slots with certainty. Until then the adapter is exercised only
  against TEST ONLY normalized events, never raw vendor payloads.
- **L3 — S06 native order read.** A supported native read of the
  actual order/transaction state for the selected funnel (the adapter
  S82 consumes at runtime), including verification that the native
  Order Summary for that funnel shows the same items the snapshot
  holds.
- **L4 — native sandbox payment proof.** Real sandbox transactions
  (main+bump in one event; later U1 under the same native order;
  refunded extra) observed through the native read and reconciled
  against adapter snapshots — doc 18 A13's minimum evidence level.
- **L4 — delayed/out-of-order native delivery.** The reconciliation
  UX in `references/states.md` exercised against real delayed native
  events, not only fixture streams.

When those land, the live path changes only the adapter's *input
source* (real S44/vendor-normalized events instead of fixtures). The
snapshot contract, the resolver, and the validators do not change.
