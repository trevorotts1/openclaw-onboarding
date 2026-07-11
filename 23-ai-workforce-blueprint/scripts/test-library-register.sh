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
#   10. C9: stale sop_count (index says 0, disk has embedded SOPs) -> FAIL (rc 7),
#       then --apply heals it to the real count -> --check PASSES (round-trip)
#   11. C9: a BRAND-NEW role with 3 embedded '### SOP' headings gets sop_count=3
#       (not the historical hardcoded 0) the moment --apply registers it, even
#       WITHOUT the hash-content-manifest chain (--no-hash)
#   12. C9: EMBEDDED_SOP_FLOOR is identical in hash-content-manifest.py and
#       qc-completeness.sh (the two canonical-count owners must never drift)
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

# ── 8b. unwired persona (no Domain tags header) -> FAIL ──────────────────────
sb="$(make_sandbox)"
if [ -d "$sb/skill/templates/persona-library" ]; then
  # Register the persona but give it NO Domain tags header -> unreachable/half-wired.
  printf '# Persona — Unwired Fixture\n\n**Persona type:** governing-persona\n\nbody\n' \
    > "$sb/skill/templates/persona-library/fixture-unwired-persona.md"
  ( cd "$sb" && python3 "skill/scripts/$GATE" \
      --index "skill/templates/role-library/_index.json" --apply --no-hash ) >/dev/null 2>&1
  rc="$(run_check "$sb")"
  [ "$rc" -eq 7 ] && pass "unwired persona (no Domain tags) FAILS (rc 7)" \
                  || die "unwired persona should FAIL (rc 7), got $rc"
else
  echo "  ! no persona-library — skipping unwired-persona fixture"
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

# ── 10. C9: stale sop_count (index says 0, disk has real embedded SOPs) ──────
# Pick a role that genuinely embeds "### SOP" content, corrupt its stored
# sop_count/sop_min back to the historical hardcoded 0/0, and prove --check
# BITES (the exact C9 bug: index misreports SOP linkage vs disk). Then
# --apply must heal it to the real count and --check must pass again.
sb="$(make_sandbox)"
read -r SOPDEPT SOPSLUG SOPPATH <<<"$(python3 - "$sb" <<'PY'
import json, sys, re
sb = sys.argv[1]
idx_path = f"{sb}/skill/templates/role-library/_index.json"
idx = json.load(open(idx_path))
skill = f"{sb}/skill"
for r in idx["roles"]:
    try:
        text = open(f"{skill}/{r['path']}", encoding="utf-8").read()
    except OSError:
        continue
    if len(re.findall(r"^###\s*SOP\b", text, re.MULTILINE)) >= 2:
        print(r["dept"], r["slug"], r["path"])
        break
PY
)"
if [ -n "${SOPSLUG:-}" ]; then
  python3 - "$sb" "$SOPDEPT" "$SOPSLUG" <<'PY'
import json, sys
sb, dept, slug = sys.argv[1], sys.argv[2], sys.argv[3]
p = f"{sb}/skill/templates/role-library/_index.json"
d = json.load(open(p))
for r in d["roles"]:
    if r["dept"] == dept and r["slug"] == slug:
        r["sop_count"] = 0
        r["sop_min"] = 0
        break
json.dump(d, open(p, "w"), indent=2)
PY
  rc="$(run_check "$sb")"
  [ "$rc" -eq 7 ] && pass "stale sop_count=0 on a role with real embedded SOPs FAILS (rc 7)" \
                  || die "stale sop_count should FAIL --check (rc 7), got $rc"
  # heal via --apply (full chain, so hash-content-manifest also re-stamps it)
  ( cd "$sb" && python3 "skill/scripts/$GATE" \
      --index "skill/templates/role-library/_index.json" --apply ) >/dev/null 2>&1
  rc="$(run_check "$sb")"
  [ "$rc" -eq 0 ] && pass "--apply heals stale sop_count then --check PASSES (rc 0)" \
                  || die "round-trip sop_count heal should PASS (rc 0), got $rc"
  # and the healed value is the REAL disk count, not another placeholder
  python3 - "$sb" "$SOPDEPT" "$SOPSLUG" "$SOPPATH" <<'PY'
