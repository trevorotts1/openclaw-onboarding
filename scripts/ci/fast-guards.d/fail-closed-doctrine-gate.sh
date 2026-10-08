#!/usr/bin/env bash
# Folded from .github/workflows/fail-closed-doctrine-gate.yml (job "N40 fail-closed doctrine + D6 enforcement"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check every shipped shell file
set -e -o pipefail
set -uo pipefail
rc=0
for f in scripts/qc-assert-fail-closed-doctrine.sh \
         scripts/apply-fleet-standards.sh \
         tests/unit/fail-closed-doctrine-gate.test.sh; do
  if bash -n "$f"; then
    echo "ok: $f"
  else
    echo "::error::$f failed bash -n"
    rc=1
  fi
done
exit $rc
)
( # step: D6 detector self-test
set -e -o pipefail
set -uo pipefail
python3 61-loop-protection-system/scripts/loop_detectors.py --self-test
)
( # step: The gate passes on the real repo doctrine
set -e -o pipefail
set -uo pipefail
bash scripts/qc-assert-fail-closed-doctrine.sh
)
( # step: Unit test (includes both mutation proofs)
set -e -o pipefail
set -uo pipefail
bash tests/unit/fail-closed-doctrine-gate.test.sh
)
( # step: A doctrine missing N40 must never exit 0
set -e -o pipefail
set -uo pipefail
python3 - <<'PY'
import io
s = io.open("AGENTS.md", encoding="utf-8").read()
low = s.lower()
i = low.find("<!-- fail_closed_dependency_v1 -->")
j = low.find("<!-- credential_check_v2 -->", i if i != -1 else 0)
assert i != -1 and j != -1, "fixture build failed: N40 markers not found"
io.open("/tmp/no-n40.md", "w", encoding="utf-8").write(s[:i] + s[j:])
PY
set +e
bash scripts/qc-assert-fail-closed-doctrine.sh /tmp/no-n40.md >/dev/null 2>&1
rc=$?
set -e
if [ "$rc" != "1" ]; then
  echo "::error::qc-assert-fail-closed-doctrine.sh exited $rc on a doctrine with N40 REMOVED (expected 1) — the gate is not firing"
  exit 1
fi
echo "N40-stripped doctrine correctly exits 1"
)
( # step: An absent doctrine must exit 3, not 0
set -e -o pipefail
set -uo pipefail
set +e
bash scripts/qc-assert-fail-closed-doctrine.sh /tmp/definitely-not-here.md >/dev/null 2>&1
rc=$?
set -e
if [ "$rc" != "3" ]; then
  echo "::error::an ABSENT doctrine exited $rc (expected 3 UNDETERMINED)"
  exit 1
fi
echo "absent doctrine correctly exits 3"
)
