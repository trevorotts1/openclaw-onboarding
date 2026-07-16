# Skill 32 — Command Center HEARTBEAT additions

These are the recurring checks Skill 32 contributes to the box's heartbeat loop.
Append the blocks below to the agent's live `HEARTBEAT.md` (the same way
`CORE_UPDATES.md` documents the Command Center Activation Check). Operator-facing
only — WE MOVE IN SILENCE; none of these checks message the client.

---

## Fleet Embedding Health Probe (every 6 h)

`scripts/heartbeat-embedding-probe.py` runs a semantic-vs-keyword quality check
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
python3 ~/.openclaw/skills/32-command-center-setup/scripts/heartbeat-embedding-probe.py
# inspect-only, writes nothing, sends no alert:
python3 ~/.openclaw/skills/32-command-center-setup/scripts/heartbeat-embedding-probe.py --dry-run
```

**Wire it as an OpenClaw cron (every 6 hours).** Uses the docs-canonical
positional form (`openclaw cron create "<schedule>" "<prompt>" --name N --agent A
--session main`) verified against the installer's cron helper:

```bash
openclaw cron create "0 */6 * * *" \
  "Run the Skill 32 Fleet Embedding Health Probe: execute 'python3 ~/.openclaw/skills/32-command-center-setup/scripts/heartbeat-embedding-probe.py'. If it reports degraded or dark, follow its remediation. Operator-only — do NOT message the client." \
  --name fleet-embedding-probe --agent main --session main --light-context
```

Idempotency: before creating, check it is not already registered —
`openclaw cron list | grep -qi fleet-embedding-probe` — and skip if present.

**If the probe reports `dark`:** the SOP embeddings or persona index are not
built/stale. Re-running the SOP library ingest (`ingest-sop-library.sh`) does
NOT fix a dark `sop_embeddings` reading by itself — it only loads SOP
*content* into the `sops` table and never touches embeddings (P4-03
root-cause). The ACTUAL fix depends on which corpus is dark:

- **`sop_embeddings` empty/stale** (the shared library): re-run
  `ingest-sop-library.sh` — as of P4-03 it now calls
  `shared-utils/sop-embed-once/provision_sop_embeddings.py` automatically at
  the end of the content ingest, which imports the operator-published
  shipped asset (zero client-key embed calls). If that step warned
  "no SOP-embeddings asset has been published yet," escalate to the operator
  to run `shared-utils/sop-embed-once/build-and-publish.sh` — do NOT attempt
  to embed the shared library with a client key.
- **Client-specific SOPs uncovered by the shared asset** (e.g. rows from
  `sop_proposals`): run `npm run db:embed:sops`
  (`scripts/backfill-sop-embeddings.ts`) — it is delta-only and will not
  re-embed anything already covered by the shipped asset.
- **Persona index (`gemini-index.sqlite`) empty/stale**: re-run persona index
  provisioning (`shared-utils/provision-persona-index.sh` /
  `install.sh` Step 6b / `update-skills.sh` Step U6b) — this is the
  DIFFERENT (System 1) corpus and is unrelated to `sop_embeddings`.

Then re-run the probe to confirm it returns to `healthy`.

---

## Command Center Activation / liveness

(See `CORE_UPDATES.md` → "HEARTBEAT.md Addition" for the twice-daily activation
check and the `pm2 list | grep blackceo-command-center` liveness probe. The
dashboard runs on **:4000**.)
