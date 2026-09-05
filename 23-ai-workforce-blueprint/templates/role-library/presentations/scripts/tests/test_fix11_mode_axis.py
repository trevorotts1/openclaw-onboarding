#!/usr/bin/env python3
"""test_fix11_mode_axis.py -- the Ultra/Standard/Economy axis is WIRED.

FIX 11's policy layer already existed and is deliberate: ULTRA_OPERATOR_CEILING
(100), DEFAULT_CONSERVATIVE_FLOOR (3), STANDARD_WORKER_DEFAULT (8), MODES,
mode_concurrency(), _mode_candidates(), ECONOMY_FLASH_REPOINT, stability_window
-- all in model_router.py, all under a binding comment. The DOOR existed too:
launcher.py has carried `--mode ultra|standard|economy` since FIX 11 landed,
and it exported the choice into the engine as PRESENTATION_MODE
(launcher.py:1433). What never existed was the READ. Three wires, all inside
the engine:

  1. NOTHING in the engine ever read PRESENTATION_MODE. The launcher's mode
     reached a sidecar and an environment variable and stopped there;
  2. dispatcher.dispatch_complete called resolve_route(phase_id) with no mode,
     so every routed LLM call resolved at the signature default;
  3. dispatcher._prompt_routing_stamp hardcoded mode="standard" -- at the ONE
     place the engine actually decides a fan-out width.

  Measured on pristine main: with PRESENTATION_MODE=ultra in the engine's
  environment (exactly what launcher.dispatch hands it) and a client measured
  at 2,500, resolve_route reported mode "standard" and the P4-PROMPT wave ran
  2,500 wide -- the 100-task operator ceiling never applied to anything.

THE CANONICAL ENTRY SCRIPT IS DELIBERATELY NOT A RUN-MODE DOOR. That is a
stated design decision, written as an executable assertion with its own
rationale in tests/test_fix36_intake_depth.py ("the run-mode axis must never be
a canonical-entry flag", "which the canonical entry must not expose"). Nothing
in this file touches that script or that test. The run-mode door is the
launcher, and the environment variable it exports is the seam. A deck built
through the canonical entry script therefore runs standard unless
PRESENTATION_MODE is already exported in the calling environment; that path is
NOT covered here, because reaching the entry script's dispatch line needs a
completed intake interview or a logged owner waiver, and no test in this file
fabricates a waiver token to make a proof pass.

This file pins the wires, and the policy they now carry. Unit-level: no
network, no spend, no deck, no render. Every profile is written into a tmp
config dir the capacity/profile env points at (the test_model_plan.py rig); the
launcher tests spawn a real child interpreter that is a one-line stub.

THE CEILING IS A CAP, NEVER A FLOOR AND NEVER A TARGET. Every assertion about
100 below is an upper bound: a client measured at 3 runs 3 in Ultra, and a
client measured at 2,500 runs 100 -- never the reverse.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import dispatcher  # noqa: E402
from presentation_job import launcher  # noqa: E402
from presentation_job import model_router  # noqa: E402
from presentation_job import resource_profile  # noqa: E402


# ---------------------------------------------------------------------------
# rig (mirrors tests/test_model_plan.py)
# ---------------------------------------------------------------------------
def _wired(provider, models, **extra):
    return dict({"provider": provider, "consented": True, "detected": True,
                 "presence": True, "wired_models": list(models)}, **extra)


def _profile(ceiling=None, plan=None):
    prof = {
        ".schema_version": 1,
        "providers": {
            "deepseek-direct": _wired("deepseek-direct",
                                      ["deepseek-v4-flash", "deepseek-v4-pro"]),
            "openrouter": _wired("openrouter",
                                 ["z-ai/glm-5.3-flash", "z-ai/glm-5.3"]),
        },
        "creative_prefs": {}, "consent": {}, "interview": {},
    }
    if ceiling is not None:
        for entry in prof["providers"].values():
            entry["concurrency_ceiling"] = ceiling
    if plan is not None:
        prof["model_plan"] = plan
    return prof


def _env(monkeypatch, tmp_path, profile=None, mode=None):
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    for var in ("PRESENTATION_RESOURCE_PROFILE_DIR",
                "PRESENTATION_RESOURCE_PROFILE",
                "PRESENTATION_MODEL_ROUTER", "PRESENTATION_MODES",
                model_router.MODE_ENV):
        monkeypatch.delenv(var, raising=False)
    if mode is not None:
        monkeypatch.setenv(model_router.MODE_ENV, mode)
    # Selection, not credentials: the FIX 114 key gate is satisfied for every
    # provider and no real key is ever read.
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    if profile is not None:
        (cfg / resource_profile.PROFILE_FILENAME).write_text(
            json.dumps(profile, indent=2), encoding="utf-8")
    return cfg


def _models(decision):
    """The candidate list BY MODEL ID.

    Not by "alias": a candidate row is {"alias": requested, **alias_def} and a
    catalog row carries its OWN "alias" label ("text.fast"), which wins the
    splat -- so a default row's `alias` reads as the catalog label, never as
    the requested one. The model id is the unambiguous identity."""
    return [c.get("model") for c in decision.get("candidates") or []]


#: The provider spelling the CATALOG hands back for the deepseek aliases
#: ("deepseek", which _norm_provider folds to "deepseek-direct"). Derived, not
#: hardcoded, so a catalog respelling cannot make these fixtures quietly stop
#: matching the routed provider the stamp compares against.
_DS_PROVIDER = model_router.resolve_alias("deepseek-v4-flash")["provider"]


#: A default table whose primary for the Economy-covered classes is NOT the
#: cheap model, so the re-point is OBSERVABLE. See
#: test_shipped_table_makes_the_economy_repoint_a_noop for why this is needed:
#: on the shipped table deepseek-v4-flash is ALREADY first for both covered
#: classes, so Economy's re-point changes nothing there. These tests pin the
#: MECHANISM; that test pins the shipped-table fact beside it, so neither is
#: ever mistaken for the other.
_PRO_FIRST = [{"alias": "deepseek-v4-pro", "allow_flash_fallback": False},
              {"alias": "glm-5.3"}]


def _pro_first_table(monkeypatch):
    for cls in model_router.ECONOMY_FLASH_REPOINT:
        monkeypatch.setitem(model_router.CAPABILITY_CANDIDATES, cls,
                            copy.deepcopy(_PRO_FIRST))


# ===========================================================================
# 1. THE RESOLUTION ORDER: explicit > PRESENTATION_MODE > standard
# ===========================================================================
def test_resolution_order_is_explicit_then_env_then_standard(monkeypatch):
    monkeypatch.delenv(model_router.MODE_ENV, raising=False)
    assert model_router.active_mode() == "standard"
    assert model_router.active_mode("Ultra") == "ultra"
    monkeypatch.setenv(model_router.MODE_ENV, "Economy")
    assert model_router.active_mode() == "economy"
    assert model_router.active_mode("Ultra") == "ultra", \
        "an explicit declaration must beat the inherited env"


def test_default_is_standard_and_nobody_lands_in_ultra_by_accident(monkeypatch,
                                                                   tmp_path):
    """No flag, no env -> standard. Asserted at BOTH layers: the resolver and
    a real routing decision."""
    _env(monkeypatch, tmp_path, _profile())
    assert model_router.active_mode() == "standard"
    assert model_router.DEFAULT_MODE == "standard"
    decision = model_router.resolve_route("P4-COPY")
    assert decision["mode"] == "standard", decision
    assert decision["mode"] != "ultra"


def test_empty_env_is_unset_never_a_selection(monkeypatch):
    monkeypatch.setenv(model_router.MODE_ENV, "   ")
    assert model_router.active_mode() == "standard"


def test_unknown_mode_is_refused_never_coerced(monkeypatch):
    monkeypatch.setenv(model_router.MODE_ENV, "turbo")
    try:
        model_router.active_mode()
    except ValueError as exc:
        assert "turbo" in str(exc)
    else:  # pragma: no cover - the failure this asserts against
        raise AssertionError("an unknown mode was silently coerced")
    # strict=False is the in-engine path: standard, never a guess upward.
    assert model_router.active_mode(strict=False) == "standard"


# ===========================================================================
# 2. THE MODE REACHES ROUTING
# ===========================================================================
def test_the_env_mode_reaches_a_routing_decision(monkeypatch, tmp_path):
    """WIRE 2+3: PRESENTATION_MODE is READ. resolve_route was called with no
    mode by dispatch_complete/heal/credit_preflight, so before this fix every
    decision carried the signature default no matter what was declared."""
    for want in model_router.MODES:
        _env(monkeypatch, tmp_path, _profile(), mode=want)
        decision = model_router.resolve_route("P4-COPY")
        assert decision["mode"] == want, decision


def test_economy_repoints_only_under_economy(monkeypatch, tmp_path):
    """PROOF 2 (mechanism): the same class, the same profile, three modes."""
    _pro_first_table(monkeypatch)
    seen = {}
    for want in model_router.MODES:
        _env(monkeypatch, tmp_path, _profile(), mode=want)
        _pro_first_table(monkeypatch)
        decision = model_router.resolve_route("P4-COPY")
        seen[want] = (decision["route"], _models(decision))
    assert seen["economy"][1][0] == "deepseek-v4-flash", seen["economy"]
    assert seen["economy"][0]["model"] == "deepseek-v4-flash", seen["economy"]
    for other in ("ultra", "standard"):
        assert seen[other][1][0] == "deepseek-v4-pro", seen[other]
        assert seen[other][0]["model"] == "deepseek-v4-pro", seen[other]
    assert "deepseek-v4-flash" not in seen["ultra"][1], seen["ultra"]


def test_shipped_table_makes_the_economy_repoint_a_noop():
    """THE HONEST FACT beside the mechanism test above: on the table this repo
    actually ships, ECONOMY_FLASH_REPOINT changes NOTHING, because
    deepseek-v4-flash is already the primary candidate of both classes it
    covers. Economy's real teeth today are its concurrency/cost width, not a
    model swap. If a later table change makes the re-point bite, the mechanism
    test above already pins it -- and this assertion will fail loudly rather
    than let the no-op be discovered in production."""
    for cls in model_router.ECONOMY_FLASH_REPOINT:
        base = [c["alias"] for c in model_router.CAPABILITY_CANDIDATES[cls]]
        assert base[0] == "deepseek-v4-flash", (
            f"{cls}'s primary is no longer the cheap model ({base}); the "
            "Economy re-point now changes the shipped route -- update this "
            "test deliberately, do not delete it")
        assert model_router._mode_candidates(cls, "economy") == \
            model_router._mode_candidates(cls, "standard")


def test_classes_outside_the_repoint_map_are_untouched_in_every_mode(monkeypatch,
                                                                     tmp_path):
    """The modality doctrine holds by construction: reasoning/long-synthesis/
    vision/image classes simply do not appear in ECONOMY_FLASH_REPOINT, so no
    mode can drop them to Flash."""
    for cls in ("reasoning_long", "judge", "vision_ocr", "image_render"):
        assert cls not in model_router.ECONOMY_FLASH_REPOINT
        base = model_router.CAPABILITY_CANDIDATES[cls]
        for want in model_router.MODES:
            assert model_router._mode_candidates(cls, want) == base


# ===========================================================================
# 3. THE CEILING IS A CAP, NEVER A FLOOR AND NEVER A TARGET
# ===========================================================================
def test_a_client_measured_at_3_stays_3_under_ultra():
    assert model_router.mode_ceiling("ultra",
                                     profile=_profile(ceiling=3))["ceiling"] == 3
    assert model_router.capped_width(3, "ultra",
                                     profile=_profile(ceiling=3))["width"] == 3
    # and Ultra never RAISES that 3 toward the operator ceiling
    plan = model_router.mode_concurrency("ultra", profile=_profile(ceiling=3))
    assert plan["concurrency"] == 3, plan


def test_a_client_measured_at_2500_is_capped_at_100_under_ultra():
    prof = _profile(ceiling=2500)
    assert model_router.mode_ceiling("ultra", profile=prof)["ceiling"] == 100
    assert model_router.capped_width(2500, "ultra", profile=prof)["width"] == 100
    assert model_router.mode_concurrency("ultra", profile=prof)["concurrency"] == 100
    assert model_router.ULTRA_OPERATOR_CEILING == 100


def test_no_mode_exceeds_the_same_client_provider_ceiling():
    """"Standard and Economy ... may never exceed the same client/provider
    ceiling" -- the binding text, asserted for all three modes."""
    for prof, expected in ((_profile(ceiling=2500), 100),
                           (_profile(ceiling=3), 3),
                           (_profile(), 100)):
        for want in model_router.MODES:
            cap = model_router.capped_width(9999, want, profile=prof)
            assert cap["width"] <= expected, (want, cap)
            assert cap["width"] <= model_router.ULTRA_OPERATOR_CEILING


