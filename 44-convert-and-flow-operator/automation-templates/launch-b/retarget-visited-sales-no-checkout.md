# Launch B — Retarget: Visited Sales Page, No Checkout (Nudge)

- **id:** `launch-b-retarget-visited-sales-no-checkout`
- **Category:** multichannel-automation
- **Derived from:** `44-convert-and-flow-operator/automation-templates/multichannel-automation/behavioral-retargeting-page-visit-fire` (Audiences C and C2)
- **Trigger:** sales-page visit with no checkout page visit inside the attribution window
- **Channels:** Facebook / Instagram retargeting · GHL email nudge · GHL SMS nudge
- **Draft only:** build as a GHL draft, publish only after the operator approves the copy and the pixel test fires. Buyer suppression (`retarget-b-buyer` + `purchased-[offer-id]`) is permanent and never removed.

## What it is
The narrow retarget layer for one drop-off: someone read the sales page and never reached checkout. They get a proof email, an objection email, one optional SMS, and a retargeting ad that changes when they come back to the page.

It is deliberately smaller than the parent 5-audience map. Three boundaries define it:

- **Starts at the sales page.** Landing-page and opt-in behaviour belong to other audiences.
- **Stops at checkout.** The moment someone opens the checkout page they leave this audience and belong to the abandoned-cart family. This layer never sends cart language.
- **Buyers are suppressed permanently.** No ad, no email, no SMS for a product already bought.

## TRIGGER
Page Visit (sales page) → Wait 60 minutes → If checkout page visited, end. Otherwise tag `retarget-b-visited-sales`.

The 60-minute wait is the whole exclusion mechanism. It costs one node and it stops the nudge from ever landing on someone who is mid-purchase.

## SEQUENCE

| Beat | Timing | What runs | Purpose |
|------|--------|-----------|---------|
| Setup | once | Pixel on sales / checkout / confirmation · custom audience from `retarget-b-visited-sales` · suppression audience from `retarget-b-buyer` + `retarget-audience-d` | Infrastructure, verified with a test visit |
| 1 | T+60 min | Add `retarget-b-visited-sales` | Separate readers from checkout-starters |
| 2 | T+2h | Email #1 — named testimonial with numbers, link to sales page | Give the proof the page could not give |
| 3 | T+48h | Email #2 — name the #1 objection, answer it. SMS once if opted in | Remove the specific hesitation |
| 4 | on 2nd visit | Add `retarget-b-high-intent` → objection-handling ad set | Escalate creative, not message volume |
| Guard | continuous | Checkout visit → remove tags, stop nudge. Purchase → remove all, add `retarget-b-buyer` | The interrupt always wins |

## AD CREATIVE

| Audience | Headline | Body | CTA | Destination |
|----------|----------|------|-----|-------------|
| B — first visit | "[Customer Name] got [specific result]" | One testimonial quote with concrete before/after. No countdown, no cart language. | See how it works | Sales page |
| B — high intent | "Still thinking about [offer]?" | The #1 objection, answered in the first line. FAQ format. | Read the answer | Sales page, anchored to the objection |

## COPY RULES
- No "cart", no "you left something behind", no "complete your order" — those describe a state the reader is not in. Using them here makes the sequence lie.
- One CTA per message. Plain, specific, unhurried.
- Proof over persuasion. Named results beat adjectives.
- If a real deadline exists (launch close, bonus expiry) it may appear once in the ad creative. A manufactured one never appears.
- Retargeting copy is not email copy: short, scannable, built for the click back.

## FLEXIBILITY

| Mode | When | What to build |
|------|------|---------------|
| **1 — Explicit desire** | Operator has their own retargeting plan | Do exactly that. This file is reference. |
| **2 — Unsure** | No retargeting set up | Beats 1 and 2 only: tag plus proof email. Most of the value, no ad spend. |
| **3 — Just do it** | "Set this up" | All four beats, both creatives, both interrupts. |

Core principle: a guide and a resource, never a rule.

Never simplify away: the checkout interrupt, buyer suppression, the SMS opt-in check.

## GHL BUILD (Skill 44 — Convert & Flow Operator)

**Dependencies first**
- Tags: `retarget-b-visited-sales`, `retarget-b-high-intent`, `retarget-b-buyer`, `purchased-[offer-id]`, `retarget-audience-d`
- Integrations: GHL Facebook Integration (custom audience sync) or Facebook Pixel · GHL tracking pixel on sales/checkout/confirmation · GHL email + SMS with one shared opt-out

**Workflows**

| Name | Structure |
|------|-----------|
| Delayed tag | Page Visit (sales) → Wait 60 min → If/Else checkout visited? Yes → End. No → Add `retarget-b-visited-sales` |
| Proof nudge | Tag Added → Email #1 → Wait 48h → If/Else link clicked? Yes → End. No → Email #2 |
| SMS nudge | Tag Added → If SMS opted in → Wait 48h → Send SMS once → End |
| Repeat visit | Page Visit (sales) count ≥ 2 → Add `retarget-b-high-intent` |
| Checkout interrupt | Page Visit (checkout) → Remove `retarget-b-visited-sales`, `retarget-b-high-intent` → remove from nudge workflow |
| Purchase interrupt | Payment Event OR Page Visit (confirmation) → Remove all `retarget-b-*` → Add `retarget-b-buyer` → Add `purchased-[offer-id]` |

**Skill 44 notes:** set `order` + `parentKey` before the first save on every node. Page Visit triggers need funnel-step tracking or a webhook from an external page — confirm the pixel fires with a test visit before building anything downstream. Facebook audience sync can lag 1–24h, so treat the email/SMS nudge as the same-day channel and the ad audience as follow-up. Cap ad frequency at the ad-set level, not with a per-contact counter.

## SCOPE
**In:** sales-page visit, no checkout.
**Out:** checkout without purchase (abandoned-cart family) · buyers (ascension ads) · landing page without opt-in (Audience A in the parent template).
