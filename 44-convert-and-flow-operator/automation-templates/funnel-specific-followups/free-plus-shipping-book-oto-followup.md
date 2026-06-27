# Free-Plus-Shipping / Book Post-Purchase + OTO Recovery Follow-Up

**id:** `free-plus-shipping-book-oto-followup`
**category:** funnel-specific-followups
**aliases:** book funnel follow-up · free plus shipping post-purchase · FPS OTO recovery · tripwire post-purchase sequence · no-upsell recovery · buyer ascension sequence

---

## What this runs
Post-purchase follow-up for a **Free-Plus-Shipping / Book funnel** (or 2-step tripwire). It (1) confirms the order and **fulfills first** (book + bonus), (2) **bonds** the new buyer to the Attractive Character (Soap Opera), (3) recovers the **no-upsell** drop-off with a second-chance OTO, and (4) **bridges** the buyer UP the value ladder to the next funnel. The front end breaks even; this sequence is where the **funnel-stacking** profit lives.

## TRIGGER
- **Starts when:** front-end purchase completed (tag `fe-purchased`); OTO disposition known (`oto-accepted` / `oto-declined`).
- **Segmentation inputs:** took-OTO vs declined · physical vs digital fulfillment · bonus engaged vs not.
- **Exits when:** buyer ascends (→ next funnel's follow-up), refund/cancel (→ retention save), or opt-out.

## CHANNELS
Email + SMS.

## SEQUENCE

### A. Confirmation + delivery — *immediately*
- **Fulfill BEFORE any ask** (Lead Funnels rule): deliver download/access + the high-value bonus training that bridges to the backend. Warm welcome from the Attractive Character. Physical → shipping timeline + tracking-to-come.

### B. Second-chance OTO (no-upsell recovery) — *+1–24h, only to `oto-declined`*
- **Stealth/Columbo close** ("By the way, since you grabbed [book], you can still add [OTO]…") + **Problem/Agitate/Solve** on the gap the OTO fills. Honest one-time framing. Single CTA, one-click add.
- Accepts → tag `oto-recovered`, stop. Declines again → proceed to ascension; do not keep pushing.
- *(This is the Cookbook "no-upsell → Message #1/#2/#3" drop-off leak.)*

### C. Buyer bonding (Soap Opera) — *daily, days 1–5*
- Soap Opera Sequence applied to buyers: #1 Set the Stage ("you're in") · #2 High Drama + Backstory · #3 Epiphany tied to the backend offer · #4 Hidden Benefits of going further. Each opens a loop and seeds the next-step offer. This is the bond Brunson says **raises stick rate before the second funnel is offered**.

### D. Ascension bridge — *day 5–7+, then ongoing*
- Soap Opera #5 (Urgency + CTA) **handing off to the next funnel**: invite to the webinar (→ `webinar-registration-reminder-replay-stack`) or the application (→ `application-homework-booking-nurture`). After this, buyer drops into the ongoing **Daily Seinfeld Sequence**.
- **Stack the next funnel:** book → webinar → high-ticket. Profit lives in the stack, not the front end.

## COPY PERSONA + SCRIPT
- **Primary:** DotCom Secrets (Soap Opera buyer-bonding #1–#5; Daily Seinfeld ongoing) + Copywriting Secrets (**Stealth/Columbo** OTO close, **PAS**, honest scarcity).
- **Fulfill-first** rule from Lead Funnels (deliver the book/bonus before any ask).
- **Structural:** `russell-brunson-the-funnel-hackers-cookbook` + Marketing Secrets Blackbook — Book/FPS recipe (2-step order + bump → OTO 1 → OTO 2/downsell → confirmation/bonus page with high-ticket CTA); Cart-Maximization (bump → OTO → downsell); Drop-Off Automation (no-upsell); Funnel Stacking.

## GHL BUILD (Skill 44 / caf)
**Workflow name:** `FSF — Book/FPS Post-Purchase: Deliver -> OTO Recover -> Bond -> Ascend`

**Trigger:** Order Submitted = front-end product (or Tag Added `fe-purchased`). Funnel sets `oto-accepted` / `oto-declined`.

**Ordered actions (caf build-plan — order/parentKey before first save; fail loud on non-2xx):**
1. Email + SMS — Order confirmation + bonus/access; tag `fe-purchased`
2. If/Else physical? → add shipping/tracking touch
3. If/Else `oto-declined`? → Wait 2h → second-chance OTO (Stealth close); accepts → `oto-recovered` & skip repeat
4. Wait 1 day → Bonding #1 (Set the Stage)
5. Wait 1 day → Bonding #2 (High Drama)
6. Wait 1 day → Bonding #3 (Epiphany → backend)
7. Wait 1 day → Bonding #4 (Hidden Benefits)
8. Wait 1 day → Ascension Email + SMS (invite to next funnel)
9. Tag `ready-to-ascend`; hand off to next funnel workflow + Daily Seinfeld list
10. Refund/cancel anytime → route to retention/cancellation-save workflow

**Goal event:** ascension purchase / next-funnel entry → exit into that funnel's follow-up.
**If/Else:** oto-accepted vs declined · physical vs digital · refund/cancel → retention save · ascended → exit · SMS vs email on DND.
**Tags:** `fe-purchased`, `oto-accepted`, `oto-declined`, `oto-recovered`, `ready-to-ascend`, `refund-requested`.

> Honor the "one-time" OTO claim — a second-chance link that stays open forever is fake urgency (Edwards/Soap Opera rule). The ascension step is a **hand-off**: enroll the buyer into the Webinar or Application template, don't duplicate that logic here.

## FLEXIBILITY NOTE
This template is a **recommended default and a resource — it is not a rule**. Modes:
1. **User has an explicit desire** → do exactly that; this template is an optional reference only, never imposed or overridden.
2. **User is unsure** → suggest this proven sequence and why, but let them decide.
3. **User wants it handled** → build from this template.
Always overridable, mixable, customizable, or ignorable. It assists; it does not dominate.

## SOURCE FIDELITY
Funnel Hacker's Cookbook (Book/FPS recipe; Cart-Maximization; no-upsell Drop-Off Automation; Funnel Stacking) · Marketing Secrets Blackbook (Book Funnel + bonus-bridge) · DotCom Secrets (Soap Opera + Daily Seinfeld; value-ladder ascension) · Copywriting Secrets (Stealth/Columbo, PAS, honest scarcity). No invented mechanics.
