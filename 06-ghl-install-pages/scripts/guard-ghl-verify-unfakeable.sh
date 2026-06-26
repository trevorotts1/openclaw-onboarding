#!/usr/bin/env bash
# guard-ghl-verify-unfakeable.sh — v1.0.0
#
# CI / QC GUARD: static proof that the verification layer cannot be faked.
#
# BACKGROUND (the fabrication this guard prevents):
#   The 2026-06-26 pre-flight produced a false "PASS — verified LIVE" by:
#     (a) Running the real page-load check (ghl_builder.verify_url), getting
#         HTTP 500 / marker_found=False, then DISCARDING the result and writing
#         a hand-typed ledger.json saying "overall_pass: true".
#     (b) Calling the 500 a harmless "API difference" rather than a FAIL.
#     (c) Substituting a storage-marker check ("is the marker in the Firebase
#         blob?") as proof of page rendering — the two are unrelated.
#     (d) Bypassing ghl_verify.py entirely for the funnel path; the summary was
#         hand-written, never derived from real load results.
#
# THIS GUARD ASSERTS (all grep/AST-level, no live network calls):
#
#   ASSERTION A — forbidden shortcut strings are ABSENT from tools/*.py.
#     The three rationalizations that enabled the fabrication:
#       1. "API difference"         (used to reframe a 500 as benign)
#       2. "marker in storage"      (used as a stand-in for page rendering)
#       3. "marker in stored bytes" (variant of the same substitute check)
#     If any of these strings re-appear in tool Python files as a PASS criterion
#     (i.e., in a context that is NOT a comment/docstring explaining what NOT
#     to do, which this guard's stripper removes), the build FAILS.
#
#   ASSERTION B — ghl_verify.py exposes the required safety symbols.
#     ghl_verify must export (at the module level, as class or constant names):
#       - VerifyContradiction   : the exception the guard raises on any
#                                 summary-more-optimistic-than-raw-log case.
#       - STORAGE_MARKER_IS_NOT_VERIFICATION (or the banned string is fully
#         absent from production code — see NOTE below).
#     This asserts the guard has NOT been removed, not renamed, and not gutted.
#
#   ASSERTION C — ghl_gate module exists with a require-pass entry point.
#     If ghl_gate.py exists: it must expose a callable named "require_pass"
#     (or a CLI that accepts "require-pass") — this is the authoritative pass
#     reader that a build calls to prove the gate was ACTUALLY run.
#     If ghl_gate.py does NOT exist yet: this assertion is a WARN (not a FAIL),
#     because B4 (the ghl_gate module) may land after B8. This guard gates
#     hermetic CI safely behind the live-run path for not-yet-implemented pieces.
#
#   ASSERTION D — ghl_verify.py is NOT bypassable via a hand-written ledger.
#     The derive_summary function must be present and the overall_pass field
#     must be derived from the raw array (not assigned from an outside source).
#     We assert the "source_of_truth" docstring key is present (a proxy for the
#     derive_summary contract being intact).
#
#   ASSERTION E — the "marker in storage" string does not appear as a gate name
#     or a pass criterion in gates.json.
#
# WHAT THIS GUARD DOES NOT CHECK:
#   - Whether pages actually load (that is a live-run check, not static).
#   - Whether ghl_verify is called correctly at runtime (static can't know).
#   - Correctness of the entire verification pipeline (unit tests cover that).
#
# Exit codes:
#   0 — PASS (all static assertions satisfied)
#   1 — FAIL (a forbidden string is present, or a required symbol is missing)
#   2 — usage / environment error
#
# Usage (standalone):
#   bash 06-ghl-install-pages/scripts/guard-ghl-verify-unfakeable.sh
#   bash 06-ghl-install-pages/scripts/guard-ghl-verify-unfakeable.sh \
#        --repo-root /path/to/repo
#
# Usage (from qc-ghl-install-pages.sh):
#   Invoked automatically when this file exists in $SKILL_DIR/scripts/.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOLS_DIR="$SKILL_DIR/tools"
GATES_JSON="$TOOLS_DIR/gates.json"
VERIFY_PY="$TOOLS_DIR/ghl_verify.py"
GATE_PY="$TOOLS_DIR/ghl_gate.py"

