#!/usr/bin/env bash
# guard-ghl-activation-resilience.sh — v1.0.0
#
# CI / QC GUARD for the GHL LAYER-2 ACTIVATION RESILIENCE doctrine (Skill 06).
#
# COMPANION to scripts/guard-ghl-token-only.sh. Together they form the two GHL
# auth guardrails:
#   - guard-ghl-token-only.sh        → the auth MODEL (refresh-token seed ONLY;
#                                       no auto UI-login / password / 2FA).
#   - guard-ghl-activation-resilience.sh (THIS) → the auth ACTIVATION must be
#                                       RESILIENT (no single-shot regression).
#
# THE BUG THIS PREVENTS (confirmed root cause, 2026-06-21 adversarial diagnostic):
#   GHL token-only auth has two layers. Layer 1 (seed-ghl-auth.py) mints a
#   Firebase id_token — always reliable. Layer 2 (inject-ghl-auth.sh) establishes
#   the GHL app-session + activates the SPA. The failure was a Layer-2 ACTIVATION
#   RACE: the OLD activate ran SINGLE-SHOT — one store.dispatch('auth/get') + one
#   $router.push('/') + one fixed ~900ms wait. That single attempt fired BEFORE
#   the SPA's Vuex auth store had warmed up and re-read the freshly-written
#   cookies, so it resolved cold and GoHighLevel bounced to the login screen
#   (log signature: `ACTIVATE-BOUNCED-TO-LOGIN: href=...`). The token was always
#   fine; a concurrent run won the race by luck, the failing ones lost it.
#
# THE CORRECT HARDENING (this guard asserts EXACTLY these invariants):
#   REQUIRED (must be present — ABSENCE fails CI):
#     R1. Bounded RETRY LOOP with backoff+jitter around Layer-2 activation
#         (NOT single-shot).
#     R2. A WARM-STORE READINESS gate: wait until the SPA auth store is booted
#         AND cookie `a` is readable before activating.
#     R3. Token-only COOKIE RE-ASSERT on wipe: if cookie `a` is wiped, re-fetch
#         login/current with the same id_token and re-write cookies (token-only).
#     R4. POSITIVE LIVENESS CHECK: success requires cookie `a` present AND its
#         decoded apiKey matches the logged-in user — NOT merely "no password
#         field visible".
#     R5. NO post-seed page reload / navigation to app root that re-runs the boot
#         IIFE (the no-reload rule).
#     R6. Layer-1 mint (securetoken POST in seed-ghl-auth.py) has a bounded retry
#         (not single-shot).
#   FORBIDDEN (must FAIL CI if present):
#     F1. A single-shot activate (auth/get + router.push) with NO surrounding
#         retry loop.
#     F2. A liveness/success determination based ONLY on hasPwd / "no password
#         box" with NO cookie-`a`+apiKey assertion.
#     F3. A post-seed reload()/location.assign/goto to the app root after seeding.
#     F4. A hardcoded deep /location/<id>/ route literal in the activate path (the
#         seed has 16 locations, no single id; the working run used plain '/').
#
# HOW IT SCANS:
#   The guard reads the two auth tool files (tools/inject-ghl-auth.sh,
#   tools/seed-ghl-auth.py). For REQUIRED markers and FORBIDDEN patterns we scan
#   CODE LINES ONLY — Python docstrings/comments and bash `#` comments are
#   stripped first (same technique as guard-ghl-token-only.sh) so that the
#   doctrine's own negated prose ("NEVER reload", "NOT merely no-password-box")
#   cannot false-positive a FORBIDDEN pattern, and so a REQUIRED marker only
#   counts when it is real code, not a comment describing it.
#
# Modeled on: scripts/guard-ghl-token-only.sh (same enumeration / exit-code /
#   self-exclusion / code-strip conventions).
#
# Exit codes:
#   0  — PASS (every REQUIRED marker present in code; no FORBIDDEN pattern in code)
#   1  — FAIL (a REQUIRED marker is absent, OR a FORBIDDEN pattern is present)
#   2  — usage / environment error
#
# Usage:
#   bash scripts/guard-ghl-activation-resilience.sh
#   bash scripts/guard-ghl-activation-resilience.sh --repo-root /path/to/repo

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    -h|--help) sed -n '1,90p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

