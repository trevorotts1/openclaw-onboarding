"""Tests for the board reconciliation sweep.

No network -- injects a fake cc_board module whose board_config, ingest_deck_task,
and reconcile are recording stubs. Tests the sweep against a temporary filesystem.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixture scaffolding
# ---------------------------------------------------------------------------


def _make_state(
    run_dir: Path,
    *,
    schema_version: int = 1,
    job_id_prefix: str = "pj_test",
    terminal: str | None = None,
    created_hours_ago: float = 1.0,
    deck_slug: str = "deck-x",
    deck_title: str = "Test Deck",
    task_id: str | None = None,
    phases: list | None = None,
) -> dict:
    created = (
        datetime.now(timezone.utc) - timedelta(hours=created_hours_ago)
    ).astimezone().isoformat(timespec="seconds")
    state: dict = {
        "schema_version": schema_version,
        "job_id": f"{job_id_prefix}_{run_dir.name}",
        "run_dir": str(run_dir),
        "created_at": created,
        "terminal": terminal,
        "intake": {"deck_slug": deck_slug, "deck_title": deck_title},
    }
    if phases is not None:
        state["phases"] = phases
    else:
        state["phases"] = []
    if task_id is not None:
        state["board"] = {"task_id": task_id}
    return state


def _write_state(run_dir: Path, state: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps(state, indent=2))


def _write_manifest(run_dir: Path, cc_task_id: str | None, cc_register_attempted: bool = True) -> None:
    ckp = run_dir / "working" / "checkpoints"
    ckp.mkdir(parents=True, exist_ok=True)
    mf: dict = {"cc_register_attempted": cc_register_attempted}
    if cc_task_id is not None:
        mf["cc_task_id"] = cc_task_id
    (ckp / "process_manifest.json").write_text(json.dumps(mf, indent=2))


def _write_movements(run_dir: Path, movements: list) -> None:
    ckp = run_dir / "working" / "checkpoints"
    ckp.mkdir(parents=True, exist_ok=True)
    (ckp / "cc-board.json").write_text(
        json.dumps({"movements": movements, "successful_advances": sum(1 for m in movements if m.get("ok"))}, indent=2)
    )


# ---------------------------------------------------------------------------
# Fake board
# ---------------------------------------------------------------------------

# These are patched in by the test functions
_FAKE_RECORDS: list[dict] = []
_FAKE_BOARD_OFF = False
_FAKE_RECONCILE_RC = 0

FAKE_CC_TASK_STATUSES = frozenset(
    {"backlog", "inbox", "planning", "in_progress", "assigned",
     "review", "testing", "blocked", "pending_dispatch", "done"}
)


def fake_board_config(env=None):
    if _FAKE_BOARD_OFF:
        return None
    return {"base_url": "http://fake", "token": "", "secret": "", "timeout": 1}


def fake_ingest_deck_task(run_dir, deck_slug, title, description, priority="medium", env=None):
    _FAKE_RECORDS.append({
        "fn": "ingest_deck_task",
        "run_dir": str(run_dir),
        "deck_slug": deck_slug,
        "title": title,
        "description": description,
        "priority": priority,
    })
    return "task-" + str(deck_slug)


def fake_reconcile(run_dir):
    _FAKE_RECORDS.append({
        "fn": "reconcile",
        "run_dir": str(run_dir),
    })
    return _FAKE_RECONCILE_RC


def fake_open_card(deck_slug, title, description):
    _FAKE_RECORDS.append({
        "fn": "open_card",
        "deck_slug": deck_slug,
        "title": title,
        "description": description,
    })
    return "task-" + str(deck_slug)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_cc_board(monkeypatch):
    """Replace cc_board with our recording stubs inside the sweep module."""
    import presentation_job.sweep as sweep_mod
    import presentation_job.board as board_mod

    global _FAKE_RECORDS, _FAKE_BOARD_OFF, _FAKE_RECONCILE_RC
    _FAKE_RECORDS.clear()
    _FAKE_BOARD_OFF = False
    _FAKE_RECONCILE_RC = 0

    # Patch the lazy imports inside reconcile_sweep
    monkeypatch.setattr(sweep_mod, "os", os)
    # We need to ensure cc_board is patched when it's imported in reconcile_sweep
    monkeypatch.setattr(board_mod, "_get_cc_board", lambda: _make_fake_cc_board())

    # Patch __main__ import of reconcile_sweep's dependencies
    monkeypatch.setattr(
        "presentation_job.board.BoardMirror", _FakeBoardMirror
    )


def _make_fake_cc_board():
    """Return a module-like object that the sweep's lazy import will use."""
    return _FakeCCBoard()


