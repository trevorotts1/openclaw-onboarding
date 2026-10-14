# PLATFORM-PROOF — skill 75 timer, platform by platform (W4-e2e-proof-U2, unit DSF-302)

> **Receipt, not current behaviour (note added by DSR-103, 2026-10-13).** This
> file captures a run made when `install-timer.sh --register` always refused.
> That has since changed: `--register` now installs and arms the timer, and is
> proven against temp roots. See `README.md` → "Registering". Every transcript
> below is left exactly as it was run.

Receipt for `W4-e2e-proof-U2`, rebuilt without Docker on Trevor's order of
2026-10-13 16:38. Each platform is simulated by running the shipped code with
that platform's own environment and paths mapped into a **temp root** on this
Mac, against a fake studio server bound to `127.0.0.1` and speaking the SPEC §2
route contract.

Nothing was installed, registered, scheduled or started. No Docker image, no
container, no client box, no fleet box, no `crontab`, no `launchctl`, no `pm2`.
No key was read from `~/.drama-studio` and no key value appears anywhere in this
file. The test key was generated inside the temp root and only its shape is
reported.

## What was run on

| | |
|---|---|
| Host | the operator Mac, `Darwin 25.3.0`, login user `<operator>` |
| Worktree | `/Users/<operator>/dsf-wt/DSF-302`, branch `unit/DSF-302` at `origin/main` (`5cd1d6145`) |
| Lane (scratch) | `…/DRAMA FIXES OCT 13/run/lanes/DSF-302-lane/` |
| Temp roots | `/tmp/lane-DSF-302-hostinger`, `/tmp/lane-DSF-302-contabo`, `/tmp/lane-DSF-302-mac` |
| Identity shim | `/tmp/lane-DSF-302-bin/id` — prints `node` for `id -un`, else `exec /usr/bin/id`. This Mac's login user is not `node`, so the Hostinger/Contabo **user** rows are simulated with it. It is named here so nobody mistakes it for a real box user. |
| Argv probe | `lanes/DSF-302-lane/probe-skill/shared-bridge/studio_bridge.py` — a stub that writes the argv and environment it was invoked with to a log and exits 0. Used **only** where the real bridge would have written outside this lane. It proves what `run-timer.sh` computes; it is not the shipped bridge. |
| Fake studio | `lanes/DSF-302-lane/fake_studio.py` — `http.server` on `127.0.0.1`, ephemeral port, validates `x-ds-key` against the generated key, serves `/api/studio/checkin`, `/api/studio/orders/<id>`, `/api/studio/orders/<id>/state`. |

The test key, generated inside the lane, never printed:

```
$ python3 -c 'import secrets;print("machine-"+secrets.token_hex(20))' > lanes/DSF-302-lane/state/machine.key
$ python3 -c "k=open('.../state/machine.key').read().strip(); print('key present:',bool(k),'len:',len(k),'prefix:',k.split('-')[0],'sfx_len:',len(k.split('-')[1]))"
key present: True len: 48 prefix: machine sfx_len: 40
```

Server up and refusing a caller with no key (instrument control: the server
answers, so a later `ok` is a real answer and not a dead socket):

```
$ curl -s -o /dev/null -w "health_no_key=%{http_code}\n" -X POST http://127.0.0.1:55327/api/studio/checkin -d '{}'
health_no_key=403
```

Files proven, byte-for-byte unchanged against `origin/main`:

```
$ shasum -a 256 …/timer-artifacts/run-timer.sh …/shared-bridge/studio_bridge.py
89627e32823c4b0072473aee5e8a3ab57b2b321fa282955c414c9c6856d7cd76  …/timer-artifacts/run-timer.sh
b8d3706cc49de4ba4b07515d82dcdfc8fae5e282da70366bf3b97dc1a5cb4956  …/shared-bridge/studio_bridge.py
$ git diff origin/main -- …/run-timer.sh …/studio_bridge.py
(no output — unchanged)
```

---

## 1. mac

This Mac **is** a mac platform box, so the timer runs for real; only its state
folder was redirected into the lane (`DS_STATE_DIR` is a documented override and
the mac guard requires the state dir to be under `$HOME`, which the lane is).

### 1a. `studio_bridge.py poll`, no order waiting

