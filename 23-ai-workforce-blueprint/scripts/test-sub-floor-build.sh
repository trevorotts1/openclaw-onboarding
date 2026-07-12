#!/usr/bin/env bash
# test-sub-floor-build.sh — P2-05 step 3: fewer-than-floor is LEGAL and correct
# end-to-end, and the naming map fails CLOSED to the FULL floor.
#
# PART A — SUB-FLOOR JOIN (a build with 3 declined floor departments):
#   * department-floor.evaluate_floor honors the 3 provenanced declines: rc=0
#     (floor MET), declined=3, expected_floor_count = 28 − 3 = 25.
#   * the durable chosen artifact <company>/departments.json == the chosen 25.
#   * chosen == provisioned == displayed: prove-board-join.py rc=0 on a company
#     whose tree + board carry exactly those 25 (+ the CEO column).
#
# PART B — FAIL-CLOSED (OQ-7): an UNREADABLE naming map degrades to the FULL 28
#   floor (22 mandatory + 6 universal-primary), NEVER fewer. A declines file can
#   shrink the floor; a broken map can NOT.
#
# Both parts exercise the REAL modules (department-floor.py, canonical_decline.py,
# prove-board-join.py). No mocks of the logic under test.
#
# Exit 0 = all pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROVE="$SCRIPT_DIR/prove-board-join.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

TMPD="$(mktemp -d)"; trap 'rm -rf "$TMPD"' EXIT

# ── Build the sub-floor fixture: chosen = 28 floor slugs − 3 declines = 25 ─────
FIXTURE_JSON="$(python3 - "$SCRIPT_DIR" "$TMPD" <<'PYEOF'
import sys, os, json, sqlite3, importlib.util
from pathlib import Path

scripts_dir, tmpd = sys.argv[1], sys.argv[2]

def load(mod, fn):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(scripts_dir, fn))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

lc = load("lc", "list-canonical-departments.py")
nm = lc.load_naming_map()
mandatory = [d["id"] for d in lc.get_mandatory(nm)]           # 22
universal = [d["id"] for d in lc.get_universal_primaries(nm)] # 6
floor = mandatory + universal
assert len(floor) == 28, f"expected 28 floor slugs, got {len(floor)}"

# Decline 3 FLOOR departments (2 mandatory + 1 universal-primary).
declines = ["app-development", "video", "account-management"]
for d in declines:
    assert d in floor, f"{d} not a floor dept"
chosen = [s for s in floor if s not in declines]             # 25
assert len(chosen) == 25

company_dir = Path(tmpd) / "acme"
dep_dir = company_dir / "departments"
dep_dir.mkdir(parents=True)

# LAYER 2 provisioned: one dir per chosen dept + the master-orchestrator (CEO).
for s in chosen:
    (dep_dir / s).mkdir()
    (dep_dir / s / "how-to.md").write_text(f"# {s}\n")
(dep_dir / "master-orchestrator").mkdir()

# LAYER 1 chosen artifact: <company>/departments.json (CEO prepended, as build-workforce does).
artifact = [{"slug": "ceo", "name": "CEO", "workspacePath": "departments/master-orchestrator"}]
artifact += [{"slug": s, "name": s} for s in chosen]
(company_dir / "departments.json").write_text(json.dumps(artifact, indent=2))

# LAYER 3 displayed: a minimal mission-control.db with a workspaces table.
db = company_dir / "mission-control.db"
conn = sqlite3.connect(str(db))
conn.execute("CREATE TABLE workspaces (slug TEXT, name TEXT, company_id TEXT)")
conn.execute("INSERT INTO workspaces VALUES ('ceo','CEO','acme')")
for s in chosen:
    conn.execute("INSERT INTO workspaces VALUES (?,?,?)", (s, s, "acme"))
conn.commit(); conn.close()

# Build-state carrying the 3 PROVENANCED declines (object form).
bs = {"canonicalReconciliation": {"ownerDeclineConfirmed": False, "decisions": {}}}
for d in declines:
    bs["canonicalReconciliation"]["decisions"][d] = {
        "decision": "no", "source": "owner-interview",
        "decidedAt": "2026-07-12T00:00:00Z", "decidedBy": "owner-acme",
        "sessionId": "sess1", "lossWarning": "test", "lossWarningAck": True,
    }
(company_dir / "build-state.json").write_text(json.dumps(bs, indent=2))

