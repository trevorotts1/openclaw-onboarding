# Agnes platform proof — Hostinger and Contabo container simulation (W4-proof-U2)

Unit **W4-proof-U2** · plan row `W4-proof-U2` · proves **SPEC acceptance 2** ("Platforms") for the two
container rows of SPEC **A12**. Receipt only: one new file, no code change, no version bump, no
CHANGELOG edit, no Agnes call, no KIE call, no network.

| | |
|---|---|
| Date | 2026-10-15 (times UTC) |
| Repo / branch | `trevorotts1/openclaw-onboarding`, worktree `/Users/<operator>/agnes-wt/W4-proof-U2`, branch `unit/AGN-W4-proof-U2`, base `origin/main` = `1e1c12dcc0ad336d24c13986973e885e58d95954` |
| Machine | operator Mac Mini only (its hostname is deliberately not recorded in a repo file) — never a client or fleet box |
| Verdict | **BLOCKED — docker not available** on the machine that has to run the container simulation |

---

## 1. Verdict

SPEC acceptance 2 asks for "Hostinger and Contabo container simulation of key lookup, remembered answer
path and quota ledger path surviving a container recreate; tesseract present or `OCR_UNAVAILABLE`".
The BUILD-PLAN `W4-proof-U2` line states the rule for this exact case: **"Docker unavailable → BLOCKED."**

Docker is unavailable on this machine: the client is installed, no daemon exists anywhere on it. So
**nothing that needs a container was run, and no container-survives-recreate result is claimed anywhere
in this receipt.** Two independent facts block the simulation:

1. **No docker daemon** (section 2) — there is nothing to start a container with, and installing a
   container runtime on the operator box is not this unit's to do.
2. **The code under test is not on `origin/main` at this base** (section 6) — `scripts/core/agnes_access/`,
   `scripts/core/agnes_quota/` and `scripts/core/onscreen_text/` do not exist at `1e1c12dcc`; wave 1 has
   not merged. A container run at this base could only exercise SPEC-derived fixtures, not the modules.

---

## 2. Instrument probe — docker availability

Raw capture: `/tmp/<operator>-W4-proof-U2-docker-probe.txt` (73 lines / 2049 bytes),
reproduced here line by line with its exit codes.

```
$ command -v docker
/opt/homebrew/bin/docker
  EXIT=0
$ docker --version
Docker version 29.7.2, build a7dcaa6fdb
  EXIT=0
$ docker version --format '{{.Client.Version}}'
29.7.2
  EXIT=1          # the format flag still asks the server, so this too ends at the socket
$ command -v dockerd
  EXIT=1          # no daemon binary anywhere on PATH
$ ls /opt/homebrew/Cellar/docker/29.7.2/bin/
docker            # the Homebrew `docker` formula ships the client only
  EXIT=0
$ ls -l /var/run/docker.sock
lrwxr-xr-x  1 root  daemon  46 Oct 11 12:19 /var/run/docker.sock -> /Users/<operator>/.docker/run/docker.sock
  EXIT=0
$ readlink /var/run/docker.sock
/Users/<operator>/.docker/run/docker.sock
  EXIT=0
$ test -S "$(readlink /var/run/docker.sock)"
  EXIT=1          # the symlink target does not exist: no daemon has ever started here
$ docker info
Server:
failed to connect to the docker API at unix:///var/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /var/run/docker.sock: connect: no such file or directory
  EXIT=1
$ docker images ; docker ps
failed to connect to the docker API at unix:///var/run/docker.sock; ... no such file or directory
  EXIT=1 (both)
$ docker context ls
NAME        DESCRIPTION                               DOCKER ENDPOINT               ERROR
default *   Current DOCKER_HOST based configuration   unix:///var/run/docker.sock
  EXIT=0         # one context, the same dead socket; no remote context
```

### Known-good control (the check is not broken)