def test_the_ceiling_never_widens_a_measured_width():
    """A cap can only ever narrow. Ultra does not lift a measured 2 to 100."""
    for want in model_router.MODES:
        for measured in (1, 2, 8, 99):
            cap = model_router.capped_width(measured, want,
                                            profile=_profile(ceiling=2500))
            assert cap["width"] <= measured, (want, measured, cap)


def test_provider_advertising_never_raises_the_operator_ceiling():
    """An UNBOUNDED (bring-your-own) client does not get 2,500 concurrent
    tasks in Ultra: the human-ratified 100 still applies."""
    prof = _profile(ceiling="UNBOUNDED")
    assert model_router.measured_client_ceiling(prof) == "UNBOUNDED"
    assert model_router.mode_ceiling("ultra", profile=prof)["ceiling"] == 100
    assert model_router.capped_width(2500, "ultra", profile=prof)["width"] == 100


# ===========================================================================
# 4. THE CEILING IS APPLIED WHERE THE WIDTH IS ACTUALLY DECIDED
# ===========================================================================
def _stamp(monkeypatch, tmp_path, *, mode, probe_available, ceiling=None):
    _env(monkeypatch, tmp_path, _profile(ceiling=ceiling), mode=mode)
    monkeypatch.setattr(capacity, "probe", lambda *a, **k: {
        "available": probe_available, "provider": _DS_PROVIDER,
        "status": "measured", "detection_source": "test-fixture"})
    return dispatcher._prompt_routing_stamp(run_dir=tmp_path)


