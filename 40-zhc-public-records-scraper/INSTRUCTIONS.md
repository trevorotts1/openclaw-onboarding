# Skill 40 — ZHC Public Records Scraper: Runtime Instructions

Operator-facing runtime guide. Read top to bottom before acting (N3). Assumes the install scripts (`00`–`07`) have run.

## The no-fabrication floor (read first)

**NEVER fabricate a public record.** Enforced by `scripts/qc-no-fabrication.sh`. When no tier can serve a query, the answer is **Tier 4 — honest gap**: tell the operator there is no online database (or the target blocks/disallows automated access) and stop. Do NOT invent an owner, deed, lien, NOD, tax balance, or permit. A record without `source` + `retrieved_at` provenance is not a record.

## Auto-detect routing

`scripts/lib-records.sh query "<address-or-zip>" "<record-type>"` runs the router:

1. **Resolve county + state.** From a full address, reuse Skill 39's geocode (Census FIPS) when available; from a ZIP, map ZIP → county (the router uses the matched FIPS). If county/state cannot be resolved → Tier 4 honest gap.
2. **Tier 1?** Is there a curated config for this county (`references/tier1-counties/<slug>.json`)? If yes AND the target passes the compliance + validation gate → use it.
3. **Tier 2?** Does this county run on a known platform vendor with an adapter (`references/tier2-adapters/`)? If yes → use the vendor adapter parameterized for this county.
4. **Tier 3?** Has the operator built a validated Tier-3 config for this target (`06-build-tier3-config.sh`)? If yes → use it.
5. **Else Tier 4** — honest gap. Log `tier_decision` = `tier4_honest_gap` and tell the operator.

Every routing decision appends a `tier_decision` event.

## Compliance gate (runs before any live fetch)

`protocols/compliance-protocol.md`, enforced by `lib-records.sh`:

- **robots.txt** — fetch + parse the target's robots.txt; if the path is disallowed for our user-agent → Tier 4 honest gap (`compliance_block`, reason `robots_disallow`). Never override.
- **ToS reference** — each target config carries `tos_url`; the operator must have acknowledged it (recorded by `04-configure-caps.sh` / per-target). An unacknowledged target → `compliance_block`, reason `tos_unacknowledged`.
- **Attribution** — every retrieved record is stamped `source` + `retrieved_at`. The router refuses to return an unattributed record.
- **Permissible use** — the operator is responsible for lawful, permissible-purpose use (FCRA/DPPA/state limits). The skill surfaces the reminder; it does not give legal advice.

## Cost cap + rate limits

`protocols/cost-cap-protocol.md`, enforced by `lib-cost-cap.sh`:

- **Per-day cap** (`PR_DAILY_CAP`, default 200) — counts queries today (tracked in the cache dir); at the cap, the router refuses with `cost_block`, reason `daily_cap`.
- **Per-target rate limit** (`PR_PER_TARGET_MIN_INTERVAL_S`, default 5s) — enforces a minimum interval between requests to the same target; the router waits (logs `rate_limit_wait`) rather than hammering.
- **Bulk cost estimate** — for a batch above `PR_BULK_CONFIRM_THRESHOLD` (default 25), the skill prints `estimated queries × PR_COST_PER_QUERY` + estimated wall-clock at the rate limit, logs `cost_estimate`, and WAITS for explicit operator confirmation before running. No silent bulk runs.

## 30-day cache

`protocols/cache-protocol.md`, in `lib-records.sh`:

- Results cache at `<MASTER_FILES_DIR>/public-records-cache/` for `PR_CACHE_TTL_DAYS` (default 30).
- Cache key = a hash of (normalized target + query) — never a raw address as a filename.
- A fresh cache hit returns instantly, free, and logs `cache_hit`.
- `--force-refresh` bypasses the cache for one query (logs `force_refresh`).
- Expired entries are re-fetched (subject to the compliance + cost gates).

## Real-estate use cases (prioritized)

