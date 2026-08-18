# D-POISON / D-POISON-CLEAN / D-POISON-ROLL / D-POISON-LIVE

Synthetic fixtures (`tests/fixtures/loop-blocked-session.jsonl`,
`tests/fixtures/healthy-session.jsonl`). Run by `verify.sh` step 3. Offline.

D1-D4 measure FLOW - events per tick. They answer "is a loop running right now?"
and go quiet the moment it stops. **D5 measures a STOCK**: how much of a transcript
is already loop wreckage. That is the gap these drills defend. A paused loop leaves
a transcript that keeps degrading every later turn, and a flow detector reports
all-clear on it.

- **D-POISON** - a transcript carrying a burst of runtime tool-loop blocks is P1
  `LP-A8`, on both faces: IGNITION (consecutive blocks in one burst) and the
  SECOND CARRIER (a compaction checkpoint summary that captured the loop verbatim -
  those are re-injected on resume and **survive a transcript roll**, so rolling the
  file alone does not clear them).
- **D-POISON-CLEAN** - the control, and the reason this is a detector rather than
  an alarm bell. The clean fixture is deliberately the HARDER file: more bytes,
  ~7x the records, and more compaction checkpoints than the poisoned one. It is
  asserted silent twice - as measured, and again with its byte count forced 8x past
  the memoryFlush re-arm floor. **Size is a severity modifier in D5, never a
  trigger.** A detector that fires on everything is not a detector.
- **D-POISON-ROLL** - an ARMED tick ARCHIVES the poisoned transcript (moved to a
  timestamped name, byte-for-byte, **never deleted**) and leaves the clean one
  untouched.
- **D-POISON-LIVE** - a transcript still being written is REFUSED even when armed.
  The watchdog never rolls the conversation someone is in; a burning session gets
  the P1 and the prepared abort (LF-9), not a file yanked from under the gateway.

## Failability (proven, not assumed)

These drills were mutation-tested rather than trusted:

| Mutation | Result |
|---|---|
| Silence rule removed alone | still PASS - masked by the WARN floor (defence in depth) |
| Size made a trigger alone | still PASS - masked by the silence rule |
| **Both guards removed together** | **D-POISON-CLEAN FAILS** (correct) |
| **D5 thresholds raised out of reach** | **all four FAIL** (correct) |

The first two rows are the honest finding that the two guards are redundant with
each other, so no single mutation of either can be caught. Only the combined
mutation exposes the real "fires on everything" defect - which is exactly the
defect the control exists to catch.

## Thresholds

Every D5 threshold in `config/thresholds.json` is derived from measurement, not
chosen for roundness; the derivation and the counts behind each number are recorded
in that file's `d5_transcript_poison._source`.
