#!/usr/bin/env bash
# test-gates-follow-live-tree.sh — BU-58 acceptance (WF-078, WF-124).
#
# Proves, against the SHIPPED gates, that all three measure the LIVE departments
# tree — the folder _qc_paths.resolve_live_departments_dir() names (BU-103) —
# instead of the recorded build-state companyRoot:
#   1. verify-library-gate.sh sets SOP-NEEDED.json and sop-research-manifest.json
#      from the LIVE company folder (the parent of that tree) when the files are
#      there, and falls back to its old lookups only when they are not;
#   2. verify-wiring.sh puts that folder FIRST in its candidate list and still
#      SCORES it (it is a candidate, never a blind acceptance);
#   3. prove-zhe.py discovers departments on that tree, and its company-dir
#      resolution tries that folder's parent first.
#
# Fixture A is the box of BU-103 / test_skill23_build_nondestructive.py L313-347:
#   a complete workspace tree with the dept agents registered on it, plus a
#   SPARSE second copy recorded as companyRoot. All three must measure the
#   workspace tree, and the sparse copy's open SOP-NEEDED record must be ignored.
# Fixture B is BU-103's launch layout: departments exist ONLY under a company
#   folder outside workspace/, recorded in state (no agents), with a
#   SOP-NEEDED.json holding open_count 1 there. The library gate must exit 10;
#   the wiring check must choose that tree with a non-zero score; the prover must
#   report the departments present.
#
# Every scenario runs against a sandboxed HOME with fixture trees; no box, fleet
# or live database is read or written. The gates' own exit codes after the
# measured assertion (role/sop verdicts of an empty fixture) are not asserted.
#
# Exit 0 = every assertion passed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WIRING="$SCRIPT_DIR/verify-wiring.sh"
LIBRARY="$SCRIPT_DIR/verify-library-gate.sh"
PROVER="$SCRIPT_DIR/prove-zhe.py"
QCPATHS="$SCRIPT_DIR/_qc_paths.py"

for f in "$WIRING" "$LIBRARY" "$PROVER" "$QCPATHS"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done
bash -n "$WIRING"  || { echo "FAIL: verify-wiring.sh does not parse" >&2; exit 1; }
bash -n "$LIBRARY" || { echo "FAIL: verify-library-gate.sh does not parse" >&2; exit 1; }
python3 - "$PROVER" <<'PY' || { echo "FAIL: prove-zhe.py does not parse" >&2; exit 1; }
import ast, sys
ast.parse(open(sys.argv[1], encoding="utf-8").read())
PY

PASSED=0
FAILED=0
ok()   { echo "  PASS: $*"; PASSED=$((PASSED+1)); }
bad()  { echo "  FAIL: $*" >&2; FAILED=$((FAILED+1)); }

# Explicit template so TMPDIR is honoured on macOS (bare mktemp -d ignores it).
TMP="$(mktemp -d "${TMPDIR:-/tmp}/gates-live-tree.XXXXXX")" || exit 1
trap 'rm -rf "$TMP"' EXIT
TMP="$(cd "$TMP" && pwd -P)"

# detect_platform aborts when it cannot tell the platform; the sandboxed HOME
# carries ~/.openclaw, and the documented override is set too.
export OPENCLAW_PLATFORM="${OPENCLAW_PLATFORM:-mac}"

A_HOME="$TMP/a"
B_HOME="$TMP/b"
A_WS="$A_HOME/.openclaw/workspace"
B_OC="$B_HOME/.openclaw"
B_WS="$B_OC/workspace"
A_SPARSE="$A_HOME/Downloads/openclaw-master-files/zero-human-company/acme"
B_COMPANY="$B_HOME/zero-human-company/acme"

