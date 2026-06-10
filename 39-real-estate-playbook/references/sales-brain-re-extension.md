# Sales-Brain Real-Estate Extension (Skill 39 → Skill 38)

This is an ADDITIVE extension to Skill 38's Sales-Brain. It is installed by
`39-real-estate-playbook/scripts/05-install-sales-brain-extension.sh` into
`38-conversational-ai-system/protocols/extensions/real-estate-sales-brain.md`.
It does NOT modify any Skill 38 core protocol file. Skill 38 reads every `*.md`
under its `protocols/extensions/` folder as an additive overlay.

## Vertical objection patterns (real estate)

| Objection | Reframe (empathy → evidence → next step) |
|---|---|
| "We want to wait for rates to drop." | "Totally fair. Worth noting: waiting can mean more competition and higher prices when rates fall — many buyers refinance later. Want me to pull what's actually available in your range now?" |
| "Zillow says my home is worth more." | "Automated estimates miss condition, upgrades, and hyper-local comps. Let me run an actual CMA from recent nearby sales so we price on reality, not an algorithm." |
| "Let's just list high and see." | "Overpricing usually costs more — the listing goes stale, then you chase the market down. A correctly-priced home tends to sell faster and often for more. Here's the comp data." |
| "We'll sell it ourselves (FSBO)." | "Respect that. A few things FSBOs often hit: pricing, exposure, negotiation, and disclosure liability. Happy to show what representation changes — no pressure." |
| "Your commission is too high." | "Let's talk about net-to-you, not the percentage. Here's how marketing + negotiation typically affects your final number." |

## CMA pricing-reveal TIMING rule

Do NOT reveal a CMA value (or react to the seller's number) until AFTER:
1. Motivation + timeline are understood (seller qualification protocol), AND
2. The comps have actually been pulled (`scripts/03-property-lookup.sh
   --want comps`). If comps are an HONEST GAP, say so — never anchor on a
   fabricated value.

Reveal sequence: acknowledge their number → present comps → let the data speak →
land on a recommended range. Anchoring on a number before the comps undermines
trust and the eventual price.

## SPICED-RE discovery frame

A real-estate adaptation of SPICED. Use it as the discovery skeleton on top of
the buyer/seller qualification questions:

- **S — Situation:** current housing situation (own/rent, where, why now).
- **P — Pain:** what's not working (too small, commute, life event, cost).
- **I — Impact:** what the pain is costing them (time, money, stress, missed
  opportunity).
- **C — Critical event:** the date that forces action (lease end, job start,
  school year, closing on another home).
- **E — Expectation:** what a great outcome looks like (price, timeline,
  certainty, neighborhood).
- **D — Decision:** who decides, what the buying/selling process looks like,
  financing/agency in place.

## Honesty floor (inherited from Skill 38, restated for RE)
- Never quote a price, comp, rate, or property fact you cannot source.
- Never imply you are the lender, the county, or the government.
- For pre-foreclosure, lead with help and options, never pressure.
