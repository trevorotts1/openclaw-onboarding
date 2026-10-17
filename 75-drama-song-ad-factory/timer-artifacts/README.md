# Drama Studio persistent timer artifacts (U6)

Joint plan section 5, row U6:

> Direct-shell persistent Mac/Hostinger/Contabo timer, no idle model event,
> correct user/paths and restart state.

This directory holds the timer FILES, their installer and a checker for the
three platforms the row names. Every mode of `install-timer.sh` is read-only
except **`--register`**, which is the one command that installs the timer and
arms it. `--register` is check-first and idempotent: when the timer is already
installed and correct it changes nothing and exits 0. Every other mode — and
`--register` aimed at a scratch root — writes files and prints the scheduler
command without arming anything, which is how this is proven without spending a
launchd slot or a container on this machine. See "Install paths" and
"Registering" below.

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
| `run-timer.sh` | The direct-shell poller the scheduler runs. Platform-aware; runs the U5 bridge's `poll`. |
| `install-timer.sh` | Renders the platform definition into its install path, and with `--register` installs + arms it. Modes: `--dry-run` (default), `--apply`, `--check-identity`, `--register`. |
| `mac/com.blackceo.drama-studio-bridge.plist.template` | macOS LaunchAgent definition. |
| `hostinger/drama-studio-timer.cron.template` | Hostinger container crontab definition. |
| `contabo/drama-studio-timer.cron.template` | Contabo container crontab definition. |
| `checks/run_checks.py` | The runnable checks (A–G), each with a plantable negative control and a true exit code. |

## The direct-shell mechanism

The scheduler runs a shell program and nothing else.

- **macOS** — launchd runs `ProgramArguments = [/bin/sh, .../run-timer.sh]`.
- **Hostinger / Contabo** — cron runs `/bin/sh .../run-timer.sh` with an explicit
  minimal environment.

`run-timer.sh` then runs the U5 bridge's `poll` with absolute paths, exporting
`DRAMA_STUDIO_STATE` so the bridge finds its key and address:

```
python3 <skill>/shared-bridge/studio_bridge.py poll --base-url "$DS_BASE_URL" \
  --skill-root <skill> --runs <platform runs dir>
```

The runs directory is the platform's persistent one: `~/.openclaw/drama-runs`
(macOS), `/data/.openclaw/drama-runs` (Hostinger), `/home/node/.openclaw/drama-runs`
(Contabo).

`poll` is the direct inbox check of SPEC §6: check-in, claim, fetch, replay the
phone's answers, print **one JSON line** `{order_id, run_dir, next}` when an order
was waiting, nothing and exit 0 when none waited. When that one line is printed
and `<skill>/shared-bridge/wake_agent.sh` exists, the timer hands the line to it
as its single argument; when there is no line, or no wake script, it simply
exits with `poll`'s own exit code. There is **no model call, no Claude, no
claude-nine, no 9Router launch, no prompt and no interactive TTY** anywhere on
the path, and no shell is left behind. The timer is not gated on an idle/agent
event: its only triggers are the wall-clock interval (`StartInterval 120` /
`*/2 * * * *`) and load/login (`RunAtLoad`).

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

## Install paths

- **macOS** — definition installs to
  `$HOME/Library/LaunchAgents/com.blackceo.drama-studio-bridge.plist`. The script
  ships inside the skill folder and is not copied (updates replace it in place, as
  the plan requires).
- **Hostinger** — definition at
  `/data/.openclaw/scripts/drama-studio-timer.cron`, script at
  `/data/.openclaw/scripts/run-timer.sh`.
- **Contabo** — definition at
  `/home/node/.openclaw/scripts/drama-studio-timer.cron`, script at
  `/home/node/.openclaw/scripts/run-timer.sh`.

## Registering (`--register`)

`--register` is the only mode that touches a scheduling surface, and it does it
the same way the two installers this script models do:

- **macOS** — writes the plist, then `launchctl bootstrap gui/$(id -u) <plist>`.
  A job that is already loaded with an unchanged plist is success and changes
  nothing; a changed plist is `launchctl bootout` first, then bootstrapped
  (the shape of `platform/mac/service-selfheal/install-service-remediate.sh`).
- **Hostinger / Contabo** — writes the definition and script, then merges
  **one** line into the `node` user's crontab: any previous line containing the
  tag `drama-studio-timer` is dropped first, then ours is appended, so a second
  run can never double the timer. Any other crontab line is preserved (the shape
  of `platform/vps/service-selfheal/install-host-watchdog-cron.sh`, which
  replaces its own line the same way). It never installs the definition file
  wholesale — that would clobber the box's other cron entries.

**Contract.** `--register` exits **0** when the timer is installed or already
installed, and **2** only for a genuine refusal: a wrong identity, an unsupported
platform, or a missing template. It accepts the same flags as every other mode —
`--platform`, `--root`, `--home`, `--skill-root`, `--identity-user`,
`--identity-home` — and the identity rules of check `C` apply to it unchanged: a
temp, non-contract or wrong-leaf HOME is refused, not installed.

**Check-first.** Every `--register` run reads the current state before it writes:
the plist is compared byte for byte, the crontab is read, stripped of our tag and
re-compared. Nothing differing means nothing written, nothing loaded, exit 0.

**Fixtures, never a bare install.** A `--root` that is not the platform's
contract root (`/Users/<user>`, `/data`, `/home/node/.openclaw`) is a scratch
install: the files are written under that root, the scheduler command is printed
and **nothing is armed**. That is the supported way to prove `--register` on a
machine with no launchd slot to spare and no container to run — temp roots and
`--dry-run` only, never a load. On a real box leave `--root` alone (or pass its
contract root) and the scheduler step runs normally.

Manual equivalents, for an operator who would rather type it:

```bash
# macOS
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.blackceo.drama-studio-bridge.plist"
# Hostinger / Contabo — run --register INSIDE the container, as the node user,
# from wherever the skill folder lives on that box:
docker exec -u node <container> bash <skill>/timer-artifacts/install-timer.sh --platform hostinger --register
```

On the containers prefer `--register` over a whole-file
`crontab /path/drama-studio-timer.cron`: that form replaces the user's crontab
outright and drops whatever else the box had scheduled, while `--register`
merges one tagged line and leaves the rest alone.

No other mode runs `launchctl`, `crontab -`, `systemctl` or `pm2`, and none of
them ever will.

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

`--register`'s idempotency and its refusal codes are proven the same way, against
temp roots: run it twice for each platform with `--root` pointed at a scratch
directory and check that the second run reports "already installed", that the
tagged crontab line is present exactly once, that `--check-identity` refuses a
wrong pair with its real exit code, and that an unsupported platform, a wrong
identity and a missing template each exit 2 — with the launchd list, this
machine's crontab and `~/Library/LaunchAgents` identical before and after.

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

The checks themselves install, enable, load and schedule nothing: they render,
read and refuse, and write only inside their own scratch. Registering is done by
`--register` on the target box, never by the checker.

## Deliberate limits

- macOS Task Scheduler / Windows is U15's (999-setup) path, not this unit.
- The timer runs `poll` and, at most, hands its one JSON line to `wake_agent.sh`.
  Deciding what the agent then does with `run_dir` and `next` is the bridge's and
  the flow units' job, not the timer's. With no JSON line the timer prints
  nothing and exits with `poll`'s code.
- The bridge itself ships in U5 (`75-drama-song-ad-factory/shared-bridge/`); this
  timer resolves its path at runtime and fails cleanly when it is absent.
