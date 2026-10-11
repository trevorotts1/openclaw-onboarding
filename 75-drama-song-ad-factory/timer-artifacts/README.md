# Drama Studio persistent timer artifacts (U6)

Joint plan section 5, row U6:

> Direct-shell persistent Mac/Hostinger/Contabo timer, no idle model event,
> correct user/paths and restart state.

This directory holds the timer FILES and a checker for the three platforms the
row names. **Nothing here is installed, loaded, scheduled or registered — not on
this operator Mac, not on any fleet or client box, not in any container.** The
installer renders files and prints the one registration command the OPERATOR
would run; it never runs it. See "Install paths" below for what each platform's
path is.

It reuses existing installer shapes, not a new framework:

- macOS: `platform/mac/service-selfheal/com.openclaw.service-remediate.plist.template`
  + `install-service-remediate.sh` (a `sed`-expanded LaunchAgent template with
  `ProgramArguments = [/bin/sh, <script>]`).
- VPS/containers: `platform/vps/service-selfheal/install-host-watchdog-cron.sh`
  (an idempotent `*/N ... /bin/sh <abs script> >> <log> 2>&1` crontab line) and
  the Hostinger/Contabo persistent-volume contract in
  `platform/vps/hostinger/` and `platform/vps/contabo/`.

## Files

| File | What it is |
| --- | --- |
| `run-timer.sh` | The direct-shell poller the scheduler runs. Platform-aware; execs the U5 bridge. |
| `install-timer.sh` | Renders the platform definition into its install path. Files only — never registers. Modes: `--dry-run` (default), `--apply`, `--check-identity`, `--register` (always refused). |
| `mac/com.blackceo.drama-studio-bridge.plist.template` | macOS LaunchAgent definition. |
| `hostinger/drama-studio-timer.cron.template` | Hostinger container crontab definition. |
| `contabo/drama-studio-timer.cron.template` | Contabo container crontab definition. |
| `checks/run_checks.py` | The runnable checks (A–G), each with a plantable negative control and a true exit code. |

## The direct-shell mechanism

The scheduler runs a shell program and nothing else.

- **macOS** — launchd runs `ProgramArguments = [/bin/sh, .../run-timer.sh]`.
- **Hostinger / Contabo** — cron runs `/bin/sh .../run-timer.sh` with an explicit
  minimal environment.

`run-timer.sh` then `exec`s the U5 bridge directly:

```
python3 <skill>/shared-bridge/studio_bridge.py handshake --base-url "$DS_BASE_URL"
```

`handshake` is `POST /api/studio/checkin` — the joint plan's "direct bridge inbox
check". There is **no model call, no Claude, no claude-nine, no 9Router launch,
no prompt and no interactive TTY** anywhere on the path. The timer is not gated
on an idle/agent event: its only triggers are the wall-clock interval
(`StartInterval 120` / `*/2 * * * *`) and load/login (`RunAtLoad`).

## Per-platform contract

| | macOS client box | Hostinger container | Contabo container |
| --- | --- | --- | --- |
| Scheduler | launchd (user LaunchAgent) | cron (inside container) | cron (inside container) |
| User | the logged-in client | `node` | `node` |
| HOME | `/Users/<user>` (persistent) | `/data` (persistent volume) | `/home/node` (**ephemeral** layer) |
| Persistent root | `$HOME` | `/data` | `/home/node/.openclaw` (the volume) |
| Key + address + state | `$HOME/.drama-studio/` | `/data/.drama-studio/` | `/home/node/.openclaw/.drama-studio/` |
| Log | `$HOME/Library/Logs/openclaw/drama-studio-timer.log` | `/data/.openclaw/logs/drama-studio-timer.log` | `/home/node/.openclaw/logs/drama-studio-timer.log` |

The Contabo row is the trap the joint plan names: `$HOME` there is the throwaway
container layer (a recreate wipes it), so the key, address, state and log all
live under the volume `/home/node/.openclaw`, never under `$HOME`. `run-timer.sh`
and the installer both refuse a Contabo state path outside that root.

