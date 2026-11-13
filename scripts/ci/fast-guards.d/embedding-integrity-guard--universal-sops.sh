#!/usr/bin/env bash
# Folded from .github/workflows/embedding-integrity-guard.yml (job "universal-sops content manifest"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Check universal-sops content manifest
echo "--- step: Check universal-sops content manifest"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedding-integrity-guard--universal-sops: step \"Check universal-sops content manifest\" failed (exit $fg_rc)"' EXIT
python3 scripts/hash-universal-sops-manifest.py --check
)
