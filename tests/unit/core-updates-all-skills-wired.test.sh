#!/usr/bin/env bash
# tests/unit/core-updates-all-skills-wired.test.sh
#
# CI guard: verifies the format-robust CORE_UPDATES merger introduced in v12.3.11.
#
# Assertion groups:
#   (A) ALL-SKILLS-SENTINEL  — wire_core_updates run against all 41 non-archived
#       */CORE_UPDATES.md folders; every folder must produce its sentinel in the
#       fixture AGENTS.md. EXPECT 41/41.
#
#   (B) PER-FORMAT UNIT      — synthetic CORE_UPDATES with one section per known
#       format; each must merge content into the correct fixture file. Covers:
#       (b1) em-dash   ## AGENTS.md — UPDATE REQUIRED
#       (b2) bracket h2  ## [ADD TO TOOLS.md]
#       (b3) bracket h3  ### [ADD TO MEMORY.md]
#       (b4) bold-bracket  **[ADD TO AGENTS.md]**
#       (b5) plain h3 under Suggested snippets  ### MEMORY.md
#       (b6) verb-first  ## Add to AGENTS.md
#       (b7) paren-suffix  ## TOOLS.md (append)
#       (b8) skip  ## SOUL.md — NO UPDATE NEEDED  (must NOT appear in SOUL fixture)
#
#   (C) IDEMPOTENCY          — running the merger twice produces exactly one sentinel
#       and one BEGIN/END block per target (byte-count stable on 2nd run).
#
#   (D) NO-COMINGLING        — pre-existing content above the appended region is
#       byte-identical after merge.
#
#   (E) STRICT-MODE-GUARD    — feeding a CORE_UPDATES whose only core-file reference
#       is an invented @@AGENTS.md@@ form with CORE_UPDATES_STRICT=1 exits non-zero
#       and prints UNRECOGNIZED HEADER.
#
#   (F) REPO-WIDE-UNRECOGNIZED — CORE_UPDATES_STRICT=1 over all 41 real skill folders
#       reports 0 unrecognized headers (so every shipping skill is covered and a new
#       15th-format file would fail CI immediately).
#
# Exit 0 = all checks pass. Exit 1 = one or more checks failed (CI FAIL).
#
# v12.3.11 / fix/v12.3.11-core-updates-parser

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

# ---------------------------------------------------------------------------
# Extract the python3 merger from update-skills.sh between PYEOF delimiters.
# The merger lives inside wire_core_updates(). We extract the python block
# bounded by <<'PYEOF' ... PYEOF (the last PYEOF occurrence after the function
# definition comment "format-robust").
# ---------------------------------------------------------------------------
extract_py_merger() {
    local script="$REPO_ROOT/update-skills.sh"
    # Find the line number of the wire_core_updates PYEOF start (after v12.3.11 comment)
    python3 - "$script" << 'PYSCRAPER'
import sys, re
content = open(sys.argv[1]).read()
# Find the wire_core_updates function start (v12.3.11 version)
fn_match = re.search(r'# ---- Helper: idempotent CORE_UPDATES\.md merger \(v12\.3\.11', content)
if not fn_match:
    print("ERROR: wire_core_updates v12.3.11 marker not found", file=sys.stderr)
    sys.exit(1)
# Find <<'PYEOF' after the function start
pyeof_start = content.find("<<'PYEOF'\n", fn_match.start())
if pyeof_start == -1:
    print("ERROR: <<'PYEOF' not found after merger function start", file=sys.stderr)
    sys.exit(1)
# Extract from after <<'PYEOF'\n to the terminating PYEOF
py_start = pyeof_start + len("<<'PYEOF'\n")
py_end = content.find('\nPYEOF\n', py_start)
if py_end == -1:
    print("ERROR: closing PYEOF not found", file=sys.stderr)
    sys.exit(1)
print(content[py_start:py_end])
PYSCRAPER
}

PY_MERGER_FILE="$TMPDIR_TEST/merger.py"
if ! extract_py_merger > "$PY_MERGER_FILE" 2>&1; then
    echo "FATAL: could not extract python merger from update-skills.sh"
    cat "$PY_MERGER_FILE"
    exit 1
fi

