#!/usr/bin/env bash
# test-p206-floor-short-probe.sh — fail-first proof for p206-floor-short-probe.py,
# the P6-01 per-box detect verdict for P2-06 ("THE FLOOR-WIPE FIX").
#
#   T1. ARMED: a full 28-dept board -> exit 0, floor_short=false, overall_armed=true.
#   T2. DEGRADED (no --remediate): a short board -> exit 1, floor_short=true, the
#       missing_mandatory / missing_universal_primary delta is reported, and
#       overall_armed=false. NOTHING on disk is touched (probe-only, no mutation
#       without --remediate).
#   T3. --remediate CLOSES THE GAP: the SAME short board with --remediate ->
#       exit 0, overall_armed=true, missing_after=[], and the probe's own
#       re-verification (not the remediator's self-report) is what the exit
#       code is based on.
#   T4. UNRESOLVABLE is distinct from DEGRADED: a --departments-dir pointing at
#       a path that isn't a real departments tree at all -> exit 2 (not 0, not
#       1) -- an "unresolvable" box must never be silently counted as either
#       armed or degraded in a fleet ledger.
#   T5. --json output is ALWAYS valid JSON on stdout even with --remediate (the
#       remediator's own stdout must never leak into and corrupt the probe's
#       JSON report).
#
# Exit 0 = all checks pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBE="$SCRIPT_DIR/p206-floor-short-probe.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

[ -f "$PROBE" ] || { echo "FATAL: $PROBE not shipped" >&2; exit 1; }
python3 -m py_compile "$PROBE" || { echo "FATAL: py_compile failed" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# HERMETICITY: --build-state-file pins declines to a neutral, empty record so
# this suite's verdict never depends on whatever real client build-state
# happens to exist on the box executing it (see the identical rationale in
# test-materialize-missing-departments.sh -- verified live on the operator's
# own box, which carries real declines that would otherwise silently change
# which departments this suite expects to see).
NEUTRAL_BS="$TMP/neutral-build-state.json"
echo '{}' > "$NEUTRAL_BS"

FULL_28="marketing sales billing-finance customer-support web-development app-development graphics video audio research communications crm openclaw-maintenance legal social-media paid-advertisement personal-assistant general-task project-architecture-office bugs healer quality-control presentations scheduling-dispatch logistics-fulfillment engineering account-management podcast"

mk_ws() { # <name> <depts...>
  local name="$1"; shift
  local dd="$TMP/$name/departments"
  rm -rf "$TMP/$name"
  mkdir -p "$dd"
  for d in "$@"; do mkdir -p "$dd/$d/some-role"; done
  echo "$dd"
}

echo "=== T1: ARMED -- full 28-dept board ==="
DD1="$(mk_ws t1 $FULL_28)"
OUT1="$(python3 "$PROBE" --box t1-box --departments-dir "$DD1" --build-state-file "$NEUTRAL_BS" --json)"
RC1=$?
echo "$OUT1" | python3 -m json.tool >/dev/null 2>&1 && ok "T1a: --json output is valid JSON" || bad "T1a: --json output is NOT valid JSON"
if [ "$RC1" = "0" ]; then ok "T1b: full board -> exit 0"; else bad "T1b: expected exit 0, got $RC1"; fi
FLOOR_SHORT1="$(echo "$OUT1" | python3 -c "import json,sys;print(json.load(sys.stdin)['floor_short'])")"
[ "$FLOOR_SHORT1" = "False" ] && ok "T1c: floor_short=false" || bad "T1c: expected floor_short=false, got $FLOOR_SHORT1"

echo "=== T2: DEGRADED (no --remediate) -- short board, zero mutation ==="
DD2="$(mk_ws t2 marketing sales research)"
BEFORE_SUM2="$(find "$DD2" -type f | sort | xargs shasum 2>/dev/null)"
OUT2="$(python3 "$PROBE" --box t2-box --departments-dir "$DD2" --build-state-file "$NEUTRAL_BS" --json)"
RC2=$?
AFTER_SUM2="$(find "$DD2" -type f | sort | xargs shasum 2>/dev/null)"
if [ "$RC2" = "1" ]; then ok "T2a: short board without --remediate -> exit 1 (DEGRADED)"; else bad "T2a: expected exit 1, got $RC2"; fi
FLOOR_SHORT2="$(echo "$OUT2" | python3 -c "import json,sys;print(json.load(sys.stdin)['floor_short'])")"
[ "$FLOOR_SHORT2" = "True" ] && ok "T2b: floor_short=true" || bad "T2b: expected floor_short=true, got $FLOOR_SHORT2"
MISS_MAND2="$(echo "$OUT2" | python3 -c "import json,sys;print(len(json.load(sys.stdin)['missing_mandatory']))")"
[ "$MISS_MAND2" -gt 0 ] 2>/dev/null && ok "T2c: missing_mandatory delta reported ($MISS_MAND2 depts)" || bad "T2c: expected a non-empty missing_mandatory delta, got count=$MISS_MAND2"
if [ "$BEFORE_SUM2" = "$AFTER_SUM2" ]; then
  ok "T2d: probe WITHOUT --remediate mutated nothing on disk"
else
  bad "T2d: probe without --remediate MUTATED the board -- detect-only contract broken"
fi

echo "=== T3: --remediate closes the gap, re-verified from the source ==="
DD3="$(mk_ws t3 marketing sales research)"
OUT3="$(python3 "$PROBE" --box t3-box --departments-dir "$DD3" --build-state-file "$NEUTRAL_BS" --remediate --json)"
RC3=$?
if [ "$RC3" = "0" ]; then ok "T3a: --remediate on a short board -> exit 0 (closed)"; else bad "T3a: expected exit 0 after --remediate, got $RC3"; fi
ARMED3="$(echo "$OUT3" | python3 -c "import json,sys;print(json.load(sys.stdin)['overall_armed'])")"
[ "$ARMED3" = "True" ] && ok "T3b: overall_armed=true post-remediation" || bad "T3b: expected overall_armed=true, got $ARMED3"
MISS_AFTER3="$(echo "$OUT3" | python3 -c "import json,sys;print(len(json.load(sys.stdin).get('missing_after', ['NOTPRESENT'])))")"
[ "$MISS_AFTER3" = "0" ] && ok "T3c: missing_after=[] (re-verified from the live tree, not the remediator's self-report)" || bad "T3c: expected missing_after=[], got count=$MISS_AFTER3"
# Independently re-verify with department-floor.py itself (never trust the probe's own claim).
INDEP="$(python3 - "$SCRIPT_DIR/../../23-ai-workforce-blueprint/scripts/department-floor.py" "$DD3" <<'PYEOF'
import importlib.util, json, sys
from pathlib import Path
floor_path, dd = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("df_indep", floor_path)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
v = m.evaluate_floor(departments_dir=Path(dd), build_state={}, core_answers={})
print(v["floor_met"])
PYEOF
)"
[ "$INDEP" = "True" ] && ok "T3d: INDEPENDENT re-check via department-floor.py directly also reports floor_met=True" \
                       || bad "T3d: independent department-floor.py check disagrees -- got floor_met=$INDEP"

