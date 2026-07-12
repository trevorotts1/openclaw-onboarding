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
#   T6. --remediate --db <scratch> ACTUALLY RUNS LAYER 3 join verification
#       (P2-06 dormant-live-join fix): an explicit --db (never ambient) makes
#       the probe independently re-verify prove-board-join.py from source
#       after remediation, reaching join_verification.status == OK and
#       exit 0 -- proving the sole production caller of
#       materialize-missing-departments.py can actually exercise the (c)2
#       contract ("then prove-board-join.py must pass") instead of always
#       reporting NOT-APPLICABLE.
#   T7. THE HEADLINE REGRESSION LOCK: a phantom CHOSEN department that is
#       neither provisioned nor part of the mandatory floor (so
#       materialize-missing-departments.py never closes it) forces
#       prove-board-join.py to report DRIFT even though the on-disk floor is
#       fully met -> the probe's independently re-verified LAYER 3 check
#       downgrades overall_armed to false and the probe exits 1, not 0.
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

echo "=== T6: --remediate --db <scratch> actually runs LAYER 3 join verification (join OK) ==="
PROVE_JOIN="$SCRIPT_DIR/../../23-ai-workforce-blueprint/scripts/prove-board-join.py"
SEED_WORKSPACES="$SCRIPT_DIR/../../32-command-center-setup/scripts/seed-workspaces.py"
if [ ! -f "$PROVE_JOIN" ] || [ ! -f "$SEED_WORKSPACES" ]; then
  bad "T6 setup: prove-board-join.py or seed-workspaces.py not found in this checkout"
else
  HOME6="$TMP/home-t6"
  CDIR6="$HOME6/clawd/zero-human-company/testco6"
  DD6="$CDIR6/departments"
  mkdir -p "$DD6/marketing/some-role" "$DD6/sales/some-role" "$DD6/research/some-role"
  python3 -c "
import json
entries = [{'id': f'dept-{i}', 'slug': i, 'emoji': '📁', 'name': i.title(), 'headTitle': f'Director of {i}', 'workspacePath': f'departments/{i}'} for i in ('marketing', 'sales', 'research')]
json.dump(entries, open('$CDIR6/departments.json', 'w'), indent=2)
"
  DB6="$TMP/mission-control-t6.db"
  python3 -c "import sqlite3; sqlite3.connect('$DB6').close()"
  OUT6=$(HOME="$HOME6" COMPANY_NAME="TestCo6" \
    python3 "$PROBE" --box t6-box --departments-dir "$DD6" --build-state-file "$NEUTRAL_BS" \
      --remediate --db "$DB6" --json 2>"$TMP/t6.log")
  RC6=$?
  JV6_STATUS=$(echo "$OUT6" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('join_verification', {}).get('status'))" 2>/dev/null)
  if [ "$RC6" = "0" ]; then
    ok "T6a: --remediate --db <scratch> -> exit 0 (floor closed + join OK)"
  else
    bad "T6a: expected exit 0, got $RC6. log:"; cat "$TMP/t6.log"
  fi
  if [ "$JV6_STATUS" = "OK" ]; then
    ok "T6b: join_verification.status == OK -- LAYER 3 was ACTUALLY VERIFIED (not silently NOT-APPLICABLE)"
  else
    bad "T6b: expected join_verification.status == OK, got '$JV6_STATUS'. output: $OUT6"
  fi
fi

echo "=== T7: HEADLINE REGRESSION LOCK -- DRIFT downgrades overall_armed / exit code ==="
if [ ! -f "$PROVE_JOIN" ] || [ ! -f "$SEED_WORKSPACES" ]; then
  bad "T7 setup: prove-board-join.py or seed-workspaces.py not found in this checkout"
