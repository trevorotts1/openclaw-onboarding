#!/usr/bin/env bash
# qc-departments-tree-resolution.test.sh
#
# THE DEFECT (v20.0.79): the QC checker measured a DIFFERENT departments tree
# than the floor-fill repairer writes to, so it reported floor departments
# MISSING that were present on disk the whole time.
#
#   REPAIRER writes   <workspace>/departments
#                     (detect-stale-artifacts.py:326 departments_root =
#                      Path(workspace)/"departments"; floor-fill-driver.py:170-171;
#                      migrate-existing-workforce.sh:138-140)
#   CHECKER read      ~/clawd/zero-human-company/<slug>/departments
#                     (_qc_company_info.py — every candidate was
#                      zero-human-company-shaped, the live tree was never a
#                      candidate at all)
#
# Measured live on 18 reachable fleet boxes: 13 had the two pointed at different
# directories, and on 10 of those the gate failed with "missing mandatory:
# funnels" while funnels/ existed in the repairer's tree on ALL of them.
#
# Two more defects in the same resolver, both measured on real boxes:
#   * the non-standard-layout fallback accepted a COMPANY dir as the departments
#     dir with no test at all (its "Check if it contains role-like subdirs"
#     comment described a check that was never written), so a company dir
#     holding one role folder + departments.json became a 2-entry "departments
#     tree" and the whole floor read as missing;
#   * the per-company subdir scan resolved symlinks WITHOUT re-applying
#     _is_template_path(), so a company entry symlinked into the Downloads
#     template tree made QC audit the shipped TEMPLATE instead of the client's
#     workforce.
#
# Scenario 3 is the anti-false-positive control: a department that is GENUINELY
# absent must still be reported MISSING. A fix that makes the gate stop
# complaining by loosening it fails this suite.
#
# Every scenario runs against a sandboxed HOME with fixture trees. No fleet box
# is read or written.

set -uo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
TESTS_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/../.." && pwd)"
SCRIPTS="$REPO_ROOT/23-ai-workforce-blueprint/scripts"

QCI="$SCRIPTS/_qc_company_info.py"
FLOOR="$SCRIPTS/department-floor.py"
PATHS="$SCRIPTS/_qc_paths.py"
FFD="$SCRIPTS/floor-fill-driver.py"

# detect_platform aborts with "Cannot detect OpenClaw platform" when neither
# /data/.openclaw nor ~/.openclaw exists. Each scenario builds ~/.openclaw inside
# its sandboxed HOME, but set the documented override too so a runner with no
# platform of its own still resolves. Respect an existing value.
export OPENCLAW_PLATFORM="${OPENCLAW_PLATFORM:-mac}"

PASSED=0
FAILED=0
ok()   { echo "  PASS: $*"; PASSED=$((PASSED+1)); }
bad()  { echo "  FAIL: $*" >&2; FAILED=$((FAILED+1)); }
fail() { echo "FAIL: $*" >&2; exit 1; }

for f in "$QCI" "$FLOOR" "$PATHS"; do
  [ -f "$f" ] || fail "not shipped: $f"
done
python3 -m py_compile "$QCI" "$FLOOR" "$PATHS" || fail "py_compile failed"

# Explicit template so TMPDIR is honored: macOS's bare `mktemp -d` resolves
# /var/folders/... via confstr and IGNORES TMPDIR, which makes it impossible to
# place fixtures on a case-SENSITIVE volume locally. Scenario 5 is only
# meaningful on a case-sensitive filesystem (Linux CI, every VPS box); on a
# case-insensitive one it passes trivially.
TMP="$(mktemp -d "${TMPDIR:-/tmp}/qc-dept-tree.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
# Canonicalize: the resolver under test calls Path.resolve(), so on macOS it
# returns /private/var/... where mktemp handed back /var/... . A TMPDIR with a
# trailing slash also yields a doubled separator. Compare like with like.
TMP="$(cd "$TMP" && pwd -P)"

