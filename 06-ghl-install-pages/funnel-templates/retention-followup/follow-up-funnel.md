# Follow-Up Funnel (Soap Opera + Seinfeld) — Skill-6 Template

- **id:** `follow-up-funnel`
- **Category:** retention-followup
- **Library entry:** #24
- **Length class:** Long-form (30–60+ day multi-channel automated sequence)
- **Aliases:** Follow-Up Funnel, Automation and Follow-Up Funnels, Communication Funnel, Email Epiphany Follow-Up Funnel, Soap Opera Sequence, Daily Seinfeld Sequence, Nurture Sequence, Indoctrination Sequence
- **Source books:** Funnel Hacker's Cookbook, Marketing Secrets Blackbook, Lead Funnels, DotCom Secrets, Expert Secrets, Traffic Secrets

---

## When to use / trigger criteria

The engine that sits **behind** every front-end funnel. Deploy right after any opt-in or purchase to bond the new lead to the Attractive Character, ascend them up the value ladder, and monetize the list over time. It is **not** a standalone traffic destination.

**Goals:** bond new subscribers before pitching · convert opt-ins who didn't buy · maximize lifetime value / ascension · recover abandoned carts and no-show registrants · keep a list warm between launches · re-monetize a cold list.

**Keywords:** follow-up sequence, email sequence, nurture/drip, soap opera sequence, seinfeld sequence, autoresponder, welcome/onboarding emails, indoctrination, abandoned cart, SMS sequence, list monetization.

**Signals:** "what do we send after they sign up?" · a capture/order funnel already exists and the ask is the backend · "they opt in but don't buy" · need to bond / tell the founder story over multiple touches · goal framed as LTV or "make money from the list."

**Anti-signals:** single-touch page with no automation (use the front-end funnel) · customer actively cancelling (use the Cancellation Funnel) · cold pre-frame before opt-in (use Bridge / Cold Traffic Article).

---

## Page / sequence structure (the "pages" are message steps)

A follow-up funnel's structure is a sequence of messages plus a thin supporting page layer.

0. **Entry Trigger** *(supporting page from the feeder funnel)* — fires on opt-in / purchase / registration / cart-abandon. Thank-you page sets "check your inbox," tags the contact, resets the Day-0 timer.

**Soap Opera Sequence (5 emails — the bonding / Emotion close):**
1. **Set the Stage** *(Day 0, immediate)* — welcome, deliver the promise, open a curiosity loop, tell them to watch their inbox.
2. **High Drama / Backstory & the Wall** *(Day 1)* — open in-media-res at the dramatic peak, rewind to backstory and the wall (the problem). Mirror the reader's pain.
3. **Epiphany** *(Day 2)* — reveal the discovery / new opportunity (Epiphany Bridge payoff); connect it to the offer; first real CTA.
4. **Hidden Benefits** *(Day 3)* — unexpected benefits, break a secondary false belief, add proof, stronger CTA.
5. **Urgency & CTA** *(Day 4)* — real scarcity/deadline, restate transformation + cost of inaction, hard CTA. Buyers exit to ascension; non-buyers roll into Seinfeld.

**Daily Seinfeld Sequence (ongoing — engagement + monetization):**
6. **Daily entertainment emails** *(Day 5+, recurring)* — "about nothing" stories that always tie to an offer via **Hook → Story → Offer**. Rotate storylines (Loss & Redemption, Us vs Them, Before & After, Amazing Discovery, Secret Telling, Third-Person Testimonial) and offers across the value ladder.

**Overlay across the whole arc:**
7. **3 Closes spine + multi-channel** — Emotion (Soap Opera) → Logic (case-study/ROI emails) → Fear (scarcity emails); mirrored across **email + SMS + Messenger + desktop push + retargeting ads + direct mail**, with behavior branches (opened/clicked, watched-to-end, bought/not-bought, cart-abandoned).

---

## Copy framework

- **Primary persona:** **The Attractive Character** (DotCom/Expert Secrets) — every message in this polarizing, relatable brand voice (backstory, parables, character flaws, polarity). Identities: Leader / Adventurer / Reporter-Evangelist / Reluctant Hero.
- **Primary script:** **Soap Opera Sequence** for bonding, then **Daily Seinfeld (Hook-Story-Offer)** for ongoing engagement.
- **Secondary scripts:** **Epiphany Bridge** (Email 3 + reframes), **3 Closes** (Emotion→Logic→Fear across 30–60 days), **Copywriting Secrets** (Jim Edwards: subject-line/curiosity hooks, one-idea-per-email, P.S. close).
- **Rule:** one idea per email; every email — even pure-value Seinfeld emails — ends with a single CTA; polarity is mandatory (bland = unopened forever).

---

## GHL build notes (Skill 6 + Skill 44)

- **Deliverable is a Workflow, not pages.** Skill 6 wires the supporting thank-you/preferences pages and hands the sequence body to GHL Workflows/Automations.
- **Skill 6 pages:** thank-you/delivery bridge into Email 1 (often inherited from feeder funnel) · optional preferences/manage-subscription page · CTA target offer pages are built by their own templates and linked, not duplicated.
- **Skill 44 widgets:** opt-in form on the feeder page (submission = entry trigger) · calendar widget only if a CTA books a call (ascension to Application Funnel). No quiz needed for the core sequence.
- **Automations:**
  - Workflow *Soap Opera*: trigger on opt-in/purchase tag → Email 1 (immediate) → wait 1 day → Emails 2–5 (Days 1–4).
  - Workflow *Daily Seinfeld*: enroll non-buyers after Soap Opera completes → recurring daily email steps (or scheduled broadcasts) using Hook-Story-Offer.
  - Branch on tags/events: bought → remove from selling, enroll ascension; clicked-no-buy → re-pitch; cart-abandoned → urgency sub-sequence.
  - Multi-channel steps inside the workflow: SMS, Messenger, desktop push, ad-audience sync for retargeting, direct-mail trigger if used.
  - Suppression/exit: unsubscribe, purchase of higher rung, hard bounce. Set send-window + timezone; tag every open/click/watch/buy so the 3 Closes can branch.
