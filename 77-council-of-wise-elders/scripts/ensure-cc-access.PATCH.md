# Hook for scripts/council-access-autoprovision.sh (integrator applies this)

`ensure-cc-access.sh` must run once per job run, before `provision-council-access.sh`, so a
brand-new client's Command Center host already has its Access application when the Council step
looks for it. The W40-B branch (`unit/W40-B-autoprovision-job`, commit e5316f4e8) still owns
`scripts/council-access-autoprovision.sh`, so this file carries the exact patch instead.

In `council-access-autoprovision.sh`, find:

```bash
ARGS="--all --json"; [ "$MODE" = apply ] && ARGS="$ARGS --apply"
# shellcheck disable=SC2086
"$PROVISION" $ARGS >"$OUT" 2>"$ERR"; RC=$?
```

Insert the ONE hook line between the `ARGS=` line and the `"$PROVISION"` line:

```bash
ARGS="--all --json"; [ "$MODE" = apply ] && ARGS="$ARGS --apply"
[ -x "$HERE/ensure-cc-access.sh" ] && "$HERE/ensure-cc-access.sh" --json $([ "$MODE" = apply ] && echo --apply) >/dev/null 2>&1 || true
# shellcheck disable=SC2086
"$PROVISION" $ARGS >"$OUT" 2>"$ERR"; RC=$?
```

Why this is safe:
- `|| true` and the `/dev/null` redirect: a failure or noisy output in the new step can never fail the
  job or corrupt the JSON `provision-council-access.sh` prints. Its result is in its own receipts.
- It inherits the already-exported `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` and the same
  `COUNCIL_ACCESS_STATE_DIR`, `CF_API_BASE`, `COUNCIL_ZONE_NAME`, `COUNCIL_ACCESS_EXCLUDE`.
- It takes its own lock (`cc-access.lock`), not the job's `run.lock`, so it does not deadlock inside the job.
- Dry-run is the default: it sends GET requests only unless the job itself was started with `--apply`.

Receipts (same state dir as the job, different file names so nothing is overwritten):
`cc-access-last-run.json` (replaced each run) and `cc-access-runs.log` (one line per run, counts only).
A host that cannot be created yet shows as `NEEDS_EMAIL` and is retried on every run.

One-time operator setup the hook needs (no per-client step afterwards):
- `COUNCIL_CC_OPERATOR_EMAILS` (comma list) in the job's environment, or `"operator":[...]` in
  `$HOME/.claude/state/council-elders/cc-access-emails.json`. Without any operator email the step
  refuses (exit 3, zero requests) and the job carries on.
- Client emails: either `"clients":{"<slug>":["owner@example.com"]}` in the same file, or nothing at
  all when the client's `rescue-<slug>` Access app already lists the client's own email (the fleet
  onboarding doc puts it there). With neither, the host stays `NEEDS_EMAIL`.
