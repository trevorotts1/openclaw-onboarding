#!/usr/bin/env bash
# tests/unit/fail-closed-doctrine-gate.test.sh
#
# Proves scripts/qc-assert-fail-closed-doctrine.sh — the N40 gate — actually
# measures what it claims to measure.
#
# ⛔ WHAT THIS TEST REFUSES TO BE. A previous unit test in this repo asserted that
# a safety cap was *defined* and passed green while runtime enforcement was dead.
# Asserting "the function exists" or "the string appears in the file" proves
# nothing. Every case below RUNS the real shipped gate and asserts on its OBSERVED
# exit code and OBSERVED message.
#
# ⛔ EVERY BLOCK HAS A MATCHING CONTROL. A gate that fails everything is
# indistinguishable from a gate that fails correctly. Case (1) proves the REAL
# repo doctrine PASSES through the very same harness that cases (2)-(4) prove a
# neutered doctrine does not.
#
# ⛔ AND THE ENFORCEMENT HALF IS MUTATION-PROVEN. Case (7) neuters the D6 detector
# inside a COPY of the skill tree and requires the gate to go red. Without that,
# case (1)'s PASS would not be evidence that the detector runs at all — only that
# the markdown reads correctly, which is precisely the failure mode this gate
# exists to avoid.
#
# Run: bash tests/unit/fail-closed-doctrine-gate.test.sh
# Exit 0 = all checks pass. Exit 1 = one or more checks failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="$REPO_ROOT/scripts/qc-assert-fail-closed-doctrine.sh"
DOCTRINE="$REPO_ROOT/AGENTS.md"
SKILL="$REPO_ROOT/61-loop-protection-system"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== fail-closed-doctrine-gate.test.sh ==="
echo "    interpreter: bash ${BASH_VERSION:-unknown}  (\$0 was run by: ${BASH:-unknown})"

if [ ! -f "$GATE" ]; then
  echo "FAIL: gate not found at $GATE"
  exit 1
fi

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/fail-closed-doctrine-test.XXXXXX")"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# stage_mutroot <dir>
#
# Build a sandbox laid out the way the gate resolves paths:
#   <root>/scripts/<gate>, <root>/61-loop-protection-system, plus the DELIVERY
#   artifacts the gate checks.
#
# The delivery artifacts are minimal stubs ON PURPOSE. A mutation proof must
# disarm exactly ONE variable; everything the gate checks other than the detector
# has to be PRESENT and passing, or the gate short-circuits on an unrelated arm
# and the mutation proves nothing. (It did exactly that during development: the
# DELIVERY half returned UNDETERMINED before the enforcement half ever ran, and
# cases 7b/8b failed for a reason that had nothing to do with the detector.)
stage_mutroot() {
  local root="$1"
  mkdir -p "$root/scripts"
  cp "$GATE" "$root/scripts/" 2>/dev/null || return 1
  cp -R "$SKILL" "$root/61-loop-protection-system" 2>/dev/null || return 1
  printf '%s\n' '# stub: delivery-half fixture' \
                'FAIL_CLOSED_DEPENDENCY_V1' > "$root/scripts/apply-fleet-standards.sh"
  printf '%s\n' '# stub: delivery-half fixture' \
                'apply-fleet-standards' > "$root/update-skills.sh"
  printf '%s\n' '# stub: delivery-half fixture' \
                'apply-fleet-standards.sh' > "$root/install.sh"
  return 0
}

# ---------------------------------------------------------------------------
# (1) CONTROL — the REAL shipped doctrine must PASS.
# Without this, every "exits 1" below would be satisfied by a gate that is simply
# broken and fails on everything.
# ---------------------------------------------------------------------------
echo "--- (1) CONTROL: the real repo doctrine passes ---"
out1="$(bash "$GATE" --quiet 2>&1)"; rc1=$?
if [ "$rc1" -eq 0 ]; then
  pass "1a: the real AGENTS.md + real D6 detector exit 0"
else
  fail "1a: the real doctrine exited $rc1 (expected 0). Output: $out1"
fi

# ---------------------------------------------------------------------------
# (2) The N40 rule REMOVED must FAIL.
# ---------------------------------------------------------------------------
echo "--- (2) a doctrine with N40 stripped exits 1 ---"
STRIPPED="$SANDBOX/AGENTS-no-n40.md"
MUT_SRC="$DOCTRINE" MUT_DST="$STRIPPED" python3 - <<'PY'
import io, os, sys
s = io.open(os.environ["MUT_SRC"], encoding="utf-8").read()
low = s.lower()
i = low.find("<!-- fail_closed_dependency_v1 -->")
if i == -1:
    sys.stderr.write("FIXTURE FAILED: no N40 marker in the source doctrine\n")
    sys.exit(1)
j = low.find("<!-- credential_check_v2 -->", i)
if j == -1:
    sys.stderr.write("FIXTURE FAILED: could not find the end of the N40 block\n")
    sys.exit(1)
