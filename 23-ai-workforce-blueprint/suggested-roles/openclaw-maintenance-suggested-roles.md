# OpenClaw Maintenance Department — Suggested Roles

**Department mission:** Keep the OpenClaw system itself healthy. The skills, agents, memory architecture, integrations, secrets, and backups that the rest of the company runs on. Without this dept, every other department degrades silently.

**Version:** 2.2.0 (v12.3.0 furnace-watch expansion)
**Director:** Director of OpenClaw Maintenance
**Devil's Advocate:** Built in (with recursive-modification guard — see Section 12)
**Universal roles in this dept:** QC role, Deep Research role

---

## Recursive Modification Guard (Critical)

Because this department maintains the very system it runs on, **any change to `[OPENCLAW_ROOT]/skills/` or to OpenClaw Maintenance's own role files requires explicit owner approval through Master Orchestrator.** This prevents the department from breaking itself (per PRD v2.1 Edge Case 20.14).

---

## Governing Rules for the 4 New Maintenance Specialists (v12.3.0)

#### Furnace-Watch Mandate (applies to all 4 specialists)

The Token Manager / Furnace Watch Specialist (role 13) performs an **hourly, read-only sweep** for runaway-agent and token-furnace conditions. Known drivers include: heartbeat-poll loops (gateway 30m default + Skill-18 HEARTBEAT.md + memory dreaming piling up session entries), GHL-MCP autostart restart-loop spinning agentTurns, broken resume/build crons firing without delivery, duplicate or orphan crons, and gateway-crash instance-backup loops. **Notify-on-change-only** — never spam a repeated alert for the same condition. Definitive furnace → auto-fix then notify. Ambiguous or feature-bearing → escalate via Rescue Rangers (see below). The Cost / Model Optimizer Specialist (role 14) and Uptime Watchdog (role 16) share the notify-on-change-only constraint on all their recurring probes.

#### Rescue Rangers Escalation (applies to all 4 specialists)

Every specialist in this department (including the 4 new ones) escalates ambiguous or feature-bearing findings via the **n8n webhook** (`$RESCUE_RANGERS_WEBHOOK_URL`):

```bash
curl -s -X POST "${RESCUE_RANGERS_WEBHOOK_URL}" \
  -H 'Content-Type: application/json' \
  -d "{\"action\":\"escalate\",\"client\":\"$(hostname 2>/dev/null||echo box)\",\"agent\":\"<ROLE_ID>\",\"message\":\"<escalation text>\"}"
```

Message must include: box identifier, driver/symptom, evidence (log excerpt or metric), proposed fix, and why the specialist is unsure. **Do NOT use `openclaw message send -t $RESCUE_RANGERS_HELP_CHAT_ID`** — bots cannot read other bots and that path is silently dropped. The webhook is a standard outbound HTTPS call that works even when the gateway is DOWN (no gateway needed). See the canonical escalation SOP: `SOP-MAINT-RESCUE-RANGERS-ESCALATION` (`sops/sop-rescue-rangers-escalation.md`).

#### Platform-Specific Guardrails for Uptime Watchdog (role 16)

- **Mac:** NEVER run `openclaw gateway restart` over SSH (launchd err 125 = box DOWN). Restart pattern: detached `openclaw gateway run` + a launchd-guarded watchdog. Watchdog cron must be a **pure-shell `*/10` probe**, notify-on-change-only — NOT an agentTurn, NOT `*/2`.
- **VPS (Hostinger Docker):** use `docker restart policy` / `--force-recreate`. Never run `openclaw gateway restart` as the primary repair path inside a container session.

---

## Roles in This Department

### 1. Director of OpenClaw Maintenance (full-time-permanent)
**Owns:** Overall system health, maintenance scheduling, version coordination, escalation to human owner for system-level decisions.
**Reports to:** Master Orchestrator
**Primary KPIs:**
- System uptime (heartbeat success rate ≥99%)
- Skill version currency (no skill more than 30 days behind upstream)
- Backup success rate (100%)
- Incident response time (<30 min from detection to acknowledgment)
**Tools:** OpenClaw CLI, GitHub, PM2 (Mac) or Docker (VPS), Cron, monitoring dashboard

---

### 2. System Health / Uptime Specialist (full-time-permanent)
**Owns:** Heartbeat monitoring, daemon health checks, log review, anomaly detection.
**Daily routine:**
- Check heartbeat success rate across all agents
- Review error logs for new patterns
- Verify all integrations responding
- Check disk space, memory usage
**Primary KPIs:** Mean time to detect (MTTD), false alert rate, daemon restart frequency
**Tools:** PM2 logs, docker logs, journalctl, custom OpenClaw monitor scripts

---

### 3. Skill Update & Patch Specialist (full-time-permanent)
**Owns:** Watching upstream skill releases, testing patches in staging, rolling out updates safely.
**Workflow:**
1. Subscribe to skill repo updates (RSS / GitHub watch)
2. Diff incoming changes vs current installation
3. Test in `~/.openclaw-staging/` (Mac) or `/data/.openclaw-staging/` (VPS) before promoting
4. Roll forward via `install.sh --update`
5. Document changes in CHANGELOG
**Primary KPIs:** Days behind upstream, failed update rate, rollback frequency
**Tools:** Git, install.sh, OpenClaw skill manager

