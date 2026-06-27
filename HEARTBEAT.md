# HEARTBEAT.md

## 🔴 WEEKLY UPDATE CHECK — Every Sunday at 3:00 AM

**When the gateway restarts and it is a Sunday between 3:00 AM and 6:00 AM, check for updates:**

1. Check if the flag file exists: `~/.openclaw/skills/.update-pending`
2. If the flag file exists:
   a. Read the notification at `/tmp/oc-update-notification.md`
   b. Clone the latest repo to `/tmp/`:
      - Mac: `git clone https://github.com/trevorotts1/openclaw-onboarding.git /tmp/oc-review`
      - VPS: `git clone https://github.com/trevorotts1/openclaw-onboarding.git /tmp/oc-review`
   c. Read `/tmp/oc-review/CHANGELOG.md` — find your installed version at `~/.openclaw/skills/.onboarding-version`
   d. Read every changelog entry between your version and the latest
   e. Make a plain-English summary of what changed
   f. Send a Telegram message to the client immediately (within 10 seconds of seeing the flag):
      ```
      Hey [Client Name], I found a system update (v[current] to v[latest]). Here is what changed:
      - [Change 1 in plain English]
      - [Change 2 in plain English]
      - [Change 3 in plain English]
      
      Want me to apply this update? Reply YES or NO.
      ```
   g. Wait for the client to reply YES or NO
   h. If YES: Follow `/tmp/oc-review/UPDATE-PLAYBOOK.md` step by step
   i. If NO: Skip the update, remove the flag, clean up /tmp
   j. **ALSO check for OpenClaw model updates** (see below)
3. If the flag file does NOT exist:
   - Still check for OpenClaw model updates (see below)
   - If nothing else needs attention, reply HEARTBEAT_OK

---

## 🔴 OPENCLAW MODEL CHECK — Run Every Sunday (and on updates)

After any update (or during Sunday check), always verify the client has the latest models:

### Step 1: Research Current Models
1. Check the current OpenClaw version: `openclaw --version`
2. Go to https://docs.openclaw.ai — check the models documentation for THIS version
3. Go to https://github.com/openclaw/openclaw — check the README and recent commits for new model support
4. Look for: new model additions, deprecated/removed models, changed model ID formats, changed config structure
5. If OpenClaw changed the config structure, validate the new structure before making changes

### Step 2: Compare Against Client's Config
1. Read the client's `~/.openclaw/openclaw.json` → `agents.defaults.models`
2. Compare the client's model list against what OpenClaw currently supports
3. Identify:
   - **NEW models** available that the client does not have
   - **DEPRECATED models** the client has that OpenClaw no longer recommends
   - **Changed model IDs** (e.g., format changes, prefix changes)

### Step 3: Apply Safe Updates
- **REMOVE Perplexity models** — OpenClaw no longer supports Perplexity as a model. Any entry matching `openrouter/perplexity/*` must be deleted from the model allow list. This is a required cleanup, not an optional removal.
- **SYNC all models** — Read the client's full openclaw.json and find ALL model references. Any model the client uses anywhere in their config must also be in `agents.defaults.models`. Sub-agents cannot use models that are not on this list.
- **ADD new models** to the client's allow list if they are stable and recommended by OpenClaw docs
- **DO NOT REMOVE** any working model (except Perplexity) without explicit client approval
- **FLAG deprecated models** with a Telegram message to the client explaining what changed
- **If a model ID format changed** (e.g., `openrouter/` prefix added), update it ONLY if the docs confirm the new format is required
- **Always back up openclaw.json** before making any model changes (follow Skill 02 backup protocol)
- **After changing models**, send a Telegram summary:
  ```
  Model update applied:
  - Added: [model name] (reason: new stable release)
  - Flagged: [model name] (reason: deprecated in latest OpenClaw — needs review)
  - Your existing models are untouched.
  ```

### Critical Rules
- NEVER remove a model that is currently working
- NEVER add experimental/alpha models without client approval
- ALWAYS verify model IDs from the official OpenClaw documentation
- ALWAYS back up before changing openclaw.json

**After applying any update, run the full QC loop (see below).**

---

## 🔴 POST-UPDATE QC LOOP — Run After Every Update

