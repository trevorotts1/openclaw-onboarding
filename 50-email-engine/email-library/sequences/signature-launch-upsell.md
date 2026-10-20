---
id: signature-launch-upsell
type: sequence
name: Signature Launch Upsell Follow-Up Sequence
tags: [sequence, signature-launch, upsell-followup, post-purchase, upsell-1, upsell-2, honor-the-purchase, value-multiplication, commitment-consistency, one-click, verified-purchase, route-graph-truth, no-invented-scarcity, moves-buyer-to-next-offer, founder-signature, convert-and-flow]
length: 150-300 words
best_for: [upsell, signature-launch-clients, verified-buyers, upsell-1-page, upsell-2-page, post-purchase-ascension]
---

## Style / Definition
A **three-email follow-up written once per upsell page pattern** — one sequence for **Upsell 1** and one for **Upsell 2** — for a buyer who reached that page and left without accepting. The job is narrow: **move the buyer back to the page and on to the next offer** in the approved route graph. It is an Upsell objective speaking to an existing customer, so every email opens by honoring the purchase and frames the upgrade as the same identity continued.

Two hard boundaries separate this sequence from a discount blast:
1. **The page is the source of truth.** Offer, amount, billing terms, disclosure, and any scarcity evidence come from the Skill-80 page request. Nothing is invented in the email.
2. **The route graph owns the destination.** Upsell 1 acceptance leads to Upsell 2; decline leads to Downsell 1. Upsell 2 is the final offer — acceptance or explicit decline both finish at the thank-you / access handoff.

## Purpose & Intention
The buyer already said yes once. Commitment/consistency says the next yes is easier than the first, but only while the decision still feels good. This sequence protects that feeling: it congratulates the purchase, shows how the upgrade **multiplies what they already own**, and removes friction with the one-click path already on the page. It never implies the first purchase was a mistake — that breeds regret and refunds.

## Pattern Map (fixed — no deviation)

### Pattern A — Upsell 1 (`upsell_1`)
| # | Framework | Angle |
|---|-----------|-------|
| 1 | Features-to-Benefit | What the upgrade adds, translated into what it does for them — and how it makes the original purchase worth more |
| 2 | Before-After-Bridge | Future-pace the version of the work that has the upgrade; bridge is the page, one click away |
| 3 | PAS | The specific gap that stays open without the upgrade — framed as opportunity, never as inadequacy — then the page as the fix |

### Pattern B — Upsell 2 (`upsell_2`)
| # | Framework | Angle |
|---|-----------|-------|
| 1 | ACCA | Acknowledge the previous acceptance, compliment the decision, congratulate the progress, ask for the next step |
| 2 | Star-Chain-Hook | Name the outcome, chain the proof that the final offer delivers it, hook back to the page |
| 3 | 3-B Plan | **The short email** — deliberately under 150 words. One truthful reason, one link |

Both patterns end at **their own page**. Upsell 1's next offer is Upsell 2. Upsell 2's next offer is the thank-you / access handoff.

## How To Write It
1. **Word count: 150–300 words** per email — EXCEPT Upsell 2 Email #3 (3-B Plan), deliberately shorter (<150).
2. **2 subject lines per email** (A/B), labeled. **2 preview lines per email** (A/B), labeled. Set B breaks the pattern; it is never crude and never off-brand.
3. **Label the body "Email Body:"** and label each email with its framework.
4. **Open by honoring the purchase.** Reference what they bought and one thing it already gives them. Use "and," never "but."
5. **Multiply, don't replace.** Show how the upgrade compounds the original purchase. Never frame the base purchase as insufficient.
6. **State the disclosure exactly.** Put the page's disclosure text beside the CTA, unchanged — amount, currency, billing type, and recurring terms if any.
7. **One CTA destination per pattern.** The matching upsell page. No alternate offers, no second link.
8. **Founder's ACTUAL name** in the closing signature. No placeholder ships; `[Founder Name]` below marks the engine's substitution slot.
9. **Timezone and send window belong to Skill 44.** This sequence supplies copy and order only.

## Truth Rules (fail-closed)
- **No invented deadline, countdown, seat cap, bonus expiry, or price.** Scarcity appears ONLY when the page request carries non-empty `factual_scarcity_evidence`.
- Amount, currency, and billing terms match the page `disclosure` verbatim. Recurring offers name the full term (e.g. today + remaining payments).
- Never promise that the email charges the buyer. The guarded one-click action lives on the page. If one-click is unavailable, the page blocks the paid action and offers safe continuation — say "on the page," not "from this email."
- **Eligibility:** verified succeeded original purchase is required. Upsell 2 requires a verified succeeded Upsell 1 **or** Downsell 1 purchase. A bump alone never qualifies. A client-side claim such as `acceptedU1=true` is never proof.
- **Suppression:** bought that instance, or already owns it → suppress the offer email or route to the next page. Payment pending/failed → page remains recoverable; no "declined" language.

