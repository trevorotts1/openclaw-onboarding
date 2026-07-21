#!/usr/bin/env bash
# ============================================================================
# tests/unit/onboarding-state-fail-closed.test.sh
# ============================================================================
# ONB-STATE-002 — four fail-open patterns in the onboarding state machine.
#
# Every check below RUNS the real code. Nothing here greps for a fixed string
# as a proxy for behaviour: the defects are all "returns 0 when it should not",
# which only an execution can observe.
#
# THE FOUR:
#   T1  install.sh's oc_state_seed fallback returned 0, so the installer
#       printed "Onboarding state seeded" on a box whose state library never
#       loaded, and BOTH of the "not seeded" branches were unreachable.
#   T3  install.sh's install_onboarding_resume_cron fallback returned 0 and its
#       call site was bare, so a box that skipped the resume cron entirely said
#       nothing at all.
#   T5  scripts/onboarding-state.sh's registration check had no `else`, so it
#       was skipped whole whenever `openclaw` was off PATH (a cron's minimal
#       PATH) and a never-registered skill could reach qc-passed.
#   T7/T8 lib-onboarding-state.sh's oc_state_seed / oc_state_set both ended
#       `2>/dev/null || true`, so a failed qc-failed regression write left the
#       stale qc-passed on disk and the caller was told the write succeeded.
#
# ANTI-FALSE-POSITIVE CONTROLS. A "fix" that simply makes everything fail must
# not pass this file. T2, T4, T6 and T9 assert the HEALTHY path still succeeds,
# and T10 asserts the fixes cannot abort an installer running set -euo pipefail
# (which is how install.sh and update-skills.sh run — a crash is not an
# acceptable substitute for a swallowed failure).
#
# Hermetic: temp HOME, temp workspaces, no network, no `openclaw`, no fleet box.
#
# Run against another checkout with:  REPO_ROOT=/path/to/repo bash <this file>
# ============================================================================

# NOT set -e: observing nonzero return codes is the entire point.
set -uo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
INSTALL_SH="$REPO_ROOT/install.sh"
LIB="$REPO_ROOT/lib-onboarding-state.sh"
SHIM="$REPO_ROOT/scripts/onboarding-state.sh"

PASSED=0
FAILED=0
pass() { printf '  PASS  %s\n' "$*"; PASSED=$((PASSED + 1)); }
fail() { printf '  FAIL  %s\n' "$*"; FAILED=$((FAILED + 1)); }
hdr()  { printf '\n=== %s ===\n' "$*"; }

for f in "$INSTALL_SH" "$LIB" "$SHIM"; do
  [ -f "$f" ] || { echo "FATAL: missing $f"; exit 2; }
done

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

# A copy of PATH with every directory that actually contains an `openclaw`
# binary removed. Used to reproduce a cron's minimal PATH deterministically
# instead of assuming the runner has no CLI installed.
path_without_openclaw() {
  local out="" d
  local -a dirs
  IFS=':' read -r -a dirs <<< "$PATH"
  for d in "${dirs[@]}"; do
    [ -n "$d" ] || continue
    [ -x "$d/openclaw" ] && continue
    out="${out:+$out:}$d"
  done
  printf '%s' "$out"
}

# ── Fragment extraction ─────────────────────────────────────────────────────
# install.sh is ~6k lines and its top half cannot run outside a real install, so
# each test executes the exact BLOCK under test, lifted by content anchors (not
# line numbers, which every other agent's version bump would invalidate).

