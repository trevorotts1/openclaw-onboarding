#!/usr/bin/env bash
# test-materialize-missing-departments-join.sh — P2-06 (c)2 CLOSING REQUIREMENT:
# fail-first proof for the "then prove-board-join.py must pass" half of
# materialize-missing-departments.py, added on top of the already-shipped
# floor-fill-driver.py wiring (see test-materialize-missing-departments.sh).
#
# WHY THIS IS A NEW GAP, NOT A DUPLICATE OF EXISTING COVERAGE
# -------------------------------------------------------------
# The already-shipped materialize-missing-departments.py (commit 84b7d4c5)
# closes LAYER 2 (provisioned: real department directories on disk) but never
# touches LAYER 1 (chosen: <company_dir>/departments.json) or LAYER 3
# (displayed: the Command Center's `workspaces` table), and never invokes
# prove-board-join.py at all (verified: zero references to it in the shipped
# file before this unit's patch). A box can therefore leave that script with
# floor_met=True on disk and STILL be broken for the client — the exact
# residue class prove-board-join.py exists to catch. This suite proves the
# extension this unit adds closes that gap for real.
#
#   T0. SAFETY REGRESSION LOCK (fail-first, reintroduces a REAL incident hit
#       during this unit's own development): the FIRST draft of
#       _find_cc_db() delegated to the shared resolve_db.find_dashboard_db()
#       unconditionally, which — on ANY box that has ever had a real Command
#       Center installed, including the operator's own dev machine — silently
#       discovers and would mutate the box's LIVE mission-control.db via a
#       plain `--apply` test run with no isolation. Proves the shipped
#       _find_cc_db() returns None with neither --db nor
#       $DASHBOARD_DB_PATH/$DATABASE_PATH set, REGARDLESS of what real
#       install-path candidates exist on the box, then proves the REMOVED
#       ambient-discovery version would have found one (this box's own real
#       ~/projects/command-center/mission-control.db, if present) -- so this
#       suite would have caught the incident before it shipped.
#   T1. CHOSEN ARTIFACT SYNC IS APPEND-ONLY: pre-existing departments.json
#       entries survive byte-for-byte; only the newly-closed dept id is
#       appended.
#   T2. NO --db / NO ENV VAR -> join_verification is NOT-APPLICABLE (never a
#       failure; a box with no Command Center has nothing to join) and the
#       overall rc still reflects the on-disk floor.
#   T3. END-TO-END THREE-LAYER JOIN: an EXPLICIT scratch --db (never ambient)
#       + isolated $HOME -> prove-board-join.py --json reports rc=0 (JOIN OK)
#       after materialize-missing-departments.py --apply + its own
#       seed-workspaces.py re-run.
#   T4. --skip-join-verify bypasses chosen-artifact sync + join check entirely.
#   T5. THE HEADLINE REGRESSION LOCK: a phantom CHOSEN department that is
#       neither provisioned nor part of the mandatory/universal-primary floor
#       (so it can never be closed by floor-fill-driver.py) forces
#       prove-board-join.py to report DRIFT even though the real on-disk
#       floor is fully met -> the overall exit code must downgrade to 1
#       ("residue not fully closed"), never 0. This is the single most
#       important new behavior this unit ships (the "then prove-board-join.py
#       must pass" half of the P2-06 (c)2 contract) and previously had NO
#       automated coverage — T2 only proved NOT-APPLICABLE and T3 only proved
#       the clean-pass OK case; neither exercises the downgrade branch at all.
#
# Exit 0 = all checks pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MATERIALIZE="$SCRIPT_DIR/materialize-missing-departments.py"
FLOOR="$SCRIPT_DIR/department-floor.py"
SEED_WORKSPACES="$REPO_ROOT/32-command-center-setup/scripts/seed-workspaces.py"
PROVE_JOIN="$SCRIPT_DIR/prove-board-join.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

