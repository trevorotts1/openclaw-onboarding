# Stripe Integration Protocol

Direct Stripe API integration for clients selling outside GHL or
alongside it.

## Capabilities

The agent can do these things via Stripe (within allow-list):

1. **Create payment links** — for product-specific links the agent
   shares in conversation
2. **Create invoices** — for custom amounts or service-based billing
3. **Check payment status** — verify if a customer has paid
4. **Create coupons + promotion codes** — per discount-code-protocol.md
5. **Subscribe to webhooks** — payment events, subscription events,
   refund events flow back into OpenClaw

## Common operations

### Send a payment link

```bash
curl https://api.stripe.com/v1/payment_links \
  -u "${STRIPE_SECRET_KEY}:" \
  -d "line_items[0][price]=${PRICE_ID}" \
  -d "line_items[0][quantity]=1"
```

Response includes a `url` field. Agent shares URL with customer.

### Check if invoice paid

```bash
curl https://api.stripe.com/v1/invoices/${INVOICE_ID} \
  -u "${STRIPE_SECRET_KEY}:"
```

Response `status` field: `paid`, `open`, `void`, `draft`, `uncollectible`.

### Send invoice to customer

```bash
curl https://api.stripe.com/v1/invoices \
  -u "${STRIPE_SECRET_KEY}:" \
  -d "customer=${CUSTOMER_ID}" \
  -d "collection_method=send_invoice" \
  -d "days_until_due=7"

# Then finalize and send:
curl https://api.stripe.com/v1/invoices/${INVOICE_ID}/finalize \
  -u "${STRIPE_SECRET_KEY}:" \
  -X POST

curl https://api.stripe.com/v1/invoices/${INVOICE_ID}/send \
  -u "${STRIPE_SECRET_KEY}:" \
  -X POST
```

## Webhook handling

For real-time payment event awareness:

1. In Stripe Dashboard → Developers → Webhooks → Add endpoint
2. URL: `https://<PUBLIC_HOSTNAME>/hooks/stripe-events`
3. Events to subscribe to:
   - `checkout.session.completed`
   - `invoice.paid`
   - `invoice.payment_failed`
   - `customer.subscription.created`
   - `customer.subscription.canceled`
   - `charge.refunded`
4. Capture Stripe signing secret as `STRIPE_WEBHOOK_SECRET`

Then add `stripe-events` to `hooks.mappings` in openclaw.json:

```json
{
  "id": "stripe-events",
  "messageTemplate": "Stripe event received: {{type}}. Object: {{data.object.id}}. Amount: {{data.object.amount}}. Customer: {{data.object.customer}}. Full payload: {{json data}}",
  "sessionKey": "hook:stripe:{{data.object.customer}}"
}
```

The agent receives Stripe events and handles them per business logic:
- `checkout.session.completed` / `invoice.paid` → tag contact `paid`,
  trigger onboarding workflow (Feature 41 when shipped)
- `invoice.payment_failed` → notify operator, send retry message to customer
- `customer.subscription.canceled` → trigger churn workflow

## Per-customer Stripe customer linkage

When a customer in GHL is also a Stripe customer, link them by storing
the Stripe customer ID in the GHL contact's custom field
`stripe_customer_id`. Agent looks up Stripe data using this link.

If unlinked, agent creates a Stripe customer record when first needed:

```bash
curl https://api.stripe.com/v1/customers \
  -u "${STRIPE_SECRET_KEY}:" \
  -d "email=${EMAIL}" \
  -d "name=${NAME}" \
  -d "metadata[ghl_contact_id]=${CONTACT_ID}"
```

Save the resulting customer ID back to GHL contact's custom field.

## Allow-list update

Per Step 9.15 allow-list, agent gains action 15:
"Create/send Stripe invoices, payment links, and process Stripe webhooks
within operator-approved policies."
```

**B. Hooks.mappings update for Stripe webhooks:**

If operator chose option 2 or 3, add a Stripe webhook mapping to `hooks.mappings` in openclaw.json (covered in protocol document).

**C. Append to Run Manifest:**

```markdown
