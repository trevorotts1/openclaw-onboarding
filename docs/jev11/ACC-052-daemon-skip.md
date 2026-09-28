# ACC-052 — the daemon skip, and why it fails open

Status: live mechanism, proven end to end 2026-09-28.

## The skip

`pres-automerge.sh` ticks every 180 seconds under launchd
(`com.blackceo.pres-automerge`). For each open PR it runs:

    gh pr view <n> --repo <repo> --json labels --jq '.labels[].name'

and, when the result contains `batch-train`, logs `SKIP #<n> batch-train` and
continues without evaluating mergeability. The required-context check, the
merge, and the `--admin` flag are never reached.

## Fail-open, deliberately

The label lookup's stderr is discarded and a failure yields an empty label list,
so a transient `gh` error would let a labeled PR fall through to the merge path.
That is safe here **because the tick has already authenticated**: the script
lists all open PRs in a single call *before* the loop, and on a non-zero exit it
logs `!!!! AUTH-FAILURE !!!!` and aborts the whole tick with rc=3. A dead
credential therefore stops every merge, labeled or not — the fail-open path is
unreachable when `gh` is broken.

## What the log proves

The daemon writes `HEARTBEAT tick ok: <n> open PR(s) to check` unconditionally on
every successful tick. A silent log therefore proves the timer stopped firing,
not that there was no work.
