"""Tests for presentation_job/scan_roots.py + multi-root wiring (2026-08-27 fix).

The incident: presentation-watchdog.sh passed ONE scan root (the department
tree) to every pass, while a real client deck ran in ~/webinar-decks. Three
hours of watchdog passes read as healthy while watching the wrong forest.

Covers the four behaviors the fix spec names:
  1. a run in an extra root IS found;
  2. a department-tree run is still found (no regression);
  3. a date-style leaf dir ("2026-08-27") is a valid run dir (identity by
     marker, never by name);
  4. an unreadable root yields UNDETERMINED, never "missing", and never
     blocks/heals/fails a deck.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.scan_roots import (
    RUN_DIR_MARKERS, ScanRoot, default_config_path, format_roots_report,
    is_run_dir, matched_markers, ok_roots, parse_roots_config,
    resolve_scan_roots, undetermined_roots,
)
from presentation_job.state import EXIT_OK, EXIT_STALLED, EXIT_SWEEP_NO_RUNS
from presentation_job.watchdog import watchdog

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sweep import _make_state, _write_state, _run_sweep  # noqa: E402


def _w(fd: Path, phase="P4-RENDER", iv=10, age=12, jid=None, terminal=None):
    """Write a state.json shaped like the engine's (same helper as test_watchdog)."""
    fd.mkdir(parents=True, exist_ok=True)
    if jid is None:
        jid = "pj_" + fd.name
    ts = (datetime.now(timezone.utc) - timedelta(minutes=age)).isoformat(timespec="seconds")
    hb = {"last_checkpoint_at": ts, "current_phase": phase,
          "interval_minutes": iv, "budget_minutes": 240,
          "interval_source": "manifest_heartbeat_minutes"}
    st = {"schema_version": 1, "job_id": jid, "run_dir": str(fd),
          "terminal": terminal, "current_phase": phase, "heartbeat": hb}
    (fd / "state.json").write_text(json.dumps(st, indent=2))
    return fd


def _run_watch(root, **kw):
    import io
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = watchdog(root, **kw)
    finally:
        sys.stdout = old
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------
# scan_roots.resolve_scan_roots
# ---------------------------------------------------------------------------

class TestResolveScanRoots:
    def test_primary_plus_env_plus_config(self, tmp_path):
        dep = tmp_path / "departments" / "Presentations" / "runs"
        extra = tmp_path / "webinar-decks"
        cfg = tmp_path / "scan-roots.conf"
        cfg.write_text(f"{extra}\n", encoding="utf-8")
        (dep).mkdir(parents=True)
        (extra).mkdir()
        roots = resolve_scan_roots(
            primary=dep,
            env={"PRESENTATION_SCAN_ROOTS": str(extra)},
            config_path=cfg,
        )
        paths = [str(r.path) for r in roots]
        assert str(dep) in paths and str(extra) in paths
        # deduped: extra came from env first, so config origin loses
        assert len(paths) == 2

    def test_env_os_pathsep_multiple(self, tmp_path):
        dep = tmp_path / "dep"; dep.mkdir()
        a = tmp_path / "a"; a.mkdir()
        b = tmp_path / "b"; b.mkdir()
        roots = resolve_scan_roots(
            primary=dep,
            env={"PRESENTATION_SCAN_ROOTS": os.pathsep.join([str(a), str(b)])},
        )
        assert [str(r.path) for r in roots] == [str(dep), str(a), str(b)]

    def test_unreadable_root_is_undetermined_not_dropped(self, tmp_path):
        dep = tmp_path / "dep"; dep.mkdir()
        ghost = tmp_path / "does-not-exist"
        roots = resolve_scan_roots(primary=dep, env={}, config_path=None)
        # ghost was never configured; now configure it and prove it survives
        # as UNDETERMINED instead of vanishing from the report
        roots2 = resolve_scan_roots(
            primary=dep,
            env={"PRESENTATION_SCAN_ROOTS": str(ghost)},
            config_path=None,
        )
        und = undetermined_roots(roots2)
        assert len(und) == 1 and und[0].path == ghost
        assert "does not exist" in und[0].detail
        # the ok list never contains it
        assert ghost not in [r.path for r in ok_roots(roots2)]
        # and the no-extra baseline is unchanged
        assert [str(r.path) for r in ok_roots(roots)] == [str(dep)]

    def test_config_missing_file_is_not_error(self, tmp_path):
        dep = tmp_path / "dep"; dep.mkdir()
        roots = resolve_scan_roots(
            primary=dep, env={}, config_path=tmp_path / "nope.conf",
        )
        assert [str(r.path) for r in roots] == [str(dep)]

    def test_config_unreadable_file_is_undetermined_input(self, tmp_path):
        dep = tmp_path / "dep"; dep.mkdir()
        cfg = tmp_path / "conf.d"  # a directory, not a file -> read fails
        cfg.mkdir()
        roots = resolve_scan_roots(primary=dep, env={}, config_path=cfg)
        assert len(undetermined_roots(roots)) == 1

    def test_config_comments_and_tilde(self, tmp_path):
        cfg = tmp_path / "scan-roots.conf"
        cfg.write_text(
            "# comment\n\n  /tmp/x  # trailing comment\n~\n", encoding="utf-8")
        paths, err = parse_roots_config(cfg)
        assert err is None
        assert [str(p) for p in paths] == ["/tmp/x", str(Path.home())]

    def test_default_config_path_sits_beside_scripts(self, tmp_path):
        scripts = tmp_path / "Presentations" / "scripts"
        scripts.mkdir(parents=True)
        p = default_config_path(scripts)
        assert p == tmp_path / "Presentations" / "config" / "scan-roots.conf"

    def test_probe_flags_not_a_directory(self, tmp_path):
        plain = tmp_path / "afile"
        plain.write_text("x")
        roots = resolve_scan_roots(primary=plain, env={}, config_path=None)
        assert roots[0].status == "undetermined"

    def test_format_report_names_every_root(self, tmp_path):
        dep = tmp_path / "dep"; dep.mkdir()
        ghost = tmp_path / "ghost"
        roots = resolve_scan_roots(
            primary=dep, env={"PRESENTATION_SCAN_ROOTS": str(ghost)},
            config_path=None,
        )
        report = format_roots_report(roots, "watchdog")
        assert str(dep) in report and str(ghost) in report
        assert "UNDETERMINED" in report and "INCOMPLETE" in report


