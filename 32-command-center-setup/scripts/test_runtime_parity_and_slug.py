"""Runtime roster parity + department slug shape (v25.1.69).

Measured on a client box at the v25.1.66 skills roll:

  * the runtime materializer wrote 22 registry rows with a DOUBLED suffix,
    `dept-app-development-dept`, because it keyed on the raw folder name and
    those folders are named `<name>-dept` — the same key-vs-folder slug bug
    phase 6c had;
  * two entries were attributed to the `default` workspace because their
    department had no matching active workspace;
  * `guard-department-runtime-parity.py` failed the roll demanding runtime
    entries for every department, because it read only `agents.list` while the
    box carries `agents.entries` (100 entries, 66 of them `dept-` prefixed).

Fixtures are real sqlite databases and real openclaw.json files.
"""
import json
import os
import sqlite3
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_GUARD = os.path.join(_HERE, "guard-department-runtime-parity.py")
_MAT = os.path.join(_HERE, "materialize-dept-agents.sh")


def _board(tmp_path, rows, archived_col=True):
    db = tmp_path / "mission-control.db"
    con = sqlite3.connect(db)
    arch = ", archived_at TEXT, archived_reason TEXT" if archived_col else ""
    con.executescript(
        "CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT, slug TEXT, "
        f"type TEXT, company_id TEXT{arch});"
    )
    cols = "id,name,slug,type,company_id" + (",archived_at" if archived_col else "")
    marks = ",".join("?" * (6 if archived_col else 5))
    con.executemany(f"INSERT INTO workspaces ({cols}) VALUES ({marks})", rows)
    con.commit(); con.close()
    return db


def _cfg(tmp_path, agents):
    p = tmp_path / "openclaw.json"
    p.write_text(json.dumps({"agents": agents}))
    return p


def _run_guard(db, cfg):
    r = subprocess.run([sys.executable, _GUARD, "--db", str(db), "--config", str(cfg), "--json"],
                       capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout)


# ─── The guard must read the MODERN roster shape ────────────────────────────

def test_guard_reads_agents_entries(tmp_path):
    # The defect: agents.entries was invisible, so every department read as
    # missing its runtime and the roll failed.
    db = _board(tmp_path, [("app-development", "App Development", "app-development",
                            "department", "c1", None)])
    cfg = _cfg(tmp_path, {"entries": {"dept-app-development": {"name": "App Development"}}})
    rc, out = _run_guard(db, cfg)
    assert rc == 0, out
    assert out["ok"] is True
    assert out["mismatches"] == []


def test_guard_still_reads_agents_list(tmp_path):
    # The legacy shape must keep working; this is the control for the change.
    db = _board(tmp_path, [("marketing", "Marketing", "marketing", "department", "c1", None)])
    cfg = _cfg(tmp_path, {"list": [{"id": "dept-marketing"}]})
    rc, out = _run_guard(db, cfg)
    assert rc == 0, out
    assert out["ok"] is True


def test_guard_reads_an_entry_whose_id_field_differs_from_its_key(tmp_path):
    db = _board(tmp_path, [("audio", "Audio", "audio", "department", "c1", None)])
    cfg = _cfg(tmp_path, {"entries": {"some-key": {"id": "dept-audio"}}})
    rc, out = _run_guard(db, cfg)
    assert rc == 0, out


def test_guard_still_fails_when_a_live_department_really_has_no_runtime(tmp_path):
    # The protection must survive: a genuinely missing runtime is still a FAIL.
    db = _board(tmp_path, [("legal", "Legal", "legal", "department", "c1", None)])
    cfg = _cfg(tmp_path, {"entries": {"dept-marketing": {"name": "Marketing"}}})
    rc, out = _run_guard(db, cfg)
    assert rc != 0
    assert [m["slug"] for m in out["mismatches"]] == ["legal"]


# ─── Archived workspaces are off the board ──────────────────────────────────

