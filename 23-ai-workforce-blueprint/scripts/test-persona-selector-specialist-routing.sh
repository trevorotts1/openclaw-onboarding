#!/usr/bin/env bash
# test-persona-selector-specialist-routing.sh
#
# Regression guard for the DEPARTMENT-AGNOSTIC specialist-routing fix (v14.22.0).
# Proves that a clearly-named canonical specialist in the 54-persona set is selected
# REGARDLESS of which department invokes the task — the defect being that
#   • 'network marketing recruiting downline duplication' never selected the real
#     specialist brunson-network-marketing-secrets (it returned hormozi/allan-dib or
#     the wrong Brunson book), and
#   • 'sketchnote ...' only reached rohde-the-sketchnote-workbook under dept=design.
#
# Runs in the HEURISTIC path (no gemini index / no API key in CI) against the canonical
# 54-persona persona-categories.json seeded into a temp HOME, so it is hermetic and
# deterministic. No client data: all personas are public authors.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS="$REPO_ROOT/23-ai-workforce-blueprint/scripts"
CANON_CATS="$REPO_ROOT/22-book-to-persona-coaching-leadership-system/persona-categories.json"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT
mkdir -p "$TMP_HOME/.openclaw/workspace/data/coaching-personas"
cp "$CANON_CATS" "$TMP_HOME/.openclaw/workspace/data/coaching-personas/persona-categories.json"

# Force the heuristic path: heuristic scoring + remove any sibling gemini-search.py so
# the semantic subprocess cannot resolve, and an empty HOME has no index for the
# in-process embedder -> _semantic_candidate_retrieval returns None (CI reality).
run_select() {
  local task="$1" dept="$2"
  # Empty temp HOME has no gemini index, so the in-process embedder and the
  # gemini-search subprocess both yield no semantic signal -> heuristic path (CI reality).
  HOME="$TMP_HOME" OPENCLAW_PLATFORM=mac SCORING_MODE=heuristic \
    python3 "$SCRIPTS/persona-selector-v2.py" \
      --task "$task" --department "$dept" \
      --no-variety --skip-stickiness --format json 2>/dev/null \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('persona_id'))"
}

echo "=== test-persona-selector-specialist-routing.sh (heuristic, 54-persona pool) ==="
echo ""

echo "--- network-marketing -> brunson-network-marketing-secrets (across departments) ---"
NM_TASK="network marketing recruiting downline duplication"
for dept in marketing sales general-task operations hr ceo communications; do
  got="$(run_select "$NM_TASK" "$dept")"
  if [ "$got" = "brunson-network-marketing-secrets" ]; then
    pass "dept=$dept -> $got"
  else
    fail "dept=$dept -> $got (expected brunson-network-marketing-secrets)"
  fi
done
echo ""

echo "--- sketchnote -> rohde-the-sketchnote-workbook (across departments) ---"
SK_TASK="sketchnote to visually map this content into a clear visual summary"
for dept in design graphics communications general-task content ceo; do
  got="$(run_select "$SK_TASK" "$dept")"
  if [ "$got" = "rohde-the-sketchnote-workbook" ]; then
    pass "dept=$dept -> $got"
  else
    fail "dept=$dept -> $got (expected rohde-the-sketchnote-workbook)"
  fi
done
echo ""

echo "--- CONTROL: a generic task names no specialty tag -> specialist NOT force-selected ---"
# Neither specialist should be picked for an unrelated generic task in an unrelated dept.
got="$(run_select "write a quarterly budget forecast and pricing model" finance 2>/dev/null || true)"
if [ "$got" != "brunson-network-marketing-secrets" ] && [ "$got" != "rohde-the-sketchnote-workbook" ]; then
  pass "generic finance task -> $got (no specialist false-positive)"
else
  fail "generic finance task wrongly force-selected a specialist -> $got"
fi
echo ""

echo "========================================"
echo "RESULTS: $PASS passed, $FAIL failed"
echo "========================================"
[ "$FAIL" -eq 0 ]
