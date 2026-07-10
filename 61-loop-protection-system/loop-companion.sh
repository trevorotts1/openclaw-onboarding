#!/usr/bin/env bash
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: loop-companion.sh
# THE ONE SANCTIONED ENTRY (spec 9.1). The watchdog tick and every companion
# command route through here. It runs the deps gate (python3), then dispatches.
# -----------------------------------------------------------------------------
#   tick [--no-send]          one watchdog tick (the 15-minute cron target)
#   audit [--local] [--json]  read-only detector pass + provisioning checklist
#   status                    one screen: armed, breakers, parked units, findings
#   install [...]             idempotent install / upgrade (host-level, refuses root)
#   verify                    the failable drill battery
#   troubleshoot              the "the healer itself is looping" decision tree
#   fix <finding-id>          operator-commanded kill card by finding id: the config-
#                             free process-park (LF-6) applies for real; a config-
#                             touching class is PREPARED (command + revert), applied on-box
#   approve <finding-id>      approve a Tier-2 proposal (prepares its on-box command + revert)
#   park <unit> / unpark <unit>|--finding <id>   park / unpark a supervised unit
#                             (`unpark --finding <id>` is the emitted one-line revert)
#   arm / disarm              leave / re-enter DRY_RUN observe-only (spec 6.1)
#   escalate                  push unacked P1s to Rescue Rangers
#   --self-test               run EVERY script's --self-test (the aggregate gate)
#
# EXIT: passes through the dispatched tool's exit code; 6 = python3 missing; 2 usage.
# =============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SELF_DIR/scripts"
TAG="[loop-companion]"

if ! command -v python3 >/dev/null 2>&1; then
    echo "$TAG FATAL: python3 is required (Loop Protection is deterministic Python)." >&2
    exit 6
fi

usage() { sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }
py() { python3 "$SCRIPTS/$1" "${@:2}"; }

aggregate_self_test() {
    echo "$TAG --self-test: running every script's self-test"
    local rc=0 f s
    for f in loop_ledger.py loop_common.py loop_detectors.py loop_backoff.py \
             loop_breaker.py loop_killcards.py loop_escalate.py loop_watchdog.py; do
        echo "--- $f ---"; python3 "$SCRIPTS/$f" --self-test || rc=1
    done
    for s in scan-no-secrets.sh scan-no-client-identifiers.sh scan-no-json-exports.sh; do
        echo "--- $s ---"; bash "$SCRIPTS/$s" --self-test || rc=1
    done
    echo "--- guard-no-anthropic-runtime.py ---"
    python3 "$SCRIPTS/guard-no-anthropic-runtime.py" --self-test || rc=1
    echo "--- loop_companion.sh ---"; bash "$SCRIPTS/loop_companion.sh" --self-test || rc=1
    for sh in preflight.sh install.sh; do
        echo "--- $sh ---"; bash "$SELF_DIR/$sh" --self-test || rc=1
    done
    [ "$rc" -eq 0 ] && echo "$TAG --self-test: ALL PASS" || echo "$TAG --self-test: FAILURES" >&2
    return $rc
}

CMD="${1:-}"; shift || true
case "$CMD" in
    tick)         py loop_watchdog.py tick "$@" ;;
    audit)        bash "$SCRIPTS/loop_companion.sh" audit "$@" ;;
    status)       bash "$SCRIPTS/loop_companion.sh" status "$@" ;;
    troubleshoot) bash "$SCRIPTS/loop_companion.sh" troubleshoot "$@" ;;
    install)      bash "$SELF_DIR/install.sh" "$@" ;;
    verify)       bash "$SELF_DIR/verify.sh" "$@" ;;
    arm)          py loop_ledger.py arm "$@" ;;
    disarm)       py loop_ledger.py disarm "$@" ;;
    park)         py loop_breaker.py park "$@" ;;
    unpark)       py loop_breaker.py unpark "$@" ;;
    escalate)     py loop_escalate.py "$@" ;;
    fix)          py loop_killcards.py fix "$@" ;;
    approve)      py loop_killcards.py approve "$@" ;;
    --self-test)  aggregate_self_test ;;
    -h|--help|"") usage ;;
    *) echo "$TAG unknown command: $CMD" >&2; usage >&2; exit 2 ;;
esac
