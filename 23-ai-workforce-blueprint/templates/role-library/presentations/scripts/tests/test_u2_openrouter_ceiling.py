#!/usr/bin/env python3
"""test_u2_openrouter_ceiling.py -- U2: the governor must not throttle
OpenRouter below the operator's stated 100.

THE OPERATOR REQUIREMENT (2026-09-07, verbatim):
    "if I am using OpenRouter I should not be capped at 8. I should be able
     to use at least 100 agents in parallel if I'm using OpenRouter."

THE DEFECT ON PRISTINE main.  `presentation_job/providers.yaml` gave
openrouter `rps 2.0 / burst 20 / max_inflight 50`.  Two separate ceilings in
that row each land below 100:

  * `max_inflight 50` -- the hard concurrency ceiling in `governor.acquire`
    (`st.inflight + n <= cfg["max_inflight"]`).  51 concurrent OpenRouter
    calls could never be in flight, whatever the wave width said.
  * `burst 20` -- the HARD rolling-10s admission ceiling
    (`window_cap = max(1.0, round(capacity * st.rate_scale))`).  Even with an
    unbounded in-flight ceiling, a 100-unit fan-out would need ~50 s just to
    be admitted, so "100 parallel" would never actually be reached.

WHERE THE 50 CAME FROM -- this matters, because raising a MEASURED ceiling
and raising a GUESS are different acts.  The row's own derivation footer said
"free 20 RPM paid unpublished -> start 20-50 ramp on 429": OpenRouter
publishes no paid concurrency or RPS cap at all, so the 20/50 was this
build's own conservative opening bid, not a fact about OpenRouter.  It was
never measured and never ramped -- the whole file has a single commit in its
history (`4019cf9b0`) and no run on this box has ever exercised OpenRouter at
any concurrency.  `test_the_old_numbers_were_never_a_measurement` locks that
provenance so nobody later reads the 50 back as evidence.

THE FIX, and what this file locks:
  1. the governor admits AT LEAST 100 concurrent acquisitions on openrouter
     (config assertion AND a live acquire proof, so a raised in-flight number
     that the window ceiling still strangles cannot pass);
  2. the governor is not the narrower of the two ceilings -- it is >= the
     ultra mode ceiling, so `min(mode, governor)` is decided by the mode;
  3. ollama stays at 3 and deepseek at 400 -- the CONTROL that proves this is
     a targeted raise and not a fleet-wide uncapping;
  4. the report_429 / report_ok ramp really is implemented AND wired to the
     OpenRouter transport -- because the 100 is justified partly by that ramp
     existing, and if it is ever removed the justification goes with it;
  5. the HONEST LIMIT of that ramp: it scales the RATE axis only and does NOT
     reduce max_inflight, so 100 concurrent is an operator bet on the
     concurrency axis, not "safe by construction".  Recorded as an executable
     characterization so the caveat cannot quietly stop being true.

STATE REDIRECTION.  Nothing here may touch the live
`~/.openclaw/state/presentation/resource_profile.json` (defect B3).  Every
test sets `PRESENTATION_RESOURCE_PROFILE=0` (the documented rollback flag,
which makes `governor._resource_profile_path()` return None on its first
branch) AND points `PRESENTATION_RESOURCE_PROFILE_DIR` /
`PRESENTATION_CAPACITY_CONFIG_DIR` at a pytest tmp_path, AND redirects the
governor acquisition log into that tmp_path (its default is
`/tmp/presentation_governor.log`).  No test in this file imports
`deck-intake-driver` or calls `resource_profile.record_model_plan` -- the
only writer of those 1,105 live rows.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import governor  # noqa: E402
from presentation_job import model_router  # noqa: E402

#: The operator's number. Not a suggestion and not a default: it is the
#: stated allocation for OpenRouter.
OPERATOR_OPENROUTER_PARALLEL = 100

DISPATCHER_SRC = SCRIPTS / "presentation_job" / "dispatcher.py"


@pytest.fixture(autouse=True)
def _isolated_governor(monkeypatch, tmp_path):
    """Every test in this file runs against a governor that cannot read or
    write anything of the operator's.

    `PRESENTATION_RESOURCE_PROFILE=0` short-circuits
    `governor._resource_profile_path()` before it consults any path at all,
    so `_plan_tier_rps` / `_plan_tier_inflight` cannot reach the live
    profile; the two dir envs are redirected as well so a future refactor
    that stops honouring the flag still lands in tmp_path."""
    monkeypatch.setenv("PRESENTATION_RESOURCE_PROFILE", "0")
    monkeypatch.setenv("PRESENTATION_RESOURCE_PROFILE_DIR", str(tmp_path))
    monkeypatch.setenv("PRESENTATION_CAPACITY_CONFIG_DIR", str(tmp_path))
    governor.set_log_path(str(tmp_path / "governor_log.jsonl"))
    governor.reload_config()
    governor._state.clear()          # no admission history bleeds across tests
    try:
        yield
    finally:
        governor._state.clear()
        governor.set_log_path("")
        governor.reload_config()


def _fill_bucket(provider: str) -> None:
    """Bring the token bucket to a full `burst` without waiting on the wall
    clock. This test is about the CEILINGS, not the refill rate: acquire()
    computes `tokens = min(burst, tokens + (now - last_refill) * rps)`, so
    backdating `last_refill` fills to exactly `burst` on any build, pre-fix
    or post-fix, without the test having to know either number."""
    st = governor._state_for(provider)
    st.tokens = 0.0
    st.last_refill = time.time() - 10_000.0


def _admit_as_many_as_possible(provider: str, want: int,
                               timeout_s: float = 1.5,
                               overall_s: float = 5.0):
    """Acquire serially until the governor refuses, returning the leases.

    Stops at the FIRST GovernorTimeout: a refusal is the answer, and
    re-asking `want` more times would only multiply the timeout.

    `overall_s` bounds the WHOLE loop, and it is load-bearing, not a
    convenience. The governor's admission ceiling is per ROLLING 10 s window
    (`_window_acquires` prunes anything older), so a loop allowed to run for
    20 s can legitimately admit two windows' worth and make a halved ceiling
    look untouched. Keeping the loop strictly inside one window is what makes
    "at most `burst` admissions" a testable statement at all."""
    leases = []
    deadline = time.monotonic() + overall_s
    for _ in range(want):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            leases.append(governor.acquire(
                provider, timeout_s=min(timeout_s, remaining)))
        except governor.GovernorTimeout:
            break
    return leases


# ---------------------------------------------------------------------------
# 0. The premise: this test is reading the file the engine reads
# ---------------------------------------------------------------------------
def test_the_instrument_reads_the_real_providers_yaml():
    """A known-good control for every assertion below. If `CONFIG_PATH` did
    not resolve, or the yaml subset loader silently returned `defaults` for
    everything, the ceiling assertions would be measuring nothing."""
    yaml_text = Path(governor.CONFIG_PATH).read_text(encoding="utf-8")
    assert "openrouter:" in yaml_text, governor.CONFIG_PATH
    # ... and the loader really parsed rows, rather than falling to _DEFAULTS
    # for all of them: a provider whose values differ from the default row.
    assert governor.provider_config("kie")["daily_cap"] == 5000
    assert governor.provider_config("kie")["max_inflight"] != \
        governor._DEFAULTS["max_inflight"]


# ---------------------------------------------------------------------------
# 1. THE REQUIREMENT -- fails on pristine main (max_inflight 50, burst 20)
# ---------------------------------------------------------------------------
def test_openrouter_inflight_ceiling_meets_the_operator_number():
    """"at least 100 agents in parallel if I'm using OpenRouter." On pristine
    main this is 50."""
    cfg = governor.provider_config("openrouter")
    assert cfg["max_inflight"] >= OPERATOR_OPENROUTER_PARALLEL, cfg


def test_openrouter_window_ceiling_can_admit_the_wave_in_one_window():
    """The second, quieter cap. `governor.acquire` refuses any admission that
    would put more than `burst` acquisitions inside a rolling 10 s window, so
    burst is a ceiling on how fast 100 parallel can ever be REACHED. At
    burst 20 a 100-unit fan-out needs ~50 s to be admitted; a max_inflight
    raise alone would leave that in place."""
    cfg = governor.provider_config("openrouter")
    assert cfg["burst"] >= OPERATOR_OPENROUTER_PARALLEL, cfg


def test_the_governor_actually_admits_one_hundred_concurrent_openrouter_calls():
    """THE POINT OF U2, proved by running the governor rather than by reading
    its config: 100 leases are held AT THE SAME TIME on openrouter.

    On pristine main this admits 20 (the burst window ceiling bites first,
    and max_inflight 50 bites right after it) and then times out."""
    _fill_bucket("openrouter")
    leases = _admit_as_many_as_possible(
        "openrouter", OPERATOR_OPENROUTER_PARALLEL)
    try:
        assert len(leases) >= OPERATOR_OPENROUTER_PARALLEL, (
            "governor admitted only %d concurrent openrouter leases; the "
            "operator's stated allocation is %d"
            % (len(leases), OPERATOR_OPENROUTER_PARALLEL))
        # and they really were CONCURRENT -- nothing was released in between
        assert governor.max_inflight_seen("openrouter") >= \
            OPERATOR_OPENROUTER_PARALLEL
    finally:
        for lease in leases:
            governor.release(lease)


def test_the_governor_is_not_narrower_than_the_ultra_mode_ceiling():
    """`capped_width` is `min(measured, mode ceiling)`, and the governor is a
    SECOND, independent gate applied later at acquire() time. If the governor
    sits below the mode ceiling, the plan number the run announces (100) is
    not the number the run can achieve -- exactly the "banner lies about the
    wave" class F15 was raised to kill."""
    cfg = governor.provider_config("openrouter")
    assert cfg["max_inflight"] >= model_router.ULTRA_OPERATOR_CEILING, (
        "governor max_inflight %s < ultra mode ceiling %s: the governor, not "
        "the declared mode, would silently decide the width"
        % (cfg["max_inflight"], model_router.ULTRA_OPERATOR_CEILING))


