#!/usr/bin/env bash
# install-startup-hook.sh -- run ON THE HOSTINGER HOST (root), once per box:
#
#   bash install-startup-hook.sh /docker/openclaw-<id>            # install
#   bash install-startup-hook.sh /docker/openclaw-<id> --check    # report only
#
# Makes the openclaw container resurrect pm2 (Command Center and tunnels) whenever
# it is recreated. The RETIRED community GHL MCP is never restored: the startup
# script strips `ghl-community-mcp` out of dump.pm2 before the resurrect, and
# never runs the retired autostart. It copies container-startup.sh, the
# owner-heartbeat wait, the wrapper boot patcher and the apt reassert (all beside
# this file) into the project's data volume and sets the openclaw service's compose
# `command:` to run the startup script. The compose file is backed up first. A
# compose that already runs `pm2 resurrect` in its own command is left exactly as
# it is; a compose with some OTHER command is refused (merge it by hand).
#
# --check verifies EVERY hardening marker the roll's watch checks (agent-pull-watch.py
# HARDENING["vps"]), not just "pm2 resurrect": image pinned by digest, patcher wired
# in exactly one place, owner-heartbeat wait, npm prefix PATH/NODE_PATH, apt reassert,
# codex plugin absent, persistent entrypoint with its version gate, /data/.openclaw
# owned by node. A key that is not exactly 1 is RED - missing or unknown is never a
# pass - and --check exits 1. The marker probes below are deliberately a line-for-line
# mirror of the watch so the two can never disagree about a box.
#
# Nothing is restarted: the hook takes effect the next time the container is
# (re)created.
#
# Exit: install: 0 installed / already hooked, 1 refused or failed, 2 usage.
#       --check: 0 every marker is 1, 1 any marker is red, 2 usage.
set -uo pipefail

PROJECT="${1:-}"
MODE="${2:-install}"
[[ -n "$PROJECT" && -d "$PROJECT" ]] || { echo "usage: $0 /docker/<project> [--check]" >&2; exit 2; }
COMPOSE="$PROJECT/docker-compose.yml"
[[ -f "$COMPOSE" ]] || { echo "no $COMPOSE" >&2; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/container-startup.sh"
WAIT_SRC="$HERE/../wait-gateway-owner-stale.sh"
RA_SRC="$HERE/reassert-apt-deps.sh"
HWP_SRC="$HERE/hostinger-wrapper-patch.py"
HOOK_LINE='    command: ["bash", "/data/.openclaw/scripts/container-startup.sh"]'

DATA="$PROJECT/data"
HROOT="$DATA/.openclaw"
CS="$HROOT/scripts/container-startup.sh"

# ---------------------------------------------------------------- marker probes
# Mirrors agent-pull-watch.py:456-500 exactly. has/cnt are the watch's own helpers.
has() { grep -hsq -E "$1" $2 2>/dev/null && echo 1 || echo 0; }
cnt() { grep -hs -c -E "$1" $2 2>/dev/null | awk '{s+=$1} END {print s+0}'; }

container() {
  command -v docker >/dev/null 2>&1 || { echo ""; return; }
  local c
  c="$( cd "$PROJECT" && docker compose ps -q openclaw 2>/dev/null | head -n1 )"
  # A box whose service is not named `openclaw`: fall back to the one running container.
  [ -n "$c" ] || c="$( cd "$PROJECT" && docker compose ps -q 2>/dev/null | head -n1 )"
  printf '%s\n' "$c"
}

marker_report() {
  local CONTAINER W1 W2 P1 P2 RM OWN CX
  CONTAINER="$(container)"

  echo "H_IMG_DIGEST=$(grep -m1 -E '^[[:space:]]*image:' "$COMPOSE" 2>/dev/null | grep -c '@sha256:')"

  W1=$(cnt 'hostinger-wrapper-patch.py' "$COMPOSE"); W1=${W1:-0}
  W2=$(cnt 'hostinger-wrapper-patch.py' "$CS"); W2=${W2:-0}
  if [ "$W1" -ge 1 ] && [ "$W2" -ge 1 ]; then echo "H_WRAPPER=0"
  elif [ "$W1" -ge 1 ] || [ "$W2" -ge 1 ]; then echo "H_WRAPPER=1"
  else echo "H_WRAPPER=0"; fi

  echo "H_HEARTBEAT=$(has 'owner[-_]heartbeat' "$COMPOSE $CS")"

  P1=$(cnt 'PATH=/data/\.npm-global/bin' "$COMPOSE $CS")
  P2=$(cnt 'NODE_PATH=/data/\.npm-global/lib/node_modules' "$COMPOSE $CS")
  if [ "$P1" -ge 1 ] && [ "$P2" -ge 1 ]; then echo "H_NPM_PREFIX=1"; else echo "H_NPM_PREFIX=0"; fi

  echo "H_REASSERT=$(has 'reassert-apt-deps\.sh' "$COMPOSE $CS")"

  if [ -n "$CONTAINER" ]; then
    CX=$(docker exec -u node "$CONTAINER" sh -c 'ps -ef 2>/dev/null | grep -c "[c]odex app-server"' 2>/dev/null | head -n1)
    case "$CX" in
      0) echo "H_CODEX_ABSENT=1" ;;
      *) echo "H_CODEX_ABSENT=" ;;
    esac
    RM=$(docker exec "$CONTAINER" sh -c 'grep -c "rm -rf /data/.npm-global" /entrypoint.sh 2>/dev/null' 2>/dev/null | head -n1)
    case "$RM" in
      ''|*[!0-9]*) echo "H_PERSIST_ENTRYPOINT=" ;;
      0) echo "H_PERSIST_ENTRYPOINT=1" ;;
      *) echo "H_PERSIST_ENTRYPOINT=$(has 'entrypoint-persist|version-gate' "$COMPOSE $CS")" ;;
    esac
  else
    # No container: the image-entrypoint facts are unknown, and unknown is never a pass.
    echo "H_CODEX_ABSENT="
    echo "H_PERSIST_ENTRYPOINT="
  fi

  # The host has no user NAMED node for uid 1000, so ownership is compared by id.
  OWN=$(stat -c '%u:%g' "$HROOT" 2>/dev/null | head -n1)
  [ -z "$OWN" ] && OWN=$(stat -f '%u:%g' "$HROOT" 2>/dev/null | head -n1)
  case "$OWN" in
    1000:1000) echo "H_OWNER_NODE=1" ;;
    '') echo "H_OWNER_NODE=" ;;
    *) echo "H_OWNER_NODE=0" ;;
  esac
}

