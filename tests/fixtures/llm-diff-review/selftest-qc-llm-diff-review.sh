#!/usr/bin/env bash
# selftest-qc-llm-diff-review.sh — NON-VACUITY PROOF for the R6 LLM diff reviewer.
#
# Proves the reviewer actually bites, actually leaves the EXEMPT list alone, and
# actually FAILS CLOSED:
#
#   1.  EXEMPT      — CF Access UUID + AUD tag + Telegram chat ID + GHL location
#                     ID + a book-derived persona name  ............... expect PASS
#   2.  CLIENT NAME — a real-human customer/roster name  .............. expect BLOCK
#   3.  SECRET      — `pit-` GHL token + Telegram bot token + API key .. expect BLOCK
#   4.  OPAQUE HOST — an opaque hostname  ....... expect PASS + flag_for_operator
#   5.  CLIENT HOST — hostname literally CONTAINING a client name  .... expect BLOCK
#   6a. FAIL-CLOSED — malformed reviewer JSON  ........................ expect BLOCK
#   6b. FAIL-CLOSED — no credential (transport unreachable)  .......... expect BLOCK
#   6c. FAIL-CLOSED — API error (bad credential -> HTTP 4xx)  ......... expect BLOCK
#
# Cases 1-5 make a real (cheap) GOOGLE GEMINI FLASH call. The gate uses the
# fleet's own Google provider — NEVER Anthropic. Cases 6a-6c are transport-
# independent (6a/6c never leave the box; 6b proves the no-key path).
#
# Reviewer credential (one Google key under three alias names):
#   GEMINI_API_KEY  →  GOOGLE_AI_STUDIO_API_KEY  →  GOOGLE_API_KEY
# None set -> FATAL (fails closed; never a vacuous pass).
#
# All fixture literals are OBVIOUSLY SYNTHETIC — no real client name and no real
# secret exists anywhere in this tree.
#
# Usage: bash tests/fixtures/llm-diff-review/selftest-qc-llm-diff-review.sh

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
REVIEWER="$REPO_ROOT/scripts/qc-llm-diff-review.py"

[ -f "$REVIEWER" ] || { echo "FATAL: reviewer not found at $REVIEWER"; exit 1; }

# ─── Credential presence (one Google key, three alias names) ─────────────────
if [ -z "${GEMINI_API_KEY:-}${GOOGLE_AI_STUDIO_API_KEY:-}${GOOGLE_API_KEY:-}" ]; then
  echo "FATAL: no Google API key (GEMINI_API_KEY / GOOGLE_AI_STUDIO_API_KEY / GOOGLE_API_KEY)."
  echo "       The gate FAILS CLOSED rather than reporting a vacuous pass."
  exit 1
fi
echo "reviewer provider: Google Gemini Flash (${QC_LLM_REVIEW_MODEL:-gemini-flash-latest})"
echo ""

FAILURES=0

# run_case <label> <expected-exit> <expected-verdict> <extra-grep|""> <args...>
run_case() {
  local label="$1" want_exit="$2" want_verdict="$3" want_grep="$4"; shift 4
  echo "═══════════════════════════════════════════════════════════════════"
  echo "CASE: $label"
  echo "      (expect exit=$want_exit verdict=$want_verdict)"
  echo "───────────────────────────────────────────────────────────────────"
  local out rc
  out="$(python3 "$REVIEWER" "$@" 2>&1)"; rc=$?
  echo "$out"
  echo "--- exit=$rc ---"
  local ok=1
  [ "$rc" = "$want_exit" ] || { echo "  ✗ EXIT MISMATCH (got $rc, want $want_exit)"; ok=0; }
  echo "$out" | grep -q "\"verdict\": \"$want_verdict\"" \
    || { echo "  ✗ VERDICT MISMATCH (want $want_verdict)"; ok=0; }
  if [ -n "$want_grep" ]; then
    echo "$out" | grep -q "$want_grep" \
      || { echo "  ✗ MISSING EXPECTED CONTENT: $want_grep"; ok=0; }
  fi
  if [ "$ok" = 1 ]; then echo "  ✓ CASE PASSED"; else echo "  ✗ CASE FAILED"; FAILURES=$((FAILURES+1)); fi
  echo ""
}

