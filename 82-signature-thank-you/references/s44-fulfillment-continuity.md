# S44 Fulfillment Continuity — Handoff Contract (S82-08)

Who owns what: **S44 owns granting entitlements and operational
messages** (packet doc 14; doc 12 section 6). **S82 consumes that
state** to render the terminal confirmation. This document is the
contract between the two: what S82 reads, what S82 records back, and
what evidence must flow from S44 before acceptance A20 can close
above L1.

## 1. Fulfillment never waits for this page

- Fulfillment **begins promptly on the successful purchase event**,
  processed by S44's event-driven purchase handler. It does not
  depend on the buyer reaching, loading, or keeping open the
  thank-you page.
- **Tab-close survival (A20):** a buyer who pays and immediately
  closes the tab still receives every granted entitlement and the
  confirmation/access fallback (section 3). The page is a *view* of
  fulfillment, never a step *in* fulfillment.
- A later extra-offer failure never strands the base purchase: S44
  grants the base from its own event; the page merely reflects that
  the base is paid/granted and the extra is failed or pending.

## 2. What S82 consumes: the fulfillment map

S82 reads S44 entitlement state through the fulfillment map, keyed by
entitlement ID:

```json
{
  "<entitlement_id>": {
    "state": "granted | pending | not_granted | revoked",
    "delivery_url": "https://… | null",
    "next_action": "access | download | manage_purchase | support |
                    schedule_included_service | noncommercial_next_step"
  }
}
```

S44's producer emits that map inside an order-level envelope
(CR-S82-002), which also carries S44's entitlement version for the
buyer:

```json
{
  "tenant_id": "…",
  "launch_id": "…",
  "contact_ref": "…",
  "entitlement_version": "ev1:<64 lowercase hex>",
  "entitlements": { "<entitlement_id>": { "state": "…",
                    "delivery_url": null, "next_action": "…" } }
}
```

- The resolver accepts either the bare map or the producer envelope.
  On the envelope it reads `entitlements` as the map above and carries
  the order-level `entitlement_version` through to the view's
  `entitlement_version` field (order-view schema); the same value may
  be supplied as the resolver's explicit version input, which then
  takes precedence. An envelope whose `tenant_id`/`launch_id` differ
  from the verified snapshot fails closed, and a version that is not a
  well-formed `ev1:` value (the item-5 shape: `ev1:` plus the
  lowercase sha256 hex of S44's canonical book-state string) fails
  closed in the resolver and fails order-view schema validation — a
  mismatched or forged version never reaches the dedupe key.
- With no version supplied, the view carries no `entitlement_version`
  field and behavior is unchanged: the confirmation observation
  derives its deterministic fingerprint fallback (section 3).

- Only a **paid** item whose fulfillment state is `granted` produces
  an access block in the view (resolver rule; A13).
- A `pending` state renders the item as pending — never as "You are
  all set" — while the base stays confirmed.
- A `revoked` state (refund/cancel/chargeback, section 4) removes the
  access block but **not** the historical receipt row.
- A `next_action` outside the six approved classifications fails
  closed in the resolver (repair D-05): S44 may not invent a
  thank-you action — and a new-charge action can never be one.

## 3. One onboarding send, whoever gets there first

Both the page and the S44 event worker observe completion. Without
deduplication the buyer would get the onboarding/confirmation send
twice. The rule:

- **The S44 event worker owns the send.** The thank-you page render
  emits **no send of any kind** — no email, no SMS, no webhook whose
  effect is a customer message.
- The page records exactly one thing: a **`confirmation_shown`
  observation** (`scripts/confirmation_observation.py`), whose dedupe
  key both sides check before any onboarding send:

  ```
  dedupe_key = sha256("<tenant_id>|<location_id>|<launch_id>|"
                      "<order_ref>|<entitlement_version>")
  ```

- If the worker reaches the send first, the page's observation is a
  no-op duplicate of an already-satisfied journey. If the page is
  somehow observed first, the worker still owns and performs the send
  exactly once, keyed by the same dedupe key. A page **refresh**
  rebuilds the identical record (same key) and changes nothing.

### Observation record shape

```json
{
  "record_type": "confirmation_shown",
  "dedupe_key": "<sha256 hex>",
  "tenant_id": "TEST-TENANT",
  "location_id": "TEST-LOCATION",
  "launch_id": "TEST-LAUNCH",
  "order_ref": "TEST-ORDER-0001",
  "entitlement_version": "derived-sha256:<hex> | <S44-supplied version>",
  "entitlement_ids": ["base-a", "extra-full", "workbook"],
  "confirmation_status": "confirmed",
  "observed_via": "thank_you_page_render",
  "emits_send": false,
  "test_only": true
}
```

`entitlement_version` is S44's version identifier for the entitlement
state shown, when S44 supplies one on the view; otherwise the page
derives a deterministic version from the view's entitlement state
(sorted entitlement/state pairs, sha256-prefixed `derived-sha256:`),
so the same state always yields the same version and any entitlement
change yields a new one. The supplied value reaches the view through
the resolver's carry-through from the producer envelope (section 2):
the view's order-level `entitlement_version` field holds S44's ev1
value, so the page-side key above can equal the worker-side key the
S44 event worker computes over the same ev1 value. (Before the gap-I6
repair, no schema-valid resolver-produced view could carry the field
and the derived fallback always fired on the page side, so the two
keys could never match.) The record carries **no PII**: no email, no
buyer name, no payment data — entitlement IDs are product
identifiers, not personal data.

## 4. Refunds, cancellations, chargebacks

- Refund, cancellation, chargeback, and subscription-expiry handling
  is governed by **S44's approved entitlement policy**, never by page
  logic. S44 updates the fulfillment map (`granted` → `revoked`, or a
  refund payment status on the snapshot line); S82 reflects it.
- Page behavior on a refunded item: the **historical receipt row
  stays**, honestly labeled Refunded / Partially refunded; the access
  block disappears; the confirmation is no longer "all set"
  (repair D-04). Partial refunds behave the same way for the affected
  item only.
- Refunding an upsell **never** removes or alters an unrelated
  original purchase: its row, amount, and access stand untouched.

## 5. Consistency between channels

The confirmation email/access fallback and this page read the **same**
verified snapshot and the **same** S44 fulfillment map, so a buyer
never sees one purchase set in email and a different one on the page.
Where the two disagree, the purchase ledger (S44/S49) is the truth and
the page is re-resolved from it — the page never edits the ledger.

## 6. Evidence S82 needs back from S44 to close A20 at L4

A20's minimum evidence in doc 18 is **L4** (authorized native
sandbox payment/workflow behavior). The five items below are the
contract's asks; their filed status as of 2026-10-16 is recorded
after the list — all five were filed by S44 at L4 and
independently reviewed by S82 (verdicts cited there).

