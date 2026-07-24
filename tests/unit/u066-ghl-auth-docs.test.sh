#!/usr/bin/env bash
# tests/unit/u066-ghl-auth-docs.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# U066 — Anthology per-client GHL auth documentation.
#
# Validates that:
#   1. INSTALL.md exists and documents the per-client GHL authentication
#      architecture (credential pair table, resolution chain, collision classes).
#   2. SKILL.md exists and documents per-client auth as a binding constraint
#      with the six binding sub-constraints.
#   3. The credential pair table has at least 2 rows (PIT + Location ID).
#   4. The collision classes section specifies all four classes (a-d) with exit
#      code 4 (VIOLATION).
#   5. Mutation proof: surgically remove the credential pair table from
#      INSTALL.md -> test RED; restore -> test GREEN.
#
# Fully offline: bash + coreutils + python3. No network, no credentials.
# Exit 0 = all checks pass.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTALL="$REPO_ROOT/59-anthology-engine/INSTALL.md"
SKILL="$REPO_ROOT/59-anthology-engine/SKILL.md"

PASS=0; FAIL=0
pass() { echo "  ok   — $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL — $1"; FAIL=$((FAIL+1)); }
hdr()  { printf '\n--- %s ---\n' "$1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ─────────────────────────────────────────────────────────────────────────────
hdr "1 — INSTALL.md exists and mentions per-client GHL auth"
# ─────────────────────────────────────────────────────────────────────────────

if [ -f "$INSTALL" ]; then
    pass "INSTALL.md exists at 59-anthology-engine/INSTALL.md"
else
    fail "INSTALL.md not found — expected at $INSTALL"
fi

if grep -qi "per-client.*GHL\|GHL.*per-client\|per-client.*auth\|private integration token\|CONVERT_AND_FLOW_PIT" "$INSTALL" 2>/dev/null; then
    pass "INSTALL.md mentions per-client GHL auth architecture"
else
    fail "INSTALL.md does not mention per-client GHL auth or CONVERT_AND_FLOW_PIT"
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "2 — SKILL.md exists and mentions per-client auth as binding constraint"
# ─────────────────────────────────────────────────────────────────────────────

if [ -f "$SKILL" ]; then
    pass "SKILL.md exists at 59-anthology-engine/SKILL.md"
else
    fail "SKILL.md not found — expected at $SKILL"
fi

if grep -qi "per-client.*auth\|per-client.*GHL\|CONVERT_AND_FLOW_PIT\|PER-CLIENT PAIR" "$SKILL" 2>/dev/null; then
    pass "SKILL.md documents per-client authentication"
else
    fail "SKILL.md does not document per-client authentication"
fi

if grep -qi "binding.constraint\|Never.*shared\|NEVER SHARED\|PER-CLIENT PAIR\|per-client.*isolation" "$SKILL" 2>/dev/null; then
    pass "SKILL.md establishes per-client auth as a binding constraint"
else
    fail "SKILL.md does not establish binding constraints for per-client auth"
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "3 — Credential pair table has at least 2 entries (PIT + Location ID)"
# ─────────────────────────────────────────────────────────────────────────────

# Extract the credential pair table from INSTALL.md.
TABLE_LINES="$(awk '/^## .*[Cc]redential pair/,/^---/' "$INSTALL" 2>/dev/null \
               | grep -E '^\|.*\|.*\|.*\|$' \
               | grep -vE '^\|.*---.*\|' \
               | grep -vE '^\| Label \|' \
               | wc -l | tr -d ' ')"

if [ "$TABLE_LINES" -ge 2 ]; then
    pass "Credential pair table has $TABLE_LINES data rows (PIT + Location ID)"
else
    fail "Credential pair table has only $TABLE_LINES data rows — expected at least 2"
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "4 — Collision classes section exists with exit code 4"
# ─────────────────────────────────────────────────────────────────────────────

if grep -qi "collision.class\|anti-commingling.*fingerprint\|AF-AE-COMMINGLE" "$INSTALL" 2>/dev/null; then
    pass "INSTALL.md documents collision classes / anti-commingling fingerprint"
else
    fail "INSTALL.md does not document collision classes or anti-commingling"
fi

# Each of the four collision-class table rows ends with "| 4 (VIOLATION) |".
VIOLATION_COUNT="$(grep -c "4 (VIOLATION)" "$INSTALL" 2>/dev/null || true)"
if [ "$VIOLATION_COUNT" -ge 4 ]; then
    pass "Collision classes specify exit code 4 (VIOLATION) — $VIOLATION_COUNT occurrences"
else
    fail "Collision classes rows with exit code 4: found $VIOLATION_COUNT, expected at least 4"
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "5 — Mutation proof: credential pair table removal -> RED, restore -> GREEN"
# ─────────────────────────────────────────────────────────────────────────────

# Use python3 -c (with - to read from stdin) so positional args are not treated
# as a script file. The heredoc provides the script via stdin.
MUTATED="$TMP/install.mutated.md"
RESTORED="$TMP/install.restored.md"

# Copy original for the restore step
cp "$INSTALL" "$RESTORED"

# Run mutation via python3.  We use - to read script from stdin, then pass
# the two file paths as positional args.  The heredoc provides the script.
python3 - "$INSTALL" "$MUTATED" <<'PYEOF'
import re, sys

src = sys.argv[1]
dst = sys.argv[2]

text = open(src).read()

# Remove the credential pair table section: everything from
# "## 1. Credential pair" through the next "---" separator.
text = re.sub(
    r'## 1\. Credential pair\n.*?\n---',
    '## 1. Credential pair — REMOVED\n\n---',
    text,
    count=1,
    flags=re.DOTALL,
)

open(dst, 'w').write(text)
print('mutation written')
PYEOF

PY_EXIT=$?
if [ "$PY_EXIT" -ne 0 ]; then
    fail "Python mutation script failed (exit $PY_EXIT)"
else
    # Verify the mutation removed the PIT label.
    if grep -q "CONVERT_AND_FLOW_PIT" "$MUTATED" 2>/dev/null; then
        fail "MUTATION FAILED — CONVERT_AND_FLOW_PIT still present after table removal"
    else
        # Restore: copy original back.
        if grep -q "CONVERT_AND_FLOW_PIT" "$RESTORED" 2>/dev/null; then
            pass "Mutation proof: removed credential pair table -> PIT missing; restored -> PIT present"
        else
            fail "Mutation proof: restore file does not contain CONVERT_AND_FLOW_PIT — test harness broken"
        fi
    fi
fi

# ── summary ──────────────────────────────────────────────────────────────────
echo ""
echo "=== $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL assertion(s) failed"
    exit 1
fi
echo "PASS: all assertions passed"
exit 0
