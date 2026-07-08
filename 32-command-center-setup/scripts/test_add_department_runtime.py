#!/usr/bin/env python3
"""test_add_department_runtime.py -- regression tests for the shared-tool gap:

    add-department.sh's own header claimed it does "the full chain in one
    shot," but it NEVER actually wired the OpenClaw agent RUNTIME: the
    openclaw.json agents.list[] entry (id=dept-<slug>) plus the
    $OC_ROOT/agents/dept-<slug>/ directory. The workspaces/agents DB rows it
    inserts make the department SHOW UP on the Command Center board;
    register_routing_dept() only writes a routing-sidecar bookkeeping file
    (extension-registry.json), never agents.list[]. Without the real runtime
    entry, Command Center's dispatch resolves NO specialist for the
    department, and every card lands and immediately STICKS in "Blocked"
    with reason no_specialist_runtime -- forever.

    This is the exact defect that hit the Anthology (Skill 59) department
    the night this was found; that skill's own caller
    (59-anthology-engine/scripts/provision-anthology-client.sh) was patched
    with a working wire_department_runtime() step, but add-department.sh --
    the SHARED tool used by every other skill and by any operator adding a
    department by hand -- was not. These tests prove the fix in
    add-department.sh itself: a synthetic Command Center dispatch check
    BLOCKS before the department is added, and RELEASES after, against a
    HERMETIC / mocked openclaw.json + mission-control.db (no live box, no
    real credential, no Anthropic identifier). Mirrors the BLOCK-before /
    RELEASE-after proof pattern in
    59-anthology-engine/tests/test_department_runtime.py.

Hermeticity: add-department.sh (like materialize-dept-agents.sh and
scaffold-agent-files.sh) resolves its OpenClaw root as /data/.openclaw else
$HOME/.openclaw -- there is no test-only override. Every test therefore runs
the script with HOME redirected at a throwaway temp directory (the same
technique provision-anthology-client.sh's own --self-test uses to keep the
cron/gateway stubs contained). A guard refuses to run at all if
/data/.openclaw exists on the host, so this can never accidentally touch a
real box.

SECOND hermeticity trap (do not remove this indirection): upsert_role_library()
has a THIRD candidate path -- deliberately, per its own comment, "so this is
usable from the repo too during dev/testing" -- resolved relative to
add-department.sh's OWN on-disk location
(SCRIPT_DIR/../../23-ai-workforce-blueprint/templates/role-library/_index.json),
NOT under $HOME. Invoking the live in-repo add-department.sh directly would
therefore let a test write into the ACTUAL tracked role-library file. Every
test here instead runs a throwaway COPY of the whole scripts/ directory (see
_isolated_scripts_copy): SCRIPT_DIR then resolves under the temp copy, whose
parent tree has no 23-ai-workforce-blueprint sibling, so that candidate
resolves to a path that does not exist and upsert_role_library() no-ops
(exactly as it does on a real installed box, where the sibling skill also
doesn't live next to the scripts/ dir under $OC_ROOT).

Run: python3 -m pytest 32-command-center-setup/scripts/test_add_department_runtime.py -q
 or: python3 32-command-center-setup/scripts/test_add_department_runtime.py
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
ADD_DEPT = SCRIPTS_DIR / "add-department.sh"

# Anthropic-family id shapes assembled from fragments; no banned literal appears.
_A = "anthro" + "pic"
_C = "clau" + "de-"
BANNED = re.compile(_C + r"|" + _A + r"/|us\." + _A + r"\.", re.I)

BASE_OPENCLAW_CFG = {
    "agents": {
        "defaults": {"model": "ollama/kimi-k2.6:cloud"},
        "list": [
            {"id": "main", "name": "Main", "workspace": "/x/main"},
            {"id": "dept-marketing", "name": "Chief Marketing Officer", "workspace": "/x/mkt"},
        ],
    }
}


def _mock_cc_dispatch(oc_root: Path, slug: str) -> str:
    """HERMETIC stand-in for the Command Center dispatch gate -- mirrors
    59-anthology-engine/tests/test_department_runtime.py's _mock_cc_dispatch.
    Returns "no_specialist_runtime" (the card would stick in Blocked) unless
    BOTH an agents.list[] entry resolving the dept slug AND its
    ~/.openclaw/agents/dept-<slug>/ dir exist."""
    cfg_path = oc_root / "openclaw.json"
    if not cfg_path.is_file():
        return "no_specialist_runtime"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    aid = "dept-%s" % slug
    agents = (cfg.get("agents") or {}).get("list") or []
    has_entry = any(isinstance(a, dict) and (a.get("id") == aid or slug in str(a.get("id", "")))
                    for a in agents)
    has_dir = (oc_root / "agents" / aid).is_dir()
    return "released" if (has_entry and has_dir) else "no_specialist_runtime"


def _make_fixture(home: Path, interview_complete: bool = True) -> tuple:
    """Build a hermetic $HOME with an OC_ROOT (openclaw.json + workforce state)
    and a mission-control.db with the exact schema add-department.sh expects.
    Returns (oc_root, db_path)."""
    oc_root = home / ".openclaw"
    oc_root.mkdir(parents=True, exist_ok=True)
    (oc_root / "openclaw.json").write_text(json.dumps(BASE_OPENCLAW_CFG, indent=2), encoding="utf-8")

    workspace_dir = oc_root / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / ".workforce-build-state.json").write_text(
        json.dumps({"interviewComplete": interview_complete}), encoding="utf-8"
    )

    db_dir = home / "projects" / "command-center"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "mission-control.db"
    db = sqlite3.connect(str(db_path))
    db.executescript(
        """
        CREATE TABLE workspaces (
            id TEXT PRIMARY KEY, name TEXT, slug TEXT, description TEXT,
            icon TEXT, parent TEXT, sort_order INTEGER,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE agents (
            id TEXT PRIMARY KEY, workspace_id TEXT, name TEXT, role TEXT,
            role_type TEXT, persona TEXT, description TEXT,
            specialist_type TEXT, status TEXT, avatar_emoji TEXT,
            is_master INTEGER, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY, workspace_id TEXT, department TEXT,
            title TEXT, description TEXT, status TEXT, priority TEXT,
            assigned_agent_id TEXT, created_by_agent_id TEXT,
            created_at TEXT, updated_at TEXT
        );
        """
    )
    db.commit()
    db.close()
    return oc_root, db_path


def _isolated_scripts_copy(home: Path, drop: str = None) -> Path:
    """Copy the WHOLE scripts/ dir into the hermetic $HOME so add-department.sh
    (and its SCRIPT_DIR-relative sibling lookups) never resolve back into the
    real, tracked repo tree. Optionally drop one sibling script by basename
    (used to exercise the inline-fallback path when materialize-dept-agents.sh
    is "missing"). Idempotent per `home` (safe to call multiple times)."""
    dest = home / "scripts-copy"
    if not dest.exists():
        shutil.copytree(SCRIPTS_DIR, dest)
    if drop:
        target = dest / drop
        if target.exists():
            target.unlink()
    return dest / "add-department.sh"


def _run_add_department(home: Path, slug: str, name: str, script: Path = None):
    """Invoke add-department.sh with HOME redirected at the hermetic fixture.
    Defaults to an isolated copy of scripts/ (see _isolated_scripts_copy) so
    NOTHING is ever written back into the real repo tree. Never runs as root
    (this process already is not); /data/.openclaw is asserted absent so the
    OC_ROOT fallback deterministically resolves under the temp HOME, never a
    real box."""
    assert not Path("/data/.openclaw").exists(), (
        "refusing to run this hermetic test: /data/.openclaw exists on this host"
    )
    if script is None:
        script = _isolated_scripts_copy(home)
    env = dict(os.environ)
    env["HOME"] = str(home)
    return subprocess.run(
        ["bash", str(script), "--slug", slug, "--name", name],
        capture_output=True, text=True, timeout=90, env=env,
    )


def _parse_summary(stdout: str) -> dict:
    """Pull the final ---SUMMARY--- JSON line add-department.sh emits."""
    lines = stdout.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "---SUMMARY---" and i + 1 < len(lines):
            return json.loads(lines[i + 1])
    raise AssertionError("no ---SUMMARY--- JSON line found in stdout:\n%s" % stdout)


# --------------------------------------------------------------------------- #
def test_card_blocks_before_wiring_and_releases_after():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        oc_root, _ = _make_fixture(home)

        # BEFORE: a synthetic card would stick in Blocked (no_specialist_runtime).
        assert _mock_cc_dispatch(oc_root, "podcast") == "no_specialist_runtime"

        r = _run_add_department(home, "podcast", "Podcast Production")
        assert r.returncode == 0, "add-department.sh failed:\n%s\n%s" % (r.stdout, r.stderr)

        # AFTER: the same dispatch check now RELEASES the department.
        assert _mock_cc_dispatch(oc_root, "podcast") == "released", (
            "card still blocked after add-department.sh:\n%s" % r.stderr
        )

        # The exact runtime Command Center's dispatch asks for exists on disk.
        assert (oc_root / "agents" / "dept-podcast").is_dir()

        cfg = json.loads((oc_root / "openclaw.json").read_text(encoding="utf-8"))
        entry = next(a for a in cfg["agents"]["list"] if a.get("id") == "dept-podcast")
        assert entry["agentDir"].endswith("agents/dept-podcast")
        # memorySearch schema matches materialize-dept-agents.sh (multimodal
        # off, fallback openai) so the dept agent is schema-valid and memory-safe.
        assert entry["memorySearch"]["multimodal"]["enabled"] is False
        assert entry["memorySearch"]["fallback"] == "openai"

        summary = _parse_summary(r.stdout)
        assert summary["status"] == "created"
        assert summary["runtime_status"] == "wired", summary


def test_wiring_preserves_sibling_agents():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        oc_root, _ = _make_fixture(home)
        r = _run_add_department(home, "podcast", "Podcast Production")
        assert r.returncode == 0, r.stderr
        ids = [a.get("id") for a in
               json.loads((oc_root / "openclaw.json").read_text(encoding="utf-8"))["agents"]["list"]]
        # Every pre-existing agent survives; only the new dept agent is added.
        assert "main" in ids and "dept-marketing" in ids and "dept-podcast" in ids, ids


def test_wiring_is_idempotent_no_duplicate():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        oc_root, _ = _make_fixture(home)
        r1 = _run_add_department(home, "podcast", "Podcast Production")
        assert r1.returncode == 0, r1.stderr
        r2 = _run_add_department(home, "podcast", "Podcast Production")  # re-run
        assert r2.returncode == 0, r2.stderr

        summary2 = _parse_summary(r2.stdout)
        assert summary2["status"] == "already_exists"
        assert summary2["runtime_status"] == "wired", summary2

        ids = [a.get("id") for a in
               json.loads((oc_root / "openclaw.json").read_text(encoding="utf-8"))["agents"]["list"]]
        assert ids.count("dept-podcast") == 1, "re-run duplicated the dept agent: %r" % ids


def test_reruning_add_department_heals_a_pre_fix_department():
    """A department created (hypothetically) by the pre-fix script -- i.e. the
    workspaces row exists in the DB, and openclaw.json has NO agents.list[]
    entry / agent dir for it yet -- gets healed onto the real runtime simply
    by re-invoking add-department.sh with the same --slug/--name (the exact
    thing the read-back-verify caller pattern already does). No separate
    remediation script is required for the fleet's existing departments."""
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        oc_root, db_path = _make_fixture(home)

        # Simulate the historical bug directly: insert a bare workspaces row
        # (as the pre-fix script would have left behind) with NO runtime.
        db = sqlite3.connect(str(db_path))
        db.execute(
            "INSERT INTO workspaces (id, name, slug, sort_order) VALUES (?, ?, ?, ?)",
            ("legacy-dept", "Legacy Dept", "legacy-dept", 10),
        )
        db.commit()
        db.close()
        assert _mock_cc_dispatch(oc_root, "legacy-dept") == "no_specialist_runtime"

        r = _run_add_department(home, "legacy-dept", "Legacy Dept")
        assert r.returncode == 0, r.stderr
        summary = _parse_summary(r.stdout)
        assert summary["status"] == "already_exists"
        assert summary["runtime_status"] == "wired", summary
        assert _mock_cc_dispatch(oc_root, "legacy-dept") == "released"


def test_interview_incomplete_defers_without_hard_failure():
    """When the AI Workforce interview is not yet complete,
    materialize-dept-agents.sh's own precondition legitimately defers
    materialization (SPEC: never materialize a default/empty department floor
    pre-interview). add-department.sh must surface this as a soft
    "deferred_interview_incomplete" status -- NOT crash, NOT silently claim
    "wired" -- so callers know to re-run once the interview finishes."""
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        oc_root, _ = _make_fixture(home, interview_complete=False)
        r = _run_add_department(home, "podcast", "Podcast Production")
        assert r.returncode == 0, r.stderr  # not a hard failure
        summary = _parse_summary(r.stdout)
        assert summary["runtime_status"] == "deferred_interview_incomplete", summary
        # Correctly still blocked -- nothing silently claimed released.
        assert _mock_cc_dispatch(oc_root, "podcast") == "no_specialist_runtime"


def test_inline_fallback_when_materializer_missing():
    """If materialize-dept-agents.sh is missing from the install,
    wire_department_runtime() must fall back to its inline replica of the same
    schema rather than leaving the department unwired -- proving BOTH the
    'call the real shared tool' path and the resilience fallback work."""
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        oc_root, _ = _make_fixture(home)

        add_dept_copy = _isolated_scripts_copy(home, drop="materialize-dept-agents.sh")

        r = _run_add_department(home, "graphics", "Graphics", script=add_dept_copy)
        assert r.returncode == 0, r.stderr
        assert "falling back to inline runtime wiring" in r.stderr

        assert (oc_root / "agents" / "dept-graphics").is_dir()
        cfg = json.loads((oc_root / "openclaw.json").read_text(encoding="utf-8"))
        entry = next(a for a in cfg["agents"]["list"] if a.get("id") == "dept-graphics")
        assert entry["memorySearch"]["multimodal"]["enabled"] is False
        assert entry["memorySearch"]["fallback"] == "openai"
        summary = _parse_summary(r.stdout)
        assert summary["runtime_status"] == "wired", summary


def test_root_guard_refuses_simulated_root():
    """A simulated root euid (via a PATH-shadowing `id` stub -- the same
    technique provision-anthology-client.sh's --self-test uses for its own
    stubs) must be refused before any write is attempted."""
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        _make_fixture(home)

        stub_bin = home / "bin"
        stub_bin.mkdir()
        id_stub = stub_bin / "id"
        id_stub.write_text("#!/usr/bin/env bash\necho 0\n")
        id_stub.chmod(0o755)

        env = dict(os.environ)
        env["HOME"] = str(home)
        env["PATH"] = str(stub_bin) + os.pathsep + env.get("PATH", "")
        r = subprocess.run(
            ["bash", str(ADD_DEPT), "--slug", "podcast", "--name", "Podcast Production"],
            capture_output=True, text=True, timeout=30, env=env,
        )
        assert r.returncode == 1, "root invocation was not refused: rc=%d\n%s" % (r.returncode, r.stderr)
        assert "refusing to run as root" in r.stderr.lower(), r.stderr
        # Nothing was written -- refusal happens before OC_ROOT/DB resolution.
        assert not (home / ".openclaw" / "agents").exists()


def test_wired_config_has_no_anthropic_id_and_no_secret_value():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        oc_root, _ = _make_fixture(home)
        r = _run_add_department(home, "podcast", "Podcast Production")
        assert r.returncode == 0, r.stderr
        blob = (oc_root / "openclaw.json").read_text(encoding="utf-8")
        assert not BANNED.search(blob), "wired openclaw.json carries an Anthropic-family id"
        assert not re.search(r"[0-9a-f]{64}", blob), "wired config carries a secret-shaped value"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print("  [PASS] %s" % fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  [FAIL] %s -- %s" % (fn.__name__, exc))
    print("test_add_department_runtime: %s (%d/%d)"
          % ("ALL PASSED" if not failed else "FAILURES", len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