---

### 4. Memory Hygiene Specialist (full-time-permanent)
**Owns:** MEMORY.md compaction, daily session log archival, Memory Wiki sync, Gemini index health.
**Workflow:**
- Daily MEMORY.md compaction (consolidate session logs into facts)
- Weekly Memory Wiki regeneration
- Monthly Gemini index integrity check (re-index if drift detected)
- Quarterly memory archive (move old session logs to compressed storage)
**Primary KPIs:** Memory file size growth rate, wiki freshness, Gemini retrieval accuracy
**Tools:** Memory Wiki, Gemini embedding tools, Cognee, Obsidian Vault

---

### 5. Integration / MCP Specialist (full-time-permanent)
**Owns:** All Model Context Protocol (MCP) servers. Third-party API integrations (Stripe, GoHighLevel, Telegram, Cloudflare, etc.). Connection health and credential rotation.
**Primary KPIs:** Integration uptime, MCP server response time, credential rotation compliance
**Tools:** MCP servers, API health monitors, secret managers

---

### 6. Backup & Recovery Specialist (full-time-permanent)
**Owns:** Backup strategy, restore testing, disaster recovery procedures.
**Mac:** Time Machine + cloud backup of `~/.openclaw/` and `~/clawd/zero-human-company/`
**VPS:** Cron + rsync of `/data/` to remote storage (S3, Backblaze B2, Hostinger Object Storage), daily snapshot
**Workflow:**
- Daily incremental backup
- Weekly full backup verification
- Monthly restore drill (restore to test environment, verify integrity)
**Primary KPIs:** Backup success rate, recovery time objective (RTO), recovery point objective (RPO)
**Tools:** rsync, Time Machine, restic, AWS CLI, Hostinger backup APIs

---

### 7. Security & Secrets Specialist (full-time-permanent)
**Owns:** API key rotation, .env file security, secrets audit, security patch tracking.
**Primary KPIs:** Days since last credential rotation, secrets exposed in logs (target: 0), patches behind on critical CVEs
**Tools:** OpenClaw secrets manager, 1Password / Bitwarden CLI, secret-scanning tools

---

### 8. Monitoring / Observability Specialist (full-time-permanent)
**Owns:** Active observability — metrics dashboards (Prometheus / Grafana / Datadog if installed), log aggregation, distributed tracing. Distinct from the System Health / Uptime Specialist (who handles binary up/down). This role tracks performance, latency, error rates across the OpenClaw fleet.
**Primary KPIs:** Mean time to detect (MTTD) anomaly, dashboard freshness, alert false-positive rate
**Tools:** Prometheus, Grafana, OpenTelemetry, custom OpenClaw monitor scripts

---

### 9. Performance Tuning Specialist (full-time-permanent)
**Owns:** Optimizing slow agents, identifying memory hogs, tuning skill execution times. Investigates "why is this agent slow today" and applies fixes (memory compaction, prompt optimization, sub-agent fan-out adjustments).
**Primary KPIs:** Agent average response time, p95 response time, memory footprint per agent, sub-agent spawn latency
**Tools:** OpenClaw profiler hooks, memory inspectors, prompt token-counting tools

---

