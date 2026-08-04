#!/usr/bin/env bash
# test-wiring-gate-role-dir-walk.sh — regression suite for verify-wiring.sh v1.0.6/v1.0.7
#
# Covers the two assertions that made the wiring gate unpassable, and the
# anti-regression cases that prove the fix did NOT loosen the gate.
#
#   A. MATERIALIZED must not count a department's RUNTIME/ARTIFACT subdirectories
#      as roles. memory/ and devils-advocate/ are created for EVERY department by
#      build-workforce.create_department_workspace(); scripts/ and
#      conversational-logs/ appear on real boxes. None has a how-to.md, so the
#      pre-fix walker failed every department with rc=2 — and only a passing
#      wiring gate may mark a department or the build done.
#
#   B. REACHABLE must not demand a Director/Head/Lead/Architect/Chief role from a
#      department whose OWN canonical roster defines none. Two canonical
#      departments are in that position: master-orchestrator ("Single Occupant —
#      No Sub-Roles") and bugs (3 flat specialists, the intake clerk is the
#      entry point).
#
#   E. STUB DETECTION must key on the signatures the stub WRITERS emit, not on the
#      bare substring "[PENDING" — which is also a substring of AUTHORED PROSE that
#      canonical templates ship ("`[PENDING]` markers in live content"). Section E
#      proves the predicate in BOTH directions: E1 every stub form the repo can write
#      is still caught, E2 every prose form the repo ships is ignored, E3 the shipped
#      library itself carries prose hits and zero real stub signatures.
#
#   ANTI-REGRESSION (must still FAIL):
#      - a real role folder with a thin how-to.md            -> rc 2
#      - a real role folder with a [PENDING] how-to.md       -> rc 2
#      - a role folder whose name merely CONTAINS a non-role
#        word (16-devils-advocate-marketing) is still a role -> rc 2
#      - a department with no director-class role that is NOT
#        in the entry-point override map                     -> rc 4
#      - an override department MISSING its declared entry
#        point folder (proves rename, not bypass)            -> rc 4
#
# HERMETIC: every path this drives resolves inside $FIXTURE_ROOT. The suite
# ASSERTS that before it runs the gate even once — verify-wiring.sh resolves its
# OpenClaw root as /data/.openclaw else $HOME/.openclaw, so HOME is redirected
# into the fixture and the run aborts if /data/.openclaw exists on this host.
# No client box, no ~/.openclaw, no network.
#
# USAGE: bash test-wiring-gate-role-dir-walk.sh
# EXIT:  0 = all assertions pass, 1 = one or more failed

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# WIRING_GATE_UNDER_TEST lets a reviewer point this suite at a DIFFERENT copy of
# the gate — specifically the pre-fix copy from origin/main — to confirm these
# assertions genuinely fail before the fix and pass after it. Defaults to the
# gate sitting next to this file.
GATE="${WIRING_GATE_UNDER_TEST:-$SCRIPT_DIR/verify-wiring.sh}"

PASS=0
FAIL=0

ok()   { echo "  PASS: $1"; PASS=$((PASS + 1)); }
bad()  { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }

# ---- preconditions -----------------------------------------------------------
for _bin in jq python3; do
  command -v "$_bin" >/dev/null 2>&1 || { echo "SKIP: $_bin not installed" >&2; exit 0; }
done
[[ -f "$GATE" ]] || { echo "FATAL: gate not found at $GATE" >&2; exit 1; }

# HERMETIC GUARD 1: verify-wiring.sh prefers /data/.openclaw over $HOME/.openclaw.
# If /data/.openclaw exists we cannot contain the run with a HOME override, so we
# refuse to run rather than risk touching a real workspace.
if [[ -d /data/.openclaw ]]; then
  echo "FATAL: /data/.openclaw exists — the gate would resolve there and a HOME" >&2
  echo "       override cannot redirect it. Refusing to run to protect a live workspace." >&2
  exit 1
fi