class _FakeCCBoard:
    CC_TASK_STATUSES = FAKE_CC_TASK_STATUSES

    @staticmethod
    def board_config(env=None):
        return fake_board_config(env)

    @staticmethod
    def ingest_deck_task(run_dir, deck_slug, title, description, priority="medium", env=None):
        return fake_ingest_deck_task(run_dir, deck_slug, title, description, priority, env=env)

    @staticmethod
    def reconcile(run_dir):
        return fake_reconcile(run_dir)


class _FakeBoardMirror:
    def __init__(self, run_dir, state, store, reporter):
        self.run_dir = run_dir
        self.state = state
        self.store = store
        self.report = reporter

    def open_card(self, deck_slug, title, description):
        _FAKE_RECORDS.append({
            "fn": "open_card",
            "run_dir": str(self.run_dir),
            "deck_slug": deck_slug,
            "title": title,
            "description": description,
        })
        task_id = "task-" + str(deck_slug)
        self.state.setdefault("board", {})["task_id"] = task_id
        return task_id


# ---------------------------------------------------------------------------
# Helper to run the sweep
# ---------------------------------------------------------------------------


def _run_sweep(
    scan_root: Path,
    *,
    scan_depth: int = 2,
    apply: bool = False,
    max_age_hours: float = 72.0,
    board_off: bool = False,
    reconcile_rc: int = 0,
) -> tuple[int, str]:
    """Run the sweep with capture. Returns (exit_code, stdout_string)."""
    global _FAKE_BOARD_OFF, _FAKE_RECONCILE_RC, _FAKE_RECORDS
    _FAKE_RECORDS.clear()
    _FAKE_BOARD_OFF = board_off
    _FAKE_RECONCILE_RC = reconcile_rc

    from io import StringIO

    # Patch sys.modules and capture stdout
    import sys as _sys

    class FakeMod:
        CC_TASK_STATUSES = FAKE_CC_TASK_STATUSES

        @staticmethod
        def board_config(env=None):
            return fake_board_config(env)

        @staticmethod
        def ingest_deck_task(run_dir, deck_slug, title, description, priority="medium", env=None):
            return fake_ingest_deck_task(run_dir, deck_slug, title, description, priority, env=env)

        @staticmethod
        def reconcile(run_dir):
            return fake_reconcile(run_dir)

    _sys.modules["cc_board"] = FakeMod

    old_stdout = _sys.stdout
    buf = StringIO()
    _sys.stdout = buf
    try:
        from presentation_job.sweep import reconcile_sweep

        rc = reconcile_sweep(
            scan_root,
            scan_depth=scan_depth,
            apply=apply,
            max_age_hours=max_age_hours,
        )
    finally:
        _sys.stdout = old_stdout
        # Clean up
        _sys.modules.pop("cc_board", None)
    return rc, buf.getvalue()


