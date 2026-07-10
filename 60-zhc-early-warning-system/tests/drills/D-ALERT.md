# Drill D-ALERT -- operator-only routing, dedup, batching, and the S10 announce trap

## What it proves

Every alert reaches the OPERATOR account only, through the box's own gateway, with
`deliver:false` agent-loop semantics -- never a client chat, never a client bot.
Repeated identical events dedup within the configured window instead of spamming.
A P1 always bypasses the daily batch cap; P2/P3 respect it. And the S10 "announce
cron bound to a non-operator chat" case is itself caught as a P1 BEFORE it can ever
fire and actually reach a client -- the sentinel is watching its own delivery
surface, not just the client's.

## Fixture / input

- `tests/fixtures/announce-cron.json` diffed against
  `tests/fixtures/baseline-clean.json`: the added `daily-report` cron entry,
  `delivery: "announce"`, `target: "client"`.
- A synthetic sequence of five identical P2 events for the same key within the
  6-hour dedup window (`thresholds.json: alert.dedup_window_hours`), to exercise
  dedup and the 4/day per-box batch cap.
- One P1 event injected into the same sequence, to prove it bypasses the batch cap
  that the P2 events are subject to.

## Pass condition

- The `announce-cron.json` diff produces exactly one P1 event, signal S10, key path
  `cron`, note identifying the `daily-report` entry's `delivery: "announce"` bound to
  a non-operator target. This event is itself routed OPERATOR-ONLY (the alert about a
  client-spam cron never itself spams the client) -- the drill confirms the alert
  transport target is always the operator account regardless of what the flagged
  cron's own target field says.
- Of the five identical synthetic P2 events, only the FIRST produces a delivered
  alert; the remaining four within the 6-hour window are recorded in the `digests`
  table but not re-delivered (dedup).
- Across the batch cap test: the operator receives at most 4 P2/P3 alerts for that
  box in the simulated day, but the injected P1 is delivered regardless of how many
  P2/P3 alerts already fired that day (`p1_bypasses_batch: true`).
- No event in this drill, at any severity, is ever addressed to anything other than
  the box's own operator account.
