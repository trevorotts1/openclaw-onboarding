#!/usr/bin/env bash
# 57-social-media-in-a-box/scripts/register-social-cron.sh
#
# PORTED weekly-theme cron registrar (merge plan §5.1). Idempotent, dedup,
# furnace-safe, persistent marker. Registers exactly ONE weekly-theme cron that
# fires 57's entry, retires the legacy Skill-35 cron, and QC-asserts exactly one.
# =============================================================================
#   cron name  : social-media-weekly-theme   (renamed from skill35-weekly-theme)
#   schedule   : 0 8 * * 6                    (Saturday 08:00, same as 35)
#   fires      : the Saturday theme-of-week prompt through 57's ONE entry
#   retires    : any skill35-weekly-theme / weekly-batch line (C15)
#
# DE-DUP LAW (merge plan §5): two of anything double-fires or splits state, so
# this guarantees EXACTLY ONE weekly-theme cron per box. Every line carries a
# stable marker comment so re-running is a no-op (idempotent check-then-act).
#
# SAFE BY DEFAULT: prints the plan (dry-run) unless --apply is given. --check
# asserts the invariant (exactly one weekly-theme cron) and exits non-zero if not.
#
# EXIT: 0 ok / 2 invariant violated (--check) / 3 usage.
# USAGE:
#   bash register-social-cron.sh [--apply] [--check] [--marker-dir DIR]
# =============================================================================
set -uo pipefail
PROG="register-social-cron.sh"

CRON_NAME="social-media-weekly-theme"
SCHEDULE="0 8 * * 6"
MARKER="# oc-skill57 ${CRON_NAME}"          # stable idempotency marker
LEGACY_RE='skill35-weekly-theme|weekly-batch|oc-skill35'
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENTRY="$SELF_DIR/social-media-entry.sh"

APPLY=0 CHECK=0
MARKER_DIR="${TMPDIR:-/tmp}/oc-skill57"
while [ $# -gt 0 ]; do
    case "$1" in
        --apply) APPLY=1; shift ;;
        --check) CHECK=1; shift ;;
        --marker-dir) MARKER_DIR="${2:-}"; shift 2 ;;
        -h|--help) sed -n '2,26p' "$0"; exit 3 ;;
        *) echo "FATAL [$PROG]: unknown arg $1" >&2; exit 3 ;;
    esac
done

# The command the cron runs: 57's ONE sanctioned entry in plan mode as a heartbeat
# trigger (the agent then drives the real week). Kept cheap + furnace-safe.
CRON_CMD="bash '$ENTRY' --mode plan --plan"
DESIRED_LINE="$SCHEDULE $CRON_CMD $MARKER"

current_crontab() { crontab -l 2>/dev/null || true; }

count_weekly_theme() {
    current_crontab | grep -cF "$MARKER" 2>/dev/null || true
}

if [ "$CHECK" -eq 1 ]; then
    n="$(count_weekly_theme)"; n="${n//[^0-9]/}"; n="${n:-0}"
    legacy="$(current_crontab | grep -Ec "$LEGACY_RE" 2>/dev/null || true)"; legacy="${legacy//[^0-9]/}"; legacy="${legacy:-0}"
    echo "=== [$PROG] QC: weekly-theme crons=$n (want 1), legacy-35 crons=$legacy (want 0) ==="
    if [ "$n" = "1" ] && [ "$legacy" = "0" ]; then
        echo "  OK: exactly one weekly-theme cron; no legacy Skill-35 cron"
        exit 0
    fi
    echo "  INVARIANT VIOLATED (expected exactly one weekly-theme cron and zero legacy)" >&2
    exit 2
fi

# Build the desired crontab: drop legacy 35 lines + any prior marker line, append one.
NEW_CRONTAB="$(current_crontab | grep -Ev "$LEGACY_RE" | grep -vF "$MARKER")"
NEW_CRONTAB="$(printf '%s\n%s\n' "$NEW_CRONTAB" "$DESIRED_LINE" | grep -v '^[[:space:]]*$')"

echo "=== [$PROG] weekly-theme cron plan ==="
echo "  keep name : $CRON_NAME"
echo "  schedule  : $SCHEDULE  (Saturday 08:00)"
echo "  fires     : $CRON_CMD"
echo "  retires   : any line matching /$LEGACY_RE/"
echo "  marker    : $MARKER"

if [ "$APPLY" -eq 0 ]; then
    echo "  (dry-run — re-run with --apply to install. Nothing changed.)"
    echo "--- resulting crontab (preview) ---"
    printf '%s\n' "$NEW_CRONTAB"
    exit 0
fi

mkdir -p "$MARKER_DIR" 2>/dev/null || true
printf '%s\n' "$NEW_CRONTAB" | crontab - || { echo "FATAL [$PROG]: crontab write failed" >&2; exit 2; }
date -u +"%Y-%m-%dT%H:%M:%SZ registered ${CRON_NAME}" > "$MARKER_DIR/${CRON_NAME}.marker" 2>/dev/null || true
echo "  APPLIED: exactly one weekly-theme cron installed; legacy retired."

# self-assert the invariant after applying
n="$(count_weekly_theme)"; n="${n//[^0-9]/}"; n="${n:-0}"
[ "$n" = "1" ] && { echo "  QC OK: exactly one weekly-theme cron present."; exit 0; }
echo "  QC FAIL: expected exactly one weekly-theme cron, found $n" >&2
exit 2
