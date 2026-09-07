"""U1 -- UNBOUNDED MUST RESOLVE TO THE MODE CEILING, NEVER TO 8.

THE DEFECT (measured on the operator box, 2026-09-07, scratch-redirected
state). `capacity.probe()` is CORRECT: `capacity.NO_CAP_PROVIDERS` is
`{"openrouter"}` (capacity.py:259 -- the operator's 2026-08-18 ruling, "do not
limit someone who brought their own capacity") and an OpenRouter route probes
`MEASURED / available UNBOUNDED`. `dispatcher._routing_stamp` then threw that
reading away:

    if _cap_mod.is_unbounded(available):
        stamp["measured_capacity"] = DEFAULT_MAX_WORKERS      # 8

and because the mode ceiling is applied AFTERWARDS as a `min()`
(`model_router.capped_width`, dispatcher.py `stamp["mode_cap"]`), ultra could
never raise it back. The measured result on pristine `origin/main`
(6b906810527d8d443029b968e52d6e5c149b5516): an OpenRouter route stamped
`measured_capacity 8, capacity_status unbounded-byok` under BOTH ultra
(`min(8, 100)`) and standard (`min(8, 25)`). Since F6 (`1602a5d39`) that one
number is also the width of all nine manifest fan-out phases, so the 8 governed
the entire fan-out surface.

Operator requirement, verbatim: "if I am using OpenRouter I should not be capped
at 8. I should be able to use at least 100 agents in parallel if I'm using
OpenRouter."

THE SECOND CASE, same function. A client with NO PROFILE
(`profile_state == "absent"`) skipped the probe block entirely and kept the same
8 -- EVEN WHEN THE PROBE HAD MEASURED 2,500 for the very provider the dispatcher
was about to use. A real measurement discarded is worse than an unbounded
reading discarded, because a number existed.

THE THIRD CASE. Where capacity genuinely CANNOT be established for the routed
provider, the old code substituted the same silent 8. Operator ruling: "system
need to ask if unclear" -- so it now REFUSES LOUDLY, naming the missing value,
and proceeds at `capacity.DEFAULT_CONSERVATIVE`. 8 is the one number that must
never be fabricated here: it is byte-identical to the operator's DELIBERATE
Ollama reserve (`CAP_TABLE[("ollama-cloud", "$100/month")] = 8` -- consume 8 of a
real ceiling of 10, leave the client 2), so a log line reading "8 workers" on an
OpenRouter run looks like the reserve being honoured when it is really capacity
resolution having failed.

WHAT THIS FILE PROVES, IN BOTH DIRECTIONS -- MEASURED, not asserted. Run against
pristine `origin/main` `6b906810527d8d443029b968e52d6e5c149b5516`'s dispatcher.py
(everything else in the tree identical), this file is **7 failed, 9 passed**;
on the U1 branch it is **16 passed**. The split is deliberate and is named per
test below:

  THE FIX (7 tests -- RED on main, GREEN here). The widths that were 8 now
  resolve to the mode ceiling or to the measurement; the refusal exists and
  names the missing value; the standard axis reaches its own ceiling instead of
  a shared fallback; and an unbounded reading about a DIFFERENT provider stops
  being labelled "unbounded-byok" for this one (on main that mis-attribution is
  live -- it merely happened to hand out the same 8 the correct path did, and
  would now hand out the mode ceiling if it were left alone).

  THE CONTROLS (9 tests -- GREEN on main AND here). These are what stop "the
  fix" from being "return 100 always": the premise constants still differ, the
  state redirect really holds, a genuinely measured small ceiling is NOT
  widened (including the operator's deliberate Ollama 8), the router-absent
  rollback still stamps DEFAULT_MAX_WORKERS byte for byte, economy still runs
  single-file, and every width is still bounded by the unit count.
  A control that goes RED on main would mean this file is measuring the wrong
  thing; each one is marked `CONTROL` in its own name or docstring.

STATE REDIRECTION (binding -- defect B3). Every test here redirects
`capacity.CONFIG_DIR_ENV` at a per-test `tmp_path`, unsets
`PRESENTATION_RESOURCE_PROFILE_DIR`/`PRESENTATION_RESOURCE_PROFILE`, and makes
the 9Router db / OpenClaw config / harness settings structurally unreachable.
`test_the_state_redirection_actually_holds` PROVES the redirect rather than
assuming it: it asserts the resolved profile path and override path both live
under `tmp_path`, so nothing in this file can read or append to the live
`~/.openclaw/state/presentation/resource_profile.json`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import dispatcher  # noqa: E402
from presentation_job import model_router  # noqa: E402
from presentation_job import resource_profile  # noqa: E402

#: The one provider still in NO_CAP_PROVIDERS -- the only id that can produce
#: the UNBOUNDED sentinel after the 2026-09-04 ruling moved deepseek-direct onto
#: the structural cap table. test_the_premise_holds proves it by name.
BYOK = capacity.PROVIDER_OPENROUTER
BYOK_MODEL = "z-ai/glm-5.3-flash"          # the catalog's served id for openrouter


def _clear_declared_cache():
    cache = getattr(capacity, "_DECLARED_CACHE", None)
    if isinstance(cache, dict):
        cache.clear()


def _isolate(monkeypatch, tmp_path):
    """No 9Router db, no OpenClaw config, no harness settings, no live profile
    dir -- detection steps (b) and (c) are structurally unreachable, so these
    tests assert on the declared override (a) and the fallthrough (e) alone.
    Same helper shape as tests/test_capacity_detection.py and
    tests/test_f17_new_provider_floor.py."""
    monkeypatch.setattr(capacity, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(capacity, "HARNESS_SETTINGS_CANDIDATES",
                        (tmp_path / "absent-settings.json",))
    for var in ("PRESENTATION_RESOURCE_PROFILE_DIR",
                "PRESENTATION_RESOURCE_PROFILE",
                "PRESENTATION_DECLARED_PROVIDER_UNCAP",
                "PRESENTATION_MODEL_ROUTER", "PRESENTATION_MODES",
                model_router.MODE_ENV):
        monkeypatch.delenv(var, raising=False)
    # FIX 114's presence-only key gate would park every route on a CI box with
    # no credentials. The router DECIDES here; it never reads a credential, and
    # no network call happens anywhere in this file.
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    _clear_declared_cache()


def _cfg(monkeypatch, tmp_path, *, profile=None, override=None):
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


def _profile(provider, model, *, ceiling=None):
    """A client profile declaring `provider/model` in the workhorse slot."""
    entry = {"provider": provider, "presence": True, "detected": True,
             "consented": True, "wired_models": [model]}
    if ceiling is not None:
        entry["concurrency_ceiling"] = ceiling
    return {
        ".schema_version": 1,
        "providers": {provider: entry},
        "model_plan": {
            "workhorse": {"provider": provider, "model": model},
            "reasoning": None, "judge": None, "thinking": None,
            "floor_waivers": ["authoring", "prompt_authoring", "cheap_text",
                              "creative_cheap", "speech_text", "reasoning_long"],
            "source": "interview", "declared_at": "2026-09-07T00:00:00+00:00",
        },
        "creative_prefs": {}, "consent": {}, "interview": {},
    }


def _stamp(monkeypatch, mode):
    monkeypatch.setenv(model_router.MODE_ENV, mode)
    return dispatcher._routing_stamp(run_dir=None, phase_id="P4-PROMPT")


# ---------------------------------------------------------------------------
# 0. THE PREMISES -- measured, never assumed, so a pass can never be an
#    accident of spelling or of a constant having moved.
# ---------------------------------------------------------------------------
def test_the_premise_holds():
    assert BYOK in capacity.NO_CAP_PROVIDERS, (
        "openrouter left NO_CAP_PROVIDERS; this file no longer reproduces U1 "
        f"-- NO_CAP_PROVIDERS = {set(capacity.NO_CAP_PROVIDERS)!r}")
    assert dispatcher.DEFAULT_MAX_WORKERS == 8
    assert model_router.ULTRA_OPERATOR_CEILING == 100
    assert model_router.ULTRA_OPERATOR_CEILING != dispatcher.DEFAULT_MAX_WORKERS, (
        "the ultra ceiling and the worker default are the same number; every "
        "assertion below would be untestable")
    assert capacity.DEFAULT_CONSERVATIVE != dispatcher.DEFAULT_MAX_WORKERS, (
        "the conservative floor and the worker default collide; the refusal "
        "assertions below could not tell a refusal from the old silent 8")
    # The digit coincidence the operator warned about, stated as a fact so a
    # future reader is never confused about WHICH 8 is which.
    assert capacity.CAP_TABLE[(capacity.PROVIDER_OLLAMA_CLOUD,
                               capacity.PLAN_OLLAMA_100)] == 8


def test_the_state_redirection_actually_holds(monkeypatch, tmp_path):
    """THE INSTRUMENT CHECK. If this fails, every other test in this file is
    reading (and `record_model_plan` could be appending to) the operator's LIVE
    ~/.openclaw/state/presentation/resource_profile.json -- defect B3."""
    _isolate(monkeypatch, tmp_path)
    cfg = _cfg(monkeypatch, tmp_path, profile=_profile(BYOK, BYOK_MODEL),
               override={"provider": BYOK})
    assert capacity.department_config_dir() == cfg
    assert capacity.override_path().parent == cfg
    assert resource_profile.profile_path().parent == cfg
    assert str(tmp_path) in str(resource_profile.profile_path())
    assert ".openclaw" not in str(resource_profile.profile_path())


# ---------------------------------------------------------------------------
# 1. THE HEADLINE. UNBOUNDED -> the MODE CEILING, not 8.
#    On pristine main both of these are 8.
# ---------------------------------------------------------------------------
def test_an_unbounded_byok_route_gets_the_ultra_ceiling_not_eight(
        monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path, profile=_profile(BYOK, BYOK_MODEL),
         override={"provider": BYOK})

    probe = capacity.probe()
    assert probe["status"] == capacity.STATUS_MEASURED, probe
    assert capacity.is_unbounded(probe["available"]), probe

    stamp = _stamp(monkeypatch, "ultra")
    assert stamp["provider"] == BYOK, stamp
    assert stamp["capacity_status"] == "unbounded-byok", stamp
    assert stamp["measured_capacity"] == model_router.ULTRA_OPERATOR_CEILING, (
        "U1: capacity.probe() said UNBOUNDED for a NO_CAP_PROVIDERS account and "
        "the stamp replaced that reading with DEFAULT_MAX_WORKERS. An unbounded "
        "provider under ultra must get the ULTRA ceiling: " + repr(stamp))
    assert stamp["measured_capacity"] != dispatcher.DEFAULT_MAX_WORKERS, stamp
    assert stamp["measured_capacity"] >= 100, (
        'operator requirement: "I should be able to use at least 100 agents in '
        'parallel if I\'m using OpenRouter" -- ' + repr(stamp))


def test_the_mode_ceiling_can_no_longer_be_pinned_below_itself(
        monkeypatch, tmp_path):
    """WHY THE 8 WAS UNLIFTABLE: `capped_width` is a `min()`, so once the stamp
    said 8 no mode could raise it. The stamp's own width must now equal the
    ceiling it is then min()'d against -- i.e. the cap is a no-op, which is the
    proof that nothing but a REAL ceiling can narrow an unbounded account."""
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path, profile=_profile(BYOK, BYOK_MODEL),
         override={"provider": BYOK})
    stamp = _stamp(monkeypatch, "ultra")
    assert stamp["mode_cap"]["capped"] is False, stamp
    assert stamp["mode_cap"]["width"] == stamp["mode_cap"]["ceiling"], stamp
    assert stamp["measured_capacity"] == stamp["mode_cap"]["width"], stamp


# ---------------------------------------------------------------------------
# 2. THE SECOND CASE. No profile + a REAL measurement -> the measurement,
#    capped by the mode ceiling. On pristine main this is 8.
# ---------------------------------------------------------------------------
def test_a_client_with_no_profile_keeps_the_measured_2500(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path,
         profile={".schema_version": 1, "providers": {}, "creative_prefs": {},
                  "consent": {}, "interview": {}},
         override={"provider": capacity.PROVIDER_DEEPSEEK_DIRECT,
                   "plan": capacity.PLAN_DEEPSEEK_FLASH})

    probe = capacity.probe()
    assert probe["status"] == capacity.STATUS_MEASURED, probe
    assert probe["available"] == 2500, probe

    decision = model_router.resolve_route("P4-PROMPT", mode="ultra")
    assert decision["profile_state"] == "absent", decision
    assert decision["route"] is None, decision

    stamp = _stamp(monkeypatch, "ultra")
    # The dispatcher default provider IS deepseek-direct, so the 2500 is a
    # measurement ABOUT THE PROVIDER THIS STAMP WILL USE.
    assert stamp["provider"] == capacity.PROVIDER_DEEPSEEK_DIRECT, stamp
    assert stamp["capacity_status"].startswith("measured"), (
        "U1 second case: the probe MEASURED 2500 for the very provider the "
        "dispatcher was about to use, and the stamp discarded it because the "
        "client had declared no providers: " + repr(stamp))
    assert stamp["measured_capacity"] == model_router.ULTRA_OPERATOR_CEILING, stamp
    assert stamp["measured_capacity"] != dispatcher.DEFAULT_MAX_WORKERS, stamp


# ---------------------------------------------------------------------------
# 3. THE THIRD CASE. Truly unknown -> REFUSE LOUDLY, naming the missing value.
#    On pristine main this is a silent 8 with no refusal record at all.
# ---------------------------------------------------------------------------
def test_a_capacity_that_cannot_be_established_refuses_loudly(
        monkeypatch, tmp_path, capsys):
    _isolate(monkeypatch, tmp_path)
    # A profile routing to openrouter, and a probe that can find NOTHING (no
    # override at all, every detection source unreachable) -> UNDETERMINED,
    # provider None: nothing attributable to this route.
    _cfg(monkeypatch, tmp_path, profile=_profile(BYOK, BYOK_MODEL))

    probe = capacity.probe()
    assert probe["status"] == capacity.STATUS_UNDETERMINED, probe

    stamp = _stamp(monkeypatch, "ultra")
    refusal = stamp.get("capacity_refusal")
    assert isinstance(refusal, dict), (
        "U1: where capacity cannot be established the honest behaviour is to "
        "REFUSE LOUDLY naming the missing value -- never a silent 8: "
        + repr(stamp))
    assert refusal["code"] == "AF-CAPACITY-UNMEASURED", refusal
    assert BYOK in refusal["missing"], (
        "the refusal must NAME the value that is missing", refusal)
    assert refusal["width_basis"] == "capacity.DEFAULT_CONSERVATIVE", refusal
    assert stamp["measured_capacity"] == capacity.DEFAULT_CONSERVATIVE, stamp
    assert stamp["measured_capacity"] != dispatcher.DEFAULT_MAX_WORKERS, (
        "a fabricated 8 here is indistinguishable from the operator's "
        "deliberate Ollama reserve: " + repr(stamp))
    err = capsys.readouterr().err
    assert "REFUSING" in err and "AF-CAPACITY-UNMEASURED" in err, err
    # F41's wave contract still holds: a refusal is not a dead wave.
    assert isinstance(stamp["measured_capacity"], int)
    assert stamp["measured_capacity"] >= 1


# ---------------------------------------------------------------------------
# 4. resolve_max_workers -- the SAME collapse, in the accessor the dispatcher's
#    own work-order pool uses. On pristine main this is 8.
# ---------------------------------------------------------------------------
def test_resolve_max_workers_unbounded_without_unit_count_is_the_mode_ceiling(
        monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path, override={"provider": BYOK})
    monkeypatch.setenv(model_router.MODE_ENV, "ultra")
    result = dispatcher.resolve_max_workers(tmp_path, None)
    assert result == model_router.ULTRA_OPERATOR_CEILING, result
    assert result != dispatcher.DEFAULT_MAX_WORKERS, result


# ---------------------------------------------------------------------------
# 5. TWO MORE THINGS U1 FIXES -- RED on pristine main, like sections 1-4.
#    They are named `control_` because of what they GUARD, not because they
#    pass on main; the module docstring states the split.
# ---------------------------------------------------------------------------
def test_control_the_standard_mode_axis_still_narrows_a_measured_client(
        monkeypatch, tmp_path):
    """U1 must not neuter F16. Where the client's concurrency ceiling IS a
    determined fact, standard still reaches less far than ultra. RED on main:
    there BOTH modes were 8, which is exactly the disease -- the two ceilings
    were unreachable because a fallback sat under the min()."""
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path,
         profile=_profile(BYOK, BYOK_MODEL, ceiling=100),
         override={"provider": BYOK})
    assert _stamp(monkeypatch, "ultra")["measured_capacity"] == \
        model_router.ULTRA_OPERATOR_CEILING
    assert _stamp(monkeypatch, "standard")["measured_capacity"] == \
        model_router.STANDARD_MODE_CEILING


def test_control_a_different_providers_measurement_is_still_not_attributed(
        monkeypatch, tmp_path):
    """DEFECT 5's guard, extended to the UNBOUNDED arm. An unbounded reading
    about SOMEBODY ELSE must not hand this route the mode ceiling. RED on main,
    where the unbounded arm ran BEFORE the identity test and stamped
    capacity_status='unbounded-byok' on an ollama-cloud route from an openrouter
    probe -- harmless only while both answers happened to be 8."""
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path,
         profile=_profile(capacity.PROVIDER_OLLAMA_CLOUD, "glm-5.3-flash"),
         override={"provider": BYOK})          # probe: openrouter, UNBOUNDED
    stamp = _stamp(monkeypatch, "ultra")
    assert stamp["provider"] == capacity.PROVIDER_OLLAMA_CLOUD, stamp
    assert stamp["capacity_status"] == "probe-not-measured", stamp
    assert stamp["measured_capacity"] != model_router.ULTRA_OPERATOR_CEILING, (
        "an UNBOUNDED reading about openrouter must never uncap an "
        "ollama-cloud route: " + repr(stamp))


# ===========================================================================
# 6. THE CONTROLS. Every test below is GREEN on pristine origin/main AND here
#    -- they are what make sections 1-5 a FIX rather than "return 100 always".
#    If one of these ever goes RED on main, this file is measuring the wrong
#    thing and every assertion above it is worthless.
# ===========================================================================
def test_control_a_genuinely_measured_small_ceiling_is_never_widened(
        monkeypatch, tmp_path):
    """The operator's Ollama reserve, and the whole point of a CAP: a client
    measured at 3 runs 3 in ultra. Ultra is a ceiling, never a target."""
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path,
         profile=_profile(capacity.PROVIDER_OLLAMA_CLOUD, "glm-5.3-flash"),
         override={"provider": capacity.PROVIDER_OLLAMA_CLOUD,
                   "plan": capacity.PLAN_OLLAMA_20})
    stamp = _stamp(monkeypatch, "ultra")
    assert stamp["capacity_status"].startswith("measured"), stamp
    assert stamp["measured_capacity"] == 3, stamp

    _cfg(monkeypatch, tmp_path,
         profile=_profile(capacity.PROVIDER_OLLAMA_CLOUD, "glm-5.3-flash"),
         override={"provider": capacity.PROVIDER_OLLAMA_CLOUD,
                   "plan": capacity.PLAN_OLLAMA_100})
    stamp = _stamp(monkeypatch, "ultra")
    assert stamp["measured_capacity"] == 8, (
        "the operator's DELIBERATE $100/month reserve -- 8 of a real ceiling "
        "of 10, leaving the client 2 -- must survive U1 untouched: "
        + repr(stamp))


def test_control_the_router_absent_rollback_is_byte_for_byte_unchanged(
        monkeypatch, tmp_path):
    """PRESENTATION_MODEL_ROUTER's absence is the documented pre-FIX-7 rollback
    path. U1 widens nothing there."""
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path, override={"provider": BYOK})
    monkeypatch.setattr(dispatcher, "_model_router", None)
    stamp = dispatcher._routing_stamp(run_dir=None, phase_id="P4-PROMPT")
    assert stamp["measured_capacity"] == dispatcher.DEFAULT_MAX_WORKERS, stamp
    assert stamp["capacity_status"] == "fallback-default", stamp
    assert stamp["router"] == "disabled", stamp


def test_control_resolve_max_workers_still_bounds_by_unit_count(
        monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path, override={"provider": BYOK})
    monkeypatch.setenv(model_router.MODE_ENV, "ultra")
    assert dispatcher.resolve_max_workers(tmp_path, None, unit_count=25) == 25
    assert dispatcher.resolve_max_workers(tmp_path, 12, unit_count=999) == 12


@pytest.mark.parametrize("mode", ["ultra", "standard", "economy"])
def test_control_the_wave_is_still_bounded_by_the_unit_count(
        monkeypatch, tmp_path, mode):
    """100 worker slots never means 100 model calls for a 25-slide deck. The
    downstream bound -- `min(width, units)` -- is what actually protects the
    provider, and U1 changes nothing about it in any mode."""
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path, profile=_profile(BYOK, BYOK_MODEL),
         override={"provider": BYOK})
    width = _stamp(monkeypatch, mode)["measured_capacity"]
    from presentation_job.fanout import resolve_effective_workers
    assert resolve_effective_workers(width, unit_count=25) == min(width, 25)
    assert resolve_effective_workers(width, unit_count=3) == min(width, 3)


def test_control_economy_still_runs_single_file_on_an_unmeasured_client(
        monkeypatch, tmp_path):
    """MEASURED, both before and after U1: economy's width is a COST policy
    (`model_router.mode_concurrency`, economy branch -- "client ceiling
    unmeasured: economy runs single-file"), applied by `capped_width`'s second
    limit. Widening the UNBOUNDED reading from 8 to 100 does not move it,
    because the cost policy was already the binding term."""
    _isolate(monkeypatch, tmp_path)
    _cfg(monkeypatch, tmp_path, profile=_profile(BYOK, BYOK_MODEL),
         override={"provider": BYOK})
    stamp = _stamp(monkeypatch, "economy")
    assert stamp["measured_capacity"] == 1, stamp
    assert stamp["mode_cap"]["capped"] is True, stamp
    assert "economy cost policy" in stamp["mode_cap"]["reason"], stamp
