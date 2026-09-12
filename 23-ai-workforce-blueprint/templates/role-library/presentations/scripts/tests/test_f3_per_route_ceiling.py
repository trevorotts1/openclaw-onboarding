#!/usr/bin/env python3
"""test_f3_per_route_ceiling.py -- ONE provider's plan answer is not every
route's ceiling.

THE DEFECT, MEASURED ON THE OPERATOR BOX 2026-09-07
---------------------------------------------------
`model_router.measured_client_ceiling(profile)` took `min()` over EVERY
provider's `concurrency_ceiling` in `resource_profile.json` and called the
result "the strictest measured ceiling wins". The live profile
(`~/.openclaw/state/presentation/resource_profile.json`) carried exactly two
numbers:

    ollama-cloud     plan_tier '$100/month'  concurrency_ceiling 8   locked
    deepseek-direct  (no plan tier)          concurrency_ceiling 100 declared

so the client-wide answer was **8**, `mode_ceiling('ultra')` was **8**, and
`capped_width(2500, 'ultra')` returned width **8**. Since v25.0.13 F6 that
number is the width of ALL NINE fan-out phases (dispatcher stamps it into
`routing.measured_capacity`, which `parallel_prompt_worker._workers_for`
honours verbatim). A DeepSeek-primary client who answered one question about
their Ollama plan had every DeepSeek route silently narrowed to 8.

THE FIX (plan section F3)
-------------------------
`measured_client_ceiling(profile, *, provider=None)`: WITH a provider, only
that provider's row is read (int -> int, "UNBOUNDED" -> "UNBOUNDED", absent
-> None). WITHOUT one, today's `min()` survives unchanged -- it is the
WHOLE-CLIENT FLOOR, and it is legitimate only for callers holding no route
(the launcher banner, `mode_concurrency`, the launch gate). `mode_ceiling`
and `capped_width` thread the provider through, and `resolve_route`
re-stamps `decision["mode_ceiling"]` with the provider of the route that
actually won -- which fixes every downstream `min()`, because `capped_width`
prefers the decision's block.

THE SPELLING TRAP, TESTED ON PURPOSE (section 2 below)
------------------------------------------------------
`resolve_alias`/the catalog return the SHORT form (`deepseek`); the profile
store and `capacity.normalize_provider` return the LONG form
(`deepseek-direct`), and `ollama_cloud`/`ollama-cloud` are one provider
spelled twice. An unfolded `providers.get(provider)` misses every real row
and answers `None` -- which reads as UNMEASURED and would look exactly like
a fix while changing nothing at all. Section 2 proves the fold in BOTH
directions.

WHAT THIS FILE DOES NOT TOUCH
-----------------------------
`ULTRA_OPERATOR_CEILING` (100) and `STANDARD_MODE_CEILING` (100) are the
OPERATOR's numbers. U3 restored standard to 100 after it was narrowed to 25
without approval; whether ultra may exceed 100 is not this fix's call.
Section 6 asserts both constants are unmoved.

WHICH ASSERTIONS ARE THE CATCH, AND WHICH ARE GUARDS
----------------------------------------------------
Sections 1-5 FAIL on pristine `eaedc0633` (the `provider=` keyword does not
exist there, and the whole-client `min()` answers 8 where a route wants
100). Sections 6-7 PASS on pristine main by design and are stated as such:
they are the regression guards for the two behaviours the fix must NOT
change (the no-arg meaning, and the operator constants).

Unit-level: no network, no spend, no deck, no render. The profile rig is
tests/test_u3_standard_ceiling_restored.py's / tests/test_fix11_mode_axis.py's,
deliberately -- same fixtures, so these files cannot drift into testing
different clients.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import model_router  # noqa: E402
from presentation_job import resource_profile  # noqa: E402


# ---------------------------------------------------------------------------
# rig (tests/test_u3_standard_ceiling_restored.py's, plus per-provider ceilings)
# ---------------------------------------------------------------------------
def _wired(provider, models, **extra):
    return dict({"provider": provider, "consented": True, "detected": True,
                 "presence": True, "wired_models": list(models)}, **extra)


def _two_provider_profile(deepseek_ceiling=100, ollama_ceiling=8):
    """THE LIVE OPERATOR-BOX SHAPE, from the four fields Fable measured.

    ollama-cloud carries a locked $100/month plan answer (ceiling 8);
    deepseek-direct carries a declared 100. Every authoring/prompt route in
    the catalog lands on deepseek-direct, so the ollama number has no
    business capping any of them."""
    prof = {
        ".schema_version": 1,
        "providers": {
            "deepseek-direct": _wired(
                "deepseek-direct", ["deepseek-flash", "deepseek-v4-pro"],
                concurrency_ceiling=deepseek_ceiling,
                ceiling_source="declared"),
            "ollama-cloud": _wired(
                "ollama-cloud", ["glm-ocr"],
                plan_tier="$100/month", plan_known=True, locked=True,
                concurrency_ceiling=ollama_ceiling,
                ceiling_source="cap-table"),
        },
        "creative_prefs": {}, "consent": {}, "interview": {},
    }
    return prof


def _env(monkeypatch, tmp_path, profile=None, mode=None):
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    monkeypatch.setenv("PRESENTATION_PROVIDER_PROBES", "0")
    for var in ("PRESENTATION_RESOURCE_PROFILE_DIR",
                "PRESENTATION_RESOURCE_PROFILE",
                "PRESENTATION_MODEL_ROUTER", "PRESENTATION_MODES",
                model_router.MODE_ENV):
        monkeypatch.delenv(var, raising=False)
    if mode is not None:
        monkeypatch.setenv(model_router.MODE_ENV, mode)
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    if profile is not None:
        (cfg / resource_profile.PROFILE_FILENAME).write_text(
            json.dumps(profile, indent=2), encoding="utf-8")
    return cfg


# ===========================================================================
# 1. THE PER-PROVIDER READ -- each provider answers with its OWN number
#    FAILS on pristine eaedc0633: measured_client_ceiling takes no
#    `provider` keyword there (TypeError), and its no-arg answer is 8.
# ===========================================================================
def test_measured_client_ceiling_with_a_provider_is_that_providers_own_number():
    prof = _two_provider_profile()
    assert model_router.measured_client_ceiling(
        prof, provider="deepseek-direct") == 100
    assert model_router.measured_client_ceiling(
        prof, provider="ollama-cloud") == 8
    # The two answers are DIFFERENT -- which is the whole point. A fix that
    # made every provider answer the same number would pass the two lines
    # above and still be the defect.
    assert model_router.measured_client_ceiling(prof, provider="deepseek-direct") \
        != model_router.measured_client_ceiling(prof, provider="ollama-cloud")


def test_a_provider_with_no_row_is_unmeasured_not_capped():
    """UNMEASURED is None, never the other provider's number and never a
    conservative floor dressed up as a reading. An absence is not a cap any
    more than it is a capability."""
    prof = _two_provider_profile()
    assert model_router.measured_client_ceiling(prof, provider="openrouter") is None
    assert model_router.measured_client_ceiling(prof, provider="kie") is None
    # ... and a provider row carrying no ceiling at all reads the same way.
    prof["providers"]["openrouter"] = _wired("openrouter", ["z-ai/glm-5.3"])
    assert model_router.measured_client_ceiling(prof, provider="openrouter") is None


def test_unbounded_stays_unbounded_per_provider():
    """U1's ruling, per route: an UNBOUNDED client is never coerced to a
    number -- least of all to the OTHER provider's 8."""
    prof = _two_provider_profile()
    prof["providers"]["deepseek-direct"]["concurrency_ceiling"] = "UNBOUNDED"
    assert model_router.measured_client_ceiling(
        prof, provider="deepseek-direct") == "UNBOUNDED"
    assert model_router.measured_client_ceiling(
        prof, provider="ollama-cloud") == 8
    # UNBOUNDED never lifts the OPERATOR's ceiling either.
    assert model_router.mode_ceiling(
        "ultra", profile=prof, provider="deepseek-direct")["ceiling"] == \
        model_router.ULTRA_OPERATOR_CEILING


