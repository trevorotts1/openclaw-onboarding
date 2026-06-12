#!/usr/bin/env bash
# test-add-sop.sh — Test suite for add-sop.sh substance gate + SOP logic (§1.2 / §4.1)
#
# Tests:
#   1. Empty SOP file → blocked by substance gate
#   2. Too-short SOP (4 lines) → blocked
#   3. SOP with no structure → blocked
#   4. Valid SOP substance check → passes
#   5. add-sop.sh missing --file arg → FAIL LOUD
#   6. regenerate-sop-index.py on a valid dept dir → produces 00-INDEX.md

set -uo pipefail
P="[test-add-sop]"
PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADD_SOP_SH="$SCRIPT_DIR/add-sop.sh"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REGEN_PY="$REPO_ROOT/23-ai-workforce-blueprint/scripts/regenerate-sop-index.py"

if [[ ! -f "$ADD_SOP_SH" ]]; then
  echo "$P FATAL: add-sop.sh not found at $ADD_SOP_SH" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap "rm -rf $TMP_DIR" EXIT

# ─── Shared substance gate testing via inline bash logic ─────────────────────
# The substance gate in add-sop.sh checks:
#   1. File non-empty
#   2. At least 5 lines
#   3. Has structure markers (## or 1. or Step N or - )
# We test this logic directly.

test_substance_gate() {
  local file="$1"
  local expected="$2"  # "pass" or "fail"
  local desc="$3"

  local is_empty=0
  local line_count
  local has_structure=0

  [[ -z "$(cat "$file" | tr -d '[:space:]')" ]] && is_empty=1
  line_count=$(wc -l < "$file" | tr -d ' ')
  grep -qE '^(#{1,3} |[0-9]+\.|Step [0-9]|-  )' "$file" 2>/dev/null && has_structure=1 || true

  if [[ $is_empty -eq 1 ]]; then
    result="fail"
    reason="file is empty"
  elif [[ "$line_count" -lt 5 ]]; then
    result="fail"
    reason="only $line_count lines (need >=5)"
  elif [[ $has_structure -eq 0 ]]; then
    result="fail"
    reason="no structure markers (no ## or 1. or Step N)"
  else
    result="pass"
    reason="ok ($line_count lines, has structure)"
  fi

  if [[ "$result" == "$expected" ]]; then
    pass "$desc: substance_gate=$result ($reason)"
  else
    fail "$desc: expected substance_gate=$expected but got $result ($reason)"
  fi
}

# ─── Test 1: Empty SOP ───────────────────────────────────────────────────────
echo "$P Test 1: empty SOP file..."
touch "$TMP_DIR/empty.md"
test_substance_gate "$TMP_DIR/empty.md" "fail" "Empty SOP"

# ─── Test 2: Too-short SOP ───────────────────────────────────────────────────
echo "$P Test 2: too-short SOP..."
printf "# Title\nLine 2\nLine 3\nLine 4\n" > "$TMP_DIR/short.md"
test_substance_gate "$TMP_DIR/short.md" "fail" "Short SOP (4 lines)"

# ─── Test 3: No structure ────────────────────────────────────────────────────
echo "$P Test 3: SOP with no structure..."
cat > "$TMP_DIR/nostructure.md" << 'EOF'
This is some text without any headers.
It has more than five lines.
But it has no numbered steps.
And no section headers.
And no bullet points.
And no dash items.
EOF
test_substance_gate "$TMP_DIR/nostructure.md" "fail" "Unstructured SOP"

# ─── Test 4: Valid SOP ───────────────────────────────────────────────────────
echo "$P Test 4: valid SOP..."
cat > "$TMP_DIR/valid.md" << 'EOF'
# Edit a Raw Episode

## Purpose
Guide the Audio Editor through the episode editing workflow.

## Steps
1. Import the raw audio file into the DAW.
2. Remove dead air at start and end.
3. Normalize audio levels to -16 LUFS.
4. Export as MP3 at 192kbps.
5. Upload to the shared drive.
EOF
test_substance_gate "$TMP_DIR/valid.md" "pass" "Valid SOP"

# ─── Test 5: Missing --file arg FAIL LOUD ─────────────────────────────────────
echo "$P Test 5: add-sop.sh --file missing should FAIL LOUD..."
# The script checks --file before hitting OC_ROOT resolver
OUTPUT=$(bash "$ADD_SOP_SH" --dept testdept --title "No File SOP" 2>&1 || true)
if echo "$OUTPUT" | grep -q "FATAL.*--file"; then
  pass "Missing --file triggers FATAL"
else
  fail "Missing --file should trigger FATAL. Got: $OUTPUT"
fi

# ─── Test 6: regenerate-sop-index.py builds 00-INDEX.md ──────────────────────
echo "$P Test 6: regenerate-sop-index.py builds 00-INDEX.md..."
if [[ ! -f "$REGEN_PY" ]]; then
  fail "regenerate-sop-index.py not found at $REGEN_PY"
else
  # Build a fake dept layout
  FAKE_DEPT="$TMP_DIR/departments/podcast/SOP"
  mkdir -p "$FAKE_DEPT"
  cat > "$FAKE_DEPT/01-edit-raw-episode.md" << 'EOF'
<!-- sop-meta
title: Edit a Raw Episode
dept: podcast
keywords: edit,audio
-->
# Edit a Raw Episode

## Steps
1. Import audio.
2. Edit silence.
3. Export MP3.
EOF
  cat > "$FAKE_DEPT/02-upload-to-drive.md" << 'EOF'
# Upload to Google Drive

## Steps
1. Open drive.
2. Upload file.
3. Share link.
EOF

  REGEN_OUT=$(python3 "$REGEN_PY" --dept podcast --workspace-root "$TMP_DIR/departments" 2>&1)
  if [[ -f "$FAKE_DEPT/00-INDEX.md" ]]; then
    SOPS_IN_INDEX=$(grep -c '^| \`' "$FAKE_DEPT/00-INDEX.md" || echo 0)
    pass "regenerate-sop-index.py created 00-INDEX.md with $SOPS_IN_INDEX SOP rows"
  else
    fail "regenerate-sop-index.py did not create 00-INDEX.md. Output: $REGEN_OUT"
  fi
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "$P Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
