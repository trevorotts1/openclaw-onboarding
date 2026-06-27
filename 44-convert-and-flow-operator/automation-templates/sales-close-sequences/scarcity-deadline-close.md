# Scarcity / Deadline Close — Standalone Fear Phase

**id:** `scarcity-deadline-close` · **category:** sales-close-sequences
**Aliases:** fear close, urgency close, deadline sequence, closing sequence, FOMO close, fast-action sequence, last-chance close, countdown sequence, scarcity sequence
**Source:** Marketing Secrets Blackbook (Brunson — Secret 51: Urgency & Scarcity — three types: limited time / limited pricing / limited quantity; "The best offers use all three at once") · DotCom Secrets (Brunson — Phase 3 of the 3 Closes: Fear/Urgency, the highest revenue-concentration phase) · Expert Secrets (Brunson — Perfect Webinar: fast-action bonus, cart-close, takeaway close "doors closing") · Copywriting Secrets (Edwards — FOMO future-pacing, cost of inaction, honest reason to act now, single CTA rule)

> **The Fear phase as a reusable standalone module.** This is the close that converts procrastinators and fence-sitters by making NOW the only logical time to act. It is derived from Brunson's 3 Closes framework (Phase 3: Fear/Urgency), rooted entirely in Marketing Secrets Blackbook Secret 51 (the three scarcity levers), and amplified by Edwards' cost-of-inaction future-pacing technique.
>
> **Modular design:** Attach this sequence at the end of any other template (Soap Opera Sequence Day 5, 3 Closes Logic phase end, Product Launch close, Webinar follow-up) or run it standalone when a warm list needs a deadline-driven push on any existing offer.

---

## THE THREE SCARCITY LEVERS (Blackbook Secret 51)

> *"There are two words that increase every sale you make: urgency and scarcity."* — Russell Brunson

| Lever | What it is | Example |
|-------|-----------|---------|
| **Limited time** | The offer expires at a fixed date/time — genuinely. Events have built-in limits. Fast-action bonuses that run out when the webinar ends. | "Buy before midnight [date] or you'll miss it" |
| **Limited pricing** | Stack bonuses that expire instead of discounting the core offer. The effective price/value of the offer declines after the deadline. | "The $300 bonus disappears after [date]. Price stays the same — but the value drops." |
| **Limited quantity** | A genuine cap on seats, units, or access. Brunson's Inner Circle: 100 spots, only opens when someone drops out. | "Only 12 spots left at this tier" |

**The stacking rule:** The best offers use all three simultaneously. If only one lever is real, use only one — never fabricate a lever you will not enforce.

---

## FLEXIBILITY PRINCIPLE

This template is a **guide and a resource, never a rule or a requirement.** Three operating modes:

| Mode | What the system does |
|------|---------------------|
| **User has an explicit desire** | Build exactly what the user specifies. This template is optional reference only. |
| **User is unsure** | Present the three-lever architecture, explain why the T-1h spike consistently drives the largest revenue beat, let the user decide what to use. |
| **User wants it handled ("just do it")** | Execute the full close sequence adapted to the user's offer and deadline. |

Always overridable, skippable, and customizable.

---

## TRIGGER
**Chain from:** SOS Email 5 clicked + no purchase · 3 Closes Logic phase completes · Seinfeld click on an offer 2+ times + no purchase (tag `hot-no-buy-[offer]`) · Product launch enters final 72h · Operator adds `start-fear-close-[offer]` manually.

**Entry condition:** Warm contact; has seen the offer at least once; not tagged `buyer-[offer]`. A **real deadline** must exist and be set in the `cart-close-datetime` custom field BEFORE the sequence starts.

**Exit:** Purchase at any step → buyer onboarding, STOP Fear close. Deadline passes without purchase → one optional downsell, then Seinfeld Daily Sequence.

## CHANNELS
Email (all steps) · SMS (T-48h, T-24h, T-1h — priority for mobile) · Facebook/Instagram Message (T-24h + T-1h mirror) · Desktop push (T-24h) · On-page countdown timer (synced to `cart-close-datetime`)

## CADENCE
5 touches in 48–72 hours:

```
Deadline announce → T-48h → T-24h → T-3h → T-1h → post-close branch
```

**Copy length rule:** Each email gets shorter as the deadline approaches. The announce email is the longest. T-1h is 2 sentences + a link. Short length at T-3h/T-1h signals genuine urgency — long emails at the last hour feel performative.

---

## THE SEQUENCE

