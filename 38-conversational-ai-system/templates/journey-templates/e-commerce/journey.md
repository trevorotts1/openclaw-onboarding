# Customer Journey Template — E-commerce

This template defines the workflows a complete e-commerce store (physical or
digital goods) should have. Per the playbook, e-commerce is transaction-heavy
and repeat-purchase-driven — less "session/engagement", more transactional
touchpoints plus reorder. (Source bullet: add Order Confirmation, Shipping
Updates, Delivery Confirmation, Review Request workflows.)

## Pre-purchase workflows

### 1. Product Question / Pre-Sale
**Trigger:** Shopper asks about sizing, materials, availability, shipping time,
or "which one should I get"
**Purpose:** Remove the purchase blocker fast and steer to the right SKU
**Conversation phases:**
- Phase 1 — Answer from the product Knowledge Source (specs, sizing, stock)
- Phase 2 — Recommend the right variant for their use; surface shipping ETA
- Phase 3 — Offer the direct add-to-cart / checkout link
**Success action:** Cart link sent; tag `pre-sale-<category>`

### 2. Cart Abandonment Recovery
**Trigger:** Items added to cart, no checkout within a few hours
**Purpose:** Recover the most common lost revenue in e-commerce
**Conversation phases:**
- Phase 1 — Friendly nudge ("your items are still here")
- Phase 2 — Resolve hesitation (shipping cost, sizing doubt, payment)
- Phase 3 — Offer a first-order incentive only if policy permits (via F28)
**Success action:** Checkout recovered; tag `cart-recovered`

## Purchase moment workflows

### 3. Order Confirmation
**Trigger:** Order placed / payment captured
**Purpose:** Instant reassurance + set delivery expectations
**Conversation phases:**
- Phase 1 — Confirm order # + items within 1 minute
- Phase 2 — State the expected ship window and where updates will come from
**Success action:** Confirmation delivered; tag `order-placed`

## Onboarding / fulfillment workflows

### 4. Shipping Updates
**Trigger:** Carrier status changes (label created, in transit, out for delivery)
**Purpose:** Proactive tracking so customers don't open "where is my order"
tickets
**Conversation phases:**
- Phase 1 — Shipped: tracking link + revised ETA
- Phase 2 — Out for delivery: heads-up to be available
**Success action:** Tracking pushed at each milestone; tag `shipped`

### 5. Delivery Confirmation
**Trigger:** Carrier marks delivered
**Purpose:** Close the loop, catch problems early, set up the review ask
**Conversation phases:**
- Phase 1 — Confirm delivery; ask "did it arrive in good shape?"
- Phase 2 — If a problem (damaged/wrong/missing) → open the resolution path
  immediately (no friction)
**Success action:** Delivery confirmed OR issue escalated to support; tag
`delivered` or `delivery-issue`

## Engagement / post-purchase workflows

### 6. Review Request
**Trigger:** Delivered + a usage window passed (e.g. 5-7 days), no open issue
**Purpose:** Convert a happy delivery into social proof + UGC
**Conversation phases:**
- Phase 1 — Ask for a rating/review with a one-tap link
- Phase 2 — On a high rating → ask for a photo/UGC; on a low rating → route to
  support to make it right BEFORE it becomes a public review
**Success action:** Review collected (feeds knowledge base/marketing) or
recovery ticket opened; tag `review-requested`

### 7. Returns / Exchange Handling
**Trigger:** Customer asks to return, exchange, or reports a defect
**Purpose:** Make returns painless to protect lifetime value
**Conversation phases:**
- Phase 1 — Acknowledge; pull the order; confirm eligibility per policy
- Phase 2 — Issue the return/exchange path; set expectations
**Success action:** Return/exchange initiated per policy; never promise refunds
outside policy without operator approval (honesty floor); tag `return-initiated`

## Retention workflows

### 8. Reorder / Replenishment
**Trigger:** Consumable product's typical run-out window approaches, OR 60-90
days post-purchase
**Purpose:** Drive repeat purchase — the core e-commerce profit lever
**Conversation phases:**
- Phase 1 — "Running low?" reminder with a one-tap reorder
- Phase 2 — Offer subscribe-and-save if available
**Success action:** Reorder link / subscription offered; tag `reorder-prompt`

### 9. VIP / Loyalty
**Trigger:** Customer crosses an order-count or spend threshold
**Purpose:** Reward and retain the highest-value buyers
**Conversation phases:**
- Phase 1 — Recognize their status; offer early access / loyalty perk
**Success action:** Loyalty perk delivered (via F28 if a discount, per policy);
tag `vip`

## Win-back workflows

### 10. Lapsed-Buyer Win-Back
**Trigger:** No purchase in 120+ days
**Purpose:** Re-activate dormant customers before they're gone
**Conversation phases:**
- Phase 1 — "We miss you" with what's new / best-seller
- Phase 2 — Time-boxed win-back incentive (via F28 if policy permits)
**Success action:** Win-back offer sent; tag `win-back`

## Notes on E-commerce-specific tone

- Be fast and transactional on confirmations/shipping; be warm and human on
  problems and reviews.
- Never let a delivery problem sit — instant resolution path protects reviews
  and lifetime value.
- Discounts only via per-product policy (F28); never invent codes.
- Match the brand voice from Business Brain (playful DTC vs premium/minimal).