def test_the_prompt_wave_stamp_carries_the_real_mode(monkeypatch, tmp_path):
    """WIRE 4: this stamp hardcoded mode="standard" -- at the one place the
    engine decides a fan-out width. routing.measured_capacity IS the worker
    slot count (parallel_prompt_worker._workers_for honours it verbatim)."""
    for want in model_router.MODES:
        stamp = _stamp(monkeypatch, tmp_path, mode=want, probe_available=8)
        assert stamp["mode"] == want, stamp
        assert stamp["mode_source"] == model_router.MODE_ENV, stamp


def test_the_wave_width_is_capped_at_100_not_2500(monkeypatch, tmp_path):
    stamp = _stamp(monkeypatch, tmp_path, mode="ultra", probe_available=2500,
                   ceiling=2500)
    assert stamp["measured_capacity"] == 100, stamp
    assert stamp["mode_cap"]["capped"] is True
    assert "mode-capped" in stamp["capacity_status"]


def test_the_wave_width_of_a_client_measured_at_3_stays_3(monkeypatch, tmp_path):
    stamp = _stamp(monkeypatch, tmp_path, mode="ultra", probe_available=3,
                   ceiling=3)
    assert stamp["measured_capacity"] == 3, stamp


def test_ultra_never_widens_the_wave_beyond_what_was_measured(monkeypatch,
                                                              tmp_path):
    """The ceiling is not a target: a box that measured 8 runs 8 in Ultra."""
    stamp = _stamp(monkeypatch, tmp_path, mode="ultra", probe_available=8,
                   ceiling="UNBOUNDED")
    assert stamp["measured_capacity"] == 8, stamp
    assert stamp["mode_cap"]["capped"] is False


