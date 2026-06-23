"""SINGLETON POOLED BROWSER — static + behavioral tests for the browser_manager
gateway, the static guard, and the no-orphan teardown contract (Skill 06).

These tests are STATIC (grep / source reads) + a couple of HERMETIC behavioral
checks that use a STUBBED `agent-browser` on PATH (logging its argv to a temp
file). NO real browser is ever spawned — the stub records argv and returns
deterministic output. This proves:

  (a) inject-ghl-auth.sh sources browser_manager.sh and routes all AB calls
      through it (no bare `agent-browser <verb>`).
  (b) browser_manager.sh keeps trap-EXIT teardown + close + state clear +
      flock-OR-mkdir lock + canonical-session enforcement + the circuit-breaker.
  (c) bm_session_name() is STABLE for a fixed GHL_LOCATION_ID across repeated
      calls (proves no per-iteration multiplication — the verified root cause).
  (d) ghl_builder.browser_cmd raises when no browser_session() is active.
  (e) the pool ceiling refuses past AB_MAX_SESSIONS.
  (f) RAW-LAUNCH NEGATIVE FIXTURE: a raw `agent-browser ... open` NOT via the
      manager -> guard exit 1; the same routed through `browser_manager.sh eval`
      -> guard exit 0; a fixture with the trap stripped -> guard FAILS. Plus a
      stubbed-agent-browser run of a SIMULATED non-zero inject abort, asserting
      the close + state-clear lines were recorded (teardown fired on the abort).
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

# ── Paths under test ──────────────────────────────────────────────────────────
_TOOLS_DIR = (Path(__file__).parent.parent / "tools").resolve()
_REPO_ROOT = _TOOLS_DIR.parent.parent.resolve()
_MANAGER_SH = _TOOLS_DIR / "browser_manager.sh"
_MANAGER_PY = _TOOLS_DIR / "browser_manager.py"
_INJECT_SH = _TOOLS_DIR / "inject-ghl-auth.sh"
_GUARD = _REPO_ROOT / "scripts" / "guard-agent-browser-managed.sh"
_REAPER = _REPO_ROOT / "scripts" / "agent-browser-reaper.sh"

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


def _read(p: Path) -> str:
    assert p.exists(), f"missing: {p}"
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) inject-ghl-auth.sh sources the manager + routes all AB calls through it
# ---------------------------------------------------------------------------

class TestInjectRoutesThroughManager:
    def test_inject_sources_browser_manager(self):
        src = _read(_INJECT_SH)
        assert re.search(r"^\s*(source|\.)\s.*browser_manager\.sh", src, re.MULTILINE), (
            "inject-ghl-auth.sh must `source` browser_manager.sh so AB() is the "
            "lock-asserting gateway wrapper."
        )

    def test_inject_calls_bm_ensure_before_first_open(self):
        src = _read(_INJECT_SH)
        assert "bm_ensure" in src, "inject must call bm_ensure (lock+lease+TTL+trap)."
        # bm_ensure must appear BEFORE the first AB --session open call.
        ensure_idx = src.index("bm_ensure")
        m = re.search(r'AB\s+--session\s+"\$SESSION"\s+open', src)
        assert m, "inject must still have an AB --session open call."
        assert ensure_idx < m.start(), "bm_ensure must precede the first open."

    def test_inject_has_no_bare_agent_browser_binary_call(self):
        """No raw `agent-browser <verb>` binary call (only the AB() wrapper)."""
        src = _read(_INJECT_SH)
        # Strip comments + the final NEXT echo (documentation prose).
        code_lines = []
        for line in src.splitlines():
            if line.lstrip().startswith("#"):
                continue
            if re.match(r'\s*echo\b', line):
                continue
            code_lines.append(line)
        code = "\n".join(code_lines)
        bad = re.findall(
            r'agent-browser(\s+--headed\s+(false|true))?\s+(--session\s+\S+\s+)?(open|eval|snapshot|wait|find|fill)\b',
            code,
        )
        assert not bad, f"inject must not call the agent-browser binary directly: {bad!r}"

    def test_inject_does_not_redefine_AB_or_AB_BIN(self):
        """The manager owns AB_BIN + AB(); inject must not re-define them."""
        src = _read(_INJECT_SH)
        assert "AB_BIN=" not in src, "inject must not re-define AB_BIN (manager owns it)."
        assert not re.search(r"^\s*AB\(\)\s*\{", src, re.MULTILINE), (
            "inject must not re-define AB() (manager owns the lock-asserting wrapper)."
        )


# ---------------------------------------------------------------------------
# (b) browser_manager.sh keeps the whole safety contract
# ---------------------------------------------------------------------------

class TestManagerContract:
    def test_trap_exit_teardown_present(self):
        src = _read(_MANAGER_SH)
        assert re.search(r"trap\s+_bm_teardown\s+EXIT", src), (
            "browser_manager.sh must keep `trap _bm_teardown EXIT ...`."
        )

    def test_teardown_closes_and_clears_state(self):
        src = _read(_MANAGER_SH)
        assert "close --session" in src, "teardown must close --session."
        assert "state clear" in src, "teardown must state clear."

    def test_lock_is_flock_or_mkdir(self):
        src = _read(_MANAGER_SH)
        assert "flock" in src, "lock must use flock when present."
        assert 'mkdir "$LOCKDIR/ab.lock.d"' in src, (
            "lock must have the portable atomic-mkdir fallback (flock is ABSENT on macOS)."
        )

    def test_canonical_session_enforced(self):
        src = _read(_MANAGER_SH)
        assert "bm_assert_session" in src, "must enforce the canonical session."
        assert "exit 64" in src, "non-canonical session must exit 64."
        assert "AB_SESSION_OVERRIDE" in src, "override must be explicit + recorded."

    def test_circuit_breaker_present(self):
        src = _read(_MANAGER_SH)
        assert "bm_breaker_check" in src, "circuit-breaker check must exist."
        assert "AB_BREAKER_MAX" in src, "breaker must have a bounded open cap."
        assert "RESCUE_RANGERS_HELP_CHAT_ID" in src, "breaker trip must escalate to Rescue Rangers."

    def test_per_call_and_session_timeout(self):
        src = _read(_MANAGER_SH)
        assert "AB_CALL_TIMEOUT" in src, "per-call timeout must exist."
        assert "AB_SESSION_TTL" in src, "per-session TTL must exist."

    def test_teardown_never_close_all_in_normal_path(self):
        """Teardown closes ONLY the canonical session (blast-radius safety).
        `close --all` is reserved for the reaper / a breaker trip."""
        src = _read(_MANAGER_SH)
        # Inside _bm_teardown(), there must be NO `close --all`.
        m = re.search(r"_bm_teardown\(\)\s*\{(.*?)\n\}", src, re.DOTALL)
        assert m, "could not locate _bm_teardown() body"
        assert "close --all" not in m.group(1), (
            "teardown must NOT close --all (blast-radius safety)."
        )


# ---------------------------------------------------------------------------
# (c) bm_session_name() stable for a fixed GHL_LOCATION_ID (no multiplication)
# ---------------------------------------------------------------------------

class TestCanonicalSessionStable:
    def _run_session_name(self, loc: str) -> str:
        env = dict(os.environ, GHL_LOCATION_ID=loc)
        res = subprocess.run(
            ["bash", str(_MANAGER_SH), "session-name"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert res.returncode == 0, res.stderr
        return res.stdout.strip()

    def test_stable_across_repeated_calls(self):
        loc = "FIXTURE0LOCATION0000"  # generic 20-char fixture id (NOT a real sub-account)
        names = {self._run_session_name(loc) for _ in range(5)}
        assert len(names) == 1, f"session name must be STABLE, got {names!r}"
        assert names == {"ghl-skill6-fixture0location0000"}

    def test_sanitized_to_a_z_0_9_dash(self):
        name = self._run_session_name("Foo_Bar/BAZ!! x")
        assert re.fullmatch(r"[a-z0-9-]+", name), f"not sanitized: {name!r}"

    def test_python_session_name_matches_shell(self):
        import browser_manager as bm
        os.environ["GHL_LOCATION_ID"] = "FIXTURE0LOCATION0000"  # generic fixture id
        try:
            assert bm.session_name() == "ghl-skill6-fixture0location0000"
            assert bm.session_name() == bm.session_name()  # stable
        finally:
            del os.environ["GHL_LOCATION_ID"]


# ---------------------------------------------------------------------------
# (d) ghl_builder.browser_cmd raises when no browser_session() is active
# ---------------------------------------------------------------------------

class TestEmitterRefusesOutsideSession:
    def test_browser_cmd_raises_without_session(self):
        import browser_manager as bm
        import ghl_builder as b
        assert not bm.session_active()
        with pytest.raises(RuntimeError, match="singleton gateway"):
            b.browser_cmd("--session", "x", "snapshot", "-i")

    def test_browser_cmd_ok_inside_session(self):
        import browser_manager as bm
        import ghl_builder as b
        with bm.browser_session("sess-fake"):
            line = b.browser_cmd("--session", "sess-fake", "snapshot", "-i")
        assert line.startswith("agent-browser --headed false")

    def test_eval_cmd_raises_without_session(self):
        import ghl_rest_canvas as rc
        with pytest.raises(RuntimeError, match="singleton gateway"):
            rc.agent_browser_eval_cmd("sess-fake", "1+1")

    def test_emitted_plan_ends_with_teardown_step(self):
        """Every emitted plan carries the mandatory final close step."""
        import browser_manager as bm
        import ghl_builder as b
        kwargs = dict(
            page_id="PAGEID0000000000fake",
            funnel_id="FUNNELID00000000fake",
            location_id="FIXTURE0LOCATION0000",
            current_location_id="FIXTURE0LOCATION0000",
            locator={"section_idx": 0, "element_idx": 0},
            new_value="<!--marker--><div>x</div>",
            page_version=1,
            page_data={"sections": [{"elements": [{"extra": {"customCode": {"value": {"rawCustomCode": "old"}}}}]}]},
            preview_url="https://example.com/p",
            marker="marker",
            session="sess-fake",
        )
        with bm.browser_session("sess-fake"):
            plan = b.emit_rest_save_plan(**kwargs)
        steps = plan["steps"]
        last = steps[-1]
        assert last.get("step") == "teardown_browser", f"last step must tear down: {last!r}"
        assert "close --session" in last["cmd"], last


# ---------------------------------------------------------------------------
# (e) pool ceiling refuses past AB_MAX_SESSIONS (hermetic, stubbed agent-browser)
# ---------------------------------------------------------------------------

def _write_stub_agent_browser(bindir: Path, log: Path, session_list_json: str) -> Path:
    """Write a fake `agent-browser` that logs argv and answers `session list
    --json` with a controllable count. No real browser."""
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "agent-browser"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$@" >> {log}\n'
        'args="$*"\n'
        'case "$args" in\n'
        f'  *"session list --json"*) printf %s {session_list_json!r} ;;\n'
        '  *) printf "" ;;\n'
        'esac\n'
        'exit 0\n',
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub


class TestPoolCeiling:
    def test_ceiling_refuses_when_at_max(self, tmp_path):
        bindir = tmp_path / "bin"
        log = tmp_path / "argv.log"
        lockdir = tmp_path / "lockdir"
        # Two active sessions reported -> at/over ceiling of 1 -> the oldest-idle
        # close is attempted, but the stub keeps reporting 2, so REFUSE exit 75.
        two_active = '{"session":"a"}\n{"session":"b"}\n'
        _write_stub_agent_browser(bindir, log, two_active)
        env = dict(
            os.environ,
            PATH=f"{bindir}:{os.environ.get('PATH','')}",
            TMPDIR=str(lockdir),
            GHL_LOCATION_ID="poolloc",
            AB_MAX_SESSIONS="1",
            AB_LOCK_WAIT="2",
            AB_SESSION_TTL="60",
        )
        res = subprocess.run(
            ["bash", str(_MANAGER_SH), "ensure"],
            capture_output=True, text=True, env=env, timeout=60,
        )
        assert res.returncode == 75, (
            f"pool ceiling must REFUSE (exit 75) past AB_MAX_SESSIONS.\n"
            f"exit={res.returncode}\nSTDERR:\n{res.stderr}"
        )
        assert "ceiling" in res.stderr.lower()


# ---------------------------------------------------------------------------
# (f) RAW-LAUNCH NEGATIVE / POSITIVE / STRIPPED-TRAP guard fixtures
# ---------------------------------------------------------------------------

def _run_guard(repo_root: Path) -> subprocess.CompletedProcess:
    assert _GUARD.exists(), f"guard missing: {_GUARD}"
    return subprocess.run(
        ["bash", str(_GUARD), "--repo-root", str(repo_root)],
        capture_output=True, text=True, timeout=90,
    )


def _scaffold_repo(tmp_path: Path) -> Path:
    """Lay down a minimal repo skeleton with the REAL gateway + reaper + docs so
    the guard runs against a controlled tree."""
    skill = tmp_path / "06-ghl-install-pages"
    tools = skill / "tools"
    scripts = tmp_path / "scripts"
    tools.mkdir(parents=True, exist_ok=True)
    scripts.mkdir(parents=True, exist_ok=True)
    # Real gateway + reaper (so the integrity + managed-only checks have them).
    shutil.copy2(_MANAGER_SH, tools / "browser_manager.sh")
    shutil.copy2(_MANAGER_PY, tools / "browser_manager.py")
    shutil.copy2(_REAPER, scripts / "agent-browser-reaper.sh")
    # Docs with the verbatim sentinel.
    sentinel = "SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown, reaper backstop"
    for doc in ("SKILL.md", "ghl-browser-builder-full.md", "CORE_UPDATES.md"):
        (skill / doc).write_text(f"# {doc}\n\n{sentinel}\n", encoding="utf-8")
    return tmp_path


class TestGuardFixtures:
    def test_raw_launch_fails(self, tmp_path):
        repo = _scaffold_repo(tmp_path)
        # A file that does NOT source the manager and calls the binary directly.
        bad = repo / "06-ghl-install-pages" / "tools" / "bad_build.sh"
        bad.write_text(
            "#!/usr/bin/env bash\n"
            'agent-browser --headed false --session foo open https://example.com\n',
            encoding="utf-8",
        )
        res = _run_guard(repo)
        assert res.returncode == 1, f"raw launch must FAIL guard.\n{res.stdout}\n{res.stderr}"
        assert "raw agent-browser launch outside browser_manager.sh" in res.stdout

    def test_routed_through_manager_passes(self, tmp_path):
        repo = _scaffold_repo(tmp_path)
        # The SAME action, but routed through the gateway (sources it + AB()).
        good = repo / "06-ghl-install-pages" / "tools" / "good_build.sh"
        good.write_text(
            "#!/usr/bin/env bash\n"
            'source "$(dirname "$0")/browser_manager.sh"\n'
            'bm_ensure\n'
            'AB --session "$(bm_session_name)" open https://example.com\n',
            encoding="utf-8",
        )
        res = _run_guard(repo)
        assert res.returncode == 0, (
            f"routing the same action through browser_manager must PASS.\n{res.stdout}\n{res.stderr}"
        )

    def test_stripped_trap_fails(self, tmp_path):
        repo = _scaffold_repo(tmp_path)
        mgr = repo / "06-ghl-install-pages" / "tools" / "browser_manager.sh"
        src = mgr.read_text(encoding="utf-8")
        # Remove the teardown trap -> gateway integrity check must FAIL.
        stripped = re.sub(r"trap\s+_bm_teardown\s+EXIT[^\n]*\n", "", src)
        assert stripped != src, "fixture must actually remove the trap line"
        mgr.write_text(stripped, encoding="utf-8")
        res = _run_guard(repo)
        assert res.returncode == 1, "stripping the teardown trap must FAIL the guard."
        assert "trap _bm_teardown EXIT" in res.stdout  # the FAIL line names it

    def test_per_iteration_session_name_in_doc_fails(self, tmp_path):
        repo = _scaffold_repo(tmp_path)
        doc = repo / "06-ghl-install-pages" / "ghl-browser-builder-full.md"
        doc.write_text(
            doc.read_text(encoding="utf-8")
            + "\nagent-browser --headed false --session ghl-foo-diag open <url>\n",
            encoding="utf-8",
        )
        res = _run_guard(repo)
        assert res.returncode == 1, "a per-iteration -diag session name in a doc must FAIL."
        assert "per-iteration session name" in res.stdout

    # ── Form C: Python argv-LIST spawn evasion (the documented residual) ──────
    # The shell-string regex cannot see `agent-browser` inside a Python list
    # passed to subprocess (strip_python erases the string token). The AST pass
    # must catch every argv-list spawn primitive so a raw launch outside the
    # manager ALWAYS fails CI — never just the shell-string form.
    @pytest.mark.parametrize(
        "spawn_stmt",
        [
            # subprocess.run with a list argv
            'subprocess.run(["agent-browser", "--headed", "false", "--session", "x", "open", "https://e.com"])',
            # subprocess.Popen with a tuple argv
            'subprocess.Popen(("agent-browser", "--session", "x", "snapshot"))',
            # check_output list argv
            'subprocess.check_output(["agent-browser", "eval", "--stdin"])',
            # os.execvp — first string arg is the binary
            'os.execvp("agent-browser", ["agent-browser", "open", "https://e.com"])',
            # os.system with the command string head
            'os.system("agent-browser --headed false --session x open https://e.com")',
            # bare imported name (from subprocess import run)
            'run(["agent-browser", "--session", "x", "click", "#go"])',
        ],
    )
    def test_python_argv_list_spawn_fails(self, tmp_path, spawn_stmt):
        repo = _scaffold_repo(tmp_path)
        bad = repo / "06-ghl-install-pages" / "tools" / "evil_spawn.py"
        bad.write_text(
            "import os, subprocess\n"
            "from subprocess import run\n"
            f"{spawn_stmt}\n",
            encoding="utf-8",
        )
        res = _run_guard(repo)
        assert res.returncode == 1, (
            f"argv-list spawn must FAIL the guard.\nstmt={spawn_stmt!r}\n"
            f"{res.stdout}\n{res.stderr}"
        )
        assert "raw agent-browser spawn (argv-list" in res.stdout, res.stdout

    def test_python_argv_list_spawn_no_false_positive(self, tmp_path):
        """Docstrings, `argv[0] == "agent-browser"` assertions, a Path like
        `d / "agent-browser"`, and the emitter's returned STRING (built via the
        sanctioned helper, never spawned) must NOT trip the argv-list AST pass."""
        repo = _scaffold_repo(tmp_path)
        benign = repo / "06-ghl-install-pages" / "tools" / "benign.py"
        benign.write_text(
            'import os, subprocess\n'
            'from pathlib import Path\n'
            '\n'
            'def emit():\n'
            '    """Returns an argv like ["agent-browser", "open", url] for the\n'
            '    AGENT to run — this module never spawns it."""\n'
            '    return "agent-browser --headed false open https://e.com"\n'
            '\n'
            'def check(argv):\n'
            '    assert argv[0] == "agent-browser"  # comparison, not a spawn\n'
            '\n'
            'def stub(d):\n'
            '    return Path(d) / "agent-browser"   # a file path, not a spawn\n'
            '\n'
            '# A spawn of a DIFFERENT binary is fine:\n'
            'subprocess.run(["bash", "-c", "true"])\n'
            'os.system("echo hello")\n',
            encoding="utf-8",
        )
        res = _run_guard(repo)
        assert res.returncode == 0, (
            f"benign agent-browser references (docstring / comparison / path / "
            f"emitter string / other-binary spawn) must NOT FAIL.\n{res.stdout}\n{res.stderr}"
        )