SKILL_DIR="$REPO_ROOT/06-ghl-install-pages"
TOOLS_DIR="$SKILL_DIR/tools"
SEED_PY="$TOOLS_DIR/seed-ghl-auth.py"
INJECT_SH="$TOOLS_DIR/inject-ghl-auth.sh"

red(){ printf "\033[31m%s\033[0m\n" "$1"; }
green(){ printf "\033[32m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }

FAILS=0

echo ""
echo "═══ guard-ghl-activation-resilience — GHL Layer-2 activation (no single-shot regression) ═══"
echo ""

# ── 0. The auth scripts must exist ────────────────────────────────────────────
for f in "$SEED_PY" "$INJECT_SH"; do
  if [ ! -f "$f" ]; then
    red "  ✗ FAIL — auth script missing: ${f#$REPO_ROOT/}"
    FAILS=$((FAILS + 1))
  fi
done
if [ "$FAILS" -gt 0 ]; then
  echo ""; red "guard-ghl-activation-resilience FAILED — auth scripts not found."; exit 1
fi

# ── Code strippers (comments/docstrings → blanks), shared style w/ token-only ──
strip_python() {
  # Emit "lineno:codeonly" with COMMENT and STRING tokens blanked via Python's
  # own tokenizer, so docstrings/comments cannot satisfy a REQUIRED marker nor
  # trigger a FORBIDDEN pattern. Fail CLOSED on a tokenizer error so the guard
  # never silently passes an unanalyzable file.
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
    sys.stdout.write("0:GUARD-ERROR-UNPARSEABLE-PYTHON\n")
    sys.exit(0)

for i in range(n):
    sys.stdout.write("%d:%s\n" % (i + 1, "".join(grid[i])))
PY
}

strip_bash() {
  # Emit "lineno:codeonly" — blank full-line and inline `#` comments (heuristic;
  # heredocs are NOT parsed, which is correct: the injector's activation JS lives
  # inside a heredoc and IS the executable code we want to scan). The strip only
  # removes shell `#` comment LINES (the doctrine prose) so they cannot satisfy a
  # REQUIRED marker or trip a FORBIDDEN pattern.
  awk '
  {
    line = $0
    if (line ~ /^[[:space:]]*#/) { print NR ":"; next }
    sub(/[[:space:]]#.*$/, "", line)
    print NR ":" line
  }' "$1"
}

# Materialize the stripped (code-only) text of each file ONCE.
INJECT_CODE="$(strip_bash "$INJECT_SH")"
SEED_CODE="$(strip_python "$SEED_PY")"

# Fail closed if the Python strip could not tokenize the seed file.
if printf '%s' "$SEED_CODE" | grep -q 'GUARD-ERROR-UNPARSEABLE-PYTHON'; then
  red "  ✗ FAIL — seed-ghl-auth.py could not be tokenized (fail-closed); cannot verify R6."
  FAILS=$((FAILS + 1))
fi

# code_has <CODE_BLOB> <ERE>  → grep the code-only blob (case-sensitive).
code_has() { printf '%s' "$1" | grep -Eq "$2"; }
# code_has_i — case-insensitive variant.
code_has_i() { printf '%s' "$1" | grep -Eqi "$2"; }

# require <label> <human-name> <pass|fail>  — print + tally.
require_result() {
  local id="$1" desc="$2" ok="$3"
  if [ "$ok" = "ok" ]; then
    green "  ✓ PASS — $id present: $desc"
  else
    red   "  ✗ FAIL — $id ABSENT: $desc"
    FAILS=$((FAILS + 1))
  fi
}
forbid_result() {
  local id="$1" desc="$2" bad="$3"
  if [ "$bad" = "clean" ]; then
    green "  ✓ PASS — $id absent (clean): $desc"
  else
    red   "  ✗ FAIL — $id PRESENT (banned regression): $desc"
    FAILS=$((FAILS + 1))
  fi
}

echo "── REQUIRED resilience markers (must be present in code) ──"

# ── R1. Bounded RETRY LOOP w/ backoff+jitter around Layer-2 activation ────────
# The hardened activate uses a `for (let attempt = 1; attempt <= ACT_MAX_ATTEMPTS
# ...)` loop with a jitter() backoff. We assert ALL THREE signals in code:
#   - an attempt counter bounded by a MAX_ATTEMPTS constant (the bounded loop),
#   - the activation cap specifically (ACT_MAX_ATTEMPTS), and
#   - a jitter() backoff helper.
# Tolerant of spacing; anchored on the distinctive identifiers the hardening uses.
r1_loop=fail
if code_has "$INJECT_CODE" 'ACT_MAX_ATTEMPTS' \
   && code_has "$INJECT_CODE" 'for[[:space:]]*\([[:space:]]*(let|var)?[[:space:]]*attempt[[:space:]]*=' \
   && code_has "$INJECT_CODE" 'attempt[[:space:]]*<=?[[:space:]]*ACT_MAX_ATTEMPTS' \
   && code_has "$INJECT_CODE" 'jitter[[:space:]]*\('; then
  r1_loop=ok
fi
require_result "R1" "bounded retry loop w/ backoff+jitter around Layer-2 activate (ACT_MAX_ATTEMPTS + for-attempt + jitter())" "$r1_loop"

# ── R2. WARM-STORE READINESS gate before activating ───────────────────────────
# Before dispatching auth/get the hardened code POLLS for the SPA store+router to
# exist (the warm-store gate). Anchored on the readiness poll that yields $store
# and $router from #app.__vue_app__, plus the explicit no-store-router failure.
r2_warm=fail
if code_has "$INJECT_CODE" '__vue_app__' \
   && code_has "$INJECT_CODE" '\$store' \
   && code_has "$INJECT_CODE" '\$router' \
   && code_has "$INJECT_CODE" 'ACTIVATE-NO-STORE-ROUTER'; then
  r2_warm=ok
fi
require_result "R2" "warm-store readiness gate (poll #app.__vue_app__ for \$store+\$router before activating)" "$r2_warm"

# ── R3. Token-only COOKIE RE-ASSERT path (login/current re-fetch on wipe) ─────
# If cookie `a` is wiped, the hardened path RE-FETCHES /oauth/2/login/current with
# the same id_token (token-only) and RE-WRITES the cookies — never a UI login.
# We assert the login/current fetch + cookie-`a` readback both exist in code
# AND that the cookie is built from btoa(JSON.stringify(...)) (the An setter),
# i.e. the script can (re)assert cookie `a` from the token-only response.
r3_reassert=fail
if code_has "$INJECT_CODE" 'login_current|login/current|/oauth/2/login/current' \
   && code_has "$INJECT_CODE" 'btoa[[:space:]]*\([[:space:]]*JSON\.stringify' \
   && code_has "$INJECT_CODE" 'token-id|token_id' \
   && code_has "$INJECT_CODE" 'COOKIE-A-READBACK|getCookie|a_name'; then
  r3_reassert=ok
fi
require_result "R3" "token-only cookie re-assert (re-fetch login/current w/ token-id + rewrite cookie \`a\` via btoa(JSON.stringify))" "$r3_reassert"

# ── R4. POSITIVE LIVENESS CHECK (cookie `a` present AND decoded apiKey/user) ──
# Success must require the decoded cookie `a` to carry apiKey + userId — NOT just
# "no password box". We assert the activate path checks user.apiKey AND user.userId
# (the auth/get user shape) before declaring "activated", AND that the injector
# decodes cookie `a` and asserts decoded.apiKey.
r4_liveness=fail
if code_has "$INJECT_CODE" 'user\.apiKey' \
   && code_has "$INJECT_CODE" 'user\.userId' \
   && code_has "$INJECT_CODE" 'decoded\.apiKey' \
   && code_has "$INJECT_CODE" 'atob[[:space:]]*\('; then
  r4_liveness=ok
fi
require_result "R4" "positive liveness check (cookie \`a\` decodes to apiKey+userId; auth/get user.apiKey+user.userId asserted)" "$r4_liveness"

# ── R5. NO post-seed reload (the no-reload rule, present + honored) ───────────
# R5 is the REQUIRED counterpart of F3: the hardened code must use $router.push()
# for in-app activation (no full navigation) AND the seed/activate flow must not
# re-open the app root. Here we assert the POSITIVE marker (router.push present);
# the negative (no reload/assign/open-after-seed) is enforced by F3 below.
r5_noreload=fail
if code_has "$INJECT_CODE" 'router\.push'; then
  r5_noreload=ok
fi
require_result "R5" "in-app activation via \$router.push (no full-page nav; no-reload rule positive marker)" "$r5_noreload"

# ── R6. Layer-1 mint bounded retry (securetoken POST not single-shot) ─────────
# seed-ghl-auth.py's _exchange() must retry the securetoken POST with a bounded
# loop (not a single urlopen). We assert (in CODE only) a bounded retry construct
# around the urlopen: a max-attempts/retries identifier AND a loop, AND the
# securetoken urlopen call itself.
r6_mint=fail
if code_has "$SEED_CODE" 'urlopen' \
   && code_has_i "$SEED_CODE" '(max_attempts|max_retries|MINT_MAX|attempts|retries)' \
   && code_has "$SEED_CODE" '(for[[:space:]]+[A-Za-z_]+[[:space:]]+in[[:space:]]+range\(|while[[:space:]])' ; then
  r6_mint=ok
fi
require_result "R6" "Layer-1 mint bounded retry (securetoken urlopen wrapped in a bounded for/while attempt loop)" "$r6_mint"

echo ""
echo "── FORBIDDEN regressions (must be ABSENT from code) ──"

# ── F1. Single-shot activate (auth/get + router.push) with NO retry loop ──────
# This is structural: a single-shot activate has auth/get + router.push but NO
# bounded retry loop around them. We FLAG F1 only when the activate identifiers
# are present (auth/get + router.push) BUT the R1 bounded-loop signature is
# ABSENT. If R1 passed, F1 is by definition clean (the loop exists).
f1_singleshot=clean
if code_has "$INJECT_CODE" "auth/get" && code_has "$INJECT_CODE" 'router\.push'; then
  if [ "$r1_loop" != "ok" ]; then
    f1_singleshot=present
  fi
fi
forbid_result "F1" "single-shot activate (auth/get + router.push with NO surrounding bounded retry loop)" "$f1_singleshot"

# ── F2. hasPwd-only liveness (no cookie-`a`+apiKey assertion) ─────────────────
# A liveness/success determination based ONLY on hasPwd / "no password box".
# We FLAG F2 only when the code uses hasPwd/password-field presence AS the
# liveness signal BUT the positive cookie-`a`+apiKey assertion (R4) is ABSENT.
# (The hardened code legitimately reads hasPwd as ONE input — that's fine as long
# as the decoded-apiKey assertion also gates success, i.e. R4 holds.)
f2_haspwd=clean
if code_has "$INJECT_CODE" '(hasPwd|input\[type=?["'"'"']?password)'; then
  if [ "$r4_liveness" != "ok" ]; then
    f2_haspwd=present
  fi
fi
forbid_result "F2" "hasPwd-only liveness (success decided by no-password-box with NO cookie-\`a\`+apiKey assertion)" "$f2_haspwd"

# ── F3. Post-seed reload()/location.assign/goto to app root ───────────────────
# Any full-page reload / location.assign / location.href = / location.replace /
# an AB ... open|navigate AFTER the seed re-runs the boot IIFE and wipes the
# seeded session. Scanned in CODE only (the "NEVER reload" prose is in comments,
# already stripped). Anchored on the destructive calls.
f3_reload=clean
if code_has "$INJECT_CODE" '(location\.reload[[:space:]]*\(|\.reload[[:space:]]*\(|location\.assign[[:space:]]*\(|location\.replace[[:space:]]*\(|location\.href[[:space:]]*=|window\.location[[:space:]]*=)'; then
  f3_reload=present
fi
# An AB ... open / AB ... navigate AFTER the seed injection is also a reload.
# Split the bash code on the __GHL_SEED__ staging line; anything after must not
# re-open/navigate the page.
INJECT_POST_SEED="$(printf '%s\n' "$INJECT_CODE" | awk 'f{print} /__GHL_SEED__/{f=1}')"
if printf '%s' "$INJECT_POST_SEED" | grep -Eq '\bAB\b[^"]*\b(open|navigate)\b'; then
  f3_reload=present
fi
forbid_result "F3" "post-seed reload / location.assign / location.href= / AB open|navigate after seeding (wipes the seeded session)" "$f3_reload"

# ── F4. Hardcoded deep /location/<id>/ route literal in the activate path ─────
# The seed carries 16 locations and no single id; the working run pushed plain
# '/'. A literal /location/<20-ish-char-id>/ route in code is the banned dead-end.
# We match a quoted route literal that embeds /location/<alnum id>. We scan CODE
# only so a comment mentioning the route cannot trip it.
f4_deeproute=clean
if printf '%s' "$INJECT_CODE" | grep -Eq "['\"\`]/location/[A-Za-z0-9]{6,}"; then
  f4_deeproute=present
fi
forbid_result "F4" "hardcoded deep /location/<id>/ route literal in the activate path (seed has 16 locations; use '/')" "$f4_deeproute"

echo ""
if [ "$FAILS" -eq 0 ]; then
  green "guard-ghl-activation-resilience PASS — Layer-2 activation is resilient (warm-store gate + bounded jittered retry + token-only cookie re-assert + positive cookie-\`a\`+apiKey liveness; no single-shot / reload / hasPwd-only / deep-route regression)."
  exit 0
else
  red "guard-ghl-activation-resilience FAILED — $FAILS violation(s)."
  echo ""
  echo "REMEDY (apply the hardening to 06-ghl-install-pages/tools/inject-ghl-auth.sh + seed-ghl-auth.py):"
  echo "  R1  Wrap the Layer-2 activate in a bounded retry loop with backoff+jitter"
  echo '      (e.g. ACT_MAX_ATTEMPTS + a for(attempt<=ACT_MAX_ATTEMPTS) loop'
  echo '      + a jitter() backoff). NEVER a single auth/get + router.push.'
  echo "  R2  Add a warm-store readiness gate: poll #app.__vue_app__ for \$store+\$router"
  echo "      (and cookie \`a\` readable) BEFORE activating; throw ACTIVATE-NO-STORE-ROUTER"
  echo "      if it never mounts."
  echo "  R3  On a cookie-\`a\` wipe, RE-FETCH /oauth/2/login/current with the same"
  echo "      token-id (token-only) and RE-WRITE the cookies via btoa(JSON.stringify(...))."
  echo "  R4  Gate success on the DECODED cookie \`a\` carrying apiKey + userId (and"
  echo "      auth/get's user.apiKey+user.userId) — NOT merely 'no password box visible'."
  echo "  R5  Activate via \$router.push() in-app — NO full-page navigation."
  echo "  R6  Wrap the securetoken POST (urlopen) in seed-ghl-auth.py in a bounded"
  echo "      attempt loop (not a single-shot urlopen)."
  echo ""
  echo "  BANNED (remove if present):"
  echo "  F1  single-shot activate with no retry loop."
  echo "  F2  liveness decided ONLY by hasPwd / no-password-box."
  echo "  F3  post-seed reload()/location.assign/location.href=/AB open|navigate."
  echo "  F4  a hardcoded /location/<id>/ route literal in the activate path (use '/')."
  echo ""
  echo "  Companion guard: scripts/guard-ghl-token-only.sh enforces the auth MODEL"
  echo "  (refresh-token seed ONLY; no auto UI-login/password/2FA). The two sit together."
  exit 1
fi
