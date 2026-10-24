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
# EXIT: 0 ok · 1 error (identity/path/bridge) · 2 refused (no key/address) ·
#       3 undefined (bridge transport unknown). Mirrors the U5 bridge.
#
# MODES: no argument = the poll. `--ready` = readiness probe (install/readiness
# seam for the Studio work): same identity/path/bridge checks, one "ready" line,
# no poll, no network. Exit 0 only when this box could poll right now.
#
# QUIET WHEN DISABLED (D34): a disabled optional capability is quiet. When
# $STATE_DIR/capability.json records `disabled` or `needs-enrollment`, or
# $STATE_DIR/capability.disabled exists (or DS_CAPABILITY_DISABLED=1), the timer
# exits 0 without polling and without repeating any line — and those checks run
# BEFORE the machine.url/machine.key demand, so a chat-only box is never told it
# is "not paired" on every tick. A recorded ready/degraded capability still needs
# both credential files and is refused (exit 2) when they are missing. Unpaired notices are
# TRANSITION-based: the state change is reported once, a steady state is silent.
#
# BOUNDED LOG RETENTION (D34): the scheduler redirects this script into
# $DS_LOG_FILE (derived per platform when unset). Past $DS_LOG_MAX_BYTES the
# log keeps only its last half, in place (same inode, so `>>` redirections and
# launchd stay valid). Bounded by construction: the file never exceeds the cap.
set -u

PROG="ds-timer"
say() { printf '%s %s\n' "$PROG:" "$*" >&2; }
die() { say "$*"; exit "${2:-1}"; }

# Transition-based diagnostics (spec 9.3): notice on state CHANGE only, so an
# idle optional poller never spams and an old log line is never a new failure.
# The marker is written ONLY into an existing state dir: a poller that finds no
# state store still writes nothing (it is a reader until pairing), and without a
# writable marker the notice simply repeats instead of silently vanishing.
DS_NOTICE_STATE="${DS_NOTICE_STATE:-}"
ds_notice() {
  _sig="$1"; shift
  [ -n "$DS_NOTICE_STATE" ] || { say "$*"; return 0; }
  _prev=""
  [ -f "$DS_NOTICE_STATE" ] && _prev="$(cat "$DS_NOTICE_STATE" 2>/dev/null || true)"
  if [ "$_sig" = "$_prev" ]; then return 0; fi
  [ -d "$(dirname "$DS_NOTICE_STATE")" ] && printf '%s\n' "$_sig" > "$DS_NOTICE_STATE" 2>/dev/null || true
  [ "$_sig" = "ok" ] && return 0
  say "$*"
}

# Bounded log retention: trim to the last half once past the cap. cat-back keeps
# the inode, so every `>> $DS_LOG_FILE` redirection stays pointed at the file.
DS_LOG_MAX_BYTES="${DS_LOG_MAX_BYTES:-262144}"
ds_trim_log() {
  [ -n "${DS_LOG_FILE:-}" ] && [ -f "$DS_LOG_FILE" ] || return 0
  _sz="$(wc -c < "$DS_LOG_FILE" 2>/dev/null | tr -d ' ')"
  case "$_sz" in ''|*[!0-9]*) return 0 ;; esac
  [ "$_sz" -gt "$DS_LOG_MAX_BYTES" ] || return 0
  tail -c "$((DS_LOG_MAX_BYTES / 2))" "$DS_LOG_FILE" > "$DS_LOG_FILE.trim.$$" 2>/dev/null || return 0
  cat "$DS_LOG_FILE.trim.$$" > "$DS_LOG_FILE" 2>/dev/null || true
  rm -f "$DS_LOG_FILE.trim.$$"
  say "log retention: trimmed $DS_LOG_FILE ($_sz -> $((DS_LOG_MAX_BYTES / 2)) bytes)"
}

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

# ---- 2b) Mode, quiet-disabled capability, bounded log retention -----------
READY=0
case "${1:-}" in
  "") : ;;
  --ready) READY=1 ;;
  *) die "unknown argument '${1}' (no argument = poll, or --ready)" 1 ;;
esac

DS_NOTICE_STATE="${DS_NOTICE_STATE:-$STATE_DIR/.poll-state}"
case "$PLATFORM" in
  mac)       DS_LOG_FILE="${DS_LOG_FILE:-$HOME/Library/Logs/openclaw/drama-studio-timer.log}" ;;
  hostinger) DS_LOG_FILE="${DS_LOG_FILE:-/data/.openclaw/logs/drama-studio-timer.log}" ;;
  contabo)   DS_LOG_FILE="${DS_LOG_FILE:-/home/node/.openclaw/logs/drama-studio-timer.log}" ;;
esac
export DS_LOG_FILE
ds_trim_log

# A disabled optional capability polls nothing and says nothing (D34). The one
# transition line tells the story once; every later tick is silent.
if [ "${DS_CAPABILITY_DISABLED:-0}" = "1" ] || [ -f "$STATE_DIR/capability.disabled" ]; then
  ds_notice disabled "studio capability disabled - timer idle (quiet)"
  exit 0
fi

# ---- 3) Explicit scheduler environment: never inherit a model/env context ----
# A launchd/cron job has a minimal environment; it must not depend on Claude's
# settings env (the plan: "Timers never assume Claude settings env loads").
case "$PLATFORM" in
  mac)       PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" ;;
  hostinger) PATH="/data/.npm-global/bin:/data/linuxbrew/.linuxbrew/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" ;;
  contabo)   PATH="/home/node/.openclaw/npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" ;;
