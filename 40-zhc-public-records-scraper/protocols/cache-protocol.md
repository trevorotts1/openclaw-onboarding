# Cache Protocol

30-day result cache. Implemented in `scripts/lib-records.sh`; dir created by
`scripts/02-init-cache.sh`.

## Location & key

- Cache dir: `<MASTER_FILES_DIR>/public-records-cache/`.
- Cache key: a hash of
  `(namespace + normalized target slug + county FIPS + record type + normalized query)`.
  The raw address is NEVER used as a filename — only the hash. This keeps the
  cache directory free of raw PII.
- **The query is part of the identity (SK1-30 / T1-05).** Until this fix the key
  was target + FIPS + record type only, so two different addresses in the same
  county for the same record type produced the SAME key: within the cache
  lifetime, a lookup for one property returned the cached, attributed record for
  a DIFFERENT property, on the fast/free/confident cache-hit path. The writer and
  the reader agreed with each other because they shared the same defect; both now
  derive the key from one function, `lib-records.sh :: _cache_key`.
- **Namespace version:** entries are written as `v2-<hash>.json`. Pre-fix entries
  (`<hash>.json`, computed without the query) are not reachable under the new
  scheme and are simply never served again. Expect a one-off rise in upstream
  calls while the new namespace fills — that is the wrong hits becoming misses.
- The normalised query identity is case-folded, comma/semicolon-separated,
  whitespace-collapsed and trimmed: `123 Main St, Springfield IL` and
  `123  MAIN ST,  Springfield  IL` are one identity; two different addresses
  never are.

## TTL & hits

- Default TTL: `PR_CACHE_TTL_DAYS` (30). A cached entry younger than the TTL is a
  **fresh hit**: returned instantly, free, and logged as `cache_hit` (with
  `age_days`). It does NOT count against the daily cap or hit the target.
- An entry older than the TTL is treated as a miss and re-fetched (subject to the
  compliance + cost gates).

## Force refresh

`lib-records.sh query "<...>" <type> --force-refresh` bypasses the cache for that
one query, re-fetching live (logged `force_refresh`), then re-caching the result.

## What the cache stores

The cache stores the retrieved record WITH its `source` + `retrieved_at`
provenance (so a cache hit is still attributed). It never stores a record without
provenance. The event log, by contrast, records only the cache STATUS + record
type + age — never the raw record contents.
