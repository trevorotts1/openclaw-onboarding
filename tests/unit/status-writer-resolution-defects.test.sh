#!/usr/bin/env bash
# status-writer-resolution-defects.test.sh
#
# refresh-build-state-from-index.py is the ONE place `status:"done"` is written
# per department (references/DONE-IS-GATED.md). Four defects, each verified on
# a real client box, made this writer measure or mutate the WRONG thing:
#
#   A. WRONG COLLECTION. The upsert loop iterated _index.json (the canonical
#      role catalog), not the client's own department set. On a client with a
#      custom company tree, their real departments were never visited (stayed
#      "pending" forever) while every generic canonical department got ADDED
#      to their roster.
#   B. WRONG TREE. find_departments_dir() offered only
#      workspace/agents/main/departments and workspace/departments -- no
#      zero-human-company/<companySlug>/departments candidate. A stray
#      single-role legacy directory won by being first-checked, and every real
#      department measured 0 roles.
#   C. WORKSPACE-ROOT KEY UNRELIABLE. .workspaceRoot is not written on every
#      build path. Resolution must not depend on it being present or correct.
#   D. SUFFIX MISMATCH. Department dirs on disk sometimes carry a "-dept"
#      suffix ("trading-operations-dept") the slug ("trading-operations") does
#      not. A bare path join silently measured 0 roles.
#
# Each scenario below runs the SAME fixture through the PRE-FIX script
# (REFRESH_PRE, defaulting to the origin/main copy fetched by the caller) and
# the POST-FIX script (REFRESH_POST, defaulting to the copy next to this
# file), and asserts the defect reproduces pre-fix and is gone post-fix. A
# script that only ever runs post-fix code proves nothing; this proves the
# fix by showing the flip.
#
# HERMETIC: every path this drives resolves inside $FIXTURE_ROOT. HOME is
# redirected into the fixture for the duration of each subprocess call, and
# the suite refuses to run at all if /data/.openclaw exists on this host (that
# candidate is hardcoded ahead of any HOME override and cannot be redirected).
# No client box, no real ~/.openclaw, no network.
#
# USAGE:
#   bash tests/unit/status-writer-resolution-defects.test.sh
#   REFRESH_PRE=/path/to/pre-fix-copy.py bash tests/unit/status-writer-resolution-defects.test.sh
# EXIT: 0 = all assertions pass, 1 = one or more failed.

set -uo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
TESTS_DIR="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

REFRESH_POST="${REFRESH_POST:-$REPO_ROOT/23-ai-workforce-blueprint/scripts/refresh-build-state-from-index.py}"

