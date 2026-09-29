#!/usr/bin/env bash
# install-startup-hook.sh -- run ON THE HOSTINGER HOST (root), once per box:
#
#   bash install-startup-hook.sh /docker/openclaw-<id>            # install
#   bash install-startup-hook.sh /docker/openclaw-<id> --check    # report only
#
# Makes the openclaw container resurrect pm2 (Command Center, GHL MCP, tunnels)
# whenever it is recreated. It copies container-startup.sh (beside this file)
# into the project's data volume and sets the openclaw service's compose
# `command:` to run it. The compose file is backed up first. A compose that
# already runs `pm2 resurrect` in its own command is left exactly as it is; a
# compose with some OTHER command is refused (merge it by hand).
#
# Nothing is restarted: the hook takes effect the next time the container is
# (re)created.
#
# Exit: 0 installed / already hooked (--check: hooked), 1 not hooked or failed, 2 usage.
set -uo pipefail

PROJECT="${1:-}"
MODE="${2:-install}"
[[ -n "$PROJECT" && -d "$PROJECT" ]] || { echo "usage: $0 /docker/<project> [--check]" >&2; exit 2; }
COMPOSE="$PROJECT/docker-compose.yml"
[[ -f "$COMPOSE" ]] || { echo "no $COMPOSE" >&2; exit 2; }
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/container-startup.sh"
HOOK_LINE='    command: ["bash", "/data/.openclaw/scripts/container-startup.sh"]'

if grep -q "pm2 resurrect\|/data/.openclaw/scripts/container-startup.sh" "$COMPOSE"; then
  echo "hooked: $COMPOSE already resurrects pm2 on start"
  exit 0
fi
if [[ "$MODE" == "--check" ]]; then
  echo "NOT hooked: $COMPOSE starts the container without pm2 resurrect"
  exit 1
fi
if grep -qE '^\s+command:' "$COMPOSE"; then
  echo "refused: $COMPOSE has a command: without pm2 resurrect; merge container-startup.sh into it by hand" >&2
  exit 1
fi
# The openclaw service is the one running Hostinger's image; its keys are
# indented four spaces, and `command:` goes right after its `image:` line.
if [[ "$(grep -cE '^    image: ghcr\.io/hostinger/hvps-openclaw' "$COMPOSE")" != "1" ]]; then
  echo "refused: cannot find exactly one hvps-openclaw service in $COMPOSE" >&2
  exit 1
fi

DATA="$PROJECT/data"
mkdir -p "$DATA/.openclaw/scripts" || exit 1
cp "$SRC" "$DATA/.openclaw/scripts/container-startup.sh" || exit 1
chown 1000:1000 "$DATA/.openclaw/scripts/container-startup.sh" 2>/dev/null || true

BACKUP="$COMPOSE.bak-startup-hook-$(date -u +%Y%m%dT%H%M%SZ)"
cp -p "$COMPOSE" "$BACKUP" || exit 1
awk -v hook="$HOOK_LINE" '{ print } /^    image: ghcr\.io\/hostinger\/hvps-openclaw/ { print hook }' "$BACKUP" > "$COMPOSE.tmp" \
  && mv "$COMPOSE.tmp" "$COMPOSE" || { cp -p "$BACKUP" "$COMPOSE"; exit 1; }
if command -v docker >/dev/null 2>&1 && ! (cd "$PROJECT" && docker compose config -q) 2>/dev/null; then
  cp -p "$BACKUP" "$COMPOSE"
  echo "refused: the edited compose did not validate; restored $BACKUP" >&2
  exit 1
fi
echo "installed: $COMPOSE runs container-startup.sh on start (backup: $BACKUP). Takes effect on the next container (re)create."
exit 0
