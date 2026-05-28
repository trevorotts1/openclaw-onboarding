# Stripe Coupons + Promotion Codes API — Reference

> Deep-dive reference for `protocols/discount-code-protocol.md` AND
> `protocols/stripe-integration-protocol.md`. Consolidated from v5.14 playbook
> (see `references/v5.14-source-playbook.md` Steps 9.26 + 9.27 for canonical blocks).

## Two related Stripe concepts

- **Coupon** (`POST /v1/coupons`) — the underlying discount DEFINITION
  (percentage OR fixed-amount, duration: once / repeating N months / forever)
- **Promotion Code** (`POST /v1/promotion_codes`) — the customer-facing CODE
  that maps to a coupon. Multiple promotion codes can point to one coupon
  (FALLPROMO and SPRINGPROMO → same 25%-off coupon).

## Capabilities (CONFIRMED via web research in v5.14)

- Percentage off OR fixed-amount off
- One-time, repeating (N months), or forever duration
- Restrict to specific products via `applies_to` array
- Customer-level restrictions (one-per-customer, first-order-only)
- Expiration date
- Maximum redemptions
- Currency-specific amounts for multi-currency stores
- Auto-generated OR operator-specified code

## Standard endpoints

```
POST https://api.stripe.com/v1/coupons
POST https://api.stripe.com/v1/promotion_codes
GET  https://api.stripe.com/v1/promotion_codes/{id}
```

`Authorization: Bearer $STRIPE_API_KEY`

## Agent usage pattern

Same governance as GHL coupons (see `ghl-coupons-api.md`): policy-driven, never first
response, honesty floor enforced. The agent picks GHL coupons when payment runs through
GHL's processor; Stripe coupons when the operator has a Stripe-direct funnel (per
`stripe-integration-protocol.md`).

