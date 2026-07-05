# Seller Qualification Protocol (Skill 39)

Universal seller-discovery frame. Triggered when a contact signals intent to
sell (or to learn what their property is worth). Tag `ZHC-seller-lead`.

## The four qualification dimensions
1. **Motivation** — "What's prompting the move?" (upsizing / downsizing /
   relocation / financial / life event / testing the market). Motivation drives
   urgency and pricing flexibility.
2. **Timeline** — "When would you ideally like to be sold and moved?" (ASAP /
   within 3 mo / this year / no rush).
3. **Target price + expectations** — "Do you have a number in mind?" Capture it,
   then route to a CMA (comparative market analysis). Do NOT confirm or deny the
   number — the CMA does that. See the CMA pricing-reveal timing rule in the
   Sales-Brain RE extension.
4. **Occupancy + condition** — owner-occupied / tenant-occupied / vacant; any
   known repairs, recent upgrades, or issues that affect showings or disclosure.

## CMA request
When the seller wants a value, log a `cma_request` event and run
`scripts/property-lookup.sh --address "<addr>" --want comps`. If comps are an
HONEST GAP (no comps provider configured), say so and offer to pull a manual CMA
once a provider key is added — never fabricate a value.

## Pre-foreclosure / distressed sellers
If the seller mentions missed payments, a notice of default (NOD), or "behind on
the mortgage," handle with care per `pre-foreclosure-outreach-protocol.md` and
tag `ZHC-pre-foreclosure-prospect`. This is a sensitive, compliance-bound path.

## Disclosure
Before listing, surface the seller's state-specific disclosure obligations per
`disclosure-compliance-protocol.md` (pointer, not legal advice).

## Routing + logging
Route per `lead-routing-protocol.md` (listing specialty / area). Each CMA request
and showing logs a JSONL event to `<MASTER_FILES_DIR>/real-estate-events.jsonl`.
