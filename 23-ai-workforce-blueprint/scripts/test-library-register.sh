#!/usr/bin/env bash
# test-library-register.sh — adversarial fixtures proving register-library-additions.py
# --check (the system-wide AUTO-REGISTER backstop) actually BITES on every half-add
# class, in ANY department. A green gate that never fails is worthless.
#
# Each fixture copies the role-library + the script to a temp tree, plants ONE
# half-add, and asserts --check exits 7 (drift). The clean baseline must exit 0.
#
# Classes proven:
#   1. clean baseline                  -> PASS (rc 0)
#   2. unregistered new role file      -> FAIL (rc 7)  [the half-add]
#   3. dead index entry (file removed) -> FAIL (rc 7)
#   4. duplicate-residue flat-beside-folder -> FAIL (rc 7)
#   5. triple-hyphen orphan file       -> FAIL (rc 7)
#   6. count drift (total_roles wrong) -> FAIL (rc 7)
#   7. unregistered dept-level SOP     -> FAIL (rc 7)
#   8. unregistered persona            -> FAIL (rc 7)
#   9. --apply heals an unregistered role then --check passes (round-trip)
#
# BASH harness; the gate itself is Python (no claude-/anthropic strings).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
GATE="register-library-additions.py"

fail=0
pass() { echo "  ✓ $1"; }
die()  { echo "  ✗ $1"; fail=1; }

