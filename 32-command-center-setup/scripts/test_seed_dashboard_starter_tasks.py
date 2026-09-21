"""Regression test: seed-dashboard-content.py must not write starter tasks on an
--update-only roll.

THE INCIDENT. The seeder's per-workspace guard is "this workspace has zero
tasks". On a MATURE board that is true of every department the client has simply
never used. run-full-install.sh Phase 6e ran the seeder in BOTH full and
--update-only mode, so a routine code roll dropped ten fresh
"Welcome to <department>" cards into a live client backlog months after install
— and the Command Center's grooming loop then spawned failing
"Author SOP: Welcome to X" follow-on work off them.

THE CONTRACT these tests pin:
  * --no-starter-tasks / SEED_STARTER_TASKS=0 writes ZERO tasks, even into
    workspaces that have none;
  * the companies row and the per-department head-agent rows are STILL ensured
    (idempotent identity/runtime rows, not board content);
  * the default (a full install) is unchanged — starter tasks still seed.
"""
import importlib.util
import os
import sqlite3

import pytest

_SD = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "seed-dashboard-content.py")
_spec = importlib.util.spec_from_file_location("seed_dashboard_content", _SD)
_sd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sd)


@pytest.fixture(autouse=True)
def _no_scaffold(monkeypatch):
    """The dept-head scaffolder shells out and writes agent files on a real box.
    Stub it: these tests are about rows, not files."""
    monkeypatch.setattr(_sd, "scaffold_agent_files", lambda *a, **k: True)


@pytest.fixture
def db(tmp_path):
    """A dashboard DB with two workspaces and an EMPTY tasks table — the exact
    state a never-used department is in on a mature board."""
    conn = sqlite3.connect(tmp_path / "mission-control.db")
    conn.executescript(
        """
        CREATE TABLE companies (id TEXT PRIMARY KEY, name TEXT, slug TEXT,
            owner_name TEXT, industry TEXT, primary_color TEXT,
            accent_color TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT, slug TEXT UNIQUE,
            description TEXT, icon TEXT, company_id TEXT);
        CREATE TABLE agents (id TEXT PRIMARY KEY, workspace_id TEXT, name TEXT,
            role TEXT, persona TEXT, description TEXT, specialist_type TEXT,
            status TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE tasks (id TEXT PRIMARY KEY, workspace_id TEXT, department TEXT,
            title TEXT, description TEXT, status TEXT, priority TEXT,
            assigned_agent_id TEXT, created_by_agent_id TEXT,
            created_at TEXT, updated_at TEXT);
        INSERT INTO workspaces (id, name, slug) VALUES
            ('ws-mkt', 'Marketing', 'marketing'),
            ('ws-leg', 'Legal', 'legal');
        """
    )
    conn.commit()
    return conn


_INFO = {"name": "Acme", "slug": "acme", "industry": "", "owner_name": "",
         "primary": "#111111", "accent": "#222222"}


def _counts(conn):
    n = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
    return n("companies"), n("agents"), n("tasks")


def test_starter_tasks_disabled_writes_zero_tasks(db):
    _sd.insert_company(db, _INFO)
    agents_added, tasks_added = _sd.insert_agents_and_tasks(
        db, _INFO, starter_tasks=False)
    db.commit()

    companies, agents, tasks = _counts(db)
    assert tasks_added == 0
    assert tasks == 0, "an update-only roll must never write a card into a live backlog"
    # ...but identity and runtime rows ARE still ensured.
    assert companies == 1
    assert agents_added == 2 and agents == 2
    roles = {r[0] for r in db.execute("SELECT role FROM agents")}
    assert roles == {"Marketing Department Head", "Legal Department Head"}


def test_no_welcome_card_is_created_when_disabled(db):
    _sd.insert_company(db, _INFO)
    _sd.insert_agents_and_tasks(db, _INFO, starter_tasks=False)
    db.commit()
    titles = [r[0] for r in db.execute("SELECT title FROM tasks")]
    assert not any(t.startswith("Welcome to ") for t in titles), titles


def test_full_install_default_still_seeds_starter_tasks(db):
    _sd.insert_company(db, _INFO)
    agents_added, tasks_added = _sd.insert_agents_and_tasks(db, _INFO)
    db.commit()
    _, _, tasks = _counts(db)
    assert agents_added == 2
    assert tasks_added == 2 and tasks == 2
    titles = sorted(r[0] for r in db.execute("SELECT title FROM tasks"))
    assert titles == ["Welcome to Legal", "Welcome to Marketing"]


def test_disabled_run_is_idempotent_and_leaves_real_tasks_alone(db):
    # A board that already carries the client's own work.
    db.execute(
        "INSERT INTO tasks (id, workspace_id, department, title, status) "
        "VALUES ('t1', 'ws-mkt', 'marketing', 'Q3 launch plan', 'backlog')")
    db.commit()

    for _ in range(2):
        _sd.insert_company(db, _INFO)
        _sd.insert_agents_and_tasks(db, _INFO, starter_tasks=False)
        db.commit()

    companies, agents, tasks = _counts(db)
    assert (companies, agents, tasks) == (1, 2, 1)
    assert db.execute("SELECT title FROM tasks").fetchone()[0] == "Q3 launch plan"


# ─── flag / env parsing ──────────────────────────────────────────────────────

def test_flag_disables(monkeypatch):
    monkeypatch.delenv("SEED_STARTER_TASKS", raising=False)
    assert _sd.starter_tasks_enabled(["--no-starter-tasks"]) is False


def test_default_is_enabled(monkeypatch):
    monkeypatch.delenv("SEED_STARTER_TASKS", raising=False)
    assert _sd.starter_tasks_enabled([]) is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "OFF", "False"])
def test_env_var_disables(monkeypatch, value):
    monkeypatch.setenv("SEED_STARTER_TASKS", value)
    assert _sd.starter_tasks_enabled([]) is False


@pytest.mark.parametrize("value", ["1", "true", "yes", ""])
def test_env_var_other_values_leave_it_enabled(monkeypatch, value):
    monkeypatch.setenv("SEED_STARTER_TASKS", value)
    assert _sd.starter_tasks_enabled([]) is True


def test_unrelated_argv_does_not_disable(monkeypatch):
    # parse_known_args must ignore anything else a caller passes.
    monkeypatch.delenv("SEED_STARTER_TASKS", raising=False)
    assert _sd.starter_tasks_enabled(["--company-slug", "acme"]) is True
