#!/usr/bin/env bash
# Folded from .github/workflows/class-kit-gate.yml (job "Class-Kit gate — passes GOOD fixture, AUTO-FAILS BAD fixture"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Ensure unzip is present
set -e
sudo apt-get update -y && sudo apt-get install -y unzip
)
( # step: Materialize the GOOD and BAD fixtures
set -e
chmod +x 23-ai-workforce-blueprint/test-fixtures/make-class-kit-fixtures.sh
bash 23-ai-workforce-blueprint/test-fixtures/make-class-kit-fixtures.sh "$RUNNER_TEMP/ck-fixtures"
echo "Deck slide count (raw):"
unzip -l "$RUNNER_TEMP"/ck-fixtures/good-kit/deck/*.pptx | grep -cE 'ppt/slides/slide[0-9]+\.xml'
)
( # step: GOOD fixture MUST PASS (gate exit 0)
set -e
chmod +x 23-ai-workforce-blueprint/scripts/qc-class-kit-gate.sh
set +e
bash 23-ai-workforce-blueprint/scripts/qc-class-kit-gate.sh "$RUNNER_TEMP/ck-fixtures/good-kit"
rc=$?
set -e
echo "GOOD fixture gate exit code: $rc"
if [ "$rc" -ne 0 ]; then
  echo "::error::Class-Kit gate REJECTED the GOOD fixture (expected PASS / exit 0, got $rc)"
  exit 1
fi
echo "GOOD fixture passed the gate as expected."
)
( # step: BAD fixture MUST AUTO-FAIL (gate exit 1)
set -e
set +e
bash 23-ai-workforce-blueprint/scripts/qc-class-kit-gate.sh "$RUNNER_TEMP/ck-fixtures/bad-kit"
rc=$?
set -e
echo "BAD fixture gate exit code: $rc"
if [ "$rc" -eq 0 ]; then
  echo "::error::Class-Kit gate PASSED the text-only BAD fixture (expected AUTO-FAIL / exit 1). The gate is not enforcing."
  exit 1
fi
echo "BAD fixture AUTO-FAILED the gate as expected (exit $rc)."
)
( # step: Summary
set -e
echo "Class-Kit gate self-test complete:"
echo "  GOOD fixture -> PASS (exit 0)"
echo "  BAD  fixture -> AUTO-FAIL (exit 1)"
echo "The enforcement gate is wired and self-testing in CI."
)
