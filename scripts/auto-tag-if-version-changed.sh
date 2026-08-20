#!/usr/bin/env bash
# auto-tag-if-version-changed.sh -- cut + push the annotated release tag the
# INSTANT a version bump lands on main, with NO agent action required.
#
# THE PROBLEM THIS CLOSES (2026-08-20 delay audit, Section 2 D3 / Section 4(b) /
# Section 7 item 3): G1b (version-consistency.yml) fails on EVERY open PR
# whenever main carries an untagged release, because G1b walks main's ENTIRE
# release history, not any one PR's diff. That happened 7 separate times
# 2026-08-18 -> 2026-08-20. The standing fix was "an agent notices, then runs
# scripts/push-version-tag.sh by hand" -- which is also why PRs #942, #944,
# #951 existed at all: someone opened a whole PR just to get a human/agent to
# look at the repo and remember to tag it. #944 alone sat 14.4h and blocked
# two real fixes (#945, #946) behind it.
#
# THE FIX: run this on every push to main (see
# .github/workflows/auto-tag-on-merge.yml). If /version differs from the
# previous commit on main, the tag for the NEW version is cut and pushed
# immediately, in the same CI run that observed the merge. No agent has to
# remember, so the failure mode is no longer "someone forgot" -- it is
# structurally impossible for main to sit untagged for longer than one CI run.
#
# THIS IS DELIBERATELY A THIN WRAPPER. The "did /version change since the
# previous commit" comparison is copy-identical to G1's own logic
# (version-consistency.yml, job check-version-tag-guard) so the two can never
# disagree about WHEN a tag is due. The actual tag-cutting is fully delegated
# to scripts/push-version-tag.sh, which already has the hardened
# SHA-resolution + ancestry-proof logic that prevents orphaned tags (shared
# local tag namespace, one agent pushing another's unmerged tag by name --
# see that script's own header for the v20.0.89/v20.0.90 incident it fixes).
# This script adds NO new tagging logic; it only removes the human
# "someone has to run it" step.
#
# Usage:
#   scripts/auto-tag-if-version-changed.sh [--remote origin]
#
# Must be run from a checkout with full history (fetch-depth 0) at the commit
# that was just pushed to main (HEAD == the new main tip; HEAD^1 == what main
# was before this push). Exits 0 whether or not a tag was needed. Exits
# non-zero ONLY if a tag WAS needed and scripts/push-version-tag.sh refused or
# failed -- i.e. a real problem worth failing the build over (see that
# script's "REFUSING TO PUSH" cases: not-an-ancestor, or a differing tag
# already published at that name).

set -euo pipefail

REMOTE="origin"
while [ $# -gt 0 ]; do
  case "$1" in
    --remote) REMOTE="$2"; shift 2 ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "Unexpected argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f "$REPO_ROOT/version" ]; then
  echo "ERROR: $REPO_ROOT/version not found -- not an openclaw-onboarding checkout?" >&2
  exit 2
fi

CURRENT_VER=$(head -1 version | tr -d '[:space:]')
echo "Current /version on HEAD: $CURRENT_VER"

PREV_SHA=$(git rev-parse HEAD^1 2>/dev/null || echo "")
if [ -z "$PREV_SHA" ]; then
  echo "No previous commit (root commit) -- nothing to compare against. Exiting."
  exit 0
fi

PREV_VER=$(git show "${PREV_SHA}:version" 2>/dev/null | head -1 | tr -d '[:space:]' || echo "")

if [ "$CURRENT_VER" = "$PREV_VER" ]; then
  echo "Version unchanged ($CURRENT_VER) since the previous commit on this ref -- no tag due."
  exit 0
fi

if [[ ! "$CURRENT_VER" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "ERROR: /version changed to '$CURRENT_VER', which is not a vX.Y.Z string. Refusing to tag." >&2
  exit 1
fi

echo "Version changed: ${PREV_VER:-<none>} -> $CURRENT_VER. Cutting the annotated tag now ..."
exec "$SCRIPT_DIR/push-version-tag.sh" "$CURRENT_VER" "$(git rev-parse HEAD)" --remote "$REMOTE"
