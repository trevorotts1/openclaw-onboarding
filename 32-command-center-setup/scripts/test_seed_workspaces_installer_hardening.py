"""Installer hardening against a real client board (v25.1.66).

Every case here was measured on one client box during a v7.6.35 roll, by
diffing the Command Center DB against the pre-deploy backup:

  * 48 head/qc/research/devils-advocate agents were re-seeded into 12
    workspaces whose archived_at was set;
  * two departments were inserted as duplicates because the board carried
    `billing-finance` named "Billing" and `legal` named "Legal Compliance"
    while the source said `billing` / `legal-compliance`;
  * the seeder's company guard fired with no way to see that the DB held
    three company rows (`default`, `wakeuphappysis`, `wake-up-happy-sis`).

Fixtures are real sqlite databases, so the assertions run against real SQL
rather than a mocked cursor. The company GUARD itself is deliberately not
touched by any test here; only the advisory line it was missing.
"""
import importlib.util
import os
import sqlite3

import pytest

_SW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed-workspaces.py")
_spec = importlib.util.spec_from_file_location("seed_workspaces_hardening", _SW_PATH)
_sw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sw)

_COMPANY = {
    "name": "Test Co", "slug": "test-co", "industry": "",
    "brand_primary": "#000", "brand_accent": "#fff", "brand_text": "#111",
}


def _db(tmp_path, archived=True):
    p = tmp_path / "mc.db"
    con = sqlite3.connect(p)
    arch = ", archived_at TEXT, archived_reason TEXT" if archived else ""
    con.executescript(f"""
        CREATE TABLE companies (id TEXT PRIMARY KEY, name TEXT, slug TEXT, industry TEXT, config TEXT);
        CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT, slug TEXT UNIQUE,
            description TEXT, icon TEXT, company_id TEXT{arch});
    """)
    con.commit(); con.close()
    return p


# ─── The board already carries the department under another slug ─────────────

def test_canonical_slug_already_collapses_the_two_client_pairs():
    # The board's `billing-finance`/`legal` versus the source's
    # `billing`/`legal-compliance` are handled by canonical_slug.py's alias
    # map, which every id here goes through. No second alias table is needed,
    # and this pins that — if the map loses either pair, the duplicate returns.
    assert _sw._canonical_dept_slug("billing") == "billing-finance"
    assert _sw._canonical_dept_slug("legal-compliance") == "legal"


@pytest.mark.parametrize("board_slug,source_id", [
    ("billing-finance", "billing"),
    ("legal", "legal-compliance"),
])
def test_the_client_pairs_do_not_produce_a_second_workspace(tmp_path, board_slug, source_id):
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO workspaces (id,name,slug,company_id) VALUES (?,?,?,'test-co')",
                (board_slug, "Whatever The Board Calls It", board_slug))
    con.commit(); con.close()

    _sw.seed(str(db), [{"id": source_id, "name": "Source Name"}], _COMPANY)

    con = sqlite3.connect(db)
    rows = con.execute("SELECT id FROM workspaces").fetchall()
    con.close()
    assert rows == [(board_slug,)], rows          # one department, one column


def test_name_match_updates_the_existing_row_instead_of_inserting(tmp_path, capsys):
    # The case no slug alias covers: the board's slug matches nothing in the
    # source, but the NAME is the same department.
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO workspaces (id,name,slug,company_id) VALUES "
                "('ws-7f3a','Partner Success','ws-7f3a','test-co')")
    con.commit(); con.close()

    _sw.seed(str(db), [{"id": "partner-success", "name": "Partner Success"}], _COMPANY)

    con = sqlite3.connect(db)
    rows = con.execute("SELECT id, name FROM workspaces").fetchall()
    con.close()
    assert len(rows) == 1, rows          # NOT two columns for one department
    assert rows[0][0] == "ws-7f3a"       # the board's row, updated in place
    out = capsys.readouterr().out
    assert "MATCHED (name)" in out
    assert "Matched existing (updated, not duplicated): 1" in out


def test_name_match_is_case_insensitive(tmp_path):
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO workspaces (id,name,slug,company_id) VALUES "
                "('ws-1','PARTNER SUCCESS','ws-1','test-co')")
    con.commit(); con.close()
    _sw.seed(str(db), [{"id": "partner-success", "name": "partner success"}], _COMPANY)
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 1
    con.close()


def test_a_genuinely_new_department_still_inserts(tmp_path):
    # The control: matching must not swallow a department that really is new.
    db = _db(tmp_path)
    _sw.seed(str(db), [{"id": "marketing", "name": "Marketing"}], _COMPANY)
    con = sqlite3.connect(db)
    rows = con.execute("SELECT id FROM workspaces").fetchall()
    con.close()
    assert rows == [("marketing",)]


