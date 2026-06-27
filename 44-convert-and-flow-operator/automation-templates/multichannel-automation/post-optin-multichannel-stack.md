# Post-Opt-In Multichannel Stack

- **id:** `post-optin-multichannel-stack`
- **Category:** multichannel-automation
- **Aliases:** Follow-Up Funnel · Actionetics Follow-Up Funnel · Automation and Follow-Up Funnel · Email + SMS + Messenger Sequence · Communication Funnel · Lead Layering Sequence
- **Source:** Lead Funnels Swipe File — Chapter 3, Step #5 (Brunson). Supporting: Funnel Hacker's Cookbook (Actionetics), Marketing Secrets Blackbook Secrets #42 + #49, DotCom Secrets Secrets #7–#8, BRUNSON-FUNNEL-LIBRARY Entry #24.

> "Follow-up funnels are more than just emails. Emails are just a small part of following up. There are also text messages, direct-mail gifts and postcards, Facebook Messenger messages, and special follow-up email offers. Actionetics customizes the follow-up based on each person's purchases, their social influence, and their actions within your funnel." — Marketing Secrets Blackbook, Secret #42

> "If they give you their email address but don't buy, contact them with an email or text or messenger sequence." — Marketing Secrets Blackbook, Secret #49

## What it is
The instant a contact opts in, a layered multichannel orchestration fires. Email is the core. Facebook Messenger, desktop browser push notifications, SMS, retargeting ads, and (for premium offers) direct mail stack on top based on what the contact subscribes to. Brunson's data: 34% of email opt-ins also subscribe to Messenger (which has 3–5x higher open rates than email); 20% of thank-you page visitors allow desktop push. More channels = higher relationship value = more ascension up the value ladder.

## TRIGGER
- **What starts it:** Opt-in form submit / lead magnet claim on any landing page.
- **GHL trigger:** Form Submitted / Funnel Step Submitted on opt-in page.
- **Fires:** Once per contact per campaign. Re-entry guard: tag `mc-stack-started` NOT present.

## CHANNELS
| Channel | How it's added | Adoption rate (Brunson) |
|---------|---------------|------------------------|
| Email | Core — collected at opt-in | ~100% of opt-ins |
| Facebook Messenger | Checkbox on opt-in / thank-you page | ~34% |
| Desktop Push Notification | Browser permission dialog on thank-you page | ~20% |
| SMS / Text | Phone field at opt-in or thank-you page micro-form | Varies |
| Retargeting Ads | Pixel fires on every funnel page; audience updated by step | Passive — all visitors |
| Direct Mail | Triggered for high-value contacts by RFMS score or repeated sales page visits | Selective |

## THE SEQUENCE

### Step 1 — Immediate: Lead Magnet Delivery (Email)
**When:** 0 min after opt-in.  
**Job:** Deliver what was promised. Instant trust deposit. Set expectations for what comes next.  
**Subject angle:** `Here's your [lead magnet] — plus what's coming next`  
**Body:** delivery link → bridge sentence to next step → relationship seed ("I'll be in touch over the next few days") → P.S. noting other channel mirrors if active.

---

### Step 2 — Simultaneous: Layer Messenger + Desktop Push (on the Thank-You Page itself)
**When:** Fires on thank-you page load — not a workflow wait step.  
**Channels:** Messenger checkbox widget + browser push permission dialog.  
**Note:** Neither requires extra data entry. Messenger: clicked by ~34%. Push: allowed by ~20%. Both stack silently.

---

### Step 3 — +5 min: Messenger Delivery (if subscribed)
**Condition:** Tag `messenger-subscribed` present.  
**Job:** Deliver the lead magnet link directly in Messenger. Buzzes on their phone even if the email goes to spam.  
**Body:** `"Hey [name] — [AC name] here. Here's the [lead magnet] you grabbed: [link]. Talk soon."`

---

### Step 4 — +2 days: Behavioral Branch on Email Open/Click
**Channels:** Email (primary) → SMS or Messenger if email not opened.  
**Job:** Follow-up content or story email. Then branch:

| Signal | Action |
|--------|--------|
| Email opened + clicked | Continue email sequence normally |
| Email opened, not clicked | Messenger/SMS nudge next day: "Did you get a chance to check this out? [link]" |
| Email NOT opened within 48h | SMS + Messenger: "Hey [name] — sent you something about [topic] via email. Quick [read/watch]: [link]" |

*This is the book's explicit principle: "contact them with an email or text or messenger sequence" for non-buyers.*

---

### Step 5 — +4 days: Desktop Push + Email
**Channels:** Desktop Push (if subscribed) + Email.  
**Push format:** Title = `[AC name]:` · Message = 1-sentence hook · URL = destination page.  
**Branch:** Push clicked → tag `push-engaged`; Not clicked within 48h → no additional push, switch to next email.

---

### Step 6 — +7 days: Retargeting Ad Fire + Email Offer
**Channels:** Email (direct offer) + Retargeting Ads (running in background from Day 1).  
**Retargeting audience logic:**

| Audience | Trigger | Ad content |
|----------|---------|------------|
| A — Saw landing page, no opt-in | Page visit pixel | Lead magnet ad with social proof |
| B — Opted in, not visited offer page | Opt-in confirmed | Content/bridge ad → offer |
| C — Visited offer page, no purchase | Offer page pixel | Testimonial / urgency ad for the offer |
| D — Reached checkout, no purchase | Checkout page pixel | "Your order is waiting" ad |
| Buyer | Purchase confirmation pixel | **Remove from ALL non-buyer audiences immediately** |

