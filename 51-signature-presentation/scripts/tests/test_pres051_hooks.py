"""PRES-051 tests: supported plugin hook registration + bounded scripts.

Contract under test (HOOKS-AND-ENFORCEMENT.md + TODO PRES-051):
  * stdin JSON schema validation (malformed / missing / wrong-event / oversized);
  * explicit company/presentation/run binding (env triple or session file; no
    cwd guessing, no default operator identity);
  * install-relative paths (no $HOME hardcode; paths containing spaces);
  * no recursive Claude invocation, no paid work on startup;
  * enforcement stays in engine transactions — hooks delegate read-only, and
    the hook layer refuses --run/--close/--new by construction;
  * bounded Stop handling: stop_hook_active guard + persisted reentry budget,
    visible resumable blocked state, no endless loop;
  * doctor install/uninstall preserves unrelated hooks, removes only owned.

Hermetic: the fake engine entry prints canned status JSON from env, so these
tests never touch a real engine, real credentials, or the network.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import sp_hook_common as c  # noqa: E402
import sp_stop  # noqa: E402

HOOK_SH = HOOKS_DIR / "sp-hook.sh"
SESSION_SCHEMA = c.SESSION_CONTEXT_SCHEMA


@pytest.fixture()
def fake_env(tmp_path: Path) -> dict:
    """A fake engine: presentation_job.py shim reading FAKE_STATE_JSON env."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "presentation_job.py").write_text(
        textwrap.dedent(
            """
            import json, os, sys
            if "--status" in sys.argv and "--json" in sys.argv:
                print(os.environ.get("FAKE_STATE_JSON", "{}"))
                sys.exit(0)
            if "--diagnose-only" in sys.argv:
                print("diagnosis")
                sys.exit(0)
            sys.exit(3)
            """
        ),
        encoding="utf-8",
    )
    run = tmp_path / "run"
    run.mkdir()
    state = {
        "job_id": "pj_fake123",
        "terminal": "in progress",
        "phases": [],
        "gates": {"qc": {"state": "fail", "reason": "no report"}},
        "manifest_sha256": "a" * 64,
    }
    env = dict(
        os.environ,
        SCRIPTS_DIR=str(scripts),
        FAKE_STATE_JSON=json.dumps(state),
        PRESENTATION_COMPANY_ID="acme",
        PRESENTATION_ID="deck1",
        PRESENTATION_RUN_DIR=str(run),
    )
    return {"env": env, "run": run, "scripts": scripts, "state": state}


def apply_env(monkeypatch, env: dict) -> None:
    for key, value in env.items():
        if key.startswith(("PRESENTATION_", "SCRIPTS_DIR", "FAKE_STATE_JSON", "OPENCLAW_")):
            monkeypatch.setenv(key, value)


def run_hook(sub: str, doc: str, env: dict, cwd: str = "/tmp") -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(HOOK_SH), sub],
        input=doc,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        cwd=cwd,
    )


# ---------------------------------------------------------------------------
# stdin schema validation
# ---------------------------------------------------------------------------
def test_stdin_malformed_json_is_bounded_no_certification(monkeypatch, tmp_path: Path):
    f = tmp_path / "in.json"
    f.write_text("{not json", encoding="utf-8")
    with f.open("r", encoding="utf-8") as fh:
        monkeypatch.setattr(sys, "stdin", fh)
        ev, err = c.read_stdin_event()
    assert ev is None
    assert err == "STDIN_MALFORMED_JSON"


def test_validate_event_rejects_missing_fields():
    event = {"session_id": "s1", "hook_event_name": "SessionStart"}
    assert c.validate_event(event, "SessionStart") is not None
    event2 = {"session_id": "", "hook_event_name": "SessionStart", "cwd": "/tmp"}
    assert c.validate_event(event2, "SessionStart") == "BAD_SESSION_ID"


def test_validate_event_rejects_wrong_event():
    event = {"session_id": "s1", "hook_event_name": "Stop", "cwd": "/tmp"}
    assert c.validate_event(event, "SessionStart") is not None
    assert c.validate_event(event, "Stop") is None


def test_stdin_oversize_rejected(monkeypatch, tmp_path: Path):
    p = tmp_path / "big.txt"
    p.write_text("x" * (c.MAX_STDIN_BYTES + 10), encoding="utf-8")
    with p.open("r", encoding="utf-8") as fh:
        monkeypatch.setattr(sys, "stdin", fh)
        ev, err = c.read_stdin_event()
        assert err == "STDIN_TOO_LARGE"