def test_a_malformed_ceiling_reads_as_unmeasured_never_as_a_higher_width():
    prof = _two_provider_profile()
    for bad in (0, -1, "8", 3.5, True, None, [], {}):
        prof["providers"]["deepseek-direct"]["concurrency_ceiling"] = bad
        got = model_router.measured_client_ceiling(
            prof, provider="deepseek-direct")
        assert got is None, (bad, got)


# ===========================================================================
# 2. THE SPELLING FOLD -- the trap that would have made this fix a no-op
#    FAILS on pristine eaedc0633 (no `provider` keyword).
# ===========================================================================
def test_the_catalogs_short_spelling_finds_the_stores_long_row():
    """`resolve_alias('deepseek-flash')` may hand back `deepseek`; the
    profile writes `deepseek-direct`. If the lookup did not fold, this would
    answer None -- 'unmeasured' -- and the ceiling would silently become the
    operator's 100 for a reason that has nothing to do with the client."""
    prof = _two_provider_profile()
    assert model_router.measured_client_ceiling(prof, provider="deepseek") == 100
    assert model_router.measured_client_ceiling(prof, provider="DeepSeek") == 100
    assert model_router.measured_client_ceiling(prof, provider="ollama_cloud") == 8
    assert model_router.measured_client_ceiling(prof, provider="Ollama Cloud") == 8


