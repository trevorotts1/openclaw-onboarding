# Rescue Rangers — Heartbeat Truthfulness Contract (client-facing addendum, SANITIZED)

**RR-014 addendum to the Public Client Contract.** Audience: client-box and
client-facing documentation consumers. This file is safe for public
repositories. It carries **no credential values, no client identities, no
table IDs, no private workflow IDs, no deployment internals.** The
authoritative private contract is `blackceo-fleet-ops:rescue/monitoring.json`
(which itself extends `blackceo-fleet-ops:rescue/contract-manifest.json`);
this file is the sanitized projection.

**Contract version:** monitoring truthfulness schema `1` (2026-09-09).

---

## What changes for a client box (and what does not)

Nothing on the box changes. Heartbeat health and notification receipts are
**operator-side monitoring concerns**: the box keeps polling, claiming and
acknowledging exactly as before. What the box may notice is timing (the
operator group hears about a stale lease or a dead box on the verified-receipt
schedule, not on a guessed count) — never a lost incident, and never a new
requirement on the box.

## The truthfulness rules

The heartbeat monitor must never report health it did not measure, and must
never count a notification that was not actually delivered:

1. **Typed reads, not assumptions.** Every monitoring source is read and
   classified as one of: complete, empty, partial or error. A partial or error
   read leaves the previous baseline untouched and marks every metric that
   depends on that source UNKNOWN, with an owned monitor fault. A broken read
   is never reported as an empty queue and never as "all healthy".
2. **Genuine empty is real.** A real empty result is legitimate and useful; it
   only becomes a fault when the source is known to be non-empty and returns
   nothing plausible.
3. **Work phases are tracked by deadline and progress, not by claims.** Queued,
   claimed, started, pending-acknowledgment, stale-lease and exhausted work
   are separate states with canonical deadlines. A box that is alive and
   polling does not by itself prove its claimed work is progressing; a stale
   lease is its own incident with one recovery owner.
4. **One recovery owner.** Stale lease recovery belongs to exactly one
   fenced reaper. No monitoring path competes with lease authority, reclaims
   its rows, or executes a second recovery.
5. **Receipt-gated notification counts.** A notification counts as sent only
   after a validated delivery receipt (message, chat and thread identity all
   present). A failed send, a timeout, a refusal or an error item cannot
   count as delivered and never appears as posted, and no count ever advances
   before the send.
6. **Dry-run changes nothing.** A dry run records its own separate counter and
   mutates no send or suppression state.
7. **Verify before declaring written.** "State written" is true only when
   every expected write family is backed by verified receipts. Echoed input
   is not a persistence receipt.
8. **A monitor-of-monitor heartbeat runs outside the monitored path.** The
   monitor itself is watched by a separate scheduler heartbeat, so a dead
   monitor is a visible fault, never silence.

## What an operator may conclude from the operator group

- A reported **stale lease** means exactly one incident per episode, owned and
  due, and is not self-healed by the monitor (the reaper owns recovery).
- A reported **read failure** means the metric is UNKNOWN: healthy-looking
  zeroes from that run must not be treated as an all-clear.
- A reported **send failure** keeps its alert owned and retryable; the failed
  notification never consumed a delivery budget.

Anything not backed by a validated receipt is labeled UNKNOWN or unverified —
never silently presented as a measured fact.