def test_the_old_numbers_were_never_a_measurement():
    """Provenance guard. The 20/50 was an unmeasured opening bid against an
    UNPUBLISHED cap, so this fix replaces a guess with an operator ruling --
    it does not raise a measured ceiling. The row must keep saying so, so a
    future reader can neither cite the old number as evidence nor read the
    new one as a discovered limit."""
    yaml_text = Path(governor.CONFIG_PATH).read_text(encoding="utf-8")
    start = yaml_text.index("openrouter:")
    end = yaml_text.index("anthropic:", start)
    block = yaml_text[start:end]
    assert "UNPUBLISHED" in block or "no published paid cap" in block, block
    assert "OPERATOR CEILING" in block, (
        "the openrouter row must name the operator ruling that set 100, so "
        "the number is never mistaken for a measurement")


# ---------------------------------------------------------------------------
# 2. THE CONTROLS -- must pass on pristine main AND on the fix
# ---------------------------------------------------------------------------
def test_ollama_is_untouched_at_three():
    """The $20 Ollama tier is 3 and that is CORRECT. This raise is
    openrouter-only; a fleet-wide uncapping would show up right here."""
    assert governor.provider_config("ollama-cloud")["max_inflight"] == 3
    assert governor.provider_config("ollama")["max_inflight"] == 3


