# GHL delivery spec (commerce)

Governs the native checkout, order-bump and one-click upsell code that the
GHL delivery skills share. Implementation lives in numbered skill dirs
(table below); the code docstrings cite the section names in this file.

## Module locations

| Module | Lives in | Old path (thin re-export only) |
|---|---|---|
| `order_components.py` | `06-ghl-install-pages/tools/` | `skills/06-ghl-delivery/` |
| `order_bumps.py` | `79-signature-order-form/scripts/` | `skills/79-checkout/` |
| `native_upsell.py` | `80-signature-upsell/components/binding/` | `skills/80-upsell/` |

`shared-utils/skills/discovery_aliases.py` (`COMMERCE_MODULES`) is the one map
of these locations. A fresh install of a numbered skill dir carries its module;
the old `skills/` paths exist so nothing that imports them breaks and are
never the implementation.

## Commerce (W8) — native reality, no counterfeit controls

1. Products and prices attach their returned native IDs to native checkout
   components. Catalog creation is NOT checkout binding.
2. Bumps attach to the right native checkout with accurate terms (integer
   minor units, currency, billing type, recurrence) and an intentional
   selection state: a bump is attached unselected and changes only by an
   explicit select/deselect. Never silently preselected.
3. Native totals add and remove with selection. The component family's
   multiple-bump and recurring-product limits are declared by the caller from
   the capability inventory, never invented, and exceeding them fails closed.
4. The documented native one-click upsell flow is V2-funnel only. Websites
   route purchases into a supported V2 purchase funnel.
5. A front-end click is never purchase proof. A paid outcome settles only on
   authoritative native read-back; a timeout is never a decline; an unknown
   capability is never assumed supported.
6. No raw card collection or storage, no token copying, no replayed charges,
   no simulated payment success.

## Confirmed gaps

1. Catalog IDs alone never prove a binding: attachment is verified by
   component read-back.
2. States (Required, Hidden, selected) are SET to the requested true/false and
   READ BACK. A blind toggle is impossible; a read-back mismatch is refused
   and recorded `mismatch-refused`, never claimed bound.
3. Every operation names an explicit tab and frame. A duplicate component id
   is refused, never resolved by first match.
4. Raw card data never reaches a component (guard below).
5. An unknown skill or module name resolves to nothing (fail closed).

## Browser driver

There is exactly one concrete driver: `BrowserManagerDriver` in
`06-ghl-install-pages/tools/order_components.py`. It reaches the browser only
through `06-ghl-install-pages/tools/browser_manager.sh eval` (the single
agent-browser gateway: lock, session, TTL, teardown). It does not call
agent-browser directly, and no second driver is added.

Each call evaluates the in-page bridge `window.__ocOrderComponents(request)`
with `{op, tab_id, frame_id, ...}` and expects `{"ok": true, "result": ...}` or
`{"ok": false, "error": <code>}`. Ops: `list_components`, `get_state`,
`set_state`. A non-zero exit, non-JSON reply, malformed reply, `ambiguous` or
`bridge-missing` is raised; it is never defaulted and never reported as done.
Verification is the executor's job (set, read back, compare), not the driver's.

## Card-data guard (`assert_no_card_data`)

Refuses a key whose segments name card data (`pan`, `cardnumber` /
`card_number` / `cardNumber`, `cvv`, `cvc`, `securitycode`, `expiry`,
`exp_month`, `exp_year`, `track1`, `track2`) at any depth including inside
lists, and any string value holding a Luhn-valid 13-19 digit run (spaces or
hyphens allowed) under any key. Keys match by segment, so `company_name` and
`japan` pass. Known ceiling: strings only; a Luhn-valid 13-digit id inside
free text is refused (safe side).

## Billing vocabulary

One set: `one_time`, `recurring`, `installment`, `trial`, taken from the upsell
request contract that `80-signature-upsell/components/adapters/adapter_common.py`
loads (`REQUEST_SCHEMA_PATH`). `extra_offer_binding.py` derives `BILLING_TYPES`
from it and `native_upsell.py` imports that name, so the wrapper and the
binding core cannot disagree. Every type except `one_time` requires
`recurring_terms`; `one_time` forbids them. The order-bump price vocabulary
(`one_time`, `recurring`, `trial_then_recurring`) is a catalog price shape, a
separate vocabulary from the upsell disclosure above.

## Proof levels and open items

- Fixture level: `BrowserManagerDriver` replays a recorded transcript of
  `browser_manager.sh eval` calls (self-check and `test_order_components.py`).
- Not live: the funnel order-form step has not been captured in a browser, so
  the bridge is not installed on a real page and every live call reports
  `bridge-missing` (capability incomplete). Live capture needs the approved
  test location (open decision CHK-19/S06-02); the checkout surface chosen is
  the GHL funnel order-form step.
