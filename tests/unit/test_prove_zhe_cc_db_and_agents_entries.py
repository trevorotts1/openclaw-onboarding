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

And a fifth: the required departments came from a folder scan, so role-library
template copies nobody chose (founding-member-concierge, launch-operations, ...)
were held to an agent + lane that no supported path can ever create.
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


def test_rescue_rangers_exempt_from_client_lane_and_agent(pz, tmp_path):
    # Operator-side escalation dept: no client board lane required...
    root = _oc_root(tmp_path, {"entries": {"dept-marketing": {}}},
                    depts=("marketing", "rescue-rangers"))
    _real_db(str(tmp_path / "home" / "projects" / "command-center" / "mission-control.db"),
             lanes=("marketing",))
    fs = pz.LocalFS(root)
    assert pz.check_command_center(fs, root, ["marketing", "rescue-rangers"])["pass"]
    # ...and no client agent either: materialize-dept-agents.sh registers only against
    # a live lane, so an agent-without-lane requirement could never be met.
    r = pz.check_depts_registered(fs, root, pz.load_openclaw_config(fs, root))
    assert r["pass"], r["detail"]
    assert r["operator_board_exempt"] == ["rescue-rangers"]


# --- "~" is expanded for every DB source ------------------------------------
# A receipt showed db_path "~/projects/command-center/mission-control.db" with
# has_workspaces_table=false: the probe opened the literal "~" path.

def test_tilde_layout_candidate_is_expanded(pz, tmp_path):
    root = _oc_root(tmp_path, {"entries": {}})
    real = str(tmp_path / "home" / "projects" / "command-center" / "mission-control.db")
    _real_db(real)
    r = pz.check_command_center(pz.LocalFS(root), root, ["marketing", "sales"])
    assert r["pass"], r["detail"]
    assert r["db_path"] == real


def test_tilde_database_path_env_is_expanded(pz, tmp_path, monkeypatch):
    root = _oc_root(tmp_path, {"entries": {}})
    live = str(tmp_path / "home" / "custom" / "mission-control.db")
    _real_db(live)
    monkeypatch.setenv("DATABASE_PATH", "~/custom/mission-control.db")
    r = pz.check_command_center(pz.LocalFS(root), root, ["marketing", "sales"])
    assert r["pass"], r["detail"]
    assert r["db_path"] == live


def test_tilde_env_local_database_path_is_expanded(pz, tmp_path):
    root = _oc_root(tmp_path, {"entries": {}})
    cc = tmp_path / "home" / "projects" / "command-center"
    _real_db(str(cc / "mission-control.db"), lanes=("other",))
    live = str(tmp_path / "home" / "custom" / "mission-control.db")
    _real_db(live)
    (cc / ".env.local").write_text("DATABASE_PATH=~/custom/mission-control.db\n")
    r = pz.check_command_center(pz.LocalFS(root), root, ["marketing", "sales"])
    assert r["pass"], r["detail"]
    assert r["db_path"] == live


# --- required departments = departments.json + the standard floor ------------
# A client Mac carried six role-library template copies under departments/ that
# are in neither its departments.json nor the floor. The folder scan demanded a
# dept-<folder> agent and a board lane for each; nothing seeds either.

STRAY = ("client-experience-booking", "founding-member-concierge", "launch-operations",
         "product-production", "rescue-rangers")


def _floor(pz):
    df = pz._load_floor_module()
    nm = df.load_naming_map()
    return df.mandatory_ids(nm) + df.universal_primary_vertical_departments(nm)


def _full_box(pz, tmp_path, chosen=(), extra_dirs=(), skip_agents=(), skip_lanes=()):
    """An interview-complete box whose chosen + floor departments all have a folder,
    a dept-<slug> agent and a board lane, except for the ones named in skip_*."""
    depts = list(dict.fromkeys(list(_floor(pz)) + list(chosen)))
    agents = {"entries": {f"dept-{d}": {} for d in depts if d not in skip_agents}}
    root = _oc_root(tmp_path, agents, depts=tuple(depts) + tuple(extra_dirs))
    ws = os.path.join(root, "workspace")
    with open(os.path.join(ws, "departments.json"), "w") as f:
        json.dump([{"id": f"dept-{d}", "slug": d} for d in chosen or depts], f)
    with open(os.path.join(ws, ".workforce-build-state.json"), "w") as f:
        json.dump({"interviewComplete": True}, f)
    _real_db(str(tmp_path / "home" / "projects" / "command-center" / "mission-control.db"),
             lanes=[d for d in depts if d not in skip_lanes])
    return root


