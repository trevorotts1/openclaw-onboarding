# OpenClaw Maintenance Department — Suggested Roles

**Department mission:** Keep the OpenClaw system itself healthy. The skills, agents, memory architecture, integrations, secrets, and backups that the rest of the company runs on. Without this dept, every other department degrades silently.

**Version:** 2.1.2 (v10.5.2 expansion)
**Director:** Director of OpenClaw Maintenance
**Devil's Advocate:** Built in (with recursive-modification guard — see Section 12)
**Universal roles in this dept:** QC role, Deep Research role

---

## Recursive Modification Guard (Critical)

Because this department maintains the very system it runs on, **any change to `[OPENCLAW_ROOT]/skills/` or to OpenClaw Maintenance's own role files requires explicit owner approval through Master Orchestrator.** This prevents the department from breaking itself (per PRD v2.1 Edge Case 20.14).

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