MANDATORY="marketing sales billing-finance customer-support web-development funnels
app-development graphics video audio research communications crm openclaw-maintenance
legal social-media paid-advertisement personal-assistant general-task
project-architecture-office bugs healer quality-control"
UNIVERSAL="presentations scheduling-dispatch logistics-fulfillment engineering
account-management podcast"

# Build a departments tree holding the full floor, minus any dept named in $2.
make_floor_tree() {
  local dir="$1" omit="${2:-}"
  mkdir -p "$dir"
  local d
  for d in $MANDATORY $UNIVERSAL; do
    [ "$d" = "$omit" ] && continue
    mkdir -p "$dir/$d"
  done
}

# Resolve the departments_dir exactly the way qc-completeness.sh does.
resolve_dd() {
  local home="$1"
  HOME="$home" SCRIPT_DIR="$SCRIPTS" python3 "$QCI" 2>/dev/null \
    | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("departments_dir") or "")
except Exception: print("")'
}

# missing_mandatory for a departments dir, via the real floor module.
missing_mandatory() {
  local home="$1" dd="$2"
  HOME="$home" python3 "$FLOOR" --json --departments-dir "$dd" 2>/dev/null \
    | python3 -c 'import json,sys
try: print(",".join(json.load(sys.stdin).get("missing_mandatory") or []))
except Exception: print("PARSE-ERROR")'
}

echo "=== S1: live tree wins over a divergent legacy tree (the ~10-box defect) ==="
H1="$TMP/s1"
mkdir -p "$H1/.openclaw/workspace"
make_floor_tree "$H1/.openclaw/workspace/departments"                 # HAS funnels
make_floor_tree "$H1/clawd/zero-human-company/acme/departments" funnels  # lacks funnels
DD1="$(resolve_dd "$H1")"
echo "  resolved: ${DD1:-<none>}"
if [ "$DD1" = "$H1/.openclaw/workspace/departments" ]; then
  ok "resolved the tree the repairer writes to"
else
  bad "resolved '$DD1', expected the live workspace tree $H1/.openclaw/workspace/departments"
fi
MM1="$(missing_mandatory "$H1" "$DD1")"
if [ -z "$MM1" ]; then
  ok "funnels reported PRESENT (missing_mandatory empty)"
else
  bad "missing_mandatory='$MM1' — a department present in the live tree read as missing"
fi

echo "=== S2: the both-trees shape — funnels in BOTH trees ==="
H2="$TMP/s2"
mkdir -p "$H2/.openclaw/workspace"
make_floor_tree "$H2/.openclaw/workspace/departments"
make_floor_tree "$H2/clawd/zero-human-company/acme/departments"
DD2="$(resolve_dd "$H2")"
echo "  resolved: ${DD2:-<none>}"
if [ "$DD2" = "$H2/.openclaw/workspace/departments" ]; then
  ok "resolved the live tree even when both trees are complete"
else
  bad "resolved '$DD2', expected $H2/.openclaw/workspace/departments"
fi
MM2="$(missing_mandatory "$H2" "$DD2")"
if [ -z "$MM2" ]; then
  ok "funnels reported PRESENT"
else
  bad "missing_mandatory='$MM2'"
fi

echo "=== S3: ANTI-FALSE-POSITIVE — a genuinely absent department stays MISSING ==="
H3="$TMP/s3"
mkdir -p "$H3/.openclaw/workspace"
make_floor_tree "$H3/.openclaw/workspace/departments" funnels   # funnels really absent
DD3="$(resolve_dd "$H3")"
echo "  resolved: ${DD3:-<none>}"
MM3="$(missing_mandatory "$H3" "$DD3")"
# TIGHTENED: assert the tree actually resolved AND that funnels is the ONLY
# missing department. Against pristine origin/main this scenario "passed"
# vacuously — the resolver found nothing, so all 23 mandatory departments read
# as missing and funnels happened to be among them. A test that a broken
# resolver satisfies proves nothing, so require the exact verdict.
if [ -z "$DD3" ]; then
  bad "no departments dir resolved — this scenario must not pass vacuously"
elif [ "$MM3" = "funnels" ]; then
  ok "genuinely-absent funnels reported missing, and ONLY funnels (missing_mandatory='$MM3')"
