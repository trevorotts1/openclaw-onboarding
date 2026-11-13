#!/usr/bin/env bash
# Folded from .github/workflows/role-workspace-root-collapse-guard.yml (job "Role-workspace root must never collapse onto the company root"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Self-test the pattern in BOTH directions, then assert this tree is clean
echo "--- step: Self-test the pattern in BOTH directions, then assert this tree is clean"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards role-workspace-root-collapse-guard: step \"Self-test the pattern in BOTH directions, then assert this tree is clean\" failed (exit $fg_rc)"' EXIT
set -euo pipefail

PATTERN='workspace_root[[:space:]]*=[[:space:]]*company_root'

# Scanned extensions are deliberately limited to the two languages the role-workspace
# builders are written in. Do NOT add --include='*.yml': THIS FILE contains the literal
# pattern in its comments and in the self-test seeds below, and would self-match.
SCAN=(-rn "$PATTERN" --include='*.py' --include='*.sh' --exclude-dir=.git)

probe="$(mktemp -d)"
trap 'rm -rf "$probe"' EXIT
mkdir -p "$probe/seeded" "$probe/clean"

# ---- Self-test A (sensitivity): a seeded defect MUST be detected. -----------------
# Without this, a pattern that quietly stopped matching would leave a gate that
# reports PASS forever while the defect walks straight past it.
printf 'def process_company(company_root, workspace_root):\n    workspace_root = company_root\n' \
  > "$probe/seeded/seeded.py"
printf '#!/usr/bin/env bash\nworkspace_root=company_root\n' \
  > "$probe/seeded/seeded.sh"
if ! grep -q "${SCAN[@]}" "$probe/seeded" >/dev/null 2>&1; then
  echo "FAIL (self-test A): the guard pattern no longer matches a seeded defect."
  echo "This gate is BLIND -- it would report PASS on a tree that carries the collapse."
  exit 1
fi
echo "self-test A: pattern DETECTS a seeded defect in .py and .sh (gate is live)"

# ---- Self-test B (specificity): correct code must NOT be flagged. -----------------
# Without this, a pattern broadened until it matched everything would be a gate that
# can only ever fail -- which is how the previous version of this check behaved.
printf 'def process_company(company_root, workspace_root):\n    return workspace_root\n\n\nprocess_company(company, Path(paths["workspace"]))\n' \
  > "$probe/clean/clean.py"
printf '#!/usr/bin/env bash\nworkspace_root="$WORKSPACE"\ncompany_root="$COMPANY"\n' \
  > "$probe/clean/clean.sh"
if grep -q "${SCAN[@]}" "$probe/clean" >/dev/null 2>&1; then
  echo "FAIL (self-test B): the guard pattern matches CORRECT code."
  grep "${SCAN[@]}" "$probe/clean" || true
  echo "This gate cries wolf -- it would block every PR regardless of content."
  exit 1
fi
echo "self-test B: pattern IGNORES correct code (gate can still pass)"

# ---- The assertion. Repo-wide, not path-scoped. ----------------------------------
hits="$(grep "${SCAN[@]}" . || true)"
if [ -n "$hits" ]; then
  echo ""
  echo "FAIL: the role-workspace root is collapsed onto the company root on this tree:"
  printf '%s\n' "$hits"
  echo ""
  echo "This makes every role symlink point at a path that does not exist, so role"
  echo "agents lose AGENTS.md / TOOLS.md / USER.md and fail silently on the next roll."
  echo ""
  echo "If you are seeing this on a pull request, the branch forked before the fix."
  echo "Rebase it on origin/main -- do not merge it as-is."
  exit 1
fi
echo ""
echo "PASS: no collapsed role-workspace root anywhere in this tree"
)
