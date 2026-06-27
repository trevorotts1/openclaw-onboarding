# Behavioral Retargeting — Page-Visit Pixel Fire + List Membership Update

- **id:** `behavioral-retargeting-page-visit-fire`
- **Category:** multichannel-automation
- **Aliases:** Retargeting Pixel Fire Sequence · Page-Visit Behavioral Retargeting · Funnel Step Retargeting Automation · Behavioral Ad Targeting by Funnel Stage · What More Can We Do — Retargeting Layer
- **Source:** Lead Funnels Swipe File — Follow-Up Funnel: "once someone lands on one of your funnel pages, you can create an action where it says, 'If they hit this page, go to Facebook and add them to this retargeting list,' or 'Take them off this retargeting list and move them over to this one.'" Supporting: Marketing Secrets Blackbook Secrets #49 + #66 + #79, BRUNSON-FUNNEL-LIBRARY Entry #24.

> "If people click on your landing page but don't give you an email address, retarget them with ads." — Marketing Secrets Blackbook, Secret #49

> "The more sales modalities you can use in your funnel, the better." — Marketing Secrets Blackbook, Secret #66

## What it is
A passive tracking layer that runs in the background of every funnel. Every time a prospect visits a funnel page, their ad audience membership updates in real time — they move to a new audience or get removed from a current one. The ads they see on Facebook/Instagram change automatically to match exactly where they dropped off in the funnel. Buyers are removed from all sales audiences instantly. No manual work after initial setup.

## TRIGGER
This is not a single trigger — every page visit is its own trigger event that updates audience membership. The automation runs continuously throughout the funnel's lifetime.

## CHANNELS
Facebook / Instagram Retargeting Ads (custom audiences) · Google Display (optional expansion) · GHL automation tags (bridge layer between page visits and ad audiences)

---

## THE 5-AUDIENCE FUNNEL RETARGETING MAP

| Audience | Trigger | What they see | Goal |
|----------|---------|--------------|------|
| **A** — Saw landing page, no opt-in | Landing page visit + no form submit | Lead magnet ad with social proof | Get them to opt in |
| **B** — Opted in, no offer page visit | Form submit + no offer page visit | Content/bridge ad → offer | Get them to the offer page |
| **C** — Visited offer page (1x), no purchase | Offer page visit + no purchase | Testimonial ad with specific results | Provide proof, drive purchase |
| **C2** — Visited offer page (2x+), no purchase | 2+ offer page visits + no purchase | Objection-handle ad / FAQ | Remove the specific hesitation |
| **D** — Reached checkout, no purchase | Checkout page visit + no purchase confirmation | "Your cart is waiting" ad | Recover the nearly-completed sale |
| **E** — Buyer | Purchase confirmation | Upsell/ascension ad ONLY — never show ad for something they bought | Ascend the value ladder |

---

## AUDIENCE-BY-AUDIENCE BREAKDOWN

### Audience A — Saw Landing Page, No Opt-In
**Trigger:** Landing page visit + no form submission within 5 min.  
**Add tag:** `retarget-audience-a`  
**Ad type:** Awareness + lead capture  
**Copy angle:** Curiosity + social proof. "3,000+ people already downloaded [lead magnet title]." No hard sell.  
**Destination:** Original landing page.  
**Priority:** Lowest (highest volume, least qualified — keep spend modest).

---

### Audience B — Opted In, No Offer Page Visit
**Trigger:** Form submission on opt-in page.  
**Audience update:** Remove from A; Add to B.  
**Ad type:** Bridge / consideration  
**Copy angle:** Educational bridge. "If you liked [lead magnet], you need to see [offer topic] because..."  
**Destination:** Offer/sales page.  
**Priority:** Medium.

---

### Audience C — Visited Offer Page (1 Visit), No Purchase
**Trigger:** Offer/sales page visit.  
**Audience update:** Remove from B; Add to C.  
**Ad type:** Social proof / conversion  
**Copy angle:** Third-person testimonial — real name, specific before/after numbers.  
"[Customer name] said: '[result in their own words]'"  
**Destination:** Offer page.  
**Priority:** High.

### Audience C2 — Visited Offer Page Multiple Times, No Purchase
**Trigger:** Second+ offer page visit.  
**Tag added:** `retarget-audience-c2-high-intent`  
**Ad type:** Objection removal  
**Copy angle:** FAQ or direct objection handle. "Still thinking about [offer]? Here's the #1 question people ask..." + answer.  
**Destination:** Offer page.  
**Priority:** Very high — these contacts are close to buying.

---

