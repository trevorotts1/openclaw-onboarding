#!/bin/sh
# self-update.sh — v1.1.0
#
# The box's own self-update runner. Starts itself in a detached session, then
# runs these steps IN THIS ORDER (Trevor, transcript L14):
#
#   step 1  999-setup the 999 installer, cloned from 999 main when absent, with
#                     NINE_API_DOCS pointing at a box-local mode-600 file and no
#                     terminal attached. The checkout is brought to origin/main with
#                     shared-utils/git_ff_sync.sh and VERIFIED (HEAD == origin/main,
#                     and the --999-sha pin when given) or the step FAILS; the
#                     9router step refuses to run from an unverified checkout.
#   step 2  9router   install-9router-guards.sh --upgrade <pinned target>
#   step 3  upgrade   OpenClaw to the version the TRIGGER passes in (Mac only;
#                     skipped on a Docker box — the host side already did it)
#   step 4  update    scripts/weekly-full-update.sh (the FULL path, no terminal)
#
# Every step's RAW exit code is recorded in the JSON status file and the job
# CONTINUES after a failed step. The single exception is OpenClaw rc 70 (rollback
# failed): the status is written and the job exits 20 at once, because a human is
# needed. The final exit code is the code of the FIRST failed step.
#
# Every script this job pulls — oc-supervisor-install.py, git_ff_sync.sh,
# oc-atomic-upgrade.sh, oc-schema-migrate.py, weekly-full-update.sh — comes from
# ONE ref: --onboarding-sha when the roll pins one, else live main (unchanged
# behavior when no pin is passed). The ref actually used is written to the status
# file as onboarding_ref, with the pin itself as onboarding_sha ("" when none).
# That is what makes a frozen roll stay frozen while it runs.
#
# The job writes ONE status file the operator watch reads:
#   <openclaw root>/fleet-refresh/agent-pull-status.json
# with the fields in references/agent-pull.md section 10.9 and SKILL.md:362.
# The per-roll log file is kept.
#
# The launcher prints, as its FIRST stdout line:
#   RUN_ID=ap-<ROLL_ID>-<epoch>-<pid>
# and passes that id to the detached child. A second launch on the same box
# prints the existing RUN_ID and exits 0: never two updaters at once.
#
# Exit codes (the detached child's; the launcher returns 0 once it has started):
#   0   success
#   20  OpenClaw rc 70 — rollback failed, human needed
#   *   otherwise the RAW exit code of the first failed step
#   22  refusal (no root, no target version, missing tools)
#
# No key value is ever printed, echoed, or written to the status file or the log.
#
# agent-pull-fix: R5
# agent-pull-fix: R10
#
# INTERPRETER: /bin/sh, POSIX-safe, macOS bash 3.2 safe. No arrays, no
# associative params, no mapfile, no ${x^^}, no heredoc nested inside $( ).
set -u

VERSION="1.1.0"
REPO_RAW_BASE="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding"
REPO_RAW="$REPO_RAW_BASE/main"

EX_OK=0
EX_UPGRADE=20
EX_UPDATE=21
EX_REFUSE=22
EX_999=23
EX_9ROUTER=24

SELF="$0"
MODE_DETACHED=0
MODE_FOREGROUND=0
ROLL_ID=""
RUN_ID=""
LAUNCH_EPOCH=""
TARGET_VERSION=""
NINE9ROUTER_TARGET="${NINEROUTER_TARGET:-}"
NINE_SETUP_SHA="${NINE_SETUP_SHA:-}"   # optional pin: the 999 checkout HEAD must equal it (CAN012)
ONBOARDING_SHA="${ONBOARDING_SHA:-}"   # optional pin: fetch EVERY script this job pulls at this sha, not live main
ONBOARDING_REF="main"                  # the ref actually used: the pinned sha, or main when unpinned

# The 999 installer's own required key names (its parse_api_docs contract) and
# the aliases a box may store a key under. NEVER printed. Writing canonicalises:
# OLLAMA_CLOUD_API_KEY -> OLLAMA_API_KEY, AGNES_AI_API_KEY -> AGNES_API_KEY.
KEY_NAMES="OLLAMA_API_KEY OLLAMA_CLOUD_API_KEY DEEPSEEK_API_KEY AGNES_API_KEY AGNES_AI_API_KEY OPENROUTER_API_KEY"
CANON_KEYS="OLLAMA_API_KEY DEEPSEEK_API_KEY AGNES_API_KEY OPENROUTER_API_KEY"
PLAN_NAMES="OLLAMA_PLAN AGNES_PLAN"
API_DOCS_DIR="$HOME/.config/blackceo-999"
API_DOCS_FILE="$API_DOCS_DIR/api-docs.md"

ROLLED_BACK=0
NEEDS_RESTART=0
STEP_CODES=""
FIRST_FAIL=""
STUCK_NOTE=""
LOCK_OWNED=0
LOCK_DIR=""
WORK=""

now_utc() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

usage() {
  sed -n '2,42p' "$SELF"
  echo ""
  echo "Usage: self-update.sh --roll-id ID --openclaw-target X.Y.Z [--ninerouter-target VERSION] [--999-sha SHA] [--onboarding-sha SHA]"
  echo "       self-update.sh --roll-id ID --openclaw-target X.Y.Z --foreground   (no detach; for tests)"
  echo ""
  echo "  --openclaw-target   also accepted as --target-version"
  echo "  --ninerouter-target also accepted as --9router-target"
  echo "  --999-sha           optional: the 999-setup HEAD must equal this sha (and origin/main)"
  echo "  --onboarding-sha    optional: fetch every script this job pulls (oc-atomic-upgrade.sh,"
  echo "                      oc-schema-migrate.py, oc-supervisor-install.py, git_ff_sync.sh,"
  echo "                      weekly-full-update.sh) at this 40-hex commit, not live main"
  exit "$1"
}

# ── status ───────────────────────────────────────────────────────────────────
# One JSON file, rewritten atomically (temp file + os.replace, mode 600). The
# error_tail is the last 20 log lines through _redact: a child that misbehaves
# must not be able to put a key in here.

_redact() {
  sed -E \
    -e 's/([A-Za-z_][A-Za-z0-9_]*(KEY|TOKEN|SECRET|PASSWORD|PASSWD))[=:][^ ]*/\1=<redacted>/g' \
    -e 's/sk-[A-Za-z0-9_-]{12,}/sk-<redacted>/g' \
    -e 's/[A-Fa-f0-9]{32,}/<redacted>/g' 2>/dev/null | cut -c1-400
}

log() { printf '[self-update %s] %s\n' "$(now_utc)" "$*"; }

record_step() {  # name raw_rc
  STEP_CODES="${STEP_CODES}$1=$2;"
}

