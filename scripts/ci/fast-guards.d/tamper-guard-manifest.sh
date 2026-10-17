#!/usr/bin/env bash
# tamper-guard-manifest - FIX-PLAN Item 32, design Section 2.2 (FP8).
#
# Publish rule: a commit that changes covered content in a sealed tree
# must regenerate that tree's integrity-manifest.json in the SAME
# commit. This guard finds every tree in the repo that carries a
# manifest and checks the manifest against the tree (digest consistency
# plus every covered file's hash). PR CI holds no fleet key, so the
# HMAC signature is verified on the box, where the key lives; this
# guard is the key-free half of the same check.
#
# Opt-in per tree by construction: a tree with no manifest is not a
# sealed tree yet and is skipped. Trees adopt manifests at publish
# time through shared-utils/tamper_guard.py generate.
set -u
cd "$(git rev-parse --show-toplevel)" || exit 2

found=0
failed=0
while IFS= read -r manifest; do
  tree="$(dirname "$manifest")"
  found=$((found + 1))
  if ! python3 shared-utils/tamper_guard.py ci-check "$tree" >/dev/null; then
    echo "tamper-guard-manifest: STALE or DIVERGED manifest in $tree"
    echo "  Regenerate it in the same commit:"
    echo "  python3 shared-utils/tamper_guard.py generate \"$tree\" --slug <slug>"
    failed=1
  fi
done < <(find . -name integrity-manifest.json -not -path './.git/*' | sort)

if [ "$found" -eq 0 ]; then
  echo "tamper-guard-manifest: no sealed trees in this checkout yet (publish-time adoption); PASS"
  exit 0
fi
if [ "$failed" -ne 0 ]; then
  exit 1
fi
echo "tamper-guard-manifest: $found sealed tree(s) verified; PASS"
exit 0
