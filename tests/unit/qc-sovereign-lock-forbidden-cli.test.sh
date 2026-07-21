#!/usr/bin/env bash
# tests/unit/qc-sovereign-lock-forbidden-cli.test.sh
#
# REGRESSION GUARD — Skill 10 (GitHub) and Skill 08 (Vercel) install QC:
# a gate must never hard-require a command-line tool its own skill forbids.
#
# THE FALSE FAIL THIS CLOSES:
#
#   10-github-setup/SKILL.md carries an "API-ONLY EXECUTION LOCK (SOVEREIGN)"
#   reading "do NOT use GitHub CLI (gh) for setup/auth", and
#   08-vercel-setup/SKILL.md carries "do NOT use the Vercel CLI for setup/auth.
#   Use browser-based account/token creation and API-token verification only."
#
#   Both install gates nevertheless hard-asserted the forbidden binary:
#       qc-github-setup.sh: assert "gh CLI installed"  "command -v gh"
#                           assert "gh authenticated"  "gh auth status ..."
#       qc-vercel-setup.sh: assert "vercel CLI installed" "command -v vercel"
#
#   A box installed EXACTLY as each skill prescribes therefore failed its own
#   gate permanently and recorded a non-zero QC exit into the wave gate. The
#   remedy an operator reaches for — install the forbidden tool — defeats the
#   sovereign lock the skill exists to enforce.
#
# WHAT THIS FILE PROVES (hermetic: fixture HOME + a PATH sandbox in a tempdir;
# no network, no box state, nothing outside the checkout is read or written):
#
#   T1  Skill 10, correct install, gh ABSENT from PATH        -> exit 0
#   T2  Skill 10, skill folder missing                        -> exit 1  (still fails on a real defect)
#   T3  Skill 10, git identity unconfigured                   -> exit 1  (still fails on a real defect)
#   T4  Skill 10, gh is not hard-asserted anywhere in the gate (static anti-regression)
#   T5  Skill 08, correct install, vercel ABSENT from PATH    -> exit 0
#   T6  Skill 08, VERCEL_TOKEN unset                          -> exit 1  (still fails on a real defect)
#   T7  Skill 08, jq missing from PATH                        -> exit 1  (still fails on a real defect)
#   T8  Skill 08, vercel is not hard-asserted in the gate      (static anti-regression)
#
# MUTATION: reinstating either forbidden-tool assert turns T1 (or T5) red,
# because the PATH sandbox below contains no gh and no vercel by construction.
#
# Exit 0 = pass. Exit 1 = the false fail regressed, or a gate stopped failing on
# a genuine defect.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GH_SKILL="$REPO_ROOT/10-github-setup"
VC_SKILL="$REPO_ROOT/08-vercel-setup"
GH_QC="$GH_SKILL/qc-github-setup.sh"
VC_QC="$VC_SKILL/qc-vercel-setup.sh"

PASSN=0
FAILN=0
pass() { echo "  PASS: $1"; PASSN=$((PASSN+1)); }
fail() { echo "  FAIL: $1"; FAILN=$((FAILN+1)); }

echo "=== qc-sovereign-lock-forbidden-cli.test.sh ==="
echo ""

for f in "$GH_QC" "$VC_QC" "$GH_SKILL/SKILL.md" "$VC_SKILL/SKILL.md"; do
  if [ ! -f "$f" ]; then echo "  FAIL: $f not found"; exit 1; fi
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ── PATH sandbox ────────────────────────────────────────────────────────────
# Only the tools a correctly-installed box is documented to have. gh and vercel
# are absent BY CONSTRUCTION, so a reinstated forbidden-tool assert cannot pass
# here even on a developer machine that happens to have them installed.
SANDBOX_BIN="$TMP/bin"
mkdir -p "$SANDBOX_BIN"
link_tool() {
  local name="$1" src
  src="$(command -v "$name" 2>/dev/null || true)"
  if [ -z "$src" ]; then
    echo "  FAIL: prerequisite '$name' is not on this machine's PATH; cannot run hermetically" >&2
    exit 1
  fi
  ln -sf "$src" "$SANDBOX_BIN/$name"
}
for t in bash dirname git grep sed node npm jq; do link_tool "$t"; done