After any skill install or update (manual or Sunday auto-update), run this QC loop:

### Step 1: QC ALL Updated Skills
For each skill that was installed or updated:
1. Read the skill's `QC.md` file
2. Run every check listed in QC.md (terminal commands, file existence, knowledge questions)
3. Document PASS or FAIL for each check
4. If ANY check fails, go to Step 2

### Step 2: Fix Failed Skills
If any skill has a FAILED QC check:
1. Spawn a sub-agent to fix the specific failure
2. Tell the sub-agent: which skill, which check failed, what the error was, what files to fix
3. After the sub-agent completes, go to Step 1 and re-run QC on the fixed skill

### Step 3: Maximum 5 Retries
- Re-run the QC loop a maximum of 5 times total
- If a skill still fails after 5 attempts, report it to the client:
  ```
  ⚠️ Skill [name] could not pass QC after 5 attempts. 
  Issue: [description of what keeps failing]
  This needs manual attention.
  ```
- Do NOT silently skip failed skills. Always report them.

### Step 4: Final Report
After all skills pass QC (or after 5 retries), send the client a final summary:
```
✅ Update complete (v[old] → v[new])

Skills updated:
- [Skill 1]: PASS
- [Skill 2]: PASS
- [Skill 3]: PASS

Skills that needed fixes during QC:
- [Skill X]: PASS (fixed on attempt 2)

Skills that could not be fixed:
- [Skill Y]: BLOCKED (reason)

A gateway restart is recommended for changes to take effect.
```

---

## FLEET EMBEDDING CANARY — Every 6 Hours

The embedding canary probe checks that the Skill 32 Command Center's semantic
search layer is alive on every box that has a Command Center installed. It
runs as a lightweight database read (no API calls, no model inference) and
writes one row into the `system_status` table in `mission-control.db`.

Script: `32-command-center-setup/scripts/heartbeat-canary-probe.py`

### What the probe checks

| Check | Table / source | Dark signal |
|---|---|---|
| SOP embeddings count | `sop_embeddings` in mission-control.db | table missing OR count = 0 |
| Persona-index count | `persona_index` / `personas` / side-car `persona-index.db` | count = 0 or table missing |
| Embedding coverage | `sop_embeddings_count / sops_total` | coverage < 40% |
| Embedding staleness | `MAX(updated_at)` in sop_embeddings | age > 30 days = dark; age > 7 days = degraded |
| Semantic vs keyword recall | canary phrase "onboard" against both indexes | recall_ratio < 0.5 = degraded |

### Status levels

- **healthy** — all checks pass. Row written to system_status. No alert sent.
- **degraded** — a soft threshold crossed: coverage 40–79%, or embeddings 7–30 days old, or persona index absent, or recall_ratio < 0.5. Logged to system_status. No Rescue Rangers ping.
- **dark** — a hard threshold crossed: embeddings empty or missing, coverage < 40%, age > 30 days, or persona index empty. **Rescue Rangers channel is pinged immediately.**

### How to trigger it manually

On a Mac client box:
```bash
python3 ~/.openclaw/skills/32-command-center-setup/scripts/heartbeat-canary-probe.py
```

Dry-run (no DB write, no Rescue Rangers alert):
```bash
python3 ~/.openclaw/skills/32-command-center-setup/scripts/heartbeat-canary-probe.py --dry-run
```

On a Hostinger VPS (inside the container):
```bash
docker exec <container> python3 /data/.openclaw/skills/32-command-center-setup/scripts/heartbeat-canary-probe.py
```

### Reading the system_status table

```bash
# Most recent probe results
sqlite3 /data/projects/command-center/mission-control.db \
  "SELECT checked_at, status, sop_embeddings_count, persona_index_count, \
          embedding_coverage, embedding_age_days, dark_reason \
   FROM system_status ORDER BY checked_at DESC LIMIT 5;"
```

Expected healthy output:
```
2026-06-27T12:00:00+00:00|healthy|2448|142|0.96|1.3|
```

