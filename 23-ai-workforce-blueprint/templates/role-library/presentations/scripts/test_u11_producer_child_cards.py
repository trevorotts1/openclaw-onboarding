"""test_u11_producer_child_cards.py — U11 Option B producer-side child cards.

Hermetic, offline (no live network — every HTTP call is a monkeypatched
cc_board._request), following the existing test_u030_status_repoint.py
pattern for cc_board.py-level tests and test_presentation_job.py's
TestBoardMirror pattern for board.py-level tests.

Covers, per the U11 acceptance criteria:
  (a) one card is created per phase (child_report(P0) and child_report(P1)
      each POST exactly once, to two distinct child_task_ids).
  (b) reporting the SAME phase twice creates ONE card, not two (the second
      child_report call for an already-known phase makes ZERO ingest POSTs).
  (c) a Command Center outage (transport error) never raises into the
      caller — child_report returns None/False, never an exception.

Also covers the dual state+manifest persistence (a resumed run with an
empty in-memory state but a populated process_manifest.json recovers the
mapping and skips re-creating), and that status resolution ('done' /
'blocked') is dispatched through the EXISTING, unmodified patch_phase
status-PATCH helper (same endpoint-routing rules already proven by
test_u030_status_repoint.py).
"""
from __future__ import annotations

import json
import sys
import tempfile
import urllib.error
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cc_board  # noqa: E402
from presentation_job.state import StateStore  # noqa: E402
from presentation_job.board import BoardMirror  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------
def _rd() -> Path:
    d = Path(tempfile.mkdtemp(prefix="u11-"))
    (d / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    return d


def _manifest(run_dir: Path) -> dict:
    p = run_dir / "working" / "checkpoints" / "process_manifest.json"
    return json.loads(p.read_text()) if p.exists() else {}


class _Recorder:
    """Records every cc_board._request(method, url, payload, cfg) call and
    replays a scripted queue of (status, body) responses or raised exceptions.
    Installed in place of cc_board._request (NOT urlopen) — one level higher
    than test_cc_board.py's Recorder, matching test_u030_status_repoint.py's
    lighter-weight monkeypatch-the-seam style."""

    def __init__(self):
        self.calls = []
        self.responses = []

    def queue(self, status, body):
        self.responses.append((status, body))

    def queue_raise(self, exc):
        self.responses.append(exc)

    def __call__(self, method, url, payload, cfg):
        self.calls.append((method, url, dict(payload) if isinstance(payload, dict) else payload))
        if not self.responses:
            raise AssertionError("no scripted response queued")
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


@pytest.fixture()
def wired(monkeypatch):
    """Install a _Recorder as cc_board._request and a fixed enabled board_config.
    Yields the recorder; cc_board._request/board_config are restored by
    monkeypatch's own teardown."""
    rec = _Recorder()
    monkeypatch.setattr(cc_board, "_request", rec)
    monkeypatch.setattr(
        cc_board, "board_config",
        lambda env=None: {"base_url": "http://cc.example.test", "token": "",
                          "secret": "", "timeout": 1},
    )
    return rec


class _Reporter:
    """Minimal stand-in for presentation_job.report.Reporter — records every
    event() call, mirroring TestBoardMirror._make_boardmirror's TestReporter."""

    def __init__(self):
        self.events = []

    def event(self, kind, message, **extra):
        self.events.append({"kind": kind, "message": message})

    def to_requester(self, *a, **kw):  # pragma: no cover — unused here
        pass


def _boardmirror(run_dir: Path, state: dict) -> tuple:
    store = StateStore(run_dir)
    reporter = _Reporter()
    bm = BoardMirror(run_dir, state, store, reporter)
    return bm, reporter, store


# ---------------------------------------------------------------------------
# Layer 1 — cc_board.py: ingest_child_task / read_child_task_id / stamp_child_task_id
# ---------------------------------------------------------------------------
def test_ingest_child_task_posts_parent_task_id(wired):
    rd = _rd()
    wired.queue(201, {"ok": True, "task_id": "child-1", "deduped": False})
    tid = cc_board.ingest_child_task(rd, "parent-99", "P4-RENDER", "P4-RENDER — Renderer", "desc")
    assert tid == "child-1"
    method, url, payload = wired.calls[0]
    assert method == "POST" and url.endswith("/api/tasks/ingest")
    assert payload["parent_task_id"] == "parent-99"
    assert payload["stage"] == "P4-RENDER"
    assert payload["department_slug"] == "presentations"


def test_ingest_child_task_idempotency_key_is_deterministic(wired):
    import hashlib
    rd = _rd()
    wired.queue(201, {"ok": True, "task_id": "child-1"})
    cc_board.ingest_child_task(rd, "parent-99", "P4-RENDER", "t", "d")
    _, _, payload = wired.calls[0]
    expected = hashlib.sha256(b"parent-99:P4-RENDER").hexdigest()
    assert payload["idempotency_key"] == expected


def test_ingest_child_task_stamps_manifest_without_clobbering(wired):
    rd = _rd()
    wired.queue(201, {"ok": True, "task_id": "child-A"})
    cc_board.ingest_child_task(rd, "parent-1", "P0A-INTAKE", "t", "d")
    wired.queue(201, {"ok": True, "task_id": "child-B"})
    cc_board.ingest_child_task(rd, "parent-1", "P4-RENDER", "t", "d")
    children = _manifest(rd).get("cc_child_task_ids")
    assert children == {"P0A-INTAKE": "child-A", "P4-RENDER": "child-B"}


def test_read_child_task_id_recovers_from_manifest(wired):
    rd = _rd()
    assert cc_board.read_child_task_id(rd, "P4-RENDER") is None
    cc_board.stamp_child_task_id(rd, "P4-RENDER", "child-42")
    assert cc_board.read_child_task_id(rd, "P4-RENDER") == "child-42"
    # A different, never-stamped phase is still None.
    assert cc_board.read_child_task_id(rd, "P9-DELIVER") is None


def test_ingest_child_task_no_url_is_noop(monkeypatch):
    monkeypatch.setattr(cc_board, "board_config", lambda env=None: None)
    rd = _rd()
    assert cc_board.ingest_child_task(rd, "parent-1", "P4-RENDER", "t", "d") is None
    assert _manifest(rd).get("cc_child_task_ids") is None


def test_ingest_child_task_transport_error_returns_none_never_raises(wired):
    rd = _rd()
    wired.queue_raise(urllib.error.URLError("connection refused"))
    result = cc_board.ingest_child_task(rd, "parent-1", "P4-RENDER", "t", "d")
    assert result is None  # did not raise


def test_ingest_child_task_no_parent_id_is_noop(wired):
    rd = _rd()
    assert cc_board.ingest_child_task(rd, "", "P4-RENDER", "t", "d") is None
    assert wired.calls == []  # never even attempted the POST


# ---------------------------------------------------------------------------
# Layer 2 — board.py: BoardMirror.child_report (real BoardMirror + real
# cc_board, only the HTTP seam is faked) — the exact call the engine makes.
# ---------------------------------------------------------------------------
def test_a_one_card_created_per_phase(wired):
    """(a) Each distinct phase gets its own child card."""
    rd = _rd()
    state = {"job_id": "pj_test", "board": {"task_id": "parent-1"}}
    bm, reporter, _ = _boardmirror(rd, state)

    wired.queue(201, {"ok": True, "task_id": "child-P0"})
    wired.queue(200, {"task": {}})  # patch_phase status PATCH/POST response
    bm.child_report("P0A-INTAKE", "P0A-INTAKE title", "desc", "done", "phase 0 done")

    wired.queue(201, {"ok": True, "task_id": "child-P4"})
    wired.queue(200, {"task": {}})
    bm.child_report("P4-RENDER", "P4-RENDER title", "desc", "done", "phase 4 done")

    ingest_calls = [c for c in wired.calls if c[1].endswith("/api/tasks/ingest")]
    assert len(ingest_calls) == 2
    created_ids = {payload["stage"]: payload for _, _, payload in ingest_calls}
    assert set(created_ids) == {"P0A-INTAKE", "P4-RENDER"}
    assert state["board"]["children"] == {"P0A-INTAKE": "child-P0", "P4-RENDER": "child-P4"}


def test_b_same_phase_twice_creates_one_card_not_two(wired):
    """(b) The core idempotency requirement: reporting the SAME phase twice
    must not create a second card — the second call makes ZERO ingest POSTs."""
    rd = _rd()
    state = {"job_id": "pj_test", "board": {"task_id": "parent-1"}}
    bm, reporter, _ = _boardmirror(rd, state)

    wired.queue(201, {"ok": True, "task_id": "child-P4"})
    wired.queue(200, {"task": {}})
    r1 = bm.child_report("P4-RENDER", "t", "d", "done", "first report")
    assert r1 is True

    # Second report of the SAME phase: only the status PATCH may re-fire, the
    # ingest POST must NOT happen again.
    wired.queue(200, {"task": {}})
    r2 = bm.child_report("P4-RENDER", "t", "d", "done", "second report (duplicate)")
    assert r2 is True

    ingest_calls = [c for c in wired.calls if c[1].endswith("/api/tasks/ingest")]
    assert len(ingest_calls) == 1, f"expected exactly ONE ingest POST, got {len(ingest_calls)}"
    assert state["board"]["children"]["P4-RENDER"] == "child-P4"


def test_resumed_run_reuses_manifest_mapping_without_reposting(wired):
    """A resumed run starts with EMPTY in-memory state but the previous
    process_manifest.json cc_child_task_ids mapping still on disk — the
    dual-recovery read must find it and skip re-creating."""
    rd = _rd()
    cc_board.stamp_child_task_id(rd, "P4-RENDER", "child-from-prior-run")

    # Fresh state dict — as if the process restarted (state["board"]["children"]
    # never got hydrated on this run yet).
    state = {"job_id": "pj_test", "board": {"task_id": "parent-1"}}
    bm, reporter, _ = _boardmirror(rd, state)

    wired.queue(200, {"task": {}})  # only the status PATCH should fire
    bm.child_report("P4-RENDER", "t", "d", "done", "resumed report")

    ingest_calls = [c for c in wired.calls if c[1].endswith("/api/tasks/ingest")]
    assert ingest_calls == [], "resumed run re-minted a child card instead of reusing it"


def test_c_outage_on_create_does_not_raise(wired):
    """(c) A Command Center outage during child-card CREATE never escapes.
    ingest_child_task fail-softs the transport error internally (same
    contract as ingest_deck_task: log to stderr, return None) — so this
    proves the FIRST of two independent fail-soft layers; the SECOND layer
    (BoardMirror._wrap catching whatever might slip past the first) is
    proven separately below by forcing an exception through a mocked
    cc_board, matching test_presentation_job.py's
    TestBoardMirror.test_typeerror_records_internal_error pattern."""
    rd = _rd()
    state = {"job_id": "pj_test", "board": {"task_id": "parent-1"}}
    bm, reporter, _ = _boardmirror(rd, state)

    wired.queue_raise(ConnectionRefusedError("CC is down"))
    result = bm.child_report("P4-RENDER", "t", "d", "done", "note")

    assert result is None  # did not raise
    assert "children" not in state.get("board", {}) or not state["board"].get("children")


def test_c_outage_on_status_patch_does_not_raise(wired):
    """(c) A Command Center outage during the status PATCH (card already
    exists) never escapes either. patch_phase's own documented contract is
    "FAIL-SOFT: returns False (never raises)" on a transport error — so
    child_report (which returns exactly what patch_phase returns) returns
    False here, not None; the requirement under test is that NOTHING raises."""
    rd = _rd()
    state = {"job_id": "pj_test", "board": {"task_id": "parent-1"}}
    bm, reporter, _ = _boardmirror(rd, state)

    wired.queue(201, {"ok": True, "task_id": "child-P4"})
    bm.child_report("P4-RENDER", "t", "d", "done", "first")

    wired.queue_raise(TimeoutError("CC timed out"))
    result = bm.child_report("P4-RENDER", "t", "d", "blocked", "second, now blocked")
    assert result is False  # did not raise despite the outage; patch_phase's own False


def test_c_wrap_layer_catches_unexpected_exception_and_never_raises(monkeypatch):
    """(c), second fail-soft layer: even if cc_board itself raised straight
    through (bypassing its own internal fail-soft — simulated here via a
    fully mocked cc_board, exactly like
    TestBoardMirror.test_typeerror_records_internal_error), BoardMirror._wrap
    still catches it, records board.internal_error, and never raises."""
    import presentation_job.board as board_module
    from unittest import mock

    fake_cc = mock.MagicMock()
    fake_cc.board_config.return_value = {"base_url": "http://example.com"}
    fake_cc.CC_TASK_STATUSES = frozenset({"done", "blocked"})
    # No child card known yet on either recovery path -- forces child_report
    # into the create branch, where the mocked ingest_child_task then raises.
    fake_cc.read_child_task_id.return_value = None
    fake_cc.ingest_child_task.side_effect = TypeError("boom — unexpected internal error")

    rd = _rd()
    state = {"job_id": "pj_test", "board": {"task_id": "parent-1"}}
    reporter = _Reporter()
    with mock.patch.object(board_module, "_cc_board", fake_cc):
        bm = board_module.BoardMirror(rd, state, StateStore(rd), reporter)
        result = bm.child_report("P4-RENDER", "t", "d", "done", "note")

    assert result is None  # did not raise
    internal_errors = [e for e in reporter.events if e["kind"] == "board.internal_error"]
    assert internal_errors, (
        f"no board.internal_error recorded; events={[e['kind'] for e in reporter.events]}"
    )


def test_no_parent_task_id_is_clean_noop(wired):
    """No parent card => nothing to nest a child under => no HTTP call at all."""
    rd = _rd()
    state = {"job_id": "pj_test"}  # no state["board"]["task_id"], no manifest cc_task_id
    bm, reporter, _ = _boardmirror(rd, state)

    result = bm.child_report("P4-RENDER", "t", "d", "done", "note")
    assert result is None
    assert wired.calls == []


def test_status_routing_matches_existing_patch_phase_rules(wired):
    """'blocked' (non-cert-bearing) routes to POST .../status; 'done'
    (cert-bearing) routes to PATCH .../{id} — proving child_report reuses
    patch_phase's EXISTING routing untouched (test_u030_status_repoint.py
    proves the same rules for the parent task)."""
    rd = _rd()
    state = {"job_id": "pj_test", "board": {"task_id": "parent-1"}}
    bm, reporter, _ = _boardmirror(rd, state)

    wired.queue(201, {"ok": True, "task_id": "child-X"})
    wired.queue(200, {})
    bm.child_report("P4-RENDER", "t", "d", "blocked", "gate failure reason")
    method, url, payload = wired.calls[-1]
    assert method == "POST" and url.endswith("/status") and payload["status"] == "blocked"

    wired.queue(200, {"task": {}})
    bm.child_report("P4-RENDER", "t", "d", "done", "now passes")
    method, url, payload = wired.calls[-1]
    assert method == "PATCH" and not url.endswith("/status")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
