# ACC-052 — the `batch-train` label governs enrollment

Status: live mechanism, proven end to end 2026-09-28.

## What the label means

A pull request carrying the GitHub label `batch-train` is **not** merged by the
continuous automerge daemon. Trevor's ruling of 2026-09-28: such PRs are merged
deliberately, in batches, after QC — never casually mid-run. Auto-merging one
would break frozen-SHA binding while a run is in flight.

## Where it is enforced

- Daemon: `~/.claude/tools/pres-automerge.sh` reads each open PR's labels and
  skips any PR whose labels contain `batch-train`.
- Train: `~/.claude/tools/pres-batch-merge.sh` collects the head branches of
  open `batch-train` PRs and folds them into a single batch pull request.

## Why both halves are required

The skip alone is not enough. The train historically discovered work only by
branch-name pattern (`fix/*`, `feat/trust-*`). A `batch-train` PR on any other
branch name would be skipped by the daemon *and* invisible to the train —
merged by nothing, forever. The label, not the branch name, is the authority.