record_fail() {  # raw_rc note
  [ -n "$FIRST_FAIL" ] || FIRST_FAIL="$1"
  [ -n "$STUCK_NOTE" ] || STUCK_NOTE="$2"
}

read_stamp() {
  head -n1 "$ROOT/skills/.onboarding-version" 2>/dev/null | tr -d '[:space:]'
}

json_version() {  # package.json -> version
  [ -n "$1" ] && [ -f "$1" ] || { printf ''; return 0; }
  python3 -c 'import json,sys
try: print(json.load(open(sys.argv[1])).get("version",""))
except Exception: print("")' "$1" 2>/dev/null | head -n1
}

# CAN015: the OpenClaw to report is the one the SUPERVISOR launches (launchd
# ProgramArguments / systemd ExecStart), not whichever copy PATH or the
# fallbacks below find first. oc-supervisor-install.py resolves it; it sits next
# to this script when run from a checkout, else it is fetched once per process.
# Call sup_helper_init in the PARENT shell (a $( ) would discard the result).
SUP_HELPER_PATH=""
sup_helper_init() {
  _h="$(dirname "$SELF")/oc-supervisor-install.py"
  if [ ! -f "$_h" ]; then
    _h="$REFRESH_DIR/oc-supervisor-install.py"
    curl -fsSL --max-time 30 "$REPO_RAW/scripts/oc-supervisor-install.py" -o "$_h" >>"$LOG" 2>&1 \
      || { rm -f "$_h"; _h=""; }
  fi
  SUP_HELPER_PATH="$_h"
}