echo "=== T4: UNRESOLVABLE is distinct from DEGRADED ==="
# department_floor.evaluate_floor() only returns rc=7 (unresolvable) when NO
# departments_dir can be found AT ALL -- an explicit (even nonexistent)
# --departments-dir is treated as a zero-department board (rc=3, DEGRADED),
# which is correct: the caller SUPPLIED a path, so "empty" is meaningful
# information, not "unresolvable". To exercise the genuine rc=7 path, omit
# --departments-dir entirely and sandbox HOME to a dir with no workforce at
# all, so department_floor.resolve_departments_dir()'s own fallback chain
# (detect_platform, then ~/clawd/zero-human-company/) finds nothing real.
EMPTY_HOME="$TMP/empty-home"
mkdir -p "$EMPTY_HOME"
OUT4="$(HOME="$EMPTY_HOME" python3 "$PROBE" --box t4-box --json 2>/dev/null)"
RC4=$?
if [ "$RC4" = "2" ]; then
  ok "T4: no --departments-dir + no resolvable workforce -> exit 2 (UNRESOLVABLE), never 0 or 1"
else
  bad "T4: expected exit 2 with no resolvable departments dir, got $RC4 (output: $OUT4)"
fi

echo "=== T5: --json + --remediate never lets the remediator's stdout corrupt the probe's JSON ==="
DD5="$(mk_ws t5 marketing)"
OUT5="$(python3 "$PROBE" --box t5-box --departments-dir "$DD5" --build-state-file "$NEUTRAL_BS" --remediate --json)"
if echo "$OUT5" | python3 -m json.tool >/dev/null 2>&1; then
  ok "T5: --remediate --json output remains a single valid JSON document"
else
  bad "T5: --remediate corrupted the --json output (remediator stdout leaked through)"
fi

echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && { echo "ALL P206-FLOOR-SHORT-PROBE TESTS PASSED"; exit 0; } || { echo "P206-FLOOR-SHORT-PROBE TESTS FAILED"; exit 1; }
