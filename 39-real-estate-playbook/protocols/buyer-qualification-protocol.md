# Buyer Qualification Protocol (Skill 39)

Universal buyer-discovery frame. Used by the conversational agent the moment a
contact signals buyer intent. Pairs with the Sales-Brain (Skill 38) — this
protocol supplies the RE-specific questions; Skill 38 supplies the tone,
follow-up cadence, and send mechanics.

## When to use
A contact expresses interest in buying, browsing listings, or "looking for a
place." Tag the contact `ZHC-buyer-lead` (create the tag in GHL first).

## The five qualification dimensions (ask conversationally, not as a form)
1. **Timeline** — "When are you hoping to be in your new place?" (now / 1-3 mo /
   3-6 mo / 6-12 mo / just browsing). Drives follow-up cadence.
2. **Financing** — "Are you paying cash, or will you be financing?" If financing:
   "Have you been pre-approved yet, or should I connect you with a lender?"
   NEVER quote a rate or pre-approve — that is the lender's job.
3. **Neighborhood / location** — target areas, commute constraints, school
   zones, must-be-near.
4. **Must-haves vs nice-to-haves** — beds, baths, square footage, garage, yard,
   single-story, HOA tolerance, pets.
5. **Budget** — "What price range feels comfortable?" Capture a range, not a
   single number. Tie back to financing.

## Investor signal
If the buyer mentions rental income, cap rate, flips, BRRRR, doors, or "as an
investment," ALSO tag `ZHC-investor-lead` and switch to investor questions
(target returns, hold horizon, financing structure, market).

## Honest-data rule
When the buyer asks about a specific property (price, comps, days-on-market),
use `scripts/03-property-lookup.sh`. If the relevant capability is an HONEST GAP,
say so — do NOT invent a number.

## Routing + logging
- Route per `lead-routing-protocol.md` (buyer specialty / area / luxury).
- Each property the buyer asks about logs a `property_lookup` event to
  `<MASTER_FILES_DIR>/real-estate-events.jsonl` via the lookup script.

## Handoff to Skill 38
Use Skill 38's intelligent follow-up for cadence and the humanizer (Skill 19,
always-on) for tone. This protocol does not duplicate either.
