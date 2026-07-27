#!/usr/bin/env bash
# U056 -- negative self-test for qc-assert-no-type-f-census.py
set -euo pipefail

fail() { echo "FAIL: $*"; exit 1; }
pass() { echo "  OK $*"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GUARD="$SCRIPT_DIR/../qc-assert-no-type-f-census.py"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
git init -q
git config user.email t@t.test
git config user.name t
mkdir -p scripts
cp "$GUARD" scripts/
cp "$SCRIPT_DIR/../qc-assert-no-type-f-census.allowlist" scripts/ 2>/dev/null || true

# Helper: write a file with the given content from a heredoc in this script.
# Uses cat <<'ENDOFFILE' so the delimiter is matched exactly.

# -- 1. Plant violations, enforce must exit 1 --
cat > BAD1.sh <<'ENDOFFILE'
find . -type f -name "*.md"
ENDOFFILE

cat > BAD2.sh <<'ENDOFFILE'
find "$dir" -type f -print0
ENDOFFILE

cat > BAD3.sh <<'ENDOFFILE'
find . -type f -o -name x
ENDOFFILE

git add -A

echo "=== Test 1: --enforce exits 1 on planted violations ==="
set +e; python3 scripts/qc-assert-no-type-f-census.py --enforce >/dev/null 2>&1; rc=$?; set -e
[ "$rc" -eq 1 ] || fail "Test 1: got $rc, want 1"
pass "Test 1: --enforce exits 1"

# -- 2. Safe forms only, enforce must exit 0 --
rm -f BAD1.sh BAD2.sh BAD3.sh
git add -A

cat > SAFE_SAME_LINE.sh <<'ENDOFFILE'
find . \( -type f -o -type l \) -name "*.md"
ENDOFFILE

cat > SAFE_PAIR.sh <<'ENDOFFILE'
COPIED=$(find . -maxdepth 2 -type f -name A.md | wc -l)
SYMLINKED=$(find . -maxdepth 2 -type l -name A.md | wc -l)
ENDOFFILE

cat > SAFE_DELETE.sh <<'ENDOFFILE'
find . -type f -delete
ENDOFFILE

cat > SAFE_ONLY_L.sh <<'ENDOFFILE'
find . -type l
ENDOFFILE

git add -A

echo "=== Test 2: --enforce exits 0 on safe forms only ==="
set +e; python3 scripts/qc-assert-no-type-f-census.py --enforce >/dev/null 2>&1; rc=$?; set -e
[ "$rc" -eq 0 ] || fail "Test 2: got $rc, want 0"
pass "Test 2: --enforce exits 0"

# -- 3. Lone -type f (no -type l neighbour) must be reported --
rm -f SAFE_PAIR.sh
git add -A

cat > LONE_F.sh <<'ENDOFFILE'
find x -type f -name AGENTS.md
ENDOFFILE

git add -A

echo "=== Test 3: lone -type f IS reported ==="
set +e; python3 scripts/qc-assert-no-type-f-census.py --enforce >/dev/null 2>&1; rc=$?; set -e
[ "$rc" -eq 1 ] || fail "Test 3: got $rc, want 1"
pass "Test 3: lone -type f reported"

# -- 4. Warn-mode exits 0 even with violations --
echo "=== Test 4: warn-mode exits 0 ==="
set +e; python3 scripts/qc-assert-no-type-f-census.py >/dev/null 2>&1; rc=$?; set -e
[ "$rc" -eq 0 ] || fail "Test 4: got $rc, want 0"
pass "Test 4: warn-mode exits 0"

echo ""
echo "PASS: negative self-test complete"