```
$ env -i HOME=/Users/<operator> \
    DRAMA_STUDIO_STATE=<lane>/mac/.drama-studio \
    python3 …/shared-bridge/studio_bridge.py poll \
      --base-url http://127.0.0.1:55327 --skill-root …/75-drama-song-ad-factory \
      --runs <lane>/mac/drama-runs
stdout bytes: 0
stderr: (empty)
exit code: 0
```

Check-in answered, no order waiting, **exit 0 and no output at all** — exactly
SPEC §6.

### 1b. `studio_bridge.py poll`, one TEST order locked

```
$ printf 'DSF302-mac-order-0003\tDSF-302 Mac test order' > <lane>/state/lock
$ env -i HOME=/Users/<operator> DRAMA_STUDIO_STATE=<lane>/mac/.drama-studio \
    python3 …/studio_bridge.py poll --base-url http://127.0.0.1:55327 \
      --skill-root …/75-drama-song-ad-factory --runs <lane>/mac/drama-runs
{"next": "/Library/Developer/CommandLineTools/usr/bin/python3 …/scripts/core/intake_preflight/factory.py next --run-dir <lane>/mac/drama-runs/DSF302-mac-order-0003", "order_id": "DSF302-mac-order-0003", "run_dir": "<lane>/mac/drama-runs/DSF302-mac-order-0003"}
exit code: 0

<lane>/mac/drama-runs
<lane>/mac/drama-runs/DSF302-mac-order-0003
<lane>/mac/drama-runs/DSF302-mac-order-0003/control
<lane>/mac/drama-runs/DSF302-mac-order-0003/control/studio-order.json
```

The run dir appears under the runs path the caller named, holding
`control/studio-order.json` (`{"base_url": "http://127.0.0.1:55327", "client_id":
"dsf302-test-client", "order_id": …, "title": …}`). A grep of the whole run tree
for the key prefix returns nothing — the key never enters a run dir.

### 1c. `run-timer.sh` for real, mac platform

```
$ ls -ld /Users/<operator>/.openclaw/drama-runs
ls: /Users/<operator>/.openclaw/drama-runs: No such file or directory

$ env -i HOME=/Users/<operator> DS_PLATFORM=mac \
    DS_STATE_DIR=<lane>/mac/.drama-studio \
    DS_SKILL_ROOT=/Users/<operator>/dsf-wt/DSF-302/75-drama-song-ad-factory \
    sh …/timer-artifacts/run-timer.sh
stdout: 0 bytes
stderr: (empty)
exit code: 0

$ ls -ld /Users/<operator>/.openclaw/drama-runs
ls: /Users/<operator>/.openclaw/drama-runs: No such file or directory
```

The shipped timer reaches the real bridge and the fake studio, exits 0, prints
nothing, and — because no order was waiting — creates nothing under the
operator's real `~/.openclaw`. The operator Mac is untouched.

### 1d. What `run-timer.sh` computes on mac (argv probe)

```
$ env -i HOME=/Users/<operator> DS_PLATFORM=mac DS_STATE_DIR=<lane>/mac/.drama-studio \
    DS_SKILL_ROOT=<lane>/probe-skill DSF302_PROBE_LOG=<lane>/probe-argv.log \
    sh …/timer-artifacts/run-timer.sh
exit code: 0
  HOME                  = /Users/<operator>
  DRAMA_STUDIO_STATE    = <lane>/mac/.drama-studio
  PATH                  = /usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin
  argv: poll --base-url http://127.0.0.1:55327 --skill-root <lane>/probe-skill --runs /Users/<operator>/.openclaw/drama-runs
```

Every mac path the timer used came from `$HOME` or from an override the caller
supplied. No platform literal appears.

### 1e. Installer, mac

```
$ bash …/timer-artifacts/install-timer.sh --platform mac --dry-run
DRY RUN — nothing written, nothing registered.
  platform : mac
  user     : <operator>
  home     : /Users/<operator>
  state    : /Users/<operator>/.drama-studio  (persistent)
  install  : /Users/<operator>/Library/LaunchAgents/com.blackceo.drama-studio-bridge.plist
  script   : /Users/<operator>/.openclaw/skills/75-drama-song-ad-factory/timer-artifacts/run-timer.sh  (ships with the skill; not copied)
  log      : /Users/<operator>/Library/Logs/openclaw/drama-studio-timer.log
  direct   : /bin/sh …/run-timer.sh  (no model, no interactive session)
  operator registration command (NOT run by this script):
    launchctl bootstrap gui/$(id -u) /Users/<operator>/Library/LaunchAgents/com.blackceo.drama-studio-bridge.plist
```

