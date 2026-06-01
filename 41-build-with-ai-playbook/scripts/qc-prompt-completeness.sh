#!/usr/bin/env bash
# qc-prompt-completeness.sh -- Skill 41. Asserts the prompt template carries all 8 required sections.
set -uo pipefail
SKILL_DIR=""
while [[ $# -gt 0 ]]; do case "$1" in --skill-dir) SKILL_DIR="${2:-}"; shift 2;; *) shift;; esac; done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -z "$SKILL_DIR" ]] && SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$SKILL_DIR/templates/build-with-ai-prompt-template.md"
echo "[skill 41 QC] prompt-completeness: checking..."
if [[ ! -f "$TEMPLATE" ]]; then echo "[skill 41 QC] FAIL: template not found at $TEMPLATE"; exit 1; fi
REQUIRED_SECTIONS=("Workflow name" "Trigger specification" "Dependency list" "Action sequence" "Conditions" "Webhook configuration" "Settings" "Post-build verification checklist")
MISSING=0
for section in "${REQUIRED_SECTIONS[@]}"; do
  if ! grep -qi "$section" "$TEMPLATE"; then echo "[skill 41 QC] MISSING SECTION: $section"; MISSING=$((MISSING + 1)); fi
done
if [[ $MISSING -eq 0 ]]; then echo "[skill 41 QC] PASS: all 8 required sections present"; exit 0; else echo "[skill 41 QC] FAIL: $MISSING section(s) missing"; exit 1; fi
