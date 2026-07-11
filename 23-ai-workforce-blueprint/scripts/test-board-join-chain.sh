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
#  T14.  MULTI-COMPANY (no FALSE drift): ONE mission-control.db holding acme's 5
#        rows AND 57 rows belonging to ANOTHER company. An UNSCOPED read sees all 62
#        and reports every one of the other company's departments as
#        DISPLAYED_NOT_CHOSEN — FALSE drift on a healthy box, which (via
#        lib-onboarding-state.sh's "any non-zero rc = not materialized") can block
#        "done" FOREVER. The join must scope to ONE company_id -> rc=0. NON-VACUOUS:
#        the suite first proves an UNSCOPED read really does see both companies, and
#        then proves the gate STILL CATCHES real drift on that same multi-company
#        board (scoping must not blind it).
#  T15.  *** THE FAIL-OPEN IS CLOSED *** — rc=6 makes scripts/qc-system-integrity.sh
#        CHECK X.11 HARD-FAIL. Before the fix rc=6 fell into X.11's `*)` catch-all ->
#        a yellow WARN, and a WARN does not change the exit code: a box with PROVEN
#        board-join drift printed "ALL CHECKS PASSED ✓". ANTI-VACUOUS: proved as a
#        DELTA on a fixture where X.11 is otherwise GREEN (every floor dept
#        materialized FULL + a clean board) — clean -> "✓ X.11"; drifted -> "✗ X.11
#        AF-BOARD-JOIN-DRIFT" AND an [X.11] entry under FAILURE DETAILS (never
#        WARNING DETAILS). FAILURES is appended ONLY on a FAIL and the script exits 1
#        iff FAIL>0, so that membership IS the exit-code proof.
#  T16.  A FAILED ARTIFACT WRITE BUYS NO PASS: write_chosen_departments_artifact() is
#        fail-soft (OSError -> warning, never raises), so a box whose durable
#        departments.json write FAILED looked identical to a pre-C7 box — the join
#        was SKIPPED and the box silently PASSED. Drives the REAL OSError branch and
#        proves the join still RUNS (build-state's companyDir marker stands in for
#        the missing artifact) and still returns rc=6 on real drift.
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
echo "== T14: MULTI-COMPANY — another company's board rows must NOT produce FALSE drift =="
# ONE mission-control.db can hold SEVERAL companies' `workspaces` rows. Here acme's
# 5 rows share the table with 57 rows belonging to 'globex' — departments acme never
# chose and never provisioned. An UNSCOPED read sees all 62 and reports every one of
# globex's as DISPLAYED_NOT_CHOSEN / DISPLAYED_NOT_PROVISIONED: FALSE drift on a
# perfectly healthy box. And because lib-onboarding-state.sh maps ANY non-zero rc
# from the QC gate to "not materialized" — feeding oc_overall_goal_check AND the
# watchdog kill condition — that false drift can block "done" INDEFINITELY.
seed_board >/dev/null 2>&1        # acme's board: clean, 5 rows
python3 - "$DB" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1]); cur = con.cursor()
for i in range(57):
    s = f"globex-dept-{i:02d}"
    cur.execute("INSERT OR IGNORE INTO workspaces (id,name,slug,description,icon,company_id) "
                "VALUES (?,?,?,?,?,?)", (s, s, s, "another company's dept", "X", "globex"))
con.commit(); con.close()
PY
# (1) the fixture is REAL — raw counts, so a vacuous "pass on an empty board" is impossible
N_ACME="$(query "SELECT COUNT(*) FROM workspaces WHERE company_id='acme'")"
N_GLOBEX="$(query "SELECT COUNT(*) FROM workspaces WHERE company_id='globex'")"
if [ "$N_ACME" = "5" ] && [ "$N_GLOBEX" = "57" ]; then
  ok "multi-company fixture is real: acme=5 rows, globex=57 rows in ONE workspaces table"
else
  bad "fixture wrong: acme=$N_ACME globex=$N_GLOBEX (want 5 / 57)"
