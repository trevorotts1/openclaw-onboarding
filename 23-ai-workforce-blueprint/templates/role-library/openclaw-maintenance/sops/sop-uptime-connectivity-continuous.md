# SOP Mirror -- Uptime / Connectivity Watchdog Specialist

**SOP ID:** `SOP-MAINT-UPTIME`
**Source:** openclaw-maintenance/uptime-connectivity-watchdog-specialist.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Cadence:** Continuous (host-level watchdog cron `*/10` pure-shell; notify-on-change-only; NOT an agentTurn)
**Owner:** Uptime / Connectivity Watchdog Specialist (R4)
**Cross-cutting references:** SOP-MAINT-RESCUE-RANGERS-ESCALATION (S5), SOP-MAINT-PROACTIVE-FIX-GUARDRAIL (S6)
**Drivers owned:** F4 (gateway down), F5 (CF tunnel down), F7 (process restart loop)

---

## 9. Standard Operating Procedures

### SOP 9.1 -- Continuous Watchdog Probe (`*/10` host-level cron)

**When to run:** Every 10 minutes, pure-shell script (NOT an agentTurn; does NOT consume agent tokens unless a recovery action is triggered). This is a host-level cron entry -- it runs outside the OpenClaw session system.

**HARD RULE (Mac):** NEVER run `openclaw gateway restart` over SSH on a Mac client. This sends a `restart` command to the launchd-managed gateway, which returns err 125 and takes the box DOWN (per memory `mac-client-gateway-launchd-ssh.md`). The ONLY safe recovery path on Mac is detached `openclaw gateway run` or letting launchd auto-restart.

**Inputs:**
- Gateway port 18789 (HTTP health check endpoint)
- CF tunnel connector status (`cloudflared tunnel info` or heartbeat endpoint)
- Process table (gateway PID, cloudflared PID)

