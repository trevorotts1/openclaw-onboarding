#!/usr/bin/env bash
# ============================================================
# test-workspace-departments-built.sh — smoke test for AF-WORKSPACE-SHELL
#   (scripts/qc-assert-workspace-departments-built.sh).
# ------------------------------------------------------------
# Proves the gate is fail-closed against the exact failure that cost real money:
# a workspace department left as an empty SHELL (DREAMS.md + memory/ only) while a
# role-library TEMPLATE was copied to the skills/ tree and reported "installed".
#
# All tests build REAL folders on disk under a temp dir and invoke the gate with
# --departments-dir <dir> (the same hook the gate exposes for operators). No live
# OpenClaw install, no network.
#
#   T1. SHELL FAILS: a workspace where every required dept exists but is an empty
#       shell (DREAMS.md + memory/ only — NO role subdirs, NO IDENTITY/SOUL/SOP)
#       FAILS the gate (rc=3 AF-WORKSPACE-SHELL).
#   T2. FULL PASSES: the SAME workspace, now fully materialized (numbered role
#       subdirs + IDENTITY.md + SOUL.md + a real >=3KB how-to.md SOP per dept)
#       PASSES the gate (rc=0).
#   T3. PARTIAL FAILS: role subdirs present but missing IDENTITY.md/SOUL.md and
#       no real SOP → PARTIAL → FAILS (rc=3). (A half-built dept is not "done".)
#   T4. TEMPLATE-NEVER-PASSES: pointing the gate at a skills/.../role-library
#       TEMPLATE tree (even a fully-populated one) FAILS as not-a-workspace
#       (rc=4). A template on disk must NEVER satisfy the gate.
#   T5. SLUG-NAMED ROLES PASS: a workspace whose role folders are SLUG-named
#       (chief-marketing-officer/, head-of-sales/) — NOT NN-prefixed — but
#       otherwise fully built (IDENTITY/SOUL + real SOP) PASSES (rc=0). This is
#       the false-SHELL bug for legitimately-built workforces.
#   T6. SOP-SUBDIR PASS: a workspace whose role SOPs live in a SOP/ subdir
#       (role/SOP/how-to.md), not 0N-*.md directly in the role dir, PASSES
#       (rc=0). The gate must recognize the SOP-subdir shape as a real SOP.
#   T7. MASTER-FILES-HOME PASS: a fully-built workspace whose path is UNDER
#       openclaw-master-files (.../openclaw-master-files/zero-human-company/<co>/
#       departments) PASSES (rc=0). master-files IS the canonical workspace home;
#       the old gate wrongly rejected it (false-flagged legitimately-built workforces).
#   T8. GENUINELY-EMPTY STILL FAILS: a workspace with NO role folders of EITHER
#       naming (only DREAMS.md + memory/) STILL FAILS (rc=3). The additive
#       detection must never weaken the real empty-shell check.
#
# Exit 0 = all tests pass; non-zero = a test failed.
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-assert-workspace-departments-built.sh"
FLOOR_PY="$SCRIPT_DIR/../23-ai-workforce-blueprint/scripts/department-floor.py"
NAMING_MAP="$SCRIPT_DIR/../23-ai-workforce-blueprint/department-naming-map.json"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

if [ ! -f "$GATE" ]; then echo "ABORT: gate not found at $GATE" >&2; exit 1; fi
if [ ! -f "$FLOOR_PY" ]; then echo "ABORT: department-floor.py not found at $FLOOR_PY" >&2; exit 1; fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# The exact REQUIRED department set the gate enforces = department-floor's
# expected_floor (mandatory(−declined) + universal-primary verticals(−declined)).
# We materialize precisely that set so the test is self-consistent with whatever
# the live naming map declares (no hardcoded dept list to drift).
REQUIRED=$(FLOOR_PY="$FLOOR_PY" python3 - <<'PY'
import importlib.util, os
spec = importlib.util.spec_from_file_location("department_floor", os.environ["FLOOR_PY"])
df = importlib.util.module_from_spec(spec); spec.loader.exec_module(df)
# Build the floor with a throwaway empty dir so we just read the required set.
import tempfile, pathlib
d = pathlib.Path(tempfile.mkdtemp()) / "departments"; d.mkdir(parents=True)
v = df.evaluate_floor(departments_dir=d, build_state={}, core_answers={"industry":"general business"})
print(" ".join(v.get("expected_floor", [])))
PY
)
if [ -z "$REQUIRED" ]; then echo "ABORT: could not compute required department set" >&2; exit 1; fi
echo "Required (floor) departments under test: $REQUIRED"
echo ""

run_gate() { # <departments_dir> ; sets RC
  RC=0
  bash "$GATE" --departments-dir "$1" >/dev/null 2>&1 || RC=$?
}