## Install paths (stated, not performed)

- **macOS** — definition installs to
  `$HOME/Library/LaunchAgents/com.blackceo.drama-studio-bridge.plist`. The script
  ships inside the skill folder and is not copied (updates replace it in place, as
  the plan requires). The operator registers it with:
  `launchctl bootstrap gui/$(id -u) $HOME/Library/LaunchAgents/com.blackceo.drama-studio-bridge.plist`
- **Hostinger** — definition at
  `/data/.openclaw/scripts/drama-studio-timer.cron`, script at
  `/data/.openclaw/scripts/run-timer.sh`. Operator registers:
  `docker exec -u node <container> sh -c 'crontab /data/.openclaw/scripts/drama-studio-timer.cron'`
- **Contabo** — definition at
  `/home/node/.openclaw/scripts/drama-studio-timer.cron`, script at
  `/home/node/.openclaw/scripts/run-timer.sh`. Operator registers:
  `docker exec -u node <container> sh -c 'crontab /home/node/.openclaw/scripts/drama-studio-timer.cron'`

`install-timer.sh --register` refuses (exit 2) and prints the operator command; it
contains no `launchctl`, `crontab -`, `systemctl` or `pm2` invocation.

## Restart state

- **macOS** — `RunAtLoad` runs the poll at login/reboot; `StartInterval 120`
  re-fires it. There is deliberately **no `KeepAlive`**: a `KeepAlive` would re-run
  the short poll the instant it exits and burn the box. A killed run is simply
  re-fired at the next interval, and the U5 claim ledger makes that idempotent.
- **Hostinger / Contabo** — cron re-fires every 2 minutes; all state is on the
  persistent volume, so a reboot, login or container recreate keeps it.

## Secrets

The machine key is read at runtime from the platform's own `0600` store
(`$DS_STATE_DIR/machine.key`) and exported as `DS_KEY` for the bridge child only.
It is never argv, never a log line and never printed; `run-timer.sh` prints no key
value on any path. The timer files contain no embedded credential (check `F`).

## Run the checks

```bash
python3 75-drama-song-ad-factory/timer-artifacts/checks/run_checks.py
# exit 0 = all pass; 1 = at least one failed (named). Writes only its own scratch.
```

Each good check is paired with a planted-bad negative control the same instrument
must reject:

| Check | Good | Negative control |
| --- | --- | --- |
| A1/A2/A3 | mac plist parses; host/cont cron lines parse | malformed plist / missing cron field / bad step are rejected |
| B | invocation is a direct `/bin/sh run-timer.sh`, no model/idle/interactive token | a definition gated on an idle model event and calling `claude` is rejected |
| C | mac/host/cont user+HOME accepted | wrong user, wrong path, temp path refused non-zero |
| D | `RunAtLoad`+`StartInterval` (no KeepAlive); state on the persistent root | plist missing `RunAtLoad`, and Contabo state on the ephemeral `$HOME`, are rejected |
| E | `--dry-run` writes nothing, registers nothing | `--apply` writes are SEEN by the same white-box detector (proves it is not blind) |
| G | the poller accepts a good identity then refuses an unpaired box (exit 2) | wrong platform/user and wrong state path refused non-zero |
| F | no credential literal in any timer file | a planted `DS_KEY=...` literal is detected by the same scanner |

Nothing here was installed, enabled, loaded or scheduled, and no launchd, cron,
systemd, pm2 or Task Scheduler surface was written.

## Deliberate limits

- macOS Task Scheduler / Windows is U15's (999-setup) path, not this unit.
- The poll runs `handshake` (check-in). Wiring a claimed order into a run is the
  U5 bridge's and the flow units' job, not the timer's.
- The bridge itself ships in U5 (`75-drama-song-ad-factory/shared-bridge/`); this
  timer resolves its path at runtime and fails cleanly when it is absent.
