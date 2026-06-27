# Webinar Registration → Indoctrination → Reminders → Live → Replay → Stack Close

**id:** `webinar-registration-reminder-replay-stack`
**category:** funnel-specific-followups
**aliases:** perfect webinar follow-up · live webinar reminder sequence · webinar registration sequence · webinar reminder replay sequence · webinar indoctrination sequence · show-up + close sequence

---

## What this runs
The complete follow-up wrapped around a **LIVE Perfect Webinar funnel**. It does three jobs in order: (1) bond registrants to the Attractive Character so they **show up** (Soap Opera indoctrination), (2) **remind** them to attend, and (3) **close** the sale during the replay/cart-open window using the **Perfect Webinar Stack** and the DotCom Secrets **3 Closes (Emotion → Logic → Fear)**. The Funnel Hacker's Cookbook Webinar Funnel recipe is the page skeleton: registration → confirmation/indoctrination → live event → replay/urgency page with cart-close countdown.

## TRIGGER
- **Starts when:** webinar registration submitted (tag `webinar-registered` + session datetime stored in a custom field).
- **Segmentation inputs:** showed-up-live vs no-show; stayed-to-close vs left-early; clicked-buy-link but didn't purchase.
- **Exits when:** `webinar-purchased` (route to onboarding), cart-close datetime passes, or opt-out.

## CHANNELS
Email (all phases) + SMS (confirmation, 1h reminder, "we're LIVE", final Fear close).

## SEQUENCE

### A. Confirmation — *immediately*
- **Email 0 — Set the Stage** (Soap Opera Email #1). Welcome from the Attractive Character, state date/time + the ONE big promise (the "one thing"/big domino), open a curiosity loop, tell them to whitelist + add to calendar. SMS = confirm + calendar link.

### B. Indoctrination (pre-webinar bonding) — *one per day to the live date*
- **Emails 1–3 = Soap Opera Sequence #2–#4:**
  - **#2 High Drama + Backstory** — start at the high-drama moment, then backstory to the wall the reader is also at.
  - **#3 Epiphany** — the epiphany that ties to the webinar's big idea (Epiphany Bridge engine).
  - **#4 Hidden Benefits** — the non-obvious payoffs of attending.
  - Every email reinforces date/time + why this webinar answers their #1 problem and opens a loop pulling to the next.

### C. Show-up reminders — *24h / 1h / live*
- **24h before:** Email + SMS — "Tomorrow: [big promise]".
- **1h before:** SMS — "Starting in 1 hour".
- **At start:** SMS-first — "We're LIVE — join now" + direct join URL.
- Framework: Soap Opera Email #5 energy (Urgency + CTA) applied to *attendance*, not pitch.

### D. Replay — *within hours of live; 24–72h window with countdown*
- **Branch — no-show:** "Sorry we missed you — here's the replay (expires soon)." Re-sell the promise, embed replay + cart-close countdown.
- **Branch — attended, no buy:** "Did you catch the [offer] at the end?" → straight to the Stack recap + 3 Closes.

### E. Cart-close close — **The Stack + 3 Closes** *(spread across the replay window)*
- **Close #1 — EMOTION:** retell the Epiphany Bridge / transformation story; future-pace the result; rebuild desire.
- **Close #2 — LOGIC:** present **THE STACK** — list every offer component with its standalone value, total it, *then* reveal the price ("dollars for dimes"); restate the guarantee. (Verbatim Perfect Webinar close.)
- **Close #3 — FEAR:** honest urgency — the cart/bonuses/price genuinely expire at the cart-close datetime; name what they lose. Final SMS at the deadline.

## COPY PERSONA + SCRIPT
- **Primary:** DotCom Secrets + Expert Secrets (Brunson).
  - **Soap Opera Sequence** (Secret #7) drives confirmation + indoctrination (#1–#5).
  - **Epiphany Bridge** (Expert Secrets) is the story engine in indoctrination + the Emotion close.
  - **The Perfect Webinar Stack** (Expert Secrets) is the Logic close — cumulative offer build → value total → price reveal.
  - **3 Closes** (DotCom Secrets Follow-Up Funnel) = Emotion → Logic → Fear across the cart window.
  - **Honest urgency only** — Soap Opera rule: "fake urgency backfires; it must be real."
- **Support:** `jim-edwards-copywriting-secrets` — subject lines (fear/desire headlines, curiosity) + honest-scarcity discipline on the Fear close.
- **Structural:** `russell-brunson-the-funnel-hackers-cookbook` — Webinar Funnel page recipe + Drop-Off Automation for no-shows.

## GHL BUILD (Skill 44 / caf)
**Workflow name:** `FSF — Live Webinar: Reg -> Indoctrinate -> Remind -> Replay -> Close`

**Trigger:** Form Submitted = registration page (or Tag Added `webinar-registered`); store webinar datetime in a custom field so reminder waits compute 24h/1h-before relative to it.

**Ordered actions (caf build-plan — order/parentKey on every action before first save; fail loud on non-2xx):**
1. Email + SMS — Confirmation (Set the Stage); tag `webinar-registered`
2–4. Email — Indoctrination #1/#2/#3 (Wait 1 day between)
5. Wait until 24h-before → Email + SMS reminder
6. Wait until 1h-before → SMS reminder
7. Wait until start → SMS "We're LIVE" + join link
8. Wait ~2h after end
9. If/Else `webinar-attended` vs `webinar-noshow` → branch replay copy
10. Email + SMS — Replay (branched) + cart-close countdown
11. Email — Close #1 EMOTION
12. Wait 1 day
13. Email — Close #2 LOGIC (The Stack + value total + price)
14. Wait until final cart-close day
15. Email + SMS — Close #3 FEAR (honest deadline)
16. At cart-close: end; tag `webinar-sequence-complete`

**Goal event:** `webinar-purchased` → exit selling steps, route to onboarding.
**Wait steps:** per-day indoctrination · until-24h · until-1h · until-start · post-event · 1 day · until cart-close.
**If/Else:** no-show vs attended · buy-link-clicked-no-purchase ("you were so close") · purchased → Goal exit · SMS vs email on DND.
**Tags:** `webinar-registered`, `webinar-attended`, `webinar-noshow`, `webinar-buy-link-clicked`, `webinar-purchased`, `webinar-sequence-complete`.

> Attendance tags come from the webinar platform webhook or a "click to join" trigger-link click. The replay-page countdown MUST match the deadline the Fear close cites — keep them in sync so urgency is real.

## FLEXIBILITY NOTE
This template is a **recommended default and a resource — it is not a rule**. Modes:
1. **User has an explicit desire** → do exactly that; this template is an optional reference only, never imposed or overridden.
2. **User is unsure** → suggest this proven sequence and why, but let them decide.
3. **User wants it handled** → build from this template.
Always overridable, mixable, customizable, or ignorable. It assists; it does not dominate.

## SOURCE FIDELITY
DotCom Secrets (Soap Opera #7; 3 Closes Emotion/Logic/Fear) · Expert Secrets (Perfect Webinar, The Stack, Epiphany Bridge) · Funnel Hacker's Cookbook (Webinar Funnel recipe + no-show drop-off automation) · Copywriting Secrets (subject lines, honest scarcity). Beats are the verbatim Soap Opera email purposes, the documented 3-Closes order, and the Perfect Webinar Stack. No invented steps.