# Build a hermetic copy of just what the gate needs: the skill scripts, the
# role-library, the persona-library, and shared-utils (for model_selector).
make_sandbox() {
  local sb; sb="$(mktemp -d)"
  mkdir -p "$sb/skill/scripts" "$sb/skill/templates" "$sb/shared-utils"
  cp "$SCRIPT_DIR"/*.py "$sb/skill/scripts/" 2>/dev/null
  cp -R "$SKILL_DIR/templates/role-library" "$sb/skill/templates/role-library"
  if [ -d "$SKILL_DIR/templates/persona-library" ]; then
    cp -R "$SKILL_DIR/templates/persona-library" "$sb/skill/templates/persona-library"
  fi
  cp -R "$REPO_ROOT/shared-utils/." "$sb/shared-utils/" 2>/dev/null
  echo "$sb"
}

run_check() {  # $1 = sandbox root ; echoes rc
  local sb="$1" rc=0
  ( cd "$sb" && python3 "skill/scripts/$GATE" \
      --index "skill/templates/role-library/_index.json" --check ) >/dev/null 2>&1 || rc=$?
  echo "$rc"
}

# ── 1. clean baseline -> PASS ────────────────────────────────────────────────
sb="$(make_sandbox)"
rc="$(run_check "$sb")"
[ "$rc" -eq 0 ] && pass "clean baseline PASSES (rc 0)" \
                || die "clean baseline should PASS (rc 0), got $rc"
rm -rf "$sb"

# pick a real department that uses the flat layout for fixtures
DEPT="sales"
LIB="templates/role-library"

# ── 2. unregistered new role file -> FAIL ───────────────────────────────────
sb="$(make_sandbox)"
printf '# Fixture Role\n\n**Role type:** specialist\n\nbody\n' \
  > "$sb/skill/$LIB/$DEPT/zzz-fixture-unregistered.md"
rc="$(run_check "$sb")"
[ "$rc" -eq 7 ] && pass "unregistered role file FAILS (rc 7)" \
                || die "unregistered role file should FAIL (rc 7), got $rc"
rm -rf "$sb"

# ── 3. dead index entry (registered file removed) -> FAIL ────────────────────
sb="$(make_sandbox)"
victim="$(python3 - "$sb" <<'PY'
import json,sys
sb=sys.argv[1]
idx=json.load(open(f"{sb}/skill/templates/role-library/_index.json"))
# remove the FILE of the first flat-layout role entry
for r in idx["roles"]:
    if r["path"].endswith(".md") and not r["path"].endswith("/how-to.md"):
        print(r["path"]); break
PY
)"
rm -f "$sb/skill/$victim"
rc="$(run_check "$sb")"
[ "$rc" -eq 7 ] && pass "dead index entry (file removed) FAILS (rc 7)" \
                || die "dead index entry should FAIL (rc 7), got $rc"
rm -rf "$sb"

# ── 4. duplicate-residue flat beside a folder-form role -> FAIL ──────────────
sb="$(make_sandbox)"
# find a folder-form role (path ends with /how-to.md) and plant a flat sibling
read -r FDEPT FSLUG <<<"$(python3 - "$sb" <<'PY'
import json,sys
sb=sys.argv[1]
idx=json.load(open(f"{sb}/skill/templates/role-library/_index.json"))
for r in idx["roles"]:
    if r["path"].endswith("/how-to.md"):
        print(r["dept"], r["slug"]); break
PY
)"
if [ -n "${FSLUG:-}" ]; then
  printf '# stale flat dup\n' > "$sb/skill/$LIB/$FDEPT/$FSLUG.md"
  rc="$(run_check "$sb")"
  [ "$rc" -eq 7 ] && pass "duplicate-residue flat-beside-folder FAILS (rc 7)" \
                  || die "duplicate-residue should FAIL (rc 7), got $rc"
else
  echo "  ! no folder-form role found — skipping dup-residue fixture"
fi
rm -rf "$sb"

# ── 5. triple-hyphen orphan file -> FAIL ─────────────────────────────────────
sb="$(make_sandbox)"
printf '# orphan\n\n**Role type:** specialist\n' \
  > "$sb/skill/$LIB/$DEPT/fixture-specialist---orphan.md"
rc="$(run_check "$sb")"
[ "$rc" -eq 7 ] && pass "triple-hyphen orphan file FAILS (rc 7)" \
                || die "triple-hyphen orphan should FAIL (rc 7), got $rc"
rm -rf "$sb"

# ── 6. count drift (corrupt total_roles) -> FAIL ─────────────────────────────
sb="$(make_sandbox)"
python3 - "$sb" <<'PY'
import json,sys
p=f"{sys.argv[1]}/skill/templates/role-library/_index.json"
d=json.load(open(p)); d["total_roles"]=d["total_roles"]+99
json.dump(d,open(p,"w"),indent=2)
PY
rc="$(run_check "$sb")"
[ "$rc" -eq 7 ] && pass "count drift (total_roles) FAILS (rc 7)" \
                || die "count drift should FAIL (rc 7), got $rc"
rm -rf "$sb"

# ── 7. unregistered dept-level SOP -> FAIL ───────────────────────────────────
sb="$(make_sandbox)"
mkdir -p "$sb/skill/$LIB/$DEPT/sops"
printf '# SOP fixture\n' > "$sb/skill/$LIB/$DEPT/sops/SOP--fixture-unregistered.md"
rc="$(run_check "$sb")"
[ "$rc" -eq 7 ] && pass "unregistered dept-level SOP FAILS (rc 7)" \
                || die "unregistered SOP should FAIL (rc 7), got $rc"
rm -rf "$sb"

# ── 8. unregistered persona -> FAIL ──────────────────────────────────────────
sb="$(make_sandbox)"
if [ -d "$sb/skill/templates/persona-library" ]; then
  printf '# Persona fixture\n' \
    > "$sb/skill/templates/persona-library/fixture-unregistered-persona.md"
  rc="$(run_check "$sb")"
  [ "$rc" -eq 7 ] && pass "unregistered persona FAILS (rc 7)" \
                  || die "unregistered persona should FAIL (rc 7), got $rc"
else
  echo "  ! no persona-library — skipping persona fixture"
fi
rm -rf "$sb"

# ── 9. --apply heals an unregistered role, then --check PASSES (round-trip) ───
sb="$(make_sandbox)"
printf '# Heal Me\n\n**Role type:** specialist\n\nbody\n' \
  > "$sb/skill/$LIB/$DEPT/zzz-fixture-heal-me.md"
( cd "$sb" && python3 "skill/scripts/$GATE" \
    --index "skill/templates/role-library/_index.json" --apply --no-hash ) >/dev/null 2>&1
rc="$(run_check "$sb")"
[ "$rc" -eq 0 ] && pass "--apply heals an unregistered role then --check PASSES (rc 0)" \
                || die "round-trip --apply then --check should PASS (rc 0), got $rc"
rm -rf "$sb"

echo
if [ "$fail" -eq 0 ]; then
  echo "✓ test-library-register: all fixtures pass — the AUTO-REGISTER backstop bites on every half-add class and heals via --apply."
  exit 0
fi
echo "✗ test-library-register: one or more fixtures FAILED"
exit 1