def test_deepseek_and_the_defaults_row_are_untouched():
    """The rest of the file is a control on the same instrument: a config
    read that returns the pre-existing numbers proves the loader is fine and
    that only the openrouter row moved."""
    assert governor.provider_config("deepseek-direct")["max_inflight"] == 400
    assert governor.provider_config("deepseek-direct")["rps"] == 5.0
    assert governor._DEFAULTS["max_inflight"] == 50
    assert governor.provider_config("kie")["max_inflight"] == 100


def test_a_provider_with_no_row_still_falls_to_defaults():
    """F17's floor is untouched: raising openrouter must not make an unknown
    provider inherit a wide ceiling it never earned."""
    cfg = governor.provider_config("acme-llm-9000")
    assert cfg["max_inflight"] == governor._DEFAULTS["max_inflight"]
    assert cfg["rps"] == governor._DEFAULTS["rps"]


# ---------------------------------------------------------------------------
# 3. THE RAMP -- implemented, and wired to the OpenRouter transport
# ---------------------------------------------------------------------------
def test_report_429_really_halves_the_rate_and_report_ok_recovers_it():
    """Part of the justification for 100 is that a miss is absorbed. That is
    only true if the ramp is real code, so assert the behaviour, not the
    comment. Passes on pristine main too -- the ramp predates this fix."""
    assert governor.report_429("openrouter") == 0.5
    assert governor._state_for("openrouter").rate_scale == 0.5
    # repeated 429s inside the penalty window re-halve
    assert governor.report_429("openrouter") == 0.25
    governor.report_ok("openrouter")
    assert governor._state_for("openrouter").rate_scale == 0.5
    governor.report_ok("openrouter")
    assert governor._state_for("openrouter").rate_scale == 1.0


