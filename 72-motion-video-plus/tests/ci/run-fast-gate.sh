#!/usr/bin/env bash
# MG-043 fast gate for Skill 72 Motion Graphics V2.
#
# This is the exact command sequence the CI workflow
# (.github/workflows/skill72-motion-graphics-tests.yml) runs for the
# per-change gate. Heavy evidence (real renders through both engines)
# stays in the full suite (npm test in 72-motion-video-plus/runtime);
# this gate is the bounded per-change subset: install verification,
# render-free TypeScript suites, the Python unit suite, the test
# matrix registry check, and a sabotage self-test proving the gate
# actually bites.
#
# Sabotage self-test: the corpus suite is re-run against a copy of the
# fixtures with one assembly input removed (the powerpoint job's
# dataset file). A correct gate goes RED on that tree: the valid job
# must stop validating. If the sabotaged run passes, this gate fails,
# because a gate that cannot go red is not a gate. When MG-022's
# assembler tests land under tests/unit, step 3 exercises the real
# assembler the same way.
#
# Exit 0 only when every step passes. "FAST GATE PASS" is printed only
# on a fully green run.

set -u
CI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$CI_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$SKILL_ROOT/.." && pwd)"
WORK_DIR="$CI_DIR/work"
mkdir -p "$WORK_DIR"

fail=0
step() {
  echo ""
  echo "=== fast gate: $1 ==="
}

step "verify.sh (install verifier)"
if bash "$SKILL_ROOT/verify.sh" > "$WORK_DIR/verify.log" 2>&1; then
  echo "PASS verify.sh"
else
  echo "FAIL verify.sh (see $WORK_DIR/verify.log)" >&2
  cat "$WORK_DIR/verify.log" >&2
  fail=1
fi

step "runtime fast suites (npm run test:fast)"
cd "$SKILL_ROOT/runtime"
if [ ! -d node_modules ] || [ "${CI:-}" = "true" ]; then
  npm ci > "$WORK_DIR/npm-ci.log" 2>&1 || { echo "FAIL npm ci (see $WORK_DIR/npm-ci.log)" >&2; fail=1; }
fi
if [ "$fail" -eq 0 ]; then
  if npm run test:fast > "$WORK_DIR/test-fast.log" 2>&1; then
    echo "PASS npm run test:fast"
    grep -E "cases passed|checks passed" "$WORK_DIR/test-fast.log" || true
  else
    echo "FAIL npm run test:fast (see $WORK_DIR/test-fast.log)" >&2
    tail -30 "$WORK_DIR/test-fast.log" >&2
    fail=1
  fi
fi

step "python unit suite"
cd "$REPO_ROOT"
if python3 -m unittest discover -s 72-motion-video-plus/tests/unit > "$WORK_DIR/python-unit.log" 2>&1; then
  echo "PASS python unit suite"
  tail -3 "$WORK_DIR/python-unit.log"
else
  echo "FAIL python unit suite (see $WORK_DIR/python-unit.log)" >&2
  tail -30 "$WORK_DIR/python-unit.log" >&2
  fail=1
fi

step "test matrix registry"
if python3 "$SKILL_ROOT/tests/check_matrix.py" > "$WORK_DIR/matrix.log" 2>&1; then
  echo "PASS matrix registry"
  cat "$WORK_DIR/matrix.log"
else
  echo "FAIL matrix registry (see $WORK_DIR/matrix.log)" >&2
  cat "$WORK_DIR/matrix.log" >&2
  fail=1
fi

step "sabotage self-test (gate must go red on a broken job input)"
SABOTAGE_DIR="$WORK_DIR/sabotage"
rm -rf "$SABOTAGE_DIR"
mkdir -p "$SABOTAGE_DIR"
cp -r "$SKILL_ROOT/tests/fixtures" "$SABOTAGE_DIR/fixtures"
rm "$SABOTAGE_DIR/fixtures/modes/powerpoint_graphic/data/bars.json"
cd "$SKILL_ROOT/runtime"
if MOTION_FIXTURES_ROOT="$SABOTAGE_DIR/fixtures" node dist/tests/run-corpus.js > "$WORK_DIR/sabotage.log" 2>&1; then
  echo "FAIL sabotage self-test: corpus suite PASSED on a fixture tree missing an assembly input; the gate does not bite" >&2
  fail=1
else
  echo "PASS sabotage self-test: corpus suite went red on the sabotaged tree"
  grep -E "^FAIL" "$WORK_DIR/sabotage.log" | head -3 || true
fi
rm -rf "$SABOTAGE_DIR"

echo ""
if [ "$fail" -eq 0 ]; then
  echo "FAST GATE PASS"
  exit 0
fi
echo "FAST GATE FAIL" >&2
exit 1
