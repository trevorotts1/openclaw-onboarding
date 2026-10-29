#!/usr/bin/env bash
# oc-atomic-upgrade.sh — v1.2.3
#
# THE ONLY SAFE WAY TO MOVE A BOX ONTO A NEW OPENCLAW BUILD.
#
# ═══════════════════════════════════════════════════════════════════════════
# WHY THIS EXISTS: `openclaw doctor --fix` CANNOT DO THIS JOB
# ═══════════════════════════════════════════════════════════════════════════
# Every previous version of this gate called `openclaw doctor --fix` to migrate
# `agents.list` -> `agents.entries`. Measured, on 12 boxes: the config's SHA-256
# was BYTE-IDENTICAL before and after. `openclaw config schema` on 2026.7.1 and
# 2026.7.1-2 reports the `agents` properties as exactly ["defaults","list"] —
# there is no `entries` for it to migrate TO. It also has a measured SIDE
# EFFECT: on one box it silently rewrote `agents.defaults.models` pins. So the
# old gate degraded to a permanent refusal that froze 35 of 38 boxes while
# risking model pins for a migration that never happened.
#
# WHAT DOCTOR *IS* USED FOR HERE (v1.1.0, fleet-roll errors #16 and #18)
# `doctor --fix` still cannot migrate `agents.list` -> `agents.entries` (above), and
# this script never uses it for that. It IS the only migrator of the AGENT/SESSION
# DATABASE: a gateway on OpenClaw >= 2026.10.5 refuses to boot on an agent database
# at schema 24 ("run openclaw doctor --fix to migrate session identities"), so a
# roll that installs the new build and starts it without doctor rolls back every time.
# On a launchd box this script therefore runs the NEW binary's
# `doctor --fix --non-interactive` (stdin /dev/null, bounded) AFTER the install and
# the config rewrite and BEFORE the start, while the gateway is booted out. Doctor
# takes exclusive maintenance and refuses while any other process holds the state
# database, so stale `openclaw` CLI processes holding <root>/state/openclaw.sqlite
# are reaped first (never the launchd job's gateway, a node service, the app, an ancestor,
# or anything started during this run; a gateway left holding the database while the job
# is booted out is an orphan and is stopped separately, see #33 below). Doctor must
# not change the model/provider selection; if it does, the upgrade rolls back. The one
# known doctor refusal this script repairs is the legacy-audit-raw checkpoint (see
# _repair_audit_checkpoint).
#
# FOUR MORE ROLL FAILURES THIS SCRIPT NOW PREVENTS (v1.2.0, fleet-roll errors #21 #24 #25 #33)
# #21  launchd KeepAlive respawns a LOADED gateway job while npm is still rewriting the
#      package, so the gateway imports a half-written tree and the stability window never
#      holds. EVERY npm install here (forward and rollback) now runs with the gateway job
#      proven booted out for the whole window, and the job is bootstrapped again only after
#      the package measures complete (_npm_install_held / _package_complete).
# #24  `doctor` loads every enabled plugin's module at startup, BEFORE it fixes anything; one
#      whose import is missing (ERR_MODULE_NOT_FOUND from a plugin-sdk export) makes it spin
#      forever. Doctor now runs under a bound AND a loop detector (the same module-load error
#      printed OC_ATOMIC_DOCTOR_LOOP_LINES times kills it at once, long before the bound). Its
#      own output then names the EXACT plugin; only that plugin's `enabled` is set to false
#      (never the allow list, never its config, never an install/enable call, never a guess),
#      the change is recorded, and doctor runs again, bounded the same way
#      (_quarantine_from_output). The rollback restores the config byte for byte.
# #25  `openclaw config validate` takes the sqlite maintenance lock even when read-only, and
#      against a SERVING gateway that kills it (healthz 000 while the pid lives). With the
#      gateway job loaded the check runs on a private copy of the config in a private state
#      directory, under a known-good and a known-bad control, and an instrument that cannot
#      tell them apart is UNDETERMINED, never "valid" (_config_valid_isolated).
# #33  an orphan gateway (ppid 1, left by an earlier run) that still holds the state
#      database makes the new LaunchAgent exit 78 "Another gateway already owns this state
#      directory", which was read as a bad binary. Before the quiesce proof, before the
#      start and before a rollback restart, a gateway process that holds the state database
#      and is not the launchd job's pid is stopped BY IDENTITY and logged (_reap_orphan_gateways).
#
# ═══════════════════════════════════════════════════════════════════════════
# THE FOUR FACTS THAT DICTATE THE ORDER OF OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════
# 1. `additionalProperties: false` is set on `agents` in BOTH schema versions.
#    `entries` is invalid on the old build; `list` is invalid on the new one.
#    THERE IS NO CONFIG THAT IS VALID ON BOTH. So the migration can never be
#    done "early and safely" — it is only ever correct in the same window as
#    the binary change.
#
# 2. The deployed runtime has NO `entries` READER. agent-scope-config-BxAUeF6t.js
#    (identical on 2026.7.1 and 2026.7.1-2) contains only
#        listAgentEntries(cfg) { const list = cfg.agents?.list; ... }
#    A scan of all 4,597 bundle files found ZERO real reads of `agents.entries`
#    against a control of 105 files referencing `agents.list`. Migrating a box
#    BEFORE its binary changes enumerates ZERO agents: a silent, total outage,
#    strictly worse than the loud crash-loop. (The beta bundle
#    agent-scope-config-BxKPUdGc.js DOES read both — but only after install.)
#
# 3. A LIVE PROCESS REWRITES openclaw.json ROUGHLY ONCE PER MINUTE, byte-
#    identically — observed while only `stat`/`sha256sum` were running.
#    Inference, labelled as such: it serializes the gateway's in-memory model,
#    which only knows `agents.list`. A hand-written `entries` is therefore
#    normalized straight back out within about a minute. ANY MIGRATION
#    PERFORMED WHILE THE GATEWAY IS UP WILL BE SILENTLY REVERTED.
#
# 4. launchd's KeepAlive + ThrottleInterval=10 respawns a still-LOADED job every
#    ~11s. `launchctl kickstart -k` restarts the PROCESS but does NOT unload the
#    JOB — it is not a stop. A real stop is `bootout`; a real start is
#    `bootstrap`. And the 5-minute self-heal agent
#    (com.openclaw.service-remediate) re-bootstraps anything that was booted
#    out, so it must be quiesced too — or, when it runs from cron where we
#    cannot boot it out, held off by the maintenance lock this script writes.
#
# THEREFORE the only correct order is, and this script performs exactly it:
#
#     quiesce (and PROVE it)  ->  install the new binary  ->  ASK THE NEW BINARY
#     WHAT SCHEMA IT SPEAKS   ->  rewrite the config to match  ->  verify the
#     rewrite is lossless     ->  start  ->  prove it STAYED up
#
# At no point does a running gateway meet a config it rejects. The config is
# rewritten only while nothing is running, and only after the binary that will
# read it is already on disk and has told us which key it wants.
#
# ═══════════════════════════════════════════════════════════════════════════
# ROLLBACK
# ═══════════════════════════════════════════════════════════════════════════
# Any failure after the quiesce restores BOTH the old binary AND the old config
# and starts the gateway again. A failed upgrade must never leave a dark box.
# "Starts the gateway again" is PROVEN, never assumed: the job is re-loaded if it
# was loaded when this began (even when the quiesce itself is what failed), and
# the rollback only reports success once launchd shows it loaded with a pid AND
# GET /healthz returns 200. The restored binary is re-measured the same way.
# If the rollback itself fails, this exits 70 (EX_SOFTWARE) with a banner naming
# exactly what is left broken and the literal commands to repair it — that case
# is the only one where a human is strictly required.
#
# ═══════════════════════════════════════════════════════════════════════════
# WHAT THIS DELIBERATELY REFUSES TO DO
# ═══════════════════════════════════════════════════════════════════════════
# * A DOCKER-HOSTED GATEWAY. The binary lives in the container IMAGE, and this
#   repo does not control the image build or pull. Doing half the procedure
#   (migrating the bind-mounted config while the image stays old) is exactly
#   failure mode 2 — a silent zero-agent box. So a docker supervisor is a
#   REFUSAL with the manual sequence printed, never a partial attempt.
# * MIGRATING WITHOUT A BINARY CHANGE THAT ASKS FOR IT. The schema probe is the
#   authority. If the installed binary still accepts `list`, the config is left
#   exactly as it is.
# * ANYTHING ON AN UNANSWERED PROBE. An unreadable config, an unparseable
#   schema, an unmeasurable version — all refuse. An absence that cannot be
#   proven is not an absence.
#
# ═══════════════════════════════════════════════════════════════════════════
# USAGE
# ═══════════════════════════════════════════════════════════════════════════
#   oc-atomic-upgrade.sh --detect
#       Read-only. Reports this box's schema shape, its MEASURED openclaw
#       version (never a recorded one), and its supervisor.
#       exit 0 = clean/new-shape, 10 = legacy `agents.list`, 3 = undetermined.
#
#   oc-atomic-upgrade.sh --upgrade [--target-version X.Y.Z] [--dry-run]
#       The atomic procedure. --dry-run prints the plan and touches nothing.
#       exit 0 = upgraded (or already correct), 78 = REFUSED / rolled back
#       (box left exactly as found), 70 = ROLLBACK FAILED (needs a human now),
#       3 = undetermined, 2 = usage,
#       79 = REFUSED (this box is a container).
#
# Environment:
#   OC_ATOMIC_QUIESCE_PROOF_SECONDS  window used to prove the once-a-minute
#                                    writer really stopped (default 75; the
#                                    writer's observed period is ~60s)
#   OC_ATOMIC_STABILITY_SECONDS      how long the gateway must stay up with an
#                                    unchanging pid before we call it started
#                                    (default 25; the crash-loop period is ~11s,
#                                    so this spans at least two respawns)
#   OC_ATOMIC_NPM                    npm binary (default: npm)
#   OC_ATOMIC_BOOTOUT_TIMEOUT        seconds to wait for a booted-out job to
#                                    actually leave launchd (default 60). bootout
#                                    is ASYNCHRONOUS: it returns before the
#                                    job is gone (the process gets SIGTERM and
#                                    up to ExitTimeOut, 20s by default, to exit).
#   OC_ATOMIC_HEALTH_TIMEOUT         seconds a ROLLBACK waits to PROVE the gateway
#                                    is back: job loaded, pid present, and
#                                    GET /healthz == 200 (default 60)
#   OC_ATOMIC_SETTLE_SECONDS         after a ROLLBACK first sees the gateway healthy
#                                    it keeps watching this long and re-checks
#                                    (same pid, still loaded, /healthz 200) before
#                                    claiming success. A bootout that outlived
#                                    OC_ATOMIC_BOOTOUT_TIMEOUT can still remove the
#                                    job later; the default (25) outlasts launchd's
#                                    20s ExitTimeOut. 0 disables (and says so).
#   OC_ATOMIC_DOCTOR_TIMEOUT         seconds `doctor --fix --non-interactive` may run
#                                    before it is killed and the upgrade rolls back
#                                    (default 900; it backs up and migrates databases)
#   OC_ATOMIC_DOCTOR_LOOP_LINES      how many times doctor may print the SAME module-load error
#                                    (digits ignored) before it is judged to be spinning on it and
#                                    killed early (default 5; 0 = rely on the bound alone)
#   Non-numeric values of the five numbers above fall back to their defaults.
#
# ═══════════════════════════════════════════════════════════════════════════
# WHICH OPENCLAW? THE ONE THE SUPERVISOR LAUNCHES (CAN015), NEVER THE ONE ON PATH
# ═══════════════════════════════════════════════════════════════════════════
# `openclaw` on PATH can be a different copy (nvm, brew, a stale shim) than the
# tree launchd/systemd runs (`node <prefix>/lib/node_modules/openclaw/dist/index.js`).
# Measuring or installing through PATH once logged "binary already at 2026.10.5 -
# no install needed" and exited 0 while the gateway kept running 2026.10.4.
# oc-supervisor-install.py reads the plist ProgramArguments / systemd ExecStart;
# this script then measures package.json of THAT tree, installs with THAT node's
# npm into THAT prefix (`npm install -g --prefix`), puts that prefix/node first on
# PATH for every `openclaw` call, and only claims success when the package the
# gateway launched is at the target AND the live gateway process was started from
# it and answers /healthz. A disagreeing PATH copy is logged and ignored. A
# supervisor definition that names no openclaw package REFUSES (never guesses).
#
# ⚠️ INTERPRETER: written for stock /bin/bash 3.2.57, which is what the fleet's
# Macs run. No associative arrays, no `mapfile`, no `${x^^}`, and never a
# heredoc nested inside `$( )` — that last one aborts at PARSE time on 3.2 and
# has already shipped a dead gate to this fleet once.

set -uo pipefail

VERSION="1.2.3"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATOR="$SCRIPT_DIR/oc-schema-migrate.py"
SUP_HELPER="$SCRIPT_DIR/oc-supervisor-install.py"
ORIG_PATH="$PATH"

MODE=""
TARGET_VERSION=""
DRY_RUN=0

# A non-integer timeout would make `[ "$i" -ge "$t" ]` error forever; fall back.
_uint() { case "$1" in ''|*[!0-9]*) printf '%s' "$2" ;; *) printf '%s' "$1" ;; esac; }

QUIESCE_PROOF_SECONDS="${OC_ATOMIC_QUIESCE_PROOF_SECONDS:-75}"
STABILITY_SECONDS="${OC_ATOMIC_STABILITY_SECONDS:-25}"
NPM_BIN="${OC_ATOMIC_NPM:-npm}"
BOOTOUT_TIMEOUT="$(_uint "${OC_ATOMIC_BOOTOUT_TIMEOUT:-}" 60)"
HEALTH_TIMEOUT="$(_uint "${OC_ATOMIC_HEALTH_TIMEOUT:-}" 60)"
SETTLE_SECONDS="$(_uint "${OC_ATOMIC_SETTLE_SECONDS:-}" 25)"
DOCTOR_TIMEOUT="$(_uint "${OC_ATOMIC_DOCTOR_TIMEOUT:-}" 900)"
DOCTOR_LOOP_LINES="$(_uint "${OC_ATOMIC_DOCTOR_LOOP_LINES:-}" 5)"
RUN_START_EPOCH="$(date +%s)"   # a state-database holder started before this is stale (_reap_state_holders)

GATEWAY_LABEL="ai.openclaw.gateway"
SELFHEAL_LABEL="com.openclaw.service-remediate"

# ─── Rollback state. Every one of these is set BEFORE the thing it undoes. ───
STATE_QUIESCED=0
STATE_BINARY_CHANGED=0
STATE_CONFIG_CHANGED=0
STATE_SELFHEAL_BOOTED_OUT=0
GATEWAY_LOADED_AT_START=0   # the job/container the rollback must put back
OLD_VERSION=""
CONFIG_BACKUP=""
OC_CONFIG=""
OC_ROOT_DIR=""
LOCK_FILE=""
SUPERVISOR=""
UIDN=""
SUP_PKG_ROOT=""   # the openclaw package the supervisor launches ("" = none found: PATH is all there is)
SUP_PREFIX=""
SUP_ENTRY=""
SUP_SOURCE=""     # launchd | systemd ("" = no supervisor definition)
SUP_UNIT=""       # definition handle: the plist/unit path, or container:<name> for docker
DOCTOR_WHY=""     # why _migrate_state_with_doctor failed (the rollback reason)
PLUGIN_QUARANTINED=""   # plugin ids whose entry this run set enabled=false (#24); the rollback undoes them with the config
PLUGIN_RECORD=""        # <root>/oc-atomic-plugin-quarantine.jsonl, the durable record of that

