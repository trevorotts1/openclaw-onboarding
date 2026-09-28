# ACC-052 — the daemon's required-context gate

Status: live mechanism, proven end to end 2026-09-28.

`pres-automerge.sh` merges only when every context in its `REQ` array is present
and complete on the PR's `statusCheckRollup`, with zero pending and zero
failures. The check is a positive list, not a threshold: a context that never
reports is treated as absent and blocks the merge, so adding a new required
workflow to the gate is what actually makes it enforceable.

## The gate is counted, not timed

The script does not wait for a PR to become green. It reads the rollup once per
tick and either merges or logs `waiting #<n> pend=<n> fail=<n>` and moves on.
A PR therefore merges on the first tick *after* its contexts complete, which is
why merge latency is bounded by the tick interval (180 s) rather than by CI.

## Refusals are recorded, never papered over

A green rollup does not guarantee a merge. When GitHub refuses — a conflicting
base, a protected branch, a required review — the script re-reads the PR's real
state and logs `MERGE REFUSED #<n> (state=<state> rc=<rc>) reason=...`. The word
`MERGED` is written only when the post-merge state actually reads `MERGED`.

## Contexts that are not the gate

`RED #<n>` means a required context reported `FAILURE`. Because only the `REQ`
list participates, a failing workflow that is *not* in `REQ` blocks nothing and
is invisible here — it must be reviewed in the PR itself.
