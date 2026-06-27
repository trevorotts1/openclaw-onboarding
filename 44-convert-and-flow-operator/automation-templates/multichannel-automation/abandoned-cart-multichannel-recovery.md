# Abandoned Cart Multichannel Recovery (2-Step Order Form Drop-Off)

- **id:** `abandoned-cart-multichannel-recovery`
- **Category:** multichannel-automation
- **Aliases:** Cart Abandonment Follow-Up · 2-Step Form Drop-Off Sequence · Step 1 Not Step 2 Recovery · Incomplete Checkout Recovery · Lost Sale Recovery Sequence
- **Source:** Funnel Hacker's Cookbook — 2-Step Order Form element: "If the customer fills out Step 1 but not Step 2, you can trigger a follow up sequence to get them to go back and finish Step 2." Supporting: Marketing Secrets Blackbook Secret #49, FHC 2-Step Order Form, BRUNSON-FUNNEL-LIBRARY Entry #8.

> "Abandoned carts is one of the places where people lose the most money in a sales funnel. A two-step order form gives you the ability to follow up with people who don't complete the checkout process." — The Funnel Hacker's Cookbook

> "If they give you their email address but don't buy, contact them with an email or text or messenger sequence." — Marketing Secrets Blackbook, Secret #49

## What it is
The 2-step order form captures name + email in Step 1 before asking for payment in Step 2. If Step 2 is never completed, the email is already captured and a multichannel recovery sequence can fire. Email is the primary channel. SMS nudges for non-openers. Messenger for subscribed contacts. Every step checks for a purchase before sending — the moment they buy, every message stops and they route to onboarding.

## TRIGGER
- **What starts it:** 2-step order form Step 1 submitted + Step 2 NOT completed within 30–60 min.
- **GHL trigger:** Form Submitted on Step 1 → Wait 30 min → If/Else: `purchased-[offer-id]` NOT present → enter sequence.
- **Re-entry guard:** Tags `cart-abandon-started` NOT present AND `purchased-[offer-id]` NOT present.

## CHANNELS
Email (primary) · SMS (secondary, on non-open) · Facebook Messenger (tertiary, if subscribed)

## THE SEQUENCE

| Step | Delay | Channel | Job |
|------|-------|---------|-----|
| 1 | +30–60 min (after abandon confirmed) | Email | "You left something behind" — soft recovery, direct link back to cart |
| 2 | +2h | SMS + Messenger (if email not opened) | Short nudge, direct link, helpful tone |
| 3 | +24h | Email | Story/objection-handle email — addresses the most common hesitation |
| 4 | +48h | SMS + Messenger | Light urgency touch (REAL urgency only) |
| 5 | +72h | Email | Final call — graceful close, door left open |
| 6 | Any point | Buyer cleanup | Purchase fires → stop all sequences → buyer onboarding |

**Purchase check before every step — if purchased, skip the step and exit to buyer onboarding.**

---

### Step 1 — +30–60 min: "You Left Something Behind" Email
**Subject:** `Did something come up? Your [offer name] is waiting for you`  
**Body:**
- Soft opening: "Hey [name] — looks like something came up before you finished."
- Low-pressure: "Your order is still here."
- One-line value reminder: what they were about to get + key benefit
- Direct link back to Step 2 checkout
- Friction reducer: guarantee / ease of setup / fast delivery
- Personal AC sign-off

---

### Step 2 — +2h: Email Open Branch → SMS + Messenger (if not opened)
**Condition:** Email NOT opened within 2h → send SMS + Messenger.

**SMS:** `Hey [name] — [AC name] here. You started grabbing [offer] a bit ago. Here to finish if you want: [link]. No pressure at all.`

**Messenger:** `Hey [name] — you were grabbing [offer] earlier! Here's the link to finish up if you want: [link]. Happy to answer any questions.`

*Email opened = skip this step entirely. Let the email work.*

---

### Step 3 — +24h: Story/Objection Handle Email
**Subject:** `The #1 thing people worry about with [offer] (and what actually happens)`  
**Body:**
- Empathy for the hesitation: "I know this kind of decision can feel like a lot. Here's what I've seen..."
- Short parable or customer story addressing the likely objection
- Reveal the positive outcome despite the hesitation
- Restate guarantee / risk-reversal
- Link back to checkout