oc_pkg() {
  if [ -n "$SUP_HELPER_PATH" ]; then
    _p="$(python3 "$SUP_HELPER_PATH" pkg_json 2>/dev/null)" && [ -f "$_p" ] && { printf '%s' "$_p"; return 0; }
  fi
  for _p in "$ROOT/npm-global/lib/node_modules/openclaw/package.json" \
            "$HOME/.openclaw/npm-global/lib/node_modules/openclaw/package.json" \
            /data/.npm-global/lib/node_modules/openclaw/package.json \
            /home/node/.openclaw/npm-global/lib/node_modules/openclaw/package.json \
            "$HOME/.npm-global/lib/node_modules/openclaw/package.json" \
            "${NPM_CONFIG_PREFIX:-/nonexistent}/lib/node_modules/openclaw/package.json"; do
    case "$_p" in /nonexistent/*) continue ;; esac
    if [ -f "$_p" ]; then printf '%s' "$_p"; return 0; fi
  done
  if command -v npm >/dev/null 2>&1; then
    _p="$(npm root -g 2>/dev/null)/openclaw/package.json"
    [ -f "$_p" ] && { printf '%s' "$_p"; return 0; }
  fi
  printf ''
}

oc_version() { json_version "$(oc_pkg)"; }

# openclaw_after for the status file. The supervisor's package.json at the target is only a
# success once the atomic upgrade (which proves the live gateway runs it) exited 0; a failed
# upgrade with the package at the target must not read as DONE.
oc_after() {
  _v="$(oc_version)"
  if [ -n "${UPG_RC:-}" ] && [ "$UPG_RC" != 0 ] && [ -n "$_v" ] && [ "$_v" = "${TARGET_VERSION:-}" ]; then
    printf 'unproven'
  else
    printf '%s' "$_v"
  fi
}

nr_pkg() {
  for _p in "$HOME/.local/share/999/npm/lib/node_modules/9router/package.json" \
            "${NPM_CONFIG_PREFIX:-/nonexistent}/lib/node_modules/9router/package.json"; do
    case "$_p" in /nonexistent/*) continue ;; esac
    if [ -f "$_p" ]; then printf '%s' "$_p"; return 0; fi
  done
  if command -v npm >/dev/null 2>&1; then
    _nr="$(npm root -g --prefix "$HOME/.local/share/999/npm" 2>/dev/null)"
    if [ -n "$_nr" ] && [ -f "$_nr/9router/package.json" ]; then
      printf '%s' "$_nr/9router/package.json"; return 0
    fi
  fi
  printf ''
}

# File-based only: running the 9router CLI can trigger a download, and the
# status file must never cause a side effect.
nr_version() { json_version "$(nr_pkg)"; }

status_write() {  # phase finished stuck
  mkdir -p "$ROOT/fleet-refresh" 2>/dev/null || return 0
  _tail="${TMPDIR:-/tmp}/self-update-tail.$$"
  tail -n 20 "$LOG" 2>/dev/null | _redact > "$_tail" 2>/dev/null || : > "$_tail"
  [ -f "$ROOT/fleet-refresh/needs_host_restart" ] && NEEDS_RESTART=1 || NEEDS_RESTART=0
  python3 - "$STATUS_JSON" "$RUN_ID" "$ROLL_ID" "$1" "$STARTED" "$(now_utc)" "$2" \
    "$STEP_CODES" "$STAMP_BEFORE" "$(read_stamp)" "$OC_BEFORE" "$(oc_after)" \
    "$NR_BEFORE" "$(nr_version)" "$ROLLED_BACK" "$NEEDS_RESTART" "$3" "$_tail" \
    "$ONBOARDING_SHA" "$ONBOARDING_REF" <<'PY'
import json, os, sys
(dest, run_id, roll_id, phase, started, updated, finished, codes,
 stamp_b, stamp_a, oc_b, oc_a, nr_b, nr_a, rolled_back, needs_restart,
 stuck, tailf, onboarding_sha, onboarding_ref) = sys.argv[1:21]
slow = {}
for part in (codes or "").split(";"):
    if "=" not in part:
        continue
    k, v = part.split("=", 1)
    try:
        slow[k] = int(v)
    except ValueError:
        pass
try:
    with open(tailf, "r", errors="replace") as f:
        tail = f.read()[-8000:]
except Exception:
    tail = ""
d = {
    "run_id": run_id,
    "roll_id": roll_id,
    "phase": phase,
    "started_utc": started,
    "updated_utc": updated,
    "finished_utc": finished or "",
    "step_exit_codes": slow,
    "stamp_before": stamp_b,
    "stamp_after": stamp_a,
    "openclaw_before": oc_b,
    "openclaw_after": oc_a,
    "ninerouter_before": nr_b,
    "ninerouter_after": nr_a,
    "rolled_back": rolled_back == "1",
    "needs_host_restart": needs_restart == "1",
    "stuck_reason": stuck,
    "onboarding_sha": onboarding_sha,
    "onboarding_ref": onboarding_ref,
    "error_tail": tail,
}
d = {k: (v.replace("\r", " ") if isinstance(v, str) else v) for k, v in d.items()}
os.makedirs(os.path.dirname(dest), exist_ok=True)
tmp = dest + ".tmp.%d" % os.getpid()
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    json.dump(d, f, separators=(",", ":"))
    f.write("\n")
os.replace(tmp, dest)
try:
    os.chmod(dest, 0o600)
except OSError:
    pass
PY
  rm -f "$_tail" 2>/dev/null
  return 0
}

finish() {  # exit_code phase [stuck]
  status_write "$2" "$(now_utc)" "${3:-$STUCK_NOTE}"
  log "END phase=$2 exit=$1"
  exit "$1"
}

# ── arguments ────────────────────────────────────────────────────────────────

while [ "$#" -gt 0 ]; do
  case "$1" in
    --roll-id)
      [ "$#" -ge 2 ] || { echo "self-update.sh: --roll-id needs a value" >&2; exit "$EX_REFUSE"; }
      ROLL_ID="$2"; shift 2 ;;
    --run-id)
      [ "$#" -ge 2 ] || { echo "self-update.sh: --run-id needs a value" >&2; exit "$EX_REFUSE"; }
      RUN_ID="$2"; shift 2 ;;
    --launch-epoch)
      [ "$#" -ge 2 ] || { echo "self-update.sh: --launch-epoch needs a value" >&2; exit "$EX_REFUSE"; }
      LAUNCH_EPOCH="$2"; shift 2 ;;
    --openclaw-target|--target-version)
      [ "$#" -ge 2 ] || { echo "self-update.sh: $1 needs a value" >&2; exit "$EX_REFUSE"; }
      TARGET_VERSION="$2"; shift 2 ;;
    --ninerouter-target|--9router-target)
      [ "$#" -ge 2 ] || { echo "self-update.sh: $1 needs a value" >&2; exit "$EX_REFUSE"; }
      NINE9ROUTER_TARGET="$2"; shift 2 ;;
    --999-sha)
      [ "$#" -ge 2 ] || { echo "self-update.sh: --999-sha needs a value" >&2; exit "$EX_REFUSE"; }
      NINE_SETUP_SHA="$2"; shift 2 ;;
    --onboarding-sha)
      [ "$#" -ge 2 ] || { echo "self-update.sh: --onboarding-sha needs a value" >&2; exit "$EX_REFUSE"; }
      ONBOARDING_SHA="$2"; shift 2 ;;
    --detached)    MODE_DETACHED=1; shift ;;
    --foreground)  MODE_FOREGROUND=1; shift ;;
    -h|--help)     usage 0 ;;
    *) echo "self-update.sh: unknown argument: $1 (try --help)" >&2; exit "$EX_REFUSE" ;;
  esac
done

# The roll id becomes a FILENAME, so it may not carry a path separator or a
# leading dot. Anything else is a refusal, never a sanitized guess.
case "${ROLL_ID:-}" in
  "") ;;
  *[!A-Za-z0-9._-]*|.*) echo "self-update.sh: REFUSED — --roll-id may contain only A-Z a-z 0-9 . _ - and may not start with '.'" >&2; exit "$EX_REFUSE" ;;
esac

# A pinned 999 sha is compared as a hex prefix, so it must be hex (7-40 chars).
NINE_SETUP_SHA="$(printf '%s' "$NINE_SETUP_SHA" | tr 'A-F' 'a-f')"
case "$NINE_SETUP_SHA" in
  "") ;;
  *[!0-9a-f]*) echo "self-update.sh: REFUSED — --999-sha must be 7-40 hex characters" >&2; exit "$EX_REFUSE" ;;
  *) [ "${#NINE_SETUP_SHA}" -ge 7 ] && [ "${#NINE_SETUP_SHA}" -le 40 ] || { echo "self-update.sh: REFUSED — --999-sha must be 7-40 hex characters" >&2; exit "$EX_REFUSE"; } ;;
esac

# A pinned onboarding sha becomes a PATH SEGMENT in every raw fetch URL, so it
# is a full commit id: exactly 40 hex characters, nothing else. A short sha or
# a branch name would let the roll drift, which is the defect the pin closes.
ONBOARDING_SHA="$(printf '%s' "$ONBOARDING_SHA" | tr 'A-F' 'a-f')"
if [ -n "$ONBOARDING_SHA" ]; then
  case "$ONBOARDING_SHA" in
    *[!0-9a-f]*) echo "self-update.sh: REFUSED — --onboarding-sha must be 40 hex characters" >&2; exit "$EX_REFUSE" ;;
  esac
  [ "${#ONBOARDING_SHA}" -eq 40 ] || { echo "self-update.sh: REFUSED — --onboarding-sha must be 40 hex characters" >&2; exit "$EX_REFUSE"; }
  ONBOARDING_REF="$ONBOARDING_SHA"
fi

# Every script this job pulls comes from THIS ref: the roll's frozen onboarding
# sha when the trigger passes one, else live main (the pre-pin behavior).
REPO_RAW="$REPO_RAW_BASE/$ONBOARDING_REF"

# The launcher's run id. Printed as the FIRST stdout line, below, and passed to
# the detached child. Kept when the child receives it with --run-id.
if [ -z "$RUN_ID" ]; then
  RUN_ID="ap-${ROLL_ID}-$(date -u +%s)-$$"
fi

# ── root, log, status ────────────────────────────────────────────────────────

if [ -n "${OPENCLAW_ROOT:-}" ] && [ -d "${OPENCLAW_ROOT}" ]; then
  ROOT="$OPENCLAW_ROOT"
elif [ -d /data/.openclaw ]; then
  ROOT=/data/.openclaw
elif [ -d "$HOME/.openclaw" ]; then
  ROOT="$HOME/.openclaw"
else
  echo "self-update.sh: REFUSED — no OpenClaw root (tried \$OPENCLAW_ROOT, /data/.openclaw, $HOME/.openclaw)" >&2
  exit "$EX_REFUSE"
fi

REFRESH_DIR="$ROOT/fleet-refresh"
mkdir -p "$REFRESH_DIR" 2>/dev/null || {
  echo "self-update.sh: REFUSED — cannot create $REFRESH_DIR" >&2; exit "$EX_REFUSE"; }
LOCK_DIR="$REFRESH_DIR/agent-pull.lock"
STATUS_JSON="$REFRESH_DIR/agent-pull-status.json"

# One log per ROLL, so two rolls on one box can never overwrite each other's
# run. Without a roll id the legacy single-file name is kept.
if [ -n "$ROLL_ID" ]; then
  STATUS_DIR="$ROOT/self-update"
  ( umask 077; mkdir -p "$STATUS_DIR" ) 2>/dev/null || {
    echo "self-update.sh: REFUSED — cannot create $STATUS_DIR" >&2; exit "$EX_REFUSE"; }
  chmod 700 "$STATUS_DIR" 2>/dev/null || true
  LOG="$STATUS_DIR/$ROLL_ID.log"
else
  mkdir -p "$ROOT/logs" 2>/dev/null || true
  LOG="$ROOT/logs/self-update.log"
fi
( umask 077; : >> "$LOG" ) 2>/dev/null || {
  echo "self-update.sh: REFUSED — cannot write $LOG" >&2; exit "$EX_REFUSE"; }
chmod 600 "$LOG" 2>/dev/null || true
STARTED="$(now_utc)"

IS_DOCKER=0
[ -f /.dockerenv ] && IS_DOCKER=1
IS_MAC=0
[ "$(uname -s)" = "Darwin" ] && IS_MAC=1

# ── single-instance lock ─────────────────────────────────────────────────────
# mkdir is atomic. The lock holds the pid and the run id. A live pid means the
# launch is a duplicate: print the EXISTING run id as the first stdout line and
# exit 0. A dead pid is a crashed run: remove the directory and continue.

lock_take() {
  _lt_i=0
  while [ "$_lt_i" -lt 20 ]; do
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      printf '%s\n' "$$" > "$LOCK_DIR/pid" 2>/dev/null
      printf '%s\n' "$RUN_ID" > "$LOCK_DIR/run_id" 2>/dev/null
      return 0
    fi
    if [ -f "$LOCK_DIR/pid" ]; then
      _lt_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null)"
      case "$_lt_pid" in
        ''|*[!0-9]*) : ;;
        *)
          if kill -0 "$_lt_pid" 2>/dev/null; then
            _lt_run="$(cat "$LOCK_DIR/run_id" 2>/dev/null)"
            printf 'RUN_ID=%s\n' "${_lt_run:-}"
            return 2
          fi ;;
      esac
      rm -rf "$LOCK_DIR" 2>/dev/null
      continue
    fi
    sleep 0.1 2>/dev/null || sleep 1
    _lt_i=$((_lt_i + 1))
  done
  return 1
}

cleanup() {
  [ -n "${WORK:-}" ] && rm -rf "$WORK" 2>/dev/null
  [ "${LOCK_OWNED:-0}" = 1 ] && rm -rf "$LOCK_DIR" 2>/dev/null
  :
}
trap cleanup EXIT HUP INT TERM

if [ "$MODE_DETACHED" = 0 ]; then
  lock_take
  _lockrc=$?
  if [ "$_lockrc" = 2 ]; then
    exit "$EX_OK"
  elif [ "$_lockrc" != 0 ]; then
    echo "self-update.sh: REFUSED — cannot create lock $LOCK_DIR" >&2
    exit "$EX_REFUSE"
  fi
  LOCK_OWNED=1
  printf 'RUN_ID=%s\n' "$RUN_ID"
else
  # The launcher owns the lock for this child; release it here when the job ends.
  LOCK_OWNED=1
fi

# ── preflight ────────────────────────────────────────────────────────────────

if ! command -v python3 >/dev/null 2>&1; then
  echo "self-update.sh: REFUSED — python3 missing (needed for the status contract)" >&2
  exit "$EX_REFUSE"
fi
if command -v curl >/dev/null 2>&1; then :; else
  echo "self-update.sh: REFUSED — curl missing — cannot fetch the update scripts from main" >&2
  exit "$EX_REFUSE"
fi
if [ -z "$TARGET_VERSION" ] && [ "$IS_DOCKER" = 0 ]; then
  printf '[self-update %s] REFUSED: no --openclaw-target (the trigger must pass the version; it is never discovered)\n' "$(now_utc)"
  exit "$EX_REFUSE"
fi

# ── detach ───────────────────────────────────────────────────────────────────
# A gateway restart must never kill this: the child is put in its OWN SESSION
# with Python start_new_session=True (spec 4.2 item 2). stdio is attached to the
# per-roll log, so the child never writes to the trigger's terminal.

if [ "$MODE_DETACHED" = 0 ] && [ "$MODE_FOREGROUND" = 0 ]; then
  [ -n "$LAUNCH_EPOCH" ] || LAUNCH_EPOCH="$(date +%s)"
  set -- --detached --run-id "$RUN_ID" --launch-epoch "$LAUNCH_EPOCH"
  [ -n "$ROLL_ID" ] && set -- "$@" --roll-id "$ROLL_ID"
  [ -n "$TARGET_VERSION" ] && set -- "$@" --openclaw-target "$TARGET_VERSION"
  [ -n "$NINE9ROUTER_TARGET" ] && set -- "$@" --ninerouter-target "$NINE9ROUTER_TARGET"
  [ -n "$NINE_SETUP_SHA" ] && set -- "$@" --999-sha "$NINE_SETUP_SHA"
  # The pin MUST reach the child: the child is the one that fetches, so dropping
  # it here would silently put the whole roll back on live main.
  [ -n "$ONBOARDING_SHA" ] && set -- "$@" --onboarding-sha "$ONBOARDING_SHA"
  CHILD="$(python3 -c 'import subprocess,sys
p = subprocess.Popen(sys.argv[2:], stdin=subprocess.DEVNULL,
                     stdout=open(sys.argv[1], "ab"), stderr=subprocess.STDOUT,
                     start_new_session=True)
print(p.pid)' "$LOG" bash "$SELF" "$@" 2>>"$LOG" </dev/null)"
  if [ -z "$CHILD" ]; then
    echo "self-update.sh: REFUSED — could not start the detached child" >&2
    rm -rf "$LOCK_DIR" 2>/dev/null
    exit "$EX_REFUSE"
  fi
  # The lock must name the CHILD's pid: the launcher exits at once, so its own
  # pid would look like a dead run on the very next launch.
  printf '%s\n' "$CHILD" > "$LOCK_DIR/pid" 2>/dev/null
  # The watch must see the new run before the child reaches its first step.
  STAMP_BEFORE="$(read_stamp)"
  sup_helper_init
  OC_BEFORE="$(oc_version)"
  NR_BEFORE="$(nr_version)"
  status_write "launched" "" ""
  LOCK_OWNED=0   # the child releases it in finish()
  log "START detached pid=$CHILD run_id=$RUN_ID target=${TARGET_VERSION:-none}"
  exit "$EX_OK"
fi

# ── the job (detached child, or --foreground) ────────────────────────────────

# The lock's pid is this process now; the launcher's own pid is already gone.
if [ "$MODE_DETACHED" = 1 ] && [ -d "$LOCK_DIR" ]; then
  printf '%s\n' "$$" > "$LOCK_DIR/pid" 2>/dev/null
fi

log "START runner v$VERSION pid=$$ root=$ROOT roll=${ROLL_ID:-none} run_id=$RUN_ID openclaw=${TARGET_VERSION:-none} ninerouter=${NINE9ROUTER_TARGET:-none}"

# Pre-update values, kept for every subsequent status write.
STAMP_BEFORE="$(read_stamp)"
sup_helper_init
OC_BEFORE="$(oc_version)"
NR_BEFORE="$(nr_version)"
[ -n "$SUP_HELPER_PATH" ] || log "WARN: oc-supervisor-install.py unavailable - openclaw versions below come from PATH-era fallbacks, not the supervisor's install"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/self-update.XXXXXX")" || {
  log "REFUSED: could not create a temp dir"
  finish "$EX_REFUSE" "preflight"
}

fetch() {  # url dest
  curl -fsSL --max-time 60 "$1" -o "$2" >>"$LOG" 2>&1
}

# ══ step 1: 999 setup (FIRST — Trevor L14) ═══════════════════════════════════

find_999() {
  for _cand in "${NINE_SETUP_REPO:-}" "$ROOT/persist-home/999-setup" "$HOME/999-setup" \
               "$ROOT/persist-home/999-setup-clean" "$HOME/Documents/999-setup" "$HOME/.claude-nine"; do
    [ -n "$_cand" ] && [ -d "$_cand" ] || continue
    [ -f "$_cand/.claude/skills/nine-router-setup/scripts/setup-macos.sh" ] || continue
    printf '%s' "$_cand"; return 0
  done
  for _link in "$HOME/.claude/skills/nine-router-setup" "$HOME/.claude-nine/skills/nine-router-setup"; do
    [ -L "$_link" ] || continue
    _cand="$(cd "$_link" 2>/dev/null && cd ../../.. 2>/dev/null && pwd -P)" || continue
    [ -n "$_cand" ] && [ -f "$_cand/.claude/skills/nine-router-setup/scripts/setup-macos.sh" ] || continue
    printf '%s' "$_cand"; return 0
  done
  return 1
}

# CAN012: bring a 999 checkout to origin/main with the SAME safe semantics the
# content-update paths use (shared-utils/git_ff_sync.sh: fetch --prune; a branch
# whose upstream was deleted + clean tree + 0 unmerged commits -> main + ff;
# anything else is left untouched and reported; never reset --hard / stash /
# branch delete), then PROVE the checkout HEAD is origin/main (and the pinned sha
# when the roll passes one). self-update.sh is delivered as a single file, so the
# helper is fetched from the pinned onboarding ref (main when unpinned) like the
# other update scripts; a sibling copy is only the fallback.
FFSYNC=""
get_ffsync() {
  [ -z "$FFSYNC" ] || return 0
  if fetch "$REPO_RAW/shared-utils/git_ff_sync.sh" "$WORK/git_ff_sync.sh" && [ -s "$WORK/git_ff_sync.sh" ]; then
    FFSYNC="$WORK/git_ff_sync.sh"; return 0
  fi
  _sib="$(dirname "$SELF")/../shared-utils/git_ff_sync.sh"
  [ -f "$_sib" ] && { FFSYNC="$_sib"; return 0; }
  return 1
}

V999_HEAD=""   # set only when sync_999 verified the checkout; the 9router step requires it
V999_WHY=""

sync_999() {  # repo -> 0 verified (V999_HEAD set) | 1 failed (V999_WHY says why)
  _r="$1"; V999_HEAD=""; V999_WHY=""
  command -v git >/dev/null 2>&1 || { V999_WHY="git missing"; return 1; }
  [ -e "$_r/.git" ] || { V999_WHY="$_r is not a git checkout; cannot verify it matches origin/main"; return 1; }
  get_ffsync || { V999_WHY="git_ff_sync.sh unavailable (fetch from main and sibling copy both failed)"; return 1; }
  _out="$(sh "$FFSYNC" "$_r" 2>&1 </dev/null)"; _rc=$?
  _def="$(git -C "$_r" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null)"; _def="${_def#origin/}"
  [ -n "$_def" ] || for _def in main master; do
    git -C "$_r" rev-parse -q --verify "refs/remotes/origin/$_def" >/dev/null 2>&1 && break; _def=
  done
  _br="$(git -C "$_r" symbolic-ref -q --short HEAD 2>/dev/null || echo 'detached HEAD')"
  _n="$(git -C "$_r" rev-list --count "origin/${_def:-main}..HEAD" 2>/dev/null || echo '?')"
  _ctx="branch=$_br unmerged_commits=$_n"
  if [ "$_rc" -ne 0 ]; then
    V999_WHY="git_ff_sync.sh rc=$_rc in $_r ($_ctx): $_out"; return 1
  fi
  [ -z "$_out" ] || log "999-setup: $_out"
  _h="$(git -C "$_r" rev-parse HEAD 2>/dev/null)"
  _om=""
  [ -z "$_def" ] || _om="$(git -C "$_r" rev-parse -q --verify "refs/remotes/origin/$_def^{commit}" 2>/dev/null)"
  if [ -z "$_h" ] || [ -z "$_om" ] || [ "$_h" != "$_om" ]; then
    V999_WHY="$_r HEAD ${_h:-none} is not origin/${_def:-?} ${_om:-none} ($_ctx)"; return 1
  fi
  if [ -n "$NINE_SETUP_SHA" ]; then
    case "$_h" in
      "$NINE_SETUP_SHA"*) ;;
      *) V999_WHY="$_r HEAD $_h is not the pinned 999-setup sha $NINE_SETUP_SHA ($_ctx)"; return 1 ;;
    esac
  fi
  V999_HEAD="$_h"
  return 0
}

# The installer's requirements, PROVED by executing them — the same probes its
# own preflight runs, so a failure is named here instead of halfway through
# provisioning.
check_999_prereqs() {
  _bad=""
  [ "$(uname -s)" = "Darwin" ] || _bad="$_bad os"
  [ "$(uname -m)" = "arm64" ] || _bad="$_bad arch"
  { command -v claude >/dev/null 2>&1 || [ -x "$HOME/.local/bin/claude" ]; } || _bad="$_bad claude"
  curl --version >/dev/null 2>&1 || _bad="$_bad curl"
  osascript -e '1+1' >/dev/null 2>&1 || _bad="$_bad osascript"
  shasum -a 256 /dev/null >/dev/null 2>&1 || _bad="$_bad shasum"
  tar --version >/dev/null 2>&1 || _bad="$_bad tar"
  security list-keychains >/dev/null 2>&1 || _bad="$_bad security"
  git --version >/dev/null 2>&1 || _bad="$_bad git"
  python3 --version >/dev/null 2>&1 || _bad="$_bad python3"
  xcode-select -p >/dev/null 2>&1 || _bad="$_bad command-line-tools"
  PREREQ_MISSING="${_bad# }"
  [ -z "$PREREQ_MISSING" ]
}

# ── env stores: find the box's OWN keys and plan names BY NAME ───────────────
# Presence only. Values are read exactly once, and only when the api-docs file
# has to be built — never printed, never echoed, never logged.

ENV_STORES=""
_add_store() {
  [ -n "$1" ] && [ -f "$1" ] && [ -r "$1" ] || return 0
  case "$ENV_STORES" in *"
$1"*) return 0 ;; esac
  ENV_STORES="$ENV_STORES
$1"
}
_add_store "$ROOT/secrets/.env"
_add_store "$ROOT/.env"
_add_store "$HOME/.openclaw/secrets/.env"
_add_store "$HOME/.openclaw/.env"
_add_store "/data/.openclaw/secrets/.env"
_add_store "/data/.openclaw/.env"
_add_store "$HOME/.openclaw/workspace/.env"
_add_store "$HOME/clawd/secrets/.env"
_add_store "$HOME/.openclaw/secrets.env"
for _f in "$ROOT"/secrets/*.env "$HOME/.openclaw"/secrets/*.env \
          "$HOME"/.openclaw/agents/*/agent/auth-profiles.json; do
  _add_store "$_f"
done
_add_store "$ROOT/openclaw.json"

ENV_STORE_COUNT=0
while IFS= read -r _f; do [ -n "$_f" ] && ENV_STORE_COUNT=$((ENV_STORE_COUNT + 1)); done <<EOF
$ENV_STORES
EOF
log "env stores searched: $ENV_STORE_COUNT (names only; no value is printed)"

# JSON stores are read by key name, recursively, with python3. Value never printed.
json_get() {  # file name mode(print|exists)
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys
path, name, mode = sys.argv[1], sys.argv[2], sys.argv[3]
def walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == name and v not in (None, ""):
                return v
            r = walk(v)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o:
            r = walk(v)
            if r is not None:
                return r
    return None
try:
    with open(path) as f:
        v = walk(json.load(f))
except Exception:
    sys.exit(1)
if v is None:
    sys.exit(1)
if mode == "exists":
    sys.exit(0)
if isinstance(v, (dict, list)):
    sys.exit(1)
sys.stdout.write(str(v))
PY
}

_name_in() {  # name -> 0 when present in any store; never prints the value
  while IFS= read -r _s; do
    [ -n "$_s" ] || continue
    case "$_s" in
      *.json) json_get "$_s" "$1" exists && return 0 ;;
      *) grep -Eq "^[[:space:]]*(export[[:space:]]+)?$1=" "$_s" 2>/dev/null && return 0 ;;
    esac
  done <<EOF
