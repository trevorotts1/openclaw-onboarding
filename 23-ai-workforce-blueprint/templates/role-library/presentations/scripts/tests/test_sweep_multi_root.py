"""Multi-root tests for the board-reconcile sweep (2026-08-27 fix companion
to test_scan_roots.py, which covers the watchdog + scan_roots module itself).

The incident: reconcile_sweep took ONE scan root, so a deck running outside
the department tree had no card reconciliation either. These tests prove:
  1. a run in an extra root IS swept;
  2. the department-tree run is still swept (no regression);
  3. an unreadable root never blocks a readable deck from being reconciled;
  4. a date-named leaf run is swept like any other (identity by marker).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_sweep import _make_state, _write_state, _run_sweep  # noqa: E402


class TestSweepMultiRoot:
    def test_run_in_extra_root_is_swept(self, tmp_path):
        dep = tmp_path / "dep"
        dep.mkdir()
        extra = tmp_path / "webinar-decks"
        run = extra / "client" / "deck" / "2026-08-27"
        _write_state(run, _make_state(run, deck_slug="deck-extra"))
        rc, out = _run_sweep(dep, extra_roots=(extra,), scan_depth=3)
        assert rc == 0
        assert str(run) in out
        assert "scanned 1" in out

    def test_department_tree_run_still_swept(self, tmp_path):
        dep = tmp_path / "dep"
        _write_state(dep / "run1", _make_state(dep / "run1", deck_slug="deck-1"))
        rc, out = _run_sweep(dep, extra_roots=(), scan_depth=2)
        assert rc == 0 and "scanned 1" in out

    def test_extra_root_run_not_deduped_against_same_dir(self, tmp_path):
        # the same run reachable via two configured roots counts once
        dep = tmp_path / "dep"
        run = dep / "shared"
        _write_state(run, _make_state(run, deck_slug="deck-shared"))
        rc, out = _run_sweep(dep, extra_roots=(dep,), scan_depth=1)
        assert "scanned 1" in out

    def test_unreadable_root_never_blocks_readable_deck(self, tmp_path):
        dep = tmp_path / "dep"
        dep.mkdir()
        _write_state(dep / "run1", _make_state(dep / "run1", deck_slug="deck-1"))
        locked = tmp_path / "locked"
        locked.mkdir()
        _write_state(locked / "run", _make_state(locked / "run", deck_slug="deck-locked"))
        locked.chmod(0)
        try:
            rc, out = _run_sweep(dep, extra_roots=(locked,), scan_depth=2)
        finally:
            locked.chmod(0o755)
        # the readable deck was still reconciled; the unreadable root was
        # reported UNDETERMINED rather than silently dropped or treated as empty
        assert rc == 0
        assert "card_missing: 1" in out
        assert "UNDETERMINED" in out

    def test_extra_root_run_is_actionable(self, tmp_path):
        dep = tmp_path / "dep"
        dep.mkdir()
        extra = tmp_path / "extra"
        run = extra / "2026-08-27"
        _write_state(run, _make_state(run, deck_slug="deck-x"))
        rc, out = _run_sweep(dep, extra_roots=(extra,), scan_depth=2, apply=False)
        assert "card_missing" in out, "a deck outside the department tree must be actionable"

    def test_summary_names_all_roots(self, tmp_path):
        dep = tmp_path / "dep"
        dep.mkdir()
        extra = tmp_path / "extra"
        extra.mkdir()
        _write_state(dep / "run1", _make_state(dep / "run1", deck_slug="deck-1"))
        rc, out = _run_sweep(dep, extra_roots=(extra,), scan_depth=1)
        assert str(dep) in out and str(extra) in out

    def test_zero_runs_anywhere_still_exit_10(self, tmp_path):
        dep = tmp_path / "dep"
        dep.mkdir()
        extra = tmp_path / "extra"
        extra.mkdir()
        rc, out = _run_sweep(dep, extra_roots=(extra,), scan_depth=1)
        assert rc == 10  # EXIT_SWEEP_NO_RUNS -- UNDETERMINED, unchanged contract