def test_the_429_penalty_also_halves_the_ten_second_window_ceiling():
    """The halving has to bite on ADMISSIONS, not just on a stored float.

    Order matters here. `report_429` runs FIRST, and the bucket is filled
    AFTERWARDS, so the token supply is not the thing under test: with a full
    `burst` of tokens available, the only mechanism that can still stop the
    run at half the burst is the scaled 10 s window ceiling. The whole loop
    is held inside a single window (see `_admit_as_many_as_possible`), or a
    second window's fresh allowance would mask the penalty entirely."""
    burst = int(governor.provider_config("openrouter")["burst"])
    governor.report_429("openrouter")
    _fill_bucket("openrouter")
    leases = _admit_as_many_as_possible(
        "openrouter", burst, timeout_s=0.6, overall_s=3.0)
    try:
        assert len(leases) <= round(burst * 0.5) + 1, (
            "a 429 must halve the 10 s admission ceiling; admitted %d of a "
            "%d burst" % (len(leases), burst))
        # ... and the penalty is a HALVING, not a shutdown: roughly half the
        # burst really does get through, so a governor that simply refused
        # everything could not pass this either.
        assert len(leases) >= round(burst * 0.5) - 1, (
            "a 429 must halve the ceiling, not close it; admitted only %d "
            "of a %d burst" % (len(leases), burst))
    finally:
        for lease in leases:
            governor.release(lease)


def test_the_openrouter_transport_feeds_the_ramp():
    """WIRED, not merely implemented. The OpenAI-compatible transport is the
    one OpenRouter runs through (`dispatch_complete` -> `_openai_compat_
    complete`), so the 429 and the clean response must both be reported from
    inside THAT function body, keyed by the ROUTED provider."""
    src = DISPATCHER_SRC.read_text(encoding="utf-8")
    lines = src.split("\n")

    def body_of(defline: str) -> str:
        start = next(i for i, l in enumerate(lines) if l.startswith(defline))
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].startswith("def ")), len(lines))
        return "\n".join(lines[start:end])

    compat = body_of("def _openai_compat_complete(")
    assert "_govern_429(provider)" in compat
    assert "_govern_ok(provider)" in compat
    assert "_lease = _govern_acquire(provider)" in compat
    # the routed provider reaches that transport at all
    dispatch = body_of("def dispatch_complete(")
    assert "_openai_compat_complete(" in dispatch
    assert "_govern_acquire(_dispatch_provider)" in dispatch
    # KNOWN-GOOD CONTROL on the same instrument: the sibling transport is
    # found and wired too, so an empty result above would be absence, not a
    # broken slicer.
    deepseek = body_of("def deepseek_complete(")
    assert '_govern_429("deepseek-direct")' in deepseek


def test_the_ramp_does_not_protect_the_concurrency_axis():
    """THE HONEST CAVEAT, made executable.

    `report_429` halves the RATE and the 10 s window ceiling. It does NOT
    lower `max_inflight`. Long-lived calls hold their leases, so a 429 storm
    slows how fast new OpenRouter calls START while the 100 already-open
    sockets stay open. That is why 100 is an operator-declared bet on the
    concurrency axis and not "safe by construction".

    If someone later teaches the governor to scale max_inflight under a 429
    penalty -- a real improvement -- this test SHOULD fail, and the caveat in
    providers.yaml and in the U2 report must be rewritten in the same commit.
    """
    before = int(governor.provider_config("openrouter")["max_inflight"])
    governor.report_429("openrouter")
    after = int(governor.provider_config("openrouter")["max_inflight"])
    assert after == before, (
        "max_inflight changed under a 429 penalty: the governor now ramps "
        "the concurrency axis too. Update the U2 caveat before relaxing "
        "this test.")
