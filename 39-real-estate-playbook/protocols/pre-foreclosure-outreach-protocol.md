# Pre-Foreclosure Outreach Protocol (pairs with Skill 40)

Governs CARE-FIRST outreach to distressed homeowners surfaced by Skill 40 (ZHC
Public Records Scraper) — Notice-of-Default (NOD), pre-foreclosure, and tax-
delinquency records. **Skill 39 NEVER scrapes records itself**; it consumes
Skill 40's `public-records-queries.jsonl` output and runs the outreach.

## Inputs

A record from Skill 40 (record type one of `NOD` / `pre_foreclosure` /
`tax_delinquency`), with source + timestamp attribution carried through from
Skill 40 (every record cites where it came from and when — never fabricated).

## Hard guardrails (non-negotiable)

1. **Care-first, never predatory.** The tone is empathetic and options-focused
   (help the homeowner understand their choices), never high-pressure or
   exploitative of distress.
2. **Honor do-not-contact + state cooling-off rules.** Some states restrict
   contact with homeowners in default and impose cooling-off / disclosure rules
   on "foreclosure consultants". Surface the relevant pointer from the state
   disclosure matrix and ESCALATE the compliance decision to the licensed agent/
   broker before any solicitation. Skill 39 gives the pointer, not legal advice.
3. **No fabricated distress.** If Skill 40 is not installed or returns nothing,
   there is NO record — do not invent a distress situation or imply one.
4. **No financial / legal / tax advice.** Options (sell, short sale, loan
   workout, reinstatement) are described at a high level with a clear "talk to
   your lender / a licensed professional" — the agent does not counsel.

## Stages (each emits a `pre_foreclosure_touch` event)

### Stage 1 — `initial`
Empathetic, low-pressure introduction. Acknowledge the situation respectfully.
Offer to explain options and a no-obligation conversation with the agent.

### Stage 2 — `options`
If the homeowner engages, outline options at a high level and route to the agent.
Surface the state pointer; escalate the compliance decision.

### Stage 3 — `handoff`
Route a willing homeowner to the licensed agent. Tag `ZHC-pre-foreclosure-prospect`.

## Event fields

`record_type` (`NOD`/`pre_foreclosure`/`tax_delinquency`), `outreach_stage`
(`initial`/`options`/`handoff`), `from_skill_40` (true).
