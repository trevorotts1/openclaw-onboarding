#!/usr/bin/env bash
# =============================================================================
# install-state-fail-open.test.sh  (ONB-STATE-002)
#
# THE DEFECT CLASS THIS LOCKS — install-time FAIL-OPEN. Four sites shipped to
# client boxes where a failure was reported as a success, or not reported at all:
#
#   1. install.sh's `oc_state_seed` fallback was `{ :; }` — a no-op returning 0.
#      Because the fallback defines the symbol either way, the dispatch's
#      `command -v oc_state_seed` test was ALWAYS true, so the compat-shim
#      branch and the "not seeded" warning were unreachable DEAD CODE, and
#      `oc_state_seed ... && success` printed "Onboarding state seeded" on a box
#      where the state machine never loaded and no state file was ever written.
#   2. install.sh's `install_onboarding_resume_cron` fallback was `{ :; }` and
#      its call site was bare: a bundle missing the lib produced ZERO log output
#      and no resume cron.
#   3. scripts/onboarding-state.sh's registration check `if command -v openclaw`
#      had NO else, so with the CLI off PATH (a cron's minimal PATH) check (a)
#      was skipped entirely and an UNREGISTERED skill reached qc-passed.
#   4. lib-onboarding-state.sh's oc_state_seed / oc_state_set both ended
#      `2>/dev/null || true`, so a failed `qc-failed` REGRESSION write left the
#      stale `qc-passed` on disk and told the caller it had succeeded.
#
# WHY THESE ASSERTIONS ARE BEHAVIOURAL, NOT TEXTUAL. Every check below RUNS the
# real code — install.sh's own lines are extracted between stable anchors that
# exist in both the fixed and unfixed file and executed — rather than grepping
# for a fixed string. A grep-based guard would pass the moment someone reworded
# a comment, and would never have caught the `command -v` dead-branch bug at all,
# because that line looked perfectly correct in isolation.
#
# FALSIFIED AGAINST THE UNFIXED CODE. Run with a repo root as $1 to point it at
# any tree. Against pristine origin/main (3827d172) this file reports 7 failed
# (T1a T1b T2 T4 T5a T6 T8); against the fix, 0. A test that passes on both has
# tested nothing.
#
# The other five assertions pass on BOTH trees on purpose and are labelled as
# such: T3 and T7 are anti-vacuity controls (a "fix" that made every box warn,
# or that turned a normal absent file into an error, would satisfy T1 and be
# worthless), T1c and T5b pin the fixture, and T9 guards the `set -e` survival
# that folding these new nonzero returns into oc_gate_skill could have broken.
# They prove the fix did no harm; only the seven above prove it did good.
#
# Hermetic: temp HOME, temp state dirs, no network, no openclaw CLI, no fleet
# box, and it never reads or writes anything under the operator's real $HOME.
# =============================================================================
set -uo pipefail

REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
INSTALL_SH="$REPO_ROOT/install.sh"
LIB="$REPO_ROOT/lib-onboarding-state.sh"
SHIM="$REPO_ROOT/scripts/onboarding-state.sh"

PASS=0; FAIL=0; SKIP=0
pass() { printf '  PASS: %s\n' "$1"; PASS=$((PASS+1)); }
fail() { printf '  FAIL: %s\n' "$1"; FAIL=$((FAIL+1)); }
skip() { printf '  SKIP: %s\n' "$1"; SKIP=$((SKIP+1)); }

TMPROOT="$(mktemp -d)"
trap 'chmod -R u+w "$TMPROOT" 2>/dev/null; rm -rf "$TMPROOT"' EXIT

# Two checks below need a write to genuinely FAIL. root ignores the permission
# bits, which would make them vacuously "pass the broken code" — the exact
# silent-success shape this file exists to prevent. Probe the denial for real
# rather than assuming it, and SKIP loudly if it does not hold. (GitHub's
# ubuntu-latest runs as non-root, so they execute there.)
_probe="$TMPROOT/.denyprobe"; mkdir -p "$_probe"; chmod 555 "$_probe"
if touch "$_probe/x" 2>/dev/null; then WRITE_DENY_WORKS=0; else WRITE_DENY_WORKS=1; fi
chmod 755 "$_probe"; rm -rf "$_probe"