# ── T1: every required dept is an empty SHELL → FAIL (rc=3) ──
echo "=== T1: SHELL workspace FAILS (AF-WORKSPACE-SHELL) ==="
DD1="$TMP/t1/zero-human-company/acme/departments"
mkdir -p "$DD1"
for d in $REQUIRED; do
  mkdir -p "$DD1/$d/memory"
  printf '# Dreams\n' > "$DD1/$d/DREAMS.md"   # the exact empty-shell shape
done
run_gate "$DD1"
if [ "$RC" -eq 3 ]; then ok "shell depts (DREAMS.md + memory/ only) -> rc=3"; else bad "shell workspace must FAIL rc=3, got rc=$RC"; fi

# ── T2: same workspace, fully materialized → PASS (rc=0) ──
echo "=== T2: FULL workspace PASSES (rc=0) ==="
DD2="$TMP/t2/zero-human-company/acme/departments"
mkdir -p "$DD2"
# A real SOP body >= 3072 bytes (the how-to.md SOP floor).
SOP_BODY="$(python3 - <<'PY'
print("# Role how-to (SOP)\n\n## 9. SOPs\n\n### SOP 9.1 — Daily run\n" + ("Steps: do the work. " * 250))
PY
)"
for d in $REQUIRED; do
  mkdir -p "$DD2/$d/memory"
  printf '# Dreams\n' > "$DD2/$d/DREAMS.md"
  printf '# Director identity\n' > "$DD2/$d/IDENTITY.md"
  printf '# Director soul\n'      > "$DD2/$d/SOUL.md"
  # numbered role subdirs with a real how-to.md SOP each
  mkdir -p "$DD2/$d/00-head/memory" "$DD2/$d/01-specialist/memory"
  printf '%s\n' "$SOP_BODY" > "$DD2/$d/00-head/how-to.md"
  printf '%s\n' "$SOP_BODY" > "$DD2/$d/01-specialist/how-to.md"
  printf '# role identity\n' > "$DD2/$d/00-head/IDENTITY.md"
  printf '# role identity\n' > "$DD2/$d/01-specialist/IDENTITY.md"
done
run_gate "$DD2"
if [ "$RC" -eq 0 ]; then ok "fully materialized depts (roles + IDENTITY + SOUL + real SOP) -> rc=0"; else bad "full workspace must PASS rc=0, got rc=$RC"; fi

# ── T3: PARTIAL (role dirs but no IDENTITY/SOUL, no real SOP) → FAIL (rc=3) ──
echo "=== T3: PARTIAL workspace FAILS (rc=3) ==="
DD3="$TMP/t3/zero-human-company/acme/departments"
mkdir -p "$DD3"
for d in $REQUIRED; do
  mkdir -p "$DD3/$d/memory" "$DD3/$d/00-head"
  printf '# Dreams\n' > "$DD3/$d/DREAMS.md"
  printf 'tiny\n'     > "$DD3/$d/00-head/how-to.md"   # < 3072 bytes -> not a real SOP
  # NO IDENTITY.md, NO SOUL.md at dept root
done
run_gate "$DD3"
if [ "$RC" -eq 3 ]; then ok "partial depts (role dir but no IDENTITY/SOUL + thin SOP) -> rc=3"; else bad "partial workspace must FAIL rc=3, got rc=$RC"; fi

# ── T4: pointing at a TEMPLATE tree must NEVER pass (rc=4 not-a-workspace) ──
echo "=== T4: TEMPLATE tree is NOT a workspace (rc=4) ==="
# Build a fully-populated FULL-looking dept set but UNDER a skills/role-library
# template path. The gate's _is_template_path guard must reject it outright.
DD4="$TMP/t4/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library"
mkdir -p "$DD4"
for d in $REQUIRED; do
  mkdir -p "$DD4/$d/00-head"
  printf '# Director identity\n' > "$DD4/$d/IDENTITY.md"
  printf '# Director soul\n'      > "$DD4/$d/SOUL.md"
  printf '%s\n' "$SOP_BODY" > "$DD4/$d/00-head/how-to.md"
done
run_gate "$DD4"
if [ "$RC" -eq 4 ]; then ok "template tree (skills/.../role-library) rejected as not-a-workspace -> rc=4"; else bad "template tree must FAIL rc=4 (never satisfy gate), got rc=$RC"; fi

