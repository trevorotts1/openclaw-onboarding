#!/usr/bin/env bash
# D3 — inventory the work that is in flight at the pin: open pull requests,
# remote heads, and local worktrees, including detached ones. Read-only.
#
# Usage: bash evidence/search/inventory_work_in_progress.sh <repo-root>

set -uo pipefail

ROOT="${1:?repo root required}"
PIN="9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865"

echo "=== pin ==="
echo "$PIN"

echo
echo "=== run time (UTC) ==="
date -u +"%Y-%m-%dT%H:%M:%SZ"

echo
echo "=== open pull requests (gh, live at run time) ==="
gh pr list --repo trevorotts1/openclaw-onboarding --state open --limit 200 \
  --json number,headRefName,isDraft,updatedAt,title \
  --jq '.[] | "\(.number)\t\(.headRefName)\tdraft=\(.isDraft)\t\(.updatedAt)\t\(.title)"'
echo "pr_list_rc=$?"

echo
echo "=== remote heads ==="
git -C "$ROOT" ls-remote --heads origin | wc -l
echo "-- of which pb/* --"
git -C "$ROOT" ls-remote --heads origin 'refs/heads/pb/*' | wc -l

echo
echo "=== local worktrees: branch vs detached ==="
git -C "$ROOT" worktree list --porcelain | awk '
  /^worktree / {wt=$2; next}
  /^detached$/ {print "DETACHED\t" wt; next}
  /^branch / {print "BRANCH\t" wt "\t" $2; next}
'

echo
echo "=== local worktree totals ==="
echo -n "total_worktrees="; git -C "$ROOT" worktree list | wc -l
echo -n "attached_to_branch="; git -C "$ROOT" worktree list --porcelain | grep -c '^branch '
echo -n "detached="; git -C "$ROOT" worktree list --porcelain | grep -c '^detached$'

echo
echo "=== local pb/* branches ==="
git -C "$ROOT" for-each-ref --format='%(refname:short) %(objectname)' refs/heads/pb/ | head -60
echo -n "local_pb_branch_count="
git -C "$ROOT" for-each-ref --format='%(refname:short)' refs/heads/pb/ | wc -l
