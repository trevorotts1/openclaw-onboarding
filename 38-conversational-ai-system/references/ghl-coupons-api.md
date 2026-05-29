# GHL Coupons API — Reference

> Deep-dive reference for `protocols/discount-code-protocol.md`. The protocol file is the
> behavioral contract; this file is the API surface the agent calls into when generating
> GHL coupons in a sales conversation. All content here is consolidated from the v5.14
> playbook (see `references/v6.0-source-playbook.md` Step 9.26 for the canonical block).

## Endpoint

```
POST https://services.leadconnectorhq.com/payments/coupon
Authorization: Bearer $GHL_API_KEY
Version: 2021-04-15
Content-Type: application/json
```

(Marketplace docs: `marketplace.gohighlevel.com/docs/ghl/payments/create-coupon`)

## Capabilities (CONFIRMED via web research in v5.14)

- Percentage OR fixed-amount discounts
- Validity period (start/end dates)
- Usage limits (max redemptions)
- Restrict to specific products
- Apply to one-time AND recurring (subscription) products
- For subscriptions: option to apply discount to ALL future payments or just first
- Coupon codes are alphanumeric, NOT case-sensitive
- Can auto-generate 7-character codes via API
- IMPORTANT CONSTRAINT: 100% discount only works with Stripe payment processor in GHL — NOT PayPal

## Manual UI path (for operator visibility)

Payments → Coupons → Create Coupon

## Agent usage pattern (governed by `discount-code-protocol.md`)

The agent NEVER creates a coupon as a first response. Coupon creation fires only when:
- Sales conversation reaches a price-objection AND non-discount response was tried first, OR
- Cart abandonment recovery (T8 of Intelligent Follow-up, see `intelligent-followup-protocol.md`), OR
- Win-back flow, OR
- Operator-approved promotional campaign

Per-product policy lives in `<MASTER_FILES_DIR>/KnowledgeBases/products/` (typed knowledge base);
the policy caps max discount %, expiry, and per-customer redemptions. The agent reads policy
BEFORE generating; if policy forbids, the agent does not offer.

## Honesty floor

Never invent a code that wasn't actually generated. Never quote a discount that exceeds
operator policy. Never auto-apply a 100% discount (UI constraint + business risk).

