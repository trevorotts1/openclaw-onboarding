# Geo-Qualification Protocol (F45) — Step 9.39

Detects whether a customer is in the business's service area and qualifies (or
gently disqualifies) them accordingly — **always confirming with the customer
before any disqualification**. This is a per-client toggle, OFF by default,
because many businesses serve everyone everywhere (digital products, nationwide
shipping) and geo-qualification would only get in the way.

## openclaw.json toggles — global default OFF + per-product opt-in

```json
{
  "skill38": {
    "geo_qualification": {
      "enabled": false,
      "per_product": {}
    }
  }
}
```

- `geo_qualification.enabled` — the GLOBAL toggle, default **false** (OFF). When
  `false`, this protocol is a no-op and no location detection or qualification
  happens. The operator turns it ON only for location-bound businesses (local
  services, regional providers, in-person appointments).
- `geo_qualification.per_product` — an OPTIONAL per-product override map, keyed by
  product name, that lets a mixed catalog gate some products and not others
  WITHOUT disabling the feature globally. Each entry is `true` (geo-gate THIS
  product) or `false` (this product is served everywhere — skip geo entirely for
  it). Resolution order for any given product:
  1. If the global `enabled` is `false` → the whole protocol is a no-op (per-product is ignored).
  2. Else if the product has an explicit `per_product[<product>]` value → use it.
  3. Else fall back to the product's presence in `service-areas.md` — a product with a service-area entry IS gated; a product with NO entry is "served everywhere."

  ```json
  {
    "skill38": {
      "geo_qualification": {
        "enabled": true,
        "per_product": {
          "In-Home Consultation": true,
          "Online Course": false
        }
      }
    }
  }
  ```

  So a client can sell an in-person service (geo-gated) AND a digital course
  (served everywhere) from the same agent: the consultation is geo-checked, the
  course never is — even with the global toggle ON.

## Detection signal priority (HINTS only)

When enabled (and the product is gated), the agent gathers location HINTS in this
priority order and uses the highest-confidence one available:

1. **Pixel/IP location** — if F49 (pixel/tracking priority) is enabled and a
   pixel event carries an approximate IP-geolocation, use it as the first hint.
2. **Phone area code** — derive a rough region from the contact's phone number
   area code.
3. **Form address** — any address fields already captured (GHL contact address,
   a form submission).
4. **Explicit ask** — if none of the above yields a usable hint, ASK the customer
   directly ("Whereabouts are you located? I want to make sure we serve your
   area."). This is the CONFIRMATION step and the only basis for an actual
   qualification decision.

The agent uses the highest-priority available hint to PRE-FILL its confirmation
question ("Looks like you might be near [city] — is that right?"), then waits for
the answer.

## CRITICAL — signals are HINTS; ALWAYS ASK before disqualifying

A pixel IP can be a VPN. An area code follows the phone, not the person (people
keep numbers when they move). A form address can be stale or a billing address.
**None of these is ground truth.** Therefore:

> The agent NEVER disqualifies a customer on a hint alone. Before ANY
> out-of-area handling, the agent CONFIRMS the customer's actual service location
> with the customer.

### The exact confirmation question

The agent asks where the SERVICE/DELIVERY would actually happen — not where the
customer "is" (which a hint may have wrong) — and frames it as a check, never a
brush-off:

> "Looks like you might be calling from outside our usual service area — just to
> be sure, what ZIP code would the service be at? I don't want to turn you away
> if we actually can help."

### All response branches (what the agent does with each answer)

The agent classifies the customer's CONFIRMED answer and acts. Five branches,
exhaustively:

| customer's confirmed answer | branch | what the agent does |
|---|---|---|
| **"Here" — the service location IS in the area** | in-area | Qualify and continue normally. Tag `ZHC-service-area-confirmed`. No out-of-area handling. |
| **"Elsewhere" — a different, genuinely out-of-area location** | confirmed out-of-area | NOW (and only now) apply the operator-configured out-of-area mode (below). Tag `ZHC-out-of-service-area`. |
| **"Vacation / traveling" — temporarily away, home/service base is in-area** | flexible (do NOT disqualify) | The service base is in-area, so treat as in-area; note the temporary location only. Tag `ZHC-service-area-flexible`. Never disqualify someone who is in-area but momentarily traveling. |
| **"Moving" — relocating INTO or OUT of the area** | flexible (clarify timing) | Ask which location the service is FOR and WHEN. If the service location/date is in-area, qualify (`ZHC-service-area-confirmed`); if it's out, treat as confirmed out-of-area. If unclear, stay flexible (`ZHC-service-area-flexible`) — do not disqualify on a pending move. |
| **No clear engagement — customer doesn't answer the location question / dodges / is ambiguous** | NO disqualification | **Do NOT disqualify.** A non-answer is NOT a confirmed out-of-area location. Continue the conversation on its current goal, ask once more naturally later if it's still relevant, and never apply an out-of-area mode without a CONFIRMED out-of-area location. |

The invariant across all branches: **a hint is a reason to ASK, never a reason to
decline; only a CONFIRMED, genuinely out-of-area service location triggers
out-of-area handling.** "Vacation," "moving," and "no engagement" all map to
*do-not-disqualify*.

## Service-area definition

Per-product service areas live in
`<MASTER_FILES_DIR>/KnowledgeBases/sales/service-areas.md`. The agent reads this
file to decide in/out. It supports per-product definitions by ZIP, county,
state, and/or radius:

```markdown
# Service Areas

## Product: In-Home Consultation
- type: radius
- center: <CENTER_ZIP_OR_CITY>
- radius_miles: 30

## Product: Regional Delivery
- type: zips
- zips: <ZIP_LIST>            # e.g. comma-separated ZIP codes

## Product: Statewide Service
- type: states
- states: <STATE_LIST>        # e.g. two-letter state codes

## Product: County Coverage
- type: counties
- counties: <COUNTY_LIST>
```

A single client can mix types across products (radius for in-home, statewide for
remote). If a product has no entry, treat it as "served everywhere" (no geo-gate
for that product) — consistent with the `per_product` resolution above.

## Out-of-area handling (operator-configured) — the 4 modes

When the customer CONFIRMS an out-of-area location (the "elsewhere" branch only),
the agent follows the operator's configured out-of-area mode (set per client;
default is the gentlest, `decline_plus_referral`):

