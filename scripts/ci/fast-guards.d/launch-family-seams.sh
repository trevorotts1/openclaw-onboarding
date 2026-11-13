#!/usr/bin/env bash
# Folded from .github/workflows/launch-family-seams.yml (job "launch-family-seams"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set +e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
fg_rc=0
if [ "$fg_rc" -eq 0 ]; then
( # step: Install test dependencies
echo "--- step: Install test dependencies"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"Install test dependencies\" failed (exit $fg_rc)"' EXIT
python -m pip install --quiet jsonschema pytest pillow==10.4.0
)
[ $? -eq 0 ] || fg_rc=1
fi
if [ "$fg_rc" -eq 0 ]; then
( # step: Required files present (a missing test is red, never skipped)
echo "--- step: Required files present (a missing test is red, never skipped)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"Required files present (a missing test is red, never skipped)\" failed (exit $fg_rc)"' EXIT
missing=0
for f in \
  49-signature-funnel/scripts/test_thankyou_translator.py \
  49-signature-funnel/scripts/test_upsell_wrapper.py \
  49-signature-funnel/scripts/test_downsell_wrapper.py \
  49-signature-funnel/scripts/test_sop_lockstep.py \
  49-signature-funnel/scripts/test_compile_launch_route.py \
  78-signature-product-selection/tests/test_selection_binding_native_ids.py \
  79-signature-order-form/tests/test_schema_lockstep_44.py \
  80-signature-upsell/verify.py \
  50-email-engine/tests/test_seam_49_to_44.py \
  shared-utils/signature_launch/tests/test_schema_copies_identical.py \
  scripts/bump-version.sh \
  scripts/check-doc-currency-guards.sh ; do
  if [ ! -f "$f" ]; then echo "MISSING: $f"; missing=1; fi
done
for d in 78-signature-product-selection/tests 79-signature-order-form/tests \
         81-signature-downsell/tests 82-signature-thank-you/tests ; do
  if [ ! -d "$d" ]; then echo "MISSING DIR: $d"; missing=1; fi
done
exit "$missing"
)
[ $? -eq 0 ] || fg_rc=1
fi
( # step: 49 thank-you translator
echo "--- step: 49 thank-you translator"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"49 thank-you translator\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" python3 49-signature-funnel/scripts/test_thankyou_translator.py
)
[ $? -eq 0 ] || fg_rc=1
( # step: 49 upsell wrapper
echo "--- step: 49 upsell wrapper"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"49 upsell wrapper\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" python3 49-signature-funnel/scripts/test_upsell_wrapper.py
)
[ $? -eq 0 ] || fg_rc=1
( # step: 49 downsell wrapper
echo "--- step: 49 downsell wrapper"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"49 downsell wrapper\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" python3 49-signature-funnel/scripts/test_downsell_wrapper.py
)
[ $? -eq 0 ] || fg_rc=1
( # step: 49 route graph hash (issue 56)
echo "--- step: 49 route graph hash (issue 56)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"49 route graph hash (issue 56)\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" python3 49-signature-funnel/scripts/test_compile_launch_route.py
)
[ $? -eq 0 ] || fg_rc=1
( # step: 49 SOP-LOCKED lockstep (issue 41)
echo "--- step: 49 SOP-LOCKED lockstep (issue 41)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"49 SOP-LOCKED lockstep (issue 41)\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" python3 49-signature-funnel/scripts/test_sop_lockstep.py
)
[ $? -eq 0 ] || fg_rc=1
( # step: 78 tests (includes the 78 to 79 adapter test, issue 11)
echo "--- step: 78 tests (includes the 78 to 79 adapter test, issue 11)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"78 tests (includes the 78 to 79 adapter test, issue 11)\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" python3 -m unittest discover -s 78-signature-product-selection/tests
)
[ $? -eq 0 ] || fg_rc=1
( # step: 79 tests (includes the 44 schema lockstep, issue 53)
echo "--- step: 79 tests (includes the 44 schema lockstep, issue 53)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"79 tests (includes the 44 schema lockstep, issue 53)\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" python3 -m unittest discover -s 79-signature-order-form/tests
)
[ $? -eq 0 ] || fg_rc=1
( # step: 80 verify
echo "--- step: 80 verify"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"80 verify\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" python3 80-signature-upsell/verify.py
)
[ $? -eq 0 ] || fg_rc=1
( # step: 81 tests
echo "--- step: 81 tests"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"81 tests\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" python3 -m unittest discover -s 81-signature-downsell/tests
)
[ $? -eq 0 ] || fg_rc=1
( # step: 82 tests
echo "--- step: 82 tests"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"82 tests\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" python3 -m unittest discover -s 82-signature-thank-you/tests
)
[ $? -eq 0 ] || fg_rc=1
( # step: Seam 49 to 50 to 44 (issue 14)
echo "--- step: Seam 49 to 50 to 44 (issue 14)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"Seam 49 to 50 to 44 (issue 14)\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" python3 -m unittest discover -s 50-email-engine/tests -p 'test_seam_49_to_44.py'
)
[ $? -eq 0 ] || fg_rc=1
( # step: Page-request schema copies identical (issue 85)
echo "--- step: Page-request schema copies identical (issue 85)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"Page-request schema copies identical (issue 85)\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" python3 -m unittest discover -s shared-utils/signature_launch/tests -p 'test_schema_copies_identical.py'
)
[ $? -eq 0 ] || fg_rc=1
( # step: Fast guard, version markers
echo "--- step: Fast guard, version markers"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"Fast guard, version markers\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" bash scripts/bump-version.sh --check
)
[ $? -eq 0 ] || fg_rc=1
( # step: Fast guard, doc currency
echo "--- step: Fast guard, doc currency"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards launch-family-seams: step \"Fast guard, doc currency\" failed (exit $fg_rc)"' EXIT
env -i HOME="$(mktemp -d)" PATH="$PATH" bash scripts/check-doc-currency-guards.sh
)
[ $? -eq 0 ] || fg_rc=1
exit "$fg_rc"