---

### Step 7 — Days 14–60: The 3-Closes Framework (over the follow-up arc)
The ongoing follow-up email sequence moves through three closing "temperatures," drawn from Brunson's copy principles (emotion drives buying decisions; logic justifies them; urgency / fear of loss moves people to act now):

| Window | Close type | What the emails do |
|--------|-----------|-------------------|
| Days 1–14 | **Emotion close** | Soap Opera + Seinfeld stories. The AC bonds with the reader through parables, character flaws, shared experiences. Prospect feels "this person gets me." |
| Days 15–30 | **Logic close** | Case studies, testimonials with specific numbers, ROI breakdowns, FAQs. The prospect has emotional desire; now give them the rational arguments to justify the decision. |
| Days 30–60 | **Fear close** (urgency/scarcity) | Real deadline (cart closing, cohort starting, price rising), concrete loss framing ("here's what you'll miss"). **Brunson rule: urgency must be REAL — fake deadlines destroy credibility.** |

---

### Step 8 — Purchase Event (fires whenever it happens): Channel Cleanup + Buyer Onboarding
**Trigger:** Purchase confirmation / payment received.  
**Actions:** Add tag `purchased-[offer-id]`; remove from all non-buyer retargeting audiences; stop all email/SMS/Messenger sequences for this offer; start buyer onboarding workflow immediately.  
**Rule:** Never retarget or sales-email a buyer for a product they already own.

---

## RFMS Score (Brunson's Contact Ranking System)
Each contact gets an action score based on **Recency** (how recently they engaged), **Frequency** (how often they engage/buy), **Monetary Value** (total spend), and **Social** (social email = 80x more valuable per Brunson; social follower count). High-RFMS contacts get priority attention, direct mail consideration, and personal outreach.

## COPY PERSONA + SCRIPT
- **Email (after Soap Opera Sequence):** Daily Seinfeld format (DCS Secret #8) — 90% entertainment / 10% content. Every story ties back to an offer. Email's only job = the click. The page sells.
- **SMS:** Ultra-short, casual, 1–2 sentences. Never formal. "Hey [name] — quick [thing]: [link]"
- **Messenger:** Conversational DM tone. 2–3 sentences. Link inline.
- **Push:** Title = brand/AC. Message = 1-sentence hook. Must earn the interrupt.

## FLEXIBILITY — Core Principle

> This template is a **GUIDE and a RESOURCE, never a rule or requirement.** It must not dominate the user's desire.

| Mode | When it applies | What the system does |
|------|----------------|----------------------|
| **1 — Explicit desire** | User specifies their channels/sequence | Do exactly that. Template is reference only. |
| **2 — User is unsure** | User doesn't know which channels to activate | Suggest email + Messenger checkbox (low friction) + desktop push (zero data entry), explain layering rationale, let user decide. |
| **3 — Just do it** | "Build the multichannel stack" | Build the full orchestration from this template. |

Every element (channels chosen, delay timing, branch conditions, 3-closes pacing) is a **recommended default the user can change or skip.** If a contact hasn't subscribed to a channel, that step is skipped silently. The template assists; it never dominates.

---

## GHL BUILD (Skill 44 — Convert & Flow Operator)

**Dependencies first** (caf refuses to build if these don't exist):
- **Tags:** `mc-stack-started`, `messenger-subscribed`, `push-subscribed`, `sms-subscribed`, `push-engaged`, `retarget-audience-a/b/c/d`, `purchased-[offer-id]`
- **Custom fields:** `mc_optin_date (date)`, `rfms_score (number)`, `last_email_open (date)`, `last_click_date (date)`
- **Custom values:** `{{lead_magnet_url}}`, `{{offer_page_url}}`, `{{ac_name}}`, `{{brand_name}}`

**Workflow nodes (in order):**
1. Trigger: Form Submitted. Filter: `mc-stack-started` NOT present.
2. Add Tag `mc-stack-started`; Set `mc_optin_date = {{now}}`; Add to retargeting audience B.
3. Email `MC-01 Lead Magnet Delivery` (immediate)
4. If/Else: `messenger-subscribed` present → Messenger `MC-M01 Delivery` (5 min); else skip
5. Wait 2 days
6. If/Else: email opened in 48h? Yes → Email `MC-02 Content`; No → SMS `MC-S01 Nudge` + (if subscribed) Messenger `MC-M02 Nudge`
7. Wait 2 days
8. If/Else: `push-subscribed` present → Push `MC-P01`; else skip
9. Email `MC-03 Story + Offer Bridge`
10. Wait 3 days
11. If/Else: `purchased-[offer-id]` present → exit to buyer onboarding; else → Email `MC-04 Direct Offer` + confirm retargeting audience C
12. Wait 7 days → Logic-close emails MC-05–MC-08 (with buyer check before each)
13. Wait 14 days → Fear-close emails MC-09–MC-11 (with buyer check before each) + trigger direct mail for RFMS-qualified contacts
14. Purchase event (at any point): Add `purchased-[offer-id]`; remove retargeting audiences; stop sequences; start buyer onboarding.

**Channel guards on every Messenger/SMS/Push step:** only send if the matching subscription tag is present; otherwise skip silently.

**Skill 44 notes:** set each node's `order` + `parentKey` before first save. Email templates MC-01..MC-11 built in GHL Email Builder. SMS templates MC-S01, MC-S02. Messenger MC-M01, MC-M02. Push MC-P01.
