#!/usr/bin/env bash
# Folded from .github/workflows/design-library-and-credential-disclosure-guards.yml (job "T1-02/T0-06: the design-library gate fails closed"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Syntax-check the gate
echo "--- step: Syntax-check the gate"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards design-library-and-credential-disclosure-guards--t1-02-t0-06: step \"Syntax-check the gate\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash -n 45-design-intelligence-library/qc-design-intelligence-library.sh
bash -n tests/unit/design-library-gate-fails-closed.test.sh
python3 -c "import json,sys; json.load(open('45-design-intelligence-library/PREREQS.json'))"
echo "OK: gate, test and prerequisite manifest parse"
)
( # step: The gate fails closed, and does not false-fail an installed box
echo "--- step: The gate fails closed, and does not false-fail an installed box"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards design-library-and-credential-disclosure-guards--t1-02-t0-06: step \"The gate fails closed, and does not false-fail an installed box\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash tests/unit/design-library-gate-fails-closed.test.sh
)
( # step: The pre-fix gate really passed the same fixtures
echo "--- step: The pre-fix gate really passed the same fixtures"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards design-library-and-credential-disclosure-guards--t1-02-t0-06: step \"The pre-fix gate really passed the same fixtures\" failed (exit $fg_rc)"' EXIT
export PRE_FIX_SHA=391a92e9a9ae5fcbc8d583853b2f286c3b32bae8
set -euo pipefail
PRE="$(mktemp -d)"
git show "${PRE_FIX_SHA}:45-design-intelligence-library/qc-design-intelligence-library.sh" > "$PRE/gate.sh"
# The pinned gate calls the validator of the same era (it still has the SHORT/MEDIUM/LONG tier table that
# KIE prompt rule 12 retired from the current validator), so the historical comparison takes the pinned
# validator too. The current gate and validator are not touched.
git show "${PRE_FIX_SHA}:45-design-intelligence-library/scripts/diu_validator.py" > "$PRE/diu_validator.py"
work="$(mktemp -d)"
cp -R 45-design-intelligence-library/. "$work/"
rm -rf "$work/.git"
cp "$PRE/gate.sh" "$work/qc-design-intelligence-library.sh"
cp "$PRE/diu_validator.py" "$work/scripts/diu_validator.py"
# Plant committed client data — synthetic, no real client name.
printf '# SI-999 synthetic fixture style card\n' > "$work/library/single-image-designs/SI-999_synthetic-fixture.md"
mkdir -p "$work/library/personal-photo-shoot/synthetic-fixture-identity"
printf '# IDENTITY — synthetic fixture\n' > "$work/library/personal-photo-shoot/synthetic-fixture-identity/IDENTITY.md"
git -C "$work" init -q
git -C "$work" config user.email fixture@localhost
git -C "$work" config user.name fixture
git -C "$work" add -A
git -C "$work" commit -q -m fixture
set +e
out="$(cd "$work" && bash qc-design-intelligence-library.sh 2>&1)"; rc=$?
set -e
if [ $rc -eq 0 ]; then
  echo "OK: the pre-fix gate exited 0 with committed client data — the defect is real and the new test is capable of catching it"
else
  echo "FAIL: the pre-fix gate already failed (rc=$rc); the new test proves nothing"
  printf '%s\n' "$out"
  exit 1
fi
)
