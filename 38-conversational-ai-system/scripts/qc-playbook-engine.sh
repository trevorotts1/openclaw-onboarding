#!/usr/bin/env bash
# qc-playbook-engine.sh (U-16) - run the playbook_engine.py unit test suite.
#
# playbook_engine.py is the CANONICAL parser for Skill 38 Layer 2 conversation
# workflow playbooks. Every other gate (qc-tool-gating.sh, qc-workflow-exits.sh,
# qc-playbook-declares.sh, qc-playbook-doc.sh metadata parsing, qc-workflow-
# visual.sh) and scripts/31-generate-workflow-visual.sh shell out to it instead
# of parsing markdown themselves. This gate proves the engine itself is sound:
# it runs the unit tests (good fixture + one deliberately broken fixture per
# grammar family) and requires a clean exit 0.
#
# Exit codes: 0 = engine unit tests pass; 1 = a test failed; 2 = engine or
#             tests not found (repo layout moved).
#
# Wiring: this gate is invoked by scripts/11-run-qc-checklist.sh and by the CI
# workflow .github/workflows/qc-static.yml (added in the wiring wave).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE="$SKILL_ROOT/tools/playbook_engine.py"
TESTS="$SKILL_ROOT/tools/tests/test_playbook_engine.py"

if [ ! -f "$ENGINE" ] || [ ! -f "$TESTS" ]; then
  echo "qc-playbook-engine: engine or tests not found under $SKILL_ROOT/tools/ (repo layout moved?)"
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "qc-playbook-engine: python3 not found on PATH."
  exit 2
fi

echo "=== qc-playbook-engine: playbook_engine.py unit tests ==="
echo "engine: $ENGINE"
echo ""

# py_compile first so a syntax error is a crisp failure, not a test error.
if ! python3 -m py_compile "$ENGINE" "$TESTS"; then
  echo "RESULT: FAIL - python3 -m py_compile failed on the engine or its tests."
  exit 1
fi

rc=0
( cd "$SKILL_ROOT" && python3 -m unittest tools.tests.test_playbook_engine ) || rc=$?

echo ""
if [ "$rc" -eq 0 ]; then
  echo "RESULT: PASS - playbook_engine.py unit tests are green."
else
  echo "RESULT: FAIL - playbook_engine.py unit tests failed (exit $rc)."
fi
exit "$rc"
