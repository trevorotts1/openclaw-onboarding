#!/usr/bin/env bash
# Folded from .github/workflows/library-lockstep.yml (job "Role/SOP/persona/dept library lockstep (no half-add in any dept)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: register-library-additions.py --check (disk <-> _index.json lockstep)
set -e -o pipefail
set -euo pipefail
GATE="23-ai-workforce-blueprint/scripts/register-library-additions.py"
if [ ! -f "$GATE" ]; then
  echo "FATAL: $GATE not found" >&2
  exit 2
fi
# Exit 7 = a half-add in some department (unregistered file / dead entry /
# duplicate-residue / triple-hyphen orphan / count drift). Exit 2 = could
# not run. Either is a hard fail that blocks the merge.
python3 "$GATE" --check
echo "library-register: every role/SOP/persona/dept on disk is registered in _index.json and vice-versa; counts agree; no duplicate-residue/orphans."
)
( # step: test-library-register.sh (the backstop bites on every half-add class)
set -e -o pipefail
set -euo pipefail
TEST="23-ai-workforce-blueprint/scripts/test-library-register.sh"
if [ ! -f "$TEST" ]; then
  echo "FATAL: $TEST not found" >&2
  exit 2
fi
bash "$TEST"
echo "test-library-register: backstop proven to fail on unregistered role/SOP/persona, dead entry, duplicate-residue, triple-hyphen orphan, and count drift — and to heal via --apply."
)
( # step: hash-content-manifest.py --check (content manifest current after any add)
set -e -o pipefail
set -euo pipefail
HCM="23-ai-workforce-blueprint/scripts/hash-content-manifest.py"
if [ ! -f "$HCM" ]; then
  echo "FATAL: $HCM not found" >&2
  exit 2
fi
python3 "$HCM" --check
echo "content-manifest current: a registration without a content-hash restamp cannot ship."
)