frag_state_stubs() {   # the state-library source attempt + its fallbacks
  awk '/^_lib_onboarding_state_self=/{f=1}
       f{print}
       f && /^command -v oc_state_summary/{exit}' "$INSTALL_SH"
}
frag_state_dispatch() {  # the Step-that-seeds block
  awk '/^# FIX 1 \(PRD 2\.1 \/ v10\.16\.48\): seed the per-skill onboarding STATE FILE/{f=1}
       f{print}
       f && /^fi$/{exit}' "$INSTALL_SH"
}
frag_cron_stubs() {    # the resume-cron source attempt + its fallback
  awk '/^_lib_resume_cron_self=/{f=1}
       f{print}
       f && /^command -v install_onboarding_resume_cron/{exit}' "$INSTALL_SH"
}
frag_cron_call() {     # Step 13b's invocation
  awk '/^# boundedness lives in scripts\/resume-onboarding\.sh\. See that lib for details\.$/{f=1;next}
       f && /^# -{10,}$/{exit}
       f{print}' "$INSTALL_SH"
}

for fn in frag_state_stubs frag_state_dispatch frag_cron_stubs frag_cron_call; do
  if [ -z "$($fn)" ]; then
    echo "FATAL: $fn extracted nothing from install.sh — the anchor moved."
    exit 2
  fi
done

# ============================================================================
hdr "T1  install.sh does NOT report a seed the state library never performed"
# ============================================================================
# The decisive question this file exists to answer. Run the real stub block and
# the real dispatch block in a directory with NO lib-onboarding-state.sh and no
# compat shim, under the same `set -euo pipefail` install.sh itself uses.
t1="$TMPROOT/t1"; mkdir -p "$t1/skills/01-x" "$t1/onboarding"
{
  echo '#!/usr/bin/env bash'
  echo 'set -euo pipefail'
  echo 'success(){ echo "SUCCESS|$*"; }'
  echo 'warn(){ echo "WARN|$*"; }'
  echo "SKILLS_DIR=\"$t1/skills\""
  echo 'ONBOARDING_VERSION="vTEST"'
  echo "ONBOARDING_DIR=\"$t1/onboarding\""
  frag_state_stubs
  frag_state_dispatch
} > "$t1/run.sh"
t1_out="$(bash "$t1/run.sh" 2>&1)"; t1_rc=$?

if printf '%s' "$t1_out" | grep -q 'SUCCESS|Onboarding state seeded'; then
  fail "T1a install.sh reported \"Onboarding state seeded\" with NO state library loaded"
  printf '        output: %s\n' "$(printf '%s' "$t1_out" | tr '\n' ' ')"
else
  pass "T1a no seed is reported when the state library never loaded"
fi

if printf '%s' "$t1_out" | grep -q 'WARN|lib-onboarding-state.sh not found'; then
  pass "T1b the \"not seeded\" branch is REACHABLE and fired"
else
  fail "T1b the \"not seeded\" branch never fired — it is still dead code"
fi

if [ "$t1_rc" -eq 0 ]; then
  pass "T1c the block did not abort its set -euo pipefail caller (rc 0)"
else
  fail "T1c the block ABORTED a set -euo pipefail caller (rc $t1_rc)"
fi

# ============================================================================
hdr "T2  ANTI-FALSE-POSITIVE: with the library present, the seed still succeeds"
# ============================================================================
t2="$TMPROOT/t2"; mkdir -p "$t2/skills/01-x" "$t2/skills/02-y" "$t2/onboarding"
cp "$LIB" "$t2/lib-onboarding-state.sh"
{
  echo '#!/usr/bin/env bash'
  echo 'set -euo pipefail'
  echo 'success(){ echo "SUCCESS|$*"; }'
  echo 'warn(){ echo "WARN|$*"; }'
  echo "SKILLS_DIR=\"$t2/skills\""
  echo 'ONBOARDING_VERSION="vTEST"'
  echo "ONBOARDING_DIR=\"$t2/onboarding\""
  echo "export ONBOARDING_STATE_FILE=\"$t2/.onboarding-state.json\""
  frag_state_stubs
  frag_state_dispatch
} > "$t2/run.sh"
t2_out="$(bash "$t2/run.sh" 2>&1)"; t2_rc=$?

if printf '%s' "$t2_out" | grep -q 'SUCCESS|Onboarding state seeded'; then
  pass "T2a a real seed is still reported as seeded"
