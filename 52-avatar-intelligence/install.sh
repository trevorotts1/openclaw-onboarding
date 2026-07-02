#!/usr/bin/env bash
# install.sh — per-skill installer for Skill 52 (idempotent; re-runs must not abort on identical).
# Copies the skill into the box, marks provers executable, re-pins gate hashes. No git/gh.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
DEST="${SKILLS_DIR:-$HOME/.claude/skills}/52-avatar-intelligence"

mkdir -p "$DEST"
# idempotent copy (cp -f never aborts on identical)
cp -Rf "$HERE"/. "$DEST"/ 2>/dev/null || true
chmod +x "$DEST"/*.sh "$DEST"/scripts/*.py 2>/dev/null || true

# re-pin gate hashes at the install location (LIVE-gate)
python3 "$DEST/scripts/aa_gate_integrity_check.py" --write >/dev/null
echo "installed 52-avatar-intelligence -> $DEST"
echo "next: bash $DEST/preflight.sh   (client provider probe → model-map.json)"