1. **Native event read-back:** for an authorized sandbox purchase,
   the actual S44 workflow/event record showing the base entitlement
   granted from the purchase event with **no thank-you page visit**
   in the journey (tab-close case).
2. **Extra-failure case:** the same read-back pattern for a journey
   where a later extra payment failed, showing the base grant intact
   and no duplicate or revoked-base side effect.
3. **Single-send proof:** the saved workflow export / send log
   showing exactly one confirmation/onboarding send for a journey
   where both the event worker fired and the thank-you page was
   rendered (and refreshed), matched against the
   `confirmation_shown` dedupe key.
4. **Refund case:** a sandbox refund of an extra only, with the
   fulfillment-map state change read back and the original purchase's
   grant shown unchanged.
5. **Receipts, not plans:** each item above as actual saved-object
   exports/read-backs with tenant identity — a plan file, a stub ID,
   or a fixture run does not close any of them (doc 14 section 1/12).

**Status (2026-10-16):** all five items were filed by S44 at L4
under Trevor's sandbox-only test-payments ruling
(`handoffs/change-requests/CR-S82-002-L4-COMPLETION-S44.md`;
full evidence `rooms/S44/work/l4/L4-COMPLETION-2026-10-16.md`)
and independently reviewed by S82
(`work/review-cr-s82-002-l4-completion.md`). Per-item verdicts:
item 1 SUPPORTED for A20's tab-close half; item 2 SUPPORTED with
its failure-form limitation carried verbatim (payment never
completed — a draft unpaid invoice with no transaction — not a
declined charge; the sandbox has no payment provider); item 3
SUPPORTED as exactly one send proven on a clean re-run, with
run 1's disclosed operator-caused duplicate send (2 native sends
against 1 claim; the pipeline never re-sent) carried with it;
item 4 SUPPORTED (the strongest leg — trace IDs for every native
read-back); item 5 SUPPORTED (values recomputed bit-for-bit by
the reviewer). Cross-cutting caveat: the native leg is CLAIMED
(S44 firsthand read-backs, no raw native payloads on file)
pending SWARM's re-read of the cited native IDs. A20 is READY
to present to SWARM; the unit stays `planned` in the ledger
until SWARM verifies and INTEGRATION records — S82 reports it
that way.
