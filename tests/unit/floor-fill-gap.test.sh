#!/usr/bin/env bash
# tests/unit/floor-fill-gap.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Acceptance test for the v16.0.2 floor-fill materialization wiring.
#
# Before v16.0.2 the update path DETECTED missing canonical floor roles/SOPs
# (via detect-stale-artifacts.py) but never FILLED them, so every v16-updated
# box kept an incomplete floor. The fix wires floor-fill into the update path
# (migrate-existing-workforce.sh Step 2b) via two shipped scripts:
#   - make-gap-from-staleness.py : detect-stale verdict -> floor-fill gap-map
#   - floor-fill-driver.py       : idempotently materializes the missing slots
#
# 2026-07-21: scenarios 3-7 added. Up to here this file exercised ONLY
# make-gap-from-staleness.py — floor-fill-driver.py itself was never RUN, only
# py_compile'd. That blind spot hid four defects, all of which this file now
# locks:
#   (a) detect-stale-artifacts.py's build-state FAST PATH never looked at the
#       filesystem, so a role folder the box BUILT and later LOST stayed
#       recorded and classified CURRENT. MISSING could not fire, the gap-map
#       came back empty, and the whole floor-fill chain no-op'd while the roll
#       reported success. build-workforce.py writes artifactProvenance on every
#       build, so this was the NORMAL path on a freshly built box.
#   (b) floor-fill-driver.py resolved the department as the BARE id and mkdir'd
#       it on a miss, so a real `Sales/` on a case-SENSITIVE filesystem (every
#       Linux VPS box) made it FABRICATE a second, empty `sales/` and
#       materialize the restored roles into the wrong department.
#   (c) the driver returned 0 unconditionally — `main()` was called without
#       sys.exit() — so a gap it could not fill reported success.
#   (d) a DRY-RUN (no --apply) still created department directories on disk.
#
# This test proves, fully offline:
#   1. both scripts compile (py_compile) and migrate passes bash -n.
#   2. make-gap-from-staleness.py turns a MISSING detect-stale verdict into the
#      correct gap-map: role -> missing_roles; sop -> named-set + missing_sops
#      with ".md" appended; CURRENT / STALE / persona / dept items dropped;
#      non-named-set depts drop the missing_sops key.
#   3. THE HEADLINE LOOP: a department whose role folders were DELETED is
#      DETECTED (MISSING) and RESTORED with real canonical library content —
#      end to end through the same three scripts the update path runs.
#   4. a gap the canonical library cannot fill exits 3 (loud), never 0, and
#      nothing is stubbed or fabricated in its place.
#   5. a case-drifted department folder resolves to the REAL directory instead
#      of spawning a duplicate.
#   6. a healthy box raises no false failure and clobbers nothing.
#   7. a dry run mutates nothing.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS="$REPO_ROOT/23-ai-workforce-blueprint/scripts"
FFD="$SCRIPTS/floor-fill-driver.py"
MGS="$SCRIPTS/make-gap-from-staleness.py"
MIG="$SCRIPTS/migrate-existing-workforce.sh"
DET="$SCRIPTS/detect-stale-artifacts.py"
IDX="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/_index.json"

PASSED=0
FAILED=0
ok()  { echo "  PASS: $*"; PASSED=$((PASSED+1)); }
bad() { echo "  FAIL: $*" >&2; FAILED=$((FAILED+1)); }
fail() { echo "FAIL: $*" >&2; exit 1; }

# 1) compile / syntax
[ -f "$FFD" ] || fail "floor-fill-driver.py not shipped at $FFD"
[ -f "$MGS" ] || fail "make-gap-from-staleness.py not shipped at $MGS"
[ -f "$MIG" ] || fail "migrate-existing-workforce.sh not shipped at $MIG"
python3 -m py_compile "$FFD" "$MGS" || fail "py_compile failed"
bash -n "$MIG" || fail "migrate-existing-workforce.sh failed bash -n"

# 2) make-gap shape
# Explicit template so TMPDIR is honored: macOS's bare `mktemp -d` resolves
# /var/folders/... via confstr and IGNORES TMPDIR, which makes it impossible to
# place the fixtures on a case-SENSITIVE volume locally. Scenario 5's duplicate-
# department check is only meaningful on a case-sensitive filesystem (Linux CI,
# every VPS box); on a case-insensitive one it passes trivially.
TMP="$(mktemp -d "${TMPDIR:-/tmp}/floor-fill-gap.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/verdict.json" <<'JSON'
{"items": [
  {"key": "sales/devils-advocate--sales",     "kind": "role",    "status": "MISSING"},
  {"key": "sales/closer",                      "kind": "role",    "status": "CURRENT"},
  {"key": "graphics/devils-advocate--graphics","kind": "role",    "status": "MISSING"},
  {"key": "graphics/SOP-DIU-615",              "kind": "sop",     "status": "MISSING"},
  {"key": "persona/growth-strategist",         "kind": "persona", "status": "MISSING"},
  {"key": "marketing",                         "kind": "dept",    "status": "STALE"}
]}
JSON

