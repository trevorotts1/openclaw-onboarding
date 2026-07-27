#!/usr/bin/env bash
# type-f-census-guard.negative-fixture.sh
#
# Negative self-test for qc-assert-no-type-f-census.py.
# Proves the guard CAN fail: plants a file with a bare `-type f` census,
# runs the guard with --enforce, and asserts exit 1.
#
# Also plants SAFE forms (paired, adjacent-pair, safe-action, comment, heredoc)
# and asserts they are NOT flagged — a guard that flags its own fix is unusable.
#
# Added by U056.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GUARD="$REPO_ROOT/scripts/qc-assert-no-type-f-census.py"

# ── Create temp workspace ──────────────────────────────────────────────────
WS="$(mktemp -d)"
trap 'rm -rf "$WS"' EXIT

# Copy the guard and its allowlist
mkdir -p "$WS/scripts/tests"
cp "$GUARD" "$WS/scripts/qc-assert-no-type-f-census.py"
# Copy an empty allowlist so the fixture is self-contained
touch "$WS/scripts/qc-assert-no-type-f-census.allowlist"

# ── Plant violation files ─────────────────────────────────────────────────

# V1: bare -type f (should trigger)
mkdir -p "$WS/violations"
cat > "$WS/violations/bare.sh" << 'VIOL1'
#!/bin/bash
find . -type f -name '*.md'
VIOL1

# V2: -type f with -o that is NOT -type l (should trigger)
cat > "$WS/violations/not_typel.sh" << 'VIOL2'
#!/bin/bash
find . -type f -o -name x
VIOL2

# V3: -type f with -print0 (should trigger)
cat > "$WS/violations/print0.sh" << 'VIOL3'
#!/bin/bash
find "$dir" -type f -print0
VIOL3

# ── Plant SAFE forms (should NOT trigger) ─────────────────────────────────
mkdir -p "$WS/safe"

# Safe 1: paired on same line
cat > "$WS/safe/paired.sh" << 'SAFE1'
#!/bin/bash
find . \( -type f -o -type l \) -name '*.md'
SAFE1

# Safe 2: -type l only (should never match anyway)
cat > "$WS/safe/typel_only.sh" << 'SAFE2'
#!/bin/bash
find . -type l -name '*.md'
SAFE2

# Safe 3: -delete
cat > "$WS/safe/delete.sh" << 'SAFE3'
#!/bin/bash
find /tmp -maxdepth 1 -type f -name '*.bak' -delete
SAFE3

# Safe 4: comment
cat > "$WS/safe/comment.sh" << 'SAFE4'
#!/bin/bash
# find . -type f -name '*.md'
echo "not a find"
SAFE4

# Safe 5: adjacent-pair (two separate find lines: f then l)
cat > "$WS/safe/adjacent.sh" << 'SAFE5'
#!/bin/bash
COPIED=$(find "$dir" -type f -name "*.md" 2>/dev/null | wc -l)
SYMLINKED=$(find "$dir" -type l -name "*.md" 2>/dev/null | wc -l)
SAFE5

# Safe 6: heredoc
cat > "$WS/safe/heredoc.sh" << 'SAFE6'
#!/bin/bash
cat << 'EOF'
find /var/log -type f -name '*.log' -delete
EOF
echo "done"
SAFE6

# ── Run guard with --enforce ───────────────────────────────────────────────
cd "$WS"
FAIL_COUNT=0

# Test violations — guard must exit 1
echo "=== Negative self-test: expect exit 1 ==="
set +e
output="$(python3 "$WS/scripts/qc-assert-no-type-f-census.py" --enforce 2>&1)"
rc=$?
set -e

if [ "$rc" -ne 1 ]; then
    echo "FAIL: guard with --enforce exited $rc (expected 1) on planted violations"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# Check each violation is reported
for f in violations/bare.sh violations/not_typel.sh violations/print0.sh; do
    if ! echo "$output" | grep -qF "$f"; then
        echo "FAIL: guard did not report $f"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

# Verify safe forms are NOT reported
for f in safe/paired.sh safe/typel_only.sh safe/delete.sh safe/comment.sh safe/adjacent.sh safe/heredoc.sh; do
    if echo "$output" | grep -qF "$f"; then
        echo "FAIL: guard incorrectly flagged SAFE form $f"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "✓ Guard correctly detects violations and exempts safe forms"
    exit 0
else
    echo "✗ Negative self-test failed with $FAIL_COUNT failure(s)"
    exit 1
fi
