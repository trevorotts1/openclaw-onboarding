# AutoWebinar (Evergreen) Watch-% Segmented Follow-Up

**id:** `autowebinar-watch-segmented-followup`
**category:** funnel-specific-followups
**aliases:** evergreen webinar follow-up · automated webinar sequence · watch-time segmented follow-up · autowebinar replay sequence · evergreen perfect webinar nurture

---

## What this runs
The follow-up for an **evergreen AutoWebinar** running 24/7. Same persuasion content as the live webinar template, but the branching is driven by **watch percentage / watch-time tracking** instead of a fixed live date, and the cart-close runs on a **per-registrant evergreen countdown**. Straight from the Cookbook AutoWebinar Funnel: "segmented follow-up sequences by watch duration — registered / watched-to-end / left-early / no-show."

## TRIGGER
- **Starts when:** AutoWebinar registration (registrant picks a start time or "watch now"); per-registrant deadline begins.
- **Segmentation inputs:** no-show · left-early (watch % below pitch point, e.g. <60%) · watched-through-pitch-no-buy · offer-link-clicked-no-purchase.
- **Exits when:** `autowebinar-purchased`, personal cart-close timer expires, or opt-out.

## CHANNELS
Email + SMS.

## SEQUENCE

### A. Confirmation + show-up — *relative to chosen slot*
- Confirm booking (Soap Opera #1 "Set the Stage", compressed). Reminders at 1 day / 1 hour / start before their selected slot. "Watch now" registrants skip to the broadcast room.

### B. Watch-tracking branch — *~1–2h after their scheduled end*
- **No-show:** re-invite to next slot + replay; re-sell the promise (High-Drama re-hook).
- **Left early:** "You missed the best part" — tease what came AFTER they dropped (the secret + the offer); drive to replay.
- **Watched, no buy:** straight to The Stack recap + 3 Closes (they heard the pitch).
- **Buyer:** exit to onboarding (Goal).

### C. Replay + close — **3 Closes on a per-registrant timer**
- **Close #1 EMOTION:** Epiphany Bridge story + future-pace.
- **Close #2 LOGIC:** The Perfect Webinar Stack — components + value total + price reveal + guarantee.
- **Close #3 FEAR:** honest **per-registrant** deadline (evergreen countdown that truly expires for *them*). SMS at their personal deadline.

## COPY PERSONA + SCRIPT
- **Primary:** Expert Secrets + DotCom Secrets — identical persuasion content to the live webinar template (Soap Opera #1 confirmation, Epiphany Bridge, Perfect Webinar **Stack**, **3 Closes** Emotion→Logic→Fear).
- **Support:** `jim-edwards-copywriting-secrets` — "you missed the best part" curiosity hooks for the left-early branch + honest-scarcity discipline.
- **Structural:** `russell-brunson-the-funnel-hackers-cookbook` — AutoWebinar Funnel: registration → confirmation → broadcast/replay room → post-webinar offer → **follow-up segmented by watch duration**.
- **Honest scarcity rule:** the per-registrant bonus/price MUST really expire when their timer ends — otherwise it is the fake urgency the books forbid.

## GHL BUILD (Skill 44 / caf)
**Workflow name:** `FSF — AutoWebinar Watch-% Segmented Follow-Up`

**Trigger:** Form Submitted = autowebinar registration (or Tag Added `autowebinar-registered`). Store a per-registrant cart-close datetime custom field at registration.
**Watch signals:** the webinar platform posts watch-% milestones via Inbound/Custom Webhook → sets tags `aw-noshow`, `aw-left-early`, `aw-watched-pitch`, `aw-offer-clicked`.

**Ordered actions (caf build-plan — order/parentKey before first save; fail loud on non-2xx):**
1. Email + SMS — Confirmation; tag `autowebinar-registered`
2. Wait until 1h-before chosen slot → SMS reminder (skip if "watch now")
3. Wait until start → SMS "starting now" + room link
4. Wait ~2h after scheduled end
5. If/Else on watch tags → no-show / left-early / watched-no-buy / buyer branches
6. (branch) Email + SMS — segment-appropriate replay re-hook
7. Email — Close #1 EMOTION
8. Wait 1 day
9. Email — Close #2 LOGIC (The Stack)
10. Wait until per-registrant cart-close datetime
11. Email + SMS — Close #3 FEAR
12. End; tag `autowebinar-sequence-complete`

**Goal event:** `autowebinar-purchased` → exit selling steps, route to onboarding.
**If/Else:** watch-% segment · offer-link-clicked-no-purchase → tighter nudge · purchased → Goal exit · SMS vs email on DND.
**Tags:** `autowebinar-registered`, `aw-noshow`, `aw-left-early`, `aw-watched-pitch`, `aw-offer-clicked`, `autowebinar-purchased`, `autowebinar-sequence-complete`.

> The only structural difference from the live template is the timing source: watch-% webhook tags + a per-registrant evergreen countdown replace the global live date. Persuasion content is identical.

## FLEXIBILITY NOTE
This template is a **recommended default and a resource — it is not a rule**. Modes:
1. **User has an explicit desire** → do exactly that; this template is an optional reference only, never imposed or overridden.
2. **User is unsure** → suggest this proven sequence and why, but let them decide.
3. **User wants it handled** → build from this template.
Always overridable, mixable, customizable, or ignorable. It assists; it does not dominate.

## SOURCE FIDELITY
Funnel Hacker's Cookbook (AutoWebinar Funnel watch-duration segmentation) · DotCom Secrets (Soap Opera, 3 Closes) · Expert Secrets (Perfect Webinar, Stack, Epiphany Bridge) · Copywriting Secrets (curiosity hooks, honest scarcity). No invented mechanics.
