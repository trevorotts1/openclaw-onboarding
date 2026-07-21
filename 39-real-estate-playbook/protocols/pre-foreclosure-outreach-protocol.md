# Pre-Foreclosure Outreach Protocol (pairs with Skill 40)

Governs CARE-FIRST outreach to distressed homeowners surfaced by Skill 40 (ZHC
Public Records Scraper) — Notice-of-Default (NOD), pre-foreclosure, and tax-
delinquency records. **Skill 39 NEVER scrapes records itself**; it consumes the
record Skill 40's retrieval path returns and runs the outreach.

## Inputs — `public-records-handoff/v1`

> **The audit log is NOT a record source.** This protocol previously named Skill
> 40's `public-records-queries.jsonl` as its input. That file is Skill 40's
> append-only AUDIT LOG, and `40-zhc-public-records-scraper/INSTRUCTIONS.md:89`
> states its PII discipline explicitly: it records record TYPES, counts,
> cache/cost/compliance status and an opaque `query_ref` / `target_ref` — *"never
> raw record contents (owner names, balances, addresses)"*. No outreach can be
> performed from it. That discipline is correct and stays; what was wrong was
> this document naming the wrong artifact.

**The record source is Skill 40's retrieval path**, `record_get` in
`40-zhc-public-records-scraper/scripts/lib-records.sh` (the attributed-record
branch at lines 524-530), which prints ONE record object on stdout per call.

A conforming record carries:

| Field | Rule |
|---|---|
| `query_ref` | Opaque reference. The join key back to the audit log. |
| `record_type` | One of `NOD` / `pre_foreclosure` / `tax_delinquency`. |
| `source` | Where the record came from. **Required** — Skill 40 refuses to cache or emit an unattributed record (`reason:"unattributed"`). |
| `retrieved_at` | ISO-8601 timestamp of retrieval. **Required**, same reason. |
| `available` | `true`. A record with `available:false` or `blocked:true` is NOT an input to outreach. |

**Refuse, never repair.** A record missing `source` or `retrieved_at` is not
attributed and must not be used for outreach — that is the guarantee "every
record cites where it came from and when, never fabricated" actually depends on.
Do not infer a source, do not backfill a timestamp, and do not read either from
the audit log to fill a gap in a record.

**The audit log's role in this protocol** is exactly one thing: given a
`query_ref` from a record, it proves what was queried, cached, blocked and
costed. It never supplies record contents, and it is never the input to an
outreach decision.

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
