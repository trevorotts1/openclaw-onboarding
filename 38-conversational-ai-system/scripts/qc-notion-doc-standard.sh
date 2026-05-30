#!/usr/bin/env bash
# qc-notion-doc-standard.sh — machine-enforce the NOTION CLIENT-DOC STANDARD
# (references/notion-client-doc-standard.md).
#
# WHY: the client Notion setup doc must follow ONE structure, in ONE order, every time.
# This gate asserts the standard doc carries the hard "EVERY CLIENT NOTION SETUP DOC
# MUST INCLUDE ALL OF THE FOLLOWING, IN THIS ORDER" headline + the full ordered mandatory
# list (items 1-12), and COMPOSES the existing scripts/qc-reference-sheet.sh (which drives
# the generator offline and asserts the rendered doc matches), so a regression that guts
# the standard or the generator FAILS the build.
#
# WHAT IT CHECKS (from the repo alone — CI-safe, BASH-only so it respects the .py
# claude-/anthropic ban):
#   1. references/notion-client-doc-standard.md exists.
#   2. The hard "...MUST INCLUDE ALL OF THE FOLLOWING, IN THIS ORDER" headline is present.
#   3. Each of the 12 ordered mandatory items is present (Quick-Start-first, URL block,
#      two-block Authorization, Content-Type split, FLAT 23-key body, tags-first +
#      manual-fill + Build-with-AI-shape-only + post-build VERIFY, Communication Playbooks,
#      VPS-vs-Mac, how-it-works LAST, every-value-its-own-block, Telegram delivery, UNIVERSAL).
#   4. The doc references the enforcing gates (qc-reference-sheet.sh + qc-notify-client-doc.sh + this gate).
#   5. The composed qc-reference-sheet.sh --require-manual-fill PASSES (generator matches).
#   6. SKILL.md / INSTRUCTIONS.md carry a pointer to the standard.
#
# Exit codes: 0 = clean; 1 = at least one mandatory item missing.
#
# Usage:
#   bash scripts/qc-notion-doc-standard.sh
#   bash scripts/qc-notion-doc-standard.sh --skill-dir DIR
#   bash scripts/qc-notion-doc-standard.sh --doc PATH         # negative-test a fixture
#   bash scripts/qc-notion-doc-standard.sh --doc-only         # skip the generator compose

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOC=""
DOC_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --doc)       DOC="$2"; DOC_ONLY=1; shift 2 ;;
    --doc-only)  DOC_ONLY=1; shift ;;
    -h|--help)   sed -n '1,34p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

[ -n "$DOC" ] || DOC="$SKILL_DIR/references/notion-client-doc-standard.md"

FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

echo "=== qc-notion-doc-standard: NOTION CLIENT-DOC STANDARD gate ==="
echo "doc : $DOC"
echo ""

if [ ! -f "$DOC" ]; then
  echo "  [FAIL] standard doc MISSING: $DOC"
  echo ""
  echo "RESULT: FAIL"
  exit 1
fi

# 1. Hard ordered headline.
grep -qiE 'EVERY CLIENT NOTION SETUP DOC MUST INCLUDE ALL OF THE FOLLOWING, IN THIS ORDER' "$DOC" \
  && pass "Section 0 ordered mandatory headline present" \
  || fail "missing the 'EVERY CLIENT NOTION SETUP DOC MUST INCLUDE ALL OF THE FOLLOWING, IN THIS ORDER' headline"