# ---------------------------------------------------------------------------
# (f cont.) Teardown FIRES on a non-zero abort (stubbed agent-browser, no real
# browser). We drive a tiny harness that sources the manager, ensures, then
# exits non-zero — the EXIT trap must record close + state clear in the argv log.
# ---------------------------------------------------------------------------

class TestTeardownFiresOnAbort:
    def test_abort_records_close_and_state_clear(self, tmp_path):
        bindir = tmp_path / "bin"
        log = tmp_path / "argv.log"
        lockdir = tmp_path / "lockdir"
        _write_stub_agent_browser(bindir, log, "")  # 0 active sessions
        harness = tmp_path / "abort_harness.sh"
        harness.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f'source "{_MANAGER_SH}"\n'
            "bm_ensure\n"
            "# simulate the inject script's non-zero REFUSE abort:\n"
            'echo "REFUSE: simulated seed failure" >&2\n'
            "exit 1\n",
            encoding="utf-8",
        )
        env = dict(
            os.environ,
            PATH=f"{bindir}:{os.environ.get('PATH','')}",
            TMPDIR=str(lockdir),
            GHL_LOCATION_ID="abortloc",
            AB_MAX_SESSIONS="1",
            AB_LOCK_WAIT="2",
            AB_SESSION_TTL="60",
        )
        res = subprocess.run(
            ["bash", str(harness)],
            capture_output=True, text=True, env=env, timeout=60,
        )
        assert res.returncode == 1, f"harness should exit 1 (simulated abort), got {res.returncode}"
        logged = log.read_text(encoding="utf-8") if log.exists() else ""
        # The EXIT trap must have closed + cleared the canonical session.
        assert "close --session ghl-skill6-abortloc" in logged, (
            f"teardown must close the canonical session on abort.\nargv log:\n{logged}"
        )
        assert "state clear ghl-skill6-abortloc" in logged, (
            f"teardown must state-clear the canonical session on abort.\nargv log:\n{logged}"
        )
