#!/usr/bin/env bash
# guard-ghl-auth-fallback.sh — v1.0.0
#
# CI / QC GUARD for the GHL TIER-2 EMAIL-2FA AUTH-FALLBACK doctrine (Skill 06).
#
# COMPANION to guard-ghl-token-only.sh + guard-ghl-activation-resilience.sh.
# Together the three GHL auth guardrails are:
#   - guard-ghl-token-only.sh            → Tier-1 auth MODEL (refresh-token seed
#                                           ONLY; the two Tier-1 files stay clean).
#   - guard-ghl-activation-resilience.sh → Tier-1 ACTIVATION is resilient.
#   - guard-ghl-auth-fallback.sh (THIS)  → Tier-2 EMAIL-2FA FALLBACK is contained,
#                                           gated-before-login, bounded, self-heals
#                                           to token-only, leaks no secret, and is
#                                           client-store-only.
#
# THE DOCTRINE (Tier 2):
#   Tier 1 (token-only) stays PRIMARY. Tier 2 is a GATED, audited, one-time
#   bootstrap that logs in with email-2FA ONLY when there is no valid token AND
#   four gates pass (authorization, gmail-PROVEN-before-login, email-2FA, creds),
#   then SELF-HEALS a fresh refresh token to the client store so the next run is
#   Tier 1 again. ALL login/password/2FA code lives in EXACTLY ONE module
#   (ghl_auth_fallback.py) plus its thin browser helper (ghl_login_browser.py).
#
# WHAT THIS GUARD ENFORCES (fails the build / QC unless ALL hold):
#   1. LOGIN CONTAINMENT — banned active-login patterns appear in EXACTLY the two
#      allowlisted files and NOWHERE else under tools/ + scripts/. Tier-1 files
#      stay clean (re-asserted by guard-ghl-token-only.sh).
#   2. GATE-BEFORE-LOGIN ORDER — the four gate sentinel comments + the four gate
#      calls inside check_all_gates appear, and the LAST gate call precedes the
#      first login/password action (static order check on stripped code).
#   3. BOUNDED ATTEMPTS — MAX_LOGIN_ATTEMPTS <= 3, the loop references it, backoff
#      present, lockout/captcha hard-stop present.
#   4. SELF-HEAL — the success path writes REFRESH_TOKEN_KEY
#      (== GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN) to the secret store.
#   5. NO-SECRET-LEAK — no print/echo/log/std*.write takes a password/code/token
#      variable; no secret literal.
#   6. CLIENT-STORE-ONLY — credential resolution uses the SecretStore resolver; no
#      operator path / operator key literal.
#   7. TIER-1-PRIMARY — in ghl_auth.py the Tier-1 token branch precedes the
#      ghl_auth_fallback import / run_tier2 call.
#   8. DOCTRINE SENTINEL — the Tier-2 sentinel present verbatim in 5 docs.
#   (No-client-names is enforced by qc-assert-no-client-names.sh, also wired in QC.)
#
# Modeled on guard-ghl-token-only.sh (same --repo-root, exit 0/1/2, red/green/
# yellow, Python-tokenizer strip for .py, fail-closed on unparseable Python).
#
# Exit codes:
#   0 — PASS    1 — FAIL    2 — usage / environment error
#
# Usage:
#   bash scripts/guard-ghl-auth-fallback.sh
#   bash scripts/guard-ghl-auth-fallback.sh --repo-root /path/to/repo

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    -h|--help) sed -n '1,70p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

SKILL_DIR="$REPO_ROOT/06-ghl-install-pages"
TOOLS_DIR="$SKILL_DIR/tools"
SCRIPTS_DIR="$REPO_ROOT/scripts"
TESTS_DIR="$SKILL_DIR/tests"

ORCH="$TOOLS_DIR/ghl_auth.py"
FALLBACK="$TOOLS_DIR/ghl_auth_fallback.py"
BROWSER="$TOOLS_DIR/ghl_login_browser.py"

# ── The Tier-2 doctrine sentinel (MUST appear verbatim) ───────────────────────
SENTINEL='GHL-AUTH-DOCTRINE: TIER-2 EMAIL-2FA FALLBACK — gated (auth+gmail-proven+email-2fa+creds), bounded, self-heals to TOKEN-ONLY'

