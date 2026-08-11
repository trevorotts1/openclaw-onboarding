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
#       3 = undetermined, 2 = usage.
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
#
# ⚠️ INTERPRETER: written for stock /bin/bash 3.2.57, which is what the fleet's
# Macs run. No associative arrays, no `mapfile`, no `${x^^}`, and never a
# heredoc nested inside `$( )` — that last one aborts at PARSE time on 3.2 and
# has already shipped a dead gate to this fleet once.

set -uo pipefail

VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATOR="$SCRIPT_DIR/oc-schema-migrate.py"

MODE=""
TARGET_VERSION=""
DRY_RUN=0

QUIESCE_PROOF_SECONDS="${OC_ATOMIC_QUIESCE_PROOF_SECONDS:-75}"
STABILITY_SECONDS="${OC_ATOMIC_STABILITY_SECONDS:-25}"
NPM_BIN="${OC_ATOMIC_NPM:-npm}"

GATEWAY_LABEL="ai.openclaw.gateway"
SELFHEAL_LABEL="com.openclaw.service-remediate"

# ─── Rollback state. Every one of these is set BEFORE the thing it undoes. ───
STATE_QUIESCED=0
STATE_BINARY_CHANGED=0
STATE_CONFIG_CHANGED=0
STATE_SELFHEAL_BOOTED_OUT=0
OLD_VERSION=""
CONFIG_BACKUP=""
OC_CONFIG=""
OC_ROOT_DIR=""
LOCK_FILE=""
SUPERVISOR=""
UIDN=""

_say()  { printf '[oc-atomic-upgrade] %s\n' "$*"; }
_ok()   { printf '[oc-atomic-upgrade] OK    %s\n' "$*"; }
_warn() { printf '[oc-atomic-upgrade] WARN  %s\n' "$*" >&2; }
_err()  { printf '[oc-atomic-upgrade] ERROR %s\n' "$*" >&2; }

# ── Resolve the box's OpenClaw root the same way every other script here does ─
_resolve_root() {
  OC_ROOT_DIR="$HOME/.openclaw"
  [ -d "/data/.openclaw" ] && OC_ROOT_DIR="/data/.openclaw"
  OC_CONFIG="$OC_ROOT_DIR/openclaw.json"
  LOCK_FILE="$OC_ROOT_DIR/.openclaw-maintenance-lock"
}

# ── MEASURED version. Never a recorded one: the fleet record for the box that
# ── went dark was two minor versions stale, and every conclusion drawn from it
# ── was wrong.
_measured_version() {
  command -v openclaw >/dev/null 2>&1 || { printf ''; return 0; }
  openclaw --version 2>/dev/null | head -1 \
    | grep -oE '[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?' | head -1
}

# ── Supervisor detection. Reports what would RESPAWN the gateway, because that
# ── is the thing a quiesce has to defeat — not merely what is running now.
_detect_supervisor() {
  UIDN="$(id -u 2>/dev/null || echo 0)"
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
  case "$SUPERVISOR" in
    launchd)
      # The self-heal agent first: booting the gateway out while its watchdog is
      # still armed just races it back up within 5 minutes.
      if launchctl print "gui/$UIDN/$SELFHEAL_LABEL" >/dev/null 2>&1; then
        launchctl bootout "gui/$UIDN/$SELFHEAL_LABEL" >/dev/null 2>&1
        STATE_SELFHEAL_BOOTED_OUT=1
        _ok "self-heal agent $SELFHEAL_LABEL booted out"
      fi
      # bootout, NOT kickstart -k. kickstart restarts the process and leaves the
      # job loaded; KeepAlive then respawns it every ~11s. Only bootout is a stop.
      launchctl bootout "gui/$UIDN/$GATEWAY_LABEL" >/dev/null 2>&1
      sleep 2
      if launchctl print "gui/$UIDN/$GATEWAY_LABEL" >/dev/null 2>&1; then
        _err "gateway job $GATEWAY_LABEL is STILL LOADED after bootout — refusing to continue"
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
  STATE_QUIESCED=1
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
      launchctl bootstrap "gui/$UIDN" "$plist" >/dev/null 2>&1
      ;;
    docker) docker start openclaw >/dev/null 2>&1 ;;
    none)   return 0 ;;
  esac
  return 0
}

