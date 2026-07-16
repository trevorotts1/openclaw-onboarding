"""U28 (B-U14) — the headless-guard COVERAGE audit + the dynamic exit-75 CI
guard test, both acceptance criterion (a): "the audit table lists every
launch site with a headless_guard() call, and the continuous-integration
test proves exit-75 refusal on each — PASS/FAIL."

GROUNDED FINDING this file's fix responds to (verified by reading, not
assumed): the D6 contract ENV-MATRIX.md documents — "headed = forbidden (D6,
exit 75)" — was ONLY actually honored by ghl_builder.py's three CLI fast
paths (`browser-cmd` / `browser-session` / `headless-guard`). Every real
BUILDER'S own CLI entry point (community/course/pipeline via the shared
ghl_run_state.cli_run(), plus ghl_form_builder.main() and
ghl_survey_builder.main(), which duplicate the same pattern) caught the
guard's RuntimeError with the SAME generic `except Exception` every other
build failure hits and returned 1 — silently breaking the exit-75 promise on
the five most-used entry points. The fix (ghl_run_state.is_d6_headless_
refusal + one check before each builder's final `return`) is exercised here
end-to-end: real AGENT_BROWSER_HEADED=true, real module code path, real
returned exit code.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).parent.resolve()
_TOOLS_DIR = (_TESTS_DIR.parent / "tools").resolve()
_REPO_ROOT = _TESTS_DIR.parent.parent.resolve()

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import ghl_builder  # noqa: E402
import ghl_community_builder as community  # noqa: E402
import ghl_course_builder as course  # noqa: E402
import ghl_pipeline_builder as pipeline  # noqa: E402
import ghl_form_builder as form  # noqa: E402
import ghl_survey_builder as survey  # noqa: E402
import headless_guard_audit  # noqa: E402

_FIXTURE_LOCATION = "FIXTURE0LOCATION0000"   # generic 20-char fixture, not a real sub-account
_PASSING_PREFLIGHT = {"pass": True, "checks": [], "stop_reason": None}


# ---------------------------------------------------------------------------
# (1) STATIC audit table — self-updating (AST), never hand-maintained.
# ---------------------------------------------------------------------------
class TestStaticAuditTable:
    def test_chokepoint_invariant_holds(self):
        """browser_manager.browser_session() must still call headless_guard()
        as its own first statement — every 'COVERED (chokepoint self-guards)'
        verdict below depends on this."""
        chokepoint = headless_guard_audit.chokepoint_guarded()
        assert chokepoint["ok"] is True, chokepoint

    def test_no_uncovered_launch_sites(self):
        table = headless_guard_audit.build_audit_table()
        assert table["gap_count"] == 0, (
            f"uncovered D6 launch site(s) found:\n{table['gaps']}"
        )
        assert table["ok"] is True

    def test_audit_finds_every_known_launch_site(self):
        """A floor, not a ceiling: these specific sites must be present in the
        table (regression guard against the AST scan silently finding
        nothing and vacuously passing)."""
        table = headless_guard_audit.build_audit_table()
        found = {(r["file"], r["function"]) for r in table["launch_sites"]}
        expected = {
            ("tools/ghl_community_builder.py", "_live_build"),
            ("tools/ghl_course_builder.py", "_live_build"),
            ("tools/ghl_pipeline_builder.py", "_live_build"),
            ("tools/ghl_form_builder.py", "_live_build"),
            ("tools/ghl_survey_builder.py", "build_survey"),
        }
        missing = expected - found
        assert not missing, f"audit did not find expected launch site(s): {missing}\ntable={table}"

    def test_iframe_drag_selftest_launch_is_compliant_by_construction(self):
        """The one raw chromium.launch* site outside the browser_session()
        chokepoint (ghl_iframe_drag.py's offline self-test) must be recorded,
        never silently dropped, and must be the literal-headless=True case."""
        table = headless_guard_audit.build_audit_table()
        hits = [r for r in table["launch_sites"]
               if r["file"] == "tools/ghl_iframe_drag.py"]
        assert len(hits) == 1, f"expected exactly one raw-launch site, got {hits}"
        assert hits[0]["kind"] == "raw_chromium_launch"
        assert hits[0]["status"].startswith("COMPLIANT-BY-CONSTRUCTION")

    def test_cli_audit_check_mode_exits_0(self):
        rc = headless_guard_audit.main(["--check"])
        assert rc == 0


# ---------------------------------------------------------------------------
# (2) DYNAMIC CI guard — ghl_builder.py's three CLI fast paths (already
# correct pre-U28; regression-locked here).
# ---------------------------------------------------------------------------
class TestGhlBuilderCliFastPathsExit75:
    def _env(self, headed: bool = True) -> dict:
        env = dict(os.environ)
        env["AGENT_BROWSER_HEADED"] = "true" if headed else ""
        return env

    def _run(self, *args: str, headed: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "ghl_builder.py"), *args],
            capture_output=True, text=True, env=self._env(headed), timeout=30,
        )

    def test_headless_guard_subcommand_headed_exits_75(self):
        res = self._run("headless-guard")
        assert res.returncode == 75, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

    def test_headless_guard_subcommand_headless_exits_0(self):
        res = self._run("headless-guard", headed=False)
        assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

    def test_browser_cmd_headed_exits_75(self):
        res = self._run("browser-cmd", "--session", "fixture-sess", "snapshot", "-i")
        assert res.returncode == 75, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

    def test_browser_session_headed_exits_75(self):
        res = self._run("browser-session", "fixture-sess")
        assert res.returncode == 75, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


# ---------------------------------------------------------------------------
# (3) DYNAMIC CI guard — the FIVE builder main()s. THE U28 FIX under test.
# Preflight is monkeypatched to pass (isolates the D6 guard/exit-code path
# from each builder's own P1..P8-shaped preflight logic, which has its own
# dedicated test coverage elsewhere) so the live path is reached fast, with
# no network / no browser / no GHL credentials.
# ---------------------------------------------------------------------------
def _argv(tmp_path, extra: list) -> list:
    return [
        "--no-dry-run", "--location-id", _FIXTURE_LOCATION,
        "--evidence-root", str(tmp_path / "evidence"),
        "--state-root", str(tmp_path / "state"),
        *extra,
    ]


class TestBuilderMainsExit75OnHeadedEnv:
    def test_community_builder_headed_exits_75(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_BROWSER_HEADED", "true")
        monkeypatch.setattr(community, "_preflight", lambda *a, **k: dict(_PASSING_PREFLIGHT))
        rc = community.main(_argv(tmp_path, []))
        assert rc == 75

    def test_course_builder_headed_exits_75(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_BROWSER_HEADED", "true")
        monkeypatch.setattr(course, "_preflight", lambda *a, **k: dict(_PASSING_PREFLIGHT))
        rc = course.main(_argv(tmp_path, []))
        assert rc == 75

    def test_pipeline_builder_headed_exits_75(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_BROWSER_HEADED", "true")
        monkeypatch.setattr(pipeline, "_run_preflight", lambda *a, **k: dict(_PASSING_PREFLIGHT))
        rc = pipeline.main(_argv(tmp_path, []))
        assert rc == 75

    def test_form_builder_headed_exits_75(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_BROWSER_HEADED", "true")
        monkeypatch.setattr(form, "_run_preflight", lambda *a, **k: dict(_PASSING_PREFLIGHT))
        rc = form.main(_argv(tmp_path, []))
        assert rc == 75

    def test_survey_builder_headed_exits_75(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_BROWSER_HEADED", "true")
        monkeypatch.setattr(survey, "_run_preflight", lambda *a, **k: dict(_PASSING_PREFLIGHT))
        # field_creation='browser' is the ONE mode that skips survey_builder's
        # separate F1 LIVE (Skill-44 custom-field GET) gate — a real
        # dependency this test must clear to reach the D6 guard at all, wholly
        # independent of the D6 guard/exit-code path itself under test here.
        rc = survey.main(_argv(tmp_path, ["--field-creation", "browser"]))
        assert rc == 75

    # ── Regression guards: a HEADLESS env must never itself produce 75 (the
    # fix must not over-fire on ordinary failures / ordinary success paths).
    def test_community_builder_headless_env_does_not_exit_75(self, tmp_path, monkeypatch):
        monkeypatch.delenv("AGENT_BROWSER_HEADED", raising=False)
        monkeypatch.setattr(community, "_preflight",
                            lambda *a, **k: {"pass": False, "stop_reason": "fixture-stop"})
        rc = community.main(_argv(tmp_path, []))
        assert rc != 75

    def test_is_d6_headless_refusal_matches_only_the_real_prefix(self):
        import ghl_run_state
        assert ghl_run_state.is_d6_headless_refusal(
            "RuntimeError: REFUSE (D6 headless guard): AGENT_BROWSER_HEADED is set..."
        )
        assert not ghl_run_state.is_d6_headless_refusal("RuntimeError: some other failure")
        assert not ghl_run_state.is_d6_headless_refusal("")
        assert not ghl_run_state.is_d6_headless_refusal(None)


# ---------------------------------------------------------------------------
# (4) cli_run() unit-level proof — isolates the fix from any one builder's
# task/preflight shape entirely: a synthetic `build` callable that raises
# the EXACT D6 RuntimeError, proving the translation logic itself.
# ---------------------------------------------------------------------------
class TestCliRunD6Translation:
    def test_cli_run_maps_d6_runtimeerror_to_75(self, tmp_path):
        import argparse
        import ghl_run_state as grs

        def _raising_build(task, evidence_root, *, dry_run, state):
            raise RuntimeError(
                "REFUSE (D6 headless guard): AGENT_BROWSER_HEADED is set to a "
                "headed value, which would open a VISIBLE browser window."
            )

        specs = [grs.PhaseSpec("plan", resumable=False)]
        args = argparse.Namespace(
            resume="", evidence_root=str(tmp_path / "ev"), dry_run=False,
            stop_after_phase="", state_root=str(tmp_path / "state"), run_id="",
        )
        rc = grs.cli_run(
            args, builder="fixture-builder", specs=specs, script_path=__file__,
            task={}, build=_raising_build, argv=["--no-dry-run"],
        )
        assert rc == 75

    def test_cli_run_ordinary_failure_still_exits_1(self, tmp_path):
        import argparse
        import ghl_run_state as grs

        def _raising_build(task, evidence_root, *, dry_run, state):
            raise RuntimeError("some ordinary build failure, not D6")

        specs = [grs.PhaseSpec("plan", resumable=False)]
        args = argparse.Namespace(
            resume="", evidence_root=str(tmp_path / "ev"), dry_run=False,
            stop_after_phase="", state_root=str(tmp_path / "state"), run_id="",
        )
        rc = grs.cli_run(
            args, builder="fixture-builder", specs=specs, script_path=__file__,
            task={}, build=_raising_build, argv=["--no-dry-run"],
        )
        assert rc == 1
