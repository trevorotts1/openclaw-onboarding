#!/usr/bin/env bash
# fix-dual-cli.sh — remove the stale Hostinger image baseline openclaw CLI.
#
# v10.14.6 — Hostinger's hvps-openclaw:latest image pre-installs openclaw at
# /usr/local/bin/openclaw at image-build time. The runtime sets
# NPM_CONFIG_PREFIX=/data/.npm-global so later `npm install -g openclaw`
# calls put a newer version at /data/.npm-global/bin/openclaw. Result: dual
# install with version mismatch. PATH puts the new one first so shell-level
# `openclaw` calls are correct, but anything hardcoding /usr/local/bin or
# using npx with the wrong package cache hits the stale one and gets
# "protocol mismatch" rejected by the gateway. This silently breaks
# `openclaw cron create`, `openclaw message send`, and any skill that
# hardcodes /usr/local paths.
#
# install.sh v10.14.6+ auto-detect runs this cleanup automatically before
# the install starts. Use this script directly for POST-INSTALL clients
# (anyone whose install was on v10.14.5 or earlier and has the dual CLI).
#
# Usage (run from the HOST, NOT inside the container — needs docker access):
#   ./scripts/fix-dual-cli.sh <container-name>
#
# Example:
#   ./scripts/fix-dual-cli.sh openclaw-c54p-openclaw-1
#
# Or directly via docker exec from the host:
#   docker exec -u root <container> sh -c "$(curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/scripts/fix-dual-cli.sh)"

set -uo pipefail

CONTAINER="${1:-}"

# If invoked with no arg AND we're already inside a container (/data exists),
# operate directly. Otherwise, require the container name.
if [ -z "$CONTAINER" ] && [ -d /data ] && [ -e /usr/local/bin/openclaw -o -e /data/.npm-global/bin/openclaw ]; then
    # Direct in-container execution path
    OLD=/usr/local/bin/openclaw
    NEW=/data/.npm-global/bin/openclaw

    if [ ! -e "$OLD" ]; then
        echo "✓ No stale /usr/local CLI present — already clean."
        [ -e "$NEW" ] && "$NEW" --version 2>&1 | head -1
        exit 0
    fi

    if [ ! -e "$NEW" ]; then
        echo "⚠️  Only /usr/local CLI present (no /data/.npm-global). Skipping — would leave you without ANY openclaw CLI."
        exit 0
    fi

    OLD_VER=$("$OLD" --version 2>&1 | head -1)
    NEW_VER=$("$NEW" --version 2>&1 | head -1)

    if [ "$OLD_VER" = "$NEW_VER" ]; then
        echo "✓ Both CLIs at same version ($OLD_VER) — no cleanup needed."
        exit 0
    fi

    echo "Dual install detected:"
    echo "  STALE:   $OLD ($OLD_VER)"
    echo "  CURRENT: $NEW ($NEW_VER)"
    echo ""

    if [ "$(id -u)" != "0" ]; then
        echo "ERROR: Need root to remove /usr/local CLI. Re-run as:"
        echo "  docker exec -u root <container> bash /path/to/fix-dual-cli.sh"
        exit 1
    fi

    TS=$(date +%Y%m%d-%H%M%S)
    BAK=/data/.openclaw/backups/cli-cleanup-$TS
    mkdir -p "$BAK"
    cp -a "$OLD" "$BAK/openclaw.symlink" 2>/dev/null || true
    cp -a /usr/local/lib/node_modules/openclaw "$BAK/" 2>/dev/null || true
    echo "Backed up to: $BAK"

    rm -f "$OLD"
    rm -rf /usr/local/lib/node_modules/openclaw

    echo "✓ Removed $OLD and /usr/local/lib/node_modules/openclaw"
    echo ""
    echo "Active CLI:"
    which -a openclaw 2>&1 | sed 's/^/  /'
    openclaw --version 2>&1 | head -1 | sed 's/^/  /'
    exit 0
fi

# Host-side execution path — wrap the in-container fix
if [ -z "$CONTAINER" ]; then
    cat >&2 <<USAGE
Usage: $0 <container-name>

  Or run inside the container directly (with root) and the script will
  auto-detect that mode and operate on the local filesystem.

Find the container name with:
  docker ps | grep openclaw
USAGE
    exit 2
fi

if ! docker ps --format '{{.Names}}' | grep -qF "$CONTAINER"; then
    echo "ERROR: container '$CONTAINER' is not running." >&2
    echo "Available openclaw containers:" >&2
    docker ps --format '  {{.Names}}' | grep openclaw >&2 || echo '  (none)' >&2
    exit 1
fi

echo "Running cleanup inside container: $CONTAINER (as root)"
# Inline the in-container path via docker exec -u root
docker exec -u root "$CONTAINER" sh -c '
OLD=/usr/local/bin/openclaw
NEW=/data/.npm-global/bin/openclaw
if [ ! -e "$OLD" ]; then
    echo "✓ No stale /usr/local CLI present — already clean."
    [ -e "$NEW" ] && "$NEW" --version 2>&1 | head -1
    exit 0
fi
if [ ! -e "$NEW" ]; then
    echo "⚠️  Only /usr/local CLI present. Skipping."
    exit 0
fi
OLD_VER=$("$OLD" --version 2>&1 | head -1)
NEW_VER=$("$NEW" --version 2>&1 | head -1)
if [ "$OLD_VER" = "$NEW_VER" ]; then
    echo "✓ Both CLIs at same version — no cleanup needed."
    exit 0
fi
echo "Dual install detected:"
echo "  STALE:   $OLD ($OLD_VER)"
echo "  CURRENT: $NEW ($NEW_VER)"
TS=$(date +%Y%m%d-%H%M%S)
BAK=/data/.openclaw/backups/cli-cleanup-$TS
mkdir -p "$BAK"
cp -a "$OLD" "$BAK/openclaw.symlink" 2>/dev/null || true
cp -a /usr/local/lib/node_modules/openclaw "$BAK/" 2>/dev/null || true
rm -f "$OLD"
rm -rf /usr/local/lib/node_modules/openclaw
echo "✓ Removed stale CLI; backup at $BAK"
which -a openclaw 2>&1 | sed "s/^/  /"
openclaw --version 2>&1 | head -1 | sed "s/^/  /"
'
