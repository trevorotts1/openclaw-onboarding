#!/usr/bin/env bash
# release.sh — one-command bump + changelog entry + annotated tag + push
#
# This is the ONLY supported way to cut a release of openclaw-onboarding.
# It ensures:
#   1. All 9 version markers are updated atomically via bump-version.sh
#   2. cc-compat.json onboardingVersion is updated to match
#   3. A CHANGELOG entry header is prepended (edit the body after running)
#   4. An annotated git tag is created at HEAD + pushed before the next commit
#      so that the G1 CI guard (version-without-tag) passes on push to main
#
# Usage:
#   ./scripts/release.sh vX.Y.Z "Short description for CHANGELOG + tag message"
#   ./scripts/release.sh vX.Y.Z "Short description" --no-push   # local only
#
# Prerequisites:
#   - Run from the repo root (or anywhere in the repo)
#   - git working tree must be CLEAN (no uncommitted changes)
#   - The new version must be > the current /version
#   - python3 must be on PATH
#
# What it does (in order):
#   1.  Validates args + clean working tree
#   2.  Calls bump-version.sh vX.Y.Z to rewrite all 9 markers
#   3.  Updates cc-compat.json onboardingVersion
#   4.  Prepends a CHANGELOG entry header (## [vX.Y.Z] — date — description)
#   5.  Commits all changes with a conventional-commit message
#   6.  Creates an annotated tag vX.Y.Z at the new commit
#   7.  Pushes commit + tag to origin (unless --no-push)
#
# CI guards satisfied by this flow:
#   G1 (version-without-tag): tag is created BEFORE the next push, so G1
#      never fires. release.sh is the only way to bump /version, ensuring
#      the tag always exists when CI sees the new version on main.
#   G2 (tag-without-changelog): CHANGELOG entry is added in the same commit
#      as the bump, so G2 passes immediately.
#   G3 (skill-content-without-version-bump): release.sh does NOT change
#      skill content; skill bumps happen in feature PRs before release.sh
#      is called. If skill content is staged alongside release.sh the author
#      must bump that skill's skill-version.txt themselves.
#
# To add release notes after running:
#   Edit CHANGELOG.md — add the body below the header line that release.sh
#   created. Then `git add CHANGELOG.md && git commit --amend --no-edit`
#   (the tag will need to be re-created: delete + recreate pointing at the
#   amended commit). Or simply add a follow-up commit before the next release.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# ─── Helpers ─────────────────────────────────────────────────────────────────
die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "  $*"; }

semver_gt() {
  # Returns 0 if $1 > $2 (both in vX.Y.Z or X.Y.Z form)
  python3 - "$1" "$2" <<'PYEOF'
import sys
def parse(v):
    return tuple(int(x) for x in v.lstrip("v").split("."))
a, b = sys.argv[1], sys.argv[2]
sys.exit(0 if parse(a) > parse(b) else 1)
PYEOF
}

# ─── Parse args ──────────────────────────────────────────────────────────────
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  grep '^#' "$0" | sed 's/^# \{0,2\}//'
  exit 0
fi

TARGET="${1:-}"
DESCRIPTION="${2:-}"
NO_PUSH="${3:-}"

if [ -z "$TARGET" ] || [ -z "$DESCRIPTION" ]; then
  die "Usage: $0 vX.Y.Z \"Short description\" [--no-push]"
fi

# Validate version format
if ! echo "$TARGET" | grep -qE '^v[0-9]+\.[0-9]+\.[0-9]+$'; then
  die "Version must be vX.Y.Z format (got '$TARGET')"
fi

# ─── Sanity checks ───────────────────────────────────────────────────────────
echo ""
echo "release.sh: preparing $TARGET — \"$DESCRIPTION\""
echo ""

# Must be a git repo
git rev-parse --git-dir > /dev/null 2>&1 || die "Not in a git repository"

# Must be on main or a release branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "main" ]; then
  echo "WARNING: releasing from branch '$CURRENT_BRANCH' (not main)."
  echo "  Press Enter to continue or Ctrl-C to abort."
  read -r
fi

# Working tree must be clean
if ! git diff --quiet HEAD; then
  die "Working tree has uncommitted changes. Commit or stash them first."
fi

# Tag must not already exist
if git rev-parse --verify "refs/tags/$TARGET" >/dev/null 2>&1; then
  die "Tag $TARGET already exists. Did you mean a different version?"
fi

# New version must be greater than current
CURRENT_VER=$(head -1 version | tr -d '[:space:]')
if ! semver_gt "$TARGET" "$CURRENT_VER"; then
  die "New version $TARGET must be greater than current $CURRENT_VER"
fi