$ENV_STORES
EOF
  return 1
}

# name_present canonical-or-alias, presence only.
name_present() {
  _name_in "$1" && return 0
  case "$1" in
    OLLAMA_API_KEY) _name_in OLLAMA_CLOUD_API_KEY ;;
    AGNES_API_KEY)  _name_in AGNES_AI_API_KEY ;;
    *) return 1 ;;
  esac
}

# key_value NAME — prints the value on stdout. Caller captures it into a local
# and hands it straight to the 600 file. Callers must never log the result.
key_value() {
  while IFS= read -r _s; do
    [ -n "$_s" ] || continue
    case "$_s" in
      *.json) json_get "$_s" "$1" print && return 0 ;;
      *)
        _line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?$1=" "$_s" 2>/dev/null | head -1)"
        [ -n "$_line" ] || continue
        _line="${_line#*=}"
        _line="${_line%"${_line##*[! ]}"}"
        case "$_line" in
          \"*\") _line="${_line#\"}"; _line="${_line%\"}" ;;
          \'*\') _line="${_line#\'}"; _line="${_line%\'}" ;;
        esac
        printf '%s' "$_line"
        return 0 ;;
    esac
  done <<EOF
$ENV_STORES
EOF
  return 1
}

# canon_value canonical_name — canonical first, then its family alias.
canon_value() {
  _cv="$(key_value "$1")" || _cv=""
  if [ -n "$_cv" ]; then printf '%s' "$_cv"; return 0; fi
  case "$1" in
    OLLAMA_API_KEY) key_value OLLAMA_CLOUD_API_KEY ;;
    AGNES_API_KEY)  key_value AGNES_AI_API_KEY ;;
    *) return 1 ;;
  esac
}

