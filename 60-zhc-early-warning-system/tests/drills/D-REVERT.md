# Drill D-REVERT -- restore-as-box-user, byte read-back, exact-value round-trip

## What it proves

`revert --to <utc-ts>` restores the EXACT prior byte content from the nearest
snapshot at or before that timestamp, always writes as the box user (never root,
`docker exec -u node` on VPS), and reads the file back after writing to confirm the
write actually took before reporting success -- a revert that "succeeds" but leaves
the file unchanged (a permissions failure swallowed silently, for instance) is a
worse outcome than the original problem, so this drill exists to prove that case is
impossible.

## Fixture / input

- `tests/fixtures/baseline-clean.json` snapshotted at time T0.
- `tests/fixtures/cap-raise.json` written at time T1 (the unstamped raise from
  D-S4), producing a second snapshot entry.
- A `revert --to T0` (or any timestamp between T0 and T1) invocation against the
  live config currently holding the T1 (raised) content.

## Pass condition

- After the revert, the live config's `agents.defaults.subagents.maxConcurrent` is
  back to `16` (the T0 value) -- an exact byte-for-byte match against the T0
  snapshot's stored content, not merely "the same cap number" (every other key in
  the file must also match T0 exactly; the revert is a full-file restore, not a
  single-key patch).
- The revert operation's own write is performed as the box user in every check the
  drill runs; a drill run that detects the write attempted as root fails loudly
  rather than silently succeeding.
- Immediately after the write, the revert path reads the file back from disk and
  compares it against the snapshot's stored sha256 before reporting success. A
  drill variant that simulates a write failure (for example, a read-only
  destination) must cause `revert` to report FAILURE, never a false success.
- The revert produces a NEW `snapshots` entry for the restored state (the ledger
  never loses the fact that a revert happened, or pretends the config was never at
  the T1 value), and a subsequent `audit` run shows the config matching baseline
  again with zero open S4 events for the reverted key.
