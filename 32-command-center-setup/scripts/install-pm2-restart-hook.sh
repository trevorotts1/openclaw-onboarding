#!/usr/bin/env bash
# install-pm2-restart-hook.sh — Mac native install — pm2 + launchd already
# handles persistence via `pm2 startup`; this script is no-op on Mac. For
# Hostinger Docker VPS only.
#
# The VPS variant of this script (in platform/vps/ of trevorotts1/openclaw-onboarding) adds
# a `command:` override to /docker/<project>/docker-compose.yml that backgrounds
# a 45-second delayed `pm2 resurrect` call so pm2's saved process list survives
# container restarts. On Mac, the host pm2 is managed by launchd and persists
# across reboots without any docker-compose hook, so this script intentionally
# does nothing and exits 0.
#
# Usage (on a Mac install — no-op):
#   ./install-pm2-restart-hook.sh
#
# Usage (on a Hostinger VPS — use the platform/vps version from the unified repo):
#   /data/.openclaw/skills/32-command-center-setup/scripts/install-pm2-restart-hook.sh /docker/<project>
set -euo pipefail

echo "[install-pm2-restart-hook] Mac native install detected — no-op."
echo "[install-pm2-restart-hook] pm2 + launchd already handles persistence via 'pm2 startup'."
echo "[install-pm2-restart-hook] If you intended to run this on a Hostinger Docker VPS, use the platform/vps version from the unified repo:"
echo "[install-pm2-restart-hook]   https://github.com/trevorotts1/openclaw-onboarding (platform/vps/ directory)"
exit 0