FOUND_KEYS=""
for _n in $KEY_NAMES; do
  _name_in "$_n" && FOUND_KEYS="$FOUND_KEYS $_n"
done
FOUND_KEYS="${FOUND_KEYS# }"

FOUND_PLANS=""
for _n in $PLAN_NAMES; do
  _name_in "$_n" && FOUND_PLANS="$FOUND_PLANS $_n"
done
FOUND_PLANS="${FOUND_PLANS# }"

log "keys found by name: ${FOUND_KEYS:-none}"
log "plan names found: ${FOUND_PLANS:-none}"

if [ "$IS_MAC" = 1 ] && [ "$IS_DOCKER" = 0 ]; then

  log "STEP 999-setup"
  status_write "999-setup" "" ""
  NINE_RC=0
  NINE_OK=1

  # A fresh Mac has no checkout: clone 999 main FIRST (Trevor L14). Only when NO
  # checkout exists anywhere find_999 looks (CAN012: cloning ~/999-setup next to
  # a usable persist-home checkout made a second, divergent copy).
  NINE_REPO="$(find_999)" || NINE_REPO=""
  if [ -z "$NINE_REPO" ] && [ ! -e "$HOME/999-setup" ]; then
    if command -v git >/dev/null 2>&1; then
      log "999-setup: no $HOME/999-setup — cloning 999 main"
      GIT_TERMINAL_PROMPT=0 git clone --depth 1 https://github.com/trevorotts1/999-setup.git "$HOME/999-setup" >>"$LOG" 2>&1 </dev/null
      _crc=$?
      [ "$_crc" -eq 0 ] || { log "FAIL 999-setup: git clone exited $_crc"; NINE_RC=$EX_999; NINE_OK=0; }
    else
      log "FAIL 999-setup: git missing — cannot clone 999 main"
      NINE_RC=$EX_999; NINE_OK=0
    fi
    NINE_REPO="$(find_999)" || NINE_REPO=""
  fi

  if [ "$NINE_OK" = 1 ] && [ -z "$NINE_REPO" ]; then
    log "FAIL 999-setup: no 999 checkout with .claude/skills/nine-router-setup/scripts/setup-macos.sh (searched \$NINE_SETUP_REPO, <root>/persist-home, \$HOME/999-setup, \$HOME/Documents/999-setup, \$HOME/.claude-nine, skill links)"
    NINE_RC=$EX_999; NINE_OK=0
  fi
  [ -n "$NINE_REPO" ] && log "999 checkout: $NINE_REPO"

  # CAN012: the checkout the installer AND the 9router guards run from must be
  # origin/main (and the pin, when given). A stale branch is a loud failure here,
  # never a quiet success followed by yesterday's guard code.
  if [ "$NINE_OK" = 1 ]; then
    if sync_999 "$NINE_REPO"; then
      log "999-setup: checkout verified at origin/main ${V999_HEAD}"
    else
      log "FAIL 999-setup: checkout is not origin/main: $V999_WHY"
      NINE_RC=$EX_999; NINE_OK=0; STUCK_NOTE="999 checkout not at origin/main"
    fi
  fi

  if [ "$NINE_OK" = 1 ] && ! check_999_prereqs; then
    log "FAIL 999-setup: installer requirements not met: $PREREQ_MISSING"
    NINE_RC=$EX_999; NINE_OK=0
  fi

  # A box that already runs 9Router never takes the installer's full path — that
  # replaces the skill link and can rewire the router (shared-utils/lib-frontdoor.sh
  # and nine_router_guard.py both enforce this). Such a box gets --skills-only.
  NINE_MODE="full"
  if [ -d "$HOME/.9router" ] || [ -f "$HOME/.local/bin/claude-nine" ]; then
    NINE_MODE="skills-only"
    log "999-setup: 9Router detected — using --skills-only (never the full installer)"
  fi

  if [ "$NINE_OK" = 1 ] && [ "$NINE_MODE" = "full" ]; then
    # spec 4B.2 item 3: the installer needs one model key and one second key.
    if ! { { name_present OLLAMA_API_KEY || name_present OPENROUTER_API_KEY; } && \
           { name_present DEEPSEEK_API_KEY || name_present OPENROUTER_API_KEY; }; }; then
      log "FAIL 999-setup: no own keys for 999 (need OLLAMA or OPENROUTER, and DEEPSEEK or OPENROUTER)"
      NINE_RC=$EX_999; NINE_OK=0; STUCK_NOTE="no own keys for 999"
    fi
  fi

  if [ "$NINE_OK" = 1 ] && [ "$NINE_MODE" = "full" ]; then
    # Build the installer's credential file OUTSIDE the client's Documents, mode
    # 600, from the box's own stores, under CANONICAL names only (the installer's
    # parse_api_docs accepts OLLAMA_API_KEY / DEEPSEEK_API_KEY / AGNES_API_KEY /
    # OPENROUTER_API_KEY). Values go into this one file and nowhere else.
    umask 077
    mkdir -p "$API_DOCS_DIR" 2>/dev/null || { log "FAIL 999-setup: cannot create $API_DOCS_DIR"; NINE_RC=$EX_999; NINE_OK=0; }
    if [ "$NINE_OK" = 1 ]; then
      chmod 700 "$API_DOCS_DIR" 2>/dev/null || true
      API_TMP="$API_DOCS_FILE.tmp.$$"
      : > "$API_TMP" 2>/dev/null || { log "FAIL 999-setup: cannot write $API_TMP"; NINE_RC=$EX_999; NINE_OK=0; }
    fi
    if [ "$NINE_OK" = 1 ]; then
      WROTE=0
      for _n in $CANON_KEYS; do
        _v="$(canon_value "$_n")" || continue
        [ -n "$_v" ] || continue
        printf '%s=%s\n' "$_n" "$_v" >> "$API_TMP" 2>/dev/null || { log "FAIL 999-setup: write to $API_TMP failed"; NINE_RC=$EX_999; NINE_OK=0; break; }
        WROTE=$((WROTE + 1))
      done
      unset _v
      # Plan names are only written when they are one of the values the installer
      # validates; anything else would fail its own check later.
      _v="$(key_value OLLAMA_PLAN)"
      case "$_v" in
        free|pro|max) printf 'OLLAMA_PLAN=%s\n' "$_v" >> "$API_TMP" ;;
      esac
      _v="$(key_value AGNES_PLAN)"
      case "$_v" in
        starter|plus|pro) printf 'AGNES_PLAN=%s\n' "$_v" >> "$API_TMP" ;;
      esac
      unset _v
      if [ "$NINE_OK" = 1 ] && [ "$WROTE" -eq 0 ]; then
        rm -f "$API_TMP" 2>/dev/null
        log "FAIL 999-setup: no readable key values in the env stores"
        NINE_RC=$EX_999; NINE_OK=0; STUCK_NOTE="no own keys for 999"
      fi
      if [ "$NINE_OK" = 1 ]; then
        chmod 600 "$API_TMP" 2>/dev/null && mv -f "$API_TMP" "$API_DOCS_FILE" 2>/dev/null || {
          rm -f "$API_TMP" 2>/dev/null
          log "FAIL 999-setup: could not install $API_DOCS_FILE mode 600"
          NINE_RC=$EX_999; NINE_OK=0
        }
        [ "$NINE_OK" = 1 ] && log "999-setup: wrote $API_DOCS_FILE (mode 600, $WROTE credential name(s); the client's Documents file was not touched)"
      fi
    fi
  fi

  if [ "$NINE_OK" = 1 ]; then
    NINE_SCRIPT="$NINE_REPO/.claude/skills/nine-router-setup/scripts/setup-macos.sh"
    if [ "$NINE_MODE" = "full" ]; then
      NINE_API_DOCS="$API_DOCS_FILE" GIT_TERMINAL_PROMPT=0 GH_PROMPT_DISABLED=1 \
        bash "$NINE_SCRIPT" >>"$LOG" 2>&1 </dev/null
    else
      NINE_API_DOCS="$API_DOCS_FILE" GIT_TERMINAL_PROMPT=0 GH_PROMPT_DISABLED=1 \
        bash "$NINE_SCRIPT" --skills-only >>"$LOG" 2>&1 </dev/null
    fi
    NINE_RC=$?
    [ "$NINE_RC" -eq 0 ] || log "FAIL 999-setup: setup-macos.sh ($NINE_MODE) exited $NINE_RC"
  fi
  [ "$NINE_RC" -eq 0 ] && log "OK 999-setup ($NINE_MODE); gh_auth=PENDING"
  record_step "999-setup" "$NINE_RC"
  [ "$NINE_RC" -eq 0 ] || record_fail "$NINE_RC" "${STUCK_NOTE:-999-setup exited $NINE_RC}"

  # ══ step 2: 9Router upgrade to the pinned target ═══════════════════════════

  log "STEP 9router"
  status_write "9router" "" ""
  R9_RC=0
  GUARDS="$NINE_REPO/.claude/skills/nine-router-setup/scripts/macos/install-9router-guards.sh"
  # CAN012: never run guard code from a 999 checkout that step 1 did not verify,
  # or that moved since: a stale checkout gives a misleading pass or fail.
  if [ -z "$V999_HEAD" ] || [ "$(git -C "$NINE_REPO" rev-parse HEAD 2>/dev/null)" != "$V999_HEAD" ]; then
    log "REFUSED 9router: the 999 checkout (${NINE_REPO:-none}) is not at a verified origin/main HEAD (${V999_WHY:-HEAD changed after verification}); not running its guards"
    R9_RC=$EX_9ROUTER
  elif [ ! -f "$GUARDS" ]; then
    log "FAIL 9router: install-9router-guards.sh not found at $GUARDS"
    R9_RC=$EX_9ROUTER
  elif [ -z "$NINE9ROUTER_TARGET" ]; then
    log "REFUSED 9router: no pinned target (pass --9router-target VERSION or set NINEROUTER_TARGET); never upgrading to an unpinned latest"
    R9_RC=$EX_REFUSE
  else
    bash "$GUARDS" --upgrade "$NINE9ROUTER_TARGET" >>"$LOG" 2>&1 </dev/null
    R9_RC=$?
    [ "$R9_RC" -eq 0 ] || log "FAIL 9router: install-9router-guards.sh --upgrade $NINE9ROUTER_TARGET exited $R9_RC"
  fi
  [ "$R9_RC" -eq 0 ] && log "OK 9router: $NINE9ROUTER_TARGET"
  record_step "9router" "$R9_RC"
  [ "$R9_RC" -eq 0 ] || record_fail "$R9_RC" "9router exited $R9_RC"