def test_stdin_empty_rejected(monkeypatch, tmp_path: Path):
    f = tmp_path / "empty.json"
    f.write_text("", encoding="utf-8")
    with f.open("r", encoding="utf-8") as fh:
        monkeypatch.setattr(sys, "stdin", fh)
        ev, err = c.read_stdin_event()
        assert err == "STDIN_EMPTY"


# ---------------------------------------------------------------------------
# binding
# ---------------------------------------------------------------------------
def test_resolve_context_env_triple(fake_env, monkeypatch):
    apply_env(monkeypatch, fake_env["env"])
    bound, why = c.resolve_context({"cwd": "/tmp"})
    assert why == ""
    assert bound["company_id"] == "acme" and bound["presentation_id"] == "deck1"
    assert bound["source"] == "env"


def test_resolve_context_partial_env_rejected(fake_env, monkeypatch):
    apply_env(monkeypatch, fake_env["env"])
    monkeypatch.setenv("PRESENTATION_RUN_DIR", "")
    bound, why = c.resolve_context({"cwd": "/tmp"})
    assert bound is None and "UNBOUND" in why


def test_resolve_context_session_file_with_spaces(fake_env, tmp_path: Path):
    run = tmp_path / "run dir with spaces"
    run.mkdir()
    proj = tmp_path / "project dir"
    proj.mkdir()
    (proj / ".presentation-session.json").write_text(
        json.dumps(
            {"schema": SESSION_SCHEMA, "company_id": "spaceco",
             "presentation_id": "deck-s", "run_dir": str(run)}
        ),
        encoding="utf-8",
    )
    bound, why = c.resolve_context({"cwd": str(proj)})
    assert why == ""
    assert bound["run_dir"] == str(run.resolve())
    assert bound["source"].startswith("session-file:")


def test_resolve_context_bad_schema_rejected(fake_env, tmp_path: Path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".presentation-session.json").write_text(
        json.dumps({"schema": "not-the-schema", "company_id": "x", "presentation_id": "y",
                    "run_dir": str(tmp_path)}),
        encoding="utf-8",
    )
    bound, why = c.resolve_context({"cwd": str(proj)})
    assert bound is None and "UNBOUND" in why


def test_resolve_context_no_binding_yields_setup_instruction(fake_env):
    for key in ("PRESENTATION_COMPANY_ID", "PRESENTATION_ID", "PRESENTATION_RUN_DIR"):
        os.environ.pop(key, None)
    bound, why = c.resolve_context({"cwd": "/tmp/nonexistent-bind"})
    assert bound is None
    assert "UNBOUND" in why and ".presentation-session.json" in why


# ---------------------------------------------------------------------------
# read-only delegation
# ---------------------------------------------------------------------------
def test_run_engine_readonly_refuses_mutating_argv():
    rc, out, err = c.run_engine_readonly(None, Path("/tmp"), ("--close",))
    assert rc == 99 and "REFUSED" in err
    rc, out, err = c.run_engine_readonly(None, Path("/tmp"), ("--run",))
    assert rc == 99
    rc, out, err = c.run_engine_readonly(None, Path("/tmp"), ("--new",))
    assert rc == 99
    rc, out, err = c.run_engine_readonly(None, Path("/tmp"), ("--resume", "--diagnose-only"))
    assert rc != 99 and "REFUSED" not in err  # argv allowed (read-only); spawn fails without an entry


def test_run_engine_readonly_allows_status(fake_env, monkeypatch):
    apply_env(monkeypatch, fake_env["env"])
    entry = fake_env["scripts"] / "presentation_job.py"
    rc, out, err = c.run_engine_readonly(entry, fake_env["run"], ("--status", "--json"))
    assert rc == 0
    assert json.loads(out)["job_id"] == "pj_fake123"


def test_read_engine_status_parses(fake_env, monkeypatch):
    apply_env(monkeypatch, fake_env["env"])
    entry = fake_env["scripts"] / "presentation_job.py"
    state, err = c.read_engine_status(entry, fake_env["run"])
    assert err == "" and state["job_id"] == "pj_fake123"


