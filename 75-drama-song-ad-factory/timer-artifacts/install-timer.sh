#!/usr/bin/env bash
# install-timer.sh — render the Drama Studio bridge timer for one platform.
#
# U6: "Direct-shell persistent Mac/Hostinger/Contabo timer, no idle model event,
# correct user/paths and restart state" (joint plan section 5, row U6).
#
# WHAT IT DOES
#   Renders mac/com.blackceo.drama-studio-bridge.plist.template or
#   hostinger|contabo/drama-studio-timer.cron.template into the platform's
#   install path, and (with --apply) writes ONLY those files. With --register it
#   also ARMS the scheduler: the Mac LaunchAgent is loaded with `launchctl
#   bootstrap`, and the Hostinger/Contabo crontab gains exactly one tagged
#   `*/2 ... /bin/sh <abs script> >> <log> 2>&1` line (any previous tagged line
#   is removed first, so a second run cannot double the timer).
#
# WHAT IT NEVER DOES — the hard line
#   Every mode except --register touches no scheduling surface at all: no
#   `launchctl`, no `crontab -`, no `systemctl`, no `pm2`, no Task Scheduler, no
#   sudo. --register is check-first and idempotent: when the timer is already
#   installed and correct it changes nothing and exits 0. It never arms a
#   scratch/fixture install either — pass --root a directory that is NOT the
#   platform's contract root and --register writes the files, PRINTS the
#   scheduler command and arms nothing. That is how this is proven without
#   spending a launchd slot or a container: fixtures first, never a bare install.
#
# MODES
#   --dry-run   (DEFAULT) render in memory, print the plan + the registration
#               command, write nothing, exit 0.
#   --apply     write the rendered script + definition files under the target
#               root only. Registers nothing.
#   --check-identity  validate a user/HOME pair against the platform contract and
#               exit 0 (ok) / 1 (wrong user or wrong path). Used by the checker.
#   --register  install the timer AND arm it. exit 0 when the timer is installed
#               or already installed; exit 2 only for a genuine refusal (wrong
#               identity, unsupported platform, missing template). It keeps
#               accepting --platform and the existing --root/--home/--skill-root/
#               --identity-user/--identity-home.
#
# Reuses the shape of platform/mac/service-selfheal/install-service-remediate.sh
# (sed-expanded template -> launchctl bootstrap, already-loaded = success) and of
# platform/vps/service-selfheal/install-host-watchdog-cron.sh (an idempotent
# `*/N ... /bin/sh <abs script> >> <log> 2>&1` crontab line, old line replaced).
#
# Usage:
#   bash install-timer.sh --platform mac [--dry-run|--apply] [--root DIR] [--home DIR]
#   bash install-timer.sh --platform hostinger --apply
#   bash install-timer.sh --platform contabo --dry-run
#   bash install-timer.sh --platform mac --register
#   bash install-timer.sh --platform mac --check-identity --identity-user U --identity-home H
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PLATFORM=""
MODE="dry-run"
ROOT=""
HOME_OVR=""
SKILL_ROOT=""
ID_USER=""
ID_HOME=""

while [ $# -gt 0 ]; do
  case "$1" in
    --platform) PLATFORM="${2:-}"; shift 2 ;;
    --dry-run)  MODE="dry-run"; shift ;;
    --apply)    MODE="apply"; shift ;;
    --register) MODE="register"; shift ;;
    --check-identity) MODE="check-identity"; shift ;;
    --root)     ROOT="${2:-}"; shift 2 ;;
    --home)     HOME_OVR="${2:-}"; shift 2 ;;
    --skill-root) SKILL_ROOT="${2:-}"; shift 2 ;;
    --identity-user) ID_USER="${2:-}"; shift 2 ;;
    --identity-home) ID_HOME="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,49p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

[ -n "$PLATFORM" ] || { echo "usage: $0 --platform mac|hostinger|contabo [mode]" >&2; exit 2; }

# ---- platform contract (v0) -------------------------------------------------
# The user and the persistent roots, verbatim from the joint plan section 1
# ("Runtime user", "Persistent state") and section 3.13. Mac state is under the
# client HOME; Hostinger HOME is persistent /data; Contabo HOME is the EPHEMERAL
# container layer, so its persistent root is /home/node/.openclaw.
case "$PLATFORM" in
  mac)
    DEF_USER="$(id -un)"; DEF_HOME="/Users/$(id -un)"; DEF_ROOT="$DEF_HOME"
    HOME_RE='^/Users/[A-Za-z0-9._-]+$'; STATE_SUBPATH=".drama-studio"
    ;;
  hostinger)
    DEF_USER="node"; DEF_HOME="/data"; DEF_ROOT="/data"
    HOME_RE='^/data$'; STATE_SUBPATH=".drama-studio"
    ;;
  contabo)
    DEF_USER="node"; DEF_HOME="/home/node"; DEF_ROOT="/home/node/.openclaw"
    HOME_RE='^/home/node$'; STATE_SUBPATH=".drama-studio"
    ;;
  *) echo "unknown platform '$PLATFORM' (mac|hostinger|contabo)" >&2; exit 2 ;;
