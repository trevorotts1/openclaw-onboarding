# Cart Abandon / Step-1-Not-Step-2 Recovery

**id:** `cart-abandon-recovery`
**category:** funnel-specific-followups
**aliases:** abandoned cart recovery · abandoned checkout · two-step order form recovery · step-1-not-step-2 follow-up · Brunson Box recovery · incomplete order recovery

---

## What this recovers
A buyer who filled in their contact/address info on **Step 1** of a 2-step order form (the "Brunson Box") but never completed payment on **Step 2**. The whole reason the 2-step form exists is so the email is captured as a **micro-commitment before billing** — that is the *only* reason this drop-off is recoverable. The Funnel Hacker's Cookbook calls the one-page order form on a low-ticket offer the "wrong order form for the price" precisely because it forfeits this recovery.

This is the Cookbook's **Drop-Off Automation** map applied to the **step-1-not-step-2** leak → Message #1 / #2 / #3.

## TRIGGER
- **Starts when:** Step 1 contact info is captured AND no completed order fires within the wait window.
- **Entry:** tag `order-step1-started` set by the Step-1 form; contact does NOT have `order-completed`.
- **Exits when:** purchase completes (instant exit), contact opts out, or Message #3 sends.

## CHANNELS
Email (primary) + SMS mirror.

## SEQUENCE

| # | Beat / purpose | Delay | Subject angle | Body framework (persona/script) |
|---|----------------|-------|---------------|----------------------------------|
| **Msg #1** | Helpful nudge — "did something go wrong?" Assume a tech hiccup, not a no. Remove friction. | 15–30 min | "Did your order go through?" | **Jim Edwards "If you want X, do this"** (warm). Name the exact product, give ONE instruction, single CTA back to Step 2 with info pre-filled. No discount. |
| **Msg #2** | Agitate the gap — remind them WHY they wanted it; neutralize risk. | +4–24 hr | "Still thinking about [result]?" | **Problem / Agitate / Solve.** Restate the problem, agitate the cost of staying stuck (loss aversion), re-present the offer + add the guarantee + 1 proof point. Single CTA. |
| **Msg #3** | Honest last call — a REAL reason to act now, then a soft close. | +24–48 hr | "Last call on your [product]" | **Honest-urgency close + Stealth/Columbo P.S.** State the true reason the window closes (bonus/price/stock), recap in one line, single CTA, "By the way…" P.S. |

## COPY PERSONA + SCRIPT
- **Primary copywriter:** `jim-edwards-copywriting-secrets` (Copywriting Secrets) — The Direct-Response Copy Closer.
  - Treats abandoners as **WARM** traffic (they already raised their hand) → lead with the **solution**, not the problem.
  - Msg #1 = "If you want X, do this"; Msg #2 = Problem/Agitate/Solve; Msg #3 = honest urgency + **Stealth/Columbo close**.
  - Ties **Ten Reasons People Buy** (escape pain, save time, save money).
  - **Honor every deadline** — fake "only 3 left" that restocks destroys integrity (Edwards rule; echoes Soap Opera "fake urgency backfires").
- **Structural persona:** `russell-brunson-the-funnel-hackers-cookbook` — supplies the 2-step Brunson Box + the Message #1/#2/#3 drop-off map.

## GHL BUILD (Skill 44 / caf)
**Workflow name:** `FSF — Cart Abandon Recovery (Msg 1/2/3)`

**Trigger:** Order Form Submission on Step 1 (or native "Abandoned Checkout"); alt = Tag Added `order-step1-started` with filter `NOT order-completed`.

**Ordered actions (caf build-plan — every action carries order/parentKey before first save; fail loud on non-2xx):**
1. Wait 20 min
2. If/Else `order-completed`? → TRUE: end (Goal). FALSE: continue
3. Send Email — Msg #1
4. Send SMS — Msg #1 (optional)
5. Wait 6 hr
6. If/Else purchased? → exit on TRUE
7. Send Email — Msg #2
8. Wait 1 day
9. If/Else purchased? → exit on TRUE
10. Send Email — Msg #3
11. Send SMS — Msg #3
12. Remove `order-step1-started`; add `cart-abandon-sequence-complete`

**Goal event:** `order-completed` (purchase) wired as a workflow GOAL → contact exits the instant they buy.
**Wait steps:** 20 min · 6 hr · 1 day · 1 day.
**If/Else:** re-check purchase after every wait; optional SMS-vs-email branch on DND/phone presence.
**Tags:** `order-step1-started`, `order-completed`, `cart-abandon-sequence-complete`.

> GHL Automations have no public API — caf builds the workflow shape (trigger + waits + if/else + email/SMS); the operator pastes finalized bodies. Keep the order-page countdown timer real so Msg #3 urgency stays true.

## FLEXIBILITY NOTE
This template is a **recommended default and a resource — it is not a rule**. Modes:
1. **User has an explicit desire** → do exactly that; this template is an optional reference only, never imposed or overridden.
2. **User is unsure** → suggest this proven sequence and why, but let them decide.
3. **User wants it handled** → build from this template.
Always overridable, mixable, customizable, or ignorable. It assists; it does not dominate.

## SOURCE FIDELITY
The Funnel Hacker's Cookbook (Brunson Box, Drop-Off Message #1/#2/#3, "wrong order form for the price") · DotCom Secrets (2-step tripwire order form) · Copywriting Secrets (PAS, "If you want X", honest urgency, Stealth close). No invented mechanics.
