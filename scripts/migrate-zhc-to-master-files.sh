#!/usr/bin/env bash
# =============================================================================
# migrate-zhc-to-master-files.sh — PRD item 1.10
# =============================================================================
# Move every Zero Human Company built before the canonical root was adopted
# (PRD 1.9) into the canonical home:
#   Mac:  ~/Downloads/openclaw-master-files/zero-human-company/<slug>/
#   VPS:  /data/openclaw-master-files/zero-human-company/<slug>/
#
# USAGE:
#   bash migrate-zhc-to-master-files.sh             # dry-run (DEFAULT — nothing moves)
#   bash migrate-zhc-to-master-files.sh --apply     # actually moves files
#   bash migrate-zhc-to-master-files.sh --help
#
# SAFETY GUARANTEES:
#   • --dry-run is the default; --apply must be passed explicitly.
#   • Nothing is EVER deleted.  Conflict copies go to .conflicts/<slug>-<source>-<ts>/.
#   • Every move is logged to <canonical>/.migration-log.json (idempotent re-run safe).
#   • A symlink is left at the old location for one release cycle.
#   • The operator gets a Telegram message listing any conflicts.
#   • After moving, sync-md-content-to-db.py + seed-workspaces.py are re-run so
#     dashboard workspace paths, departments.json, and mission-control.db point at
#     the new location.  The Gemini index path is verified post-move.
#
# EXIT CODES:
#   0  success (or dry-run completed with no errors)
#   1  fatal (e.g., cannot detect platform)
#   2  partial (at least one company could not be migrated)
#
# All logic is implemented in shared-utils/migrate_zhc_runner.py so bash
# quoting issues with JSON cannot corrupt path handling.
#
# PRD 1.10 — v11.5.0 (WAVE 2)
# =============================================================================
set -euo pipefail

# ── argument passthrough ──────────────────────────────────────────────────────
APPLY_FLAG=""
for arg in "$@"; do
  case "$arg" in
    --apply)   APPLY_FLAG="--apply" ;;
    --dry-run) APPLY_FLAG="" ;;
    --help|-h)
      echo "Usage: $0 [--dry-run | --apply]"
      echo "  --dry-run  Print manifest, move nothing (DEFAULT)"
      echo "  --apply    Actually move companies to the canonical root"
      exit 0 ;;
    *) echo "Unknown flag: $arg" >&2; exit 1 ;;
  esac
done

# ── locate shared-utils and runner ───────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SHARED_UTILS="$REPO_ROOT/shared-utils"
RUNNER="$SHARED_UTILS/migrate_zhc_runner.py"

if [ ! -f "$RUNNER" ]; then
  echo "FATAL: $RUNNER not found." >&2
  echo "Run this script from the openclaw-onboarding repo." >&2
  exit 1
fi

# ── delegate all logic to Python (avoids bash/JSON quoting complexity) ────────
exec python3 "$RUNNER" \
  --shared-utils "$SHARED_UTILS" \
  --repo-root    "$REPO_ROOT" \
  $APPLY_FLAG