# Extract install.sh's lib-sourcing + fallback definitions, and its state-seed
# dispatch, between anchors that are present in BOTH the fixed and unfixed file.
extract_install_blocks() {
  awk '/^_lib_onboarding_state_self=/,/^command -v oc_state_summary/' "$INSTALL_SH"
  awk '/^# FIX 1 \(PRD 2\.1 \/ v10\.16\.48\): seed the per-skill onboarding STATE FILE/,/^# ── Seed nudge lifecycle state file/' "$INSTALL_SH" \
    | sed '$d'
}

build_probe() {   # $1 = dir that will act as install.sh's own directory
  local d="$1"
  {
    echo '#!/bin/bash'
    echo 'set -euo pipefail'
    echo 'success() { echo "SUCCESS: $*"; }'
    echo 'warn()    { echo "WARN: $*"; }'
    echo 'SKILLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skills"'
    echo 'ONBOARDING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"'
    echo 'ONBOARDING_VERSION="v-test"'
    extract_install_blocks
  } > "$d/probe.sh"
}

echo "== install-state-fail-open (ONB-STATE-002) =="
echo "   repo root: $REPO_ROOT"

# ---------------------------------------------------------------------------
# T1 — DECISIVE. State library absent => install.sh must NOT claim it seeded.
# ---------------------------------------------------------------------------
echo
echo "== T1 - state library never loaded =="
D="$TMPROOT/t1"; mkdir -p "$D/skills/01-demo"   # NO lib-onboarding-state.sh, NO scripts/ shim
build_probe "$D"
OUT="$(OC_CONFIG="$D/cfg" bash "$D/probe.sh" 2>&1)"
if printf '%s' "$OUT" | grep -q 'SUCCESS: Onboarding state seeded'; then
  fail "T1a: install.sh reported \"Onboarding state seeded\" with the state library ABSENT"
else
  pass "T1a: install.sh does NOT report a seed when the state library never loaded"
fi
if printf '%s' "$OUT" | grep -q 'WARN:'; then
  pass "T1b: the absent state library is reported LOUDLY (warn emitted)"
else
  fail "T1b: state library absent produced no warning at all"
fi
if [ -f "$D/cfg/.onboarding-state.json" ]; then
  fail "T1c: a state file appeared even though the library never loaded"
else
  pass "T1c: no state file on disk, matching what the log now says"
fi

# ---------------------------------------------------------------------------
# T2 — the compat-shim branch must be REACHABLE (it was dead code).
# ---------------------------------------------------------------------------
echo
echo "== T2 - compat-shim fallback branch is reachable =="
D="$TMPROOT/t2"; mkdir -p "$D/skills/01-demo" "$D/scripts" "$D/home"
cp "$SHIM" "$D/scripts/onboarding-state.sh"          # shim present, root lib ABSENT
build_probe "$D"
OUT="$(HOME="$D/home" SKILLS_DIR="$D/skills" OC_CONFIG="$D/cfg" bash "$D/probe.sh" 2>&1)"
if printf '%s' "$OUT" | grep -q 'compat shim'; then
  pass "T2: with the root lib absent the compat-shim branch RUNS (was unreachable)"
else
  fail "T2: compat-shim branch still unreachable — 'command -v' is satisfied by the stub"
fi

# ---------------------------------------------------------------------------
# T3 — CONTROL / anti-vacuity: a healthy box must still report success.
# A fix that made every box warn would pass T1 and be worthless.
# ---------------------------------------------------------------------------
echo
echo "== T3 - CONTROL: healthy box still seeds and still says so =="
D="$TMPROOT/t3"; mkdir -p "$D/skills/01-demo" "$D/cfg"
cp "$LIB" "$D/lib-onboarding-state.sh"
build_probe "$D"
OUT="$(OC_CONFIG="$D/cfg" bash "$D/probe.sh" 2>&1)"
if printf '%s' "$OUT" | grep -q 'SUCCESS: Onboarding state seeded' \
   && [ -f "$D/cfg/.onboarding-state.json" ]; then
  pass "T3: healthy box reports the seed AND the state file exists"
else
  fail "T3: healthy box no longer seeds — the fix broke the working path"
fi

