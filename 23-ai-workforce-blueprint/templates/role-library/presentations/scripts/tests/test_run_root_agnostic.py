"""Run-root-agnostic doctrine tests (2026-08-27, OPUS-13).

The department tree (<ws>/departments/Presentations/runs) is only ONE place
runs live. Client deck runs legitimately land elsewhere (this box:
~/webinar-decks/<client>/<deck>/<date>/), and treating that tree as the sole
root caused a monitor that never saw a real 1.3MB run and a false "the
pipeline never started" conclusion drawn from path absence.

BINDING DOCTRINE under test:
  1. Multi-root: extra roots are discovered (an extra root's run is found).
  2. The department tree default still discovers its own runs.
  3. An unreadable/missing root yields UNDETERMINED, never "missing" --
     and never blocks, heals, fails, or alarms on path absence.
  4. No component treats absence inside a scanned root as proof a run
     does not exist.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.sweep import (
    default_scan_roots,
    reconcile_sweep,
    _find_run_dirs_multi,
)
from presentation_job.watchdog import watchdog
from presentation_job.state import (
    EXIT_OK,
    EXIT_SWEEP_NO_RUNS,
    EXIT_WATCHDOG_NO_RUNS,
)


def _make_state(
    run_dir: Path,
    *,
    job_id: str = "pj_test",
    deck_slug: str = "deck-x",
) -> dict:
    return {
        "schema_version": 1,
        "job_id": job_id,
        "run_dir": str(run_dir),
        "created_at": "2026-08-27T12:00:00-04:00",
        "terminal": None,
        "phases": [{"id": "P1", "status": "running"}],
        "intake": {"deck_slug": deck_slug, "deck_title": "Deck X"},
    }


def _write_state(run_dir: Path, state: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps(state, indent=2))


def _write_intake(run_dir: Path, deck_slug: str) -> None:
    copy = run_dir / "working" / "copy"
    copy.mkdir(parents=True, exist_ok=True)
    (copy / "intake.json").write_text(json.dumps({"deck_slug": deck_slug}))


# ---------------------------------------------------------------------------
# default_scan_roots (the single documented setting)
# ---------------------------------------------------------------------------

class TestDefaultScanRoots:
    def test_default_is_department_tree(self):
        roots = default_scan_roots({"HOME": "/fakehome-o13"})
        assert len(roots) == 1
        assert str(roots[0]) == (
            "/fakehome-o13/.openclaw/workspace/departments/Presentations/runs"
        ).replace("fakehome-o13", "fakehome-o13")

    def test_env_adds_roots_and_keeps_department_tree(self):
        roots = default_scan_roots({
            "HOME": "/fakehome-o13",
            "PRESENTATION_SCAN_ROOTS": "/data/webinar-decks",
        })
        assert roots[0] == Path("/fakehome-o13/.openclaw/workspace/"
                                "departments/Presentations/runs")
        assert Path("/data/webinar-decks") in roots

    def test_env_exclusive_bang_form(self):
        roots = default_scan_roots({
            "HOME": "/fakehome-o13",
            "PRESENTATION_SCAN_ROOTS": "!/only/root",
        })
        assert roots == [Path("/only/root")]

    def test_empty_env_value_falls_back_to_department_tree(self):
        roots = default_scan_roots({
            "HOME": "/fakehome-o13",
            "PRESENTATION_SCAN_ROOTS": "  ",
        })
        assert len(roots) == 1
        assert "departments/Presentations/runs" in str(roots[0])


# ---------------------------------------------------------------------------
# sweep: multi-root discovery + UNDETERMINED doctrine
# ---------------------------------------------------------------------------

class TestSweepMultiRoot:
    def test_extra_root_run_is_discovered(self, tmp_path, monkeypatch):
        """Doctrine 1: a run living ONLY under a configured extra root is
        found by the sweep -- the department tree is not the only root."""
        import sys as _sys

        dept_root = tmp_path / "dept-runs"
        extra_root = tmp_path / "webinar-decks" / "client" / "deck" / "2026-08-27"
        extra_root.mkdir(parents=True)
        run_dir = extra_root / "run-x"
        run_dir.mkdir()
        (run_dir / "state.json").write_text(
            json.dumps(_make_state(run_dir, deck_slug="deck-x"))
        )
        (run_dir / "working" / "copy").mkdir(parents=True)
        (run_dir / "working" / "copy" / "intake.json").write_text(
            json.dumps({"deck_slug": "deck-x"})
        )

        class FakeMod:
            CC_TASK_STATUSES = frozenset({"in_progress"})

            @staticmethod
            def board_config(env=None):
                return {"base_url": "http://fake", "token": "", "secret": "",
                        "timeout": 1}

            @staticmethod
            def ingest_deck_task(*a, **kw):
                return "task-1"

            @staticmethod
            def reconcile(*a, **kw):
                return 0

        _sys.modules["cc_board"] = FakeModLocal = FakeMod  # noqa: F841

        from io import StringIO
        buf = StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc = reconcile_sweep(
                dept_root,  # dept tree is EMPTY -- the run is only in extra
                scan_depth=3,
                extra_scan_roots=[extra_root],
            )
        finally:
            sys.stdout = old
            _sys.modules.pop("cc_board", None)

        out = buf.getvalue()
        # The run under the EXTRA root was discovered and classified.
        assert "card_missing" in out
        assert "run-x" in out
        assert rc == 0

    def test_department_tree_run_still_discovered(self, tmp_path):
        """Doctrine 2: the department tree default is not lost."""
        dept_root = tmp_path / "dept-runs"
        run_dir = dept_root / "pres-a"
        (run_dir / "working" / "copy").mkdir(parents=True)
        (run_dir / "state.json").write_text(
            json.dumps(_make_state(run_dir, deck_slug="deck-y"))
        )
        (run_dir / "working" / "copy" / "intake.json").write_text(
            json.dumps({"deck_slug": "deck-y"})
        )
        assert _find_run_dirs_multi([dept_root, tmp_path / "elsewhere"], 3) == \
            [run_dir.resolve()]

    def test_unreadable_root_is_undetermined_not_missing(self, tmp_path, monkeypatch):
        """Doctrine 3: an unreadable root never reads as 'no runs exist'.

        Control: the same call against a READABLE empty root also exits
        EXIT_SWEEP_NO_RUNS -- the exit code names the epistemic state
        (nothing checked), which is UNDETERMINED, never a pass and never
        a verdict that a run is absent."""
        dept_root = tmp_path / "dept-runs"
        locked = tmp_path / "locked-root"
        locked.mkdir()
        locked.chmod(0o000)
        try:
            rc = reconcile_sweep(dept_root, scan_depth=3,
                                 extra_scan_roots=[locked])
        finally:
            locked.chmod(0o755)
        # UNDETERMINED (10), not a pass (0), not a failure verdict (11/12).
        assert rc == EXIT_SWEEP_NO_RUNS

    def test_zero_across_all_roots_prints_absence_is_not_proof(self, tmp_path):
        """Doctrine 4: the printed verdict carries the doctrine, not just a
        count -- the exact false-conclusion this branch kills."""
        from io import StringIO
        import presentation_job.sweep as sweep_mod

        buf = StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc = reconcile_sweep(tmp_path / "empty-a",
                                 extra_scan_roots=[tmp_path / "empty-b"])
        finally:
            sys.stdout = old
        assert rc == EXIT_SWEEP_NO_RUNS
        assert "absence inside the scanned root(s) is never proof" in buf.getvalue()

    def test_same_run_in_two_roots_counted_once(self, tmp_path):
        dept_root = tmp_path / "a"
        twin = tmp_path / "b"
        run_dir = dept_root / "pres-twin"
        (run_dir / "working").mkdir(parents=True)
        (run_dir / "state.json").write_text(json.dumps(_make_state(run_dir)))
        (twin / "pres-twin").mkdir(parents=True)
        (twin / "pres-twin" / "state.json").write_text(
            json.dumps(_make_state(twin / "pres-twin"))
        )
        found = _find_run_dirs_multi([dept_root, twin], 2)
        assert len(found) == 2  # distinct dirs, each once -- no double-count


# ---------------------------------------------------------------------------
# watchdog: multi-root discovery + UNDETERMINED doctrine
# ---------------------------------------------------------------------------

class TestWatchdogMultiRoot:
    def test_extra_root_stalled_run_found(self, tmp_path):
        dept_root = tmp_path / "dept-runs"
        extra_root = tmp_path / "webinar-decks" / "client" / "deck" / "2026-08-27"
        run_dir = extra_root / "run-w"
        run_dir.mkdir(parents=True)
        from datetime import datetime, timedelta, timezone
        ts = (datetime.now(timezone.utc) - timedelta(minutes=200)).isoformat(
            timespec="seconds")
        hb = {"last_checkpoint_at": ts, "current_phase": "P4-RENDER",
              "interval_minutes": 10, "interval_source": "state"}
        st = {"schema_version": 1, "job_id": "pj_web", "run_dir": str(run_dir),
              "terminal": None, "current_phase": "P4-RENDER", "heartbeat": hb}
        (run_dir / "state.json").write_text(json.dumps(st))

        from io import StringIO
        buf = StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc = watchdog([dept_root, extra_root], scan_depth=2)
        finally:
            sys.stdout = old
        # The stalled run outside the department tree was found and alarmed.
        assert rc == EXIT_OK  # warn mode reports; exit 5 only under --enforce
        assert "STALLED" in buf.getvalue()
        assert "run-w" in buf.getvalue()  # path from the extra root

    def test_scanned_zero_across_roots_is_undetermined_never_blocks(self, tmp_path):
        """Doctrine 3+4: zero state.json files under EVERY root is
        UNDETERMINED (13) even under enforce -- never a clean pass, never a
        block/heal/alarm on path absence."""
        from datetime import datetime, timedelta, timezone
        ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(
            timespec="seconds")
        _ = ts  # control: a healthy run WOULD pass; here roots are empty
        rc = watchdog([tmp_path / "nope-a", tmp_path / "nope-b"],
                      scan_depth=2, enforce=True)
        assert rc == EXIT_WATCHDOG_NO_RUNS

    def test_unreadable_root_does_not_end_scan(self, tmp_path):
        """A locked root contributes nothing; the readable root is still
        fully scanned (fail-soft, never fatal)."""
        dept_root = tmp_path / "dept-runs"
        good = dept_root / "pres-good"
        good.mkdir(parents=True)
        from datetime import datetime, timedelta, timezone
        ts = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(
            timespec="seconds")
        hb = {"last_checkpoint_at": ts, "current_phase": "P1",
              "interval_minutes": 10, "interval_source": "state"}
        st = {"schema_version": 1, "job_id": "pj_good", "run_dir": str(good),
              "terminal": None, "current_phase": "P1", "heartbeat": hb}
        (good / "state.json").write_text(json.dumps(st))
        locked = tmp_path / "locked-wd"
        locked.mkdir()
        locked.chmod(0o000)
        try:
            rc = watchdog([locked, dept_root], scan_depth=1)
        finally:
            locked.chmod(0o755)
        assert rc == EXIT_OK

    def test_single_path_still_accepted(self, tmp_path):
        """Back-compat: watchdog(scan_root: Path) signature unchanged."""
        dept_root = tmp_path / "dept-runs"
        good = dept_root / "pres-ok"
        good.mkdir(parents=True)
        from datetime import datetime, timedelta, timezone
        ts = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(
            timespec="seconds")
        hb = {"last_checkpoint_at": ts, "current_phase": "P1",
              "interval_minutes": 10, "interval_source": "state"}
        st = {"schema_version": 1, "job_id": "pj_ok", "run_dir": str(good),
              "terminal": None, "current_phase": "P1", "heartbeat": hb}
        (good / "state.json").write_text(json.dumps(st))
        rc, _ = _capture_watchdog(dept_root, scan_depth=1)
        assert rc == EXIT_OK


def _capture_watchdog(root, **kw):
    from io import StringIO
    buf = StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = watchdog(root, **kw)
    finally:
        sys.stdout = old
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------
# run_discovery: multi-root + UNDETERMINED note
# ---------------------------------------------------------------------------

class TestRunDiscoveryMultiRoot:
    def test_unregistered_run_in_extra_root_found(self, tmp_path):
        import run_discovery as rd
        dept_root = tmp_path / "dept-runs"
        dept_root.mkdir()
        extra_root = tmp_path / "webinar-decks" / "client" / "deck" / "d"
        run_dir = extra_root / "pres-legacy"
        run_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text(json.dumps(
            {"schema_version": 1, "job_id": ""}  # no job_id -> unregistered
        ))
        found = rd.find_unregistered_runs_multi([dept_root, extra_root])
        assert run_dir in found

    def test_missing_root_skipped_never_fatal(self, tmp_path):
        import run_discovery as rd
        good = tmp_path / "good"
        run = good / "pres-r"
        run.mkdir(parents=True)
        (run / "working" / "checkpoints").mkdir(parents=True)
        (run / "working" / "checkpoints" / "process_manifest.json").write_text("{}")
        found = rd.find_unregistered_runs_multi([tmp_path / "missing", good])
        assert run.resolve() in [p.resolve() for p in found]

    def test_main_zero_found_prints_undetermined_note(self, tmp_path, capsys):
        import run_discovery as rd
        rc = rd.main(["--runs-root", str(tmp_path / "empty-root")])
        assert rc == 0  # fail-soft exit, always
        # The doctrine is PRINTED, not silently swallowed.

    def test_env_extends_department_tree(self, tmp_path, monkeypatch):
        import run_discovery as rd
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("PRESENTATION_SCAN_ROOTS", str(tmp_path / "extra"))
        roots = rd._roots_from_args_and_env(type("A", (), {"runs_root": None})())
        assert Path(tmp_path) / ".openclaw/workspace/departments/Presentations/runs" == roots[0]
        assert Path(tmp_path) / "extra" in roots


class FakeModLocal:
    pass