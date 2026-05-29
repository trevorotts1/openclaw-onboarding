# Stripe Webhooks — Reference

> Deep-dive reference for `protocols/stripe-integration-protocol.md`. Consolidated from
> v5.14 playbook Step 9.27. See `references/v6.0-source-playbook.md` for the canonical block.

## Webhook endpoint exposed by OpenClaw

Skill 29 (GHL Convert and Flow) installs a Cloudflare tunnel ingress for OpenClaw's
`hooks.mappings`. Skill 38 adds a `stripe-events` mapping that receives:

- `checkout.session.completed`
- `invoice.paid`
- `invoice.payment_failed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted` (i.e. canceled)
- `charge.refunded`

## Per-customer GHL ↔ Stripe linkage

A custom field `stripe_customer_id` is added to the GHL location at install time. When
the Stripe webhook fires, OpenClaw looks up the GHL contact by `stripe_customer_id`,
updates tags (paid, refunded, churned), and (per protocol) may kick a follow-up workflow.

## Verification

Stripe signs every webhook with a secret. The Stripe webhook handler in OpenClaw verifies
the `Stripe-Signature` header against `STRIPE_WEBHOOK_SIGNING_SECRET` (stored in
`~/.openclaw/secrets/.env`). Any unverified payload is rejected — no exceptions.