Full schema (written by the probe on first run — idempotent):
```sql
CREATE TABLE IF NOT EXISTS system_status (
  id                     TEXT PRIMARY KEY,
  probe_type             TEXT    NOT NULL DEFAULT 'embedding-canary',
  box_id                 TEXT,
  checked_at             TEXT    NOT NULL,
  sops_total             INTEGER DEFAULT -1,
  sop_embeddings_count   INTEGER DEFAULT -1,
  persona_index_count    INTEGER DEFAULT -1,
  embedding_coverage     REAL    DEFAULT -1.0,
  semantic_probe_query   TEXT,
  semantic_probe_hits    INTEGER DEFAULT 0,
  keyword_probe_hits     INTEGER DEFAULT 0,
  semantic_recall_ratio  REAL    DEFAULT 0.0,
  embedding_age_days     REAL,
  status                 TEXT    NOT NULL DEFAULT 'unknown',
  dark_reason            TEXT,
  alert_sent             INTEGER DEFAULT 0,
  alert_msg              TEXT,
  created_at             TEXT    DEFAULT (datetime('now'))
);
```

### Rescue Rangers alert format

When a box goes dark the probe calls:
```bash
openclaw message send --channel telegram \
  -t "${RESCUE_RANGERS_HELP_CHAT_ID}" \
  -m "[heartbeat-canary / <hostname>] EMBEDDING DARK
Reason: <reason>
Time: <ISO timestamp>
Action: SSH in; run ingest-sop-library.sh <client-slug> <version>"
```

The `RESCUE_RANGERS_HELP_CHAT_ID` env var must be set on every box that has
a Command Center installed. Use `~/clawd/fleet-heartbeat/scripts/propagate-rescue-chat-id.sh`
to push it fleet-wide.

### How to wire the canary as an OpenClaw cron

Run this once per box after Skill 32 is installed:

```bash
openclaw cron create \
  --name heartbeat-embedding-canary \
  --schedule "0 */6 * * *" \
  --tz "America/New_York" \
  --agent main \
  --session isolated \
  --model "ollama/deepseek-v4-flash:cloud" \
  --tools exec \
  --message "Run the fleet embedding canary probe: exec python3 ~/.openclaw/skills/32-command-center-setup/scripts/heartbeat-canary-probe.py && echo CANARY_OK || echo CANARY_FAIL"
```

Verify the cron was created:
```bash
openclaw cron list | grep heartbeat-embedding-canary
```

Fire it immediately to confirm it works end-to-end:
```bash
openclaw cron run <cron-id-from-list>
```

Expected output in the cron log:
```
[heartbeat-canary] v1.0.0  box=<hostname>  db=/data/projects/command-center/mission-control.db
  sops_total:           2555
  sop_embeddings_count: 2448
  persona_index_count:  142
  embedding_coverage:   95.81%
  embedding_age_days:   1.3
  keyword_hits:         38
  semantic_hits:        38
  semantic_recall_ratio:1.00
  status:               healthy
  wrote system_status id=<hex>
CANARY_OK
```

### Recovery when a box is dark

1. SSH into the box (VPS) or open terminal (Mac).
2. Confirm the problem:
   ```bash
   sqlite3 /data/projects/command-center/mission-control.db \
     "SELECT status, dark_reason FROM system_status ORDER BY checked_at DESC LIMIT 1;"
   ```
3. If `sop_embeddings` is missing or empty, re-run the SOP ingester:
   ```bash
   bash ~/.openclaw/skills/32-command-center-setup/scripts/ingest-sop-library.sh \
       <client-slug> <latest-version>
   ```
4. If `persona_index` is empty, rebuild the persona index:
   ```bash
   python3 ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/gemini-search.py \
       --rebuild-index
   ```
5. Re-run the canary to confirm recovery (exit 0 = healthy):
   ```bash
   python3 ~/.openclaw/skills/32-command-center-setup/scripts/heartbeat-canary-probe.py
   ```
6. Reply to the Rescue Rangers alert with the resolution summary.

### Anti-patterns

- Do NOT re-embed the persona corpus per-department (memory-bloat guard — see INSTALL.md Phase 4.2).
- Do NOT run the canary with `--dry-run` on the live heartbeat cron — the cron must write to system_status or the dashboard has no data.
- Do NOT ignore `degraded` status indefinitely — degraded converts to dark when embeddings exceed 30 days old.
- Do NOT manually insert into `system_status` to fake health — the probe is the only writer.
