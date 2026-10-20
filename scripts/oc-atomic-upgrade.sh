#!/usr/bin/env bash
# oc-atomic-upgrade.sh — v1.0.0
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
#   Non-numeric values of the three timeouts above fall back to their defaults.
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

VERSION="1.0.0"
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
  node_dir="$(printf '%s\n' "$out" | sed -n 's/^node=//p' | head -1)"
  [ -n "$node_dir" ] && node_dir="$(dirname "$node_dir")"
  [ -n "$SUP_PKG_ROOT" ] && [ -n "$SUP_PREFIX" ] || return 1
  [ -n "$node_dir" ] && [ -d "$node_dir" ] && PATH="$node_dir:$PATH"
  [ -d "$SUP_PREFIX/bin" ] && PATH="$SUP_PREFIX/bin:$PATH"
  export PATH
  # THAT node's npm, unless the operator pinned one.
  [ -z "${OC_ATOMIC_NPM:-}" ] && [ -n "$node_dir" ] && [ -x "$node_dir/npm" ] && NPM_BIN="$node_dir/npm"
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
      docker inspect -f '{{.State.Pid}}' openclaw 2>/dev/null | grep -E '^[1-9][0-9]*$'
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
    docker)  [ "$(docker inspect -f '{{.State.Running}}' openclaw 2>/dev/null)" = "true" ] ;;
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

# rc 0 ONLY when GET /healthz answers 200. No curl = cannot prove = rc 1.
_healthz_ok() {
  command -v curl >/dev/null 2>&1 || return 1
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
        "http://127.0.0.1:$(_gateway_port)/healthz" 2>/dev/null)" = "200" ]
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
_config_valid_for_installed_binary() {
  local out
  out="$(openclaw config validate --json 2>/dev/null)" && return 0
  printf '%s' "$out" | python3 -c 'import json,sys
try:
    for i in json.load(sys.stdin).get("issues") or []:
        print("%s: %s" % (i.get("path"), i.get("message")))
except Exception:
    print("(no parseable issue list - the build rejected the config)")' 2>/dev/null | sed 's/^/    | /' >&2
  return 1
}