import json, sys, re
sb, dept, slug, path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
d = json.load(open(f"{sb}/skill/templates/role-library/_index.json"))
r = next(x for x in d["roles"] if x["dept"] == dept and x["slug"] == slug)
text = open(f"{sb}/skill/{path}", encoding="utf-8").read()
expected = len(re.findall(r"^###\s*SOP\b", text, re.MULTILINE))
sys.exit(0 if (r["sop_count"] == expected and expected >= 2 and r["sop_min"] == 1) else 1)
PY
  if [ $? -eq 0 ]; then
    pass "healed sop_count equals a fresh recount of the role's own embedded SOP headings"
  else
    die "healed sop_count must equal the real disk count, not a placeholder"
  fi
else
  echo "  ! no role with >=2 embedded '### SOP' headings found — skipping stale-sop_count fixture"
fi
rm -rf "$sb"

# ── 11. C9: a BRAND-NEW role gets a REAL sop_count immediately, even under
#     --no-hash (proves _derive_role_meta computes it directly, not only via
#     the chained hash-content-manifest restamp) ─────────────────────────────
sb="$(make_sandbox)"
printf '# Fixture Role With SOPs\n\n**Role type:** specialist\n\n## 9. Standard Operating Procedures\n\n### SOP 9.1 -- First\nbody\n\n### SOP 9.2 -- Second\nbody\n\n### SOP 9.3 -- Third\nbody\n' \
  > "$sb/skill/$LIB/$DEPT/zzz-fixture-new-role-with-sops.md"
( cd "$sb" && python3 "skill/scripts/$GATE" \
    --index "skill/templates/role-library/_index.json" --apply --no-hash ) >/dev/null 2>&1
python3 - "$sb" <<'PY'
import json, sys
sb = sys.argv[1]
d = json.load(open(f"{sb}/skill/templates/role-library/_index.json"))
r = next((x for x in d["roles"] if x["slug"] == "zzz-fixture-new-role-with-sops"), None)
sys.exit(0 if (r is not None and r.get("sop_count") == 3 and r.get("sop_min") == 1) else 1)
PY
if [ $? -eq 0 ]; then
  pass "brand-new role gets sop_count=3 (real count) immediately, even under --no-hash"
else
  die "brand-new role should get a REAL sop_count on first registration (--no-hash), not 0"
fi
rm -rf "$sb"

# ── 12. C9: EMBEDDED_SOP_FLOOR must never drift between the two canonical
#     owners (hash-content-manifest.py and qc-completeness.sh's live-workspace
#     gate) — a silent renumber in either file would desynchronize what the
#     library index reports vs what the build-completeness gate enforces.
HCM_FLOOR="$(grep -m1 '^EMBEDDED_SOP_FLOOR = ' "$SCRIPT_DIR/hash-content-manifest.py" | sed -E 's/.*= *([0-9]+).*/\1/')"
QC_FLOOR="$(grep -m1 'EMBEDDED_SOP_FLOOR = ' "$SCRIPT_DIR/qc-completeness.sh" | sed -E 's/.*= *([0-9]+).*/\1/')"
if [ -n "$HCM_FLOOR" ] && [ -n "$QC_FLOOR" ] && [ "$HCM_FLOOR" = "$QC_FLOOR" ]; then
  pass "EMBEDDED_SOP_FLOOR agrees between hash-content-manifest.py and qc-completeness.sh ($HCM_FLOOR)"
else
  die "EMBEDDED_SOP_FLOOR drifted: hash-content-manifest.py=$HCM_FLOOR vs qc-completeness.sh=$QC_FLOOR"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "✓ test-library-register: all fixtures pass — the AUTO-REGISTER backstop bites on every half-add class and heals via --apply."
  exit 0
fi
echo "✗ test-library-register: one or more fixtures FAILED"
exit 1
