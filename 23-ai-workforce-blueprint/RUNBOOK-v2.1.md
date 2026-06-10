# OpenClaw v2.1 — Operational Runbook

**For operators upgrading from v10.3.x or v10.4.x to v10.5.0.**

This runbook is for the human who clones one of the onboarding repos and needs to know which scripts to run when. The interview-facing flow stays the same (clients run Skill 23 Option A as before). This runbook is about the v2.1 plumbing.

---

## 1. After `git pull` on a fresh install

```bash
# Mac
cd ~/Downloads/openclaw-master-files
git pull
bash install.sh

# VPS (inside container)
cd /data/.openclaw/master-files
git pull
bash install.sh
```

The install script copies skills, sets up workspaces, and configures the OpenClaw daemon. Nothing new for v2.1.

## 2. After `git pull` on an EXISTING install (upgrading)

Run the v2.1 migrations once to upgrade existing companies, agents, and the Gemini index:

```bash
bash 23-ai-workforce-blueprint/scripts/run-v2.1-migrations.sh
```

What this does:
1. Verifies platform detection
2. Adds the Persona Governance Override clause to every existing `SOUL.md` and `IDENTITY.md` (idempotent)
3. Re-indexes every persona blueprint at section level (replaces character chunks)
4. Creates role-level workspace folders for every existing department

Safe to re-run. Each step skips work already done.

## 3. Verify the install

```bash
bash 23-ai-workforce-blueprint/scripts/verify-v2.1-installation.sh
```

Exits 0 if everything is green. Exits non-zero with a list of failures if not.

## 4. Day-to-day scripts

### When the AI needs to know which industry vertical a client is in
```bash
python3 shared-utils/industry-detector.py --text "$(cat path/to/pre-interview-research.md)"
```
Returns a JSON object with `industry_slug`, `confidence`, `needs_confirmation`, and matched signal keywords.

### When a task is dispatched and we need a persona (v2.1-aware)
```bash
python3 23-ai-workforce-blueprint/scripts/persona-selector-v2.py \
  --task "write a follow-up email to the prospect" \
  --department sales
```
Returns JSON with `persona_id`, `score`, `interaction_mode` (leadership/coaching/hybrid), `task_category`, and a 5-layer breakdown. Checks stickiness first — if `persona_assignment` table has a row for (sales, email-outreach) with score ≥0.5, returns it without re-scoring.

### When a category needs to be inferred from a task description
```bash
python3 23-ai-workforce-blueprint/scripts/infer-task-category.py "write a follow-up email"
# -> email-outreach
```
14 categories supported. Used by stickiness and adaptive weights.

### When you want to know the active weight matrix for a task
```bash
python3 shared-utils/adaptive_weights.py --task "help me decide on pricing" --mode coaching
# -> { "weights": { "owner_values": 0.55, ... } }
```

### When the owner abandons an in-progress interview
The cron should be wired (see Section 7 below). To run manually:
```bash
python3 shared-utils/nudge-incomplete-interviews.py --dry-run    # preview
python3 shared-utils/nudge-incomplete-interviews.py              # actually send
```

### When a critical task moves to "done" and DA should be triggered
```bash
# Write task context to a temp file
cat > /tmp/da-context.json <<EOF
{
  "task_id": "...",
  "title": "Launch the new pricing page",
  "department": "marketing",
  "priority": "critical",
  "persona": "hormozi-100m-offers"
}
EOF

python3 shared-utils/devils-advocate.py --trigger critical_task --context-json /tmp/da-context.json
```
Returns one specific, data-cited challenge. Severity + confidence.

### When a behavioral interview completes and USER.md needs updating
```bash
# answers.json should have keys B-1 through B-5
python3 shared-utils/extract-behavioral-patterns.py --answers-json /path/to/answers.json
```
Writes the structured profile to `USER.md` under `## Behavioral Identity Profile`. Source answers preserved verbatim under `## Behavioral Identity Source Answers`.

## 5. The hand-touch list (manual integrations recommended)

These small edits unlock the full v2.1 experience but weren't shipped to avoid risky inline edits to 90+ KB files. Each is a 3-10 line change.

### A. `build-workforce.py` — wire `create-role-workspaces`

After `create_department_workspace()` returns the dept path (around line 1107), add:

```python
# v2.1: Create role-level workspaces alongside the dept workspace
try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).parent))
    from create_role_workspaces import build_all_roles_for_dept as _build_roles
    role_list = [
        {"name": f"Director of {dept_data['name']}", "is_ceo": False},
        {"name": "QC Specialist", "type": "full-time-permanent"},
        {"name": "Deep Research Specialist", "type": "on-call"},
    ]
    for s in specialists:
        role_list.append({"name": s["name"], "type": s["type"]})
    _build_roles(dept_path, dept_id, role_list, workspace_root)
except Exception as _e:
    print(f"WARN: role-level workspace creation failed for {dept_id}: {_e}")
```