# Stubbed curl: the Vercel gate's live token probe is a warn_only check and this
# suite does not grade it. The stub returns nothing, which makes that warning
# FIRE rather than pass — the conservative direction. No network is used.
cat >"$SANDBOX_BIN/curl" <<'STUB'
#!/usr/bin/env bash
exit 1
STUB
chmod +x "$SANDBOX_BIN/curl"

if [ -e "$SANDBOX_BIN/gh" ] || [ -e "$SANDBOX_BIN/vercel" ]; then
  echo "  FAIL: sandbox PATH is contaminated with a forbidden CLI" >&2
  exit 1
fi

strip_ansi() { sed -e 's/\x1b\[[0-9;]*m//g'; }

# ── fixture box ─────────────────────────────────────────────────────────────
# A box installed exactly as each SKILL.md prescribes: the skill folders are
# present under ~/.openclaw/skills, git carries a global identity, and the
# credentials live in the environment. No gh, no vercel.
make_box() {
  local box="$1"
  mkdir -p "$box/.openclaw/skills"
  cp -R "$GH_SKILL" "$box/.openclaw/skills/10-github-setup"
  cp -R "$VC_SKILL" "$box/.openclaw/skills/08-vercel-setup"
  cp "$REPO_ROOT/lib-shared.sh" "$box/.openclaw/skills/lib-shared.sh"
  printf '[user]\n\tname = Operator\n\temail = operator@example.invalid\n' >"$box/.gitconfig"
}

run_gate() {
  # run_gate <box> <skill-dir-name> <script-name> [extra env assignments...]
  local box="$1" skill="$2" script="$3"; shift 3
  env -i \
    HOME="$box" \
    PATH="$SANDBOX_BIN" \
    "$@" \
    bash "$box/.openclaw/skills/$skill/$script" 2>&1 | strip_ansi
  return "${PIPESTATUS[0]}"
}

# ── T1: Skill 10 on a correctly-installed box, no gh ────────────────────────
BOX1="$TMP/box1"; make_box "$BOX1"
OUT1="$(run_gate "$BOX1" 10-github-setup qc-github-setup.sh)"; RC1=$?
if [ "$RC1" -eq 0 ]; then
  pass "T1 Skill 10 gate exits 0 on a box installed exactly as SKILL.md prescribes (gh absent)"
else
  fail "T1 Skill 10 gate exited $RC1 on a correct install with gh absent — the false fail is back"
  printf '%s\n' "$OUT1" | sed 's/^/      /'
fi

# ── T2: Skill 10 still fails on a real defect (skill folder missing) ────────
BOX2="$TMP/box2"; make_box "$BOX2"
# Run the copy from box1 but point HOME at a box whose skills dir lacks Skill 10.
rm -rf "$BOX2/.openclaw/skills/10-github-setup"
OUT2="$(env -i HOME="$BOX2" PATH="$SANDBOX_BIN" \
        bash "$BOX1/.openclaw/skills/10-github-setup/qc-github-setup.sh" 2>&1 | strip_ansi)"
RC2="${PIPESTATUS[0]}"
if [ "$RC2" -eq 1 ] && printf '%s' "$OUT2" | grep -q 'FAIL — Skill 10 folder present'; then
  pass "T2 Skill 10 gate still exits 1, naming 'Skill 10 folder present', when the skill folder is absent"
else
  fail "T2 Skill 10 gate did not fail on the absent skill folder (rc=$RC2) — the gate no longer catches a real defect"
  printf '%s\n' "$OUT2" | sed 's/^/      /'
fi

# ── T3: Skill 10 still fails on a real defect (no git identity) ─────────────
BOX3="$TMP/box3"; make_box "$BOX3"
rm -f "$BOX3/.gitconfig"
OUT3="$(run_gate "$BOX3" 10-github-setup qc-github-setup.sh)"; RC3=$?
if [ "$RC3" -eq 1 ] && printf '%s' "$OUT3" | grep -q 'FAIL — git user.email configured'; then
  pass "T3 Skill 10 gate still exits 1, naming 'git user.email configured', when git has no global identity"