# ── PART A assertions via the REAL department-floor.py ────────────────────────
df = load("df", "department-floor.py")
v = df.evaluate_floor(departments_dir=dep_dir, build_state=bs)
res = {"company_dir": str(company_dir), "db": str(db), "dep_dir": str(dep_dir)}
res["floor_rc"] = v["rc"]
res["declined_count"] = len(v["declined"])
res["expected_floor_count"] = v["expected_floor_count"]
res["chosen_source"] = v["chosen_departments_source"]
# The durable chosen artifact carries the 25 chosen depts PLUS the CEO column
# (build-workforce always prepends "ceo"); compare against that exact set.
res["chosen_from_floor"] = sorted(v["chosen_departments"])
res["expected_chosen"] = sorted(chosen + ["ceo"])

# Fail-closed (PART B): unreadable naming map -> FULL 28.
df.NAMING_MAP = Path(tmpd) / "does-not-exist.json"
empty = df.load_naming_map()
res["failclosed_mandatory"] = len(df.mandatory_ids(empty))
res["failclosed_universal"] = len(df.universal_primary_vertical_departments(empty))

print(json.dumps(res))
PYEOF
)"

echo "  fixture: $(echo "$FIXTURE_JSON" | python3 -c 'import json,sys;d=json.load(sys.stdin);print("floor_rc",d["floor_rc"],"declined",d["declined_count"],"expected_floor",d["expected_floor_count"])')"

get() { echo "$FIXTURE_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin)['$1'])"; }

# ── PART A ───────────────────────────────────────────────────────────────────
[ "$(get floor_rc)" = "0" ] && ok "sub-floor build: department-floor rc=0 (floor MET with 3 declines)" || bad "floor rc != 0 (got $(get floor_rc))"
[ "$(get declined_count)" = "3" ] && ok "exactly 3 declines honored" || bad "declined_count != 3 (got $(get declined_count))"
[ "$(get expected_floor_count)" = "25" ] && ok "expected_floor_count == 25 (28 − 3)" || bad "expected_floor_count != 25 (got $(get expected_floor_count))"
[ "$(get chosen_source)" = "artifact" ] && ok "chosen list read from the durable departments.json artifact" || bad "chosen_source != artifact (got $(get chosen_source))"

cf="$(get chosen_from_floor)"; ec="$(get expected_chosen)"
if [ "$cf" = "$ec" ]; then ok "departments.json chosen set == the 25 chosen departments (+ CEO column)"; else bad "chosen artifact != expected"; echo "    got: $cf"; echo "    exp: $ec"; fi

# prove-board-join.py rc=0 (chosen == provisioned == displayed). Keep stdout (the
# --json verdict) SEPARATE from stderr so the JSON parses cleanly.
CDIR="$(get company_dir)"; DB="$(get db)"
set +e
pj="$(python3 "$PROVE" --company-dir "$CDIR" --db "$DB" --json 2>"$TMPD/pj.err")"; prc=$?
set -e
if [ "$prc" -eq 0 ]; then ok "prove-board-join.py rc=0 on the sub-floor company (JOIN-OK)"; else bad "prove-board-join rc=$prc"; echo "$pj" | head -20; cat "$TMPD/pj.err" | head; fi
if echo "$pj" | grep -q '"status": "JOIN-OK"'; then ok "join status JOIN-OK (no drift classes)"; else bad "join not JOIN-OK"; fi
# and it counts exactly 26 (25 depts + CEO) on every layer. --json prints the
# human render FIRST then the indent=2 JSON verdict, so slice from its first
# line that is exactly "{".
jc="$(echo "$pj" | python3 -c '
import json,sys
lines=sys.stdin.read().splitlines()
start=next(i for i,l in enumerate(lines) if l.rstrip()=="{")
d=json.loads("\n".join(lines[start:]))
print(d["counts"]["chosen"],d["counts"]["provisioned"],d["counts"]["displayed"])
' 2>/dev/null || echo "err")"
[ "$jc" = "26 26 26" ] && ok "chosen==provisioned==displayed count = 26 (25 depts + CEO)" || bad "layer counts != 26/26/26 (got '$jc')"

# ── PART B: fail-closed to full 28 ───────────────────────────────────────────
[ "$(get failclosed_mandatory)" = "22" ] && ok "OQ-7 fail-closed: unreadable map => 22 mandatory (never fewer)" || bad "failclosed_mandatory != 22 (got $(get failclosed_mandatory))"
[ "$(get failclosed_universal)" = "6" ] && ok "OQ-7 fail-closed: unreadable map => 6 universal-primary (never fewer)" || bad "failclosed_universal != 6 (got $(get failclosed_universal))"
fm="$(get failclosed_mandatory)"; fu="$(get failclosed_universal)"
[ "$((fm + fu))" = "28" ] && ok "OQ-7 fail-closed: broken map degrades to the FULL 28 floor" || bad "fail-closed floor != 28"

echo ""
echo "── test-sub-floor-build: $PASS passed, $FAIL failed ──"
[ "$FAIL" -eq 0 ] || exit 1
