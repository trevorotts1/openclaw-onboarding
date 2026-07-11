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
# THE BUG THE FIRST FIX SHIPPED, WHICH THIS FILE NOW ALSO GUARDS: that gate
# FAILED OPEN. ingest-sop-library.sh runs under `set -euo pipefail` and prints
# "downloaded N SOP records" only AFTER curl+gunzip succeed, so any network /
# GitHub outage / rate-limit / asset-removal / gunzip error aborted it before
# that line. The installer then parsed no count, passed NEITHER --expected NOR
# --min-total, and the gate fell back to a floor of 1 -- but CC's boot-seed
# (autoSeedStarterSOPs) has ALREADY filled `sops` by Phase 6, so the gate
# returned "healthy: 54 row(s) >= floor 1" over the exact ghost it exists to
# catch and the install stamped commandCenterSopLibraryIngested=true.
# Scenario 4c below is that exact repro, and it must now fail the install.
#
# Tests:
#   1. Static: PHASE 6i block present, unconditional (not gated behind
#      --update-only), calls ingest-sop-library.sh with the client slug,
#      posts CC converge with {"scope":"sops"}, invokes the row-count gate
#      with BOTH floors, persists the converge status, and has NO fail-open
#      (WARN-and-continue) branch left on any gate failure path.
#   2. Static: bash -n syntax check on the full orchestrator (this phase's
#      insertion must never break the rest of the script).
#   3. Static: INSTALL.md's duplicate "Phase 6c: SOP V2 Library Ingestion"
#      heading collision is resolved (renamed 6i; only one real Phase-6c
#      heading remains -- the unrelated dashboard department sync).
#   4. FUNCTIONAL (extraction sandbox): the PHASE 6i source block is sliced
#      out of run-full-install.sh verbatim and run under a stub environment
#      (fake ingest-sop-library.sh -- no network, no live CC, no live GitHub
#      release download) to prove the actual glue -- not just grep patterns --
#      behaves correctly. The real assert-sop-library-populated.py is
#      exercised (never a stub) via the shared resolve_db.py env-var
#      candidate, proving the phase's invocation contract (no explicit --db)
#      resolves the DB the same way the rest of Skill 32 does:
#        4a. Healthy: ingest writes 2555 rows + converge's 107 role-library
#            rows -> fail_install NEVER called.
#        4b. Ghost: ingest succeeds but writes 0 rows -> fail_install called.
#        4c. THE FAIL-OPEN REPRO: CC boot-seed has already written the live
#            54-row ghost (source all NULL), then ingest FAILS (rc=1, no
#            "downloaded N" line -- the network/asset failure shape). The old
#            code passed no floor and PASSED this at "floor 1".
#            fail_install MUST now be called.
#        4d. THE SPEC-MISS REPRO: ingest fully succeeds (2555 rows) but
#            converge/importRoleLibrary never lands a role-library row (the
#            live C2 shape: "ZERO role-library rows"). A bare COUNT(*) passes
#            this. fail_install MUST now be called.
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

PHASE_BLOCK="$(awk '/^# PHASE 6i -- SOP V2 Library Ingestion/,/^# PHASE 7 /' "$RFI")"

# FAIL-CLOSED: the gate must ALWAYS receive an explicit --min-total. The
# original defect was a code path that omitted it and let the script's old
# default floor of 1 rubber-stamp the boot-seed ghost.
if echo "$PHASE_BLOCK" | grep -qE '\-\-min-total "\$SOP_MIN_TOTAL"'; then
  pass "row-count gate always invoked WITH an explicit --min-total (no floorless call path)"
else
  fail "gate is not invoked with an explicit --min-total -- the fail-open rubber stamp is back"
fi

# SPEC step (2): assert role-library rows > 0, not just a bare COUNT(*).
if echo "$PHASE_BLOCK" | grep -q '\-\-min-role-library 1'; then
  pass "role-library row assert wired (--min-role-library 1)"
else
  fail "no --min-role-library assert -- a failed converge (ZERO role-library rows) would still pass"
fi

# A failed ingest must be fatal, never a degrade to a permissive floor.
if echo "$PHASE_BLOCK" | grep -q 'fail_install "phase=6i: ingest-sop-library.sh FAILED'; then
  pass "ingest rc != 0 is a HARD fail_install (never degrades to a not-empty floor)"