[ -f "$MATERIALIZE" ] || { echo "FATAL: $MATERIALIZE not shipped" >&2; exit 1; }
python3 -m py_compile "$MATERIALIZE" || { echo "FATAL: py_compile failed" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

NEUTRAL_BS="$TMP/neutral-build-state.json"
echo '{}' > "$NEUTRAL_BS"

json_get() { # <json-string> <python-expr-on-loaded-dict>
  # Some of the scripts under test print a human-readable block to stdout
  # BEFORE their --json blob on the same stream (prove-board-join.py's
  # render()); decode from the first '{' onward so this works for both
  # bare-JSON and table-prefixed output without having to know which.
  python3 -c "
import json, sys
s = sys.stdin.read()
i = s.find('{')
d = json.loads(s[i:]) if i >= 0 else {}
print($2)
" <<<"$1"
}

mk_workspace() { # <company-dir> <space-separated present-dept slugs>
  local cdir="$1"; shift
  local dd="$cdir/departments"
  rm -rf "$cdir"
  mkdir -p "$dd"
  for d in "$@"; do
    mkdir -p "$dd/$d/some-role"
  done
  echo "$dd"
}

echo "=== T0: SAFETY REGRESSION LOCK — _find_cc_db() never ambiently discovers a real DB ==="
NO_ENV_RESULT=$(python3 - "$MATERIALIZE" <<'PYEOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("mmd_t0", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m._find_cc_db(None))
PYEOF
)
if [ "$NO_ENV_RESULT" = "None" ]; then
  ok "T0a: _find_cc_db(None) with no --db and no \$DASHBOARD_DB_PATH/\$DATABASE_PATH -> None (no ambient discovery)"
else
  bad "T0a: _find_cc_db(None) should return None with no explicit signal but returned '$NO_ENV_RESULT' -- AMBIENT DB DISCOVERY REGRESSION (the live-incident class)"
fi

# Prove this suite WOULD have caught the actual incident: reintroduce the
# removed ambient-discovery version into a scratch copy and show it finds a
# real install-path candidate when one exists on THIS box (the exact
# mechanism that silently touched the operator's live mission-control.db
# during this unit's own development) -- skips cleanly (not a failure) on a
# box with no such path, since the point is proving the OLD code's hazard
# existed, not asserting every CI box has one.
BROKEN="$SCRIPT_DIR/.materialize-BROKEN-T0-scratch.py"
trap 'rm -rf "$TMP" "$BROKEN"' EXIT
python3 - "$MATERIALIZE" "$BROKEN" <<'PYEOF'
import re, sys
src_path, dst_path = sys.argv[1], sys.argv[2]
src = open(src_path).read()
needle = "def _find_cc_db(explicit_db):"
assert needle in src
start = src.index(needle)
end = src.index("\n\n\ndef verify_board_join", start)
assert end > start
old_unsafe_fn = (
    "def _find_cc_db(explicit_db):\n"
    "    # REINTRODUCED FOR T0 FAIL-FIRST PROOF: the pre-fix version -- falls\n"
    "    # through to the shared resolver's full ambient install-path candidate\n"
    "    # list (the actual defect this unit hit and fixed).\n"
    "    if explicit_db:\n"
    "        from pathlib import Path as _P\n"
    "        p = _P(explicit_db)\n"
    "        return p if p.is_file() else None\n"
    "    import sys as _sys\n"
    "    from pathlib import Path as _P\n"
    "    _sys.path.insert(0, str(REPO_ROOT / 'shared-utils'))\n"
    "    try:\n"
    "        from resolve_db import find_dashboard_db\n"
    "        p = find_dashboard_db()\n"
    "        return p if p and str(p) and _P(p).is_file() else None\n"
    "    except ImportError:\n"
    "        return None\n"
)
patched = src[:start] + old_unsafe_fn + src[end + 3:]
assert patched != src
open(dst_path, "w").write(patched)
print("pre-fix _find_cc_db reintroduced into scratch copy")
PYEOF
python3 -m py_compile "$BROKEN" || bad "T0 setup: broken scratch copy failed to compile"
UNSAFE_RESULT=$(env -u DASHBOARD_DB_PATH -u DATABASE_PATH python3 - "$BROKEN" <<'PYEOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("mmd_t0_broken", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m._find_cc_db(None))
PYEOF
)
if [ "$UNSAFE_RESULT" != "None" ]; then
  ok "T0b: the REMOVED ambient-discovery version finds a real DB on THIS box ($UNSAFE_RESULT) with zero explicit signal -- reproduces the actual incident; this suite (T0a) WOULD have caught it before ship"
else
  echo "  SKIP: T0b: no ambient install-path candidate exists on this box to demonstrate the hazard against (T0a's contract proof stands regardless)"
fi

echo "=== T1: chosen-artifact sync is append-only ==="
CDIR1="$TMP/t1"
DD1=$(mk_workspace "$CDIR1" marketing sales research crm)
python3 -c "
import json
existing = [{'id': 'dept-marketing', 'slug': 'marketing', 'emoji': '📣', 'name': 'Marketing', 'headTitle': 'CMO', 'workspacePath': 'departments/marketing'}]
json.dump(existing, open('$CDIR1/departments.json', 'w'), indent=2)
"
python3 "$MATERIALIZE" --departments-dir "$DD1" --build-state-file "$NEUTRAL_BS" --apply --json \
  >"$TMP/t1-result.json" 2>"$TMP/t1.log"
APPENDED=$(json_get "$(cat "$TMP/t1-result.json")" "','.join(sorted(d.get('chosen_artifact_appended', [])))")
CHOSEN_HAS_MARKETING=$(python3 -c "import json; print(any(e['slug']=='marketing' and e['emoji']=='📣' for e in json.load(open('$CDIR1/departments.json'))))")
if [ -n "$APPENDED" ]; then
  ok "T1a: chosen_artifact_appended reports newly-closed dept id(s): $APPENDED"
else
  bad "T1a: expected chosen_artifact_appended to be non-empty (many depts were short). log:"; cat "$TMP/t1.log"
fi
if [ "$CHOSEN_HAS_MARKETING" = "True" ]; then
  ok "T1b: the PRE-EXISTING 'marketing' entry (custom emoji marker) survived byte-for-byte -- append-only confirmed"
else
  bad "T1b: pre-existing chosen-artifact entry was altered -- append-only contract broken"
fi

echo "=== T2: no --db / no env var -> NOT-APPLICABLE, never a false failure ==="
CDIR2="$TMP/t2"
DD2=$(mk_workspace "$CDIR2" marketing)
JOIN_JSON=$(env -u DASHBOARD_DB_PATH -u DATABASE_PATH \
  python3 "$MATERIALIZE" --departments-dir "$DD2" --build-state-file "$NEUTRAL_BS" --apply --json 2>"$TMP/t2.log")
T2_RC=$?
JV_STATUS=$(json_get "$JOIN_JSON" "d.get('join_verification', {}).get('status')")
if [ "$JV_STATUS" = "NOT-APPLICABLE" ]; then
  ok "T2a: join_verification.status == NOT-APPLICABLE with no --db / no env var (no ambient DB found)"
else
  bad "T2a: expected join_verification.status == NOT-APPLICABLE, got '$JV_STATUS'"
fi
if [ "$T2_RC" = "0" ]; then
  ok "T2b: overall rc=0 (floor met; NOT-APPLICABLE join never blocks a box with no Command Center)"
else
  bad "T2b: expected rc=0, got $T2_RC"
fi

echo "=== T3: end-to-end three-layer join via an EXPLICIT scratch --db ==="
if [ ! -f "$SEED_WORKSPACES" ] || [ ! -f "$PROVE_JOIN" ]; then
  bad "T3 setup: seed-workspaces.py or prove-board-join.py not found in this checkout"
else
  HOME3="$TMP/home-t3"
  CDIR3="$HOME3/clawd/zero-human-company/testco"
  DD3=$(mk_workspace "$CDIR3" marketing sales research crm billing-finance)
  python3 -c "
import json
entries = [{'id': f'dept-{i}', 'slug': i, 'emoji': '📁', 'name': i.title(), 'headTitle': f'Director of {i}', 'workspacePath': f'departments/{i}'} for i in ('marketing','sales','research','crm','billing-finance','bugs')]
json.dump(entries, open('$CDIR3/departments.json', 'w'), indent=2)
"
  DB3="$TMP/mission-control-t3.db"
  python3 -c "import sqlite3; sqlite3.connect('$DB3').close()"

  HOME="$HOME3" COMPANY_NAME="TestCo" \
    python3 "$MATERIALIZE" --departments-dir "$DD3" --build-state-file "$NEUTRAL_BS" \
      --apply --db "$DB3" --json >"$TMP/t3-result.json" 2>"$TMP/t3.log"
  T3_RC=$?
  T3_JV_STATUS=$(json_get "$(cat "$TMP/t3-result.json")" "d.get('join_verification', {}).get('status')")
  if [ "$T3_RC" = "0" ]; then
    ok "T3a: materialize-missing-departments.py --db <scratch> exits 0 (floor met + join OK)"
  else
    bad "T3a: expected rc=0, got $T3_RC. log:"; cat "$TMP/t3.log"
  fi
  if [ "$T3_JV_STATUS" = "OK" ]; then
    ok "T3b: join_verification.status == OK (chosen == provisioned == displayed via an explicit --db, never ambient)"
  else
    bad "T3b: expected join_verification.status == OK, got '$T3_JV_STATUS'. log:"; cat "$TMP/t3.log"
  fi

  # Independent re-check: a fresh prove-board-join.py invocation against the
  # same explicit scratch db/company-dir must also report JOIN OK.
  HOME="$HOME3" python3 "$PROVE_JOIN" --company-dir "$CDIR3" --db "$DB3" --json \
    >"$TMP/t3-postjoin.out" 2>"$TMP/t3-postjoin.log"
  T3_POST_RC=$?
  if [ "$T3_POST_RC" = "0" ]; then
    ok "T3c: independent prove-board-join.py re-check also exits 0 (JOIN OK)"
  else
    bad "T3c: independent prove-board-join.py re-check exit=$T3_POST_RC (expected 0). log:"; cat "$TMP/t3-postjoin.log"
  fi
fi

echo "=== T4: --skip-join-verify bypasses chosen-artifact sync + join check ==="
CDIR4="$TMP/t4"
DD4=$(mk_workspace "$CDIR4" marketing)
python3 "$MATERIALIZE" --departments-dir "$DD4" --build-state-file "$NEUTRAL_BS" \
  --apply --skip-join-verify --json >"$TMP/t4-result.json" 2>"$TMP/t4.log"
HAS_JV=$(json_get "$(cat "$TMP/t4-result.json")" "'join_verification' in d")
HAS_APPENDED=$(json_get "$(cat "$TMP/t4-result.json")" "'chosen_artifact_appended' in d")
if [ "$HAS_JV" = "False" ] && [ "$HAS_APPENDED" = "False" ]; then
  ok "T4: --skip-join-verify produces a result with no join_verification / chosen_artifact_appended keys at all"
else
  bad "T4: --skip-join-verify should omit join_verification + chosen_artifact_appended entirely (has_jv=$HAS_JV has_appended=$HAS_APPENDED)"
fi
[ ! -f "$CDIR4/departments.json" ] && ok "T4b: --skip-join-verify never even created a departments.json artifact" \
  || bad "T4b: --skip-join-verify unexpectedly wrote a departments.json"

echo "=== T5: HEADLINE REGRESSION LOCK -- DRIFT downgrades the overall exit code to 1 ==="
if [ ! -f "$SEED_WORKSPACES" ] || [ ! -f "$PROVE_JOIN" ]; then
  bad "T5 setup: seed-workspaces.py or prove-board-join.py not found in this checkout"
else
  HOME5="$TMP/home-t5"
  CDIR5="$HOME5/clawd/zero-human-company/testco5"
  DD5=$(mk_workspace "$CDIR5" marketing sales research crm billing-finance)
  # Pre-seed the CHOSEN artifact with the 5 real present depts PLUS one
  # PHANTOM department that is neither on disk nor part of the mandatory /
  # universal-primary floor department_floor.evaluate_floor() enforces, so
  # build_gap_map() never includes it and it can NEVER be closed by
  # floor-fill-driver.py -- it stays chosen forever, with no matching tree.
  python3 -c "
import json
entries = [{'id': f'dept-{i}', 'slug': i, 'emoji': '📁', 'name': i.title(), 'headTitle': f'Director of {i}', 'workspacePath': f'departments/{i}'} for i in ('marketing', 'sales', 'research', 'crm', 'billing-finance')]
entries.append({'id': 'dept-zzz-totally-fake-phantom-dept', 'slug': 'zzz-totally-fake-phantom-dept', 'emoji': '👻', 'name': 'Zzz Totally Fake Phantom Dept', 'headTitle': 'Director of Nothing', 'workspacePath': 'departments/zzz-totally-fake-phantom-dept'})
json.dump(entries, open('$CDIR5/departments.json', 'w'), indent=2)
"
  DB5="$TMP/mission-control-t5.db"
  python3 -c "import sqlite3; sqlite3.connect('$DB5').close()"

  HOME="$HOME5" COMPANY_NAME="TestCo5" \
    python3 "$MATERIALIZE" --departments-dir "$DD5" --build-state-file "$NEUTRAL_BS" \
      --apply --db "$DB5" --json >"$TMP/t5-result.json" 2>"$TMP/t5.log"
  T5_RC=$?
  T5_JV_STATUS=$(json_get "$(cat "$TMP/t5-result.json")" "d.get('join_verification', {}).get('status')")
  T5_AFTER_FLOOR_MET=$(json_get "$(cat "$TMP/t5-result.json")" "d.get('after_floor_met')")

  if [ "$T5_AFTER_FLOOR_MET" = "True" ]; then
    ok "T5 setup: after_floor_met == True -- the real on-disk floor IS fully closed (this test isolates a PURE join-layer defect, not a floor-materialization failure)"
  else
    bad "T5 setup: after_floor_met != True -- test does not isolate the join layer. log:"; cat "$TMP/t5.log"
  fi
  if [ "$T5_JV_STATUS" = "DRIFT" ]; then
    ok "T5a: join_verification.status == DRIFT (the phantom chosen dept can never be provisioned or displayed)"
  else
    bad "T5a: expected join_verification.status == DRIFT, got '$T5_JV_STATUS'. log:"; cat "$TMP/t5.log"
  fi
  if [ "$T5_RC" = "1" ]; then
    ok "T5b: overall rc == 1 even though the on-disk floor is met -- DRIFT correctly downgrades the exit code (the P2-06 (c)2 contract's headline branch, now under a real regression lock)"
  else
    bad "T5b: expected overall rc == 1, got $T5_RC -- a DRIFT join must never leave rc=0. log:"; cat "$TMP/t5.log"
  fi

  # Independent re-check: prove-board-join.py run fresh against the same
  # scratch db/company-dir must ALSO report DRIFT (rc=2) -- confirms this
  # isn't an artifact of materialize's own status mapping.
  HOME="$HOME5" python3 "$PROVE_JOIN" --company-dir "$CDIR5" --db "$DB5" --json \
    >"$TMP/t5-postjoin.out" 2>"$TMP/t5-postjoin.log"
  T5_POST_RC=$?
  if [ "$T5_POST_RC" = "2" ]; then
    ok "T5c: independent prove-board-join.py re-check also reports rc=2 (AF-BOARD-JOIN-DRIFT)"
  else
    bad "T5c: independent prove-board-join.py re-check exit=$T5_POST_RC (expected 2). log:"; cat "$TMP/t5-postjoin.log"
  fi
fi

echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && { echo "ALL MATERIALIZE-MISSING-DEPARTMENTS-JOIN TESTS PASSED"; exit 0; } || { echo "MATERIALIZE-MISSING-DEPARTMENTS-JOIN TESTS FAILED"; exit 1; }
