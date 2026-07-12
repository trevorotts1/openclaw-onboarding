#!/usr/bin/env bash
# ============================================================
#  test-p208-sop-role-provisioning-probe.sh — P2-08 (c) step 3 regression lock
#
#  Proves scripts/probe/p208-sop-role-provisioning-probe.sh's three
#  INDEPENDENT checks (SOP library populated / skill-version drift / refresh
#  queue drained) each correctly flip the overall verdict, and that the
#  fail-closed --min-total contract (no implicit floor) is enforced.
#
#  Every scenario stubs a throwaway sqlite DB, a throwaway skills dir +
#  reference repo dir, and a throwaway refresh-queue file so this test NEVER
#  touches the real mission-control.db, the real installed skills dir, or the
#  real workspace queue file.
#
#  FAIL-FIRST PROOF (reproducible): before scripts/probe/p208-...-probe.sh
#  existed, scenario 0 below fails (script not found) and every dependent
#  scenario fails with it -- 0/N pass. With the script shipped, N/N pass.
#
#  EXIT CODES: 0 all passed, 1 one or more failed.
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROBE="$REPO_ROOT/scripts/probe/p208-sop-role-provisioning-probe.sh"
FAIL_COUNT=0
PASS_COUNT=0

_pass() { echo "  PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
_fail() { echo "  FAIL: $1" >&2; FAIL_COUNT=$((FAIL_COUNT + 1)); }
_section() { echo ""; echo "=== $1 ==="; }

_section "Scenario 0 — the probe script must exist and pass bash -n"
if [ -f "$PROBE" ]; then
  _pass "p208-sop-role-provisioning-probe.sh shipped at $PROBE"
else
  _fail "p208-sop-role-provisioning-probe.sh NOT FOUND at $PROBE -- pre-fix tree"
fi
if [ -f "$PROBE" ] && bash -n "$PROBE" 2>/dev/null; then
  _pass "bash -n OK"
else
  [ -f "$PROBE" ] && _fail "bash -n FAILED"
fi
if [ ! -f "$PROBE" ]; then
  _section "SUMMARY"; echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"; exit 1
fi

TESTHOME="$(mktemp -d)"
trap 'rm -rf "$TESTHOME"' EXIT

_mk_db() {
  # $1=db path  $2=total sops rows  $3=role-library rows (source='role-library')
  local db="$1" total="$2" rl="$3"
  python3 - "$db" "$total" "$rl" <<'PYEOF'
import sqlite3, sys
db, total, rl = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
conn = sqlite3.connect(db)
conn.execute("CREATE TABLE sops (id INTEGER PRIMARY KEY, slug TEXT, source TEXT)")
n = 0
for i in range(rl):
    conn.execute("INSERT INTO sops (slug, source) VALUES (?, 'role-library')", (f"rl-{i}",))
    n += 1
while n < total:
    conn.execute("INSERT INTO sops (slug, source) VALUES (?, NULL)", (f"jsonl-{n}",))
    n += 1
conn.commit()
conn.close()
PYEOF
}

_mk_skills_dirs_matching() {
  # $1=installed dir  $2=reference dir  -- both get 41-foo/skill-version.txt = 1.0.0
  mkdir -p "$1/41-foo" "$2/41-foo"
  echo "1.0.0" > "$1/41-foo/skill-version.txt"
  echo "1.0.0" > "$2/41-foo/skill-version.txt"
}

_run_probe() { bash "$PROBE" "$@"; }

# ─── Scenario 1: usage error -- no --min-total supplied (fail-closed) ───────
_section "Scenario 1 — missing --min-total is a USAGE ERROR (exit 2), never an implicit floor"
OUT1="$(_run_probe --json 2>&1)"; RC1=$?
if [ "$RC1" -eq 2 ] && echo "$OUT1" | grep -qi "min-total is required"; then
  _pass "missing --min-total correctly refused with exit 2 (fail-closed, no implicit floor)"
else
  _fail "missing --min-total did not fail closed (rc=$RC1): $OUT1"
fi

# ─── Scenario 2: everything healthy -- PROVISIONED, exit 0 ─────────────────
_section "Scenario 2 — healthy SOP DB + matching skill versions + empty queue -> PROVISIONED, exit 0"
DB2="$TESTHOME/mc2.db"; _mk_db "$DB2" 50 5
SK2="$TESTHOME/skills2"; REF2="$TESTHOME/ref2"; _mk_skills_dirs_matching "$SK2" "$REF2"
WS2="$TESTHOME/ws2"; mkdir -p "$WS2"
cat > "$WS2/.artifact-refresh-queue.json" <<'EOF'
{"summary": {"stale": 0}, "items": []}
EOF
OUT2="$(_run_probe --min-total 10 --db "$DB2" --skills-dir "$SK2" --repo-dir "$REF2" --workspace "$WS2" 2>&1)"; RC2=$?
if [ "$RC2" -eq 0 ] && echo "$OUT2" | grep -q "VERDICT: PROVISIONED"; then
  _pass "healthy inputs -> PROVISIONED, exit 0"
else
  _fail "healthy inputs did not report PROVISIONED (rc=$RC2): $OUT2"
fi

# ─── Scenario 3: SOP ghost (below floor) -> DEGRADED ────────────────────────
_section "Scenario 3 — SOP total below floor -> DEGRADED, exit 1 (the C2 ghost class)"
DB3="$TESTHOME/mc3.db"; _mk_db "$DB3" 5 5
OUT3="$(_run_probe --min-total 10 --db "$DB3" --skills-dir "$SK2" --repo-dir "$REF2" --workspace "$WS2" 2>&1)"; RC3=$?
if [ "$RC3" -eq 1 ] && echo "$OUT3" | grep -q "\[MISS\].*SOP library" && echo "$OUT3" | grep -q "VERDICT: DEGRADED"; then
  _pass "SOP ghost (5 rows < floor 10) correctly reported DEGRADED"
else
  _fail "SOP ghost did not report DEGRADED (rc=$RC3): $OUT3"
fi

# ─── Scenario 4: zero role-library rows (converge never ran) -> DEGRADED ────
_section "Scenario 4 — total healthy but ZERO role-library rows -> DEGRADED (the C2-exact shape)"
DB4="$TESTHOME/mc4.db"; _mk_db "$DB4" 2555 0
OUT4="$(_run_probe --min-total 10 --db "$DB4" --skills-dir "$SK2" --repo-dir "$REF2" --workspace "$WS2" 2>&1)"; RC4=$?
if [ "$RC4" -eq 1 ] && echo "$OUT4" | grep -qi "\[MISS\].*SOP library"; then
  _pass "2555 total rows but 0 role-library rows still correctly reported DEGRADED (independent floors)"
else
  _fail "zero-role-library-rows case did not report DEGRADED (rc=$RC4): $OUT4"
fi

# ─── Scenario 5: skill version drift -> DEGRADED ────────────────────────────
_section "Scenario 5 — a drifted skill-version.txt -> DEGRADED, named in output"
SK5="$TESTHOME/skills5"; REF5="$TESTHOME/ref5"
mkdir -p "$SK5/41-foo" "$REF5/41-foo"
echo "1.0.0" > "$SK5/41-foo/skill-version.txt"
echo "2.0.0" > "$REF5/41-foo/skill-version.txt"
OUT5="$(_run_probe --min-total 10 --db "$DB2" --skills-dir "$SK5" --repo-dir "$REF5" --workspace "$WS2" 2>&1)"; RC5=$?
if [ "$RC5" -eq 1 ] && echo "$OUT5" | grep -q "\[MISS\].*skill versions" && echo "$OUT5" | grep -q "41-foo"; then
  _pass "skill-version drift correctly reported DEGRADED, drifted skill named"
else
  _fail "skill-version drift did not report DEGRADED with the skill named (rc=$RC5): $OUT5"
fi

# ─── Scenario 6: refresh queue still has a STALE role item -> DEGRADED ─────
# (This is the DIRECT proof this probe would have caught the pre-P2-08 gap:
# a box whose refresh-stale-roles.py never ran, or failed, still shows a
# STALE role entry queued.) ───────────────────────────────────────────────
_section "Scenario 6 — a queued STALE role item -> DEGRADED (proves this probe catches the P2-08 gap)"
WS6="$TESTHOME/ws6"; mkdir -p "$WS6"
cat > "$WS6/.artifact-refresh-queue.json" <<'EOF'
{"summary": {"stale": 1}, "items": [
  {"key": "sales/closer", "kind": "role", "status": "STALE", "built_from": "sha256:old", "current": "sha256:new"}
]}
EOF
OUT6="$(_run_probe --min-total 10 --db "$DB2" --skills-dir "$SK2" --repo-dir "$REF2" --workspace "$WS6" 2>&1)"; RC6=$?
if [ "$RC6" -eq 1 ] && echo "$OUT6" | grep -q "\[MISS\].*refresh queue" && echo "$OUT6" | grep -q "sales/closer"; then
  _pass "queued STALE role item correctly reported DEGRADED, key named"
else
  _fail "queued STALE role item did not report DEGRADED (rc=$RC6): $OUT6"
fi

# ─── Scenario 7: a queued STALE *sop* item (out of P2-08 step 2's scope) ────
# must NOT fail this check -- only kind=="role" is asserted empty. ──────────
_section "Scenario 7 — a queued STALE sop item does NOT fail the refresh-queue check (out of scope)"
WS7="$TESTHOME/ws7"; mkdir -p "$WS7"
cat > "$WS7/.artifact-refresh-queue.json" <<'EOF'
{"summary": {"stale": 1}, "items": [
  {"key": "graphics/SOP--foo", "kind": "sop", "status": "STALE", "built_from": "sha256:old", "current": "sha256:new"}
]}
EOF
OUT7="$(_run_probe --min-total 10 --db "$DB2" --skills-dir "$SK2" --repo-dir "$REF2" --workspace "$WS7" 2>&1)"; RC7=$?
if [ "$RC7" -eq 0 ] && echo "$OUT7" | grep -q "\[OK\].*refresh queue"; then
  _pass "STALE sop item correctly did NOT fail the role-scoped refresh-queue check"
else
  _fail "STALE sop item incorrectly failed the refresh-queue check (rc=$RC7): $OUT7"
fi

# ─── Scenario 8: --json emits valid JSON with expected keys ────────────────
_section "Scenario 8 — --json output is valid JSON with expected keys"
OUT8="$(_run_probe --json --min-total 10 --db "$DB2" --skills-dir "$SK2" --repo-dir "$REF2" --workspace "$WS2" 2>&1)"
if echo "$OUT8" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'sop_library' in d and 'ok' in d['sop_library']
assert 'skill_versions' in d and 'drift_count' in d['skill_versions']
assert 'refresh_queue' in d and 'stale_role_count' in d['refresh_queue']
assert d['overall_provisioned'] is True
" 2>/dev/null; then
  _pass "--json emits valid JSON with all three check sections + overall_provisioned"
else
  _fail "--json output malformed or missing expected keys: $OUT8"
fi

_section "SUMMARY"
echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
