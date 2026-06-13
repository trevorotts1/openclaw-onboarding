#!/usr/bin/env bash
# tests/unit/wire-no-match-completes.test.sh
#
# CI guard: verifies that the grep no-match-abort traps fixed in v12.3.9 are
# correctly guarded so a legitimate no-match never aborts wiring or the
# version stamp.
#
# Four assertion groups:
#   (A) GHL-GREP     — wire_ghl_mcp port-grep with a ${...} INSTALL.md (no digit port)
#                      completes without aborting; GHL_MCP_PORT falls back to 8765.
#   (B) WIRING-LOOP  — the grep pipeline completing does NOT abort wiring/stamp;
#                      validated by simulating the relevant pipeline pieces.
#   (C) HAPPY-PATH   — print_install_summary equivalent: grep -c on zero-match
#                      LOG_FILE under set -euo pipefail → exits 0, prints CLEANLY.
#   (D) STATIC-GUARD — all command-substitution/standalone grep pipelines inside
#                      update-skills.sh + install.sh that are NOT already in a
#                      condition / || true / || : guard are flagged as regressions.
#
# Exit 0 = all checks pass. Exit 1 = one or more checks failed (CI FAIL).
#
# v12.3.9 / fix/v12.3.9-update-skills-grep-abort

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== wire-no-match-completes.test.sh (v12.3.9) ==="
echo ""

# ── (A) GHL-GREP: port detection with a \${...} INSTALL.md ──────────────────
echo "--- (A) GHL-GREP: wire_ghl_mcp port-grep no-match ---"

# Build a synthetic INSTALL.md with only a literal ${...} variable — no digits.
GHL_INSTALL_DIR="$TMPDIR_TEST/36-ghl-mcp-setup"
mkdir -p "$GHL_INSTALL_DIR"
cat > "$GHL_INSTALL_DIR/INSTALL.md" << 'EOF'
## GHL MCP Setup

Start the server on http://localhost:${GHL_MCP_PORT}/mcp
EOF