**Steps:**
1. HTTP GET `http://localhost:18789/health` (or the box's documented health endpoint). If response is 200: gateway is UP.
2. Check CF tunnel: `cloudflared tunnel info <tunnel-id>` or check connector heartbeat. If connector is healthy: tunnel is UP.
3. If BOTH are UP: exit silently (notify-on-change-only: silence = healthy). Log nothing.
4. If gateway is DOWN: proceed to SOP 9.2 (Mac) or SOP 9.3 (VPS).
5. If CF tunnel is DOWN: proceed to SOP 9.4.
6. If BOTH are DOWN: execute SOP 9.2/9.3 first (gateway), then SOP 9.4 (tunnel), then send ONE Rescue Rangers alert (S5) with the full picture.

**Outputs:** Silence on healthy; `working/maintenance/uptime/down-YYYYMMDD-HHMMSS.json` on any DOWN event.

**Hand to:** SOP 9.2 (Mac gateway down), SOP 9.3 (VPS gateway down), SOP 9.4 (CF tunnel down). **Failure mode:** Probe script itself errors: send alert via Rescue Rangers (S5). Never swallow script errors silently.

---

### SOP 9.2 -- Mac Gateway Recovery (SAFE PATH ONLY)

**When to run:** When SOP 9.1 detects gateway DOWN on a Mac client.

**CRITICAL: Do NOT use `openclaw gateway restart` on Mac over SSH. It will make the box WORSE.**

**Steps:**
1. Check launchd status: `launchctl print user/$(id -u)/ai.openclaw.gateway` (or equivalent). If launchd shows the service as running but the health check fails, launchd may be trying to restart it -- wait 30 seconds and re-probe before taking action.
2. If launchd is NOT running the service: run `launchctl kickstart -k user/$(id -u)/ai.openclaw.gateway`. This is the launchd-safe restart (NOT `openclaw gateway restart`).
3. Wait 20 seconds. Re-run health check probe.
4. If still DOWN after kickstart: run detached `nohup openclaw gateway run > /tmp/gateway-recovery.log 2>&1 &`. This starts the gateway as a background process independent of launchd.
5. Wait 30 seconds. Re-run health check probe.
6. If UP: send ONE Telegram notification via `openclaw message send --channel telegram`: "Gateway recovered on [box_name] at [timestamp]. Method: [kickstart|detached-run]. Was down approximately [duration]."
7. If still DOWN after step 5: escalate to Rescue Rangers (S5) with full evidence (launchd output, process table, gateway log tail).

**Outputs:** Gateway UP or escalation to Rescue Rangers. **Hand to:** SOP 9.5 (post-recovery verification). **Failure mode:** Every recovery attempt makes things worse: STOP and escalate to Rescue Rangers. Do NOT loop on recovery attempts.

---

### SOP 9.3 -- VPS Gateway Recovery

**When to run:** When SOP 9.1 detects gateway DOWN on a Hostinger Docker VPS.

**Steps:**
1. Run `docker ps -a | grep openclaw`. If the container shows `Exited`: it crashed.
2. Run `docker compose up -d` (NOT `docker compose restart` -- use `up -d` which applies compose file changes).
3. Wait 30 seconds. Re-run health check probe.
4. If still DOWN: run `docker compose up -d --force-recreate`. This is the full recreate path.
5. Wait 30 seconds. Re-run health check probe.
6. If UP: send ONE Telegram notification via `openclaw message send --channel telegram`.
7. If still DOWN: escalate to Rescue Rangers (S5) with container logs (`docker logs openclaw --tail 100`).

**Outputs:** Gateway UP or escalation. **Hand to:** SOP 9.5. **Failure mode:** force-recreate fails: send full container logs to Rescue Rangers. Do NOT continue retrying.

---

### SOP 9.4 -- CF Tunnel Recovery

**When to run:** When SOP 9.1 detects CF tunnel DOWN.

**Steps:**
1. Check the cloudflared connector process: `ps aux | grep cloudflared`. If not running: restart it.
2. On Mac: use the launchd service for cloudflared if it exists. Run `launchctl kickstart user/$(id -u)/com.cloudflare.cloudflared` (or the equivalent plist name). If no launchd service: run detached `nohup cloudflared tunnel run <tunnel-id> > /tmp/cloudflared-recovery.log 2>&1 &`.
3. On VPS: `docker compose restart cloudflared` OR restart the cloudflared container.
4. Wait 60 seconds (CF tunnel takes longer than gateway to stabilize). Re-probe.
5. If connector is healthy: send ONE Telegram notification.
6. If still DOWN: escalate to Rescue Rangers (S5). Include: tunnel ID, connector ID, cloudflared log tail.

**Outputs:** Tunnel UP or escalation. **Hand to:** SOP 9.5. **Failure mode:** Three restart attempts fail: stop and escalate to Rescue Rangers. Do NOT loop.

---

### SOP 9.5 -- Post-Recovery Verification

**When to run:** After any gateway or tunnel recovery action.

**Steps:**
1. HTTP GET `http://localhost:18789/health`. Confirm 200.
2. Send a real live turn to the main agent (one minimal test message via `openclaw message send`). Confirm it responds.
3. Verify CF tunnel is accessible from outside the box (if possible: `curl https://<tunnel-hostname>/health` or check cloudflared connector dashboard).
4. Update `working/maintenance/uptime/down-YYYYMMDD-HHMMSS.json`: `{ recovered_at, method, verified: true }`.
5. Append the incident to `~/clawd/fleet-heartbeat/change-log.md`.

**Outputs:** Verification record, change-log entry. **Hand to:** Done (healthy). **Failure mode:** Live turn fails even though health endpoint is 200: escalate to Rescue Rangers -- gateway may be up but agent routing is broken.

---

### SOP 9.6 -- Kill-Loop and PM2 Second-Gateway Detection (Drivers F5/F7)

**When to run:** When SOP 9.1 detects the gateway PID changing rapidly (multiple restarts within the probe window) or when `ps aux` shows two gateway processes.

**Steps:**
1. Identify the restart trigger: `launchd` (Mac -- check `KeepAlive` / `SuccessfulExit` plist keys) vs `PM2` (if PM2 is present on the box) vs a manual watchdog cron that is restarting the gateway.
2. If a watchdog CRON is issuing `openclaw gateway restart` commands: disable it immediately (comment out in crontab per S6 guardrail -- do NOT delete). This is the kill-loop per memory `mac-client-gateway-launchd-ssh.md`.
3. If PM2 is running a second gateway instance alongside launchd: stop the PM2-managed gateway (`pm2 stop openclaw-gateway`) and delete its PM2 entry (`pm2 delete openclaw-gateway`). Let launchd be the single supervisor.
4. Confirm only ONE gateway process is running after remediation.
5. Escalate to Rescue Rangers (S5) if two supervisors cannot be safely resolved (feature-bearing PM2 config present).

**Outputs:** Single gateway process; escalation if ambiguous. **Hand to:** SOP 9.5. **Failure mode:** Cannot determine which supervisor is authoritative: Rescue Rangers immediately.

---