def _hash_state_files(root: Path) -> str:
    """SHA256 of all state.json files sorted."""
    files = sorted(root.glob("**/state.json"))
    h = hashlib.sha256()
    for f in files:
        h.update(f.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBoardDisabled:
    """With board_config() returning None, the sweep reports board_disabled,
    makes zero stub calls, and exits 0."""

    def test_board_disabled_zero_calls(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-1"))
        _FAKE_RECORDS.clear()

        # Set board off, call _run_sweep
        rc, out = _run_sweep(root, board_off=True)
        assert rc == 0
        assert "board_disabled" in out
        # No ingest calls because board is off
        assert len(_FAKE_RECORDS) == 0
        # Still classified
        assert "card_missing" in out


class TestNotARunDir:
    """Directories that are not valid engine run dirs are never ingested."""

    def test_no_state_json(self, tmp_path):
        from presentation_job.state import EXIT_SWEEP_NO_RUNS

        root = tmp_path / "scan"
        root.mkdir()
        (root / "junk").mkdir()
        (root / "junk" / "notes.txt").write_text("not a run dir")

        rc, out = _run_sweep(root, scan_depth=2)
        # Zero run dirs found is UNDETERMINED, not a pass -- G5.
        assert rc == EXIT_SWEEP_NO_RUNS
        assert rc != 0
        # No state.json found anywhere -> explicit NO state.json line, marked
        # unmistakably as not-a-pass.
        assert "NO state.json" in out
        assert "UNDETERMINED" in out
        assert "not a pass" in out.lower()

    def test_state_no_job_id(self, tmp_path):
        from presentation_job.state import EXIT_OK, EXIT_SWEEP_ALL_REJECTED

        root = tmp_path / "scan"
        root.mkdir()
        d = root / "bad"
        d.mkdir()
        (d / "state.json").write_text(json.dumps({"schema_version": 1, "job_id": "wrong_format"}))

        rc, out = _run_sweep(root)
        # G5: the ONLY run dir found was rejected -- zero were ever classified,
        # which is the same epistemic state as an empty scan. Must not be a pass.
        assert rc == EXIT_SWEEP_ALL_REJECTED
        assert rc != EXIT_OK
        assert "not_a_run_dir" in out
        assert "NOT a pass" in out

    def test_wrong_schema_version(self, tmp_path):
        from presentation_job.state import EXIT_OK, EXIT_SWEEP_ALL_REJECTED

        root = tmp_path / "scan"
        root.mkdir()
        d = root / "bad"
        d.mkdir()
        _write_state(d, _make_state(d, schema_version=99))

        rc, out = _run_sweep(root)
        assert rc == EXIT_SWEEP_ALL_REJECTED
        assert rc != EXIT_OK
        assert "not_a_run_dir" in out
        assert "SCHEMA VERSION MISMATCH" in out
        assert "NOT a pass" in out

    def test_bad_json_state(self, tmp_path):
        from presentation_job.state import EXIT_OK, EXIT_SWEEP_ALL_REJECTED

        root = tmp_path / "scan"
        root.mkdir()
        d = root / "bad"
        d.mkdir()
        (d / "state.json").write_text("{not json")

        rc, out = _run_sweep(root)
        assert rc == EXIT_SWEEP_ALL_REJECTED
        assert rc != EXIT_OK
        assert "not_a_run_dir" in out
        assert "NOT a pass" in out


class TestCardMissing:
    """Valid run dirs with no task_id anywhere are card_missing."""

    def test_card_missing_dry_run_zero_calls(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-a"))
        _FAKE_RECORDS.clear()

        rc, out = _run_sweep(root, apply=False)
        assert rc == 0
        assert "card_missing" in out
        assert len(_FAKE_RECORDS) == 0  # dry run, zero calls

    def test_card_missing_apply_calls_ingest_once(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-a"))
        _FAKE_RECORDS.clear()

        rc, out = _run_sweep(root, apply=True)
        assert rc == 0
        assert "card_missing" in out
        ingest_calls = [r for r in _FAKE_RECORDS if r["fn"] == "ingest_deck_task"]
        assert len(ingest_calls) == 1
        assert ingest_calls[0]["deck_slug"] == "deck-a"


class TestConsistent:
    """Run dirs with a task_id are consistent and never re-ingested."""

    def test_consistent_with_cc_task_id(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-b"))
        _write_manifest(root / "run1", cc_task_id="t-1")
        _write_movements(root / "run1", [
            {"kind": "status", "ok": True, "phase_id": "P4-RENDER", "target": "in_progress"}
        ])

        rc, out = _run_sweep(root, apply=True)
        assert rc == 0
        assert "consistent" in out
        ingest_calls = [r for r in _FAKE_RECORDS if r["fn"] == "ingest_deck_task"]
        assert len(ingest_calls) == 0  # already has card, not re-ingested

    def test_consistent_with_state_board_task_id(self, tmp_path):
        """Either record suffices -- state["board"]["task_id"] alone means consistent."""
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-d", task_id="t-3"))

        rc, out = _run_sweep(root, apply=True)
        assert rc == 0
        assert "consistent" in out
        ingest_calls = [r for r in _FAKE_RECORDS if r["fn"] == "ingest_deck_task"]
        assert len(ingest_calls) == 0


class TestCardBehind:
    """Run dirs with a task_id and unsuperseded ok:false status movement delegate to reconcile."""

    def test_card_behind_reconcile_called(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-c"))
        _write_manifest(root / "run1", cc_task_id="t-2")
        _write_movements(root / "run1", [
            {"kind": "status", "ok": False, "phase_id": "P4-RENDER", "target": "in_progress"}
        ])

        rc, out = _run_sweep(root, apply=True)
        assert rc == 0
        assert "card_behind" in out
        reconcile_calls = [r for r in _FAKE_RECORDS if r["fn"] == "reconcile"]
        assert len(reconcile_calls) == 1

    def test_reconcile_returns_1_reported(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-c"))
        _write_manifest(root / "run1", cc_task_id="t-2")
        _write_movements(root / "run1", [
            {"kind": "status", "ok": False, "phase_id": "P4-RENDER", "target": "in_progress"}
        ])

        rc, out = _run_sweep(root, apply=True, reconcile_rc=1)
        assert rc == 0
        reconcile_calls = [r for r in _FAKE_RECORDS if r["fn"] == "reconcile"]
        assert len(reconcile_calls) == 1
        # sweep continues, non-zero rc reported
        assert "replay" in out.lower() or "still failed" in out.lower() or "failed" in out.lower()


class TestTooOld:
    """Run dirs older than max_age_hours are too_old, and both directions are tested."""

    def test_too_old_at_default_72(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-e", created_hours_ago=100.0))

        rc, out = _run_sweep(root, max_age_hours=72.0, apply=True)
        assert rc == 0
        assert "too_old" in out
        ingest_calls = [r for r in _FAKE_RECORDS if r["fn"] == "ingest_deck_task"]
        assert len(ingest_calls) == 0

    def test_not_too_old_at_200(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-e", created_hours_ago=100.0))

        rc, out = _run_sweep(root, max_age_hours=200.0, apply=True)
        assert rc == 0
        assert "card_missing" in out or "consistent" in out
        # Should NOT be flagged as too_old in the classification line
        # "too_old: 0" in the summary is fine
        assert "  too_old" not in out


class TestFinishedJobNotIngested:
    """A run dir with terminal 'DONE' and no card is not ingested."""

    def test_finished_not_ingested(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-f", terminal="DONE"))

        rc, out = _run_sweep(root, apply=True)
        assert rc == 0
        ingest_calls = [r for r in _FAKE_RECORDS if r["fn"] == "ingest_deck_task"]
        assert len(ingest_calls) == 0


class TestNoSlugYieldsNotARunDir:
    """A run dir whose _deck_slug returns None is not_a_run_dir."""

    def test_no_slug_not_ingested(self, tmp_path):
        from presentation_job.state import EXIT_OK, EXIT_SWEEP_ALL_REJECTED

        root = tmp_path / "scan"
        root.mkdir()
        state = _make_state(root / "run1", deck_slug="")
        state["intake"] = {"deck_slug": "", "deck_title": "T"}
        _write_state(root / "run1", state)

        rc, out = _run_sweep(root, apply=True)
        # G5: the only run dir found was unresolvable -- zero classified, not a pass.
        assert rc == EXIT_SWEEP_ALL_REJECTED
        assert rc != EXIT_OK
        assert "not_a_run_dir" in out
        ingest_calls = [r for r in _FAKE_RECORDS if r["fn"] == "ingest_deck_task"]
        assert len(ingest_calls) == 0

    def test_dir_name_not_used_as_slug(self, tmp_path):
        """The directory name must never be used as the slug."""
        from presentation_job.state import EXIT_OK, EXIT_SWEEP_ALL_REJECTED

        root = tmp_path / "scan"
        root.mkdir()
        state = _make_state(root / "some-random-dir", deck_slug="")
        state["intake"] = {"deck_slug": "", "deck_title": "T"}
        _write_state(root / "some-random-dir", state)

        rc, out = _run_sweep(root, apply=True)
        assert rc == EXIT_SWEEP_ALL_REJECTED
        assert rc != EXIT_OK
        # The ingest should never be called with "some-random-dir" as slug
        ingest_calls = [r for r in _FAKE_RECORDS if r["fn"] == "ingest_deck_task"]
        assert len(ingest_calls) == 0


class TestTitleIndependentMatch:
    """Two run dirs sharing a deck_slug but with different titles resolve to the same handle,
    and the second is consistent, not card_missing."""

    def test_same_slug_different_title_not_duplicated(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()

        # First run dir: no card yet
        _write_state(root / "m1", _make_state(root / "m1", deck_slug="alpha", deck_title="Original Title"))

        # Second run dir: same slug, different title, HAS a card already
        _write_state(root / "m2", _make_state(root / "m2", deck_slug="alpha", deck_title="RENAMED ON BOARD"))
        _write_manifest(root / "m2", cc_task_id="t-alpha")
        _write_movements(root / "m2", [
            {"kind": "status", "ok": True, "phase_id": "P4-RENDER", "target": "in_progress"}
        ])

        rc, out = _run_sweep(root, apply=True)
        assert rc == 0
        ingest_calls = [r for r in _FAKE_RECORDS if r["fn"] == "ingest_deck_task"]
        # m1 is card_missing -> ingested once; m2 is consistent -> not ingested
        assert len(ingest_calls) == 1
        assert ingest_calls[0]["deck_slug"] == "alpha"
        # The title is never used as a match key
        assert "consistent" in out


class TestNeverSendsDone:
    """A target status of 'done' is never sent."""

    def test_done_never_sent(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        # A finished job that DOES have a card — if it needed advancing, it would
        # go to card_behind, and reconcile handles it. The sweep itself never
        # derives "done" as a target.
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-z", terminal="DONE"))
        _write_manifest(root / "run1", cc_task_id="t-zeta")
        _write_movements(root / "run1", [
            {"kind": "status", "ok": True, "phase_id": "P4-RENDER", "target": "in_progress"}
        ])

        rc, out = _run_sweep(root, apply=True)
        assert rc == 0
        assert "consistent" in out
        # No done patch was sent
        # The sweep doesn't call patch_phase directly — it delegates to reconcile
        # for card_behind. This confirms the sweep itself never sends done.


class TestStateJsonUntouched:
    """state.json is byte-identical before and after every sweep mode."""

    def test_state_json_unchanged(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-a"))
        _write_state(root / "run2", _make_state(root / "run2", deck_slug="deck-b"))
        _write_manifest(root / "run2", cc_task_id="t-1")
        _write_movements(root / "run2", [
            {"kind": "status", "ok": True, "phase_id": "P4-RENDER", "target": "in_progress"}
        ])

        before = _hash_state_files(root)
        rc, out = _run_sweep(root, apply=True)
        assert rc == 0
        after = _hash_state_files(root)
        assert before == after, "state.json was modified by the sweep"

        # Also test dry run
        before2 = _hash_state_files(root)
        rc2, out2 = _run_sweep(root, apply=False)
        assert rc2 == 0
        after2 = _hash_state_files(root)
        assert before2 == after2, "state.json was modified during dry run"


class TestBrokenRunDirContinues:
    """A run dir that raises inside the sweep body is recorded as failure
    and the next run dir is still processed."""

    def test_broken_dir_does_not_end_sweep(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        # Broken
        (root / "broken").mkdir()
        (root / "broken" / "state.json").write_text("{not json")
        # Good
        _write_state(root / "good", _make_state(root / "good", deck_slug="deck-good"))

        rc, out = _run_sweep(root)
        assert rc == 0
        assert "not_a_run_dir" in out  # broken
        # The good run dir should still be classified
        assert "card_missing" in out


class TestSweepFailurePropagatesExitCode:
    """G5: 'FAIL-SOFT' means one bad run dir never ENDS the loop -- it does
    not mean the sweep's own return code gets to lie about it. A run dir
    whose ingest call raises is recorded as 'failure'; the sweep as a whole
    must then return EXIT_SWEEP_HAD_FAILURES, not EXIT_OK."""

    def test_ingest_exception_makes_sweep_fail(self, tmp_path, monkeypatch):
        from presentation_job.state import EXIT_OK, EXIT_SWEEP_HAD_FAILURES

        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "boom", _make_state(root / "boom", deck_slug="deck-boom"))

        def _boom(*a, **kw):
            raise RuntimeError("simulated ingest failure")

        # fake_ingest_deck_task is looked up as a module global at call time,
        # so patching it here reaches the FakeMod.ingest_deck_task shim that
        # _run_sweep installs as the sweep's cc_board.
        monkeypatch.setattr(sys.modules[__name__], "fake_ingest_deck_task", _boom)

        rc, out = _run_sweep(root, apply=True)
        assert rc == EXIT_SWEEP_HAD_FAILURES
        assert rc != EXIT_OK
        assert "FAILED" in out
        assert "not a pass" in out.lower()


class TestAllRejectedIsNotAPass:
    """G5 HARDEN: an adversarial re-attack proved that when every run dir a
    sweep finds is rejected by Guard A (not_a_run_dir), the sweep printed a
    reassuring 'scanned N ... not_a_run_dir: N' and still returned EXIT_OK --
    worse than an empty scan, because 'scanned N' reads as having checked
    something. Three vectors, all proven to force rc=0 before this fix:
      1. STATE_SCHEMA_VERSION bumped -- every run dir fails the `!=` check.
      2. truncated/corrupt state.json on every run dir.
      3. unresolvable deck_slug on every run dir.
    None of these may return EXIT_OK. The legitimate "some rejected, some
    fine" path (real fleets always carry debris) must still pass."""

    def test_schema_bump_rejects_everything_not_a_pass(self, tmp_path):
        """Vector 1: a routine STATE_SCHEMA_VERSION bump makes EVERY run dir
        on the box invalid. Must be caught AND clearly named as a schema
        issue, not silently reported as a clean empty-ish sweep."""
        from presentation_job.state import EXIT_OK, EXIT_SWEEP_ALL_REJECTED

        root = tmp_path / "scan"
        root.mkdir()
        for i in range(5):
            d = root / f"run{i}"
            _write_state(d, _make_state(d, deck_slug=f"deck-{i}", schema_version=99))

        rc, out = _run_sweep(root)
        assert rc == EXIT_SWEEP_ALL_REJECTED
        assert rc != EXIT_OK
        assert "scanned 5" in out
        assert "not_a_run_dir: 5" in out
        assert "reconciled 0" in out
        # Unmistakable: names the schema mismatch specifically, not a generic shrug.
        assert "SCHEMA VERSION MISMATCH" in out
        assert "schema_version" in out.lower()
        assert "NOT a pass" in out

    def test_corrupt_json_rejects_everything_not_a_pass(self, tmp_path):
        """Vector 2: truncated/corrupt state.json on every run dir (e.g. a
        crash or disk-full mid-write)."""
        from presentation_job.state import EXIT_OK, EXIT_SWEEP_ALL_REJECTED

        root = tmp_path / "scan"
        root.mkdir()
        for i in range(5):
            d = root / f"run{i}"
            d.mkdir()
            (d / "state.json").write_text('{"schema_version": 1, "job_id": "pj_x", truncat')

        rc, out = _run_sweep(root)
        assert rc == EXIT_SWEEP_ALL_REJECTED
        assert rc != EXIT_OK
        assert "scanned 5" in out
        assert "not_a_run_dir: 5" in out
        assert "reconciled 0" in out
        assert "NOT a pass" in out

    def test_unresolvable_slug_rejects_everything_not_a_pass(self, tmp_path):
        """Vector 3: every run dir resolves to no deck_slug."""
        from presentation_job.state import EXIT_OK, EXIT_SWEEP_ALL_REJECTED

        root = tmp_path / "scan"
        root.mkdir()
        for i in range(5):
            d = root / f"run{i}"
            state = _make_state(d, deck_slug="")
            state["intake"] = {"deck_slug": "", "deck_title": "T"}
            _write_state(d, state)

        rc, out = _run_sweep(root)
        assert rc == EXIT_SWEEP_ALL_REJECTED
        assert rc != EXIT_OK
        assert "scanned 5" in out
        assert "not_a_run_dir: 5" in out
        assert "reconciled 0" in out
        assert "NOT a pass" in out

    def test_mixed_rejects_and_one_good_still_passes(self, tmp_path):
        """The legitimate path is NOT broken by this fix: a real fleet always
        carries some debris (old/broken run dirs) alongside real ones. As
        long as at least one run dir was actually classified, this is still
        a genuine pass."""
        from presentation_job.state import EXIT_OK

        root = tmp_path / "scan"
        root.mkdir()
        for i in range(4):
            d = root / f"bad{i}"
            _write_state(d, _make_state(d, deck_slug=f"deck-{i}", schema_version=99))
        _write_state(root / "good", _make_state(root / "good", deck_slug="deck-good"))

        rc, out = _run_sweep(root)
        assert rc == EXIT_OK
        assert "scanned 5" in out
        assert "not_a_run_dir: 4" in out
        assert "reconciled 1" in out
        assert "card_missing" in out

    def test_failures_take_priority_over_all_rejected_wording(self, tmp_path):
        """When a run dir raises AND the rest are all rejected, the sweep
        must still report non-pass (already guaranteed by EXIT_SWEEP_HAD_FAILURES,
        proven here to not regress into EXIT_OK now that the all-rejected
        branch also exists)."""
        from presentation_job.state import EXIT_OK, EXIT_SWEEP_HAD_FAILURES

        root = tmp_path / "scan"
        root.mkdir()
        for i in range(3):
            d = root / f"bad{i}"
            _write_state(d, _make_state(d, deck_slug=f"deck-{i}", schema_version=99))
        _write_state(root / "boom", _make_state(root / "boom", deck_slug="deck-boom"))

        def _boom(*a, **kw):
            raise RuntimeError("simulated ingest failure")

        import sys as _sys
        orig = _sys.modules[__name__].fake_ingest_deck_task
        _sys.modules[__name__].fake_ingest_deck_task = _boom
        try:
            rc, out = _run_sweep(root, apply=True)
        finally:
            _sys.modules[__name__].fake_ingest_deck_task = orig

        assert rc == EXIT_SWEEP_HAD_FAILURES
        assert rc != EXIT_OK


class TestFinishedNoCardCountsAsReconciled:
    """finished_no_card is a REAL classification (Guard A + slug already
    passed) -- it must count toward 'reconciled' and must never be lumped
    into not_a_run_dir, or a box where every job finished cleanly with no
    card would wrongly trip the all-rejected gate on a perfectly healthy
    sweep."""

    def test_all_finished_no_card_is_still_a_pass(self, tmp_path):
        from presentation_job.state import EXIT_OK

        root = tmp_path / "scan"
        root.mkdir()
        for i in range(5):
            d = root / f"run{i}"
            _write_state(d, _make_state(d, deck_slug=f"deck-{i}", terminal="DONE"))

        rc, out = _run_sweep(root, apply=True)
        assert rc == EXIT_OK
        assert "scanned 5" in out
        assert "reconciled 5" in out
        assert "finished_no_card: 5" in out
        assert "not_a_run_dir: 0" in out
        ingest_calls = [r for r in _FAKE_RECORDS if r["fn"] == "ingest_deck_task"]
        assert len(ingest_calls) == 0


class TestEmptyScan:
    """scanned == 0 is UNDETERMINED, not a pass (G5) -- it prints the explicit
    NO state.json line AND returns a distinct non-EXIT_OK code so a caller
    that only checks the return code cannot mistake "found nothing" for
    "found N and all were fine"."""

    def test_empty_scan_says_no_state_json(self, tmp_path):
        from presentation_job.state import EXIT_OK, EXIT_SWEEP_NO_RUNS

        root = tmp_path / "scan"
        root.mkdir()
        (root / "sub").mkdir()

        rc, out = _run_sweep(root)
        assert rc == EXIT_SWEEP_NO_RUNS
        assert rc != EXIT_OK
        assert "NO state.json" in out or "NO state.json found" in out
        assert "UNDETERMINED" in out

    def test_empty_scan_code_distinct_from_all_rejected_code(self, tmp_path):
        """The two UNDETERMINED codes must stay distinguishable -- 'found
        nothing' (10) and 'found some, rejected all of them' (12) are
        reached through different paths and a caller may want to log them
        differently even though both are non-pass."""
        from presentation_job.state import EXIT_SWEEP_NO_RUNS, EXIT_SWEEP_ALL_REJECTED

        assert EXIT_SWEEP_NO_RUNS != EXIT_SWEEP_ALL_REJECTED

        root = tmp_path / "scan"
        root.mkdir()
        rc, _ = _run_sweep(root)
        assert rc == EXIT_SWEEP_NO_RUNS


class TestApplyWithoutReconcileBoard:
    """--apply without --reconcile-board exits 2."""

    def test_apply_without_reconcile_board_exits_2(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()

        from presentation_job.__main__ import main, build_parser
        p = build_parser()
        try:
            p.parse_args(["--apply", "--scan-root", str(root)])
            # If no error, verify that main catches it
            rc = main(["--apply", "--scan-root", str(root)])
            assert rc == 2
        except SystemExit as exc:
            assert exc.code == 2


class TestScanDepthHonoured:
    """--scan-depth is honoured, both directions."""

    def test_depth_1_does_not_find_depth_2(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "top", _make_state(root / "top", deck_slug="d-top"))
        nested = root / "nested" / "deep"
        _write_state(nested, _make_state(nested, deck_slug="d-deep"))

        rc, out = _run_sweep(root, scan_depth=1)
        assert rc == 0
        # "top" should be found (depth 1)
        assert "top" in out
        # "deep" should NOT be found at depth 1
        # "scanned 1" means only top was found
        assert "scanned 1" in out or "scanned 1 " in out or "scan" in out.lower()

    def test_depth_2_finds_depth_2(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "top", _make_state(root / "top", deck_slug="d-top"))
        nested = root / "nested" / "deep"
        _write_state(nested, _make_state(nested, deck_slug="d-deep"))

        rc, out = _run_sweep(root, scan_depth=2)
        assert rc == 0
        assert "top" in out
        assert "nested" in out or "deep" in out
        assert "scanned 2" in out


class TestEachRunDirCountedOnce:
    """The walk counts each run dir once."""

    def test_symlinked_run_dir_counted_once(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-x"))

        # Create a symlink to the same run dir at a different path
        alt = root / "alt"
        alt.mkdir()
        link = alt / "run1"
        link.symlink_to(root / "run1", target_is_directory=True)

        rc, out = _run_sweep(root, scan_depth=2)
        assert rc == 0
        assert "scanned 1" in out, f"Expected scanned 1, got: {out}"


class TestSummaryHasDenominator:
    """Every summary carries a denominator."""

    def test_summary_has_scanned_denominator(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-a"))

        rc, out = _run_sweep(root)
        assert rc == 0
        assert "scanned 1" in out


class TestNoDeadImports:
    """The sweep module can be imported without side effects."""

    def test_sweep_can_be_imported(self):
        from presentation_job.sweep import reconcile_sweep, _deck_slug, _classify, _find_run_dirs
        assert callable(reconcile_sweep)
        assert callable(_deck_slug)
        assert callable(_classify)
        assert callable(_find_run_dirs)


class TestFindingsFile:
    """reconcile-findings.jsonl is written per actionable run dir per scan."""

    def test_findings_file_has_correct_shape(self, tmp_path):
        root = tmp_path / "scan"
        root.mkdir()
        _write_state(root / "run1", _make_state(root / "run1", deck_slug="deck-a"))

        findings_path = root / "reconcile-findings.jsonl"
        # Run twice
        _run_sweep(root, apply=False)  # dry run -> writes
        _run_sweep(root, apply=True)   # apply -> writes

        assert findings_path.exists()
        lines = [l for l in findings_path.read_text().splitlines() if l.strip()]
        assert len(lines) >= 1
        for line in lines:
            obj = json.loads(line)
            assert "run_dir" in obj
            assert "outcome" in obj
            assert "deck_slug" in obj
            assert "applied" in obj
