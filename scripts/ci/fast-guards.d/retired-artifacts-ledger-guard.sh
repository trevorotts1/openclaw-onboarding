#!/usr/bin/env bash
# Folded from .github/workflows/retired-artifacts-ledger-guard.yml (job "_retired.json matches git history"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Verify the retired-artifacts ledger is in sync
set -e -o pipefail
set +e
set -uo pipefail
python3 23-ai-workforce-blueprint/scripts/gen-retired-artifacts-ledger.py --check
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "" >&2
  echo "A canonical role-library file was deleted (or restored) without" >&2
  echo "regenerating the retired-artifacts ledger. Until the ledger records" >&2
  echo "it, no box can ever remove that file — it stays readable forever in" >&2
  echo "the staging tree and in every stray copy inside the skill search path." >&2
  echo "" >&2
  echo "Fix:" >&2
  echo "  python3 23-ai-workforce-blueprint/scripts/gen-retired-artifacts-ledger.py" >&2
  echo "  git add 23-ai-workforce-blueprint/templates/role-library/_retired.json" >&2
fi
exit "$rc"
)