`command -v docker` → **EXIT=0** and `docker --version` → **EXIT=0** printing `Docker version 29.7.2`.
The instrument runs and answers on this same machine, same shell, same transport — so the negative
below is a fact about the daemon, not a broken probe.

### Sources checked (negative-result contract)

| Source | Command | Result |
|---|---|---|
| docker client | `command -v docker` | present, `/opt/homebrew/bin/docker` (Homebrew formula `docker` 29.7.2) |
| docker daemon binary | `command -v dockerd`; `ls /opt/homebrew/Cellar/docker/29.7.2/bin/` | **absent** — package contains `docker` only |
| socket | `ls -l /var/run/docker.sock`; `test -S <target>` | dangling symlink to `~/.docker/run/docker.sock`; target missing |
| Docker Desktop | `ls -d /Applications/Docker.app /Applications/Docker Desktop.app` | **absent** (EXIT=1) |
| Homebrew casks | `brew list --cask \| grep -Ei 'docker\|orb\|podman\|rancher'` | **absent** (EXIT=1) |
| alternative runtimes | `command -v colima orbctl podman nerdctl limactl finch` | **all absent** (EXIT=1 each); only a leftover `~/.lima/_config`, no `limactl` |
| docker-compose | `command -v docker-compose` | present — client only, talks to the same dead socket |
| local daemon ports | `nc -z -G 2 127.0.0.1 2375` / `2376` | **closed** (EXIT=1 each) |
| daemon running | `pgrep -fl Docker` | no match |

**Not checked, on purpose:** any remote/fleet docker host, and SSH to the Hostinger or Contabo boxes.
This unit is a *local* container simulation; running a container on a client box is a write to a client
box and is not authorised here. If a fleet docker host is ever the intended instrument, that is a new
unit with an explicit go, not a silent widening of this one.

---

## 3. The two platform contracts (SPEC A12, quoted, unchanged)

| Platform | Key name | Remembered answer | Quota ledger (persistent) | OCR |
|---|---|---|---|---|
| Hostinger Docker (user `node`, HOME `/data`) | container env | client data folder under `/data` | `/data/.openclaw/drama-runs/.agnes-quota.sqlite3` | UNDETERMINED |
| Contabo Docker (only `~/.openclaw` persists) | container env | client data folder under `~/.openclaw` | `/home/node/.openclaw/drama-runs/.agnes-quota.sqlite3` | UNDETERMINED |

The persistence trap this unit exists to prove is already written down in this repo, in
`timer-artifacts/README.md` ("Per-platform contract"):

> `HOME` … Hostinger `/data` (persistent volume) · Contabo `/home/node` (**ephemeral** layer)
> Persistent root … `/data` · `/home/node/.openclaw` (the volume)
> "The Contabo row is the trap … `$HOME` there is the throwaway container layer (a recreate wipes it),
> so the key, address, state and log all live under the volume `/home/node/.openclaw`, never under `$HOME`."

So the quota ledger at `/home/node/.openclaw/drama-runs/.agnes-quota.sqlite3` is inside the surviving
volume, and a remembered answer written straight under `$HOME` on Contabo would **not** survive a
recreate. That is exactly the claim a container recreate has to settle — and it is unsettled here
(section 1).

---

## 4. What runs without a container — both platforms

Derivation of the two contracts from the platform `HOME` alone, each command in an empty environment
(`env -i`) so nothing from the operator's own shell leaks in. Raw capture:
`/tmp/<operator>-W4-proof-U2-platform-derived.txt`.

**Hostinger** (user `node`, `HOME=/data`):

```
$ env -i PATH=/usr/bin:/bin HOME=/data sh -c 'echo HOME=$HOME; echo quota=$HOME/.openclaw/drama-runs/.agnes-quota.sqlite3'
HOME=/data
quota=/data/.openclaw/drama-runs/.agnes-quota.sqlite3          # = SPEC A12, exact
  EXIT=0
$ env -i PATH=/usr/bin:/bin HOME=/data AGNES_AI_API_KEY=FAKE_KEY_W4_PROOF_U2_NOT_A_SECRET \
    sh -c 'if [ -n "$AGNES_AI_API_KEY" ]; then echo key_present=true; else echo key_present=false; fi'
key_present=true                                               # fake key in container env
  EXIT=0
$ env -i PATH=/usr/bin:/bin HOME=/data sh -c '...same test...'   # no key in env
key_present=false
  EXIT=0
```

