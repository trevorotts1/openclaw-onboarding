#!/usr/bin/env bash
# =============================================================================
# weekly-full-update.sh — a box's own weekly update, identical to the operator's roll.
# =============================================================================
# Runs `scripts/fleet-refresh.sh --local --apply` from this box's onboarding
# clone, so the Sunday update does exactly what the operator's fleet roll does:
#   onboarding (update-skills.sh) + 999-setup (only if already installed)
#   + Command Center pull/build/restart (atomic-deploy.sh) + sessions.reset
#   + snapshot before / health gate after / automatic rollback on regression.
#
# Callers (both fetch this file from GitHub main, so every box runs the latest):
#   * the silent Sunday shell cron   (scripts/setup-weekly-update.sh)
#   * the Sunday agent cron, RULE 9 auto-apply and RULE 10 "install all" (cron-prompt.txt)
#
# The clone is found at the same paths fleet-refresh.sh probes over SSH (or
# ONBOARDING_CLONE), cloned there if absent, and synced to origin/main first.
# If no clone can be made (no git / no network to GitHub), it falls back to the
# previous onboarding-only path (update-skills.sh) and says so.
#
# Never restarts the gateway, never sends a chat message.
# Exit: fleet-refresh.sh's exit code (0 ok, 2 rolled back / partial, 3 unknown).
# =============================================================================
set -uo pipefail

REPO_URL="https://github.com/trevorotts1/openclaw-onboarding.git"
UPDATER_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh"

# cron runs with PATH=/usr/bin:/bin; openclaw, node, npm and pm2 live elsewhere.
# Without them sessions.reset and atomic-deploy.sh cannot run at all.
for d in "${OPENCLAW_ROOT:-/nonexistent}/npm-global/bin" /data/.openclaw/npm-global/bin \
         "$HOME/.openclaw/npm-global/bin" "$HOME/.npm-global/bin" "$HOME/.local/bin" \
         /usr/local/bin /opt/homebrew/bin; do
  [ -d "$d" ] && case ":$PATH:" in *":$d:"*) ;; *) PATH="$d:$PATH" ;; esac
done
export PATH

log() { echo "[weekly-full-update $(date '+%Y-%m-%d %H:%M:%S')] $*"; }

R=""
for d in "${ONBOARDING_CLONE:-}" "$HOME/.openclaw/skills/onboarding" "$HOME/clawd/openclaw-onboarding" \
         "$HOME/openclaw-onboarding" "$HOME/.openclaw/onboarding" \
         /data/clawd/openclaw-onboarding /data/openclaw-onboarding; do
  if [ -n "$d" ] && [ -f "$d/scripts/fleet-refresh.sh" ] && [ -d "$d/.git" ]; then R="$d"; break; fi
done
if [ -z "$R" ]; then
  if [ -d /data/.openclaw ]; then R=/data/openclaw-onboarding; else R="$HOME/clawd/openclaw-onboarding"; fi
  if [ -e "$R" ] || ! { mkdir -p "$(dirname "$R")" && git clone -q "$REPO_URL" "$R"; }; then
    log "WARNING: no usable onboarding clone (could not create $R) — falling back to update-skills.sh only (no 999, no health gate, no rollback)"
    tmp="$(mktemp "${TMPDIR:-/tmp}/openclaw-update-XXXXXX.sh")"
    trap 'rm -f "$tmp"' EXIT
    curl -fsSL --max-time 60 "$UPDATER_URL" -o "$tmp" || { log "ERROR: could not download update-skills.sh"; exit 1; }
    bash "$tmp"
    exit $?
  fi
  log "cloned onboarding to $R"
fi

PREV="$(git -C "$R" rev-parse HEAD 2>/dev/null || true)"
if ! { git -C "$R" fetch -q origin main && git -C "$R" reset -q --hard origin/main; }; then
  log "ERROR: could not sync $R to origin/main — nothing was changed on this box"
  exit 1
fi
log "onboarding clone $R: ${PREV:0:12} -> $(git -C "$R" rev-parse --short=12 HEAD)"

export FLEET_PREV_ONBOARDING_SHA="$PREV"   # rollback target for the snapshot
exec bash "$R/scripts/fleet-refresh.sh" --local --apply
