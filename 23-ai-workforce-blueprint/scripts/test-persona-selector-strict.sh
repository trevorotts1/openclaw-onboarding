#!/usr/bin/env bash
# test-persona-selector-strict.sh
#
# Contract guard for F3.2 — the `--strict` exit-code flag on persona-selector-v2.py.
#
# Requirement (analysis 2026-07-05, F3.2):
#   Keep exit 0 for back-compat (the Command Center spawns the selector and reads
#   JSON only) BUT add `--strict` → exit 3 on NO_PERSONAS_AVAILABLE / fallback-used,
#   for use by QC gates and heartbeat checks.
#
# Invariants proven here (hermetic — sandboxed empty HOME, no client data, all
# personas public authors; heuristic path so no gemini index / API key needed):
#   1. NON-strict + empty universe            -> exit 0   (back-compat unbroken)
#   2. --strict   + empty universe            -> exit 3   (NO_PERSONAS_AVAILABLE)
#   3. --strict   + mechanical task           -> exit 0   (no_persona_required is
#                                                          NOT degradation)
#   4. --strict   + healthy match             -> exit 0   (real task-matched persona)
#   5. non-strict never changes stdout JSON vs --strict (only the exit code differs)
#
# The stdout JSON contract is asserted UNCHANGED between the two modes so a
# --strict caller can still parse the same payload.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS="$REPO_ROOT/23-ai-workforce-blueprint/scripts"
CANON_CATS="$REPO_ROOT/22-book-to-persona-coaching-leadership-system/persona-categories.json"
SEL="$SCRIPTS/persona-selector-v2.py"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT
mkdir -p "$TMP_HOME/.openclaw"

# ── EMPTY universe: point PERSONA_CATEGORIES_PATH at a file that does not exist
#    and give a HOME with no coaching-personas dir, so list_available_personas
#    returns [] -> NO_PERSONAS_AVAILABLE. ──────────────────────────────────────
EMPTY_CATS="$TMP_HOME/.openclaw/does-not-exist-persona-categories.json"

run_empty() { # args: extra flags... ; prints exit code on its own line after JSON
  HOME="$TMP_HOME" OPENCLAW_PLATFORM=mac SCORING_MODE=heuristic \
  PERSONA_CATEGORIES_PATH="$EMPTY_CATS" \
    python3 "$SEL" --task "write a launch sales email" --department marketing \
      --no-record --no-variety --skip-stickiness --format json "$@"
}

echo "=== test-persona-selector-strict.sh (F3.2 --strict exit contract) ==="
echo ""

# 1. NON-strict + empty universe -> exit 0 (back-compat)
run_empty >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && pass "empty universe, non-strict -> exit 0 (back-compat)" \
                || fail "empty universe, non-strict -> exit $rc (expected 0)"

# 2. --strict + empty universe -> exit 3, and stdout still carries NO_PERSONAS_AVAILABLE
out_strict="$(run_empty --strict 2>/dev/null)"; rc=$?
warn="$(printf '%s' "$out_strict" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("warning"))' 2>/dev/null)"
[ "$rc" -eq 3 ] && pass "empty universe, --strict -> exit 3" \
                || fail "empty universe, --strict -> exit $rc (expected 3)"
[ "$warn" = "NO_PERSONAS_AVAILABLE" ] && pass "--strict stdout still emits NO_PERSONAS_AVAILABLE" \
                || fail "--strict stdout warning=$warn (expected NO_PERSONAS_AVAILABLE)"

# 3. stdout JSON identical between strict and non-strict (only exit code differs)
out_plain="$(run_empty 2>/dev/null)"
if [ "$out_plain" = "$out_strict" ]; then
  pass "stdout JSON identical strict vs non-strict (only exit code differs)"
else
  fail "stdout JSON DIFFERS between strict and non-strict (contract: payload unchanged)"
fi

# ── HEALTHY universe: seed the canonical public-author persona set. ────────────
mkdir -p "$TMP_HOME/.openclaw/workspace/data/coaching-personas"
SEEDED_CATS="$TMP_HOME/.openclaw/workspace/data/coaching-personas/persona-categories.json"
cp "$CANON_CATS" "$SEEDED_CATS"

run_seeded() { # args: task dept extra... ; JSON on stdout, exit preserved
  local task="$1" dept="$2"; shift 2
  HOME="$TMP_HOME" OPENCLAW_PLATFORM=mac SCORING_MODE=heuristic \
  PERSONA_CATEGORIES_PATH="$SEEDED_CATS" \
    python3 "$SEL" --task "$task" --department "$dept" \
      --no-record --no-variety --skip-stickiness --format json "$@"
}

# 4. --strict + mechanical task -> exit 0 (no_persona_required is not degradation)
run_seeded "restart the server" operations --strict >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && pass "--strict + mechanical task -> exit 0 (no_persona_required)" \
                || fail "--strict + mechanical task -> exit $rc (expected 0)"

# 5. --strict + healthy match -> exit 0 (real matched persona is not degraded)
out_ok="$(run_seeded "write persuasive sales copy for a coaching offer" marketing --strict 2>/dev/null)"; rc=$?
pid="$(printf '%s' "$out_ok" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("persona_id"))' 2>/dev/null)"
if [ "$rc" -eq 0 ] && [ -n "$pid" ] && [ "$pid" != "None" ]; then
  pass "--strict + healthy match -> exit 0 (matched $pid)"
else
  fail "--strict + healthy match -> exit $rc persona_id=$pid (expected exit 0 + a persona)"
fi

echo ""
echo "========================================"
echo "RESULTS: $PASS passed, $FAIL failed"
echo "========================================"
[ "$FAIL" -eq 0 ]
