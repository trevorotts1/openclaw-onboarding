#!/usr/bin/env bash
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: ews-entry.sh
# THE ONE SANCTIONED ENTRY. The sentinel tick and every companion command route
# through here (spec 4.1). It runs the deps gate (python3), then dispatches.
# -----------------------------------------------------------------------------
#   tick [--no-send]         one sentinel tick (the 15-minute cron target)
#   audit [--json]           read-only diff table (companion)
#   install [...]            idempotent install / upgrade
#   verify                   the failable drill battery
#   troubleshoot             the spec-5.4 decision tree
#   approve-baseline --key P stamp an intended change (S4 honors the stamp)
#   revert --to <utc-ts>     restore a snapshot AS THE BOX USER (refuses root)
#   baseline {pin|diff|show} baseline management
#   cadence {show|recommend|set ...}   weekly-pinned cadence (D8)
#   fleet {ingest|cycle|digest}        operator-box aggregator (operator box only)
#   escalate                 push unacked P1s to Rescue Rangers
#   prune                    enforce snapshot retention (D7)
#   --self-test              run EVERY script's --self-test (the aggregate gate)
#
# EXIT: passes through the dispatched tool's exit code; 6 = python3 missing; 2 usage.
# =============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SELF_DIR/scripts"
TAG="[ews-entry]"

if ! command -v python3 >/dev/null 2>&1; then
    echo "$TAG FATAL: python3 is required (EWS is deterministic Python)." >&2
    exit 6
fi

usage() {
    sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

py() { python3 "$SCRIPTS/$1" "${@:2}"; }

aggregate_self_test() {
    echo "$TAG --self-test: running every script's self-test"
    local rc=0 f
    for f in ews_ledger.py ews_common.py ews_baseline.py ews_snapshot.py ews_revert.py \
             ews_sentinel.py ews_alert.py ews_fleet.py ews_cadence.py; do
        echo "--- $f ---"
        python3 "$SCRIPTS/$f" --self-test || rc=1
    done
    for s in scan-no-secrets.sh scan-no-client-identifiers.sh scan-no-json-exports.sh; do
        echo "--- $s ---"; bash "$SCRIPTS/$s" --self-test || rc=1
    done
    echo "--- guard-no-anthropic-runtime.py ---"
    python3 "$SCRIPTS/guard-no-anthropic-runtime.py" --self-test || rc=1
    for sh in preflight.sh install.sh; do
        echo "--- $sh ---"; bash "$SELF_DIR/$sh" --self-test || rc=1
    done
    echo "--- ews_companion.sh ---"; bash "$SCRIPTS/ews_companion.sh" --self-test || rc=1
    [ "$rc" -eq 0 ] && echo "$TAG --self-test: ALL PASS" || echo "$TAG --self-test: FAILURES" >&2
    return $rc
}

CMD="${1:-}"; shift || true
case "$CMD" in
    tick)             py ews_sentinel.py tick "$@" ;;
    audit)            bash "$SCRIPTS/ews_companion.sh" audit "$@" ;;
    install)          bash "$SELF_DIR/install.sh" "$@" ;;
    verify)           bash "$SELF_DIR/verify.sh" "$@" ;;
    troubleshoot)     bash "$SCRIPTS/ews_companion.sh" troubleshoot "$@" ;;
    approve-baseline) py ews_baseline.py approve-baseline "$@" ;;
    revert)           py ews_revert.py "$@" ;;
    baseline)         py ews_baseline.py "$@" ;;
    cadence)          py ews_cadence.py "$@" ;;
    fleet)            py ews_fleet.py "$@" ;;
    escalate)         py ews_alert.py escalate "$@" ;;
    prune)            py ews_snapshot.py prune "$@" ;;
    --self-test)      aggregate_self_test ;;
    -h|--help|"")     usage ;;
    *) echo "$TAG unknown command: $CMD" >&2; usage >&2; exit 2 ;;
esac