FIXTURE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/wiring-gate-fixture.XXXXXX")"
cleanup() { [[ -n "${FIXTURE_ROOT:-}" && -d "$FIXTURE_ROOT" ]] && rm -rf "$FIXTURE_ROOT"; }
trap cleanup EXIT

# ---- fixture builder ---------------------------------------------------------
# Builds a self-contained OpenClaw root + workspace under $FIXTURE_ROOT/home.
FIX_HOME="$FIXTURE_ROOT/home"
OC="$FIX_HOME/.openclaw"
WS="$OC/workspace"
DEPTS="$WS/departments"

reset_fixture() {
  rm -rf "$FIX_HOME"
  mkdir -p "$OC/agents" "$DEPTS"
  printf '%s\n' '{"agents":{"list":[]}}' > "$OC/openclaw.json"
  printf '%s\n' "{\"workspaceRoot\":\"$WS\",\"departments\":[]}" > "$WS/.workforce-build-state.json"
}

# substantive_how_to <path> — a how-to.md that clears HOW_TO_MIN_BYTES (3072 B)
# and carries no [PENDING marker.
substantive_how_to() {
  { printf '# Role how-to\n\n## Section 9 SOPs\n'
    # ~4 KB of filler; content is irrelevant, only size + absence of [PENDING.
    for _i in $(seq 1 60); do
      printf 'This role executes its standard operating procedure deterministically. '
      printf 'Step %s is recorded in the department activity log for audit.\n' "$_i"
    done
  } > "$1"
}

# add_dept <slug> — register a department (state + config + runtime agent dir).
add_dept() {
  local slug="$1"
  mkdir -p "$DEPTS/$slug" "$OC/agents/dept-$slug"
  local tmp
  tmp="$(mktemp)"
  jq --arg s "$slug" '.departments += [{"id":$s}]' \
    "$WS/.workforce-build-state.json" > "$tmp" && mv "$tmp" "$WS/.workforce-build-state.json"
  tmp="$(mktemp)"
  jq --arg id "dept-$slug" --arg wsp "$DEPTS/$slug" \
    '.agents.list += [{"id":$id,"workspace":$wsp}]' \
    "$OC/openclaw.json" > "$tmp" && mv "$tmp" "$OC/openclaw.json"
}

# set_agent_workspace <slug> <path> — point the registered agent at <path>.
# The REGISTERED assertion checks that openclaw.json's workspace path resolves on
# disk; that is orthogonal to the tree-resolution and suffix cases below, so the
# fixture keeps it truthful rather than letting it mask what is under test.
set_agent_workspace() {
  local tmp
  tmp="$(mktemp)"
  jq --arg id "dept-$1" --arg wsp "$2" \
    '.agents.list |= map(if .id == $id then .workspace = $wsp else . end)' \
    "$OC/openclaw.json" > "$tmp" && mv "$tmp" "$OC/openclaw.json"
}

# add_role <slug> <folder> — a materialized role with a substantive how-to.md.
add_role() {
  mkdir -p "$DEPTS/$1/$2"
  substantive_how_to "$DEPTS/$1/$2/how-to.md"
}

# add_runtime_dirs <slug> — exactly what create_department_workspace() and the
# runtime leave inside a department directory.
add_runtime_dirs() {
  local slug="$1"
  mkdir -p "$DEPTS/$slug/memory" \
           "$DEPTS/$slug/devils-advocate" \
           "$DEPTS/$slug/conversational-logs" \
           "$DEPTS/$slug/scripts"
  printf '# Devil'"'"'s Advocate SOUL\n' > "$DEPTS/$slug/devils-advocate/SOUL.md"
  printf '# Devil'"'"'s Advocate SOP\n'  > "$DEPTS/$slug/devils-advocate/SOP.md"
  printf 'log\n' > "$DEPTS/$slug/conversational-logs/contact-1__x.md"
  printf '#!/bin/sh\n' > "$DEPTS/$slug/scripts/build.sh"
}