io.open(os.environ["MUT_DST"], "w", encoding="utf-8").write(s[:i] + s[j:])
PY
if [ $? -ne 0 ]; then
  fail "2a: could not build the N40-stripped fixture"
else
  out2="$(bash "$GATE" "$STRIPPED" 2>&1)"; rc2=$?
  if [ "$rc2" -eq 1 ]; then
    pass "2a: a doctrine missing the N40 block exits 1 (THE GATE FIRES)"
  else
    fail "2a: N40-stripped doctrine exited $rc2 (expected 1). Output: $out2"
  fi
  if printf '%s' "$out2" | grep -q 'N40'; then
    pass "2b: the failure names N40"
  else
    fail "2b: the failure does not name N40. Output: $out2"
  fi
fi

# ---------------------------------------------------------------------------
# (3) The Blockers BOUND removed must FAIL — this is the regression that matters
# most, because the unbounded "try 5-10 methods" instruction is what CAUSED the
# incident. N40 can be perfectly present elsewhere and the hole still be open.
# ---------------------------------------------------------------------------
echo "--- (3) removing the Blockers bound exits 1, even with N40 intact ---"
UNBOUND="$SANDBOX/AGENTS-unbound.md"
MUT_SRC="$DOCTRINE" MUT_DST="$UNBOUND" python3 - <<'PY'
import io, os, re, sys
s = io.open(os.environ["MUT_SRC"], encoding="utf-8").read()
# Drop ONLY the bound blockquote inside the Blockers section.
out = re.sub(r"> ⛔ \*\*BOUNDED BY N40\.\*\*.*?\n\n", "", s,
             count=1, flags=re.S)
out = out.replace("**capability failures only; see N40**", "")
if out == s:
    sys.stderr.write("FIXTURE FAILED: the Blockers bound was not found\n")
    sys.exit(1)
io.open(os.environ["MUT_DST"], "w", encoding="utf-8").write(out)
PY
if [ $? -ne 0 ]; then
  fail "3a: could not build the unbound fixture"
else
  out3="$(bash "$GATE" "$UNBOUND" 2>&1)"; rc3=$?
  if [ "$rc3" -eq 1 ]; then
    pass "3a: N40 present but Blockers UNBOUND still exits 1"
  else
    fail "3a: unbound doctrine exited $rc3 (expected 1). Output: $out3"
  fi
fi

# ---------------------------------------------------------------------------
# (4) UNDETERMINED never collapses into 0.
# ---------------------------------------------------------------------------
echo "--- (4) an absent / empty doctrine exits 3, never 0 ---"
out4a="$(bash "$GATE" "$SANDBOX/nope/does-not-exist.md" 2>&1)"; rc4a=$?
if [ "$rc4a" -eq 3 ]; then
  pass "4a: an ABSENT doctrine exits 3 (UNDETERMINED), not 0"
else
  fail "4a: absent doctrine exited $rc4a (expected 3). Output: $out4a"
fi
: > "$SANDBOX/empty.md"
out4b="$(bash "$GATE" "$SANDBOX/empty.md" 2>&1)"; rc4b=$?
if [ "$rc4b" -eq 3 ]; then
  pass "4b: an EMPTY doctrine exits 3 (UNDETERMINED), not 0"
else
  fail "4b: empty doctrine exited $rc4b (expected 3). Output: $out4b"
fi

# ---------------------------------------------------------------------------
# (5) usage errors exit 2.
# ---------------------------------------------------------------------------
echo "--- (5) usage errors exit 2 ---"
out5="$(bash "$GATE" --bogus-flag 2>&1)"; rc5=$?
if [ "$rc5" -eq 2 ]; then
  pass "5a: an unknown flag exits 2"
else
  fail "5a: unknown flag exited $rc5 (expected 2). Output: $out5"
fi

# ---------------------------------------------------------------------------
# (6) The D6 detector's own self-test still passes (the detector is not merely
# importable — its whole battery, including the real-corpus control, runs).
# ---------------------------------------------------------------------------
echo "--- (6) the shipped D6 detector self-test passes ---"
out6="$(python3 "$SKILL/scripts/loop_detectors.py" --self-test 2>&1)"; rc6=$?
if [ "$rc6" -eq 0 ]; then
  pass "6a: loop_detectors.py --self-test exits 0"
else
  fail "6a: detector self-test exited $rc6. Output: $out6"
fi
if printf '%s' "$out6" | grep -q 'D6 case: PASS'; then
  pass "6b: the self-test battery includes a D6 case"
else
  fail "6b: no D6 case in the detector self-test. Output: $out6"
fi

# ---------------------------------------------------------------------------
# (7) MUTATION PROOF — the ENFORCEMENT half.
#
# Copy the gate + the skill tree into a sandbox laid out the way the gate
# resolves paths (<root>/scripts/<gate>, <root>/61-loop-protection-system), then
# NEUTER D6 so it always returns no findings. The gate must go RED.
#
# If this case fails, case (1) was passing for some reason other than the
# detector actually running, and the enforcement half of this gate is decorative.
# ---------------------------------------------------------------------------
echo "--- (7) MUTATION PROOF: neuter D6, the gate must go red ---"
MUTROOT="$SANDBOX/mutroot"
stage_mutroot "$MUTROOT"
MUT_DET="$MUTROOT/61-loop-protection-system/scripts/loop_detectors.py"