REQUIRED_SENTINEL_DOCS=(
  "$SKILL_DIR/SKILL.md"
  "$SKILL_DIR/INSTRUCTIONS.md"
  "$SKILL_DIR/CORE_UPDATES.md"
  "$REPO_ROOT/AGENTS.md"
  "$REPO_ROOT/TOOLS.md"
)

# ── BANNED ACTIVE-LOGIN / 2FA PATTERNS (ERE) — same family as token-only guard ─
BANNED_PATTERNS=(
  'input\[type=?["'"'"']?password'
  '\.type\([^)]*[Pp]assword'
  '\.fill\([^)]*[Pp]assword'
  'sendKeys\([^)]*[Pp]assword'
  '\.value[[:space:]]*=[[:space:]]*.*[Pp]assword'
  'document\.querySelector\([^)]*password[^)]*\)\.(value|type|fill)'
  'os\.environ(\.get\(|\[)[[:space:]]*["'"'"'](GHL_(AGENCY_)?PASSWORD|GHL_(AGENCY_)?EMAIL)'
  '\$\{?GHL_(AGENCY_)?PASSWORD'
  '\$\{?GHL_(AGENCY_)?EMAIL'
  '(do|ui|perform|auto|automatic)_?[Ll]ogin'
  'login[Ww]ith(Email|Password|Credentials)'
  'signInWith(Email|Password)'
  '(handle_?2fa|enter_?otp|two_?factor_?(fill|submit|enter|input))'
  'fill[_-]?(the[_-]?)?(sign[_-]?in|login)[_-]?form'
)
# Allow read-only DETECTION idioms (same forgiveness as token-only guard).
ALLOW_REGEX='(!!|hasPwd|hasPassword|querySelectorAll|onLogin|ACTIVATE-BOUNCED|detect|throw|STOP|REFUSE|return false|return null|=== *null)'

