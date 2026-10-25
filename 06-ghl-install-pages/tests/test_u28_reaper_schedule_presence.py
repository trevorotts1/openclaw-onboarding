"""U28 (B-U14) item 4 — schedule-presence check: "assert the reaper schedule
is actually installed ... a reaper that exists but never runs is the
false-done pattern" (spec text, verbatim).

Exercises the REAL script (scripts/check-agent-browser-reaper-schedule.sh)
against a stubbed `openclaw` CLI on PATH — hermetic (no real gateway, no
network), proving the script's PASS (registered AND enabled) / ABSENT /
DISABLED / UNKNOWN logic and its exit codes for real, not by re-implementing
the check inline. Cross-platform by
construction: the script queries `openclaw cron list --json` (the same
uniform Mac/VPS abstraction scripts/ensure-pipeline-crons.sh already relies
on), never a native launchd/crontab call — see the script's own header for
why that makes ONE script correct on both platforms.

A genuine LIVE run against this repo checkout's real `openclaw` CLI (when
present) is documented in the U28 ledger note, not asserted here — a pytest
suite must stay hermetic/portable and never depend on a specific box's live
cron registry to pass in CI.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).parent.resolve()
_SCRIPT = _TESTS_DIR.parent / "scripts" / "check-agent-browser-reaper-schedule.sh"
# Resolved ONCE against the real (test-runner) PATH so a test that crafts a
# restricted PATH for the SCRIPT's own lookups (e.g. to hide `openclaw`)
# doesn't also make `bash` itself unresolvable to subprocess.run.
_BASH = shutil.which("bash") or "/bin/bash"


def _write_stub_openclaw(bindir: Path, jobs: list, *, broken: bool = False) -> Path:
    """A fake `openclaw` whose `cron list --json` prints a fixed jobs array
    (or, if `broken`, prints nothing / fails, to exercise the UNKNOWN path)."""
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "openclaw"
    if broken:
        body = 'echo "" ; exit 1\n'
    else:
        payload = json.dumps({"jobs": jobs}).replace("'", "'\\''")
        body = (
            'case "$*" in\n'
            f"  *\"cron list\"*) echo '{payload}' ;;\n"
            '  *) echo "" ;;\n'
            'esac\n'
            'exit 0\n'
        )
    stub.write_text(f"#!/usr/bin/env bash\n{body}", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub


def _run(env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_BASH, str(_SCRIPT)], capture_output=True, text=True, env=env, timeout=30,
    )


def _jq_only_env(tmp_path: Path, jobs: list):
    """PATH where the script's jq branch is the ONLY possible parser:
    the stub `openclaw` + symlinks to just the external tools the script and
    cron-lib.sh need — and deliberately NO python3. Returns None (caller
    skips) when jq isn't installed on this box."""
    bindir = tmp_path / "jq-bin"
    _write_stub_openclaw(bindir, jobs)
    for tool in ("bash", "dirname", "grep", "jq"):
        real = shutil.which(tool)
        if real is None:
            return None
        link = bindir / tool
        if not link.exists():
            link.symlink_to(real)
    return dict(os.environ, PATH=str(bindir))


