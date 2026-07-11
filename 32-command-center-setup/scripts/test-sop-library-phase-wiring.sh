#!/usr/bin/env bash
# test-sop-library-phase-wiring.sh — regression + functional test for C2's
# Phase 6i (SOP V2 library ingestion) wiring in run-full-install.sh.
#
# THE BUG THIS GUARDS AGAINST: run-full-install.sh documented Phase 6c "SOP V2
# Library Ingestion" in INSTALL.md as automatic since v10.13.29, but the code
# never called ingest-sop-library.sh (`grep -c ingest-sop-library
# run-full-install.sh` == 0). Every fresh install therefore silently shipped
# whatever the Command Center's boot-time starter seed happened to write
# instead of the real ~2,555-row V2 library.
#
# Tests:
#   1. Static: PHASE 6i block present, unconditional (not gated behind
#      --update-only), calls ingest-sop-library.sh with the client slug,
#      posts CC converge with {"scope":"sops"}, invokes the row-count gate,
#      and reaches fail_install on the ghost path.
#   2. Static: bash -n syntax check on the full orchestrator (this phase's
#      insertion must never break the rest of the script).
#   3. Static: INSTALL.md's duplicate "Phase 6c: SOP V2 Library Ingestion"
#      heading collision is resolved (renamed 6i; only one real Phase-6c
#      heading remains -- the unrelated dashboard department sync).
#   4. FUNCTIONAL (extraction sandbox): the PHASE 6i source block is sliced
#      out of run-full-install.sh verbatim and run under a stub environment
#      (fake ingest-sop-library.sh that writes a fixture DB -- no network,
#      no live CC, no live GitHub release download) to prove the actual glue
#      -- not just grep patterns -- behaves correctly:
#        4a. Healthy fixture (2555 rows) -> fail_install is NEVER called.
#        4b. Ghost fixture (0 rows, ingest silently no-ops) -> fail_install
#            IS called with a message mentioning "EMPTY".
#        4c. Real assert-sop-library-populated.py is exercised (not a stub)
#            via the shared resolve_db.py env-var candidate, proving the
#            phase's invocation contract (no explicit --db) actually
#            resolves the DB the same way the rest of Skill 32 does.
#
# Run:  bash test-sop-library-phase-wiring.sh

set -uo pipefail
P="[test-sop-library-phase-wiring]"
PASS=0
FAIL=0
pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RFI="$SCRIPT_DIR/run-full-install.sh"
ASSERT_PY="$SCRIPT_DIR/assert-sop-library-populated.py"
INSTALL_MD="$(cd "$SCRIPT_DIR/.." && pwd)/INSTALL.md"
REPO_SHARED_UTILS="$(cd "$SCRIPT_DIR/../.." && pwd)/shared-utils"

if [[ ! -f "$RFI" ]]; then
  echo "$P FATAL: run-full-install.sh not found at $RFI" >&2
  exit 1
fi

# ─── Test 1: static wiring assertions ─────────────────────────────────────
echo "$P Test 1: static wiring in run-full-install.sh..."
if grep -q '^# PHASE 6i -- SOP V2 Library Ingestion' "$RFI"; then
  pass "PHASE 6i marker present"
else
  fail "PHASE 6i marker missing"
fi

if grep -qE 'bash "\$INGEST_SOP_SH" "\$CLIENT_SLUG"' "$RFI"; then
  pass "ingest-sop-library.sh invoked with \$CLIENT_SLUG"
else
  fail "ingest-sop-library.sh invocation with \$CLIENT_SLUG not found"
fi

if grep -q '"scope":"sops"' "$RFI"; then
  pass "CC converge call posts scope=sops"
else
  fail "converge scope=sops payload not found"
fi

if grep -qE 'python3 "\$ASSERT_SOP_PY"' "$RFI"; then
  pass "assert-sop-library-populated.py invoked"
else
  fail "row-count gate script not invoked"
fi

if grep -qE 'fail_install "phase=6i: SOP V2 library is EMPTY' "$RFI"; then
  pass "fail_install wired to the ghost (empty) condition"
else
  fail "fail_install call for the empty/ghost condition not found"
fi

