# Cost Cap Protocol

Enforced by `scripts/lib-cost-cap.sh` + `scripts/lib-records.sh`. No silent bulk
runs; no daily overruns; no hammering a target.

## Caps (env-overridable; recorded by `04-configure-caps.sh`)

| Control | Env var | Default |
|---|---|---|
| Global daily query cap | `PR_DAILY_CAP` | 200 |
| Per-target rate limit | `PR_PER_TARGET_MIN_INTERVAL_S` | 5s |
| Bulk-op confirm threshold | `PR_BULK_CONFIRM_THRESHOLD` | 25 |
| Estimated cost per query | `PR_COST_PER_QUERY` | $0.00 (see below) |

## Cost is $0.00 by default — the bulk-confirm gate is batch-size-gated

Public-records county portals are **free**, so `PR_COST_PER_QUERY` defaults to
`$0.00` and the computed `est_cost` (`batch_size × PR_COST_PER_QUERY`) is `$0.00`
until the operator sets a real per-query cost. Because of that, the bulk-confirm
gate below triggers on **batch size** (`PR_BULK_CONFIRM_THRESHOLD`), NOT on a
dollar figure — the `$0.00` estimate is informational, not a cost cap. If you
route through a **paid** Tier-2 vendor, set `PR_COST_PER_QUERY` to that vendor's
real per-query price so the estimate reflects an actual spend before you confirm.

## Per-day cap

The router checks `under_daily_cap` before any live fetch. At the cap, it refuses
with `cost_block` (reason `daily_cap`) and tells the operator — it does not
silently overrun. The counter resets daily (tracked per UTC date in the cache
dir).

## Per-target rate limit

Before fetching a target, the router takes an **atomic reservation** through
`lib-cost-cap.sh :: rate_wait`: it holds a per-target lock, computes the delay
from the last ACTUAL request time, sleeps the remainder while still holding the
reservation, and stamps the timestamp at the **request boundary** — the instant
before the caller issues the request. It logs `rate_limit_wait` with the seconds
actually waited. The caller does not sleep again.

**Why it is a reservation (SK1-30 / T2-33).** The old shape computed the delay,
stamped the timestamp immediately, and left the sleeping to the caller. The
recorded time was therefore the time the delay was COMPUTED, not the time the
request was MADE, so the next computation measured from the wrong origin: after
one waited request the following request measured its gap from the previous
computation and could fire with zero spacing. The audit log recorded a compliant
wait for a non-compliant request rate — a terms-of-service exposure on a
scraping skill. Holding the lock across the sleep also serialises concurrent
callers instead of letting them race through together.

## Bulk cost estimate + operator confirmation

For any batch above `PR_BULK_CONFIRM_THRESHOLD`, BEFORE running:

1. Compute the estimate: `batch_size × PR_COST_PER_QUERY` (cost — `$0.00` unless a
   paid vendor cost is configured) and `batch_size × PR_PER_TARGET_MIN_INTERVAL_S`
   (approx wall-clock seconds at the rate limit). The confirm is gated on the
   batch size crossing `PR_BULK_CONFIRM_THRESHOLD`, not on the dollar figure.
2. Log a `cost_estimate` event (`confirmed:false`).
3. PRESENT the estimate to the operator and WAIT for explicit confirmation.
4. On confirmation, log `cost_estimate` (`confirmed:true`) and run, still
   respecting the per-day cap and per-target rate limit.

The operator never gets a surprise bill or a surprise multi-hour run.
