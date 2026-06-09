# Command Center Extensibility

## Adding a New Capability After Build

This document explains how to add new departments, skills, or agents to a client's running Command Center **without** rebuilding from scratch.

---

## When to Use This

Use this path when:
- A new skill has been released in the onboarding repo (Sunday update detected it)
- You're manually adding a vertical that wasn't included in the initial Skill 23 build
- The `general-task` or `project-architecture-office` departments have been added to the floor but not yet provisioned on an older box

Do **NOT** use this path for:
- Changing the client's `SOUL.md`, `IDENTITY.md`, or interview answers (full re-interview required)
- Upgrading OpenClaw itself (see OpenClaw upgrade procedure)

---

## Automatic Detection (Sunday cron)

The Sunday 3am cron (`update-skills.sh` → `check-updates.sh`) now also triggers `sync-extensions.sh` after detecting version drift. This handles:

1. Version bump detected → pull latest repo
2. New departments in `_index.json` vs `last-sync.json` → detected by `detect-extensions.py`
3. Each new dept → registered via `register-routing-dept.py` + workspace materialized
4. Owner notified via Telegram

No manual action needed in the normal case.

---

## Manual Extension

Run this on the target box:

```bash
# From the installed repo root (e.g., ~/Downloads/openclaw-onboarding/)
bash 32-command-center-setup/scripts/sync-extensions.sh --verbose
```

To force-add a specific department (e.g., if it was skipped):

```bash
bash 32-command-center-setup/scripts/sync-extensions.sh --dept project-architecture-office
```

Dry-run first:

```bash
bash 32-command-center-setup/scripts/sync-extensions.sh --dry-run --verbose
```

---

## Script Reference

| Script | Purpose |
|--------|---------|
| `scripts/sync-extensions.sh` | Master orchestrator — detect → routing registration → materialize → **CC workspaces row + QC specialist** → notify |
| `scripts/detect-extensions.py` | Diffs current `_index.json` against `last-sync.json`, emits NEW: lines |
| `scripts/register-routing-dept.py` | Writes dept into `extension_registry` in `openclaw.json` (idempotent) |
| `scripts/materialize-dept-agents.sh` | Creates agent workspace dirs for a new dept (idempotent, pre-existing) |
| `scripts/add-department.sh` | **Full manual-path dept add:** CC workspaces row + head agent + QC specialist + routing registration + role-library entry. Use when adding a dept NOT in `_index.json`, or for post-build manual additions. Idempotent. |
| `scripts/seed-workspaces.py` | Seeds ALL departments from `departments.json` into the CC DB. Run during initial install; also use to re-seed from scratch if the DB is wiped. |
| `scripts/ingest-sop-library.py` | Syncs SOP markdown files into the CC database for search and routing. Run after adding any new SOP. |
| `23-ai-workforce-blueprint/scripts/generate-governing-personas.sh` | Regenerates `governing-personas.md` for all departments from the current persona index. Run after adding a new persona or updating persona tags. |
| `23-ai-workforce-blueprint/scripts/add-role.sh` | **Post-build single-role add:** creates one specialist role under an existing dept — role workspace + agent row + persona governance. No full rebuild needed. |

---

## Sync State File

After each successful sync, `sync-extensions.sh` writes:

```
~/.openclaw/extension-sync/last-sync.json   (Mac)
/data/.openclaw/extension-sync/last-sync.json   (VPS)
```

Format:
```json
{
  "synced_at": "2026-06-09T21:00:00Z",
  "departments": ["app-development", "audio", ..., "general-task", "project-architecture-office"],
  "total_roles": 244,
  "version": "11.1.0"
}
```

Re-running `sync-extensions.sh` with no new departments is a no-op (exits 0 immediately after updating the timestamp).

---

## Model Rules for New Departments

Any new department registered via this path must follow:

- **N30:** `OLLAMA_BASE_URL` MUST be `https://ollama.com` for `:cloud` models — NEVER `127.0.0.1`
- **N31:** Agent model field MUST be an object `{primary, fallbacks:[...]}` — never a bare string

Both rules are enforced by `register-routing-dept.py` (the new entry always uses the object form) and validated by `scripts/qc-system-integrity.sh`.

---

## Rollback

If a registration causes issues:

1. Restore the backup: `cp ~/.openclaw/openclaw.json.bak-reg-<ts> ~/.openclaw/openclaw.json`
2. Restart the gateway: `openclaw gateway restart` (orchestrator only — N7)
3. Re-run `sync-extensions.sh --dry-run` to verify the diff

The registration is additive only (`extension_registry.departments[]` append). The core `agents.list[]` is not modified by `register-routing-dept.py` — it is modified only by `build-workforce.py` during a full Skill 23 rebuild.

---

## SOP Cross-Reference

See also: `../universal-sops/adding-capability-after-build.md` (v2.0.0) for the full step-by-step SOP covering all 6 events: new book/video/persona, new department, new role/specialist, new SOP, new skill, and persona governance updates. Includes CC verification gates (SELECT from workspaces, loadDepartments, sample route) — not just openclaw.json checks.