**Contabo** (user `node`, `HOME=/home/node`):

```
$ env -i PATH=/usr/bin:/bin HOME=/home/node sh -c 'echo HOME=$HOME; echo quota=$HOME/.openclaw/drama-runs/.agnes-quota.sqlite3'
HOME=/home/node
quota=/home/node/.openclaw/drama-runs/.agnes-quota.sqlite3     # = SPEC A12, exact; inside the surviving volume
  EXIT=0
$ env -i PATH=/usr/bin:/bin HOME=/home/node AGNES_AI_API_KEY=FAKE_KEY_W4_PROOF_U2_NOT_A_SECRET \
    sh -c 'if [ -n "$AGNES_AI_API_KEY" ]; then echo key_present=true; else echo key_present=false; fi'
key_present=true
  EXIT=0
$ env -i PATH=/usr/bin:/bin HOME=/home/node sh -c '...same test...'
key_present=false
  EXIT=0
```

This is the **shell contract derivation only**: it proves the paths and the env key name resolve the way
SPEC A12 says. It is not `agnes_access.key_value()`, not `agnes_quota.state_path()`, and it does not
prove anything survives a recreate. Nothing here is a container result.

**OCR on this machine (SPEC A12's operator row):**

```
$ command -v tesseract
/opt/homebrew/bin/tesseract
  EXIT=0
$ tesseract --version | head -1
tesseract 5.5.3
  EXIT=0
```

Inside a `node:22-bookworm` container tesseract is a separate question and stays **UNDETERMINED** —
`node:22-bookworm` does not ship it, so the expected answer there is `OCR_UNAVAILABLE`, never PASS.
That expectation is not a result; it is untested (section 5).

---

## 5. Status of each acceptance line

| SPEC acceptance 2 item | Status here | Why |
|---|---|---|
| key lookup, fake key in container env → `key_present: true` | **BLOCKED** | needs a container; section 4 shows the env contract only, with no module to call |
| remembered answer on the platform's persistent path | **BLOCKED** | `agnes_access.remember()` is not on `origin/main` at this base, and no container to hold the path |
| quota ledger on the platform's persistent path | **BLOCKED** | same: `agnes_quota` not merged, no container |
| container recreate → both survive | **BLOCKED** | no docker daemon (section 2); nothing was created, so nothing could be re-created |
| tesseract present or `OCR_UNAVAILABLE` | **partial** | operator Mac: tesseract 5.5.3 present (proven, section 4). In-container: UNDETERMINED, untested |
| no network to Agnes, no KIE call | **held** | nothing in this unit contacts a provider; the only key material ever used is a named fake |

---

## 6. What a re-run needs

Two things, both outside this unit:

1. **A machine with a docker daemon.** Install nothing here as part of this receipt — a daemon is the
   operator's call, and the re-run is the same commands below.
2. **The wave-1 Agnes modules.** At base `1e1c12dcc`:

   ```
   $ ls 75-drama-song-ad-factory/scripts/core/ | grep -c agnes
   0
   $ grep -rln "agnes_quota\|agnes_access" 75-drama-song-ad-factory/ | wc -l
   0
   ```

   So the re-run happens on the pinned candidate head that carries `W1-agnes-core-U1..U9` (named by
   SWARM-PLAN), never by copying those files into this branch.

---

## 7. Re-run procedure (not executed here — docker unavailable)

Each platform, same shape: a volume at the **persistent root**, container started as `-u node` with the
platform's `HOME`, one fake key in the container env, tests run inside, then destroy and recreate the
container and read the two paths back. No real key, no provider call, no Agnes or KIE request.

```sh
# --- Hostinger shape: HOME /data is the persistent volume ---
docker volume create agn-u2-hostinger
docker run --rm -v agn-u2-hostinger:/data alpine sh -c \
  'mkdir -p /data/.openclaw/drama-runs && chown -R 1000:1000 /data'   # uid 1000 = node in node:22-bookworm
docker run -d --name agn-u2-hostinger -u node -e HOME=/data \
  -e AGNES_AI_API_KEY=FAKE_KEY_W4_PROOF_U2_NOT_A_SECRET \
  -v agn-u2-hostinger:/data node:22-bookworm sleep infinity

# --- Contabo shape: HOME /home/node is ephemeral; only ~/.openclaw is the volume ---
docker volume create agn-u2-contabo
docker run --rm -v agn-u2-contabo:/vol alpine sh -c \
  'mkdir -p /vol/.openclaw/drama-runs && chown -R 1000:1000 /vol'
docker run -d --name agn-u2-contabo -u node -e HOME=/home/node \
  -e AGNES_AI_API_KEY=FAKE_KEY_W4_PROOF_U2_NOT_A_SECRET \
  -v agn-u2-contabo:/home/node/.openclaw node:22-bookworm sleep infinity
```

Inside each container, from the candidate worktree:

```sh
# key lookup: fake key in the container env -> key_present true (and absent -> false)
python3 75-drama-song-ad-factory/scripts/core/agnes_access/agnes_access.py status --client-dir <platform client data folder>

# remembered answer + quota ledger on the platform's own paths
python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/agnes_access \
                     75-drama-song-ad-factory/scripts/core/agnes_quota

# OCR: tesseract present, else OCR_UNAVAILABLE (never PASS)
command -v tesseract || echo OCR_UNAVAILABLE
```

Then the recreate test — the part that is BLOCKED today:

```sh
docker rm -f agn-u2-hostinger      # /data survives (volume)      -> docker run ... (same volume) -> read back
docker rm -f agn-u2-contabo        # /home/node wiped, ~/.openclaw survives -> docker run ... (same volume) -> read back
```

Both reads must still show the remembered answer and the quota rows. On Contabo, anything written
directly under `/home/node` (outside `~/.openclaw`) must be **gone** after the recreate — that is the
failure the trap in `timer-artifacts/README.md` predicts, and it is the result this receipt is missing.

Paste both platforms' outputs into this file when the daemon exists; until then the verdict stays
**BLOCKED — docker not available**.

---

## 8. Regression (nothing that worked changed)

Area command, recorded base first and after this file was added — same command, same worktree, same
environment:

```
$ python3 -m pytest -q 75-drama-song-ad-factory/tests
base   (1e1c12dcc): 1 failed, 193 passed in 2.56s
+this  (unit head):  1 failed, 193 passed
```

The single failure is **pre-existing on the base** and is not touched by this unit (its file is outside
this unit's "Owns" line):

```
FAILED 75-drama-song-ad-factory/tests/test_model_choice.py::ModelChoice::test_no_model_pin_in_skill_docs
E  AssertionError: <match at the alias it forbids> ... references/studio-e2e-receipt.md
```

Zero new failures: same cases, same counts, base failure unchanged. The failing string itself is not
quoted here on purpose — this file is inside that test's `references/*.md` sweep, so quoting the alias it
forbids would add a second failing case to exactly this test.

Repo guards were run against this file too. `bash scripts/qc-assert-no-client-names.sh` reported **0 hits
from `references/agnes-platform-proof.md`** (32 hits remain repo-wide, all in files this unit never
touches — pre-existing on the base). That is why every operator path above is written `/Users/<operator>/…`,
`/tmp/<operator>-W4-proof-U2-…`, the way `references/studio-e2e-receipt.md` already writes them: a raw
operator home directory name in a tracked file trips that guard, and `main` is green on it.