def test_the_fold_works_in_the_other_direction_too():
    """A profile written under the SHORT spelling (a pre-normalisation row --
    `_eligible` already tolerates these) asked about under the LONG one."""
    prof = {"providers": {"deepseek": {"concurrency_ceiling": 2500}}}
    assert model_router.measured_client_ceiling(
        prof, provider="deepseek-direct") == 2500


def test_the_fold_is_never_evidence_that_a_provider_exists():
    """Folding a name is spelling hygiene, not presence. An unknown provider
    is still unmeasured."""
    prof = _two_provider_profile()
    assert model_router.measured_client_ceiling(
        prof, provider="acme-llm-9000") is None


# ===========================================================================
# 3. mode_ceiling AND capped_width THREAD THE PROVIDER
#    THE LIVE-BOX REPRODUCTION. On pristine eaedc0633 the last assertion of
#    the first test reads 8, which is the defect.
# ===========================================================================
def test_mode_ceiling_is_the_routed_providers_ceiling():
    prof = _two_provider_profile()
    # what the box did BEFORE the fix, still available to callers with no route
    assert model_router.mode_ceiling("ultra", profile=prof)["ceiling"] == 8
    # what a DeepSeek route gets now
    block = model_router.mode_ceiling("ultra", profile=prof,
                                      provider="deepseek-direct")
    assert block["ceiling"] == 100
    assert block["measured_ceiling"] == 100
    assert block["ceiling_provider"] == "deepseek-direct"
    # and an Ollama route still gets its real 8 -- the reserve holds
    assert model_router.mode_ceiling(
        "ultra", profile=prof, provider="ollama-cloud")["ceiling"] == 8


def test_capped_width_2500_ultra_is_100_on_a_deepseek_route():
    """THE EXACT NUMBER FABLE MEASURED. capped_width(2500, 'ultra') returned
    width 8 on the live box; on a DeepSeek route it is 100 -- the operator
    ceiling, never provider advertising."""
    prof = _two_provider_profile()
    assert model_router.capped_width(2500, "ultra", profile=prof)["width"] == 8
    cut = model_router.capped_width(2500, "ultra", profile=prof,
                                    provider="deepseek-direct")
    assert cut["width"] == 100
    assert cut["capped"] is True
    assert model_router.capped_width(
        2500, "ultra", profile=prof, provider="ollama-cloud")["width"] == 8


def test_a_cap_still_only_ever_narrows():
    """Per-route or not, this is a min(): a route whose provider measures 3
    runs 3 under ultra. The fix must not turn a ceiling into a target."""
    prof = _two_provider_profile(deepseek_ceiling=3)
    assert model_router.capped_width(
        2500, "ultra", profile=prof, provider="deepseek-direct")["width"] == 3
    assert model_router.capped_width(
        3, "ultra", profile=prof, provider="deepseek-direct")["width"] == 3