# The phase must be UNCONDITIONAL (runs in both full-install and
# --update-only, matching 6b/6c/6d/6e/6f/6g) -- assert it is not nested
# inside an `if [[ "$UPDATE_ONLY" ...` guard by checking the line range
# between the 6i and 7 markers contains no such guard.
PHASE_BLOCK="$(awk '/^# PHASE 6i -- SOP V2 Library Ingestion/,/^# PHASE 7 /' "$RFI")"
if echo "$PHASE_BLOCK" | grep -q 'UPDATE_ONLY'; then
  fail "PHASE 6i block references \$UPDATE_ONLY -- should run unconditionally like its 6b-6g siblings"
else
  pass "PHASE 6i runs unconditionally (full-install AND --update-only)"
fi

# ─── Test 2: full-script syntax check ─────────────────────────────────────
echo "$P Test 2: bash -n syntax check on the full orchestrator..."
if bash -n "$RFI" 2>/tmp/rfi-syntax-err.$$; then
  pass "run-full-install.sh syntax OK with Phase 6i inserted"
else
  fail "run-full-install.sh syntax error: $(cat /tmp/rfi-syntax-err.$$)"
fi
rm -f "/tmp/rfi-syntax-err.$$"

# ─── Test 3: INSTALL.md duplicate-heading collision resolved ─────────────
echo "$P Test 3: INSTALL.md Phase 6c/6i heading reconciliation..."
if [[ -f "$INSTALL_MD" ]]; then
  # NOTE: "### Phase 6c — Make pm2 survive container restarts" is a
  # legitimate, unrelated, pre-existing heading (out of C2's scope -- left
  # untouched). Only the SOP-specific duplicate ("## Phase 6c: SOP V2
  # Library Ingestion") is the one this fix renamed to 6i.
  SIX_C_SOP_HEADINGS="$(grep -c '^## Phase 6c: SOP V2 Library Ingestion' "$INSTALL_MD" || true)"
  if [[ "$SIX_C_SOP_HEADINGS" -eq 0 ]]; then
    pass "no leftover '## Phase 6c: SOP V2 Library Ingestion' heading (renamed to 6i)"
  else
    fail "still $SIX_C_SOP_HEADINGS heading(s) matching the old duplicate 'Phase 6c: SOP...' pattern"
  fi
  if grep -q '^### Phase 6c — Make pm2 survive container restarts' "$INSTALL_MD"; then
    pass "unrelated pm2-restart 'Phase 6c' heading correctly left untouched (out of C2 scope)"
  else
    fail "unrelated pm2-restart 'Phase 6c' heading unexpectedly changed/removed (was out of scope)"
  fi
  if grep -q '^## Phase 6i: SOP V2 Library Ingestion' "$INSTALL_MD"; then
    pass "'## Phase 6i: SOP V2 Library Ingestion' heading present"
  else
    fail "'## Phase 6i: SOP V2 Library Ingestion' heading not found"
  fi
else
  fail "INSTALL.md not found at $INSTALL_MD"
fi

# ─── Test 4: functional sandbox — extract + run the real PHASE 6i snippet ─
echo "$P Test 4: functional sandbox (stubbed ingest, real row-count gate)..."
if [[ ! -f "$ASSERT_PY" ]]; then
  fail "assert-sop-library-populated.py not found -- cannot run functional sandbox"
