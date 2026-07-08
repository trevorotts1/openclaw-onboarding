# F52 Master-Files Event Contract — real-estate-events.jsonl (Skill 39)

Skill 39 emits one JSONL event per real-estate interaction to
`<MASTER_FILES_DIR>/real-estate-events.jsonl`, per the F52 master-files event
contract. The file is append-only; one JSON object per line; never rewritten.

`<MASTER_FILES_DIR>` is resolved by `scripts/01-locate-master-files-folder.sh`
(the SAME folder Skill 38 uses — Skill 39 reuses Skill 38's selection if present).

## Event types
- `property_lookup` — emitted on every property lookup (`property-lookup.sh`).
- `showing` — emitted when a showing is confirmed (incl. open-house subtype).
- `cma_request` — emitted when a seller CMA is requested.

## Schema (fields)

| Field | Type | Description |
|---|---|---|
| `ts` | string (ISO-8601 UTC) | event timestamp, e.g. `2026-05-30T14:03:21Z` |
| `skill` | string | always `"39-real-estate-playbook"` |
| `event` | string | `property_lookup` \| `showing` \| `cma_request` |
| `address_hash` | string | sha256 of the lower-cased input address — an opaque, stable correlator. The raw address and street are NEVER persisted (PII-free contract). |
| `normalized` | object | `{ "city", "state", "zip" }` heuristic split — coarse geography only, no street |
| `capabilities` | object | per-capability state, e.g. `{ "comps":"AVAILABLE", "mls":"HONEST_GAP" }` (for `property_lookup`) |
| `available` | number | count of capabilities that were AVAILABLE |
| `honest_gaps` | number | count of capabilities that were an HONEST GAP |

For `showing` and `cma_request` events the producer adds the event-specific
fields it has (e.g. `datetime`, `requesting_party` for showings) and omits the
`capabilities`/`available`/`honest_gaps` triple where not applicable.

## Example line (property_lookup)
```json
{"ts":"2026-05-30T14:03:21Z","skill":"39-real-estate-playbook","event":"property_lookup","address_hash":"9f2c…","normalized":{"city":"Springfield","state":"IL","zip":"62701"},"capabilities":{"property_lookup":"AVAILABLE","geocode":"AVAILABLE","street_view":"HONEST_GAP","comps":"HONEST_GAP"},"available":2,"honest_gaps":2}
```

## Privacy
The event log records PROPERTY interactions with NO raw PII. The specific street
address is never persisted — it is reduced to an opaque `address_hash` (sha256 of
the lower-cased input) plus the coarse city/state/zip (shared by many properties).
No names, phone numbers, or emails are written by Skill 39's event emitter.
`qc-no-personal-data.sh` fails the build if the emitter is ever changed back to
persisting a raw `address`/`street`. The companion log
`public-records-queries.jsonl` (Skill 40) carries public-records provenance.

## Consumers
- Skill 38 analytics / weekly tune-up can read this log to report RE activity.
- The ZHC closeout (Skill 37) can summarize RE activity if present.
- It is a plain JSONL file — any downstream tool can `tail`/parse it.
