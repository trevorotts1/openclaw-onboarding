#!/usr/bin/env bash
# tests/unit/skill60-cron-tick-delivery.test.sh - Skill 60 v1.3.0 wrapper wiring.
#
# Against a copy of the real skill with the sentinel and alert scripts stubbed:
#   A. cron-tick runs the escalate sweep (Rescue Rangers delivery) after the tick
#   B. cron-tick --no-send skips the sweep and passes --no-send to the sentinel
#      in a position argparse accepts (top-level flag BEFORE the subcommand)
#   C. a failing sweep never changes the tick's exit code (10 still maps to 0)
#   D. `tick --no-send` (the documented by-hand form) no longer errors
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SK="$ROOT/60-zhc-early-warning-system"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "PASS $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }

cp -R "$SK" "$T/skill"
export EWS_STATE_DIR="$T/state"; mkdir -p "$EWS_STATE_DIR"
LOG="$T/calls.log"; export LOG
cat > "$T/skill/scripts/ews_sentinel.py" <<'PY'
import os, sys
open(os.environ["LOG"], "a").write("sentinel " + " ".join(sys.argv[1:]) + "\n")
if sys.argv[-1] != "tick":
    sys.exit(2)          # argparse-style usage error: subcommand must come last
sys.exit(10)
PY
cat > "$T/skill/scripts/ews_alert.py" <<'PY'
import os, sys
open(os.environ["LOG"], "a").write("alert " + " ".join(sys.argv[1:]) + "\n")
sys.exit(int(os.environ.get("ALERT_RC", "0")))
PY

: > "$LOG"; bash "$T/skill/ews-entry.sh" cron-tick >/dev/null 2>&1; rc=$?
[ "$rc" = 0 ] && ok "A1 cron-tick exits 0 on findings" || bad "A1 rc=$rc"
grep -qx "alert escalate" "$LOG" && ok "A2 escalate sweep ran after the tick" || bad "A2 log: $(tr '\n' '|' < "$LOG")"

: > "$LOG"; bash "$T/skill/ews-entry.sh" cron-tick --no-send >/dev/null 2>&1; rc=$?
[ "$rc" = 0 ] && ok "B1 cron-tick --no-send exits 0" || bad "B1 rc=$rc"
grep -qx "sentinel --no-send tick" "$LOG" && ok "B2 --no-send reaches the sentinel before 'tick'" || bad "B2 log: $(tr '\n' '|' < "$LOG")"
grep -q "^alert" "$LOG" && bad "B3 --no-send still ran the sweep" || ok "B3 --no-send skips the sweep"

: > "$LOG"; out="$(ALERT_RC=1 bash "$T/skill/ews-entry.sh" cron-tick 2>&1)"; rc=$?
[ "$rc" = 0 ] && ok "C1 failing sweep leaves the tick exit code alone" || bad "C1 rc=$rc"
case "$out" in *"escalate sweep reported a problem"*) ok "C2 failing sweep is logged";; *) bad "C2 no log line";; esac

: > "$LOG"; bash "$T/skill/ews-entry.sh" tick --no-send >/dev/null 2>&1; rc=$?
[ "$rc" = 10 ] && ok "D1 'tick --no-send' runs (exit 10 = findings, not a usage error)" || bad "D1 rc=$rc"

echo "skill60-cron-tick-delivery: $pass passed, $fail failed"
[ "$fail" = 0 ]
