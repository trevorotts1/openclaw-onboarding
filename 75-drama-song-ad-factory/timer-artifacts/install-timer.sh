#!/usr/bin/env bash
# install-timer.sh — render the Drama Studio bridge timer for one platform.
#
# U6: "Direct-shell persistent Mac/Hostinger/Contabo timer, no idle model event,
# correct user/paths and restart state" (joint plan section 5, row U6).
#
# WHAT IT DOES
#   Renders mac/com.blackceo.drama-studio-bridge.plist.template or
#   hostinger|contabo/drama-studio-timer.cron.template into the platform's
#   install path, and (with --apply) writes ONLY those files.
#
# WHAT IT NEVER DOES — the hard line
#   It NEVER registers anything: no `launchctl bootstrap/bootout/kickstart`, no
#   `crontab -`, no `systemctl`, no `pm2`, no Task Scheduler. It touches no
#   scheduling surface and installs/loads/enables nothing. The operator runs the
#   one registration command that --dry-run PRINTS; this script only prints it.
#   There is no code path here that arms a timer.
#
# MODES
#   --dry-run   (DEFAULT) render in memory, print the plan + the registration
#               command the OPERATOR would run, write nothing, exit 0.
#   --apply     write the rendered script + definition files under the target
#               root only. Still registers nothing.
#   --check-identity  validate a user/HOME pair against the platform contract and
#               exit 0 (ok) / 1 (wrong user or wrong path). Used by the checker.
#   --register  ALWAYS refused (exit 2): registration belongs to the operator on
#               the box, never to this repository script.
#
# Reuses the shape of platform/mac/service-selfheal/install-service-remediate.sh
# (sed-expanded template -> LaunchAgents plist) and of
# platform/vps/service-selfheal/install-host-watchdog-cron.sh (an idempotent
# `*/N ... /bin/sh <abs script> >> <log> 2>&1` crontab line).
#
# Usage:
#   bash install-timer.sh --platform mac [--dry-run|--apply] [--root DIR] [--home DIR]
#   bash install-timer.sh --platform hostinger --apply
#   bash install-timer.sh --platform contabo --dry-run
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
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
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

if [ "$MODE" = "register" ]; then
  echo "refused: this repository script never registers a timer." >&2
  echo "         Registration is a deliberate operator action on the box:" >&2
  case "$PLATFORM" in
    mac)       echo "           launchctl bootstrap gui/\$(id -u) $SEL_HOME/Library/LaunchAgents/com.blackceo.drama-studio-bridge.plist" >&2 ;;
    hostinger) echo "           docker exec -u node <container> sh -c 'crontab /data/.openclaw/scripts/drama-studio-timer.cron'" >&2 ;;
    contabo)   echo "           docker exec -u node <container> sh -c 'crontab /home/node/.openclaw/scripts/drama-studio-timer.cron'" >&2 ;;
  esac
  exit 2
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
    STORE_DIR="$SEL_HOME/$STATE_SUBPATH"
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

[ -f "$TEMPLATE" ] || { echo "template not found: $TEMPLATE" >&2; exit 1; }

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

# Registration command printed for the OPERATOR; never executed here.
reg_command() {
  case "$PLATFORM" in
    mac)       printf 'launchctl bootstrap gui/$(id -u) %s\n' "$DEST_PLIST" ;;
    hostinger) printf "docker exec -u node <container> sh -c 'crontab %s'\n" "$DEST_CRON" ;;
    contabo)   printf "docker exec -u node <container> sh -c 'crontab %s'\n" "$DEST_CRON" ;;
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
  echo "  operator registration command (NOT run by this script):"
  echo "    $(reg_command)"
  render >/dev/null
  exit 0
fi

# ---- --apply: write files ONLY. No scheduling surface, ever. ----------------
validate_identity "$SEL_USER" "$SEL_HOME" || exit 1

if [ "$PLATFORM" = "mac" ]; then
  mkdir -p "$(dirname "$DEST_PLIST")" "$(dirname "$LOG_PATH")" "$STORE_DIR"
  render > "$DEST_PLIST"
  chmod 644 "$DEST_PLIST"
  echo "wrote $DEST_PLIST"
else
  mkdir -p "$SCRIPTS_DIR" "$(dirname "$LOG_PATH")" "$STORE_DIR"
  cp "$HERE/run-timer.sh" "$DEST_SCRIPT"
  chmod 700 "$DEST_SCRIPT"
  render > "$DEST_CRON"
  chmod 600 "$DEST_CRON"
  echo "wrote $DEST_SCRIPT"
  echo "wrote $DEST_CRON"
fi
echo "files written. NOT registered. To register, the operator runs:"
echo "  $(reg_command)"