esac

SEL_USER="${ID_USER:-${USER:-$DEF_USER}}"
SEL_HOME="${ID_HOME:-${HOME_OVR:-$DEF_HOME}}"
SEL_ROOT="${ROOT:-$DEF_ROOT}"

# ---- identity / path validation (shared by --check-identity and every write) -
validate_identity() {
  local u="$1" h="$2" bad=0
  case "$h" in
    /tmp/*|/var/tmp/*|/private/tmp/*) echo "refused: HOME '$h' is a temp path (not persistent)" >&2; bad=1 ;;
  esac
  # `[[ =~ ]]`, not `printf | grep -q`: under `set -o pipefail` a `grep -q` that
  # matches and exits early sends SIGPIPE to printf and fails the pipeline — the
  # exact false-refusal trap this repo's installers guard against.
  if ! [[ "$h" =~ $HOME_RE ]]; then
    echo "refused: HOME '$h' does not match $PLATFORM contract ($HOME_RE)" >&2; bad=1
  fi
  case "$PLATFORM" in
    mac)
      [ "$u" = "$(id -un)" ] || { echo "refused: user '$u' is not the login user '$(id -un)'" >&2; bad=1; }
      [ "${h##*/}" = "$u" ] || { echo "refused: HOME leaf '${h##*/}' != user '$u'" >&2; bad=1; }
      ;;
    hostinger|contabo)
      [ "$u" = "node" ] || { echo "refused: $PLATFORM must run as 'node', got '$u'" >&2; bad=1; }
      ;;
  esac
  return "$bad"
}

if [ "$MODE" = "check-identity" ]; then
  if validate_identity "$SEL_USER" "$SEL_HOME"; then
    echo "identity ok: platform=$PLATFORM user=$SEL_USER home=$SEL_HOME"
    exit 0
  fi
  exit 1
fi

# ---- resolve paths ----------------------------------------------------------
case "$PLATFORM" in
  mac)
    # Paths derive from the install ROOT (defaults to HOME). Real installs use
    # root == home; a scratch test can point root elsewhere while HOME (the
    # identity) stays the real one.
    DEST_PLIST="$SEL_ROOT/Library/LaunchAgents/com.blackceo.drama-studio-bridge.plist"
    TEMPLATE="$HERE/mac/com.blackceo.drama-studio-bridge.plist.template"
    STORE_DIR="$SEL_ROOT/$STATE_SUBPATH"
    LOG_PATH="$SEL_ROOT/Library/Logs/openclaw/drama-studio-timer.log"
    SKILL="${SKILL_ROOT:-$SEL_ROOT/.openclaw/skills/75-drama-song-ad-factory}"
    SCRIPT_PATH="$SKILL/timer-artifacts/run-timer.sh"
    PATH_VAL="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
    INTERVAL=120
    SCHEDULE=""
    DEST_SCRIPT=""
    ;;
  hostinger)
    SCRIPTS_DIR="$SEL_ROOT/.openclaw/scripts"
    DEST_SCRIPT="$SCRIPTS_DIR/run-timer.sh"
    DEST_CRON="$SCRIPTS_DIR/drama-studio-timer.cron"
    TEMPLATE="$HERE/hostinger/drama-studio-timer.cron.template"
    # Root-derived, like mac and contabo: with the contract root (/data) this is
    # exactly $SEL_HOME/.drama-studio, so a real install is unchanged; a scratch
    # --root keeps every fixture write inside that scratch.
    STORE_DIR="$SEL_ROOT/$STATE_SUBPATH"
    LOG_PATH="$SEL_ROOT/.openclaw/logs/drama-studio-timer.log"
    SCRIPT_PATH="$DEST_SCRIPT"
    PATH_VAL="/data/.npm-global/bin:/data/linuxbrew/.linuxbrew/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    SCHEDULE="*/2 * * * *"
    ;;
  contabo)
    SCRIPTS_DIR="$SEL_ROOT/scripts"
    DEST_SCRIPT="$SCRIPTS_DIR/run-timer.sh"
    DEST_CRON="$SCRIPTS_DIR/drama-studio-timer.cron"
    TEMPLATE="$HERE/contabo/drama-studio-timer.cron.template"
    STORE_DIR="$SEL_ROOT/$STATE_SUBPATH"
    LOG_PATH="$SEL_ROOT/logs/drama-studio-timer.log"
    SCRIPT_PATH="$DEST_SCRIPT"
    PATH_VAL="/home/node/.openclaw/npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    SCHEDULE="*/2 * * * *"
    ;;
