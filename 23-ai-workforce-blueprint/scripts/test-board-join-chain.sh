#!/usr/bin/env bash
# test-board-join-chain.sh — THE C-SERIES JOIN.
#
# Proves the one contract no existing suite asserts: that the three layers of the
# provisioning pipeline describe the SAME company.
#
#     chosenDepartments  ==  provisioned tree  ==  CC-DISPLAYED workspaces
#
# The layers are each already guarded INTERNALLY (suite 5: roster == _index.json
# == folders; suite 7: C5 no phantom duplicate trees; suite 8: C7 the chosen-list
# artifact is durable and readable; guard-department-runtime-parity: every board
# row has a runtime). Not one of them proves the layers AGREE — so all three can
# be internally perfect and still describe three different companies.
#
# NON-VACUITY IS THE POINT. This suite does not hand-write the "displayed" set: it
# runs the REAL shipped code for every layer —
#     LAYER 1  build-workforce.write_chosen_departments_artifact()   (Skill 23)
#     LAYER 2  a materialized departments/ tree on disk
#     LAYER 3  32-command-center-setup/scripts/seed-workspaces.py    (Skill 32)
#              executed as a SUBPROCESS against a real SQLite mission-control.db
# — and then joins what those programs actually produced. A pass therefore means
# the shipped pipeline built an agreeing chain, not that the test agreed with
# itself.
#
#   T1.  THE HAPPY CHAIN (non-vacuous): the real artifact writer + the real
#        seeder produce chosen == provisioned == displayed -> rc=0. Asserted with
#        RAW counts (>=5 departments on every layer), so an empty-set "pass" is
#        impossible.
#   T2.  VARIANT TOLERANCE (no FALSE drift): the tree carries `billing/` while the
#        chosen slug + board slug are `billing-finance` (a legal
#        CANONICAL_VARIANT_SLUGS spelling). The join must NOT report drift.
#        Likewise `master-orchestrator/` is the CEO column's tree.
#   T3.  *** THE ACCEPTANCE CASE *** — a department CHOSEN but NOT DISPLAYED.
#        Delete one seeded workspaces row: the client paid for the department and
#        cannot see it. -> rc=2, drift class CHOSEN_NOT_DISPLAYED, named.
#   T4.  DISPLAYED but NOT CHOSEN — a ghost Kanban column. -> rc=2,
#        DISPLAYED_NOT_CHOSEN.
#   T5.  CHOSEN but NOT PROVISIONED — a promised department that was never built.
#        -> rc=2, CHOSEN_NOT_PROVISIONED.
#   T6.  PROVISIONED but NOT CHOSEN — a phantom department tree. -> rc=2,
#        PROVISIONED_NOT_CHOSEN.
#   T7.  ARCHIVE-AWARE (the A8 / C6 soft-archive lifecycle): a chosen department
#        whose workspaces row is ARCHIVED is NOT displayed -> rc=2,
#        CHOSEN_NOT_DISPLAYED. "Archived" is not "displayed".
#   T8.  THE ELIMINATE PATH IS CLEAN (no false positive): a DECLINED department
#        that is not chosen, not provisioned, and archived on the board does NOT
#        trip the join -> rc=0.
#   T9.  FAIL-CLOSED — no chosen list: with the C7 artifact AND the build-state
#        record gone, the gate refuses to re-derive the floor and call it "chosen"
#        -> rc=3 CANNOT-VOUCH (never 0).
#  T10.  FAIL-CLOSED — empty board: the workspaces table exists but is EMPTY while
#        the client chose N departments -> rc=3 CANNOT-VOUCH (never 0). An empty
#        board is not a pass.
#  T11.  NOT-APPLICABLE is honest and separate: a DB with no `workspaces` table
#        (no Command Center yet) -> rc=4, and rc=4 is NOT rc=0.
#  T12.  ENFORCEMENT — the gate the QC pipeline actually runs
#        (scripts/qc-assert-workspace-departments-built.sh, the onboarding-honesty
#        "done" contract) FAILS rc=6 AF-BOARD-JOIN-DRIFT on the T3 board. A prover
#        no pipeline calls is a document, not a gate.
#  T13.  ...and that same gate does NOT return 6 on the clean chain (no false
#        fire), and SKIPS loudly (never fails) on a pre-C7 workspace that has no
#        chosen-list artifact at all.
#
# HERMETIC: builds its own mktemp sandbox, sandboxes $HOME, and pins the CC DB via
# DASHBOARD_DB_PATH. Writes NOTHING under the real ~/.openclaw, ~/projects, or the
# repo. Needs only python3 (sqlite3 is stdlib) — no jq, no network, no git.
#
# Exit 0 = all tests pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
JOIN_PY="$SCRIPT_DIR/prove-board-join.py"
SEEDER="$REPO_ROOT/32-command-center-setup/scripts/seed-workspaces.py"
QC_GATE="$REPO_ROOT/scripts/qc-assert-workspace-departments-built.sh"