python3 "$MGS" "$TMP/verdict.json" --out "$TMP/gap.json" || fail "make-gap exited non-zero"

python3 - "$TMP/gap.json" <<'PY' || exit 1
import json, sys
gap = json.load(open(sys.argv[1]))
def check(cond, msg):
    if not cond:
        print(f"FAIL: {msg}\n  gap={json.dumps(gap)}", file=sys.stderr); sys.exit(1)
check(gap.get("sales", {}).get("missing_roles") == ["devils-advocate--sales"], "sales missing_roles wrong")
check("missing_sops" not in gap.get("sales", {}), "non-named-set sales should drop missing_sops key")
check(gap.get("graphics", {}).get("kind") == "named-set", "graphics should be named-set")
check(gap["graphics"]["missing_roles"] == ["devils-advocate--graphics"], "graphics missing_roles wrong")
check(gap["graphics"]["missing_sops"] == ["SOP-DIU-615.md"], "graphics missing_sops should append .md")
check("persona/growth-strategist" not in json.dumps(gap), "persona items must be dropped")
check("marketing" not in gap, "STALE / dept items must be dropped")
print("OK: make-gap-from-staleness produces the correct MISSING-only gap-map")
PY
ok "make-gap-from-staleness produces the correct MISSING-only gap-map"

[ -f "$DET" ] || fail "detect-stale-artifacts.py not shipped at $DET"
[ -f "$IDX" ] || fail "role-library _index.json not shipped at $IDX"
python3 -m py_compile "$DET" || fail "py_compile detect-stale-artifacts.py failed"

# Two REAL sales roles straight out of the shipped manifest, so the fixture is
# canonical rather than invented and the restored bytes are the real library's.
read -r R1 R2 <<<"$(python3 - "$IDX" <<'PY'
import json, sys
rs = [r["slug"] for r in json.load(open(sys.argv[1]))["roles"] if r.get("dept") == "sales"]
print(rs[0], rs[1])
PY
)"
[ -n "${R1:-}" ] && [ -n "${R2:-}" ] || fail "could not read two sales roles from the manifest"

# Build a workspace the way a real box has one: departments/sales/ materialized
# from the canonical library, plus the build-state artifactProvenance
# build-workforce.py writes on every build.
WS="$TMP/ws"
mkdir -p "$WS/departments"
cat > "$TMP/seed-gap.json" <<JSON
{"sales": {"kind": "roster", "missing_roles": ["$R1", "$R2"]}}
JSON
python3 "$FFD" --gap-file "$TMP/seed-gap.json" --workspace "$WS/departments" --apply >/dev/null 2>&1 \
  || fail "could not seed the fixture department from the canonical library"
python3 - "$IDX" "$WS" "$R1" "$R2" <<'PY' || fail "could not write the fixture build-state"
import json, sys
idx, ws, r1, r2 = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
shas = {f"{r['dept']}/{r['slug']}": r["content_sha"] for r in json.load(open(idx))["roles"]}
ap = {"manifestVersion": "fixture",
      "roles": {f"sales/{s}": {"source_content_sha": shas[f"sales/{s}"]} for s in (r1, r2)},
      "depts": {}, "sops": {}, "personas": {}}
open(ws + "/.workforce-build-state.json", "w").write(json.dumps({"artifactProvenance": ap}))
PY

status_of() {  # status_of <workspace> <key>
  python3 "$DET" --workspace "$1" --manifest "$IDX" --json 2>/dev/null \
    | python3 -c "
import json,sys
k=sys.argv[1]
for i in json.load(sys.stdin)['items']:
    if i['key']==k: print(i['status']); break
else: print('ABSENT-FROM-VERDICT')
" "$2"
}

echo ""
echo "=== Scenario 3 — role folder DELETED entirely: DETECTED as MISSING, then RESTORED ==="
[ "$(status_of "$WS" "sales/$R2")" = "CURRENT" ] \
  && ok "baseline: the built role is CURRENT before anything is deleted" \
  || bad "baseline wrong: sales/$R2 should be CURRENT on the seeded fixture"