# ─── LIVE MODEL CASES (Google Gemini Flash) ──────────────────────────────────
run_case "1. EXEMPT — CF UUID + AUD tag + Telegram chat ID + GHL location ID + book persona" \
  0 PASS "" --diff-file "$HERE/exempt.diff"

# NOTE: greps target the FINDING's "category" field, never the "counts" keys —
# a grep for bare client_name would also match `"client_name": 0` and be vacuous.
run_case "2. CLIENT NAME — a real human customer / roster member" \
  1 BLOCK '"category": "client_name"' --diff-file "$HERE/client-name.diff"

run_case "3. SECRET — pit- GHL token + Telegram bot token + API key" \
  1 BLOCK '"category": "secret"' --diff-file "$HERE/secret.diff"

# "why" only ever appears INSIDE a flag_for_operator entry, so this proves the
# list is actually populated (grepping "flag_for_operator" would match the empty
# array key and pass vacuously).
run_case "4. OPAQUE HOSTNAME — allowed, surfaced under flag_for_operator" \
  0 PASS '"why"' --diff-file "$HERE/opaque-hostname.diff"

# A hostname carrying a client's name may be reported as client_name OR as
# one_client_build — both are correct BLOCKs. Assert a real finding exists
# ("confidence" appears only inside a finding object) rather than pinning the
# category, which would make the test brittle without making it stronger.
run_case "5. CLIENT-NAMED HOSTNAME — hostname contains a client name" \
  1 BLOCK '"confidence"' --diff-file "$HERE/client-hostname.diff"

# ─── FAIL-CLOSED CASES ───────────────────────────────────────────────────────
run_case "6a. FAIL-CLOSED — malformed reviewer JSON" \
  1 BLOCK "reviewer_error" --diff-file "$HERE/exempt.diff" --response-file "$HERE/malformed-response.txt"

echo "═══════════════════════════════════════════════════════════════════"
echo "CASE: 6b. FAIL-CLOSED — no credential (all key aliases unset)"
echo "      (expect exit=1 verdict=BLOCK)"
echo "───────────────────────────────────────────────────────────────────"
_out="$(env -u GEMINI_API_KEY -u GOOGLE_AI_STUDIO_API_KEY -u GOOGLE_API_KEY \
        python3 "$REVIEWER" --diff-file "$HERE/exempt.diff" 2>&1)"; _rc=$?
echo "$_out"; echo "--- exit=$_rc ---"
if [ "$_rc" = 1 ] && echo "$_out" | grep -q reviewer_error; then
  echo "  ✓ CASE PASSED (fails closed)"
else
  echo "  ✗ CASE FAILED (must BLOCK)"; FAILURES=$((FAILURES+1))
fi
echo ""

echo "═══════════════════════════════════════════════════════════════════"
echo "CASE: 6c. FAIL-CLOSED — API error (bad credential -> HTTP 4xx)"
echo "      (expect exit=1 verdict=BLOCK)"
echo "───────────────────────────────────────────────────────────────────"
_out="$(env -u GOOGLE_AI_STUDIO_API_KEY -u GOOGLE_API_KEY \
        GEMINI_API_KEY="AIzaINVALID-selftest-credential-0000000000000000" \
        python3 "$REVIEWER" --diff-file "$HERE/exempt.diff" 2>&1)"; _rc=$?
echo "$_out"; echo "--- exit=$_rc ---"
if [ "$_rc" = 1 ] && echo "$_out" | grep -q reviewer_error; then
  echo "  ✓ CASE PASSED (fails closed on API error)"
else
  echo "  ✗ CASE FAILED (must BLOCK)"; FAILURES=$((FAILURES+1))
fi
echo ""

echo "═══════════════════════════════════════════════════════════════════"
if [ "$FAILURES" -eq 0 ]; then
  echo "RESULT: ALL CASES PASSED — reviewer is non-vacuous, exempt-safe, and fails closed."
  exit 0
fi
echo "RESULT: $FAILURES CASE(S) FAILED"
exit 1
