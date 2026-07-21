#!/usr/bin/env bash
# Publish a version tag safely from a SHARED local tag namespace.
#
# THE BUG THIS PREVENTS
# --------------------
# Many concurrent agents share this machine's local tags. Plain
#   git push origin v20.0.90
# resolves the NAME against whatever local tag exists. If another agent already
# created v20.0.90 on its own unmerged branch, git happily publishes THAT
# commit. The remote then carries a version tag pointing at code that is not on
# main, which makes G2 demand a CHANGELOG entry no one on main has — turning
# main and every open PR red until the branch merges. One mis-push jams the
# whole merge lane. That is exactly how v20.0.89 and v20.0.90 got orphaned.
#
# THE FIX
# -------
# Never push a tag by name. Resolve it to an explicit SHA, prove that SHA is on
# main, and push the SHA into the tag ref.
#
# Usage:
#   scripts/push-version-tag.sh v20.0.91 [<commit-ish>] [--remote origin]
#
# With no <commit-ish> the tag must already exist locally and is verified in
# place. With one, the tag is (re)created locally at that commit first.

set -euo pipefail

REMOTE="origin"
TAG=""
COMMITISH=""

while [ $# -gt 0 ]; do
  case "$1" in
    --remote) REMOTE="$2"; shift 2 ;;
    -h|--help) sed -n '1,30p' "$0"; exit 0 ;;
    *)
      if [ -z "$TAG" ]; then TAG="$1"; elif [ -z "$COMMITISH" ]; then COMMITISH="$1";
      else echo "Unexpected argument: $1" >&2; exit 2; fi
      shift ;;
  esac
done

if [ -z "$TAG" ]; then
  echo "Usage: $0 vX.Y.Z [<commit-ish>] [--remote origin]" >&2
  exit 2
fi

if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "ERROR: '$TAG' is not a vX.Y.Z version tag." >&2
  exit 2
fi

echo "Fetching $REMOTE (main + tags) ..."
git fetch --quiet "$REMOTE" main --tags

MAIN_REF="refs/remotes/${REMOTE}/main"
git rev-parse --verify --quiet "${MAIN_REF}^{commit}" >/dev/null || {
  echo "ERROR: ${MAIN_REF} does not resolve." >&2; exit 2; }

# Refuse to clobber a tag that is already published at a different commit.
REMOTE_TARGET="$(git ls-remote --tags "$REMOTE" "refs/tags/${TAG}^{}" | awk '{print $1}')"

if [ -n "$COMMITISH" ]; then
  TARGET="$(git rev-parse --verify "${COMMITISH}^{commit}")"
  if git rev-parse --verify --quiet "refs/tags/${TAG}" >/dev/null; then
    EXISTING="$(git rev-parse "refs/tags/${TAG}^{commit}")"
    if [ "$EXISTING" != "$TARGET" ]; then
      echo "Local tag $TAG exists at ${EXISTING:0:12} but you asked for ${TARGET:0:12}."
      echo "It probably belongs to another agent. Recreating LOCALLY only."
      git tag -d "$TAG" >/dev/null
      git tag -a "$TAG" "$TARGET" -m "$TAG"
    fi
  else
    git tag -a "$TAG" "$TARGET" -m "$TAG"
  fi
else
  git rev-parse --verify --quiet "refs/tags/${TAG}" >/dev/null || {
    echo "ERROR: local tag $TAG does not exist and no commit-ish was given." >&2; exit 2; }
  TARGET="$(git rev-parse "refs/tags/${TAG}^{commit}")"
fi

# Annotated only — G1 rejects lightweight tags.
if [ "$(git cat-file -t "refs/tags/${TAG}")" != "tag" ]; then
  echo "ERROR: $TAG is a LIGHTWEIGHT tag. Only annotated tags may be published." >&2
  echo "  git tag -d $TAG && git tag -a $TAG $TARGET -m \"$TAG — <description>\"" >&2
  exit 1
fi

# THE LOAD-BEARING CHECK: the target must already be on main.
if ! git merge-base --is-ancestor "$TARGET" "$MAIN_REF"; then
  echo "" >&2
  echo "REFUSING TO PUSH: $TAG -> ${TARGET:0:12} is NOT an ancestor of ${REMOTE}/main." >&2
  echo "" >&2
  echo "  $(git log -1 --format='%h %s' "$TARGET")" >&2
  echo "" >&2
  echo "This is the mis-push that orphans a tag. Merge the branch FIRST, then tag" >&2
  echo "the resulting merge commit on main:" >&2
  echo "  git fetch $REMOTE main" >&2
  echo "  scripts/push-version-tag.sh $TAG ${REMOTE}/main" >&2
  exit 1
fi

if [ -n "$REMOTE_TARGET" ] && [ "$REMOTE_TARGET" != "$TARGET" ]; then
  echo "" >&2
  echo "REFUSING TO PUSH: $TAG already exists on $REMOTE at ${REMOTE_TARGET:0:12}," >&2
  echo "which differs from ${TARGET:0:12}. Moving a published tag is a force" >&2
  echo "operation on shared history and is an OPERATOR decision." >&2
  exit 1
fi

if [ -n "$REMOTE_TARGET" ]; then
  echo "✓ $TAG already published at ${TARGET:0:12} and on main. Nothing to do."
  exit 0
fi

# Push the resolved SHA into the tag ref — never the bare name.
echo "Pushing $TAG -> ${TARGET:0:12} (verified on ${REMOTE}/main) ..."
git push "$REMOTE" "refs/tags/${TAG}"
echo "✓ Published $TAG at ${TARGET:0:12}."
