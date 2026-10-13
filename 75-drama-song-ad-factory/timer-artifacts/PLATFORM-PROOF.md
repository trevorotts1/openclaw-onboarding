# PLATFORM-PROOF — Hostinger and Contabo timer simulation (W4-e2e-proof-U2)

Unit: **DSF-301** (`W4-e2e-proof-U2`). Branch `unit/DSF-301`, base `origin/main` at
`762408cfb` (batch #1957 — `run-timer.sh` and `shared-bridge/studio_bridge.py` already merged).

**Result: BLOCKED — docker is not available on this operator Mac.**

This unit is required to simulate two Linux client platforms (Hostinger and Contabo) by running a
`node:22-bookworm` container per platform and driving `run-timer.sh` inside it. Docker is not
available here, so **no container simulation was run and no Hostinger or Contabo platform line is
proven**. Nothing below is a substitute for that simulation, and nothing in this file should be
read as proof that either platform works.

BUILD-PLAN.md `W4-e2e-proof-U2` names this exact outcome:

> If docker is not available: BLOCKED "docker not available" (the conductor files
> "Needs Trevor: name a Hostinger and a Contabo canary box").

No key was read, generated or printed for this unit. No file under `~/.drama-studio` was opened. No
client box or fleet box was contacted — this was a local check of this Mac only.

---

## 1. The docker check — every command and its verbatim output

Host: `Darwin 25.3.0` (macOS, arm64), operator Mac Mini. Working tree
`/Users/blackceomacmini/dsf-wt/DSF-301`.

### 1.1 `docker version` — client present, server absent

```console
$ docker version
Client: Docker Engine - Community
 Version:           29.7.2
 API version:       1.55
 Go version:        go1.26.5
 Git commit:        a7dcaa6fdb
 Built:             Wed Aug  5 17:34:15 2026
 OS/Arch:           darwin/arm64
 Context:           default
failed to connect to the docker API at unix:///var/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /var/run/docker.sock: connect: no such file or directory
```

The client half prints, then the server half fails: no daemon socket at `/var/run/docker.sock`.

### 1.2 `docker info` — no server section

```console
$ docker info
Client: Docker Engine - Community
 Version:    29.7.2
 Context:    default
 Debug Mode: false
 Plugins:
  compose: Docker Compose (Docker Inc.)
    Version:  5.5.0
    Path:     /Users/blackceomacmini/.docker/cli-plugins/docker-compose

Server:
failed to connect to the docker API at unix:///var/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /var/run/docker.sock: connect: no such file or directory
```

`Server:` is empty apart from the connection error — there is no engine to run a container.

### 1.3 `docker run --rm hello-world` — the definitive run attempt

```console
$ docker run --rm hello-world
failed to connect to the docker API at unix:///var/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /var/run/docker.sock: connect: no such file or directory
$ echo $?
1
```

Exit 1. No container was created, pulled or run on this machine by this unit.

### 1.4 Control — is it the instrument or the target?

The same docker CLI, in the same shell, resolves a real answer when one exists
(`docker context ls` and `docker info`'s own client block both print), so the CLI is functional and
the failure is specifically the missing daemon:

```console
$ docker context ls
NAME        DESCRIPTION                               DOCKER ENDPOINT               ERROR
default *   Current DOCKER_HOST based configuration   unix:///var/run/docker.sock
```

```console
$ cat ~/.docker/config.json
{
	"auths": {}
}
```

There is no alternate context pointing at another host, and `DOCKER_HOST` is unset.

### 1.5 There is no daemon to start — Docker Desktop and every alternative runtime are absent

```console
$ ls -d /Applications/Docker.app
ls: /Applications/Docker.app: No such file or directory

$ command -v colima podman limactl
<no output; exit 1>

$ brew list --formula | grep -iE 'docker|colima|podman|lima'
docker
docker-compose
```

Only the brew `docker` **client** and `docker-compose` are installed. There is no Docker.app to
open, and no colima / podman / lima daemon that could supply a docker-compatible endpoint.
`~/.docker/` exists and contains only `cli-plugins/`, `contexts/` and a 16-byte `config.json` — a
client install, never a running engine.

Starting a daemon would mean installing new software on the operator Mac. That is out of scope for
this unit, so it was not done.

---

## 2. Hostinger platform line — NOT PROVEN

Required (BUILD-PLAN.md `W4-e2e-proof-U2`): a `node:22-bookworm` container as `-u node` with
`HOME=/data`, a volume mounted at `/data`, the skill mounted read-only, a **test** `machine.key` and
`machine.url` in `/data/.drama-studio`, then `DS_PLATFORM=hostinger sh run-timer.sh` — poll runs,
finds no order, exits 0, and the state paths are `/data/.drama-studio` and `/data/.openclaw/drama-runs`.
Then a second run with one locked TEST order, whose run dir must appear under
`/data/.openclaw/drama-runs`.

**No command was run inside any container. The block above (§1.3) is the whole of the attempt.**

What the container would have had to show, and its current status:

| Claim | Status |
| --- | --- |
| Poll runs as user `node` with `HOME=/data`, finds no order, exits 0 | **not proven** |
| State dir resolves to `/data/.drama-studio` | **not proven** |
| Runs dir resolves to `/data/.openclaw/drama-runs` | **not proven** |
| A locked TEST order produces a run dir under `/data/.openclaw/drama-runs` | **not proven** |

The platform's *declared* contract, for the record — this is what `run-timer.sh` enforces by
refusal, read from the merged file, **not** a runtime result:

```sh
hostinger)
    # Hostinger client container: service user `node`, persistent HOME is /data.
    [ "$RUN_USER" = "node" ] || die "hostinger: must run as user 'node', got '$RUN_USER'" 1
    case "$HOME" in
      /data) : ;;
      *) die "hostinger: HOME must be /data (persistent), got '${HOME:-<unset>}'" 1
    esac
    ;;
```

```sh
hostinger) DEFAULT_STATE="$HOME/.drama-studio" ;;               # HOME=/data, persistent
...
hostinger) RUNS_DIR="/data/.openclaw/drama-runs" ;;
```

---

## 3. Contabo platform line — NOT PROVEN

Required: same container as `-u node` with `HOME=/home/node`, a volume at `/home/node/.openclaw`,
the skill mounted read-only, a **test** `machine.key` and `machine.url` in
`/home/node/.openclaw/.drama-studio`, then `DS_PLATFORM=contabo sh run-timer.sh` — poll runs, finds
no order, exits 0, state paths are the platform's own (`/home/node/.openclaw/.drama-studio`,
persistent runs dir `/home/node/.openclaw/drama-runs`). Then one locked TEST order, whose run dir
must appear under `/home/node/.openclaw/drama-runs`.

**No command was run inside any container. The block above (§1.3) is the whole of the attempt.**

| Claim | Status |
| --- | --- |
| Poll runs as user `node` with `HOME=/home/node`, finds no order, exits 0 | **not proven** |
| State dir resolves to `/home/node/.openclaw/.drama-studio` (not the ephemeral `$HOME`) | **not proven** |
| Runs dir resolves to `/home/node/.openclaw/drama-runs` | **not proven** |
| A locked TEST order produces a run dir under `/home/node/.openclaw/drama-runs` | **not proven** |
| Contabo's ephemeral-`$HOME` trap is escaped in a live container recreate | **not proven** |

The declared contract, read from the merged file — again refusal logic, not a runtime result:

```sh
contabo)
    # Contabo client container: user `node`; HOME is the EPHEMERAL layer, so all
    # persistent state (key, address, state dir) must live under /home/node/.openclaw.
    [ "$RUN_USER" = "node" ] || die "contabo: must run as user 'node', got '$RUN_USER'" 1
    case "$HOME" in
      /home/node) : ;;
      *) die "contabo: HOME must be /home/node, got '${HOME:-<unset>}'" 1
    esac
```

```sh
contabo) DEFAULT_STATE="$HOME/.openclaw/.drama-studio" ;;      # volume, not $HOME leaf
...
contabo) RUNS_DIR="/home/node/.openclaw/drama-runs" ;;
```

---

## 4. Supplementary evidence — what WAS run, and what it does not cover

This is not the platform simulation and does not stand in for it. The shipped static checker for the
same two platforms was run on this Mac, from this worktree, and passes:

```console
$ python3 75-drama-song-ad-factory/timer-artifacts/checks/run_checks.py
  scratch: /var/folders/yf/zc5k46g93zs1dp56646v91rm0000gn/T/ds-timer-check-w2t4brmd
  [A1 mac pars] PASS exit=0  rendered LaunchAgent parses
  [    A1-neg] PASS exit=0  malformed plist rejected non-zero
  [A2 host pars] PASS exit=0  cron line parses
  [    A2-neg] PASS exit=0  malformed (missing field) cron rejected
  [A3 cont pars] PASS exit=0  cron line parses
  [    A3-neg] PASS exit=0  malformed (bad step) cron rejected
  [B mac direct] PASS exit=0  direct /bin/sh, no model/idle token, no interactive token
  [B host direct] PASS exit=0  direct /bin/sh, no model/idle token, no interactive token
  [B cont direct] PASS exit=0  direct /bin/sh, no model/idle token, no interactive token
  [  B script] PASS exit=0  run-timer.sh execs python3 directly, no model/interactive token on the exec line
  [     B-neg] PASS exit=0  idle/model-event definition rejected (WatchPaths + claude)
  [C identity] PASS exit=0  mac good->0:ok mac bad-user->1:ok mac bad-path->1:ok host good->0:ok host bad-user->1:ok cont good->0:ok cont bad-user->1:ok cont bad-path->1:ok
  [ D restart] PASS exit=0  mac RunAtLoad+120s no-KeepAlive; host/cont state on persistent roots
  [    D-neg1] PASS exit=0  plist missing RunAtLoad rejected (no login/reboot run)
  [    D-neg2] PASS exit=0  contabo state on ephemeral $HOME rejected
  [ E dry-run] PASS exit=0  dry-run exit=0, no file created anywhere in scratch
  [     E-neg] PASS exit=0  apply detected 1 written file(s) -> detector discriminates
  [E register] PASS exit=0  no LaunchAgent/crontab written by the dry-run path
  [  G poller] PASS exit=0  contabo user enforced on mac: rc=1ok | mac wrong state path: rc=1ok | mac good identity, unpaired -> refused 2: rc=2ok
  [F no-secret] PASS exit=0  no credential literal in any shipped timer file
  [     F-neg] PASS exit=0  planted secret detected by same scanner
  [ F env-ref] PASS exit=0  run-timer.sh reads the key from its 0600 store and exports DS_KEY (env only)

22/22 checks passed
$ echo $?
0
```

What that 22/22 covers: the shipped plist and cron definitions parse, the definitions are direct
shell and not model/idle gated, the identity and state-path *refusals* fire (including the Contabo
ephemeral-`$HOME` rejection), the dry-run writes nothing, and no timer file carries a credential
literal.

What it explicitly does **not** cover, and must not be confused with: a real Linux container
actually running `run-timer.sh` as user `node`, a real network poll against a studio endpoint, a
real claim of a test order, or a run directory actually appearing on a platform volume. Every one of
those remains unproven — they are the §2 and §3 rows above.

---

## 5. Final section — which platform lines are proven, plainly

**Proven on this Mac: nothing about either platform at runtime.**

| Platform line | Verdict |
| --- | --- |
| Hostinger — `DS_PLATFORM=hostinger sh run-timer.sh` polls, exits 0, state paths are `/data/.drama-studio` and `/data/.openclaw/drama-runs` | **NOT PROVEN** (no container available) |
| Hostinger — a locked TEST order lands a run dir under `/data/.openclaw/drama-runs` | **NOT PROVEN** (no container available) |
| Contabo — `DS_PLATFORM=contabo sh run-timer.sh` polls, exits 0, state paths are `/home/node/.openclaw/.drama-studio` and `/home/node/.openclaw/drama-runs` | **NOT PROVEN** (no container available) |
| Contabo — a locked TEST order lands a run dir under `/home/node/.openclaw/drama-runs` | **NOT PROVEN** (no container available) |
| The timer definitions and refusal logic are statically consistent for both platforms | proven (§4, 22/22 static checks) — this is **not** a runtime platform proof |

**Why:** `docker version`, `docker info` and `docker run --rm hello-world` all fail with
`dial unix /var/run/docker.sock: connect: no such file or directory`, and there is no Docker Desktop,
colima, podman or lima on this Mac to start a daemon from (§1).

**Correct outcome per BUILD-PLAN.md:** BLOCKED — "docker not available". The conductor files
**"Needs Trevor: name a Hostinger and a Contabo canary box"**, so W4-e2e-proof-U1 and this unit's
remaining rows can be run on real boxes. No code was changed, and no version or CHANGELOG edit was
made; this branch adds this one file.