if [ ! -f "$MUT_DET" ]; then
  fail "7a: could not stage a copy of the detector tree"
else
  MUT_FILE="$MUT_DET" python3 - <<'PY'
import io, os, sys
p = os.environ["MUT_FILE"]
s = io.open(p, encoding="utf-8").read()
needle = "def d6_futile_retry_burst(bursts, thresholds, signatures=None):"
if needle not in s:
    sys.stderr.write("MUTATION DID NOT APPLY - the D6 signature was not found\n")
    sys.exit(1)
# Neuter: the detector still exists, imports fine, and returns nothing ever.
mutated = s.replace(needle, needle + "\n    return []  # MUTANT", 1)
if mutated == s:
    sys.stderr.write("MUTATION DID NOT APPLY - replace was a no-op\n")
    sys.exit(1)
io.open(p, "w", encoding="utf-8").write(mutated)
PY
  mut_applied=$?
  if [ "$mut_applied" -eq 0 ]; then
    pass "7a: the mutation applied (D6 exists and was neutered to return [])"
  else
    fail "7a: the mutation did not apply — the D6 function was not found"
  fi

  out7="$(bash "$MUTROOT/scripts/qc-assert-fail-closed-doctrine.sh" "$DOCTRINE" 2>&1)"; rc7=$?
  if [ "$rc7" -eq 1 ]; then
    pass "7b: with D6 neutered the gate exits 1 — case (1) measures the DETECTOR, not just the markdown"
  else
    fail "7b: neutered D6 exited $rc7 (expected 1). The enforcement half is NOT measuring runtime behaviour. Output: $out7"
  fi
  if printf '%s' "$out7" | grep -q 'did NOT fire'; then
    pass "7c: the failure says the detector did not fire"
  else
    fail "7c: the failure does not name the dead detector. Output: $out7"
  fi
fi

# ---------------------------------------------------------------------------
# (8) SECOND MUTATION — a detector that fires on EVERYTHING must also go red.
# Firing is not the same as discriminating; a count-only D6 would pass (7) and
# still be unshippable, because the real corpus contains a healthy 460-call
# burst it would flag.
# ---------------------------------------------------------------------------
echo "--- (8) MUTATION PROOF: make D6 fire on everything, the gate must go red ---"
MUT2="$SANDBOX/mutroot2"
stage_mutroot "$MUT2"
MUT_DET2="$MUT2/61-loop-protection-system/scripts/loop_detectors.py"

if [ ! -f "$MUT_DET2" ]; then
  fail "8a: could not stage the second detector copy"
else
  MUT_FILE="$MUT_DET2" python3 - <<'PY'
import io, os, sys
p = os.environ["MUT_FILE"]
s = io.open(p, encoding="utf-8").read()
# Disarm exactly ONE variable: the SILENCE RULE. Everything else is untouched.
needle = """        # THE SILENCE RULE - no evidence of futility, no finding, at ANY volume.
        if errors <= 0 and failclosed <= 0:
            continue"""
if needle not in s:
    sys.stderr.write("MUTATION DID NOT APPLY - the silence rule was not found\n")
    sys.exit(1)
mutated = s.replace(needle, "        # MUTANT: silence rule disarmed", 1)
# ...and make volume alone sufficient, i.e. the count-only design.
n2 = """        if calls >= t["p1_burst_calls"] and ratio >= t["p1_error_ratio"]:"""
if n2 not in s:
    sys.stderr.write("MUTATION DID NOT APPLY - the burst face was not found\n")
    sys.exit(1)
mutated = mutated.replace(n2, """        if calls >= t["p1_burst_calls"]:""", 1)
io.open(p, "w", encoding="utf-8").write(mutated)
PY
  mut2_applied=$?
  if [ "$mut2_applied" -eq 0 ]; then
    pass "8a: the second mutation applied (silence rule disarmed, volume made sufficient)"
  else
    fail "8a: the second mutation did not apply"
  fi

  out8="$(bash "$MUT2/scripts/qc-assert-fail-closed-doctrine.sh" "$DOCTRINE" 2>&1)"; rc8=$?
  if [ "$rc8" -eq 1 ]; then
    pass "8b: a count-only D6 exits 1 — the healthy 460-call control is asserted with real weight"
  else
    fail "8b: count-only D6 exited $rc8 (expected 1). The silent control is NOT enforced. Output: $out8"
  fi
  if printf '%s' "$out8" | grep -q 'healthy'; then
    pass "8c: the failure names the healthy control burst"
  else
    fail "8c: the failure does not name the control. Output: $out8"
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi

echo "PASS: all N40 fail-closed doctrine gate checks pass"
exit 0