---

## 2. hostinger

Temp root: `HOME=/tmp/lane-DSF-302-hostinger/data`, state
`<HOME>/.drama-studio`, runs `<HOME>/.openclaw/drama-runs`.

### 2a. `studio_bridge.py poll` under the platform HOME, no order

```
$ env -i HOME=/tmp/lane-DSF-302-hostinger/data PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin \
    DRAMA_STUDIO_STATE=/tmp/lane-DSF-302-hostinger/data/.drama-studio \
    python3 …/shared-bridge/studio_bridge.py poll \
      --base-url http://127.0.0.1:55327 --skill-root …/75-drama-song-ad-factory \
      --runs /tmp/lane-DSF-302-hostinger/data/.openclaw/drama-runs
stdout: 0 bytes
stderr: (empty)
exit code: 0
runs dir after: (empty)
```

Check-in answered, no order, exit 0, no output.

### 2b. `studio_bridge.py poll`, one TEST order locked

```
$ printf 'DSF302-hostinger-order-0001\tDSF-302 Hostinger test order' > <lane>/state/lock
$ env -i HOME=/tmp/lane-DSF-302-hostinger/data \
    DRAMA_STUDIO_STATE=/tmp/lane-DSF-302-hostinger/data/.drama-studio \
    python3 …/studio_bridge.py poll --base-url http://127.0.0.1:55327 \
      --skill-root …/75-drama-song-ad-factory \
      --runs /tmp/lane-DSF-302-hostinger/data/.openclaw/drama-runs
{"next": "…/factory.py next --run-dir /tmp/lane-DSF-302-hostinger/data/.openclaw/drama-runs/DSF302-hostinger-order-0001", "order_id": "DSF302-hostinger-order-0001", "run_dir": "/tmp/lane-DSF-302-hostinger/data/.openclaw/drama-runs/DSF302-hostinger-order-0001"}
exit code: 0

/tmp/lane-DSF-302-hostinger/data/.openclaw/drama-runs/DSF302-hostinger-order-0001
/tmp/lane-DSF-302-hostinger/data/.openclaw/drama-runs/DSF302-hostinger-order-0001/control
/tmp/lane-DSF-302-hostinger/data/.openclaw/drama-runs/DSF302-hostinger-order-0001/control/studio-order.json
{"base_url": "http://127.0.0.1:55327", "client_id": "dsf302-test-client", "order_id": "DSF302-hostinger-order-0001", "title": "DSF-302 Hostinger test order"}
grep -rl "machine-" <runs tree>  ->  none
```

### 2c. `run-timer.sh` under the temp root — **REFUSED by its own guard** (finding)

Unshimmed, this Mac's real login user:

```
$ env -i HOME=/tmp/lane-DSF-302-hostinger/data PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin \
    DS_PLATFORM=hostinger sh …/timer-artifacts/run-timer.sh
ds-timer: hostinger: must run as user 'node', got '<operator>' 1
exit code: 1
```

With the identity shim so the user row reads `node`, the temp-root HOME is
refused:

```
$ env -i HOME=/tmp/lane-DSF-302-hostinger/data PATH=/tmp/lane-DSF-302-bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin \
    DS_PLATFORM=hostinger sh …/timer-artifacts/run-timer.sh
ds-timer: hostinger: HOME must be /data (persistent), got '/tmp/lane-DSF-302-hostinger/data' 1
exit code: 1
```

**This is a real finding, not a failure of the run.** `run-timer.sh` does not
map a temp root: it asserts that `HOME` *is* `/data`. Nothing under the temp
root can satisfy it.

Control, same instrument with a known-good answer (mac platform, same shell,
same host, reaches the poll and exits 0 — shown in §1c): the refusal above is
about the Hostinger identity, not about a broken script or a broken shell.

### 2d. `run-timer.sh` with `HOME=/data` (env only — `/data` is **not** created)

