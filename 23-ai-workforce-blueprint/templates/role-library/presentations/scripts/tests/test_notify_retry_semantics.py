"""Regression tests for the notify retry semantics fix (report.flush_undeliverable).

TWO PRIOR ATTEMPTS at this exact problem failed, for two different reasons --
these tests exist specifically to keep both closed:

  1. A terminal attempt cap: an outage that outlasted the cap, then recovered,
     lost the alert permanently. Test: TestOutageRecoversForAnyLength (proves
     delivery for N = 1..8 and N = 20 -- there is no N at which this stops
     working, because there is no cap).

  2. A recoverable park behind a --drain-parked-style flag: recovery needed a
     human to type it, and putting that flag on a cron line defeated the
     poisoned/transport split (recreated unbounded retry). Tests:
     TestNoHumanActionRequired (delivery happens with ZERO calls to
     cmd_sweep_undeliverable -- proven with a raising guard, not a text
     search) and TestCronCannotDefeatBackoffOrUnpark (a tight loop of the
     REAL cmd_sweep_undeliverable makes at most one transport attempt and
     never touches an already-parked message).

See report.py's module-level docstring (above POISON_CONFIRM_THRESHOLD) for
the epistemics: a non-zero exit is NOT, by itself, evidence of poisoning --
only a message that keeps failing AFTER the transport is independently
proven up (another message got through) counts as poisoning evidence.
Everything else retries forever on capped backoff. Nothing is ever silently
discarded.
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.state import StateStore, utcnow
from presentation_job.report import (
    Reporter, flush_undeliverable, _backoff_seconds, POISON_CONFIRM_THRESHOLD,
    RETRY_BACKOFF_CAP_SECONDS,
)
from presentation_job import __main__ as pj_main


def _mkstate(tmp_path, chat_id="tc"):
    rd = tmp_path / "r"
    rd.mkdir()
    store = StateStore(rd)
    s = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00", "manifest_path": "/x.json",
        "manifest_version": 25, "manifest_sha256": "0" * 64,
        "presentation_type": "from_scratch", "requester": {"chat_id": chat_id},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "parked": [], "heartbeat": {}, "terminal": None,
    }
    return s, store, rd


def _stub(tmp_path, name, fail_first_n):
    """A tiny counting transport: fails for its first `fail_first_n` calls
    (across the WHOLE test, not per-message -- exactly what an outage of
    length N looks like), then succeeds forever after."""
    counter = tmp_path / f"{name}.count"
    script = tmp_path / f"{name}.py"
    script.write_text(
        "import sys\n"
        f"cf = {str(counter)!r}\n"
        "try:\n"
        "    n = int(open(cf).read().strip() or '0')\n"
        "except FileNotFoundError:\n"
        "    n = 0\n"
        "n += 1\n"
        "open(cf, 'w').write(str(n))\n"
        f"sys.exit(0 if n > {fail_first_n} else 1)\n"
    )
    return f"{sys.executable} {script}"


def _rewind(state):
    """Test-only clock fast-forward -- sets every queued entry due NOW,
    substituting for waiting real backoff minutes. Not a recovery action."""
    for m in state.get("undeliverable", []):
        m["next_attempt_at"] = "2000-01-01T00:00:00+00:00"


class TestOutageRecoversForAnyLength:
    """The first failed attempt's exact regression: a terminal cap lost an
    alert a longer-but-finite outage would otherwise have delivered. There
    must be no N at which this stops working."""

    @pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6, 7, 8, 20])
    def test_delivers_after_n_failures_no_flag(self, tmp_path, monkeypatch, n):
        s, st, rd = _mkstate(tmp_path)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", _stub(tmp_path, f"n{n}", n))
        r = Reporter(s, st)
        r.to_requester("blocked", f"alert n={n}", phase_id="P", reason="outage")

        delivered = isinstance(s.get("sent", {}).get("blocked"), dict)
        rounds = 0
        while not delivered and rounds < n + 5:
            rounds += 1
            _rewind(s)
            flush_undeliverable(s, st)
            delivered = isinstance(s.get("sent", {}).get("blocked"), dict) and not s["undeliverable"]

        assert delivered, f"n={n}: never delivered; state={s}"
        assert s["undeliverable"] == [], f"n={n}: a message was left behind, not delivered or parked"
        assert s.get("parked") == [], f"n={n}: a plain transient failure must never be misclassified as poisoned"


class TestNoHumanActionRequired:
    """The second failed attempt's exact regression: recovery needed a human
    to type --sweep-undeliverable. Proven with a raising guard -- if anything
    below calls it, the test fails loudly, not by inspecting source text."""

    def test_recovery_via_to_requester_alone(self, tmp_path, monkeypatch):
        s, st, rd = _mkstate(tmp_path)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", _stub(tmp_path, "auto", 3))
        real = pj_main.cmd_sweep_undeliverable

        def _boom(*a, **kw):
            raise AssertionError("cmd_sweep_undeliverable must never be needed for recovery")
        monkeypatch.setattr(pj_main, "cmd_sweep_undeliverable", _boom)
        try:
            r = Reporter(s, st)
            r.to_requester("blocked", "no-human-needed", phase_id="P", reason="outage")
            for _ in range(6):
                if isinstance(s.get("sent", {}).get("blocked"), dict):
                    break
                _rewind(s)
                # Every ordinary progress ping ALSO drains the backlog --
                # this is the actual production trigger, not a special call.
                r.to_requester("progress", "ordinary activity")
        finally:
            monkeypatch.setattr(pj_main, "cmd_sweep_undeliverable", real)

        assert isinstance(s.get("sent", {}).get("blocked"), dict)
        assert s["undeliverable"] == []

    def test_cmd_status_opportunistically_drains_a_terminal_job(self, tmp_path, monkeypatch):
        """A job that already finished (or parked) with a stuck alert heals
        the next time ANYONE runs the ordinary, pre-existing --status
        command -- not a special recovery flag."""
        s, st, rd = _mkstate(tmp_path)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", _stub(tmp_path, "status", 1))
        r = Reporter(s, st)
        r.to_requester("done", "job finished, but the DONE alert failed once")
        assert len(s["undeliverable"]) == 1
        _rewind(s)
        st.save(s)

        class A:
            run_dir = rd
            json = False
        rc = pj_main.cmd_status(A())
        assert rc == 0
        s2 = st.load()
        assert isinstance(s2.get("sent", {}).get("done"), dict)
        assert s2["undeliverable"] == []


class TestCronCannotDefeatBackoffOrUnpark:
    """The second failed attempt's OTHER half: 'putting the flag in a cron
    line recreated unbounded retry.' A tight loop of the REAL
    cmd_sweep_undeliverable (no clock advance between calls) must make at
    most one transport attempt, and must never touch an already-parked
    message -- because it shares flush_undeliverable with every automatic
    caller and flush_undeliverable never reads state['parked']."""

    def test_hammering_the_flag_does_not_hot_loop_or_unpark(self, tmp_path, monkeypatch):
        s, st, rd = _mkstate(tmp_path)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", _stub(tmp_path, "hammer", 10**6))
        r = Reporter(s, st)
        r.to_requester("progress", "stuck behind backoff")
        s.setdefault("parked", []).append({
            "at": utcnow(), "kind": "blocked", "message": "already poisoned",
            "chat_id": "tc", "attempts": 9, "confirmed_up_failures": POISON_CONFIRM_THRESHOLD,
            "parked_at": utcnow(), "parked_reason": "pre-seeded",
        })
        st.save(s)

        class A:
            run_dir = rd
        for _ in range(20):
            pj_main.cmd_sweep_undeliverable(A())

        counter = tmp_path / "hammer.count"
        calls = int(counter.read_text().strip()) if counter.is_file() else 0
        final = st.load()
        assert calls <= 1, f"backoff defeated by cron-style hammering: {calls} transport attempts"
        assert len(final.get("parked", [])) == 1
        assert final["parked"][0]["message"] == "already poisoned"
        assert all(m.get("message") != "already poisoned" for m in final.get("undeliverable", []))


class TestNoHotLoop:
    def test_immediate_reflush_makes_no_extra_attempt(self, tmp_path, monkeypatch):
        s, st, rd = _mkstate(tmp_path)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", _stub(tmp_path, "hot", 10**6))
        r = Reporter(s, st)
        r.to_requester("progress", "never delivers")
        before = s["undeliverable"][0]["attempts"]
        flush_undeliverable(s, st)  # due-check must skip: not due yet
        after = s["undeliverable"][0]["attempts"]
        assert before == after

    def test_backoff_grows_then_caps(self):
        vals = [_backoff_seconds(a) for a in range(1, 12)]
        assert vals[-1] == RETRY_BACKOFF_CAP_SECONDS
        assert all(v <= RETRY_BACKOFF_CAP_SECONDS for v in vals)
        assert vals[0] < vals[3] < RETRY_BACKOFF_CAP_SECONDS


class TestPoisonedMessageParks:
    """A deterministically-poisoned message (same content fails identically
    regardless of transport health) stops retrying and stays visible with
    content preserved -- never silently discarded."""

    def test_poison_parks_stays_visible_never_discarded(self, tmp_path, monkeypatch):
        s, st, rd = _mkstate(tmp_path)
        marker = "POISON-XYZ"
        script = tmp_path / "poison.py"
        log = tmp_path / "poison.log"
        script.write_text(
            "import sys, json\n"
            f"log = {str(log)!r}\n"
            "raw = sys.stdin.read()\n"
            "try:\n"
            "    msg = json.loads(raw).get('message','')\n"
            "except Exception:\n"
            "    msg = ''\n"
            "open(log, 'a').write(msg + chr(10))\n"
            f"sys.exit(1 if {marker!r} in msg else 0)\n"
        )
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", f"{sys.executable} {script}")

        r = Reporter(s, st)
        poison_text = f"deck build failed: {marker}"
        r.to_requester("blocked", poison_text, phase_id="P", reason="bad-content")
        assert len(s["undeliverable"]) == 1

        for i in range(POISON_CONFIRM_THRESHOLD + 2):
            r.to_requester("progress", f"unrelated healthy ping {i}")
            _rewind(s)
            flush_undeliverable(s, st)

        assert len(s.get("parked", [])) == 1, f"never parked: {s}"
        assert s["parked"][0]["message"] == poison_text, "content must be preserved verbatim"
        assert all(m.get("message") != poison_text for m in s["undeliverable"])

        calls_before = log.read_text().count(marker) if log.is_file() else 0
        for i in range(6):
            r.to_requester("progress", f"more pings {i}")
            _rewind(s)
            flush_undeliverable(s, st)
        calls_after = log.read_text().count(marker) if log.is_file() else 0
        assert calls_after == calls_before, "a parked message must never be re-dispatched"

    def test_plain_transport_outage_never_misclassified_as_poison(self, tmp_path, monkeypatch):
        """Control for the poison test above: everyone failing (no sibling
        ever succeeds) must NOT accumulate poisoning evidence, however many
        retries happen -- see result.py's transport rule."""
        s, st, rd = _mkstate(tmp_path)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", _stub(tmp_path, "alldown", 10**6))
        r = Reporter(s, st)
        r.to_requester("blocked", "nobody can get through", phase_id="P", reason="down")
        for _ in range(POISON_CONFIRM_THRESHOLD + 5):
            _rewind(s)
            flush_undeliverable(s, st)
        assert s.get("parked", []) == [], "pure transport-down must never be parked -- retry forever"
        assert len(s["undeliverable"]) == 1
