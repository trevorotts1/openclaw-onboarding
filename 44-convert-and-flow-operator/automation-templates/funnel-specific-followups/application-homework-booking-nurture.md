# Application → Homework / Bonding → Booking → Show-Up Nurture

**id:** `application-homework-booking-nurture`
**category:** funnel-specific-followups
**aliases:** high-ticket application follow-up · application funnel nurture · homework sequence · booking show-up sequence · strategy call nurture · phone funnel follow-up

---

## What this runs
The follow-up for a high-ticket **Application Funnel** (the "take-away sale"). After a prospect submits the application, it delivers **homework / bonding videos** (so they sell themselves before the call), drives them to **book** the qualification call, maximizes **show-up**, and **re-books no-shows**. The whole sequence stays in a take-away frame — "we're selective, prove you're a fit" — never "please buy."

## TRIGGER
- **Starts when:** application form submitted (Page 2 of the funnel; tag `application-submitted`).
- **Segmentation inputs:** qualified vs not (budget/fit fields) · booked vs applied-but-unbooked · showed vs no-show/cancelled.
- **Exits when:** disqualified routed out / to lower-ticket, call completed → onboarding/close, or opt-out.

## CHANNELS
Email + SMS (SMS for the 1h reminder and no-show recovery).

## SEQUENCE

### A. Homework / bonding — *immediately + before the call*
- Deliver the Application Funnel thank-you-page **bonding videos**: founder Epiphany Bridge origin story + client transformation case studies (same proof as the Page-1 credibility video). Pre-frame the call as a selective fit-check. Single CTA = book the call. **Take-away frame throughout.**

### B. Booking push — *for applicants who didn't book*
- Reminders at +few hours / +1 day / +2 days while unbooked.
- **Jim Edwards "If you want X, do this"** — one instruction (pick a time), restate the call payoff (a plan/clarity), single CTA to the booking widget, honest scarcity on slots if true.
- Booked → stop booking-push, enter pre-call track.

### C. Pre-call show-up nurture — *on booking / 1 day / 1 hour before*
- Confirmation + Soap Opera **"Hidden Benefits"** energy (future-pace the after-state) + logistics. 1h reminder via SMS. Reinforce take-away: "come ready to show us you're a fit."

### D. No-show / cancel recovery — *within 1–2h, then +1 day*
- Warm, non-needy re-invite ("we held your spot, but only so long"), single CTA back to calendar, honest scarcity.
- Re-booked → back to pre-call track. Persistent no-show after N attempts → downsell to a self-serve/lower-ticket offer or long-term nurture.

## COPY PERSONA + SCRIPT
- **Primary:** Expert Secrets / DotCom Secrets — Application Funnel = **take-away sale**. **Epiphany Bridge** bonding videos (origin + client case studies). Soap Opera "Hidden Benefits" energy in the confirmation.
- **Support:** `jim-edwards-copywriting-secrets` — "If you want X, do this" booking nudges, honest scarcity on call slots, single-CTA discipline, subject lines.
- **Structural:** `russell-brunson-the-funnel-hackers-cookbook` — Application Funnel recipe: credibility/case-study video → application (prospect sells themselves) → homework page with bonding videos + calendar; closed by phone (setter → closer).

## GHL BUILD (Skill 44 / caf) — cleanest as 3 linked workflows
**Trigger:** Form Submitted = application (or Tag Added `application-submitted`). If/Else on application fields → `app-qualified` vs `app-disqualified`.

**Workflow 1 — `FSF — Application: Homework + Booking Push`**
1. Email + SMS — Homework/bonding video; tag `application-submitted`
2. If/Else qualification → disqualified → lower-ticket path; qualified continue
3. Wait 4h → If `appointment-booked`? FALSE → booking nudge #1
4. Wait 1 day → still unbooked → nudge #2
5. Wait 1 day → still unbooked → nudge #3 (honest scarcity)

**Workflow 2 — trigger Appointment Booked**
- Confirmation Email + SMS; tag `call-booked`; stop booking-push
- Wait until 1 day before → reminder + pre-call homework
- Wait until 1 hour before → SMS reminder

**Workflow 3 — trigger Appointment No-Show / Cancelled**
- Wait 1–2h → "we missed you" Email + SMS rebook CTA
- Wait 1 day → second rebook nudge; after N misses → tag `app-persistent-noshow` → downsell/nurture

**Goal event:** call completed / sale → exit nurture, route to onboarding or post-call close.
**If/Else:** qualified vs disqualified · booked vs unbooked · showed vs no-show/cancelled · persistent no-show → downsell.
**Tags:** `application-submitted`, `app-qualified`, `app-disqualified`, `call-booked`, `call-showed`, `call-noshow`, `app-persistent-noshow`.

> GHL's native calendar provides Booked / No-Show / Cancelled triggers (no custom webhook needed). caf builds each workflow shape; operator pastes finalized bodies.

## FLEXIBILITY NOTE
This template is a **recommended default and a resource — it is not a rule**. Modes:
1. **User has an explicit desire** → do exactly that; this template is an optional reference only, never imposed or overridden.
2. **User is unsure** → suggest this proven sequence and why, but let them decide.
3. **User wants it handled** → build from this template.
Always overridable, mixable, customizable, or ignorable. It assists; it does not dominate.

## SOURCE FIDELITY
Funnel Hacker's Cookbook (Application Funnel: credibility video → application → homework/bonding + booking; setter→closer phone close) · DotCom Secrets / Expert Secrets (take-away sale, Epiphany Bridge) · Copywriting Secrets ("If you want X", honest scarcity, single CTA). No invented mechanics.
