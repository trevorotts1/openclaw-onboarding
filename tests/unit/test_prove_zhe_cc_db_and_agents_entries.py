"""prove-zhe.py must measure the box's REAL board and REAL agent roster.

Four false FAILs seen at phase 7z on an OpenClaw 2026.9.x Mac box:
  * a stray 0-byte <oc_root>/workspace/mission-control.db sat ahead of the
    Command Center's real DB in the candidate list, so check (c) opened the
    decoy and reported "workspaces table absent";
  * openclaw.json carried the migrated `agents.entries` roster (object keyed by
    agent id) and no `agents.list`, so check (a) saw zero registered agents;
  * the lane check matched folder slugs literally, so folder legal-compliance
    missed its canonical board lane "legal";
  * rescue-rangers (operator-side board) was held to a client board lane.
"""
import importlib.util
import json
import os
import sqlite3
import sys

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
_PROVER = os.path.join(_ROOT, "23-ai-workforce-blueprint", "scripts", "prove-zhe.py")


@pytest.fixture
def pz(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("prove_zhe_under_test", _PROVER)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(_PROVER))
    spec.loader.exec_module(mod)
    # Hermetic: no operator secrets, no ambient DB override, a private HOME.
    monkeypatch.setattr(mod, "_SECRETS_CACHE", {})
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("DASHBOARD_DB_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return mod


def _oc_root(tmp_path, agents, depts=("marketing", "sales")):
    root = tmp_path / "home" / ".openclaw"
    for d in depts:
        (root / "workspace" / "departments" / d).mkdir(parents=True)
    (root / "openclaw.json").write_text(json.dumps({"agents": agents}))
    return str(root)


def _real_db(path, lanes=("marketing", "sales")):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE workspaces (slug TEXT, name TEXT)")
    c.executemany("INSERT INTO workspaces VALUES (?, ?)", [(s, s.title()) for s in lanes])
    c.commit()
    c.close()


# --- check (a): agents registered -------------------------------------------

def test_agents_entries_roster_counts_as_registered(pz, tmp_path):
    root = _oc_root(tmp_path, {"defaults": {}, "entries": {
        "dept-marketing": {"name": "Marketing"}, "dept-sales": {"name": "Sales"}}})
    fs = pz.LocalFS(root)
    r = pz.check_depts_registered(fs, root, pz.load_openclaw_config(fs, root))
    assert r["pass"], r["detail"]
    assert r["registered_as_agents"] == ["marketing", "sales"]


def test_legacy_agents_list_roster_still_counts(pz, tmp_path):
    root = _oc_root(tmp_path, {"list": [{"id": "dept-marketing"}, {"id": "dept-sales"}]})
    fs = pz.LocalFS(root)
    assert pz.check_depts_registered(fs, root, pz.load_openclaw_config(fs, root))["pass"]


def test_unregistered_dept_still_fails_on_entries_roster(pz, tmp_path):
    root = _oc_root(tmp_path, {"entries": {"dept-marketing": {}}})
    fs = pz.LocalFS(root)
    r = pz.check_depts_registered(fs, root, pz.load_openclaw_config(fs, root))
    assert not r["pass"]
    assert r["files_without_agent"] == ["sales"]


# --- check (c): the Command Center DB ---------------------------------------

def test_zero_byte_decoy_ahead_of_real_db_is_skipped(pz, tmp_path):
    root = _oc_root(tmp_path, {"entries": {}})
    decoy = os.path.join(root, "workspace", "mission-control.db")
    open(decoy, "w").close()
    real = str(tmp_path / "home" / "projects" / "command-center" / "mission-control.db")
    _real_db(real)
    r = pz.check_command_center(pz.LocalFS(root), root, ["marketing", "sales"])
    assert r["pass"], r["detail"]
    assert r["db_path"] == real
    assert os.path.getsize(decoy) == 0  # never written to


def test_database_path_env_wins(pz, tmp_path, monkeypatch):
    root = _oc_root(tmp_path, {"entries": {}})
    _real_db(str(tmp_path / "home" / "projects" / "command-center" / "mission-control.db"),
             lanes=("other",))
    live = str(tmp_path / "custom" / "mission-control.db")
    _real_db(live)
    monkeypatch.setenv("DATABASE_PATH", live)
    r = pz.check_command_center(pz.LocalFS(root), root, ["marketing", "sales"])
    assert r["pass"], r["detail"]
    assert r["db_path"] == live


def test_cc_env_local_database_path_wins(pz, tmp_path):
    root = _oc_root(tmp_path, {"entries": {}})
    cc = tmp_path / "home" / "projects" / "command-center"
    _real_db(str(cc / "mission-control.db"), lanes=("other",))
    live = str(tmp_path / "custom" / "mission-control.db")
    _real_db(live)
    (cc / ".env.local").write_text(f'FOO=bar\nDATABASE_PATH="{live}"\n')
    r = pz.check_command_center(pz.LocalFS(root), root, ["marketing", "sales"])
    assert r["pass"], r["detail"]
    assert r["db_path"] == live


def test_only_decoy_present_fails_closed_and_creates_nothing(pz, tmp_path):
    root = _oc_root(tmp_path, {"entries": {}})
    open(os.path.join(root, "workspace", "mission-control.db"), "w").close()
    r = pz.check_command_center(pz.LocalFS(root), root, ["marketing"])
    assert not r["pass"]
    assert not (tmp_path / "home" / "projects").exists()


def test_alias_folder_matches_its_canonical_lane(pz, tmp_path):
    # Folder legal-compliance, board lane "legal" (seeded via canonical_dept_slug).
    root = _oc_root(tmp_path, {"entries": {}}, depts=("legal-compliance",))
    _real_db(str(tmp_path / "home" / "projects" / "command-center" / "mission-control.db"),
             lanes=("legal",))
    r = pz.check_command_center(pz.LocalFS(root), root, ["legal-compliance", "sales"])
    assert r["dept_lanes_missing"] == ["sales"]


def test_rescue_rangers_exempt_from_client_lane_only(pz, tmp_path):
    # Operator-side escalation dept: no client board lane required...
    root = _oc_root(tmp_path, {"entries": {"dept-marketing": {}}},
                    depts=("marketing", "rescue-rangers"))
    _real_db(str(tmp_path / "home" / "projects" / "command-center" / "mission-control.db"),
             lanes=("marketing",))
    fs = pz.LocalFS(root)
    assert pz.check_command_center(fs, root, ["marketing", "rescue-rangers"])["pass"]
    # ...but it is still held to agent registration.
    r = pz.check_depts_registered(fs, root, pz.load_openclaw_config(fs, root))
    assert r["files_without_agent"] == ["rescue-rangers"]