## Use Cases
- Post-purchase ascension after the Signature Launch main offer (Upsell 1)
- Final ascension after Upsell 1 or Downsell 1 (Upsell 2)
- Re-sends after the buyer returns to the launch pages without completing the offer
- Draft sequence generated alongside each Skill-80 page in a Skill-49 / Skill-83 launch

## Detailed Example — Upsell 1, Email 1 of 3

**Email 1 — Framework: Features-to-Benefit**

**Subject Line A:** {{contact.first_name}}, your purchase just earned a second gear
**Subject Line B:** Most buyers never switch this part on, {{contact.first_name}}
**Preview Text A:** You made the right call. Here is how to compound it.
**Preview Text B:** Same system. A different output. Still one click.

**Email Body:**

{{contact.first_name}},

First — good call on {{original_offer_name}}. It already covers {{one_thing_it_gives_them}}, and that part works whether or not you read another line of this email.

Here is what most buyers discover next: **{{upsell_offer_name}} is the second gear.**

**{{feature_1}}** means {{benefit_1}}, so the work you already own stops waiting on you.

**{{feature_2}}** means {{benefit_2}}, so the result you bought shows up sooner.

Notice the theme: this does not replace what you purchased. **It multiplies it.** Same foundation, more output.

Because your account and payment method are already set up, the upgrade takes one click and everything carries over:

{{disclosure_text}}

**[Return to your upgrade page →]**

Either way, {{original_offer_name}} serves you well. This is simply the difference between owning the engine and running it at full power.

[Founder Name]

*(Engine note: fill feature/benefit pairs from the approved upsell page copy; paste `disclosure_text` unchanged; founder's actual name replaces the slot.)*

## Detailed Example — Upsell 2, Email 1 of 3

**Email 1 — Framework: ACCA**

**Subject Line A:** {{contact.first_name}}, you already proved the pattern
**Subject Line B:** The last door in this launch, {{contact.first_name}}
**Preview Text A:** Acknowledge. Compliment. Congratulate. One next step.
**Preview Text B:** You said yes once. This is the same decision, finished.

**Email Body:**

{{contact.first_name}},

You accepted {{previous_offer_name}}. That was the right decision — and it tells us something useful about you: you act when the path is clear.

Compliment where it belongs: you did not just buy a product. You chose the version of your work that runs on a system instead of on willpower.

So here is the congratulations part: that choice is already producing {{progress_outcome}}.

The final piece is **{{upsell_2_offer_name}}** — {{one_sentence_outcome}}. It takes everything you already own and finishes the build.

{{disclosure_text}}

**[Review the final upgrade on your page →]**

You have already made the harder decision. This one is the same decision, one level up. If it is not for you, your page closes cleanly at the thank-you step — nothing else to decline.

[Founder Name]

*(Engine note: use only outcomes evidenced in the approved page copy; paste `disclosure_text` unchanged; decline route is the thank-you handoff.)*

## Quality Checklist
- [ ] One sequence pair covers both page patterns: `upsell_1` and `upsell_2`
- [ ] Triggered only after the matching Skill-80 upsell page is written
- [ ] 3 emails per pattern, frameworks matching the pattern map exactly
- [ ] Every email 150–300 words EXCEPT Upsell 2 Email #3 (shorter, <150)
- [ ] Every email: 2 labeled subject lines + 2 labeled preview lines (A/B)
- [ ] Opening honors the previous purchase; zero inadequacy framing; base purchase remains a good decision
- [ ] Upgrade shown to multiply the original purchase's value
- [ ] Disclosure pasted verbatim beside the CTA; amount, currency and billing terms match the page
- [ ] Zero invented deadline, scarcity, price or bonus; scarcity only with `factual_scarcity_evidence`
- [ ] One CTA destination per pattern (its own upsell page); no alternate offers
- [ ] Next offer matches the route graph: U1 → U2 on accept, D1 on decline; U2 → thank-you on accept or decline
- [ ] Eligibility honored: verified purchase only; bump alone never qualifies for U2; client-side claims never proof
- [ ] Suppression honored for bought/already-owned; pending/failed keeps the page recoverable
- [ ] Body labeled "Email Body:"; each email labeled with its framework
- [ ] Founder's ACTUAL name in every signature — zero placeholders shipped
- [ ] Standard formatting: ≤3-sentence paragraphs, bolds, CTAs on their own lines, ≤4 emojis