_say()  { printf '[oc-atomic-upgrade] %s\n' "$*"; }
_ok()   { printf '[oc-atomic-upgrade] OK    %s\n' "$*"; }
_warn() { printf '[oc-atomic-upgrade] WARN  %s\n' "$*" >&2; }
_err()  { printf '[oc-atomic-upgrade] ERROR %s\n' "$*" >&2; }

# ── Resolve the box's OpenClaw root the same way every other script here does ─
#
# ⚠️ UIDN IS SET HERE, IN THE PARENT SHELL, ON PURPOSE. It used to be assigned
# inside _detect_supervisor(), which is invoked as `SUPERVISOR="$(...)"` -- a
# COMMAND SUBSTITUTION, i.e. a subshell. The assignment was therefore discarded
# the moment that subshell exited, leaving UIDN empty and every launchd domain
# target malformed as `gui//ai.openclaw.gateway`.
#
# That is not a cosmetic bug. `launchctl bootout gui//<label>` FAILS, so the
# gateway is never actually stopped; `launchctl print gui//<label>` also fails,
# so _gateway_pid() returns empty and the quiesce proof reads "no pid running"
# and PASSES. The procedure would then migrate the config underneath a LIVE
# gateway -- which is precisely fact 3, the once-a-minute writer that silently
# reverts the migration, and exactly the outcome this script exists to prevent.
#
# It survived the first round of tests because the launchctl stub resolved its
# label with `basename`, and basename normalises the double slash. A stub that
# is more forgiving than the real tool hides the defect it was written to catch;
# tests/unit/oc-atomic-upgrade.test.sh now asserts the domain target matches
# gui/<digits>/<label> on every call.
_resolve_root() {
  OC_ROOT_DIR="$HOME/.openclaw"
  [ -d "/data/.openclaw" ] && OC_ROOT_DIR="/data/.openclaw"
  OC_CONFIG="$OC_ROOT_DIR/openclaw.json"
  LOCK_FILE="$OC_ROOT_DIR/.openclaw-maintenance-lock"
  UIDN="$(id -u 2>/dev/null || echo 0)"
}

# ── Are we INSIDE a container? The docker branch of _detect_supervisor only
# ── proves a container literally named `openclaw` exists on a LOCAL daemon.
# ── Inside a container there is no docker binary and no socket, so that check
# ── reads "none" and the procedure would proceed where it must never run.
# ── These markers are authoritative and are checked FIRST. /proc does not
# ── exist on macOS, where the reads simply fail.
# agent-pull-fix: R9
_running_in_container() {
  [ -f /.dockerenv ] && return 0
  [ -f /.containerenv ] && return 0
  [ -f /run/.containerenv ] && return 0
  if [ -r /proc/1/cgroup ] \
     && grep -Eq 'docker|kubepods|containerd|libpod' /proc/1/cgroup 2>/dev/null; then
    return 0
  fi
  return 1
}

# ── MEASURED version. Never a recorded one: the fleet record for the box that
# ── went dark was two minor versions stale, and every conclusion drawn from it
# ── was wrong.
_path_version() {
  PATH="$ORIG_PATH" command -v openclaw >/dev/null 2>&1 || { printf ''; return 0; }
  PATH="$ORIG_PATH" openclaw --version 2>/dev/null | head -1 \
    | grep -oE '[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?' | head -1
}
# CAN015: the version is the one the supervisor's package.json says, not whatever
# `openclaw` PATH happens to resolve to.
_measured_version() {
  if [ -n "$SUP_PKG_ROOT" ]; then
    python3 "$SUP_HELPER" version 2>/dev/null
    return 0
  fi
  _path_version
}

# CAN015: find the install the supervisor launches. Sets globals, so it must run
# in the parent shell (never inside $( )). rc 0 = resolved, or no supervisor
# definition at all (PATH is then the only install and nothing can disagree);
# rc 1 = a supervisor definition exists but names no installed openclaw.
_resolve_supervisor_install() {
  local out rc node_dir pv
  out="$(python3 "$SUP_HELPER" show 2>/dev/null)"; rc=$?
  [ "$rc" -eq 1 ] && return 0
  [ "$rc" -eq 0 ] || return 1
  SUP_PKG_ROOT="$(printf '%s\n' "$out" | sed -n 's/^pkg_root=//p' | head -1)"
  SUP_PREFIX="$(printf '%s\n' "$out" | sed -n 's/^prefix=//p' | head -1)"
  SUP_ENTRY="$(printf '%s\n' "$out" | sed -n 's/^entry=//p' | head -1)"
  SUP_SOURCE="$(printf '%s\n' "$out" | sed -n 's/^source=//p' | head -1)"
  SUP_UNIT="$(printf '%s\n' "$out" | sed -n 's/^unit=//p' | head -1)"
  node_dir="$(printf '%s\n' "$out" | sed -n 's/^node=//p' | head -1)"
  [ -n "$node_dir" ] && node_dir="$(dirname "$node_dir")"
  [ -n "$SUP_PKG_ROOT" ] && [ -n "$SUP_PREFIX" ] || return 1
  # ORDER MATTERS (v1.2.3): the supervisor's node dir must END UP FIRST. npm is a
  # `#!/usr/bin/env node` script, so it runs under the first `node` on PATH, and so do
  # the package's own lifecycle scripts (openclaw's preinstall refuses a node below its
  # engines floor). On a Homebrew Mac $SUP_PREFIX/bin is /opt/homebrew/bin, whose `node`
  # is the stale one the node-floor step just replaced; prepended AFTER the private node
  # it won, npm ran on Node 26.8.1, the preinstall guard exited 1 and every box rolled
  # back with exit 78 (Big Fleet Roll 20261029).
  [ -d "$SUP_PREFIX/bin" ] && PATH="$SUP_PREFIX/bin:$PATH"
  [ -n "$node_dir" ] && [ -d "$node_dir" ] && PATH="$node_dir:$PATH"
  export PATH
  # THAT node's npm, unless the operator pinned one.
  [ -z "${OC_ATOMIC_NPM:-}" ] && [ -n "$node_dir" ] && [ -x "$node_dir/npm" ] && NPM_BIN="$node_dir/npm"
  # Docker-on-host boxes: the persistent prefix's bin/node shim has no npm of
  # its own; the HOST npm (any version - --prefix makes the ABI irrelevant)
  # performs the install into the bind-mounted prefix.
  [ -z "${OC_ATOMIC_NPM:-}" ] && [ -z "$NPM_BIN" ] && [ -x "$(command -v npm 2>/dev/null || true)" ] && NPM_BIN="$(command -v npm)"
  _say "supervisor install: $SUP_PKG_ROOT  (prefix $SUP_PREFIX, npm $NPM_BIN, measured $(_measured_version))"
  pv="$(_path_version)"
  if [ -n "$pv" ] && [ "$pv" != "$(_measured_version)" ]; then
    _warn "PATH openclaw ($(PATH="$ORIG_PATH" command -v openclaw)) is $pv but the gateway launches $(_measured_version) - these DISAGREE; upgrading the supervisor's install and ignoring the PATH copy"
  fi
  return 0
}

# Install into the supervisor's prefix; with no supervisor definition, as before.
_npm_install() {
  if [ -n "$SUP_PREFIX" ]; then
    "$NPM_BIN" install -g --prefix "$SUP_PREFIX" "openclaw@$1"
  else
    "$NPM_BIN" install -g "openclaw@$1"
  fi
}

# ── Supervisor detection. Reports what would RESPAWN the gateway, because that
# ── is the thing a quiesce has to defeat — not merely what is running now.
# NOTE: this runs inside `$( )`. Anything it assigns is discarded when that
# subshell exits, so it must READ state (UIDN, set by _resolve_root) and never
# be the only place that sets it. See the warning on _resolve_root above.
_detect_supervisor() {
  if command -v launchctl >/dev/null 2>&1 \
     && launchctl print "gui/$UIDN/$GATEWAY_LABEL" >/dev/null 2>&1; then
    printf 'launchd'
    return 0
  fi
  if command -v docker >/dev/null 2>&1 \
     && docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx 'openclaw'; then
    printf 'docker'
    return 0
  fi
  # CAN016: docker-on-host fleet layout — the gateway container is named
  # <something>-openclaw-1 (compose project prefix). A container literally
  # named `openclaw` matches the branch above; these need an explicit check.
  if command -v docker >/dev/null 2>&1 \
     && docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q 'openclaw'; then
    printf 'docker'
    return 0
  fi
  if command -v launchctl >/dev/null 2>&1 \
     && [ -f "$HOME/Library/LaunchAgents/$GATEWAY_LABEL.plist" ]; then
    # plist on disk but not loaded: launchd is still the supervisor, the job is
    # just currently down. Treating this as "no supervisor" would skip the
    # bootstrap at the end and leave the box dark on purpose.
    printf 'launchd'
    return 0
  fi
  printf 'none'
}

# ── Live gateway PID. Never prints a command line: `ps eww` on this process
# ── dumps every secret in its environment, so it is never used here.
_gateway_pid() {
  case "$SUPERVISOR" in
    launchd)
      launchctl print "gui/$UIDN/$GATEWAY_LABEL" 2>/dev/null \
        | awk -F'=' '/^[[:space:]]*pid =/{gsub(/[^0-9]/,"",$2); print $2; exit}'
      ;;
    docker)
      if docker inspect -f '{{.State.Running}}' openclaw 2>/dev/null | grep -q true; then
        docker inspect -f '{{.State.Pid}}' openclaw 2>/dev/null | grep -E '^[1-9][0-9]*$'
      else
        # CAN016: compose layout (<project>-openclaw-1). The FIRST openclaw-named
        # running container wins; the literal-name branch above stays exact.
        local c
        c="$(docker ps --format '{{.Names}}' 2>/dev/null | grep 'openclaw' | head -1)"
        [ -n "$c" ] && docker inspect -f '{{.State.Pid}}' "$c" 2>/dev/null | grep -E '^[1-9][0-9]*$'
      fi
      ;;
    *) printf '' ;;
  esac
}

# ── Bounded poll: run "$@" once a second until it succeeds or $1 seconds pass.
# ── launchctl bootout/bootstrap return BEFORE launchd has finished, so a single
# ── check right after one is a race, not a measurement.
_poll() {
  local t="$1" i=0
  shift
  while :; do
    "$@" && return 0
    [ "$i" -ge "$t" ] && return 1
    sleep 1; i=$((i+1))
  done
}

_job_loaded()  { launchctl print "gui/$UIDN/$1" >/dev/null 2>&1; }
_job_unloaded() { ! _job_loaded "$1"; }
_gateway_unloaded() { _job_unloaded "$GATEWAY_LABEL"; }

# Is the gateway job/container present right now? (Not whether it is healthy.)
_gateway_loaded() {
  case "$SUPERVISOR" in
    launchd) _job_loaded "$GATEWAY_LABEL" ;;
    docker)
      [ "$(docker inspect -f '{{.State.Running}}' openclaw 2>/dev/null)" = "true" ] && return 0
      # CAN016: compose layout container
      local c
      c="$(docker ps --format '{{.Names}}' 2>/dev/null | grep 'openclaw' | head -1)"
      [ -n "$c" ] && [ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" = "true" ]
      ;;
    *)       return 1 ;;
  esac
}

# gateway.port from the config, default 18789 (same rule as ghl-mcp-autostart.sh).
_gateway_port() {
  OC_CFG="$OC_CONFIG" python3 -c 'import json,os
try:
    print(int((json.load(open(os.environ["OC_CFG"])).get("gateway") or {}).get("port") or 18789))
except Exception:
    print(18789)' 2>/dev/null || echo 18789
}

# 1 when gateway.tls.enabled is true in the config, else 0 (also on an unreadable
# config). A TLS gateway answers https ONLY: an http:// probe gets an empty reply,
# so a healthy gateway would read as down and the upgrade would roll back.
_gateway_tls() {
  OC_CFG="$OC_CONFIG" python3 -c 'import json,os
try:
    t=((json.load(open(os.environ["OC_CFG"])).get("gateway") or {}).get("tls") or {}).get("enabled")
    print(1 if str(t).lower()=="true" else 0)
except Exception:
    print(0)' 2>/dev/null || echo 0
}

