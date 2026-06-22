#!/usr/bin/env bash
# guard-ghl-token-only.sh — v1.0.0
#
# CI / QC GUARD for the GHL TOKEN-ONLY AUTH DOCTRINE (Skill 06, D7).
#
# THE DOCTRINE (D7 — "TOKEN-ONLY"):
#   GHL / Convert and Flow funnel/website/page builds authenticate by ONE path
#   only: mint a Firebase id_token from GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN and
#   reconstruct the SPA session (Firebase IndexedDB record + the six SPA
#   cookies), headless. NO Sign-in form is auto-filled, NO password is typed,
#   two-factor (2FA) is NEVER reached. On token failure the builder STOPS and
#   reports — it does NOT auto-open the login form or a 2FA prompt. The fix is a
#   fresh refresh token (Token Grabber), never a UI login. GHL_AGENCY_EMAIL /
#   GHL_AGENCY_PASSWORD are a DOCUMENTED, MANUAL human-operator last resort only,
#   never auto-invoked by any agent or script.
#
# WHAT THIS GUARD ENFORCES (fails the build / QC on any violation):
#   (1) CODE INVARIANT — the auth scripts (tools/seed-ghl-auth.py,
#       tools/inject-ghl-auth.sh) must NOT reintroduce an AUTOMATIC UI-login or a
#       2FA fallback. We scan CODE LINES ONLY (Python docstrings + `#` comments
#       and bash `#` comments are stripped first) so the doctrine's own negated
#       prose ("NO auto UI-login", "GHL_AGENCY_PASSWORD remain a MANUAL last
#       resort") never false-positives. The banned ACTIVE-LOGIN patterns are
#       things that only appear when an agent is actually driving the login form:
#         - typing/filling a password field (.type/.fill/sendKeys/setting .value
#           on an input[type=password], document.querySelector('...password...')
#           followed by a write)
#         - reading GHL_PASSWORD / GHL_AGENCY_PASSWORD / GHL_EMAIL into the code
#           path (os.environ[...PASSWORD...], a $GHL_*PASSWORD shell expansion)
#         - calling a login routine (do_login/ui_login/perform_login/loginWith*/
#           signInWithEmail/two_factor/handle_2fa/enter_otp)
#       A single read-only DETECTION of a password field (to STOP and report) is
#       explicitly allowed — see ALLOW patterns below.
#   (2) DOCTRINE SENTINEL — the canonical sentinel string MUST be present in the
#       skill docs (SKILL.md, INSTRUCTIONS.md, CORE_UPDATES.md). If a doc loses
#       the sentinel, an agent could silently revert to the old login pattern, so
#       its absence is a hard FAIL.
#
# Modeled on: scripts/qc-assert-no-client-names.sh (same enumeration / exit /
#   self-exclusion conventions) and scripts/qc-assert-ghl-mcp-supervised.sh.
#
# Exit codes:
#   0  — PASS (no auto-login/2FA in code; sentinel present in every required doc)
#   1  — FAIL (auto-login/2FA reintroduced, or a required doc lost the sentinel)
#   2  — usage / environment error
#
# Usage:
#   bash scripts/guard-ghl-token-only.sh
#   bash scripts/guard-ghl-token-only.sh --repo-root /path/to/repo

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    -h|--help) sed -n '1,60p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

SKILL_DIR="$REPO_ROOT/06-ghl-install-pages"
TOOLS_DIR="$SKILL_DIR/tools"
SEED_PY="$TOOLS_DIR/seed-ghl-auth.py"
INJECT_SH="$TOOLS_DIR/inject-ghl-auth.sh"

# ── The canonical doctrine sentinel (MUST appear verbatim) ────────────────────
# Keep this byte-for-byte identical everywhere it is embedded (AGENTS.md,
# TOOLS.md, the skill docs, the CORE_UPDATES bridge).
SENTINEL='GHL-AUTH-DOCTRINE: TOKEN-ONLY (D7) — refresh-token seed is the only auth path; NO auto UI-login / password / 2FA'