def test_standard_default_wave_width_is_unchanged_by_this_fix(monkeypatch,
                                                              tmp_path):
    """NO REGRESSION: the default path (no mode declared anywhere) keeps the
    width it had. The mode ceiling only ever cuts a width ABOVE the operator
    ceiling -- it never re-clamps a measured width down to the 8-wide worker
    default, which is the behaviour the operator ruled out on 2026-09-04."""
    for probe in (8, 24, 100):
        _env(monkeypatch, tmp_path, _profile())
        monkeypatch.setattr(capacity, "probe", (
            lambda _p: lambda *a, **k: {
                "available": _p, "provider": _DS_PROVIDER,
                "status": "measured", "detection_source": "test-fixture"})(probe))
        stamp = dispatcher._prompt_routing_stamp(run_dir=tmp_path)
        assert stamp["mode"] == "standard"
        assert stamp["measured_capacity"] == probe, stamp


def test_dispatcher_active_mode_reads_the_env_and_degrades_loudly(monkeypatch):
    monkeypatch.delenv(model_router.MODE_ENV, raising=False)
    assert dispatcher._active_mode() == ("standard", "default")
    monkeypatch.setenv(model_router.MODE_ENV, "Ultra")
    assert dispatcher._active_mode() == ("ultra", model_router.MODE_ENV)
    monkeypatch.setenv(model_router.MODE_ENV, "turbo")
    mode, source = dispatcher._active_mode()
    assert mode == "standard", "a bad env must never widen a run"
    assert "invalid" in source, source  # never silent


