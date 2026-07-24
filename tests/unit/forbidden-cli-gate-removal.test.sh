#!/usr/bin/env bash
# ============================================================
#  forbidden-cli-gate-removal.test.sh — U102
#
#  Two install gates (10-github-setup, 08-vercel-setup) used to hard-require
#  the very CLI their own SKILL.md sovereign lock forbids (gh, vercel). A box
#  installed exactly as documented failed its own gate permanently.
#
#  This test proves the forbidden-CLI assertions are GONE and replaced with a
#  "SKIPPED BY DESIGN" note, and that a correct install (no forbidden CLI)
#  passes the gate.
#
#  EXIT CODES:
#    0  — all tests passed
#    1  — one or more tests failed
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FAIL_COUNT=0
PASS_COUNT=0

_pass() { echo "  PASS: $1"; (( PASS_COUNT++ )) || true; }
_fail() { echo "  FAIL: $1" >&2; (( FAIL_COUNT++ )) || true; }
_section() { echo ""; echo "=== $1 ==="; }

# ─── Hermetic environment ────────────────────────────────────────────────────
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

# Fake binaries so tool-presence assertions pass (git, node, npm, jq, curl).
# git responds to config queries; everything else exits 0.
mkdir -p "$TMPDIR_TEST/bin"
for tool in git node npm jq curl; do
  cat > "$TMPDIR_TEST/bin/$tool" <<'FAKE'
#!/usr/bin/env bash
if [ "${1:-}" = "config" ] && [ "${3:-}" = "user.email" ]; then echo "test@example.com"; exit 0; fi
if [ "${1:-}" = "config" ] && [ "${3:-}" = "user.name" ]; then echo "Test User"; exit 0; fi
exit 0
FAKE
  chmod +x "$TMPDIR_TEST/bin/$tool"
done

export HOME="$TMPDIR_TEST/home"
mkdir -p "$HOME"
export PATH="$TMPDIR_TEST/bin:$PATH"
export SECRETS_ENV="$TMPDIR_TEST/nonexistent.env"
export WORKSPACE="$TMPDIR_TEST/workspace"
mkdir -p "$WORKSPACE"

# The gates source lib-shared.sh, whose resolve_platform_paths() sets
# SKILLS_DIR_DEFAULT to $HOME/.openclaw/skills on Mac. Create the skill
# folders there so the "Skill NN folder present" assertions pass.
mkdir -p "$HOME/.openclaw/skills/10-github-setup" "$HOME/.openclaw/skills/08-vercel-setup"

# ─── Test 1: GitHub gate skips gh CLI by design ──────────────────────────────
_section "Test 1 — GitHub gate: gh CLI is SKIPPED BY DESIGN, not FAIL"
GITHUB_OUT="$(bash "$REPO_ROOT/10-github-setup/qc-github-setup.sh" 2>&1 || true)"
if echo "$GITHUB_OUT" | grep -q "SKIPPED BY DESIGN.*GitHub CLI"; then
  _pass "GitHub gate prints SKIPPED BY DESIGN for gh CLI"
else
  _fail "GitHub gate does NOT print SKIPPED BY DESIGN for gh CLI"
fi
if echo "$GITHUB_OUT" | grep -qE "FAIL.*(GitHub CLI|gh)"; then
  _fail "GitHub gate FAILs on gh CLI (forbidden assertion still present)"
else
  _pass "GitHub gate does not FAIL on gh CLI"
fi

# ─── Test 2: Vercel gate skips vercel CLI by design ──────────────────────────
_section "Test 2 — Vercel gate: vercel CLI is SKIPPED BY DESIGN, not FAIL"
VERCEL_OUT="$(bash "$REPO_ROOT/08-vercel-setup/qc-vercel-setup.sh" 2>&1 || true)"
if echo "$VERCEL_OUT" | grep -q "SKIPPED BY DESIGN.*Vercel CLI"; then
  _pass "Vercel gate prints SKIPPED BY DESIGN for vercel CLI"
else
  _fail "Vercel gate does NOT print SKIPPED BY DESIGN for vercel CLI"
fi
if echo "$VERCEL_OUT" | grep -qE "FAIL.*(Vercel CLI|vercel)"; then
  _fail "Vercel gate FAILs on vercel CLI (forbidden assertion still present)"
else
  _pass "Vercel gate does not FAIL on vercel CLI"
fi

# ─── Test 3: Gates exit 0 on a correct install (no forbidden CLI) ────────────
_section "Test 3 — Gates exit 0 when forbidden CLI is absent"
if bash "$REPO_ROOT/10-github-setup/qc-github-setup.sh" >/dev/null 2>&1; then
  _pass "GitHub gate exits 0 without gh installed"
else
  _fail "GitHub gate exits non-zero without gh installed"
fi
# Vercel gate needs VERCEL_TOKEN to pass the hard assert; set a fake one
if VERCEL_TOKEN="fake-token" bash "$REPO_ROOT/08-vercel-setup/qc-vercel-setup.sh" >/dev/null 2>&1; then
  _pass "Vercel gate exits 0 without vercel CLI installed (with token)"
else
  _fail "Vercel gate exits non-zero without vercel CLI installed"
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "═══ Result: $PASS_COUNT passed | $FAIL_COUNT failed ═══"
[ $FAIL_COUNT -gt 0 ] && exit 1 || exit 0
