# Drill D-DEADMAN -- the operator-box aggregator's dead-man switch

## What it proves

A box that is too broken to run its own tick, write its own ledger, or reach its own
gateway is not a box the operator silently loses visibility into. The hourly
operator-box aggregator tracks a per-box "last fresh tick" timestamp, and a box that
misses two consecutive hourly cycles with no fresh tick is declared "sentinel dark"
and raises a P1 -- on the OPERATOR's behalf, sourced from the operator box, not from
the broken box (which by definition cannot report on itself).

## Fixture / input

- A synthetic per-box digest history for one box: fresh digests arriving on a normal
  hourly cadence, then a gap.
- Three timing variants: (a) a gap of exactly one missed cycle, (b) a gap of exactly
  two missed cycles, (c) a gap of three-plus missed cycles.

## Pass condition

- Variant (a), one missed cycle: no dead-man P1. `thresholds.json`'s
  `dead_man_cycles: 2` means a single missed hour is tolerated (network hiccup,
  clock skew, a slow tick) without paging the operator.
- Variant (b), two missed cycles: exactly one dead-man P1 fires, identifying the box
  by name, signal class `sentinel-dark`, with the last-known-good tick timestamp
  attached so the operator knows how stale the box's last real data is.
- Variant (c), three-plus missed cycles: the dead-man P1 from variant (b) is NOT
  re-fired every additional missed cycle (that would violate the dedup/escalation
  design) -- instead, since a dead-man P1 escalates immediately per D4 (no 30-minute
  unacked wait, unlike a normal P1), the drill confirms the escalation to the Rescue
  Rangers channel fires once, at the moment the box first crosses the two-cycle
  threshold, not on every subsequent aggregator pass.
- A box whose digests resume on schedule after a gap is picked back up cleanly: the
  next fresh digest clears the dead-man state without a separate "recovered"
  acknowledgment step being required to unblock future dead-man detection.