# ===========================================================================
# 5. THE CLIENT'S EXPLICIT CHOICE OUTRANKS ECONOMY'S COST RE-POINT
# ===========================================================================
_CLIENT_GLM = {"provider": "openrouter", "model": "z-ai/glm-5.3"}


def test_a_declared_workhorse_is_not_overridden_by_economy(monkeypatch,
                                                           tmp_path):
    """Operator requirement 2026-09-04: "I don't want to be forced to do
    anything." Economy is a cost preference; a model plan is the client's own
    choice about their own account. The choice wins."""
    _env(monkeypatch, tmp_path,
         _profile(plan={"workhorse": _CLIENT_GLM, "reasoning": None,
                        "judge": None, "floor_waivers": []}),
         mode="economy")
    _pro_first_table(monkeypatch)
    decision = model_router.resolve_route("P4-COPY")
    assert decision["mode"] == "economy"
    assert decision["route"] == {"provider": "openrouter",
                                 "model": "z-ai/glm-5.3"}, decision
    assert decision["client_plan"]["applied"] is True
    # and Economy did not reorder the fallbacks behind the client's row either
    assert _models(decision)[:2] == ["z-ai/glm-5.3", "deepseek-v4-pro"], decision
    assert "deepseek-v4-flash" not in _models(decision), decision
    assert "suppressed" in decision["client_plan"]["economy_repoint"]


def test_an_undeclared_class_still_repoints_under_economy(monkeypatch,
                                                          tmp_path):
    """The other half of the ruling: Economy still governs every class the
    client left to the department. This client declared only a judge."""
    _env(monkeypatch, tmp_path,
         _profile(plan={"workhorse": None, "reasoning": None,
                        "judge": _CLIENT_GLM, "floor_waivers": []}),
         mode="economy")
    _pro_first_table(monkeypatch)
    decision = model_router.resolve_route("P4-COPY")   # authoring: undeclared
    assert decision.get("client_plan") is None, decision
    assert _models(decision)[0] == "deepseek-v4-flash", decision
    assert decision["route"]["model"] == "deepseek-v4-flash", decision


def test_a_floor_failed_declaration_does_not_govern_the_class(monkeypatch,
                                                              tmp_path):
    """A declaration below its class floor and not waived is NOT in force --
    the department default is serving that class, so Economy's cost policy
    applies to it exactly as for a client who declared nothing. The fallback
    is still on the record (client_plan_floor), never a silent swap."""
    _env(monkeypatch, tmp_path,
         _profile(plan={"workhorse": None,
                        "reasoning": {"provider": "deepseek-direct",
                                      "model": "deepseek-v4-flash"},
                        "judge": None, "floor_waivers": []}),
         mode="economy")
    decision = model_router.resolve_route("P3-ARC")   # reasoning_long
    assert decision.get("client_plan") is None
    assert decision["client_plan_floor"]["slot"] == "reasoning", decision


def test_client_precedence_holds_in_every_mode(monkeypatch, tmp_path):
    for want in model_router.MODES:
        _env(monkeypatch, tmp_path,
             _profile(plan={"workhorse": _CLIENT_GLM, "reasoning": None,
                            "judge": None, "floor_waivers": []}),
             mode=want)
        decision = model_router.resolve_route("P4-COPY")
        assert decision["route"] == {"provider": "openrouter",
                                     "model": "z-ai/glm-5.3"}, (want, decision)


# ===========================================================================
# 6. THE MUTATION TRAP
# ===========================================================================
def test_the_default_table_survives_50_resolves_across_all_three_modes(
        monkeypatch, tmp_path):
    """_mode_candidates used to hand back the LIVE CAPABILITY_CANDIDATES list
    object for every non-Economy mode; any caller mutating it corrupted the
    department default process-wide -- every later phase, every other client
    in the same process, permanently."""
    before = copy.deepcopy(model_router.CAPABILITY_CANDIDATES)
    ids_before = {k: id(v) for k, v in model_router.CAPABILITY_CANDIDATES.items()}
    for i in range(50):
        want = model_router.MODES[i % len(model_router.MODES)]
        _env(monkeypatch, tmp_path,
             _profile(plan={"workhorse": _CLIENT_GLM, "reasoning": None,
                            "judge": _CLIENT_GLM, "floor_waivers": []}),
             mode=want)
        for phase in ("P4-COPY", "P4-PROMPT", "P1Q-COPY-QC", "P3-ARC"):
            model_router.resolve_route(phase)
    assert model_router.CAPABILITY_CANDIDATES == before
    assert {k: id(v) for k, v in
            model_router.CAPABILITY_CANDIDATES.items()} == ids_before