`references/real-estate-use-cases.md`. In priority order:

1. **Pre-foreclosure / Notice-of-Default (NOD)** — feeds Skill 39's pre-foreclosure outreach.
2. **Tax delinquency** — owners behind on property taxes (distressed-seller signal).
3. **Comps support** — recorded sale prices/dates to support a CMA (Skill 39).
4. **Permits** — open/closed building permits (condition + flip signals).
5. **Tax records** — assessed value, tax history.
6. **Ownership / deeds** — current owner, recent transfers, liens.

Skill 40 surfaces these records (with provenance); Skill 39 decides what to DO with them. Skill 40 never runs outreach.

## `public-records-queries.jsonl` schema

Append-only JSONL at `<MASTER_FILES_DIR>/public-records-queries.jsonl`. One JSON object per line. Written by `scripts/lib-pr-events.sh pr_event <type> <json>`. Machine-readable schema: `templates/public-records-queries.schema.json`. Common fields on every event:

| Field | Type | Meaning |
|---|---|---|
| `ts` | string (ISO-8601 UTC) | When appended |
| `skill` | string | Always `"40-zhc-public-records-scraper"` |
| `event` | string | One of the event types below |
| `query_ref` | string | Opaque local query handle (NOT a raw address) |
| `target_ref` | string | County/portal slug (e.g. `cook-county-il`), NOT a person |

Event types and their type-specific payload fields:

| `event` | Type-specific fields |
|---|---|
| `cache_init` | (none beyond common) |
| `tier_decision` | `tier` (`tier1`/`tier2`/`tier3`/`tier4_honest_gap`), `county_fips`, `state`, `reason` |
| `cache_hit` | `record_type`, `age_days` |
| `force_refresh` | `record_type` |
| `query` | `record_type`, `result_count`, `source`, `retrieved_at` |
| `compliance_block` | `reason` (`robots_disallow`/`tos_unacknowledged`/`unattributed`) |
| `cost_estimate` | `batch_size`, `est_cost`, `est_seconds`, `confirmed` (bool) |
| `cost_block` | `reason` (`daily_cap`), `daily_count` |
| `rate_limit_wait` | `waited_seconds` |
| `honest_gap` | `reason` (`no_online_db`/`county_unresolved`/`target_blocked`) |

**PII discipline in the log:** the log records record TYPES + counts + cache/cost/compliance status and an opaque `query_ref`/`target_ref` — never raw record contents (owner names, balances, addresses). This keeps the operator's ground-truth log clean while proving exactly what was queried, cached, blocked, and costed.

## Pairing with Skill 39

When Skill 40 surfaces a `pre_foreclosure` / `NOD` / `tax_delinquency` record, Skill 39's `pre-foreclosure-outreach-protocol.md` consumes it (care-first outreach). Skill 40 stays in its lane: find + attribute + cache + log. It never messages a homeowner.

## Idempotency & re-runs

All `00`–`07` scripts are idempotent (validate/marker compare, then act). `02-init-cache.sh` never wipes an existing cache or log. `lib-records.sh` / `lib-pr-events.sh` / `lib-cost-cap.sh` are libraries; the only state they mutate is the append-only log, the cache dir, and the per-day counter.

## Verification checklist (post-install)

- [ ] `~/.openclaw/skills/40-zhc-public-records-scraper/` exists with all listed files
- [ ] `scripts/*.sh` are `chmod +x`
- [ ] `00-verify-prerequisites.sh` passes (MASTER_FILES_DIR, jq, curl)
- [ ] `<MASTER_FILES_DIR>/public-records-cache/` exists + `public-records-queries.jsonl` created
- [ ] `03-load-tier1-counties.sh` indexes the shipped Tier-1 configs without error
- [ ] `bash scripts/qc-no-personal-data.sh` → PASS
- [ ] `bash scripts/qc-no-fabrication.sh` → PASS
- [ ] `bash scripts/qc-compliance.sh` → PASS