def test_standard_is_capped_the_same_way_as_ultra():
    """U3 left standard at the operator's 100. The per-route read must not
    quietly re-narrow it (nor widen it)."""
    prof = _two_provider_profile()
    for mode in ("ultra", "standard"):
        assert model_router.mode_ceiling(
            mode, profile=prof, provider="deepseek-direct")["ceiling"] == 100


def test_an_unknown_mode_is_still_refused_with_a_provider():
    for kwargs in ({}, {"provider": "deepseek-direct"}):
        try:
            model_router.mode_ceiling("turbo", profile=_two_provider_profile(),
                                      **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"mode_ceiling accepted an unknown mode {kwargs}")


# ===========================================================================
# 4. resolve_route RE-STAMPS THE CEILING FOR THE ROUTE THAT WON
#    This is the line that fixes every downstream min(), because
#    capped_width() prefers decision["mode_ceiling"] and the dispatcher's
#    routing stamp passes decision=.
#    FAILS on pristine eaedc0633: the stamp is the whole-client 8.
# ===========================================================================
def test_the_decision_carries_the_routed_providers_ceiling(monkeypatch, tmp_path):
    prof = _two_provider_profile()
    _env(monkeypatch, tmp_path, prof, mode="ultra")
    decision = model_router.resolve_route("P4-COPY")
    assert decision["route"] is not None, decision
    assert model_router._norm_provider(decision["route"]["provider"]) == \
        "deepseek-direct", decision["route"]
    assert decision["mode_ceiling"]["ceiling"] == 100, decision["mode_ceiling"]
    assert decision["mode_ceiling"]["ceiling_provider"] == \
        decision["route"]["provider"]


def test_the_stamped_decision_is_what_narrows_the_wave(monkeypatch, tmp_path):
    """dispatcher._routing_stamp calls capped_width(..., decision=decision)
    -- exactly this shape. 2,500 measured, ultra, DeepSeek route -> 100."""
    prof = _two_provider_profile()
    _env(monkeypatch, tmp_path, prof, mode="ultra")
    decision = model_router.resolve_route("P4-PROMPT")
    cut = model_router.capped_width(2500, "ultra", decision=decision)
    assert cut["width"] == 100, cut


def test_a_route_on_the_low_provider_still_gets_its_own_low_ceiling(
        monkeypatch, tmp_path):
    """ANTI-VACUITY. If the fix simply stopped applying client ceilings, the
    two tests above would pass and the operator's Ollama reserve would be
    gone. A phase that really routes to ollama-cloud must still read 8."""
    prof = _two_provider_profile()
    # P-IMAGE-QC is vision_ocr: [deepseek-v4-pro, glm-5.3, glm-ocr]. Strip
    # DeepSeek (and never add OpenRouter) so the only eligible candidate left
    # is glm-ocr, whose provider IS ollama-cloud.
    prof["providers"].pop("deepseek-direct")
    prof["providers"]["ollama-cloud"]["wired_models"] = ["glm-ocr"]
    _env(monkeypatch, tmp_path, prof, mode="ultra")
    decision = model_router.resolve_route("P-IMAGE-QC")
    assert decision["route"] is not None, \
        f"no ollama-cloud route resolved -- {decision.get('reason')}"
    assert model_router._norm_provider(decision["route"]["provider"]) == \
        "ollama-cloud", decision["route"]
    assert decision["mode_ceiling"]["ceiling"] == 8, decision["mode_ceiling"]
    assert model_router.capped_width(2500, "ultra", decision=decision)["width"] == 8


def test_a_parked_phase_keeps_the_whole_client_floor(monkeypatch, tmp_path):
    """No route means no per-route answer exists. The client-level cap is the
    only honest number left -- it is not deleted, and it is not invented."""
    prof = _two_provider_profile()
    _env(monkeypatch, tmp_path, prof, mode="ultra")
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: False)
    decision = model_router.resolve_route("P4-COPY")
    assert decision["route"] is None, decision
    assert decision["mode_ceiling"]["ceiling"] == 8
    assert decision["mode_ceiling"]["ceiling_provider"] is None


