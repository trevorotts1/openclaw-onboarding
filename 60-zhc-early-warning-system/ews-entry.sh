#!/usr/bin/env bash
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: ews-entry.sh
# THE ONE SANCTIONED ENTRY. The sentinel tick and every companion command route
# through here (spec 4.1). It runs the deps gate (python3), then dispatches.
# -----------------------------------------------------------------------------
#   tick [--no-send]         one sentinel tick, BY HAND (true exit contract:
#                            0 clean, 1 error, 2 usage, 10 findings present)
#   cron-tick [--no-send]    the SCHEDULER's tick (the 15-minute cron target).
#                            Runs the exact same sentinel tick as `tick`, then
#                            maps exit 10 (FINDINGS PRESENT) to 0. Findings are
#                            a SUCCESSFUL detection, but the openclaw scheduler
#                            reads any non-zero exit as a job failure and
#                            auto-disables a job after 10 consecutive ones, so a
#                            box with a standing finding used to switch its own
#                            sentinel off. Every OTHER non-zero exit (1 error,
#                            2 usage, 6 deps) passes through UNCHANGED, so a
#                            genuinely broken tick still fails loudly.
#   audit [--json]           read-only diff table (companion)
#   install [...]            idempotent install / upgrade
#   verify                   the failable drill battery
#   troubleshoot             the spec-5.4 decision tree
#   approve-baseline --key P stamp an intended change (S4 honors the stamp)
#   revert --to <utc-ts>     restore a snapshot AS THE BOX USER (refuses root)
#   baseline {pin|diff|show} baseline management
#   cadence {show|recommend|set ...}   weekly-pinned cadence (D8)
#   fleet {ingest|cycle|digest}        operator-box aggregator (operator box only)
#   escalate                 route unacked P1s through rescue ADMISSION (durable
#                            ticket receipt; the group message is supplemental)
#   notices [--peek]         read (and consume) the box's own pending D5 self-notices
#   prune                    enforce snapshot retention (D7)
#   --self-test              run EVERY script's --self-test (the aggregate gate)
#
# EXIT: passes through the dispatched tool's exit code; 6 = python3 missing; 2 usage.
#       `cron-tick` is the ONE deliberate exception: it remaps 10 to 0 (see above).
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
    # Print the banner-delimited header block, however long it grows. The old
    # fixed '2,30p' range leaked the first lines of executable code into the
    # help text and would silently truncate the header as soon as it grew.
    sed -n '2,/^# =\{20,\}$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

py() { python3 "$SCRIPTS/$1" "${@:2}"; }

# ---------------------------------------------------------------------------
# cron_tick - the scheduler-facing wrapper around the sentinel tick.
#
# ROOT CAUSE OF "THE TICK CRON KEEPS AUTO-DISABLING ITSELF": the cron was
# registered as `ews-entry.sh tick`, which passes the sentinel's exit code
# through verbatim. The sentinel exits 10 when it HAS findings, which is the
# system working. The openclaw scheduler has no notion of a "findings" exit:
# it records any non-zero exit as lastRunStatus=error and auto-disables the
# job after 10 consecutive failures. A box holding a standing finding
# therefore failed every 15 minutes until the scheduler switched the sentinel
# off - the guard silenced by its own detections.
#
# This wrapper is the fix: 10 becomes 0 HERE, at the scheduler boundary only.
# The findings themselves are untouched (they are recorded in the ledger and
# routed by the tick itself), `tick` keeps the honest exit contract for
# by-hand runs and scripts, and every other non-zero exit still propagates so
# a real breakage (1 error, 2 usage, 6 missing python3) still fails the job.
# ---------------------------------------------------------------------------
cron_tick() {
    local rc=0
    py ews_sentinel.py tick "$@" || rc=$?
    if [ "$rc" -eq 10 ]; then
        echo "$TAG cron-tick: sentinel reported FINDINGS (exit 10). That is a successful" >&2
        echo "$TAG detection, not a job failure - exiting 0 so the scheduler does not" >&2
        echo "$TAG auto-disable the tick. Read the findings with: ews-entry.sh audit" >&2
        return 0
    fi
    return "$rc"
}

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
    cron-tick)        cron_tick "$@" ;;
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
    notices)          py ews_alert.py notices "$@" ;;
    prune)            py ews_snapshot.py prune "$@" ;;
    --self-test)      aggregate_self_test ;;
    -h|--help|"")     usage ;;
    *) echo "$TAG unknown command: $CMD" >&2; usage >&2; exit 2 ;;
esac