fi
# (2) NON-VACUITY: an UNSCOPED read really does see BOTH companies. This is the
#     hazard the scoping exists to defeat — if this assertion ever fails, T14 is
#     passing for the wrong reason (an empty/absent globex fixture).
python3 - "$JOIN_PY" "$DB" > "$TMP/unscoped.txt" 2>/dev/null <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("pbj", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
disp, arch, cids, col = m.read_displayed(sys.argv[2])          # NO company filter
print(len(disp), len(sorted(str(c) for c in cids)), ",".join(sorted(str(c) for c in cids)))
PY
read -r U_ROWS U_NIDS U_IDS < "$TMP/unscoped.txt"
if [ "${U_ROWS:-0}" -ge 62 ] && [ "${U_NIDS:-0}" = "2" ]; then
  ok "NON-VACUOUS: an UNSCOPED read sees all $U_ROWS rows across $U_NIDS companies ($U_IDS) — the hazard is real"
else
  bad "unscoped read saw rows=${U_ROWS:-?} companies=${U_NIDS:-?} (want >=62 / 2) — fixture not proving the hazard"
fi
# (3) AUTO-SCOPING (no --company-slug): this is the path every consumer gets by
#     default. It must scope to acme and report NO drift.
join_auto() { python3 "$JOIN_PY" --company-dir "$COMPANY_DIR" --db "$DB" "$@"; }
join_auto >"$TMP/ms.out" 2>"$TMP/ms.err"; rc=$?
[ "$rc" = "0" ] && ok "auto-scoped join on a MULTI-COMPANY board -> rc=0 (no false drift)" \
  || { bad "FALSE DRIFT on a multi-company board -> rc=$rc (want 0)"; sed -n '1,12p' "$TMP/ms.err"; }
grep -q "company scope    : acme" "$TMP/ms.out" \
  && ok "the verdict names the company it scoped to (acme)" || bad "company scope not surfaced in the verdict"
grep -q "globex" "$TMP/ms.out" \
  && ok "…and still REPORTS that globex's rows are on the board (scoped, not blind)" \
  || bad "the other company's ids are not surfaced — scoping is silent"
# (4) EXPLICIT --company-slug must agree with the auto path
[ "$(join_rc)" = "0" ] && ok "explicit --company-slug acme -> rc=0 (agrees with auto-scoping)" \
  || bad "explicit --company-slug disagrees with auto-scoping"
# (5) THE GATE THE PIPELINE ACTUALLY RUNS must not fire on a multi-company board
HOME="$SANDBOX_HOME" DASHBOARD_DB_PATH="$DB" \
  bash "$QC_GATE" --departments-dir "$DEPTS_DIR" >"$TMP/qc14.out" 2>"$TMP/qc14.err"; rc=$?
[ "$rc" != "6" ] && ok "qc-assert-workspace-departments-built.sh does NOT hard-fail rc=6 on a multi-company board (rc=$rc)" \
  || { bad "THE QC GATE FALSE-FIRES rc=6 on a multi-company box — this would block 'done' forever"; tail -12 "$TMP/qc14.err"; }
# (6) …and it still CATCHES real drift on the very same multi-company board
sql "DELETE FROM workspaces WHERE slug='sales' AND company_id='acme'"
HOME="$SANDBOX_HOME" DASHBOARD_DB_PATH="$DB" \
  bash "$QC_GATE" --departments-dir "$DEPTS_DIR" >"$TMP/qc14b.out" 2>"$TMP/qc14b.err"; rc=$?
[ "$rc" = "6" ] && ok "REAL drift is still caught on the SAME multi-company board -> rc=6 (scoping did not blind the gate)" \
  || bad "scoping BLINDED the gate — real drift on a multi-company board -> rc=$rc (want 6)"
grep -q "CHOSEN_NOT_DISPLAYED: sales" "$TMP/qc14b.err" \
  && ok "and it names the right department (sales), not globex's" || bad "wrong/no department named"
sql "DELETE FROM workspaces WHERE company_id='globex'"
seed_board >/dev/null 2>&1

echo
echo "== T15: *** FAIL-OPEN CLOSED *** rc=6 makes qc-system-integrity.sh CHECK X.11 HARD-FAIL =="
# THE BLOCKER THIS PROVES FIXED: CHECK X.11's `case` had arms 0/3/5/4/* only. rc=6
# fell into `*)` -> a yellow WARN — and a WARN does NOT change the exit code (the
# script exits 0 when FAIL==0). So a box with PROVEN board-join drift printed
# "ALL CHECKS PASSED", with the drift mislabeled as an infrastructure error.
#
# ANTI-VACUITY: qc-system-integrity.sh runs ~50 checks and a sandbox trips several
# of them, so "it exited non-zero" proves NOTHING on its own. The proof is the
# DELTA on CHECK X.11 itself, on a fixture where X.11 is otherwise GREEN:
#     clean board  -> "✓ X.11"  (X.11 contributes ZERO failures)
#     drifted board-> "✗ X.11 AF-BOARD-JOIN-DRIFT" AND an [X.11] entry in the
#                     FAILURE DETAILS block (never WARNING DETAILS)
# An [X.11] entry in FAILURES means FAIL was incremented; the script exits 1 iff
# FAIL>0. So a box whose ONLY defect is board drift now exits NON-ZERO, where it
# previously printed ALL CHECKS PASSED.
QC_SYS="$REPO_ROOT/scripts/qc-system-integrity.sh"
if [ ! -f "$QC_SYS" ]; then
  bad "qc-system-integrity.sh not found — cannot prove the fail-open is closed"
else
  FULL_HOME="$TMP/full"; FULL_CDIR="$FULL_HOME/clawd/zero-human-company/acme"
  FULL_DD="$FULL_CDIR/departments"; FULL_DB="$FULL_HOME/mc.db"
  mkdir -p "$FULL_DD"
  # A fixture where X.11 passes CLEAN requires every FLOOR department materialized
  # FULL (roles + IDENTITY + SOUL + a real >=3KB SOP). The floor is DYNAMIC (vertical
  # detection grows it as the tree appears), so converge it, then write the chosen
  # list with the REAL C7 artifact writer and seed the board with the REAL seeder.
  HOME="$FULL_HOME" OPENCLAW_PLATFORM=mac python3 - "$SKILL_DIR" "$FULL_CDIR" \
      >"$TMP/full.log" 2>&1 <<'PY'
import importlib.util, sys
from pathlib import Path
SKILL, COMPANY = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("df", f"{SKILL}/scripts/department-floor.py")
df = importlib.util.module_from_spec(spec); spec.loader.exec_module(df)
dd = Path(COMPANY) / "departments"
SOP = "# How To\n\n" + ("A substantive standard operating procedure line.\n" * 120)
def materialize(d):
    role = dd / d / "01-lead"; role.mkdir(parents=True, exist_ok=True)
    (dd / d / "IDENTITY.md").write_text(f"# {d} director\n")
    (dd / d / "SOUL.md").write_text(f"# {d} soul\n")
    (role / "how-to.md").write_text(SOP)
floor = []
for _ in range(6):
    floor = list(df.evaluate_floor(departments_dir=dd).get("expected_floor", []))
    missing = [d for d in floor if not (dd / d).is_dir()]
    if not missing:
        break
    for d in missing:
        materialize(d)
materialize("master-orchestrator")
spec2 = importlib.util.spec_from_file_location("bw", f"{SKILL}/scripts/build-workforce.py")
bw = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(bw)
bw._build_state_path = lambda: str(Path(COMPANY).parents[2] / ".openclaw/workspace/.workforce-build-state.json")
sel = {d: {"name": d.replace("-", " ").title(), "emoji": "\U0001F4E6", "head": "Head"} for d in floor}
bw.write_chosen_departments_artifact(sel, company_dir=COMPANY, source="fail-open-fixture")
print("FLOOR", len(floor))
PY
  python3 -c "import sqlite3,sys; sqlite3.connect(sys.argv[1]).close()" "$FULL_DB"
  HOME="$FULL_HOME" DASHBOARD_DB_PATH="$FULL_DB" COMPANY_NAME="Acme" COMPANY_SLUG="acme" \
    OPENCLAW_PLATFORM=mac python3 "$SEEDER" >>"$TMP/full.log" 2>&1
  # PRECONDITION: the gate, SELF-RESOLVING (exactly how qc-system-integrity.sh calls
  # it — with no --departments-dir), must be GREEN on this fixture. Without a green
  # baseline the ✓->✗ delta below would prove nothing.
  HOME="$FULL_HOME" DASHBOARD_DB_PATH="$FULL_DB" OPENCLAW_PLATFORM=mac \
    bash "$QC_GATE" >"$TMP/fg.out" 2>"$TMP/fg.err"; rc=$?
  if [ "$rc" != "0" ]; then
    bad "PRECONDITION FAILED: the self-resolved gate is not green on the full fixture (rc=$rc) — cannot prove the delta"
    tail -6 "$TMP/fg.err"
  else
    ok "baseline: every floor department FULL + clean board -> the self-resolved gate is GREEN (rc=0)"

    # ── RUN A: clean board ──
    HOME="$FULL_HOME" DASHBOARD_DB_PATH="$FULL_DB" OPENCLAW_PLATFORM=mac \
      timeout 300 bash "$QC_SYS" >"$TMP/sysA.out" 2>&1; SYS_A=$?
    sed 's/\x1b\[[0-9;]*m//g' "$TMP/sysA.out" > "$TMP/sysA.txt"
    grep -q "✓ X.11" "$TMP/sysA.txt" \
      && ok "CLEAN board -> qc-system-integrity CHECK X.11 is GREEN (contributes 0 failures)" \
      || { bad "CLEAN board -> X.11 not green; the delta below would be meaningless"; grep -a "X.11" "$TMP/sysA.txt"; }
    grep -q "AF-BOARD-JOIN-DRIFT" "$TMP/sysA.txt" \
      && bad "X.11 reports board-join drift on a CLEAN board (false fire)" \
      || ok "…and reports NO board-join drift on a clean board (the check is not always-on)"

    # ── introduce REAL drift: the client chose 'sales', it is built, and its board
    #    column is gone. They paid for it and cannot see it. ──
    python3 -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute(\"DELETE FROM workspaces WHERE slug='sales'\"); c.commit()" "$FULL_DB"
    HOME="$FULL_HOME" DASHBOARD_DB_PATH="$FULL_DB" OPENCLAW_PLATFORM=mac \
      bash "$QC_GATE" >/dev/null 2>&1; rc=$?
    [ "$rc" = "6" ] && ok "the delegate gate returns rc=6 AF-BOARD-JOIN-DRIFT on the drifted board" \
      || bad "delegate gate -> rc=$rc (want 6) — the rest of T15 is meaningless"

    # ── RUN B: drifted board ──
    HOME="$FULL_HOME" DASHBOARD_DB_PATH="$FULL_DB" OPENCLAW_PLATFORM=mac \
      timeout 300 bash "$QC_SYS" >"$TMP/sysB.out" 2>&1; SYS_B=$?
    sed 's/\x1b\[[0-9;]*m//g' "$TMP/sysB.out" > "$TMP/sysB.txt"

    grep -q "✗ X.11 AF-BOARD-JOIN-DRIFT" "$TMP/sysB.txt" \
      && ok "DRIFT -> CHECK X.11 HARD-FAILS and names AF-BOARD-JOIN-DRIFT" \
      || { bad "*** FAIL-OPEN *** X.11 did not hard-fail on rc=6"; grep -a "X.11" "$TMP/sysB.txt"; }

    # THE FAIL-OPEN SIGNATURE: rc=6 must never reach the catch-all WARN arm.
    grep -q "could not run (rc=6)" "$TMP/sysB.txt" \
      && bad "*** FAIL-OPEN *** rc=6 still routes to the WARN catch-all ('gate could not run')" \
      || ok "rc=6 never routes to the WARN catch-all (it is no longer mislabeled an infra error)"

    # The [X.11] entry must land in FAILURE DETAILS, NOT WARNING DETAILS. FAILURES is
    # appended ONLY on a FAIL, and the script exits 1 iff FAIL>0 — so this single
    # assertion IS the exit-code proof.
    awk '/^FAILURE DETAILS:/{f=1} /^WARNING DETAILS:/{f=0} f' "$TMP/sysB.txt" | grep -q "\[X.11\]" \
      && ok "[X.11] is listed under FAILURE DETAILS => FAIL was incremented => the script must exit non-zero" \
      || bad "[X.11] is NOT in FAILURE DETAILS — the drift did not increment FAIL (fail-open)"
    awk '/^WARNING DETAILS:/{w=1} w' "$TMP/sysB.txt" | grep -q "\[X.11\]" \
      && bad "*** FAIL-OPEN *** [X.11] was recorded as a WARNING (warnings do NOT change the exit code)" \
      || ok "[X.11] is NOT a warning (a warning would not change the exit code — that WAS the bug)"

    [ "$SYS_B" -ne 0 ] \
      && ok "qc-system-integrity.sh exits NON-ZERO ($SYS_B) on a box with proven board-join drift" \
      || bad "*** FAIL-OPEN *** qc-system-integrity.sh exited 0 on a box with proven board-join drift"

    # The drift class + the named department must reach the operator's screen.
    grep -q "CHOSEN_NOT_DISPLAYED" "$TMP/sysB.txt" \
      && ok "the drift class reaches the operator (CHOSEN_NOT_DISPLAYED surfaced under X.11)" \
      || bad "the drift class was swallowed — the operator cannot see WHAT drifted"
  fi
fi

echo
echo "== T16: a FAILED artifact write must NOT buy a silent pass =="
# write_chosen_departments_artifact() is fail-soft: an OSError writing
# <company>/departments.json is a WARNING, never a raise. On such a box the artifact
# is ABSENT and artifactPath is recorded as None. If artifactPath were the only
# company scope key, the chosen list would read back empty and the QC gate would SKIP
# the join as though this were a pre-C7 build — a box whose durable write FAILED
# would be indistinguishable from one that never had the feature, and would PASS.
# We drive the REAL fail-soft branch (a patched open() that raises OSError on the
# artifact) and prove the join still RUNS.
T16_STATE="$SANDBOX_HOME/.openclaw/workspace/.workforce-build-state.json"
mkdir -p "$(dirname "$T16_STATE")"
rm -f "$COMPANY_DIR/departments.json"
python3 - "$SKILL_DIR" "$COMPANY_DIR" "$T16_STATE" >"$TMP/t16.log" 2>&1 <<'PY'
import builtins, importlib.util, json, sys
SKILL, COMPANY, STATE = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("bw", f"{SKILL}/scripts/build-workforce.py")
bw = importlib.util.module_from_spec(spec); spec.loader.exec_module(bw)
bw._build_state_path = lambda: STATE
_real_open = builtins.open
def _boom(path, *a, **k):
    # Fail exactly the durable artifact write — the REAL OSError branch.
    if str(path).endswith("departments.json"):
        raise OSError(28, "No space left on device")
    return _real_open(path, *a, **k)
builtins.open = _boom
try:
    sel = {"marketing": {"name": "Marketing", "emoji": "\U0001F4E3", "head": "CMO"},
           "sales": {"name": "Sales", "emoji": "\U0001F4B0", "head": "CRO"},
           "billing-finance": {"name": "Billing & Finance", "emoji": "\U0001F4B3", "head": "CFO"},
           "publishing-studio": {"name": "Publishing Studio", "emoji": "\U0001F4DA", "head": "Head"}}
    bw.write_chosen_departments_artifact(sel, company_dir=COMPANY, source="failed-write-fixture")
finally:
    builtins.open = _real_open
rec = json.load(_real_open(STATE))["canonicalReconciliation"]["chosenDepartments"]
print("ARTIFACT_PATH", rec.get("artifactPath"))
print("ARTIFACT_WRITTEN", rec.get("artifactWritten"))
print("COMPANY_DIR", rec.get("companyDir"))
print("SLUGS", len(rec.get("slugs") or []))
PY
if [ ! -f "$COMPANY_DIR/departments.json" ] && grep -q "ARTIFACT_PATH None" "$TMP/t16.log" \
   && grep -q "ARTIFACT_WRITTEN False" "$TMP/t16.log"; then
  ok "the REAL fail-soft branch ran: the durable artifact never landed (artifactPath=None, artifactWritten=False)"
else
  bad "could not reproduce a failed artifact write"; cat "$TMP/t16.log"
fi
grep -q "COMPANY_DIR $COMPANY_DIR" "$TMP/t16.log" \
  && ok "…but build-state still records companyDir (the reconciliation-ran marker)" \
  || bad "companyDir not recorded — a failed write is indistinguishable from a pre-C7 box"
# Now put REAL drift on the board. The join MUST still run and catch it.
sql "DELETE FROM workspaces WHERE slug='sales'"
HOME="$SANDBOX_HOME" DASHBOARD_DB_PATH="$DB" \
  bash "$QC_GATE" --departments-dir "$DEPTS_DIR" >"$TMP/qc16.out" 2>"$TMP/qc16.err"; rc=$?
[ "$rc" = "6" ] && ok "drift on a box whose artifact write FAILED -> rc=6 (the failed write bought NO pass)" \
  || { bad "*** SILENT PASS *** artifact-write failure let real drift through -> rc=$rc (want 6)"; tail -8 "$TMP/qc16.err"; }
grep -q "CHECK SKIPPED — no durable chosen-departments list" "$TMP/qc16.err" \
  && bad "the gate SKIPPED the join — a failed write is still being read as 'pre-C7'" \
  || ok "the gate did NOT skip the join (build-state stood in for the missing artifact)"
rm -f "$T16_STATE"
seed_board >/dev/null 2>&1

echo
echo "==================================================="
echo "  test-board-join-chain: PASS=$PASS FAIL=$FAIL"
echo "==================================================="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
