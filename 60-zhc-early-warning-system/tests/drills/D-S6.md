# Drill D-S6 -- config-write hygiene, root-owned writes, and snapshot-on-every-write

## What it proves

Every config write is snapshotted regardless of who wrote it or how severe the
finding is (reversibility is unconditional), a root-owned write is always a P1
(this is the exact S6 gateway-freeze incident the whole skill exists to catch), and
a write whose `argv` does not match any known sanctioned writer is a P2 even when
ownership is otherwise fine.

## Fixture / input

- A synthetic `config-audit.jsonl` tail with three rows against
  `tests/fixtures/baseline-clean.json` as the config being written:
  1. a normal write: `argv` contains `"openclaw"` (a `known_writer_argv_tokens`
     entry from `config/signatures.json`), file ownership = box user (`node`).
  2. a root-owned write: same `argv`, but the ownership stat on the written file
     reports `root` instead of the box user.
  3. an unknown-writer write: file ownership = box user, but `argv` contains none of
     `config/signatures.json`'s `known_writer_argv_tokens`.

## Pass condition

- Row 1 produces a `snapshots` table entry (path, ts, sha256, revert command text)
  and zero operator alerts -- a sanctioned, correctly-owned write is silent.
- Row 2 produces a P1 event, class=`config-write`, note identifying root ownership
  as the cause, PLUS a `snapshots` entry exactly as in row 1 -- reversibility is
  never conditional on severity.
- Row 3 produces a P2 event, class=`config-write`, note identifying the `argv` as an
  unknown writer, PLUS a `snapshots` entry.
- No script belonging to this skill itself ever performs a config-touching write as
  root; the drill's root-owned case is manufactured entirely in the synthetic audit
  row, never by actually running a skill script as root.
