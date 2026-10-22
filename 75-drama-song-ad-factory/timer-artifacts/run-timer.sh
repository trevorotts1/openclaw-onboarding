#!/bin/sh
# run-timer.sh — the DIRECT-SHELL poller skill 75's persistent timer runs.
#
# U6: "Direct-shell persistent Mac/Hostinger/Contabo timer, no idle model event,
# correct user/paths and restart state" (joint plan section 5, row U6).
#
# WHAT IT IS. One POSIX-shell entry point that the platform scheduler (macOS
# launchd; cron inside the Hostinger/Contabo client container) invokes on an
# interval. It does the direct bridge inbox check the joint plan's platform table
# names ("Direct bridge inbox check ... No idle model call"): it resolves the
# computer's own machine key and studio address, then execs the U5 bridge
# (75-drama-song-ad-factory/shared-bridge/studio_bridge.py) with absolute paths.
#
# WHAT IT IS NOT. It never starts Claude, claude-nine, the 9Router launcher, or
# any interactive session; it never touches a model, a hook, a monitor or an
# OpenClaw idle/agent event. It is a plain program, run by a plain interval. That
# is the whole point of the row: the old schedules were model turns every couple
# of minutes while idle; this fires a shell script and nothing else.
#
# SECRETS. The key is read from the platform's own 0600 file at $DS_KEY_FILE and
# exported as DS_KEY for the child only. It is never echoed, never argv, never a
# log line. This script prints no key value on any path.
#
# EXIT: 0 ok — or a QUIET SKIP of the optional Studio capability (disabled /
#       needs-enrollment / degraded: never a noisy per-tick failure) ·
#       1 error (identity/path/bridge) · 2 refused (ready but key/address
#       vanished) · 3 undefined (bridge transport unknown) · any other code
#       is a WAKE failure propagated separately from a successful poll.
set -u

PROG="ds-timer"
say() { printf '%s %s\n' "$PROG:" "$*" >&2; }
die() { say "$*"; exit "${2:-1}"; }

# ---- 1) Platform identity: the RIGHT user and the RIGHT paths, or refuse ----
# The plan (section 1, "Runtime user" / "Persistent state") fixes these exactly.
PLATFORM="${DS_PLATFORM:-}"
if [ -z "$PLATFORM" ]; then
  case "$(uname -s 2>/dev/null)" in
    Darwin) PLATFORM=mac ;;
    Linux)  PLATFORM=linux ;;
    *)      die "unsupported uname $(uname -s 2>/dev/null); set DS_PLATFORM" 1 ;;
  esac
fi

RUN_USER="$(id -un 2>/dev/null || echo '')"
[ -n "$RUN_USER" ] || die "cannot resolve current user (id -un failed)" 1