# ---------------------------------------------------------------- fixtures ----
build_fixture_a() {
  python3 - "$A_HOME" <<'PY'
import json, sys
from pathlib import Path

home = Path(sys.argv[1])
oc = home / ".openclaw"
ws = oc / "workspace"
live = ws / "departments"
sparse = home / "Downloads" / "openclaw-master-files" / "zero-human-company" / "acme"

for slug in ("marketing", "sales"):
    (live / slug).mkdir(parents=True)
    (live / slug / "SOUL.md").write_text("complete\n")
for slug in ("marketing", "sales", "support"):
    (sparse / "departments" / slug).mkdir(parents=True)

(ws / ".workforce-build-state.json").write_text(json.dumps({
    "interviewComplete": True,
    "companyRoot": str(sparse),          # the SPARSE copy — must never win
    "companySlug": "acme",
    "departments": [{"slug": "marketing", "status": "done"},
                    {"slug": "sales", "status": "done"}],
}))
(oc / "openclaw.json").write_text(json.dumps({"agents": {"entries": {
    "main": {"workspace": str(ws)},
    "dept-marketing": {"workspace": str(live / "marketing")},
    "dept-sales": {"workspace": str(live / "sales")},
    "dept-support": {"workspace": str(home / "deleted" / "support")},
}}}))

# Both company folders carry a SOP-NEEDED.json; ONLY the sparse one is open, and
# ONLY the sparse one carries a research manifest. Measuring the workspace tree
# therefore means "SOP-NEEDED GATE PASS" and "no manifest found".
(ws / "SOP-NEEDED.json").write_text(json.dumps({"open_count": 0, "records": []}))
(sparse / "SOP-NEEDED.json").write_text(json.dumps(
    {"open_count": 1, "records": [
        {"id": "SN-A1", "role": "analyst", "department": "support",
         "status": "open"}]}))
(sparse / "sop-research-manifest.json").write_text(json.dumps({"departments": []}))
PY
}

build_fixture_b() {
  python3 - "$B_HOME" <<'PY'
import json, sys
from pathlib import Path

home = Path(sys.argv[1])
oc = home / ".openclaw"
ws = oc / "workspace"
ws.mkdir(parents=True)
company = home / "zero-human-company" / "acme"
for slug in ("marketing", "sales", "support"):
    (company / "departments" / slug).mkdir(parents=True)

# Launch layout: the departments live ONLY under the company folder; state records
# that folder. No openclaw.json yet, so the library gate's ZHE leg is skipped.
(ws / ".workforce-build-state.json").write_text(json.dumps({
    "companyRoot": str(company),
    "companySlug": "acme",
    "departments": [{"slug": "marketing", "status": "done"},
                    {"slug": "sales", "status": "done"},
                    {"slug": "support", "status": "done"}],
}))
(company / "SOP-NEEDED.json").write_text(json.dumps(
    {"open_count": 1, "records": [
        {"id": "SN-B1", "role": "analyst", "department": "marketing",
         "status": "open"}]}))
PY
}

# The prover needs an OpenClaw root and a completed interview to run check (a).
make_fixture_b_provable() {
  python3 - "$B_HOME" <<'PY'
import json, sys
from pathlib import Path

home = Path(sys.argv[1])
oc = home / ".openclaw"
ws = oc / "workspace"
(oc / "openclaw.json").write_text(json.dumps(
    {"agents": {"defaults": {"workspace": str(ws)}, "list": []}}))
state = json.loads((ws / ".workforce-build-state.json").read_text())
state["interviewComplete"] = True
(ws / ".workforce-build-state.json").write_text(json.dumps(state))
PY
}

# ------------------------------------------------------------------ runners ---
run_gate() {  # run_gate <home> <outfile> <receipts> -- <script> [args...]
  local home="$1" out="$2" receipts="$3"; shift 3
  [ "${1:-}" = "--" ] && shift
  env -i HOME="$home" OPENCLAW_PLATFORM="$OPENCLAW_PLATFORM" \
      PATH="$PATH" ZHE_RECEIPTS_DIR="$receipts" \
      bash "$@" > "$out" 2>&1
  return $?
}

run_prover() {  # run_prover <home> <oc-root> <receipts>
  env -i HOME="$1" OPENCLAW_PLATFORM="$OPENCLAW_PLATFORM" PATH="$PATH" \
      ZHE_RECEIPTS_DIR="$3" \
      python3 "$PROVER" --local "$2" > "$TMP/prover.log" 2>&1
}

# prints the departments the prover's check (a) found, newest receipt first
prover_present() {
  python3 - "$1" <<'PY'
import glob, json, os, sys
files = sorted(glob.glob(os.path.join(sys.argv[1], "*.json")),
               key=os.path.getmtime)
check = {}
if files:
    check = json.load(open(files[-1])).get("checks", {}).get(
        "floor_depts_registered_as_agents", {})
print(" ".join(check.get("departments_present") or []))
PY
}

has()   { grep -qF -- "$2" "$1"; }
hasnt() { ! grep -qF -- "$2" "$1"; }
assert_has()   { local f="$1" s="$2" l="$3"; if has "$f" "$s";   then ok "$l"; else bad "$l (missing: $s)"; sed -n '1,20p' "$f" | sed 's/^/    > /' >&2; fi; }
assert_hasnt() { local f="$1" s="$2" l="$3"; if hasnt "$f" "$s"; then ok "$l"; else bad "$l (should not contain: $s)"; fi; }

