#!/usr/bin/env python3
"""test_u5_operator_reserve.py -- the operator's 2-slot reserve survives the
whole chain, instead of being spent by a whitelist.

Operator ruling, 2026-09-04 and restated verbatim 2026-09-07: "ollama 20
dollar plan is 3 agents max ollama 100 a month plan is 8", "i said 8 so that
2 are left over for other work".  The Ollama $100 seat really allows 10; the
job is allowed 8 of them so the client keeps 2 for whatever else runs on the
same account.

capacity.CAP_TABLE recorded that correctly.  resource_profile.record_plan
copies CAP_TABLE straight into the profile as `concurrency_ceiling`.  But
governor._plan_tier_inflight then filtered the recorded ceiling through
`float(ceiling) in (3.0, 10.0)` -- so the reserved **8 was discarded**, the
function fell through to PLAN_TIER_RPS, and that map still said 10.  The
reserve was written, thrown away, and silently replaced with the raw account
maximum at the one place that sets the governor's in-flight cap.

Measured on pristine main before this fix: a profile carrying the cap table's
own value for (ollama-cloud, $100/month) produced governor max_inflight 10.

Three legs:
  1. CONSTANTS  -- the tier map and CAP_TABLE agree, and agree with the ruling.
  2. THE CHAIN  -- CAP_TABLE -> profile -> provider_config keeps the 8.
  3. NO WHITELIST -- an arbitrary recorded ceiling is honored as width, and is
     NOT smuggled in as a rate (a concurrency ceiling is not an rps).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import governor  # noqa: E402

OLLAMA = "ollama-cloud"


def _write_profile(tmp_path, monkeypatch, provider, **fields):
    """Point the governor at a throwaway profile store (never the live one)."""
    d = tmp_path / "profile"
    d.mkdir(exist_ok=True)
    monkeypatch.setenv(governor_profile_dir_env(), str(d))
    monkeypatch.delenv("PRESENTATION_RESOURCE_PROFILE", raising=False)
    (d / "resource_profile.json").write_text(json.dumps({
        ".schema_version": 1,
        "providers": {provider: dict(fields)},
    }), encoding="utf-8")
    _clear_config_cache()
    return d


def governor_profile_dir_env():
    from presentation_job import resource_profile
    return resource_profile.DIR_ENV


def _clear_config_cache():
    # provider_config memoizes providers.yaml by mtime, not the profile, but
    # reset anyway so ordering between tests can never matter.
    governor._config_cache = None
    governor._config_mtime = None


# ---------------------------------------------------------------------------
# 1. CONSTANTS
# ---------------------------------------------------------------------------

def test_cap_table_encodes_the_ruling():
    assert capacity.CAP_TABLE[(OLLAMA, capacity.PLAN_OLLAMA_20)] == 3
    assert capacity.CAP_TABLE[(OLLAMA, capacity.PLAN_OLLAMA_100)] == 8, (
        "the $100 Ollama tier is 8, not the raw account maximum of 10 -- "
        "the operator reserves 2 slots for other work")


def test_governor_tier_map_agrees_with_cap_table():
    """The governor's mirror must not drift from the source of truth again --
    the exact drift this test exists to catch (it said 10 while CAP_TABLE
    said 8, under a comment claiming they were 'the same numbers')."""
    assert governor.PLAN_TIER_RPS["$20/month"] == float(
        capacity.CAP_TABLE[(OLLAMA, capacity.PLAN_OLLAMA_20)])
    assert governor.PLAN_TIER_RPS["$100/month"] == float(
        capacity.CAP_TABLE[(OLLAMA, capacity.PLAN_OLLAMA_100)])
    assert 10.0 not in governor.PLAN_TIER_RPS.values(), (
        "10 is the raw seat maximum; admitting it anywhere in the tier map "
        "spends the operator's 2-slot reserve")


# ---------------------------------------------------------------------------
# 2. THE CHAIN -- cap table -> profile -> governor
# ---------------------------------------------------------------------------

def test_recorded_cap_table_ceiling_reaches_max_inflight(tmp_path, monkeypatch):
    """This is the leg that was broken: the profile carried 8 and the
    governor answered 10."""
    ceiling = capacity.CAP_TABLE[(OLLAMA, capacity.PLAN_OLLAMA_100)]
    _write_profile(tmp_path, monkeypatch, OLLAMA,
                   plan_tier=capacity.PLAN_OLLAMA_100,
                   plan_known=True,
                   concurrency_ceiling=ceiling,
                   ceiling_source="cap-table")
    cfg = governor.provider_config(OLLAMA)
    assert cfg["max_inflight"] == 8, (
        f"governor admitted {cfg['max_inflight']} in flight for a profile "
        f"recording {ceiling} -- the reserve was discarded")
    assert cfg["rps"] == 8.0


def test_twenty_dollar_tier_is_three(tmp_path, monkeypatch):
    _write_profile(tmp_path, monkeypatch, OLLAMA,
                   plan_tier=capacity.PLAN_OLLAMA_20,
                   plan_known=True,
                   concurrency_ceiling=capacity.CAP_TABLE[
                       (OLLAMA, capacity.PLAN_OLLAMA_20)],
                   ceiling_source="cap-table")
    cfg = governor.provider_config(OLLAMA)
    assert cfg["max_inflight"] == 3
    assert cfg["rps"] == 3.0


def test_tier_string_alone_still_yields_eight(tmp_path, monkeypatch):
    """No recorded ceiling at all -- the tier map is the only source, and it
    must not answer 10."""
    _write_profile(tmp_path, monkeypatch, OLLAMA,
                   plan_tier="$100/month", plan_known=True)
    cfg = governor.provider_config(OLLAMA)
    assert cfg["max_inflight"] == 8
    assert cfg["rps"] == 8.0


# ---------------------------------------------------------------------------
# 3. NO WHITELIST -- and no category error
# ---------------------------------------------------------------------------

def test_arbitrary_measured_ceiling_is_honored_as_width(tmp_path, monkeypatch):
    """The old guard only admitted 3 or 10, so a measured ceiling was thrown
    away. Any positive recorded ceiling is now the in-flight cap."""
    _write_profile(tmp_path, monkeypatch, OLLAMA,
                   concurrency_ceiling=47, ceiling_source="probe")
    assert governor.provider_config(OLLAMA)["max_inflight"] == 47


def test_ceiling_is_not_smuggled_in_as_a_rate(tmp_path, monkeypatch):
    """A concurrency ceiling is NOT a requests-per-second. DeepSeek's 2,500
    parallel slots must never become 2,500 rps -- that axis stays with
    providers.yaml."""
    baseline = governor.provider_config("deepseek-direct")["rps"]
    _write_profile(tmp_path, monkeypatch, "deepseek-direct",
                   concurrency_ceiling=2500, ceiling_source="probe")
    cfg = governor.provider_config("deepseek-direct")
    assert cfg["max_inflight"] == 2500, "width should follow the measurement"
    assert cfg["rps"] == baseline, (
        f"rps became {cfg['rps']} -- a concurrency ceiling was projected "
        "onto the rate axis")


def test_zero_and_bogus_ceilings_are_ignored(tmp_path, monkeypatch):
    for bad in (0, -5, True, "UNBOUNDED", None):
        _write_profile(tmp_path, monkeypatch, OLLAMA,
                       plan_tier="$100/month", plan_known=True,
                       concurrency_ceiling=bad)
        cfg = governor.provider_config(OLLAMA)
        assert cfg["max_inflight"] == 8, (
            f"ceiling {bad!r} produced max_inflight {cfg['max_inflight']}; "
            "a bogus ceiling must fall back to the tier, not to the seat max")


# ---------------------------------------------------------------------------
# 4. THE ADMISSION WINDOW -- a width the governor will not admit is not a width
# ---------------------------------------------------------------------------

def _admit(provider, want):
    """How many leases are granted with NO waiting? `burst` is enforced by
    acquire() as a hard rolling-10s admission ceiling, so this measures the
    real opening width of a fan-out wave."""
    held, n = [], 0
    try:
        for _ in range(want):
            held.append(governor.acquire(provider, timeout_s=0.001))
            n += 1
    except Exception:
        pass
    for lease in held:
        try:
            governor.release(lease)
        except Exception:
            pass
    return n


def test_burst_follows_the_ceiling_so_a_wave_can_actually_open(
        tmp_path, monkeypatch):
    """Measured on the operator box before this fix: deepseek-direct, profile
    ceiling 100, admitted 20 of a 100-wide ultra wave and queued the other 80
    behind a 10-second window. providers.yaml's burst was 20."""
    _write_profile(tmp_path, monkeypatch, "deepseek-direct",
                   concurrency_ceiling=100, ceiling_source="declared")
    cfg = governor.provider_config("deepseek-direct")
    assert cfg["max_inflight"] == 100
    assert cfg["burst"] >= 100, (
        f"burst {cfg['burst']} < ceiling 100: acquire() would admit only "
        f"{cfg['burst']} of a 100-wide wave per rolling 10s window")
    assert _admit("deepseek-direct", 100) == 100


def test_sustained_rate_is_not_touched(tmp_path, monkeypatch):
    """Only the opening window widens. rps is the sustained limiter and must
    stay exactly where providers.yaml put it -- widening a burst is not
    permission to hammer the account."""
    from presentation_job import governor as g
    yaml_rps = g._config_for("deepseek-direct").get("rps")
    _write_profile(tmp_path, monkeypatch, "deepseek-direct",
                   concurrency_ceiling=100, ceiling_source="declared")
    assert governor.provider_config("deepseek-direct")["rps"] == yaml_rps


def test_burst_only_ever_raises(tmp_path, monkeypatch):
    """A yaml row already wider than the ceiling keeps its own value."""
    from presentation_job import governor as g
    yaml_burst = int(g._config_for("deepseek-direct").get("burst") or 0)
    _write_profile(tmp_path, monkeypatch, "deepseek-direct",
                   concurrency_ceiling=2, ceiling_source="declared")
    cfg = governor.provider_config("deepseek-direct")
    assert cfg["max_inflight"] == 2, "the ceiling still binds concurrency"
    assert cfg["burst"] == yaml_burst, (
        f"burst was lowered to {cfg['burst']}; this rule raises only")