# run_gate <dept> — sets the globals GATE_RC and GATE_OUT.
# Deliberately NOT called via $(...): command substitution runs in a subshell, so
# any global set inside it is discarded and every later `grep $GATE_OUT` assertion
# would silently test an empty string.
GATE_OUT=""
GATE_RC=""
run_gate() {
  local dept="$1"
  # HERMETIC GUARD 2: assert the resolved root is inside the fixture before running.
  case "$OC" in
    "$FIXTURE_ROOT"/*) : ;;
    *) echo "FATAL: resolved OpenClaw root $OC is outside $FIXTURE_ROOT" >&2; exit 1 ;;
  esac
  HOME="$FIX_HOME" bash "$GATE" --dept "$dept" > "$FIXTURE_ROOT/gate-out.txt" 2>&1
  GATE_RC=$?
  GATE_OUT="$(cat "$FIXTURE_ROOT/gate-out.txt")"
}

expect_rc() {
  local label="$1" want="$2"
  if [[ "$GATE_RC" == "$want" ]]; then
    ok "$label (rc=$GATE_RC)"
  else
    bad "$label — expected rc=$want, got rc=$GATE_RC"
    printf '%s\n' "$GATE_OUT" | sed 's/^/        | /' >&2
  fi
}

# gate_says <needle> <label> — assert the gate's output contains a literal string.
gate_says() {
  if printf '%s' "$GATE_OUT" | grep -qF -- "$1"; then
    ok "$2"
  else
    bad "$2 — output did not contain: $1"
    printf '%s\n' "$GATE_OUT" | sed 's/^/        | /' >&2
  fi
}

echo "=============================================================="
echo "verify-wiring.sh role-dir walk + reachability regression suite"
echo "fixture: $FIXTURE_ROOT"
echo "=============================================================="

# --- HERMETIC SELF-CHECK ------------------------------------------------------
echo ""
echo "[0] hermetic containment"
reset_fixture
if [[ -d "$OC" && "$OC" == "$FIXTURE_ROOT"/* ]]; then
  ok "OpenClaw root resolves inside the fixture ($OC)"
else
  bad "OpenClaw root did not resolve inside the fixture"
fi
_real_oc="$HOME/.openclaw"
_before=""
[[ -d "$_real_oc" ]] && _before="$(ls -A "$_real_oc" 2>/dev/null | sort | md5 2>/dev/null || ls -A "$_real_oc" | sort | md5sum)"

# A healthy baseline department: a director-class role (so REACHABLE is satisfied
# and is NOT the variable under test) plus one specialist.
healthy_dept() {
  local slug="$1"
  add_dept "$slug"
  add_role "$slug" "00-director-of-$slug"
  add_role "$slug" "01-market-analyst"
}

# --- A: runtime dirs must not be counted as roles -----------------------------
echo ""
echo "[A] MATERIALIZED must ignore runtime/artifact subdirectories"
reset_fixture
healthy_dept research
add_runtime_dirs research
run_gate research
expect_rc "dept with real roles + memory/ devils-advocate/ conversational-logs/ scripts/ passes" 0
gate_says "Role dirs found: 2" "ROLE_COUNT reports 2 real roles (runtime dirs excluded from the count)"
gate_says "SKIP (not roles" "skipped runtime dirs are reported, not silently dropped"
gate_says "memory" "memory/ named in the skip line"
gate_says "conversational-logs" "conversational-logs/ named in the skip line"

# --- A anti-regression: real roles must still be gated ------------------------
echo ""
echo "[A-neg] a real role with a thin how-to.md must STILL fail rc=2"
reset_fixture
healthy_dept research
add_runtime_dirs research
mkdir -p "$DEPTS/research/02-survey-specialist"
printf 'tiny\n' > "$DEPTS/research/02-survey-specialist/how-to.md"
run_gate research
expect_rc "thin how-to.md still fails materialization" 2

echo ""
echo "[A-neg] a real role with a [PENDING] how-to.md must STILL fail rc=2"
reset_fixture
healthy_dept research
add_runtime_dirs research
mkdir -p "$DEPTS/research/02-survey-specialist"
# >= HOW_TO_MIN_BYTES so SIZE cannot be what fails it — the [PENDING marker must be.
# Pre-fix this passed: `grep -q "[PENDING"` is an unbalanced bracket expression, so
# grep errored (rc=2), the `if` read false, and the assertion never fired.
{ printf '# Survey Specialist  [PENDING - FILL FROM LIBRARY]\n'
  for _i in $(seq 1 120); do
    printf 'padding line %s written only to clear the three-kilobyte size floor.\n' "$_i"
  done
} > "$DEPTS/research/02-survey-specialist/how-to.md"
_sz=$(wc -c < "$DEPTS/research/02-survey-specialist/how-to.md" | tr -d ' ')
if [[ "$_sz" -ge 3072 ]]; then
  ok "the [PENDING] fixture is ${_sz}B — above the 3072B floor, so size is not the cause"
else
  bad "the [PENDING] fixture is only ${_sz}B — it would fail on size, not on the marker"
fi
run_gate research
expect_rc "[PENDING] how-to.md still fails materialization" 2
gate_says "pending-placeholder" "the failure is attributed to the [PENDING] marker, not size"

echo ""
echo "[A-neg] a role whose name CONTAINS a non-role word is still a role"
reset_fixture
healthy_dept research
add_runtime_dirs research
# Exact-match filtering: '16-devils-advocate-research' is a REAL roster role and
# must still be gated, even though 'devils-advocate' is a non-role basename.
mkdir -p "$DEPTS/research/16-devils-advocate-research"
printf 'tiny\n' > "$DEPTS/research/16-devils-advocate-research/how-to.md"
run_gate research
expect_rc "16-devils-advocate-research is gated as a role (thin -> rc 2)" 2

echo ""
echo "[A-neg] a role folder with NO how-to.md at all must STILL fail rc=2"
reset_fixture
healthy_dept research
add_runtime_dirs research
mkdir -p "$DEPTS/research/02-survey-specialist"
run_gate research
expect_rc "missing how-to.md still fails materialization" 2

echo ""
echo "[A-neg] a dept whose ONLY subdirectories are runtime dirs must fail"
reset_fixture
add_dept research
add_runtime_dirs research
run_gate research
# rc=6 (mixed): such a department has neither a role nor an entry point, so BOTH
# the materialization and the reachability assertions fail. That is the correct
# verdict — the point of the case is that runtime dirs alone are worth zero roles.
expect_rc "runtime dirs alone do not satisfy the zero-role-dirs assertion" 6
gate_says "no-role-dirs" "the failure is 'no-role-dirs', proving runtime dirs are not counted"

# --- E: stub-marker detection, proven in BOTH directions ----------------------
# v1.0.7. The gate used to test the bare substring "[PENDING", which is not a stub
# signature — it is a substring of AUTHORED PROSE. Canonical role-library templates
# legitimately discuss PENDING markers as subject matter, so fully-instantiated
# 12-71 KB how-to.md files were failed as stubs and the wiring gate blocked completed
# builds. The gate now tests the two signatures the stub WRITERS actually emit
# ("FILL FROM LIBRARY" and "how-to.md (stub)" — see STUB_MARKERS in verify-wiring.sh).
#
# A one-directional test is not proof. Both directions are asserted below:
#   E1  every stub form this repo can WRITE is still caught      (must fail rc=2)
#   E2  every prose form this repo SHIPS is ignored              (must pass rc=0)
# Each E1 fixture is >= HOW_TO_MIN_BYTES so size can never be what fails it, and the
# attribution is asserted, so a case cannot pass for the wrong reason.

# marked_how_to <path> <first-line> — a >=3072B how-to.md whose first line is <first-line>.
marked_how_to() {
  local path="$1" first="$2"
  { printf '%s\n' "$first"
    for _i in $(seq 1 120); do
      printf 'padding line %s written only to clear the three-kilobyte size floor.\n' "$_i"
    done
  } > "$path"
  local sz
  sz=$(wc -c < "$path" | tr -d ' ')
  if [[ "$sz" -lt 3072 ]]; then
    bad "fixture $path is only ${sz}B — it would fail on size, not on the marker"
  fi
}

echo ""
echo "[E1] every stub form the repo can WRITE is still caught (rc=2)"
# The four signatures, each traced to the code that emits it.
_stub_case() {
  local label="$1" first_line="$2"
  reset_fixture
  healthy_dept research
  add_runtime_dirs research
  mkdir -p "$DEPTS/research/02-survey-specialist"
  marked_how_to "$DEPTS/research/02-survey-specialist/how-to.md" "$first_line"
  run_gate research
  expect_rc "$label" 2
  gate_says "pending-placeholder" "  ^ attributed to the stub marker, not to size"
}
_stub_case "hyphen form (build-workforce.py:5637)" \
  '# Survey Specialist - how-to.md  [PENDING - FILL FROM LIBRARY]'
_stub_case "em-dash form (create_role_workspaces.py:259, add-role.sh:377)" \
  '# Survey Specialist — how-to.md  [PENDING — FILL FROM LIBRARY]'
_stub_case "OWNER-REQUESTED form (build-workforce.py:2801)" \
  '# Survey Specialist - how-to.md  [PENDING - OWNER-REQUESTED CUSTOM ROLE - FILL FROM LIBRARY]'
_stub_case "stub-title form (shared-utils/create-role-workspaces.py:145)" \
  '# Survey Specialist — how-to.md (stub)'

echo ""
echo "[E2] every prose form the repo SHIPS is ignored (rc=0)"
# These strings are verbatim from canonical role-library templates that ship today.
# Pre-fix, each of these ALONE failed a complete role as an unfilled stub.
_prose_case() {
  local label="$1"
  shift
  reset_fixture
  healthy_dept research
  add_runtime_dirs research
  mkdir -p "$DEPTS/research/02-survey-specialist"
  { printf '%s\n' '# Survey Specialist'
    printf '%s\n' "$@"
    for _i in $(seq 1 120); do
      printf 'authored operating procedure line %s with real substance.\n' "$_i"
    done
  } > "$DEPTS/research/02-survey-specialist/how-to.md"
  run_gate research
  expect_rc "$label" 0
}
_prose_case "qc-specialist auto-fail battery prose is not a stub" \
  '1. **Auto-fail battery (hard layer, runs FIRST):** A critical defect forces FAIL' \
  'regardless of averages. Examples: missing required fields, broken integrations,' \
  '`[PENDING]` markers in live content, unresolved errors in outputs.'
_prose_case "presentations slide-copy prose is not a stub" \
  '**Failure mode:** If slides_copy.md is not complete (has [PENDING] placeholders in' \
  'more than 10% of slides), the DA review cannot be meaningfully completed.'
_prose_case "graphics pricing-gap prose is not a stub" \
  '- **Action:** Document the gap in PRICING.md as a `[PENDING]` entry so it is visible.'
_prose_case "all three prose forms together are still not a stub" \
  '`[PENDING]` markers in live content, unresolved errors in outputs.' \
  'has [PENDING] placeholders in more than 10% of slides' \
  'Document the gap in PRICING.md as a `[PENDING]` entry so it is visible.'

echo ""
echo "[E3] the shipped templates that triggered the false failure are prose, not stubs"
# Ground the fix in the real library rather than in hand-written fixtures: the
# templates carrying "[PENDING" must carry NO real stub signature. If a future
# template ever ships a genuine stub marker, this assertion fires.
_LIB="$(cd "$SCRIPT_DIR/.." && pwd)/templates/role-library"
if [[ -d "$_LIB" ]]; then
  _prose_files=$(grep -rlF -- '[PENDING' "$_LIB" 2>/dev/null | wc -l | tr -d ' ')
  _stub_files=$(grep -rlF -e 'FILL FROM LIBRARY' -e 'how-to.md (stub)' "$_LIB" 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$_prose_files" -gt 0 ]]; then
    ok "$_prose_files shipped template(s) contain '[PENDING' prose (the false-failure source)"
  else
    bad "expected shipped templates carrying '[PENDING' prose — found none"
  fi
  if [[ "$_stub_files" -eq 0 ]]; then
    ok "ZERO shipped templates carry a real stub signature — every '[PENDING' hit was prose"
  else
    bad "$_stub_files shipped template(s) carry a real stub signature — investigate before shipping"
    grep -rlF -e 'FILL FROM LIBRARY' -e 'how-to.md (stub)' "$_LIB" 2>/dev/null | sed 's/^/        | /' >&2
  fi
else
  echo "  SKIP: role-library not found at $_LIB"
fi

# --- B: reachability for departments whose roster defines no Director ---------
echo ""
echo "[B] REACHABLE honours the roster's declared entry point"
reset_fixture
add_dept bugs
add_role bugs "01-bug-intake-clerk"
add_role bugs "02-triage-dedup-analyst"
add_role bugs "03-bug-librarian"
add_runtime_dirs bugs
run_gate bugs
expect_rc "bugs (roster defines no director-class role) passes via bug-intake-clerk" 0
gate_says "declared entry point for 'bugs'" "bugs resolves via the declared override, not a director match"

reset_fixture
add_dept master-orchestrator
add_role master-orchestrator "00-master-orchestrator"
add_role master-orchestrator "01-quality-control-agent-master-orchestrator-dept"
add_runtime_dirs master-orchestrator
run_gate master-orchestrator
expect_rc "master-orchestrator passes via its single-occupant entry point" 0
gate_says "declared entry point for 'master-orchestrator'" "master-orchestrator resolves via the declared override"

# --- B anti-regression: the override is a rename, not a bypass ----------------
echo ""
echo "[B-neg] an override dept MISSING its declared entry point must STILL fail rc=4"
reset_fixture
add_dept bugs
add_role bugs "02-triage-dedup-analyst"
add_role bugs "03-bug-librarian"
add_runtime_dirs bugs
run_gate bugs
expect_rc "bugs without bug-intake-clerk still fails reachability" 4

echo ""
echo "[B-neg] a NON-override dept with no director-class role must STILL fail rc=4"
reset_fixture
add_dept crm
add_role crm "01-pipeline-hygiene-specialist"
add_runtime_dirs crm
run_gate crm
expect_rc "crm with no director-class role still fails reachability" 4

echo ""
echo "[B] a normal dept with a real director role still passes on the keyword path"
reset_fixture
add_dept crm
add_role crm "00-director-of-crm"
add_role crm "01-pipeline-hygiene-specialist"
add_runtime_dirs crm
run_gate crm
expect_rc "crm with a director role passes" 0
gate_says "entry point role = 00-director-of-crm" "director keyword path still used when a director role exists"

# --- C: departments-tree resolution -------------------------------------------
# Pre-fix, DEPTS_DIR was a single unvalidated guess: state.workspaceRoot, else
# dirname(STATE_FILE). When workspaceRoot is absent (it is not written on every
# path) the gate pinned itself to $OC_ROOT/workspace/departments and delivered a
# confident verdict about a tree that may not hold the workforce at all.
echo ""
echo "[C] the departments tree is DETECTED and proven, not guessed"
reset_fixture
# The workforce lives in a company-shaped tree. workspace/departments EXISTS but
# holds only an unrelated leftover — the exact shape in which the pre-fix gate
# pinned itself to workspace/departments and reported every real department
# missing. No workspaceRoot key is written, so detection is the only way through.
_ORIG_DEPTS="$DEPTS"
COMPANY_TREE="$FIX_HOME/clawd/zero-human-company/acme-co/departments"
mkdir -p "$COMPANY_TREE" "$DEPTS/unrelated-leftover"
printf '%s\n' "{\"companySlug\":\"acme-co\",\"departments\":[]}" > "$WS/.workforce-build-state.json"
DEPTS="$COMPANY_TREE"          # add_dept/add_role write through $DEPTS
add_dept crm
add_role crm "00-director-of-crm"
add_role crm "01-pipeline-hygiene-specialist"
add_runtime_dirs crm
set_agent_workspace crm "$COMPANY_TREE/crm"
run_gate crm
expect_rc "a company-shaped tree is found even with no workspaceRoot in state" 0
gate_says "$COMPANY_TREE" "the resolved tree is reported in the output"
gate_says "candidate tree:" "each candidate tree and its score are printed"
DEPTS="$_ORIG_DEPTS"

echo ""
echo "[C-neg] when NO candidate tree holds the workforce, abort loudly (rc=9)"
reset_fixture
add_dept crm            # named in state + registered, but no directory anywhere
rm -rf "$DEPTS/crm"
run_gate crm
expect_rc "no resolvable tree is a precondition failure, not a verdict" 9
gate_says "could not resolve a departments tree" "the abort explains itself"
gate_says "Refusing to report a verdict" "the gate refuses rather than guessing"

# --- D: slug <-> directory suffix tolerance -----------------------------------
echo ""
echo "[D] a '<slug>-dept' directory resolves for a bare slug"
reset_fixture
add_dept trading-operations
# The state names 'trading-operations'; disk stores 'trading-operations-dept'.
# Pre-fix this probed a non-existent bare path and measured ZERO roles, tripping
# materialization for a department that was fully built.
rm -rf "$DEPTS/trading-operations"
mkdir -p "$DEPTS/trading-operations-dept"
add_role trading-operations-dept "00-director-of-trading-operations"
add_role trading-operations-dept "01-settlement-specialist"
add_runtime_dirs trading-operations-dept
set_agent_workspace trading-operations "$DEPTS/trading-operations-dept"
run_gate trading-operations
expect_rc "the -dept suffixed directory is found and measured" 0
gate_says "Role dirs found: 2" "both roles in the -dept directory are counted"
gate_says "trading-operations-dept" "the resolved directory carries the -dept suffix"

echo ""
echo "[D-neg] a genuinely absent department still fails materialization"
reset_fixture
add_dept trading-operations
rm -rf "$DEPTS/trading-operations"
mkdir -p "$DEPTS/some-other-dept/00-director-of-other"
substantive_how_to "$DEPTS/some-other-dept/00-director-of-other/how-to.md"
run_gate trading-operations
# The tree resolves (some-other-dept exists) but this department does not, so the
# verdict is a real materialization failure — never a silent pass.
if [[ "$GATE_RC" == "2" || "$GATE_RC" == "6" || "$GATE_RC" == "9" ]]; then
  ok "an absent department is reported as a failure (rc=$GATE_RC), never a pass"
else
  bad "an absent department did not fail — got rc=$GATE_RC"
  printf '%s\n' "$GATE_OUT" | sed 's/^/        | /' >&2
fi

# --- final hermetic assertion -------------------------------------------------
echo ""
echo "[Z] no writes escaped the fixture"
_after=""
[[ -d "$_real_oc" ]] && _after="$(ls -A "$_real_oc" 2>/dev/null | sort | md5 2>/dev/null || ls -A "$_real_oc" | sort | md5sum)"
if [[ "$_before" == "$_after" ]]; then
  ok "the real \$HOME/.openclaw top-level listing is unchanged"
else
  bad "the real \$HOME/.openclaw listing CHANGED — the suite was not hermetic"
fi

echo ""
echo "=============================================================="
echo "assertions: $PASS passed, $FAIL failed"
echo "=============================================================="
[[ $FAIL -eq 0 ]] || exit 1
exit 0
