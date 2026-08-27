"""Multi-root + depth tests for run_discovery.py (2026-08-27 fix).

Two blind spots closed:
  1. ONE ROOT: --runs-root was single; now repeatable + env + config.
  2. ONE LEVEL: iterdir() only; now a bounded walk to --scan-depth, so the
     incident run at <root>/<client>/<deck>/<date>/ is found.

Identity is by marker (state.json / legacy manifest / .job.lock), never by
directory name. Absence inside a scan root is never proof of absence.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_discovery as rd  # noqa: E402


def _mk_run(root: Path, rel: str, with_state=True, registered=False) -> Path:
    d = root / rel
    d.mkdir(parents=True, exist_ok=True)
    if with_state:
        st = {"schema_version": 1,
              "job_id": ("pj_test_" + rel.replace("/", "_")) if registered else None,
              "run_dir": str(d) if registered else None}
        (d / "state.json").write_text(json.dumps(st))
    return d


class TestDiscoveryMultiRoot:
    def test_finds_run_three_levels_down(self, tmp_path):
        root = tmp_path / "webinar-decks"
        run = _mk_run(root, "client/deck/2026-08-27")
        found = rd.find_unregistered_runs(root, scan_depth=3)
        assert run in found, "the incident shape (<root>/<client>/<deck>/<date>) must be found"

    def test_one_level_regression(self, tmp_path):
        root = tmp_path / "runs"
        run = _mk_run(root, "pres-run")
        assert rd.find_unregistered_runs(root, scan_depth=1) == [run]

    def test_depth_limit_respected(self, tmp_path):
        root = tmp_path / "runs"
        _mk_run(root, "a/b/c/d/too-deep")
        assert rd.find_unregistered_runs(root, scan_depth=3) == []

    def test_registered_run_not_reported(self, tmp_path):
        root = tmp_path / "runs"
        _mk_run(root, "registered-run", registered=True)
        assert rd.find_unregistered_runs(root, scan_depth=1) == []

    def test_job_lock_only_dir_is_discovered(self, tmp_path):
        root = tmp_path / "runs"
        d = root / "died-early"
        d.mkdir(parents=True)
        (d / ".job.lock").write_text("1")
        found = rd.find_unregistered_runs(root, scan_depth=1)
        assert d in found

    def test_run_dir_not_descended_into(self, tmp_path):
        # a deck's own working/ subtree never holds another run
        root = tmp_path / "runs"
        run = _mk_run(root, "outer")
        inner = run / "working" / "nested-state"
        inner.mkdir(parents=True)
        (inner / "state.json").write_text("{}")
        found = rd.find_unregistered_runs(root, scan_depth=3)
        assert run in found and inner not in found

    def test_discover_multi_root_union_and_dedup(self, tmp_path):
        dep = tmp_path / "dep"; dep.mkdir()
        extra = tmp_path / "webinar-decks"; extra.mkdir()
        r1 = _mk_run(dep, "pres-a")
        r2 = _mk_run(extra, "client/deck/2026-08-27")
        roots = rd.resolve_scan_roots(primary=dep, env={"PRESENTATION_SCAN_ROOTS": str(extra)},
                                      config_path=None)
        report = rd.discover(roots, scan_depth=3)
        names = [str(p) for p in report.unregistered]
        assert str(r1) in names and str(r2) in names
        assert report.complete is True
        assert report.verdict == "found"

    def test_unreadable_root_means_incomplete_never_none(self, tmp_path):
        dep = tmp_path / "dep"; dep.mkdir()
        locked = tmp_path / "locked"; locked.mkdir()
        _mk_run(locked, "hidden-run")
        locked.chmod(0)
        try:
            roots = rd.resolve_scan_roots(
                primary=dep, env={"PRESENTATION_SCAN_ROOTS": str(locked)},
                config_path=None)
            report = rd.discover(roots, scan_depth=1)
        finally:
            locked.chmod(0o755)
        assert report.complete is False
        assert report.verdict == "UNDETERMINED", (
            "an unreadable root must make the whole scan verdict UNDETERMINED, "
            "never 'none' -- absence from a scan that could not run is not evidence")

    def test_cli_accepts_repeated_runs_root(self, tmp_path, capsys):
        dep = tmp_path / "dep"; dep.mkdir()
        extra = tmp_path / "webinar-decks"; extra.mkdir()
        r2 = _mk_run(extra, "client/deck/2026-08-27")
        rc = rd.main(["--runs-root", str(dep), "--runs-root", str(extra),
                      "--scan-depth", "3"])
        assert rc == 0
        out = capsys.readouterr().out
        assert str(r2) in out
        assert "2 unregistered" in out or "1 unregistered" in out
        assert str(extra) in out, "every scanned root must be named in the output"

    def test_cli_zero_readable_roots_is_undetermined(self, tmp_path, capsys):
        rc = rd.main(["--runs-root", str(tmp_path / "ghost-a"),
                      "--runs-root", str(tmp_path / "ghost-b")])
        assert rc == 0  # fail-soft contract unchanged
        err = capsys.readouterr().err
        assert "UNDETERMINED" in err

    def test_scan_depth_flag_rejected_below_one(self, tmp_path, capsys):
        rc = rd.main(["--runs-root", str(tmp_path), "--scan-depth", "0"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "scan-depth" in err

    def test_report_verdict_none_when_clean(self, tmp_path):
        root = tmp_path / "runs"; root.mkdir()
        _mk_run(root, "registered", registered=True)
        roots = rd.resolve_scan_roots(primary=root, env={}, config_path=None)
        report = rd.discover(roots, scan_depth=1)
        assert report.complete and report.verdict == "none"