# ===========================================================================
# 5. THE WHOLE-CLIENT FLOOR IS STILL THERE, AND IT IS NAMED HONESTLY
#    The min() is not deleted -- the launch gate, the launcher banner and
#    mode_concurrency have no route to ask about.
#    The docstring assertion FAILS on pristine eaedc0633, which says "The
#    strictest measured ceiling wins".
# ===========================================================================
def test_the_no_arg_call_is_documented_as_the_whole_client_floor():
    doc = (model_router.measured_client_ceiling.__doc__ or "")
    assert "strictest measured ceiling wins" not in doc, (
        "the no-arg min() is the WHOLE-CLIENT FLOOR, for callers holding no "
        "route -- calling it 'the strictest ceiling wins' is the reading "
        "that made one provider's plan answer cap every route")
    assert "WHOLE-CLIENT FLOOR" in doc


def test_mode_concurrency_is_deliberately_left_whole_client():
    """The launcher banner and .mode-plan.json describe the CLIENT, not one
    route. F3 does not change that signature."""
    prof = _two_provider_profile()
    assert model_router.mode_concurrency(
        "ultra", profile=prof)["concurrency"] == 8


# ===========================================================================
# 6. REGRESSION GUARDS -- these PASS on pristine eaedc0633 BY DESIGN.
#    They exist to prove the fix changed nothing it was not asked to change.
# ===========================================================================
def test_the_no_arg_meaning_is_byte_identical_to_before():
    """PASSES ON MAIN. Stated so no reader mistakes it for a catch."""
    prof = _two_provider_profile()
    assert model_router.measured_client_ceiling(prof) == 8
    assert model_router.measured_client_ceiling(None) is None
    assert model_router.measured_client_ceiling({}) is None
    assert model_router.measured_client_ceiling({"providers": {}}) is None
    unb = {"providers": {"a": {"concurrency_ceiling": "UNBOUNDED"}}}
    assert model_router.measured_client_ceiling(unb) == "UNBOUNDED"
    mixed = {"providers": {"a": {"concurrency_ceiling": "UNBOUNDED"},
                           "b": {"concurrency_ceiling": 5}}}
    assert model_router.measured_client_ceiling(mixed) == 5


def test_the_operator_constants_are_not_this_fixs_to_move():
    """PASSES ON MAIN. U3 restored standard to 100 this morning after it was
    narrowed to 25 without approval; whether ultra may exceed 100 is an
    OPERATOR decision and explicitly not F3's."""
    assert model_router.ULTRA_OPERATOR_CEILING == 100
    assert model_router.STANDARD_MODE_CEILING == 100
    assert model_router.MODE_OPERATOR_CEILING["ultra"] == 100
    assert model_router.MODE_OPERATOR_CEILING["standard"] == 100


# ===========================================================================
# 7. THE SIGNATURES THE OTHER LANES WERE PROMISED
#    PASSES ON MAIN only for the no-arg halves; the keyword-only checks are
#    the catch.
# ===========================================================================
def test_the_agreed_signatures_are_keyword_only_and_no_arg_safe():
    """Existing tests stub these with fixed-arity lambdas, and three
    production callers call them positionally-free. `provider` must be
    KEYWORD-ONLY, and every no-arg/one-arg call must keep today's meaning."""
    import inspect
    for fn, first in ((model_router.measured_client_ceiling, "profile"),
                      (model_router.mode_ceiling, "mode"),
                      (model_router.capped_width, "width")):
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        assert params[0].name == first, (fn.__name__, params[0].name)
        prov = sig.parameters.get("provider")
        assert prov is not None, f"{fn.__name__} has no provider keyword"
        assert prov.kind is inspect.Parameter.KEYWORD_ONLY, \
            f"{fn.__name__}: provider must be keyword-only"
        assert prov.default is None, f"{fn.__name__}: provider must default None"
    prof = _two_provider_profile()
    # positional first argument still works everywhere it did
    assert model_router.measured_client_ceiling(prof) == 8
    assert model_router.mode_ceiling("ultra", profile=prof)["ceiling"] == 8
    assert model_router.capped_width(2500, "ultra", profile=prof)["width"] == 8
