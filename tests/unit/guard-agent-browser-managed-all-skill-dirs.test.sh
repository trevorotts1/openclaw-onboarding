#!/usr/bin/env bash
# tests/unit/guard-agent-browser-managed-all-skill-dirs.test.sh — P3-04 (c)1
# AUTO-DISCOVERY negative-fixture proof.
#
# THE RESIDUAL (Skill-6 spec §(b), 2026-07-11): scripts/guard-agent-browser-
# managed.sh's MANAGED-ONLY (1) and HEADLESS-ONLY (5) checks scanned only THREE
# hand-enumerated roots (06-ghl-install-pages/, 41-build-with-ai-playbook/,
# 03-agent-browser/) — any OTHER skill directory (44-convert-and-flow-operator/
# among them, the exact root P3-08 needs widened for its Tier-4 workflow-build
# backstop) could plant an unmanaged `agent-browser open|eval|...` spawn and
# pass this guard SILENTLY.
#
# THE FIX: MANAGED_SCAN_ROOTS is no longer a fixed list — it is AUTO-DISCOVERED
# from every top-level `NN-*/` skill directory (_discover_skill_dirs). This test
# proves BOTH halves of that claim:
#   (A) FAIL-FIRST — the guard AS IT WAS immediately before this fix landed
#       (PINNED to commit 49b88cd5832a99ff7885036d7e9dbc78c43b9a2d, v19.58.0's
#       hand-enumerated 3-root array; read via `git show`, never hand-retyped
#       — see the PRE_FIX_REF default below for why this is a fixed SHA and
#       NOT `origin/main`) is blind to a spawn planted in
#       44-convert-and-flow-operator/ AND in a brand-new directory that did
#       not exist when the guard was written — reproducing the bug.
#   (B) the CURRENT (fixed) guard catches BOTH, by construction, with ZERO
#       further edits to the guard for either directory — proving true
#       auto-discovery, not a second hand-added entry.
#
# Runs the REAL guard scripts (old + current) against a MINIMAL synthetic
# --repo-root — hermetic, fast, independent of unrelated drift elsewhere in the
# real tree.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CURRENT_GUARD="$REPO_ROOT/scripts/guard-agent-browser-managed.sh"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== guard-agent-browser-managed-all-skill-dirs.test.sh (P3-04 c1) ==="
[[ -f "$CURRENT_GUARD" ]] || { echo "FAIL: guard not found: $CURRENT_GUARD"; exit 1; }

TMP_TREE="$(mktemp -d)"
PRE_FIX_GUARD="$(mktemp)"
trap 'rm -rf "$TMP_TREE" "$PRE_FIX_GUARD"' EXIT

# ── the pre-fix guard, read from git history (never hand-retyped — 2.1 law:
# "run once against the origin/main copy") ────────────────────────────────────
# PINNED, not a moving ref: `origin/main` was the right target ONLY until this
# fix merged -- once merged, origin/main IS the fixed (auto-discovering) guard,
# so a `${PRE_FIX_GUARD_REF:-origin/main}` default would read the FIXED guard
# here, section (A) would find it no longer blind, and this CI-wired test would
# fail PERMANENTLY on every future PR (proven: PRE_FIX_GUARD_REF=origin/
# fix/skill6-residuals bash ...all-skill-dirs.test.sh -> "TESTS FAILED", exit 1,
# because that branch's tip IS the fixed guard). Fix (P3-04 fix-loop item 1):
# pin the default to the last-BLIND commit SHA --
# 49b88cd5832a99ff7885036d7e9dbc78c43b9a2d is the commit immediately BEFORE
# this fix landed (v19.58.0 release, hand-enumerated 3-root
# MANAGED_SCAN_ROOTS array, verified blind to 44-*/62-* below). A commit SHA
# is immutable and remains resolvable in `git show` forever once it is an
# ancestor of main (this repo's `--no-ff` merge discipline, meta-rule 2.6,
# guarantees it stays an ancestor) -- so this never goes stale the way a
# branch ref does. PRE_FIX_GUARD_REF stays override-able (e.g. for a one-time
# documented re-proof against a different ref) but the default is now a
# fixed point in history, not a moving target.
PRE_FIX_REF="${PRE_FIX_GUARD_REF:-49b88cd5832a99ff7885036d7e9dbc78c43b9a2d}"
if ! git -C "$REPO_ROOT" show "${PRE_FIX_REF}:scripts/guard-agent-browser-managed.sh" \
     > "$PRE_FIX_GUARD" 2>/dev/null; then
  # A shallow CI checkout (actions/checkout default fetch-depth=1) may not
  # have the pinned SHA resolvable yet -- try one bounded, best-effort fetch
  # before giving up (self-healing; never widens what the workflow checks out).
  git -C "$REPO_ROOT" fetch --depth=1 origin main >/dev/null 2>&1 || true
  git -C "$REPO_ROOT" show "${PRE_FIX_REF}:scripts/guard-agent-browser-managed.sh" \
    > "$PRE_FIX_GUARD" 2>/dev/null || true
