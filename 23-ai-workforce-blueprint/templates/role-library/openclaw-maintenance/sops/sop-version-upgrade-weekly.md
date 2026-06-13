# SOP Mirror -- OpenClaw Version & Upgrade Manager Specialist

**SOP ID:** `SOP-MAINT-VERSION-UPGRADE`
**Source:** openclaw-maintenance/version-and-upgrade-manager-specialist.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Cadence:** Weekly (research-first -- NEVER upgrade without reading docs first)
**Owner:** OpenClaw Version & Upgrade Manager Specialist (R3)
**Cross-cutting references:** SOP-MAINT-RESCUE-RANGERS-ESCALATION (S5), SOP-MAINT-PROACTIVE-FIX-GUARDRAIL (S6)

---

## 9. Standard Operating Procedures

### SOP 9.1 -- Weekly Version Check (Research-First Pre-Flight)

**When to run:** Once weekly. NEVER skip the research step -- per memory rule `feedback-no-guessing-verify-docs.md`: "Before touching OpenClaw / OpenRouter / Ollama (or claiming a fact about them), check docs.openclaw.ai / openrouter.ai / ollama.com."

**Inputs:**
- Current installed version: `openclaw --version` OR `openclaw gateway status`
- `docs.openclaw.ai` release notes (fetch live -- do NOT rely on training-data knowledge of version numbers)
- Official OpenClaw GitHub release notes / KNOWN-ISSUES page (live fetch)

**Steps:**
1. Read the CURRENT installed version. Record it: `current_version`.
2. Fetch `docs.openclaw.ai/changelog` or equivalent release-notes page. Record the LATEST released version: `latest_version`.
3. If `current_version == latest_version`: log a clean-sweep entry and exit silently. No upgrade needed.
4. If `latest_version > current_version`: proceed to SOP 9.2 (safety assessment).

**Outputs:**
- `working/maintenance/version-upgrades/check-YYYYMMDD.json` (`{ current_version, latest_version, action: "no_upgrade_needed | proceed_to_assessment" }`)

**Hand to:** SOP 9.2 if upgrade available. **Failure mode:** Cannot fetch docs.openclaw.ai: do NOT proceed with the upgrade. Log the docs-fetch failure and alert via Rescue Rangers (S5). Never upgrade blind.

---

### SOP 9.2 -- Safety Assessment (This Box)

**When to run:** After SOP 9.1 confirms a newer version is available.

**Inputs:**
- `docs.openclaw.ai` KNOWN-ISSUES + MIGRATION notes for ALL versions between `current_version` and `latest_version`
- This box's `openclaw.json` (especially: `mcp.servers`, `agents`, `plugins` -- areas that historically break on schema drift)
- Platform type: Mac (launchd/Homebrew) or VPS (Hostinger Docker)

**Steps:**
1. Read the MIGRATION notes for every intermediate version. Flag any breaking change that matches this box's config (e.g., `mcpServers` root-level deprecated in v10.15.x per memory `openclaw-mcp-schema-drift.md`).
2. Read the KNOWN-ISSUES page. If the new version has a known critical issue affecting this box's platform or config: do NOT upgrade. Log the issue and wait for a patch release.
3. Check for config conflicts:
   - VPS (Hostinger Docker): does `docker-compose.yml` `command:` hardcode an older version pin? If yes, the pin must be updated first or the upgrade will silently revert (per memory `feedback-hostinger-compose-command-pin.md`).
   - Mac: is the gateway managed by launchd? If yes, the upgrade path is Homebrew -- NEVER `openclaw gateway restart` over SSH (per memory `mac-client-gateway-launchd-ssh.md`).
4. Write the safety verdict: `{ safe_to_upgrade: true|false, blocking_issues: [...], platform: "mac|vps" }`.

**Outputs:**
- Updated `working/maintenance/version-upgrades/check-YYYYMMDD.json`

**Hand to:** SOP 9.3 if `safe_to_upgrade: true`; SOP 9.5 (hold) if blocking issues. **Failure mode:** Cannot determine platform (no docker-compose, no launchd plist): escalate to Rescue Rangers (S5) before proceeding.