# rc 0 ONLY when GET /healthz answers 200. No curl = cannot prove = rc 1.
# TLS gateway: https with -k (loopback only, self-signed cert).
_healthz_ok() {
  command -v curl >/dev/null 2>&1 || return 1
  local s=http k=""
  if [ "$(_gateway_tls)" = "1" ]; then s=https; k="-k"; fi
  # shellcheck disable=SC2086  # k is empty or the single word -k
  [ "$(curl -s $k -o /dev/null -w '%{http_code}' --max-time 3 \
        "$s://127.0.0.1:$(_gateway_port)/healthz" 2>/dev/null)" = "200" ]
}

_config_sha() {
  [ -f "$OC_CONFIG" ] || { printf ''; return 0; }
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$OC_CONFIG" 2>/dev/null | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$OC_CONFIG" 2>/dev/null | awk '{print $1}'
  else
    printf ''
  fi
}

# ── Does the INSTALLED binary accept the config on disk? `openclaw config validate`
# ── is the build's own verdict (rc 1 = rejected). Prints ONLY each issue's path and
# ── message (never the offending value) so a misplaced secret cannot reach a log.
# ── 2026.10.4 -> 2026.10.5 shipped a box whose config held skills.workshop.autonomous
# ── .mode "propose": every CLI command died, and this script had still printed
# ── "ATOMIC UPGRADE COMPLETE" because nothing here ever asked the new binary.
#
# ── #25: on 2026.10.5 `config validate` takes the sqlite maintenance lock EVEN WHEN
# ── READ-ONLY, so run against the live state directory while a gateway is SERVING it
# ── stops that gateway answering (healthz 000 while its pid lives). Whenever the gateway
# ── job is loaded the verdict therefore comes from _config_valid_isolated, which never
# ── touches the live state directory. With the job booted out (the upgrade window) no
# ── gateway exists to contend with, and the plain call is correct.
_print_validate_issues() {
  printf '%s' "$1" | python3 -c 'import json,sys
try:
    for i in json.load(sys.stdin).get("issues") or []:
        print("%s: %s" % (i.get("path"), i.get("message")))
except Exception:
    print("(no parseable issue list - the build rejected the config)")' 2>/dev/null | sed 's/^/    | /' >&2
}
_config_valid_for_installed_binary() {
  local out
  if _gateway_loaded; then _config_valid_isolated; return $?; fi
  out="$(openclaw config validate --json 2>/dev/null)" && return 0
  _print_validate_issues "$out"
  return 1
}

# One validate run that cannot see the live state directory: its own state dir ($1), its
# own config file ($2), config writes refused. rc and stdout are the build's own verdict.
_validate_in_isolation() {
  OPENCLAW_STATE_DIR="$1" OPENCLAW_CONFIG_PATH="$2" OPENCLAW_CONFIG_READONLY=1 \
    openclaw config validate --json 2>/dev/null
}

# rc 0 = the build accepts the config; rc 1 = it rejects it (issues printed) OR the check
# could not be trusted. The private state dir holds a COPY of the config and symlinks to the
# live plugin directories (so third-party plugin entries still resolve) but none of the live
# state. The instrument is proven on this very transport first: a known-bad config must be
# rejected and a known-good one accepted, else the answer is UNDETERMINED and treated as "not
# proven valid" (the caller then runs the full procedure inside the quiesce, where a live
# validate is safe) - never as "valid".
_config_valid_isolated() {
  local iso out rc d
  iso="$(mktemp -d "${TMPDIR:-/tmp}/oc-validate.XXXXXX")" || {
    _warn "isolated config validation UNDETERMINED: could not create a private state directory"; return 1; }
  for d in extensions npm plugins; do
    [ -d "$OC_ROOT_DIR/$d" ] && ln -s "$OC_ROOT_DIR/$d" "$iso/$d"
  done
  printf '{}\n' > "$iso/control-good.json"
  printf '{"agents":{"__oc_atomic_probe__":true}}\n' > "$iso/control-bad.json"
  if ! cp "$OC_CONFIG" "$iso/openclaw.json" 2>/dev/null; then
    _rm_isolated "$iso"; _warn "isolated config validation UNDETERMINED: could not copy the config"; return 1
  fi
  if ! _validate_in_isolation "$iso" "$iso/control-good.json" >/dev/null; then
    _rm_isolated "$iso"; _warn "isolated config validation UNDETERMINED: the known-good control was rejected, so this check cannot be trusted"; return 1
  fi
  if _validate_in_isolation "$iso" "$iso/control-bad.json" >/dev/null; then
    _rm_isolated "$iso"; _warn "isolated config validation UNDETERMINED: the known-bad control was ACCEPTED, so this check cannot tell valid from invalid"; return 1
  fi
  out="$(_validate_in_isolation "$iso" "$iso/openclaw.json")"; rc=$?
  _rm_isolated "$iso"
  [ "$rc" -eq 0 ] && return 0
  _print_validate_issues "$out"
  return 1
}
_rm_isolated() { rm -f "$1/extensions" "$1/npm" "$1/plugins" 2>/dev/null; rm -rf "$1" 2>/dev/null; }

# ── SHARED INSTALLATION LEASE (mac.MAC-1 / consistency.C1) ───────────────────
# oc-atomic is the writer that actually moves a box onto a new OpenClaw build,
# so it MUST hold the same lease as update-skills.sh, self-update.sh and the
# weekly cron — otherwise two writers migrate the same config concurrently.
# Liveness is decided by the RECORD (pid + process start identity + run id),
# never by the file's existence and never by its age (mac.MAC-13).
#
# NESTED writers inherit: self-update → (this script) and weekly-full-update →
# fleet-refresh → (this script) are DESCENDANTS of the lease holder, so they
# proceed without rewriting or releasing it. Refusing them is the defect that
# closed PR #2612 — the box's own update chain refused its own children.
OC_LEASE_PATH="${OPENCLAW_UPDATE_LEASE:-/tmp/openclaw-update.lock}"
OC_LEASE_STATE=""      # "" | owned | inherited
OC_LEASE_IMPL=""

_lease_start() { ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' | sed 's/^ *//;s/ *$//' || true; }
_lease_ppid()  { ps -o ppid= -p "$1" 2>/dev/null | tr -d ' ' || true; }
_lease_rpid() {
  if [ -d "$OC_LEASE_PATH" ]; then head -1 "$OC_LEASE_PATH/pid" 2>/dev/null || true
  else sed -n 's/^pid=\([0-9][0-9]*\).*/\1/p' "$OC_LEASE_PATH" 2>/dev/null | head -1 || true
  fi
  return 0
}
_lease_rstart() { sed -n 's/^start=//p' "$OC_LEASE_PATH" 2>/dev/null | head -1 || true; return 0; }

_lease_owner_live() {
  local _p _s
  if [ -d "$OC_LEASE_PATH" ]; then
    _p="$(_lease_rpid)"; [ -n "$_p" ] || return 1
    kill -0 "$_p" 2>/dev/null || return 1
    return 0                      # legacy mkdir lease: pid only, never age
  fi
  [ -f "$OC_LEASE_PATH" ] || return 1
  _p="$(_lease_rpid)"; [ -n "$_p" ] || return 1
  kill -0 "$_p" 2>/dev/null || return 1
  _s="$(_lease_rstart)"
  if [ -n "$_s" ]; then [ "$(_lease_start "$_p")" = "$_s" ] || return 1; fi
  return 0
}

# 0 = this process is the holder or one of its descendants. A legacy mkdir lease
# carries no start identity, so it can never prove a process tree.
_lease_in_owner_tree() {
  [ -d "$OC_LEASE_PATH" ] && return 1
  _lease_owner_live || return 1
  local _p _cur _n
  _p="$(_lease_rpid)"; _cur="$$"; _n=0
  while [ -n "$_cur" ] && [ "$_cur" -gt 1 ] 2>/dev/null && [ "$_n" -lt 64 ]; do
    [ "$_cur" = "$_p" ] && return 0
    _cur="$(_lease_ppid "$_cur")"
    _n=$((_n + 1))
  done
  return 1
}

_lease_write_own() {
  printf 'pid=%s\nstart=%s\nrun_id=%s\nrole=%s\ninstall_path=%s\nutc=%s\n' \
    "$$" "$(_lease_start "$$")" "${1:-}" "oc-atomic-upgrade" "${OC_ROOT_DIR:-}" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$OC_LEASE_PATH" 2>/dev/null
}

_lease_load_helper() {
  local _h _d
  _d="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
  for _h in "$_d/box-update-lock.sh" \
            "${OC_ROOT_DIR:-$HOME/.openclaw}/scripts/box-update-lock.sh" \
            "${OC_ROOT_DIR:-$HOME/.openclaw}/fleet-refresh/onboarding/scripts/box-update-lock.sh"; do
    if [ -f "$_h" ]; then
      # shellcheck source=/dev/null
      . "$_h" || continue
      declare -F box_update_lock_acquire >/dev/null 2>&1 && return 0
    fi
  done
  return 1
}

# 0 held · 3 a live foreign writer owns it · 1 unrecoverable.
_lease_acquire() {
  OC_LEASE_IMPL="inline"
  if _lease_load_helper; then OC_LEASE_IMPL="helper"; fi

  if _lease_in_owner_tree; then
    OC_LEASE_STATE="inherited"
    # Also export the helper's identity keys so a DESCENDANT that takes the
    # helper path can prove inheritance from the same run.
    BFX_LOCK_RUN_ID="$(sed -n 's/^run_id=//p' "$OC_LEASE_PATH" 2>/dev/null | head -1 || true)"
    BFX_LOCK_OWNER_PID="$(_lease_rpid)"
    export BFX_LOCK_RUN_ID BFX_LOCK_OWNER_PID
    _say "lease     : inherited $OC_LEASE_PATH from pid $(_lease_rpid) (nested writer)"
    return 0
  fi

  if [ -e "$OC_LEASE_PATH" ] && [ ! -f "$OC_LEASE_PATH" ]; then
    _lease_owner_live && return 3
    rm -rf "$OC_LEASE_PATH" 2>/dev/null || return 1
  fi

  if [ "$OC_LEASE_IMPL" = "helper" ]; then
    box_update_lock_acquire "$OC_LEASE_PATH" "${RUN_ID:-oc-atomic-$$}" \
      "oc-atomic-upgrade" "${OC_ROOT_DIR:-}"
    case "$?" in
      0) OC_LEASE_STATE="owned"
         _say "lease     : acquired $OC_LEASE_PATH (shared lease)"
         return 0 ;;
      3) return 3 ;;
      *) return 1 ;;
    esac
  fi

  if command -v flock >/dev/null 2>&1; then
    # `exec` with ONLY redirections applies every one of them to the whole script, so a bare `exec 9<>f 2>/dev/null`
    # sends stderr to /dev/null for the rest of the run and every later _err line (each rollback reason) vanishes.
    # Group the exec so the 2>/dev/null covers only its own failure message; fd 9 still stays open.
    { exec 9<>"$OC_LEASE_PATH"; } 2>/dev/null || return 1
    if ! flock -n 9 2>/dev/null; then
      { exec 9>&-; } 2>/dev/null || true
      return 3
    fi
    if _lease_owner_live; then
      flock -u 9 2>/dev/null || true
      { exec 9>&-; } 2>/dev/null || true
      return 3
    fi
    _lease_write_own "${RUN_ID:-oc-atomic-$$}" || return 1
    OC_LEASE_STATE="owned"
    _say "lease     : acquired $OC_LEASE_PATH (flock + record, pid $$)"
    return 0
  fi

  if _lease_owner_live; then return 3; fi
  if [ -e "$OC_LEASE_PATH" ]; then rm -f "$OC_LEASE_PATH" 2>/dev/null || return 1; fi
  ( set -o noclobber; : > "$OC_LEASE_PATH" ) 2>/dev/null || return 3
  _lease_write_own "${RUN_ID:-oc-atomic-$$}" || return 1
  OC_LEASE_STATE="owned"
  _say "lease     : acquired $OC_LEASE_PATH (exclusive create, pid $$)"
  return 0
}

_lease_release() {
  if [ "$OC_LEASE_STATE" = "owned" ]; then
    if [ "$OC_LEASE_IMPL" = "helper" ]; then
      command -v box_update_lock_release >/dev/null 2>&1 && box_update_lock_release
    elif _lease_owner_live && [ "$(_lease_rpid)" = "$$" ]; then
      rm -rf "$OC_LEASE_PATH" 2>/dev/null || true
    fi
  fi
  OC_LEASE_STATE=""
  return 0
}

# mac.MAC-2 — an UNPINNED upgrade (the Saturday 23:59 cron: no
# --target-version, so the target is whatever npm says at that minute) must
# never run while another writer owns this box. It reports WHY through
# _UPW_WHY. A PINNED upgrade does not need this probe: the lease acquire below
# already refuses a live foreign writer, and a holder in our own process tree
# is the roll that spawned us.
_UPW_WHY=""
_unpinned_foreign_writer() {
  _UPW_WHY=""
  local _root _ap
  _root="${OC_ROOT_DIR:-$HOME/.openclaw}"
  _ap="$_root/fleet-refresh/agent-pull.lock/pid"
  if [ -f "$_ap" ]; then
    local _pp
    _pp="$(head -1 "$_ap" 2>/dev/null || true)"
    if [ -n "$_pp" ] && kill -0 "$_pp" 2>/dev/null; then
      _UPW_WHY="a self-update / agent-pull run holds agent-pull.lock (pid $_pp)"
      return 0
    fi
  fi
  if _lease_owner_live && ! _lease_in_owner_tree; then
    _UPW_WHY="the installation lease $OC_LEASE_PATH is held by pid $(_lease_rpid) ($(sed -n 's/^role=//p' "$OC_LEASE_PATH" 2>/dev/null | head -1))"
    return 0
  fi
  return 1
}

# ── The maintenance lock. remediate.sh / gateway-health-watchdog.sh honour it.
# ── It exists because the 5-minute self-heal ALSO runs from cron on some boxes,
# ── where there is no LaunchAgent to boot out — a bootout alone would leave a
# ── cron-driven remediator free to bootstrap the gateway back mid-procedure and
# ── silently revert the migration (fact 3).
_lock_acquire() {
  mkdir -p "$OC_ROOT_DIR" 2>/dev/null
  # `start=` is the process START IDENTITY (mac.MAC-13): remediate.sh decides a
  # maintenance lock is stale from pid + this identity, NEVER from its age, so a
  # slow upgrade is never healed out from under itself and a recycled pid is not
  # mistaken for a live one. `started=` is the human timestamp.
  printf 'pid=%s\nstart=%s\nstarted=%s\nreason=oc-atomic-upgrade v%s\n' \
    "$$" "$(_lease_start "$$")" "$(date '+%Y-%m-%dT%H:%M:%S')" "$VERSION" > "$LOCK_FILE" 2>/dev/null
  if [ ! -f "$LOCK_FILE" ]; then
    _err "could not write the maintenance lock at $LOCK_FILE"
    return 1
  fi
  _ok "maintenance lock held: $LOCK_FILE (self-heal will stand down)"
  return 0
}
_lock_release() { rm -f "$LOCK_FILE" 2>/dev/null; }

# ─────────────────────────────────────────────────────────────────────────────
# QUIESCE
# ─────────────────────────────────────────────────────────────────────────────
# Stop the gateway job/container and PROVE it is gone. bootout, NOT kickstart -k: kickstart
# restarts the process and leaves the job loaded, so KeepAlive respawns it every ~11s; only
# bootout is a stop, and it is ASYNCHRONOUS (it returns before the job has left launchd), so
# the proof is a bounded poll, never a one-shot check. Shared by the quiesce and by the npm
# window (_gateway_stop_for_npm). rc 1 = it is still there; the caller refuses to go on.
_stop_gateway_job() {
  case "$SUPERVISOR" in
    launchd)
      launchctl bootout "gui/$UIDN/$GATEWAY_LABEL" >/dev/null 2>&1
      if ! _poll "$BOOTOUT_TIMEOUT" _gateway_unloaded; then
        _err "gateway job $GATEWAY_LABEL is STILL LOADED ${BOOTOUT_TIMEOUT}s after bootout — refusing to continue"
        return 1
      fi
      _ok "gateway job booted out of gui/$UIDN (not merely restarted)"
      ;;
    docker)
      # CAN016: compose layout container (<project>-openclaw-1). Same contract as
      # the literal-name case: an explicit stop is not revived by restart policy.
      local c
      c="$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep 'openclaw' | head -1)"
      if [ -n "$c" ]; then
        docker stop "$c" >/dev/null 2>&1 || return 1
        _ok "container $c stopped (restart:unless-stopped does not revive an explicit stop)"
      else
        docker stop openclaw >/dev/null 2>&1 || return 1
        _ok "container openclaw stopped (restart:unless-stopped does not revive an explicit stop)"
      fi
      ;;
  esac
  return 0
}

_quiesce() {
  # Rollback state is set BEFORE the stop it undoes (see the state block at the
  # top). It used to be set after, so a quiesce that failed returned early with
  # STATE_QUIESCED=0 and the rollback never restarted the gateway it had just
  # booted out -- then printed "exactly as it was found".
  STATE_QUIESCED=1
  case "$SUPERVISOR" in
    launchd)
      # The self-heal agent first: booting the gateway out while its watchdog is
      # still armed just races it back up within 5 minutes.
      if _job_loaded "$SELFHEAL_LABEL"; then
        STATE_SELFHEAL_BOOTED_OUT=1
        launchctl bootout "gui/$UIDN/$SELFHEAL_LABEL" >/dev/null 2>&1
        _ok "self-heal agent $SELFHEAL_LABEL booted out"
      fi
      _stop_gateway_job || return 1
      ;;
    docker) _stop_gateway_job || return 1 ;;
    none)
      _ok "no supervisor found — nothing to quiesce"
      ;;
  esac
  return 0
}

