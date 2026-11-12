"""PD-019: the message throttle is persisted in the job state, so a resume
(a fresh Reporter over the same state.json) does not repeat messages.

Stub transport only -- presentation_job.report.dispatch3 is replaced, no
system is called.
"""
import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

import presentation_job.report as rpt  # noqa: E402
from presentation_job.report import Reporter  # noqa: E402
from presentation_job.result import CheckResult  # noqa: E402
from presentation_job.state import StateStore  # noqa: E402


def _mkstate(tmp_path, chat_id="tc"):
    rd = tmp_path / "r"
    rd.mkdir()
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00", "manifest_path": "/x.json",
        "manifest_version": 25, "manifest_sha256": "0" * 64,
        "presentation_type": "from_scratch",
        "requester": {"chat_id": chat_id}, "phases": [], "gates": {},
        "waivers": [], "events": [], "sent": {}, "undeliverable": [],
        "heartbeat": {}, "terminal": None,
    }
    store.save(state)
    return state, store


class _StubTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, chat_id, kind, message):
        self.calls.append((chat_id, kind, message))
        return CheckResult.PASS


def _fake_clock(monkeypatch, minutes):
    monkeypatch.setattr(rpt, "_parse_minutes", lambda ts: minutes[0])


def test_a1_first_progress_survives_a_new_reporter(tmp_path, monkeypatch):
    """A1: first-phase message sent once; a new Reporter 1 minute later sends
    nothing for an ordinary progress message."""
    state, store = _mkstate(tmp_path)
    stub = _StubTransport()
    monkeypatch.setattr(rpt, "dispatch3", stub)
    clock = [0.0]
    _fake_clock(monkeypatch, clock)

    Reporter(state, store).to_requester(
        "progress", "Phase 1 of 46 — starting", phase_id="P1")
    assert len(stub.calls) == 1

    clock[0] = 1.0
    reloaded = store.load()
    Reporter(reloaded, store).to_requester(
        "progress", "Phase 2 of 46 — starting", phase_id="P2")

    assert len(stub.calls) == 1, "a resume must not repeat a throttled progress message"
    assert reloaded["report_throttle"]["first_phase_sent"] is True
    assert reloaded.get("throttled", 0) == 1


def test_a1_throttle_values_are_persisted(tmp_path, monkeypatch):
    """The three values live in state['report_throttle'] after a send."""
    state, store = _mkstate(tmp_path)
    monkeypatch.setattr(rpt, "dispatch3", _StubTransport())
    clock = [0.0]
    _fake_clock(monkeypatch, clock)

    Reporter(state, store).to_requester(
        "progress", "Phase 1 of 46 — starting", phase_id="P1")

    saved = store.load()["report_throttle"]
    assert saved["first_phase_sent"] is True
    assert saved["last_progress_at"]["__any__"] == 0.0
    assert isinstance(saved["blocked_dedupe"], dict)


def test_a2_blocked_dedupe_survives_a_new_reporter(tmp_path, monkeypatch):
    """A2: a delivered blocked message is not re-sent 2 minutes later by a new
    Reporter, and IS sent 11 minutes later."""
    state, store = _mkstate(tmp_path)
    stub = _StubTransport()
    monkeypatch.setattr(rpt, "dispatch3", stub)
    clock = [0.0]
    _fake_clock(monkeypatch, clock)

    Reporter(state, store).to_requester(
        "blocked", "x", phase_id="P4-RENDER", reason="exit 1")
    assert len(stub.calls) == 1
    saved = store.load()
    keys = list(saved["report_throttle"]["blocked_dedupe"])
    assert keys == ["P4-RENDER | exit 1"], keys
    assert "\x00" not in keys[0], "the dedupe key must survive a JSON round trip"

    clock[0] = 2.0
    Reporter(store.load(), store).to_requester(
        "blocked", "x", phase_id="P4-RENDER", reason="exit 1")
    assert len(stub.calls) == 1, "2 minutes later must still be deduped"

    clock[0] = 11.0
    Reporter(store.load(), store).to_requester(
        "blocked", "x", phase_id="P4-RENDER", reason="exit 1")
    assert len(stub.calls) == 2, "11 minutes later must be sent again"