fi
if [[ ! -s "$PRE_FIX_GUARD" ]]; then
  # Still unavailable (e.g. a tarball checkout with no git history at all) --
  # skip (A) honestly rather than fabricate a "pass".
  echo "  SKIP: could not read ${PRE_FIX_REF}:scripts/guard-agent-browser-managed.sh from git history -- skipping the fail-first (A) half, running (B)-(D) only."
  PRE_FIX_GUARD=""
fi

# ── Build the minimal synthetic tree the guard's sections (0)-(4) require,
# PLUS 44-convert-and-flow-operator/ (the P3-08-named root) and a brand-new
# never-before-seen numbered dir (proves auto-discovery, not a second hand-add) ─
mkdir -p \
  "$TMP_TREE/06-ghl-install-pages/tools" \
  "$TMP_TREE/scripts" \
  "$TMP_TREE/44-convert-and-flow-operator/tools" \
  "$TMP_TREE/62-hypothetical-future-skill"

cat > "$TMP_TREE/06-ghl-install-pages/tools/browser_manager.sh" <<'EOF'
#!/usr/bin/env bash
# Minimal stub satisfying guard section (2) GATEWAY INTEGRITY verbatim markers.
_bm_teardown() { :; }
trap _bm_teardown EXIT
bm_lock() { mkdir "$LOCKDIR/ab.lock.d"; }
bm_close() { agent-browser close --session "$1"; }
bm_state_clear() { agent-browser state clear; }
bm_breaker_check() { :; }
AB() { agent-browser --session "$1" "${@:2}"; }
EOF
: > "$TMP_TREE/06-ghl-install-pages/tools/browser_manager.py"
cat > "$TMP_TREE/scripts/agent-browser-reaper.sh" <<'EOF'
#!/usr/bin/env bash
: # minimal stub
EOF
SENTINEL='SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown, reaper backstop'
for doc in SKILL.md ghl-browser-builder-full.md CORE_UPDATES.md; do
  printf '%s\n' "$SENTINEL" > "$TMP_TREE/06-ghl-install-pages/$doc"
done

# ── (A) FAIL-FIRST: the pre-fix guard is blind to spawns in BOTH new roots ────
if [[ -n "$PRE_FIX_GUARD" ]]; then
  echo ""
  echo "--- (A) fail-first: pre-fix guard (${PRE_FIX_REF}) is BLIND to 44-*/62-* ---"
  # Plant the fixtures for this half too (removed again before section B).
  FIXTURE_44="$TMP_TREE/44-convert-and-flow-operator/tools/zz-planted-unmanaged-probe.sh"
  FIXTURE_62="$TMP_TREE/62-hypothetical-future-skill/zz-planted-unmanaged-probe.sh"
  cat > "$FIXTURE_44" <<'EOF'
#!/usr/bin/env bash
agent-browser --session zz-planted-test open https://example.com
EOF
  cat > "$FIXTURE_62" <<'EOF'
#!/usr/bin/env bash
agent-browser snapshot -i
EOF
  A_OUT="$(bash "$PRE_FIX_GUARD" --repo-root "$TMP_TREE" 2>&1)"
  A_EXIT=$?
  if [[ "$A_EXIT" -eq 0 ]]; then
    pass "(A) pre-fix guard PASSES (exit 0) with both fixtures planted -- reproduces the bug (44-*/a future skill dir were unscanned)"
  else
    fail "(A) pre-fix guard should have PASSED (blind) here -- either the fixture setup or the pre-fix-guard fetch drifted. Output: $(printf '%s' "$A_OUT" | tail -10)"
  fi
  rm -f "$FIXTURE_44" "$FIXTURE_62"
fi