else
  log "STEP 999-setup: skipped (not a macOS host)"
  record_step "999-setup" 0
  log "STEP 9router: skipped (not a macOS host)"
  record_step "9router" 0
fi

# ══ step 3: OpenClaw upgrade (Mac only) ══════════════════════════════════════
# The target version is the one the trigger passed. Nothing here discovers a
# version — a self-update that guesses its own destination is the defect the
# atomic upgrade exists to prevent.

if [ "$IS_DOCKER" = 1 ]; then
  log "STEP upgrade: skipped (/.dockerenv — the host side performed it)"
  record_step "upgrade" 0
else
  # spec 4A.2 item 1: let the trigger turn return before the gateway goes down.
  # ponytail: fixed 120 s wait for the trigger turn to return; upgrade path = poll the gateway session API
  if [ "$MODE_DETACHED" = 1 ] && [ -n "$LAUNCH_EPOCH" ]; then
    while [ $(( $(date +%s) - LAUNCH_EPOCH )) -lt 120 ]; do sleep 5; done
  fi
  log "STEP upgrade: OpenClaw -> $TARGET_VERSION"
  status_write "upgrade" "" ""
  UPG_RC=0
  if ! fetch "$REPO_RAW/scripts/oc-atomic-upgrade.sh" "$WORK/oc-atomic-upgrade.sh" \
     || ! fetch "$REPO_RAW/scripts/oc-schema-migrate.py" "$WORK/oc-schema-migrate.py" \
     || [ -z "$SUP_HELPER_PATH" ] || ! cp "$SUP_HELPER_PATH" "$WORK/oc-supervisor-install.py"; then
    log "FAIL upgrade: could not fetch oc-atomic-upgrade.sh / oc-schema-migrate.py / oc-supervisor-install.py from main"
    UPG_RC=$EX_UPGRADE
  else
    chmod 700 "$WORK/oc-atomic-upgrade.sh" 2>/dev/null || true
    bash "$WORK/oc-atomic-upgrade.sh" --upgrade --target-version "$TARGET_VERSION" >>"$LOG" 2>&1 </dev/null
    UPG_RC=$?
  fi
  record_step "upgrade" "$UPG_RC"
  if [ "$UPG_RC" -eq 70 ]; then
    log "FAIL upgrade: oc-atomic-upgrade.sh exited 70 — rollback failed, a human is needed"
    status_write "upgrade" "$(now_utc)" "upgrade exited 70 (rollback failed)"
    finish 20 "upgrade" "upgrade exited 70 (rollback failed)"
  fi
  if [ "$UPG_RC" -ne 0 ]; then
    log "FAIL upgrade: oc-atomic-upgrade.sh exited $UPG_RC"
    record_fail "$UPG_RC" "upgrade exited $UPG_RC"
  else
    log "OK upgrade: $TARGET_VERSION (the supervisor's install now reports $(oc_version))"
  fi
