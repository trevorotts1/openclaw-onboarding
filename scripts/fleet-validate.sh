#!/usr/bin/env bash
# =============================================================================
# fleet-validate.sh — POST-FAN-OUT VALIDATION HARNESS (FLEET-FIX 4b / AUD-58)
# =============================================================================
# The HARD GATE in front of the ONE batched fleet roll.  Nothing is declared
# rolled until this is green on EVERY box in the wave.
#
# It answers exactly one question per box, and it answers it out loud:
#
#     did this box actually take the roll, and can it actually work?
#
# FIVE REQUIRED CHECKS, PER BOX (all five, no exceptions, no skips):
#   1. MC_API_TOKEN store REACHABLE            (verdict only — the value is never read)
#   2. write-back probe returns 2xx or 401     (anything else = FAIL)
#   3. agent-browser probe passes
#   4. `openclaw --version` + the runRetries CEILING ROW (absent row = FAIL)
#   5. repo stamp == the expected version + sha (the STALE-CHECKOUT / DOWNGRADE detector)
#
# Every box's result is written to its PERSISTENT LEDGER ROW:
#
#     /tmp/<sweep>/<box>.json          (+ /tmp/<sweep>/_sweep.json rollup)
#
# so a wave that dies mid-flight still leaves per-box evidence behind, and
# `--resume` re-runs ONLY the boxes that are not already green.
#
# FAIL-LOUD, FAIL-CLOSED:
#   • An undeclared expectation aborts the sweep (exit 4) BEFORE any box is
#     touched.  A gate you cannot fail is not a gate.
#   • An unreachable box, an unparseable probe, a check that never ran — all FAIL
#     or UNKNOWN.  Nothing becomes green by default.
#   • > 20 boxes is REFUSED (doctrine: <= 20 boxes per wave).
#
# USAGE
#   bash scripts/fleet-validate.sh --sweep-id roll-v19-44-0 \
#        --boxes-file wave1.json --expectations expectations.json
#
#   bash scripts/fleet-validate.sh --sweep-id canary --box operator-box \
#        --expectations expectations.json --backend local        # operator-box canary
#
#   bash scripts/fleet-validate.sh --sweep-id sim --boxes-file boxes.json \
#        --expectations exp.json --backend sim --sim-fixture fx.json   # hermetic
#
# EXPECTATIONS FILE (every field REQUIRED — the sweep refuses to run without them):
#   {
#     "repo_version":        "v19.44.0",
#     "repo_sha":            "002f8333...",
#     "openclaw_min_version":"2026.5.22",
#     "run_retries_max":     3,
#     "writeback_url":       "http://127.0.0.1:4000/api/tasks/ingest",
#     "repo_dir":            "$HOME/openclaw-onboarding"   (optional; per-box override wins)
#   }
#
# BOX MANIFEST (JSON array, same shape fleet-refresh.sh already uses):
#   [{"name":"box-01","ssh_target":"user@host","repo_dir":"$HOME/openclaw-onboarding"}, ...]
#
# EXIT CODES
#   0  every box PASS
#   2  at least one box FAIL      <- the roll is BLOCKED
#   3  at least one box UNKNOWN   <- the roll is BLOCKED (UNKNOWN is never green)
#   4  sweep REFUSED (undeclared expectations, bad manifest, wave cap exceeded)
#   1  fatal
#
# NEVER run qc-completeness.sh during a roll — it leaks a client Telegram alert.
# This harness deliberately does not call it, and never will.
#
# AUD-58 / FLEET-FIX 4b
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HARNESS="$REPO_ROOT/shared-utils/fleet_validation_harness.py"

RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'

if [ ! -f "$HARNESS" ]; then
    printf "${RED}[fleet-validate] FATAL: harness not found at %s${NC}\n" "$HARNESS" >&2
    exit 1
fi

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || {
    printf "${RED}[fleet-validate] FATAL: python3 not found on PATH${NC}\n" >&2
    exit 1
}

case "${1:-}" in
    -h|--help|"")
        sed -n '2,70p' "${BASH_SOURCE[0]}"
        # An invocation with no arguments must NOT be mistaken for a green sweep.
        [ -z "${1:-}" ] && exit 4
        exit 0
        ;;
esac

"$PY" "$HARNESS" "$@"
rc=$?

case "$rc" in
    0) printf "${GREEN}[fleet-validate] every box in this wave is GREEN — the roll may proceed.${NC}\n" ;;
    2|3) printf "${RED}[fleet-validate] WAVE NOT GREEN (exit %s) — the fleet roll is BLOCKED.${NC}\n" "$rc" >&2 ;;
    4) printf "${RED}[fleet-validate] SWEEP REFUSED (exit 4) — nothing was probed, nothing is green.${NC}\n" >&2 ;;
esac
exit "$rc"