# ── (B) baseline: the minimal synthetic tree PASSES clean under the CURRENT guard
echo ""
echo "--- (B) baseline: minimal tree (incl. empty 44-*/62-* roots) passes ---"
B_OUT="$(bash "$CURRENT_GUARD" --repo-root "$TMP_TREE" 2>&1)"
B_EXIT=$?
if [[ "$B_EXIT" -eq 0 ]]; then
  pass "(B) current guard PASSES on the clean synthetic tree (44-*/62-* auto-discovered, zero false positives)"
else
  fail "(B) current guard should PASS on the clean tree -- auto-discovery introduced a false positive. Output: $(printf '%s' "$B_OUT" | tail -15)"
fi
if printf '%s' "$B_OUT" | grep -q '44-convert-and-flow-operator'; then
  pass "(B) current guard's scan-roots line names 44-convert-and-flow-operator (the P3-08 root)"
else
  fail "(B) current guard did not list 44-convert-and-flow-operator among its scan roots"
fi
if printf '%s' "$B_OUT" | grep -q '62-hypothetical-future-skill'; then
  pass "(B) current guard's scan-roots line names the never-before-seen 62-* dir (true auto-discovery)"
else
  fail "(B) current guard did not list 62-hypothetical-future-skill among its scan roots -- not truly auto-discovering"
fi

# ── (C) plant an unmanaged bare agent-browser call in BOTH new roots at once ──
echo ""
echo "--- (C) planted unmanaged spawn in 44-* AND 62-* -> CURRENT guard MUST FAIL on both ---"
FIXTURE_44="$TMP_TREE/44-convert-and-flow-operator/tools/zz-planted-unmanaged-probe.sh"
cat > "$FIXTURE_44" <<'EOF'
#!/usr/bin/env bash
# Planted negative fixture (P3-04 test only) -- a raw, unmanaged agent-browser
# spawn that does NOT route through 06-ghl-install-pages/tools/browser_manager.sh.
agent-browser --session zz-planted-test open https://example.com
EOF
FIXTURE_62="$TMP_TREE/62-hypothetical-future-skill/zz-planted-unmanaged-probe.sh"
cat > "$FIXTURE_62" <<'EOF'
#!/usr/bin/env bash
# Planted negative fixture (P3-04 test only) -- same unmanaged spawn shape,
# planted in a numbered directory that did not exist when the guard was written.
agent-browser snapshot -i
EOF

C_OUT="$(bash "$CURRENT_GUARD" --repo-root "$TMP_TREE" 2>&1)"
C_EXIT=$?
if [[ "$C_EXIT" -ne 0 ]]; then
  pass "(C) current guard FAILS (exit $C_EXIT) with both fixtures planted"
else
  fail "(C) current guard did NOT bite with unmanaged spawns planted in 44-*/62-* (exit 0 -- still blind to these roots)"
fi
if printf '%s' "$C_OUT" | grep -q "44-convert-and-flow-operator/tools/zz-planted-unmanaged-probe.sh"; then
  pass "(C) current guard's failure output names the 44-convert-and-flow-operator/ planted file"
else
  fail "(C) current guard should name the 44-* planted file (got: $(printf '%s' "$C_OUT" | grep -i 'fail\|zz-planted' | head -5 | tr '\n' ';'))"
fi
if printf '%s' "$C_OUT" | grep -q "62-hypothetical-future-skill/zz-planted-unmanaged-probe.sh"; then
  pass "(C) current guard's failure output names the 62-hypothetical-future-skill/ planted file (a dir that did not exist when the guard was written)"
else
  fail "(C) current guard should name the 62-* planted file (got: $(printf '%s' "$C_OUT" | grep -i 'fail\|zz-planted' | head -5 | tr '\n' ';'))"
fi

rm -f "$FIXTURE_44" "$FIXTURE_62"

# ── (D) clean tree passes again once every fixture is removed ────────────────
echo ""
echo "--- (D) tree passes again once all planted fixtures are removed ---"
D_OUT="$(bash "$CURRENT_GUARD" --repo-root "$TMP_TREE" 2>&1)"
D_EXIT=$?
if [[ "$D_EXIT" -eq 0 ]]; then
  pass "(D) current guard PASSES again after fixtures removed (fixtures didn't leave residue)"
else
  fail "(D) current guard should PASS once fixtures are removed. Output: $(printf '%s' "$D_OUT" | tail -15)"
fi

echo ""
echo "================================================="
echo "Results: $PASS passed, $FAIL failed"
echo "================================================="
if [[ "$FAIL" -eq 0 ]]; then
  echo "ALL TESTS PASSED"
  exit 0
else
  echo "TESTS FAILED"
  exit 1
fi