# The real-world loss: a tree-reshuffling pass strips specialist role dirs.
R2_DIR="$(find "$WS/departments/sales" -maxdepth 1 -type d -name "*${R2}" | head -1)"
[ -n "$R2_DIR" ] || fail "fixture role folder for $R2 not found"
rm -rf "$R2_DIR"

ST="$(status_of "$WS" "sales/$R2")"
if [ "$ST" = "MISSING" ]; then
  ok "a role folder that is GONE from disk classifies MISSING (was CURRENT: the build record was trusted blind)"
else
  bad "absence NOT detected — sales/$R2 classified $ST while its folder does not exist"
fi

python3 "$DET" --workspace "$WS" --manifest "$IDX" --json > "$TMP/verdict2.json" 2>/dev/null
python3 "$MGS" "$TMP/verdict2.json" --out "$TMP/gap2.json" || fail "make-gap failed on the deleted-folder verdict"
if python3 -c "
import json,sys
g=json.load(open('$TMP/gap2.json'))
sys.exit(0 if '$R2' in g.get('sales',{}).get('missing_roles',[]) else 1)
"; then
  ok "the deleted role reaches the gap-map floor-fill-driver.py consumes"
else
  bad "gap-map does not contain the deleted role — floor-fill would have nothing to do"
fi

python3 "$FFD" --gap-file "$TMP/gap2.json" --workspace "$WS/departments" --apply >/dev/null 2>&1
FFRC=$?
RESTORED="$(find "$WS/departments/sales" -maxdepth 1 -type d -name "*${R2}" | head -1)"
if [ "$FFRC" -eq 0 ] && [ -n "$RESTORED" ] && [ -f "$RESTORED/how-to.md" ]; then
  ok "the deleted role folder was RESTORED by floor-fill-driver.py (rc 0)"
else
  bad "role folder NOT restored (driver rc=$FFRC, dir='${RESTORED:-none}')"
fi
BYTES=$(wc -c < "$RESTORED/how-to.md" 2>/dev/null || echo 0)
if [ "$BYTES" -ge 3072 ]; then
  ok "restored how-to.md is real canonical library content ($BYTES bytes, >= the 3072B floor)"
else
  bad "restored how-to.md is only $BYTES bytes — stub/fabricated content, not the library"
fi

echo ""
echo "=== Scenario 4 — a gap the canonical library CANNOT fill exits 3, never 0 ==="
echo '{"sales": {"kind": "roster", "missing_roles": ["no-such-role-exists-in-the-library"]}}' > "$TMP/gap-bad.json"
python3 "$FFD" --gap-file "$TMP/gap-bad.json" --workspace "$WS/departments" --apply >"$TMP/bad.json" 2>"$TMP/bad.err"
BADRC=$?
if [ "$BADRC" -eq 3 ]; then
  ok "unfillable gap -> rc 3 (loud), not a silent 0"
else
  bad "unfillable gap returned rc $BADRC — a detected gap went unfilled and the driver reported success"
fi
grep -q "FAILED" "$TMP/bad.err" \
  && ok "a loud FAILED line is printed to stderr for the unfilled gap" \
  || bad "no loud failure line on stderr"
if [ -z "$(find "$WS/departments/sales" -maxdepth 1 -name '*no-such-role*')" ]; then
  ok "nothing was stubbed or fabricated for the unfillable role"
else
  bad "the driver fabricated a folder for a role the library does not carry"
fi