# ---------------------------------------------------------------------------
# Identity markers (content, never the directory's name)
# ---------------------------------------------------------------------------

class TestIdentityMarkers:
    def test_date_leaf_is_run_dir(self, tmp_path):
        d = tmp_path / "webinar-decks" / "client" / "deck" / "2026-08-27"
        d.mkdir(parents=True)
        (d / "state.json").write_text("{}")
        assert is_run_dir(d)
        assert "state.json" in matched_markers(d)

    def test_job_lock_alone_is_a_marker(self, tmp_path):
        d = tmp_path / "run"; d.mkdir()
        (d / ".job.lock").write_text("1")
        assert is_run_dir(d)

    def test_legacy_manifest_is_a_marker(self, tmp_path):
        d = tmp_path / "run"
        (d / "working" / "checkpoints").mkdir(parents=True)
        (d / "working" / "checkpoints" / "process_manifest.json").write_text("{}")
        assert is_run_dir(d)

    def test_plain_directory_is_not_a_run_dir(self, tmp_path):
        d = tmp_path / "not-a-run"; d.mkdir()
        assert not is_run_dir(d)

    def test_no_marker_named_like_a_slug(self, tmp_path):
        d = tmp_path / "pres-wave-e-x-123"; d.mkdir()
        assert not is_run_dir(d), "a name convention must never prove a run dir"

    def test_marker_tuple_contents(self):
        assert RUN_DIR_MARKERS == (
            "state.json", "working/checkpoints/process_manifest.json", ".job.lock")


# ---------------------------------------------------------------------------
# Watchdog: multi-root behavior
# ---------------------------------------------------------------------------