`/data` does not exist on this Mac; it is named in the environment only. The
timer still derives its state path from `$HOME`:

```
$ ls -ld /data
ls: /data: No such file or directory

$ env -i HOME=/data PATH=/tmp/lane-DSF-302-bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin \
    DS_PLATFORM=hostinger sh …/timer-artifacts/run-timer.sh
ds-timer: no studio address at /data/.drama-studio/machine.url — this computer is not paired
exit code: 2
```

Negative control on the same guard, state dir off the platform root:

```
$ env -i HOME=/data … DS_PLATFORM=hostinger DS_STATE_DIR=/tmp/lane-DSF-302-hostinger/elsewhere sh …/run-timer.sh
ds-timer: hostinger: state dir must be under /data, got '/tmp/lane-DSF-302-hostinger/elsewhere' 1
exit code: 1
```

### 2e. What `run-timer.sh` computes on hostinger (argv probe)

Key and address supplied through the script's own `DS_KEY_FILE`/`DS_URL_FILE`
overrides (pointed at the lane), skill root pointed at the argv probe, `HOME=/data`:

```
$ env -i HOME=/data PATH=/tmp/lane-DSF-302-bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin \
    DS_PLATFORM=hostinger DS_URL_FILE=<lane>/state/machine.url DS_KEY_FILE=<lane>/state/machine.key \
    DS_SKILL_ROOT=<lane>/probe-skill DSF302_PROBE_LOG=<lane>/probe-argv.log \
    sh …/timer-artifacts/run-timer.sh
stdout: 0 bytes   stderr: (empty)   exit code: 0

{"DRAMA_STUDIO_STATE": "/data/.drama-studio", "DS_PLATFORM": "hostinger", "HOME": "/data",
 "PATH": "/data/.npm-global/bin:/data/linuxbrew/.linuxbrew/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
 "argv": ["…/probe-skill/shared-bridge/studio_bridge.py", "poll",
          "--base-url", "http://127.0.0.1:55327",
          "--skill-root", "…/probe-skill",
          "--runs", "/data/.openclaw/drama-runs"]}

$ ls -ld /data              ->  ls: /data: No such file or directory
$ ls -ld /data/.openclaw    ->  ls: /data/.openclaw: No such file or directory
```

So the shipped timer's own Hostinger numbers are
`DRAMA_STUDIO_STATE=/data/.drama-studio` and `--runs /data/.openclaw/drama-runs`,
and **no Mac path appears anywhere in what it computed.**

### 2f. Installer, hostinger

```
$ bash …/install-timer.sh --platform hostinger --dry-run --identity-user node --identity-home /data
DRY RUN — nothing written, nothing registered.
  platform : hostinger
  user     : node
  home     : /data
  state    : /data/.drama-studio  (persistent)
  install  : /data/.openclaw/scripts/drama-studio-timer.cron
  script   : /data/.openclaw/scripts/run-timer.sh
  log      : /data/.openclaw/logs/drama-studio-timer.log
  direct   : /bin/sh /data/.openclaw/scripts/run-timer.sh  (no model, no interactive session)
  operator registration command (NOT run by this script):
    docker exec -u node <container> sh -c 'crontab /data/.openclaw/scripts/drama-studio-timer.cron'

# negative control: a temp-root HOME is refused by design
$ bash …/install-timer.sh --platform hostinger --dry-run --identity-user node --identity-home /tmp/lane-DSF-302-hostinger/data
refused: HOME '/tmp/lane-DSF-302-hostinger/data' is a temp path (not persistent)
refused: HOME '/tmp/lane-DSF-302-hostinger/data' does not match hostinger contract (^/data$)
dry-run: identity refused (see above); nothing written
exit=1

# --register always refuses and prints the operator command
$ bash …/install-timer.sh --platform contabo --register
refused: this repository script never registers a timer.
         Registration is a deliberate operator action on the box:
           docker exec -u node <container> sh -c 'crontab /home/node/.openclaw/scripts/drama-studio-timer.cron'
exit=2
```

---

## 3. contabo

Temp root: `HOME=/tmp/lane-DSF-302-contabo/home/node`, state
`<HOME>/.openclaw/.drama-studio`, runs `<HOME>/.openclaw/drama-runs`.

### 3a. `studio_bridge.py poll` under the platform HOME, no order

