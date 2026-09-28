"""Fix 10 — Kie.ai spend ceilings are fail-open (fail-closed now).

THE DEFECT
`governor.acquire` raised `GovernorTimeout("daily_cap … reached")` when the
kie daily cap was exhausted, but `build_deck._gov_acquire` and
`kie_tasks._gov_acquire` caught EVERY exception, printed "proceeding
unthrottled", and the paid `createTask` POST ran anyway.

THE FIX
`governor` now raises `GovernorDailyCapReached` (a `GovernorTimeout`
subclass) at the daily-cap check. Both `_gov_acquire` functions re-raise it,
and also re-raise a submit-side (`poll=False`) rate timeout. Fail-soft
remains ONLY for "governor module absent". The phase parks instead of
spending: the paid call is never made.

THE TEST (per the fix order): `daily_cap=1`, one acquire, then submit with
`_http_json` mocked. The mock is never called. Plus the two companion
behaviours the fix mandates: `kie_tasks._gov_acquire` re-raises the cap, and
a submit-side rate timeout re-raises (poll-side stays fail-soft).

STATE REDIRECTION: the governor store / resource-profile dirs and the
governor log are pointed at tmp_path, so nothing here can reach the live
state. Flat file inside tests/, manages its own import path — matching every
sibling here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import governor  # noqa: E402


@pytest.fixture
def gov_env(tmp_path, monkeypatch):
    """Isolated governor state + log. No network, no spend, no real provider."""
    monkeypatch.setenv("PRESENTATION_RESOURCE_PROFILE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("PRESENTATION_CAPACITY_CONFIG_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    governor.set_log_path(str(tmp_path / "governor_log.jsonl"))
    with governor._lock:
        governor._state.clear()
    # the shared store is a per-process singleton bound to the FIRST test's
    # tmp_path; drop it so this test's day_count=1 does not leak into the next
    monkeypatch.setattr(governor._gstore, "_STORE", None)
    # daily_cap=1, generous rate bucket so only the cap can bite
    monkeypatch.setattr(
        governor,
        "provider_config",
        lambda _p: {
            "rps": 1000.0,
            "burst": 100,
            "max_inflight": 100,
            "daily_cap": 1,
            "poll_counts_toward_rps": True,
        },
    )
    yield tmp_path


def _consume_the_cap():
    lease = governor.acquire("kie", n=1, timeout_s=5)
    assert lease is not None
    governor.release(lease)


def test_daily_cap_parks_before_spend(gov_env, monkeypatch):
    """The fix order's MUST scenario: daily_cap=1, one acquire, then submit
    with _http_json mocked — the mock is never called."""
    import build_deck as bd

    assert bd._governor is governor  # the real module is wired, not absent
    _consume_the_cap()

    # _gov_acquire must re-raise the cap, not fail-soft to None
    with pytest.raises(governor.GovernorDailyCapReached):
        bd._gov_acquire(poll=False)

    # submit_task must park BEFORE the paid createTask POST
    calls = []
    monkeypatch.setattr(bd, "_http_json", lambda *a, **k: calls.append((a, k)))
    with pytest.raises(governor.GovernorDailyCapReached):
        bd.submit_task("a test slide prompt", "fake-key")
    assert calls == [], "paid createTask POST was attempted after the daily cap"


def test_kie_tasks_gov_acquire_reraises_daily_cap(gov_env):
    """The second _gov_acquire re-raises the cap too."""
    import kie_tasks

    _consume_the_cap()
    with pytest.raises(governor.GovernorDailyCapReached):
        kie_tasks._gov_acquire(governor, True, poll=False)


def test_submit_side_rate_timeout_reraises_poll_stays_soft(gov_env, monkeypatch):
    """A submit-side (poll=False) rate timeout re-raises; poll-side stays
    fail-soft, and unrelated errors stay fail-soft."""
    import build_deck as bd

    def boom(*a, **k):
        raise governor.GovernorTimeout("timed out")

    monkeypatch.setattr(governor, "acquire", boom)
    with pytest.raises(governor.GovernorTimeout):
        bd._gov_acquire(poll=False)
    assert bd._gov_acquire(poll=True) is None

    def other_boom(*a, **k):
        raise RuntimeError("wedged bucket")

    monkeypatch.setattr(governor, "acquire", other_boom)
    assert bd._gov_acquire(poll=False) is None
