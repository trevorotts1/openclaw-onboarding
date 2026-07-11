#!/usr/bin/env bash
# =============================================================================
# RESCUE RANGERS :: install-rescue-ledger.sh
# Installs the durable ticket ledger + tooling onto the OPERATOR Mac.
# (Topic-4 FIX 4-A install leg — runnable script; EXECUTION IS DEFERRED to the
#  operator. Repo-side only, this file is never auto-run by onboarding.)
# -----------------------------------------------------------------------------
# WHAT IT DOES (idempotent, safe to re-run):
#   1. Creates the rescue state dir   ~/clawd/fleet-heartbeat/rescue  (0700).
#   2. Copies rescue_ledger.py, rescue_cc_board.py, migrate-rescue-staticdata.py,
#      relay_brain_validation.js into that dir (the department's runtime tools).
#   3. Bootstraps the SQLite schema   (rescue_ledger.py init).
#   4. OPTIONAL migration from a supplied n8n staticData export (--migrate FILE).
#   5. Prints the two DEFERRED live steps it does NOT perform (n8n redeploy;
#      VPS status-poll return-leg wiring) so the operator sees exactly what is left.
#
# IT NEVER: touches n8n, any VPS, any client box, or any GHL account; installs a
# cron; arms anything. Move in silence — operator-verbose, no client output.
#
# USAGE (operator Mac, as the box user — NOT root):
#   bash install-rescue-ledger.sh [--state-dir DIR] [--migrate STATICDATA.json] [--dry-run]
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${RESCUE_STATE_DIR:-$HOME/clawd/fleet-heartbeat/rescue}"
MIGRATE_FILE=""
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --state-dir) STATE_DIR="$2"; shift 2 ;;
    --migrate)   MIGRATE_FILE="$2"; shift 2 ;;
    --dry-run)   DRY_RUN=1; shift ;;
    -h|--help)   sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ "$(id -u)" = "0" ]; then
  echo "REFUSING to install as root — a root-owned file under the rescue dir can" >&2
  echo "wedge the operator toolchain. Re-run as the box user." >&2
  exit 1
fi

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then echo "python3 not found on PATH" >&2; exit 1; fi

TOOLS=(rescue_ledger.py rescue_cc_board.py migrate-rescue-staticdata.py relay_brain_validation.js)

echo "[install-rescue-ledger] state dir: $STATE_DIR"
if [ "$DRY_RUN" = "1" ]; then
  echo "[install-rescue-ledger] DRY-RUN — would create $STATE_DIR and copy: ${TOOLS[*]}"
else
  mkdir -p "$STATE_DIR"
  chmod 700 "$STATE_DIR" 2>/dev/null || true
  for t in "${TOOLS[@]}"; do
    cp -f "$HERE/$t" "$STATE_DIR/$t"
  done
  echo "[install-rescue-ledger] copied ${#TOOLS[@]} tool(s) into $STATE_DIR"
  "$PY" "$STATE_DIR/rescue_ledger.py" --state-dir "$STATE_DIR" init
fi

if [ -n "$MIGRATE_FILE" ]; then
  if [ ! -f "$MIGRATE_FILE" ]; then
    echo "[install-rescue-ledger] --migrate file not found: $MIGRATE_FILE" >&2
    exit 2
  fi
  echo "[install-rescue-ledger] migrating staticData export: $MIGRATE_FILE"
  DR_FLAG=""; [ "$DRY_RUN" = "1" ] && DR_FLAG="--dry-run"
  "$PY" "$HERE/migrate-rescue-staticdata.py" --export "$MIGRATE_FILE" \
        --state-dir "$STATE_DIR" $DR_FLAG
fi

cat <<'DEFERRED'

[install-rescue-ledger] DONE. LIVE steps remain (DEFERRED — operator action):
  1. n8n Relay Brain redeploy — paste relay_brain_validation.js into the Relay
     Brain Code node (nine-field enforcement + status branch). Pre-change JSON
     export ritual + staging test FIRST. See RELAY-BRAIN-PATCH.md.
  2. VPS outbound-only status-poll return leg — arm the client AGENTS.md
     {action:"status", ticketId} poll on live VPS boxes (fleet rollout, batched).
  3. Command Center department — register the board column/topic once:
       bash 32-command-center-setup/scripts/add-department.sh rescue-rangers
     (runtime parity guard: guard-department-runtime-parity.py). The board caller
     (rescue_cc_board.py) is already fail-soft; this only creates the column.
  4. Aging/SLA cron — schedule the aging sweep beside the CC stale-task sweep, e.g.
     */30 min: rescue_ledger.py aging --older-than-minutes <N>  (page Fixer topic
     once per aged ticket, deduped). See SOP-RR-03.
  5. AGENTS.md escalation stamping on NEW boxes — wire stamp-rescue-escalation-
     section.sh into install.sh (client role) so a fresh box gets the instructions,
     not just the env vars (kills R5). Runnable now via the script; install.sh wiring
     is the batched onboarding roll.
DEFERRED