esac

if [ ! -f "$TEMPLATE" ]; then
  echo "template not found: $TEMPLATE" >&2
  # A missing template is a genuine --register refusal (exit 2); the other modes
  # keep their historical exit 1.
  if [ "$MODE" = "register" ]; then exit 2; fi
  exit 1
fi

render() {
  sed -e "s|__SCRIPT_PATH__|${SCRIPT_PATH}|g" \
      -e "s|__LOG_PATH__|${LOG_PATH}|g" \
      -e "s|__HOME__|${SEL_HOME}|g" \
      -e "s|__USER__|${SEL_USER}|g" \
      -e "s|__PATH__|${PATH_VAL}|g" \
      -e "s|__STORE_DIR__|${STORE_DIR}|g" \
      -e "s|__INTERVAL__|${INTERVAL:-120}|g" \
      -e "s|__SCHEDULE__|${SCHEDULE}|g" \
      "$TEMPLATE"
}

# The single executable line of a rendered crontab definition: every comment and
# blank line in the template is documentation, the last remaining line is the job.
cron_definition_line() {
  printf '%s\n' "$1" | sed -e '/^[[:space:]]*#/d' -e '/^[[:space:]]*$/d' | tail -1
}

# The current crontab exactly as the register step sees it. In a fixture root the
# file under that root stands in for `crontab -l`, so proving idempotency never
# reads, writes or clobbers a real crontab.
cron_get() {
  if [ "$FIXTURE" = 1 ]; then
    cat "$CRONTAB_FIXTURE" 2>/dev/null || true
  else
    crontab -l 2>/dev/null || true
  fi
}

RENDERED="$(render)"

# Registration entry point for the platform. `--register` runs the scheduler
# step itself; this is what the operator is shown for a manual arm.
reg_command() {
  case "$PLATFORM" in
    mac) printf 'launchctl bootstrap gui/$(id -u) %s\n' "$DEST_PLIST" ;;
    *)   printf 'bash %s --platform %s --register\n' "$HERE/install-timer.sh" "$PLATFORM" ;;
  esac
}

if [ "$MODE" = "dry-run" ]; then
  # Validate the identity the operator WILL run under, but write nothing.
  if ! validate_identity "$SEL_USER" "$SEL_HOME"; then
    echo "dry-run: identity refused (see above); nothing written" >&2
    exit 1
  fi
  echo "DRY RUN — nothing written, nothing registered."
  echo "  platform : $PLATFORM"
  echo "  user     : $SEL_USER"
  echo "  home     : $SEL_HOME"
  echo "  state    : $STORE_DIR  (persistent)"
  case "$PLATFORM" in
    mac)
      echo "  install  : $DEST_PLIST"
      echo "  script   : $SCRIPT_PATH  (ships with the skill; not copied)"
      ;;
    *)
      echo "  install  : $DEST_CRON"
      echo "  script   : $DEST_SCRIPT"
      ;;
  esac
  echo "  log      : $LOG_PATH"
  echo "  direct   : /bin/sh $SCRIPT_PATH  (no model, no interactive session)"
  echo "  register with (this dry run arms nothing):"
  echo "    $(reg_command)"
  if [ "$PLATFORM" = "mac" ]; then
    echo "  rendered plist:"
    printf '%s\n' "$RENDERED" | sed -e 's/^/    /'
  else
    echo "  rendered crontab line:"
    printf '    %s\n' "$(cron_definition_line "$RENDERED")"
  fi
  exit 0
fi

# ---- identity gate for every write ------------------------------------------
if [ "$MODE" = "register" ]; then
  if ! validate_identity "$SEL_USER" "$SEL_HOME"; then
    echo "refused: --register needs a valid $PLATFORM identity (see above)" >&2
    exit 2
  fi
else
  validate_identity "$SEL_USER" "$SEL_HOME" || exit 1
fi

# ---- write the definition files (shared by --apply and --register) ----------
# CHANGED=0 means every file on disk was already byte-identical: that is what
# makes a second run a no-op instead of a rewrite.
CHANGED=0
put_file() {  # put_file <path> <mode> <content>
  if [ -f "$1" ] && [ "$(cat "$1")" = "$3" ]; then
    echo "unchanged $1"
    return 0
  fi
  mkdir -p "$(dirname "$1")"
  printf '%s\n' "$3" > "$1"
  chmod "$2" "$1"
  echo "wrote $1"
  CHANGED=1
}

mkdir -p "$(dirname "$LOG_PATH")" "$STORE_DIR"
if [ "$PLATFORM" = "mac" ]; then
  put_file "$DEST_PLIST" 644 "$RENDERED"