# 2. The 12 ordered mandatory items (match on the load-bearing concept).
declare -a ITEM_KEYS=(
  "Quick Start FIRST|🚀 Quick Start"
  "Webhook URL|hooks/<HOOK_NAME>|own code block"
  "Authorization as TWO|TWO separate code blocks|block 1 = exactly .Authorization"
  "Content-Type as two code blocks|Content-Type.*Key/Value split|block 1 = .Content-Type"
  "FLAT 23-key Raw Body|23-key Raw Body|ghl-raw-body-json-standard"
  "tags FIRST|Build-with-AI builds the SHAPE only|SHAPE only|post-build VERIFY"
  "Your Communication Playbooks|Help me build a .purpose. playbook|trigger word|I Do / You Do"
  "VPS-vs-Mac|VPS .Hostinger Docker. vs Mac|vps-vs-mac-install-considerations"
  "How-it-works explanation LAST|how-it-works LAST|Full Reference"
  "every copyable value in its own code block|its own code block|own copy button"
  "delivered to the client via Telegram|via Telegram"
  "UNIVERSAL|no personal/client data|generic placeholder"
)
declare -a ITEM_NAMES=(
  "(1) Quick Start FIRST"
  "(2) Webhook URL — own code block"
  "(3) Authorization as TWO separate code blocks"
  "(4) Content-Type as two code blocks"
  "(5) FLAT 23-key Raw Body — own code block"
  "(6) Build step: tags-first + manual-fill + Build-with-AI-shape-only + post-build VERIFY"
  "(7) Your Communication Playbooks (CTA + trigger word + I-Do/You-Do + brainstorm)"
  "(8) VPS-vs-Mac install-considerations"
  "(9) How-it-works explanation LAST"
  "(10) every copyable value in its own code block"
  "(11) delivered to the client via Telegram"
  "(12) UNIVERSAL — no personal/client data"
)
i=0
for keyset in "${ITEM_KEYS[@]}"; do
  if grep -qiE "$keyset" "$DOC"; then
    pass "ordered mandatory item present: ${ITEM_NAMES[$i]}"
  else
    fail "ordered mandatory item MISSING: ${ITEM_NAMES[$i]}"
  fi
  i=$((i+1))
done

# 3. The doc names its enforcing gates.
grep -qF 'qc-reference-sheet.sh' "$DOC"   && pass "doc references qc-reference-sheet.sh"   || fail "doc must reference qc-reference-sheet.sh"
grep -qF 'qc-notify-client-doc.sh' "$DOC" && pass "doc references qc-notify-client-doc.sh" || fail "doc must reference qc-notify-client-doc.sh"
grep -qF 'qc-notion-doc-standard.sh' "$DOC" && pass "doc references its own gate (qc-notion-doc-standard.sh)" || fail "doc must reference qc-notion-doc-standard.sh"

# 4. Compose qc-reference-sheet.sh --require-manual-fill (the generator matches the standard).
if [ "$DOC_ONLY" -eq 0 ]; then
  QCREF="$SKILL_DIR/scripts/qc-reference-sheet.sh"
  if [ -f "$QCREF" ]; then
    if bash "$QCREF" --require-manual-fill >/dev/null 2>&1; then
      pass "composed qc-reference-sheet.sh --require-manual-fill PASSES (generated doc matches the standard order)"
    else
      fail "composed qc-reference-sheet.sh --require-manual-fill FAILED — the generated client doc violates the standard order/structure"
    fi
  else
    fail "qc-reference-sheet.sh not found to compose (scripts/qc-reference-sheet.sh)"
  fi
fi

# 5. SKILL.md / INSTRUCTIONS.md pointer (skip when running against a fixture --doc).
if [ -z "${DOC##*notion-client-doc-standard.md}" ]; then
  PTR=0
  for f in "$SKILL_DIR/SKILL.md" "$SKILL_DIR/INSTRUCTIONS.md"; do
    [ -f "$f" ] && grep -qF 'notion-client-doc-standard.md' "$f" && PTR=1
  done
  [ "$PTR" -eq 1 ] && pass "SKILL.md/INSTRUCTIONS.md point to the standard" \
                    || fail "SKILL.md or INSTRUCTIONS.md must point to references/notion-client-doc-standard.md"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — the Notion client-doc standard carries the ordered mandatory list (1-12) and the generator matches it."
  exit 0
else
  echo "RESULT: FAIL — a Notion-client-doc-standard mandatory item is missing or the generator does not match (see above)."
  exit 1
fi
