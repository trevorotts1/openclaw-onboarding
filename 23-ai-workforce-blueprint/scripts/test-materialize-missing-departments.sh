#!/usr/bin/env bash
# test-materialize-missing-departments.sh — P2-06 (c)2: fail-first proof for
# materialize-missing-departments.py, the live remediation for a box that is
# missing whole departments ("the wipe").
#
# WHY THIS IS A NEW GAP, NOT A DUPLICATE OF EXISTING COVERAGE
# -------------------------------------------------------------
# tests/unit/floor-fill-gap.test.sh already proves make-gap-from-staleness.py
# DROPS "dept"-kind items from its gap-map on purpose ("STALE / dept items
# must be dropped") — the existing v16.0.2 update-path floor-fill
# (migrate-existing-workforce.sh Step 2b -> floor-fill-driver.py) only ever
# fills missing ROLES/SOPS inside a department that ALREADY EXISTS on disk.
# A department that is entirely ABSENT was invisible to that pipeline. This
# suite proves the NEW script this unit ships closes exactly that residue.
#
#   T1. FULL REMEDIATION, ADDITIVE-ONLY: a short board (5 real depts on disk,
#       one flat-.md-library dept [sales] and one subdir-library dept
#       [engineering] both PRE-EXISTING with a marker file) -> --apply
#       materializes every missing dept with REAL library-filled content
#       (>=3072 bytes/role, the same LIBRARY_FILL_MIN_BYTES floor
#       create_role_workspaces.py itself enforces -- never a stub), department-
#       floor.py reports floor_met=True afterward, and the two PRE-EXISTING
#       depts are BYTE-IDENTICAL before/after (checksum-proven additive-only).
#   T2. IDEMPOTENT RE-RUN: running --apply again on an already-complete board
#       is a byte-identical no-op ("none -- floor already met").
#   T3. DECLINES RESPECTED: a build-state decline for two depts survives
#       --apply -- they are NEVER re-added, floor_met is still True (declines
#       shrink the enforced floor, exactly like department-floor.py itself).
#   T4. DRY-RUN NEVER MUTATES: without --apply, a short board's on-disk tree
#       is byte-identical before/after (rc=3, report-only).
#   T5. FAIL-FIRST REGRESSION LOCK: reintroduces the actual bug hit during
#       this unit's own development -- enumerating a dept's library roster by
#       globbing '*.md' at the dept-folder root, which returns [] for every
#       library dept that uses the per-role '<slug>/how-to.md' subdirectory
#       layout (e.g. engineering/, account-management/) instead of flat files
#       (e.g. sales/, billing/, presentations/). Proves this suite would have
#       caught it: T1 must FAIL when the bug is present, and PASS again once restored.
#
# Exit 0 = all checks pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MATERIALIZE="$SCRIPT_DIR/materialize-missing-departments.py"
FLOOR="$SCRIPT_DIR/department-floor.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