def test_archived_workspace_is_ignored_not_missing(tmp_path):
    db = _board(tmp_path, [
        ("app-development", "App Development", "app-development", "department", "c1", None),
        ("engineering", "Engineering", "engineering", "department", "c1", "2026-09-01T00:00:00Z"),
    ])
    cfg = _cfg(tmp_path, {"entries": {"dept-app-development": {"name": "App Development"}}})
    rc, out = _run_guard(db, cfg)
    assert rc == 0, out
    assert out["checked"] == 1
    assert out["mismatches"] == []
    assert [x["reason"] for x in out["excluded"]] == ["archived"]
    assert "engineering" in [x["slug"] for x in out["excluded"]]


def test_an_archived_only_board_passes(tmp_path):
    db = _board(tmp_path, [("engineering", "Engineering", "engineering", "department",
                            "c1", "2026-09-01T00:00:00Z")])
    cfg = _cfg(tmp_path, {"entries": {}})
    rc, out = _run_guard(db, cfg)
    assert rc == 0, out


# ─── The materializer's slug shape ──────────────────────────────────────────

def _strip_from_materializer():
    """The affix stripper the materializer carries, lifted verbatim."""
    def _strip_dept_affix(raw):
        t = (raw or "").strip()
        if t.lower().startswith("dept-"):
            t = t[5:]
        if t.lower().endswith("-dept"):
            t = t[:-5]
        return t.strip("-") or (raw or "")
    return _strip_dept_affix


@pytest.mark.parametrize("folder,want", [
    ("app-development-dept", "app-development"),   # the client's shape
    ("dept-app-development", "app-development"),   # already prefixed
    ("app-development", "app-development"),        # already bare
    ("Engineering-Dept", "Engineering"),           # case-insensitive affix
])
def test_folder_name_never_becomes_a_doubled_agent_id(folder, want):
    strip = _strip_from_materializer()
    agent_id = f"dept-{strip(folder)}"
    assert agent_id == f"dept-{want}"
    assert not agent_id.lower().endswith("-dept"), agent_id
    assert agent_id.lower().count("dept-") == 1, agent_id


def test_affix_strip_leaves_everything_else_to_the_downstream_normaliser():
    # "Sales & Marketing" must survive as-is here: the entries-key step knows
    # how to normalise it, and normalising early DROPPED such folders (T4).
    strip = _strip_from_materializer()
    assert strip("Sales & Marketing") == "Sales & Marketing"


def test_materializer_strips_the_dept_affix_at_the_scan():
    src = open(_MAT).read()
    assert "discovered.setdefault(_strip_dept_affix(child.name)" in src, \
        "the scan still keys on the raw folder name"


def test_materializer_skips_a_department_with_no_live_workspace():
    src = open(_MAT).read()
    assert "_live = _live_workspace_slugs()" in src
    assert "no ACTIVE workspace row on the board" in src
    # and it must skip BEFORE writing the entry
    assert src.index("no ACTIVE workspace row") < src.index('agent_id = f"dept-{slug}"')


def test_materializer_fails_open_when_the_board_is_unreadable():
    # A missing DB must not empty a client's runtime roster.
    src = open(_MAT).read()
    assert "if _live is not None and slug not in _live" in src, \
        "the skip must be conditional on having read the board"


# ─── A parity finding is not a failed refresh ───────────────────────────────

def test_update_only_roll_warns_instead_of_failing_the_refresh():
    src = open(os.path.join(_HERE, "run-full-install.sh")).read()
    assert 'if [[ "${UPDATE_ONLY:-false}" == "true" ]]; then' in src
    assert "parity guard WARN" in src
    assert "CC refresh itself SUCCEEDED" in src


def test_full_install_still_refuses_on_a_parity_finding():
    src = open(os.path.join(_HERE, "run-full-install.sh")).read()
    i = src.index("phase=6e2 department-runtime-parity: WARN")
    j = src.index('fail_install "phase=6e2:')
    assert i < j, "the full-install refusal must still follow the update-only warning"