# ---------------------------------------------------------------------------
# Stop: bounded, reentry-guarded, resumable
# ---------------------------------------------------------------------------
def test_stop_completion_claim_without_evidence_gives_corrective_feedback(fake_env):
    ev = json.dumps(
        {"session_id": "s1", "hook_event_name": "Stop", "cwd": "/tmp",
         "stop_hook_active": False,
         "last_assistant_message": "All done, deck complete and delivered!"}
    )
    p = run_hook("stop", ev, fake_env["env"])
    assert p.returncode == 0
    assert "completion claimed" in p.stderr
    assert "--resume" in p.stderr
    budget = json.loads((fake_env["run"] / "working" / ".sp-stop-budget.json").read_text())
    assert budget["used"] == 1


def test_stop_identical_state_reentry_guard(fake_env):
    ev = json.dumps(
        {"session_id": "s1", "hook_event_name": "Stop", "cwd": "/tmp",
         "stop_hook_active": False, "last_assistant_message": "done complete"}
    )
    run_hook("stop", ev, fake_env["env"])
    p2 = run_hook("stop", ev, fake_env["env"])
    assert p2.returncode == 0
    assert "reentry guard" in p2.stderr
    budget = json.loads((fake_env["run"] / "working" / ".sp-stop-budget.json").read_text())
    assert budget["used"] == 1  # identical state answered once only


def test_stop_hook_active_allows_immediately(fake_env):
    ev = json.dumps(
        {"session_id": "s1", "hook_event_name": "Stop", "cwd": "/tmp",
         "stop_hook_active": True, "last_assistant_message": "done"}
    )
    p = run_hook("stop", ev, fake_env["env"])
    assert p.returncode == 0
    assert "stop_hook_active=true" in p.stderr
    assert "completion claimed" not in p.stderr


def test_stop_budget_exhausted_allows(fake_env):
    budget = fake_env["run"] / "working" / ".sp-stop-budget.json"
    budget.parent.mkdir(exist_ok=True)
    budget.write_text(json.dumps({"used": 99, "last_hash": "", "updated_at": ""}))
    ev = json.dumps(
        {"session_id": "s1", "hook_event_name": "Stop", "cwd": "/tmp",
         "stop_hook_active": False, "last_assistant_message": "done complete"}
    )
    p = run_hook("stop", ev, fake_env["env"])
    assert p.returncode == 0
    assert "budget spent" in p.stderr


def test_stop_suspended_note_when_supervisor_unconfigured(fake_env):
    ev = json.dumps(
        {"session_id": "s1", "hook_event_name": "Stop", "cwd": "/tmp",
         "stop_hook_active": False, "last_assistant_message": "done complete"}
    )
    env = dict(fake_env["env"])
    env.pop("PRESENTATION_SCAN_ROOTS", None)
    p = run_hook("stop", ev, env)
    assert "suspended" in p.stderr or "scan root" in p.stderr


def test_stop_no_feedback_when_engine_evidence_ok(fake_env):
    state = json.loads(fake_env["env"]["FAKE_STATE_JSON"])
    state["terminal"] = "DONE"
    state["gates"] = {}
    env = dict(fake_env["env"], FAKE_STATE_JSON=json.dumps(state))
    ev = json.dumps(
        {"session_id": "s1", "hook_event_name": "Stop", "cwd": "/tmp",
         "stop_hook_active": False, "last_assistant_message": "done complete"}
    )
    p = run_hook("stop", ev, env)
    assert p.returncode == 0
    assert "no corrective feedback owed" in p.stderr


# ---------------------------------------------------------------------------
# hygiene: no secrets, no recursive claude, no paid work
# ---------------------------------------------------------------------------
def test_no_secret_in_hook_output(fake_env):
    env = dict(fake_env["env"], PRESENTATION_TOKEN="sk-ant-fake-secret-value")
    ev = json.dumps(
        {"session_id": "s1", "hook_event_name": "SessionStart", "cwd": "/tmp",
         "source": "startup"}
    )
    p = run_hook("session-start", ev, env)
    blob = p.stdout + p.stderr
    assert "sk-ant-fake-secret-value" not in blob
    assert "sk-ant-" not in blob


def test_handlers_never_spawn_claude_or_install(fake_env):
    src = "".join(f.read_text(encoding="utf-8") for f in HOOKS_DIR.glob("*.py"))
    src += (HOOKS_DIR / "sp-hook.sh").read_text(encoding="utf-8")
    assert "claude --" not in src
    assert "claude -p" not in src
    assert "pip install" not in src
    assert "npm install" not in src
    assert "brew install" not in src


