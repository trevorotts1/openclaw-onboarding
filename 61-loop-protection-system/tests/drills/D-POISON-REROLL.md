# D-POISON-REROLL (+ BOUND / REFUSAL / TICK)

Synthetic fixture (`tests/fixtures/loop-blocked-session.jsonl`), plus a synthetic
240-byte session name generated in the drill. Run by `verify.sh` step 3. Offline.

These four drills exist because of a **real crash, reproduced before it was fixed**:
the LF-10 transcript roll was not idempotent, and the watchdog it protects had no
failure boundary around a kill card, so the two defects together turned the loop
protection system into a loop that killed its own scheduled job.

## The fault, as measured

`collect_sessions()` globbed every `*.jsonl` under `agents/*/sessions/` except
trajectories. An LF-10 archive is a `*.jsonl` in that same directory, `shutil.move`
preserves the original mtime, and the archived bytes are the same poisoned bytes.
So on the NEXT tick the archive re-measured as poisoned **and** idle, D5 raised a
fresh P1, and LF-10 archived the archive - appending another
`.loop-archive-<stamp>` to the name every tick, 30 bytes at a time:

| tick | longest name (bytes) | result |
|---|---|---|
| 1 | 26 | archived (correct) |
| 2 | 56 | archive re-archived |
| … | +30/tick | … |
| 7 | 206 | archive re-archived |
| **8** | **236 -> 266** | **`OSError: [Errno 63] File name too long`, UNCAUGHT** |

Independently reproduced against a uuid-shaped session name (42 bytes, the realistic
case): **7 successful rounds, crash on the 8th**, last legal name 252 bytes. The
per-round cost is 30 bytes (`.loop-archive-` + a 16-byte stamp).

It crashes on **both** interpreters, which matters because a cron `PATH=/usr/bin:/bin`
resolves the system one:

| interpreter | where it raises |
|---|---|
| 3.9.6 (`/usr/bin/python3`, cron's) | `Path.exists()` - the pre-flight existence check itself |
| 3.14.5 (homebrew) | survives `exists()`, raises in `shutil.move` |

Either way it leaves the tick dead and, at `*/15`, would have taken about two hours
to get there.

Two things made it worse than a wasted tick:

1. The healer self-breaker (`max_fixes_per_target_per_day`) could not catch it. It
   counts fixes per **unit**, and D5's unit is derived from the FILENAME - which
   changed on every roll. The one mechanism designed to stop a looping healer was
   structurally blind to this loop.
2. The `OSError` escaped `tick()`. In a scheduled job that is not one lost finding,
   it is a **watchdog that dies silently every run** while the box still looks
   watched - the exact failure this skill exists to prevent.

## The drills

- **D-POISON-REROLL** - 10 armed ticks over ONE poisoned transcript roll it
  **exactly once**. Afterwards the directory holds one file, carrying exactly one
  archive marker, and no name has grown. An archive is finished work and is out of
  D5's scope permanently.
- **D-POISON-REROLL-BOUND** - the constructed name is bounded to 255 bytes (the
  single-component limit on every filesystem this skill ships to). An over-long stem
  is truncated and joined to a short sha256 of the FULL stem, so the name stays
  unique and **deterministic** - the same transcript always yields the same archive
  name, which is what keeps a re-run idempotent instead of piling up near-duplicates.
  A stem that already fits is left byte-for-byte alone. Asserted on the helper AND
  end to end: a real roll of a 240-byte-stem transcript must succeed.
- **D-POISON-REROLL-REFUSAL** - an `OSError` from the move (read-only mount,
  permissions, a vanished parent) comes back as `{applied: False}` with the
  transcript left exactly as found. A filesystem refusal is a refusal, never a crash.
- **D-POISON-REROLL-TICK** - the outer boundary, proven with fault injection at the
  kill-card seam: two poisoned transcripts, the FIRST rigged to raise. The tick
  returns, counts `errors == 1`, and **still rolls the second one**. One bad unit
  never kills the tick.

## Failability (proven, not assumed)

Mutation-tested against the fixed tree, one mutation at a time:

| Mutation | Result |
|---|---|
| Archive exclusion removed from `_session_files()` (the root cause restored) | **D-POISON-REROLL FAILS** |
| `NAME_MAX_BYTES` weakened 255 -> 10000 (the bound made ineffective) | **D-POISON-REROLL-BOUND FAILS** |
| `try/except OSError` removed from `lf10_archive_and_roll_session` | **D-POISON-REROLL-REFUSAL FAILS** |
| Per-finding boundary removed from `tick()` | **D-POISON-REROLL-TICK FAILS** |

Each mutation fails its own drill and no other, so the four checks are independent -
none is masked by another (contrast D-POISON, where two redundant guards mask each
other and only the combined mutation is catchable).

## Invariant

`loop_killcards.ARCHIVE_MARKER` is the shared contract: the kill card WRITES it and
the D5 collector SKIPS it. It is a module constant precisely so the producer and the
consumer cannot drift apart - a drift between them re-opens the runaway above.