fi

# ══ step 4: content update ═══════════════════════════════════════════════════
# The same entry point the Sunday cron uses: fetched from the pinned onboarding
# ref (main when unpinned). It never restarts the gateway and never messages a
# client.

log "STEP update: weekly-full-update.sh"
status_write "update" "" ""

# F17: keep the config the content update may rewrite, so a rollback restores it.
CFG_BACKUP="$REFRESH_DIR/openclaw.json.pre-$RUN_ID"
if [ -f "$ROOT/openclaw.json" ]; then
  ( umask 077; cp "$ROOT/openclaw.json" "$CFG_BACKUP" ) 2>/dev/null && chmod 600 "$CFG_BACKUP" 2>/dev/null || CFG_BACKUP=""
fi

UPD_RC=0
if ! fetch "$REPO_RAW/scripts/weekly-full-update.sh" "$WORK/weekly-full-update.sh"; then
  log "FAIL update: could not fetch scripts/weekly-full-update.sh from main"
  UPD_RC=$EX_UPDATE
else
  bash "$WORK/weekly-full-update.sh" >>"$LOG" 2>&1 </dev/null
  UPD_RC=$?
fi
if [ "$UPD_RC" -eq 2 ]; then
  ROLLED_BACK=1
  if [ -n "$CFG_BACKUP" ] && [ -f "$CFG_BACKUP" ]; then
    cp "$CFG_BACKUP" "$ROOT/openclaw.json" 2>/dev/null && log "update: rolled back — restored $ROOT/openclaw.json from $CFG_BACKUP"
  fi
fi
record_step "update" "$UPD_RC"
if [ "$UPD_RC" -ne 0 ]; then
  log "FAIL update: weekly-full-update.sh exited $UPD_RC"
  record_fail "$UPD_RC" "update exited $UPD_RC"
else
  log "OK update"
fi

# ══ done ═════════════════════════════════════════════════════════════════════

if [ -n "$FIRST_FAIL" ]; then
  finish "$FIRST_FAIL" "done" "$STUCK_NOTE"
fi
finish "$EX_OK" "done" ""
