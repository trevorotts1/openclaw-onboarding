#!/usr/bin/env bash
# Folded from .github/workflows/memory-activator-guard.yml (job "Skill 31: the activator is correct, complete and atomic (T0-45, T2-27, T2-28)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Shell syntax
set -e -o pipefail
set -euo pipefail
bash -n 31-upgraded-memory-system/scripts/activate-memory-stack.sh
bash -n 31-upgraded-memory-system/qc-upgraded-memory-system.sh
bash -n 31-upgraded-memory-system/validate.sh
bash -n tests/unit/memory-activator-correct-atomic.test.sh
echo "OK: every Skill 31 shell file parses"
)
( # step: The live configuration is written by exactly ONE statement
set -e -o pipefail
set -euo pipefail
python3 - <<'PY'
import re, sys
src = open("31-upgraded-memory-system/scripts/activate-memory-stack.sh").read()
# Strip comments so only executable code is measured.
bare = "\n".join(l for l in src.split("\n") if not l.lstrip().startswith("#"))
# Both Python mutations must target the STAGED file, never the live one.
if 'python3 - "$OC_CONFIG"' in bare:
    print("FAIL: a configuration mutation still targets the LIVE openclaw.json")
    sys.exit(1)
staged_targets = bare.count('python3 - "$OC_STAGED"')
if staged_targets != 2:
    print(f"FAIL: expected 2 staged mutations, found {staged_targets}")
    sys.exit(1)
installs = len(re.findall(r'mv -f "\$OC_STAGED" "\$OC_CONFIG"', bare))
if installs != 1:
    print(f"FAIL: expected exactly 1 atomic install of the staged file, found {installs}")
    sys.exit(1)
if 'openclaw memory status || true' in bare:
    print("FAIL: the runtime status call is still swallowed by '|| true'")
    sys.exit(1)
print("OK: both mutations are staged; one atomic install; the status call is checked")
PY
)
( # step: Activator suite (with the mutation proof)
set -e -o pipefail
bash tests/unit/memory-activator-correct-atomic.test.sh
)
( # step: The corpus embed-once invariant is unregressed
set -e -o pipefail
bash tests/unit/memory-corpus-no-defaults-extrapaths.test.sh
)