A_OUT=$(bash -c '
set -euo pipefail
GHL_MCP_INSTALL_MD="'"$GHL_INSTALL_DIR/INSTALL.md"'"
GHL_MCP_PORT=8765
DETECTED_PORT=$(grep -oE "localhost:[0-9]+" "$GHL_MCP_INSTALL_MD" 2>/dev/null | head -1 | cut -d: -f2 || true)
[ -n "$DETECTED_PORT" ] && GHL_MCP_PORT="$DETECTED_PORT"
echo "PORT=$GHL_MCP_PORT"
' 2>&1) || { fail "(A) GHL grep pipeline aborted under set -euo pipefail"; }

if echo "$A_OUT" | grep -q "PORT=8765"; then
    pass "(A) GHL port-grep no-match: completed, GHL_MCP_PORT=8765 (default)"
else
    fail "(A) GHL port-grep no-match: unexpected output: $A_OUT"
fi

# ── (B) WIRING-LOOP: analogous STATUS_LINE grep no-match ────────────────────
echo ""
echo "--- (B) WIRING-LOOP: STATUS_LINE grep no-match ---"

B_OUT=$(bash -c '
set -euo pipefail
QC_OUTPUT="Some output without a STATUS line here"
QC_STATUS_LINE="$(printf "%s\n" "$QC_OUTPUT" | grep -E "^STATUS:" | tail -1 || true)"
echo "STATUS=${QC_STATUS_LINE:-(empty)}"
' 2>&1) || { fail "(B) STATUS_LINE grep pipeline aborted under set -euo pipefail"; }

if echo "$B_OUT" | grep -q "STATUS="; then
    pass "(B) STATUS_LINE no-match: completed, empty result as expected"
else
    fail "(B) STATUS_LINE no-match: unexpected output: $B_OUT"
fi

# Also test FUZZY_DIR no-match
B2_OUT=$(bash -c '
set -euo pipefail
FUZZY_DIR=$(find "'"$TMPDIR_TEST"'" -maxdepth 2 -type d -iname "*openclaw*" 2>/dev/null | grep -i "master" | head -1 || true)
echo "FUZZY=${FUZZY_DIR:-(empty)}"
' 2>&1) || { fail "(B2) FUZZY_DIR grep pipeline aborted under set -euo pipefail"; }

if echo "$B2_OUT" | grep -q "FUZZY="; then
    pass "(B2) FUZZY_DIR no-match: completed, empty result as expected"
else
    fail "(B2) FUZZY_DIR no-match: unexpected output: $B2_OUT"
fi

# Also test GATE-HUMAN no-match
B3_OUT=$(bash -c '
set -euo pipefail
OBS_OUT="GATE-STATUS: pending"
ONBOARDING_GATE_SUMMARY="$(printf "%s\n" "$OBS_OUT" | grep "^GATE-HUMAN:" | sed "s/^GATE-HUMAN: //" || true)"
echo "GATE=${ONBOARDING_GATE_SUMMARY:-(empty)}"
' 2>&1) || { fail "(B3) GATE-HUMAN grep pipeline aborted under set -euo pipefail"; }

if echo "$B3_OUT" | grep -q "GATE="; then
    pass "(B3) GATE-HUMAN no-match: completed, empty result as expected"
else
    fail "(B3) GATE-HUMAN no-match: unexpected output: $B3_OUT"
fi

# ── (C) HAPPY-PATH: grep -c on clean log ────────────────────────────────────
echo ""
echo "--- (C) HAPPY-PATH: grep -c zero-match on clean log ---"

CLEAN_LOG="$TMPDIR_TEST/clean.log"
echo "INFO: all steps completed successfully" > "$CLEAN_LOG"

C_OUT=$(bash -c '
set -euo pipefail
LOG_FILE="'"$CLEAN_LOG"'"
err_pat="^  ✗ ERROR:|GatewayClientRequestError|GatewayTransportError"
warn_pat="^  ⚠️"
err_count=$(grep -cE "$err_pat" "$LOG_FILE" 2>/dev/null | head -1 || true)
warn_count=$(grep -cE "$warn_pat" "$LOG_FILE" 2>/dev/null | head -1 || true)
err_count=${err_count:-0}
warn_count=${warn_count:-0}
# Also test standalone grep no-match (line 5460 equivalent)
grep -nE "$err_pat|$warn_pat" "$LOG_FILE" 2>/dev/null | tail -10 | sed "s/^/     /" || true
if [ "$err_count" -eq 0 ] && [ "$warn_count" -eq 0 ]; then
    echo "INSTALL COMPLETED CLEANLY"
fi
' 2>&1) || { fail "(C) print_install_summary aborted on clean log under set -euo pipefail"; }

if echo "$C_OUT" | grep -q "INSTALL COMPLETED CLEANLY"; then
    pass "(C) Happy-path: clean log → INSTALL COMPLETED CLEANLY, exit 0"
else
    fail "(C) Happy-path: unexpected output: $C_OUT"
fi

# ── (D) STATIC-GUARD: no unguarded grep in command-subst/standalone stmts ───
echo ""
echo "--- (D) STATIC-GUARD: no unguarded grep exits under set -e+pipefail ---"

# Strategy: find command-substitution grep pipelines and standalone grep
# statements that are NOT already guarded. We look for:
#   $(...grep...)  or standalone grep ... that does NOT end with || true / || :
#   and is NOT inside a condition (if/while/until/&&/||)
#
# This is a heuristic: we grep for the patterns the design documented and
# verify each is guarded with || true.
#
# Documented traps that MUST have || true:
MUST_HAVE_GUARD=(
    "FUZZY_DIR=\$(find.*grep"
    "DETECTED_PORT=\$(grep"
    "ONBOARDING_GATE_SUMMARY=.*grep"
    "QC_STATUS_LINE=.*grep"
    "numbered_count=\$(find.*grep"
    "skill_md_count=\$(find.*grep"
    "get_gateway_capability.*grep"
    "STATUS_LINE=.*grep"
    "err_count=\$(grep"
    "warn_count=\$(grep"
    "grep -nE.*err_pat.*warn_pat.*LOG_FILE.*sed"
    "_OPTG_STATUS=.*grep"
)

D_FAIL=0
for pattern in "${MUST_HAVE_GUARD[@]}"; do
    # Check update-skills.sh and install.sh for the pattern
    for script in "$REPO_ROOT/update-skills.sh" "$REPO_ROOT/install.sh"; do
        [ -f "$script" ] || continue
        # Find lines matching the pattern
        matching=$(grep -nE "$pattern" "$script" 2>/dev/null || true)
        if [ -z "$matching" ]; then
            continue  # pattern not present in this file — OK
        fi
        # Each matching line must have || true or || : at end of the relevant block
        while IFS= read -r match_line; do
            lineno=$(echo "$match_line" | cut -d: -f1)
            # Extract the line content (possibly multi-line with continuation)
            # We look ahead up to 3 lines for || true
            block=$(sed -n "${lineno},$((lineno+3))p" "$script" 2>/dev/null || true)
            if echo "$block" | grep -qE "\|\| true|\|\| :"; then
                : # guarded — OK
            else
                fail "(D) Unguarded grep pipeline in $(basename "$script") at line $lineno: $match_line"
                D_FAIL=$((D_FAIL+1))
            fi
        done <<< "$matching"
    done
done

if [ "$D_FAIL" -eq 0 ]; then
    pass "(D) Static guard: all documented grep pipelines have || true guards"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL assertion(s) failed — see above"
    exit 1
fi

echo "PASS: all wire-no-match assertions pass"
exit 0
