#!/usr/bin/env bash
# Folded from .github/workflows/binding-laws-guard.yml (job "Prove the binding-laws guard discriminates" + "Enforce binding laws on the pull request range"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Run the discrimination self-check
echo "--- step: Run the discrimination self-check"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards binding-laws-guard: step \"Run the discrimination self-check\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 scripts/test_check_binding_laws.py
)
( # step: Enforce the binding laws
echo "--- step: Enforce the binding laws"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards binding-laws-guard: step \"Enforce the binding laws\" failed (exit $fg_rc)"' EXIT
export BASE_SHA="${FG_BASE_SHA:-}"
export HEAD_SHA="${FG_HEAD_SHA:-}"
export ATTEST="$(case ",${FG_PR_LABELS:-}," in *,binding-laws:attest,*) echo true;; *) echo false;; esac)"
set -euo pipefail
git rev-parse --verify "$BASE_SHA^{commit}" >/dev/null
git rev-parse --verify "$HEAD_SHA^{commit}" >/dev/null
args=(--base "$BASE_SHA" --head "$HEAD_SHA" --json)
if [ "$ATTEST" = "true" ]; then
  echo "::notice::binding-laws:attest is set -- evidence laws are required, not deferred"
  if [ -d binding-laws-evidence ]; then
    args+=(--evidence-dir binding-laws-evidence)
  else
    echo "::error::label binding-laws:attest is set but binding-laws-evidence/ is not in the tree"
    exit 1
  fi
  args+=(--require-evidence)
fi
set +e
python3 scripts/check-binding-laws.py "${args[@]}"
rc=$?
set -e
if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
  echo "::error::binding-laws checker could not run (rc=$rc); that is never a pass"
  exit 2
fi
exit "$rc"
)
