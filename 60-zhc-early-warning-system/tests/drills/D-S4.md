# Drill D-S4 -- unstamped cap raise vs approved cap raise

## What it proves

The never-silently-raise rule: an unstamped safety-cap raise is ALWAYS a P1 with a
working revert command, and the ONLY way to make the sentinel go quiet on a specific
raised value is an explicit `approve-baseline` stamp -- never a silent baseline
rewrite, never a lowered severity, never a "it's probably fine" heuristic.

## Fixture / input

- `tests/fixtures/cap-raise.json` diffed against `tests/fixtures/baseline-clean.json`
  as the pinned baseline: `agents.defaults.subagents.maxConcurrent` moves 16 -> 64
  with no ledger `baseline_stamps` entry for that key/value-hash.
- The same diff, but with a `baseline_stamps` record present for
  `agents.defaults.subagents.maxConcurrent` at the hash of value `64`, simulating a
  prior `approve-baseline --key agents.defaults.subagents.maxConcurrent` call.

## Pass condition

- **Unstamped**: exactly one P1 event, key path
  `agents.defaults.subagents.maxConcurrent`, measured=64, baseline=16, class=`cap`,
  direction=`raise`. The event carries a working revert command
  (`ews-entry.sh revert --to <snapshot-ts>`) that, if executed against the snapshot
  taken at baseline time, restores the value to 16.
  `enforce_caps_default` is `false` (D2, `thresholds.json`) so the sentinel does NOT
  auto-revert -- it only alerts and hands over the revert line.
- **Stamped**: the identical diff (same fixture, same raised value) with the
  matching `baseline_stamps` record present produces ZERO operator alerts for that
  key. The raw config diff still shows the value moved (the sentinel is not lying
  about reality), but the event is suppressed at the alert layer because the stamp
  covers this exact value's hash.
- A stamp for a DIFFERENT value (for example, a prior approval of 32, not 64) does
  NOT suppress the alert for 64 -- stamps are per-key, per-value-hash, never a
  blanket "this key is approved forever."