```
$ env -i HOME=/tmp/lane-DSF-302-contabo/home/node PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin \
    DRAMA_STUDIO_STATE=/tmp/lane-DSF-302-contabo/home/node/.openclaw/.drama-studio \
    python3 …/studio_bridge.py poll --base-url http://127.0.0.1:55327 \
      --skill-root …/75-drama-song-ad-factory \
      --runs /tmp/lane-DSF-302-contabo/home/node/.openclaw/drama-runs
stdout: 0 bytes   stderr: (empty)   exit code: 0
```

### 3b. `studio_bridge.py poll`, one TEST order locked

```
$ printf 'DSF302-contabo-order-0002\tDSF-302 Contabo test order' > <lane>/state/lock
$ env -i HOME=/tmp/lane-DSF-302-contabo/home/node … python3 …/studio_bridge.py poll …
{"next": "…/factory.py next --run-dir /tmp/lane-DSF-302-contabo/home/node/.openclaw/drama-runs/DSF302-contabo-order-0002", "order_id": "DSF302-contabo-order-0002", "run_dir": "/tmp/lane-DSF-302-contabo/home/node/.openclaw/drama-runs/DSF302-contabo-order-0002"}
exit code: 0

/tmp/lane-DSF-302-contabo/home/node/.openclaw/drama-runs/DSF302-contabo-order-0002
/tmp/lane-DSF-302-contabo/home/node/.openclaw/drama-runs/DSF302-contabo-order-0002/control
/tmp/lane-DSF-302-contabo/home/node/.openclaw/drama-runs/DSF302-contabo-order-0002/control/studio-order.json
state dir: machine.key machine.url studio.db studio.db-shm studio.db-wal
```

### 3c. `run-timer.sh` under the temp root — **REFUSED by its own guard** (finding)

```
# real identity
$ env -i HOME=/tmp/lane-DSF-302-contabo/home/node DS_PLATFORM=contabo sh …/run-timer.sh
ds-timer: contabo: must run as user 'node', got '<operator>' 1
exit code: 1

# identity shim -> user 'node'
$ env -i HOME=/tmp/lane-DSF-302-contabo/home/node PATH=/tmp/lane-DSF-302-bin:… DS_PLATFORM=contabo sh …/run-timer.sh
ds-timer: contabo: HOME must be /home/node, got '/tmp/lane-DSF-302-contabo/home/node' 1
exit code: 1
```

Same finding as Hostinger: the timer wants `HOME` to *be* `/home/node`.

### 3d. `run-timer.sh` with `HOME=/home/node` (env only — `/home/node` is not created)

```
$ ls -ld /home/node
ls: /home/node: No such file or directory

$ env -i HOME=/home/node PATH=/tmp/lane-DSF-302-bin:… DS_PLATFORM=contabo sh …/run-timer.sh
ds-timer: no studio address at /home/node/.openclaw/.drama-studio/machine.url — this computer is not paired
exit code: 2
```

Note the derived state path: `HOME/.openclaw/.drama-studio` — the volume, not
the ephemeral leaf, which is the Contabo trap SPEC §2 names.

Negative controls on the same guard stack:

```
# state dir off the volume
$ env -i HOME=/home/node … DS_PLATFORM=contabo DS_STATE_DIR=/tmp/lane-DSF-302-contabo/ephemeral sh …/run-timer.sh
ds-timer: contabo: state dir must be persistent (/home/node/.openclaw/...), got '/tmp/lane-DSF-302-contabo/ephemeral' 1
exit code: 1

# PM2_HOME off the volume
$ env -i HOME=/home/node … DS_PLATFORM=contabo PM2_HOME=/home/node/.cache/pm2 sh …/run-timer.sh
ds-timer: contabo: PM2_HOME must be under /home/node/.openclaw, got '/home/node/.cache/pm2' 1
exit code: 1
```

### 3e. What `run-timer.sh` computes on contabo (argv probe)