# ── T5: SLUG-named role folders (no NN prefix) but fully built → PASS (rc=0) ──
echo "=== T5: SLUG-named role folders PASS (rc=0) ==="
DD5="$TMP/t5/zero-human-company/acme/departments"
mkdir -p "$DD5"
for d in $REQUIRED; do
  mkdir -p "$DD5/$d/memory"
  printf '# Dreams\n' > "$DD5/$d/DREAMS.md"
  printf '# Director identity\n' > "$DD5/$d/IDENTITY.md"
  printf '# Director soul\n'      > "$DD5/$d/SOUL.md"
  # SLUG-named role subdirs (NO NN prefix) with role files + a real how-to.md SOP
  mkdir -p "$DD5/$d/chief-marketing-officer/memory" "$DD5/$d/head-of-sales/memory"
  printf '# role identity\n' > "$DD5/$d/chief-marketing-officer/IDENTITY.md"
  printf '# role soul\n'     > "$DD5/$d/chief-marketing-officer/SOUL.md"
  printf '%s\n' "$SOP_BODY"  > "$DD5/$d/chief-marketing-officer/how-to.md"
  printf '# role identity\n' > "$DD5/$d/head-of-sales/IDENTITY.md"
  printf '%s\n' "$SOP_BODY"  > "$DD5/$d/head-of-sales/how-to.md"
done
run_gate "$DD5"
if [ "$RC" -eq 0 ]; then ok "slug-named role folders (chief-marketing-officer/, head-of-sales/) -> rc=0"; else bad "slug-named-role workspace must PASS rc=0, got rc=$RC"; fi

# ── T6: SOPs in a role's SOP/ subdir (not 0N-*.md direct) → PASS (rc=0) ──
echo "=== T6: SOP-subdir shape PASSES (rc=0) ==="
DD6="$TMP/t6/zero-human-company/acme/departments"
mkdir -p "$DD6"
for d in $REQUIRED; do
  mkdir -p "$DD6/$d/memory"
  printf '# Dreams\n' > "$DD6/$d/DREAMS.md"
  printf '# Director identity\n' > "$DD6/$d/IDENTITY.md"
  printf '# Director soul\n'      > "$DD6/$d/SOUL.md"
  # numbered role subdir whose SOPs live in a SOP/ subdir, NOT how-to.md/0N-*.md direct
  mkdir -p "$DD6/$d/00-head/SOP" "$DD6/$d/00-head/memory"
  printf '# role identity\n' > "$DD6/$d/00-head/IDENTITY.md"
  printf '%s\n' "$SOP_BODY" > "$DD6/$d/00-head/SOP/how-to.md"
done
run_gate "$DD6"
if [ "$RC" -eq 0 ]; then ok "role SOPs in a SOP/ subdir (role/SOP/how-to.md) -> rc=0"; else bad "SOP-subdir workspace must PASS rc=0, got rc=$RC"; fi

# ── T7: workspace UNDER openclaw-master-files (canonical home) → PASS (rc=0) ──
echo "=== T7: master-files-home path PASSES (rc=0) ==="
DD7="$TMP/t7/Downloads/openclaw-master-files/zero-human-company/acme/departments"
mkdir -p "$DD7"
for d in $REQUIRED; do
  mkdir -p "$DD7/$d/memory"
  printf '# Dreams\n' > "$DD7/$d/DREAMS.md"
  printf '# Director identity\n' > "$DD7/$d/IDENTITY.md"
  printf '# Director soul\n'      > "$DD7/$d/SOUL.md"
  mkdir -p "$DD7/$d/00-head/memory" "$DD7/$d/01-specialist/memory"
  printf '%s\n' "$SOP_BODY" > "$DD7/$d/00-head/how-to.md"
  printf '%s\n' "$SOP_BODY" > "$DD7/$d/01-specialist/how-to.md"
  printf '# role identity\n' > "$DD7/$d/00-head/IDENTITY.md"
  printf '# role identity\n' > "$DD7/$d/01-specialist/IDENTITY.md"
done
run_gate "$DD7"
if [ "$RC" -eq 0 ]; then ok "fully-built workspace UNDER openclaw-master-files (canonical home) -> rc=0"; else bad "master-files-home workspace must PASS rc=0 (it is the workspace home, not a template), got rc=$RC"; fi

# ── T8: genuinely-empty dept (no role folders of EITHER naming) STILL FAILS ──
echo "=== T8: genuinely-empty dept STILL FAILS (rc=3) ==="
# Same shape as T1 but explicit: ONLY DREAMS.md + memory/ — zero role folders of
# EITHER naming convention. The additive detection must NOT weaken this.
DD8="$TMP/t8/zero-human-company/acme/departments"
mkdir -p "$DD8"
for d in $REQUIRED; do
  mkdir -p "$DD8/$d/memory"
  printf '# Dreams\n' > "$DD8/$d/DREAMS.md"
  # NO NN-prefixed role folder, NO slug-named role folder, NO IDENTITY/SOUL/SOP.
done
run_gate "$DD8"
if [ "$RC" -eq 3 ]; then ok "genuinely-empty depts (DREAMS.md + memory/ only, zero role folders) STILL -> rc=3"; else bad "genuinely-empty workspace must STILL FAIL rc=3, got rc=$RC"; fi

echo ""
echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && { echo "ALL WORKSPACE-SHELL GATE TESTS PASSED"; exit 0; } || { echo "WORKSPACE-SHELL GATE TEST FAILURES"; exit 1; }
