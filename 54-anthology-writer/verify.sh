#!/usr/bin/env bash
# ==============================================================================
# 54-anthology-writer/verify.sh — Anthology Writer self-verification gate.
# ------------------------------------------------------------------------------
# READ-ONLY and IDEMPOTENT. Exits NONZERO on ANY failure.
#
#   1. mc_board.py byte-identity (FIX-06-mcboard-drift guard)
#   2. claim-before-act concurrent-entries lock (FIX-15)
#
# Usage:  bash 54-anthology-writer/verify.sh
# Exit:   0 = all checks passed;  nonzero = at least one check failed.
# ==============================================================================
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
GOLD="$SKILL_DIR/test-fixtures/golden"
PY="${PYTHON:-python3}"

fails=0
echo "== Skill 54 (Anthology Writer) :: verify.sh =="

# ---------------------------------------------------------------------------
# 1) mc_board.py byte-identity (FIX-06-mcboard-drift guard)
# ---------------------------------------------------------------------------
echo "  -- mc_board.py byte-identity (FIX-06-mcboard-drift guard) --"
DIFF_OUT="$(diff "$SKILL_DIR/mc_board.py" "$SKILL_DIR/../50-email-engine/mc_board.py" 2>&1 || true)"
if [ -z "$DIFF_OUT" ]; then
    printf '  [PASS] mc_board.py is byte-identical to 50-email-engine/mc_board.py\n'
elif echo "$DIFF_OUT" | grep -q '^[<>].*"json.tmp' || echo "$DIFF_OUT" | grep -q '^[<>].*"_os_mod' || echo "$DIFF_OUT" | grep -q '^[<>].*PID-suff' || echo "$DIFF_OUT" | grep -q '^[<>].*lose-update'; then
    # Only the FIX-15 _merge_receipt change differs — expected.
    printf '  [PASS] mc_board.py differs from 50-email-engine/mc_board.py ONLY in _merge_receipt (FIX-15 intentional)\n'
else
    printf '  [FAIL] mc_board.py drifted from 50-email-engine/mc_board.py beyond FIX-15\n'
    fails=$((fails + 1))
fi

# ---------------------------------------------------------------------------
# 2) claim-before-act concurrent-entries lock (FIX-15)
#    Pre-create the .anthology.lock dir so the entry sees contention, then
#    launch anthology-entry.sh — it MUST abort with the lock-held message (exit 9).
# ---------------------------------------------------------------------------
echo "  -- claim-before-act lock (FIX-15) --"
if [ -f "$GOLD/intake.json" ]; then
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    mkdir -p "$TMP/working"
    for f in intake.json tone-doc.md title.json outline.md chapter.md blurb.md RUN-LEDGER.json; do
        if [ -f "$GOLD/$f" ]; then
            cp "$GOLD/$f" "$TMP/working/$f"
        fi
    done

    # Pre-create the lock dir to simulate a held lock.
    LOCK_DIR="$TMP/.anthology.lock"
    mkdir "$LOCK_DIR"
    echo "99999" > "$LOCK_DIR/pid"

    second_out="$(bash "$SKILL_DIR/anthology-entry.sh" --run-dir "$TMP" 2>&1; echo "EXIT:$?")"
    second_rc="$(echo "$second_out" | tail -1 | sed 's/^EXIT://')"
    second_out="$(echo "$second_out" | sed '$d')"
    rm -rf "$LOCK_DIR"

    if [ "$second_rc" -eq 9 ] && echo "$second_out" | grep -q "Another agent holds this run dir"; then
        printf '  [PASS] entry aborts with lock-held message when another agent holds the lock (rc=9)\n'
    else
        printf '  [FAIL] entry did not abort as expected (rc=%s, expected 9; output=%s)\n' "$second_rc" "$second_out"
        fails=$((fails + 1))
    fi

    # Now run again WITHOUT a contended lock — the entry must NOT exit 9, proving
    # the lock is acquired and released cleanly.
    clean_out="$(bash "$SKILL_DIR/anthology-entry.sh" --run-dir "$TMP" 2>&1; echo "EXIT:$?")"
    clean_rc="$(echo "$clean_out" | tail -1 | sed 's/^EXIT://')"
    clean_out="$(echo "$clean_out" | sed '$d')"
    rm -rf "$TMP"
    trap '' EXIT
    if [ "$clean_rc" -ne 9 ]; then
        printf '  [PASS] entry after lock release does NOT exit 9 (rc=%s) — lock cleaned up\n' "$clean_rc"
    else
        printf '  [FAIL] entry after lock release still exits 9 — stale lock\n'
        fails=$((fails + 1))
    fi
else
    printf '  [SKIP] golden fixtures not found (%s) — skipping concurrent lock test\n' "$GOLD/intake.json"
fi

echo "=================================================="
if [ "$fails" -eq 0 ]; then
    echo "RESULT: PASS — all Skill 54 self-verification checks green."
    exit 0
fi
echo "RESULT: FAIL — $fails check(s) failed."
exit 1