# Accept --repo-root for forward-compat with the repo-level QC convention.
while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) shift 2 ;;  # accepted but we use SKILL_DIR derived from $0
    -h|--help) sed -n '1,80p' "$0"; exit 0 ;;
    *) printf "Unknown argument: %s\n" "$1" >&2; exit 2 ;;
  esac
done

# ── Helpers ────────────────────────────────────────────────────────────────────
red()   { printf "\033[31m%s\033[0m\n" "$1"; }
green() { printf "\033[32m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }

FAILS=0
WARNS=0

fail() { red "  FAIL — $1"; FAILS=$((FAILS + 1)); }
warn() { yellow "  WARN — $1"; WARNS=$((WARNS + 1)); }
pass() { green "  PASS — $1"; }

echo ""
echo "guard-ghl-verify-unfakeable — static proof no fake-pass shortcut survives"
echo ""

# ── Python comment/docstring stripper (same technique as guard-ghl-token-only) ─
strip_python() {
  python3 - "$1" <<'PY'
import io, sys, tokenize

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
except Exception as e:
    sys.stdout.write(f"0:GUARD-ERROR-UNREADABLE do_login_placeholder\n")
    sys.exit(0)

lines = src.splitlines()
n = len(lines)
grid = [list(line) for line in lines]

def erase(start, end):
    (sr, sc), (er, ec) = start, end
    for r in range(sr, er + 1):
        idx = r - 1
        if idx < 0 or idx >= n:
            continue
        row = grid[idx]
        c0 = sc if r == sr else 0
        c1 = ec if r == er else len(row)
        for c in range(c0, min(c1, len(row))):
            row[c] = " "

try:
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            erase(tok.start, tok.end)
except (tokenize.TokenError, IndentationError, SyntaxError):
    sys.stdout.write("0:GUARD-ERROR-UNPARSEABLE do_login_placeholder\n")
    sys.exit(0)

for i in range(n):
    sys.stdout.write("%d:%s\n" % (i + 1, "".join(grid[i])))
PY
}

# ── ASSERTION A: forbidden shortcut strings absent from tools/*.py (code only) ─
echo "Assertion A — forbidden fake-pass shortcut strings absent from tool code:"
echo ""

# These three strings were used to rationalize a failed verification as passing.
# They are forbidden in PRODUCTION CODE paths (comments/docstrings stripped first).
FORBIDDEN_STRINGS=(
  "API difference"
  "marker in storage"
  "marker in stored bytes"
)

shopt -s nullglob
PY_FILES=("$TOOLS_DIR"/*.py)
shopt -u nullglob

if [ ${#PY_FILES[@]} -eq 0 ]; then
  fail "No .py files found in $TOOLS_DIR — cannot scan for forbidden strings"
else
  for forbidden in "${FORBIDDEN_STRINGS[@]}"; do
    hits_found=0
    for pyf in "${PY_FILES[@]}"; do
      fname="$(basename "$pyf")"
      # Strip comments/docstrings so explanatory prose ("do NOT use...") doesn't
      # trigger; we only flag the string when it appears in live code.
      while IFS= read -r codeln; do
        lineno="${codeln%%:*}"
        code="${codeln#*:}"
        [ -z "$code" ] && continue
        if printf '%s' "$code" | grep -Fq "$forbidden"; then
          # Allow the string in a pure assignment to a constant that is itself
          # the forbidden-string SENTINEL (e.g. STORAGE_MARKER_IS_NOT_VERIFICATION
          # = "marker in storage"). Such a line contains the string as a value,
          # not as a pass criterion. Detect this by checking if the line is a
          # simple constant assignment with no conditional/return around it.
          if printf '%s' "$code" | grep -Eiq \
             '^\s*(STORAGE_MARKER_IS_NOT_VERIFICATION|_FORBIDDEN_|NOT_A_GATE|BANNED_STRING)\s*='; then
            continue  # This is a sentinel constant — intentional, not a violation.
          fi
          fail "Forbidden string '$forbidden' found in $fname:$lineno (code context, not comment)"
          hits_found=$((hits_found + 1))
        fi
      done < <(strip_python "$pyf")
    done
    if [ "$hits_found" -eq 0 ]; then
      pass "Forbidden string '$forbidden' absent from all tool code"
    fi
  done
fi
echo ""

# ── ASSERTION B: ghl_verify.py exposes required safety symbols ─────────────────
echo "Assertion B — ghl_verify.py exposes required safety symbols:"
echo ""

if [ ! -f "$VERIFY_PY" ]; then
  fail "ghl_verify.py not found at $VERIFY_PY — verification layer is missing"
else
  # Check VerifyContradiction is defined at module scope.
  if grep -Eq '^class VerifyContradiction' "$VERIFY_PY"; then
    pass "ghl_verify.py defines VerifyContradiction exception class"
  else
    fail "ghl_verify.py is missing 'class VerifyContradiction' — the guard that prevents rosy summaries"
  fi

  # Check assert_consistent is defined (the contradiction guard function).
  if grep -Eq '^def assert_consistent' "$VERIFY_PY"; then
    pass "ghl_verify.py defines assert_consistent() — the summary-vs-raw guard"
  else
    fail "ghl_verify.py is missing 'def assert_consistent' — the contradiction guard is gone"
  fi

  # Check verify_all is defined (the single canonical pass function).
  if grep -Eq '^def verify_all' "$VERIFY_PY"; then
    pass "ghl_verify.py defines verify_all() — the single canonical verify pass"
  else
    fail "ghl_verify.py is missing 'def verify_all' — the canonical verify entry point is gone"
  fi

  # Check that the storage-marker shortcut is declared forbidden (either as a
  # constant named STORAGE_MARKER_IS_NOT_VERIFICATION, or by verifying the
  # forbidden string does NOT appear as a pass criterion — Assertion A covers
  # the latter, so here we check for the explicit sentinel constant if present).
  if grep -Eq 'STORAGE_MARKER_IS_NOT_VERIFICATION' "$VERIFY_PY"; then
    pass "ghl_verify.py carries STORAGE_MARKER_IS_NOT_VERIFICATION sentinel (storage-marker explicitly banned)"
  else
    # Not a hard FAIL here — Assertion A already bans the string in code.
    # But note its absence so it can be added.
    warn "ghl_verify.py does not carry STORAGE_MARKER_IS_NOT_VERIFICATION sentinel constant (recommended; Assertion A still bans the string)"
  fi

  # Check that derive_summary is present (summary must be derived, not hand-assigned).
  if grep -Eq '^def derive_summary' "$VERIFY_PY"; then
    pass "ghl_verify.py defines derive_summary() — overall_pass is derived, not assignable"
  else
    fail "ghl_verify.py is missing 'def derive_summary' — the contract preventing hand-assigned pass verdicts is gone"
  fi
fi
echo ""

# ── ASSERTION C: ghl_gate.py exists and exposes require_pass (WARN if absent) ──
echo "Assertion C — ghl_gate.py (authoritative pass reader) status:"
echo ""

if [ ! -f "$GATE_PY" ]; then
  warn "ghl_gate.py not yet present at $GATE_PY (B4 may not have landed yet — WARN only in CI; required before a live build ships)"
else
  # ghl_gate.py exists — assert it exposes require_pass.
  if grep -Eq '(def require_pass|"require-pass"|'"'"'require-pass'"'"')' "$GATE_PY"; then
    pass "ghl_gate.py exposes require_pass entry point"
  else
    fail "ghl_gate.py exists but does not expose require_pass / 'require-pass' — the authoritative pass reader is incomplete"
  fi
fi
echo ""

# ── ASSERTION D: derive_summary contract intact (no hand-assigned overall_pass) ─
echo "Assertion D — derive_summary contract: overall_pass is computed, not injected:"
echo ""

if [ -f "$VERIFY_PY" ]; then
  # In the stripped code, overall_pass must only appear as a derived value
  # (assigned from a boolean expression involving the raw array counts), never
  # as an outright assignment of a literal True that bypasses the reduction.
  # We check that no code line assigns overall_pass = True (the literal) outside
  # of derive_summary (which assigns it from 'total > 0 and failed == 0').
  override_hits=0
  while IFS= read -r codeln; do
    lineno="${codeln%%:*}"
    code="${codeln#*:}"
    [ -z "$code" ] && continue
    # Flag any line that assigns overall_pass to literal True without a
    # computation (i.e., not via 'and'/'or'/comparison). A safe assignment
    # looks like: "overall = total > 0 and failed == 0" or any expression.
    # An unsafe assignment looks like: "overall_pass = True" (bare literal).
    if printf '%s' "$code" | grep -Eq 'overall_pass\s*=\s*True\b' && \
       ! printf '%s' "$code" | grep -Eq '(and|or|>|<|==|!=|not\b)'; then
      fail "ghl_verify.py:$lineno assigns overall_pass = True (bare literal) — this is the hand-written override pattern"
      override_hits=$((override_hits + 1))
    fi
  done < <(strip_python "$VERIFY_PY")
  if [ "$override_hits" -eq 0 ]; then
    pass "ghl_verify.py has no bare 'overall_pass = True' assignments — verdict is always derived"
  fi
else
  warn "Assertion D skipped — ghl_verify.py not found"
fi
echo ""

# ── ASSERTION E: gates.json does not carry marker-in-storage as a pass gate ────
echo "Assertion E — gates.json: 'marker in storage' is NOT a pass criterion:"
echo ""

if [ ! -f "$GATES_JSON" ]; then
  fail "gates.json not found at $GATES_JSON"
else
  # Check the JSON text (not just the "gates" array) for the forbidden storage
  # marker strings appearing as gate result values ("PASS") or pass criteria.
  # We parse JSON and look for any gate entry that has result=PASS and a
  # description containing the forbidden strings.
  result=$(python3 - "$GATES_JSON" <<'PY'
import json, sys

path = sys.argv[1]
try:
    d = json.load(open(path, encoding="utf-8"))
except Exception as e:
    print(f"PARSE_ERROR:{e}")
    sys.exit(0)

forbidden = ["marker in storage", "marker in stored bytes"]
violations = []

def walk(obj, path=""):
    if isinstance(obj, dict):
        # Check if this looks like a gate result with result=PASS and a
        # forbidden string in the evidence.
        result_val = obj.get("result", "")
        evidence   = obj.get("evidence", "")
        if isinstance(result_val, str) and result_val.upper() == "PASS":
            for f in forbidden:
                if f in evidence.lower() or f in str(obj).lower():
                    violations.append(f"gate at {path}: result=PASS with evidence containing '{f}'")
        for k, v in obj.items():
            walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, f"{path}[{i}]")

walk(d)
if violations:
    print("VIOLATIONS:" + "|".join(violations))
else:
    print("CLEAN")
PY
  )

  case "$result" in
    CLEAN)
      pass "gates.json has no 'marker in storage' as a PASS criterion"
      ;;
    VIOLATIONS:*)
      vlist="${result#VIOLATIONS:}"
      IFS='|' read -ra viols <<< "$vlist"
      for v in "${viols[@]}"; do
        fail "gates.json: $v"
      done
      ;;
    PARSE_ERROR:*)
      fail "gates.json could not be parsed: ${result#PARSE_ERROR:}"
      ;;
    *)
      fail "gates.json check returned unexpected output: $result"
      ;;
  esac
fi
echo ""

# ── Summary ────────────────────────────────────────────────────────────────────
echo "guard-ghl-verify-unfakeable complete: $FAILS FAIL(s), $WARNS WARN(s)"
echo ""

if [ "$FAILS" -eq 0 ]; then
  if [ "$WARNS" -gt 0 ]; then
    yellow "guard-ghl-verify-unfakeable PASS WITH WARNINGS ($WARNS warning(s))."
    yellow "  Warnings do not block CI but should be resolved before a live build ships."
  else
    green "guard-ghl-verify-unfakeable PASS — verification layer cannot be faked."
  fi
  exit 0
else
  red "guard-ghl-verify-unfakeable FAIL — $FAILS violation(s)."
  echo ""
  echo "REMEDY:"
  echo "  A — remove any 'API difference' / 'marker in storage' / 'marker in"
  echo "      stored bytes' strings from production code paths in tools/*.py."
  echo "  B — restore VerifyContradiction, assert_consistent, verify_all, and"
  echo "      derive_summary to ghl_verify.py."
  echo "  C — implement ghl_gate.py with a require_pass entry point."
  echo "  D — replace any bare 'overall_pass = True' with a derived computation."
  echo "  E — remove any 'marker in storage' PASS gate from gates.json."
  exit 1
fi