def test_pre_tool_use_unrelated_passes(fake_env):
    ev = json.dumps(
        {"session_id": "s1", "hook_event_name": "PreToolUse", "cwd": "/tmp",
         "tool_name": "Bash", "tool_input": {"command": "ls /tmp"}}
    )
    p = run_hook("pre-tool-use", ev, fake_env["env"])
    assert p.returncode == 0
    assert p.stderr == ""


def test_pre_tool_use_relevant_delegates_without_approving(fake_env):
    ev = json.dumps(
        {"session_id": "s1", "hook_event_name": "PreToolUse", "cwd": "/tmp",
         "tool_name": "Bash",
         "tool_input": {"command": "python3 presentation_job.py --close --run-dir x"}}
    )
    p = run_hook("pre-tool-use", ev, fake_env["env"])
    assert p.returncode == 0
    assert "does not approve the transition" in p.stderr


def test_post_tool_use_records_never_receipt(fake_env):
    ev = json.dumps(
        {"session_id": "s1", "hook_event_name": "PostToolUse", "cwd": "/tmp",
         "tool_name": "Bash", "tool_input": {"command": "echo hi"},
         "tool_response": {"exit": 0}, "tool_use_id": "tu_1"}
    )
    p = run_hook("post-tool-use", ev, fake_env["env"])
    assert p.returncode == 0
    assert "Authoritative verification stays with the engine" in p.stderr
    lines = (fake_env["run"] / "working" / "logs" / "sp-post-tool-use.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["tool_use_id"] == "tu_1"
    assert "never an uploaded/complete receipt" in rec["note"]


# ---------------------------------------------------------------------------
# doctor install/uninstall
# ---------------------------------------------------------------------------
def test_doctor_install_preserves_unrelated_and_dedupes(fake_env, tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo unrelated", "timeout": 5}]}]}}),
        encoding="utf-8",
    )
    backup = tmp_path / "backup"
    skill_dir = HOOKS_DIR.parent.parent
    for _ in range(2):
        p = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "sp_doctor.py"), "--skill-dir", str(skill_dir),
             "--install", "--settings", str(settings), "--backup-dir", str(backup)],
            capture_output=True, text=True, timeout=60,
        )
        assert p.returncode == 0
    data = json.loads(settings.read_text())
    stop_groups = data["hooks"]["Stop"]
    assert any("echo unrelated" in str(g) for g in stop_groups)
    owned = sum(
        1 for g in stop_groups for h in (g or {}).get("hooks", [])
        if "sp-hook.sh" in (h or {}).get("command", "")
    )
    assert owned == 1  # deduped across two installs
    backups = list(backup.glob("settings-*.bak.json"))
    assert backups  # backup written


def test_doctor_uninstall_removes_only_owned(fake_env, tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo unrelated"}]}]}}),
        encoding="utf-8",
    )
    skill_dir = HOOKS_DIR.parent.parent
    subprocess.run(
        [sys.executable, str(HOOKS_DIR / "sp_doctor.py"), "--skill-dir", str(skill_dir),
         "--install", "--settings", str(settings), "--backup-dir", str(tmp_path / "bak")],
        capture_output=True, text=True, timeout=60, check=True,
    )
    p = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "sp_doctor.py"), "--skill-dir", str(skill_dir),
         "--uninstall", "--settings", str(settings)],
        capture_output=True, text=True, timeout=60,
    )
    assert p.returncode == 0
    data = json.loads(settings.read_text())
    owned_left = sum(
        1 for e, groups in data["hooks"].items() for g in groups
        for h in (g or {}).get("hooks", []) if "sp-hook.sh" in (h or {}).get("command", "")
    )
    assert owned_left == 0
    assert "echo unrelated" in settings.read_text()


def test_doctor_check_registration_reports_owned(fake_env, tmp_path: Path):
    settings = tmp_path / "settings.json"
    skill_dir = HOOKS_DIR.parent.parent
    subprocess.run(
        [sys.executable, str(HOOKS_DIR / "sp_doctor.py"), "--skill-dir", str(skill_dir),
         "--install", "--settings", str(settings), "--backup-dir", str(tmp_path / "bak")],
        capture_output=True, text=True, timeout=60, check=True,
    )
    p = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "sp_doctor.py"), "--check-registration",
         "--settings", str(settings)],
        capture_output=True, text=True, timeout=60,
    )
    assert p.returncode == 0
    report = json.loads(p.stdout)
    assert report["ok"] and report["owned_count"] == 4
    assert set(report["events"]) == {"SessionStart", "PreToolUse", "PostToolUse", "Stop"}
