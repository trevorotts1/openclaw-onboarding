# Access and Privacy Contract (S82-07)

The security contract for the terminal thank-you page. Spec: packet
doc 12 sections 5 (order resolution and reconciliation), 6
(fulfillment authority) and 8 (privacy, indexing and operational
safety); acceptance: doc 18 A13 and section 7. Enforcement companion:
`scripts/validate_access.py`; resolver-side enforcement lives in
`scripts/thank_you_resolver.py` and is not duplicated here.

## 1. How an order may be resolved

An order view exists only when the order was resolved through one of
two authorities:

1. **Native authenticated context** — the platform's own signed-in
   order/session context, read through a supported adapter (S06/S44
   lanes), or
2. **A short-lived opaque server-side reference** — an unguessable
   token that maps, server-side only, to exactly one order, expires,
   and reveals nothing by itself.

Everything else is not authority and builds nothing:

- **Guessed or sequential order IDs are rejected.** An incrementing
  order number a stranger can enumerate is not a credential. The
  resolver never accepts a bare order ID from the request as proof of
  anything; the reference must resolve server-side to a verified
  snapshot whose tenant/location/launch identity matches this page
  instance.
- **Stale tokens are rejected.** An expired opaque reference, or one
  issued for a different tenant, location, launch, or journey, fails
  closed to the `stale_session` / `wrong_order_reference` error states
  (see `references/states.md`) — never to a best-guess receipt.
- **URL and query claims are never authority.** Names, email
  addresses, `vip=true`, entitlement or offer parameters in a URL
  change nothing and, where they attempt to claim access, are rejected
  by the resolver (`query_string_authority_rejected`).

## 2. The receipt is never public

- A public thank-you URL, on its own, **never exposes a full receipt**
  to anyone who can guess or copy it. Without a resolved authenticated
  context or a live opaque reference, the page shows only the generic
  error/support state — no items, no amounts, no order reference, and
  never a sample receipt.
- Later extras are combined into one view only when native
  order/transaction relationships establish they belong to the **same
  journey**. Purchases are never grouped merely because they share an
  email address, and a returning buyer's historical entitlements stay
  separate from what was just purchased unless explicitly labeled as
  historical.

## 3. Access links and the real security boundary

- Access, download, and scheduling links point **only to the official
  protected membership / download / scheduling destination** for the
  purchased entitlement.
- **The destination must independently authorize the buyer.** The
  destination checks the buyer's own entitlement before serving
  anything. A page-render condition ("we only showed the link to
  buyers") is **never** the security boundary for premium access: a
  copied link must be useless to a non-buyer.
- `validate_access.py` enforces the checkable parts of this against a
  link manifest: every access destination is `https`, every access
  destination declares `destination_independently_authorizes: true`,
  no destination URL carries identity/entitlement claim parameters,
  and every access block is keyed to an entitlement that is actually
  in the verified view. A `mailto:` support link is not an access
  block and is exempt from the https and authorization-flag rules.

## 4. No PII leakage

Customer receipt data must not leak through any side channel:

- **URL parameters** — no buyer name, email, order detail, or
  entitlement claim in any rendered link or in the page URL.
- **Analytics events** — events may carry page/role/status classes,
  never order contents, amounts tied to an identified buyer, email,
  or names.
- **Logs and error logs** — log opaque references, statuses, and error
  codes; never receipt contents, email addresses, or tokens.
- **Screenshots and evidence galleries** — fixtures and test evidence
  use dummy identities only; any approved real test screenshot is
  redacted before it enters an engineering artifact.
- **Shared/public media folders** — receipt imagery is never uploaded
  to a broadly shared media library.
- **Payment card data** — no card number, CVC, expiry, or payment
  token ever appears in HTML, JS state, request/view JSON, logs, or
  evidence. The resolver rejects raw credential fields on sight.

## 5. Caching, indexing, and the shared-computer rule

- Where the hosting mechanism supports it, receipt pages are served
  with **private / no-store** behavior, and the rendered fragment
  carries noindex guidance. This is defense in depth, not the access
  control.
- **A robots `noindex` tag alone is NOT security and is never claimed
  as such.** Indexing controls who finds a page; authorization
  controls who may see the receipt. Only section 1–3 controls are
  security.
- **Shared computer rule:** the page holds no receipt in broadly
  cached HTML or persistent client state. The next visitor on the same
  machine must see nothing of the previous buyer's receipt — no
  items, no amounts, no access links — without that buyer's own
  authenticated context.

## 6. Fixtures

Every fixture, test, and screenshot in this skill uses **TEST ONLY
dummy identities** (`TEST-TENANT`, `TEST-ORDER-0001`, `example.test`
destinations). Fixture IDs are blocked from production publishing; a
fixture view is evidence about code behavior, never about a real
customer.

## 7. What remains live proof (not claimed here)

This contract and `validate_access.py` are offline (L1) evidence.
The following stay named blockers until authorized native proof
exists: that the real native order-read path rejects guessed IDs and
stale tokens in the live environment, and that each real destination
independently authorizes in production. No sample receipt stands in
for either.
