# SOP Mirror -- Proactive Fix Guardrail (Cross-Cutting)

**SOP ID:** `SOP-MAINT-PROACTIVE-FIX-GUARDRAIL`
**Source:** openclaw-maintenance (cross-cutting; co-owned by R1, R2, R3, R4)
**Authority:** This SOP is authoritative for all roles in openclaw-maintenance. Role files embed it by reference. This file is the canonical copy.
**Type:** Cross-cutting guardrail SOP -- always-on; applied BEFORE any fix is executed
**Purpose:** The Tier-1/2/3 boundary specialized to maintenance fixes. Ensures no maintenance specialist deletes a critical feature, breaks a config, or takes an irreversible action without proper authorization.

---

## 9. Standard Operating Procedures

### SOP 9.1 -- Pre-Fix Guardrail Checklist (Run Before EVERY Fix)

**When to run:** Before applying ANY change -- config edit, cron disable/delete, model swap, version upgrade, gateway action. No exceptions.

**Steps (complete all in order):**

1. **Classify the fix tier:**
   - **Tier 1 (auto-apply):** Purely mechanical; no features affected; easily reversible; evidence is conclusive (e.g., commenting out a verified-duplicate cron line; fixing a clearly-wrong API state string).
   - **Tier 2 (apply + notify):** Changes behavior an SOP documents; touches config or cron entries that MIGHT have a feature purpose; model swap with doc-verified replacement.
   - **Tier 3 (propose + hold):** Touches operator-explicit config; feature-bearing crons; by-design free-tier primaries; master SOP; model manifest; SOUL.md / USER.md / AGENTS.md; anything constitutional. Do NOT apply -- draft the proposal and escalate to Rescue Rangers (SOP-MAINT-RESCUE-RANGERS-ESCALATION).

2. **Disable-not-delete rule (crons and features):**
   - NEVER delete a cron entry -- comment it out (`#`) in the crontab.
   - NEVER delete a feature cron unless it has been PROVEN an orphan or duplicate with no active purpose AND operator has approved.
   - NEVER delete a config key unless you have a backup and operator approval.
   - Repoint-not-remove: if a cron is feature-bearing but misfired, repoint its target rather than removing it.

3. **Backup rule (config edits):**
   - Before ANY `openclaw.json` deep-merge or edit: copy the file to `working/maintenance/backups/openclaw.json.bak-YYYYMMDD-HHMMSS`.
   - Before ANY `docker-compose.yml` edit: copy to `working/maintenance/backups/docker-compose.yml.bak-YYYYMMDD-HHMMSS`.
   - Backup MUST exist before the edit proceeds. No exceptions.

4. **Validate-after rule:**
   - After EVERY `openclaw.json` edit: run `openclaw config validate`.
   - If validation FAILS: restore the backup IMMEDIATELY. Do NOT attempt a second edit without understanding why the first failed.
   - After any gateway restart: run `openclaw gateway status`. If DOWN: follow SOP-MAINT-UPTIME (S4).

5. **Mac gateway rule:**
   - On Mac: NEVER run `openclaw gateway restart` over SSH. This sends the command to launchd which returns err 125 and takes the box DOWN.
   - Safe Mac recovery: `launchctl kickstart` or detached `openclaw gateway run`.

6. **Notification rule:**
   - Every Tier 2 or Tier 3 action generates exactly ONE operator notification (not one per affected item).
   - Notifications go via `openclaw message send --channel telegram`. Never direct to Telegram API.

**Outputs:** Written pre-fix record (tier classification + backup path) in the relevant working/ ledger. **Hand to:** Apply the fix (if Tier 1 or 2); Rescue Rangers escalation (if Tier 3 or ambiguous). **Failure mode:** Cannot classify the fix tier: default to Tier 3 (escalate). When in doubt, propose and hold.

---

### SOP 9.2 -- Feature-Bearing Cron Decision Tree

**When to run:** Whenever a cron entry is a furnace candidate but may be feature-bearing.

**Steps:**
1. Look up the cron's target command. Does it match any of these KNOWN maintenance crons (safe to disable if misfiring)?
   - Heartbeat poll cron (fires `openclaw run` with a heartbeat task) -- known furnace if interval < 30 min.
   - Memory dreaming plugin cron -- known furnace if interval < 30 min.
   - Broken-delivery retry cron -- known furnace if retrying same delivery id.
   - Duplicate of another cron entry (exact same command, two entries).
2. Does the cron target match any of these KNOWN feature crons (NEVER auto-disable)?
   - Skill 44 CAF workflow build cron (per memory `skill44-caf-workflow-build.md`).
   - GHL MCP autostart / health cron (per memory `ghl-mcp-autostart-session-kill-loop.md` -- this is a KNOWN loop but the FIX is host-level watchdog + notify-on-change, NOT cron deletion).
   - ZHC closeout cron.
   - Any cron referencing a business workflow by name.
3. If KNOWN maintenance (step 1): classify as Tier 1 or 2 disable (comment out).
4. If KNOWN feature (step 2): mark as `needs_owner_decision`; escalate to Rescue Rangers (S5). Do NOT touch it.
5. If UNKNOWN: mark as `needs_owner_decision`; escalate. Default is feature-bearing until proven otherwise.

**Outputs:** Decision record in furnace-watch ledger. **Hand to:** Pre-fix checklist (SOP 9.1) after classification. **Failure mode:** Cannot determine cron purpose after checking docs + ledger: escalate to Rescue Rangers.

---

### SOP 9.3 -- Config Edit Safety Protocol (Deep-Merge vs Direct Edit)

**When to run:** Before any `openclaw.json` modification.

**Steps:**
1. Determine the edit method:
   - **`openclaw config set <key> <value>`:** only for TOP-LEVEL flat keys. Per memory `openclaw-memory-activation-pattern.md`: nested keys (e.g., `agents.defaults.memorySearch.provider`) FAIL with `Invalid input` on 2026.5.20+.
   - **JSON deep-merge:** required for nested keys. Direct edit of the JSON file using a backup-first workflow.
2. Backup `openclaw.json` (SOP 9.1 step 3 rule).
3. Apply the edit.
4. Run `openclaw config validate`. On failure: restore backup immediately.
5. Run `openclaw gateway status`. On DOWN: follow SOP-MAINT-UPTIME (S4).
6. Log the edit: `{ key_path, old_value, new_value, edit_method, validated_at, backup_path }`.

**Outputs:** Config edit applied and validated, or backup restored. **Hand to:** Done. **Failure mode:** Validate passes but gateway status returns error: something deeper is wrong -- escalate to Rescue Rangers.

---

### SOP 9.4 -- Rollback Protocol

**When to run:** When any fix causes a degraded state (config validate fails, gateway goes DOWN, live turn fails post-fix).

**Steps:**
1. STOP all further fix attempts immediately. Do NOT retry the same fix.
2. Restore the most recent backup: `cp working/maintenance/backups/openclaw.json.bak-YYYYMMDD-HHMMSS /path/to/openclaw.json`.
3. If the gateway is DOWN: follow SOP-MAINT-UPTIME (S4) to restore it.
4. Re-run `openclaw config validate` and `openclaw gateway status` after restore.
5. If the restore succeeds: send ONE operator notification with what was tried, what went wrong, and what was restored.
6. If the restore ALSO fails (backup is corrupt or inaccessible): escalate to Rescue Rangers (S5) IMMEDIATELY with full evidence. This is a P0 incident.

**Outputs:** Restored state or P0 escalation. **Hand to:** Rescue Rangers if restore fails. **Failure mode:** Multiple backup copies are corrupted: P0 escalation. Do NOT attempt further edits.

---