[ -f "$MATERIALIZE" ] || { echo "FATAL: $MATERIALIZE not shipped" >&2; exit 1; }
python3 -m py_compile "$MATERIALIZE" || { echo "FATAL: py_compile failed" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

checksum_tree() { find "$1" -type f | sort | xargs shasum 2>/dev/null | sed "s#$1##"; }

# HERMETICITY: materialize-missing-departments.py defaults to
# department_floor.load_build_state(), which reads the EXECUTING BOX's REAL
# ~/.openclaw (or /data/.openclaw) workforce build-state file when present.
# On a dev/operator box that already has a real client build-state with real
# declines recorded, that default would silently change which departments
# this suite expects to see materialized -- a test that passes only on a
# clean CI runner and fails (or worse, false-passes) on a populated box is
# not hermetic. Every call in this suite that is NOT explicitly testing
# decline behavior (T3) pins --build-state-file to this neutral, empty file
# so the suite's verdict never depends on what happens to be on the box.
NEUTRAL_BS="$TMP/neutral-build-state.json"
echo '{}' > "$NEUTRAL_BS"

# department-floor.py's CLI has NO --build-state-file flag (evaluate_floor()'s
# build_state param is function-only, main() never exposes an override), so a
# decline-aware check must call evaluate_floor() directly, exactly like
# test-department-floor.sh's own eval_floor() driver does.
floor_met() { # <departments_dir> [build-state-file]
  local dd="$1" bsf="${2:-}"
  python3 - "$FLOOR" "$dd" "$bsf" <<'PYEOF'
import importlib.util, json, sys
from pathlib import Path
floor_path, dd, bsf = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("department_floor_mmdtest", floor_path)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
bs = json.loads(Path(bsf).read_text()) if bsf else {}
v = m.evaluate_floor(departments_dir=Path(dd), build_state=bs, core_answers={})
print(v["floor_met"])
PYEOF
}

# ── T1: full remediation, additive-only ─────────────────────────────────────
echo "=== T1: full remediation is additive-only and materializes real content ==="
DD1="$TMP/t1/departments"
mkdir -p "$DD1/sales/some-role" "$DD1/engineering/some-role" \
         "$DD1/marketing/some-role" "$DD1/research/some-role" "$DD1/crm/some-role"
echo "PRE-EXISTING sales marker -- must survive untouched" > "$DD1/sales/MARKER.txt"
echo "PRE-EXISTING engineering marker -- must survive untouched" > "$DD1/engineering/MARKER.txt"
BEFORE_SALES_SUM="$(checksum_tree "$DD1/sales")"
BEFORE_ENG_SUM="$(checksum_tree "$DD1/engineering")"

python3 "$MATERIALIZE" --departments-dir "$DD1" --build-state-file "$NEUTRAL_BS" --apply --json > "$TMP/t1-result.json" 2>"$TMP/t1-stderr.log"
T1_RC=$?

AFTER_MET="$(floor_met "$DD1" "$NEUTRAL_BS")"
if [ "$AFTER_MET" = "True" ]; then
  ok "T1a: department-floor.py reports floor_met=True after --apply"
else
  bad "T1a: expected floor_met=True after --apply, got $AFTER_MET (see $TMP/t1-stderr.log)"
fi

# Additive-only: every byte of the two PRE-EXISTING depts is untouched.
if [ -f "$DD1/sales/MARKER.txt" ] && grep -q "PRE-EXISTING sales marker" "$DD1/sales/MARKER.txt" \
   && [ -f "$DD1/engineering/MARKER.txt" ] && grep -q "PRE-EXISTING engineering marker" "$DD1/engineering/MARKER.txt"; then
  ok "T1b: pre-existing sales/ + engineering/ marker files survived --apply untouched"
else
  bad "T1b: a pre-existing marker file was lost or modified -- additive-only contract broken"
fi
AFTER_SALES_SUM="$(checksum_tree "$DD1/sales")"
AFTER_ENG_SUM="$(checksum_tree "$DD1/engineering")"
if [ "$BEFORE_SALES_SUM" = "$AFTER_SALES_SUM" ]; then
  ok "T1c: sales/ (pre-existing, flat-.md library dept) is byte-identical before/after --apply"
else
  bad "T1c: sales/ subtree changed -- a pre-existing dept was touched (additive-only contract broken)"
fi
if [ "$BEFORE_ENG_SUM" = "$AFTER_ENG_SUM" ]; then
  ok "T1c2: engineering/ (pre-existing, subdir-layout library dept) is byte-identical before/after --apply"
else
  bad "T1c2: engineering/ subtree changed -- a pre-existing dept was touched (additive-only contract broken)"
fi

# Real content, not stubs: spot-check the flat-.md-layout materialization.
FLAT_HOWTO="$(find "$DD1/billing-finance" -name how-to.md 2>/dev/null | head -1)"
if [ -n "$FLAT_HOWTO" ] && [ "$(wc -c < "$FLAT_HOWTO")" -ge 3072 ]; then
  ok "T1d: flat-.md-layout dept (billing-finance) materialized real content ($(wc -c < "$FLAT_HOWTO") bytes >= 3072)"
else
  bad "T1d: billing-finance how-to.md missing or below the 3072-byte library-fill floor -- looks stubbed"
fi
# A genuinely NEW subdir-layout dept must also be filled (e.g. presentations, universal-primary).
NEW_SUBDIR_HOWTO="$(find "$DD1/presentations" -mindepth 2 -name how-to.md 2>/dev/null | head -1)"
if [ -n "$NEW_SUBDIR_HOWTO" ] && [ "$(wc -c < "$NEW_SUBDIR_HOWTO")" -ge 3072 ]; then
  ok "T1f: NEW subdir-layout dept (presentations, universal-primary, was entirely absent) materialized real content"
else
  bad "T1f: presentations (new subdir-layout dept) not materialized with real content -- THIS IS THE ACTUAL BUG HIT DURING DEV (flat glob misses subdir-layout depts)"
fi

# ── T2: idempotent re-run ────────────────────────────────────────────────────
echo "=== T2: idempotent re-run on an already-complete board is a byte-identical no-op ==="
SUM_BEFORE_RERUN="$(checksum_tree "$DD1")"
python3 "$MATERIALIZE" --departments-dir "$DD1" --build-state-file "$NEUTRAL_BS" --apply --json > "$TMP/t2-result.json" 2>/dev/null
python3 -c "
import json
r = json.load(open('$TMP/t2-result.json'))
assert r['action'] == 'none -- floor already met', r
print('OK')
" >/dev/null 2>&1 && ok "T2a: second --apply short-circuits with action='none -- floor already met'" \
                    || bad "T2a: second --apply did not short-circuit as expected"
SUM_AFTER_RERUN="$(checksum_tree "$DD1")"
if [ "$SUM_BEFORE_RERUN" = "$SUM_AFTER_RERUN" ]; then
  ok "T2b: re-run produced a byte-identical tree (idempotent, no re-clobber)"
else
  bad "T2b: re-run MUTATED the tree -- not idempotent"
fi

# ── T3: declines respected ───────────────────────────────────────────────────
echo "=== T3: a client decline survives --apply -- never re-added ==="
DD3="$TMP/t3/departments"
mkdir -p "$DD3/marketing/some-role"
BS3="$TMP/t3-build-state.json"
cat > "$BS3" <<'JSON'
{"canonicalReconciliation":{"ownerDeclineConfirmed":true,"decisions":{"bugs":"no","podcast":"no"}}}
JSON
python3 "$MATERIALIZE" --departments-dir "$DD3" --build-state-file "$BS3" --apply --json > "$TMP/t3-result.json" 2>"$TMP/t3-stderr.log"
AFTER_MET3="$(floor_met "$DD3" "$BS3")"
if [ "$AFTER_MET3" = "True" ]; then
  ok "T3a: floor_met=True with 2 depts declined (declines shrink the enforced floor)"
else
  bad "T3a: expected floor_met=True honoring 2 declines, got $AFTER_MET3"
fi
if [ ! -d "$DD3/bugs" ] && [ ! -d "$DD3/podcast" ]; then
  ok "T3b: declined depts 'bugs' and 'podcast' were NEVER materialized"
else
  bad "T3b: a declined dept was materialized anyway (bugs=$( [ -d "$DD3/bugs" ] && echo present || echo absent ), podcast=$( [ -d "$DD3/podcast" ] && echo present || echo absent ))"
fi

# ── T4: dry-run never mutates ────────────────────────────────────────────────
echo "=== T4: dry-run (no --apply) never touches disk ==="
DD4="$TMP/t4/departments"
mkdir -p "$DD4/marketing/some-role"
BEFORE_SUM4="$(checksum_tree "$DD4")"
python3 "$MATERIALIZE" --departments-dir "$DD4" --build-state-file "$NEUTRAL_BS" --json > "$TMP/t4-result.json" 2>/dev/null
T4_RC=$?
AFTER_SUM4="$(checksum_tree "$DD4")"
if [ "$T4_RC" = "3" ]; then
  ok "T4a: dry-run on a short board exits rc=3 (matches department-floor.py's own short-floor rc)"
else
  bad "T4a: expected dry-run rc=3, got $T4_RC"
fi
if [ "$BEFORE_SUM4" = "$AFTER_SUM4" ]; then
  ok "T4b: dry-run left the tree byte-identical (zero mutation without --apply)"
else
  bad "T4b: dry-run MUTATED the tree -- --apply gate is broken"
fi

# ── T5: fail-first regression lock for the real bug hit during this unit's
#    own development. The FIRST implementation of library_roster_for() (this
#    unit's builder, before the fix below) globbed '*.md' at the dept-folder
#    root. That silently returns [] for every library dept using the per-role
#    '<slug>/how-to.md' SUBDIRECTORY layout (engineering/, account-management/,
#    account-management/, ...) -- so a subdir-layout universal-primary dept
#    would be reported under no_library_source and NEVER materialized, and
#    the board would stay floor-short forever. This test reintroduces that
#    exact defect into a SCRATCH COPY of the script (never the file under
#    test in place) and proves T1's own assertions catch it, then proves the
#    real shipped script (unmodified) still passes. ──────────────────────────
echo "=== T5: fail-first regression lock (reintroduces the flat-glob-only library-roster bug) ==="
# Must live ALONGSIDE the real scripts (not in $TMP): the script self-locates
# its department-floor.py / create_role_workspaces.py siblings via its OWN
# __file__ parent dir, so a copy placed elsewhere cannot import them. Removed
# unconditionally on exit (trap), and is never staged/committed -- a scratch
# artifact of this test run only.
BROKEN="$SCRIPT_DIR/.materialize-BROKEN-T5-scratch.py"
trap 'rm -rf "$TMP" "$BROKEN"' EXIT
python3 - "$MATERIALIZE" "$BROKEN" <<'PYEOF'
import re, sys
src_path, dst_path = sys.argv[1], sys.argv[2]
src = open(src_path).read()
# Replace the _index.json-based roster lookup with the naive glob-only version
# that shipped in this unit's FIRST draft and silently missed every
# subdirectory-layout library dept (the actual bug found during development).
needle = 'def library_roster_for(dept_id, index_roles=None):'
assert needle in src, "library_roster_for() signature not found -- cannot inject regression"
start = src.index(needle)
end = src.index('\n\n\ndef build_gap_map', start)
assert end > start, "could not locate end of library_roster_for() for injection"
broken_fn = (
    "def library_roster_for(dept_id, index_roles=None):\n"
    "    # BUG INJECTED FOR T5 FAIL-FIRST PROOF: naive flat glob only -- misses\n"
    "    # every subdirectory-layout library dept (engineering/, account-management/, ...).\n"
    "    lib_dir = LIBRARY / crw.normalize_dept(dept_id)\n"
    "    if not lib_dir.is_dir():\n"
    "        return []\n"
    "    return sorted(f.stem for f in lib_dir.glob('*.md') if f.name != 'how-to-use-this-department.md')\n"
)
patched = src[:start] + broken_fn + src[end + 3:]
assert patched != src
open(dst_path, "w").write(patched)
print("regression injected into scratch copy")
PYEOF
python3 -m py_compile "$BROKEN" || { bad "T5 setup: broken scratch copy failed to compile"; }

DD5="$TMP/t5/departments"
mkdir -p "$DD5/marketing/some-role"
python3 "$BROKEN" --departments-dir "$DD5" --build-state-file "$NEUTRAL_BS" --apply --json > "$TMP/t5-result.json" 2>/dev/null
python3 -c "
import json
r = json.load(open('$TMP/t5-result.json'))
no_lib = r.get('no_library_source', [])
after_met = r.get('after_floor_met')
assert 'engineering' in no_lib, f'expected subdir-layout dept engineering in no_library_source, got {no_lib}'
assert after_met is False, f'expected after_floor_met=False with the bug present, got {after_met}'
print('OK')
" >/dev/null 2>"$TMP/t5.err" \
  && ok "T5a: the injected flat-glob-only bug reproduces the real defect (engineering reported no_library_source, floor stays short) -- this suite WOULD have caught it" \
  || bad "T5a: injected-bug scratch copy did NOT reproduce the expected failure (see $TMP/t5.err) -- T5 does not actually test what it claims"

# Restore-and-confirm: the REAL shipped script (never modified on disk) still passes.
python3 "$MATERIALIZE" --departments-dir "$DD5" --build-state-file "$NEUTRAL_BS" --apply --json > "$TMP/t5-fixed-result.json" 2>/dev/null
python3 -c "
import json
r = json.load(open('$TMP/t5-fixed-result.json'))
assert r.get('after_floor_met') is True, r
assert r.get('no_library_source') == [], r
print('OK')
" >/dev/null 2>"$TMP/t5b.err" \
  && ok "T5b: the real shipped materialize-missing-departments.py (index-based, unmodified) closes the same gap cleanly" \
  || bad "T5b: the real shipped script failed on the identical scenario the injected bug failed on (see $TMP/t5b.err)"

echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && { echo "ALL MATERIALIZE-MISSING-DEPARTMENTS TESTS PASSED"; exit 0; } || { echo "MATERIALIZE-MISSING-DEPARTMENTS TESTS FAILED"; exit 1; }
