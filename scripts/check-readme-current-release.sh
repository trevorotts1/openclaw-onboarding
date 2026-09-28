#!/usr/bin/env bash
# check-readme-current-release.sh — README.md must describe the CURRENT release.
#
# WHY THIS EXISTS: the two prose lines below are NOT in scripts/version-markers.json
# (that manifest is deliberately limited to markers that are pure "vX.Y.Z" tokens —
# see its _comment) and nothing rolled or checked them, so they drifted for weeks:
# the top banner sat at "v25.0.16 ... Paired Command Center: v7.1.5" and the
# "## Current release" heading sat at "v25.0.10" while /version and cc-compat.json's
# pinnedTag had moved on to v25.1.95 / v7.6.68. Readers of README.md — the first
# thing anyone sees — got a stale story.
#
# scripts/bump-version.sh now rolls the version numbers in both lines on every
# bump (it does not, and cannot, auto-write the surrounding description — that
# stays hand-authored per release, exactly like CHANGELOG.md entries already are).
# This script is the CI-side half: it fails the build if either number drifts
# from its source of truth.
#
# Usage: bash scripts/check-readme-current-release.sh   (run from repo root)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FAIL=0

REPO_VER=$(head -1 version | tr -d '[:space:]')
echo "Repo /version: $REPO_VER"

# "## Current release: vX.Y.Z" heading must equal /version.
HEADER_VER=$(grep -oE '^## Current release: v[0-9]+\.[0-9]+\.[0-9]+' README.md | head -1 | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || echo "MISSING")
if [ "$HEADER_VER" != "$REPO_VER" ]; then
  echo "README DRIFT: '## Current release: $HEADER_VER' heading != /version ($REPO_VER)"
  FAIL=1
else
  echo "OK: README '## Current release' heading matches /version ($HEADER_VER)"
fi

# Top banner's own version token ("> **vX.Y.Z — ...**") must equal /version.
BANNER_VER=$(grep -oE '^> \*\*v[0-9]+\.[0-9]+\.[0-9]+ ' README.md | head -1 | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || echo "MISSING")
if [ "$BANNER_VER" != "$REPO_VER" ]; then
  echo "README DRIFT: top banner version ($BANNER_VER) != /version ($REPO_VER)"
  FAIL=1
else
  echo "OK: README top banner version matches /version ($BANNER_VER)"
fi

# Banner's "Paired Command Center: **vX.Y.Z**" must equal cc-compat.json's pinnedTag.
if [ -f cc-compat.json ]; then
  PINNED_TAG=$(python3 -c "import json; print(json.load(open('cc-compat.json'))['commandCenter']['pinnedTag'])" 2>/dev/null || echo "MISSING")
  BANNER_CC=$(grep -oE 'Paired Command Center: \*\*v[0-9]+\.[0-9]+\.[0-9]+\*\*' README.md | head -1 | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || echo "MISSING")
  if [ "$BANNER_CC" != "$PINNED_TAG" ]; then
    echo "README DRIFT: banner 'Paired Command Center: $BANNER_CC' != cc-compat.json pinnedTag ($PINNED_TAG)"
    FAIL=1
  else
    echo "OK: README 'Paired Command Center' matches cc-compat.json pinnedTag ($BANNER_CC)"
  fi
else
  echo "WARNING: cc-compat.json not found — paired Command Center check skipped."
fi

if [ "$FAIL" -ne 0 ]; then
  echo ""
  echo "FIX: run ./scripts/bump-version.sh \$(head -1 version) to re-roll both README"
  echo "     version tokens, or edit README.md by hand, then re-run this check."
  exit 1
fi

echo ""
echo "All README current-release markers agree."
