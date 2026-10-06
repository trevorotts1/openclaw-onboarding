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

> **Note on the delegation.** Once `gateway-watchdog.sh` is on disk,
> `remediate.sh` hands it the **whole** gateway leg and never calls its own
> `heal_label` bootstrap for the gateway. So the watchdog, not `remediate.sh`,
> is what has to handle a gateway that is **dead AND booted out**. It does:
> see "What `gateway-health-watchdog.sh` does" below.

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
- **Mac, dead AND booted out** → `launchctl bootstrap gui/<uid>
  ~/Library/LaunchAgents/<label>.plist` **first**, then the kickstart. A
  `kickstart -k` against a label that is not bootstrapped does nothing at all,
  and a detached OpenClaw upgrade that stalls leaves exactly that state.
- **Mac label resolution excludes the siblings.** A box commonly carries other
  labels containing both `openclaw` and `gateway` (an operator box runs
  `ai.openclaw.gateway-watchdog` next to `ai.openclaw.gateway`), and
  `launchctl list` is not ordered, so the match skips `watchdog`, `remediate`,
  `tunnel`, `monitor` and `selfheal` names.
- **Clears the OpenClaw 2026.9.x session-store migration gate.** 2026.9.x
  refuses to *start* the gateway while a legacy JSON session store is on disk
  (`Legacy session store requires migration: <path>.` from
  `src/config/sessions/startup-migration.ts`), so restarting it only re-hits the
  same refusal. When that string is in the gateway log the watchdog runs
  `openclaw doctor --session-sqlite import --session-sqlite-all-agents --yes
  --non-interactive` once per cooldown, then heals normally. The import is
  non-destructive: the legacy JSON files stay on disk.
- `--report-only` / `GATEWAY_WATCHDOG_DRYRUN=1` logs the would-be action and
  takes none. Never runs bare `gws`; never edits config/creds/plists. Log:
  `~/Library/Logs/openclaw/gateway-watchdog.log`.

## Install (no sudo)

**Every fleet roll converges this.** `update-skills.sh` runs the installer on
its Mac leg on every roll, so a box that was onboarded before this shipped, or
whose LaunchAgent was booted out and never re-bootstrapped, is repaired the next
time it rolls. The roll prints one greppable line:

```
[GATEWAY-WATCHDOG] state=installed        # the installer ran
[GATEWAY-WATCHDOG] state=already-current  # scripts match the bundle, agent loaded, nothing touched
[GATEWAY-WATCHDOG] state=skipped-not-mac  # VPS, container, or running as root
[GATEWAY-WATCHDOG] state=warn             # could not converge; the roll continues regardless
```

The converge is deliberately **fail-soft**: it never fails a roll and never
withholds the version stamp. `warn` names a staged copy under
`$OC_CONFIG/scripts/service-selfheal/` that outlives the temp clone, so the
remedy in the log is always a path that still exists.

`install.sh` also runs it at first-time onboarding (end-of-install, Mac-gated).
To (re)install by hand:

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
grep '\[GATEWAY-WATCHDOG\]' /tmp/openclaw-update-*.log | tail -1
```

Regression suite: `tests/unit/roll-converges-gateway-watchdog.test.sh`, wired by
`.github/workflows/roll-converges-gateway-watchdog-guard.yml`.

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
