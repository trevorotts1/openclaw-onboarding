# Funnel Completion Checklist (Item 32)

The gated sub-stage inside `ghl-install-test`. A page installed into a funnel
is not delivered until the funnel around it exists and works: the funnel,
its steps, its forms, its pop-ups, its click actions, its order form, and
its products. `scripts/validate_funnel_completion.py` verifies the
per-object receipt `ghl-install-test/funnel-completion.json` and the live
click-through record `ghl-install-test/clickthrough.json` against this
checklist at stage close.

## When the sub-stage applies

Required whenever the intake publish target is GHL, OR any funnel step
binds an externally hosted page by embed. Otherwise the receipt file
records `status: "not_applicable"` with a reason citing the intake values,
and the validator checks that record against the intake.

## Scope note (Amendment 6, C12): a deliberate override

SOP Stage 1B says a missing checkout product is "a separate setup task,"
outside this skill's scope. This sub-stage deliberately OVERRIDES that
boundary for products the order form sells: the funnel cannot complete
without them, so creating a missing product inside the job is part of
funnel completion. The paired SOP text amendment is queued in Item 30; the
checklist, not the old boundary sentence, governs until it lands.

## The checklist

1. The funnel is created, with its steps in the intended order (the
   receipt's `order` fields run consecutively from 1).
2. Every step is bound to its page: a GHL page ID, or an embed URL for an
   externally hosted page (the embed URL is one of Item 34's three
   provenance bindings).
3. Every form is created and attached to its step.
4. Every pop-up is created and wired to the trigger element that opens it.
5. Every click action is connected: element, action, and target recorded,
   and each one actually clicked in the live journey
   (`verified_by_clickthrough: true`).
6. The order form is bound to its step.
7. Every product the order form sells exists before the order form needs
   it. Creation is IDEMPOTENT: an existence check by name and role runs
   first, the receipt records `existence_check: true` and `created:
   true/false` per object, and creating a duplicate of an object that
   already exists is a checklist FAILURE, not a shortcut. This applies to
   the funnel, its forms, and its products alike.
8. Payment provider presence is checked and recorded as a boolean only
   (`payment.provider_present`). Presence, never credential material.

## Rails (Amendment 5A, final)

Each object in the receipt carries its own `rail`, and the validator
enforces this table. It comes from the primary-source research verdict in
Amendment 5A (as of October 2026 there is no documented API or official
MCP path to create a funnel, add steps, or write funnel page content), not
from preference:

| Object | Rail |
|---|---|
| Funnel creation | browser |
| Steps, ordering, page content | browser |
| Step bindings (page or embed) | browser |
| Form creation and attachment | browser |
| Pop-ups | browser |
| Click actions | browser |
| Order-form binding | browser |
| Product attachment inside an order-form page | browser |
| Product creation (full CRUD incl. prices) | api |
| Funnel redirects | api |
| Custom values | api |
| Tags (create) | api |

Browser-rail work runs under the Browser Engine Contract
(`references/browser-engine-contract.md`): isolated named sessions,
launch, seed, act, capture, teardown, reap.

## The live click-through (closing evidence)

Setup claims do not close this sub-stage; a clicked visitor journey does.
The journey runs in the stage's browser session and is recorded in
`ghl-install-test/clickthrough.json`, with named screenshots under
`ghl-install-test/evidence/`:

- step 1 loads;
- the primary CTA is clicked;
- the pop-up opens;
- the form displays and is test-submitted under Item 5's test-contact
  rules;
- the journey advances to the order step, which must RENDER the product
  and the price (the record names the product ID and the price shown, and
  they must match the receipt's products array);
- a booking step, when present, must render its calendar.

Two SOP Stage 13 rules ride in this record BY NAME:

- **Once-only form submission:** a shared form is submitted only ONCE,
  with a designated test contact (`form_submission.submissions_count`
  must be exactly 1).
- **No live charge:** sales are verified in test mode only
  (`live_charge_made` must be false). Never make an unauthorized live
  charge to prove a checkout works.

## Outputs

- `ghl-install-test/funnel-completion.json`: the per-object receipt
  (`funnel`, `steps`, `forms`, `popups`, `click_actions`, `order_forms`,
  `products`, `payment`, plus optional `redirects`, `custom_values`,
  `tags`), mirrored into the install receipt's summary.
- `ghl-install-test/clickthrough.json`: the journey record.
- `handoff/automation-handoff.json` (Item 31): its form IDs come from
  THIS receipt's `forms` array and from nowhere else; the gate refuses
  the close when they disagree.
