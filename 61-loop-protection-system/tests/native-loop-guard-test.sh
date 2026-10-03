#!/usr/bin/env bash
# =============================================================================
# SKILL 61 :: tests/native-loop-guard-test.sh  (SKS-003, spec Fix 5)
# Offline, hermetic. Stub `openclaw` on $LOOP_OPENCLAW_BIN; LOOP_NO_PROBES=1; a
# scratch LOOP_STATE_DIR. Proves:
#   1. the module's own --self-test passes
#   2. CLI shapes: unset / false / true  ->  WARN(4) / WARN(4) / ok(0)
#   3. a failed read is UNDETERMINED (3), never ok
#   4. the real companion `tick` route runs the daily hook, stamps the ledger,
#      records ONE WARN finding, and does not change the tick's exit code
#   5. NO `config set` / `config unset` reached the stub on any path
# Usage: bash tests/native-loop-guard-test.sh        exit 0 = all pass
# =============================================================================
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
MOD="$SKILL/scripts/check_native_loop_guard.py"
TD="$(mktemp -d "${TMPDIR:-/tmp}/loop-nativeguard-test.XXXXXX")"
trap 'rm -rf "$TD"' EXIT
FAILS=0
pass() { echo "  PASS: $*"; }
fail() { echo "  FAIL: $*" >&2; FAILS=$((FAILS+1)); }
expect_rc() { # name want got
    if [ "$3" -eq "$2" ]; then pass "$1 (rc=$3)"; else fail "$1 (want rc=$2, got rc=$3)"; fi
}

python3 "$MOD" --emit-stub "$TD/openclaw" || { echo "cannot emit stub" >&2; exit 1; }
export LOOP_OPENCLAW_BIN="$TD/openclaw" LOOP_NO_PROBES=1 STUB_LOG="$TD/calls.log"
export LOOP_STATE_DIR="$TD/state" LOOP_OPENCLAW_ROOT="$TD/oc" SKILL_SCRIPTS="$SKILL/scripts"
mkdir -p "$TD/oc"; : > "$STUB_LOG"
cli() { python3 "$MOD" "$@"; }

echo "== 1. module --self-test"
cli --self-test >"$TD/st.out" 2>"$TD/st.err"; expect_rc "module self-test" 0 $?

echo "== 2. three shapes through the CLI (global only, no agents)"
export STUB_AGENTS='[]'
STUB_GLOBAL=unset cli check >"$TD/o" 2>&1;  expect_rc "unset -> WARN" 4 $?
grep -q 'native guard off' "$TD/o" && pass "unset output names 'native guard off'" || fail "unset output text"
grep -q 'config set tools.loopDetection.enabled true --strict-json' "$TD/o" \
    && pass "WARN prints the PREPARED Tier-2 command" || fail "prepared command missing"
grep -q 'NOT applied' "$TD/o" && pass "WARN says NOT applied" || fail "'NOT applied' missing"
STUB_GLOBAL=false cli check >"$TD/o" 2>&1;  expect_rc "false -> WARN" 4 $?
STUB_GLOBAL=true  cli check >"$TD/o" 2>&1;  expect_rc "true  -> ok" 0 $?
grep -q '^ok:' "$TD/o" && pass "true output is the ok line" || fail "ok line"
STUB_GLOBAL=true  cli check --json >"$TD/o" 2>&1
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["verdict"]=="ok" and d["prepared_fix"]==[]' "$TD/o" \
    && pass "--json verdict ok, nothing prepared" || fail "--json ok shape"

echo "== 2b. effective value: per-agent override vs global"
export STUB_AGENTS='[{"id":"alpha"},{"id":"beta"}]'
STUB_GLOBAL=true cli check >"$TD/o" 2>&1;                          expect_rc "global on, no override -> ok" 0 $?
STUB_GLOBAL=true STUB_AGENT_beta=false cli check >"$TD/o" 2>&1;    expect_rc "global on, beta override false -> WARN" 4 $?
grep -q 'agent beta overrides it to false' "$TD/o" && pass "WARN names agent beta" || fail "agent name missing"
STUB_GLOBAL=false STUB_AGENT_alpha=true STUB_AGENT_beta=true cli check >"$TD/o" 2>&1
expect_rc "global off but every agent override true -> WARN (global still off)" 4 $?

echo "== 3. failed reads are UNDETERMINED, never ok"
export STUB_AGENTS='[]'
STUB_GLOBAL=maintenance cli check >"$TD/o" 2>&1; expect_rc "offline maintenance -> UNDETERMINED" 3 $?
STUB_GLOBAL=true STUB_AGENTS=FAIL cli check >"$TD/o" 2>&1; expect_rc "agents list fails -> UNDETERMINED" 3 $?
( unset LOOP_OPENCLAW_BIN; LOOP_NO_PROBES=1 cli check >"$TD/o" 2>&1 ); expect_rc "no openclaw resolved (hermetic) -> UNDETERMINED" 3 $?

echo "== 4. real companion tick route runs the daily hook"
export STUB_GLOBAL=unset STUB_AGENTS='[]'
bash "$SKILL/loop-companion.sh" tick --no-send --dry-run >"$TD/tick1.out" 2>"$TD/tick1.err"; TRC1=$?
grep -q 'native guard off' "$TD/tick1.err" && pass "tick surfaced the WARN on stderr" || fail "tick did not run the hook"
python3 - "$LOOP_STATE_DIR" <<'PY' && pass "ledger: ONE open WARN NATIVE-GUARD-OFF + run stamp set" || fail "ledger state"
import os, sys
sys.path.insert(0, os.path.join(os.environ["SKILL_SCRIPTS"]))
from loop_ledger import Ledger
led = Ledger()
rows = led.open_findings("NATIVE-GUARD-OFF")
assert len(rows) == 1 and rows[0]["severity"] == "WARN", rows
assert led.get_meta("native_guard_last_run_ts"), "run stamp missing"
assert led.get_meta("last_tick_ts"), "watchdog liveness stamp missing"
led.close()
PY
N1=$(wc -l <"$STUB_LOG")
bash "$SKILL/loop-companion.sh" tick --no-send --dry-run >"$TD/tick2.out" 2>"$TD/tick2.err"; TRC2=$?
N2=$(wc -l <"$STUB_LOG")
[ "$N2" -eq "$N1" ] && pass "second tick inside 24h made ZERO new probes (cadence holds)" \
    || fail "second tick re-probed ($N1 -> $N2 calls)"
[ "$TRC1" -eq "$TRC2" ] && pass "tick exit code unchanged by the hook ($TRC1)" \
    || fail "tick rc differs between runs ($TRC1 vs $TRC2)"
grep -q 'native_guard\|check_native' "$SKILL/scripts/loop_watchdog.py" \
    && fail "watchdog was edited (this lane must not touch it)" || pass "loop_watchdog.py carries no native-guard code"

echo "== 5. no mutating call reached the stub on ANY path above"
if grep -qE '^(config (set|unset)|agents (add|delete|set))' "$STUB_LOG" \
   || ! awk '!/^(config get |agents list)/ { bad=1 } END { exit bad }' "$STUB_LOG"; then
    fail "stub log holds a non-read call:"; sort "$STUB_LOG" | uniq -c | sort -rn | head -5 >&2
else
    pass "every recorded call was 'config get' or 'agents list' ($(wc -l <"$STUB_LOG" | tr -d ' ') calls)"
fi

echo
if [ "$FAILS" -eq 0 ]; then echo "[native-loop-guard-test] ALL PASS"; exit 0; fi
echo "[native-loop-guard-test] $FAILS FAILURE(S)" >&2; exit 1