```
$ env -i HOME=/home/node PATH=/tmp/lane-DSF-302-bin:… DS_PLATFORM=contabo \
    DS_URL_FILE=<lane>/state/machine.url DS_KEY_FILE=<lane>/state/machine.key \
    DS_SKILL_ROOT=<lane>/probe-skill DSF302_PROBE_LOG=<lane>/probe-argv.log sh …/run-timer.sh
stdout: 0 bytes   stderr: (empty)   exit code: 0

{"DRAMA_STUDIO_STATE": "/home/node/.openclaw/.drama-studio", "DS_PLATFORM": "contabo", "HOME": "/home/node",
 "PATH": "/home/node/.openclaw/npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
 "argv": ["…/probe-skill/shared-bridge/studio_bridge.py", "poll",
          "--base-url", "http://127.0.0.1:55327",
          "--skill-root", "…/probe-skill",
          "--runs", "/home/node/.openclaw/drama-runs"]}

$ ls -ld /home/node  ->  ls: /home/node: No such file or directory
```

### 3f. Installer, contabo

```
$ bash …/install-timer.sh --platform contabo --dry-run --identity-user node --identity-home /home/node
DRY RUN — nothing written, nothing registered.
  platform : contabo
  user     : node
  home     : /home/node
  state    : /home/node/.openclaw/.drama-studio  (persistent)
  install  : /home/node/.openclaw/scripts/drama-studio-timer.cron
  script   : /home/node/.openclaw/scripts/run-timer.sh
  log      : /home/node/.openclaw/logs/drama-studio-timer.log
  direct   : /bin/sh /home/node/.openclaw/scripts/run-timer.sh  (no model, no interactive session)
  operator registration command (NOT run by this script):
    docker exec -u node <container> sh -c 'crontab /home/node/.openclaw/scripts/drama-studio-timer.cron'
```

---

## 4. The finding Trevor named: is each path COMPUTED FROM HOME, or PINNED?

Both, and which one it is differs per path. The **formulas** are written in
terms of `$HOME`; the **guards** pin `$HOME` and the state dir to exact absolute
literals. On a real box the two coincide, so the timer works. Under a temp root
they cannot, so the timer refuses — which is why the temp-root mapping above is
refused and is recorded as a finding rather than a failure.

### `run-timer.sh`

| Path | Mechanism | Where | Meaning on a real box |
|---|---|---|---|
| `RUN_USER` | taken from the environment, then compared to a literal | `run-timer.sh:43` (`id -un`), compared at `:57` (hostinger) and `:66` (contabo) | must literally be user `node`; on this Mac it is `<operator>` |
| mac `HOME` | pattern + leaf check, both derived from the environment | `run-timer.sh:49-53` | any `/Users/<user>` whose leaf equals the user — genuinely HOME-derived |
| hostinger `HOME` | **absolute literal** | `run-timer.sh:58-61` (`/data`) | `HOME` must *be* `/data`; a temp root is refused |
| contabo `HOME` | **absolute literal** | `run-timer.sh:67-70` (`/home/node`) | `HOME` must *be* `/home/node`; a temp root is refused |
| contabo `PM2_HOME` | **absolute literal prefix** | `run-timer.sh:72-77` (`/home/node/.openclaw/*`) | must be on the volume when set |
| mac state dir | **computed from `$HOME`** | `run-timer.sh:86` (`$HOME/.drama-studio`), overridable at `:90` (`DS_STATE_DIR`), guard `:96` (`$HOME/*`) | derived; the guard follows HOME too |
| hostinger state dir | formula **computed from `$HOME`**, guard is an **absolute literal** | `run-timer.sh:87` (`$HOME/.drama-studio`) vs `:97` (`/data/*`) | the two agree only because the guard already forced `HOME=/data` |
| contabo state dir | formula **computed from `$HOME`**, guard is an **absolute literal** | `run-timer.sh:88` (`$HOME/.openclaw/.drama-studio`) vs `:98` (`/home/node/.openclaw/*`) | same |
| `machine.key` / `machine.url` | derived from the state dir; **no platform guard** | `run-timer.sh:101-102` | caller-overridable (`DS_KEY_FILE`, `DS_URL_FILE`) — used by the probes above |
| `PATH` | **absolute literal per platform** | `run-timer.sh:108` (mac), `:109` (hostinger), `:110` (contabo) | overwritten, never inherited; the cron/launchd environment is explicit |
| skill root | **computed from `$HOME`**, then the script's own dir | `run-timer.sh:129-135` (`$HOME/.openclaw/skills/…`, `$HOME/.claude/skills/…`, `$(dirname $0)/..`) | derived |
| mac runs dir | **computed from `$HOME`** | `run-timer.sh:151` (`$HOME/.openclaw/drama-runs`) | derived — proven at runtime in §1d |
| hostinger runs dir | **absolute literal** | `run-timer.sh:152` (`/data/.openclaw/drama-runs`) | not derived; proven at runtime in §2e |
| contabo runs dir | **absolute literal** | `run-timer.sh:153` (`/home/node/.openclaw/drama-runs`) | not derived; proven at runtime in §3e |
| `DRAMA_STUDIO_STATE` export | derived from the (already guarded) state dir | `run-timer.sh:148` | this is what the bridge reads |