info "Current version : $CURRENT_VER"
info "Target version  : $TARGET"
info "Description     : $DESCRIPTION"
echo ""

# ─── Step 1: bump all 9 version markers ──────────────────────────────────────
echo "[1/6] Bumping all 9 version markers to $TARGET ..."
bash "$SCRIPT_DIR/bump-version.sh" "$TARGET"
echo ""

# ─── Step 2: update cc-compat.json onboardingVersion ─────────────────────────
CC_COMPAT="$REPO_ROOT/cc-compat.json"
if [ -f "$CC_COMPAT" ]; then
  echo "[2/6] Updating cc-compat.json onboardingVersion to $TARGET ..."
  python3 - <<PYEOF
import json, sys
p = "$CC_COMPAT"
d = json.load(open(p))
d["onboardingVersion"] = "$TARGET"
with open(p, "w") as f:
    json.dump(d, f, indent=2)
    f.write("\n")
print(f"  cc-compat.json onboardingVersion = {d['onboardingVersion']}")
PYEOF
else
  echo "[2/6] cc-compat.json not found — skipping (not required pre-v11.5)"
fi
echo ""

# ─── Step 3: prepend CHANGELOG entry ─────────────────────────────────────────
echo "[3/6] Prepending CHANGELOG entry for $TARGET ..."
CHANGELOG="$REPO_ROOT/CHANGELOG.md"
TODAY=$(date -u +%Y-%m-%d)
ENTRY="## [$TARGET]  -  $TODAY  -  $DESCRIPTION"

if [ ! -f "$CHANGELOG" ]; then
  echo "# Changelog" > "$CHANGELOG"
  echo "" >> "$CHANGELOG"
fi

# Prepend the entry at the top (after any leading # Changelog header line)
python3 - <<PYEOF
import re
p = "$CHANGELOG"
entry = "$ENTRY"
content = open(p).read()

# If file starts with "# Changelog" (or similar), insert after that line.
# Otherwise prepend at the very top.
if re.match(r'^#\s+Changelog', content, re.IGNORECASE):
    # Insert after the first line
    lines = content.split("\n", 1)
    new = lines[0] + "\n\n" + entry + "\n\n" + (lines[1].lstrip("\n") if len(lines) > 1 else "")
else:
    new = entry + "\n\n" + content

open(p, "w").write(new)
print(f"  Prepended: {entry}")
PYEOF
echo ""

# ─── Step 4: stage all changed files ─────────────────────────────────────────
echo "[4/6] Staging changed files ..."
git add version install.sh update-skills.sh CHANGELOG.md \
  "23-ai-workforce-blueprint/skill-version.txt" \
  "23-ai-workforce-blueprint/templates/role-library/_index.json" \
  "23-ai-workforce-blueprint/templates/role-library/_qc-summary.md" \
  README.md \
  DIRECT-TO-AGENT-UPDATE-MESSAGE.md \
  ${CC_COMPAT:+cc-compat.json}
echo "  Staged."
echo ""

# ─── Step 5: commit ──────────────────────────────────────────────────────────
echo "[5/6] Committing release $TARGET ..."
git commit -m "$(cat <<COMMIT_MSG
chore(release): bump to $TARGET — $DESCRIPTION

Version bump applied to all 9 markers (bump-version.sh).
CHANGELOG entry prepended.
cc-compat.json onboardingVersion updated.
Annotated tag $TARGET will be created in this release.sh run.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
COMMIT_MSG
)"
RELEASE_SHA=$(git rev-parse HEAD)
info "Commit: $RELEASE_SHA"
echo ""

# ─── Step 6: create annotated tag ────────────────────────────────────────────
echo "[6/6] Creating annotated tag $TARGET at $RELEASE_SHA ..."
git tag -a "$TARGET" "$RELEASE_SHA" \
  -m "$TARGET — $DESCRIPTION

Release of openclaw-onboarding.
Commit: $RELEASE_SHA
Tagged by release.sh on $TODAY."
info "Tag created: $TARGET"
echo ""

# ─── Push (unless --no-push) ─────────────────────────────────────────────────
if [ "${NO_PUSH:-}" = "--no-push" ]; then
  echo "Skipping push (--no-push). To push manually:"
  echo "  git push origin main && git push origin $TARGET"
else
  echo "Pushing commit + tag to origin ..."
  git push origin "$CURRENT_BRANCH"
  git push origin "$TARGET"
  echo "  Pushed commit and tag $TARGET."
fi

echo ""
echo "========================================"
echo "  Release $TARGET complete."
echo "  Merge SHA  : $RELEASE_SHA"
echo "  Tag        : $TARGET"
echo "  CHANGELOG  : edit $CHANGELOG to add release notes body"
echo "========================================"
