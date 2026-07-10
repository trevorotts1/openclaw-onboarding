#!/usr/bin/env bash
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: scripts/loop_companion.sh
# The companion sub-implementation for audit / status / troubleshoot (spec 6.4).
# The sole ENTRY is ../loop-companion.sh; it routes these here. Read-only unless
# a fix/park is explicitly commanded. NO model call.
#   audit [--local] [--json]  full detector pass + provisioning-prevention
#                             checklist + breaker/backoff state + last findings.
#                             exit 0 clean / 4 findings.
#   status                    one screen: armed?, breakers, parked units, open findings.
#   troubleshoot              the "the healer itself is looping" decision tree (REPAIRS.md).
# =============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_DIR="$(cd "$SELF_DIR/.." && pwd)"
TAG="[loop-companion]"
EX_OK=0; EX_ERR=1; EX_USAGE=2; EX_FINDINGS=4

py() { python3 "$SELF_DIR/$1" "${@:2}"; }

cmd_audit() {
    local json=0
    for a in "$@"; do case "$a" in --json) json=1 ;; esac; done
    # Read-only detector pass over collected evidence + the provisioning checklist.
    SKILL_DIR="$SKILL_DIR" JSON="$json" python3 - "$SELF_DIR" <<'PY'
import json, os, sys
sys.path.insert(0, sys.argv[1])
import loop_common as C
import loop_watchdog as W
from loop_ledger import Ledger
th = C.load_skill_config("thresholds.json")
ev = W.collect_evidence()
findings = W.run_detectors(ev, th, C.load_signatures())
led = Ledger()
prov = {
    "heartbeat_allowlist": "check: one agent with an explicit .heartbeat block flips resolveHeartbeatAgents to allowlist",
    "compaction_arithmetic": "check: effective ceiling = contextWindow - softThresholdTokens > 0",
    "one_owner_per_process": "check: exactly one declared supervisor per long-lived process",
    "no_in_session_daemons": "check: no long-lived daemon started inside an OpenClaw session",
    "no_announce_to_client_cron": "check: no announce-mode cron bound to a non-operator chat",
    "light_context_on_recurring": "check: every recurring agentTurn cron declares light-context",
    "offset_healthcheck_present": "check: telegram-offset-healthcheck host cron present",
    "breaker_files_present": bool(C.load_skill_config("breakers.json")),
}
out = {"armed": led.is_armed(), "findings": findings,
       "open_findings": led.open_findings(), "parked_units": led.parked_units(),
       "tripped_breakers": led.tripped_breakers(),
       "provisioning_checklist": prov}
led.close()
if os.environ.get("JSON") == "1":
    print(json.dumps(out, indent=2, sort_keys=True))
else:
    print("LOOP PROTECTION AUDIT (armed=%s)" % out["armed"])
    print("  detector findings this pass: %d" % len(findings))
    for f in findings:
        print("   - [%s] %s: %s" % (f["severity"], f["loop_class"], f["detail"]))
    print("  open findings (ledger): %d | parked units: %d | tripped breakers: %d"
          % (len(out["open_findings"]), len(out["parked_units"]), len(out["tripped_breakers"])))
    print("  provisioning-prevention checklist: %d checks" % len(prov))
sys.exit(4 if findings else 0)
PY
}

cmd_status() {
    python3 - "$SELF_DIR" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from loop_ledger import Ledger
led = Ledger()
print("LOOP PROTECTION STATUS")
print("  armed: %s (DRY_RUN observe-only when false)" % led.is_armed())
print("  tripped breakers: %d" % len(led.tripped_breakers()))
print("  parked units: %s" % ", ".join(r["unit"] for r in led.parked_units()) or "(none)")
print("  open findings: %d" % len(led.open_findings()))
for f in led.all_findings(limit=5):
    print("   - #%s [%s] %s %s (%s)" % (f["finding_id"], f["severity"],
          f["loop_class"], f.get("unit") or "-", f["state"]))
led.close()
PY
}

cmd_troubleshoot() {
    local rep="$SKILL_DIR/REPAIRS.md"
    if [ -f "$rep" ]; then
        echo "$TAG troubleshoot decision tree -> $rep"
        sed -n '1,40p' "$rep"
    else
        echo "$TAG REPAIRS.md not found" >&2; return $EX_ERR
    fi
}

self_test() {
    echo "$TAG self-test: audit (read-only) + status render on a scratch ledger"
    local td; td="$(mktemp -d)"
    export LOOP_STATE_DIR="$td/loop-protection" LOOP_OPENCLAW_ROOT="$td/oc"
    mkdir -p "$td/oc"
    # audit exits 0 (no findings collectible in the sandbox) or 4 (findings); both are valid
    cmd_audit >/dev/null 2>&1; local rc=$?
    if [ "$rc" -eq 0 ] || [ "$rc" -eq 4 ]; then echo "  audit case: PASS (rc=$rc, read-only)"
    else echo "$TAG self-test FAIL: audit errored ($rc)" >&2; rm -rf "$td"; return 1; fi
    cmd_status >/dev/null 2>&1 || { echo "$TAG self-test FAIL: status errored" >&2; rm -rf "$td"; return 1; }
    echo "  status case: PASS"
    rm -rf "$td"; unset LOOP_STATE_DIR LOOP_OPENCLAW_ROOT
    echo "$TAG self-test: PASS"; return 0
}

CMD="${1:-}"; shift || true
case "$CMD" in
    audit)        cmd_audit "$@" ;;
    status)       cmd_status "$@" ;;
    troubleshoot) cmd_troubleshoot "$@" ;;
    --self-test)  self_test ;;
    -h|--help|"") echo "$TAG usage: loop_companion.sh {audit [--local] [--json]|status|troubleshoot}" ;;
    *) echo "$TAG unknown command: $CMD" >&2; exit $EX_USAGE ;;
esac