red(){ printf "\033[31m%s\033[0m\n" "$1"; }
green(){ printf "\033[32m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }

FAILS=0

echo ""
echo "═══ guard-ghl-auth-fallback — GHL TIER-2 EMAIL-2FA fallback doctrine ═══"
echo ""

# ── 0. Required new files must exist ──────────────────────────────────────────
for f in "$ORCH" "$FALLBACK" "$BROWSER"; do
  if [ ! -f "$f" ]; then
    red "  ✗ FAIL — required Tier-2 module missing: ${f#$REPO_ROOT/}"
    FAILS=$((FAILS + 1))
  fi
done
if [ "$FAILS" -gt 0 ]; then
  echo ""; red "guard-ghl-auth-fallback FAILED — Tier-2 modules not found."; exit 1
fi

# ── Python tokenizer strip (comments + string literals blanked; fail-closed) ──
strip_python() {
  python3 - "$1" <<'PY'
import io, sys, tokenize
path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    src = fh.read()
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
    sys.stdout.write("0:GUARD-ERROR-UNPARSEABLE-PYTHON do_login\n")
    sys.exit(0)
for i in range(n):
    sys.stdout.write("%d:%s\n" % (i + 1, "".join(grid[i])))
PY
}

# Strip ONLY comments (NOT string literals). Used for the containment scan so a
# login pattern hidden inside a string literal (e.g. a password selector, or
# .fill("...password...")) is still caught, while the doctrine's negated prose in
# COMMENTS stays forgiven. Fails closed on unparseable Python.
strip_python_comments_only() {
  python3 - "$1" <<'PY'
import io, sys, tokenize
path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    src = fh.read()
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
        if tok.type == tokenize.COMMENT:
            erase(tok.start, tok.end)
        # A module/func docstring is a bare STRING statement on its own line(s);
        # blank multi-line triple-quoted strings so doctrine prose in docstrings
        # does not false-positive, but keep ordinary inline string literals
        # (selectors, paths) intact so embedded login/secret markers are caught.
        elif tok.type == tokenize.STRING and tok.start[0] != tok.end[0]:
            erase(tok.start, tok.end)
except (tokenize.TokenError, IndentationError, SyntaxError):
    sys.stdout.write("0:GUARD-ERROR-UNPARSEABLE-PYTHON do_login\n")
    sys.exit(0)
for i in range(n):
    sys.stdout.write("%d:%s\n" % (i + 1, "".join(grid[i])))
PY
}

strip_bash() {
  awk '
  {
    line = $0
    if (line ~ /^[[:space:]]*#/) { print NR ":"; next }
    sub(/[[:space:]]#.*$/, "", line)
    print NR ":" line
  }' "$1"
}

# Combined banned-pattern alternation (built once).
BANNED_ALT="$(printf '%s\n' "${BANNED_PATTERNS[@]}" | paste -sd'|' -)"

# Return 0 if a banned (non-allowed) pattern hits anywhere in the stripped file.
# Fast path: grep the WHOLE stripped output once for any banned pattern, then for
# each matching line drop the ones a read-only ALLOW idiom forgives. This avoids
# the per-line × per-pattern subprocess storm (a 10x+ speedup).
file_has_banned() {
  local file="$1" stripper="$2"
  local hits
  hits="$("$stripper" "$file" | grep -E "$BANNED_ALT" 2>/dev/null | grep -Ev "$ALLOW_REGEX" 2>/dev/null)"
  [ -n "$hits" ]
}

# ── 1. LOGIN CONTAINMENT ──────────────────────────────────────────────────────
echo "── 1. Login containment (banned login patterns in exactly the 2 allowlisted files) ──"
ALLOWLIST_BASENAMES=("ghl_auth_fallback.py" "ghl_login_browser.py")
is_allowlisted() {
  local base; base="$(basename "$1")"
  for a in "${ALLOWLIST_BASENAMES[@]}"; do [ "$base" = "$a" ] && return 0; done
  return 1
}
# The two allowlisted files SHOULD carry login code (they own it).
for f in "$FALLBACK" "$BROWSER"; do
  if file_has_banned "$f" strip_python; then
    green "  ✓ PASS — login code present (expected) in ${f#$REPO_ROOT/}"
  else
    yellow "  ⚠ note — no banned login pattern detected in ${f#$REPO_ROOT/} (still allowlisted)"
  fi
done
# Everything ELSE under tools/ + scripts/ must be CLEAN (excluding self + guards +
# the Tier-1 files which the token-only guard owns).
CONTAIN_FAIL=0
scan_clean() {
  local file="$1" stripper="$2"
  is_allowlisted "$file" && return 0
  case "$(basename "$file")" in
    guard-ghl-auth-fallback.sh|guard-ghl-token-only.sh|guard-ghl-activation-resilience.sh) return 0 ;;
    seed-ghl-auth.py|inject-ghl-auth.sh) return 0 ;;  # owned by token-only guard
  esac
  if file_has_banned "$file" "$stripper"; then
    red "  ✗ FAIL — login/2FA pattern OUTSIDE the allowlist: ${file#$REPO_ROOT/}"
    CONTAIN_FAIL=$((CONTAIN_FAIL + 1))
  fi
}
# For NON-allowlisted files we strip ONLY comments (keep string literals) so a
# login pattern hidden inside a string (selector / .fill("...password...")) is
# still caught — the doctrine prose lives in comments/docstrings and stays clean.
while IFS= read -r f; do scan_clean "$f" strip_python_comments_only; done < <(find "$TOOLS_DIR" -name '*.py' -type f 2>/dev/null)
while IFS= read -r f; do scan_clean "$f" strip_bash;                 done < <(find "$TOOLS_DIR" -name '*.sh' -type f 2>/dev/null)
while IFS= read -r f; do scan_clean "$f" strip_python_comments_only; done < <(find "$SCRIPTS_DIR" -name '*.py' -type f 2>/dev/null)
if [ "$CONTAIN_FAIL" -eq 0 ]; then
  green "  ✓ PASS — no login/2FA code outside the two allowlisted files."
else
  FAILS=$((FAILS + CONTAIN_FAIL))
fi

# ── helper: first stripped line number matching an ERE in a file ──────────────
# The stripper emits "lineno:code"; grep the whole stream once for the pattern in
# the CODE portion and return the first matching line number. The pattern is
# anchored after the "lineno:" prefix so a digit in the line number can't match.
first_line_matching() {
  local file="$1" pat="$2"
  strip_python "$file" | grep -E "^[0-9]+:.*($pat)" 2>/dev/null | head -1 | cut -d: -f1
}
# Sentinel comments are stripped by the tokenizer (they're comments), so check the
# RAW file for the four gate sentinel comments.
raw_first_line() {
  grep -nE "$2" "$1" 2>/dev/null | head -1 | cut -d: -f1
}

# ── 2. GATE-BEFORE-LOGIN ORDERING (in ghl_auth_fallback.py) ───────────────────
echo ""
echo "── 2. Gate-before-login ordering ──"
ORDER_FAIL=0
for sent in 'GATE-A: AUTHORIZATION' 'GATE-B: GMAIL-PROVEN' 'GATE-C: EMAIL-2FA-SELECTED' 'GATE-D: CREDS-PRESENT'; do
  if ! grep -Fq "# $sent" "$FALLBACK"; then
    red "  ✗ FAIL — missing required gate sentinel comment: # $sent"
    ORDER_FAIL=$((ORDER_FAIL + 1))
  fi
done
# The four gate CALLS inside check_all_gates (code, not comments).
LAST_GATE_CALL=$(first_line_matching "$FALLBACK" 'gate_d_creds_present\(')
FIRST_LOGIN=$(first_line_matching "$FALLBACK" 'def login_with_2fa\(|fill_password\(|\.fill_password')
if [ -z "$LAST_GATE_CALL" ]; then
  red "  ✗ FAIL — gate_d_creds_present() call not found in code."
  ORDER_FAIL=$((ORDER_FAIL + 1))
fi
if [ -z "$FIRST_LOGIN" ]; then
  red "  ✗ FAIL — login_with_2fa()/password action not found in code."
  ORDER_FAIL=$((ORDER_FAIL + 1))
fi
if [ -n "$LAST_GATE_CALL" ] && [ -n "$FIRST_LOGIN" ]; then
  if [ "$LAST_GATE_CALL" -lt "$FIRST_LOGIN" ]; then
    green "  ✓ PASS — last gate call (L$LAST_GATE_CALL) precedes first login action (L$FIRST_LOGIN)."
  else
    red "  ✗ FAIL — a login action (L$FIRST_LOGIN) appears BEFORE the last gate call (L$LAST_GATE_CALL)."
    ORDER_FAIL=$((ORDER_FAIL + 1))
  fi
fi
# check_all_gates must call all four gates.
for g in gate_a_authorization gate_b_gmail_proven gate_c_email_2fa gate_d_creds_present; do
  if ! grep -Eq "$g\(" "$FALLBACK"; then
    red "  ✗ FAIL — gate call missing: $g()"
    ORDER_FAIL=$((ORDER_FAIL + 1))
  fi
done
[ "$ORDER_FAIL" -eq 0 ] && green "  ✓ PASS — all four gates present and ordered before login."
FAILS=$((FAILS + ORDER_FAIL))

# ── 3. BOUNDED ATTEMPTS ───────────────────────────────────────────────────────
echo ""
echo "── 3. Bounded login attempts + backoff + hard-stop ──"
ATT_FAIL=0
MAXVAL=$(grep -Eo 'MAX_LOGIN_ATTEMPTS[[:space:]]*=[[:space:]]*[0-9]+' "$FALLBACK" | grep -Eo '[0-9]+$' | head -1)
if [ -z "$MAXVAL" ]; then
  red "  ✗ FAIL — MAX_LOGIN_ATTEMPTS constant not found."
  ATT_FAIL=$((ATT_FAIL + 1))
elif [ "$MAXVAL" -gt 3 ]; then
  red "  ✗ FAIL — MAX_LOGIN_ATTEMPTS=$MAXVAL exceeds the cap of 3."
  ATT_FAIL=$((ATT_FAIL + 1))
else
  green "  ✓ PASS — MAX_LOGIN_ATTEMPTS=$MAXVAL (<= 3)."
fi
grep -Eq 'range\([^)]*MAX_LOGIN_ATTEMPTS|while[^\n]*MAX_LOGIN_ATTEMPTS' "$FALLBACK" \
  && green "  ✓ PASS — login loop references MAX_LOGIN_ATTEMPTS." \
  || { red "  ✗ FAIL — login loop does not reference MAX_LOGIN_ATTEMPTS."; ATT_FAIL=$((ATT_FAIL + 1)); }
grep -Eq 'backoff\(' "$FALLBACK" \
  && green "  ✓ PASS — backoff present." \
  || { red "  ✗ FAIL — no backoff call in the login loop."; ATT_FAIL=$((ATT_FAIL + 1)); }
grep -Eiq 'lockout|captcha|hard-stop|detect_lockout_or_captcha' "$FALLBACK" \
  && green "  ✓ PASS — lockout/captcha hard-stop present." \
  || { red "  ✗ FAIL — no lockout/captcha hard-stop."; ATT_FAIL=$((ATT_FAIL + 1)); }
FAILS=$((FAILS + ATT_FAIL))

# ── 4. SELF-HEAL present ──────────────────────────────────────────────────────
echo ""
echo "── 4. Self-heal writes the canonical refresh-token key ──"
SH_FAIL=0
grep -Fq 'REFRESH_TOKEN_KEY = "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN"' "$FALLBACK" \
  && green "  ✓ PASS — REFRESH_TOKEN_KEY anchored to GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN." \
  || { red "  ✗ FAIL — REFRESH_TOKEN_KEY not anchored to GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN."; SH_FAIL=$((SH_FAIL + 1)); }
grep -Eq 'write_secret\([[:space:]]*REFRESH_TOKEN_KEY' "$FALLBACK" \
  && green "  ✓ PASS — success path writes REFRESH_TOKEN_KEY to the store." \
  || { red "  ✗ FAIL — no write_secret(REFRESH_TOKEN_KEY, ...) in the self-heal path."; SH_FAIL=$((SH_FAIL + 1)); }
FAILS=$((FAILS + SH_FAIL))

# ── 5. NO-SECRET-LEAK ─────────────────────────────────────────────────────────
echo ""
echo "── 5. No secret leak (no print/echo/log of password/code/token; no literals) ──"
LEAK_FAIL=0
# A print/log/std*.write call whose line ALSO names a secret variable. Single grep
# pass over the stripped output (string literals blanked so a benign string isn't
# flagged; a real `print(refresh_token)` survives because the variable is code).
_LEAK_CALL='(print|logging\.[a-z]+|logger\.[a-z]+|sys\.std(out|err)\.write|echo)[[:space:]]*\('
_LEAK_VAR='\b(password|passwd|refresh_token|id_token|access_token|firebase_token|otp_code)\b'
for f in "$FALLBACK" "$BROWSER" "$ORCH"; do
  leak="$(strip_python "$f" | grep -E "$_LEAK_CALL" 2>/dev/null | grep -Ei "$_LEAK_VAR" 2>/dev/null)"
  if [ -n "$leak" ]; then
    red "  ✗ FAIL — possible secret in a log/print: ${f#$REPO_ROOT/}"
    LEAK_FAIL=$((LEAK_FAIL + 1))
  fi
done
# No long JWT/base64-looking literal (a real token).
if grep -EqR '["'"'"'][A-Za-z0-9_-]{120,}["'"'"']' "$FALLBACK" "$BROWSER" "$ORCH" 2>/dev/null; then
  red "  ✗ FAIL — a long token-looking string literal is present (possible secret)."
  LEAK_FAIL=$((LEAK_FAIL + 1))
fi
[ "$LEAK_FAIL" -eq 0 ] && green "  ✓ PASS — no password/code/token printed or logged; no secret literal."
FAILS=$((FAILS + LEAK_FAIL))

# ── 6. CLIENT-STORE-ONLY ──────────────────────────────────────────────────────
echo ""
echo "── 6. Client-store-only credential resolution ──"
CS_FAIL=0
grep -Eq 'class SecretStore|SecretStore\(' "$FALLBACK" "$ORCH" \
  && green "  ✓ PASS — credential resolution uses the SecretStore resolver." \
  || { red "  ✗ FAIL — no SecretStore resolver reference."; CS_FAIL=$((CS_FAIL + 1)); }
# No operator path literal in the production modules. Strip COMMENTS + multi-line
# docstrings (so doctrine prose mentioning a path is allowed) but KEEP inline
# string literals — an operator HOME path baked into a string (e.g.
# open("/Users/operator/...")) is a hard fail.
for f in "$FALLBACK" "$BROWSER" "$ORCH"; do
  if strip_python_comments_only "$f" | grep -Eq '/Users/[A-Za-z0-9._-]+'; then
    red "  ✗ FAIL — operator path literal in code: ${f#$REPO_ROOT/}"
    CS_FAIL=$((CS_FAIL + 1))
  fi
done
[ "$CS_FAIL" -eq 0 ] && green "  ✓ PASS — no operator path; client-store resolution only."
FAILS=$((FAILS + CS_FAIL))

# ── 7. TIER-1-PRIMARY (branch order in ghl_auth.py) ───────────────────────────
echo ""
echo "── 7. Tier-1-primary branch order in the orchestrator ──"
T1_FAIL=0
TIER1_LINE=$(first_line_matching "$ORCH" 'tier1_mint_and_seed\(|resolve_refresh_token\(')
FALLBACK_IMPORT_LINE=$(first_line_matching "$ORCH" 'import ghl_auth_fallback|run_tier2\(')
if [ -z "$TIER1_LINE" ]; then
  red "  ✗ FAIL — orchestrator does not attempt Tier 1 (resolve_refresh_token/tier1_mint_and_seed)."
  T1_FAIL=$((T1_FAIL + 1))
elif [ -z "$FALLBACK_IMPORT_LINE" ]; then
  red "  ✗ FAIL — orchestrator never references the fallback (import/run_tier2)."
  T1_FAIL=$((T1_FAIL + 1))
elif [ "$TIER1_LINE" -lt "$FALLBACK_IMPORT_LINE" ]; then
  green "  ✓ PASS — Tier-1 token branch (L$TIER1_LINE) precedes fallback import (L$FALLBACK_IMPORT_LINE)."
else
  red "  ✗ FAIL — fallback import (L$FALLBACK_IMPORT_LINE) precedes the Tier-1 branch (L$TIER1_LINE)."
  T1_FAIL=$((T1_FAIL + 1))
fi
# The fallback import MUST be lazy (inside a function), not at module top level
# (col-0 import). A top-level "import ghl_auth_fallback" is a hard fail.
if grep -Eq '^import ghl_auth_fallback|^from ghl_auth_fallback' "$ORCH"; then
  red "  ✗ FAIL — ghl_auth_fallback is imported at module top level (must be lazy)."
  T1_FAIL=$((T1_FAIL + 1))
else
  green "  ✓ PASS — fallback import is lazy (not module-top)."
fi
FAILS=$((FAILS + T1_FAIL))

# ── 8. DOCTRINE SENTINEL in all required docs ─────────────────────────────────
echo ""
echo "── 8. Doctrine sentinel present in all required docs ──"
for doc in "${REQUIRED_SENTINEL_DOCS[@]}"; do
  rel="${doc#$REPO_ROOT/}"
  if [ ! -f "$doc" ]; then
    red "  ✗ FAIL — required doc missing: $rel"; FAILS=$((FAILS + 1)); continue
  fi
  if grep -Fq "$SENTINEL" "$doc"; then
    green "  ✓ PASS — sentinel present in $rel"
  else
    red "  ✗ FAIL — Tier-2 doctrine sentinel MISSING from $rel"
    FAILS=$((FAILS + 1))
  fi
done

# ── re-assert the Tier-1 token-only guard still passes (companion invariant) ──
echo ""
echo "── companion: Tier-1 token-only guard must still PASS ──"
if [ -f "$SCRIPTS_DIR/guard-ghl-token-only.sh" ]; then
  if bash "$SCRIPTS_DIR/guard-ghl-token-only.sh" --repo-root "$REPO_ROOT" >/dev/null 2>&1; then
    green "  ✓ PASS — guard-ghl-token-only.sh still green (Tier-1 files clean)."
  else
    red "  ✗ FAIL — guard-ghl-token-only.sh is RED; Tier-1 files were disturbed."
    FAILS=$((FAILS + 1))
  fi
else
  yellow "  ⚠ note — guard-ghl-token-only.sh not found at expected path."
fi

echo ""
if [ "$FAILS" -eq 0 ]; then
  green "guard-ghl-auth-fallback PASS — Tier-2 contained, gated-before-login, bounded, self-healing, leak-free."
  exit 0
else
  red "guard-ghl-auth-fallback FAILED — $FAILS violation(s)."
  exit 1
fi