# Docs that MUST carry the sentinel so an agent reading any of them gets the rule.
REQUIRED_SENTINEL_DOCS=(
  "$SKILL_DIR/SKILL.md"
  "$SKILL_DIR/INSTRUCTIONS.md"
  "$SKILL_DIR/CORE_UPDATES.md"
)

# ── BANNED ACTIVE-LOGIN / 2FA PATTERNS (ERE) ──────────────────────────────────
# These only appear in CODE that is actually driving a UI login or a 2FA flow.
# Matched ONLY against code lines (docstrings/comments stripped first).
BANNED_PATTERNS=(
  # Typing / filling a password (any engine).
  'input\[type=?["'"'"']?password'
  '\.type\([^)]*[Pp]assword'
  '\.fill\([^)]*[Pp]assword'
  'sendKeys\([^)]*[Pp]assword'
  '\.value[[:space:]]*=[[:space:]]*.*[Pp]assword'
  'document\.querySelector\([^)]*password[^)]*\)\.(value|type|fill)'
  # Reading the manual-only login creds INTO the code path (env access in code).
  'os\.environ(\.get\(|\[)[[:space:]]*["'"'"'](GHL_(AGENCY_)?PASSWORD|GHL_(AGENCY_)?EMAIL)'
  '\$\{?GHL_(AGENCY_)?PASSWORD'
  '\$\{?GHL_(AGENCY_)?EMAIL'
  # Calling a login / sign-in / 2FA routine.
  '(do|ui|perform|auto|automatic)_?[Ll]ogin'
  'login[Ww]ith(Email|Password|Credentials)'
  'signInWith(Email|Password)'
  '(handle_?2fa|enter_?otp|two_?factor_?(fill|submit|enter|input))'
  'fill[_-]?(the[_-]?)?(sign[_-]?in|login)[_-]?form'
)

# ── ALLOW patterns (read-only DETECTION of a failed seed — NOT a violation) ────
# A line matching a BANNED pattern is forgiven ONLY if it ALSO matches one of
# these read-only detection idioms. These are the legitimate "did the seed fail?
# → STOP" checks (e.g. `const hasPwd = !!document.querySelector('input[type=
# password]')`). The distinguishing feature: the password selector is wrapped in
# a boolean/presence test (!!, hasPwd, ?, querySelector(...) with no write), and
# the line throws / sets a stop flag rather than typing into the field.
ALLOW_REGEX='(!!|hasPwd|hasPassword|querySelectorAll|onLogin|ACTIVATE-BOUNCED|detect|throw|STOP|REFUSE|return false|return null|=== *null)'