echo ""
echo "=== Scenario 5 — case-drifted department folder resolves to the REAL directory ==="
# On a case-SENSITIVE filesystem (Linux CI, every VPS box) `Sales` and `sales`
# are different directories; the pre-fix driver created the second one and
# filled it, leaving the real department short. The assertion is layout-based
# rather than case-based so it is equally valid on macOS's case-INSENSITIVE
# volume: exactly ONE department directory may exist afterwards.
CD="$TMP/casedrift/departments"
mkdir -p "$CD/Sales/01-seed"
printf 'seed\n' > "$CD/Sales/01-seed/how-to.md"
cat > "$TMP/gap-case.json" <<JSON
{"sales": {"kind": "roster", "missing_roles": ["$R1"]}}
JSON
python3 "$FFD" --gap-file "$TMP/gap-case.json" --workspace "$CD" --apply >/dev/null 2>&1
NDIRS=$(find "$CD" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
if [ "$NDIRS" -eq 1 ]; then
  ok "no duplicate department directory was created for the case-drifted name"
else
  bad "$NDIRS department directories exist — the driver fabricated a duplicate instead of resolving 'Sales'"
fi
if [ -n "$(find "$CD/Sales" -maxdepth 1 -type d -name "*${R1}")" ]; then
  ok "the restored role landed inside the REAL 'Sales' department"
else
  bad "the restored role did not land in the real 'Sales' department"
fi

echo ""
echo "=== Scenario 6 — healthy box: no false failure, nothing clobbered ==="
BEFORE="$(cd "$WS/departments" && find . -type f | sort | xargs shasum 2>/dev/null | shasum | awk '{print $1}')"
python3 "$DET" --workspace "$WS" --manifest "$IDX" --json > "$TMP/verdict3.json" 2>/dev/null
python3 "$MGS" "$TMP/verdict3.json" --out "$TMP/gap3.json" || fail "make-gap failed on the healthy verdict"
if python3 -c "
import json,sys
g=json.load(open('$TMP/gap3.json'))
sys.exit(0 if '$R2' not in g.get('sales',{}).get('missing_roles',[]) else 1)
"; then
  ok "the restored role is no longer reported MISSING (the loop actually closed)"
else
  bad "the restored role is STILL reported MISSING after being filled"
fi
# Re-run the SAME gap that was already satisfied: must be a clean no-op.
python3 "$FFD" --gap-file "$TMP/gap2.json" --workspace "$WS/departments" --apply >"$TMP/rerun.json" 2>&1
RRC=$?
AFTER="$(cd "$WS/departments" && find . -type f | sort | xargs shasum 2>/dev/null | shasum | awk '{print $1}')"
[ "$RRC" -eq 0 ] \
  && ok "re-running an already-satisfied gap is rc 0 (no false failure on a healthy box)" \
  || bad "re-run on a healthy box returned rc $RRC"
[ "$BEFORE" = "$AFTER" ] \
  && ok "the department tree is byte-identical after the idempotent re-run — nothing clobbered" \
  || bad "the re-run mutated existing files"

echo ""
echo "=== Scenario 7 — dry run (no --apply) mutates nothing ==="
DR="$TMP/dryrun/departments"
mkdir -p "$DR"
python3 "$FFD" --gap-file "$TMP/seed-gap.json" --workspace "$DR" >/dev/null 2>&1
if [ "$(find "$DR" -mindepth 1 | wc -l | tr -d ' ')" -eq 0 ]; then
  ok "dry run created nothing on disk"
else
  bad "dry run wrote to disk: $(find "$DR" -mindepth 1 | head -3 | tr '\n' ' ')"
fi

echo ""
echo "=== Scenario 8 — migrate Step 2b PROPAGATES the driver's failure (static) ==="
# The driver returning 3 only matters if something reads it. Step 2b used to run
# `python3 ... | tee -a "$LOG" || log "completed with warnings"`, which threw the
# rc away twice: `tee`'s status masks python3's, and the `||` swallowed even
# that. FINAL_RC was then set exclusively from qc-completeness, so an unfilled
# floor gap could never make the migration exit non-zero — and update-skills.sh
# maps a non-zero migration to _D2_MIGRATE_STATUS=fail, which is what prints the
# WORKFORCE-PROVISIONING INCOMPLETE block. Running the real migration here is not
# an option (it targets the live $HOME workspace), so assert the wiring
# statically, the same way the D15 both-paths guard does.
grep -q 'FF_RC=\${PIPESTATUS\[0\]}' "$MIG" \
  && ok "Step 2b captures the driver's own exit code via PIPESTATUS (not tee's)" \
  || bad "Step 2b does not capture the driver's rc via PIPESTATUS — the failure is swallowed by the pipe"
grep -q 'FF_UNFILLED=1' "$MIG" \
  && ok "Step 2b latches an unfilled floor gap (FF_UNFILLED)" \
  || bad "Step 2b has no unfilled-gap latch"
grep -q 'FF_UNFILLED:-0' "$MIG" \
  && ok "the unfilled-gap latch reaches FINAL_RC (a non-zero migration exit)" \
  || bad "FF_UNFILLED never reaches FINAL_RC — the migration would still exit 0 on an unfilled floor gap"
grep -q 'sys.exit(main())' "$FFD" \
  && ok "the driver's main() return value actually becomes its exit status" \
  || bad "floor-fill-driver.py calls main() without sys.exit() — every run exits 0 regardless"

echo ""
echo "──────────────────────────────────────────────"
echo "  floor-fill-gap: $PASSED passed, $FAILED failed"
echo "──────────────────────────────────────────────"
if [ "$FAILED" -ne 0 ]; then
  echo "FAIL: floor-fill-gap.test.sh — $FAILED check(s) failed" >&2
  exit 1
fi
echo "PASS: floor-fill-gap.test.sh — scripts compile, gap-map shape correct, and the DELETE -> DETECT -> RESTORE loop closes"
