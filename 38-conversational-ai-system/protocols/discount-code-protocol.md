# Discount Code Generation Protocol

The agent generates discount codes via GHL or Stripe APIs when sales
context warrants, governed by operator-approved policies per product.

## When the agent deploys codes

The agent considers offering a discount code when:

1. **Price objection** during sales conversation (per Step 9.23 Sales Brain)
   AND the agent has tried at least one non-discount response first
   (reframe value, surface ROI)
2. **Cart abandonment** — invoice/quote sent but no payment within 24h,
   typically deployed at T8 of Intelligent Follow-up (day 15)
3. **Win-back** — cold lead returns after 30+ days of silence, may
   warrant a welcome-back code
4. **Promotional campaigns** — proactive outreach (Feature 15 when shipped)
   may generate campaign-specific codes

The agent NEVER offers a discount as a first response to pricing
questions. Codes are a close tool, not a default response.

## Operator-controlled policies (per product)

Each product in `<MASTER_FILES_DIR>/KnowledgeBases/products/` can specify:

```yaml
discount_policy:
  agent_can_auto_generate: true | false  # if false, every code requires operator approval
  max_discount_percent: 20  # never more than 20% off this product
  max_discount_amount: 200  # OR fixed cap in dollars
  allowed_contexts: [price_objection, cart_abandonment, win_back]
  excluded_contexts: [first_message]  # never offer in first 24h
  preferred_codes:
    - id: PRICEOBJ20
      discount: 20%
      use_case: price_objection
    - id: WINBACK15
      discount: 15%
      use_case: win_back
  expiration_default: 48h  # codes the agent generates expire fast (urgency)
```

If a product has no discount policy, the default is conservative: agent
asks operator for approval before generating any code for that product.

## GHL Discount Codes (Coupons API)

Endpoint: `marketplace.gohighlevel.com/docs/ghl/payments/create-coupon`

Confirmed capabilities (research-verified):
- Percentage OR fixed amount discounts
- Validity period (start/end dates)
- Usage limits (max redemptions)
- Restrict to specific products
- One-time AND recurring (subscription) products
- For subscriptions: option to apply to ALL future payments OR just first
- Codes are alphanumeric, not case-sensitive
- Auto-generate 7-character alphanumeric codes via API
- IMPORTANT: 100% discount only works with Stripe processor inside GHL,
  NOT PayPal

Example agent flow (via GHL skill):

```python
ghl_skill.create_coupon(
  location_id=client_location_id,
  name=f"Auto-generated for {contact_name} - price objection",
  discount_type="percentage",
  discount_value=15,
  product_ids=[product_id],
  expiration=now + timedelta(hours=48),
  max_redemptions=1
)
```

If the GHL skill doesn't expose `create_coupon` directly, fallback to
direct API call:

```
POST https://services.leadconnectorhq.com/payments/coupons
Headers:
  Authorization: Bearer <GHL_PRIVATE_INTEGRATION_TOKEN>
  Version: 2021-07-28
Body:
  {
    "altId": "<location_id>",
    "altType": "location",
    "name": "<descriptive name>",
    "discountType": "percentage",
    "discountValue": 15,
    "productIds": ["<product_id>"],
    "validFrom": "<ISO date>",
    "validTo": "<ISO date>",
    "maxRedemptions": 1
  }
```

## Stripe Discount Codes (Coupons + Promotion Codes)

Stripe has TWO related concepts:
- **Coupon** (`POST /v1/coupons`) — underlying discount definition
- **Promotion Code** (`POST /v1/promotion_codes`) — customer-facing code
  that maps to a coupon

Multiple promotion codes can map to one coupon (FALLPROMO and SPRINGPROMO
→ same 25% off coupon).

Two-step flow:

```bash
# Step 1: Create the coupon (or reuse existing)
curl https://api.stripe.com/v1/coupons \
  -u "${STRIPE_SECRET_KEY}:" \
  -d percent_off=15 \
  -d duration=once \
  -d applies_to[products][]="${STRIPE_PRODUCT_ID}"

# Step 2: Create a customer-facing promotion code
curl https://api.stripe.com/v1/promotion_codes \
  -u "${STRIPE_SECRET_KEY}:" \
  -d coupon="${COUPON_ID}" \
  -d code="PRICEOBJ${CONTACT_ID_SHORT}" \
  -d max_redemptions=1 \
  -d expires_at="${EXPIRY_TIMESTAMP}" \
  -d restrictions[first_time_transaction]=false
```

Stripe coupon capabilities (research-verified):
- Percentage off OR fixed amount off
- One-time, repeating (N months), OR forever duration
- Restrict to specific products via `applies_to` array
- Customer-level restrictions (one-per-customer, first-order-only)
- Expiration date
- Maximum redemptions
- Currency-specific amounts for multi-currency stores

## Choosing GHL vs Stripe

For each product, the discount platform is determined by:
1. What payment processor handles this product? (Set in product registry)
2. If GHL handles payment → use GHL coupons
3. If Stripe handles payment directly (outside GHL) → use Stripe promotion codes
4. If both, default to whichever the operator specified as primary

## Agent behavior — generating a code

When the agent decides to deploy a code:

1. Check policy for this product (allowed contexts, max discount, etc.)
2. If policy permits → check for matching preferred code in policy
3. If matching preferred code exists → use that (don't generate new)
4. If no matching preferred code → generate a new code:
   - 7-char alphanumeric (GHL convention)
   - OR specific format (Stripe: `<prefix><contact_id_short>`)
5. Call appropriate API (GHL or Stripe)
6. Save generated code to `<MASTER_FILES_DIR>/discount-codes/<code>.md`
   with metadata (created_by_agent, contact_id, conversation_id,
   product_id, context, expiration)
7. Share with customer in conversation:
   "Tell you what — here's a code that gets you 15% off if you sign up
   today: PRICEOBJ20. Just enter it at checkout. Good for 48 hours."
8. Tag contact with `received-code-<code>` for follow-up tracking

## Cart abandonment recovery deployment

When Intelligent Follow-up (Step 9.25) hits T8 (day 15), it checks if
the stalled product has discount policy allowing cart-abandonment codes.
If yes, generate and offer at T8.

## Honesty floor (from Sales Brain Rule 8)

Never create false urgency. "48-hour expiration" is real (the code
actually expires). "Limited spots" claims are real or not made at all.
Never lie about price comparisons or fabricate "regular price" anchors.

## Allow-list action

Per Step 9.15 allow-list, agent has action 11 (create discount codes
within operator-approved policies). Agent-initiated within policy
limits — not customer-invokable. Customer cannot say "give me a code"
and have the agent comply; the agent makes the deployment decision
based on sales context and policy.
```

**B. Append to Run Manifest:**

```markdown
