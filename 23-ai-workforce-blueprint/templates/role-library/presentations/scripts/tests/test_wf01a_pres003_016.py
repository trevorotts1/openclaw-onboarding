"""WF01-A -- PRES-003 fail-closed admission + PRES-016 adaptive recovery.

PRES-003 (fail-closed admission, dispatcher.py _govern_acquire/_govern_release):
  * budget cap / acquire timeout / broken governor config / missing governor
    module -> the transport is NEVER invoked; the refusal is typed and visible
    (GOVERNOR-BLOCKED / GOVERNOR-RETRY) instead of a silent fail-open.
  * explicitly classified local units (local CPU / file / image inspection)
    bypass the provider gate by allowlist, nothing else does.
  * one logical HTTP request holds exactly one lease, even when the outer
    admission and the transport's per-attempt admission nest.

PRES-016 (adaptive recovery, governor.py report_429/report_ok/provider_config):
  * a 429 followed by an ALREADY-IN-FLIGHT success keeps the penalty.
  * a full healthy observation window allows only GRADUAL (additive) increase.
  * mixed 200/429 traffic never bounces to full speed after each success.
  * a failing provider must not stop an unrelated provider.
  * circuit state persists across jobs (processes) with revision CAS; a
    same-provider stale-revision write is rejected VISIBLY (governor log).
  * the concurrency ceiling never lifts the start-rate window: burst stays the
    providers.yaml row, max_inflight follows the profile ceiling (PRES-016
    supersedes the U5 admission-window lift; v25.0.17/.20 ceilings, provider
    normalization and the ollama Max 8 + 2 reserve are preserved).

STATE REDIRECTION: every test redirects the resource-profile store, the
capacity config dir and the governor log into tmp_path. No network, no real
provider, no secrets (the DeepSeek key stub is the literal "wf01a-not-a-key").
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import dispatcher  # noqa: E402
from presentation_job import governor  # noqa: E402


# ---------------------------------------------------------------------------
# isolation fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def gov_env(tmp_path, monkeypatch):
    """Isolated governor state + log + circuit store. No network, no engine,
    no real provider, no real profile store."""
    monkeypatch.setenv("PRESENTATION_RESOURCE_PROFILE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("PRESENTATION_CAPACITY_CONFIG_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    saved_log = governor.log_path()
    governor.set_log_path(str(tmp_path / "governor_log.jsonl"))
    with governor._lock:
        governor._state.clear()
    with dispatcher._GOVERN_DEPTH_LOCK:
        dispatcher._GOVERN_DEPTH.clear()
        dispatcher._GOVERN_ACTIVE.clear()
    _reset_circuit(governor)
    try:
        yield tmp_path
    finally:
        governor.set_log_path(saved_log)
        with governor._lock:
            governor._state.clear()
        with dispatcher._GOVERN_DEPTH_LOCK:
            dispatcher._GOVERN_DEPTH.clear()
            dispatcher._GOVERN_ACTIVE.clear()
        _reset_circuit(governor)


def _reset_circuit(g):
    for name in ("_circuit_cache", "_circuit_loaded_at"):
        if hasattr(g, name):
            if name == "_circuit_loaded_at":
                setattr(g, name, 0.0)
            else:
                setattr(g, name, {})
    if hasattr(g, "_circuit_lock"):
        with g._circuit_lock:
            g.__dict__.setdefault("_circuit_cache", {})


@pytest.fixture
def no_transport(monkeypatch):
    """Count every outbound HTTP attempt. A fail-open admission would call it;
    fail-closed admission must leave it at zero."""
    calls = {"n": 0}

    def _boom(*a, **k):  # pragma: no cover - must never run
        calls["n"] += 1
        raise AssertionError("TRANSPORT CALLED after admission refusal")

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    return calls


@pytest.fixture
def ds_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "wf01a-not-a-key")


# ---------------------------------------------------------------------------
# PRES-003: refusal classes -> zero transport calls
# ---------------------------------------------------------------------------

def _cap_config(**over):
    cfg = dict(governor._DEFAULTS)
    cfg.update({"rps": 100.0, "burst": 100, "max_inflight": 100, "daily_cap": 0})
    cfg.update(over)
    return cfg


def test_budget_cap_refusal_blocks_transport(gov_env, monkeypatch, no_transport, ds_key):
    """Daily cap exhausted -> acquire raises -> admission is a typed refusal,
    deepseek_complete raises GOVERNOR-* with ZERO outbound calls."""
    monkeypatch.setattr(governor, "provider_config",
                        lambda p: _cap_config(daily_cap=1))
    held = governor.acquire("deepseek-direct", timeout_s=1.0)  # consume the cap
    with pytest.raises(governor.GovernorTimeout):
        governor.acquire("deepseek-direct", timeout_s=0.01)
    governor.release(held)
    with pytest.raises(Exception) as exc:
        dispatcher.deepseek_complete("s", "u")
    text = str(exc.value)
    assert "GOVERNOR-" in text, text
    assert "not attempted" in text.lower() or "no outbound" in text.lower(), text
    assert no_transport["n"] == 0


def test_acquire_timeout_refusal_blocks_transport(gov_env, monkeypatch, no_transport, ds_key):
    """Acquire timeout (no tokens, tiny window) -> typed retry refusal,
    zero transport calls."""
    # drain the bucket under a generous config, then starve it
    monkeypatch.setattr(governor, "provider_config",
                        lambda p: _cap_config(rps=1000.0, burst=10))
    held = governor.acquire("deepseek-direct", timeout_s=1.0)
    governor.release(held)

    def _starved(p):
        return _cap_config(rps=0.001, burst=0, max_inflight=100)

    monkeypatch.setattr(governor, "provider_config", _starved)
    with pytest.raises(governor.GovernorTimeout):
        governor.acquire("deepseek-direct", timeout_s=0.01)
    # inject a short admission timeout so the proof does not spend the real
    # 120 s ceiling; the refusal semantics are identical either way
    monkeypatch.setattr(dispatcher, "_GOVERN_ACQUIRE_TIMEOUT_S", 0.05)
    with pytest.raises(Exception) as exc:
        dispatcher.deepseek_complete("s", "u")
    assert "GOVERNOR-" in str(exc.value)
    assert no_transport["n"] == 0


def test_broken_governor_config_refusal_blocks_transport(gov_env, monkeypatch, no_transport, ds_key):
    """Governor raising an unexpected error (broken config/store) -> typed
    retry refusal, zero transport calls."""
    def _broken(provider):
        raise RuntimeError("providers.yaml unreadable")
    monkeypatch.setattr(governor, "provider_config", _broken)
    with pytest.raises(Exception) as exc:
        dispatcher.deepseek_complete("s", "u")
    text = str(exc.value)
    assert "GOVERNOR-" in text
    assert "providers.yaml unreadable" in text
    assert no_transport["n"] == 0


def test_missing_governor_blocks_transport(gov_env, monkeypatch, no_transport, ds_key):
    """Missing governor module -> PERMANENT blocked refusal naming the
    remediation, zero transport calls."""
    monkeypatch.setattr(dispatcher, "_governor", None)
    adm = dispatcher._govern_admit("deepseek-direct")
    assert adm is not None and not adm.admitted and adm.blocked
    assert "governor" in adm.reason.lower()
    with pytest.raises(Exception) as exc:
        dispatcher.deepseek_complete("s", "u")
    assert "GOVERNOR-BLOCKED" in str(exc.value)
    assert no_transport["n"] == 0


def test_missing_governor_blocks_dispatch_complete_end_to_end(gov_env, monkeypatch, no_transport, ds_key):
    """dispatch_complete (router absent -> default provider) refuses BEFORE any
    transport work when the governor module is missing."""
    monkeypatch.setattr(dispatcher, "_model_router", None)
    monkeypatch.setattr(dispatcher, "_governor", None)
    with pytest.raises(Exception) as exc:
        dispatcher.dispatch_complete("s", "u", phase_id="P-TEST")
    assert "GOVERNOR-BLOCKED" in str(exc.value)
    assert no_transport["n"] == 0


def test_admitted_path_invokes_transport(gov_env, monkeypatch, ds_key):
    """POSITIVE control: with the governor healthy, the transport IS reached
    (proving the refusals above are not dead stubs gating everything)."""
    monkeypatch.setattr(governor, "provider_config",
                        lambda p: _cap_config(rps=1000.0, burst=1000, max_inflight=100))
    import urllib.request
    seen = {"n": 0}

    def _ok(req, timeout=None, **k):
        seen["n"] += 1
        raise AssertionError("stop at the transport boundary (success expected "
                             "to reach it; the stub response is out of scope)")

    monkeypatch.setattr(urllib.request, "urlopen", _ok)
    with pytest.raises(AssertionError, match="transport boundary"):
        dispatcher.deepseek_complete("s", "u")
    assert seen["n"] == 1  # exactly one attempt reached the wire boundary


def test_local_bypass_allowlist(gov_env):
    """Only explicitly classified local tokens bypass the provider gate, and
    they consume NO governor bucket."""
    for token in ("local-image-inspection", "local-file", "local-cpu"):
        adm = dispatcher._govern_admit(token)
        assert adm.admitted, token
        assert adm.lease is None
        assert "local" in adm.reason.lower()
    assert "deepseek-direct" not in governor._state
    # a NON-allowlisted provider still gates
    adm = dispatcher._govern_admit("kie")
    assert adm.admitted  # healthy governor admits it
    assert "kie" in governor._state


def test_reentrant_nested_admission_takes_one_real_lease(gov_env, monkeypatch):
    """Outer admission + nested per-attempt admission on one thread take
    exactly ONE real governor acquire (one logical request, one lease)."""
    monkeypatch.setattr(governor, "provider_config",
                        lambda p: _cap_config())
    real = {"n": 0}
    orig = governor.acquire

    def _counting(provider, **k):
        real["n"] += 1
        return orig(provider, **k)

    monkeypatch.setattr(governor, "acquire", _counting)
    outer = dispatcher._govern_admit("deepseek-direct")
    assert outer.admitted and outer.lease is not None
    inner = dispatcher._govern_admit("deepseek-direct")
    assert inner.admitted
    assert real["n"] == 1, "nested admission must reuse the outer lease"
    assert inner.lease is outer.lease
    dispatcher._govern_release("deepseek-direct", inner.lease)
    dispatcher._govern_release("deepseek-direct", outer.lease)


def test_failed_outer_admission_does_not_leak_a_dead_lease(gov_env, monkeypatch, no_transport, ds_key):
    """Reentrant fix: an outer frame whose acquire FAILED must not be counted
    as depth -- the next admission re-attempts the governor instead of
    believing a lease exists."""
    def _boom(provider, **k):
        raise RuntimeError("governor wedged")
    monkeypatch.setattr(governor, "acquire", _boom)
    a1 = dispatcher._govern_admit("deepseek-direct")
    assert not a1.admitted
    a2 = dispatcher._govern_admit("deepseek-direct")
    assert not a2.admitted  # re-attempted (and failed again), no dead lease
    key = f"{threading.get_ident()}:deepseek-direct"
    with dispatcher._GOVERN_DEPTH_LOCK:
        assert dispatcher._GOVERN_DEPTH.get(key, 0) == 0
        assert key not in dispatcher._GOVERN_ACTIVE


# ---------------------------------------------------------------------------
# PRES-016: adaptive recovery
# ---------------------------------------------------------------------------

def test_429_then_stale_inflight_success_keeps_penalty(gov_env):
    """A success that arrives AFTER a 429 but began BEFORE it (already
    in-flight) must not erase the penalty."""
    scale = governor.report_429("kie")
    assert scale == 0.5
    governor.report_ok("kie")   # the stale in-flight success
    snap = governor.snapshot()["kie"]
    assert snap["rate_scale"] == 0.5, "stale success erased the penalty"
    assert snap["penalty_remaining_s"] > 0


def test_healthy_window_allows_gradual_additive_increase(gov_env):
    """A full healthy observation window with the minimum sample count raises
    the scale by ONE additive step -- never straight back to 1.0."""
    governor.report_429("kie")
    now = time.time()
    with governor._lock:
        st = governor._state_for("kie")
        st.penalty_started = now - (governor.HEALTHY_WINDOW_S + 5)
        st.ok_samples = [st.penalty_started + 1.0 + i
                         for i in range(governor.HEALTHY_MIN_SAMPLES)]
    governor.report_ok("kie")
    snap = governor.snapshot()["kie"]
    assert snap["rate_scale"] == pytest.approx(0.5 + governor.SCALE_STEP)
    assert snap["rate_scale"] < 1.0


def test_recovery_needs_min_samples_even_after_window(gov_env):
    """Time alone (window elapsed) is not recovery: below the minimum sample
    count the scale must not move."""
    governor.report_429("kie")
    now = time.time()
    with governor._lock:
        st = governor._state_for("kie")
        st.penalty_started = now - (governor.HEALTHY_WINDOW_S + 5)
        st.ok_samples = [now]  # one lonely sample
    governor.report_ok("kie")
    assert governor.snapshot()["kie"]["rate_scale"] == 0.5


def test_mixed_traffic_never_bounces_to_full_speed(gov_env):
    """Alternating 429/200 keeps the scale down; no single success restores it."""
    for _ in range(4):
        governor.report_429("kie")
        governor.report_ok("kie")
    snap = governor.snapshot()["kie"]
    assert snap["rate_scale"] < 1.0
    assert snap["rate_scale"] >= governor.SCALE_FLOOR


def test_repeat_429s_multiply_down_to_floor(gov_env):
    scales = [governor.report_429("kie")]
    for _ in range(6):
        scales.append(governor.report_429("kie"))
    assert scales[0] == 0.5
    assert all(b < a for a, b in zip(scales, scales[1:]) if b > governor.SCALE_FLOOR)
    assert scales[-1] == governor.SCALE_FLOOR


def test_failing_provider_does_not_stop_unrelated_provider(gov_env):
    governor.report_429("kie")
    governor.report_ok("openrouter")  # creates the unrelated provider's state
    assert governor.snapshot()["openrouter"]["rate_scale"] == 1.0
    assert governor.snapshot()["kie"]["rate_scale"] == 0.5


def test_retry_after_honored(gov_env):
    """An explicit Retry-After stretches (and is reported as) the penalty."""
    governor.report_429("kie", retry_after_s=300.0)
    snap = governor.snapshot()["kie"]
    assert 290.0 <= snap["penalty_remaining_s"] <= 300.0
    assert snap["retry_after_s"] == 300.0


def test_retry_after_is_capped(gov_env):
    governor.report_429("kie", retry_after_s=10 ** 9)
    snap = governor.snapshot()["kie"]
    assert snap["retry_after_s"] == governor.RETRY_AFTER_CAP_S


def test_burst_is_not_lifted_by_concurrency_ceiling(gov_env, tmp_path, monkeypatch):
    """PRES-016: a profile concurrency ceiling of 100 must NOT lift the
    start-rate window (burst stays the providers.yaml row); only max_inflight
    follows the ceiling."""
    profile = tmp_path / "state" / "resource_profile.json"
    profile.write_text(json.dumps({
        "providers": {"deepseek-direct": {
            "concurrency_ceiling": 100, "ceiling_source": "declared"}}}),
        encoding="utf-8")
    governor.reload_config()
    cfg = governor.provider_config("deepseek-direct")
    yaml_burst = int(governor._config_for("deepseek-direct").get("burst") or 0)
    assert cfg["max_inflight"] == 100
    assert cfg["burst"] == yaml_burst, (
        f"burst {cfg['burst']} was lifted by the concurrency ceiling; "
        "concurrency 100 must not fabricate a 100-per-window start rate")


def test_openrouter_concurrency_100_is_not_100_rps(gov_env, tmp_path):
    """The declared OpenRouter allocation (100 concurrent) must not fabricate
    permission for 100 requests per second: rps and burst stay the yaml row."""
    profile = tmp_path / "state" / "resource_profile.json"
    profile.write_text(json.dumps({
        "providers": {"openrouter": {
            "concurrency_ceiling": 100, "ceiling_source": "declared"}}}),
        encoding="utf-8")
    governor.reload_config()
    cfg = governor.provider_config("openrouter")
    yaml = governor._config_for("openrouter")
    assert cfg["max_inflight"] == 100
    assert cfg["rps"] == float(yaml["rps"])          # 10.0 -- unchanged
    assert cfg["burst"] == int(yaml["burst"])        # 100/10s window -- unchanged


def test_ollama_max8_reserve2_preserved(gov_env, tmp_path):
    """v25 operator ruling: $100/month Ollama takes 8 of 10 slots (2 reserve).
    PRES-016 removes only the burst lift -- the 8 must survive on the
    concurrency axis and the tier rate on the rate axis."""
    profile = tmp_path / "state" / "resource_profile.json"
    profile.write_text(json.dumps({
        "providers": {"ollama-cloud": {
            "plan_tier": "$100/month", "concurrency_ceiling": 8}}}),
        encoding="utf-8")
    governor.reload_config()
    cfg = governor.provider_config("ollama-cloud")
    assert cfg["max_inflight"] == 8
    assert cfg["rps"] == 8.0
    assert cfg["burst"] == int(governor._config_for("ollama")["burst"])


# ---------------------------------------------------------------------------
# PRES-016: persisted shared circuit state
# ---------------------------------------------------------------------------

def _circuit_doc(gov_env):
    path = Path(gov_env) / "state" / "governor_circuit.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def test_simultaneous_different_provider_writes_both_persist(gov_env):
    """Two writers for two providers: both entries survive in ONE document."""
    a = governor.report_429("kie")
    b = governor.report_429("openrouter")
    doc = _circuit_doc(gov_env)
    assert doc is not None, "circuit state was not persisted"
    assert doc["providers"]["kie"]["rate_scale"] == a
    assert doc["providers"]["openrouter"]["rate_scale"] == b
    assert doc["revision"] >= 2


def test_same_provider_stale_revision_rejected_visibly(gov_env):
    """A writer whose cached base revision is stale, carrying an OLDER event,
    must not clobber the newer entry -- and the rejection is visible in the
    governor log."""
    newer = time.time() + 1000.0
    path = Path(gov_env) / "state" / "governor_circuit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "revision": 7,
        "providers": {"kie": {"rate_scale": 0.25, "penalty_until": newer + 60,
                              "penalty_started": newer, "last_429_ts": newer,
                              "retry_after_s": 60.0, "updated_at": newer}},
        "updated_at": newer}), encoding="utf-8")
    _reset_circuit(governor)
    stale_base_doc = {"revision": 2, "providers": {}}
    ok = governor._persist_circuit({
        "kie": {"rate_scale": 0.5, "penalty_until": time.time() + 60,
                "penalty_started": time.time(), "last_429_ts": time.time(),
                "retry_after_s": 60.0, "updated_at": time.time(),
                "base_revision": 2}})
    doc = _circuit_doc(gov_env)
    assert doc is not None
    assert doc["providers"]["kie"]["rate_scale"] == 0.25, (
        "a stale-revision writer clobbered a newer entry")
    log = (Path(gov_env) / "governor_log.jsonl").read_text(encoding="utf-8")
    assert "circuit-stale-revision" in log, "rejection was not visible"


def test_circuit_state_shared_across_processes(gov_env, monkeypatch):
    """Another process's persisted penalty is honored by THIS process's
    acquire path (scale + cooldown imported from the shared document)."""
    now = time.time()
    path = Path(gov_env) / "state" / "governor_circuit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "revision": 3,
        "providers": {"kie": {"rate_scale": 0.25, "penalty_until": now + 60,
                              "penalty_started": now - 5,
                              "last_429_ts": now - 5, "retry_after_s": 60.0,
                              "updated_at": now}},
        "updated_at": now}), encoding="utf-8")
    _reset_circuit(governor)
    with governor._lock:
        st = governor._state_for("kie")
        governor._sync_circuit_locked(st, "kie", now)
        assert st.rate_scale == 0.25
        assert st.rate_scale_until >= now + 55
    snap = governor.snapshot()["kie"]
    assert snap["rate_scale"] == 0.25
    assert snap["penalty_remaining_s"] > 0


def test_snapshot_exposes_circuit_fields(gov_env):
    governor.report_429("kie", retry_after_s=90.0)
    snap = governor.snapshot()["kie"]
    assert snap["penalty_remaining_s"] > 0
    assert snap["next_retry_at_epoch"] >= time.time() + 80
    assert snap["retry_after_s"] == 90.0