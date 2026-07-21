#!/usr/bin/env bash
# ============================================================================
# tests/unit/onboarding-state-fail-closed-vacuity.sh
# ============================================================================
# ANTI-VACUITY GATE for onboarding-state-fail-closed.test.sh.
#
# "A test that passes both ways has tested nothing." This script reconstructs
# the four pre-fix behaviours in a scratch copy of the tree and asserts the
# suite REJECTS it. If the suite ever stops detecting the defects it was written
# for — because a refactor moved an anchor, or someone softened an assertion —
# this fails, loudly, instead of the suite quietly becoming decorative.
#
# Reconstruction rather than a pinned parent SHA: this repo takes many merges a
# day from parallel agents, and a pinned ancestor stops resolving behind a
# squash, a rebase or a shallow checkout. The four edits below are the exact
# inverse of the fix, and each one asserts it actually matched something — a
# reconstruction that silently no-ops would recreate the vacuity it exists to
# prevent.
#
# Hermetic: copies the three files under test into a temp dir and edits the
# copies. Never touches the working tree, and deliberately does NOT read `git
# archive HEAD` — that would measure the last commit rather than the code
# actually being shipped, which is its own way of testing nothing.
# ============================================================================
set -uo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SUITE="$REPO_ROOT/tests/unit/onboarding-state-fail-closed.test.sh"
[ -f "$SUITE" ] || { echo "FATAL: missing $SUITE"; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/scripts"
cp "$REPO_ROOT/install.sh"                 "$WORK/install.sh"              || exit 2
cp "$REPO_ROOT/lib-onboarding-state.sh"    "$WORK/lib-onboarding-state.sh" || exit 2
cp "$REPO_ROOT/scripts/onboarding-state.sh" "$WORK/scripts/onboarding-state.sh" || exit 2

echo "--- reconstructing the four pre-fix defects in $WORK ---"

# ── ONB-STATE-002a + 002b: the two no-op stubs and their call sites ─────────
python3 - "$WORK/install.sh" <<'PY' || exit 2
import re, sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()


def sub(pattern, repl, s, what):
    out, n = re.subn(pattern, repl, s, count=1, flags=re.M)
    if n != 1:
        sys.exit("reconstruction did not match (%s) — the anchor moved" % what)
    print("  re-broke:", what)
    return out


src = sub(r'^command -v oc_state_seed .*$',
          'command -v oc_state_seed          >/dev/null 2>&1 || oc_state_seed()          { :; }',
          src, "002a oc_state_seed no-op stub")

src = sub(r'^if \[ "\$\{_oc_state_lib_loaded:-0\}" = "1" \]; then$',
          'if command -v oc_state_seed >/dev/null 2>&1; then',
          src, "002a command -v dispatch")

src = sub(r'^command -v install_onboarding_resume_cron .*$',
          'command -v install_onboarding_resume_cron >/dev/null 2>&1 || install_onboarding_resume_cron() { :; }',
          src, "002b resume-cron no-op stub")

src = sub(r'^if ! install_onboarding_resume_cron; then\n.*\nfi$',
          'install_onboarding_resume_cron',
          src, "002b bare Step 13b call site")

open(path, "w", encoding="utf-8").write(src)
PY

# ── ONB-STATE-002c: drop the else that fails closed on a missing CLI ────────
python3 - "$WORK/scripts/onboarding-state.sh" <<'PY' || exit 2
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
needle = '  else\n    reasons="${reasons}skills-info:openclaw-cli-not-on-path; "\n  fi\n'
if src.count(needle) != 1:
    sys.exit("reconstruction did not match (002c fail-closed else) — the anchor moved")
open(path, "w", encoding="utf-8").write(src.replace(needle, '  fi\n', 1))
print("  re-broke: 002c registration check has no else")
PY

# ── ONB-STATE-002d: restore `2>/dev/null || true` on both state writes ──────
python3 - "$WORK/lib-onboarding-state.sh" <<'PY' || exit 2
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
needle = "  NOW=\"$(oc_state_now)\" python3 - <<'PYEOF'\n"
n = src.count(needle)
if n != 2:
    sys.exit("expected exactly 2 unswallowed state-write heredocs, found %d" % n)
src = src.replace(needle, "  NOW=\"$(oc_state_now)\" python3 - <<'PYEOF' 2>/dev/null || true\n")
open(path, "w", encoding="utf-8").write(src)
print("  re-broke: 002d oc_state_seed + oc_state_set swallow their writes")
PY

for f in install.sh lib-onboarding-state.sh scripts/onboarding-state.sh; do
  bash -n "$WORK/$f" || { echo "FATAL: reconstructed $f is not valid bash"; exit 2; }
done

echo "--- running the suite against the reconstructed pre-fix tree ---"
REPO_ROOT="$WORK" bash "$SUITE"
rc=$?

echo ""
if [ "$rc" -eq 0 ]; then
  echo "VACUITY FAIL: the suite PASSED a tree carrying all four defects."
  echo "              It proves nothing. Fix the suite, not this gate."
  exit 1
fi
echo "VACUITY OK: the suite rejects the pre-fix tree (rc $rc)."
exit 0