red(){ printf "\033[31m%s\033[0m\n" "$1"; }
green(){ printf "\033[32m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }

FAILS=0

echo ""
echo "═══ guard-ghl-token-only — GHL TOKEN-ONLY auth doctrine (D7) ═══"
echo ""

# ── 0. The auth scripts must exist ────────────────────────────────────────────
for f in "$SEED_PY" "$INJECT_SH"; do
  if [ ! -f "$f" ]; then
    red "  ✗ FAIL — auth script missing: ${f#$REPO_ROOT/}"
    FAILS=$((FAILS + 1))
  fi
done
if [ "$FAILS" -gt 0 ]; then
  echo ""; red "guard-ghl-token-only FAILED — auth scripts not found."; exit 1
fi

# ── 1. CODE INVARIANT — no auto UI-login / 2FA in the auth scripts ────────────
# Strip docstrings + comments so the doctrine's negated prose can't trigger.
strip_python() {
  # Emit "lineno:codeonly" with comments AND string-literal contents blanked,
  # so the doctrine's own negated prose (docstrings, comment lines, and any
  # explanatory string) cannot trigger a banned-pattern match. We use Python's
  # own tokenizer: COMMENT and STRING tokens are replaced with empty space,
  # everything else (the actual code) is preserved on its original line number.
  # If tokenizing fails, we FAIL CLOSED (emit a sentinel error line) so the
  # guard never silently passes a file it could not analyze.
  python3 - "$1" <<'PY'
import io, sys, tokenize

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    src = fh.read()
lines = src.splitlines()
n = len(lines)
# Per-line list of chars; we will erase columns covered by COMMENT/STRING tokens.
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
except (tokenize.TokenError, IndentationError, SyntaxError) as e:
    # Fail closed: surface a line the bash scanner will flag (it matches none of
    # the ALLOW idioms, so it is reported and the guard FAILS rather than passing
    # an unanalyzable file).
    sys.stdout.write("0:GUARD-ERROR-UNPARSEABLE-PYTHON do_login\n")
    sys.exit(0)

for i in range(n):
    sys.stdout.write("%d:%s\n" % (i + 1, "".join(grid[i])))
PY
}

strip_bash() {
  # Emit "lineno:codeonly" — blank out full-line and inline # comments. This is
  # a heuristic strip (does not parse heredocs), which is fine: the banned
  # patterns are active-login code, and the inject script's only password
  # reference is a read-only detection inside a heredoc that the ALLOW regex
  # forgives anyway.
  awk '
  {
    line = $0
    # Strip a leading-whitespace full-line comment.
    if (line ~ /^[[:space:]]*#/) { print NR ":"; next }
    # Strip an inline comment (best-effort: from " #" to EOL).
    sub(/[[:space:]]#.*$/, "", line)
    print NR ":" line
  }' "$1"
}

scan_code() {
  local file="$1" label="$2" stripper="$3"
  local hits=0
  local codeln
  while IFS= read -r codeln; do
    local lineno="${codeln%%:*}"
    local code="${codeln#*:}"
    [ -z "$code" ] && continue
    for pat in "${BANNED_PATTERNS[@]}"; do
      if printf '%s' "$code" | grep -Eq "$pat"; then
        # Forgive read-only detection idioms (failed-seed STOP checks).
        if printf '%s' "$code" | grep -Eq "$ALLOW_REGEX"; then
          continue
        fi
        red "  ✗ FAIL — $label:$lineno reintroduces auto UI-login / 2FA:"
        echo "          $(printf '%s' "$code" | sed 's/^[[:space:]]*//' | cut -c1-120)"
        echo "          (matched banned pattern: $pat)"
        hits=$((hits + 1))
      fi
    done
  done < <("$stripper" "$file")
  if [ "$hits" -eq 0 ]; then
    green "  ✓ PASS — $label has no auto UI-login / 2FA code path."
  fi
  return "$hits"
}

scan_code "$SEED_PY"   "seed-ghl-auth.py"   strip_python || FAILS=$((FAILS + $?))
scan_code "$INJECT_SH" "inject-ghl-auth.sh" strip_bash   || FAILS=$((FAILS + $?))

# ── 2. DOCTRINE SENTINEL — present in every required doc ──────────────────────
echo ""
for doc in "${REQUIRED_SENTINEL_DOCS[@]}"; do
  rel="${doc#$REPO_ROOT/}"
  if [ ! -f "$doc" ]; then
    red "  ✗ FAIL — required doc missing: $rel"
    FAILS=$((FAILS + 1))
    continue
  fi
  if grep -Fq "$SENTINEL" "$doc"; then
    green "  ✓ PASS — sentinel present in $rel"
  else
    red "  ✗ FAIL — doctrine sentinel MISSING from $rel"
    echo "          expected verbatim: $SENTINEL"
    FAILS=$((FAILS + 1))
  fi
done

echo ""
if [ "$FAILS" -eq 0 ]; then
  green "guard-ghl-token-only PASS — TOKEN-ONLY doctrine intact (no auto login/2FA; sentinel present)."
  exit 0
else
  red "guard-ghl-token-only FAILED — $FAILS violation(s)."
  echo ""
  echo "REMEDY:"
  echo "  - If a CODE FAIL: the auth scripts must NEVER auto-fill a login form,"
  echo "    type a password, read GHL_(AGENCY_)PASSWORD/EMAIL into a browser"
  echo "    action, or handle 2FA. The ONLY auth path is the Firebase"
  echo "    refresh-token seed (seed-ghl-auth.py + inject-ghl-auth.sh). On token"
  echo "    failure: STOP + report, re-grab via the Token Grabber. A read-only"
  echo "    DETECTION of a password field (to STOP) is allowed."
  echo "  - If a SENTINEL FAIL: restore the verbatim doctrine sentinel to the doc."
  exit 1
fi
