#!/usr/bin/env python3
"""test_f17_new_provider_floor.py -- F17: a NEW provider must not silently
drop the whole pipeline to 8-wide / rps 1.

THE DEFECT (spec section 8, fix list F17). A provider this build has never
heard of resolved to None in `capacity.normalize_provider`, and every
consumer read that None as "no capacity information at all":

  * `capacity.detect()` fell through every case to DEFAULT_CONSERVATIVE = 3,
    so `dispatcher.resolve_max_workers` returned 3 no matter how much ready
    work there was;
  * `dispatcher._prompt_routing_stamp` could not attribute the measurement to
    the route, stamped capacity_status=provider-unresolved and fell to
    DEFAULT_MAX_WORKERS = 8;
  * `governor.provider_config` fell to `defaults` (rps 1.0) with nothing in
    the governor's own log saying it had done so.

None of it was announced anywhere, and the only cure was a code change --
against the standing operator ruling that nobody is forced onto a model and a
new one must work WITHOUT one.

THE FIX, and what this file locks:
  1. a provider the CLIENT DECLARED in their model plan normalises to itself
     and measures UNBOUNDED (the declaration is the client bringing their own
     capacity), so `resolve_max_workers` dispatches as wide as the ready work;
  2. an UNDECLARED unknown provider is still unknown -- the guess-upward gate
     is untouched (the control that proves 1 is a fix, not a hole);
  3. a CAP_TABLE provider is never uncapped by a declaration -- an account
     ceiling is a fact the client cannot opt out of by naming the provider;
  4. the governor announces the defaults fallback once per process, naming
     the providers.yaml row the operator has to add;
  5. `record_model_plan` ADOPTS an unknown declared provider onto the profile
     so `model_router._eligible` can see it, while still refusing a provider
     this build DOES know and the probe did not find.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import dispatcher  # noqa: E402
from presentation_job import governor  # noqa: E402
from presentation_job import model_router  # noqa: E402
from presentation_job import resource_profile  # noqa: E402

#: A provider id that appears in NO table, NO alias list and NO yaml row in
#: this repo -- proven by test_the_new_provider_id_is_genuinely_unknown below,
#: so a pass here can never be an accident of spelling.
NEW_PROVIDER = "acme-llm-9000"
NEW_MODEL = "acme-1-turbo"


def _clear_declared_cache():
    """Drop capacity's declaration cache when the module has one.

    getattr, not a bare attribute: the CONTROL tests in this file must run --
    and pass -- against a build with no F17 in it at all, so the harness may
    never depend on a symbol the fix introduces. Only the assertions may."""
    cache = getattr(capacity, "_DECLARED_CACHE", None)
    if isinstance(cache, dict):
        cache.clear()


def _isolate(monkeypatch, tmp_path):
    """No 9Router db, no OpenClaw config, no harness settings -- detection
    steps b and c are structurally unreachable, so these tests assert on the
    declared override (a) and the fallthrough (e) alone. Same helper shape as
    tests/test_capacity_detection.py."""
    monkeypatch.setattr(capacity, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(capacity, "HARNESS_SETTINGS_CANDIDATES",
                        (tmp_path / "absent-settings.json",))
    monkeypatch.delenv("PRESENTATION_RESOURCE_PROFILE_DIR", raising=False)
    monkeypatch.delenv("PRESENTATION_RESOURCE_PROFILE", raising=False)
    monkeypatch.delenv("PRESENTATION_DECLARED_PROVIDER_UNCAP", raising=False)
    # The declaration read is cached on (path, mtime_ns, size); tmp_path is
    # unique per test, but clear it anyway so no ordering can leak a verdict.
    _clear_declared_cache()


def _cfg(monkeypatch, tmp_path, *, profile=None, override=None):
    """One tmp config dir carrying the capacity override and the resource
    profile side by side, exactly as a real box does."""
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    if profile is not None:
        (cfg / resource_profile.PROFILE_FILENAME).write_text(
            json.dumps(profile, indent=2), encoding="utf-8")
    if override is not None:
        (cfg / capacity.OVERRIDE_FILENAME).write_text(
            json.dumps(override), encoding="utf-8")
    _clear_declared_cache()
    return cfg


def _profile_declaring(provider, model, *, slot="workhorse"):
    """A profile whose model plan NAMES {provider, model} -- the client
    telling us which account they own."""
    return {
        ".schema_version": 1,
        "providers": {provider: {"provider": provider, "presence": True}},
        "model_plan": {
            "workhorse": None, "reasoning": None, "judge": None,
            slot: {"provider": provider, "model": model},
            "thinking": None, "floor_waivers": [], "source": "interview",
            "declared_at": "2026-09-06T00:00:00+00:00",
        },
        "creative_prefs": {}, "consent": {}, "interview": {},
    }


# ---------------------------------------------------------------------------
# 0. The premise: the id under test really is unknown to this build
# ---------------------------------------------------------------------------
def test_the_new_provider_id_is_genuinely_unknown(monkeypatch, tmp_path):
    """The premise every assertion below rests on. If NEW_PROVIDER were a real
    id, the tests would pass for the wrong reason -- so prove it is absent
    from each source BY NAME, with a known-good control on the same
    instrument proving the check can find something when it is there.

    Passes on a build with no F17 in it too: that is the point of a premise."""
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path)               # empty profile: nothing declared
    assert NEW_PROVIDER not in capacity.CAP_TABLE_PROVIDERS, "capacity.CAP_TABLE"
    assert NEW_PROVIDER not in capacity.NO_CAP_PROVIDERS, "capacity.NO_CAP_PROVIDERS"
    assert NEW_PROVIDER not in capacity.PLANS_BY_PROVIDER, "capacity.PLANS_BY_PROVIDER"
    assert NEW_PROVIDER not in governor.PROVIDER_ALIASES, "governor.PROVIDER_ALIASES"
    yaml_text = Path(governor.CONFIG_PATH).read_text(encoding="utf-8")
    assert NEW_PROVIDER not in yaml_text, "presentation_job/providers.yaml"
    # The known-good controls, on those SAME instruments: real ids ARE found,
    # so an empty result above is absence, not a broken check.
    assert "openrouter" in capacity.NO_CAP_PROVIDERS
    assert "ollama-cloud" in capacity.PLANS_BY_PROVIDER
    assert "kie" in governor.PROVIDER_ALIASES
    assert "openrouter:" in yaml_text


# ---------------------------------------------------------------------------
# 1. A DECLARED new provider resolves, measures unbounded, and dispatches wide
# ---------------------------------------------------------------------------
def test_a_declared_new_provider_normalises_to_itself(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path,
         profile=_profile_declaring(NEW_PROVIDER, NEW_MODEL))
    assert capacity.normalize_provider(NEW_PROVIDER) == NEW_PROVIDER
    # ... and spelling drift folds onto the same one id, never a second provider
    assert capacity.normalize_provider("ACME_LLM 9000") == NEW_PROVIDER


def test_a_declared_new_provider_measures_unbounded_not_three(monkeypatch, tmp_path):
    """Before F17 this resolved provider=None and fell to case (e)/DEFAULT_
    CONSERVATIVE = 3 -- a three-wide deck for a client who bought thousands."""
    _isolate(monkeypatch, tmp_path)
    cfg = _cfg(monkeypatch, tmp_path,
               profile=_profile_declaring(NEW_PROVIDER, NEW_MODEL),
               override={"provider": NEW_PROVIDER})
    result = capacity.probe(cfg)
    assert result["status"] == capacity.STATUS_MEASURED, result
    assert capacity.is_unbounded(result["available"]), result
    assert result["provider"] == NEW_PROVIDER
    assert any("bring-your-own-key" in n for n in result.get("notes") or []), result


def test_a_declared_new_provider_does_not_collapse_the_wave_width(
        monkeypatch, tmp_path):
    """THE POINT OF F17. resolve_max_workers is the accessor the dispatch path
    reads; on pristine main it returned DEFAULT_CONSERVATIVE = 3 here, so 25
    ready units ran 3 at a time behind a provider the client is paying for."""
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path,
         profile=_profile_declaring(NEW_PROVIDER, NEW_MODEL),
         override={"provider": NEW_PROVIDER})
    assert dispatcher.resolve_max_workers(tmp_path, None, unit_count=25) == 25
    assert dispatcher.resolve_max_workers(tmp_path, None, unit_count=25) != \
        capacity.DEFAULT_CONSERVATIVE


def test_a_declared_self_throttle_is_still_honoured_verbatim(monkeypatch, tmp_path):
    """"Do not limit someone who brought their own capacity" is not "ignore
    them when they limit themselves": a declared max_concurrent on a declared
    new provider is honoured exactly, the same as for openrouter."""
    _isolate(monkeypatch, tmp_path)
    cfg = _cfg(monkeypatch, tmp_path,
               profile=_profile_declaring(NEW_PROVIDER, NEW_MODEL),
               override={"provider": NEW_PROVIDER, "max_concurrent": 40})
    result = capacity.probe(cfg)
    assert result["status"] == capacity.STATUS_MEASURED, result
    assert result["available"] == 40, result


def test_the_p4_prompt_stamp_attributes_the_route_instead_of_giving_up(
        monkeypatch, tmp_path, capsys):
    """The OTHER consumer of the None. `_prompt_routing_stamp` folds both the
    routed and the probed provider through capacity.normalize_provider; on
    pristine main BOTH sides of a new-provider route resolved to None, so the
    stamp declared the identity UNRESOLVABLE and labelled the width
    capacity_status=provider-unresolved -- a route the client chose, recorded
    as a provider the build could not identify.

    NOTE what this does NOT claim. F17 fixes the ATTRIBUTION and the probe; it
    asserts nothing about the WIDTH. When this test was written it recorded
    that "measured_capacity stays at DEFAULT_MAX_WORKERS here, exactly as it
    does for openrouter today ... that mapping is deliberate and untouched" --
    F17's own commit message said the same. U1 (2026-09-07) removed that
    mapping: an UNBOUNDED reading now resolves to the MODE CEILING, for this
    declared provider exactly as for openrouter. The assertions below were
    always about capacity_status and never about the number, so they hold
    unchanged either way -- which is why the width belongs in
    tests/test_u1_unbounded_is_not_eight.py and not here."""
    _isolate(monkeypatch, tmp_path)
    monkeypatch.delenv(model_router.MODE_ENV, raising=False)
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    profile = _profile_declaring(NEW_PROVIDER, NEW_MODEL)
    profile["providers"][NEW_PROVIDER]["consented"] = True
    profile["model_plan"]["floor_waivers"] = [
        "authoring", "prompt_authoring", "cheap_text", "creative_cheap",
        "speech_text"]
    _cfg(monkeypatch, tmp_path, profile=profile,
         override={"provider": NEW_PROVIDER})

    decision = model_router.resolve_route("P4-PROMPT")
    assert decision["route"] == {"provider": NEW_PROVIDER, "model": NEW_MODEL}, \
        decision
    stamp = dispatcher._prompt_routing_stamp(run_dir=tmp_path)
    assert stamp["provider"] == NEW_PROVIDER, stamp
    assert stamp["capacity_status"] == "unbounded-byok", stamp
    assert stamp["capacity_status"] != "provider-unresolved", stamp
    assert "UNRESOLVABLE" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 2. THE CONTROLS -- the guess-upward gates F17 must NOT have opened
# ---------------------------------------------------------------------------
def test_an_undeclared_unknown_provider_is_still_unknown(monkeypatch, tmp_path):
    """The counterfactual that makes test 1 a fix instead of a hole: with NO
    declaration, the same id resolves to None and the same override still
    collapses to DEFAULT_CONSERVATIVE. A typo can never buy capacity."""
    _isolate(monkeypatch, tmp_path)
    cfg = _cfg(monkeypatch, tmp_path, override={"provider": NEW_PROVIDER})
    assert capacity.normalize_provider(NEW_PROVIDER) is None
    result = capacity.probe(cfg)
    assert result["status"] != capacity.STATUS_MEASURED, result
    assert result["available"] == capacity.DEFAULT_CONSERVATIVE, result
    assert dispatcher.resolve_max_workers(tmp_path, None, unit_count=25) == \
        capacity.DEFAULT_CONSERVATIVE


def test_a_declaration_never_uncaps_a_cap_table_provider(monkeypatch, tmp_path):
    """ollama-cloud's $20/$100 tiers are hard ACCOUNT limits. Declaring the
    provider in a model plan is not a purchase: it still PARKS behind the
    one-time plan question instead of going unbounded."""
    _isolate(monkeypatch, tmp_path)
    cfg = _cfg(monkeypatch, tmp_path,
               profile=_profile_declaring("ollama-cloud", "glm-5.3-flash"),
               override={"provider": "ollama-cloud"})
    result = capacity.probe(cfg)
    assert result["status"] == capacity.STATUS_PARKED, result
    assert not capacity.is_unbounded(result["available"]), result
    # The same statement at the helper level, when the build HAS the helper.
    # A control has to hold on the pre-fix build too, so it may not require a
    # symbol the fix introduces -- the probe assertion above is the one that
    # runs everywhere.
    if hasattr(capacity, "is_no_cap_provider"):
        assert not capacity.is_no_cap_provider("ollama-cloud")
        assert not capacity.is_no_cap_provider("deepseek-direct")


def test_a_declared_local_ollama_is_still_refused(monkeypatch, tmp_path):
    """A local Ollama buys no plan. That refusal is deliberate, not ignorance,
    so the declaration path must skip it -- otherwise F17 would hand an
    unbounded ceiling to a laptop."""
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path,
         profile=_profile_declaring("ollama-local", "llama3"))
    assert capacity.normalize_provider("ollama-local") is None
    if hasattr(capacity, "is_no_cap_provider"):   # see the note above
        assert not capacity.is_no_cap_provider("ollama-local")


def test_the_rollback_env_restores_the_pre_f17_behaviour(monkeypatch, tmp_path):
    """PRESENTATION_DECLARED_PROVIDER_UNCAP=0 is the documented rollback: the
    declaration is ignored and the pre-F17 answer comes back exactly."""
    _isolate(monkeypatch, tmp_path)
    cfg = _cfg(monkeypatch, tmp_path,
               profile=_profile_declaring(NEW_PROVIDER, NEW_MODEL),
               override={"provider": NEW_PROVIDER})
    monkeypatch.setenv("PRESENTATION_DECLARED_PROVIDER_UNCAP", "0")
    _clear_declared_cache()
    assert capacity.normalize_provider(NEW_PROVIDER) is None
    assert capacity.probe(cfg)["available"] == capacity.DEFAULT_CONSERVATIVE


# ---------------------------------------------------------------------------
# 3. The governor stops being silent about the defaults row
# ---------------------------------------------------------------------------
def test_governor_announces_the_defaults_fallback_once(monkeypatch, tmp_path):
    """rps 1.0 across a whole fan-out is a real throttle. It may still happen
    -- inventing a rate for an unknown endpoint would only trade a stall for
    a 429 storm -- but it must never happen in silence."""
    log = tmp_path / "governor_log.jsonl"
    governor.set_log_path(str(log))
    governor.reload_config()          # also clears the once-per-process set
    try:
        cfg = governor.provider_config(NEW_PROVIDER)
        assert cfg["rps"] == governor._DEFAULTS["rps"], cfg
        governor.provider_config(NEW_PROVIDER)
        governor.provider_config(NEW_PROVIDER)
    finally:
        governor.set_log_path("")
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    notes = [r for r in rows if r.get("event") == "config-defaults"
             and r.get("provider") == NEW_PROVIDER]
    assert len(notes) == 1, rows        # ONCE per process, not once per call
    assert "no providers.yaml row" in notes[0]["note"], notes[0]
    assert "rps" in notes[0]["note"], notes[0]


def test_governor_says_nothing_for_a_provider_that_has_a_row(monkeypatch, tmp_path):
    """The control: the announcement must fire on the ABSENCE of a row, not
    on every provider_config call. kie has a row, so it stays quiet -- and
    the alias path (deepseek-direct -> the `deepseek` row) stays quiet too."""
    log = tmp_path / "governor_log.jsonl"
    governor.set_log_path(str(log))
    governor.reload_config()
    try:
        assert governor.provider_config("kie")["rps"] == 2.0
        assert governor.provider_config("deepseek-direct")["max_inflight"] == 400
    finally:
        governor.set_log_path("")
    rows = [json.loads(line) for line in
            log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []
    assert [r for r in rows if r.get("event") == "config-defaults"] == []


# ---------------------------------------------------------------------------
# 4. The profile adopts a declared new provider so the router can see it
# ---------------------------------------------------------------------------
def _plan_env(monkeypatch, tmp_path, profile):
    cfg = _cfg(monkeypatch, tmp_path, profile=profile)
    monkeypatch.delenv("PRESENTATION_MODEL_ROUTER", raising=False)
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    return cfg


_SEED_PROFILE = {
    ".schema_version": 1,
    "providers": {
        "deepseek-direct": {"provider": "deepseek-direct", "presence": True,
                            "wired_models": ["deepseek-flash"]},
    },
    "creative_prefs": {}, "consent": {}, "interview": {},
}


def test_record_model_plan_adopts_an_unknown_declared_provider(
        monkeypatch, tmp_path):
    """`_eligible` only routes to a provider the profile CARRIES, and only a
    probe ever put one there -- and the probe knows five providers. Adopting
    the client's declaration is what makes a new provider reachable without a
    code change."""
    cfg = _plan_env(monkeypatch, tmp_path, json.loads(json.dumps(_SEED_PROFILE)))
    prof = resource_profile.record_model_plan(
        {"workhorse": f"{NEW_MODEL}@{NEW_PROVIDER}"}, source="cli")
    entry = prof["providers"][NEW_PROVIDER]
    assert entry["client_declared"] is True, entry
    assert entry["presence"] is True, entry
    assert prof["model_plan"]["workhorse"] == {"provider": NEW_PROVIDER,
                                               "model": NEW_MODEL}
    # it survives the real save/load round trip, so the router reads it off disk
    reloaded = resource_profile.load_profile(cfg)
    assert NEW_PROVIDER in reloaded["providers"]
    ok, reason = model_router._eligible(
        reloaded["providers"], {"provider": NEW_PROVIDER, "model": NEW_MODEL})
    assert ok, reason


def test_record_model_plan_still_refuses_a_known_provider_the_probe_did_not_find(
        monkeypatch, tmp_path):
    """The control. ollama-cloud is a provider the probe CAN discover, so the
    profile's silence about it is evidence -- adoption must not swallow that
    refusal, or a typo would mint a provider."""
    _plan_env(monkeypatch, tmp_path, json.loads(json.dumps(_SEED_PROFILE)))
    with pytest.raises(ValueError) as exc:
        resource_profile.record_model_plan(
            {"workhorse": "glm-ocr@ollama-cloud"}, source="cli")
    assert "does not carry provider 'ollama-cloud'" in str(exc.value)


def test_record_model_plan_still_refuses_a_provider_less_profile(
        monkeypatch, tmp_path):
    """The other control: a plan naming only KNOWN providers on an empty
    profile is still refused, because there is nothing for adoption to
    legitimately speak for."""
    _plan_env(monkeypatch, tmp_path, {".schema_version": 1, "providers": {}})
    with pytest.raises(ValueError) as exc:
        resource_profile.record_model_plan(
            {"workhorse": "deepseek-flash@deepseek-direct"}, source="cli")
    assert "NO providers" in str(exc.value)
