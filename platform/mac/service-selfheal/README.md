# Mac Service Self-Heal (`remediate.sh` + `gateway-health-watchdog.sh`)

Per-Mac belt-and-suspenders that keeps the OpenClaw **gateway** and **every
cloudflared tunnel** LaunchAgent both *loaded* and *running*, and adds an
HTTP-**health** probe for the gateway (catches a *hung* gateway whose process is
alive but whose port is dead).

## Why this exists

launchd `KeepAlive` only respawns a job that is still **loaded**. A job that gets
**booted-out** — by an installer, an `openclaw service` step, a crash during
login, or a manual `launchctl bootout` — silently stays down until something
re-bootstraps it. And `KeepAlive` never fires for a process that is alive but
**hung** (the gateway-deferral-deadlock symptom: a token rotation defers a
restart, a SIGTERM lands mid-deferral, the gateway is left dark or wedged).
`remediate.sh` + `gateway-health-watchdog.sh` cover both gaps. They complement:

| Mechanism | Scope |
|---|---|
| launchd `KeepAlive` | respawns a *loaded* job whose process exits |
| `gateway-health-watchdog.sh` | HTTP `{"ok":true}` health probe + `launchctl kickstart` of a *hung* gateway (after N consecutive fails + cooldown) |
| **`remediate.sh`** | re-bootstraps *booted-out* gateway/cloudflared agents; kickstarts *dead* KeepAlive jobs; **delegates** the gateway health leg to the watchdog when present |

## What `remediate.sh` does (idempotent, read-mostly)

For the gateway (delegated to `gateway-watchdog.sh` when present) and for every
`com.cloudflared.*` / `com.cloudflare.*` LaunchAgent:

1. plist exists but job **not loaded** → `launchctl bootstrap`.
2. loaded **KeepAlive** job with **no PID** → `launchctl kickstart -k`.
3. loaded **periodic** (`StartInterval`) job with no PID → OK (normal).
4. healthy → log `OK`, do nothing.

It never edits a plist and never touches client credentials. Log:
`~/Library/Logs/openclaw/service-remediate.log`.

## What `gateway-health-watchdog.sh` does

- Resolves the **real** gateway port (`openclaw gateway status` → `PORT` →
  `OPENCLAW_GATEWAY_PORT` → `18789` only as a last resort — it never assumes
  18789).
- HTTP-probes `http://127.0.0.1:<port>/` for a `{"ok":true}` body (CLI
  `openclaw gateway status` is the corroborating fallback signal).
- Acts **only after N consecutive failures** (default 3) **and** outside a
  post-action **cooldown** (default 600s) — it can never become a restart storm.
- Box-aware heal: **Mac** → `launchctl kickstart -k` the live gateway label;
  **VPS host** → `docker restart` the openclaw container; **inside a container**
  → log ESCALATE and rely on the container restart policy (no docker socket).
- `--report-only` / `GATEWAY_WATCHDOG_DRYRUN=1` logs the would-be action and
  takes none. Never runs bare `gws`; never edits config/creds/plists. Log:
  `~/Library/Logs/openclaw/gateway-watchdog.log`.

## Install (no sudo)

`install.sh` runs this automatically on Mac (end-of-install, Mac-gated). To
(re)install by hand:

```bash
bash platform/mac/service-selfheal/install-service-remediate.sh
```

Installs `remediate.sh` to `~/.openclaw/service-env/remediate.sh` **and**
`gateway-health-watchdog.sh` to `~/.openclaw/service-env/gateway-watchdog.sh`
(the exact name `remediate.sh` delegates to), then loads the
`com.openclaw.service-remediate` LaunchAgent (runs every 5 min; override with
`REMEDIATE_INTERVAL=<seconds>`). No second LaunchAgent is created — the watchdog
runs on the existing service-remediate schedule via delegation.

## Verify

```bash
launchctl print gui/$(id -u)/com.openclaw.service-remediate | grep state
tail -10 ~/Library/Logs/openclaw/service-remediate.log
tail -10 ~/Library/Logs/openclaw/gateway-watchdog.log
```

## VPS host

The same box-aware watchdog runs on a Docker **host** (not inside the container)
via a `*/5` host crontab installed by
`platform/vps/service-selfheal/install-host-watchdog-cron.sh` (operator runs it on the host —
`install.sh` cannot, because it re-execs into the container). There it
`docker restart`s the openclaw container when the gateway HTTP health fails.

## Related

- `platform/mac/tunnel-hardening/` — cloudflared connector hardening (Layers A–D)
  and the no-sudo `cloudflared tunnel run` KeepAlive agent
  (`install-tunnel-run-agent.sh`) that this self-heal then keeps bootstrapped.
- `platform/vps/service-selfheal/install-host-watchdog-cron.sh` — VPS host
  equivalent of the gateway health watchdog.