If you skip this edit: just run `post-build-role-workspaces.py` after every `build-workforce.py` run. Same result.

### B. `persona-selector-v2.py` — the canonical selector (v11.4.0+)

`persona-selector-v2.py` is THE canonical selector. `select-persona-for-task.py`
is now a deprecated shim that delegates to v2. No change needed in
`src/lib/persona-selector.ts` — it already calls v2.

If you have any custom scripts, update them:

```typescript
// Correct (v11.4.0+):
scriptPath = path.join(openclaw_root, "skills", "23-ai-workforce-blueprint", "scripts", "persona-selector-v2.py");

// Deprecated (still works via shim but logs a warning to stderr):
scriptPath = path.join(openclaw_root, "skills", "23-ai-workforce-blueprint", "scripts", "select-persona-for-task.py");
```

### C. `install.sh` — ensure `shared-utils/` gets copied

The install script copies `skills/` to `~/.openclaw/skills/`. Verify `shared-utils/` is included. If not, add this near the skills-copy block:

```bash
mkdir -p "$OPENCLAW_ROOT/shared-utils"
cp -R "$REPO_ROOT/shared-utils/." "$OPENCLAW_ROOT/shared-utils/"
chmod +x "$OPENCLAW_ROOT/shared-utils/"*.sh "$OPENCLAW_ROOT/shared-utils/"*.py 2>/dev/null || true
```

## 6. Persona stickiness — how it actually flows

A first task arrives in Sales:
1. `persona-selector-v2.py` runs, infers `task_category = email-outreach`
2. No row in `persona_assignment` for (sales, email-outreach) → run full scoring
3. Top persona scores 0.847 → returned for execution
4. Command Center stores this in `persona_assignment` table
5. Stores task on Kanban with `persona_id`, `persona_name`, etc.

A second similar task arrives in Sales:
1. `persona-selector-v2.py` checks `persona_assignment` table
2. Finds the row from task 1 → returns sticky assignment without re-scoring
3. Output has `"stickiness": true` in `breakdown`

After 10 sticky uses, an even-better persona scores 0.892:
1. Score differential = 0.892 - 0.847 = 0.045
2. < 0.15 threshold → keep sticky persona, log differential

After 10 sticky uses, a much-better persona scores 0.95:
1. Differential = 0.103 → still < 0.15 → keep
2. Eventually if differential ≥ 0.15 → switch, increment `switch_count`

## 7. Cron entries (recommended)

```cron
# Telegram nudges for incomplete interviews — every 6 hours
0 */6 * * * /usr/bin/python3 /path/to/shared-utils/nudge-incomplete-interviews.py

# Weekly persona effectiveness report — Mondays at 08:00
0 8 * * MON /usr/bin/python3 /path/to/shared-utils/persona-weekly-report.py

# Memory hygiene compaction — daily at 03:00 (handled by Skill 31 if installed)
```

## 8. When something breaks

| Symptom | Where to look |
|---|---|
| `detect_platform` says "Cannot detect OpenClaw platform" | The expected directories don't exist. Run `install.sh` first. |
| `migrate-deferral-clauses` reports 0 scanned | Company root path empty. Check `OPENCLAW_COMPANY_ROOT` env. |
| `persona-selector-v2` returns NO_PERSONAS_AVAILABLE | No personas indexed. Run Skill 22 on at least one book. |
| `gemini-section-indexer` falls back to deterministic embeddings | `GOOGLE_API_KEY` not set. Real Gemini embeddings need that env var. |
| Command Center: migrations 016-021 didn't run | Restart the Node process. Migrations run on startup. |
| Telegram nudges don't send | `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` env vars missing. |

## 9. Rollback

To roll back to v10.4.x:
```bash
git checkout v10.4.1 -- shared-utils/ 23-ai-workforce-blueprint/ install.sh
```

The Wave 3 additions are pure ADDS — they don't modify existing v10.4.x files. Just removing the new files restores prior behavior.

For the Command Center, migrations 016-021 are append-only schema changes. Rolling back the code without rolling back the DB is safe; new columns are simply ignored.

---

**Maintainer notes:**
- Every script in this runbook has `--dry-run` or equivalent for safe testing
- Every script logs to stdout/stderr — pipe to a log file in production
- All Python is 3.8+ compatible
- No external dependencies beyond what's already in OpenClaw's `requirements.txt`
