# SOP: Adding a Capability After Build

**Version:** 1.0.0
**Applies to:** All client boxes (Mac and VPS)
**Owner department:** Project Architecture Office (PAO) / General Task (for one-off additions)
**Trigger:** New skill/department available in onboarding repo; owner wants new capability on running box

---

## When This SOP Applies

- A client box has been through the full Skill 1–43 install
- A new skill or department has been released (Sunday cron detected version drift)
- An owner asks their agent to "add [capability X]" to the running Command Center
- The `general-task` or `project-architecture-office` departments are available in the repo but not yet on the client's box

**Does NOT apply to:**
- Adding new GoHighLevel workflows (use Skill 38/41 SOPs)
- Changing the client's AI persona or interview data (requires full re-interview)
- Upgrading OpenClaw itself (use OpenClaw upgrade procedure)

---

## Pre-Conditions (verify ALL before starting)

| # | Check | How |
|---|-------|-----|
| 1 | Box is ONLINE | `openclaw gateway status` returns `running` |
| 2 | You have SSH / terminal access | Test with a simple `echo $HOSTNAME` |
| 3 | OpenClaw version is up to date | `openclaw --version` ≥ installed skill's minimum |
| 4 | Repo clone is fresh | `git remote get-url origin` matches intended URL |
| 5 | `OLLAMA_API_KEY` is set | `echo $OLLAMA_API_KEY` is non-empty |
| 6 | No other agent is mid-build on this box | `openclaw subagents list` returns empty or non-critical agents |

---

## Steps (DMAIC)

### Define (D) — Identify the capability

1. Parse the owner's request to identify the specific skill/department slug
   - E.g. "add project tracking" → `project-architecture-office`
   - E.g. "add a catch-all for misc tasks" → `general-task`
2. Confirm the slug exists in `_index.json`:
   ```bash
   python3 -c "import json; idx=json.load(open('23-ai-workforce-blueprint/templates/role-library/_index.json')); print(list(idx['departments'].keys()))"
   ```
3. If slug not in index → this capability doesn't exist yet; escalate to owner (do NOT invent it)

### Measure (M) — Check current state

4. Check if already installed on the box:
   ```bash
   openclaw config get agents.list 2>/dev/null | python3 -c "import json,sys; agents=json.load(sys.stdin); [print(a.get('id','')) for a in agents]" | grep <slug>
   ```
5. Check `last-sync.json`:
   ```bash
   cat ~/.openclaw/extension-sync/last-sync.json 2>/dev/null | python3 -m json.tool
   ```
6. If already installed → verify health and report to owner (do NOT re-add)

### Analyze (A) — Dry-run the extension

7. Run `sync-extensions.sh` in dry-run mode:
   ```bash
   bash 32-command-center-setup/scripts/sync-extensions.sh --dry-run --verbose --dept <slug>
   ```
8. Review output for any warnings before proceeding

### Improve (I) — Execute the extension

9. Run the live sync:
   ```bash
   bash 32-command-center-setup/scripts/sync-extensions.sh --dept <slug>
   ```
10. Verify registration succeeded:
    ```bash
    cat ~/.openclaw/openclaw.json | python3 -c "import json,sys; cfg=json.load(sys.stdin); reg=cfg.get('extension_registry',{}).get('departments',[]); [print(r['dept_slug']) for r in reg]"
    ```
11. Confirm `last-sync.json` was updated:
    ```bash
    cat ~/.openclaw/extension-sync/last-sync.json | python3 -m json.tool | grep synced_at
    ```

### Control (C) — Validate and hand off

12. **QC GATE (≥8.5):** Run system integrity check:
    ```bash
    bash scripts/qc-system-integrity.sh 2>&1 | tail -20
    ```
    Must pass N30 (Ollama URL) and N31 (model object) checks.
13. Restart gateway (orchestrator only — N7):
    ```bash
    openclaw gateway restart
    ```
14. Send Telegram confirmation to owner:
    > "I've added [capability X] to your Command Center. The [dept-name] department is now live. You can reach it by messaging [topic/channel]. Let me know if you'd like to test it with a sample task."

---

## Failure Modes

| Failure | Recovery |
|---------|----------|
| `sync-extensions.sh` exits non-zero | Check log in `~/.openclaw/extension-sync/sync-*.log`; restore backup if needed (see EXTENSIBILITY.md Rollback section) |
| Dept slug not in naming map | Ensure repo is on latest main; if slug truly doesn't exist, inform owner capability is not yet available |
| Gateway restart fails (LaunchAgent err 125 on Mac) | Use `openclaw gateway run` instead; set up watchdog cron (see Mac client gateway SOP) |
| QC gate < 8.5 | Do NOT deliver to owner; fix the failing check, then re-run QC |
| Owner asks about a slug that conflicts with existing dept | Do NOT add a duplicate; explain that the existing dept handles that work |

---

## Hand-To

After completion, hand off to:
- **Owner (Telegram):** confirmation message (Step 14)
- **Head of General Task / Chief Project Architect:** update project tracker if this was part of a larger build initiative
- **SOP Writer:** if a pattern is discovered (e.g. adding a capability always requires an extra env key), write a new SOP addendum

---

## SOP Author

Project Architecture Office — SOP Writer role
QC reviewed per Rule 6 (different model from writer)
First version: v11.1.0 (2026-06-09)