# detect_platform.py needs a platform; the repo's other CI suites pin it the same way.
export OPENCLAW_PLATFORM="${OPENCLAW_PLATFORM:-mac}"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

for f in "$JOIN_PY" "$SEEDER" "$QC_GATE"; do
  [ -f "$f" ] || { echo "FATAL: missing $f" >&2; exit 2; }
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SANDBOX_HOME="$TMP/home"
COMPANY_DIR="$SANDBOX_HOME/clawd/zero-human-company/acme"
DEPTS_DIR="$COMPANY_DIR/departments"
DB="$SANDBOX_HOME/mission-control.db"
STATE="$TMP/build-state.json"
mkdir -p "$COMPANY_DIR" "$DEPTS_DIR"

# ── LAYER 1 — the REAL C7 artifact writer ────────────────────────────────────
# build-workforce.write_chosen_departments_artifact() is the shipped code that
# decides what "chosen" means (CEO-first, canonical, deduped). We call IT; we do
# not hand-write departments.json.
echo "== Building LAYER 1 (chosen) with the REAL build-workforce artifact writer =="
python3 - "$SKILL_DIR" "$COMPANY_DIR" "$STATE" <<'PY' || { echo "FATAL: layer-1 build failed" >&2; exit 2; }
import importlib.util, json, sys
SKILL, COMPANY, STATE = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("bw", f"{SKILL}/scripts/build-workforce.py")
bw = importlib.util.module_from_spec(spec); spec.loader.exec_module(bw)
bw._build_state_path = lambda: STATE           # isolate build-state into the sandbox
selected = {
    "marketing":         {"name": "Marketing",         "emoji": "\U0001F4E3", "head": "CMO"},
    "sales":             {"name": "Sales",             "emoji": "\U0001F4B0", "head": "CRO"},
    "billing-finance":   {"name": "Billing & Finance", "emoji": "\U0001F4B3", "head": "CFO"},
    "publishing-studio": {"name": "Publishing Studio", "emoji": "\U0001F4DA", "head": "Head of Publishing"},
}
bw.write_chosen_departments_artifact(selected, company_dir=COMPANY, source="join-prover-fixture")
slugs = [e["slug"] for e in json.load(open(f"{COMPANY}/departments.json"))]
print("  chosen slugs:", slugs)
assert slugs[0] == "ceo", slugs
assert len(slugs) == 5, slugs
PY

# ── LAYER 2 — the provisioned tree ───────────────────────────────────────────
# NOTE the deliberately AWKWARD spellings: `billing/` is a legal
# CANONICAL_VARIANT_SLUGS spelling of billing-finance, and the CEO's tree is
# `master-orchestrator/` (generate_departments_json's own workspacePath). A naive
# set-diff false-fires on both; the canonical join key must not.
mk_tree() {
  rm -rf "$DEPTS_DIR"; mkdir -p "$DEPTS_DIR"
  for d in marketing sales billing publishing-studio master-orchestrator; do
    mkdir -p "$DEPTS_DIR/$d/01-a-role"
  done
}
mk_tree

# ── LAYER 3 — the REAL Skill-32 seeder, as a subprocess, against a real DB ───
seed_board() {
  rm -f "$DB"
  python3 -c "import sqlite3,sys; sqlite3.connect(sys.argv[1]).close()" "$DB"
  HOME="$SANDBOX_HOME" \
  DASHBOARD_DB_PATH="$DB" \
  COMPANY_NAME="Acme" \
  COMPANY_SLUG="acme" \
  OPENCLAW_PLATFORM="mac" \
    python3 "$SEEDER" >"$TMP/seed.log" 2>&1
  return $?
}

sql() { python3 - "$DB" "$1" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1]); con.execute("PRAGMA journal_mode=DELETE")
cur = con.cursor()
for stmt in sys.argv[2].split(";;"):
    if stmt.strip():
        cur.execute(stmt)
con.commit(); con.close()
PY
}

