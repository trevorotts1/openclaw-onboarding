#!/usr/bin/env bash
# tests/unit/qc-assert-no-impersonation-directives.test.sh
#
# Behavioral tests for U124: Fleet rollout — anti-impersonation identity fix.
# Tests scripts/qc-assert-no-impersonation-directives.sh.
#
#   a) exit 1 with a violator file present
#   b) exit 0 with clean files
#   c) Detects "Act AS IF you ARE the persona" in non-excluded file
#   d) Detects "act AS that persona" equivalent phrasing
#   e) Detects "You ARE the persona" equivalent phrasing
#   f) Template files are excluded (no false positive)
#   g) Mutation proof: sentinel RED then GREEN

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/qc-assert-no-impersonation-directives.sh"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== qc-assert-no-impersonation-directives.test.sh ==="
echo ""
[ -f "$SCRIPT" ] || { echo "FATAL: $SCRIPT not found"; exit 1; }

_clean_workspace() {
  local root="$1"
  mkdir -p "$root/subdir"
  printf '# Clean File\n## Identity\nResolved agent identity. No impersonation here.\n' > "$root/IDENTITY.md"
  printf '# Clean Subdir File\n## Voice\nThis file uses primary identity language.\n' > "$root/subdir/IDENTITY.md"
  printf '# Clean Python\n"""Agent generator with no impersonation."""\nprint("hello")\n' > "$root/generator.py"
}

_violator_workspace() {
  local root="$1"
  _clean_workspace "$root"
  printf '# Violator\n## Override\nAct AS IF you ARE the persona for this task.\n' > "$root/violator.md"
}

_template_violator_workspace() {
  local root="$1"
  _clean_workspace "$root"
  mkdir -p "$root/23-ai-workforce-blueprint/templates/role-library/test-dept"
  printf '# Template File\nAct AS IF you ARE the persona for the duration.\n' > "$root/23-ai-workforce-blueprint/templates/role-library/test-dept/role.md"
}

echo "--- Test A: exit 1 when violator file is present ---------"
W_A="$(mktemp -d)"
_violator_workspace "$W_A"
if QC_IMPERSONATION_SCAN_ROOT="$W_A" bash "$SCRIPT" >/dev/null 2>&1; then fail "A: Expected exit 1, got exit 0"; else pass "A: Exited non-zero with violator"; fi

echo "--- Test B: exit 0 with clean files --------"
W_B="$(mktemp -d)"
_clean_workspace "$W_B"
if QC_IMPERSONATION_SCAN_ROOT="$W_B" bash "$SCRIPT" >/dev/null 2>&1; then pass "B: Exited 0 with clean files"; else fail "B: Expected exit 0, got non-zero"; fi

echo "--- Test C: detects primary sentinel in non-excluded file ---"
W_C="$(mktemp -d)"
_clean_workspace "$W_C"
printf '# Bad\nAct AS IF you ARE the persona for the task.\n' > "$W_C/bad.md"
OUTPUT_C=$(QC_IMPERSONATION_SCAN_ROOT="$W_C" bash "$SCRIPT" 2>&1) || true
if echo "$OUTPUT_C" | grep -q "INVARIANT VIOLATED"; then pass "C: Detected primary sentinel"; else fail "C: Did NOT detect primary sentinel. Output: $OUTPUT_C"; fi

echo "--- Test D: detects 'act AS that persona' ---"
W_D="$(mktemp -d)"
_clean_workspace "$W_D"
printf '# Bad\nWhen assigned, act AS that persona for decisions.\n' > "$W_D/bad.md"
OUTPUT_D=$(QC_IMPERSONATION_SCAN_ROOT="$W_D" bash "$SCRIPT" 2>&1) || true
if echo "$OUTPUT_D" | grep -q "INVARIANT VIOLATED"; then pass "D: Detected act AS that persona"; else fail "D: Did NOT detect act AS that persona. Output: $OUTPUT_D"; fi

echo "--- Test E: detects 'You ARE the persona' ---"
W_E="$(mktemp -d)"
_clean_workspace "$W_E"
printf '# Bad\n## P\nYou ARE the persona when working.\n' > "$W_E/bad.md"
OUTPUT_E=$(QC_IMPERSONATION_SCAN_ROOT="$W_E" bash "$SCRIPT" 2>&1) || true
if echo "$OUTPUT_E" | grep -q "INVARIANT VIOLATED"; then pass "E: Detected You ARE the persona"; else fail "E: Did NOT detect You ARE the persona. Output: $OUTPUT_E"; fi

echo "--- Test F: Template exclusion ---"
W_F="$(mktemp -d)"
_template_violator_workspace "$W_F"
if QC_IMPERSONATION_SCAN_ROOT="$W_F" bash "$SCRIPT" >/dev/null 2>&1; then pass "F: Templates excluded (exit 0)"; else fail "F: Template caused false positive"; fi

echo "--- Test G: Mutation proof ---"
W_G="$(mktemp -d)"
_clean_workspace "$W_G"
printf '# Bad File\nAct AS IF you ARE the persona for the task.\n' > "$W_G/bad.md"
cp "$SCRIPT" "$W_G/qc-copy.sh"
if QC_IMPERSONATION_SCAN_ROOT="$W_G" bash "$W_G/qc-copy.sh" >/dev/null 2>&1; then fail "G-green: Expected exit 1, got 0"; else pass "G-green: Intact sentinel detects (exit 1)"; fi
sed -i '' 's/Act AS IF you ARE the persona/BrokenXYZNoMatch/g' "$W_G/qc-copy.sh"
if QC_IMPERSONATION_SCAN_ROOT="$W_G" bash "$W_G/qc-copy.sh" >/dev/null 2>&1; then pass "G-red: Mutated sentinel fails (exit 0 = RED)"; else fail "G-red: Should have gone RED"; fi
cp "$SCRIPT" "$W_G/qc-reverted.sh"
sed -i '' 's/Act AS IF you ARE the persona/BrokenXYZNoMatch/g' "$W_G/qc-reverted.sh"
sed -i '' 's/BrokenXYZNoMatch/Act AS IF you ARE the persona/g' "$W_G/qc-reverted.sh"
if QC_IMPERSONATION_SCAN_ROOT="$W_G" bash "$W_G/qc-reverted.sh" >/dev/null 2>&1; then fail "G-revert: Reverted should detect (exit 1), got 0"; else pass "G-revert: Reverted detects again (exit 1 = GREEN)"; fi

echo ""
echo "=== RESULTS: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then exit 1; else exit 0; fi