### `shared-bridge/studio_bridge.py`

| Path | Mechanism | Where | Meaning |
|---|---|---|---|
| state folder | **computed from the environment's `HOME`** | `studio_bridge.py:103-106` (`_home_state`: `pathlib.Path(home) / ".drama-studio"`, `home` read from `os.environ["HOME"]`), `:109-113` (`state_dir`: `DRAMA_STUDIO_STATE` else `_home_state`) | no literal anywhere |
| key lookup | state dir, then HOME state | `studio_bridge.py:147` | both derived |
| studio address | `--base-url`, else state dir, else HOME state | `studio_bridge.py:155-160` | all derived |
| claim ledger | `<state folder>/studio.db` | `studio_bridge.py:693` | derived |
| runs dir | **the `--runs` argument only** | `studio_bridge.py:709` (`pathlib.Path(args.runs).expanduser() / order_id`) | the bridge has no platform knowledge at all; the caller decides |

Runtime proof of the bridge's derivation, calling the shipped functions with
three different `HOME` values and no `DRAMA_STUDIO_STATE`:

```
$ env -i HOME=/tmp/lane-DSF-302-hostinger/data python3 -c "… print(b.state_dir(), b._home_state())"
  state_dir()=/tmp/lane-DSF-302-hostinger/data/.drama-studio            _home_state()=/tmp/lane-DSF-302-hostinger/data/.drama-studio
$ env -i HOME=/tmp/lane-DSF-302-contabo/home/node python3 -c "…"
  state_dir()=/tmp/lane-DSF-302-contabo/home/node/.drama-studio         _home_state()=/tmp/lane-DSF-302-contabo/home/node/.drama-studio
$ env -i HOME=/Users/<operator> python3 -c "…"
  state_dir()=/Users/<operator>/.drama-studio                      _home_state()=/Users/<operator>/.drama-studio
# HOME unset -> falls back to pathlib.Path.home()
$ env -i python3 -c "…"
  state_dir()= /Users/<operator>/.drama-studio
```

No Mac path is baked into the bridge: with a Hostinger or Contabo `HOME` it
derives that platform's path and nothing else.

### `install-timer.sh`

| Path | Mechanism | Where |
|---|---|---|
| mac `HOME` | regex over the caller's value, derived | `install-timer.sh:78` (`^/Users/[A-Za-z0-9._-]+$`), validated `:104-110` |
| hostinger `HOME` | **absolute literal** | `install-timer.sh:81-82` (`DEF_HOME=/data`, `HOME_RE='^/data$'`) |
| contabo `HOME` | **absolute literal** | `install-timer.sh:85-86` (`DEF_HOME=/home/node`, `HOME_RE='^/home/node$'`) |
| temp-root refusal | explicit, by design | `install-timer.sh:99-100` (`/tmp/*`, `/var/tmp/*`, `/private/tmp/*`) |
| store dir | derived from the (guarded) root/home | `install-timer.sh:146` (mac), `:160` (hostinger), `:171` (contabo) |

### What that means for a real box

On a real Hostinger or Contabo container the timer's formula and its literal
agree — `HOME` *is* `/data` or `/home/node`, the user *is* `node`, and the
derived state dir lands exactly on the literal the guard requires. So the timer
works there, and it works because those two facts are true, not because the
code is portable. **The timer does not derive its paths from whatever
environment it is handed; it requires those exact absolute paths to exist.**
That is the deliberate design of SPEC §2 (persistent volume, wiped ephemeral
layer), and the guards are what enforce it — a wrong path is refused, never
silently used. The practical consequence is only this: the platform paths
cannot be exercised by pointing `HOME` at a temp root. The bridge underneath
them can, and was.

