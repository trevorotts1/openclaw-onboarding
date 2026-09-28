# ACC-052 — the batch tick as a one-step state machine

Status: live mechanism, proven end to end 2026-09-28.

`pres-batch-merge.sh` does **not** poll or wait. Each invocation performs exactly
one step, then exits, so it is safe to run by hand at any time — a lock
directory (`/private/tmp/pres-merge.lockdir`) serializes concurrent invocations
and a second caller exits immediately.

## The two states

1. **A `batch/auto-merge` PR is open and green** — merge it, then exit. The
   merge is a squash, so the folded branches land as one commit.
2. **No such PR** — collect every ready branch, merge them into one local
   `batch/auto-merge` branch, run `scripts/bump-version.sh` when present, push,
   and open the batch PR. CI decides the outcome on a later tick.

## Why one batch PR

Every folded branch rides the same CI run: one set of required contexts covers
the whole set, instead of one run per branch. A branch that conflicts with the
growing batch is reported as `CONFLICT skipped: <branch>` and left out rather
than aborting the batch.

## Cost of the state machine

A branch that enters the batch after the PR has opened waits for the next two
ticks — one to merge the current batch, one to open the next. This is the
deliberate trade for "merged in batches, never mid-run".
