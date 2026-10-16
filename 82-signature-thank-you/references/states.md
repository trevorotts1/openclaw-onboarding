# Delayed, Pending, Outage and Error States — Skill 82 (S82-06)

**Scope:** every non-happy-path rendering of the terminal thank-you
page, implemented in `scripts/render_thank_you.py` (`render_thank_you`
with a `state` argument, `render_state_fragment`, `render_error`).
Layout and copy for the resolved order view live in
`references/layout-and-copy-profiles.md` (S82-04).

Governing rules (packet doc 12 sections 4, 5, 8, 10):

- A pending purchase is stated honestly and never shown as confirmed:
  no "You are all set" for unconfirmed access.
- A pending or failed extra never withholds valid base access (A20).
- Refreshing or re-checking an order summary never initiates another
  purchase.
- An error or outage never produces a fake/sample receipt. The
  alternatives are an honest state, the last verified cached data
  (labeled), or nothing but an explanation and a support route.

## 1. Delayed reconciliation state (`mode: "reconciling"`)

**When:** a purchase event is delayed — e.g. checkout succeeded but a
later extra's event has not arrived, or the native order read lags the
redirect — so the resolver cannot yet produce the final view, or the
view exists but carries `reconciling: true` with items unresolved.

**What renders:**

- Heading: "Confirming your purchase", with a decorative spinner
  (`aria-hidden`, disabled under `prefers-reduced-motion`).
- The bounded retry policy in words: which check this is
  ("check {attempt} of {max_attempts}") and when the next automatic
  check happens.
- The explicit promise: "You do not need to pay again, and checking
  again never starts another purchase."
- The alternative access/support route, always visible (not only after
  the budget runs out): the access link in the buyer's confirmation
  email, and the support CTA (`data-cta-class="support"`).
- A manual "Check again now" button
  (`data-cta-class="noncommercial_next_step"`,
  `data-ty82-action="recheck"`). It re-reads order state; it cannot
  submit a payment.
- If a partial view exists (base confirmed, extra delayed), it renders
  below the banner in the normal layout with the extra labeled
  `Pending`; the banner explains only the unresolved part.

**Retry / backoff policy (bounded):**

| Check | Wait before it |
|---|---|
| 1 (initial render) | — |
| 2 | 5 seconds |
| 3 | 15 seconds |
| 4 | 30 seconds |
| 5 | 60 seconds |

After check 5 the page **stops** auto-refreshing. It does not loop
forever, does not escalate to a purchase, and leaves the buyer on the
email/support fallback with the order reference in hand. Constants:
`RETRY_DELAYS_SECONDS = (5, 15, 30, 60)`,
`MAX_RECONCILIATION_CHECKS = 5` in `scripts/render_thank_you.py`.
Exceeding the budget is a support case, not a silent infinite spinner.

**State input:**

```json
{"mode": "reconciling",
 "retry": {"attempt": 2, "max_attempts": 5, "next_retry_seconds": 15}}
```

## 2. Pending item states (in the normal layout)

Pending is a per-item state, not a page failure. The resolver labels
each pending item `Pending` in the summary, keeps it out of the paid
total (it appears in the separate `Pending (not yet confirmed)` total
row), grants it no access block, and names it in "What happens next"
with the delivery-on-confirmation wording (layout doc section 2.3).
`requires_customer_action` renders as `Action needed`; `unknown`
renders as `Confirming`. Page-level profiles: `partially_pending` and
`pending` (layout doc sections 3.2–3.3). A tab close during pending
strands nothing: fulfillment and the confirmation email proceed from
the purchase event, not from this page (doc 12 section 6).

## 3. Provider outage — cached view (`mode: "outage_cached"`)

**When:** the native order/transaction read fails or times out but a
previously verified cached view exists **for this buyer, this order,
within its privacy/consistency rules**.

**What renders:** the normal layout, preceded by the outage banner:

- "Some details could not be refreshed" — the buyer is told plainly
  that this is the **last confirmed copy** of the order, verified data
  as last saved, not a guess and not live.
- An **"Unresolved items"** list: every item whose state could not be
  re-checked (pending / failed / action-needed / confirming), named
  with its last known status label. If nothing is unresolved, the
  banner says so instead of listing nothing silently.
- The support CTA inside the banner.

**Never:** cached data from a different buyer or order (a shared
computer's next visitor must not see a previous buyer's receipt —
the host's `private, no-store` handling in section 5 applies),
cached data presented as freshly confirmed, or a fabricated "sample"
order standing in for the missing read. If no valid cached view
exists, the outage renders as the `native_read_failure` error
(section 4), not as an invented receipt.

## 4. Error states (`mode: "error"`, `render_error`)

Every error fragment contains **no order data at all** — no items, no
amounts, no order reference pulled from an unverified source — and
never a fake sample receipt. Each carries an explanation in plain
words and the support fallback (`data-cta-class="support"`), inside a
`role="alert"` region.

| `error_kind` | When | Heading (approved pattern) | Fallback route |
|---|---|---|---|
| `wrong_order_reference` | The order reference does not resolve, is guessed/sequential, or belongs to another store | "We could not find that order reference" | Use the full link in the confirmation email; support can find the order from that email |
| `stale_session` | The authenticated order context / opaque reference has expired | "Your session has expired" | Sign in again from the confirmation email link; the purchase itself is unchanged |
| `native_read_failure` | The native order read errors with no valid cached view (section 3) | "We could not load your order just now" | "Try again" button (`noncommercial_next_step`, re-reads only), confirmation-email access link, support |

Supporting rules (doc 12 section 5): guessed sequential order IDs and
stale tokens are rejected, never resolved to "the nearest" order; a
public thank-you URL on its own exposes no receipt; identity
(tenant/location/launch/order ownership) is validated before any
render, and a wrong-tenant or wrong-order request reaches an error
state, never another buyer's data.

## 5. Privacy and operational notes for all states

- The host page for any state (including errors and reconciling) must
  send `Cache-Control: private, no-store` and should carry
  `<meta name="robots" content="noindex, nofollow">`. The renderer
  emits this guidance as an HTML comment at the top of every fragment;
  a robots tag alone is not privacy and is never claimed as such
  (doc 12 section 8).
- No PII, order data, or card data in URLs, analytics events, error
  logs, or screenshots for any state. Error fragments contain no order
  data by construction.
- State transitions update the `aria-live` status region; focus is
  never moved or trapped by a state change.
- Duplicate page refreshes are safe: rendering is a read. No state in
  this document can create a duplicate onboarding send or a second
  charge (fulfillment dedupe is S44's, doc 12 section 6; this page
  only consumes state).

## 6. Test coverage

`tests/test_render.py` covers: reconciling (retry + support present,
no buy/new-charge CTA), pending (never "You are all set", base access
preserved), failed-extra (base access preserved, failed labeled),
outage (`Unresolved items` label), and all three error kinds (support
fallback present, no purchased names/amounts — i.e. no sample receipt
— anywhere in the fragment).
