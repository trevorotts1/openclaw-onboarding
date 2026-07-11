#!/usr/bin/env python3
"""test_stage_s0_card_before_drive.py -- offline regression cover for finding A1.

The defect: the S0 dispatcher mirrored the participant's board card (mc_board.py
ensure) AFTER the holdable drive-tree-provision step, inside a short-circuiting
runner. When Drive provisioning HOLDS (exit 3 -- e.g. GOOGLE_IMPERSONATE_USER not
set) the runner returned before the mirror ever ran, so ledger participants got NO
board card (observed live: 5 ledger rows, 0 cards).

The fix: the fail-soft card mirror is wired BEFORE drive-tree-provision and its exit
code is never propagated. These tests prove, network-free (every collaborator
subprocess mocked), that:
  1. with Drive HELD, the card is STILL mirrored (mc_board ensure ran) and it ran
     BEFORE drive-tree-provision; the stage still holds (Drive is a hard dep).
  2. a board that itself refuses/errors NEVER holds S0 (fail-soft at the call site).
  3. on the happy path the order is still card-before-Drive.

Run: python3 -m pytest 59-anthology-engine/tests/test_stage_s0_card_before_drive.py -q
"""
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import stage_s0_intake as s0  # noqa: E402

PKEY = "CONTACT1::ANTH1"


class _Proc:
    def __init__(self, rc, out="{}"):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


def _make_fake_run(calls, drive_rc=0, board_rc=0):
    """A stage_s0_intake.subprocess.run stand-in that records the ORDER of the
    collaborator calls and lets each test choose the Drive / board exit codes."""
    def fake_run(argv, *args, **kwargs):
        script = Path(argv[1]).name if len(argv) > 1 else ""
        sub = argv[2] if len(argv) > 2 else ""
        # record (script, first-non-flag-subcommand-ish token) in call order
        marker = next((a for a in argv[2:] if not a.startswith("-")), sub)
        calls.append((script, marker))
        if script == "drive-tree-provision.py":
            return _Proc(drive_rc)
        if script == "mc_board.py":
            return _Proc(board_rc, '{"ok": true, "task_id": "card_x"}')
        # anthology_state.py: upsert-participant / get-anthology / advance-stage all 0
        return _Proc(0, "{}")
    return fake_run


def _index(calls, script):
    for i, (s, _m) in enumerate(calls):
        if s == script:
            return i
    return -1


def test_card_is_mirrored_before_drive_even_when_drive_holds(tmp_path, monkeypatch):
    """A1 core: Drive HELD (exit 3) must NOT stop the card mirror -- the card is
    created first, then the stage holds at Drive (a hard dependency)."""
    calls = []
    monkeypatch.setattr(s0.subprocess, "run", _make_fake_run(calls, drive_rc=3))
    # never actually spawn S1 (irrelevant here; Drive holds before the advance anyway)
    monkeypatch.setattr(s0, "_spawn_next", lambda *a, **k: False)

    rc = s0._invoke_wiring(PKEY, run_dir=str(tmp_path))

    # the board mirror ran (the card exists) ...
    board_i = _index(calls, "mc_board.py")
    drive_i = _index(calls, "drive-tree-provision.py")
    assert board_i != -1, "mc_board.py ensure must run -- the card must be created"
    assert drive_i != -1, "drive-tree-provision.py must run"
    # ... and it ran BEFORE drive-tree-provision (card-before-Drive) ...
    assert board_i < drive_i, "the card mirror MUST precede the holdable Drive step (A1)"
    # ... it was the idempotent 'ensure' create for THIS participant ...
    assert calls[board_i][1] == "ensure"
    # ... and the stage still HOLDS because Drive is a hard dependency (exit 3).
    assert rc == s0.EX_HELD, "Drive HELD still short-circuits the stage after the card is mirrored"


def test_board_refusal_never_holds_s0(tmp_path, monkeypatch):
    """A1 fail-soft: even a board that itself returns non-OK (a refusal/error) must
    NOT hold S0 -- the mirror's exit code is never propagated. With Drive OK the
    stage completes despite a dark board."""
    calls = []
    monkeypatch.setattr(s0.subprocess, "run",
                        _make_fake_run(calls, drive_rc=0, board_rc=2))  # board refuses
    spawned = {"n": 0}
    monkeypatch.setattr(s0, "_spawn_next", lambda *a, **k: spawned.__setitem__("n", spawned["n"] + 1))

    rc = s0._invoke_wiring(PKEY, run_dir=str(tmp_path))

    assert rc == s0.EX_OK, "a board refusal must NOT hold the stage (fail-soft at the call site)"
    assert _index(calls, "mc_board.py") != -1, "the mirror was still attempted"
    assert spawned["n"] == 1, "S0 still advanced + spawned S1 despite the dark board"


def test_happy_path_order_is_card_before_drive(tmp_path, monkeypatch):
    """On the fully-successful path the order is still card-before-Drive, and the
    stage completes (advance + spawn S1)."""
    calls = []
    monkeypatch.setattr(s0.subprocess, "run", _make_fake_run(calls, drive_rc=0, board_rc=0))
    monkeypatch.setattr(s0, "_spawn_next", lambda *a, **k: True)

    rc = s0._invoke_wiring(PKEY, run_dir=str(tmp_path))

    assert rc == s0.EX_OK
    assert _index(calls, "mc_board.py") < _index(calls, "drive-tree-provision.py"), \
        "card-before-Drive must hold on the happy path too"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
