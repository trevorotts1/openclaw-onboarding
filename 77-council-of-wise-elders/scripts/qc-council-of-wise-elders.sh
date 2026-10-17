#!/usr/bin/env bash
# Council of Wise Elders (77): bundled QC gate.
# Runs the offline doctor, bundle verification, roster and preservation
# checks. Safe on a client box: checks that need a source checkout skip
# cleanly when no git checkout is present.
# Exit 0 = pass, 1 = fail. This script never modifies anything.

set -u
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0

note_pass() { echo "PASS $1"; }
note_fail() { echo "FAIL $1"; FAIL=1; }

echo "== Council of Wise Elders QC =="
echo "skill dir: $SKILL_DIR"

# 1. Node present (PREREQS: node >= 18 runs the skill's own scripts).
if command -v node >/dev/null 2>&1; then
  note_pass "node present: $(node --version)"
else
  note_fail "node not found (PREREQS.json requires Node.js 18+)"
fi

# 2. Doctor: layout, versions, roster, labels, JSON, manifest, state.
if command -v node >/dev/null 2>&1; then
  if node "$SKILL_DIR/scripts/doctor.mjs" --root "$SKILL_DIR"; then
    note_pass "doctor"
  else
    note_fail "doctor (see output above)"
  fi
  # 3. Bundle verification against manifest.json.
  if node "$SKILL_DIR/scripts/verify-bundles.mjs" --root "$SKILL_DIR"; then
    note_pass "bundle verification"
  else
    note_fail "bundle verification (see output above)"
  fi
fi

# 4. No state files inside the folder (defense in depth beside doctor).
if find "$SKILL_DIR" \( -name '*.sqlite' -o -name '*.sqlite3' -o -name '*.db' \) -print | grep -q .; then
  note_fail "state database files found inside the skill folder"
else
  note_pass "no state database files inside the skill folder"
fi

# 5. No em dash characters in the package text (house style rule).
EM="$(printf '\342\200\224')"
if grep -rIl "$EM" "$SKILL_DIR" >/dev/null 2>&1; then
  note_fail "em dash character found in package files: $(grep -rIl "$EM" "$SKILL_DIR" | head -3)"
else
  note_pass "no em dash characters in package files"
fi

# 6. Source-checkout-only checks: wave roster and Skill 76 preservation.
REPO_ROOT="$(dirname "$SKILL_DIR")"
if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  ROSTER_COUNT="$(grep '^OC_WAVE6_SKILLS=' "$REPO_ROOT/lib-onboarding-state.sh" | grep -o '77-council-of-wise-elders' | wc -l | tr -d ' ')"
  if [ "$ROSTER_COUNT" = "1" ]; then
    note_pass "wave roster contains 77-council-of-wise-elders exactly once"
  else
    note_fail "wave roster count for 77-council-of-wise-elders is $ROSTER_COUNT, expected 1"
  fi
  if [ -z "$(git -C "$REPO_ROOT" status --porcelain -- 76-local-embedder)" ] \
     && [ -z "$(git -C "$REPO_ROOT" diff HEAD --name-only -- 76-local-embedder)" ]; then
    note_pass "76-local-embedder untouched"
  else
    note_fail "76-local-embedder has changes in this checkout"
  fi
else
  echo "SKIP source-checkout checks (not inside a git checkout)"
fi

if [ "$FAIL" -eq 0 ]; then
  echo "QC: PASS"
else
  echo "QC: FAIL"
fi
exit "$FAIL"