### 10. Disaster Recovery Specialist (full-time-permanent)
**Owns:** Recovery procedures (separate from backups themselves — that's the Backup Specialist). Runbooks for "rebuild from scratch on new hardware", restore drills (quarterly), RTO/RPO definitions, cross-region recovery if applicable.
**Primary KPIs:** Documented recovery time objective (RTO), recovery point objective (RPO), drill pass rate, runbook freshness
**Tools:** Runbook documentation, restore drill checklist, cross-region replication tools

---

### 11. QC Role — OpenClaw Maintenance (full-time-permanent)
**Owns:** Reviews every system change before it ships. Verifies test coverage on patches, backup verifications, rollback plans.

---

### 12. Deep Research Role — OpenClaw Maintenance (on-call)
**Owns:** Researches OpenClaw architecture evolution, evaluates new skills/MCPs/memory systems. Tracks the OpenClaw docs site for upstream changes.

---

### 13. Token Manager / Furnace Watch Specialist (full-time-permanent)
**Owns:** The #1 cost-protection job. Sweeps the box **≥ hourly** for runaway-agent and token-furnace conditions — heartbeat-poll loops, memory-dreaming accumulation, GHL-MCP autostart agentTurn furnace, broken resume/build crons, duplicate/orphan crons, and gateway-crash instance-backup loops. Kills confirmed furnaces. Escalates ambiguous or feature-bearing findings to Rescue Rangers via the n8n webhook (`$RESCUE_RANGERS_WEBHOOK_URL`) before touching anything. Notify-on-change-only; never deletes a critical feature.
**Cadence:** ≥ hourly lightweight read-only probe; notify-on-change-only.
**Primary KPIs:** Token burn variance (target ≤15% MoM); furnace incidents detected before budget impact; zero critical-feature deletions.
**SOPs:** `SOP-MAINT-FURNACE-WATCH` (primary); co-owns `SOP-MAINT-RESCUE-RANGERS-ESCALATION`, `SOP-MAINT-PROACTIVE-FIX-GUARDRAIL`.
**Tools:** OpenClaw health dashboard, token burn analyzer, cron inspector, curl (webhook POST to `$RESCUE_RANGERS_WEBHOOK_URL` for Rescue Rangers escalations — do NOT use `openclaw message send -t <group>` for escalations; owner on-change notifications still use `openclaw message send`).

---

### 14. Cost / Model Optimizer Specialist (full-time-permanent)
**Owns:** Model right-sizing. Catches model overkill on recurring tasks and routes each task to the cheapest model the box already has access to that still does the job. Preserves by-design free-tier primaries and never removes a provider the owner explicitly chose.
**Cadence:** Daily review of token burn trending; notify-on-change-only.
**Primary KPIs:** Per-task token cost trend (target: reduce or hold); zero unauthorized model swaps; model-overkill incidents identified before budget impact.
**SOPs:** `SOP-MAINT-MODEL-OVERKILL` (primary); co-owns `SOP-MAINT-RESCUE-RANGERS-ESCALATION`, `SOP-MAINT-PROACTIVE-FIX-GUARDRAIL`.
**Tools:** Token burn analyzer, OpenClaw agent configuration, model routing table.

---

### 15. Version & Upgrade Manager Specialist (full-time-permanent)
**Owns:** OpenClaw version upgrades. Research-first protocol: reads `docs.openclaw.ai` + official GitHub release notes/known-issues **before** any upgrade action. Assesses safety for this box's specific config. Upgrades via the platform-correct path (Mac: Homebrew/launchd — never `gateway restart` over SSH; VPS: `docker compose pull` + `--force-recreate` — never in-container npm as primary). Runs `openclaw config validate` + a real live turn post-upgrade. Maintains a rollback line for every upgrade.
**Cadence:** Weekly (research-first); hold if any P1 is open.
**Primary KPIs:** Days behind current release (target ≤14); upgrade success rate (target ≥95%); zero upgrades without post-upgrade live-turn verification.
**SOPs:** `SOP-MAINT-VERSION-UPGRADE` (primary); co-owns `SOP-MAINT-RESCUE-RANGERS-ESCALATION`, `SOP-MAINT-PROACTIVE-FIX-GUARDRAIL`.
**Tools:** `docs.openclaw.ai`, OpenClaw GitHub releases, `openclaw config validate`, platform-specific upgrade commands.

---

### 16. Uptime / Connectivity Watchdog Specialist (full-time-permanent)
**Owns:** Gateway (port 18789) + Cloudflare tunnel continuous availability so Rescue Rangers can always reach the box. Hard platform rules: on Mac NEVER `openclaw gateway restart` over SSH (launchd err 125 = box DOWN) — use detached `openclaw gateway run` + a launchd-guarded watchdog. Kills gw-watchdog kill-spawn loops and PM2 second-gateway restart loops. On VPS uses Docker restart policy / `--force-recreate`.
**Cadence:** Continuous host-level watchdog cron (`*/10` pure-shell; notify-on-change-only — NOT an agentTurn, NOT `*/2`).
**Primary KPIs:** Gateway uptime (target ≥99.5%); CF tunnel healthy; zero Mac SSH-restart incidents; watchdog false-positive rate.
**SOPs:** `SOP-MAINT-UPTIME` (primary); co-owns `SOP-MAINT-RESCUE-RANGERS-ESCALATION`, `SOP-MAINT-PROACTIVE-FIX-GUARDRAIL`.
**Tools:** `openclaw gateway run` (detached), launchd (Mac), Docker restart policy (VPS), CF tunnel health endpoint, `openclaw message send`.

---

## Department Handoffs

**Receives from:**
- **Every department** → system issues, integration failures, agent malfunctions
- **Master Orchestrator** → priority directives, owner-approved system changes
- **Owner** → manual approval for any change in `[OPENCLAW_ROOT]/skills/` (recursive guard)

**Hands off to:**
- **Every department** → health status, change notifications, scheduled maintenance windows
- **Master Orchestrator** → escalations requiring owner attention
- **Owner** → critical issues that need human decision

---

## Platform-Specific Notes

**Mac:**
- PM2 daemon survives reboot via `pm2 startup` configuration
- Daily backup to Time Machine + cloud
- All paths via `detect_platform.py`

**VPS (Hostinger Docker):**
- Docker container must have `restart: unless-stopped` policy
- `/data/` MUST be a Docker volume (not bind mount) to survive `docker-compose down/up`
- PM2 inside container coordinated with Docker restart policy
- Daily snapshot to Hostinger Object Storage + offsite (B2/S3)

