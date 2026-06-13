# SOP Mirror -- Token Manager / Furnace Watch Specialist

**SOP ID:** `SOP-MAINT-FURNACE-WATCH`
**Source:** openclaw-maintenance/token-manager-furnace-watch-specialist.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Cadence:** >= hourly (lightweight read-only probes; notify-on-change-only)
**Owner:** Token Manager / Furnace Watch Specialist (R1)
**Cross-cutting references:** SOP-MAINT-RESCUE-RANGERS-ESCALATION (S5), SOP-MAINT-PROACTIVE-FIX-GUARDRAIL (S6)

---

## 9. Standard Operating Procedures

### SOP 9.1 -- Furnace Probe (Hourly Sweep)

**When to run:** Every hour, lightweight read-only probe. This is NOT an agentTurn on a 2-minute cron -- it is a host-level pure-shell cron (`*/60` or an equivalent host watchdog) that costs zero agent tokens unless a finding is detected.

**Inputs:**
- Host process table (gateway PID, known watchdog PIDs)
- OpenClaw session ledger / active-agents list (read-only)
- Cron ledger (crontab -l or `/data/.openclaw/crons/`)
- Recent agentTurn logs (tail last 100 lines)
- GHL-MCP process (port 8765 status check)

**Steps:**
1. Read the active session list. Count open agent sessions. If count > expected-idle-baseline (set by operator in config; default 2), log with timestamp and session ids as a candidate furnace condition.
2. Scan cron entries for any job firing at `*/2` or `*/5` or `*/10` that triggers an `agentTurn` or `openclaw run` or `openclaw message`. Each such entry is a furnace candidate -- log with cron text and firing interval.
3. Check GHL-MCP port 8765: if it announces "healthy (pid NNN)" with a NEW pid since last probe, that is a restart-loop candidate. Log the pid and announce timestamp.
4. Tail the last 100 lines of the gateway log. Look for: looping heartbeat log entries (`[heartbeat poll]` appearing more than once per 30 minutes), memory-dreaming log entries firing every < 5 minutes, broken-delivery cron retrying in a tight loop (same delivery id appearing > 3 times in 100 lines).
5. Check for duplicate/orphan cron entries: two cron entries triggering the same function name. Log pairs.
6. If NO findings: exit silently (notify-on-change-only: silence = healthy).
7. If ANY finding: proceed to SOP 9.2 (Triage and Kill Decision). Do NOT auto-kill without triage.

**Outputs:**
- `working/maintenance/furnace-watch/probe-YYYYMMDD-HHMMSS.json` (only written when a finding exists; silent on clean sweep)

**Hand to:** SOP 9.2 on any finding; SOP-MAINT-RESCUE-RANGERS-ESCALATION (S5) if triage is ambiguous.

**Failure mode:** If the probe script itself fails (cron host not running, disk unreadable), alert via `openclaw message send --channel telegram -t "${RESCUE_RANGERS_HELP_CHAT_ID}"` and do NOT suppress the error.

---

### SOP 9.2 -- Furnace Triage and Kill Decision

**When to run:** Immediately after SOP 9.1 identifies a furnace candidate.

**Inputs:**
- `working/maintenance/furnace-watch/probe-YYYYMMDD-HHMMSS.json`
- OpenClaw docs (docs.openclaw.ai) if the looping component is unknown

**Steps:**
1. For each candidate, determine if it is: (A) a DEFINITIVE furnace (hard evidence of runaway loop burning tokens with no useful output), (B) AMBIGUOUS (might be a feature with valid reason to run frequently), or (C) FALSE POSITIVE (expected behavior).
2. Definitive furnace drivers -- auto-kill is authorized:
   - Heartbeat poll logging > 1 per 30 minutes into the agent session (known bug per memory: `heartbeat-poll-session-loop-fleetwide.md`).
   - Broken-delivery cron retrying the same delivery id in a tight loop.
   - Memory dreaming firing every < 5 minutes (expected: >= 30 minutes).
   - Duplicate/orphan cron entry (exact duplicate of another cron line).
3. Ambiguous candidates -- NEVER auto-kill. Mark `needs_owner_decision`, notify operator via Rescue Rangers (SOP S5). Propose the fix but DO NOT apply it.
4. Feature-bearing crons -- NEVER delete. Disable only (crontab edit to comment out, NOT remove) per SOP-MAINT-PROACTIVE-FIX-GUARDRAIL (S6).
5. Apply kill/disable per S6 guardrail. Write the finding to the ledger.

**Outputs:**
- `working/maintenance/furnace-watch/ledger.json` (append entry: timestamp, driver, action taken, token_savings_estimate)
- Notify-on-change-only: send ONE Telegram message per incident via `openclaw message send --channel telegram`, not a per-probe message.

**Hand to:** SOP 9.3 (post-fix verification); S5 for escalations.

**Failure mode:** If auto-kill is applied and the gateway goes down, immediately dispatch SOP-MAINT-UPTIME (S4) and escalate to Rescue Rangers.

---

### SOP 9.3 -- Post-Fix Verification

**When to run:** After any furnace kill/disable action.

**Steps:**
1. Wait 5 minutes. Re-run the hourly probe.
2. Confirm the furnace condition is gone (no new loop entries in logs, session count back to baseline).
3. If still present: escalate to Rescue Rangers (S5). Do NOT re-kill in a loop.
4. Update `working/maintenance/furnace-watch/ledger.json` with `verified_at` and `outcome: resolved|escalated`.

**Outputs:** Updated ledger entry. **Hand to:** SOP S5 if not resolved. **Failure mode:** Three consecutive failed verifications = P0 escalation to Rescue Rangers with full evidence package.

---

### SOP 9.4 -- Furnace Driver Reference (F1-F13)

**When to run:** Reference only -- use when triaging a candidate to identify its known driver.

**Drivers this role owns:**
- **F1 Heartbeat-poll session loop:** `[heartbeat poll]` log spam per memory rule `heartbeat-poll-session-loop-fleetwide.md`. Fix: JSON deep-merge `gateway: { heartbeat: { intervalMs: 1800000 } }`.
- **F2 Memory dreaming over-frequency:** dreaming cron or plugin config firing < 30 min. Fix: pin interval >= 30 min in plugin config.
- **F3 Broken-resume build cron:** a workflow build cron retrying a failed run ID on every fire. Fix: clear the stale run ID from the cron ledger.
- **F6 GHL-MCP autostart session-kill loop:** bot announces "healthy on :8765 (pid NNN)" with changing PID per `ghl-mcp-autostart-session-kill-loop.md`. Fix: host-level watchdog + notify-on-change-only.
- **F10 Broken-delivery cron:** delivery cron retrying a completed or failed delivery id. Fix: mark delivery complete in ledger, disable retry.
- **F11 Duplicate/orphan cron:** two cron entries triggering the same function. Fix: disable the duplicate (comment out, not delete).
- **F13 Instance-backup gateway-crash loop:** backup cron triggering a gateway-crash on every fire. Fix: identify the crashing backup step and disable it pending investigation.

**Triggers this role hands off:**
- **F8 Model overkill (cost side):** hand to Cost/Model Optimizer (R2).
- **F9 Token-furnace model selection:** hand to Cost/Model Optimizer (R2).
- **F12 SOP re-embed broken embed index:** hand to Memory Hygiene Specialist.

---
