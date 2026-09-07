"""U4 -- the per-worker governor lease was hard-coded to `deepseek-direct`.

THE DEFECT

`parallel_prompt_worker._default_provider_call` opened its outer governor lease
with a constant:

    _lease = dispatcher._govern_acquire("deepseek-direct")     # line 400
    ...
    dispatcher._govern_release("deepseek-direct", _lease)      # line 409

regardless of where the wave was actually routed. Two consequences, both bad:

  * the REAL provider's limits were never enforced by that lease -- an
    OpenRouter wave's rate/in-flight budget was charged to DeepSeek, so
    openrouter's own bucket saw only dispatch_complete's inner acquire; and
  * DeepSeek's shared ACCOUNT bucket (providers.yaml `deepseek`: rps 5,
    max_inflight 400) was consumed by traffic that never touched DeepSeek.

THE TRAP THIS FIX HAD TO SURVIVE (the DEFECT-5 class, on the governor's bucket)

Provider identity has TWO live spellings here. MEASURED on this box:

    model_router.resolve_alias("deepseek-v4-pro")["provider"] -> 'deepseek'
    capacity.probe()["provider"]                              -> 'deepseek-direct'

and the two config authorities disagree the same way:

    providers.yaml top-level keys : 'deepseek',      'ollama',       'openrouter'
    capacity.CAP_TABLE keys       : 'deepseek-direct','ollama-cloud','openrouter'

`dispatcher._routing_stamp` stamps `routing["provider"]` from the CATALOG
(`str(route.get("provider"))`, dispatcher.py:2798) -- so the stamp says
'deepseek' while every transport gates on 'deepseek-direct'. `governor`
folds on the CONFIG side (`PROVIDER_ALIASES`, so provider_config agrees for
both spellings) but NOT on the BUCKET side: `governor._state_for` and
`dispatcher._GOVERN_DEPTH` are keyed by the RAW string. So simply passing
`routing["provider"]` through un-normalised would have replaced a wrong-bucket
bug with a split-bucket bug -- two independent 400-in-flight buckets over ONE
DeepSeek account, and a re-entrancy depth counter that can no longer dedupe the
worker's outer lease against the transport's inner one.

THE FIX: fold BOTH sides through `dispatcher._govern_provider` (which defers to
`capacity.normalize_provider`, the ONE cap-table authority) and key the lease on
the ROUTE's provider. An identity the fold cannot establish is announced LOUDLY
and takes NO outer lease -- never a silent fallback to DeepSeek.

BOTH DIRECTIONS ARE PROVEN. A fix that folded everything onto one bucket would
satisfy the collapse tests and be just as wrong, so the separation tests below
(openrouter must NOT land in DeepSeek's bucket, ollama must NOT either) are
load-bearing, not decoration.

STATE REDIRECTION (defect B3): every test here points
PRESENTATION_RESOURCE_PROFILE_DIR / PRESENTATION_CAPACITY_CONFIG_DIR at
tmp_path and the governor log at tmp_path, so nothing in this file can reach
~/.openclaw/state/presentation/resource_profile.json.

Flat file inside tests/, manages its own import path -- matching every sibling
here (test_f8_one_governor_per_wave.py, test_defect5_routing_stamp_provider_identity.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import dispatcher  # noqa: E402
from presentation_job import governor  # noqa: E402
from presentation_job import parallel_prompt_worker as ppw  # noqa: E402

#: What the CATALOG spells into routing["provider"] on a DeepSeek route.
CATALOG_DEEPSEEK = "deepseek"
#: What the cap table, the transports and the probe all call the same account.
CANON_DEEPSEEK = capacity.PROVIDER_DEEPSEEK_DIRECT          # 'deepseek-direct'
CANON_OPENROUTER = capacity.PROVIDER_OPENROUTER             # 'openrouter'
CANON_OLLAMA = capacity.PROVIDER_OLLAMA_CLOUD               # 'ollama-cloud'


def _fold(provider):
    """The governor key this build derives for `provider`.

    Deliberately tolerant of a tree WITHOUT the U4 fold: there it degrades to
    the raw string, which is exactly what pristine main keys its buckets and
    its depth counter on. Every assertion below is therefore a statement about
    BEHAVIOUR -- "these two spellings must reach one bucket" -- and fails on
    main because the strings differ, not because a symbol is missing."""
    fold = getattr(dispatcher, "_govern_provider", None)
    if fold is None:  # pragma: no cover - pristine-main path
        return str(provider or "").strip()
    return fold(provider)


@pytest.fixture
def gov_env(tmp_path, monkeypatch):
    """Isolated governor state + log, and the resource-profile store redirected
    away from the live one. No network, no engine, no real provider."""
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
    _announced = getattr(ppw, "_lease_announced", None)
    if _announced is not None:
        _announced.clear()
    try:
        yield tmp_path
    finally:
        governor.set_log_path(saved_log)
        with governor._lock:
            governor._state.clear()
        with dispatcher._GOVERN_DEPTH_LOCK:
            dispatcher._GOVERN_DEPTH.clear()
            dispatcher._GOVERN_ACTIVE.clear()
        if _announced is not None:
            _announced.clear()


def _buckets_with_traffic() -> dict:
    """provider id -> peak in-flight, for every bucket that saw an admission.
    This is the governor's own module state: the thing the account limit is
    actually enforced against."""
    with governor._lock:
        return {p: st.max_inflight_seen
                for p, st in governor._state.items()
                if st.max_inflight_seen > 0}


def _drive_worker(monkeypatch, run_dir: Path, routing: dict) -> dict:
    """Run the REAL `_default_provider_call` with the transport stubbed, and
    report which governor buckets its lease touched WHILE the dispatch was in
    flight (a released lease leaves inflight back at 0, so the peak is read
    from inside the call)."""
    seen: dict = {}

    def _compose(**kwargs):
        return "sys", "user"

    def _dispatch_complete(system_prompt, user_prompt, *, phase_id, run_dir=None,
                           **kwargs):
        # Snapshot the buckets while the worker's outer lease is HELD.
        seen.update(_buckets_with_traffic())
        return "PROMPT BODY", {}, {"provider": routing.get("provider")}

    monkeypatch.setattr(dispatcher, "compose_prompt", _compose)
    monkeypatch.setattr(dispatcher, "dispatch_complete", _dispatch_complete)
    monkeypatch.setattr(dispatcher, "_clean_payload", lambda c: c)

    slide = {"slide_id": "s01", "ordinal": 1, "copy": ["Headline"]}
    ppw._default_provider_call(slide, routing, 1, run_dir,
                               "director-of-presentations", 1)
    return seen


# ---------------------------------------------------------------------------
# 1. THE DEFECT: the lease must follow the ROUTE, not a constant.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("routed,expected", [
    (CANON_OPENROUTER, CANON_OPENROUTER),
    (CANON_OLLAMA, CANON_OLLAMA),
    ("anthropic", "anthropic"),
])
def test_lease_is_taken_against_the_routed_provider(gov_env, monkeypatch,
                                                    routed, expected):
    """A wave routed to OpenRouter / Ollama / Anthropic must hold ITS bucket."""
    seen = _drive_worker(monkeypatch, gov_env, {
        "provider": routed, "model": "m", "mode": "standard",
        "measured_capacity": 4})
    assert expected in seen, (
        f"U4: a wave routed to {routed!r} took no lease against {expected!r} -- "
        f"buckets that saw traffic: {sorted(seen)}. The real provider's rate "
        f"and in-flight limits are not being enforced.")


@pytest.mark.parametrize("routed", [CANON_OPENROUTER, CANON_OLLAMA, "anthropic"])
def test_a_non_deepseek_route_never_burns_the_deepseek_bucket(gov_env,
                                                              monkeypatch,
                                                              routed):
    """THE HEADLINE DEFECT. DeepSeek's shared account bucket must not be
    consumed by traffic that never touched DeepSeek.

    On pristine main the lease is hard-coded to "deepseek-direct", so this
    bucket is charged on EVERY wave whatever the route."""
    seen = _drive_worker(monkeypatch, gov_env, {
        "provider": routed, "model": "m", "mode": "standard",
        "measured_capacity": 4})
    assert CANON_DEEPSEEK not in seen, (
        f"U4: a wave routed to {routed!r} charged DeepSeek's account bucket "
        f"({CANON_DEEPSEEK!r}) -- buckets that saw traffic: {sorted(seen)}. "
        f"DeepSeek's rate/in-flight budget is being spent by a provider that "
        f"was never called.")


# ---------------------------------------------------------------------------
# 2. THE TRAP: two spellings of ONE account are ONE bucket (fold direction).
# ---------------------------------------------------------------------------

def test_the_two_spellings_are_two_names_for_one_bucket(gov_env):
    """The catalog spelling and the canonical spelling name the SAME DeepSeek
    account, so they must share one token bucket and one in-flight counter.

    Without the fold these are two dict keys: two independent 400-in-flight
    buckets over one account (800 effective), and the re-entrancy depth counter
    cannot dedupe the worker's outer lease against the transport's inner one."""
    assert (_fold(CATALOG_DEEPSEEK)
            == _fold(CANON_DEEPSEEK)), (
        "U4: the catalog spelling and the canonical spelling still fold to "
        "different governor ids")

    outer = dispatcher._govern_acquire(CATALOG_DEEPSEEK)   # what the stamp says
    inner = dispatcher._govern_acquire(CANON_DEEPSEEK)     # what transports say
    try:
        traffic = _buckets_with_traffic()
        assert CATALOG_DEEPSEEK not in governor._state, (
            f"U4: the catalog spelling {CATALOG_DEEPSEEK!r} opened its own "
            f"governor bucket -- buckets: {sorted(governor._state)}. One "
            f"DeepSeek account is now governed as two.")
        assert list(traffic) == [CANON_DEEPSEEK], (
            f"U4: one logical call touched {sorted(traffic)}; it must touch "
            f"exactly [{CANON_DEEPSEEK!r}]")
        assert traffic[CANON_DEEPSEEK] == 1, (
            f"U4: one logical call took {traffic[CANON_DEEPSEEK]} in-flight "
            f"slots -- the nested acquire did not re-use the outer lease, so "
            f"max_inflight under-counts real capacity")
        assert inner is outer, (
            "U4: the nested acquire returned a second lease instead of "
            "re-using the outer one")
    finally:
        dispatcher._govern_release(CANON_DEEPSEEK, inner)
        dispatcher._govern_release(CATALOG_DEEPSEEK, outer)

    with governor._lock:
        assert governor._state[CANON_DEEPSEEK].inflight == 0, (
            "U4: releasing under the other spelling leaked an in-flight slot")


def test_a_deepseek_route_stamped_by_the_catalog_lands_in_the_canonical_bucket(
        gov_env, monkeypatch):
    """End-to-end on the worker: the stamp carries 'deepseek' (what
    _routing_stamp writes) and the lease must land on 'deepseek-direct' (what
    providers.yaml + the transports govern)."""
    seen = _drive_worker(monkeypatch, gov_env, {
        "provider": CATALOG_DEEPSEEK, "model": "deepseek-v4-flash",
        "mode": "standard", "measured_capacity": 4})
    assert list(seen) == [CANON_DEEPSEEK], (
        f"U4: a catalog-spelled DeepSeek route touched {sorted(seen)} instead "
        f"of exactly [{CANON_DEEPSEEK!r}]")


# ---------------------------------------------------------------------------
# 3. THE OTHER DIRECTION: distinct providers must STAY distinct.
#    A fix that folded everything onto one bucket would pass section 2 and be
#    just as broken. These are the mutation guard.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("a,b", [
    (CANON_OPENROUTER, CANON_DEEPSEEK),
    (CANON_OPENROUTER, CANON_OLLAMA),
    (CANON_OLLAMA, CANON_DEEPSEEK),
    ("anthropic", CANON_DEEPSEEK),
])
def test_different_providers_are_never_merged_into_one_bucket(gov_env, a, b):
    """Separate accounts, separate limits: folding them together would let one
    provider's traffic exhaust another's budget -- the same class of bug as the
    hard-coded lease, pointed the other way."""
    assert _fold(a) != _fold(b), (
        f"U4: {a!r} and {b!r} fold onto the same governor bucket -- two "
        f"separate accounts would share one rate and in-flight budget")

    la = dispatcher._govern_acquire(a)
    lb = dispatcher._govern_acquire(b)
    try:
        traffic = _buckets_with_traffic()
        assert sorted(traffic) == sorted({_fold(a),
                                          _fold(b)}), (
            f"U4: leases on {a!r} and {b!r} did not open two buckets: "
            f"{sorted(traffic)}")
        assert lb is not la, (
            f"U4: an acquire on {b!r} re-used the lease held for {a!r}")
    finally:
        dispatcher._govern_release(b, lb)
        dispatcher._govern_release(a, la)


def test_an_unknown_provider_keeps_its_own_identity(gov_env):
    """A provider this build has never heard of is NOT folded onto the
    nearest-looking one. capacity.normalize_provider returns None for it; the
    gate keeps the canonical token so it is governed as itself (at
    providers.yaml `defaults`, which governor announces on its own)."""
    assert capacity.normalize_provider("acme-llm") is None, (
        "control: this test needs a provider the cap table does NOT resolve")
    assert _fold("acme-llm") == "acme-llm"
    assert _fold("Acme_LLM") == "acme-llm", (
        "U4: spelling variants of one unknown provider must still be one bucket")
    assert _fold("acme-llm") != CANON_DEEPSEEK


# ---------------------------------------------------------------------------
# 4. UNRESOLVABLE IS LOUD, NEVER A SILENT DEEPSEEK DEFAULT.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("routing", [
    {"model": "m", "mode": "standard", "measured_capacity": 4},   # no provider
    {"provider": "", "model": "m", "mode": "standard", "measured_capacity": 4},
    {"provider": None, "model": "m", "mode": "standard", "measured_capacity": 4},
])
def test_an_unnameable_route_refuses_loudly_instead_of_charging_deepseek(
        gov_env, monkeypatch, capsys, routing):
    """"system need to ask if unclear" -- when the provider cannot be
    established the worker must SAY SO and take no outer lease, never
    substitute DeepSeek. On pristine main this silently charged
    "deepseek-direct" with nothing anywhere saying why."""
    seen = _drive_worker(monkeypatch, gov_env, dict(routing))

    assert CANON_DEEPSEEK not in seen, (
        f"U4: an unnameable route silently charged {CANON_DEEPSEEK!r} -- "
        f"buckets: {sorted(seen)}. That is the fabricated-default disease.")
    assert seen == {}, (
        f"U4: an unnameable route took an outer lease anyway, on {sorted(seen)}")

    err = capsys.readouterr().err
    assert "UNRESOLVABLE" in err, (
        f"U4: the refusal was SILENT. stderr said: {err!r}")
    assert "NO outer lease" in err, (
        f"U4: the announcement does not say what it did instead: {err!r}")


def test_the_refusal_reaches_the_governor_log(gov_env, monkeypatch):
    """LOUD means on the governor's own proof surface too -- stderr is only
    read live, the acquisition log is what the after-the-fact audit reads."""
    _drive_worker(monkeypatch, gov_env, {"model": "m", "mode": "standard",
                                         "measured_capacity": 4})
    log = Path(governor.log_path())
    assert log.is_file(), "U4: no governor log was written at all"
    body = log.read_text(encoding="utf-8")
    assert "lease-unresolved" in body, (
        f"U4: the unresolvable-lease refusal never reached the governor log: "
        f"{body!r}")


def test_announcement_is_once_per_process_not_once_per_slide(gov_env,
                                                             monkeypatch,
                                                             capsys):
    """A 100-slide wave must not print 100 identical warnings."""
    routing = {"model": "m", "mode": "standard", "measured_capacity": 4}
    for _ in range(5):
        _drive_worker(monkeypatch, gov_env, dict(routing))
    assert capsys.readouterr().err.count("UNRESOLVABLE") == 1, (
        "U4: the unresolvable-lease warning is per-slide, not per-process")