else
  bad "expected missing_mandatory to be exactly 'funnels', got '$MM3'"
fi

echo "=== S4: both platform layouts resolve correctly (Mac \$HOME and Docker/VPS /data) ==="
S4="$TMP/s4"
mkdir -p "$S4/data/.openclaw" "$S4/home"
LAYOUT="$(python3 - "$SCRIPTS" "$S4" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from _qc_paths import live_departments_dir
base = Path(sys.argv[2])
print(live_departments_dir(data_openclaw=base / "data" / ".openclaw"))
print(live_departments_dir(data_openclaw=base / "absent", home=base / "home"))
PY
)"
VPS_DD="$(echo "$LAYOUT" | sed -n 1p)"
MAC_DD="$(echo "$LAYOUT" | sed -n 2p)"
if [ "$VPS_DD" = "$S4/data/.openclaw/workspace/departments" ]; then
  ok "Docker/VPS layout -> $VPS_DD"
else
  bad "Docker/VPS layout resolved '$VPS_DD'"
fi
if [ "$MAC_DD" = "$S4/home/.openclaw/workspace/departments" ]; then
  ok "Mac / \$HOME-rooted container layout -> $MAC_DD"
else
  bad "Mac layout resolved '$MAC_DD'"
fi
# Lockstep: the checker's rule must stay identical to the repairer's. If someone
# changes floor-fill-driver.py's /data probe, this catches the divergence.
if grep -q '/data/\.openclaw' "$FFD" && grep -q '/data/\.openclaw' "$PATHS"; then
  ok "checker and repairer share the /data/.openclaw precedence rule"
else
  bad "the /data/.openclaw precedence rule is not present in both the repairer and the checker"
fi

echo "=== S5: case-drifted department name on a case-SENSITIVE path ==="
H5="$TMP/s5"
mkdir -p "$H5/.openclaw/workspace"
make_floor_tree "$H5/.openclaw/workspace/departments" sales
mkdir -p "$H5/.openclaw/workspace/departments/Sales"     # capital S only
DD5="$(resolve_dd "$H5")"
MM5="$(missing_mandatory "$H5" "$DD5")"
if [ -n "$DD5" ] && [ "$MM5" = "" ]; then
  ok "case-drifted 'Sales' counted as sales (missing_mandatory empty)"
else
  bad "case drift not absorbed: missing_mandatory='$MM5' (resolved '$DD5')"
fi

echo "=== S6: a COMPANY dir with no departments/ is not accepted as one ==="
H6="$TMP/s6"
mkdir -p "$H6/.openclaw"                       # platform marker, but NO workspace tree
mkdir -p "$H6/clawd/zero-human-company/acme/master-orchestrator"
echo '{}' > "$H6/clawd/zero-human-company/acme/departments.json"
DD6="$(resolve_dd "$H6")"
echo "  resolved: ${DD6:-<none>}"
if [ "$DD6" = "$H6/clawd/zero-human-company/acme" ]; then
  bad "company dir accepted AS the departments dir — the whole floor would read missing"
else
  ok "company dir with no departments/ rejected (resolved '${DD6:-<none>}')"
fi

echo "=== S7: a company entry symlinked into the Downloads template tree ==="
H7="$TMP/s7"
mkdir -p "$H7/.openclaw"                       # platform marker, NO workspace tree
TPL="$H7/Downloads/openclaw-master-files/zero-human-company/acme"
make_floor_tree "$TPL/departments"
mkdir -p "$H7/clawd/zero-human-company"
ln -s "$TPL" "$H7/clawd/zero-human-company/acme"
DD7="$(resolve_dd "$H7")"
echo "  resolved: ${DD7:-<none>}"
case "$DD7" in
  *openclaw-master-files*) bad "resolved INTO the shipped template tree: $DD7" ;;
  *)                       ok "template tree not audited (resolved '${DD7:-<none>}')" ;;
esac

echo
echo "passed=$PASSED failed=$FAILED"
[ "$FAILED" -eq 0 ] || exit 1
echo "ALL PASS"