else
  SNIPPET="$(awk '/^# PHASE 6i -- SOP V2 Library Ingestion/,/^# PHASE 7 /{ if ($0 !~ /^# PHASE 7 /) print }' "$RFI")"
  if [[ -z "$SNIPPET" ]]; then
    fail "could not extract the PHASE 6i snippet from run-full-install.sh (marker drift?)"
  else
    _run_sandbox() {
      # $1 = scenario name, $2 = row count the stub ingest writes,
      # $3 = expected fail_install behavior: "no" or "yes"
      local scenario="$1" rows="$2" expect_fail="$3"
      local SBOX FAIL_MARKER SKILL_ROOT
      SBOX="$(mktemp -d)"
      # Mirror the REAL repo depth (assert-sop-library-populated.py resolves
      # shared-utils/ via parent.parent.parent = repo root, not $SBOX itself)
      # so the shared resolve_db.py import actually succeeds in the sandbox,
      # not just in production -- a shallower fixture directory would silently
      # fall back to _HAS_SHARED_RESOLVER=False and always report "DB not
      # found" regardless of scenario, masking the real ghost/healthy paths.
      SKILL_ROOT="$SBOX/repo/32-command-center-setup"
      mkdir -p "$SKILL_ROOT/scripts" "$SKILL_ROOT/dashboard" "$SBOX/repo/shared-utils"
      FAIL_MARKER="$SBOX/fail_install_called"

      # Real row-count gate script + the real shared resolver, unmodified.
      cp "$ASSERT_PY" "$SKILL_ROOT/scripts/assert-sop-library-populated.py"
      cp "$REPO_SHARED_UTILS/resolve_db.py" "$SBOX/repo/shared-utils/resolve_db.py"

      # Stub ingest-sop-library.sh: no network, writes N rows into the DB at
      # $DASHBOARD_DB_PATH (the same env var the shared resolve_db.py honors,
      # which the real phase code never overrides with an explicit --db).
      cat > "$SKILL_ROOT/scripts/ingest-sop-library.sh" <<STUBEOF
#!/usr/bin/env bash
set -euo pipefail
CLIENT="\${1:?usage}"
python3 - "\$DASHBOARD_DB_PATH" "$rows" <<'PYEOF'
import sqlite3, sys
db_path, n = sys.argv[1], int(sys.argv[2])
conn = sqlite3.connect(db_path)
conn.execute("CREATE TABLE IF NOT EXISTS sops (id TEXT PRIMARY KEY, slug TEXT, source TEXT)")
for i in range(n):
    conn.execute("INSERT INTO sops (id, slug, source) VALUES (?, ?, ?)", (f"sop_{i}", f"slug-{i}", None))
conn.commit()
conn.close()
PYEOF
echo "[sop-library] client=\$CLIENT  tag=stub"
echo "[sop-library] downloaded $rows SOP records"
echo "[sop-library] done."
STUBEOF
      chmod +x "$SKILL_ROOT/scripts/ingest-sop-library.sh"

      # Harness: stub log/state_set/fail_install/cc_env_get (the real
      # functions this snippet calls, normally defined earlier in
      # run-full-install.sh), export the exact vars the snippet reads, no
      # STATE_FILE (so state_set branches are simply skipped -- irrelevant to
      # what this test proves), no DASHBOARD_DIR/.env.local (so the CC
      # converge HTTP attempt is skipped cleanly, never touching the
      # network) -- isolates the test to exactly: ingest -> row-count gate ->
      # fail_install decision.
      cat > "$SBOX/harness.sh" <<HARNESSEOF
#!/usr/bin/env bash
set -u
log() { :; }
state_set() { :; }
state_set_arg() { :; }
cc_env_get() { :; }
fail_install() {
  echo "FAIL_INSTALL_CALLED: \$1" > "$FAIL_MARKER"
  exit 1
}
SKILL_DIR="$SKILL_ROOT"
CLIENT_SLUG="test-client"
DASHBOARD_DIR="$SKILL_ROOT/dashboard"
DASHBOARD_PORT="1"
LOG_FILE="$SBOX/install.log"
STATE_FILE=""
export DASHBOARD_DB_PATH="$SBOX/mission-control.db"

$SNIPPET
HARNESSEOF
      bash "$SBOX/harness.sh" >"$SBOX/stdout.log" 2>&1
      local rc=$?

      if [[ "$expect_fail" == "yes" ]]; then
        if [[ -f "$FAIL_MARKER" ]] && grep -q "EMPTY" "$FAIL_MARKER"; then
          pass "$scenario: fail_install called on the ghost/empty condition (rc=$rc)"
        else
          fail "$scenario: expected fail_install (EMPTY) but marker=$( [[ -f "$FAIL_MARKER" ]] && cat "$FAIL_MARKER" || echo '<not written>' ), rc=$rc, stdout tail: $(tail -5 "$SBOX/stdout.log")"
        fi
      else
        if [[ ! -f "$FAIL_MARKER" ]]; then
          pass "$scenario: fail_install NOT called on a healthy library (rc=$rc)"
        else
          fail "$scenario: fail_install unexpectedly called: $(cat "$FAIL_MARKER"), stdout tail: $(tail -5 "$SBOX/stdout.log")"
        fi
      fi
      rm -rf "$SBOX"
    }

    _run_sandbox "4a healthy (2555 rows)" 2555 "no"
    _run_sandbox "4b ghost (0 rows -- ingest silently no-ops)" 0 "yes"
  fi
fi

# ─── Summary ────────────────────────────────────────────────────────────
echo ""
echo "$P Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
