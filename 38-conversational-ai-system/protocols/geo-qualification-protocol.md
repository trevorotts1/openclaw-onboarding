# Geo-Qualification Protocol (F45) — Step 9.39

> **OFF by default.** This is a per-client toggle. Many businesses serve everyone
> everywhere; geo-qualification only makes sense for location-bound services (in-person
> trades, local service-area businesses, regional licensing). The operator turns it on.

When enabled, the agent figures out WHERE a prospect is located so it can route, qualify,
or (carefully) decline out-of-area leads — while NEVER disqualifying anyone on a guess.

## CRITICAL RULE — signals are HINTS, always ASK to confirm

Every location signal below is a HINT, never a verdict. The agent NEVER disqualifies,
declines, or routes a prospect out-of-area on a signal alone. Before ANY disqualification
or out-of-area handling, the agent **asks the customer to confirm** their location in a
natural way ("Just to make sure I point you to the right team — what city/ZIP are you
in?"). A phone area code can be a moved-away number; a pixel/IP can be a VPN or a
traveler; a form address can be a billing address. ASK FIRST. Disqualifying a real
in-area lead because of a stale area code is the exact failure this rule prevents.

## Location detection priority

The agent gathers the best available hint in this priority order, then confirms:

1. **Pixel / IP geolocation** — only if F49 (pixel/intent) is installed and provides it.
   Strongest as a first hint, weakest as proof (VPN/traveler). HINT only.
2. **Phone area code** — the contact's phone number's area code maps to a region. HINT only
   (numbers move with people).
3. **Form address** — a city/state/ZIP the contact entered on a form. HINT only (could be
   billing/work address).
4. **Explicit ask** — the agent asks directly. This is the CONFIRMATION step and the only
   basis for an actual qualification decision.

The agent uses the highest-priority available hint to PRE-FILL its confirmation question
("Looks like you might be near [city] — is that right?"), then waits for the answer.

## Service areas knowledge base

Per-product service areas live in:

```
<MASTER_FILES_DIR>/KnowledgeBases/sales/service-areas.md
```

Each product/service defines its area by any of: **ZIP code list, county list, state
list, or radius** (miles from one or more anchor points). A product with no entry is
treated as **served everywhere** (no geo gate for that product).

## Out-of-area handling (operator-configured)

When the customer's CONFIRMED location is outside a product's service area, the agent
follows the operator-chosen handling mode (set in `service-areas.md` per product, with a
client-wide default):

- **decline + referral** — politely decline and refer to a partner/competitor/directory
  the operator listed.
- **limited-remote** — offer the remote/virtual version of the service if one exists.
- **waitlist** — capture the lead onto an expansion waitlist (tag + note) for when the
  business reaches that area.
- **full decline** — politely decline with no referral.

The agent always stays warm and helpful regardless of mode — an out-of-area prospect is a
future customer or a referrer.

## Tags this protocol creates (all ZHC-prefixed, per MEMORY Rule 20)

- `ZHC-out-of-service-area` — confirmed outside the service area (after ASK).
- `ZHC-service-area-confirmed` — confirmed inside the service area.
- `ZHC-service-area-flexible` — in-area for the remote/virtual version, or a borderline/
  radius-edge case the operator wants flagged for judgment.

Tags are created programmatically with the `ZHC-` prefix (D.1 mechanism, MEMORY Rule 20).

## Geo-qualification log (JSONL data contract, F52)

Every geo decision is appended to
`<MASTER_FILES_DIR>/geo-qualification-log.jsonl` — one JSON object per line:

```json
{"timestamp":"2026-05-30T15:01:00Z","event_type":"geo_qualified","contact_id":"<contact_id>","product":"<product>","signal_used":"phone_area_code","signal_value_hint":"<area-region>","confirmed_by_ask":true,"confirmed_location_hint":"<city/zip>","in_area":false,"handling_mode":"decline_referral","tag":"ZHC-out-of-service-area"}
```

`confirmed_by_ask` is ALWAYS true on any disqualifying decision — a record with
`in_area:false` and `confirmed_by_ask:false` is a protocol violation. The JSONL schema is
documented in `INSTRUCTIONS.md` (Phase 5 data contract table).

## openclaw.json toggles

```json
{
  "skill38": {
    "geo_qualification": {
      "enabled": false
    }
  }
}
```

- `geo_qualification.enabled` — default **false** (OFF). Per-client opt-in; the operator
  enables it only for location-bound businesses.

## MEMORY.md (Rule 23)

When geo-qualification is ON, location signals (pixel/IP → area code → form address →
explicit ask) are HINTS only. The agent ALWAYS ASKS to confirm before any
disqualification or out-of-area handling — never disqualify on a guess. Out-of-area
handling is operator-configured (decline+referral / limited-remote / waitlist / full
decline). Service areas live in `KnowledgeBases/sales/service-areas.md` per product. See
`<MASTER_FILES_DIR>/geo-qualification-protocol.md`.