else
  mkdir -p "$SCRIPTS_DIR"
  if cmp -s "$HERE/run-timer.sh" "$DEST_SCRIPT" 2>/dev/null; then
    echo "unchanged $DEST_SCRIPT"
  else
    cp "$HERE/run-timer.sh" "$DEST_SCRIPT"
    chmod 700 "$DEST_SCRIPT"
    echo "wrote $DEST_SCRIPT"
    CHANGED=1
  fi
  put_file "$DEST_CRON" 600 "$RENDERED"
fi

if [ "$MODE" != "register" ]; then
  echo "files written. NOT registered. To register, run:"
  echo "  $(reg_command)"
  exit 0
fi

# ---- --register: arm the scheduler. Check-first, idempotent. ----------------
# A root that is not the platform's contract root is a scratch/fixture install:
# write the files, PRINT the scheduler command, arm nothing. A real box never
# passes --root at all (or passes its own contract root), so it arms normally.
if [ "$SEL_ROOT" != "$DEF_ROOT" ]; then
  FIXTURE=1
  echo "fixture root: '$SEL_ROOT' is not the $PLATFORM contract root '$DEF_ROOT'."
  echo "  files written; the scheduler command below is PRINTED, not executed."
else
  FIXTURE=0
fi

if [ "$PLATFORM" = "mac" ]; then
  LABEL="com.blackceo.drama-studio-bridge"
  GUI="gui/$(id -u)"
  BOOTSTRAP="launchctl bootstrap $GUI $DEST_PLIST"
  if [ "$FIXTURE" = 1 ]; then
    if [ "$CHANGED" = 0 ]; then
      echo "already installed: $DEST_PLIST already holds the rendered definition."
    else
      echo "installed $DEST_PLIST"
    fi
    echo "  nothing loaded here; to arm it on the real box: $BOOTSTRAP"
    exit 0
  fi
  if launchctl print "$GUI/$LABEL" >/dev/null 2>&1; then
    if [ "$CHANGED" = 0 ]; then
      echo "already installed and loaded: $LABEL"
      exit 0
    fi
    echo "definition changed; re-loading $LABEL"
    launchctl bootout "$GUI/$LABEL" 2>/dev/null || true
  fi
  # An already-loaded job is success (the pre-check above races with nothing, but
  # launchctl itself can report the same condition) — install-service-remediate.sh
  # treats a loaded job as the target state too.
  if launchctl bootstrap "$GUI" "$DEST_PLIST"; then
    echo "loaded $LABEL"
    exit 0
  fi
  if launchctl print "$GUI/$LABEL" >/dev/null 2>&1; then
    echo "already loaded: $LABEL"
    exit 0
  fi
  echo "refused: launchctl bootstrap failed for $DEST_PLIST" >&2
  exit 2
fi

# ---- Hostinger / Contabo: one tagged, de-duplicated crontab line ------------
CRON_TAG="drama-studio-timer"
CRON_LINE="$(cron_definition_line "$RENDERED")"
[ -n "$CRON_LINE" ] || { echo "refused: rendered definition has no executable line" >&2; exit 2; }
CRONTAB_FIXTURE="$SCRIPTS_DIR/.crontab-installed"

if [ "$FIXTURE" = 0 ]; then
  command -v crontab >/dev/null 2>&1 || { echo "refused: crontab not found on this $PLATFORM install" >&2; exit 2; }
fi

CURRENT="$(cron_get)"
if [ -n "$CURRENT" ]; then
  # Drop every previous line that belongs to this timer, then re-append ours, so
  # a second run can never double the timer. `|| true` because grep exits 1 when
  # it filters out EVERY line, which under `set -o pipefail` would abort here.
  KEPT="$(printf '%s\n' "$CURRENT" | grep -vF "$CRON_TAG" || true)"
else
  KEPT=""
fi
if [ -n "$KEPT" ]; then
  # $'...' because $(printf ...) would strip the trailing newline and glue the
  # two jobs onto one line — which is exactly how a merge goes wrong.
  DESIRED="$KEPT"$'\n'"$CRON_LINE"
else
  DESIRED="$CRON_LINE"
fi

if [ "$DESIRED" = "$CURRENT" ]; then
  echo "already installed: the '$CRON_TAG' crontab entry is present exactly once."
  echo "  nothing changed."
  exit 0
fi

if [ "$FIXTURE" = 1 ]; then
  printf '%s\n' "$DESIRED" > "$CRONTAB_FIXTURE"
  echo "installed $CRONTAB_FIXTURE (fixture stand-in for the node user's crontab)."
else
  printf '%s\n' "$DESIRED" | crontab -
  echo "installed the '$CRON_TAG' crontab entry for user '$SEL_USER'."
fi
echo "  scheduled line:"
printf '    %s\n' "$CRON_LINE"
exit 0