# Verify the merger actually looks like Python
if ! head -1 "$PY_MERGER_FILE" | grep -q "^import"; then
    echo "FATAL: extracted merger does not start with 'import' — extraction failed"
    head -3 "$PY_MERGER_FILE"
    exit 1
fi

# ---------------------------------------------------------------------------
# Helper: run merger against a specific CORE_UPDATES.md and fixture dir
# Usage: run_merger <skill_folder> <cu_file> <fixture_dir> [strict]
# ---------------------------------------------------------------------------
run_merger() {
    local skill_folder="$1"
    local cu_file="$2"
    local fixture_dir="$3"
    local strict="${4:-0}"

    touch \
        "$fixture_dir/AGENTS.md" \
        "$fixture_dir/TOOLS.md" \
        "$fixture_dir/MEMORY.md" \
        "$fixture_dir/SOUL.md" \
        "$fixture_dir/IDENTITY.md" \
        "$fixture_dir/USER.md" 2>/dev/null || true

    local sentinel="<!-- skill:${skill_folder}:core-update-applied -->"
    CORE_UPDATES_STRICT="$strict" python3 "$PY_MERGER_FILE" \
        "$cu_file" \
        "$fixture_dir/AGENTS.md" \
        "$fixture_dir/TOOLS.md" \
        "$fixture_dir/MEMORY.md" \
        "$fixture_dir/SOUL.md" \
        "$fixture_dir/IDENTITY.md" \
        "$fixture_dir/USER.md" \
        "$sentinel" \
        "$skill_folder" \
        "$strict"
}

echo "=== core-updates-all-skills-wired.test.sh (v12.3.11) ==="
echo ""

# ── (A) ALL-SKILLS-SENTINEL ─────────────────────────────────────────────────
echo "--- (A) ALL-SKILLS-SENTINEL: 41 non-archived skills produce sentinels ---"

SKILL_DIRS=()
while IFS= read -r d; do
    # Skip the repo-root CORE_UPDATES.md (not a skill dir)
    [[ "$d" == "$REPO_ROOT/CORE_UPDATES.md" ]] && continue
    # Skip ARCHIVED skill directories (check the parent dir name, not the file)
    parent_dir="$(dirname "$d")"
    parent_name="$(basename "$parent_dir")"
    [[ "$parent_name" == *"-ARCHIVED" ]] && continue
    # Skip if parent is REPO_ROOT itself
    [[ "$parent_dir" == "$REPO_ROOT" ]] && continue
    SKILL_DIRS+=("$parent_dir")
done < <(find "$REPO_ROOT" -maxdepth 2 -name "CORE_UPDATES.md" | sort)

REAL_SKILLS=("${SKILL_DIRS[@]}")