else
  fail "ingest failure does not fail_install -- the degraded path can still rubber-stamp a ghost"
fi

if echo "$PHASE_BLOCK" | grep -q "printed NO 'downloaded N SOP records' line"; then
  pass "unparseable download count is a HARD fail_install (no floor => no gate => fail)"
else
  fail "a missing download count does not fail_install -- the gate can still run floorless"
fi

if echo "$PHASE_BLOCK" | grep -q 'fail_install "phase=6i: SOP V2 library gate FAILED'; then
  pass "fail_install wired to EVERY non-zero gate rc"
else
  fail "no fail_install on the gate's non-zero rc"
fi

# The converge outcome must be durably recorded, not merely logged.
if echo "$PHASE_BLOCK" | grep -q 'commandCenterSopConvergeStatus'; then
  pass "converge status persisted to the state file (durable record of a miss)"
else
  fail "SOP_CONVERGE_STATUS never persisted to the state file"
fi

# NO fail-open branch may survive: the old code WARN'd + continued on rc=2
# (no mission-control.db) and on a missing gate script, both of which let an
# unverified library ship green.
if echo "$PHASE_BLOCK" | grep -qE 'SOP_ASSERT_RC" -eq 2'; then
  fail "a WARN-and-continue branch for gate rc=2 still exists -- that is a fail-open path"
else
  pass "no WARN-and-continue branch for gate rc=2 (every non-zero rc is fatal)"
fi

if echo "$PHASE_BLOCK" | grep -q 'fail_install "phase=6i: row-count gate unavailable'; then
  pass "a missing gate script / missing python3 is fatal (an unverified library never ships green)"
else
  fail "missing gate script still degrades to a WARN -- an unverified library can ship green"
fi

# A missing INGEST script is fatal too -- it ships in this same skill dir, and
# skipping it silently is the C2 ghost by another name (and was inconsistent
# with the missing-GATE-script branch, which is fatal).
if echo "$PHASE_BLOCK" | grep -q 'fail_install "phase=6i: \$INGEST_SOP_SH not found'; then
  pass "a missing ingest-sop-library.sh is fatal (never a silent skip)"
else
  fail "a missing ingest-sop-library.sh still silently skips -- the ghost ships green"
fi

# STATE CONTRACT: .commandCenterSopLibraryIngested must be a BOOLEAN on every
# path. Writing a non-empty STRING on the skip paths (the old
# "script-missing" / "no-client-slug" / "gate-script-missing" values) is a
# fail-open in disguise -- a non-empty string is TRUTHY, so every consumer
# doing `if (state.commandCenterSopLibraryIngested)` reads a SKIPPED ingest as
# a SUCCESSFUL one. Reasons belong in .commandCenterSopLibrarySkipReason.
if echo "$PHASE_BLOCK" | grep -qE 'commandCenterSopLibraryIngested = "'; then
  fail "commandCenterSopLibraryIngested is assigned a truthy STRING somewhere -- consumers will read a skip/failure as success (fail-open state contract)"
else
  pass "commandCenterSopLibraryIngested is never a truthy string (boolean-only state contract)"
fi

if echo "$PHASE_BLOCK" | grep -q 'commandCenterSopLibrarySkipReason'; then
  pass "skip/failure reasons recorded in .commandCenterSopLibrarySkipReason (not smuggled into the boolean)"
else
  fail "no .commandCenterSopLibrarySkipReason field -- skip reasons have nowhere honest to go"
fi

# The phase must be UNCONDITIONAL (runs in both full-install and
# --update-only, matching 6b/6c/6d/6e/6f/6g).
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
      # $1 scenario name
      # $2 rows the stub ingest writes (source NULL -- the JSONL-asset writer)
      # $3 role-library rows the stub writes (stands in for CC converge ->
      #    importRoleLibrary(), which cannot run in a sandbox: no live CC)
      # $4 stub ingest exit code (non-zero => it also prints NO "downloaded"
      #    line, exactly like the real `set -euo pipefail` script aborting on
      #    a curl/gunzip failure)
      # $5 rows the CC boot-seed (autoSeedStarterSOPs) already wrote BEFORE
      #    this phase runs -- source NULL, the live ghost
      # $6 expected fail_install: "no" or "yes"
      local scenario="$1" rows="$2" role_rows="$3" ingest_rc="$4" bootseed="$5" expect_fail="$6"
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

      # CC boot-seed: autoSeedStarterSOPs has ALREADY run (CC booted in Phase
      # 6), so `sops` is NEVER empty by the time this phase's gate runs. This
      # is the fact that turned "just check it's not empty" into a rubber stamp.
      python3 - "$SBOX/mission-control.db" "$bootseed" <<'PYEOF'
