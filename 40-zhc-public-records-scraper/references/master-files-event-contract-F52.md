# F52 Master-Files Event Contract — public-records-queries.jsonl (Skill 40)

Skill 40 emits one append-only JSONL event per records-engine action to
`<MASTER_FILES_DIR>/public-records-queries.jsonl`, per the F52 master-files event
contract. Append-only; one JSON object per line; never rewritten.

`<MASTER_FILES_DIR>` is resolved by `scripts/01-locate-master-files-folder.sh`
(reuses Skill 38/39's selection if present so all skills share one folder).

> This document is the SINGLE source of truth for the log contract and is kept in
> lockstep with the machine-readable schema at
> `templates/public-records-queries.schema.json` and the schema section of
> `INSTRUCTIONS.md`. The line emitter is `scripts/lib-pr-events.sh`.

## PII discipline (binding)

The log records record TYPES + counts + cache/cost/compliance status and OPAQUE
handles only. It NEVER stores raw record contents (owner names, balances) and
NEVER stores a raw input address or ZIP. The query is referenced by an opaque
local handle (`query_ref`, e.g. `q_1717082400_28114`) and the target by a
county/portal SLUG (`target_ref`, e.g. `cook-county-il`) — never a person and
never a street address. `scripts/qc-no-personal-data.sh` enforces the no-raw-PII
posture across the skill tree.

## Common fields (on every line)

| Field | Type | Description |
|---|---|---|
| `ts` | string (ISO-8601 UTC) | event timestamp (`date -u +%Y-%m-%dT%H:%M:%SZ`) |
| `skill` | string | always `"40-zhc-public-records-scraper"` |
| `event` | string | one of the event types below |
| `query_ref` | string | opaque local query handle — NOT a raw address |
| `target_ref` | string | county/portal slug (e.g. `cook-county-il`) — NOT a person |

## Event types and their type-specific fields

| `event` | Type-specific fields |
|---|---|
| `cache_init` | (none beyond common) — the cache dir + log were initialized |
| `tier_decision` | `tier` (`tier1`/`tier2`/`tier3`/`tier4_honest_gap`), `county_fips`, `state`, `reason` |
| `cache_hit` | `record_type`, `age_days` |
| `force_refresh` | `record_type` |
| `query` | `record_type`, `result_count`, `source`, `retrieved_at` |
| `compliance_block` | `reason` (`robots_disallow`/`tos_unacknowledged`/`unattributed`) |
| `cost_estimate` | `batch_size`, `est_cost`, `est_seconds`, `confirmed` (bool) |
| `cost_block` | `reason` (`daily_cap`), `daily_count` |
| `rate_limit_wait` | `waited_seconds` |
| `honest_gap` | `reason` (`no_online_db`/`county_unresolved`/`target_blocked`) |

`event` is constrained to this enum by `templates/public-records-queries.schema.json`.
`record_type` is one of `ownership` / `deeds` / `tax` / `tax_delinquency` /
`permits` / `pre_foreclosure` / `NOD`. `tier` is one of `tier1` / `tier2` /
`tier3` / `tier4_honest_gap`.

## Example line (Tier-1 routing decision — no raw address)
```json
{"ts":"2026-05-30T14:10:02Z","skill":"40-zhc-public-records-scraper","event":"tier_decision","query_ref":"q_1717082400_28114","target_ref":"maricopa-county-az","tier":"tier1","county_fips":"04013","state":"04","reason":"curated tier1 config"}
```

## Example line (Tier-4 honest gap — no raw address)
```json
{"ts":"2026-05-30T14:12:40Z","skill":"40-zhc-public-records-scraper","event":"honest_gap","query_ref":"q_1717082560_90431","target_ref":"unknown","reason":"county_unresolved"}
```

## Example line (cache hit)
```json
{"ts":"2026-05-30T14:14:05Z","skill":"40-zhc-public-records-scraper","event":"cache_hit","query_ref":"q_1717082645_11290","target_ref":"cook-county-il","record_type":"ownership","age_days":3}
```

## Provenance of the records themselves

The log captures the QUERY and its routing/cost/compliance status — not extracted
record contents. When a record is actually fetched (by a tier adapter after
robots + ToS + attribution pass), the record itself carries its own `source` +
`retrieved_at` attribution per the compliance rules and is cached under
`public-records-cache/` (the cache key is a hash of target+county+record_type —
never a raw address). An unattributed result is not a record and is refused.

## Consumers
- Skill 39's pre-foreclosure protocol consumes the `pre_foreclosure` / `NOD` /
  `tax_delinquency` signals (record TYPES, never raw owner PII).
- The per-day cost + rate counters live under the cache dir (not this log).
- Any downstream tool can `tail`/parse the JSONL against the machine-readable
  schema at `templates/public-records-queries.schema.json`.
