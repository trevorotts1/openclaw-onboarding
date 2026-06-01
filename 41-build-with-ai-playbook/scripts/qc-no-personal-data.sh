#!/usr/bin/env bash
# qc-no-personal-data.sh -- Skill 41. UNIVERSAL gate: zero real client/personal identifiers.
set -uo pipefail
SKILL_DIR=""
while [[ $# -gt 0 ]]; do case "$1" in --skill-dir) SKILL_DIR="${2:-}"; shift 2;; *) shift;; esac; done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -z "$SKILL_DIR" ]] && SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
echo "[skill 41 QC] no-personal-data: scanning $SKILL_DIR ..."
# Banned real identifiers for this operator/business. These must NEVER appear in a universal skill.
BANNED='trevor|blackceo|trevelyn|tsarumi|TrevelynsMini|blackceomacmini'
HITS="$(grep -rniE "$BANNED" "$SKILL_DIR" --include='*.md' --include='*.sh' --include='*.json' 2>/dev/null | grep -vi 'qc-no-personal-data' || true)"
if [[ -n "$HITS" ]]; then
  echo "[skill 41 QC] FAIL: banned real identifier(s) found:"
  echo "$HITS" | head -20
  exit 1
fi
echo "[skill 41 QC] PASS: no banned real identifiers (universal-only respected)"
exit 0