TOTAL_SKILLS=${#REAL_SKILLS[@]}
echo "  Found $TOTAL_SKILLS non-archived skill directories with CORE_UPDATES.md"

SENTINEL_PASS=0
SENTINEL_FAIL=0
for sd in "${REAL_SKILLS[@]}"; do
    folder="$(basename "$sd")"
    cu_file="$sd/CORE_UPDATES.md"
    fixture_dir="$TMPDIR_TEST/fixture_${folder}"
    mkdir -p "$fixture_dir"

    run_merger "$folder" "$cu_file" "$fixture_dir" "0" > /dev/null 2>&1 || true

    sentinel="<!-- skill:${folder}:core-update-applied -->"
    if grep -qF "$sentinel" "$fixture_dir/AGENTS.md" 2>/dev/null; then
        SENTINEL_PASS=$((SENTINEL_PASS+1))
    else
        echo "  MISSING SENTINEL for: $folder"
        SENTINEL_FAIL=$((SENTINEL_FAIL+1))
    fi
done

if [ "$SENTINEL_FAIL" -eq 0 ]; then
    pass "ALL-SKILLS-SENTINEL: $SENTINEL_PASS/$TOTAL_SKILLS skills produced their sentinel"
else
    fail "ALL-SKILLS-SENTINEL: $SENTINEL_FAIL/$TOTAL_SKILLS skills missing sentinel (got $SENTINEL_PASS/$TOTAL_SKILLS)"
fi

echo ""

# ── (B) PER-FORMAT UNIT TESTS ────────────────────────────────────────────────
echo "--- (B) PER-FORMAT UNIT TESTS ---"

SYN_DIR="$TMPDIR_TEST/synthetic"
mkdir -p "$SYN_DIR"

# (b1) em-dash: ## AGENTS.md — UPDATE REQUIRED
B1_DIR="$TMPDIR_TEST/b1"; mkdir -p "$B1_DIR"
cat > "$B1_DIR/CORE_UPDATES.md" << 'SYNEOF'
# Synthetic skill b1

## AGENTS.md — UPDATE REQUIRED

em-dash-content-b1

## SOUL.md — NO UPDATE NEEDED

should-not-appear
SYNEOF
run_merger "syn-b1" "$B1_DIR/CORE_UPDATES.md" "$B1_DIR" "0" > /dev/null 2>&1 || true
if grep -q "em-dash-content-b1" "$B1_DIR/AGENTS.md" 2>/dev/null; then
    pass "b1: em-dash ## AGENTS.md — UPDATE REQUIRED merged to AGENTS.md"
else
    fail "b1: em-dash ## AGENTS.md — UPDATE REQUIRED NOT merged to AGENTS.md"
fi
if grep -q "should-not-appear" "$B1_DIR/SOUL.md" 2>/dev/null; then
    fail "b1: SOUL.md — NO UPDATE NEEDED content leaked into SOUL.md"
else
    pass "b1: SOUL.md — NO UPDATE NEEDED correctly skipped"
fi

# (b2) bracket h2: ## [ADD TO TOOLS.md]
B2_DIR="$TMPDIR_TEST/b2"; mkdir -p "$B2_DIR"
cat > "$B2_DIR/CORE_UPDATES.md" << 'SYNEOF'
# Synthetic skill b2

## [ADD TO TOOLS.md]

bracket-h2-tools-content-b2
SYNEOF
run_merger "syn-b2" "$B2_DIR/CORE_UPDATES.md" "$B2_DIR" "0" > /dev/null 2>&1 || true
if grep -q "bracket-h2-tools-content-b2" "$B2_DIR/TOOLS.md" 2>/dev/null; then
    pass "b2: bracket h2 ## [ADD TO TOOLS.md] merged to TOOLS.md"
else
    fail "b2: bracket h2 ## [ADD TO TOOLS.md] NOT merged to TOOLS.md"
fi

# (b3) bracket h3: ### [ADD TO MEMORY.md]
B3_DIR="$TMPDIR_TEST/b3"; mkdir -p "$B3_DIR"
cat > "$B3_DIR/CORE_UPDATES.md" << 'SYNEOF'
# Synthetic skill b3

## Suggested snippets

### [ADD TO MEMORY.md]

bracket-h3-memory-content-b3
SYNEOF
run_merger "syn-b3" "$B3_DIR/CORE_UPDATES.md" "$B3_DIR" "0" > /dev/null 2>&1 || true
if grep -q "bracket-h3-memory-content-b3" "$B3_DIR/MEMORY.md" 2>/dev/null; then
    pass "b3: bracket h3 ### [ADD TO MEMORY.md] merged to MEMORY.md"
else
    fail "b3: bracket h3 ### [ADD TO MEMORY.md] NOT merged to MEMORY.md"
fi

# (b4) bold-bracket: **[ADD TO AGENTS.md]**
B4_DIR="$TMPDIR_TEST/b4"; mkdir -p "$B4_DIR"
cat > "$B4_DIR/CORE_UPDATES.md" << 'SYNEOF'
# Synthetic skill b4

## AGENTS.md snippet

**[ADD TO AGENTS.md]**

bold-bracket-agents-content-b4
SYNEOF
run_merger "syn-b4" "$B4_DIR/CORE_UPDATES.md" "$B4_DIR" "0" > /dev/null 2>&1 || true
if grep -q "bold-bracket-agents-content-b4" "$B4_DIR/AGENTS.md" 2>/dev/null; then
    pass "b4: bold-bracket **[ADD TO AGENTS.md]** merged to AGENTS.md"
else
    fail "b4: bold-bracket **[ADD TO AGENTS.md]** NOT merged to AGENTS.md"
fi

# (b5) plain h3 under Suggested snippets: ### MEMORY.md
B5_DIR="$TMPDIR_TEST/b5"; mkdir -p "$B5_DIR"
cat > "$B5_DIR/CORE_UPDATES.md" << 'SYNEOF'
# Synthetic skill b5

## Suggested snippets

### MEMORY.md

plain-h3-memory-content-b5
SYNEOF
run_merger "syn-b5" "$B5_DIR/CORE_UPDATES.md" "$B5_DIR" "0" > /dev/null 2>&1 || true
if grep -q "plain-h3-memory-content-b5" "$B5_DIR/MEMORY.md" 2>/dev/null; then
    pass "b5: plain h3 ### MEMORY.md (under Suggested snippets) merged to MEMORY.md"
else
    fail "b5: plain h3 ### MEMORY.md NOT merged to MEMORY.md"
fi

# (b6) verb-first: ## Add to AGENTS.md
B6_DIR="$TMPDIR_TEST/b6"; mkdir -p "$B6_DIR"
cat > "$B6_DIR/CORE_UPDATES.md" << 'SYNEOF'
# Synthetic skill b6

## Add to AGENTS.md

verb-first-agents-content-b6
SYNEOF
run_merger "syn-b6" "$B6_DIR/CORE_UPDATES.md" "$B6_DIR" "0" > /dev/null 2>&1 || true
if grep -q "verb-first-agents-content-b6" "$B6_DIR/AGENTS.md" 2>/dev/null; then
    pass "b6: verb-first ## Add to AGENTS.md merged to AGENTS.md"
else
    fail "b6: verb-first ## Add to AGENTS.md NOT merged to AGENTS.md"
fi

# (b7) paren-suffix: ## TOOLS.md (append)
B7_DIR="$TMPDIR_TEST/b7"; mkdir -p "$B7_DIR"
cat > "$B7_DIR/CORE_UPDATES.md" << 'SYNEOF'
# Synthetic skill b7

## TOOLS.md (append)

paren-suffix-tools-content-b7
SYNEOF
run_merger "syn-b7" "$B7_DIR/CORE_UPDATES.md" "$B7_DIR" "0" > /dev/null 2>&1 || true
if grep -q "paren-suffix-tools-content-b7" "$B7_DIR/TOOLS.md" 2>/dev/null; then
    pass "b7: paren-suffix ## TOOLS.md (append) merged to TOOLS.md"
else
    fail "b7: paren-suffix ## TOOLS.md (append) NOT merged to TOOLS.md"
fi

echo ""

# ── (C) IDEMPOTENCY ──────────────────────────────────────────────────────────
echo "--- (C) IDEMPOTENCY: 2nd run produces no extra content ---"

C_DIR="$TMPDIR_TEST/idempotency"; mkdir -p "$C_DIR"
cat > "$C_DIR/CORE_UPDATES.md" << 'SYNEOF'
# Idempotency test skill

## AGENTS.md - UPDATE REQUIRED

idempotency-test-content-unique-xyz

## TOOLS.md - UPDATE REQUIRED

idempotency-tools-content-unique-xyz
SYNEOF

# First run
run_merger "syn-idempotency" "$C_DIR/CORE_UPDATES.md" "$C_DIR" "0" > /dev/null 2>&1 || true
AGENTS_BYTES_1=$(wc -c < "$C_DIR/AGENTS.md")
TOOLS_BYTES_1=$(wc -c < "$C_DIR/TOOLS.md")
SENTINEL_COUNT_1=$(grep -c "<!-- skill:syn-idempotency:core-update-applied -->" "$C_DIR/AGENTS.md" || true)
BEGIN_COUNT_1=$(grep -c "BEGIN skill:syn-idempotency:agents" "$C_DIR/AGENTS.md" || true)

# Second run
run_merger "syn-idempotency" "$C_DIR/CORE_UPDATES.md" "$C_DIR" "0" > /dev/null 2>&1 || true
AGENTS_BYTES_2=$(wc -c < "$C_DIR/AGENTS.md")
TOOLS_BYTES_2=$(wc -c < "$C_DIR/TOOLS.md")
SENTINEL_COUNT_2=$(grep -c "<!-- skill:syn-idempotency:core-update-applied -->" "$C_DIR/AGENTS.md" || true)
BEGIN_COUNT_2=$(grep -c "BEGIN skill:syn-idempotency:agents" "$C_DIR/AGENTS.md" || true)

if [ "$AGENTS_BYTES_1" -eq "$AGENTS_BYTES_2" ]; then
    pass "IDEMPOTENCY: AGENTS.md byte-count stable on 2nd run ($AGENTS_BYTES_1 bytes)"
else
    fail "IDEMPOTENCY: AGENTS.md grew from $AGENTS_BYTES_1 to $AGENTS_BYTES_2 bytes on 2nd run"
fi
if [ "$TOOLS_BYTES_1" -eq "$TOOLS_BYTES_2" ]; then
    pass "IDEMPOTENCY: TOOLS.md byte-count stable on 2nd run ($TOOLS_BYTES_1 bytes)"
else
    fail "IDEMPOTENCY: TOOLS.md grew from $TOOLS_BYTES_1 to $TOOLS_BYTES_2 bytes on 2nd run"
fi
if [ "$SENTINEL_COUNT_2" -eq 1 ]; then
    pass "IDEMPOTENCY: sentinel appears exactly once after 2nd run (count=$SENTINEL_COUNT_2)"
else
    fail "IDEMPOTENCY: sentinel count after 2nd run = $SENTINEL_COUNT_2 (expected 1)"
fi
if [ "$BEGIN_COUNT_2" -eq 1 ]; then
    pass "IDEMPOTENCY: BEGIN marker appears exactly once after 2nd run (count=$BEGIN_COUNT_2)"
else
    fail "IDEMPOTENCY: BEGIN marker count after 2nd run = $BEGIN_COUNT_2 (expected 1)"
fi

echo ""

# ── (D) NO-COMINGLING ────────────────────────────────────────────────────────
echo "--- (D) NO-COMINGLING: pre-existing content is byte-identical after merge ---"

D_DIR="$TMPDIR_TEST/nocomingling"; mkdir -p "$D_DIR"
# Write pre-existing content via python3 to guarantee exact byte layout
python3 -c "
content = '## Pre-existing Section\n\nThis content was in AGENTS.md before the skill was installed.\nIt must not be touched by the merger.\n'
open('$D_DIR/AGENTS.md', 'w').write(content)
open('$D_DIR/AGENTS_pre.md', 'w').write(content)
"
touch "$D_DIR/TOOLS.md" "$D_DIR/MEMORY.md" "$D_DIR/SOUL.md" "$D_DIR/IDENTITY.md" "$D_DIR/USER.md"

cat > "$D_DIR/CORE_UPDATES.md" << 'SYNEOF'
# No-comingling test skill

## AGENTS.md - UPDATE REQUIRED

skill-appended-content-nc
SYNEOF

run_merger "syn-nocomingling" "$D_DIR/CORE_UPDATES.md" "$D_DIR" "0" > /dev/null 2>&1 || true

# The pre-existing content must appear byte-for-byte at the START of AGENTS.md
# Use Python for reliable byte-level comparison
COMINGLING_RESULT=$(python3 -c "
pre = open('$D_DIR/AGENTS_pre.md', 'rb').read()
after = open('$D_DIR/AGENTS.md', 'rb').read()
if after[:len(pre)] == pre:
    print('MATCH')
else:
    print('MISMATCH: pre=%r head=%r' % (pre[:40], after[:40]))
")
if echo "$COMINGLING_RESULT" | grep -q "^MATCH"; then
    pass "NO-COMINGLING: pre-existing head of AGENTS.md is byte-identical after merge"
else
    fail "NO-COMINGLING: pre-existing head of AGENTS.md was modified"
    echo "    $COMINGLING_RESULT"
fi
# The skill content must also be present
if grep -q "skill-appended-content-nc" "$D_DIR/AGENTS.md"; then
    pass "NO-COMINGLING: appended skill content is present in AGENTS.md"
else
    fail "NO-COMINGLING: appended skill content is missing from AGENTS.md"
fi

echo ""

# ── (E) STRICT-MODE-GUARD ────────────────────────────────────────────────────
echo "--- (E) STRICT-MODE-GUARD: invented format causes non-zero exit under STRICT=1 ---"

E_DIR="$TMPDIR_TEST/strictguard"; mkdir -p "$E_DIR"
# Use a heading that LOOSE_RE (h2/h3 with target.md) catches but HEADER_PATTERN
# does not recognise — "## XTRA:AGENTS.md:weird" — contains AGENTS.md but has
# a non-standard prefix that breaks the normalising regex
python3 -c "
import os; os.makedirs('$E_DIR', exist_ok=True)
open('$E_DIR/CORE_UPDATES.md', 'w').write(
    '# Strict guard test\n\n'
    '## XTRA:AGENTS.md:weird\n\n'
    'invented-format-content\n'
)
"

STRICT_STDERR="$TMPDIR_TEST/strict_stderr.txt"
STRICT_EXIT=0
CORE_UPDATES_STRICT=1 python3 "$PY_MERGER_FILE" \
    "$E_DIR/CORE_UPDATES.md" \
    "$E_DIR/AGENTS.md" "$E_DIR/TOOLS.md" "$E_DIR/MEMORY.md" \
    "$E_DIR/SOUL.md" "$E_DIR/IDENTITY.md" "$E_DIR/USER.md" \
    "<!-- skill:syn-strict:core-update-applied -->" \
    "syn-strict" "1" \
    2>"$STRICT_STDERR" || STRICT_EXIT=$?

if [ "$STRICT_EXIT" -ne 0 ]; then
    pass "STRICT-MODE-GUARD: non-zero exit ($STRICT_EXIT) when CORE_UPDATES_STRICT=1"
else
    fail "STRICT-MODE-GUARD: exited 0 (expected non-zero) with invented format under STRICT=1"
fi
if grep -q "UNRECOGNIZED HEADER" "$STRICT_STDERR"; then
    pass "STRICT-MODE-GUARD: UNRECOGNIZED HEADER printed to stderr"
else
    fail "STRICT-MODE-GUARD: UNRECOGNIZED HEADER not printed to stderr"
    cat "$STRICT_STDERR"
fi

echo ""

# ── (F) REPO-WIDE UNRECOGNIZED HEADERS ──────────────────────────────────────
echo "--- (F) REPO-WIDE-UNRECOGNIZED: 0 unrecognized headers in all 41 skill CORE_UPDATES ---"

UNREC_COUNT=0
for sd in "${REAL_SKILLS[@]}"; do
    folder="$(basename "$sd")"
    cu_file="$sd/CORE_UPDATES.md"
    fixture_dir="$TMPDIR_TEST/strict_fixture_${folder}"
    mkdir -p "$fixture_dir"

    UNREC_STDERR="$TMPDIR_TEST/unrec_${folder}.txt"
    UNREC_EXIT=0
    CORE_UPDATES_STRICT=1 python3 "$PY_MERGER_FILE" \
        "$cu_file" \
        "$fixture_dir/AGENTS.md" "$fixture_dir/TOOLS.md" "$fixture_dir/MEMORY.md" \
        "$fixture_dir/SOUL.md" "$fixture_dir/IDENTITY.md" "$fixture_dir/USER.md" \
        "<!-- skill:${folder}:core-update-applied -->" \
        "$folder" "1" \
        2>"$UNREC_STDERR" || UNREC_EXIT=$?

    if grep -q "UNRECOGNIZED HEADER" "$UNREC_STDERR" 2>/dev/null; then
        echo "  UNRECOGNIZED in $folder:"
        grep "UNRECOGNIZED HEADER" "$UNREC_STDERR"
        UNREC_COUNT=$((UNREC_COUNT+1))
    fi
done

if [ "$UNREC_COUNT" -eq 0 ]; then
    pass "REPO-WIDE-UNRECOGNIZED: 0 unrecognized headers across all ${#REAL_SKILLS[@]} skill CORE_UPDATES.md files"
else
    fail "REPO-WIDE-UNRECOGNIZED: $UNREC_COUNT skill(s) have unrecognized headers (new 15th format?)"
fi

echo ""

# ── SUMMARY ──────────────────────────────────────────────────────────────────
echo "========================================"
echo "RESULTS: $PASS passed, $FAIL failed"
echo "========================================"
echo ""

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