# ==============================================================================
echo "=== B1: launch layout — the library gate reads SOP-NEEDED.json from the LIVE company folder (rc 10) ==="
build_fixture_b
run_gate "$B_HOME" "$TMP/lib-b.log" "$TMP/zhe-lib-b" -- "$LIBRARY"
LIB_EXIT=$?
if [ "$LIB_EXIT" = "10" ]; then
  ok "library gate exits 10 on the live company folder's open SOP-NEEDED record"
else
  bad "library gate exit $LIB_EXIT, expected 10"
  sed -n '1,25p' "$TMP/lib-b.log" | sed 's/^/    > /' >&2
fi
assert_has "$TMP/lib-b.log" "SOP-NEEDED GATE FAIL" "the SOP-NEEDED gate ran and failed"
assert_has "$TMP/lib-b.log" "$B_COMPANY/SOP-NEEDED.json" "it names the live company folder's file"

echo "=== B2: launch layout — the wiring check puts the live tree first and scores it ==="
run_gate "$B_HOME" "$TMP/wiring-b.log" "$TMP/zhe-wiring-b" -- "$WIRING"
assert_has "$TMP/wiring-b.log" "candidate tree: $B_COMPANY/departments" \
  "the live tree is printed as a candidate"
assert_has "$TMP/wiring-b.log" "Departments tree: $B_COMPANY/departments" \
  "the live tree is the tree chosen"
assert_has "$TMP/wiring-b.log" "resolved 3/3 named dept(s)" \
  "the live tree scored all three named departments (non-zero)"

echo "=== B3: launch layout — the prover reports the live departments present ==="
make_fixture_b_provable
rm -rf "$TMP/zhe-b"; mkdir -p "$TMP/zhe-b"
run_prover "$B_HOME" "$B_OC" "$TMP/zhe-b"
B_PRESENT="$(prover_present "$TMP/zhe-b")"
if [ "$B_PRESENT" = "marketing sales support" ]; then
  ok "check (a) reports marketing sales support"
else
  bad "check (a) departments present: '$B_PRESENT' (expected 'marketing sales support')"
  sed -n '1,25p' "$TMP/prover.log" | sed 's/^/    > /' >&2
fi

echo "=== A1: complete workspace tree — the wiring check measures the workspace tree ==="
build_fixture_a
run_gate "$A_HOME" "$TMP/wiring-a.log" "$TMP/zhe-wiring-a" -- "$WIRING"
assert_has "$TMP/wiring-a.log" "Departments tree: $A_WS/departments" \
  "the workspace tree is the tree chosen"
assert_has "$TMP/wiring-a.log" "resolved 2/2 named dept(s)" \
  "the workspace tree scored both named departments"
assert_hasnt "$TMP/wiring-a.log" "$A_SPARSE" \
  "the sparse companyRoot copy is never a candidate"

echo "=== A2: complete workspace tree — the prover measures the workspace tree ==="
rm -rf "$TMP/zhe-a"; mkdir -p "$TMP/zhe-a"
run_prover "$A_HOME" "$A_HOME/.openclaw" "$TMP/zhe-a"
A_PRESENT="$(prover_present "$TMP/zhe-a")"
if [ "$A_PRESENT" = "marketing sales" ]; then
  ok "check (a) reports marketing sales (the sparse-only 'support' is absent)"
else
  bad "check (a) departments present: '$A_PRESENT' (expected 'marketing sales')"
  sed -n '1,25p' "$TMP/prover.log" | sed 's/^/    > /' >&2
fi

echo "=== A3: complete workspace tree — the library gate measures the workspace tree ==="
run_gate "$A_HOME" "$TMP/lib-a.log" "$TMP/zhe-lib-a" -- "$LIBRARY"
assert_has "$TMP/lib-a.log" "SOP-NEEDED GATE PASS" \
  "the workspace folder's closed SOP-NEEDED record is the one read"
assert_hasnt "$TMP/lib-a.log" "SOP-NEEDED GATE FAIL" \
  "the sparse copy's open record was not read"
assert_has "$TMP/lib-a.log" "no sop-research-manifest.json found" \
  "no manifest in the workspace folder, and the sparse copy's manifest was not read"

echo "============================================"
echo "test-gates-follow-live-tree: PASS=$PASSED FAIL=$FAILED"
echo "============================================"
[ "$FAILED" -eq 0 ] || exit 1
exit 0
