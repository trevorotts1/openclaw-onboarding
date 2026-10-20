# Abandoned Checkout Recovery (Started, Unpaid)

- **id:** `abandoned-checkout-recovery`
- **Lane:** `launch-b`
- **Template:** `abandoned-cart-multichannel-recovery` (`44-convert-and-flow-operator/automation-templates/multichannel-automation/`)
- **Category:** multichannel-automation
- **Source:** Funnel Hacker's Cookbook (2-Step Order Form) + Marketing Secrets Blackbook, Secret #49

## What it is

Recovery for contacts who **started checkout and stayed unpaid**. Checkout start captures the
contact before payment; the abandon window is 30 minutes of no purchase. The sequence moves
through email, SMS, and Messenger over 72 hours.

**Hard rule:** the purchase tag is checked before every send, and the purchase event stops every
node in this lane. A contact who buys receives no further abandonment message.

**Draft only:** every workflow and every trigger is written as a draft; `CAF_DRAFT_ONLY` keeps
`active` off. Nothing sends, nothing goes live. Live switch-on is a separate client approval.

## TRIGGER — started, unpaid

- **Starts when:** checkout started (Step 1 contact details captured) and still unpaid after 30 minutes.
- **GHL trigger:** Form Submitted on Step 1 -> Wait 30 min -> If/Else `purchased-[offer-id]` NOT present -> enter.
- **Re-entry guard:** enter only if `cart-abandon-started` NOT present AND `purchased-[offer-id]` NOT present.
- **Fires:** once per contact per offer.

## STOP ON PURCHASE

- Every step starts with a purchase check. Purchased = exit to buyer onboarding, no send.
- The purchase event (any point) runs: add `purchased-[offer-id]`, remove `cart-abandon-started`,
  stop all lane nodes, remove from retargeting audience D, start buyer onboarding.
- No abandonment message may send after a purchase, including queued sends.

## CHANNELS

Email (primary) · SMS (secondary, only when email not opened) · Facebook Messenger (tertiary, only if `messenger-subscribed`)

## THE SEQUENCE

| Step | Delay | Channel | Job |
|------|-------|---------|-----|
| 1 | +30 min after checkout start, still unpaid | Email | "You left something behind" with a direct link back to checkout |
| 2 | +2h | SMS + Messenger (only if email not opened) | Short nudge, direct link, no pitch |
| 3 | +24h | Email | Story / objection handle, restate guarantee |
| 4 | +48h | SMS + Messenger | Light urgency — real reason only |
| 5 | +72h | Email | Last call, graceful close |
| 6 | Any point | System | Purchase event — stop all, route to onboarding |

---

### Step 1 — +30 min: "You Left Something Behind"

**Subject:** `Did something come up? Your [offer name] is waiting for you`

- "Hey [name] — looks like you started checking out [offer name] and something came up before you finished."
- "No worries — your order is still here."
- One-line value reminder plus the key benefit
- Direct link back: `{{checkout_url}}`
- Friction reducer: `{{guarantee_statement}}`
- Personal sign-off from the AC

---

### Step 2 — +2h: Email Not Opened -> SMS + Messenger

**Condition:** purchase check first. Then: email opened -> skip. Not opened -> send.

**SMS:** `Hey [name] — [AC name] here. You started grabbing [offer] a bit ago. Here is the link to finish: {{checkout_url}}. No pressure at all.`

**Messenger:** `Hey [name] — you were grabbing [offer] earlier! Here is the link to finish up if you want: {{checkout_url}}. Happy to help if you have any questions.`

Gate SMS on `sms-subscribed` and Messenger on `messenger-subscribed`.

---

### Step 3 — +24h: Story / Objection Handle

**Subject:** `The #1 thing people worry about with [offer name] (and what actually happens)`

- Empathy for the hesitation
- Short customer story naming the objection and resolving it
- Restate the guarantee
- Link back to checkout

---

### Step 4 — +48h: SMS + Messenger Urgency

**Condition:** purchase check first. Send only with a real reason.

**SMS:** `Hey [name] — quick heads-up: {{urgency_reason}}. Link: {{checkout_url}}. No worries if the timing is not right.`

**Messenger:** `Hey [name] — quick heads-up: {{urgency_reason}}. Here is the link: {{checkout_url}}. No worries if the timing is not right.`

If no real scarcity exists, use this as a genuine check-in, never a fake countdown.

---

### Step 5 — +72h: Last Call

**Subject:** `Last note about [offer name]`

- "This is my last message about [offer] — I do not want to fill your inbox."
- One-line value summary
- Real deadline if one exists; otherwise: "Whenever the timing is right, the link will still be here: `{{checkout_url}}`"
- Graceful close and what they will keep receiving

---

### Step 6 — Purchase Event: Stop and Route

Add `purchased-[offer-id]`; remove `cart-abandon-started`; stop all lane nodes; remove from
retargeting audience D; start buyer onboarding.

## GHL BUILD

**Dependencies first**
- Tags: `cart-abandon-started`, `purchased-[offer-id]`, `messenger-subscribed`, `sms-subscribed`
- Custom values: `{{checkout_url}}`, `{{offer_name}}`, `{{guarantee_statement}}`, `{{urgency_reason}}`

**Workflow nodes**
1. Trigger: Form Submitted (Step 1 order form)
2. Wait 30 min
3. If/Else: `purchased-[offer-id]` present? Yes -> exit; No -> continue
4. Add Tag `cart-abandon-started`
5. Email `CA-01 You Left Something Behind`
6. Wait 2 hours
7. If/Else: purchased? Yes -> exit; No -> If email opened in 2h? Yes -> skip; No -> SMS `CA-S01` + (if `messenger-subscribed`) Messenger `CA-M01`
8. Wait 22 hours
9. If/Else: purchased? Yes -> exit; No -> Email `CA-02 Story/Objection Handle`
10. Wait 24 hours
11. If/Else: purchased? Yes -> exit; No -> SMS `CA-S02` + (if subscribed) Messenger `CA-M02`
12. Wait 24 hours
13. If/Else: purchased? Yes -> exit; No -> Email `CA-03 Last Call`
14. Remove Tag `cart-abandon-started`

**Purchase interrupt (any point):** add `purchased-[offer-id]`; remove `cart-abandon-started`;
stop active nodes; start buyer onboarding.

Set `order` and `parentKey` on every node before first save.

## COPY PERSONA

Helpful, personal, low-pressure throughout. First person from the Attractive Character. Emails
150-300 words, short paragraphs, one CTA — the click back to checkout.

## FLEXIBILITY

Timing gaps are defaults: compress for high-ticket, extend for subscriptions. The purchase check
before every send and the hard stop on purchase are not optional.
