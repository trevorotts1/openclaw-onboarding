# Abandoned Cart Recovery Sequence

**id:** `abandoned-cart-recovery` · **category:** sales-close-sequences
**Aliases:** checkout abandonment, cart recovery, 2-step order recovery, incomplete checkout sequence, order form abandonment
**Source:** DotCom Secrets (Brunson — 2-Step Order Form design: Step 1 captures email BEFORE billing, enabling recovery; 'no abandoned-cart follow-up = dead funnel') · The Funnel Hacker's Cookbook (Brunson — 2-Step Tripwire: Step 1 abandonment is a recoverable lead) · Marketing Secrets Blackbook (Brunson — 'whoever can spend the most to acquire a customer wins'; recovery has zero extra CAC) · Copywriting Secrets (Edwards — PAS for hesitation friction, guarantee block, hot-traffic short copy, single CTA)

> **The highest-intent non-buyer on the list.** Someone who reached the checkout page and entered their email (Step 1 of Brunson's 2-step order form) but did not complete payment (Step 2). They were sold enough to start — something stopped them at the last moment. The recovery sequence addresses the four real stop-points: technical glitch, distraction, price hesitation, or fear of regret.
>
> **Why the 2-step form matters here:** Brunson's 2-step order form captures the email address on Step 1 (contact/shipping info) BEFORE asking for billing info on Step 2. This is the mechanism that makes recovery possible. Without this design, the abandoning prospect is lost forever.

---

## FLEXIBILITY PRINCIPLE

This template is a **guide and a resource, never a rule or a requirement.** Three operating modes:

| Mode | What the system does |
|------|---------------------|
| **User has an explicit desire** | Build exactly what the user specifies. This template is optional reference only — never impose it. |
| **User is unsure** | Present the ROI case (highest-intent leads, zero extra CAC), explain each step, let the user decide. |
| **User wants it handled ("just do it")** | Execute the full template adapted to the user's offer and cart. |

Always overridable, skippable, customizable.

---

## TRIGGER
- 2-step order form: **Step 1 submitted (email captured) BUT Step 2 not submitted within 15–30 minutes.**
- GHL mechanic: `checkout-started` tag added WITHOUT `buyer-[offer]` tag within the timeout window.

**Entry condition:** Contact has email; `checkout-started` tag present; `buyer-[offer]` tag absent. Offer/cart is still open.
**Exit:** Purchase at any step → buyer onboarding, STOP recovery. Cart closes without purchase → optional downsell, then Seinfeld Daily Sequence.

> **Fire immediately.** Every hour of delay reduces recovery rate significantly. Mobile users who abandoned due to distraction are often recoverable within 30–60 minutes.

## CHANNELS
Email (all steps, primary) · SMS (Step 1 immediate nudge — critical for mobile abandons) · Facebook/Instagram Message (optional mirror of the immediate nudge)

## CADENCE
3 emails in 48 hours maximum.
- **Immediate:** within 30–60 minutes
- **Day 1:** +24 hours
- **Day 2 (optional):** +48 hours, only if cart still open and no purchase

---

## COPY PRINCIPLE — HOT TRAFFIC RULE (Edwards)

These contacts are **hot traffic.** They already heard the pitch. They already got to checkout. **Do NOT run a new Soap Opera Sequence or a full Stack.** Lead with the product and the friction they may have hit. Short, direct, empathetic. One CTA. Guarantee front and center. This is not a persuasion sequence — it is a friction-removal service.

---

## THE SEQUENCE

| Step | Timing | Beat | Subject angle | Body framework | Persona |
|------|--------|------|---------------|----------------|---------|
| 1 | Immediate (30–60 min) | **"Did something go wrong?"** — assume it was a technical glitch first. Non-pushy, earns goodwill, catches real technical abandonments. Give a direct link back to the cart + 1-sentence guarantee. | "Did something go wrong with your order?" / "Your [offer] order is waiting" | Empathy line → offer reminder → direct checkout link → 1-sentence guarantee → P.S. with link. SMS: same, 1 line + link. | Edwards hot-traffic: short, product + reassurance |
| 2 | Day 1 (+24h) | **Benefit reminder + Guarantee expansion.** For the 'second thoughts' buyer. One hero benefit with 'which means' (Edwards bullet). Then the guarantee restated in full: what's covered, time frame, how to claim. Then one brief testimonial. Then the link. | "One thing I want you to know before you decide" / "[Customer] had the same hesitation…" | 'You were a moment away from [result].' → hero benefit (Feature + Benefit + 'which means') → full guarantee block → brief testimonial (Before → After → time) → link. P.S.: 'Reply if something went wrong technically.' | Edwards Ultimate Bullet + guarantee; Brunson Third-Person Testimonial |
| 3 | Day 2 (+48h) — only if cart still open | **Final recovery + light urgency.** Cart-close date/time. One outcome sentence. Guarantee in one sentence. Scarcity lever(s) only if genuinely real. Easy yes. | "Your spot is still available — closes [date]" / "Last chance to finish your order" | 'Your order is still incomplete, and [offer] closes [date/time].' → 2 sentences on what they get → scarcity facts (if real) → guarantee line → link. P.S.: 'Questions? Reply — I'll answer before [deadline].' | Blackbook S51 (light, honest); Edwards short close |
| 4 | Post-sequence | **Branch by outcome:** Buyers → buyer onboarding. Cart closed, no purchase → 'cart is now closed' note + optional downsell → Seinfeld. Cart still open, no purchase → merge back into main launch sequence at current urgency phase. | — | Buyer: confirmation + access. Non-buyer: downsell or Seinfeld enrollment. | Brunson Stack Don't Switch; deadline was real |

---

## GHL BUILD (Skill 44 → GoHighLevel)
**Workflow:** `Abandoned Cart Recovery — [Offer Name]` (separate from the main launch sequence)

1. **Trigger:** `Tag Added = checkout-started`.
2. **Wait 30 minutes.** `If/Else`: has `buyer-[offer]`? YES → exit (no recovery needed). NO → continue.
3. **Step 1 email + SMS** simultaneously.
4. **Wait 24h.** `If/Else`: buyer? YES → exit. NO → Step 2 email.
5. **Wait 24h.** `If/Else`: (a) buyer → exit; (b) `cart-close-datetime` passed → send closed-cart email + optional downsell → Seinfeld; (c) cart still open → Step 3 email.
6. **Post-Step 3:** `If/Else`: buyer → exit; non-buyer + cart still open → merge into launch sequence urgency phase; non-buyer + cart closed → Seinfeld enrollment.

**Purchase Goal** (`buyer-[offer]`) is wired at every step — the moment a purchase occurs, ALL recovery emails stop and buyer onboarding begins.

**GHL notes:** Build as a SEPARATE workflow from the main launch sequence. The `checkout-started` tag should be added by the GHL order form when Step 1 is submitted. The checkout link in recovery emails should point back to the same order form page (GHL can pre-fill contact data via URL params). Mirror Step 1 in SMS — mobile abandoners are most likely to re-engage within 60 minutes.

## INTEGRITY GUARDRAILS
- Guarantee stated in recovery emails must exactly match the actual offer guarantee.
- Do not fabricate urgency/scarcity if none is real (Edwards: "never invent scarcity you won't honor"). If cart has no deadline, omit scarcity from Day 2.
- Do not send recovery emails after the cart has genuinely closed for non-buyers — send the 'closed' acknowledgment instead.
- Maximum 3 recovery emails in 48 hours. Recovery is a service, not harassment.

## KPIs
Recovery rate: % of `checkout-started` who purchase · Step-1 vs. Step-2 vs. Step-3 recovery comparison · Revenue recovered per abandoned cart attempt · Time-to-recovery distribution · SMS vs. email open/recover comparison