hardening_check() { # $1 = required exit message
  local out red=0 line
  out="$(marker_report)"
  while IFS= read -r line; do
    printf '%s\n' "$line"          # the raw KEY=value line, byte-identical to the watch probe
    case "$line" in
      *=1) printf '  PASS %s\n' "${line%%=*}" ;;
      *=0) printf '  RED  %s (present but wrong)\n' "${line%%=*}"; red=1 ;;
      *)   printf '  RED  %s (missing or unknown - never a pass)\n' "${line%%=*}"; red=1 ;;
    esac
  done <<< "$out"
  if [ "$red" = 0 ]; then
    echo "hardening: every marker is 1"
    return 0
  fi
  echo "hardening: $1" >&2
  return 1
}

if grep -q "pm2 resurrect\|/data/.openclaw/scripts/container-startup.sh" "$COMPOSE"; then
  HOOKED=1
else
  HOOKED=0
fi

if [[ "$MODE" == "--check" ]]; then
  if [ "$HOOKED" = 1 ]; then
    echo "hooked: $COMPOSE runs the start-up hook"
  else
    echo "NOT hooked: $COMPOSE starts the container without pm2 resurrect"
  fi
  hardening_check "not every hardening marker is 1; the roll's watch will read this box OPERATOR-FIRST (Mode A)"
  exit $?
fi

if [[ "$MODE" != "install" ]]; then
  echo "usage: $0 /docker/<project> [--check]" >&2; exit 2
fi

if [ "$HOOKED" = 0 ]; then
  if grep -qE '^[[:space:]]+command:' "$COMPOSE"; then
    echo "refused: $COMPOSE has a command: without pm2 resurrect; merge container-startup.sh into it by hand" >&2
    exit 1
  fi
  # The openclaw service is the one running Hostinger's image; its keys are
  # indented four spaces, and `command:` goes right after its `image:` line.
  if [[ "$(grep -cE '^    image: ghcr\.io/hostinger/hvps-openclaw' "$COMPOSE")" != "1" ]]; then
    echo "refused: cannot find exactly one hvps-openclaw service in $COMPOSE" >&2
    exit 1
  fi
  BACKUP="$COMPOSE.bak-startup-hook-$(date -u +%Y%m%dT%H%M%SZ)"
  cp -p "$COMPOSE" "$BACKUP" || exit 1
  awk -v hook="$HOOK_LINE" '{ print } /^    image: ghcr\.io\/hostinger\/hvps-openclaw/ { print hook }' "$BACKUP" > "$COMPOSE.tmp" \
    && mv "$COMPOSE.tmp" "$COMPOSE" || { cp -p "$BACKUP" "$COMPOSE"; exit 1; }
  if command -v docker >/dev/null 2>&1 && ! (cd "$PROJECT" && docker compose config -q) 2>/dev/null; then
    cp -p "$BACKUP" "$COMPOSE"
    echo "refused: the edited compose did not validate; restored $BACKUP" >&2
    exit 1
  fi
else
  echo "hooked: $COMPOSE already resurrects pm2 on start"
fi

# The scripts container-startup.sh calls if present: the owner-heartbeat wait, the
# wrapper boot patcher and the apt reassert. Ownership 1000:1000 so the node user can
# read and run them; the patcher's known-good copy and its SHA-256 stay per-box.
mkdir -p "$HROOT/scripts" || exit 1
for _f in "$SRC" "$WAIT_SRC" "$HWP_SRC" "$RA_SRC"; do
  [ -f "$_f" ] || { echo "refused: missing $_f beside this installer" >&2; exit 1; }
  _n="$(basename "$_f")"
  cp "$_f" "$HROOT/scripts/$_n" && chmod 755 "$HROOT/scripts/$_n" || exit 1
  chown 1000:1000 "$HROOT/scripts/$_n" 2>/dev/null || true
done

echo "installed: $COMPOSE runs container-startup.sh on start. Takes effect on the next container (re)create."
if [ -n "${BACKUP:-}" ]; then echo "backup: $BACKUP"; fi
# The patcher stops the boot unless it can prove a safe result, and the ONLY other
# accepted proof is a known-good copy whose recorded SHA-256 it can check. Record it
# before the next recreate (docker-persistence.md D4 step 2) or the box stays down.
echo "NOTE: record the patched wrapper's SHA-256 as KNOWN_GOOD_SHA256 on this box (docker-persistence.md D4 step 2); without it a failed patch STOPS the boot by design."
echo "hardening report for this box:"
hardening_check "advisory only on install - fix these before the next roll" || true
exit 0
