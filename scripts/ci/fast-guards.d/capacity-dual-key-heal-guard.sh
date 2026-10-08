#!/usr/bin/env bash
# Folded from .github/workflows/capacity-dual-key-heal-guard.yml (job "capacity-monitor heals both maxConcurrent keys"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Shell syntax
set -e -o pipefail
set -euo pipefail
bash -n install.sh
bash -n scripts/capacity-monitor.sh
bash -n tests/unit/capacity-dual-key-heal.test.sh
)
( # step: writer must reconcile agents.defaults.maxConcurrent (regression guard)
set -e -o pipefail
set -euo pipefail
if ! grep -q 'defaults\["maxConcurrent"\] = safe' scripts/capacity-monitor.sh; then
  echo "FAIL: capacity-monitor.sh no longer assigns agents.defaults.maxConcurrent."
  echo "      That is the single-key writer that left 500 unhealed for 5 days."
  exit 1
fi
echo "OK: dual-key writer present."
)
( # step: capacity dual-key heal self-test
set -e -o pipefail
set -euo pipefail
bash tests/unit/capacity-dual-key-heal.test.sh
)
( # step: ANTI-VACUITY: the single-key writer must turn this suite RED
set -e -o pipefail
set -euo pipefail
cp scripts/capacity-monitor.sh /tmp/capacity-monitor.sh.orig
# Reconstruct the pre-fix, subagents-only writer.
python3 - <<'PY'
p = "scripts/capacity-monitor.sh"
s = open(p).read()
a = 'defaults_changed = has_defaults_key and (prev_defaults != safe)'
b = 'if has_defaults_key:\n    defaults["maxConcurrent"] = safe\n'
assert a in s and b in s, "mutation anchors missing — update this guard"
s = s.replace(a, 'defaults_changed = False').replace(b, '')
open(p, "w").write(s)
PY
if bash tests/unit/capacity-dual-key-heal.test.sh > /tmp/mutant.txt 2>&1; then
  cp /tmp/capacity-monitor.sh.orig scripts/capacity-monitor.sh
  echo "FAIL: the suite PASSED against the single-key writer — it cannot detect the defect it exists for."
  cat /tmp/mutant.txt
  exit 1
fi
cp /tmp/capacity-monitor.sh.orig scripts/capacity-monitor.sh
echo "OK: single-key writer is caught. Failures observed:"
grep 'FAIL:' /tmp/mutant.txt || true
)
( # step: Summary
set -e -o pipefail
echo "capacity-dual-key-heal-guard: PASS — both keys reconciled, strict-schema key never created, install.sh clamps down instead of overwriting to 100, runaway overrides warn loudly."
)