| Step | Timing | Beat | Subject | Body framework | Persona |
|------|--------|------|---------|----------------|---------|
| 1 | T-72h or sequence start | **Deadline announce.** 'I want to make sure you don't miss this.' State the closing date/time. Explain WHY the deadline is real (lever reasons). 2-sentence offer summary. Informational, not pressured. | "Heads up: this closes [date]" / "Something you need to know before [date]" | 'I want to make sure you don't miss this.' → Deadline: 'On [date] at [time], [offer] closes.' → WHY it closes (the real lever reasons) → 2-sentence offer: '[Name] gives you [key result], for [price], with [guarantee].' → CTA. P.S.: one scarcity fact. | Brunson urgency intro + Blackbook S51 three levers |
| 2 | T-48h | **Three levers quantified.** 48h warning. Name and quantify all applicable levers. 3-bullet offer summary (each ending in 'which means…'). SMS mirrors the email in 1 line. | "48 hours left — [what changes after]" | 'In 48 hours, [offer] closes. Here's what that means:' → Lever 1 (time): closes [datetime]. → Lever 2 (pricing): price rises / bonus removed on [date]. → Lever 3 (quantity): [N] spots remain. → 3 bullets (result + 'which means') → Price reminder → CTA. SMS: '48h left — closes [date]: [link]' | Blackbook S51; Edwards bullets with 'which means' |
| 3 | T-24h | **Cost of inaction — FOMO future-pace (Edwards).** 'Picture yourself 6 months from now still [the pain], because today you said not yet.' Then the bonus expiry. SMS priority. | "24 hours — [bonus] disappears tonight" / "Picture yourself in 6 months…" | Deadline → Future-pace: 'Picture yourself 6 months from now still [pain]. Nothing changed because today you said wait. Now picture the other path: [vivid after-state].' → Back to offer: 'That's exactly what [offer] gives you. [Price]. [Guarantee].' → Expiry fact. → CTA. P.S.: 'Bonus expires at [time].' SMS: '[Offer] bonus expires tonight: [link]' | Edwards FOMO future-pacing; Blackbook S51 bonus-expiry |
| 4 | T-3h | **Short urgency email — 3 sentences maximum.** Subject does the work. No story. Pure proximity to loss. Brevity signals the close is real. | "3 hours" / "Closing tonight — last email" | '3 hours from now, [offer] closes for good.' → One line on what they get → CTA link → 'That's it.' → P.S.: '[Time] tonight — then [what changes].' | Brunson takeaway close; Edwards: one CTA, zero fluff |
| 5 | T-1h | **Final call — SMS is priority.** Two email lines. SMS targets mobile users. The T-1h SMS typically drives the largest single conversion spike in the campaign. | "Final call — 60 minutes" / "Closing now" | 'Closing in 1 hour. Final call for [offer name].' → [link] → That is all. SMS: 'FINAL CALL — closes in 60 min. Last chance: [link]' | Brunson FOMO close (honored — closes in 1 hour) |
| 6 | Post-close | **Branch:** Buyers → onboarding + ascend. Non-buyers → optional downsell (once) → Seinfeld. Optional: 'cart is closed' email validates the deadline was real. Do NOT re-open the cart. | — | Buyer: access + next step. Non-buyer: 'Cart closed. Here's what's next.' → downsell offer or Seinfeld enrollment. | Brunson Stack Don't Switch; integrity: deadline honored |

---

## COPY PERSONA & SCRIPT
- **Primary:** Brunson — 3 Closes Fear phase · Blackbook Secret 51 · Perfect Webinar takeaway close.
- **Supporting:** Edwards — cost-of-inaction future-pacing (the T-24h email's core move: "picture yourself in 6 months still [pain] because you did nothing today"); single CTA rule; P.S. deadline restatement; short copy at T-3h and T-1h.
- **The emotional driver in the Fear phase is NOT 'what you gain' (that was the Emotion close) — it is 'what you LOSE by not acting.'** Cost of inaction, expiring bonus, closing access, rising price, limited remaining spots.

---

## GHL BUILD (Skill 44 → GoHighLevel)
**Workflow:** `Scarcity / Deadline Close — [Offer Name]`

1. **Trigger:** `Tag Added = start-fear-close-[offer]`. Filter: `buyer-[offer]` must be absent.
2. **Add tag:** `in-fear-close-[offer]`. Confirm `cart-close-datetime` is set.
3. **Deadline announce** immediately on trigger (Email + SMS).
4. `Wait Until` [cart-close-datetime minus 48h] → T-48h email + SMS.
5. `Wait Until` [cart-close-datetime minus 24h] → T-24h email + SMS.
6. `Wait Until` [cart-close-datetime minus 3h] → T-3h email (short).
7. `Wait Until` [cart-close-datetime minus 1h] → T-1h email + SMS.
8. `Wait Until` [cart-close-datetime plus 1h] → `If/Else`: buyer → onboarding; non-buyer → optional downsell → Seinfeld.

**Critical GHL notes:**
- `cart-close-datetime` = single source of truth for ALL waits AND the on-page countdown timer.
- **Purchase Goal** (`buyer-[offer]`) wired at every step — fires immediately on purchase, exits all emails.
- At cart-close-datetime, GHL order form / product price genuinely changes (enforce the deadline in the platform).
- T-24h and T-1h SMS sends: set a send-window constraint (8am–9pm contact timezone) to avoid late-night sends.
- After the deadline passes, immediately remove the `in-fear-close-[offer]` tag and add `close-complete-[offer]` for clean reporting.

## INTEGRITY GUARDRAILS
- Deadline is real and enforced — offer/price genuinely changes after it. No re-opens without a new explicitly announced deadline. (Blackbook S51; Edwards: "always tell the truth and back it up")
- Use only scarcity levers that are true — never fabricate quantity, time, or pricing urgency you will not enforce.
- Do not run this sequence on the same offer to the same contact more than once per campaign window. Repeated fake closes destroy trust permanently.
- Cost-of-inaction future-pacing must be grounded in a real pain the prospect has — do not invent a before-state.

## KPIs
Announce email open rate · T-48h conversion rate · T-24h conversion rate · T-1h conversion spike (% of total Fear-phase revenue in this window) · Overall Fear-phase conversion rate · SMS vs. email recovery comparison per beat · Post-close downsell take rate
