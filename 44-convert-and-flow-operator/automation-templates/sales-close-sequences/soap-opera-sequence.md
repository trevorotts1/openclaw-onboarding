# Soap Opera Sequence — 5-Email Bonding / EMOTION Close

**id:** `soap-opera-sequence` · **category:** sales-close-sequences
**Aliases:** SOS, 5-day welcome sequence, indoctrination sequence, Attractive Character bonding sequence, Emotion close
**Source:** DotCom Secrets (Brunson) · Epiphany Bridge (Expert Secrets / Network Marketing Secrets) · subject-line craft from Copywriting Secrets (Edwards)

> **Where it sits in the 3 Closes:** This is the **EMOTION close.** "People do not buy based on logic; they buy based on emotion, then try to justify their purchase logically" (Brunson, *Network Marketing Secrets*, Secret #4). The Soap Opera Sequence bonds the brand-new subscriber to the Attractive Character *before* any Logic or Fear close is attempted.

---

## TRIGGER
- **What starts it:** New opt-in (lead magnet / squeeze page), new subscriber, or first purchase (welcome variant).
- **Entry condition:** has email; not already tagged `sos-started`.
- **Exit:** purchase → buyer track; or finish Email 5 → graduate to the **Seinfeld Daily Sequence**.

## CHANNELS
Email (primary) · optional SMS nudge on Email 4 & 5 · optional Facebook Messenger mirror (DotCom / Lead Funnels multi-channel follow-up funnel).

## CADENCE
One email/day, Day 0–4. **Every email ends on an open-loop cliffhanger** that pulls the reader into tomorrow's email.

---

## THE SEQUENCE (the 5 beats)

| # | Email | Beat / Purpose | Subject angle | Body framework | Persona script |
|---|-------|----------------|---------------|----------------|----------------|
| 1 | **Set the Stage** | Introduce yourself, deliver the freebie, *tease* the transformation story to come. Bond, open loop #1. Almost no pitch. | "I have to tell you something (it starts tomorrow)" | Hello → confirm download → "before you dig in, something personal…" → tease story → cliffhanger | Attractive Character backstory tease |
| 2 | **High Drama, Backstory & the Wall** | Open *in the middle of* the worst moment, rewind to backstory, hit the **Wall** (old vehicle failed). Reader sees themselves. | "I was sitting in my car, broke…" | Cold open at peak drama → "let me back up" → Backstory + Desire → External + Internal struggle → the Wall → cliffhanger | Epiphany Bridge: Backstory/Desire/External/Internal/Wall + Edwards Agitate |
| 3 | **The Epiphany** | The aha moment / new opportunity, the Plan, the Conflict. Frame discovery as a **new vehicle**, not an improvement. | "Then I discovered the one thing that changed it all" | Resolve loop → Epiphany → Plan → Conflict → first taste of Achievement → soft link to offer → cliffhanger | Epiphany Bridge: Epiphany/Plan/Conflict |
| 4 | **Hidden Benefits** | Reveal the upside they didn't expect; future-pace the result. Logic begins entering under the emotion. | "The benefit nobody talks about…" | **Before/After/Bridge** (Edwards): paint Before → vivid After → Bridge = the offer. 3–5 hidden benefits via "which means…". Cliffhanger: "tomorrow this goes away." | Edwards Before/After/Bridge + Ultimate Bullet Formula |
| 5 | **Urgency & CTA** | The close. Recap transformation, drive ONE action with an **honest** reason to act now. First real Fear/urgency touch. | "This closes tonight" | One-line recap → restate offer (what/how/when/how much) → honest urgency (limited time/price/quantity) → guarantee → single CTA → P.S. with deadline | Edwards 13-part close + Brunson urgency/scarcity (honored) |

---

## COPY PERSONA & SCRIPT
- **Primary:** Russell Brunson — Attractive Character + **Epiphany Bridge Script**: *Backstory → Desire → External → Internal → Wall → Epiphany → Plan → Conflict → Achievement → Transformation.*
- **Supporting:** Jim Edwards — curiosity subject lines, open-loop hooks, **Before/After/Bridge** (future pacing), Ultimate Bullet Formula ("It ___ so you can ___ which means ___").
- **Voice rules:** make it about THEM; the story must be TRUE; every benefit ties to ≥1 of the Ten Reasons People Buy.

---

## GHL BUILD (Skill 44 → GoHighLevel)
**Workflow:** `SOS — Soap Opera Sequence (5-Day Emotion Close)`

1. **Trigger:** *Contact Tag Added* = `lead-[magnet]` **or** *Form Submitted* = opt-in form. **Filter:** tag `sos-started` missing.
2. **Add Tag** `sos-started`.
3. **Email 1** (immediate) → **Wait 1 day** → **Email 2** → **Wait 1 day** → **Email 3** → **Wait 1 day** → **Email 4** (+ optional SMS) → **Wait 1 day** → **Email 5** (+ SMS).
4. **Add Tag** `sos-complete` → enroll into **Seinfeld Daily Sequence** workflow.

**Wait steps:** 5 × "Wait 1 day," ideally "wait until 8:00am contact-timezone" for a clean daily rhythm.

**If/Else & Goals:**
- **Purchase Goal** (`buyer-[offer]`) anywhere → exit SOS, enroll buyer onboarding, STOP close emails.
- Email 1 not opened in 24h → resend with new subject before continuing.
- Email 5 clicked + no purchase → enroll in `scarcity-deadline-close` for a final 24h push.

**Build it as a Workflow (not a drip Campaign)** so the purchase Goal can short-circuit the sequence. Personalize `{{contact.first_name}}`.

## INTEGRITY GUARDRAILS
Honor every deadline literally (no re-opened carts / no magic restock). Story must be true. Every claim provable.

## KPIs
Email 1 open rate · Email 3→4 CTR (epiphany landed) · Email 5 conversion · % graduating to Seinfeld · revenue per new lead.