import sqlite3, sys
db_path, n = sys.argv[1], int(sys.argv[2])
conn = sqlite3.connect(db_path)
conn.execute("CREATE TABLE IF NOT EXISTS sops (id TEXT PRIMARY KEY, slug TEXT, source TEXT)")
for i in range(n):
    conn.execute("INSERT OR REPLACE INTO sops (id, slug, source) VALUES (?, ?, ?)",
                 (f"bootseed_{i}", f"bootseed-{i}", None))
conn.commit()
conn.close()
PYEOF

      # Stub ingest-sop-library.sh: no network. On rc=0 it writes N JSONL rows
      # (source NULL) + M role-library rows and prints the real script's
      # "downloaded N SOP records" contract line. On rc!=0 it prints NOTHING of
      # the sort and dies -- mirroring `set -euo pipefail` aborting at curl.
      cat > "$SKILL_ROOT/scripts/ingest-sop-library.sh" <<STUBEOF
#!/usr/bin/env bash
set -euo pipefail
CLIENT="\${1:?usage}"
echo "[sop-library] client=\$CLIENT  tag=stub"
echo "[sop-library] downloading https://example.invalid/sops-library-v2.jsonl.gz"
if [[ "$ingest_rc" -ne 0 ]]; then
  echo "curl: (22) The requested URL returned error: 404" >&2
  exit $ingest_rc
fi
python3 - "\$DASHBOARD_DB_PATH" "$rows" "$role_rows" <<'PYEOF'
import sqlite3, sys
db_path, n, role_n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
conn = sqlite3.connect(db_path)
conn.execute("CREATE TABLE IF NOT EXISTS sops (id TEXT PRIMARY KEY, slug TEXT, source TEXT)")
for i in range(n):
    conn.execute("INSERT OR REPLACE INTO sops (id, slug, source) VALUES (?, ?, ?)",
                 (f"sop_{i}", f"slug-{i}", None))
for i in range(role_n):
    conn.execute("INSERT OR REPLACE INTO sops (id, slug, source) VALUES (?, ?, ?)",
                 (f"role_{i}", f"role-{i}", "role-library"))
conn.commit()
conn.close()
PYEOF
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
        if [[ -f "$FAIL_MARKER" ]]; then
          pass "$scenario: fail_install called (rc=$rc) -- $(head -c 120 "$FAIL_MARKER")..."
        else
          fail "$scenario: expected fail_install but it was NEVER called (rc=$rc) -- THIS IS A FAIL-OPEN GATE. stdout tail: $(tail -3 "$SBOX/stdout.log")"
        fi
      else
        if [[ ! -f "$FAIL_MARKER" ]]; then
          pass "$scenario: fail_install NOT called on a healthy library (rc=$rc)"
        else
          fail "$scenario: fail_install unexpectedly called: $(cat "$FAIL_MARKER"), stdout tail: $(tail -3 "$SBOX/stdout.log")"
        fi
      fi
      rm -rf "$SBOX"
    }

    #            scenario                                        rows  role  irc  boot  expect_fail
    _run_sandbox "4a healthy (2555 rows + 107 role-library)"      2555  107   0    54    "no"
    _run_sandbox "4b ghost (ingest ok, writes 0 rows)"            0     0     0    0     "yes"
    _run_sandbox "4c FAIL-OPEN REPRO (ingest FAILS, 54 boot-seed rows already present)" \
                                                                  0     0     1    54    "yes"
    _run_sandbox "4d SPEC-MISS REPRO (ingest ok 2555, ZERO role-library rows)" \
                                                                  2555  0     0    54    "yes"
  fi
fi

# ─── Summary ────────────────────────────────────────────────────────────
echo ""
echo "$P Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