---

### SOP 9.3 -- Upgrade Execution (Platform-Correct Path)

**When to run:** After SOP 9.2 returns `safe_to_upgrade: true`.

**Platform A: Mac (Homebrew / launchd)**

**Steps:**
1. Back up `openclaw.json` to `working/maintenance/version-upgrades/openclaw.json.bak-YYYYMMDD`.
2. Run `brew upgrade openclaw` (or the documented Homebrew tap upgrade command from docs.openclaw.ai).
3. Do NOT run `openclaw gateway restart` over SSH -- this triggers launchd err 125 and takes the box DOWN. Instead, use detached `openclaw gateway run` if a restart is needed.
4. Run `openclaw config validate`. If it fails: restore backup immediately and escalate to Rescue Rangers.
5. Proceed to SOP 9.4 (post-upgrade verification).

**Platform B: VPS (Hostinger Docker)**

**Steps:**
1. Back up `openclaw.json` and `/docker/<project>/docker-compose.yml` to `working/maintenance/version-upgrades/`.
2. Update `docker-compose.yml` `command:` line to reference the new version (if it has a hardcoded pin). Do NOT leave the old pin (per memory `openclaw-vps-beyond-image-upgrade.md`).
3. Run `docker compose pull && docker compose up -d --force-recreate` (NOT in-container `npm install` as primary path -- it reverts on next recreate per memory `openclaw-vps-docker-persistent-upgrade.md`).
4. Wait 30 seconds for gateway to come up. Run `openclaw config validate`. If it fails: restore backup, run `docker compose up -d --force-recreate` again, escalate to Rescue Rangers.
5. Proceed to SOP 9.4 (post-upgrade verification).

**Outputs:**
- Upgraded installation
- Backup files in `working/maintenance/version-upgrades/`

**Hand to:** SOP 9.4. **Failure mode:** Any upgrade step fails: restore backup immediately (see S6 guardrail), do NOT retry without escalating.

---

### SOP 9.4 -- Post-Upgrade Verification

**When to run:** Immediately after SOP 9.3 upgrade execution.

**Steps:**
1. Run `openclaw --version` (or `openclaw gateway status --deep` on VPS per memory `openclaw-vps-beyond-image-upgrade.md`). Confirm the version matches `latest_version`. IMPORTANT: on VPS, `docker exec openclaw --version` shows the IMAGE version (old); use `openclaw gateway status --deep` to see the RUNNING version.
2. Send a real live turn to the main agent (one minimal test message). Confirm it responds correctly.
3. Check gateway health: `openclaw gateway status`. Confirm no error flags.
4. Run `openclaw config validate` one final time.
5. Send operator notification via `openclaw message send --channel telegram`: "OpenClaw upgraded from `{current_version}` to `{latest_version}` on `{box_name}`. Live turn verified. Config validated."
6. Update `working/maintenance/version-upgrades/check-YYYYMMDD.json`: `{ upgraded_at, from_version, to_version, verified: true }`.
7. Append to `~/clawd/fleet-heartbeat/change-log.md` per the 6 mandatory rules (per memory `openclaw-vps-docker-persistent-upgrade.md`).

**Outputs:** Verification record, operator notification, change-log entry. **Hand to:** Done. **Failure mode:** Live turn fails or validate fails: revert (restore backup), alert via Rescue Rangers, log as REVERTED.

---

### SOP 9.5 -- Upgrade Hold (Blocking Issue)

**When to run:** When SOP 9.2 finds a blocking issue that prevents safe upgrade.

**Steps:**
1. Log the blocking issue to `working/maintenance/version-upgrades/holds.json`: `{ version, blocking_reason, detected_at, check_again_after }`.
2. Set a weekly re-check: on next weekly run, fetch the docs again to see if the issue is resolved in a patch release.
3. Notify operator once (not every week) via Rescue Rangers (S5).

**Outputs:** Hold record. **Hand to:** SOP 9.1 on next weekly cycle. **Failure mode:** Operator directs upgrade despite hold: execute under Tier 3 approval -- require written operator sign-off before proceeding.

---