esac
export PATH

# ---- 3b) Optional Studio capability: evaluated BEFORE any credential demand --
# SPEC 9.3 / D24. The optional Studio capability is recorded in the CANONICAL
# installation state file, capability.json (disabled | needs-enrollment | ready |
# degraded), written by studio_bridge.py. A disabled or chat-only computer polls
# nothing and says nothing — and must not be told it is "not paired" on every
# tick, which is what happens when the credential demand below runs first. The
# recorded capability is therefore read HERE, before section 4.
#
# A recorded ready/degraded capability falls through to the credential demand
# UNCHANGED, so an enabled-but-broken install is refused (exit 2) rather than
# silently skipped. With NO record, studio_bridge._capability_state's canonical
# answer for "no key and no enrolment intent" is `disabled`, so an unpaired box
# exits 0 in total silence and writes nothing — no record, no marker, no key.
# This reads the canonical file and introduces no second state mechanism.
# `--ready` is a readiness probe: it is never skipped here.
CAP_FILE="${DS_CAPABILITY_FILE:-$STATE_DIR/capability.json}"
CAP_RECORDED=""
if [ -f "$CAP_FILE" ]; then
  # Parse with a real JSON reader, not a line regex: a case variant, a
  # duplicate key or a multi-line layout must not change the decision. json
  # resolves a duplicate key deterministically (last wins) and rejects a
  # truncated file, so the same record can never yield opposite outcomes.
  CAP_RECORDED="$(python3 -c 'import json,sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.exit(0)
v = d.get("capability") if isinstance(d, dict) else None
print(v.strip().lower() if isinstance(v, str) else "")' "$CAP_FILE" 2>/dev/null || true)"
fi
if [ "$READY" -eq 0 ]; then
  case "$CAP_RECORDED" in
    disabled|needs-enrollment)
      ds_notice "$CAP_RECORDED" "studio capability $CAP_RECORDED - timer idle (quiet)"
      exit 0 ;;
    ready|degraded)
      : ;;   # enabled: the credential demand below still decides (refusal kept)
    "")
      # No usable record: no key and no enrolment intent is the canonical
      # `disabled` state. Silent, and writes nothing.
      if [ ! -f "$KEY_FILE" ]; then
        exit 0
      fi ;;
    *)
      : ;;   # unrecognised value: fail CLOSED, let the credential demand decide
  esac
fi

# ---- 4) The machine key + studio address (own store, never Claude settings) --
# The pairing gate comes FIRST: an unpaired computer is not paired whether or
# not the skill copy and interpreter are present, and must say exactly that.
# Transition notices only: one line when pairing state CHANGES, silence after.
[ -f "$URL_FILE" ] || { ds_notice unpaired "no studio address at $URL_FILE — this computer is not paired"; exit 2; }
DS_BASE_URL="$(tr -d '\r\n' < "$URL_FILE" 2>/dev/null || true)"
[ -n "$DS_BASE_URL" ] || { ds_notice unpaired "empty studio address at $URL_FILE"; exit 2; }

[ -f "$KEY_FILE" ] || { ds_notice unpaired "no machine key at $KEY_FILE — this computer is not paired"; exit 2; }
DS_KEY="$(tr -d '\r\n' < "$KEY_FILE" 2>/dev/null || true)"
[ -n "$DS_KEY" ] || { ds_notice unpaired "empty machine key at $KEY_FILE"; exit 2; }
export DS_KEY
ds_notice ok "paired"

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

# ---- 5b) Readiness seam (W07-U3 Studio work): everything the poll needs is
# resolved, nothing is polled, no network. Exit 0 = this box could poll now.
if [ "$READY" -eq 1 ]; then
  say "ready: platform=$PLATFORM user=$RUN_USER state=$STATE_DIR bridge=$BRIDGE python=$PYTHON"
  exit 0
fi

# ---- 6) Order poll: check-in, claim, replay, one JSON line if one waited -----
# poll = SPEC §6. No model call, no Claude, no prompt, no interactive TTY.
# Exports the state root the bridge uses for its key/address fallback.
export DRAMA_STUDIO_STATE="$STATE_DIR"

# ---- 6b) Optional Studio capability gate (SPEC 9.3 / D24) -------------------
# The capability is modelled explicitly as disabled | needs-enrollment | ready |
# degraded in the installation state. disabled/needs-enrollment -> quiet skip:
# a chat-only box must never be polled into noise or auto-enrolled just to
# silence logs. ready -> poll. degraded -> the gate already tried the local
# receipt recovery (key-only / interrupted enrolment, never a re-enrol); we say
# so ONCE per TRANSITION and skip quietly — the gate prints a line only when
# the state changes, so old ticks never pile up and old log lines are never
# new failures (last-attempt/successful-check timestamps live in capability.json).
GATE_RC=0
GATE_OUT="$("$PYTHON" "$BRIDGE" capability --gate --repair 2>&1)" || GATE_RC=$?
[ -z "$GATE_OUT" ] || say "$GATE_OUT"
[ "$GATE_RC" -eq 0 ] || exit 0    # not ready: the optional poller stays quiet

[ -n "$DS_BASE_URL" ] || { say "no studio address at $URL_FILE — this computer is not paired"; exit 2; }
[ -n "$DS_KEY" ] || { say "no machine key at $KEY_FILE — this computer is not paired"; exit 2; }

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