else
  fail "T2a the healthy seed path REGRESSED — no success reported (rc $t2_rc): $t2_out"
fi
if [ -f "$t2/.onboarding-state.json" ] && grep -q '01-x' "$t2/.onboarding-state.json"; then
  pass "T2b the state file was really written and contains the discovered skills"
else
  fail "T2b no usable state file was written"
fi

# ============================================================================
hdr "T3  a skipped onboarding-resume cron is reported, not silent"
# ============================================================================
t3="$TMPROOT/t3"; mkdir -p "$t3"
{
  echo '#!/usr/bin/env bash'
  echo 'set -euo pipefail'
  echo 'success(){ echo "SUCCESS|$*"; }'
  echo 'warn(){ echo "WARN|$*"; }'
  frag_cron_stubs
  frag_cron_call
} > "$t3/run.sh"
t3_out="$(bash "$t3/run.sh" 2>&1)"; t3_rc=$?

if printf '%s' "$t3_out" | grep -qi 'resume cron NOT installed'; then
  pass "T3a a box that skipped the resume cron says so"
else
  fail "T3a the resume cron was skipped SILENTLY — no operator-visible signal"
fi
if [ "$t3_rc" -eq 0 ]; then
  pass "T3b Step 13b did not abort its set -euo pipefail caller (rc 0)"
else
  fail "T3b Step 13b ABORTED a set -euo pipefail caller (rc $t3_rc)"
fi

# ============================================================================
hdr "T4  ANTI-FALSE-POSITIVE: the real cron installer is called and stays quiet"
# ============================================================================
# The shipped install_onboarding_resume_cron returns 0 on every path by design,
# so a healthy box must see the call happen and NO warning.
t4="$TMPROOT/t4"; mkdir -p "$t4"
{
  echo '#!/usr/bin/env bash'
  echo 'set -euo pipefail'
  echo 'success(){ echo "SUCCESS|$*"; }'
  echo 'warn(){ echo "WARN|$*"; }'
  echo 'install_onboarding_resume_cron(){ echo "REAL-CRON-INSTALLER-RAN"; return 0; }'
  frag_cron_stubs
  frag_cron_call
} > "$t4/run.sh"
t4_out="$(bash "$t4/run.sh" 2>&1)"; t4_rc=$?

if printf '%s' "$t4_out" | grep -q 'REAL-CRON-INSTALLER-RAN'; then
  pass "T4a the real installer is still invoked (the fallback did not shadow it)"
else
  fail "T4a the real installer was NOT invoked: $t4_out"
fi
if printf '%s' "$t4_out" | grep -qi 'resume cron NOT installed'; then
  fail "T4b a healthy box was warned about a cron that WAS installed (false alarm)"
else
  pass "T4b a healthy box gets no false warning"
fi
[ "$t4_rc" -eq 0 ] && pass "T4c healthy path rc 0" || fail "T4c healthy path rc $t4_rc"

# ============================================================================
hdr "T5  the registration check fails CLOSED when openclaw is off PATH"
# ============================================================================
SAN_PATH="$(path_without_openclaw)"
if PATH="$SAN_PATH" command -v openclaw >/dev/null 2>&1; then
  fail "T5-precondition could not build a PATH without openclaw — T5 is not valid"