| mode | behavior |
|---|---|
| `decline_plus_referral` | politely decline AND, if the operator provided a referral list/partner, point the customer to an alternative. The gentlest default. Tag `ZHC-out-of-service-area`. |
| `limited_remote` | offer the subset of products/services that CAN be delivered remotely (consults, digital), decline only the in-person ones. Tag `ZHC-service-area-flexible` for the remote-eligible path. |
| `waitlist` | capture the customer for a future-expansion waitlist (note the location), tell them you'll reach out if you expand there. Tag `ZHC-out-of-service-area`. |
| `full_decline` | politely decline with NO referral (the operator has none). Tag `ZHC-out-of-service-area`. |

All decline copy stays warm and non-dismissive (honesty floor + brand voice) —
an out-of-area prospect is a future customer or a referrer.

## Tags

Applied programmatically → `ZHC-` prefix (zhc-tag-prefix-protocol.md):

- `ZHC-out-of-service-area` — customer CONFIRMED a location outside the service
  area; out-of-area handling applied.
- `ZHC-service-area-confirmed` — customer confirmed an IN-area location; qualified.
- `ZHC-service-area-flexible` — borderline / customer is flexible on location
  (e.g. on vacation but home base in-area, a pending move, willing to travel to a
  covered ZIP, or eligible for `limited_remote`).

## Logging (the data contract — F52)

Every qualification decision is recorded as JSONL, one line appended to
`<MASTER_FILES_DIR>/geo-qualification-log.jsonl`:

```json
{"timestamp":"2026-05-30T16:12:44Z","event_type":"geo_qualification","contact_id":"<CONTACT_ID>","channel":"sms","hint_source":"phone_area_code","hint_value":"<REGION_HINT>","confirmed_with_customer":true,"confirmed_location":"<CONFIRMED_LOCATION>","product":"In-Home Consultation","in_area":false,"out_of_area_mode":"decline_plus_referral","tag_applied":"ZHC-out-of-service-area"}
```

JSONL schema (one object per line):

| field | type | meaning |
|---|---|---|
| `timestamp` | string (ISO-8601 UTC) | when the decision was made |
| `event_type` | string | `geo_qualification` (always, for F45 firings) |
| `contact_id` | string | GHL contact id |
| `channel` | string | inbound channel |
| `hint_source` | string | `pixel_ip` / `phone_area_code` / `form_address` / `explicit_ask` |
| `hint_value` | string | the region the hint suggested (coarse — no precise PII) |
| `confirmed_with_customer` | boolean | MUST be `true` before any disqualification |
| `confirmed_location` | string | the location the customer confirmed (coarse) |
| `product` | string | which product's service area was checked |
| `in_area` | boolean | whether the confirmed location is in the service area |
| `out_of_area_mode` | string | the operator-configured mode applied (if out of area) |
| `tag_applied` | string | `ZHC-out-of-service-area` / `ZHC-service-area-confirmed` / `ZHC-service-area-flexible` |

> Invariant: a JSONL line with `in_area:false` and a `ZHC-out-of-service-area`
> tag MUST have `confirmed_with_customer:true` — the agent never disqualifies on
> a hint alone. The "vacation," "moving," and "no-engagement" branches never
> produce an `in_area:false` + `ZHC-out-of-service-area` line.

The JSONL schema is also documented in `INSTRUCTIONS.md` (Phase 5 data contract table).

## MEMORY.md (Rule 23)

When geo-qualification is ON (globally, or per-product via `geo_qualification.per_product`),
location signals (pixel/IP → area code → form address → explicit ask) are HINTS only. The
agent ALWAYS ASKS to confirm before any disqualification or out-of-area handling — never
disqualify on a guess, and never on "vacation," "moving," or a non-answer (those are
do-not-disqualify). Out-of-area handling is operator-configured (decline+referral /
limited-remote / waitlist / full decline). Service areas live in
`KnowledgeBases/sales/service-areas.md` per product. See MEMORY Rule 23, appended by
`scripts/06-append-memory-rules.sh`.

## Cross-references

- Knowledge base: `<MASTER_FILES_DIR>/KnowledgeBases/sales/service-areas.md`.
- Optional hint source: F49 pixel-priority.
- Tag namespace: `protocols/zhc-tag-prefix-protocol.md`.
- AGENTS.md Step 2.0: `scripts/05-update-agents-md.sh` (marker `STEP_2_0_GEO_QUALIFICATION`).
- INSTRUCTIONS.md Step 9.39.