else
  fail "T3 Skill 10 gate did not fail on the missing git identity (rc=$RC3) — the gate no longer catches a real defect"
  printf '%s\n' "$OUT3" | sed 's/^/      /'
fi

# ── T4: static anti-regression, Skill 10 ────────────────────────────────────
if grep -qE '^[[:space:]]*assert .*command -v gh' "$GH_QC" \
   || grep -qE '^[[:space:]]*assert .*gh auth status' "$GH_QC"; then
  fail "T4 qc-github-setup.sh hard-asserts the GitHub CLI again, against its own SOVEREIGN lock"
else
  pass "T4 qc-github-setup.sh carries no hard assertion on the forbidden GitHub CLI"
fi

# ── T5: Skill 08 on a correctly-installed box, no vercel ────────────────────
BOX5="$TMP/box5"; make_box "$BOX5"
OUT5="$(run_gate "$BOX5" 08-vercel-setup qc-vercel-setup.sh VERCEL_TOKEN=fixture-token-not-a-credential)"; RC5=$?
if [ "$RC5" -eq 0 ]; then
  pass "T5 Skill 08 gate exits 0 on a box installed exactly as SKILL.md prescribes (vercel absent)"
else
  fail "T5 Skill 08 gate exited $RC5 on a correct install with vercel absent — the false fail is back"
  printf '%s\n' "$OUT5" | sed 's/^/      /'
fi

# ── T6: Skill 08 still fails on a real defect (no token) ────────────────────
BOX6="$TMP/box6"; make_box "$BOX6"
OUT6="$(run_gate "$BOX6" 08-vercel-setup qc-vercel-setup.sh)"; RC6=$?
if [ "$RC6" -eq 1 ] && printf '%s' "$OUT6" | grep -q 'FAIL — VERCEL_TOKEN set'; then
  pass "T6 Skill 08 gate still exits 1, naming 'VERCEL_TOKEN set', when the token is unset"
else
  fail "T6 Skill 08 gate did not fail on the missing token (rc=$RC6) — the gate no longer catches a real defect"
  printf '%s\n' "$OUT6" | sed 's/^/      /'
fi

# ── T7: Skill 08 still fails on a real defect (jq missing) ──────────────────
NOJQ_BIN="$TMP/bin-nojq"
mkdir -p "$NOJQ_BIN"
for t in bash dirname git grep sed node npm curl; do
  [ -e "$SANDBOX_BIN/$t" ] && cp -R "$SANDBOX_BIN/$t" "$NOJQ_BIN/$t"
done
BOX7="$TMP/box7"; make_box "$BOX7"
OUT7="$(env -i HOME="$BOX7" PATH="$NOJQ_BIN" VERCEL_TOKEN=fixture-token-not-a-credential \
        bash "$BOX7/.openclaw/skills/08-vercel-setup/qc-vercel-setup.sh" 2>&1 | strip_ansi)"
RC7="${PIPESTATUS[0]}"
if [ "$RC7" -eq 1 ] && printf '%s' "$OUT7" | grep -q 'FAIL — jq installed'; then
  pass "T7 Skill 08 gate still exits 1, naming 'jq installed', when a genuinely required tool is absent"
else
  fail "T7 Skill 08 gate did not fail on the absent jq (rc=$RC7) — the gate no longer catches a real defect"
  printf '%s\n' "$OUT7" | sed 's/^/      /'
fi

# ── T8: static anti-regression, Skill 08 ────────────────────────────────────
if grep -qE '^[[:space:]]*assert .*command -v vercel' "$VC_QC"; then
  fail "T8 qc-vercel-setup.sh hard-asserts the Vercel CLI again, against its own SOVEREIGN lock"
else
  pass "T8 qc-vercel-setup.sh carries no hard assertion on the forbidden Vercel CLI"
fi

echo ""
echo "=== $PASSN passed, $FAILN failed ==="
[ "$FAILN" -eq 0 ] || exit 1
exit 0
