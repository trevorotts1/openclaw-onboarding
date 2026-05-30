# F52 Master-Files Event Contract — public-records-queries.jsonl (Skill 40)

Skill 40 emits one JSONL event per records query to
`<MASTER_FILES_DIR>/public-records-queries.jsonl`, per the F52 master-files event
contract. Append-only; one JSON object per line; never rewritten.

`<MASTER_FILES_DIR>` is resolved by `scripts/01-locate-master-files-folder.sh`
(reuses Skill 38/39's selection if present so all skills share one folder).

## Event type
- `records_query` — emitted on every `02-detect-and-route.sh` invocation (one per
  query). Cache hits AND honest gaps are logged too (a cache hit and a Tier 4 gap
  are both real events worth recording).

## Schema (fields)

| Field | Type | Description |
|---|---|---|
| `ts` | string (ISO-8601 UTC) | event timestamp |
| `date` | string (UTC date) | `YYYY-MM-DD` — used by the per-day rate-limit + cost counters |
| `skill` | string | always `"40-zhc-public-records-scraper"` |
| `event` | string | always `"records_query"` |
| `address` | string | the input address (as provided; may be empty if county/state given) |
| `county` | string | resolved county (may be empty if unresolved → Tier 4) |
| `state` | string | resolved 2-letter state |
| `zip` | string | parsed ZIP (if any) |
| `record_type` | string | `recorder` \| `assessor` \| `tax` \| `parcel` \| … |
| `tier` | number | `1`–`4` (4 = honest gap) |
| `target` | string | the matched portal domain / adapter file / config base (empty on Tier 4) |
| `cache_hit` | boolean | true if served from the 30-day cache |
| `queries_today` | number | running per-day count (rate-limit basis) |
| `est_cost_usd` | string | cost estimate for this op (e.g. `"0.00"`) |
| `blocked` | boolean | true if a rate-limit/cost cap HELD the op pending operator confirmation |

## Example line (Tier 1 hit, free, not blocked)
```json
{"ts":"2026-05-30T14:10:02Z","date":"2026-05-30","skill":"40-zhc-public-records-scraper","event":"records_query","address":"123 Main St, Phoenix, AZ 85003","county":"Maricopa","state":"AZ","zip":"85003","record_type":"recorder","tier":1,"target":"mcassessor.maricopa.gov;recorder.maricopa.gov","cache_hit":false,"queries_today":4,"est_cost_usd":"0.00","blocked":false}
```

## Example line (Tier 4 honest gap)
```json
{"ts":"2026-05-30T14:12:40Z","date":"2026-05-30","skill":"40-zhc-public-records-scraper","event":"records_query","address":"1 Rural Rd, Smallville, KS 67524","county":"","state":"KS","zip":"67524","record_type":"recorder","tier":4,"target":"","cache_hit":false,"queries_today":5,"est_cost_usd":"0.00","blocked":false}
```

## Privacy + provenance
The log records the QUERY and its routing/cost, not extracted PII. Extracted
public records themselves (when fetched) carry their own source + timestamp
attribution per the compliance rules and are cached under
`public-records-cache/`. The companion `real-estate-events.jsonl` (Skill 39)
carries the downstream RE interactions; the two logs are complementary.

## Consumers
- Skill 39's pre-foreclosure protocol consumes the NOD / tax-delinquency signals.
- Rate-limit + cost counters read this same log (`date` field).
- Any downstream tool can `tail`/parse the JSONL.
