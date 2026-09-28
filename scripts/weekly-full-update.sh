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
# It runs from the roll's own copy of the onboarding repo (the same one the
# operator's roll uses, <OpenClaw root>/fleet-refresh/onboarding), cloned if
# absent and synced to origin/main first. If no copy can be made (no git / no
# network to GitHub), it falls back to the previous onboarding-only path
# (update-skills.sh) and says so.
#
# Never restarts the gateway, never sends a chat message.
# Exit: fleet-refresh.sh's exit code (0 ok, 2 rolled back / partial, 3 unknown).
# =============================================================================
set -uo pipefail

REPO_URL="${FLEET_ROLL_REPO_URL:-https://github.com/trevorotts1/openclaw-onboarding.git}"
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

# Never move the copy under a run that is already in progress (e.g. the
# operator's roll): its lock lives in the OpenClaw root.
for L in "${OPENCLAW_ROOT:-/nonexistent}" /data/.openclaw "$HOME/.openclaw"; do
  P="$(cat "$L/.fleet-refresh.lock/pid" 2>/dev/null)" && kill -0 "$P" 2>/dev/null && {
    log "another fleet-refresh (pid $P) is running on this box — nothing changed"; exit 0; }
done

# The roll's OWN copy of the onboarding repo, the same one the operator's roll
# keeps (scripts/fleet-roll-copy.sh, same steps): <OpenClaw root>/fleet-refresh/onboarding,
# refreshed to origin/main. The box's other clones are never used or changed.
# ONBOARDING_CLONE, when set, names an explicit clone to run from instead.
B="${OPENCLAW_ROOT:-}"
[ -n "$B" ] || { if [ -d /data/.openclaw ]; then B=/data/.openclaw; else B="$HOME/.openclaw"; fi; }
R="${ONBOARDING_CLONE:-$B/fleet-refresh/onboarding}"
if [ -z "${ONBOARDING_CLONE:-}" ] && [ -e "$R" ] && [ "$(git -C "$R" remote get-url origin 2>/dev/null)" != "$REPO_URL" ]; then
  rm -rf "$R"
fi
PREV="$(git -C "$R" rev-parse HEAD 2>/dev/null || true)"
if [ -d "$R/.git" ]; then
  if ! { git -C "$R" fetch -q --depth 1 origin +refs/heads/main:refs/remotes/origin/main \
         && git -C "$R" checkout -q -B main origin/main && git -C "$R" reset -q --hard origin/main; }; then
    log "ERROR: could not sync $R to origin/main — nothing was changed on this box"
    exit 1
  fi
elif ! { mkdir -p "$(dirname "$R")" && git clone -q --depth 1 --single-branch --branch main "$REPO_URL" "$R"; }; then
  log "WARNING: no usable onboarding copy (could not create $R) — falling back to update-skills.sh only (no 999, no health gate, no rollback)"
  tmp="$(mktemp "${TMPDIR:-/tmp}/openclaw-update-XXXXXX.sh")"
  trap 'rm -f "$tmp"' EXIT
  curl -fsSL --max-time 60 "$UPDATER_URL" -o "$tmp" || { log "ERROR: could not download update-skills.sh"; exit 1; }
  bash "$tmp"
  exit $?
fi
log "onboarding copy $R: ${PREV:0:12} -> $(git -C "$R" rev-parse --short=12 HEAD)"

export FLEET_PREV_ONBOARDING_SHA="$PREV"   # rollback target for the snapshot
exec bash "$R/scripts/fleet-refresh.sh" --local --apply