def test_mode_candidates_hands_back_a_fresh_list_and_fresh_rows():
    """The copy lives in _mode_candidates now, so the NEXT caller cannot make
    this mistake either -- not only resolve_route, which copied defensively."""
    for cls in ("authoring", "judge", "reasoning_long"):
        for want in model_router.MODES:
            got = model_router._mode_candidates(cls, want)
            assert got is not model_router.CAPABILITY_CANDIDATES[cls]
            for i, row in enumerate(got):
                if i < len(model_router.CAPABILITY_CANDIDATES[cls]):
                    assert row is not model_router.CAPABILITY_CANDIDATES[cls][i]
            got.append({"alias": "poison"})
            got[0]["alias"] = "poisoned"
            assert all(c.get("alias") not in ("poison", "poisoned")
                       for c in model_router.CAPABILITY_CANDIDATES[cls])


# ===========================================================================
# 7. THE ROLLBACK FLAG STILL TURNS THE WHOLE SURFACE INERT
# ===========================================================================
def test_presentation_modes_0_leaves_the_surface_inert(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, _profile(ceiling=2500), mode="economy")
    monkeypatch.setenv(model_router.MODE_FLAG_ENV, "0")
    assert model_router.modes_enabled() is False
    decision = model_router.resolve_route("P4-COPY")
    # the env mode is NOT read, no concurrency/ceiling stamps, no re-point
    assert decision["mode"] == "standard", decision
    assert "mode_concurrency" not in decision
    assert "mode_ceiling" not in decision
    assert model_router._mode_candidates("authoring", "economy") == \
        [dict(c) for c in model_router.CAPABILITY_CANDIDATES["authoring"]]


