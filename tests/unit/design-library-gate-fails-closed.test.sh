#!/usr/bin/env bash
# tests/unit/design-library-gate-fails-closed.test.sh
#
# Locks two fail-open branches in 45-design-intelligence-library/qc-design-intelligence-library.sh
# (FINDINGS T1-02 and T0-06). Before the fix BOTH branches fell through to the
# unconditional "All checks passed" banner and exit 0.
#
#   T1-02 — client identity material detected in the library was printed as a
#           WARNING and the run was then certified "Ready for installation on
#           boxes". That is the mechanism by which one client's material reaches
#           another client's box.
#
#   T0-06 — an unavailable python3 was treated as a SKIP, so the gate reported
#           success having exercised none of the coded gates it exists to test
#           (route-check, prompt-caps, and the consent gate that refuses a
#           minor's identity material).
#
# ANTI-FALSE-POSITIVE CONTROLS (a "fix" that simply makes everything fail must
# not pass this test):
#   * Case 2 and Case 3 assert an INSTALLED box holding the client data it is
#     supposed to hold still PASSES. Case 3 reproduces the measured box shape:
#     6 of 30 reachable boxes run this skill from a git clone of this repository
#     rooted at <home>/.openclaw/skills, so the gate must not key off "am I in a
#     git checkout" — it keys off whether the path is TRACKED.
#   * Case 4 asserts the repository's own clean state still PASSES.
#   * Case 6 asserts a box WITH python3 is unaffected.
#
# Hermetic: temp dirs, local git only, no network, no fleet box is touched.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL_SRC="$REPO_ROOT/45-design-intelligence-library"
GATE_REL="qc-design-intelligence-library.sh"

PASS=0; FAIL=0
ok()   { echo "  ok   — $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL — $1"; FAIL=$((FAIL+1)); }

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

# Planted client data. Synthetic only — no real client name appears anywhere in
# this repository's fixtures.
PLANTED_CARD="library/single-image-designs/SI-999_synthetic-fixture.md"
PLANTED_DIR="library/personal-photo-shoot/synthetic-fixture-identity"

# stage <name> -> echoes a fresh copy of the skill folder
stage() {
  local d="$TMPROOT/$1"
  rm -rf "$d"; mkdir -p "$d"
  cp -R "$SKILL_SRC/." "$d/"
  rm -rf "$d/.git"
  echo "$d"
}

plant() { # plant <skilldir>
  local d="$1"
  printf '# SI-999 synthetic fixture style card\n' > "$d/$PLANTED_CARD"
  mkdir -p "$d/$PLANTED_DIR"
  printf '# IDENTITY — synthetic fixture\n- Consent: granted\n' > "$d/$PLANTED_DIR/IDENTITY.md"
}

git_init_commit_all() { # git_init_commit_all <dir>
  local d="$1"
  git -C "$d" init -q
  git -C "$d" config user.email "fixture@localhost"
  git -C "$d" config user.name "fixture"
  git -C "$d" add -A
  git -C "$d" commit -q -m "fixture"
}

run_gate() { # run_gate <skilldir> [env-prefixed PATH]  -> sets RC and OUT
  local d="$1"
  OUT="$(cd "$d" && bash "$d/$GATE_REL" 2>&1)"; RC=$?
}

echo "=== design-library gate fails closed (T1-02, T0-06) ==="

# ---------------------------------------------------------------------------
# Case 1 (T1-02) — REPOSITORY CONTEXT: client data COMMITTED to version control
#                  must be a HARD FAILURE that lists the offending paths.
# ---------------------------------------------------------------------------
D="$(stage repo-committed)"
plant "$D"
git_init_commit_all "$D"
run_gate "$D"
if [[ $RC -ne 0 ]]; then
  ok "case 1: committed client data exits non-zero (rc=$RC)"
else
  bad "case 1: committed client data exited 0 — the gate is fail-open"
fi
case "$OUT" in
  *"SI-999_synthetic-fixture.md"*) ok "case 1: the offending style card is listed" ;;
  *) bad "case 1: the offending style card was not listed in the output" ;;
esac
case "$OUT" in
  *"synthetic-fixture-identity"*) ok "case 1: the offending identity folder is listed" ;;
  *) bad "case 1: the offending identity folder was not listed in the output" ;;
esac
case "$OUT" in
  *"All checks passed"*) bad "case 1: the run was still certified 'All checks passed'" ;;
  *) ok "case 1: the run was NOT certified 'All checks passed'" ;;
esac

# ---------------------------------------------------------------------------
# Case 2 (anti-false-positive) — INSTALLED CONTEXT, no git at all: a box holding
#                  its own style cards and identity folders must PASS.
# ---------------------------------------------------------------------------
D="$(stage installed-nogit)"
plant "$D"
run_gate "$D"
if [[ $RC -eq 0 ]]; then
  ok "case 2: installed box (no git) with its own client data PASSES (rc=0)"
else
  bad "case 2: installed box with expected client data was REJECTED (rc=$RC) — false-fail"
fi
case "$OUT" in
  *"NOT committed"*) ok "case 2: the data is reported as present-but-not-committed" ;;
  *) bad "case 2: the present-but-not-committed report is missing" ;;
esac