else
  t5="$TMPROOT/t5"; mkdir -p "$t5/home/.openclaw/workspace" "$t5/skills/99-test-skill"
  # No CORE_UPDATES.md and no qc-*.sh: checks (b) and (c) are no-ops, so the
  # skill's verdict rests ENTIRELY on the registration check under test.
  printf 'name: test-skill\ndescription: fixture\n' > "$t5/skills/99-test-skill/SKILL.md"
  t5_out="$(
    PATH="$SAN_PATH" HOME="$t5/home" SKILLS_DIR="$t5/skills" \
    bash -c '
      set -uo pipefail
      # shellcheck source=/dev/null
      source "$1" >/dev/null 2>&1
      reason="$(obs_verify_skill 99-test-skill "$2")"; rc=$?
      echo "RC=$rc REASON=$reason"
    ' _ "$SHIM" "$t5/skills" 2>&1
  )"
  if printf '%s' "$t5_out" | grep -q 'RC=0'; then
    fail "T5a an UNREGISTERED skill reached qc-passed with no openclaw on PATH -> $t5_out"
  else
    pass "T5a an unverifiable skill does not pass the gate ($t5_out)"
  fi
  if printf '%s' "$t5_out" | grep -q 'openclaw-cli-not-on-path'; then
    pass "T5b the reason NAMES the cause instead of an unexplained failure"
  else
    fail "T5b the failure reason does not name the missing CLI -> $t5_out"
  fi

  # ==========================================================================
  hdr "T6  ANTI-FALSE-POSITIVE: a genuinely registered skill still passes"
  # ==========================================================================
  t6="$TMPROOT/t6"; mkdir -p "$t6/home/.openclaw/workspace" "$t6/bin"
  cat > "$t6/bin/openclaw" <<'FAKECLI'
#!/usr/bin/env bash
# Minimal stand-in for `openclaw skills info <name>` on a healthy box.
echo "Name: test-skill"
echo "Source: openclaw-managed"
echo "Details: Ready"
FAKECLI
  chmod +x "$t6/bin/openclaw"
  t6_out="$(
    PATH="$t6/bin:$SAN_PATH" HOME="$t6/home" SKILLS_DIR="$t5/skills" \
    bash -c '
      set -uo pipefail
      # shellcheck source=/dev/null
      source "$1" >/dev/null 2>&1
      reason="$(obs_verify_skill 99-test-skill "$2")"; rc=$?
      echo "RC=$rc REASON=$reason"
    ' _ "$SHIM" "$t5/skills" 2>&1
  )"
  if printf '%s' "$t6_out" | grep -q 'RC=0'; then
    pass "T6 a registered skill still verifies (the gate was not just broken)"
  else
    fail "T6 a REGISTERED skill was rejected — the fix over-fires -> $t6_out"
  fi
fi

# ============================================================================
hdr "T7  oc_state_seed reports a write it could not perform"
# ============================================================================
# The state path is a DIRECTORY, so the write cannot succeed for ANY user --
# including root, which a permission-bit fixture would not cover.
t7="$TMPROOT/t7"; mkdir -p "$t7/state.json" "$t7/skills/01-x"
t7_out="$(
  ONBOARDING_STATE_FILE="$t7/state.json" OC_SKILLS_DIR="$t7/skills" \
  bash -c '
    set -uo pipefail
    # shellcheck source=/dev/null
    source "$1"
    oc_state_seed "$2" vTEST; echo "RC=$?"
  ' _ "$LIB" "$t7/skills" 2>&1
)"
if printf '%s' "$t7_out" | grep -q 'RC=0'; then
  fail "T7 oc_state_seed returned 0 for a seed that could not be written -> $t7_out"
else
  pass "T7 oc_state_seed returns nonzero when the state file cannot be written"
fi

# ============================================================================
hdr "T8  oc_state_set reports a status it could not record"
# ============================================================================
# python3 removed from PATH: the write cannot run at all. Root-proof, and it is
# the exact shape of the swallowed qc-failed regression write.
t8="$TMPROOT/t8"; mkdir -p "$t8/skills"
printf '{"skills":{"01-x":{"status":"qc-passed"}}}' > "$t8/state.json"
NOPY_PATH="$TMPROOT/nopy-bin"; mkdir -p "$NOPY_PATH"
for b in bash date grep sed awk cat mkdir rm ls printf env dirname basename chmod cp mv find sort head tail tr wc; do
  p="$(command -v "$b" 2>/dev/null)" && ln -sf "$p" "$NOPY_PATH/$b" 2>/dev/null