# ---------------------------------------------------------------------------
# T4 — registration check must fail CLOSED when openclaw is off PATH.
# ---------------------------------------------------------------------------
echo
echo "== T4 - obs_verify_skill with openclaw off PATH =="
D="$TMPROOT/t4"; mkdir -p "$D/home/.openclaw/workspace" "$D/skills/09-unreg"
printf 'name: unreg-demo\n' > "$D/skills/09-unreg/SKILL.md"   # no CORE_UPDATES, no qc-*.sh
OUT="$(env -i PATH=/usr/bin:/bin HOME="$D/home" SKILLS_DIR="$D/skills" \
       bash -c 'source "$0" 2>/dev/null
                command -v openclaw >/dev/null 2>&1 && { echo INVALID-PROBE; exit 9; }
                if r=$(obs_verify_skill 09-unreg); then echo "GATE-PASS:$r"; else echo "GATE-FAIL:$r"; fi' \
       "$SHIM" 2>&1 | tail -1)"
case "$OUT" in
  GATE-FAIL:*openclaw-cli:absent*)
      pass "T4: unregistered skill FAILS the gate with a named reason ($OUT)" ;;
  GATE-PASS:*)
      fail "T4: UNREGISTERED skill reached qc-passed with openclaw off PATH ($OUT)" ;;
  *)  fail "T4: unexpected gate result: $OUT" ;;
esac

# ---------------------------------------------------------------------------
# T5 — a failed qc-failed REGRESSION write must be nonzero, not silent success.
# ---------------------------------------------------------------------------
echo
echo "== T5 - oc_state_set regression write onto an unwritable state file =="
if [ "$WRITE_DENY_WORKS" -eq 0 ]; then
  skip "T5: cannot deny writes as this user (root?) — assertion would be vacuous"
else
D="$TMPROOT/t5"; mkdir -p "$D/cfg" "$D/skills"
echo '{"version":"v1","skills":{"07-demo":{"status":"qc-passed"}}}' > "$D/cfg/.onboarding-state.json"
chmod 444 "$D/cfg/.onboarding-state.json"; chmod 555 "$D/cfg"
RC=0
OC_CONFIG="$D/cfg" OC_SKILLS_DIR="$D/skills" ONBOARDING_STATE_FILE="$D/cfg/.onboarding-state.json" \
  bash -c 'source "$0"; oc_state_set 07-demo qc-failed regression' "$LIB" >/dev/null 2>&1 || RC=$?
chmod 755 "$D/cfg"
if [ "$RC" -ne 0 ]; then
  pass "T5a: oc_state_set returns nonzero (rc=$RC) when the write fails"
else
  fail "T5a: oc_state_set returned 0 after failing to record qc-failed (stale qc-passed left on disk)"
fi
if grep -q 'qc-passed' "$D/cfg/.onboarding-state.json"; then
  pass "T5b: the stale qc-passed is still on disk — which is exactly why rc must be nonzero"
else
  fail "T5b: fixture invalid — the file changed unexpectedly"
fi
fi

# ---------------------------------------------------------------------------
# T6 — a seed that could not write must say so.
# ---------------------------------------------------------------------------
echo
echo "== T6 - oc_state_seed into an unusable state directory =="
# The blocker is a regular FILE where the state dir must be, so `mkdir -p` fails
# for EVERY user including root — no permission bits involved, nothing to make
# this vacuous in a root container.
D="$TMPROOT/t6"; mkdir -p "$D/skills/01-demo"; : > "$D/blocker"
RC=0
OC_CONFIG="$D" OC_SKILLS_DIR="$D/skills" ONBOARDING_STATE_FILE="$D/blocker/.onboarding-state.json" \
  bash -c 'source "$0"; oc_state_seed "$1" v1' "$LIB" "$D/skills" >/dev/null 2>&1 || RC=$?
if [ "$RC" -ne 0 ]; then
  pass "T6: oc_state_seed returns nonzero (rc=$RC) when it cannot write the state file"
else
  fail "T6: oc_state_seed returned 0 while creating nothing"
fi

