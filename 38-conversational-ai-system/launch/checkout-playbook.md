# Checkout playbook — one link, verbatim

Applies when `conversation_ai.mode` is `checkout` or `full`.

## The only checkout artifact

`offer.checkout_url`. That is the entire checkout surface this lane may use. It is
sent exactly as it appears in the plan:

- No trailing slash added or removed.
- No query parameters, UTM tags, or tracking appended.
- No shortener, redirect, or link wrapper.
- No construction from a slug, an offer name, or the landing/sales page.
- No substitution of `offer.sales_page_url`, `offer.landing_url`, or
  `offer.thank_you_url` when the checkout URL is missing.

`offer.thank_you_url` is the post-purchase destination. It is not a checkout link and
is never sent to a buyer as one.

## When to send it

Send the link when the customer signals purchase intent:

- "How do I buy / sign up / get started?"
- "Send me the link."
- "I'm ready."
- A payment-plan question, after the plan answer from the FAQ playbook.

Send it once per intent. Do not repeat it in every reply, and do not append a sales
pitch to it. One line with the link, then stop or resume the current step.

## Price at checkout

Any price the bot states matches `offer.price_usd` + `offer.currency` exactly. The
checkout page shows the authoritative total. If the customer reports a different
number on the page, the bot does not confirm, correct, or negotiate it; it escalates
to the operator.

`payment_plans: true` means options exist at checkout. This lane does not know the
installment amount, count, or schedule, and never states one.

## Unavailable checkout

If `offer.checkout_url` is `null`:

1. Do not send any link.
2. Say the checkout link is not available yet.
3. Escalate to the operator.
4. Do not offer to take payment another way, do not take card details, and do not
   promise a time when the link will exist.

A launch whose mode is `checkout` or `full` with a `null` checkout URL is a planning
gap, not something the bot papers over.

## Purchase state

The bot never declares a purchase successful. Only the CRM's payment record does.

- "Did my payment go through?" → check the location record; if unavailable, escalate.
- Never ask for or accept card numbers, CVVs, or bank details in any channel.
- Never claim access has been granted before the payment record exists.
- Post-purchase access is `offer.thank_you_url` when present; otherwise escalate.

## Self-check before shipping

- [ ] The emitted playbook contains no literal URL; it reads `offer.checkout_url`.
- [ ] The null path sends nothing and escalates.
- [ ] No URL is modified or wrapped.
- [ ] Price assertions match `offer.price_usd` and `offer.currency`.
- [ ] No payment-plan amount, count, or schedule is stated.
- [ ] No purchase-success or access-granted claim is made by the bot.
