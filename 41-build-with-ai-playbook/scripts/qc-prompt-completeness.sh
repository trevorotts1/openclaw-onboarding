#!/usr/bin/env bash
# qc-prompt-completeness.sh -- Skill 41.
#
# Two modes:
#   (default) template mode  -- asserts the shipped prompt TEMPLATE carries all 8
#                               required sections. Well-formedness of the skill's
#                               own template. This can NEVER fail on real generated
#                               output because it only ever reads the template.
#   --prompt <file>          -- asserts a REAL generated Build-with-AI prompt carries
#                               all 8 required sections AND minimum content: it is not
#                               a stub, has substantive body text, and left no template
#                               placeholder brackets unfilled. This is the gate that
#                               actually bites on thin/fabricated output; wire it into
#                               Step 6 against the prompt you are about to paste into GHL.
#
# Exit: 0 PASS, 1 FAIL, 2 usage/environment.
set -uo pipefail

MODE="template"
SKILL_DIR=""
PROMPT_FILE=""
MIN_WORDS="${QC_PROMPT_MIN_WORDS:-120}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill-dir) SKILL_DIR="${2:-}"; shift 2;;
    --prompt) MODE="prompt"; PROMPT_FILE="${2:-}"; shift 2;;
    --min-words) MIN_WORDS="${2:-}"; shift 2;;
    -h|--help)
      echo "usage: qc-prompt-completeness.sh [--skill-dir DIR] | --prompt FILE [--min-words N]"; exit 0;;
    *) shift;;
  esac
done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -z "$SKILL_DIR" ]] && SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

REQUIRED_SECTIONS=("Workflow name" "Trigger specification" "Dependency list" "Action sequence" "Conditions" "Webhook configuration" "Settings" "Post-build verification checklist")

# Assert every required section title appears (case-insensitive) in $1. Sets MISSING.
assert_sections() {
  local target="$1"; MISSING=0
  local section
  for section in "${REQUIRED_SECTIONS[@]}"; do
    if ! grep -qi "$section" "$target"; then
      echo "[skill 41 QC] MISSING SECTION: $section"; MISSING=$((MISSING + 1))
    fi
  done
}

if [[ "$MODE" == "prompt" ]]; then
  echo "[skill 41 QC] prompt-completeness (--prompt): checking real generated output..."
  if [[ -z "$PROMPT_FILE" ]]; then echo "[skill 41 QC] FAIL: --prompt requires a file path"; exit 2; fi
  if [[ ! -f "$PROMPT_FILE" ]]; then echo "[skill 41 QC] FAIL: prompt file not found at $PROMPT_FILE"; exit 1; fi

  FAIL=0
  # (1) all 8 sections present in the REAL output
  assert_sections "$PROMPT_FILE"
  if [[ $MISSING -gt 0 ]]; then echo "[skill 41 QC] FAIL: $MISSING section(s) missing from generated prompt"; FAIL=$((FAIL + 1)); fi

  # (2) substantive body -- not a stub. Count words on the real output.
  WORDS="$(wc -w < "$PROMPT_FILE" | tr -d '[:space:]')"; WORDS="${WORDS:-0}"
  if [[ "$WORDS" -lt "$MIN_WORDS" ]]; then
    echo "[skill 41 QC] FAIL: generated prompt is too thin ($WORDS words < $MIN_WORDS floor) -- looks like a stub"; FAIL=$((FAIL + 1))
  fi

  # (3) no unfilled template placeholders left in the output. The shipped template
  #     carries bracketed instruction lines like "[Clear, descriptive name ...]";
  #     a real, filled prompt must not still contain a lone bracketed placeholder.
  PLACEHOLDERS="$(grep -cE '^[[:space:]]*\[[^]]+\][[:space:]]*$' "$PROMPT_FILE" 2>/dev/null | tr -d '[:space:]')"; PLACEHOLDERS="${PLACEHOLDERS:-0}"
  if [[ "$PLACEHOLDERS" -gt 0 ]]; then
    echo "[skill 41 QC] FAIL: $PLACEHOLDERS unfilled template placeholder(s) ([...] lines) still present -- fill every section before building"; FAIL=$((FAIL + 1))
  fi

  if [[ $FAIL -eq 0 ]]; then
    echo "[skill 41 QC] PASS: generated prompt has all 8 sections, $WORDS words, no unfilled placeholders"; exit 0
  fi
  echo "[skill 41 QC] FAIL: generated prompt failed $FAIL completeness check(s)"; exit 1
fi

# ── default: template well-formedness ─────────────────────────────────────────
TEMPLATE="$SKILL_DIR/templates/build-with-ai-prompt-template.md"
echo "[skill 41 QC] prompt-completeness (template): checking..."
if [[ ! -f "$TEMPLATE" ]]; then echo "[skill 41 QC] FAIL: template not found at $TEMPLATE"; exit 1; fi
assert_sections "$TEMPLATE"
if [[ $MISSING -eq 0 ]]; then echo "[skill 41 QC] PASS: all 8 required sections present"; exit 0; else echo "[skill 41 QC] FAIL: $MISSING section(s) missing"; exit 1; fi