class TestWatchdogMultiRoot:
    def test_run_in_extra_root_is_found(self, tmp_path):
        dep = tmp_path / "dep"; dep.mkdir()
        extra = tmp_path / "webinar-decks"
        # date-style leaf, exactly like the incident run
        run = _w(extra / "client" / "deck" / "2026-08-27", age=40)
        rc, out = _run_watch(dep, extra_roots=(extra,), scan_depth=3, enforce=True)
        assert rc == EXIT_STALLED, "stalled run in extra root must be found"
        assert str(run) in out and "STALLED" in out
        assert "scan roots: 2 readable" in out

    def test_department_tree_run_still_found(self, tmp_path):
        dep = tmp_path / "dep"
        _w(dep / "pres-run", age=40)
        rc, out = _run_watch(dep, extra_roots=(), scan_depth=1, enforce=True)
        assert rc == EXIT_STALLED and "STALLED" in out

    def test_extra_root_run_not_stalled_exits_ok(self, tmp_path):
        dep = tmp_path / "dep"; dep.mkdir()
        extra = tmp_path / "extra"
        _w(extra / "2026-08-27", age=2)
        rc, out = _run_watch(dep, extra_roots=(extra,), scan_depth=1)
        assert rc == EXIT_OK and "STALLED" not in out

    def test_unreadable_root_is_undetermined_not_missing(self, tmp_path):
        dep = tmp_path / "dep"; dep.mkdir()
        _w(dep / "readable-run", age=40)
        locked = tmp_path / "locked"
        locked.mkdir()
        _w(locked / "run", age=40)
        # make the root unreadable for the current user (chmod 000)
        locked.chmod(0)
        try:
            rc, out = _run_watch(dep, extra_roots=(locked,), scan_depth=1, enforce=True)
        finally:
            locked.chmod(0o755)  # restore so pytest tmp cleanup works
        # the stall in the readable root is still found (never blocked by the
        # unreadable sibling), and the unreadable root is reported, not dropped
        assert rc == EXIT_STALLED
        assert "UNDETERMINED" in out
        assert str(locked) in out

    def test_all_roots_unreadable_is_undetermined_exit_13(self, tmp_path):
        dep = tmp_path / "dep"
        _w(dep / "run", age=40)
        dep.chmod(0)
        try:
            rc, out = _run_watch(dep, extra_roots=(), scan_depth=1)
        finally:
            dep.chmod(0o755)
        assert rc == 13  # EXIT_WATCHDOG_NO_RUNS -- could not look != healthy
        assert "UNDETERMINED" in out

    def test_roots_recorded_in_findings_jsonl(self, tmp_path):
        dep = tmp_path / "dep"
        extra = tmp_path / "extra"
        extra.mkdir()
        _w(dep / "a", age=40)
        _run_watch(dep, extra_roots=(extra,), scan_depth=1)
        lines = [json.loads(l) for l in
                 (dep / "watchdog-findings.jsonl").read_text().splitlines() if l.strip()]
        assert lines, "a stall must produce a findings line"
        assert str(dep) in lines[0]["scan_roots"]
        assert str(extra) in lines[0]["scan_roots"]

    def test_scan_audit_written_on_clean_pass(self, tmp_path):
        dep = tmp_path / "dep"
        _w(dep / "a", age=2)
        _run_watch(dep, extra_roots=(), scan_depth=1)
        audit = dep / "watchdog-scan-audit.jsonl"
        assert audit.exists(), "the audit record must be written even with zero stalls"
        rec = json.loads(audit.read_text().splitlines()[-1])
        assert rec["record"] == "scan_audit"
        assert rec["complete"] is True
        assert rec["scanned"] == 1 and rec["stalled"] == 0

    def test_audit_flags_incomplete_when_root_unreadable(self, tmp_path):
        dep = tmp_path / "dep"; dep.mkdir()
        locked = tmp_path / "locked"; locked.mkdir()
        locked.chmod(0)
        try:
            _run_watch(dep, extra_roots=(locked,), scan_depth=1)
        finally:
            locked.chmod(0o755)
        rec = json.loads((dep / "watchdog-scan-audit.jsonl").read_text().splitlines()[-1])
        assert rec["complete"] is False
        assert any(str(locked) in u["path"] for u in rec["scan_roots_undetermined"])

    def test_run_in_both_roots_scanned_once(self, tmp_path):
        dep = tmp_path / "dep"
        run = _w(dep / "shared", age=40)
        rc, out = _run_watch(dep, extra_roots=(dep,), scan_depth=1)
        assert out.count("STALLED") == 1, "dedup across roots: one run, one finding"

    def test_config_file_roots_are_used(self, tmp_path):
        dep = tmp_path / "dep"; dep.mkdir()
        extra = tmp_path / "via-config"
        _w(extra / "deck" / "2026-08-27", age=40)
        cfg = tmp_path / "scan-roots.conf"
        cfg.write_text(f"{extra}\n", encoding="utf-8")
        rc, out = _run_watch(dep, roots_config=cfg, scan_depth=3, enforce=True)
        assert rc == EXIT_STALLED and str(extra) in out

    def test_env_var_roots_are_used(self, tmp_path, monkeypatch):
        dep = tmp_path / "dep"; dep.mkdir()
        extra = tmp_path / "via-env"
        _w(extra / "2026-08-27", age=40)
        rc, out = _run_watch(dep, env={"PRESENTATION_SCAN_ROOTS": str(extra)},
                             scan_depth=1, enforce=True)
        assert rc == EXIT_STALLED and str(extra) in out

    def test_env_param_beats_process_env(self, tmp_path, monkeypatch):
        # the injected env dict is authoritative for resolution (test isolation)
        monkeypatch.setenv("PRESENTATION_SCAN_ROOTS", "/nonexistent-xyz")
        dep = tmp_path / "dep"; dep.mkdir()
        _w(dep / "a", age=40)
        rc, out = _run_watch(dep, env={}, scan_depth=1, enforce=True)
        assert rc == EXIT_STALLED and "nonexistent-xyz" not in out