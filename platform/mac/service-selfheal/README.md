# Mac Service Self-Heal (`remediate.sh`)

Per-Mac belt-and-suspenders that keeps the OpenClaw **gateway** and **every
cloudflared tunnel** LaunchAgent both *loaded* and *running*.

## Why this exists

launchd `KeepAlive` only respawns a job that is still **loaded**. A job that gets
**booted-out** — by an installer, an `openclaw service` step, a crash during
login, or a manual `launchctl bootout` — silently stays down until something
re-bootstraps it. `remediate.sh` is that something. It complements:

| Mechanism | Scope |
|---|---|
| launchd `KeepAlive` | respawns a *loaded* job whose process exits |
| `gateway-watchdog.sh` | HTTP health probe + kickstart of a *hung* gateway |
| **`remediate.sh`** | re-bootstraps *booted-out* gateway/cloudflared agents; kickstarts *dead* KeepAlive jobs |

## What `remediate.sh` does (idempotent, read-mostly)

For the gateway (delegated to `gateway-watchdog.sh` when present) and for every
`com.cloudflared.*` / `com.cloudflare.*` LaunchAgent:

1. plist exists but job **not loaded** → `launchctl bootstrap`.
2. loaded **KeepAlive** job with **no PID** → `launchctl kickstart -k`.
3. loaded **periodic** (`StartInterval`) job with no PID → OK (normal).
4. healthy → log `OK`, do nothing.

It never edits a plist and never touches client credentials. Log:
`~/Library/Logs/openclaw/service-remediate.log`.

## Install (no sudo)

```bash
bash platform/mac/service-selfheal/install-service-remediate.sh
```

Installs `remediate.sh` to `~/.openclaw/service-env/remediate.sh` and loads the
`com.openclaw.service-remediate` LaunchAgent (runs every 5 min; override with
`REMEDIATE_INTERVAL=<seconds>`).

## Verify

```bash
launchctl print gui/$(id -u)/com.openclaw.service-remediate | grep state
tail -10 ~/Library/Logs/openclaw/service-remediate.log
```

## Related

- `platform/mac/tunnel-hardening/` — cloudflared connector hardening (Layers A–D)
  and the no-sudo `cloudflared tunnel run` KeepAlive agent
  (`install-tunnel-run-agent.sh`) that this self-heal then keeps bootstrapped.
