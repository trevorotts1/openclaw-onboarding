# Skill 32 — Command Center HEARTBEAT additions

These are the recurring checks Skill 32 contributes to the box's heartbeat loop.
Append the blocks below to the agent's live `HEARTBEAT.md` (the same way
`CORE_UPDATES.md` documents the Command Center Activation Check). Operator-facing
only — WE MOVE IN SILENCE; none of these checks message the client.

---

## Fleet Embedding Canary (every 6 h)

`scripts/heartbeat-canary-probe.py` runs a semantic-vs-keyword quality check
against the Command Center `mission-control.db`, records the result in the
`system_status` table (so the dashboard can surface embedding health per box),
and alerts the Rescue Rangers escalation channel **only** when embeddings are
dark. It is read-only apart from the `system_status` table it owns, and it
**cannot** alert unless `RESCUE_RANGERS_HELP_CHAT_ID` is set — so it is safe to
schedule.

**Status meanings**

| status   | meaning                                                                 | exit |
|----------|-------------------------------------------------------------------------|------|
| healthy  | ≥80% SOP embedding coverage, persona index present, < 7 days old        | 0    |
| degraded | coverage 40–79%, OR 7–30 days stale, OR recall ratio < 0.5              | 1    |
| dark     | embeddings table missing/empty, persona index empty, <40% cov, >30d old | 2    |
| error    | DB not found / script failure                                           | 3    |

**Manual run (operator box):**

```bash
python3 ~/.openclaw/skills/32-command-center-setup/scripts/heartbeat-canary-probe.py
# inspect-only, writes nothing, sends no alert:
python3 ~/.openclaw/skills/32-command-center-setup/scripts/heartbeat-canary-probe.py --dry-run
```

**Wire it as an OpenClaw cron (every 6 hours).** Uses the docs-canonical
positional form (`openclaw cron create "<schedule>" "<prompt>" --name N --agent A
--session main`) verified against the installer's cron helper:

```bash
openclaw cron create "0 */6 * * *" \
  "Run the Skill 32 Fleet Embedding Canary: execute 'python3 ~/.openclaw/skills/32-command-center-setup/scripts/heartbeat-canary-probe.py'. If it reports degraded or dark, follow its remediation. Operator-only — do NOT message the client." \
  --name fleet-embedding-canary --agent main --session main --light-context
```

Idempotency: before creating, check it is not already registered —
`openclaw cron list | grep -qi fleet-embedding-canary` — and skip if present.

**If the canary reports `dark`:** the SOP embeddings or persona index are not
built/stale. Re-run the SOP library ingest + persona index provisioning for the
box, then re-run the canary to confirm it returns to `healthy`.

---

## Command Center Activation / liveness

(See `CORE_UPDATES.md` → "HEARTBEAT.md Addition" for the twice-daily activation
check and the `pm2 list | grep blackceo-command-center` liveness probe. The
dashboard runs on **:4000**.)