class TestSchedulePresenceCheck:
    def test_present_and_enabled_exits_0(self, tmp_path):
        bindir = tmp_path / "bin"
        _write_stub_openclaw(bindir, [
            {"name": "agent-browser-reaper", "cron": "13 * * * *", "enabled": True},
            {"name": "some-other-cron", "cron": "0 * * * *", "enabled": True},
        ])
        env = dict(os.environ, PATH=f"{bindir}:{os.environ.get('PATH', '')}")
        res = _run(env)
        assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        assert "PASS" in res.stdout and "ENABLED" in res.stdout
        assert "13 * * * *" in res.stdout, "must surface the registered schedule by name"

    def test_absent_exits_1(self, tmp_path):
        bindir = tmp_path / "bin"
        _write_stub_openclaw(bindir, [
            {"name": "some-other-cron", "cron": "0 * * * *"},
        ])
        env = dict(os.environ, PATH=f"{bindir}:{os.environ.get('PATH', '')}")
        res = _run(env)
        assert res.returncode == 1, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        assert "FAIL" in res.stdout and "ABSENT" in res.stdout

    def test_empty_registry_exits_1_not_0(self, tmp_path):
        """Zero jobs registered anywhere must never be misread as PRESENT."""
        bindir = tmp_path / "bin"
        _write_stub_openclaw(bindir, [])
        env = dict(os.environ, PATH=f"{bindir}:{os.environ.get('PATH', '')}")
        res = _run(env)
        assert res.returncode == 1
        assert "ABSENT" in res.stdout

    def test_no_openclaw_cli_exits_2_unknown_not_1(self, tmp_path):
        """A missing CLI is UNKNOWN (2), never conflated with a confirmed
        ABSENT (1) — a broken check must never masquerade as a real finding."""
        empty_bin = tmp_path / "empty-bin"
        empty_bin.mkdir()
        # A PATH with no openclaw at all (but keep enough of the real PATH for
        # bash itself to resolve, minus any dir that happens to carry a real
        # openclaw shim).
        env = dict(os.environ, PATH=str(empty_bin))
        res = _run(env)
        assert res.returncode == 2, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        assert "UNKNOWN" in res.stdout

    def test_broken_cli_output_exits_2_unknown(self, tmp_path):
        bindir = tmp_path / "bin"
        _write_stub_openclaw(bindir, [], broken=True)
        env = dict(os.environ, PATH=f"{bindir}:{os.environ.get('PATH', '')}")
        res = _run(env)
        # A failing `cron list` makes oc_cron_present return 2 (UNKNOWN:
        # "failed CLI call is UNKNOWN, never 'absent'" — D10), so this script
        # must surface UNKNOWN (2), never the confirmed ABSENT (1) the
        # contract reserves for "ran cleanly and found no such name".
        assert res.returncode == 2, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        assert "UNKNOWN" in res.stdout
        assert "ABSENT" not in res.stdout

    def test_never_dumps_other_jobs_message_bodies(self, tmp_path):
        """BY NAME ONLY: another job's --message/--command payload must never
        appear in this script's stdout."""
        bindir = tmp_path / "bin"
        secret_marker = "OTHER-JOB-SECRET-PAYLOAD-MARKER"
        _write_stub_openclaw(bindir, [
            {"name": "agent-browser-reaper", "cron": "13 * * * *", "enabled": True},
            {"name": "some-other-cron", "cron": "0 * * * *", "command": secret_marker},
        ])
        env = dict(os.environ, PATH=f"{bindir}:{os.environ.get('PATH', '')}")
        res = _run(env)
        assert res.returncode == 0
        assert secret_marker not in res.stdout
        assert secret_marker not in res.stderr


