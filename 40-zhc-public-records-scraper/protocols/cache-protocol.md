# Cache Protocol

30-day result cache. Implemented in `scripts/lib-records.sh`; dir created by
`scripts/02-init-cache.sh`.

## Location & key

- Cache dir: `<MASTER_FILES_DIR>/public-records-cache/`.
- Cache key: a hash of `(normalized target slug + county FIPS + record type)`.
  The raw address is NEVER used as a filename — only the hash. This keeps the
  cache directory free of raw PII.

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