# ── #21: THE NPM WINDOW. A gateway job that is LOADED while npm rewrites the package gets
# ── respawned by KeepAlive every ~11s against a half-written tree ("Cannot find module
# ── .../dist/index.js"), so the stability window never holds and a rollback that reinstalls
# ── the old build the same way leaves the box dark. Every npm install here therefore runs
# ── with the job proven booted out for the WHOLE window, and nothing may bootstrap it again
# ── until the package measures complete.
# A package is complete when it measures a version AND the file the supervisor launches
# exists (the very file the half-written tree was missing).
_package_complete() {
  [ -n "$(_measured_version)" ] || return 1
  [ -z "$SUP_ENTRY" ] || [ -f "$SUP_ENTRY" ] || return 1
  [ -z "$SUP_PKG_ROOT" ] || [ -f "$SUP_PKG_ROOT/package.json" ]
}
# Make sure the gateway is not loaded right now. No-op when it already is not (the normal
# case: the quiesce booted it out); after a failed START it IS loaded and must be booted out
# again before the rollback reinstalls anything.
_gateway_stop_for_npm() {
  _gateway_loaded || return 0
  _warn "the gateway is LOADED at the start of an npm window (KeepAlive would respawn it against a half-written package) - stopping it first"
  _stop_gateway_job
}
# npm install of $1 with the gateway held stopped on BOTH sides of it. rc 2 = the gateway
# could not be held stopped, so npm never ran; otherwise npm's own rc.
_npm_install_held() {
  local rc out
  _gateway_stop_for_npm || return 2
  out="$(mktemp "${TMPDIR:-/tmp}/oc-atomic-npm.XXXXXX" 2>/dev/null)" || out=/dev/null
  _npm_install "$1" >"$out" 2>&1; rc=$?
  [ "$rc" -eq 2 ] && rc=1      # 2 is this function's own "never ran" code
  # v1.2.3: a failed install used to say only "FAILED" (its output went to /dev/null), so four
  # boxes rolled back with no reason in the job log. Show npm's last 40 lines (secret-looking
  # lines dropped: a registry auth error can echo a token) and the node npm ran under.
  if [ "$rc" -ne 0 ]; then
    _err "npm exited $rc (ran under $(command -v node 2>/dev/null || echo 'no node on PATH') $(node -v 2>/dev/null)); its last 40 lines follow"
    tail -n 40 "$out" 2>/dev/null | grep -viE 'token|secret|apikey|password|bearer|_auth' | sed 's/^/[oc-atomic-upgrade]   npm| /' >&2
  fi
  [ "$out" = /dev/null ] || rm -f "$out"
  # Something (a remediator that ignored the lock, a stray bootstrap) loaded the job DURING
  # the window: it may have imported a half-written tree. Stop it again so the start that
  # follows the install is a fresh process on the complete package.
  if _gateway_loaded; then
    _warn "the gateway job was loaded again DURING the npm window - booting it out so it restarts on the finished package"
    _gateway_stop_for_npm || return 2
  fi
  return "$rc"
}

# ── PROVE the quiesce. An absent process is a claim; a config that stops
# ── changing is the measurement, because the once-a-minute writer is the actual
# ── thing that would revert the migration.
_prove_quiesced() {
  local pid sha_a sha_b
  pid="$(_gateway_pid)"
  if [ -n "$pid" ]; then
    _err "a gateway process is STILL RUNNING (pid present) after the stop — refusing to rewrite a live config"
    return 1
  fi
  if [ "$QUIESCE_PROOF_SECONDS" -le 0 ]; then
    _warn "quiesce proof window disabled (OC_ATOMIC_QUIESCE_PROOF_SECONDS=$QUIESCE_PROOF_SECONDS) — the once-a-minute writer was NOT proven stopped"
    return 0
  fi
  sha_a="$(_config_sha)"
  _say "proving the once-a-minute config writer has stopped (${QUIESCE_PROOF_SECONDS}s window)..."
  sleep "$QUIESCE_PROOF_SECONDS"
  sha_b="$(_config_sha)"
  if [ -z "$sha_a" ] || [ -z "$sha_b" ]; then
    _err "could not hash the config to prove quiescence — no shasum/sha256sum available. UNDETERMINED, not clear."
    return 1
  fi
  if [ "$sha_a" != "$sha_b" ]; then
    _err "the config CHANGED during the quiesce window — something is still writing it. Refusing."
    return 1
  fi
  _ok "config unchanged across ${QUIESCE_PROOF_SECONDS}s — the writer is stopped"
  return 0
}

_start_gateway() {
  case "$SUPERVISOR" in
    launchd)
      local plist="$HOME/Library/LaunchAgents/$GATEWAY_LABEL.plist"
      if [ ! -f "$plist" ]; then
        _err "no LaunchAgent plist at $plist — cannot bootstrap the gateway back"
        return 1
      fi
      # The exit code is a claim, not the result: bootstrap can exit non-zero
      # (e.g. 5) while the job really did load. _prove_started measures it.
      launchctl bootstrap "gui/$UIDN" "$plist" >/dev/null 2>&1
      ;;
    docker) docker start openclaw >/dev/null 2>&1 || { local c; c="$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep 'openclaw' | head -1)"; [ -n "$c" ] && docker start "$c" >/dev/null 2>&1; } || return 1 ;;
    none)   return 0 ;;
  esac
  return 0
}

# One tick of the rollback's "put the gateway back" loop. rc 0 ONLY when the job
# is loaded, has a pid, and /healthz answers 200 -- each earlier miss does the
# one corrective action for that miss and returns 1 so _poll re-checks.
_restore_gateway_step() {
  case "$SUPERVISOR" in
    launchd)
      if ! _job_loaded "$GATEWAY_LABEL"; then
        launchctl bootstrap "gui/$UIDN" "$HOME/Library/LaunchAgents/$GATEWAY_LABEL.plist" >/dev/null 2>&1
        return 1
      fi
      if [ -z "$(_gateway_pid)" ]; then
        launchctl kickstart "gui/$UIDN/$GATEWAY_LABEL" >/dev/null 2>&1
        return 1
      fi
      ;;
    docker)
      if ! _gateway_loaded; then
        local c
        c="$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep 'openclaw' | head -1)"
        if [ -n "$c" ]; then docker start "$c" >/dev/null 2>&1; else docker start openclaw >/dev/null 2>&1; fi
        return 1
      fi
      ;;
  esac
  _healthz_ok
}

# Put back the gateway the rollback stopped, and PROVE it. A bootstrap exit code
# is a claim; loaded + pid + /healthz 200 is the result -- and it must still hold
# after SETTLE_SECONDS. One good moment is not proof: a bootout that outlived
# BOOTOUT_TIMEOUT is still tearing down, answers healthy until it lands, and then
# removes the job (the box goes dark after we claimed success). If the job did not
# hold, loop: the step re-bootstraps it. Bounded at 3 attempts.
_restore_gateway() {
  local attempt=0 pid_a pid_b l h p
  if [ "$SUPERVISOR" = "launchd" ] && [ ! -f "$HOME/Library/LaunchAgents/$GATEWAY_LABEL.plist" ]; then
    _err "no LaunchAgent plist at $HOME/Library/LaunchAgents/$GATEWAY_LABEL.plist — cannot bootstrap the gateway back"
    return 1
  fi
  while [ "$attempt" -lt 3 ]; do
    attempt=$((attempt+1))
    if _poll "$HEALTH_TIMEOUT" _restore_gateway_step; then
      pid_a="$(_gateway_pid)"
      if [ "$SETTLE_SECONDS" -gt 0 ]; then
        _say "gateway answered (pid ${pid_a:-none}); holding ${SETTLE_SECONDS}s to prove an earlier, slower bootout cannot still remove it..."
        sleep "$SETTLE_SECONDS"
      else
        _warn "rollback settle window disabled (OC_ATOMIC_SETTLE_SECONDS=0) — 'still up' was NOT proven"
      fi
      pid_b="$(_gateway_pid)"
      if _gateway_loaded && [ -n "$pid_b" ] && [ "$pid_a" = "$pid_b" ] && _healthz_ok; then
        _ok "gateway PROVEN back and HELD ${SETTLE_SECONDS}s: $SUPERVISOR state loaded, pid $pid_b, /healthz 200"
        return 0
      fi
      _warn "gateway did not hold through the settle window (pid ${pid_a:-none} -> ${pid_b:-none}) — re-loading (attempt $attempt of 3)"
    else
      break
    fi
  done
  l=no; h=no
  _gateway_loaded && l=yes
  _healthz_ok && h=yes
  p="$(_gateway_pid)"
  _err "gateway NOT proven back (job loaded: $l; pid: ${p:-none}; /healthz 200: $h; attempts: $attempt; per-attempt wait ${HEALTH_TIMEOUT}s)"
  return 1
}

_restore_selfheal() {
  [ "$STATE_SELFHEAL_BOOTED_OUT" = "1" ] || return 0
  local plist="$HOME/Library/LaunchAgents/$SELFHEAL_LABEL.plist"
  if [ -f "$plist" ]; then
    # bootstrap while the earlier bootout is still tearing down fails, so retry
    # until launchd actually reports the job loaded -- not until bootstrap exits 0.
    if _poll "$HEALTH_TIMEOUT" _selfheal_rearm_step; then
      STATE_SELFHEAL_BOOTED_OUT=0
      _ok "self-heal agent $SELFHEAL_LABEL back and loaded"
      return 0
    fi
    _warn "self-heal agent $SELFHEAL_LABEL is NOT loaded after bootstrap. Re-run platform/mac/service-selfheal/install-service-remediate.sh"
  else
    _warn "self-heal plist $plist is gone — could not re-arm $SELFHEAL_LABEL. Re-run platform/mac/service-selfheal/install-service-remediate.sh"
  fi
  return 1
}
_selfheal_rearm_step() {
  _job_loaded "$SELFHEAL_LABEL" && return 0
  launchctl bootstrap "gui/$UIDN" "$HOME/Library/LaunchAgents/$SELFHEAL_LABEL.plist" >/dev/null 2>&1
  _job_loaded "$SELFHEAL_LABEL"
}

# ── Prove the gateway STAYED up. A pid at t0 proves it launched; the same pid
# ── still there at t0+N proves it did not exit 78 and get respawned. The
# ── crash-loop period is ~11s, so the default window spans at least two.
_prove_started() {
  local pid_a pid_b
  [ "$SUPERVISOR" = "none" ] && { _ok "no supervisor — nothing to prove started"; return 0; }
  sleep 3
  pid_a="$(_gateway_pid)"
  if [ -z "$pid_a" ]; then
    _err "the gateway did NOT come up (no pid after start)"
    return 1
  fi
  if [ "$STABILITY_SECONDS" -le 0 ]; then
    _warn "stability window disabled (OC_ATOMIC_STABILITY_SECONDS=$STABILITY_SECONDS) — 'stayed up' was NOT proven"
  else
    _say "proving the gateway STAYS up (${STABILITY_SECONDS}s, pid=$pid_a)..."
    sleep "$STABILITY_SECONDS"
    pid_b="$(_gateway_pid)"
    if [ -z "$pid_b" ]; then
      _err "the gateway DIED during the stability window — it came up and then exited"
      return 1
    fi
    if [ "$pid_a" != "$pid_b" ]; then
      _err "the gateway pid CHANGED during the stability window ($pid_a -> $pid_b) — that is the crash-loop signature (exit 78 + KeepAlive respawn), not a healthy start"
      return 1
    fi
  fi
  # A stable pid is a process, not a service: require it to ANSWER, same as the rollback.
  if ! _poll "$HEALTH_TIMEOUT" _healthz_ok; then
    _err "the gateway is up (pid $(_gateway_pid)) but GET /healthz never answered 200 within ${HEALTH_TIMEOUT}s"
    return 1
  fi
  _ok "gateway up, stable and answering /healthz 200 (pid $(_gateway_pid))"
  return 0
}

# ── Epoch seconds a process started (ps etime is [[dd-]hh:]mm:ss on macOS and Linux), and
# ── the epoch a file's inode last changed (GNU stat -c %Z, then BSD stat -f %c). "" on any failure.
_proc_start_epoch() {
  local e d=0 a b c secs
  e="$(ps -o etime= -p "$1" 2>/dev/null | tr -d '[:space:]')"
  case "$e" in ''|*[!0-9:-]*) return 1 ;; esac
  case "$e" in *-*) d="${e%%-*}"; e="${e#*-}" ;; esac
  IFS=: read -r a b c <<<"$e"
  if [ -n "$c" ]; then secs=$((10#$a*3600 + 10#$b*60 + 10#$c)); else secs=$((10#$a*60 + 10#$b)); fi
  printf '%s' "$(( $(date +%s) - 10#$d*86400 - secs ))"
}
_file_ctime() { stat -c %Z "$1" 2>/dev/null || stat -f %c "$1" 2>/dev/null; }  # GNU first: on GNU, `stat -f %c` succeeds with filesystem info

# ── CAN015: success means the GATEWAY PROCESS runs the target, not that some
# ── openclaw on PATH reports it. The package the supervisor launches must measure
# ── the target now, and (launchd) the live pid's command line must be that very
# ── launch path. (ps -o args= shows arguments only; the environment is never read.)
_prove_gateway_on_target() {
  local v pid args
  v="$(_measured_version)"
  if [ "$v" != "$TARGET_VERSION" ]; then
    _err "the package the gateway launches measures '${v:-nothing}', not $TARGET_VERSION"
    return 1
  fi
  pid="$(_gateway_pid)"
  # No pid, no proof: never claim "gateway pid  runs ..." for a process nobody identified.
  if [ -z "$pid" ]; then _err "no gateway process is identified (supervisor: $SUPERVISOR) - cannot prove it runs the target"; return 1; fi
  if ! _healthz_ok; then _err "/healthz did not answer 200"; return 1; fi
  if [ "$SUPERVISOR" = "launchd" ] && [ -n "$SUP_ENTRY" ]; then
    args="$(ps -o args= -p "$pid" 2>/dev/null)"
    if [ -z "$args" ]; then
      _warn "could not read the gateway process arguments (pid ${pid:-none}); package version and /healthz are the evidence"
    else
      case "$args" in
        *"$SUP_ENTRY"*) ;;
        *) _err "the live gateway (pid $pid) was not launched from $SUP_ENTRY"; return 1 ;;
      esac
    fi
  fi
  # A gateway started BEFORE the package on disk was (re)installed still runs the old code even
  # though its args, the package.json version and /healthz all look right (in-place `npm i -g`
  # with no restart). So the pid must have started no earlier than the package's last change.
  if [ -n "$SUP_PKG_ROOT" ]; then
    local started changed
    started="$(_proc_start_epoch "$pid")"; changed="$(_file_ctime "$SUP_PKG_ROOT/package.json")"
    if [ -z "$started" ] || [ -z "$changed" ]; then
      _err "cannot compare the gateway start time (pid $pid: '${started:-?}') with the package change time ('${changed:-?}'); not proven"
      return 1
    fi
    # 2s slack: etime is whole seconds, so the derived start can be a second early.
    if [ $((started + 2)) -lt "$changed" ]; then
      _err "the live gateway (pid $pid) started before $SUP_PKG_ROOT/package.json last changed - it predates the installed build"
      return 1
    fi
  fi
  _ok "gateway pid $(_gateway_pid) runs $SUP_PKG_ROOT at $v (target $TARGET_VERSION), /healthz 200"
  return 0
}