case "$PLATFORM" in
  mac)
    # macOS box: HOME must be /Users/<user>, and the user must match HOME's leaf.
    case "$HOME" in
      /Users/*) : ;;
      *) die "mac: HOME must be /Users/<user>, got '${HOME:-<unset>}'" 1 ;;
    esac
    [ "${HOME##*/}" = "$RUN_USER" ] || die "mac: HOME leaf '${HOME##*/}' != user '$RUN_USER'" 1
    ;;
  hostinger)
    # Hostinger client container: service user `node`, persistent HOME is /data.
    [ "$RUN_USER" = "node" ] || die "hostinger: must run as user 'node', got '$RUN_USER'" 1
    case "$HOME" in
      /data) : ;;
      *) die "hostinger: HOME must be /data (persistent), got '${HOME:-<unset>}'" 1 ;;
    esac
    ;;
  contabo)
    # Contabo client container: user `node`; HOME is the EPHEMERAL layer, so all
    # persistent state (key, address, state dir) must live under /home/node/.openclaw.
    [ "$RUN_USER" = "node" ] || die "contabo: must run as user 'node', got '$RUN_USER'" 1
    case "$HOME" in
      /home/node) : ;;
      *) die "contabo: HOME must be /home/node, got '${HOME:-<unset>}'" 1 ;;
    esac
    # PM2_HOME is set by compose; if present it must be the persistent one.
    if [ -n "${PM2_HOME:-}" ]; then
      case "$PM2_HOME" in
        /home/node/.openclaw/*) : ;;
        *) die "contabo: PM2_HOME must be under /home/node/.openclaw, got '$PM2_HOME'" 1 ;;
      esac
    fi
    ;;
  *) die "unknown DS_PLATFORM '$PLATFORM' (mac|hostinger|contabo)" 1 ;;
esac

# ---- 2) Persistent state root: the key/address/state MUST survive reboot ----
# Contabo is the trap the plan names: $HOME is throwaway there, so state goes on
# the volume. Wrong (ephemeral) path => refuse, never silently lose state.
case "$PLATFORM" in
  mac)       DEFAULT_STATE="$HOME/.drama-studio" ;;
  hostinger) DEFAULT_STATE="$HOME/.drama-studio" ;;               # HOME=/data, persistent
  contabo)   DEFAULT_STATE="$HOME/.openclaw/.drama-studio" ;;      # volume, not $HOME leaf
esac
STATE_DIR="${DS_STATE_DIR:-$DEFAULT_STATE}"
case "$STATE_DIR" in
  /*) : ;;
  *) die "state dir must be absolute, got '$STATE_DIR'" 1 ;;
esac
case "$PLATFORM" in
  mac)       case "$STATE_DIR" in "$HOME"/*) : ;; *) die "mac: state dir must be under HOME, got '$STATE_DIR'" 1 ;; esac ;;
  hostinger) case "$STATE_DIR" in /data/*) : ;; *) die "hostinger: state dir must be under /data, got '$STATE_DIR'" 1 ;; esac ;;
  contabo)   case "$STATE_DIR" in /home/node/.openclaw/*) : ;; *) die "contabo: state dir must be persistent (/home/node/.openclaw/...), got '$STATE_DIR'" 1 ;; esac ;;
esac

KEY_FILE="${DS_KEY_FILE:-$STATE_DIR/machine.key}"
URL_FILE="${DS_URL_FILE:-$STATE_DIR/machine.url}"

# ---- 3) Explicit scheduler environment: never inherit a model/env context ----
# A launchd/cron job has a minimal environment; it must not depend on Claude's
# settings env (the plan: "Timers never assume Claude settings env loads").
case "$PLATFORM" in
  mac)       PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" ;;
  hostinger) PATH="/data/.npm-global/bin:/data/linuxbrew/.linuxbrew/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" ;;
  contabo)   PATH="/home/node/.openclaw/npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" ;;
esac
export PATH

# ---- 4) The machine key + studio address (own store, never Claude settings) --
# Studio intake is OPTIONAL (SPEC 9.3): an unpaired computer is a quiet skip,
# not a failure repeated every two minutes. These loads are soft here; the
# capability gate in section 5.5 decides, and only a READY box whose files
# vanished under it fails hard.
DS_BASE_URL=""
[ -f "$URL_FILE" ] && DS_BASE_URL="$(tr -d '\r\n' < "$URL_FILE" 2>/dev/null || true)"
DS_KEY=""
[ -f "$KEY_FILE" ] && DS_KEY="$(tr -d '\r\n' < "$KEY_FILE" 2>/dev/null || true)"
[ -n "$DS_KEY" ] && export DS_KEY

# ---- 5) Resolve the U5 bridge and an absolute interpreter -------------------
SKILL_ROOT="${DS_SKILL_ROOT:-}"
if [ -z "$SKILL_ROOT" ]; then
  for cand in \
    "$HOME/.openclaw/skills/75-drama-song-ad-factory" \
    "$HOME/.claude/skills/75-drama-song-ad-factory" \
    "$(dirname "$0")/.."
  do
    [ -f "$cand/shared-bridge/studio_bridge.py" ] && { SKILL_ROOT="$cand"; break; }
  done
fi
[ -n "$SKILL_ROOT" ] || die "cannot locate skill 75 root; set DS_SKILL_ROOT" 1
case "$SKILL_ROOT" in /*) : ;; *) die "DS_SKILL_ROOT must be absolute, got '$SKILL_ROOT'" 1 ;; esac
BRIDGE="$SKILL_ROOT/shared-bridge/studio_bridge.py"
[ -f "$BRIDGE" ] || die "U5 bridge not found at $BRIDGE" 1

PYTHON="$(command -v python3 2>/dev/null || true)"
[ -n "$PYTHON" ] || die "python3 not found on PATH ($PATH)" 1

# ---- 6) Optional Studio capability gate (SPEC 9.3 / D24) --------------------
# The capability is modelled explicitly as disabled | needs-enrollment | ready |
# degraded in the installation state. disabled/needs-enrollment -> quiet skip:
# a chat-only box must never be polled into noise or auto-enrolled just to
# silence logs. ready -> poll. degraded -> the gate already tried the local
# receipt recovery (key-only / interrupted enrolment, never a re-enrol); we say
# so ONCE per TRANSITION and skip quietly — the gate prints a line only when
# the state changes, so old ticks never pile up and old log lines are never
# new failures (last-attempt/successful-check timestamps live in capability.json).
export DRAMA_STUDIO_STATE="$STATE_DIR"
GATE_RC=0
GATE_OUT="$("$PYTHON" "$BRIDGE" capability --gate --repair 2>&1)" || GATE_RC=$?
[ -z "$GATE_OUT" ] || say "$GATE_OUT"
[ "$GATE_RC" -eq 0 ] || exit 0    # not ready: the optional poller stays quiet

[ -n "$DS_BASE_URL" ] || { say "no studio address at $URL_FILE — this computer is not paired"; exit 2; }
[ -n "$DS_KEY" ] || { say "no machine key at $KEY_FILE — this computer is not paired"; exit 2; }

# ---- 7) Order poll: check-in, claim, replay, one JSON line if one waited -----
# poll = SPEC §6. No model call, no Claude, no prompt, no interactive TTY.
# Exports the state root the bridge uses for its key/address fallback.

case "$PLATFORM" in
  mac)       RUNS_DIR="$HOME/.openclaw/drama-runs" ;;
  hostinger) RUNS_DIR="/data/.openclaw/drama-runs" ;;
  contabo)   RUNS_DIR="/home/node/.openclaw/drama-runs" ;;
esac

WAKE="$SKILL_ROOT/shared-bridge/wake_agent.sh"
if [ -f "$WAKE" ]; then
  POLL_OUT="$("$PYTHON" "$BRIDGE" poll --base-url "$DS_BASE_URL" --skill-root "$SKILL_ROOT" --runs "$RUNS_DIR")"
  POLL_RC=$?
  if [ "$POLL_RC" -eq 0 ] && [ -n "$POLL_OUT" ]; then
    # An order waited and the bridge printed its JSON line: hand that one line
    # to the wake script. A WAKE failure is propagated SEPARATELY from the
    # poll's success (SPEC 9.4): the exit code is the wake's own, and the line
    # names both, so a failed wake never looks like a clean tick. The wake
    # request itself stays queued in the claim ledger and is retried on the
    # next tick under the same order.
    WAKE_RC=0
    "$WAKE" "$POLL_OUT" || WAKE_RC=$?
    if [ "$WAKE_RC" -ne 0 ]; then
      say "poll succeeded but the WAKE failed (rc=$WAKE_RC) -- the handoff is not complete and stays queued"
      exit "$WAKE_RC"
    fi
  fi
  exit "$POLL_RC"
fi

# No wake script yet: hand the process straight to the poll, so its exit code is
# ours and no shell is left behind.
exec "$PYTHON" "$BRIDGE" poll --base-url "$DS_BASE_URL" --skill-root "$SKILL_ROOT" --runs "$RUNS_DIR"