PASS=0
FAIL=0
ok()  { echo "  PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }

# ---- preconditions -------------------------------------------------------
for _bin in jq python3; do
  command -v "$_bin" >/dev/null 2>&1 || { echo "SKIP: $_bin not installed" >&2; exit 0; }
done
[[ -f "$REFRESH_POST" ]] || { echo "FATAL: post-fix script not found at $REFRESH_POST" >&2; exit 1; }

# REFRESH_PRE lets a reviewer point this suite at the pre-fix copy from
# origin/main to confirm these assertions genuinely fail before the fix and
# pass after it. If not supplied, fetch it from origin/main via git (falls
# back to SKIP-ing the before/after comparison, running post-fix only, if git
# or the ref is unavailable -- the post-fix assertions still run and matter).
_TMP_PRE=""
cleanup_pre() { [[ -n "$_TMP_PRE" && -f "$_TMP_PRE" ]] && rm -f "$_TMP_PRE"; }
trap cleanup_pre EXIT

if [[ -n "${REFRESH_PRE:-}" ]]; then
  : # caller-supplied
elif command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --verify origin/main >/dev/null 2>&1; then
  _TMP_PRE="$(mktemp "${TMPDIR:-/tmp}/refresh-pre-fix.XXXXXX.py")"
  if git -C "$REPO_ROOT" show origin/main:23-ai-workforce-blueprint/scripts/refresh-build-state-from-index.py > "$_TMP_PRE" 2>/dev/null \
     && [[ -s "$_TMP_PRE" ]]; then
    REFRESH_PRE="$_TMP_PRE"
  else
    REFRESH_PRE=""
  fi
else
  REFRESH_PRE=""
fi

if [[ -z "${REFRESH_PRE:-}" ]]; then
  echo "WARN: no pre-fix copy available (git origin/main unreachable) -- running POST-FIX assertions only, before/after comparison skipped" >&2
fi

# HERMETIC GUARD: refresh-build-state-from-index.py checks /data/.openclaw
# BEFORE $HOME/.openclaw, and that candidate cannot be redirected by a HOME
# override. If it exists on this host, refuse to run rather than risk it.
if [[ -d /data/.openclaw ]]; then
  echo "FATAL: /data/.openclaw exists -- the script would resolve there and a HOME" >&2
  echo "       override cannot redirect it. Refusing to run to protect a live workspace." >&2
  exit 1
fi

FIXTURE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/status-writer-fixture.XXXXXX")"
cleanup_all() { cleanup_pre; [[ -n "${FIXTURE_ROOT:-}" && -d "$FIXTURE_ROOT" ]] && rm -rf "$FIXTURE_ROOT"; }
trap cleanup_all EXIT

FIX_HOME="$FIXTURE_ROOT/home"
OC="$FIX_HOME/.openclaw"
WS="$OC/workspace"
STATE="$WS/.workforce-build-state.json"
INDEX="$FIXTURE_ROOT/_index.json"

reset_fixture() {
  rm -rf "$FIXTURE_ROOT"
  mkdir -p "$WS"
}

# how_to <path> — any non-empty how-to.md with no [PENDING marker (this
# script's count_roles_on_disk() has no size floor, unlike verify-wiring.sh).
how_to() {
  mkdir -p "$(dirname "$1")"
  printf '# Role how-to\n\nThis role executes its standard operating procedure deterministically.\n' > "$1"
}

# run_refresh <script> <extra-args...> — invoke under test with HOME
# redirected into the fixture and both file-path overrides set. Captures
# stdout+stderr to $FIXTURE_ROOT/last.log and returns the script's exit code.
run_refresh() {
  local script="$1"; shift
  HOME="$FIX_HOME" \
  WORKFORCE_INDEX_PATH="$INDEX" \
  WORKFORCE_BUILD_STATE_PATH="$STATE" \
    python3 "$script" "$@" > "$FIXTURE_ROOT/last.log" 2>&1
  echo $?
}

jget() { python3 -c "import json,sys; d=json.load(open('$STATE')); print(json.dumps(eval('d$1', {'d': d})))" 2>/dev/null; }

# ==============================================================================
# SCENARIO 1 (DEFECT A + B): a client with a CUSTOM company tree. Real
# departments live under clawd/zero-human-company/<companySlug>/departments/,
# one of which ("widget-fabrication") is NOT in the canonical index at all.
# Assert: post-fix, both are MEASURED and NO generic canonical department is
# added to the client's roster. Pre-fix: the custom tree is never found (both
# depts measure 0 roles) AND every other canonical department gets ADDED.
# ==============================================================================
echo "=== SCENARIO 1: custom-company tree (DEFECT A + B) ==="

build_scenario1() {
  reset_fixture
  cat > "$INDEX" <<'EOF'
{
  "total_roles": 9,
  "departments": {
    "sales": {"roles": ["sales-director", "sales-rep"]},
    "marketing": {"roles": ["marketing-director", "marketing-analyst"]},
    "hr": {"roles": ["hr-director", "hr-generalist"]},
    "finance": {"roles": ["finance-director", "finance-analyst"]},
    "operations": {"roles": ["ops-director"]}
  }
}
EOF
  cat > "$STATE" <<'EOF'
{
  "companySlug": "acme-custom",
  "departments": {
    "sales": {"slug": "sales", "name": "Sales", "status": "building", "rolesPlanned": 0, "rolesDone": 0, "roleLibraryFilled": false, "sopLibraryFilled": false, "wiringStatus": "pending"},
    "widget-fabrication": {"slug": "widget-fabrication", "name": "Widget Fabrication", "status": "building", "rolesPlanned": 2, "rolesDone": 0, "roleLibraryFilled": false, "sopLibraryFilled": false, "wiringStatus": "pending"}
  },
  "totalRoles": 0,
  "totalDepartments": 0
}
EOF
  # Real departments live ONLY under the custom-company tree -- nothing under
  # the legacy workspace/departments or workspace/agents/main/departments
  # trees a fixed-candidate guess would have checked.
  how_to "$FIX_HOME/clawd/zero-human-company/acme-custom/departments/sales/sales-director/how-to.md"
  how_to "$FIX_HOME/clawd/zero-human-company/acme-custom/departments/sales/sales-rep/how-to.md"
  how_to "$FIX_HOME/clawd/zero-human-company/acme-custom/departments/widget-fabrication/fab-lead/how-to.md"
  how_to "$FIX_HOME/clawd/zero-human-company/acme-custom/departments/widget-fabrication/fab-tech/how-to.md"
}

if [[ -n "${REFRESH_PRE:-}" ]]; then
  build_scenario1
  run_refresh "$REFRESH_PRE" --strict >/dev/null
  _pre_count=$(jget "['departments'].keys().__len__()" 2>/dev/null || python3 -c "import json; print(len(json.load(open('$STATE'))['departments']))")
  _pre_sales_roles=$(python3 -c "import json; print(json.load(open('$STATE'))['departments']['sales']['rolesDone'])")
  if [[ "$_pre_count" -gt 2 ]]; then
    ok "PRE-FIX reproduces DEFECT A: generic canonical department(s) were added (count=$_pre_count, want >2)"
  else
    bad "PRE-FIX did not reproduce DEFECT A (count=$_pre_count, expected >2 -- premise may have changed)"
  fi
  if [[ "$_pre_sales_roles" == "0" ]]; then
    ok "PRE-FIX reproduces DEFECT B: custom-company tree never found (sales rolesDone=0)"
  else
    bad "PRE-FIX did not reproduce DEFECT B (sales rolesDone=$_pre_sales_roles, expected 0)"
  fi
fi

build_scenario1
_rc1=$(run_refresh "$REFRESH_POST" --strict)
if [[ "$_rc1" != "0" ]]; then
  bad "POST-FIX scenario 1 run failed (rc=$_rc1); log:"; sed 's/^/    /' "$FIXTURE_ROOT/last.log" >&2
else
  _post_count=$(python3 -c "import json; print(len(json.load(open('$STATE'))['departments']))")
  _post_keys=$(python3 -c "import json; print(','.join(sorted(json.load(open('$STATE'))['departments'].keys())))")
  _post_sales=$(python3 -c "import json; print(json.load(open('$STATE'))['departments']['sales']['rolesDone'])")
  _post_widget=$(python3 -c "import json; print(json.load(open('$STATE'))['departments']['widget-fabrication']['rolesDone'])")
  _post_widget_planned=$(python3 -c "import json; print(json.load(open('$STATE'))['departments']['widget-fabrication']['rolesPlanned'])")

  if [[ "$_post_count" == "2" && "$_post_keys" == "sales,widget-fabrication" ]]; then
    ok "POST-FIX: NO generic canonical department added (departments = {sales, widget-fabrication} exactly)"
  else
    bad "POST-FIX: roster changed unexpectedly (count=$_post_count, keys=$_post_keys)"
  fi
  if [[ "$_post_sales" == "2" ]]; then
    ok "POST-FIX: canonical dept 'sales' measured from the custom-company tree (rolesDone=2)"
  else
    bad "POST-FIX: 'sales' rolesDone=$_post_sales (want 2)"
  fi
  if [[ "$_post_widget" == "2" ]]; then
    ok "POST-FIX: CUSTOM (non-canonical) dept 'widget-fabrication' is ALSO measured (rolesDone=2)"
  else
    bad "POST-FIX: 'widget-fabrication' rolesDone=$_post_widget (want 2)"
  fi
  if [[ "$_post_widget_planned" == "2" ]]; then
    ok "POST-FIX: custom dept's rolesPlanned preserved (not zeroed by the absent index entry)"
  else
    bad "POST-FIX: 'widget-fabrication' rolesPlanned=$_post_widget_planned (want 2, preserved)"
  fi
fi

# ==============================================================================
# SCENARIO 2 (DEFECT D): department stored on disk with a "-dept" suffix the
# slug does not carry. Tree resolution itself is unambiguous (single legacy
# candidate); only the per-department directory match is under test.
# ==============================================================================
echo ""
echo "=== SCENARIO 2: '-dept' suffix mismatch (DEFECT D) ==="

build_scenario2() {
  reset_fixture
  cat > "$INDEX" <<'EOF'
{
  "total_roles": 2,
  "departments": {
    "trading-operations": {"roles": ["trading-director", "trader"]}
  }
}
EOF
  cat > "$STATE" <<'EOF'
{
  "departments": {
    "trading-operations": {"slug": "trading-operations", "name": "Trading Operations", "status": "building", "rolesPlanned": 0, "rolesDone": 0, "roleLibraryFilled": false, "sopLibraryFilled": false, "wiringStatus": "pending"}
  },
  "totalRoles": 0,
  "totalDepartments": 0
}
EOF
  # On-disk directory carries the "-dept" suffix; the slug does not.
  how_to "$WS/departments/trading-operations-dept/trading-director/how-to.md"
  how_to "$WS/departments/trading-operations-dept/trader/how-to.md"
}

if [[ -n "${REFRESH_PRE:-}" ]]; then
  build_scenario2
  run_refresh "$REFRESH_PRE" --strict >/dev/null
  _pre_roles=$(python3 -c "import json; print(json.load(open('$STATE'))['departments']['trading-operations']['rolesDone'])")
  if [[ "$_pre_roles" == "0" ]]; then
    ok "PRE-FIX reproduces DEFECT D: '-dept' suffixed dir not matched (rolesDone=0)"
  else
    bad "PRE-FIX did not reproduce DEFECT D (rolesDone=$_pre_roles, expected 0 -- premise may have changed)"
  fi
fi

build_scenario2
_rc2=$(run_refresh "$REFRESH_POST" --strict)
if [[ "$_rc2" != "0" ]]; then
  bad "POST-FIX scenario 2 run failed (rc=$_rc2); log:"; sed 's/^/    /' "$FIXTURE_ROOT/last.log" >&2
else
  _post_roles=$(python3 -c "import json; print(json.load(open('$STATE'))['departments']['trading-operations']['rolesDone'])")
  if [[ "$_post_roles" == "2" ]]; then
    ok "POST-FIX: '-dept' suffixed directory matched, both roles measured (rolesDone=2)"
  else
    bad "POST-FIX: 'trading-operations' rolesDone=$_post_roles (want 2)"
  fi
fi

# ==============================================================================
# SCENARIO 3 (DEFECT B/C — ambiguity): two DISTINCT real trees both contain
# the client's full department set with an EQUAL score. Assert the script
# refuses to guess (fails loudly, no state write) rather than silently
# measuring whichever tree its fixed candidate order happened to check first.
# ==============================================================================
echo ""
echo "=== SCENARIO 3: ambiguous departments tree (fail loud, never guess) ==="

build_scenario3() {
  reset_fixture
  cat > "$INDEX" <<'EOF'
{
  "total_roles": 3,
  "departments": {
    "sales": {"roles": ["sales-director", "sales-rep"]},
    "ops": {"roles": ["ops-director"]}
  }
}
EOF
  cat > "$STATE" <<'EOF'
{
  "departments": {
    "sales": {"slug": "sales", "name": "Sales", "status": "building", "rolesPlanned": 0, "rolesDone": 0, "roleLibraryFilled": false, "sopLibraryFilled": false, "wiringStatus": "pending"},
    "ops": {"slug": "ops", "name": "Operations", "status": "building", "rolesPlanned": 0, "rolesDone": 0, "roleLibraryFilled": false, "sopLibraryFilled": false, "wiringStatus": "pending"}
  },
  "totalRoles": 0,
  "totalDepartments": 0
}
EOF
  # Tree X: the legacy standard candidate.
  how_to "$WS/departments/sales/sales-director/how-to.md"
  how_to "$WS/departments/sales/sales-rep/how-to.md"
  how_to "$WS/departments/ops/ops-director/how-to.md"
  # Tree Y: an UNRELATED zero-human-company company dir that happens to carry
  # the SAME two department slugs with real content -- genuinely ambiguous;
  # nothing (no .workspaceRoot, no .companySlug, no openclaw.json) picks a
  # side.
  how_to "$FIX_HOME/clawd/zero-human-company/some-other-co/departments/sales/sales-director/how-to.md"
  how_to "$FIX_HOME/clawd/zero-human-company/some-other-co/departments/sales/sales-rep/how-to.md"
  how_to "$FIX_HOME/clawd/zero-human-company/some-other-co/departments/ops/ops-director/how-to.md"
}

if [[ -n "${REFRESH_PRE:-}" ]]; then
  build_scenario3
  _pre_state_before="$(cat "$STATE")"
  _pre_rc3=$(run_refresh "$REFRESH_PRE" --strict)
  if [[ "$_pre_rc3" == "0" ]]; then
    ok "PRE-FIX reproduces the guessing defect: exits 0 (silently picked ONE of two equally-valid trees, no warning)"
  else
    bad "PRE-FIX did not reproduce the guessing defect (rc=$_pre_rc3, expected 0 -- premise may have changed)"
  fi
fi

build_scenario3
_state_before="$(cat "$STATE")"
_rc3=$(run_refresh "$REFRESH_POST" --strict)
_state_after="$(cat "$STATE")"
if [[ "$_rc3" != "0" ]]; then
  ok "POST-FIX: ambiguous resolution FAILS LOUD (rc=$_rc3, nonzero)"
else
  bad "POST-FIX: ambiguous resolution did NOT fail (rc=0) -- it silently guessed"
fi
if grep -qi "ambiguous\|refusing to guess" "$FIXTURE_ROOT/last.log"; then
  ok "POST-FIX: FATAL message names the ambiguity ('ambiguous' / 'refusing to guess')"
else
  bad "POST-FIX: FATAL output does not explain the ambiguity; log:"; sed 's/^/    /' "$FIXTURE_ROOT/last.log" >&2
fi
if [[ "$_state_before" == "$_state_after" ]]; then
  ok "POST-FIX: build-state left byte-identical -- no corrupted/partial write on an ambiguous resolution"
else
  bad "POST-FIX: build-state was modified despite refusing to resolve a tree (corruption risk)"
fi

# ==============================================================================
# SCENARIO 4 (non-regression): the STANDARD case -- no custom tree, no suffix
# drift, single unambiguous candidate. Pre-fix and post-fix must agree
# EXACTLY; this fix must never change behavior for the common case.
# ==============================================================================
echo ""
echo "=== SCENARIO 4: standard case is unchanged (non-regression) ==="

build_scenario4() {
  reset_fixture
  cat > "$INDEX" <<'EOF'
{
  "total_roles": 3,
  "departments": {
    "sales": {"roles": ["sales-director", "sales-rep"]},
    "ops": {"roles": ["ops-director"]}
  }
}
EOF
  cat > "$STATE" <<'EOF'
{
  "departments": {
    "sales": {"slug": "sales", "name": "Sales", "status": "building", "rolesPlanned": 0, "rolesDone": 0, "roleLibraryFilled": false, "sopLibraryFilled": false, "wiringStatus": "pending"},
    "ops": {"slug": "ops", "name": "Operations", "status": "building", "rolesPlanned": 0, "rolesDone": 0, "roleLibraryFilled": false, "sopLibraryFilled": false, "wiringStatus": "pending"}
  },
  "totalRoles": 0,
  "totalDepartments": 0
}
EOF
  how_to "$WS/departments/sales/sales-director/how-to.md"
  how_to "$WS/departments/sales/sales-rep/how-to.md"
  how_to "$WS/departments/ops/ops-director/how-to.md"
}

if [[ -n "${REFRESH_PRE:-}" ]]; then
  build_scenario4
  run_refresh "$REFRESH_PRE" --strict >/dev/null
  _pre_sales=$(python3 -c "import json; print(json.load(open('$STATE'))['departments']['sales']['rolesDone'])")
  _pre_ops=$(python3 -c "import json; print(json.load(open('$STATE'))['departments']['ops']['rolesDone'])")

  build_scenario4
  run_refresh "$REFRESH_POST" --strict >/dev/null
  _post_sales=$(python3 -c "import json; print(json.load(open('$STATE'))['departments']['sales']['rolesDone'])")
  _post_ops=$(python3 -c "import json; print(json.load(open('$STATE'))['departments']['ops']['rolesDone'])")

  if [[ "$_pre_sales" == "$_post_sales" && "$_pre_ops" == "$_post_ops" && "$_post_sales" == "2" && "$_post_ops" == "1" ]]; then
    ok "standard case unchanged: pre-fix and post-fix agree exactly (sales=2, ops=1)"
  else
    bad "standard case DIVERGED: pre(sales=$_pre_sales,ops=$_pre_ops) vs post(sales=$_post_sales,ops=$_post_ops)"
  fi
else
  build_scenario4
  run_refresh "$REFRESH_POST" --strict >/dev/null
  _post_sales=$(python3 -c "import json; print(json.load(open('$STATE'))['departments']['sales']['rolesDone'])")
  _post_ops=$(python3 -c "import json; print(json.load(open('$STATE'))['departments']['ops']['rolesDone'])")
  if [[ "$_post_sales" == "2" && "$_post_ops" == "1" ]]; then
    ok "standard case measures correctly post-fix (sales=2, ops=1) [pre-fix comparison skipped]"
  else
    bad "standard case post-fix wrong: sales=$_post_sales, ops=$_post_ops"
  fi
fi

echo ""
echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] && { echo "ALL STATUS-WRITER RESOLUTION TESTS PASSED"; exit 0; } || { echo "STATUS-WRITER RESOLUTION TEST FAILURES"; exit 1; }
