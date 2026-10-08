#!/usr/bin/env bash
# Folded from .github/workflows/updater-traps-1-and-3-guard.yml (job ".clawdbot pre-clear refuses on a live box; CC bootstrap never clones a second board"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Configure git identity (needed for local test-fixture repos)
set -e
git config --global user.email "ci@example.test"
git config --global user.name "CI"
)
( # step: Syntax-check update-skills.sh (including heredoc payloads)
set -e -o pipefail
set -euo pipefail
bash -n update-skills.sh
# bash -n does NOT parse heredoc bodies. Extract every python3
# heredoc and compile it separately so a broken payload cannot ship.
python3 - <<'PYEOF'
import re, sys
lines = open("update-skills.sh", encoding="utf-8", errors="replace").read().split("\n")
i = n = fails = 0
while i < len(lines):
    m = re.search(r"<<-?'?(PYEOF|PY)'?\s*(\|\||&&|2>|>>|$)", lines[i])
    if m and "python3" in lines[i]:
        tag, start = m.group(1), i + 1
        j = start
        while j < len(lines) and lines[j].strip() != tag:
            j += 1
        n += 1
        try:
            compile("\n".join(lines[start:j]), "heredoc@%d" % (start + 1), "exec")
        except SyntaxError as e:
            fails += 1
            print("FAIL heredoc at line %d: %s" % (start + 1, e))
        i = j
    i += 1
print("python heredocs compiled: %d, failures: %d" % (n, fails))
sys.exit(1 if fails else 0)
PYEOF
)
( # step: Run traps 1+3 regression suite
set -e -o pipefail
set -euo pipefail
bash scripts/test-updater-traps-1-and-3.sh
echo "updater-traps-1-and-3-guard: PASS"
)
( # step: Prove the complete root update path
set -e -o pipefail
set -euo pipefail
bash tests/unit/update-skills-full-scripts-tree.test.sh
python3 tests/unit/cc-runtime-preflight.test.py
python3 tests/unit/fleet-refresh-cc-main-convergence.test.py
bash tests/unit/full-update-path-contract.test.sh
bash scripts/test-loop-protection-wiring.sh
)