query() { python3 - "$DB" "$1" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1]); cur = con.cursor()
for row in cur.execute(sys.argv[2]).fetchall():
    print("|".join("" if c is None else str(c) for c in row))
con.close()
PY
}

echo "== Building LAYER 3 (displayed) with the REAL Skill-32 seed-workspaces.py =="
if ! seed_board; then
  echo "FATAL: seed-workspaces.py failed:" >&2; cat "$TMP/seed.log" >&2; exit 2
fi
grep -E "INSERTED|Seeding complete" "$TMP/seed.log" | sed 's/^/  /'

# The join gate, always pointed at the sandbox.
join() { python3 "$JOIN_PY" --company-dir "$COMPANY_DIR" --db "$DB" --company-slug acme "$@"; }
join_rc() { join >"$TMP/join.out" 2>"$TMP/join.err"; echo $?; }

echo
echo "== T1: THE HAPPY CHAIN — chosen == provisioned == displayed (non-vacuous) =="
rc="$(join_rc)"
[ "$rc" = "0" ] && ok "clean chain -> rc=0" || { bad "clean chain -> rc=$rc (want 0)"; cat "$TMP/join.err"; }
# read the RAW counts straight out of the verdict JSON (stdout, after the table)
python3 - "$JOIN_PY" "$COMPANY_DIR" "$DB" <<'PY' > "$TMP/counts.txt" 2>/dev/null
import importlib.util, io, json, sys, contextlib
spec = importlib.util.spec_from_file_location("pbj", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = m.main(["--company-dir", sys.argv[2], "--db", sys.argv[3], "--company-slug", "acme", "--json"])
out = buf.getvalue()
v = json.loads(out[out.index("{"):])
print(v["counts"]["chosen"], v["counts"]["provisioned"], v["counts"]["displayed"], rc)
PY
read -r C_CHOSEN C_PROV C_DISP C_RC < "$TMP/counts.txt"
if [ "${C_CHOSEN:-0}" -ge 5 ] && [ "${C_PROV:-0}" -ge 5 ] && [ "${C_DISP:-0}" -ge 5 ] && [ "${C_RC:-1}" = "0" ]; then
  ok "NON-VACUOUS: chosen=$C_CHOSEN provisioned=$C_PROV displayed=$C_DISP (all >=5, rc=0)"
else
  bad "vacuous or wrong: chosen=${C_CHOSEN:-?} provisioned=${C_PROV:-?} displayed=${C_DISP:-?} rc=${C_RC:-?}"
fi
if [ "$(query "SELECT COUNT(*) FROM workspaces WHERE company_id='acme'")" = "5" ]; then
  ok "the REAL seeder wrote 5 board rows (displayed layer is shipped-code output, not test-authored)"
else
  bad "seeder wrote $(query "SELECT COUNT(*) FROM workspaces") rows (want 5)"
fi

echo
echo "== T2: VARIANT TOLERANCE — billing/ (tree) vs billing-finance (chosen+board), master-orchestrator/ = CEO =="
[ -d "$DEPTS_DIR/billing" ] && ok "tree really does carry the variant spelling billing/" || bad "fixture lost billing/"
[ "$(query "SELECT slug FROM workspaces WHERE slug='billing-finance'")" = "billing-finance" ] \
  && ok "board really does carry the canonical spelling billing-finance" || bad "board lost billing-finance"
[ "$(join_rc)" = "0" ] && ok "variant spellings produce NO false drift (rc=0)" || bad "FALSE DRIFT on a legal variant spelling"

echo
echo "== T3: *** ACCEPTANCE *** a department CHOSEN but NOT DISPLAYED -> the gate FAILS =="
sql "DELETE FROM workspaces WHERE slug='sales'"
rc="$(join_rc)"
[ "$rc" = "2" ] && ok "seeded mismatch (sales chosen, board row deleted) -> rc=2" || bad "seeded mismatch -> rc=$rc (want 2)"
grep -q "CHOSEN_NOT_DISPLAYED" "$TMP/join.err" && ok "drift class CHOSEN_NOT_DISPLAYED reported" || bad "CHOSEN_NOT_DISPLAYED not reported"
grep -q "CHOSEN_NOT_DISPLAYED: sales" "$TMP/join.err" && ok "the missing department is named: sales" || bad "sales not named in the failure"
grep -q "PROVISIONED_NOT_DISPLAYED" "$TMP/join.err" && ok "also caught as a headless workspace (PROVISIONED_NOT_DISPLAYED)" || bad "PROVISIONED_NOT_DISPLAYED not reported"
seed_board >/dev/null 2>&1   # restore

echo
echo "== T4: DISPLAYED but NOT CHOSEN — a ghost Kanban column =="
sql "INSERT INTO workspaces (id,name,slug,description,icon,company_id) VALUES ('legal','Legal','legal','ghost','⚖',  'acme')"
rc="$(join_rc)"
[ "$rc" = "2" ] && ok "ghost board column -> rc=2" || bad "ghost board column -> rc=$rc (want 2)"
grep -q "DISPLAYED_NOT_CHOSEN: legal" "$TMP/join.err" && ok "DISPLAYED_NOT_CHOSEN names legal" || bad "DISPLAYED_NOT_CHOSEN/legal not reported"
grep -q "DISPLAYED_NOT_PROVISIONED" "$TMP/join.err" && ok "also caught as a column with no tree behind it" || bad "DISPLAYED_NOT_PROVISIONED not reported"
seed_board >/dev/null 2>&1

echo
echo "== T5: CHOSEN but NOT PROVISIONED — a promised department that was never built =="
rm -rf "$DEPTS_DIR/marketing"
rc="$(join_rc)"
[ "$rc" = "2" ] && ok "unbuilt chosen department -> rc=2" || bad "unbuilt chosen department -> rc=$rc (want 2)"
grep -q "CHOSEN_NOT_PROVISIONED: marketing" "$TMP/join.err" && ok "CHOSEN_NOT_PROVISIONED names marketing" || bad "CHOSEN_NOT_PROVISIONED/marketing not reported"
mk_tree

echo
echo "== T6: PROVISIONED but NOT CHOSEN — a phantom department tree =="
mkdir -p "$DEPTS_DIR/video/01-a-role"
rc="$(join_rc)"
[ "$rc" = "2" ] && ok "phantom tree -> rc=2" || bad "phantom tree -> rc=$rc (want 2)"
grep -q "PROVISIONED_NOT_CHOSEN: video" "$TMP/join.err" && ok "PROVISIONED_NOT_CHOSEN names video" || bad "PROVISIONED_NOT_CHOSEN/video not reported"
mk_tree

echo
echo "== T7: ARCHIVE-AWARE — an ARCHIVED row is NOT displayed (A8 / C6 lifecycle) =="
sql "ALTER TABLE workspaces ADD COLUMN archived_at TEXT;;UPDATE workspaces SET archived_at='2026-07-11T00:00:00Z' WHERE slug='sales'"
rc="$(join_rc)"
[ "$rc" = "2" ] && ok "chosen department archived off the board -> rc=2" || bad "archived-but-chosen -> rc=$rc (want 2)"
grep -q "CHOSEN_NOT_DISPLAYED: sales" "$TMP/join.err" && ok "an archived department is correctly NOT displayed" || bad "archive column ignored — 'archived' was treated as 'displayed'"
grep -q "archive column   : archived_at" "$TMP/join.out" && ok "the lifecycle column is detected and reported" || bad "archive column not surfaced in the verdict"

echo
echo "== T8: THE ELIMINATE PATH IS CLEAN — a DECLINED dept, archived, trips NOTHING =="
sql "UPDATE workspaces SET archived_at=NULL WHERE slug='sales';;INSERT INTO workspaces (id,name,slug,description,icon,company_id,archived_at) VALUES ('legal','Legal','legal','declined','⚖','acme','2026-07-11T00:00:00Z')"
rc="$(join_rc)"
[ "$rc" = "0" ] && ok "declined+archived+unbuilt department -> rc=0 (no false positive)" || { bad "eliminate path false-fires -> rc=$rc (want 0)"; cat "$TMP/join.err"; }
grep -q "archived (NOT displayed): legal" "$TMP/join.out" && ok "the archived department is reported, not hidden" || bad "archived department not surfaced"
seed_board >/dev/null 2>&1

echo
echo "== T9: FAIL-CLOSED — no chosen list -> CANNOT VOUCH, never a pass =="
mv "$COMPANY_DIR/departments.json" "$TMP/departments.json.bak"
mv "$STATE" "$TMP/state.bak"
rc="$(join_rc)"
[ "$rc" = "3" ] && ok "no C7 chosen list -> rc=3 CANNOT-VOUCH" || bad "no chosen list -> rc=$rc (want 3)"
[ "$rc" != "0" ] && ok "the gate does NOT fail open when it cannot know what was chosen" || bad "GATE FAILS OPEN"
grep -q "will NOT re-derive it from the floor" "$TMP/join.err" && ok "refuses to fabricate a chosen list from the floor" || bad "no refusal message"
mv "$TMP/departments.json.bak" "$COMPANY_DIR/departments.json"
mv "$TMP/state.bak" "$STATE"

echo
echo "== T10: FAIL-CLOSED — an EMPTY board is not a pass =="
sql "DELETE FROM workspaces"
rc="$(join_rc)"
[ "$rc" = "3" ] && ok "seeded-nothing board -> rc=3 CANNOT-VOUCH" || bad "empty board -> rc=$rc (want 3)"
grep -q "An empty board" "$TMP/join.err" && ok "says so out loud" || bad "empty board not explained"
seed_board >/dev/null 2>&1

echo
echo "== T11: NOT-APPLICABLE is honest and separate from PASS =="
EMPTY_DB="$TMP/no-cc.db"
python3 -c "import sqlite3,sys; sqlite3.connect(sys.argv[1]).close()" "$EMPTY_DB"
python3 "$JOIN_PY" --company-dir "$COMPANY_DIR" --db "$EMPTY_DB" >/dev/null 2>"$TMP/na.err"; rc=$?
[ "$rc" = "4" ] && ok "no workspaces table (no Command Center) -> rc=4 NOT-APPLICABLE" || bad "no-CC -> rc=$rc (want 4)"
[ "$rc" != "0" ] && ok "NOT-APPLICABLE is not a pass" || bad "NOT-APPLICABLE collapsed into PASS"

echo
echo "== T12: ENFORCEMENT — the QC gate the pipeline runs FAILS rc=6 on the seeded mismatch =="
sql "DELETE FROM workspaces WHERE slug='sales'"
HOME="$SANDBOX_HOME" DASHBOARD_DB_PATH="$DB" \
  bash "$QC_GATE" --departments-dir "$DEPTS_DIR" >"$TMP/qc.out" 2>"$TMP/qc.err"; rc=$?
[ "$rc" = "6" ] && ok "qc-assert-workspace-departments-built.sh -> rc=6 AF-BOARD-JOIN-DRIFT" \
  || { bad "QC gate -> rc=$rc (want 6)"; tail -20 "$TMP/qc.err"; }
grep -q "AF-BOARD-JOIN-DRIFT" "$TMP/qc.err" && ok "the QC gate names the invariant" || bad "QC gate did not name AF-BOARD-JOIN-DRIFT"
grep -q "CHOSEN_NOT_DISPLAYED" "$TMP/qc.err" && ok "the QC gate names the drift class" || bad "QC gate did not name the drift class"
seed_board >/dev/null 2>&1

echo
echo "== T13: NO FALSE FIRE — clean chain, and a pre-C7 workspace SKIPS loudly =="
HOME="$SANDBOX_HOME" DASHBOARD_DB_PATH="$DB" \
  bash "$QC_GATE" --departments-dir "$DEPTS_DIR" >"$TMP/qc2.out" 2>"$TMP/qc2.err"; rc=$?
[ "$rc" != "6" ] && ok "clean chain -> QC gate does NOT return 6 (rc=$rc, the pre-existing shell verdict)" \
  || { bad "QC gate FALSE-FIRES rc=6 on a clean chain"; tail -20 "$TMP/qc2.err"; }
# A workspace with NO chosen-list artifact (a pre-C7 build) must SKIP, not fail —
# otherwise every existing suite that points this gate at a bare fixture breaks.
LEGACY="$TMP/legacy/departments"; mkdir -p "$LEGACY/marketing/01-a-role"
HOME="$SANDBOX_HOME" DASHBOARD_DB_PATH="$DB" \
  bash "$QC_GATE" --departments-dir "$LEGACY" >"$TMP/qc3.out" 2>"$TMP/qc3.err"; rc=$?
[ "$rc" != "6" ] && ok "pre-C7 workspace (no chosen list) -> gate SKIPS the join (rc=$rc), never 6" \
  || bad "pre-C7 workspace wrongly hard-failed the join"
grep -q "AF-BOARD-JOIN-DRIFT: CHECK SKIPPED" "$TMP/qc3.err" \
  && ok "the skip is LOUD and recorded (never silent)" || bad "the skip was silent"

echo
echo "==================================================="
echo "  test-board-join-chain: PASS=$PASS FAIL=$FAIL"
echo "==================================================="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