def test_name_match_never_reaches_across_a_company_boundary(tmp_path):
    # A same-named workspace owned by ANOTHER company must not be adopted by a
    # name match. The company guard owns that decision, not this fallback.
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO workspaces (id,name,slug,company_id) VALUES "
                "('ws-them','Partner Success','ws-them','other-co')")
    con.commit(); con.close()
    _sw.seed(str(db), [{"id": "partner-success", "name": "Partner Success"}], _COMPANY)
    con = sqlite3.connect(db)
    owners = dict(con.execute("SELECT id, company_id FROM workspaces").fetchall())
    con.close()
    assert owners["ws-them"] == "other-co"        # untouched
    assert owners.get("partner-success") == "test-co"   # ours inserted separately


# ─── The company split is legible ────────────────────────────────────────────

def test_company_split_line_names_every_company_and_the_catch_all_owner(tmp_path, capsys):
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    con.executemany(
        "INSERT INTO workspaces (id,name,slug,company_id) VALUES (?,?,?,?)",
        [("general-task", "General Task", "general-task", "wakeuphappysis"),
         ("a", "A", "a", "wakeuphappysis"),
         ("b", "B", "b", "default")],
    )
    con.commit(); con.close()

    # Seeding as 'default' while the catch-all belongs to 'wakeuphappysis'.
    _sw.seed(str(db), [{"id": "marketing", "name": "Marketing"}],
             dict(_COMPANY, slug="default"))
    out = capsys.readouterr().out
    assert "[company-split]" in out
    assert "MISMATCH" in out
    assert "wakeuphappysis" in out and "default" in out


def test_company_split_line_is_quiet_when_aligned(tmp_path, capsys):
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO workspaces (id,name,slug,company_id) VALUES "
                "('general-task','General Task','general-task','test-co')")
    con.commit(); con.close()
    _sw.seed(str(db), [{"id": "marketing", "name": "Marketing"}], _COMPANY)
    out = capsys.readouterr().out
    assert "MISMATCH" not in out
    assert "owns the catch-all" in out


def test_company_split_is_advisory_and_never_raises_on_an_old_schema(tmp_path):
    # No archived_at column, no companies rows: must still seed, never crash.
    db = _db(tmp_path, archived=False)
    _sw.seed(str(db), [{"id": "marketing", "name": "Marketing"}], _COMPANY)
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 1
    con.close()


# ─── The archived guard in materialize-dept-agents.sh ────────────────────────
# The guard is embedded in a bash heredoc, so the rule is asserted at source
# level: the workspaces query must exclude archived rows AND the per-workspace
# check must exist for the manifest path, which that query never touches.

_MAT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "materialize-dept-agents.sh")


def test_materialize_excludes_archived_workspaces_from_the_query():
    src = open(_MAT).read()
    assert "AND archived_at IS NULL" in src


def test_materialize_skips_an_archived_workspace_on_the_manifest_path():
    # The manifest path resolves ws_id by slug and never sees the query above,
    # so it needs its own per-workspace check or archived departments still get
    # agents. Assert the whole reachable guard, not just the query text: a
    # `if False:` / commented-out condition must fail this.
    src = open(_MAT).read()
    guard = ('    if _HAS_ARCHIVED_AT:\n'
             '        try:\n'
             '            arow = db.execute(\n'
             '                "SELECT archived_at FROM workspaces WHERE id=? LIMIT 1", (ws_id,)\n'
             '            ).fetchone()')
    assert guard in src, "the per-workspace archived guard is missing or unreachable"
    assert "if arow and arow[0]:" in src
    assert "workspace is archived" in src
    # and it must run BEFORE any agent rows are written for that workspace
    assert src.index("workspace is archived") < src.index("ensure_trio_quad_rows(db, ws_id")


def test_materialize_never_writes_archived_at():
    # Skipping is not enough: nothing here may un-archive a department.
    src = open(_MAT).read()
    assert "SET archived_at" not in src
    assert "archived_at =" not in src.replace("archived_at IS NULL", "")


@pytest.mark.parametrize("sql", ["DELETE FROM workspaces", "DELETE  FROM workspaces"])
def test_the_installer_never_hard_deletes_a_workspace(sql):
    # The 22 archived rows hard-deleted on the client box were removed by the
    # Command Center's sync script (--prune), NOT by anything here. This pins
    # that no onboarding installer script gains a workspace delete.
    for f in ("run-full-install.sh", "seed-workspaces.py", "materialize-dept-agents.sh"):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), f)
        assert sql not in open(p).read(), f
