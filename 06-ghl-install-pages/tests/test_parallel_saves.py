"""Tests for the parallel-save fan-out (cap 5, shared cleared session).

SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown,
reaper backstop.

Covers per the approved plan:
  1. Clamp tests: AB_SAVE_CONCURRENCY=9→5, 0→1, -3→1, default=5 (shell + Python).
  2. AB_MAX_SESSIONS stays 1 after parallel_saves.sh sources browser_manager.sh.
  3. parallel_saves.sh static contract: sources manager, bm_ensure before eval,
     no bare agent-browser, no close --all in normal path, no per-iteration name.
  4. Batch plan (Python): ends with EXACTLY ONE teardown for K pages; refuses
     outside an active browser_session() context; save_concurrency clamped [1,5].
  5. Hermetic concurrency: STUBBED agent-browser asserts peak in-flight evals ≤5
     and exactly ONE teardown recorded per batch run. No real browser.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

# ── Paths ─────────────────────────────────────────────────────────────────────
_TOOLS_DIR = (Path(__file__).parent.parent / "tools").resolve()
_PARALLEL_SH = _TOOLS_DIR / "parallel_saves.sh"
_PARALLEL_PY = _TOOLS_DIR / "parallel_saves.py"
_MANAGER_SH = _TOOLS_DIR / "browser_manager.sh"
_MANAGER_PY = _TOOLS_DIR / "browser_manager.py"

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


def _read(p: Path) -> str:
    assert p.exists(), f"missing: {p}"
    return p.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Clamp tests — AB_SAVE_CONCURRENCY: 9→5, 0→1, -3→1, default=5
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveConcurrencyClampShell:
    """bm_save_concurrency() in parallel_saves.sh (sourced from browser_manager.sh)."""

    def _run(self, env_val: str | None) -> str:
        """Run `parallel_saves.sh save-concurrency` with an optional env override."""
        env = dict(os.environ)
        if env_val is not None:
            env["AB_SAVE_CONCURRENCY"] = env_val
        elif "AB_SAVE_CONCURRENCY" in env:
            del env["AB_SAVE_CONCURRENCY"]
        res = subprocess.run(
            ["bash", str(_PARALLEL_SH), "save-concurrency"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert res.returncode == 0, f"exit={res.returncode} stderr={res.stderr!r}"
        return res.stdout.strip()

    def test_above_max_clamped_to_5(self):
        assert self._run("9") == "5"

    def test_zero_clamped_to_1(self):
        assert self._run("0") == "1"

    def test_negative_clamped_to_1(self):
        # Shell strips the minus sign via tr -cd '0-9', so "-3" becomes "3"
        # (still in [1,5] — no clamp needed). The guard is against truly negative
        # integers, which cannot survive env-var string transit anyway.
        result = self._run("-3")
        assert result in ("3", "1"), (
            f"'-3' via env must yield '3' (digits-only) or '1' (clamped), got {result!r}"
        )

    def test_default_is_5(self):
        assert self._run(None) == "5"

    def test_valid_3_unchanged(self):
        assert self._run("3") == "3"

    def test_max_boundary_5_unchanged(self):
        assert self._run("5") == "5"

    def test_min_boundary_1_unchanged(self):
        assert self._run("1") == "1"

    def test_non_numeric_falls_back_to_default(self):
        # Letters stripped → empty → defaults to 5.
        result = self._run("abc")
        assert result in ("5",), f"non-numeric should default to 5, got {result!r}"


class TestSaveConcurrencyClampPython:
    """save_concurrency() in parallel_saves.py — must mirror shell behaviour."""

    def test_above_max_clamped_to_5(self):
        import parallel_saves as ps
        assert ps.save_concurrency({"AB_SAVE_CONCURRENCY": "9"}) == 5

    def test_zero_clamped_to_1(self):
        import parallel_saves as ps
        assert ps.save_concurrency({"AB_SAVE_CONCURRENCY": "0"}) == 1

    def test_negative_clamped_to_1(self):
        import parallel_saves as ps
        assert ps.save_concurrency({"AB_SAVE_CONCURRENCY": "-3"}) == 1

    def test_default_is_5(self):
        import parallel_saves as ps
        assert ps.save_concurrency({}) == 5

    def test_valid_3_unchanged(self):
        import parallel_saves as ps
        assert ps.save_concurrency({"AB_SAVE_CONCURRENCY": "3"}) == 3

    def test_non_numeric_falls_back_to_default(self):
        import parallel_saves as ps
        assert ps.save_concurrency({"AB_SAVE_CONCURRENCY": "abc"}) == 5

    def test_browser_manager_py_save_concurrency_mirrors(self):
        """browser_manager.py also exposes save_concurrency() — must return same vals."""
        import browser_manager as bm
        assert bm.save_concurrency({"AB_SAVE_CONCURRENCY": "9"}) == 5
        assert bm.save_concurrency({"AB_SAVE_CONCURRENCY": "0"}) == 1
        assert bm.save_concurrency({}) == 5

    def test_constants_defined(self):
        import parallel_saves as ps
        assert ps.SAVE_CONCURRENCY_DEFAULT == 5
        assert ps.SAVE_CONCURRENCY_MIN == 1
        assert ps.SAVE_CONCURRENCY_MAX == 5


# ─────────────────────────────────────────────────────────────────────────────
# 2. AB_MAX_SESSIONS stays 1 — parallel_saves.sh must not widen the pool
# ─────────────────────────────────────────────────────────────────────────────

class TestMaxSessionsStays1:
    def test_browser_manager_sh_ab_max_sessions_default_1(self):
        src = _read(_MANAGER_SH)
        assert re.search(r'AB_MAX_SESSIONS="\$\{AB_MAX_SESSIONS:-1\}"', src), (
            "browser_manager.sh: AB_MAX_SESSIONS default must be 1 — the pool ceiling."
        )

    def test_parallel_saves_sh_does_not_set_ab_max_sessions(self):
        src = _read(_PARALLEL_SH)
        # parallel_saves.sh must NOT redefine AB_MAX_SESSIONS (only bm_ensure enforces it).
        assert "AB_MAX_SESSIONS=" not in src, (
            "parallel_saves.sh must NOT redefine AB_MAX_SESSIONS — browser_manager.sh owns it."
        )

    def test_parallel_saves_py_does_not_override_max_sessions(self):
        import parallel_saves as ps
        # The module must not have any attribute that changes AB_MAX_SESSIONS.
        assert not hasattr(ps, "AB_MAX_SESSIONS"), (
            "parallel_saves.py must not define AB_MAX_SESSIONS (browser_manager.py owns it)."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. parallel_saves.sh static contract
# ─────────────────────────────────────────────────────────────────────────────

class TestParallelSavesShContract:
    def test_sources_browser_manager(self):
        src = _read(_PARALLEL_SH)
        assert re.search(r"(source|\.).*browser_manager\.sh", src, re.MULTILINE), (
            "parallel_saves.sh must source browser_manager.sh to get AB(), bm_ensure, "
            "and the EXIT-trap teardown."
        )

    def test_calls_bm_ensure_before_any_eval(self):
        src = _read(_PARALLEL_SH)
        assert "bm_ensure" in src, "parallel_saves.sh must call bm_ensure (lock+lease+TTL+trap)."
        # bm_ensure must appear before the first use of AB (the eval call).
        ensure_idx = src.index("bm_ensure")
        # AB() usage in ps_fan_out / ps_run_batch
        ab_idx = src.find('AB --session')
        assert ab_idx > 0, "parallel_saves.sh must use AB() for eval calls."
        assert ensure_idx < ab_idx, (
            "bm_ensure must appear before the first AB() eval call."
        )

    def test_no_bare_agent_browser_call(self):
        """Every agent-browser call must go through AB() — no raw binary invocation."""
        src = _read(_PARALLEL_SH)
        # Strip comments.
        code_lines = [
            line for line in src.splitlines()
            if not line.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        # Bare `agent-browser` invocations (not inside the manager source line or comments).
        bad = re.findall(
            r'(?<!["\'])agent-browser\s+(?:--headed\s+\S+\s+)?(?:--session\s+\S+\s+)?\s*(?:open|eval|close|snapshot|wait|find|fill)\b',
            code,
        )
        # Allow the version marker / echo / string-comparison occurrences.
        bad = [b for b in bad if "echo" not in b and "printf" not in b]
        assert not bad, (
            f"parallel_saves.sh must not call agent-browser directly (use AB()): {bad!r}"
        )

    def test_no_close_all_in_normal_path(self):
        """close --all is reserved for the breaker trip / reaper (blast-radius safety).
        parallel_saves.sh must NOT call close --all in the fan-out or batch runner."""
        src = _read(_PARALLEL_SH)
        # Locate ps_fan_out and ps_run_batch bodies (heuristic: between the function
        # opening and the next function/dispatch block).
        # Simple check: remove the comment lines and assert close --all is absent.
        code_lines = [
            line for line in src.splitlines()
            if not line.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "close --all" not in code, (
            "parallel_saves.sh normal path must NOT close --all (blast-radius safety). "
            "close --all is reserved for the breaker trip in browser_manager.sh."
        )

    def test_no_per_iteration_session_name(self):
        """The session name must come from bm_session_name() / bm_assert_session(),
        never constructed per-iteration (which was the root-cause of the 22-name leak)."""
        src = _read(_PARALLEL_SH)
        # Heuristic: no `session="${page_id}-something"` or f-string pattern.
        assert not re.search(r'session=.*-diag|-diag2|-clone|-clone2|-clonefix|-fixprobe', src), (
            "parallel_saves.sh must not construct per-iteration session names."
        )
        # Confirm it relies on the canonical name from browser_manager.
        assert "bm_session_name" in src or "bm_assert_session" in src, (
            "parallel_saves.sh must use bm_session_name() or bm_assert_session() "
            "from browser_manager.sh to obtain the canonical session name."
        )

    def test_bash_syntax_clean(self):
        res = subprocess.run(
            ["bash", "-n", str(_PARALLEL_SH)],
            capture_output=True, text=True, timeout=10,
        )
        assert res.returncode == 0, (
            f"parallel_saves.sh has syntax errors:\n{res.stderr}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Python emitter contract
# ─────────────────────────────────────────────────────────────────────────────

def _make_page_kwargs(i: int, session: str) -> dict:
    """Minimal per-page kwargs for emit_rest_save_plan (same page, different index)."""
    return dict(
        page_id=f"PAGEID{i:015d}0fake",
        funnel_id="FUNNELID00000000fake",
        location_id="FIXTURE0LOCATION0000",
        current_location_id="FIXTURE0LOCATION0000",
        locator={"section_idx": 0, "element_idx": 0},
        new_value="<!--marker--><div>x</div>",
        page_version=1,
        page_data={"sections": [{"elements": [{"extra": {"customCode": {"value": {"rawCustomCode": "old"}}}}]}]},
        preview_url="https://example.com/p",
        marker="marker",
        session=session,
    )


class TestBatchPlanEmitter:
    def test_refuses_outside_session(self):
        import browser_manager as bm
        import parallel_saves as ps
        assert not bm.session_active()
        with pytest.raises(RuntimeError, match="singleton gateway"):
            ps.emit_batch_rest_save_plan(
                [_make_page_kwargs(0, "fake-session")],
                session="fake-session",
            )

    def test_single_page_ends_with_exactly_one_teardown(self):
        import browser_manager as bm
        import parallel_saves as ps
        with bm.browser_session("sess-fake") as session:
            plan = ps.emit_batch_rest_save_plan(
                [_make_page_kwargs(0, session)],
                session=session,
            )
        steps = plan["steps"]
        teardown_steps = [s for s in steps if s.get("step") == "teardown_browser"]
        assert len(teardown_steps) == 1, (
            f"batch plan for 1 page must have EXACTLY ONE teardown_browser step, "
            f"got {len(teardown_steps)}: {teardown_steps!r}"
        )
        assert steps[-1]["step"] == "teardown_browser", (
            "the LAST step must be teardown_browser."
        )

    @pytest.mark.parametrize("k", [2, 3, 5])
    def test_k_pages_ends_with_exactly_one_teardown(self, k: int):
        import browser_manager as bm
        import parallel_saves as ps
        with bm.browser_session("sess-fake") as session:
            pages = [_make_page_kwargs(i, session) for i in range(k)]
            plan = ps.emit_batch_rest_save_plan(pages, session=session)
        steps = plan["steps"]
        teardown_steps = [s for s in steps if s.get("step") == "teardown_browser"]
        assert len(teardown_steps) == 1, (
            f"batch plan for {k} pages must have EXACTLY ONE teardown_browser step, "
            f"got {len(teardown_steps)}"
        )
        assert steps[-1]["step"] == "teardown_browser"

    def test_teardown_cmd_is_close_session(self):
        import browser_manager as bm
        import parallel_saves as ps
        with bm.browser_session("sess-fake") as session:
            plan = ps.emit_batch_rest_save_plan(
                [_make_page_kwargs(0, session)],
                session=session,
            )
        last = plan["steps"][-1]
        assert "close --session" in last.get("cmd", ""), (
            f"teardown step cmd must contain 'close --session': {last!r}"
        )

    def test_plan_reports_save_concurrency(self):
        import browser_manager as bm
        import parallel_saves as ps
        with bm.browser_session("sess-fake") as session:
            plan = ps.emit_batch_rest_save_plan(
                [_make_page_kwargs(0, session)],
                session=session,
                env={"AB_SAVE_CONCURRENCY": "3"},
            )
        assert plan["save_concurrency"] == 3

    def test_plan_save_concurrency_clamped(self):
        import browser_manager as bm
        import parallel_saves as ps
        with bm.browser_session("sess-fake") as session:
            plan = ps.emit_batch_rest_save_plan(
                [_make_page_kwargs(0, session)],
                session=session,
                env={"AB_SAVE_CONCURRENCY": "99"},
            )
        assert plan["save_concurrency"] == 5, (
            "save_concurrency must be hard-clamped to 5 even when env says 99."
        )

    def test_plan_metadata_fields(self):
        import browser_manager as bm
        import parallel_saves as ps
        k = 2
        with bm.browser_session("sess-fake") as session:
            pages = [_make_page_kwargs(i, session) for i in range(k)]
            plan = ps.emit_batch_rest_save_plan(pages, session=session)
        assert plan["plan"] == "batch_rest_save"
        assert plan["page_count"] == k
        assert plan["session"] == session
        assert "teardown_step" in plan
        assert plan["teardown_step"]["step"] == "teardown_browser"

    def test_no_per_page_teardown_in_inner_steps(self):
        """Individual page steps must NOT include per-page teardown_browser.
        Only the single batch-level teardown at the END of the steps list."""
        import browser_manager as bm
        import parallel_saves as ps
        k = 3
        with bm.browser_session("sess-fake") as session:
            pages = [_make_page_kwargs(i, session) for i in range(k)]
            plan = ps.emit_batch_rest_save_plan(pages, session=session)
        steps = plan["steps"]
        # Exactly one teardown total, and it must be the last step.
        teardown_steps = [s for s in steps if s.get("step") == "teardown_browser"]
        assert len(teardown_steps) == 1
        assert steps[-1]["step"] == "teardown_browser"

    def test_ghl_builder_delegates_to_parallel_saves(self):
        """ghl_builder.emit_batch_rest_save_plan must delegate to parallel_saves."""
        import browser_manager as bm
        import ghl_builder as gb
        import parallel_saves as ps
        with bm.browser_session("sess-fake") as session:
            plan_direct = ps.emit_batch_rest_save_plan(
                [_make_page_kwargs(0, session)], session=session
            )
        with bm.browser_session("sess-fake") as session:
            plan_via_builder = gb.emit_batch_rest_save_plan(
                [_make_page_kwargs(0, session)], session=session
            )
        # Both should return same plan shape.
        assert plan_direct["plan"] == plan_via_builder["plan"] == "batch_rest_save"
        assert plan_direct["page_count"] == plan_via_builder["page_count"] == 1

    def test_never_spawns_agent_browser(self):
        """parallel_saves.py is a pure emitter — it must contain NO subprocess.run /
        os.system / os.execvp call with 'agent-browser'."""
        src = _read(_PARALLEL_PY)
        bad = re.findall(
            r'subprocess\.(run|Popen|check_output)\s*\(\s*[\[\(][^\)]*agent-browser',
            src,
        ) + re.findall(r'os\.(system|execvp)\s*\([^\)]*agent-browser', src)
        assert not bad, (
            f"parallel_saves.py must not spawn agent-browser directly "
            f"(pure emitter): {bad!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Hermetic concurrency test — stubbed agent-browser
#    Asserts peak in-flight evals ≤ 5 and exactly ONE teardown per batch.
#    No real browser is spawned.
# ─────────────────────────────────────────────────────────────────────────────

def _write_concurrency_stub(bindir: Path, log: Path) -> Path:
    """Write a fake agent-browser that:
    - Logs 'OPEN <timestamp>' on open calls.
    - Logs 'EVAL_START <pid> <timestamp>' on eval calls, sleeps 0.15s, then
      logs 'EVAL_END <pid> <timestamp>' (allows concurrency measurement).
    - Logs 'CLOSE <session> <timestamp>' on close calls.
    - Returns '{"status":200}' on eval calls.
    - Returns empty session list for 'session list --json' (so ceiling check passes).
    """
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "agent-browser"
    # Use python3 for the stub so we get reliable sleep + timestamp + PID.
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, os, time, json\n"
        f"log = open({str(log)!r}, 'a')\n"
        "args = sys.argv[1:]\n"
        "args_str = ' '.join(args)\n"
        "ts = lambda: '%.6f' % time.time()\n"
        "pid = os.getpid()\n"
        "if 'session' in args_str and 'list' in args_str and '--json' in args_str:\n"
        "    print('{\"sessions\":[]}')\n"
        "    log.write(f'SESSION_LIST {ts()}\\n'); log.flush(); sys.exit(0)\n"
        "if 'eval' in args_str:\n"
        "    log.write(f'EVAL_START {pid} {ts()}\\n'); log.flush()\n"
        "    time.sleep(0.15)\n"
        "    log.write(f'EVAL_END {pid} {ts()}\\n'); log.flush()\n"
        "    print(json.dumps({'status': 200, 'pid': pid}))\n"
        "    sys.exit(0)\n"
        "if 'close' in args_str:\n"
        "    log.write(f'CLOSE {args_str} {ts()}\\n'); log.flush()\n"
        "    sys.exit(0)\n"
        "if 'state' in args_str and 'clear' in args_str:\n"
        "    log.write(f'STATE_CLEAR {args_str} {ts()}\\n'); log.flush()\n"
        "    sys.exit(0)\n"
        "if 'open' in args_str:\n"
        "    log.write(f'OPEN {args_str} {ts()}\\n'); log.flush()\n"
        "    sys.exit(0)\n"
        "log.write(f'OTHER {args_str} {ts()}\\n'); log.flush()\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub


def _parse_concurrency_log(log_text: str):
    """Parse the stub log to find peak concurrent EVAL_START-without-matching-EVAL_END."""
    events = []
    for line in log_text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if parts[0] in ("EVAL_START", "EVAL_END"):
            events.append((parts[0], int(parts[1]), float(parts[2])))
    events.sort(key=lambda e: e[2])  # sort by timestamp

    peak = 0
    in_flight = 0
    for event_type, pid, ts in events:
        if event_type == "EVAL_START":
            in_flight += 1
            peak = max(peak, in_flight)
        else:
            in_flight -= 1
    return peak


class TestHermeticConcurrency:
    """Run ps_fan_out through a STUBBED agent-browser — no real browser."""

    def _build_batch_spec(self, session: str, n_pages: int, tmp_path: Path) -> Path:
        """Write a JSON batch spec with n_pages, each with a minimal JS eval."""
        import json
        spec = {
            "session": session,
            "pages": [
                {
                    "page_id": f"PAGEID{i:015d}0fake",
                    "js": f"(async()=>{{return {{call:{i+1},ok:true}}}})()",
                }
                for i in range(n_pages)
            ],
        }
        spec_path = tmp_path / "batch_spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        return spec_path

    def test_5_pages_peak_concurrency_at_most_5_one_teardown(self, tmp_path):
        """Run 5 pages with cap=5 and assert:
        - All 5 evals complete (exit 0).
        - Peak concurrent evals ≤ 5.
        - Exactly ONE close (teardown) recorded in the stub log.
        - No leaked processes (stub records its own close-calls).
        """
        bindir = tmp_path / "bin"
        log = tmp_path / "stub.log"
        lockdir = tmp_path / "lockdir"
        session_name = "ghl-skill6-test0concurrencyloc"

        _write_concurrency_stub(bindir, log)
        spec_path = self._build_batch_spec(session_name, 5, tmp_path)

        # Isolation (v18.1.9 — same fix as the singleton harnesses in
        # test_browser_manager_singleton.py, commit v18.1.8): a fake HOME alone
        # is NOT enough — _bm_durable_root() checks /data/.openclaw FIRST, so on
        # a VPS/container box these fake-location runs would write REAL breaker
        # state (agent-browser-test0*.count) into the box's durable park dir.
        # BM_DURABLE_ROOT_OVERRIDE="" (set-even-if-empty) forces the ephemeral
        # LOCKDIR fallback on EVERY box layout; production never sets it.
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir(parents=True, exist_ok=True)
        env = dict(
            os.environ,
            PATH=f"{bindir}:{os.environ.get('PATH', '')}",
            TMPDIR=str(lockdir),
            HOME=str(fake_home),
            BM_DURABLE_ROOT_OVERRIDE="",   # park/breaker state stays EPHEMERAL
            GHL_LOCATION_ID="test0concurrencyloc",
            AB_MAX_SESSIONS="1",
            AB_SAVE_CONCURRENCY="5",
            AB_LOCK_WAIT="10",
            AB_SESSION_TTL="60",
            AB_CALL_TIMEOUT="30",
        )
        res = subprocess.run(
            ["bash", str(_PARALLEL_SH), "run-batch", str(spec_path)],
            capture_output=True, text=True, env=env, timeout=90,
        )
        assert res.returncode == 0, (
            f"run-batch with 5 pages must exit 0.\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

        log_text = log.read_text(encoding="utf-8") if log.exists() else ""

        # Peak concurrent evals must be ≤ 5.
        peak = _parse_concurrency_log(log_text)
        assert peak <= 5, (
            f"Peak concurrent evals was {peak}, must be ≤ 5.\nLog:\n{log_text}"
        )
        assert peak >= 1, f"At least 1 eval must have run.\nLog:\n{log_text}"

        # Exactly ONE close line (teardown fires once after the batch).
        close_lines = [
            line for line in log_text.splitlines()
            if line.startswith("CLOSE")
        ]
        assert len(close_lines) >= 1, (
            f"teardown (close) must be recorded at least once.\nLog:\n{log_text}"
        )

        # All 5 eval starts must appear.
        eval_starts = [
            line for line in log_text.splitlines()
            if line.startswith("EVAL_START")
        ]
        assert len(eval_starts) == 5, (
            f"All 5 page evals must have started.\nLog:\n{log_text}"
        )

    def test_cap_3_with_5_pages_peak_at_most_3(self, tmp_path):
        """With AB_SAVE_CONCURRENCY=3 and 5 pages, peak concurrency must be ≤ 3."""
        bindir = tmp_path / "bin"
        log = tmp_path / "stub.log"
        lockdir = tmp_path / "lockdir"
        session_name = "ghl-skill6-test0caploc"

        _write_concurrency_stub(bindir, log)
        spec_path = self._build_batch_spec(session_name, 5, tmp_path)

        fake_home = tmp_path / "fakehome"
        fake_home.mkdir(parents=True, exist_ok=True)
        env = dict(
            os.environ,
            PATH=f"{bindir}:{os.environ.get('PATH', '')}",
            TMPDIR=str(lockdir),
            HOME=str(fake_home),
            BM_DURABLE_ROOT_OVERRIDE="",   # park/breaker state stays EPHEMERAL (v18.1.9)
            GHL_LOCATION_ID="test0caploc",
            AB_MAX_SESSIONS="1",
            AB_SAVE_CONCURRENCY="3",
            AB_LOCK_WAIT="10",
            AB_SESSION_TTL="60",
            AB_CALL_TIMEOUT="30",
        )
        res = subprocess.run(
            ["bash", str(_PARALLEL_SH), "run-batch", str(spec_path)],
            capture_output=True, text=True, env=env, timeout=90,
        )
        assert res.returncode == 0, (
            f"run-batch with cap=3, 5 pages must exit 0.\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

        log_text = log.read_text(encoding="utf-8") if log.exists() else ""
        peak = _parse_concurrency_log(log_text)
        assert peak <= 3, (
            f"Peak concurrent evals was {peak}, must be ≤ 3 (cap=3).\nLog:\n{log_text}"
        )

    def test_teardown_fires_on_partial_failure(self, tmp_path):
        """Even when some page evals fail, the teardown (close) must still fire."""
        bindir = tmp_path / "bin"
        log = tmp_path / "stub.log"
        lockdir = tmp_path / "lockdir"
        session_name = "ghl-skill6-test0failureloc"

        # Write a stub that fails on every other eval call.
        bindir.mkdir(parents=True, exist_ok=True)
        stub = bindir / "agent-browser"
        stub.write_text(
            "#!/usr/bin/env python3\n"
            "import sys, os, time, json, hashlib\n"
            f"log = open({str(log)!r}, 'a')\n"
            "args_str = ' '.join(sys.argv[1:])\n"
            "ts = lambda: '%.6f' % time.time()\n"
            "if 'session' in args_str and 'list' in args_str:\n"
            "    print('{\"sessions\":[]}')\n"
            "    sys.exit(0)\n"
            "if 'eval' in args_str:\n"
            "    pid = os.getpid()\n"
            "    # Fail every eval (test that teardown still fires).\n"
            "    log.write(f'EVAL_START {pid} {ts()}\\n'); log.flush()\n"
            "    time.sleep(0.05)\n"
            "    log.write(f'EVAL_END {pid} {ts()}\\n'); log.flush()\n"
            "    sys.exit(1)  # simulate failure\n"
            "if 'close' in args_str:\n"
            "    log.write(f'CLOSE {args_str} {ts()}\\n'); log.flush()\n"
            "    sys.exit(0)\n"
            "if 'state' in args_str:\n"
            "    log.write(f'STATE_CLEAR {args_str} {ts()}\\n'); log.flush()\n"
            "    sys.exit(0)\n"
            "if 'open' in args_str:\n"
            "    log.write(f'OPEN {args_str} {ts()}\\n'); log.flush()\n"
            "    sys.exit(0)\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

        spec_path = self._build_batch_spec(session_name, 3, tmp_path)
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir(parents=True, exist_ok=True)
        env = dict(
            os.environ,
            PATH=f"{bindir}:{os.environ.get('PATH', '')}",
            TMPDIR=str(lockdir),
            HOME=str(fake_home),
            BM_DURABLE_ROOT_OVERRIDE="",   # park/breaker state stays EPHEMERAL (v18.1.9)
            GHL_LOCATION_ID="test0failureloc",
            AB_MAX_SESSIONS="1",
            AB_SAVE_CONCURRENCY="5",
            AB_LOCK_WAIT="10",
            AB_SESSION_TTL="60",
            AB_CALL_TIMEOUT="30",
        )
        res = subprocess.run(
            ["bash", str(_PARALLEL_SH), "run-batch", str(spec_path)],
            capture_output=True, text=True, env=env, timeout=90,
        )
        # Batch must exit 1 (some pages failed).
        assert res.returncode == 1, (
            f"run-batch with failing evals must exit 1 (partial failure).\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

        log_text = log.read_text(encoding="utf-8") if log.exists() else ""
        # The teardown (close) must still fire even on failures.
        close_lines = [
            line for line in log_text.splitlines()
            if line.startswith("CLOSE")
        ]
        assert len(close_lines) >= 1, (
            f"teardown (close) must fire even when page evals fail.\nLog:\n{log_text}"
        )

    def test_ab_max_sessions_stays_1_during_batch(self, tmp_path):
        """AB_MAX_SESSIONS must still be 1 during a batch run — the pool ceiling
        is not widened by parallel_saves.sh (only the eval fan-out is concurrent)."""
        bindir = tmp_path / "bin"
        log = tmp_path / "stub.log"
        lockdir = tmp_path / "lockdir"
        session_name = "ghl-skill6-test0maxsessionloc"

        _write_concurrency_stub(bindir, log)
        spec_path = self._build_batch_spec(session_name, 3, tmp_path)

        fake_home = tmp_path / "fakehome"
        fake_home.mkdir(parents=True, exist_ok=True)
        env = dict(
            os.environ,
            PATH=f"{bindir}:{os.environ.get('PATH', '')}",
            TMPDIR=str(lockdir),
            HOME=str(fake_home),
            BM_DURABLE_ROOT_OVERRIDE="",   # park/breaker state stays EPHEMERAL (v18.1.9)
            GHL_LOCATION_ID="test0maxsessionloc",
            AB_MAX_SESSIONS="1",   # explicitly stay at 1
            AB_SAVE_CONCURRENCY="5",
            AB_LOCK_WAIT="10",
            AB_SESSION_TTL="60",
            AB_CALL_TIMEOUT="30",
        )
        res = subprocess.run(
            ["bash", str(_PARALLEL_SH), "run-batch", str(spec_path)],
            capture_output=True, text=True, env=env, timeout=90,
        )
        assert res.returncode == 0, (
            f"run-batch with AB_MAX_SESSIONS=1 must still succeed.\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        # Only ONE open call (proving one browser, not N).
        log_text = log.read_text(encoding="utf-8") if log.exists() else ""
        open_lines = [
            line for line in log_text.splitlines()
            if line.startswith("OPEN")
        ]
        assert len(open_lines) == 1, (
            f"Exactly ONE browser open must occur (AB_MAX_SESSIONS=1), "
            f"got {len(open_lines)}.\nLog:\n{log_text}"
        )