_restore_selfheal() {
  [ "$STATE_SELFHEAL_BOOTED_OUT" = "1" ] || return 0
  local plist="$HOME/Library/LaunchAgents/$SELFHEAL_LABEL.plist"
  if [ -f "$plist" ]; then
    launchctl bootstrap "gui/$UIDN" "$plist" >/dev/null 2>&1
    STATE_SELFHEAL_BOOTED_OUT=0
    _ok "self-heal agent $SELFHEAL_LABEL bootstrapped back"
  else
    _warn "self-heal plist $plist is gone — could not re-arm $SELFHEAL_LABEL. Re-run platform/mac/service-selfheal/install-service-remediate.sh"
  fi
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
    return 0
  fi
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
  _ok "gateway up and stable for ${STABILITY_SECONDS}s on pid $pid_a"
  return 0
}

# ─────────────────────────────────────────────────────────────────────────────
# ROLLBACK — undoes, in reverse, exactly what was recorded as done.
# ─────────────────────────────────────────────────────────────────────────────
_rollback() {
  local why="$1" failed=0
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
      STATE_CONFIG_CHANGED=0
    else
      _err "CONFIG RESTORE FAILED — the backup is intact at $CONFIG_BACKUP"
      failed=1
    fi
  fi

  if [ "$STATE_BINARY_CHANGED" = "1" ] && [ -n "$OLD_VERSION" ]; then
    _say "reinstalling the previous binary: openclaw@$OLD_VERSION"
    if "$NPM_BIN" install -g "openclaw@$OLD_VERSION" >/dev/null 2>&1; then
      _ok "binary restored to openclaw@$OLD_VERSION"
      STATE_BINARY_CHANGED=0
    else
      _err "BINARY RESTORE FAILED — this box may be left on a build its config does not match"
      failed=1
    fi
  fi

  if [ "$STATE_QUIESCED" = "1" ]; then
    if _start_gateway; then
      _ok "gateway started again"
      STATE_QUIESCED=0
    else
      _err "GATEWAY RESTART FAILED — the box is DOWN"
      failed=1
    fi
  fi

  _restore_selfheal
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
    echo "  ##    npm install -g openclaw@${OLD_VERSION:-<version>}" >&2
    echo "  ##    launchctl bootstrap gui/\$(id -u) \\" >&2
    echo "  ##      \$HOME/Library/LaunchAgents/$GATEWAY_LABEL.plist" >&2
    echo "  ##  Then re-arm the self-heal agent:" >&2
    echo "  ##    bash platform/mac/service-selfheal/install-service-remediate.sh" >&2
    echo "  ################################################################" >&2
    return 70
  fi
  _ok "rollback complete — this box is exactly as it was found"
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
  mv="$(_measured_version)"

  echo "config     : $OC_CONFIG"
  echo "supervisor : $SUPERVISOR"
  echo "version    : ${mv:-UNMEASURABLE} (MEASURED via \`openclaw --version\`, never a recorded value)"

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
  SUPERVISOR="$(_detect_supervisor)"

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

  if [ "$OLD_VERSION" = "$TARGET_VERSION" ] && [ "$shape" != "LEGACY_LIST" ]; then
    _ok "already on $TARGET_VERSION with a non-legacy config — nothing to do."
    return 0
  fi

  if [ "$DRY_RUN" = "1" ]; then
    echo ""
    _say "DRY RUN — the plan, in order, touching nothing:"
    echo "    1. write the maintenance lock  ($LOCK_FILE)"
    echo "    2. bootout $SELFHEAL_LABEL, then bootout $GATEWAY_LABEL (NOT kickstart)"
    echo "    3. prove quiescence: no pid, and config sha stable for ${QUIESCE_PROOF_SECONDS}s"
    echo "    4. back up the config"
    echo "    5. $NPM_BIN install -g openclaw@$TARGET_VERSION"
    echo "    6. ask the NEW binary: openclaw config schema  -> which keys does \`agents\` accept?"
    echo "    7. if it accepts \`entries\` and not \`list\`: migrate + verify losslessness; else leave the config alone"
    echo "    8. bootstrap $GATEWAY_LABEL; require a STABLE pid for ${STABILITY_SECONDS}s"
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
    if ! "$NPM_BIN" install -g "openclaw@$TARGET_VERSION" >/dev/null 2>&1; then
      _rollback "\`$NPM_BIN install -g openclaw@$TARGET_VERSION\` FAILED"
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
  schema_file="$(mktemp "${TMPDIR:-/tmp}/oc-schema.XXXXXX.json")" || {
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

  # ── 8. START, AND PROVE IT STAYED UP ───────────────────────────────────────
  if ! _start_gateway; then
    _rollback "the gateway could not be started after the upgrade"
    return $?
  fi
  if ! _prove_started; then
    _rollback "the gateway did not stay up after the upgrade"
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
