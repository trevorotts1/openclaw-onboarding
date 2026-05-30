# Skill 40 — Worked Examples

All examples use UNIVERSAL placeholders. No real address, owner, client, or key appears. Every
example shows the honest-gap and compliance paths.

## Example 1 — Tier 1 hit (curated county)

```
Query: lib-records.sh query "<address in Cook County, IL>" ownership

Router:
  1. resolve county+state → Cook County, IL (FIPS 17031)   (event: tier_decision, tier:tier1)
  2. compliance gate → robots.txt allows + tos acknowledged
  3. cache miss → fetch via tier1-counties/cook-county-il.json selectors
  4. stamp source + retrieved_at on the record
  5. cache the result (30-day TTL)
  → (event: query, record_type:ownership, result_count:1, source:"cook-county-il", retrieved_at:"...")
```

The record is returned WITH provenance. No provenance → not returned.

## Example 2 — Tier 4 honest gap (no online database)

```
Query: lib-records.sh query "<address in a rural county with no online portal>" deeds

Router:
  1. resolve county+state → <County>, <ST>
  2. Tier 1? no curated config. Tier 2? no known platform. Tier 3? no operator config.
  3. → Tier 4 honest gap (event: tier_decision, tier:tier4_honest_gap; event: honest_gap, reason:no_online_db)

Agent to operator: "That county has no online records database I can query, and no Tier-3 config is
built for it. I won't guess — if you have the county clerk's portal URL, I can build a Tier-3 config
and validate it. Otherwise this is a manual lookup."
```

NEVER an invented deed. The honest gap is the answer.

## Example 3 — Compliance block (robots disallow)

```
Query against a target whose robots.txt disallows our path:

  compliance gate → robots_disallow
  → (event: compliance_block, reason:robots_disallow) → Tier 4 honest gap

Agent: "That portal's robots.txt disallows automated access to that path, so I won't scrape it.
That's a manual lookup, or we can check whether they offer an API/bulk data feed."
```

robots.txt is binding. Never overridden.

## Example 4 — Bulk op cost estimate + confirm

```
Operator: "Pull pre-foreclosure records for these 60 addresses."

  batch_size = 60 > PR_BULK_CONFIRM_THRESHOLD (25)
  estimate = 60 × PR_COST_PER_QUERY + (60 × PR_PER_TARGET_MIN_INTERVAL_S) wall-clock
  → (event: cost_estimate, batch_size:60, est_cost:..., est_seconds:..., confirmed:false)

Agent: "Estimated: 60 queries, ~$X, ~Y minutes at the 5s/target rate limit. Confirm to proceed?"
  On operator YES → (event: cost_estimate ... confirmed:true) → run, respecting the per-day cap.
  At PR_DAILY_CAP → (event: cost_block, reason:daily_cap) → stop and tell the operator.
```

No silent bulk runs. The operator confirms cost + time first.

## Example 5 — Cache hit (free + instant)

```
Repeat query within 30 days:
  cache key = hash(target + query) → fresh hit
  → (event: cache_hit, record_type:tax, age_days:4)  → returned instantly, free.

Force a refresh:
  lib-records.sh query "<...>" tax --force-refresh
  → (event: force_refresh, record_type:tax) → bypasses cache (subject to compliance + cost gates).
```

## Example 6 — Tier 2 (platform adapter reuse)

```
Query against a county that runs on Tyler Technologies (no dedicated Tier-1 config):

  Tier 1? no. Tier 2? yes — county-platform-map.md maps it to the Tyler adapter.
  → use tier2-adapters/tyler-technologies.md parameterized for this county
  → (event: tier_decision, tier:tier2, reason:"tyler-technologies platform")
```

One adapter serves many counties on the same vendor.

## Example 7 — Pairing with Skill 39 (pre-foreclosure)

```
Query: lib-records.sh query "<address>" pre_foreclosure  → Tier 1/2/3 hit returns a NOD record
  (with source + retrieved_at).

Skill 40 logs it and STOPS — it does not message anyone.
Skill 39's pre-foreclosure-outreach-protocol.md consumes the record and runs care-first outreach.
```

Skill 40 stays in its lane: find + attribute + cache + log.

## Example 8 — Reading the event log (operator ground truth)

```bash
$ tail -3 "$MASTER_FILES_DIR/public-records-queries.jsonl"
{"ts":"2026-05-30T16:00:01Z","skill":"40-zhc-public-records-scraper","event":"tier_decision","query_ref":"q_77","target_ref":"cook-county-il","tier":"tier1","county_fips":"17031","state":"17"}
{"ts":"2026-05-30T16:00:02Z","skill":"40-zhc-public-records-scraper","event":"cache_hit","query_ref":"q_77","target_ref":"cook-county-il","record_type":"ownership","age_days":4}
{"ts":"2026-05-30T16:01:00Z","skill":"40-zhc-public-records-scraper","event":"honest_gap","query_ref":"q_78","target_ref":"<rural-county>","reason":"no_online_db"}
```

The log records record TYPES + counts + status and opaque handles — never raw record contents.