done
t8_out="$(
  PATH="$NOPY_PATH" ONBOARDING_STATE_FILE="$t8/state.json" OC_SKILLS_DIR="$t8/skills" \
  "$NOPY_PATH/bash" -c '
    set -uo pipefail
    # shellcheck source=/dev/null
    source "$1"
    oc_state_set 01-x qc-failed "regressed"; echo "RC=$?"
  ' _ "$LIB" 2>&1
)"
if printf '%s' "$t8_out" | grep -q 'RC=0'; then
  fail "T8a oc_state_set returned 0 for a qc-failed write that never happened -> $t8_out"
else
  pass "T8a oc_state_set returns nonzero when the status cannot be recorded"
fi
# The point of the defect: the stale qc-passed is still on disk. The caller must
# not have been told otherwise.
if grep -q 'qc-passed' "$t8/state.json"; then
  pass "T8b the stale qc-passed is indeed still on disk — which is why rc must be nonzero"
else
  fail "T8b fixture invalid: the state file no longer holds the stale status"
fi

# ============================================================================
hdr "T9  ANTI-FALSE-POSITIVE: the healthy write path still works end to end"
# ============================================================================
t9="$TMPROOT/t9"; mkdir -p "$t9/skills/01-x" "$t9/skills/02-y"
t9_out="$(
  ONBOARDING_STATE_FILE="$t9/state.json" OC_SKILLS_DIR="$t9/skills" \
  bash -c '
    set -euo pipefail
    # shellcheck source=/dev/null
    source "$1"
    oc_state_seed "$2" vTEST      ; echo "SEED_RC=$?"
    oc_state_set 01-x qc-passed   ; echo "SET1_RC=$?"
    oc_state_set 01-x qc-failed r ; echo "SET2_RC=$?"
  ' _ "$LIB" "$t9/skills" 2>&1
)"
if printf '%s' "$t9_out" | grep -q 'SEED_RC=0' \
   && printf '%s' "$t9_out" | grep -q 'SET1_RC=0' \
   && printf '%s' "$t9_out" | grep -q 'SET2_RC=0'; then
  pass "T9a seed + both status writes still return 0 on a healthy box"
else
  fail "T9a the healthy path REGRESSED -> $t9_out"
fi
if command -v python3 >/dev/null 2>&1 \
   && python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d["skills"]["01-x"]["status"]=="qc-failed" else 1)' "$t9/state.json"; then
  pass "T9b the qc-failed REGRESSION really overwrote qc-passed on disk"
else
  fail "T9b qc-failed did not overwrite qc-passed — the regression rule broke"
fi

# ============================================================================
hdr "T10 oc_gate_skill cannot abort a set -euo pipefail caller when writes fail"
# ============================================================================
# The gate must FAIL CLOSED (rc 1), never crash the installer that sourced it.
t10="$TMPROOT/t10"; mkdir -p "$t10/skills/01-x"
t10_out="$(
  ONBOARDING_STATE_FILE="$TMPROOT/t7/state.json" OC_SKILLS_DIR="$t10/skills" \
  bash -c '
    set -euo pipefail
    # shellcheck source=/dev/null
    source "$1"
    if oc_gate_skill 01-x; then echo "GATE=PASS"; else echo "GATE=FAIL"; fi
    echo "SURVIVED"
  ' _ "$LIB" 2>&1
)"
if printf '%s' "$t10_out" | grep -q 'SURVIVED'; then
  pass "T10a the caller survived an unwritable state file (no set -e abort)"
else
  fail "T10a the caller was ABORTED mid-gate -> $t10_out"
fi
if printf '%s' "$t10_out" | grep -q 'GATE=FAIL'; then
  pass "T10b the gate failed closed when it could not record what it found"
else
  fail "T10b the gate did not fail closed -> $t10_out"
fi

# ============================================================================
printf '\n============================================\n'
printf '  passed: %d   failed: %d\n' "$PASSED" "$FAILED"
printf '============================================\n'
[ "$FAILED" -eq 0 ] || exit 1
exit 0