# ---------------------------------------------------------------------------
# T7 — ABSENT vs BROKEN must NOT be collapsed. An absent state file is normal
# (seed owns creation); it must stay quiet and rc 0.
# ---------------------------------------------------------------------------
echo
echo "== T7 - ABSENT state file stays tolerated (must not become loud) =="
D="$TMPROOT/t7"; mkdir -p "$D/cfg" "$D/skills/01-demo"
RC=0
ERR="$(OC_CONFIG="$D/cfg" OC_SKILLS_DIR="$D/skills" ONBOARDING_STATE_FILE="$D/cfg/.onboarding-state.json" \
  bash -c 'source "$0"; oc_state_seed "$1" v1' "$LIB" "$D/skills" 2>&1 >/dev/null)" || RC=$?
if [ "$RC" -eq 0 ] && [ -z "$ERR" ] && [ -f "$D/cfg/.onboarding-state.json" ]; then
  pass "T7: absent state file is created quietly, rc 0, nothing on stderr"
else
  fail "T7: absent (normal) was treated as broken — rc=$RC stderr=[$ERR]"
fi

# ---------------------------------------------------------------------------
# T8 — a PRESENT but corrupt state file must be loud, nonzero, and must NOT be
# silently reset (the old `except Exception: state={}` discarded every status).
# ---------------------------------------------------------------------------
echo
echo "== T8 - PRESENT but corrupt state file =="
D="$TMPROOT/t8"; mkdir -p "$D/cfg" "$D/skills/01-demo"
printf 'not json {{{' > "$D/cfg/.onboarding-state.json"
RC=0
OC_CONFIG="$D/cfg" OC_SKILLS_DIR="$D/skills" ONBOARDING_STATE_FILE="$D/cfg/.onboarding-state.json" \
  bash -c 'source "$0"; oc_state_seed "$1" v1' "$LIB" "$D/skills" >/dev/null 2>&1 || RC=$?
if [ "$RC" -ne 0 ] && [ "$(cat "$D/cfg/.onboarding-state.json")" = 'not json {{{' ]; then
  pass "T8: corrupt state file is nonzero AND left intact (not silently reset)"
else
  fail "T8: corrupt state file was swallowed or overwritten (rc=$RC)"
fi

# ---------------------------------------------------------------------------
# T9 — oc_gate_skill must fail CLOSED when it cannot record, and must not abort
# a caller running under `set -euo pipefail` (this lib is sourced by such
# callers; a crash is not an acceptable substitute for a swallowed failure).
# ---------------------------------------------------------------------------
echo
echo "== T9 - oc_gate_skill under set -e when state writes fail =="
if [ "$WRITE_DENY_WORKS" -eq 0 ]; then
  skip "T9: cannot deny writes as this user (root?) — assertion would be vacuous"
else
D="$TMPROOT/t9"; mkdir -p "$D/cfg" "$D/skills/01-demo" "$D/bin"
printf 'name: demo\n' > "$D/skills/01-demo/SKILL.md"
printf '#!/bin/bash\necho "Name: demo"\necho Ready\n' > "$D/bin/openclaw"; chmod +x "$D/bin/openclaw"
echo '{"skills":{"01-demo":{"status":"qc-passed"}}}' > "$D/cfg/.onboarding-state.json"
chmod 444 "$D/cfg/.onboarding-state.json"; chmod 555 "$D/cfg"
OUT="$(PATH="$D/bin:$PATH" OC_CONFIG="$D/cfg" OC_SKILLS_DIR="$D/skills" \
       ONBOARDING_STATE_FILE="$D/cfg/.onboarding-state.json" \
  bash -c 'set -euo pipefail; source "$0"
           if oc_gate_skill 01-demo; then echo GATE-PASS; else echo GATE-FAIL; fi
           echo SURVIVED' "$LIB" 2>/dev/null)"
chmod 755 "$D/cfg"
if printf '%s' "$OUT" | grep -q GATE-FAIL && printf '%s' "$OUT" | grep -q SURVIVED; then
  pass "T9: gate fails closed on state-write failure AND the set -e caller survives"
else
  fail "T9: expected GATE-FAIL + SURVIVED, got [$(printf '%s' "$OUT" | tr '\n' '/')]"
fi
fi

echo
echo "────────────────────────────"
echo "passed: $PASS   failed: $FAIL   skipped: $SKIP"
[ "$FAIL" -eq 0 ]