else
  HOME7="$TMP/home-t7"
  CDIR7="$HOME7/clawd/zero-human-company/testco7"
  DD7="$CDIR7/departments"
  mkdir -p "$DD7/marketing/some-role" "$DD7/sales/some-role" "$DD7/research/some-role"
  # A phantom CHOSEN department that is NOT part of the mandatory/universal-primary
  # floor (so evaluate_floor() never lists it as "missing" and
  # materialize-missing-departments.py never closes it) and has no on-disk dir --
  # it stays CHOSEN forever, is neither PROVISIONED nor (per seed-workspaces.py,
  # which seeds straight from this artifact) excluded from DISPLAYED, so the join
  # reports drift even after the real floor is fully materialized.
  python3 -c "
import json
entries = [{'id': f'dept-{i}', 'slug': i, 'emoji': '📁', 'name': i.title(), 'headTitle': f'Director of {i}', 'workspacePath': f'departments/{i}'} for i in ('marketing', 'sales', 'research')]
entries.append({'id': 'dept-zzz-totally-fake-phantom-dept', 'slug': 'zzz-totally-fake-phantom-dept', 'emoji': '👻', 'name': 'Zzz Totally Fake Phantom Dept', 'headTitle': 'Director of Nothing', 'workspacePath': 'departments/zzz-totally-fake-phantom-dept'})
json.dump(entries, open('$CDIR7/departments.json', 'w'), indent=2)
"
  DB7="$TMP/mission-control-t7.db"
  python3 -c "import sqlite3; sqlite3.connect('$DB7').close()"
  OUT7=$(HOME="$HOME7" COMPANY_NAME="TestCo7" \
    python3 "$PROBE" --box t7-box --departments-dir "$DD7" --build-state-file "$NEUTRAL_BS" \
      --remediate --db "$DB7" --json 2>"$TMP/t7.log")
  RC7=$?
  JV7_STATUS=$(echo "$OUT7" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('join_verification', {}).get('status'))" 2>/dev/null)
  ARMED7=$(echo "$OUT7" | python3 -c "import json,sys; print(json.load(sys.stdin)['overall_armed'])" 2>/dev/null)
  FLOOR_MET_ON_DISK7=$(python3 - "$SCRIPT_DIR/../../23-ai-workforce-blueprint/scripts/department-floor.py" "$DD7" <<'PYEOF'
import importlib.util, json, sys
from pathlib import Path
floor_path, dd = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("df_t7", floor_path)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
v = m.evaluate_floor(departments_dir=Path(dd), build_state={}, core_answers={})
print(v["floor_met"])
PYEOF
)
  if [ "$FLOOR_MET_ON_DISK7" = "True" ]; then
    ok "T7 setup: the real on-disk floor IS fully met post-remediation (isolates this test to a PURE join-layer defect, not a floor-materialization failure)"
  else
    bad "T7 setup: on-disk floor not met post-remediation -- test does not isolate the join layer. log:"; cat "$TMP/t7.log"
  fi
  if [ "$JV7_STATUS" = "DRIFT" ]; then
    ok "T7a: join_verification.status == DRIFT (the phantom chosen dept is neither provisioned nor library-backed, so it can never be closed)"
  else
    bad "T7a: expected join_verification.status == DRIFT, got '$JV7_STATUS'. output: $OUT7"
  fi
  if [ "$ARMED7" = "False" ]; then
    ok "T7b: overall_armed == false despite the on-disk floor being met -- the independently re-verified LAYER 3 DRIFT correctly downgrades the verdict"
  else
    bad "T7b: expected overall_armed == false, got '$ARMED7' -- a DRIFT join must never report ARMED"
  fi
  if [ "$RC7" = "1" ]; then
    ok "T7c: probe exits 1 (DEGRADED) on a DRIFT join, even though floor_met on disk -- this is the P2-06 (c)2 contract's headline branch, now under a real regression lock"
  else
    bad "T7c: expected exit 1, got $RC7"
  fi
fi

echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && { echo "ALL P206-FLOOR-SHORT-PROBE TESTS PASSED"; exit 0; } || { echo "P206-FLOOR-SHORT-PROBE TESTS FAILED"; exit 1; }
