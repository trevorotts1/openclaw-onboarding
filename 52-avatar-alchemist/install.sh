#!/usr/bin/env bash
# install.sh — per-skill installer for Skill 52 (idempotent; re-runs must not abort on identical).
# Copies the skill into the box, marks provers executable, re-pins gate hashes. No git/gh.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
DEST="${SKILLS_DIR:-$HOME/.claude/skills}/52-avatar-alchemist"

# hermetic: never let a prover import materialize .pyc into the source tree
# during install/verify (the leak this closes: __pycache__/*.pyc embeds the
# OPERATOR'S absolute source path in co_filename — 6 such files shipped
# before this fix, including the stale pre-merge name "52-avatar-intelligence").
export PYTHONDONTWRITEBYTECODE=1
find "$HERE" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$HERE" -name "*.pyc" -delete 2>/dev/null || true

mkdir -p "$DEST"
# idempotent copy (cp -f never aborts on identical). rsync when available so
# __pycache__/*.pyc (and any other build cruft) is excluded at copy time, not
# merely deleted afterward on the source side; cp fallback deletes any that
# slipped through on the DESTINATION after copying.
if command -v rsync >/dev/null 2>&1; then
  rsync -a --exclude='__pycache__/' --exclude='*.pyc' "$HERE"/ "$DEST"/
else
  cp -Rf "$HERE"/. "$DEST"/ 2>/dev/null || true
  find "$DEST" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
  find "$DEST" -name "*.pyc" -delete 2>/dev/null || true
fi
chmod +x "$DEST"/*.sh "$DEST"/scripts/*.py 2>/dev/null || true

# re-pin gate hashes at the install location (LIVE-gate)
PYTHONDONTWRITEBYTECODE=1 python3 "$DEST/scripts/aa_gate_integrity_check.py" --write >/dev/null
# belt+suspenders: re-pinning can itself compile a .pyc; sweep once more.
find "$DEST" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$DEST" -name "*.pyc" -delete 2>/dev/null || true
echo "installed 52-avatar-alchemist -> $DEST (hermetic: zero .pyc shipped/generated at install)"
echo "next: bash $DEST/preflight.sh   (client provider probe → model-map.json)"
