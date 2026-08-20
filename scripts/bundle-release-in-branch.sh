#!/usr/bin/env bash
# bundle-release-in-branch.sh -- fold the version bump + CHANGELOG entry into
# a FIX PR's own branch, so the release ceremony ships in the SAME PR as the
# code it releases.
#
# THE PROBLEM THIS SOLVES (2026-08-20 delay audit, Recommendation R3):
# Six version tags were cut in ~21h (v22.0.51 -> v22.0.56), each demanding a
# CHANGELOG-entry-then-annotated-tag two-step done as its OWN pull request.
# That produced pure-CHANGELOG PRs #942, #944, #951 -- each touching exactly
# one file, CHANGELOG.md, and nothing else. #944 sat 14.4h open->merged and
# blocked two real fixes (#945, #946) behind it in this repo's single-
# merge-writer serialization, for a one-line CHANGELOG entry. See
# CONTROL/DELAY-DIAGNOSIS-FABLE.md Section 2 D3, Section 4(b), Section 7 item 3.
#
# scripts/check-no-standalone-release-pr.py is the CI gate that now REJECTS a
# PR whose entire diff is release-ceremony-only. This script is how you
# comply with the rule it enforces: run it inside the branch that already
# carries your fix, so the bump and the CHANGELOG entry land in the same
# commit(s)/PR as the code.
#
# WHAT THIS DOES (built ON the existing machinery -- does not reinvent it):
#   1. bash scripts/bump-version.sh vX.Y.Z   -- rolls all 10 version markers
#      (the exact same atomic roll scripts/release.sh Step 1 uses)
#   2. Prepends a CHANGELOG.md entry, header format identical to
#      scripts/release.sh Step 3, so extract-changelog-section.py and G2's
#      header-format matcher both still work on it.
#
# WHAT THIS DELIBERATELY DOES NOT DO, unlike scripts/release.sh:
#   - Does NOT commit (you fold the diff into your own fix commit(s))
#   - Does NOT create or push an annotated tag
#   - Does NOT push anything
# All three of those still matter for a real release cut directly on main
# (scripts/release.sh remains the tool for that). For a FIX PR, the tag is
# cut automatically once the PR merges to main -- see
# .github/workflows/auto-tag-on-merge.yml, which calls
# scripts/push-version-tag.sh the moment /version changes on main. No agent
# has to remember to run it by hand.
#
# Usage:
#   scripts/bundle-release-in-branch.sh vX.Y.Z "Short description for CHANGELOG"
#
# Then:
#   git diff                                   # review the bump + entry
#   git add -A && git commit --amend --no-edit # fold into your fix commit
#     (or: git commit -m "..." for a separate commit in the same PR -- either
#      way, the constraint is "same PR", not "same commit")
#   git push
#
# Prerequisites: run from anywhere inside the repo; git working tree may have
# your own uncommitted fix changes already staged/unstaged (this script only
# touches the specific version-marker files + CHANGELOG.md, so it will not
# clobber unrelated in-progress edits).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  grep '^#' "$0" | sed 's/^# \{0,2\}//'
  exit 0
fi

TARGET="${1:-}"
DESCRIPTION="${2:-}"

if [ -z "$TARGET" ] || [ -z "$DESCRIPTION" ]; then
  echo "Usage: $0 vX.Y.Z \"Short description for CHANGELOG\"" >&2
  exit 2
fi

if ! echo "$TARGET" | grep -qE '^v[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "ERROR: version must be vX.Y.Z format (got '$TARGET')" >&2
  exit 2
fi

CURRENT_VER=$(head -1 version 2>/dev/null | tr -d '[:space:]' || echo "")
if [ -z "$CURRENT_VER" ]; then
  echo "ERROR: could not read current version from $REPO_ROOT/version" >&2
  exit 2
fi

NEWER=$(python3 - "$TARGET" "$CURRENT_VER" <<'PYEOF'
import sys
def parse(v):
    return tuple(int(x) for x in v.lstrip("v").split("."))
a, b = sys.argv[1], sys.argv[2]
print("1" if parse(a) > parse(b) else "0")
PYEOF
)
if [ "$NEWER" != "1" ]; then
  echo "ERROR: target $TARGET must be greater than current $CURRENT_VER" >&2
  exit 2
fi

echo "[1/2] Bumping all version markers: $CURRENT_VER -> $TARGET ..."
bash "$SCRIPT_DIR/bump-version.sh" "$TARGET"
echo ""

echo "[2/2] Prepending CHANGELOG entry for $TARGET ..."
CHANGELOG="$REPO_ROOT/CHANGELOG.md"
TODAY=$(date -u +%Y-%m-%d)
ENTRY="## [$TARGET]  -  $TODAY  -  $DESCRIPTION"

if [ ! -f "$CHANGELOG" ]; then
  echo "# Changelog" > "$CHANGELOG"
  echo "" >> "$CHANGELOG"
fi

python3 - <<PYEOF
import re
p = "$CHANGELOG"
entry = "$ENTRY"
content = open(p, encoding="utf-8").read()

if re.match(r'^#\s+Changelog', content, re.IGNORECASE):
    lines = content.split("\n", 1)
    new = lines[0] + "\n\n" + entry + "\n\n" + (lines[1].lstrip("\n") if len(lines) > 1 else "")
else:
    new = entry + "\n\n" + content

open(p, "w", encoding="utf-8").write(new)
print(f"  Prepended: {entry}")
PYEOF
echo ""

echo "========================================"
echo "  Bundled $TARGET into this branch (NOT committed, NOT tagged, NOT pushed)."
echo "  Review with: git diff"
echo "  Fold into your fix commit, then push. The tag is cut automatically on merge."
echo "========================================"
