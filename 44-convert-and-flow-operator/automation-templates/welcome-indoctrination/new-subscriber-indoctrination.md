# New-Subscriber Indoctrination Sequence

- **id:** `new-subscriber-indoctrination`
- **Category:** welcome-indoctrination
- **Aliases:** Welcome Sequence · Onboarding Email Sequence · Lead-Magnet Delivery + Indoctrination · Indoctrination Funnel Emails · New Lead Nurture · Follow-Up Funnel Welcome Leg
- **Source:** DotCom Secrets — Follow-Up Funnels + the Soap Opera "Set the Stage" beat; The Funnel Hacker's Cookbook (lead/squeeze funnel thank-you page "routes the lead into a follow-up sequence"); DCS Secret #6 (Attractive Character worldview/polarity); Copywriting Secrets Secret #18 (Email Teasers).

## What it is
The foundational welcome that **every** opt-in receives. Its job is to **deliver** the promised lead magnet, **set the relationship and expectations**, get the one critical onboarding action (whitelist / move to Primary inbox), **install the brand worldview**, and **route** the lead into the deeper bond (Soap Opera Sequence) or the value ladder.

**Distinct from the Soap Opera Sequence:** indoctrination = deliver + expectations + whitelist + worldview. Soap Opera = narrative bonding + selling. Use indoctrination as the universal welcome and chain the SOS after it (or use the SOS as the indoctrination body for product-led lists).

## TRIGGER
- **What starts it:** Opt-in / lead-magnet form submit (any capture entry point).
- **Fires:** Once per contact. **Guard:** enter only if tag `indoctrinated` is NOT present.

## CHANNELS
Email (primary). Optional SMS for delivery confirmation + whitelist nudge.

## THE SEQUENCE

| # | Beat | Delay | Job | Subject angle |
|---|------|-------|-----|---------------|
| 0 | **Instant Delivery** | immediate | Deliver the lead magnet; ONE instruction (whitelist / drag to Primary); tease what's next | `Here's your [lead magnet] (+ what to do first)` |
| 1 | **Set the Stage / Welcome to my world** | +1 day | Who the AC is; backstory tease; email expectations; first curiosity loop | `Welcome to [brand] — here's how this works` |
| 2 | **Worldview / Manifesto (Polarity)** | +1 day | Install the core belief; us-vs-them line in the sand; new way vs old way | `Why [common approach] is keeping you stuck` |
| 3 | **Bridge to Offer / Hand-off to SOS** | +1 day | Invite to the next rung (offer / webinar) OR hand control to the Soap Opera Sequence | `Ready for the next step?` |

### Per-email body frameworks
- **E0 Delivery:** merged-name salutation → prominent download link (the ONE CTA) → whitelist instruction → tease tomorrow (open loop) → friendly close.
- **E1 Set the Stage:** official welcome + AC backstory tease → "free stuff better than others charge for" → set the email expectation → open loop → P.S. names next subject.
- **E2 Worldview:** state the core belief / new opportunity → us-vs-them ("talkers vs doers") line in the sand → make the reader pick a side → bridge to value ladder → single CTA.
- **E3 Bridge:** recap value delivered (reciprocity) → introduce the next rung → single CTA → if handing to SOS, tease "over the next 5 days I'll tell you the story of...".

## COPY PERSONA + SCRIPT
- **Worldview / polarity:** Attractive Character (DCS #6) — backstory, polarity, us-vs-them storyline.
- **Set-the-stage + open loops:** Soap Opera Sequence beat (DCS #7).
- **Email mechanics:** Copywriting Secrets Email Teaser (Jim Edwards #18) — subject = headline, merged-name salutation, ONE specific CTA, short friend-to-friend tone; the email's job is the click.
- **Founder-story option:** swap E2 for an Epiphany Bridge (Expert Secrets) origin story.
- **Brand clarity handoff:** if the manifesto needs sharpening, route copy to StoryBrand (Miller) / Brand Mapping persona — this template supplies the flow, not the brand architecture.

## FLEXIBILITY — Core Principle

> This template is a **GUIDE and a RESOURCE, never a rule or requirement.** It must not dominate the user's desire.

| Mode | When it applies | What the system does |
|------|----------------|----------------------|
| **1 — Explicit desire** | User states what they want | Do exactly that. This template is an optional reference only — never impose or override. |
| **2 — User is unsure** | User doesn't know what to do | Suggest this indoctrination container (deliver + expectations + worldview + hand-off) and explain the rationale; let the user decide. |
| **3 — Just do it** | User says "handle it" / "build it" | Build the full sequence — IND-00 through IND-03, tags, custom fields, if/else branches — exactly from this template. |

Every element (number of emails, worldview vs founder-story for E2, hand-off to SOS vs direct offer, cadence) is a **recommended default the user can change or skip.** The template assists; it never dominates.

---

## GHL BUILD (Skill 44 — Convert & Flow Operator, Tier 0)
**Dependencies first:**
- **Tags:** `lead-new`, `indoctrinated`, `delivered-asset`, `warm`
- **Custom fields:** `optin_source` (text), `asset_delivered` (date)
- **Custom values:** `{{lead_magnet_url}}`, `{{ac_name}}`, `{{next_step_url}}`, `{{brand_name}}`

**Workflow:**
1. **Trigger:** Form Submitted / Funnel Step (opt-in). **Filter:** tag `indoctrinated` NOT present.
2. Action: Add Tag `lead-new`; grant access if gated.
3. Email `IND-00 Instant Delivery` (immediate) + optional SMS delivery confirm → Add Tag `delivered-asset`, Set `asset_delivered`.
4. Wait 1 day → Email `IND-01 Set the Stage` → Wait 1 day → Email `IND-02 Worldview` → Wait 1 day → Email `IND-03 Bridge`.
5. Action: Add Tag `indoctrinated`; Add to Workflow `Soap Opera Sequence` (or value-ladder sales workflow).

**If/Else branches:**
- **Delivery fork:** IF E0 opened but download not clicked in 1 day → "did you grab it?" resend (email + SMS); ELSE continue.
- **Warm fork:** IF next-step CTA clicked → tag `warm`, optionally fork to sales early.
- **Suppression:** IF `unsubscribed` or `customer` → exit.

**Skill 44 notes:** dependency-first; set node `order` + `parentKey` before first save; internal-API build when Firebase token healthy, else Tier 4 agent-browser backstop + owner nudge. Email nodes reference Email-Builder templates `IND-00..IND-03`.