### Audience D — Reached Checkout, No Purchase
**Trigger:** Checkout page visit + no purchase confirmation.  
**Audience update:** Remove from C/C2; Add to D.  
**Ad type:** Transaction completion — highest priority  
**Copy angle:** Direct, transactional, brief. "You were moments away from [result]. Your cart is still here: [link]"  
**Optional:** If a genuine incentive exists (bonus, discount): include it.  
**Destination:** Direct checkout page (skip the sales page — don't make them re-read the offer).  
**Priority:** Highest — send the cart-abandon email+SMS sequence alongside this ad.

---

### Audience E — Buyer
**Trigger:** Purchase confirmation page visit OR payment event in GHL.  
**Audience update:** Remove from ALL audiences A through D. Add to E (buyer).  
**Rule:** NEVER show a buyer an ad for a product they already own. Audience E is for ascension ads (next rung of value ladder) only.  
**Priority:** High for ascension. Zero for the original offer.

---

## SWITCHING MODALITIES IN RETARGETING
Per Marketing Secrets Blackbook Secret #66: if the prospect dropped off on a VSL page (video), retarget them with a written testimonial or text ad. If they dropped off on a written copy page, retarget with a short video. "The more sales modalities you can use in your funnel, the better" — retargeting lets you switch modalities after the initial drop-off without rebuilding the funnel.

## CHANNEL EXPANSION PRINCIPLE
Per Marketing Secrets Blackbook Secret #79: once Facebook retargeting is working, expand to Instagram, YouTube (pre-roll), Google Display, and Pinterest with the same audiences and adapted creative. Same offer, new channels. No new product needed.

---

## AD CREATIVE BRIEFS

| Audience | Headline | Body | CTA |
|----------|---------|------|-----|
| A | "Download [Lead Magnet Title] Free" | "[X,000] people already grabbed this — here's why..." | "Get Free Access" |
| B | "The Next Step After [Lead Magnet Topic]" | "If [lead magnet result] worked for you, [offer] will [next result]..." | "See How" |
| C | "[Customer Name] Got [Specific Result]" | "[Testimonial quote with numbers]" | "Get the Same Result" |
| C2 | "Still Thinking About [Offer]?" | "The #1 question: [objection]. Here's the real answer..." | "See for Yourself" |
| D | "Your [Offer Name] Cart Is Waiting" | "You started [X]. Here's your link to finish: [link]" | "Complete My Order" |

---

## COPY PERSONA + SCRIPT
- **Audience A/B:** Curiosity-driven, no pressure. Not selling — informing.
- **Audience C:** Social proof — other people's words and numbers. The AC may not even appear.
- **Audience C2:** Direct, question-answering, helpful. Address the specific hesitation.
- **Audience D:** Transactional. Brief. One CTA only.
- **Note:** Retargeting ad copy is NOT email copy. Keep it short, visually distinct, and scannable. The ad's only job is the click back to the funnel page.

## FLEXIBILITY — Core Principle

> This template is a **GUIDE and a RESOURCE, never a rule or requirement.** It must not dominate the user's desire.

| Mode | When it applies | What the system does |
|------|----------------|----------------------|
| **1 — Explicit desire** | User has their own retargeting strategy | Do exactly that. Template is reference only. |
| **2 — User is unsure** | No retargeting set up | Suggest starting with Audience D (checkout abandon) — highest ROI, then expand to C, then B, then A. Let user decide. |
| **3 — Just do it** | "Set up retargeting" | Build all 5 audiences with pixel mapping, audience logic, and ad creative briefs above. |

Start with D and C (closest to the money). The full 5-audience map is the eventual build; starting partial is fine and recommended.

---

## GHL BUILD (Skill 44 — Convert & Flow Operator)

**Dependencies first:**
- **Tags:** `retarget-audience-a`, `retarget-audience-b`, `retarget-audience-c`, `retarget-audience-c2-high-intent`, `retarget-audience-d`, `retarget-audience-e-buyer`, `purchased-[offer-id]`
- **Integrations required:** GHL Facebook Integration (custom audience sync) OR Facebook Pixel on all funnel pages + webhook from page platform

**GHL automation per funnel page:**

| Page | GHL Action |
|------|-----------|
| Landing page visit + no opt-in (5 min wait) | Add `retarget-audience-a` |
| Opt-in form submit | Remove `a`; Add `retarget-audience-b` |
| Offer/sales page visit | Remove `b`; Add `retarget-audience-c` |
| Offer page 2nd visit | Add `retarget-audience-c2-high-intent` |
| Checkout page visit | Remove `c`, `c2`; Add `retarget-audience-d` |
| Purchase confirmation / payment | Remove `a`, `b`, `c`, `c2`, `d`; Add `retarget-audience-e-buyer`; Add `purchased-[offer-id]` |

**Page-visit tracking in GHL:** Requires GHL tracking pixel on funnel pages (GHL funnels natively; external pages need pixel code + webhook). Confirm pixel fires are working before building audience-update workflows.

**Skill 44 notes:** Set `order` + `parentKey` before first save on every node. Page-visit triggers in GHL may have latency (up to 24h for audience sync with Facebook). For highest-urgency audiences (D — checkout abandon), pair with the abandoned-cart email/SMS sequence for immediate outreach while the ad retargeting updates.
