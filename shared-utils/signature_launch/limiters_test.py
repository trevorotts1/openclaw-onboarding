#!/usr/bin/env python3
"""Self-check for shared-utils/signature_launch/limiters.py.

Runnable with no framework and no network:
    python3 shared-utils/signature_launch/limiters_test.py

Also collects cleanly under pytest if that is the caller's habit.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import limiters as L  # noqa: E402


class FakeClock:
    """Instant sleep, deterministic now()."""

    def __init__(self, start=1000.0):
        self.t = float(start)

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += max(0.0, float(seconds))


def _tmpdir():
    return Path(tempfile.mkdtemp(prefix="limiters-test-"))


def test_kie_limiter_20_per_10s_and_persistence():
    d = _tmpdir()
    clock = FakeClock()
    path = d / "kie.json"
    kie = L.KieLimiter(path, clock=clock)
    for _ in range(20):
        assert kie.try_acquire() is True
    assert kie.try_acquire() is False, "21st start in the window must be refused"

    waited = kie.acquire()
    assert waited > 0 and abs(waited - 10.0) < 0.06, waited
    assert kie.try_acquire() is True

    # A second instance shares the same persisted budget.
    time_after = clock.now()
    fresh = L.KieLimiter(path, clock=clock)
    assert time_after >= 1010.0
    assert len(fresh._grants()) >= 1


def test_kie_limiter_timeout_and_corrupt_state():
    d = _tmpdir()
    clock = FakeClock()
    path = d / "kie.json"
    kie = L.KieLimiter(path, clock=clock)
    for _ in range(20):
        kie.try_acquire()
    try:
        kie.acquire(timeout_s=3.0)
    except TimeoutError:
        pass
    else:
        raise AssertionError("acquire must honor timeout_s")

    path.write_text("{not json", encoding="utf-8")
    try:
        fresh = L.KieLimiter(path, clock=clock)
        fresh.try_acquire()
    except L.LimiterStateError:
        pass
    else:
        raise AssertionError("corrupt state must fail closed")


def test_spend_cap_reserve_commit_release_and_unknown_price():
    d = _tmpdir()
    clock = FakeClock()
    cap = L.SpendCap(d / "spend.json", ceiling_minor=1000, clock=clock)

    cap.reserve("a", 600)
    cap.reserve("b", 300)
    assert cap.remaining_minor() == 100
    try:
        cap.reserve("c", 200)
    except L.SpendCapExceeded:
        pass
    else:
        raise AssertionError("over-cap reservation must be refused")

    cap.release("b")
    assert cap.remaining_minor() == 400
    cap.reserve("c", 200)
    cap.commit("c", 150)
    assert cap.snapshot()["spent_minor"] == 150
    assert cap.remaining_minor() == 1000 - 600 - 150

    try:
        cap.reserve("d", None)
    except L.UnknownPrice:
        pass
    else:
        raise AssertionError("unknown price must block")

    try:
        L.SpendCap(d / "spend.json", ceiling_minor=2000, clock=clock)
    except L.LimiterStateError:
        pass
    else:
        raise AssertionError("a different ceiling must not silently reuse state")


def test_spend_cap_double_reserve_and_corrupt_state():
    d = _tmpdir()
    cap = L.SpendCap(d / "spend.json", ceiling_minor=100)
    cap.reserve("a", 10)
    try:
        cap.reserve("a", 10)
    except L.LimiterStateError:
        pass
    else:
        raise AssertionError("double reserve must be refused")

    (d / "spend.json").write_text("[]", encoding="utf-8")
    try:
        cap.snapshot()
    except L.LimiterStateError:
        pass
    else:
        raise AssertionError("corrupt spend state must fail closed")


def test_ghl_throttle_spacing_rate_and_429():
    d = _tmpdir()
    clock = FakeClock()
    ghl = L.GhlBuildThrottle(d / "ghl.json", clock=clock)

    assert ghl.before("save") == 0.0
    waited = ghl.before("save")
    assert waited == 6.0, waited

    assert ghl.before("publish") == 0.0
    waited = ghl.before("publish")
    assert waited == 15.0, waited

    # 100 requests/minute, save/publish calls included.
    ghl2 = L.GhlBuildThrottle(d / "ghl2.json", clock=clock)
    for _ in range(100):
        ghl2.before()
    waited = ghl2.before()
    assert waited == 60.0, waited

    ghl3 = L.GhlBuildThrottle(d / "ghl3.json", clock=clock)
    assert ghl3.note_429("45") == 45.0
    waited = ghl3.before()
    assert waited == 45.0, waited
    assert L.GhlBuildThrottle(d / "ghl3.json", clock=clock).available_in() == 0.0


def test_model_concurrency_resolution():
    d = _tmpdir()
    cfg = d / "config"
    cfg.write_text(json.dumps({
        "agents": {"defaults": {"subagents": {"maxConcurrent": 8},
                               "maxConcurrent": 12}}}), encoding="utf-8")

    got = L.model_concurrency(str(cfg), provider="ollama-cloud", ollama_plan=20)
    assert got["runtime_cap"] == 7, got
    assert got["provider_cap"] == 3, got
    assert got["agents"] == 3, got

    got = L.model_concurrency(str(cfg), provider="openrouter")
    assert got["provider_cap"] is None and got["agents"] == 7, got

    got = L.model_concurrency(str(cfg), provider="some-other-provider")
    assert got["provider_cap"] == L.UNKNOWN_PROVIDER_QUOTA_DEFAULT, got

    prof = d / "profile"
    prof.mkdir()
    (prof / ".capacity-profile.json").write_text(
        json.dumps({"maxConcurrentAgents": 4}), encoding="utf-8")
    got = L.model_concurrency(str(cfg), profile_dir=str(prof))
    assert got["runtime_cap"] == 3, got
    assert got["agents"] == 3, got

    got = L.model_concurrency()
    assert got["agents"] is None, got


def test_model_concurrency_gate_slots_and_stale_lease():
    d = _tmpdir()
    clock = FakeClock()
    gate = L.ModelConcurrencyGate(d / "slots.json", limit=2, lease_ttl_s=60, clock=clock)
    assert gate.try_acquire("w1") is True
    assert gate.try_acquire("w2") is True
    assert gate.try_acquire("w3") is False
    assert gate.active() == ["w1", "w2"]
    gate.release("w1")
    assert gate.try_acquire("w3") is True

    clock.sleep(61)
    assert gate.active() == [], "expired leases must be pruned"
    assert gate.try_acquire("w4") is True


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"ok {test.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
