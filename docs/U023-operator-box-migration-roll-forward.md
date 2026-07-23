# U023 -- Operator Box Migration Roll-Forward (110-111)

**Date:** 2026-07-23
**Surface:** live
**Finding:** MASTER-SPEC item #23

## Context

The live operator-box DB has 109/111 migrations applied. Migrations 110-111 are staged and will apply on the next boot/update. This runbook rolls the operator box forward safely and idempotently.

## Prerequisites

- SSH access to the operator box (Trevor's Mac)
- `pm2` is installed and managing the OpenClaw gateway
- `sqlite3` is available on the box
- The repo has been pulled to the latest commit that includes migrations 110-111

## Pre-flight: check current migration count

```bash
sqlite3 data/mission-control.db "SELECT COUNT(*) FROM _migrations;"
```

If the output is already `111`, the roll-forward is already applied. Stop here -- nothing to do.

## Method A: pm2 restart (preferred)

The gateway applies pending migrations at startup. Restarting pm2 triggers this:

```bash
cd ~/July-23-Fixes/repos/blackceo-command-center
git pull origin main
pm2 restart all
```

Wait 10 seconds for the gateway to boot, then verify:

```bash
sqlite3 data/mission-control.db "SELECT COUNT(*) FROM _migrations;"
# Expected: 111
pm2 status
# All processes must show status "online"
```

## Method B: update.sh (fallback)

If `update.sh` exists and is the canon update path:

```bash
cd ~/July-23-Fixes/repos/blackceo-command-center
bash update.sh
```

Then verify as above.

## Post-roll-forward verification

```bash
sqlite3 data/mission-control.db "SELECT COUNT(*) FROM _migrations;"
# Must return 111

pm2 status
# All processes must show status "online"
```

## Idempotency guarantee

Both methods are safe to re-run:
- `git pull` on an already-current repo is a no-op
- `pm2 restart` on an already-restarted gateway is safe
- Pending migrations are applied with `IF NOT EXISTS` guards (see spec-common Section 4, SQLite migration convention)
- Re-running migrations that are already applied is a no-op

## Failure recovery

If the migration count is still below 111 after the restart:

1. Check pm2 logs for migration errors: `pm2 logs --lines 50`
2. Confirm the repo is on the latest commit: `git log --oneline -1`
3. Manually list pending migrations: `sqlite3 data/mission-control.db "SELECT * FROM _migrations ORDER BY id DESC LIMIT 5;"`
4. If migrations 110-111 are absent from the `_migrations` table, run them manually per the migration files in `migrations/`
5. Re-verify count

## Named Stop

This is a `live` surface unit. Restarting pm2 on the live operator box is a Named Stop -- the operator must trigger the restart. The runbook is `ready-to-apply`.