# ── The maintenance lock. remediate.sh / gateway-health-watchdog.sh honour it.
# ── It exists because the 5-minute self-heal ALSO runs from cron on some boxes,
# ── where there is no LaunchAgent to boot out — a bootout alone would leave a
# ── cron-driven remediator free to bootstrap the gateway back mid-procedure and
# ── silently revert the migration (fact 3).
_lock_acquire() {
  mkdir -p "$OC_ROOT_DIR" 2>/dev/null
  printf 'pid=%s\nstarted=%s\nreason=oc-atomic-upgrade v%s\n' \
    "$$" "$(date '+%Y-%m-%dT%H:%M:%S')" "$VERSION" > "$LOCK_FILE" 2>/dev/null
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
      # bootout, NOT kickstart -k. kickstart restarts the process and leaves the
      # job loaded; KeepAlive then respawns it every ~11s. Only bootout is a stop.
      # bootout is ASYNCHRONOUS: it returns before the job has left launchd, so
      # a one-shot check straight after it races the teardown. Poll, bounded.
      launchctl bootout "gui/$UIDN/$GATEWAY_LABEL" >/dev/null 2>&1
      if ! _poll "$BOOTOUT_TIMEOUT" _gateway_unloaded; then
        _err "gateway job $GATEWAY_LABEL is STILL LOADED ${BOOTOUT_TIMEOUT}s after bootout — refusing to continue"
        return 1
      fi
      _ok "gateway job booted out of gui/$UIDN (not merely restarted)"
      ;;
    docker)
      # Unreachable in --upgrade (refused in preflight); kept correct so
      # --detect and any future explicitly-driven use are not lying.
      docker stop openclaw >/dev/null 2>&1 || return 1
      _ok "container openclaw stopped (restart:unless-stopped does not revive an explicit stop)"
      ;;
    none)
      _ok "no supervisor found — nothing to quiesce"
      ;;
  esac
  return 0
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
    docker) docker start openclaw >/dev/null 2>&1 || return 1 ;;
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
      if ! _gateway_loaded; then docker start openclaw >/dev/null 2>&1; return 1; fi
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
# ── the epoch a file's inode last changed (BSD stat -f %c, GNU stat -c %Z). "" on any failure.
_proc_start_epoch() {
  local e d=0 a b c secs
  e="$(ps -o etime= -p "$1" 2>/dev/null | tr -d '[:space:]')"
  case "$e" in ''|*[!0-9:-]*) return 1 ;; esac
  case "$e" in *-*) d="${e%%-*}"; e="${e#*-}" ;; esac
  IFS=: read -r a b c <<<"$e"
  if [ -n "$c" ]; then secs=$((10#$a*3600 + 10#$b*60 + 10#$c)); else secs=$((10#$a*60 + 10#$b)); fi
  printf '%s' "$(( $(date +%s) - 10#$d*86400 - secs ))"
}
_file_ctime() { stat -f %c "$1" 2>/dev/null || stat -c %Z "$1" 2>/dev/null; }

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
  if [ "$SUPERVISOR" = "launchd" ] && [ -n "$SUP_PKG_ROOT" ]; then
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
# ROLLBACK — undoes, in reverse, exactly what was recorded as done.
# ─────────────────────────────────────────────────────────────────────────────
_rollback() {
  local why="$1" failed=0 proved=""
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
    else
      _err "CONFIG RESTORE FAILED — the backup is intact at $CONFIG_BACKUP"
      failed=1
    fi
  fi

  if [ "$STATE_BINARY_CHANGED" = "1" ] && [ -n "$OLD_VERSION" ]; then
    _say "reinstalling the previous binary: openclaw@$OLD_VERSION"
    # The install's exit code is a claim; the MEASURED version is the result.
    _npm_install "$OLD_VERSION" >/dev/null 2>&1
    if [ "$(_measured_version)" = "$OLD_VERSION" ]; then
      _ok "binary restored to openclaw@$OLD_VERSION (measured)"
      proved="$proved binary=$OLD_VERSION"
      STATE_BINARY_CHANGED=0
    else
      _err "BINARY RESTORE FAILED — this box may be left on a build its config does not match"
      failed=1
    fi
  fi

  if [ "$STATE_QUIESCED" = "1" ]; then
    if [ "$GATEWAY_LOADED_AT_START" = "1" ]; then
      # Re-load what we booted out, then PROVE it (loaded + pid + /healthz 200).
      # Never claim a restart from an exit code.
      if _restore_gateway; then
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
    echo "  ##    curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:<port>/healthz   # must print 200" >&2
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
    _refuse_banner \
      "This gateway is supervised by DOCKER. The binary lives in the container IMAGE, which this repo does not build or pull, so this script cannot make the binary change and the config change atomic." \
      "Nothing was changed. Migrating the bind-mounted config while the image stays old would enumerate ZERO agents — a silent total outage."
    echo "  MANUAL SEQUENCE for a docker-hosted box (each step verified before the next):" >&2
    echo "    1. docker stop openclaw                # unless-stopped does not revive an explicit stop" >&2
    echo "    2. pull/build the new image" >&2
    echo "    3. bash $0 --detect      # confirm the shape and the config path" >&2
    echo "    4. migrate the config with: python3 $MIGRATOR apply <cfg> <tmp> && \\" >&2
    echo "       python3 $MIGRATOR verify <cfg> <tmp> && cat <tmp> > <cfg>" >&2
    echo "    5. docker start openclaw ; then confirm the pid is STABLE for 25s" >&2
    return 78
  fi
  # Only launchd can be stopped, restarted and pid-proven here. A systemd unit (or any gateway no
  # supervisor above owns) would be "upgraded" on disk while the old process keeps answering /healthz.
  if [ "$SUPERVISOR" != "launchd" ]; then
    _refuse_banner \
      "The gateway supervisor is '${SUP_SOURCE:+$SUP_SOURCE unit, detected as }$SUPERVISOR', and this script can only stop, restart and pid-prove a launchd gateway. Installing here would leave the running gateway on the OLD build and still report success." \
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
    echo "    3. prove quiescence: no pid, and config sha stable for ${QUIESCE_PROOF_SECONDS}s"
    echo "    4. back up the config"
    echo "    5. $NPM_BIN install -g ${SUP_PREFIX:+--prefix $SUP_PREFIX }openclaw@$TARGET_VERSION   (the supervisor's install: ${SUP_PKG_ROOT:-none found, PATH})"
    echo "    6. ask the NEW binary: openclaw config schema  -> which keys does \`agents\` accept?"
    echo "    7. if it accepts \`entries\` and not \`list\`: migrate + verify losslessness; else leave the config alone"
    echo "    7b. map retired values (skills.workshop.autonomous.mode propose -> off) then \`openclaw config validate\` with the NEW binary; rejected = roll back"
    echo "    8. bootstrap $GATEWAY_LABEL; require a STABLE pid for ${STABILITY_SECONDS}s, /healthz 200, and the launched package at $TARGET_VERSION"
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
    if ! _npm_install "$TARGET_VERSION" >/dev/null 2>&1; then
      _rollback "\`$NPM_BIN install -g ${SUP_PREFIX:+--prefix $SUP_PREFIX }openclaw@$TARGET_VERSION\` FAILED"
      return $?
    fi
    STATE_BINARY_CHANGED=1
    new_version="$(_measured_version)"
    if [ "$new_version" != "$TARGET_VERSION" ]; then
      _rollback "the install reported success but the binary MEASURES $new_version, not $TARGET_VERSION — an exit code is a claim, not a result"
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