# ---------------------------------------------------------------------------
# Case 3 (anti-false-positive, THE measured box shape) — INSTALLED CONTEXT that
#                  IS a git checkout of this repository: skill files tracked,
#                  box-authored client data UNTRACKED. Must PASS.
#                  Measured read-only 2026-07-21: 6 of 30 reachable boxes are
#                  exactly this shape.
# ---------------------------------------------------------------------------
D="$(stage installed-inside-clone)"
git_init_commit_all "$D"          # commit the skill WITHOUT client data
plant "$D"                        # box then writes its own cards — untracked
run_gate "$D"
if [[ $RC -eq 0 ]]; then
  ok "case 3: installed box running from a clone, untracked client data, PASSES (rc=0)"
else
  bad "case 3: a box running from a clone was REJECTED (rc=$RC) — this is the false-fail the scoping exists to prevent"
fi
# Prove the fixture is genuinely a checkout, so case 3 is not passing by accident.
if git -C "$D" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  ok "case 3: fixture is genuinely inside a git work tree"
else
  bad "case 3: fixture is not a git work tree — the case proves nothing"
fi
if [[ -n "$(git -C "$D" ls-files -- "$D/$GATE_REL" 2>/dev/null)" ]]; then
  ok "case 3: the gate script itself is tracked in that checkout (matches the boxes)"
else
  bad "case 3: the gate script is not tracked — the fixture does not match the measured boxes"
fi

# ---------------------------------------------------------------------------
# Case 4 (anti-false-positive) — the repository's own clean state must PASS.
# ---------------------------------------------------------------------------
D="$(stage repo-clean)"
git_init_commit_all "$D"
run_gate "$D"
if [[ $RC -eq 0 ]]; then
  ok "case 4: clean repository state PASSES (rc=0)"
else
  bad "case 4: clean repository state was rejected (rc=$RC)"
fi

# ---------------------------------------------------------------------------
# Case 5 (T0-06) — python3 UNAVAILABLE must be a hard failure, never a skip.
#                  PATH is rebuilt from symlinks so every other tool the gate
#                  needs is present and ONLY python3 is missing.
# ---------------------------------------------------------------------------
D="$(stage nopython)"
SANDBIN="$TMPROOT/sandbin"; mkdir -p "$SANDBIN"
for b in bash sh git find grep mktemp shasum awk sed cat cp rm mkdir wc tr head basename dirname sort uname stat ls; do
  p="$(command -v "$b" 2>/dev/null)" || continue
  ln -sf "$p" "$SANDBIN/$b"
done
if PATH="$SANDBIN" command -v python3 >/dev/null 2>&1; then
  bad "case 5: python3 is still reachable in the sandbox PATH — the case proves nothing"
else
  ok "case 5: sandbox PATH genuinely has no python3"
fi
OUT="$(cd "$D" && PATH="$SANDBIN" bash "$D/$GATE_REL" 2>&1)"; RC=$?
if [[ $RC -ne 0 ]]; then
  ok "case 5: missing python3 exits non-zero (rc=$RC)"
else
  bad "case 5: missing python3 exited 0 — the gate certified PASS having tested nothing"
fi
case "$OUT" in
  *"skipping gate self-tests"*) bad "case 5: the gate still SKIPS its self-tests" ;;
  *) ok "case 5: the gate no longer skips its self-tests" ;;
esac
case "$OUT" in
  *"python3 unavailable"*) ok "case 5: the failure names the missing runtime" ;;
  *) bad "case 5: the failure does not name the missing runtime" ;;
esac
case "$OUT" in
  *"REQUIRED prerequisite"*) ok "case 5: the runtime is declared a required prerequisite" ;;
  *) bad "case 5: the runtime is not declared a prerequisite in the failure text" ;;
esac
case "$OUT" in
  *"All checks passed"*) bad "case 5: the run was still certified 'All checks passed'" ;;
  *) ok "case 5: the run was NOT certified 'All checks passed'" ;;
esac

# ---------------------------------------------------------------------------
# Case 6 (anti-false-positive) — with python3 present the gate behaves normally
#                  and actually RUNS the validator self-tests.
# ---------------------------------------------------------------------------
D="$(stage withpython)"
run_gate "$D"
if [[ $RC -eq 0 ]]; then
  ok "case 6: python3 present — gate passes (rc=0)"
else
  bad "case 6: python3 present but the gate failed (rc=$RC)"
fi
case "$OUT" in
  *"consent-check MINOR -> hard no"*) ok "case 6: the consent gate self-test really executed" ;;
  *) bad "case 6: the consent gate self-test did not execute" ;;
esac

# ---------------------------------------------------------------------------
# Case 7 — python3 is declared a machine-readable prerequisite of the skill.
# ---------------------------------------------------------------------------
if python3 - "$SKILL_SRC/PREREQS.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
hit = [p for p in data.get("prerequisites", [])
       if p.get("type") == "binary" and p.get("check", {}).get("binary") == "python3"]
sys.exit(0 if hit and hit[0].get("severity") == "required" and hit[0].get("satisfy", "").strip() else 1)
PY
then
  ok "case 7: PREREQS.json declares python3 as a required binary with a satisfy step"
else
  bad "case 7: PREREQS.json does not declare python3 as a required binary prerequisite"
fi

echo ""
echo "=== $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] || exit 1
exit 0