---

### Step 4 — +48h: SMS + Messenger Urgency (REAL urgency only)
**Condition:** purchased check first. Only send if not yet purchased.  
**SMS:** `Hey [name] — quick heads-up: [genuine reason — discount expires [date] / X spots left / cohort starts [date]]. Link: [short link]. No worries if timing isn't right.`

> **Brunson rule:** "Whatever the reason, it needs to be real. Fake urgency will backfire on you, and you'll lose all credibility." — DotCom Secrets. If there is no real scarcity, frame as a genuine check-in, not a countdown.

---

### Step 5 — +72h: Last Call Email
**Subject:** `Last note about [offer name]`  
**Body:**
- "This is my last message about [offer]. I don't want to fill your inbox."
- One-line value summary
- Real deadline if it exists; otherwise: "Whenever timing is right, the link will still be here: [link]"
- Graceful close: "Either way, I'll still be sending you [value/content]. Talk soon."

---

### Step 6 — Purchase Event (any point): Stop and Route
**Actions:** Add `purchased-[offer-id]`; remove `cart-abandon-started`; stop all abandon sequence nodes; send purchase confirmation; remove from retargeting audience D; start buyer onboarding.

---

## COPY PERSONA + SCRIPT
- **Tone:** Helpful, personal, low-pressure throughout. The AC is a trusted guide who noticed the prospect left — not a pushy salesperson.
- **Voice:** First person, casual, personal sign-off. No corporate language.
- **Email length:** 150–300 words max. Short paragraphs. White space. One CTA per email. The email's only job is the click back to the cart.

## FLEXIBILITY — Core Principle

> This template is a **GUIDE and a RESOURCE, never a rule or requirement.** It must not dominate the user's desire.

| Mode | When it applies | What the system does |
|------|----------------|----------------------|
| **1 — Explicit desire** | User wants a custom cart recovery flow | Do exactly that. Template is reference only. |
| **2 — User is unsure** | User asks how to handle cart abandons | Suggest 3-email + 2-SMS framework with purchase-check gates; let user decide. |
| **3 — Just do it** | "Build the cart recovery" | Build all 5 steps with purchase checks and channel guards as described. |

Timing gaps (30 min, 2h, 24h, 48h, 72h) are recommended defaults. Adjust for offer type and price point — high-ticket may compress; subscriptions may extend.

---

## GHL BUILD (Skill 44 — Convert & Flow Operator)

**Dependencies first:**
- **Tags:** `cart-abandon-started`, `purchased-[offer-id]`, `messenger-subscribed`, `sms-subscribed`
- **Custom values:** `{{cart_page_url}}`, `{{offer_name}}`, `{{guarantee_statement}}`, `{{urgency_reason}}`

**Workflow nodes:**
1. Trigger: Form Submitted (Step 1 order form)
2. Wait 30–60 min
3. If/Else: `purchased-[offer-id]` NOT present → continue; else exit
4. Add Tag `cart-abandon-started`
5. Email `CA-01 You Left Something Behind` (immediate)
6. Wait 2 hours
7. If/Else: purchased? Yes → exit; No → If email opened in 2h? Yes → skip; No → SMS `CA-S01 Nudge` + (if `messenger-subscribed`) Messenger `CA-M01`
8. Wait 22 hours (total 24h)
9. If/Else: purchased? Yes → exit; No → Email `CA-02 Story/Objection Handle`
10. Wait 24 hours (total 48h)
11. If/Else: purchased? Yes → exit; No → SMS `CA-S02 Urgency` + (if subscribed) Messenger `CA-M02`
12. Wait 24 hours (total 72h)
13. If/Else: purchased? Yes → exit; No → Email `CA-03 Last Call`
14. Remove Tag `cart-abandon-started`

**Purchase interrupt (at any point):** Add `purchased-[offer-id]`; remove `cart-abandon-started`; stop active nodes; start buyer onboarding.

**Skill 44 notes:** Set `order` + `parentKey` on every node before first save. Templates: Email CA-01..CA-03 in GHL Email Builder; SMS CA-S01..CA-S02; Messenger CA-M01..CA-M02.