def _prove(pz, root):
    r = pz.prove("LOCAL", "", pz.LocalFS(root))
    return r, r["checks"]["floor_depts_registered_as_agents"], r["checks"]["command_center_board"]


def test_stray_template_folders_warn_not_fail(pz, tmp_path):
    root = _full_box(pz, tmp_path, extra_dirs=STRAY)
    r, a, c = _prove(pz, root)
    assert a["pass"], a["detail"]
    assert c["pass"], c["detail"]
    assert a["required_source"] == "departments.json"
    assert a["stray_template_folders"] == sorted(STRAY)
    assert "stray template folder" in r["warnings"][0]
    for d in STRAY:
        assert os.path.isdir(os.path.join(root, "workspace", "departments", d))  # never deleted


def test_chosen_dept_missing_its_lane_still_fails(pz, tmp_path):
    root = _full_box(pz, tmp_path, chosen=_floor(pz) + ["listings"], skip_lanes=("listings",))
    _, a, c = _prove(pz, root)
    assert a["pass"], a["detail"]
    assert not c["pass"]
    assert c["dept_lanes_missing"] == ["listings"]


def test_chosen_dept_missing_its_agent_still_fails(pz, tmp_path):
    root = _full_box(pz, tmp_path, chosen=_floor(pz) + ["listings"], skip_agents=("listings",))
    _, a, _ = _prove(pz, root)
    assert not a["pass"]
    assert a["files_without_agent"] == ["listings"]


def test_floor_dept_left_out_of_departments_json_is_still_required(pz, tmp_path):
    chosen = [d for d in _floor(pz) if d != "sales"]
    root = _full_box(pz, tmp_path, chosen=chosen, skip_agents=("sales",), skip_lanes=("sales",))
    _, a, c = _prove(pz, root)
    assert a["files_without_agent"] == ["sales"]
    assert c["dept_lanes_missing"] == ["sales"]


def test_legal_compliance_alias_checks_the_canonical_agent(pz, tmp_path):
    # Folder legal-compliance beside legal: lane "legal", agent dept-legal. Both checks
    # judge the SAME canonical department; no dept-legal-compliance is demanded.
    root = _full_box(pz, tmp_path, extra_dirs=("legal-compliance",))
    _, a, c = _prove(pz, root)
    assert a["pass"], a["detail"]
    assert c["pass"], c["detail"]
    assert "legal-compliance" not in a["stray_template_folders"]


def test_legal_compliance_alias_without_canonical_agent_fails(pz, tmp_path):
    root = _full_box(pz, tmp_path, extra_dirs=("legal-compliance",), skip_agents=("legal",))
    _, a, _ = _prove(pz, root)
    assert not a["pass"]
    assert a["files_without_agent"] == ["legal"]


def test_variant_spelling_agent_and_lane_satisfy_the_floor_dept(pz, tmp_path):
    # billing-finance chosen and built under its variant "finance": agent dept-finance,
    # lane "finance". The floor dept is met under the spelling it was built as.
    chosen = ["finance" if d == "billing-finance" else d for d in _floor(pz)]
    root = _full_box(pz, tmp_path, chosen=chosen, skip_agents=("billing-finance",),
                     skip_lanes=("billing-finance",))
    _, a, c = _prove(pz, root)
    assert a["pass"], a["detail"]
    assert c["pass"], c["detail"]


def test_rescue_rangers_folder_is_stray_not_required(pz, tmp_path):
    root = _full_box(pz, tmp_path, extra_dirs=("rescue-rangers",))
    _, a, c = _prove(pz, root)
    assert a["pass"] and c["pass"]
    assert a["stray_template_folders"] == ["rescue-rangers"]


def test_no_chosen_list_keeps_every_folder_required(pz, tmp_path):
    root = _full_box(pz, tmp_path, extra_dirs=("launch-operations",))
    os.remove(os.path.join(root, "workspace", "departments.json"))
    _, a, _ = _prove(pz, root)
    assert a["required_source"] == "folder-scan (no chosen list)"
    assert a["files_without_agent"] == ["launch-operations"]