class TestRegisteredIsNotEnabled:
    """Finding 28 (oct-25-fixes.md): "The check is presence-based and counts
    disabled jobs, so it can report PASS for a disabled reaper (live:
    agent-browser-reaper exists with enabled=false)." A registered-but-disabled
    reaper never runs, so presence must never be the verdict."""

    def test_registered_but_disabled_exits_3(self, tmp_path):
        bindir = tmp_path / "bin"
        _write_stub_openclaw(bindir, [
            {"name": "agent-browser-reaper", "cron": "13 * * * *", "enabled": False},
        ])
        env = dict(os.environ, PATH=f"{bindir}:{os.environ.get('PATH', '')}")
        res = _run(env)
        assert res.returncode == 3, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        assert "DISABLED" in res.stdout
        assert "FAIL" in res.stdout
        assert "PASS" not in res.stdout, "a disabled reaper must never print PASS"

    def test_disabled_via_status_field_exits_3(self, tmp_path):
        """No `enabled` key, computed `status: "disabled"` instead — the
        documented fallback must still catch it."""
        bindir = tmp_path / "bin"
        _write_stub_openclaw(bindir, [
            {"name": "agent-browser-reaper", "cron": "13 * * * *", "status": "disabled"},
        ])
        env = dict(os.environ, PATH=f"{bindir}:{os.environ.get('PATH', '')}")
        res = _run(env)
        assert res.returncode == 3, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        assert "DISABLED" in res.stdout

    def test_enabled_unknown_exits_2_not_0(self, tmp_path):
        """Neither `enabled` nor `status`: state is UNDETERMINED, and an
        undetermined backstop is not a proven backstop."""
        bindir = tmp_path / "bin"
        _write_stub_openclaw(bindir, [
            {"name": "agent-browser-reaper", "cron": "13 * * * *"},
        ])
        env = dict(os.environ, PATH=f"{bindir}:{os.environ.get('PATH', '')}")
        res = _run(env)
        assert res.returncode == 2, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        assert "UNKNOWN" in res.stdout
        assert "PASS" not in res.stdout

    def test_check_never_mutates_the_registry(self, tmp_path):
        """Reactivation requires authorization: the check must issue no
        mutating `cron` subcommand. The stub records every argv it was
        called with and the test asserts only a `list` ever appears."""
        bindir = tmp_path / "bin"
        argv_log = tmp_path / "argv.log"
        bindir.mkdir(parents=True, exist_ok=True)
        stub = bindir / "openclaw"
        payload = json.dumps({"jobs": [
            {"name": "agent-browser-reaper", "cron": "13 * * * *", "enabled": False},
        ]})
        stub.write_text(
            "#!/usr/bin/env bash\n"
            f'printf "%s\\n" "$*" >> "{argv_log}"\n'
            'case "$*" in\n'
            f"  *\"cron list\"*) echo '{payload}' ;;\n"
            '  *) echo "" ;;\n'
            'esac\n'
            'exit 0\n',
            encoding="utf-8",
        )
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        env = dict(os.environ, PATH=f"{bindir}:{os.environ.get('PATH', '')}")
        res = _run(env)
        assert res.returncode == 3
        calls = [ln.strip() for ln in argv_log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        mutating = [c for c in calls if "cron" in c and "cron list" not in c]
        assert not mutating, f"check invoked a non-list cron subcommand: {mutating}"

    def test_status_active_without_enabled_exits_0(self, tmp_path):
        """No `enabled` key, computed `status` other than "disabled": the
        documented fallback decides the state (only an absent `enabled` AND
        absent `status` is UNKNOWN). Pinned so the two parser branches can
        never disagree about this direction."""
        bindir = tmp_path / "bin"
        _write_stub_openclaw(bindir, [
            {"name": "agent-browser-reaper", "cron": "13 * * * *", "status": "active"},
        ])
        env = dict(os.environ, PATH=f"{bindir}:{os.environ.get('PATH', '')}")
        res = _run(env)
        assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        assert "PASS" in res.stdout

    def test_enabled_string_false_exits_3(self, tmp_path):
        """`enabled: "false"` (string) is disabled exactly like boolean
        false — never UNKNOWN, never PASS."""
        bindir = tmp_path / "bin"
        _write_stub_openclaw(bindir, [
            {"name": "agent-browser-reaper", "cron": "13 * * * *", "enabled": "false"},
        ])
        env = dict(os.environ, PATH=f"{bindir}:{os.environ.get('PATH', '')}")
        res = _run(env)
        assert res.returncode == 3, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        assert "DISABLED" in res.stdout
        assert "PASS" not in res.stdout


class TestParserParity:
    """The verdict must NOT depend on which parser a box happens to have
    installed. Divergence observed live 2026-10-25 (pre-fix): the jq branch
    answered UNKNOWN (2) for payloads the python3 branch resolved —
    `enabled: "false"` -> 3, `enabled: null, status: "disabled"` -> 3,
    `status: "active"` -> 0 — so the same reaper state read DISABLED on one
    box and UNKNOWN on another."""

    PAYLOADS = [
        ([{"name": "agent-browser-reaper", "cron": "13 * * * *", "enabled": True}], 0),
        ([{"name": "agent-browser-reaper", "cron": "13 * * * *", "enabled": False}], 3),
        ([{"name": "agent-browser-reaper", "cron": "13 * * * *"}], 2),
        ([{"name": "agent-browser-reaper", "cron": "13 * * * *", "enabled": "false"}], 3),
        ([{"name": "agent-browser-reaper", "cron": "13 * * * *", "enabled": None, "status": "disabled"}], 3),
        ([{"name": "agent-browser-reaper", "cron": "13 * * * *", "status": "active"}], 0),
    ]

    def test_jq_branch_matches_python_branch(self, tmp_path):
        for jobs, expected in self.PAYLOADS:
            env_jq = _jq_only_env(tmp_path, jobs)
            if env_jq is None:
                pytest.skip("jq not installed on this box")
            res_jq = _run(env_jq)
            assert res_jq.returncode == expected, (
                f"jq branch, jobs={jobs}\nSTDOUT:\n{res_jq.stdout}\nSTDERR:\n{res_jq.stderr}"
            )
            bindir = tmp_path / "bin"
            _write_stub_openclaw(bindir, jobs)
            env_py = dict(os.environ, PATH=f"{bindir}:{os.environ.get('PATH', '')}")
            res_py = _run(env_py)
            assert res_py.returncode == res_jq.returncode, (
                f"PARSER DIVERGENCE on jobs={jobs}: python3 branch={res_py.returncode}, "
                f"jq branch={res_jq.returncode}\nPY STDOUT:\n{res_py.stdout}\nJQ STDOUT:\n{res_jq.stdout}"
            )
