#!/usr/bin/env bash
# Verify a single pushed tag's commit is on origin/main. Run by
# .github/workflows/tag-on-main-guard.yml on EVERY push of a tag matching
# v*, so a mis-pushed tag is caught within seconds of landing on the remote.
#
# WHY THIS EXISTS
# ----------------
# scripts/push-version-tag.sh already refuses to publish an orphaned tag --
# but only when a push runs THROUGH it. On 2026-09-29 a different lane pushed
# annotated tag v25.2.16 straight (bypassing the wrapper) onto 3aa92592, an
# unmerged draft-PR commit. The real v25.2.16 release on main could not take
# its own name until the wrong tag was manually deleted and retagged.
#
# This script is the backstop for every OTHER way a tag can reach the remote.
# It never moves or deletes anything -- rewriting a published tag is shared
# history and stays an operator decision -- it only fails loudly and names
# the exact fix.
#
# Usage:
#   scripts/check-tag-on-main.sh <tag> [--main-ref REF]
# Exit 0 = the tag's commit is on REF (default origin/main).
# Exit 1 = it is not, or the tag does not exist in this checkout.
# Exit 2 = usage/internal error (e.g. REF does not resolve).

set -euo pipefail

TAG=""
MAIN_REF="origin/main"

while [ $# -gt 0 ]; do
  case "$1" in
    --main-ref) MAIN_REF="$2"; shift 2 ;;
    -h|--help) sed -n '1,20p' "$0"; exit 0 ;;
    *)
      if [ -z "$TAG" ]; then TAG="$1"; else echo "Unexpected argument: $1" >&2; exit 2; fi
      shift ;;
  esac
done

if [ -z "$TAG" ]; then
  echo "Usage: $0 <tag> [--main-ref REF]" >&2
  exit 2
fi

if ! git rev-parse --verify --quiet "refs/tags/${TAG}" >/dev/null; then
  echo "ERROR: tag '$TAG' does not exist in this checkout." >&2
  exit 1
fi

if ! git rev-parse --verify --quiet "${MAIN_REF}^{commit}" >/dev/null; then
  echo "ERROR: '$MAIN_REF' does not resolve to a commit." >&2
  exit 2
fi

TARGET="$(git rev-parse "refs/tags/${TAG}^{commit}")"
MAIN_SHA="$(git rev-parse "${MAIN_REF}")"

if git merge-base --is-ancestor "$TARGET" "$MAIN_REF"; then
  echo "OK: $TAG -> ${TARGET:0:12} is on ${MAIN_REF} (${MAIN_SHA:0:12})."
  exit 0
fi

echo "" >&2
echo "TAG-ON-MAIN GUARD FAILED: $TAG -> ${TARGET:0:12} is NOT an ancestor of ${MAIN_REF} (${MAIN_SHA:0:12})." >&2
echo "" >&2
echo "  $(git log -1 --format='%h %s' "$TARGET")" >&2
echo "" >&2
echo "This tag points at code that never merged to main. It is squatting on a" >&2
echo "release name, so the real release under this name cannot be cut until" >&2
echo "this is resolved. Moving or deleting a published tag rewrites shared" >&2
echo "history that other programs may depend on -- THIS IS AN OPERATOR" >&2
echo "DECISION, never automated. Options:" >&2
echo "" >&2
echo "  1) Delete the wrong tag and retag the real release commit:" >&2
echo "       git push origin :refs/tags/$TAG" >&2
echo "       git tag -d $TAG 2>/dev/null || true" >&2
echo "       scripts/push-version-tag.sh $TAG $MAIN_REF" >&2
echo "" >&2
echo "  2) Leave the wrong tag alone and release under the next version name" >&2
echo "     instead (bump, then scripts/push-version-tag.sh <next-tag> $MAIN_REF)." >&2
exit 1