# ===========================================================================
# 8. THE MODE IS VISIBLE: banner, run record, and the engine's own env
# ===========================================================================
def _stub_engine(monkeypatch, tmp_path):
    """The test_capacity_detection.py rig: a REAL child interpreter runs a
    one-line stub presentation_job.py, so "the engine was spawned with this
    env" is proven by a process that actually ran -- not by mocking Popen.
    The stub writes whatever PRESENTATION_MODE it received into a marker."""
    monkeypatch.setattr(capacity, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(capacity, "HARNESS_SETTINGS_CANDIDATES",
                        (tmp_path / "absent-settings.json",))
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", "/usr/bin/true")
    monkeypatch.setattr(capacity, "measure_working_concurrent",
                        lambda: (0, "stub", True))
    monkeypatch.setattr(launcher, "resolve_scripts_dir", lambda: tmp_path)
    seen = tmp_path / "engine_env.marker"
    (tmp_path / "presentation_job.py").write_text(
        "import os, pathlib, sys\n"
        "pathlib.Path(" + repr(str(seen)) + ").write_text("
        "os.environ.get('PRESENTATION_MODE', '<<UNSET>>'))\n"
        "sys.exit(0)\n", encoding="utf-8")
    return cfg, seen


def test_the_mode_is_recorded_and_handed_to_the_engine(monkeypatch, tmp_path,
                                                       capsys):
    """REQUIREMENT E, end to end: an operator can see which mode a deck was
    built in AFTER the fact, and the engine process actually receives it."""
    cfg, seen = _stub_engine(monkeypatch, tmp_path)
    monkeypatch.delenv(model_router.MODE_ENV, raising=False)
    run_dir = tmp_path / "run"
    rc = launcher.dispatch(str(run_dir), client="acme", deck_type="standard",
                           background=False, mode="Ultra")
    assert rc == 0, rc
    # 1. the engine's OWN environment carried it
    assert seen.read_text(encoding="utf-8") == "ultra"
    # 2. the run's own record
    sidecar = run_dir / ".mode-plan.json"
    assert sidecar.is_file(), "no .mode-plan.json -- the run does not say"
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    assert record["mode"] == "ultra"
    assert record["declared"] is True
    assert record["mode_source"] == "--mode"
    assert record["ceiling"]["ceiling"] == 100
    assert record["concurrency"]["operator_ceiling"] == 100
    # 3. the banner
    out = capsys.readouterr()
    assert "run mode ULTRA" in (out.out + out.err), (out.out + out.err)[-1500:]


def test_an_undeclared_run_still_records_standard(monkeypatch, tmp_path):
    """The un-moded launch is a standard launch, and says so. Its REFUSAL
    surface is unchanged -- declaring a mode can still block a launch (FIX 12
    credit preflight / AF-MODE-INVALID); not declaring one still cannot."""
    cfg, seen = _stub_engine(monkeypatch, tmp_path)
    monkeypatch.delenv(model_router.MODE_ENV, raising=False)
    run_dir = tmp_path / "run"
    rc = launcher.dispatch(str(run_dir), client="acme", deck_type="standard",
                           background=False)
    assert rc == 0, rc
    assert seen.read_text(encoding="utf-8") == "standard"
    record = json.loads((run_dir / ".mode-plan.json").read_text(encoding="utf-8"))
    assert record["mode"] == "standard"
    assert record["declared"] is False
    assert record["mode_source"] == "default"


def test_the_launcher_env_mode_is_inherited_when_nothing_is_declared(
        monkeypatch, tmp_path):
    cfg, seen = _stub_engine(monkeypatch, tmp_path)
    monkeypatch.setenv(model_router.MODE_ENV, "Economy")
    run_dir = tmp_path / "run"
    assert launcher.dispatch(str(run_dir), client="acme", deck_type="standard",
                             background=False) == 0
    assert seen.read_text(encoding="utf-8") == "economy"
    record = json.loads((run_dir / ".mode-plan.json").read_text(encoding="utf-8"))
    assert record["mode_source"] == model_router.MODE_ENV


def test_modes_flag_off_writes_no_sidecar_and_declares_no_env(monkeypatch,
                                                              tmp_path):
    """PRESENTATION_MODES=0 -- the documented rollback -- leaves the whole
    surface inert: no .mode-plan.json, no PRESENTATION_MODE for the engine."""
    cfg, seen = _stub_engine(monkeypatch, tmp_path)
    monkeypatch.delenv(model_router.MODE_ENV, raising=False)
    monkeypatch.setenv(model_router.MODE_FLAG_ENV, "0")
    run_dir = tmp_path / "run"
    assert launcher.dispatch(str(run_dir), client="acme", deck_type="standard",
                             background=False, mode="ultra") == 0
    assert seen.read_text(encoding="utf-8") == "<<UNSET>>"
    assert not (run_dir / ".mode-plan.json").exists()


def test_launcher_mode_flag_beats_the_env_at_the_door(monkeypatch, tmp_path):
    """REQUIREMENT B, at the door that exists: launcher --mode >
    PRESENTATION_MODE env > "standard". Proven end to end -- the winning mode
    is what the REAL child process reports back from its own environment, not
    what the launcher says it computed."""
    cfg, seen = _stub_engine(monkeypatch, tmp_path)
    monkeypatch.setenv(model_router.MODE_ENV, "economy")
    run_dir = tmp_path / "run"
    assert launcher.dispatch(str(run_dir), client="acme", deck_type="standard",
                             background=False, mode="Ultra") == 0
    assert seen.read_text(encoding="utf-8") == "ultra", (
        "the inherited env beat the explicit --mode at the launcher door")
    record = json.loads((run_dir / ".mode-plan.json").read_text(encoding="utf-8"))
    assert record["mode"] == "ultra"
    assert record["mode_source"] == "--mode"


def test_launcher_refuses_an_unknown_mode_before_anything_spawns(monkeypatch,
                                                                 tmp_path):
    """AF-MODE-INVALID is unchanged by this fix: an unknown declared mode is
    refused at the door, and the engine never runs."""
    cfg, seen = _stub_engine(monkeypatch, tmp_path)
    monkeypatch.delenv(model_router.MODE_ENV, raising=False)
    rc = launcher.dispatch(str(tmp_path / "run"), client="acme",
                           deck_type="standard", background=False, mode="turbo")
    assert rc == launcher.DISPATCH_MODE_INVALID
    assert not seen.exists(), "the engine ran despite an invalid mode"