# ─────────────────────────────────────────────────────────────────────────────
# STATE-DATABASE HOLDERS (fleet-roll error #18) AND DOCTOR (error #16)
# ─────────────────────────────────────────────────────────────────────────────
# #18: a stale `openclaw` CLI from an earlier run (a hung status / config validate /
# memory command) still holds <root>/state/openclaw.sqlite open. The new gateway
# then refuses to start ("undergoing offline maintenance") and doctor refuses to
# take maintenance ("An agent database is in use"). Only a bare CLI that started
# BEFORE this run is ever stopped; see _reap_state_holders for what is never touched.
# #16: the new gateway refuses an agent database at schema 24, and only
# `doctor --fix` migrates it (see the header). Doctor needs the gateway stopped and
# no other holder, which is exactly the window this script already owns.
# Both apply to the launchd supervisor only; a docker install keeps its state inside
# the container, where nothing here can see it, and is left exactly as before.

_pid_gone() { ! kill -0 "$1" 2>/dev/null; }

# Prints the subcommand word (e.g. "doctor") and returns 0 ONLY when $1 is a bare
# openclaw CLI invocation: `openclaw <word> ...`, or `node <...>/openclaw[.mjs|/dist/*.js]
# <word> ...`. Anything else returns 1 and prints nothing: a gateway or node-host service
# or other long-running / interactive subcommand, the OpenClaw app (*.app), an unparseable
# command line, or any process that is not openclaw. Only ps's argument vector is read
# (never the environment), and only the subcommand word is ever printed.
_cli_holder_subcommand() (
  local args tok seen=0 sub=""
  args="$(ps -o args= -p "$1" 2>/dev/null)"
  [ -n "$args" ] || exit 1
  case "$args" in *.app/*|*.app\ *) exit 1 ;; esac
  set -f
  for tok in $args; do
    if [ "$seen" = "0" ]; then
      case "$tok" in
        -*) ;;                                        # a runtime flag, e.g. node --max-old-space-size=4096
        node|*/node|nodejs|*/nodejs) ;;               # the runtime hosting the CLI
        openclaw|*/openclaw|*/openclaw.mjs|*/openclaw/dist/*.js|*/openclaw/dist/*.mjs) seen=1 ;;
        *) exit 1 ;;
      esac
      continue
    fi
    case "$tok" in -*) continue ;; esac
    sub="$tok"
    break
  done
  case "$sub" in
    ''|*[!a-z0-9-]*) exit 1 ;;
    gateway|node|daemon|acp|mcp|tui|chat|terminal|attach|connect|dashboard|proxy|worker|onboard|configure|browser|voicecall|webhooks|resume) exit 1 ;;
  esac
  printf '%s' "$sub"
)

# Pids holding the shared state database (or its -wal/-shm) open, one per line.
# rc 0 = measured (the list may be empty); rc 2 = could not measure (no lsof). An
# unmeasurable state is NOT "nobody holds it".
_state_holders() {
  local f
  command -v lsof >/dev/null 2>&1 || return 2
  for f in "$OC_ROOT_DIR/state/openclaw.sqlite" "$OC_ROOT_DIR/state/openclaw.sqlite-wal" "$OC_ROOT_DIR/state/openclaw.sqlite-shm"; do
    [ -e "$f" ] && lsof -t "$f" 2>/dev/null
  done | sort -u | grep -E '^[0-9]+$'
  return 0
}

# Stop the STALE bare `openclaw` CLI processes that hold the state database, and log
# each one. A holder is left alone unless ALL of these hold: it is a bare openclaw CLI
# (_cli_holder_subcommand), it is not this process or one of its parents, it is not the
# gateway pid, and it started clearly BEFORE this run (2s slack: etime is whole seconds).
# SIGTERM first, SIGKILL only if it survives. rc 0 = nobody we can see holds the database
# afterwards (or lsof is missing: said so, not assumed clear); rc 1 = someone still does.
_reap_state_holders() {
  local where="$1" pids pid sub started gw anc p n rc left
  [ "$SUPERVISOR" = "launchd" ] || return 0
  pids="$(_state_holders)"; rc=$?
  if [ "$rc" -eq 2 ]; then
    _warn "lsof is not available - who holds $OC_ROOT_DIR/state/openclaw.sqlite ($where) is UNDETERMINED, not 'nobody'"
    return 0
  fi
  [ -n "$pids" ] || { _ok "no process holds the state database ($where)"; return 0; }
  anc=" $$ "; p="$$"; n=0
  while [ "$n" -lt 64 ]; do
    p="$(_lease_ppid "$p")"
    case "$p" in ''|*[!0-9]*) break ;; esac
    [ "$p" -gt 1 ] || break
    anc="$anc$p "; n=$((n+1))
  done
  gw="$(_gateway_pid)"
  for pid in $pids; do
    case "$anc" in *" $pid "*) _say "state-database holder pid $pid is this run or one of its parents - left alone"; continue ;; esac
    if [ -n "$gw" ] && [ "$pid" = "$gw" ]; then _say "state-database holder pid $pid is the gateway - left alone"; continue; fi
    sub="$(_cli_holder_subcommand "$pid")" || sub=""
    if [ -z "$sub" ]; then
      _say "state-database holder pid $pid is not a bare openclaw CLI (a service, the app, or another program) - left alone"
      continue
    fi
    started="$(_proc_start_epoch "$pid")"
    if [ -z "$started" ]; then
      _say "state-database holder pid $pid (openclaw $sub): start time unreadable - left alone"
      continue
    fi
    if [ $((started + 2)) -ge "$RUN_START_EPOCH" ]; then
      _say "state-database holder pid $pid (openclaw $sub) started during this run - left alone"
      continue
    fi
    kill -TERM "$pid" 2>/dev/null
    _poll 5 _pid_gone "$pid" || { kill -KILL "$pid" 2>/dev/null; _poll 3 _pid_gone "$pid"; }
    if _pid_gone "$pid"; then
      _ok "reaped stale openclaw CLI holder pid $pid (openclaw $sub, started $((RUN_START_EPOCH - started))s before this run; $where)"
    else
      _warn "stale openclaw CLI holder pid $pid (openclaw $sub) did not stop"
    fi
  done
  left="$(_state_holders | tr '\n' ' ' | sed 's/ *$//')"
  if [ -n "$left" ]; then
    _warn "the state database is still held by pid(s): $left ($where)"
    return 1
  fi
  _ok "no process holds the state database ($where)"
  return 0
}

# Run a command with stdin from /dev/null, stdout+stderr into $2, and the whole process
# group killed after $1 seconds. rc 124 = timed out; 127 = could not start; otherwise the
# command's own exit code (a signal death is 128+signal).
# #24: with OC_BOUNDED_LOOP_RE and OC_BOUNDED_LOOP_N set, the command is also killed EARLY (rc 125)
# once one output line matching that regex has been printed N times (digits ignored, so a timestamp
# or a pid does not hide the repeat). That is a command spinning on the same error, and waiting out
# the whole bound for it would leave the box dark for nothing; a command that merely mentions an
# error once or twice is left to finish.
_run_bounded() {
  local t="$1" out="$2"
  shift 2
  python3 -I - "$t" "$out" "$@" <<'PY'
import os, re, signal, subprocess, sys, time
t, out, cmd = int(sys.argv[1]), sys.argv[2], sys.argv[3:]
lre, ln = os.environ.get("OC_BOUNDED_LOOP_RE", ""), int(os.environ.get("OC_BOUNDED_LOOP_N") or 0)
rx = re.compile(lre) if lre and ln > 0 else None

def looping():
    seen = {}
    with open(out, "r", errors="replace") as fh:
        for line in fh:
            if rx.search(line):
                k = re.sub(r"[0-9]+", "#", line.strip())[:300]
                seen[k] = seen.get(k, 0) + 1
                if seen[k] >= ln:
                    return True
    return False

with open(out, "wb") as fh:
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as e:
        fh.write(("cannot start %s: %s\n" % (cmd[0], e.strerror)).encode())
        sys.exit(127)
    end = time.monotonic() + t
    while True:
        left = end - time.monotonic()
        try:
            rc = p.wait(timeout=max(0.0, min(1.0, left)))
            break
        except subprocess.TimeoutExpired:
            pass
        if rx is not None and looping():
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            sys.exit(125)
        if left <= 0:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            sys.exit(124)
sys.exit(rc if rc >= 0 else 128 - rc)
PY
}

# Doctor output is advisory text, but mask anything shaped like a credential before it is logged.
_mask_secrets() {
  sed -E \
    -e 's/(sk|rk|pk|ghp|gho|ghs|xox[abprs]|AIza|ya29)[-_.A-Za-z0-9]{16,}/<masked>/g' \
    -e 's/([Tt]oken|[Kk]ey|[Ss]ecret|[Pp]assw(or)?d|[Aa]uthorization|[Bb]earer)([^[:space:]]{0,30})([=:][[:space:]]*|[[:space:]]+)[^[:space:]]+/\1\3\4<masked>/g'
}

# One line of JSON naming ONLY the model selection: agents.defaults.model (primary, fallbacks),
# the NAMES pinned in agents.defaults.models, and each agent's own model. NOCONFIG when there is
# no config, UNREADABLE when it cannot be parsed. Values are model names, never credentials.
_model_snapshot() {
  [ -f "$OC_CONFIG" ] || { printf 'NOCONFIG'; return 0; }
  OC_CFG="$OC_CONFIG" python3 -I -c 'import json,os
def nm(m):
    if isinstance(m, str):
        return {"primary": m, "fallbacks": []}
    if isinstance(m, dict):
        return {"primary": m.get("primary"), "fallbacks": m.get("fallbacks") or []}
    return None
try:
    c = json.load(open(os.environ["OC_CFG"]))
    a = c.get("agents") or {}
    d = a.get("defaults") or {}
    pins = d.get("models")
    ents = a.get("entries")
    if not isinstance(ents, dict):
        ents = dict((str(e.get("id", i)), e) for i, e in enumerate(a.get("list") or []) if isinstance(e, dict))
    print(json.dumps({"defaults": nm(d.get("model")),
                      "pins": sorted(pins) if isinstance(pins, dict) else None,
                      "agents": dict((k, nm(v.get("model"))) for k, v in ents.items() if isinstance(v, dict) and "model" in v)},
                     sort_keys=True))
except Exception:
    print("UNREADABLE")' 2>/dev/null || printf 'UNREADABLE'
}

# Doctor refuses the audit-logs migration when the sanitized archive no longer matches its
# checkpoint, and there is no supported flag for it (vendor docs: "do not delete or rewrite
# archives"). The unsupported narrow repair is to drop ONLY the raw-archive checkpoint rows
# (exactly scope 'migration.legacy-audit-raw' in diagnostic_events of the shared state
# database) so doctor re-parses the raw archive and de-duplicates it by key. NEVER a LIKE:
# 'migration.legacy-audit' is the live coordination lease. The rows are saved first, the
# before/after counts are logged, and nothing is deleted while any process holds the database.
_repair_audit_checkpoint() {
  local db="$OC_ROOT_DIR/state/openclaw.sqlite" rows rc
  if [ ! -f "$db" ]; then
    _err "no state database at $db - there is no audit checkpoint to repair"
    return 1
  fi
  if ! _reap_state_holders "before the audit-checkpoint repair"; then
    _err "a process still holds the state database - refusing to edit it"
    return 1
  fi
  rows="$OC_ROOT_DIR/audit-checkpoint-rows-$(date +%Y%m%d-%H%M%S).json"
  OC_STATE_DB="$db" OC_ROWS_OUT="$rows" python3 -I - <<'PY'
import json, os, sqlite3, sys
SCOPE = "migration.legacy-audit-raw"
db, out = os.environ["OC_STATE_DB"], os.environ["OC_ROWS_OUT"]
try:
    con = sqlite3.connect(db, timeout=15)
    cur = con.execute("SELECT * FROM diagnostic_events WHERE scope = ?", (SCOPE,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, [v if v is None or isinstance(v, (int, float, str)) else repr(v) for v in r])) for r in cur.fetchall()]
    if not rows:
        print("    | no rows with scope %s - nothing to delete" % SCOPE)
        sys.exit(3)
    with os.fdopen(os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as fh:
        json.dump(rows, fh)
    deleted = con.execute("DELETE FROM diagnostic_events WHERE scope = ?", (SCOPE,)).rowcount
    con.commit()
    left = con.execute("SELECT COUNT(*) FROM diagnostic_events WHERE scope = ?", (SCOPE,)).fetchone()[0]
    print("    | scope %s: rows before=%d deleted=%d after=%d (saved to %s)" % (SCOPE, len(rows), deleted, left, out))
    sys.exit(0 if left == 0 else 1)
except Exception as e:
    print("    | audit checkpoint repair failed: %s: %s" % (type(e).__name__, e))
    sys.exit(1)
PY
  rc=$?
  [ "$rc" -eq 0 ]
}

# Run the NEW binary's `doctor --fix --non-interactive` so the agent/session database is
# migrated before the gateway starts. rc 0 = doctor exited 0 with no refused step and the
# model/provider names are unchanged; rc 1 = failed, the reason is in DOCTOR_WHY and the
# caller rolls back. Called only after the quiesce is PROVEN and the new binary is on disk.
_migrate_state_with_doctor() {
  local out rc attempt=0 refused before after qrc
  DOCTOR_WHY=""
  if ! _reap_state_holders "before doctor"; then
    DOCTOR_WHY="another process still holds $OC_ROOT_DIR/state/openclaw.sqlite and is not a stale bare openclaw CLI this script may stop, so \`openclaw doctor --fix\` would refuse (it needs exclusive maintenance)"
    return 1
  fi
  before="$(_model_snapshot)"
  if [ "$before" = "UNREADABLE" ]; then
    DOCTOR_WHY="the model/provider selection in $OC_CONFIG could not be read, so \"doctor did not change it\" cannot be proven - refusing to run doctor"
    return 1
  fi
  out="$(mktemp "${TMPDIR:-/tmp}/oc-doctor.XXXXXX")" || {
    DOCTOR_WHY="could not create a temp file for the doctor output"; return 1; }
  # Doctor rewrites retired config keys: record that BEFORE it runs so the rollback restores the config.
  [ -f "$OC_CONFIG" ] && STATE_CONFIG_CHANGED=1
  while :; do
    attempt=$((attempt+1))
    _say "running the NEW binary: openclaw doctor --fix --non-interactive (attempt $attempt of 2, bound ${DOCTOR_TIMEOUT}s, stdin /dev/null) ..."
    OC_BOUNDED_LOOP_RE='ERR_MODULE_NOT_FOUND|ERR_PACKAGE_PATH_NOT_EXPORTED|Cannot find (module|package) ' OC_BOUNDED_LOOP_N="$DOCTOR_LOOP_LINES" \
      _run_bounded "$DOCTOR_TIMEOUT" "$out" openclaw doctor --fix --non-interactive; rc=$?
    tail -n 40 "$out" | _mask_secrets | sed 's/^/    | /'
    refused=0
    if grep -qF 'sanitized archive is missing or truncated' "$out" 2>/dev/null \
       || grep -qF 'sanitized archive changed after checkpoint' "$out" 2>/dev/null; then
      refused=1
    fi
    if [ "$rc" -eq 0 ] && [ "$refused" -eq 0 ]; then break; fi
    if [ "$refused" -eq 1 ] && [ "$attempt" -eq 1 ]; then
      _warn "doctor refused on the legacy-audit-raw checkpoint - dropping only that scope's rows, then re-running doctor once"
      if ! _repair_audit_checkpoint; then
        rm -f "$out"
        DOCTOR_WHY="doctor --fix refused on the legacy-audit-raw checkpoint and the narrow checkpoint repair did not complete"
        return 1
      fi
      continue
    fi
    # #24: doctor loads every enabled plugin's module at startup, BEFORE it fixes anything, and spins on one
    # whose import is gone. It was killed at the first sign of the loop (rc 125) or at its bound (rc 124), or
    # it died; if its own output names ONE plugin entry, disable that entry (only its `enabled` flag, recorded)
    # and run it again, bounded the same way. Not counted as one of the two doctor attempts.
    if [ "$rc" -ne 0 ] && [ "$PLUGIN_QUARANTINE_COUNT" -lt "$PLUGIN_QUARANTINE_MAX" ]; then
      _quarantine_from_output "$out"; qrc=$?
      if [ "$qrc" -eq 0 ]; then attempt=$((attempt-1)); continue; fi
      if [ "$qrc" -eq 2 ]; then rm -f "$out"; DOCTOR_WHY="$PLUGIN_WHY"; return 1; fi
    fi
    rm -f "$out"
    if [ "$rc" -eq 125 ]; then
      DOCTOR_WHY="doctor --fix was spinning on the same module-load error (ERR_MODULE_NOT_FOUND) that names no single enabled plugin entry, and was killed"
    elif [ "$rc" -eq 124 ]; then
      DOCTOR_WHY="doctor --fix did not finish within ${DOCTOR_TIMEOUT}s and was killed"
    elif [ "$refused" -eq 1 ]; then
      DOCTOR_WHY="doctor --fix STILL refuses on the audit checkpoint after the checkpoint repair and one re-run"
    else
      DOCTOR_WHY="doctor --fix FAILED (exit $rc, output above) - the agent/session database was not proven migrated"
    fi
    return 1
  done
  rm -f "$out"
  after="$(_model_snapshot)"
  if [ "$before" != "NOCONFIG" ] && [ "$after" != "$before" ]; then
    _err "doctor changed the model/provider selection:"
    _err "  before: $before"
    _err "  after : $after"
    DOCTOR_WHY="doctor --fix changed the model/provider selection (names above) - model config must never be touched"
    return 1
  fi
  _ok "doctor --fix exited 0 with no refused step; model/provider names identical before and after"
  return 0
}

# ─────────────────────────────────────────────────────────────────────────────
# ORPHAN GATEWAY (fleet-roll error #33)
# ─────────────────────────────────────────────────────────────────────────────
# A gateway left by an earlier run (ppid 1: launchd re-parented it) still owns the state
# database while this run boots out the JOB. The job's pid is empty, so the quiesce proof
# reads "nothing running", and the new LaunchAgent then exits 78 "Another gateway (pid N)
# already owns this state directory" - which used to be read as a bad binary and cost the
# box its whole first cycle. _reap_state_holders deliberately never touches a gateway; this
# is the one place that does, and only a process that passes EVERY test below:
#   * it holds the state database open (lsof, the same evidence _reap_state_holders uses),
#   * its command line is `[node ...] <openclaw entry> gateway` (or the `openclaw-gateway`
#     process title) - only the argument vector is read, never the environment, and only
#     the entry path is ever logged (a gateway can be started with a token on its line),
#   * it is not the launchd job's own pid, nor a child of it, nor this process,
#   * its start time is unchanged between the first look and each signal (identity, so a
#     recycled pid is never signalled).
# SIGTERM first, SIGKILL only if it survives. Launchd boxes only.

# rc 0 and prints the entry token iff pid $1 runs `[node flags] <openclaw entry> [flags] gateway`
# or is titled `openclaw-gateway`; anything else (the app, a CLI, another program) is rc 1.
_gateway_cmdline_entry() (
  local args tok seen=0 first=""
  args="$(ps -o args= -p "$1" 2>/dev/null)"
  [ -n "$args" ] || exit 1
  case "$args" in *.app/*|*.app\ *) exit 1 ;; esac
  set -f
  for tok in $args; do
    if [ -z "$first" ]; then
      first="$tok"
      case "$tok" in openclaw-gateway|*/openclaw-gateway) printf '%s' "$tok"; exit 0 ;; esac
    fi
    if [ "$seen" = "0" ]; then
      case "$tok" in
        -*) ;;
        node|*/node|nodejs|*/nodejs) ;;
        openclaw|*/openclaw|*/openclaw.mjs|*/openclaw/dist/*.js|*/openclaw/dist/*.mjs) seen=1; first="$tok" ;;
        *) exit 1 ;;
      esac
      continue
    fi
    case "$tok" in -*) continue ;; esac
    if [ "$tok" = "gateway" ]; then printf '%s' "$first"; exit 0; fi
    exit 1
  done
  exit 1
)

# rc 0 = no orphan gateway holds the state database afterwards (or lsof is missing: said so,
# not assumed clear); rc 1 = one still does. $1 = where in the run this is, for the log.
_reap_orphan_gateways() {
  local where="$1" pids pid gw rc ent started ppid left=""
  [ "$SUPERVISOR" = "launchd" ] || return 0
  pids="$(_state_holders)"; rc=$?
  if [ "$rc" -eq 2 ]; then
    _warn "lsof is not available - whether an orphan gateway owns $OC_ROOT_DIR/state ($where) is UNDETERMINED, not 'no'"
    return 0
  fi
  gw="$(_gateway_pid)"
  for pid in $pids; do
    [ "$pid" = "$$" ] && continue
    if [ -n "$gw" ] && [ "$pid" = "$gw" ]; then
      _say "state-database holder pid $pid is the launchd job's gateway - left alone ($where)"; continue
    fi
    ent="$(_gateway_cmdline_entry "$pid")" || continue      # a CLI or another program: _reap_state_holders' business
    ppid="$(_lease_ppid "$pid")"
    if [ -n "$gw" ] && [ "$ppid" = "$gw" ]; then
      _say "state-database holder pid $pid is a child of the launchd job's gateway (pid $gw) - left alone ($where)"; continue
    fi
    started="$(_lease_start "$pid")"
    if [ -z "$started" ]; then
      _warn "orphan gateway candidate pid $pid: start time unreadable, identity cannot be pinned - left alone ($where)"
      left="$left $pid"; continue
    fi
    _say "ORPHAN GATEWAY pid $pid (ppid ${ppid:-?}, started $started, $(basename "$ent")) holds the state database and is not the launchd job's pid (${gw:-job not running}) - stopping it ($where)"
    kill -TERM "$pid" 2>/dev/null
    _poll 10 _pid_gone "$pid" || {
      if [ "$(_lease_start "$pid")" = "$started" ] && _gateway_cmdline_entry "$pid" >/dev/null; then kill -KILL "$pid" 2>/dev/null; fi
      _poll 3 _pid_gone "$pid"
    }
    if _pid_gone "$pid"; then
      _ok "orphan gateway pid $pid stopped ($where)"
    else
      _err "orphan gateway pid $pid did NOT stop ($where)"
      left="$left $pid"
    fi
  done
  if [ -n "$left" ]; then
    _err "an orphan gateway still owns the state directory (pid(s):$left) - a start now would exit 78 and be misread as a bad binary"
    return 1
  fi
  return 0
}

# ─────────────────────────────────────────────────────────────────────────────
# UNLOADABLE PLUGIN (fleet-roll error #24)
# ─────────────────────────────────────────────────────────────────────────────
# `doctor` imports every enabled plugin's module at startup. When one plugin's import is
# gone (ERR_MODULE_NOT_FOUND from an `openclaw/plugin-sdk/...` export) it SPINS instead of
# failing: Star Bobatoon's `doctor --fix` hung until it was killed by hand. The load happens at
# startup, before doctor changes anything, so killing it there costs nothing. When the bounded
# doctor (_migrate_state_with_doctor) is killed - early by the loop detector in _run_bounded, or at
# its bound - or dies, and its own output names one enabled plugin entry, that entry - and only its
# `enabled` flag - is set to false, recorded, and doctor is run again. It never guesses (no single
# named plugin = nothing is touched), never edits the allow list or the entry's `config`, never
# creates an entry, and never calls
# `openclaw plugins install|enable|update` (codex is never installed or enabled here). The
# change lives in the config this run already backed up, so any rollback restores it byte
# for byte; the record below is how a human finds and reverses it after a SUCCESSFUL run.
PLUGIN_QUARANTINE_MAX=3

# <event> <plugin> <import> <was-enabled> -> one JSON line in <root>/oc-atomic-plugin-quarantine.jsonl
_plugin_record() {
  PLUGIN_RECORD="$OC_ROOT_DIR/oc-atomic-plugin-quarantine.jsonl"
  OC_REC="$PLUGIN_RECORD" OC_CFG="$OC_CONFIG" OC_BAK="${CONFIG_BACKUP:-}" OC_VER="$VERSION" python3 -I - "$@" <<'PY' 2>/dev/null
import json, os, sys, time
ev, plugin, imp, was = (sys.argv[1:5] + ["", "", "", ""])[:4]
rec = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": ev, "plugin": plugin,
       "failing_import": imp, "was_enabled": was, "config": os.environ["OC_CFG"],
       "config_backup": os.environ["OC_BAK"], "oc_atomic_upgrade": os.environ["OC_VER"],
       "restore": "set plugins.entries.%s.enabled back to %s in %s (or: cat the config_backup over it); then re-run openclaw doctor" % (plugin, was, os.environ["OC_CFG"])}
fd = os.open(os.environ["OC_REC"], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
with os.fdopen(fd, "a") as fh:
    fh.write(json.dumps(rec, sort_keys=True) + "\n")
PY
}

# Disable exactly plugins.entries.<$1>.enabled. rc 0 = done and recorded.
_plugin_disable_entry() {
  local id="$1" imp="$2" staged was
  staged="${OC_CONFIG}.atomic-staged.$$"
  was="$(python3 "$MIGRATOR" plugin-disable "$OC_CONFIG" "$id" "$staged" 2>/dev/null)" || { rm -f "$staged"; return 1; }
  was="${was#was=}"
  [ -s "$staged" ] || { rm -f "$staged"; return 1; }
  # Rollback state BEFORE the write it undoes.
  STATE_CONFIG_CHANGED=1
  # QC-ALLOW-NO-CHOWN: redirect through the existing inode — owner/group/mode preserved by construction.
  if ! cat "$staged" > "$OC_CONFIG" 2>/dev/null; then rm -f "$staged"; return 1; fi
  rm -f "$staged"
  PLUGIN_QUARANTINED="$PLUGIN_QUARANTINED $id"
  _plugin_record quarantined "$id" "$imp" "$was"
  return 0
}

# Name the plugin a doctor output file ($1) blames and disable that entry. Counts against
# PLUGIN_QUARANTINE_MAX; the caller checks PLUGIN_QUARANTINE_COUNT first. rc 0 = one entry disabled
# (run doctor again); rc 1 = nothing attributable, nothing touched; rc 2 = a plugin was named
# but its entry could not be disabled (PLUGIN_WHY).
PLUGIN_QUARANTINE_COUNT=0
PLUGIN_WHY=""
_quarantine_from_output() {
  local hit id imp
  hit="$(python3 "$MIGRATOR" plugin-attribute "$1" "$OC_CONFIG" 2>/dev/null)" || return 1
  id="${hit%%	*}"; imp="${hit#*	}"
  case "$id" in codex) _say "the failing plugin is codex: disabling its entry only - codex is never installed, enabled or accepted here" ;; esac
  if ! _plugin_disable_entry "$id" "$imp"; then
    PLUGIN_WHY="plugin '$id' fails to load ($imp) and doctor spins on it, but its entry in $OC_CONFIG could not be disabled"
    return 2
  fi
  PLUGIN_QUARANTINE_COUNT=$((PLUGIN_QUARANTINE_COUNT+1))
  _ok "QUARANTINED plugin '$id' (module fails to load: $imp): plugins.entries.$id.enabled set to false, nothing else changed; recorded in $PLUGIN_RECORD"
  return 0
}

# ─────────────────────────────────────────────────────────────────────────────
# ROLLBACK — undoes, in reverse, exactly what was recorded as done.
# ─────────────────────────────────────────────────────────────────────────────
_rollback() {
  local why="$1" failed=0 proved="" rc p
  echo "" >&2
  _err "ROLLING BACK: $why"

  if [ "$STATE_CONFIG_CHANGED" = "1" ] && [ -n "$CONFIG_BACKUP" ] && [ -f "$CONFIG_BACKUP" ]; then
    # `cat >` writes THROUGH the existing inode, so the file's owner, group and
    # mode are unchanged by construction — there is no ownership to restore. A
    # cp/mv is what would need a chown; that is exactly why this is a redirect.
    # On a root-run cron a cp would leave the config root-owned, the gateway (a
    # non-root uid) would get EACCES on reload, and every config-touching
    # feature would go dark while it still reported healthy.
    # QC-ALLOW-NO-CHOWN: redirect through the existing inode — owner/group/mode preserved by construction.
    if cat "$CONFIG_BACKUP" > "$OC_CONFIG" 2>/dev/null; then
      _ok "config restored from $CONFIG_BACKUP (inode/owner/mode preserved)"
      proved="$proved config"
      STATE_CONFIG_CHANGED=0
      for p in $PLUGIN_QUARANTINED; do _plugin_record reverted-by-rollback "$p" "" "restored"; done
      PLUGIN_QUARANTINED=""
    else
      _err "CONFIG RESTORE FAILED — the backup is intact at $CONFIG_BACKUP"
      failed=1
    fi
  fi

  if [ "$STATE_BINARY_CHANGED" = "1" ] && [ -n "$OLD_VERSION" ]; then
    if [ "$(_measured_version)" = "$OLD_VERSION" ] && _package_complete; then
      _ok "binary is already openclaw@$OLD_VERSION and the package is complete (measured) - nothing to reinstall"
      proved="$proved binary=$OLD_VERSION"
      STATE_BINARY_CHANGED=0
    else
      _say "reinstalling the previous binary: openclaw@$OLD_VERSION"
      # #21: the gateway job is booted out for the WHOLE npm window (it is loaded here when the
      # failure came after the start, and KeepAlive would respawn it against a half-written tree).
      # The install's exit code is a claim; the MEASURED version and a complete package are the result.
      _npm_install_held "$OLD_VERSION"; rc=$?
      if [ "$rc" -eq 2 ]; then
        _err "BINARY RESTORE NOT ATTEMPTED — the gateway could not be held stopped, and npm into a package a respawning gateway is importing is how a box goes dark"
        failed=1
      elif [ "$(_measured_version)" = "$OLD_VERSION" ] && _package_complete; then
        _ok "binary restored to openclaw@$OLD_VERSION (measured, package complete)"
        proved="$proved binary=$OLD_VERSION"
        STATE_BINARY_CHANGED=0
      else
        _err "BINARY RESTORE FAILED — this box may be left on a build its config does not match"
        failed=1
      fi
    fi
  fi

  if [ "$STATE_QUIESCED" = "1" ]; then
    if [ "$GATEWAY_LOADED_AT_START" = "1" ]; then
      # An orphan gateway or a stale CLI holding the state database would keep the restored gateway
      # from starting (#33).
      _reap_orphan_gateways "before the rollback restart" || true
      _reap_state_holders "before the rollback restart" || true
      # Re-load what we booted out, then PROVE it (loaded + pid + /healthz 200).
      # Never claim a restart from an exit code. #21: never onto a package that is not complete.
      if ! _package_complete; then
        _err "GATEWAY NOT RE-LOADED — the package is incomplete (${SUP_ENTRY:-package.json} missing); bootstrapping onto it would only crash-loop. Repair the package first (steps below)"
        failed=1
      elif _restore_gateway; then
        proved="$proved gateway(loaded+pid+healthz200)"
        STATE_QUIESCED=0
      else
        _err "GATEWAY RESTORE NOT PROVEN — the box is DOWN or unhealthy"
        failed=1
      fi
    else
      _say "no loaded gateway ($SUPERVISOR) when this began — nothing was booted out, nothing to put back"
      STATE_QUIESCED=0
    fi
  fi

  _restore_selfheal || failed=1
  _lock_release

  if [ "$failed" = "1" ]; then
    echo "" >&2
    echo "  ################################################################" >&2
    echo "  ##  ROLLBACK FAILED — THIS BOX NEEDS A HUMAN NOW              ##" >&2
    echo "  ################################################################" >&2
    echo "  ##  Config backup : ${CONFIG_BACKUP:-<none written>}" >&2
    echo "  ##  Previous build: ${OLD_VERSION:-<unknown>}" >&2
    echo "  ##  Repair by hand:" >&2
    echo "  ##    cat '${CONFIG_BACKUP:-BACKUP}' > '$OC_CONFIG'" >&2
    echo "  ##    npm install -g ${SUP_PREFIX:+--prefix $SUP_PREFIX }openclaw@${OLD_VERSION:-<version>}" >&2
    echo "  ##    launchctl bootstrap gui/\$(id -u) \\" >&2
    echo "  ##      \$HOME/Library/LaunchAgents/$GATEWAY_LABEL.plist" >&2
    echo "  ##    launchctl kickstart gui/\$(id -u)/$GATEWAY_LABEL" >&2
    echo "  ##    curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:<port>/healthz   # must print 200 (https and curl -k when gateway.tls.enabled)" >&2
    echo "  ##  Then re-arm the self-heal agent:" >&2
    echo "  ##    bash platform/mac/service-selfheal/install-service-remediate.sh" >&2
    echo "  ################################################################" >&2
    return 70
  fi
  _ok "rollback complete and VERIFIED:${proved:- nothing needed undoing}"
  return 78
}

_refuse_banner() {
  local reason="$1" state="$2"
  echo "" >&2
  echo "  ################################################################" >&2
  echo "  ##  UPGRADE REFUSED — ATOMIC SCHEMA-MIGRATION GATE             ##" >&2
  echo "  ################################################################" >&2
  echo "  ##  Box    : $(hostname 2>/dev/null || uname -n 2>/dev/null || echo unknown)" >&2
  echo "  ##  Config : $OC_CONFIG" >&2
  echo "  ##" >&2
  echo "  ##  $reason" >&2
  echo "  ##  $state" >&2
  echo "  ##" >&2
  echo "  ##  A box left one build stale is recoverable. A dark box is not." >&2
  echo "  ##  Inspect with:  bash $0 --detect" >&2
  echo "  ################################################################" >&2
  echo "" >&2
}

# ─────────────────────────────────────────────────────────────────────────────
# DETECT
# ─────────────────────────────────────────────────────────────────────────────
do_detect() {
  local verdict json rc mv
  _resolve_root
  SUPERVISOR="$(_detect_supervisor)"
  if command -v python3 >/dev/null 2>&1 && [ -f "$SUP_HELPER" ] && ! _resolve_supervisor_install; then
    echo "install    : UNRESOLVABLE (the supervisor definition names no installed openclaw package)"
    SUP_PKG_ROOT=""
  fi
  mv="$(_measured_version)"

  echo "config     : $OC_CONFIG"
  echo "supervisor : $SUPERVISOR"
  if [ -n "$SUP_PKG_ROOT" ]; then
    echo "install    : $SUP_PKG_ROOT (the package the supervisor launches; PATH copy: $(_path_version | grep . || echo none))"
    echo "version    : ${mv:-UNMEASURABLE} (MEASURED from that package.json, never a recorded value)"
  else
    echo "version    : ${mv:-UNMEASURABLE} (MEASURED via \`openclaw --version\`, never a recorded value)"
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    echo "shape      : UNDETERMINED (python3 is not available, so the config was never parsed)"
    return 3
  fi
  if [ ! -f "$MIGRATOR" ]; then
    echo "shape      : UNDETERMINED (the transform engine is missing at $MIGRATOR)"
    return 3
  fi
  if [ ! -f "$OC_CONFIG" ]; then
    echo "shape      : NO_CONFIG (fresh box — nothing to migrate)"
    return 0
  fi

  json="$(python3 "$MIGRATOR" detect "$OC_CONFIG" 2>&1)"; rc=$?
  verdict="$(printf '%s' "$json" | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("UNDETERMINED"); raise SystemExit(0)
print("%s|%s|%s" % (d.get("verdict","UNDETERMINED"), d.get("agent_count",0), d.get("detail","")))' 2>/dev/null)"

  echo "shape      : ${verdict%%|*}"
  echo "agents     : $(printf '%s' "$verdict" | cut -d'|' -f2)"
  echo "detail     : $(printf '%s' "$verdict" | cut -d'|' -f3-)"
  return $rc
}

# ─────────────────────────────────────────────────────────────────────────────
# UPGRADE — the atomic procedure
# ─────────────────────────────────────────────────────────────────────────────
do_upgrade() {
  local rc detect_rc shape schema_file schema_keys wants_entries wants_list
  local staged new_version ts

  _resolve_root
  # agent-pull-fix: R9
  if _running_in_container; then
    _refuse_banner \
      "This script is running INSIDE A CONTAINER. Its OpenClaw binary lives in the image, which this repo does not build or pull, so the binary change and the config change cannot be made atomic. The host's docker daemon is not reachable from in here either." \
      "Nothing was changed. Run this on the HOST, not inside the container."
    return 79
  fi
  SUPERVISOR="$(_detect_supervisor)"
  # What the rollback must put back, recorded BEFORE anything is stopped.
  _gateway_loaded && GATEWAY_LOADED_AT_START=1

  # ── INSTALLATION LEASE + UNPINNED-CRON GUARD ──────────────────────────────
  # Order matters: BOTH probes look at the lease BEFORE we take it, so an
  # unpinned Saturday cron can see the roll that owns the box and stand down
  # instead of racing it (mac.MAC-2). A pinned upgrade (self-update passes
  # --target-version) skips the unpinned probe: the acquire below is enough.
  if [ -z "${TARGET_VERSION:-}" ] && _unpinned_foreign_writer; then
    _refuse_banner \
      "This upgrade is UNPINNED (no --target-version, so the target would be whatever npm says right now) and ANOTHER UPDATER ALREADY OWNS THIS BOX: $_UPW_WHY. Two writers must never migrate the same installation." \
      "Nothing was changed. Stand down and let the running update finish."
    return 78
  fi
  _lease_acquire
  case "$?" in
    0) trap '_lease_release' EXIT ;;
    3) _refuse_banner \
         "The SHARED INSTALLATION LEASE is held by another live updater (pid $(_lease_rpid)). One box has exactly one update owner; a second writer here would migrate this config underneath the first." \
         "Nothing was changed. Wait for the holder to finish, then re-run."
       return 78 ;;
    *) _refuse_banner "The shared installation lease at $OC_LEASE_PATH could not be taken or written." \
         "Nothing was changed. Check permissions on $OC_LEASE_PATH."
       return 78 ;;
  esac

  # ── PREFLIGHT. Everything that could refuse is checked BEFORE anything stops,
  # ── so a refusal costs the box nothing at all.
  if ! command -v python3 >/dev/null 2>&1; then
    _refuse_banner "python3 is NOT AVAILABLE, so the config can never be parsed or migrated." \
      "Nothing was changed."
    return 78
  fi
  if [ ! -f "$MIGRATOR" ]; then
    _refuse_banner "The transform engine is MISSING at $MIGRATOR." \
      "Nothing was changed. Re-run update-skills.sh to deliver scripts/ to this box."
    return 78
  fi
  if [ ! -f "$SUP_HELPER" ]; then
    _refuse_banner "The supervisor-install resolver is MISSING at $SUP_HELPER." \
      "Nothing was changed. Re-run update-skills.sh to deliver scripts/ to this box."
    return 78
  fi
  if ! _resolve_supervisor_install; then
    _refuse_banner "The gateway supervisor definition (LaunchAgent plist / systemd unit) does not name an installed openclaw package, so the install it launches cannot be measured. PATH is NOT a substitute: it can be a different copy at a different version." \
      "Nothing was changed."
    return 78
  fi
  if ! command -v openclaw >/dev/null 2>&1; then
    _refuse_banner "The \`openclaw\` CLI is NOT ON PATH, so neither the version nor the schema can be measured." \
      "Nothing was changed."
    return 78
  fi
  if [ "$SUPERVISOR" = "docker" ]; then
    # CAN016: the blanket refusal's premise (binary lives in the image) is FALSE
    # on the fleet's real layout — the openclaw package sits on a bind-mounted
    # persistent prefix (<host>/data/.npm-global), so an on-disk install +
    # docker stop/start + pid + /healthz proof is atomic the same way launchd is.
    if echo "$SUP_UNIT" | grep -q '^container:' && [ -f "$SUP_PKG_ROOT/package.json" ]; then
      _say "docker supervisor with a bind-mounted persistent install (CAN016): upgrading ON DISK at $SUP_PKG_ROOT, then restarting the container and pid-proving it"
    else
      _refuse_banner \
        "This gateway is supervised by DOCKER and its OpenClaw binary lives in the container IMAGE (no bind-mounted install was resolved), which this script cannot build or pull — the binary change and the config change cannot be made atomic." \
        "Nothing was changed. Pull/build the new image, then restart the container and confirm the new pid and /healthz."
      echo "  MANUAL SEQUENCE for an image-baked docker box (each step verified before the next):" >&2
      echo "    1. docker stop openclaw                # unless-stopped does not revive an explicit stop" >&2
      echo "    2. pull/build the new image" >&2
      echo "    3. bash $0 --detect      # confirm the shape and the config path" >&2
      echo "    4. migrate the config with: python3 $MIGRATOR apply <cfg> <tmp> && \\" >&2
      echo "       python3 $MIGRATOR verify <cfg> <tmp> && cat <tmp> > <cfg>" >&2
      echo "    5. docker start openclaw ; then confirm the pid is STABLE for 25s" >&2
      return 78
    fi
  fi
  # Only launchd, and docker with a bind-mounted install, can be stopped,
  # restarted and pid-proven here. A systemd unit (or any gateway no supervisor
  # above owns) would be "upgraded" on disk while the old process keeps
  # answering /healthz.
  if [ "$SUPERVISOR" != "launchd" ] && { [ "$SUPERVISOR" != "docker" ] || ! echo "$SUP_UNIT" | grep -q '^container:' || [ ! -f "$SUP_PKG_ROOT/package.json" ]; }; then
    _refuse_banner \
      "The gateway supervisor is '${SUP_SOURCE:+$SUP_SOURCE unit, detected as }$SUPERVISOR', and this script can only stop, restart and pid-prove a launchd gateway or a docker container with a bind-mounted install. Installing here would leave the running gateway on the OLD build and still report success." \
      "Nothing was changed. Upgrade the install (${SUP_PKG_ROOT:-the unit ExecStart path}) and restart the gateway by hand (systemctl restart), then confirm the new pid and /healthz."
    return 78
  fi
  if ! command -v "$NPM_BIN" >/dev/null 2>&1; then
    _refuse_banner "npm ($NPM_BIN) is NOT ON PATH, so the binary cannot be installed or rolled back." \
      "Nothing was changed. Refusing to start a procedure whose rollback is already impossible."
    return 78
  fi

  OLD_VERSION="$(_measured_version)"
  if [ -z "$OLD_VERSION" ]; then
    _refuse_banner "\`openclaw --version\` did not report a measurable version." \
      "Nothing was changed. Without the current version there is no rollback target, so this procedure must not start."
    return 78
  fi

  if [ -z "$TARGET_VERSION" ]; then
    TARGET_VERSION="$("$NPM_BIN" view openclaw version 2>/dev/null | tr -d '[:space:]')"
  fi
  if [ -z "$TARGET_VERSION" ]; then
    _refuse_banner "Could not determine a target version (\`npm view openclaw version\` returned nothing)." \
      "Nothing was changed."
    return 78
  fi

  if [ -f "$OC_CONFIG" ]; then
    python3 "$MIGRATOR" detect "$OC_CONFIG" >/dev/null 2>&1; detect_rc=$?
    case "$detect_rc" in
      0)  shape="CLEAN" ;;
      10) shape="LEGACY_LIST" ;;
      *)  shape="UNDETERMINED" ;;
    esac
  else
    shape="NO_CONFIG"
  fi

  if [ "$shape" = "UNDETERMINED" ]; then
    _refuse_banner "The config at $OC_CONFIG could NOT be inspected (see the detector's reason above)." \
      "Nothing was changed. An unreadable config is not a clean config."
    python3 "$MIGRATOR" detect "$OC_CONFIG" 2>&1 | sed 's/^/    | /' >&2
    return 78
  fi

  _say "box       : $(hostname 2>/dev/null || uname -n 2>/dev/null || echo unknown)"
  _say "supervisor: $SUPERVISOR"
  _say "version   : $OLD_VERSION (measured)  ->  $TARGET_VERSION (target)"
  _say "config    : $OC_CONFIG  [shape: $shape]"

  # "Already on target" needs the supervisor's package at the target AND the live gateway process
  # launched from it AND /healthz 200 (_prove_gateway_on_target). A package at the target under a
  # gateway still running the old build (or no gateway at all) falls through to the full procedure,
  # which restarts the gateway and re-proves it.
  # The proof includes pid start >= package.json ctime, so an in-place reinstall with no restart
  # is not "already on target" either.
  if [ "$OLD_VERSION" = "$TARGET_VERSION" ] && [ "$shape" != "LEGACY_LIST" ]; then
    if ! _prove_gateway_on_target; then
      _warn "the package is at $TARGET_VERSION but the gateway is NOT proven running it (above) — running the full procedure to restart and re-prove it"
    # "Nothing to do" is only true if the installed build actually accepts the config.
    elif [ "$shape" = "NO_CONFIG" ] || _config_valid_for_installed_binary; then
      _ok "already on $TARGET_VERSION, gateway running it, non-legacy config the installed build accepts — nothing to do."
      return 0
    else
      _warn "already on $TARGET_VERSION but the installed build REJECTS the config (above) — running the full procedure to migrate it"
    fi
  fi

  if [ "$DRY_RUN" = "1" ]; then
    echo ""
    _say "DRY RUN — the plan, in order, touching nothing:"
    echo "    1. write the maintenance lock  ($LOCK_FILE)"
    echo "    2. bootout $SELFHEAL_LABEL, then bootout $GATEWAY_LABEL (NOT kickstart)"
    echo "    2b. (launchd) stop any ORPHAN gateway (not the job's pid) that holds the state database, by identity, and log it"
    echo "    3. prove quiescence: no pid, and config sha stable for ${QUIESCE_PROOF_SECONDS}s"
    echo "    4. back up the config"
    echo "    5. $NPM_BIN install -g ${SUP_PREFIX:+--prefix $SUP_PREFIX }openclaw@$TARGET_VERSION   (the supervisor's install: ${SUP_PKG_ROOT:-none found, PATH}) with the gateway job proven booted out for the whole window; the package must measure complete before anything is started"
    echo "    6. ask the NEW binary: openclaw config schema  -> which keys does \`agents\` accept?"
    echo "    7. if it accepts \`entries\` and not \`list\`: migrate + verify losslessness; else leave the config alone"
    echo "    7a. (launchd) reap STALE bare openclaw CLI processes holding $OC_ROOT_DIR/state/openclaw.sqlite (never the launchd job's gateway, a node service, the app, or anything started in this run; an orphan gateway is stopped at 2b), then run the NEW binary: doctor --fix --non-interactive (stdin /dev/null, bounded ${DOCTOR_TIMEOUT}s) so the agent/session database migration finishes BEFORE the gateway starts; a legacy-audit-raw checkpoint refusal drops only that scope's rows and re-runs doctor once; model/provider names must be identical afterwards, else roll back"
    echo "    7a1. (launchd) doctor spinning on a plugin whose module cannot load (the same ERR_MODULE_NOT_FOUND ${DOCTOR_LOOP_LINES} times, or the bound) is killed; the plugin is named from its output, ONLY plugins.entries.<id>.enabled is set to false (recorded; never the allow list, never install/enable/update), and doctor runs again"
    echo "    7b. map retired values (skills.workshop.autonomous.mode propose -> off) then \`openclaw config validate\` with the NEW binary (job is out, so no gateway to contend with; against a SERVING gateway the check runs on a private copy in a private state dir under known-good/known-bad controls); rejected = roll back"
    echo "    8. stop any orphan gateway again, reap stale state-database holders again; bootstrap $GATEWAY_LABEL; require a STABLE pid for ${STABILITY_SECONDS}s, /healthz 200, and the launched package at $TARGET_VERSION"
    echo "    9. release the lock, re-arm $SELFHEAL_LABEL"
    echo "    Any failure from step 3 onward: restore config AND binary, start the gateway."
    return 0
  fi

  # ── 1. LOCK ────────────────────────────────────────────────────────────────
  _lock_acquire || { _refuse_banner "Could not acquire the maintenance lock." "Nothing was changed."; return 78; }

  # ── 2-3. QUIESCE AND PROVE IT ──────────────────────────────────────────────
  if ! _quiesce; then
    _rollback "the gateway could not be stopped"; return $?
  fi
  # #33: the job is out, so its pid is empty and the proof below would read "nothing running"
  # while an orphan from an earlier run still owns the state directory and rewrites the config.
  if ! _reap_orphan_gateways "after the quiesce"; then
    _rollback "an orphan gateway process still owns the state directory and could not be stopped"
    return $?
  fi
  if ! _prove_quiesced; then
    _rollback "quiescence could not be PROVEN — a live writer would silently revert the migration within about a minute"
    return $?
  fi

  # ── 4. BACK UP ─────────────────────────────────────────────────────────────
  if [ -f "$OC_CONFIG" ]; then
    ts="$(date +%Y%m%d-%H%M%S)"
    CONFIG_BACKUP="${OC_CONFIG}.bak-pre-atomic-upgrade-${ts}"
    if ! cp -p "$OC_CONFIG" "$CONFIG_BACKUP" 2>/dev/null; then
      CONFIG_BACKUP=""
      _rollback "the config could not be backed up — refusing to change a config we cannot roll back"
      return $?
    fi
    _ok "config backed up: $CONFIG_BACKUP"
  fi

  # ── 5. INSTALL THE NEW BINARY (while nothing is running) ───────────────────
  if [ "$OLD_VERSION" != "$TARGET_VERSION" ]; then
    _say "installing openclaw@$TARGET_VERSION ..."
    # Rollback state BEFORE the install it undoes: an npm that dies half-way leaves a half-written
    # tree, and the rollback must repair that, not trust an exit code (#21).
    STATE_BINARY_CHANGED=1
    _npm_install_held "$TARGET_VERSION"; rc=$?
    if [ "$rc" -eq 2 ]; then
      _rollback "the gateway could not be held stopped for the npm window - npm was NOT run, so no respawning gateway can import a half-written package"
      return $?
    fi
    if [ "$rc" -ne 0 ]; then
      _rollback "\`$NPM_BIN install -g ${SUP_PREFIX:+--prefix $SUP_PREFIX }openclaw@$TARGET_VERSION\` FAILED"
      return $?
    fi
    new_version="$(_measured_version)"
    if [ "$new_version" != "$TARGET_VERSION" ]; then
      _rollback "the install reported success but the binary MEASURES $new_version, not $TARGET_VERSION — an exit code is a claim, not a result"
      return $?
    fi
    if ! _package_complete; then
      _rollback "the install measures $new_version but the package is INCOMPLETE (${SUP_ENTRY:-package.json} is missing) - the gateway must not be started on it"
      return $?
    fi
    _ok "binary is now openclaw@$new_version (measured)"
  else
    _ok "binary already at $TARGET_VERSION — no install needed"
  fi

  # ── 6. ASK THE NEW BINARY WHICH SCHEMA IT SPEAKS ───────────────────────────
  # This is the authority. The transform is only correct against a build that
  # reads `entries`; nothing else in this procedure may assume it.
  schema_file="$(mktemp "${TMPDIR:-/tmp}/oc-schema.XXXXXX")" || {
    _rollback "could not create a temp file for the schema probe"; return $?; }
  if ! openclaw config schema > "$schema_file" 2>/dev/null; then
    rm -f "$schema_file"
    _rollback "\`openclaw config schema\` FAILED on the installed binary — the accepted key set is UNKNOWN, and a migration must never be performed on an unanswered schema probe"
    return $?
  fi
  schema_keys="$(python3 "$MIGRATOR" schema-keys "$schema_file" 2>/dev/null)"; rc=$?
  rm -f "$schema_file"
  if [ "$rc" -ne 0 ] || [ -z "$schema_keys" ]; then
    _rollback "the schema probe could not be parsed — the accepted key set under \`agents\` is UNDETERMINED, so no migration decision can be made"
    return $?
  fi
  wants_entries=0; wants_list=0
  printf '%s\n' "$schema_keys" | grep -qx 'entries' && wants_entries=1
  printf '%s\n' "$schema_keys" | grep -qx 'list'    && wants_list=1
  _ok "installed binary accepts under \`agents\`: $(printf '%s' "$schema_keys" | tr '\n' ' ')"

  # ── 7. REWRITE THE CONFIG TO MATCH — only if the binary asked for it ────────
  if [ "$shape" = "LEGACY_LIST" ]; then
    if [ "$wants_entries" = "0" ]; then
      if [ "$wants_list" = "1" ]; then
        _ok "this build still accepts \`agents.list\` — the config is already valid for it. NOT migrating."
      else
        _rollback "the installed binary accepts NEITHER \`list\` NOR \`entries\` under \`agents\` — this config cannot be made valid for it by this transform"
        return $?
      fi
    else
      staged="${OC_CONFIG}.atomic-staged.$$"
      if ! python3 "$MIGRATOR" apply "$OC_CONFIG" "$staged" 2>&1 | sed 's/^/    | /'; then
        rm -f "$staged"
        _rollback "the transform REFUSED this config (see the reason above) — it will not guess"
        return $?
      fi
      if [ ! -s "$staged" ]; then
        rm -f "$staged"
        _rollback "the transform produced no output"
        return $?
      fi
      # VERIFY BEFORE COMMITTING. Count identical, key set == id set exactly,
      # every entry round-trips through `{...entry, id}`, every other key
      # untouched, resolved workspace unmoved.
      if ! python3 "$MIGRATOR" verify "$OC_CONFIG" "$staged" 2>&1 | sed 's/^/    | /'; then
        rm -f "$staged"
        _rollback "the migrated config FAILED losslessness verification (see the failures above) — it was never installed"
        return $?
      fi
      # `cat >` writes THROUGH the existing inode, so owner, group and mode
      # survive by construction. A cp/mv here would leave a root-run cron's
      # config root-owned and the gateway would get EACCES on reload.
      # QC-ALLOW-NO-CHOWN: redirect through the existing inode — owner/group/mode preserved by construction.
      if ! cat "$staged" > "$OC_CONFIG" 2>/dev/null; then
        rm -f "$staged"
        _rollback "could not write the migrated config into place"
        return $?
      fi
      STATE_CONFIG_CHANGED=1
      rm -f "$staged"
      _ok "config migrated to \`agents.entries\` and PROVEN lossless"
      # Re-read from disk. The verify above ran against the staged file; this
      # proves what actually landed.
      python3 "$MIGRATOR" detect "$OC_CONFIG" >/dev/null 2>&1; rc=$?
      if [ "$rc" -ne 0 ]; then
        _rollback "the config on disk still does not read as migrated after the write (detector rc=$rc)"
        return $?
      fi
      _ok "re-read from disk: the legacy key is gone"
    fi
  else
    if [ "$wants_list" = "0" ] && [ "$wants_entries" = "1" ] && [ "$shape" = "CLEAN" ]; then
      _ok "config carries no legacy key and the new build wants \`entries\` — nothing to migrate"
    else
      _ok "no migration needed for shape $shape"
    fi
  fi

  # ── 7a. MIGRATE THE AGENT/SESSION DATABASE WITH THE NEW BINARY'S DOCTOR ────
  # The gateway is booted out (proven above), the new binary is on disk, and the config is
  # in the shape that binary reads. Doctor only repairs state here; it leaves the (already
  # stopped) service as it found it. Launchd boxes only: see the STATE-DATABASE block.
  if [ "$SUPERVISOR" = "launchd" ]; then
    if ! _migrate_state_with_doctor; then
      _rollback "$DOCTOR_WHY"
      return $?
    fi
  else
    _say "doctor --fix: not run for the $SUPERVISOR supervisor (its state lives where this script cannot see it) - unchanged"
  fi

  # ── 7b. THE NEW BINARY MUST ACCEPT THE CONFIG BEFORE ANYTHING IS CALLED DONE ─
  # Apply the known value map for keys the new build retired (propose -> off, per
  # the vendor's doctor migration), then ask the build itself. An unmapped or
  # still-rejected config rolls back loudly: a config the new build rejects must
  # never be reported as a successful upgrade, and must never reach the gateway.
  if [ -f "$OC_CONFIG" ]; then
    schema_file="$(mktemp "${TMPDIR:-/tmp}/oc-schema.XXXXXX")" || {
      _rollback "could not create a temp file for the workshop-mode probe"; return $?; }
    if openclaw config schema > "$schema_file" 2>/dev/null; then
      staged="${OC_CONFIG}.atomic-staged.$$"
      wm="$(python3 "$MIGRATOR" workshop-migrate "$schema_file" "$OC_CONFIG" "$staged" 2>&1)"; rc=$?
      rm -f "$schema_file"
      if [ "$rc" -ne 0 ]; then
        rm -f "$staged"
        _rollback "the config holds a value the new build rejects and there is no known migration for it: $wm"
        return $?
      fi
      case "$wm" in
        migrated:*)
          STATE_CONFIG_CHANGED=1
          # QC-ALLOW-NO-CHOWN: redirect through the existing inode — owner/group/mode preserved by construction.
          if ! cat "$staged" > "$OC_CONFIG" 2>/dev/null; then
            rm -f "$staged"; _rollback "could not write the workshop-mode migration into place"; return $?
          fi
          _ok "$wm" ;;
      esac
      rm -f "$staged"
    else
      rm -f "$schema_file"
      _rollback "\`openclaw config schema\` FAILED on the installed binary - the workshop-mode value cannot be checked"
      return $?
    fi
    if ! _config_valid_for_installed_binary; then
      _rollback "the NEW build ($(_measured_version)) REJECTS the config (issues above) - refusing to report success on a config the installed binary cannot load"
      return $?
    fi
    _ok "the installed binary accepts the config (openclaw config validate)"
  fi

  # ── 8. START, AND PROVE IT STAYED UP ───────────────────────────────────────
  # #33: an orphan gateway that owns the state directory makes the LaunchAgent exit 78, which reads
  # as a bad binary. Stop it by identity first; a stale CLI that grabbed the database since doctor
  # would stop the start too.
  if ! _reap_orphan_gateways "before the gateway start"; then
    _rollback "an orphan gateway process still owns the state directory - the start would exit 78 and look like a bad binary"
    return $?
  fi
  _reap_state_holders "before the gateway start" || _warn "starting the gateway anyway; the start proof below decides"
  if ! _start_gateway; then
    _rollback "the gateway could not be started after the upgrade"
    return $?
  fi
  if ! _prove_started; then
    _rollback "the gateway did not stay up after the upgrade"
    return $?
  fi
  if ! _prove_gateway_on_target; then
    _rollback "the gateway is not running the target build - exit 0 would be a false success"
    return $?
  fi

  # ── 9. RELEASE ─────────────────────────────────────────────────────────────
  STATE_QUIESCED=0
  _restore_selfheal
  _lock_release

  echo ""
  _ok "ATOMIC UPGRADE COMPLETE"
  _say "  binary : $OLD_VERSION -> $(_measured_version) (measured)"
  _say "  config : ${CONFIG_BACKUP:+backup retained at $CONFIG_BACKUP}"
  [ -z "$PLUGIN_QUARANTINED" ] || _say "  plugins: entry DISABLED because its module fails to load:$PLUGIN_QUARANTINED  (restore steps in $PLUGIN_RECORD)"
  return 0
}

# ─────────────────────────────────────────────────────────────────────────────
main() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --detect)  MODE="detect"; shift ;;
      --upgrade) MODE="upgrade"; shift ;;
      --dry-run) DRY_RUN=1; shift ;;
      --target-version)
        [ $# -ge 2 ] || { _err "--target-version needs a value"; exit 2; }
        TARGET_VERSION="$2"; shift 2 ;;
      -h|--help) sed -n '1,110p' "${BASH_SOURCE[0]}"; exit 0 ;;
      *) _err "unknown argument: $1"; exit 2 ;;
    esac
  done
  case "$MODE" in
    detect)  do_detect;  exit $? ;;
    upgrade) do_upgrade; exit $? ;;
    *) _err "one of --detect or --upgrade is required"; exit 2 ;;
  esac
}

main "$@"