### One cosmetic defect, no code changed

`run-timer.sh:30` is `die() { say "$*"; exit "${2:-1}"; }`, so the exit code
carried as the second argument is printed as part of the message:
`ds-timer: hostinger: must run as user 'node', got '<operator>' 1`. The
code is right, the message carries a stray `1`. Recorded, not fixed — this unit
makes no code change.

---

## 5. In-container runs — UNDETERMINED

A real `node:22-bookworm` container per platform was **not** run. Docker is
absent on this Mac and starting or installing a daemon is out of scope for this
unit (Trevor's order: no Docker, no install, no client box).

Docker evidence, re-collected on this run:

```
$ docker version
Client: Docker Engine - Community
 Version:           29.7.2
 …
 Context:           default
failed to connect to the docker API at unix:///var/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /var/run/docker.sock: connect: no such file or directory

$ docker info
Client: …
Server:
failed to connect to the docker API at unix:///var/run/docker.sock; … no such file or directory

$ docker ps ; echo "exit=$?"
failed to connect to the docker API at unix:///var/run/docker.sock; … no such file or directory
exit=1

# instrument control, same CLI, same shell, same host, known non-empty answer
$ docker context ls
NAME        DESCRIPTION                               DOCKER ENDPOINT               ERROR
default *   Current DOCKER_HOST based configuration   unix:///var/run/docker.sock
```

The client works (the control prints a row) and the daemon socket is missing, so
the fault is the absent daemon, not a broken instrument.

An in-container run is therefore **UNDETERMINED** — not BLOCKED. The container
row stays open for a real client box, which remains a "Needs Trevor" item.

Supplementary, same instrument, shipped checker:

```
$ python3 …/timer-artifacts/checks/run_checks.py
U6 timer-artifacts checks
  [A1 mac pars] PASS …   [A1-neg] PASS …   [A2 host pars] PASS …   [A2-neg] PASS …
  [A3 cont pars] PASS …  [A3-neg] PASS …   [B mac direct] PASS …   [B host direct] PASS …
  [B cont direct] PASS … [B script] PASS … [B-neg] PASS …          [C identity] PASS …
  [D restart] PASS …     [D-neg1] PASS …   [D-neg2] PASS …         [E dry-run] PASS …
  [E-neg] PASS …         [E register] PASS… [G poller] PASS …      [F no-secret] PASS …
  [F-neg] PASS …         [F env-ref] PASS …
22/22 checks passed
exit=0
```

That covers definition parsing, the direct-shell invocation and the
identity/state-path refusals. It does **not** cover a container, and it is not
offered as one.

---

## 6. Verdict per platform

| Platform | Verdict | What is actually proved |
|---|---|---|
| **mac** | **PROVEN** | The shipped `run-timer.sh` runs end-to-end on this Mac against the fake studio: check-in, exit 0, no output, nothing written outside the lane (§1c). The bridge claims a locked TEST order and lands its run dir under the caller's runs path (§1b). Every mac path is computed from `$HOME` (§1d, §4). |
| **hostinger** | **UNDETERMINED** | Bridge layer PROVEN by temp-root simulation: poll checks in, finds no order, exit 0 with no output (§2a); with a locked TEST order the run dir appears under the platform runs path (§2b). The timer's own Hostinger numbers are proven at runtime as `/data/.drama-studio` and `/data/.openclaw/drama-runs`, with no Mac path in them (§2e). But a temp-root run of `run-timer.sh` is refused by its own guard (§2c) and a **real** run needs user `node` with `HOME=/data` in a container or on a real box — neither exists here. |
| **contabo** | **UNDETERMINED** | Same split. Bridge layer PROVEN by temp-root simulation (§3a, §3b). The timer derives `/home/node/.openclaw/.drama-studio` and runs `/home/node/.openclaw/drama-runs`, and refuses a state dir off the volume and a `PM2_HOME` off the volume (§3d, §3e). A real run needs user `node` with `HOME=/home/node`; UNDETERMINED. |

Nothing in this receipt was BLOCKED. No code was changed, no version or CHANGELOG
entry was made, no key was read from `~/.drama-studio` and no key value is
printed here.
