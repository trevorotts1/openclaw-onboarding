"""FIX-7 (D14) — the render poll loop must have a hard cap with exponential backoff
(10s/20s/40s) and return a terminal FAIL (RenderPollTimeout) instead of hanging the
run in 'in_progress'.

QC gate (GAUNTLET-LOOP row FIX-7):
  Start a kie task (or mock) that never completes; run the poll loop
  -> Loop exits FAIL at <= 15 min, surfaces a terminal status; task status updates;
     no silent hang.
  Evidence: timestamped poll log showing the FAIL surface; elapsed time.

The cap is a wall-clock deadline, so the deterministic unit tests monkeypatch the
clock to prove the LADDER and the HARD CAP without waiting 15 real minutes, and one
real-time test runs a compressed cap (30s, the env floor) against a never-completing
mock to prove the loop actually terminates on the wall clock.
"""

import json
import sys
import time
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

import build_deck as bd


class _FakeClock:
    """Deterministic fake time: poll_task calls time.time() for the deadline and
    time.sleep() to wait. sleep() advances the fake clock by the requested interval,
    so the wall-clock cap is exercised exactly as in production."""

    def __init__(self, start=1_000_000.0):
        self.now = start
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, sec):
        self.sleeps.append(sec)
        self.now += sec


def _never_completing_http(state="processing"):
    """A mocked _http_json that always reports a healthy non-terminal state — the
    'task that never completes' from the FIX-7 test spec."""

    def fake(method, url, api_key, body=None):
        assert url.startswith(bd.POLL_URL)
        return {"code": 200, "data": {"state": state}}

    return fake


def _success_http(after=1):
    """Control: a task that DOES complete after `after` polls. Proves the poll loop
    still succeeds on a real render (the known-good control of the QC row)."""
    calls = {"n": 0}

    def fake(method, url, api_key, body=None):
        calls["n"] += 1
        if calls["n"] < after:
            return {"code": 200, "data": {"state": "processing"}}
        return {"code": 200, "data": {
            "state": "success",
            "resultJson": json.dumps({"resultUrls": ["https://cdn.example/x.png"]}),
        }}

    return fake


# ---------------------------------------------------------------------------
# Test 1: deterministic ladder + hard cap under a fake clock
# ---------------------------------------------------------------------------
class TestPollCapDeterministic:
    def test_never_completing_task_raises_renderpolltimeout_at_cap(self, monkeypatch):
        """A task that never completes must surface RenderPollTimeout at the hard
        cap (never a silent hang)."""
        fake = _FakeClock()
        monkeypatch.setattr(bd.time, "time", fake.time)
        monkeypatch.setattr(bd.time, "sleep", fake.sleep)
        monkeypatch.setattr(bd, "POLL_MAX_SECONDS", 900)  # production cap
        monkeypatch.setattr(bd, "_http_json", _never_completing_http())

        started = fake.time()
        with pytest.raises(bd.RenderPollTimeout) as exc:
            bd.poll_task("task-never-completes", "fake-key")
        elapsed = fake.time() - started

        # HARD CAP surfaced as a terminal FAIL — the poll loop exited by the cap.
        assert "900" in str(exc.value)
        assert "never-completes" in str(exc.value)
        assert elapsed >= 900, f"raised before the cap: elapsed={elapsed}"
        assert elapsed < 900 + max(fake.sleeps or [0]) + 60, \
            f"loop overshot the cap: elapsed={elapsed}"

    def test_ladder_is_10_20_40(self, monkeypatch):
        """The poll backoff ladder is exactly 10s (first 2 min), 20s (next 3 min),
        40s after — per FIX-7."""
        fake = _FakeClock()
        monkeypatch.setattr(bd.time, "time", fake.time)
        monkeypatch.setattr(bd.time, "sleep", fake.sleep)
        monkeypatch.setattr(bd, "POLL_MAX_SECONDS", 900)
        monkeypatch.setattr(bd, "_http_json", _never_completing_http())

        with pytest.raises(bd.RenderPollTimeout):
            bd.poll_task("task-never-completes", "fake-key")

        # Every sleep must be one of the ladder values, in the right order:
        # 10s while elapsed < 120, 20s while < 120+180=300, 40s after.
        seen = []
        for i, s in enumerate(fake.sleeps):
            assert s in (10, 20, 40), f"sleep {i} = {s} not in ladder 10/20/40"
            seen.append(s)
        assert 10 in seen and 20 in seen and 40 in seen, \
            f"ladder did not escalate across all three steps: {seen}"
        # The first 2 min are 10s polls (12 of them), then 20s for 3 min (9), then 40s.
        assert seen[:12] == [10] * 12, seen[:20]
        assert seen[12:21] == [20] * 9, seen[10:25]
        assert all(s == 40 for s in seen[21:]), seen

    def test_completing_task_still_returns_url(self, monkeypatch):
        """Known-good control: a render that completes still returns resultUrls[0] —
        the cap must not break the healthy path."""
        fake = _FakeClock()
        monkeypatch.setattr(bd.time, "time", fake.time)
        monkeypatch.setattr(bd.time, "sleep", fake.sleep)
        monkeypatch.setattr(bd, "POLL_MAX_SECONDS", 900)
        monkeypatch.setattr(bd, "_http_json", _success_http(after=3))

        url = bd.poll_task("task-healthy", "fake-key")
        assert url == "https://cdn.example/x.png"


# ---------------------------------------------------------------------------
# Test 2: real-time — the loop terminates on the wall clock at the compressed cap
# ---------------------------------------------------------------------------
class TestPollCapRealTime:
    def test_never_completing_task_exits_fail_on_wall_clock(self, monkeypatch):
        """REAL-TIME timed test: with the cap compressed to its 30s env floor, a
        never-completing task must raise RenderPollTimeout in roughly that window —
        it must TERMINATE, never hang. Evidence: elapsed wall time recorded here."""
        monkeypatch.setattr(bd, "POLL_MAX_SECONDS", 30)
        monkeypatch.setattr(bd, "_http_json", _never_completing_http())

        started = time.time()
        with pytest.raises(bd.RenderPollTimeout):
            bd.poll_task("task-never-completes-live", "fake-key")
        elapsed = time.time() - started

        # Hard cap surfaced FAIL. Allow one extra ladder interval (40s) of slack for
        # scheduler jitter, but NEVER allow a hang: well under the 15-min production cap.
        assert elapsed >= 30, f"FAIL surfaced before the cap: {elapsed:.1f}s"
        assert elapsed < 90, f"poll loop overshot the cap: {elapsed:.1f}s — would hang in production"
