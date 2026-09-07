#!/usr/bin/env python3
"""test_f15f16_mode_truth.py -- the mode plan stops lying, and ultra means
something.

TWO DEFECTS, ONE FILE (model_router.py), ONE PR -- F15 first because F16's
width axis is only honest once F15 makes mode_concurrency() report the number
the run will actually use.

F15 -- THE RECORD LIED IN THE REASSURING DIRECTION (review K3).
    `.mode-plan.json` and the launcher banner both print
    `mode_concurrency(mode)["concurrency"]`. NOTHING downstream read that
    number: the width the P4-PROMPT wave actually runs at comes from
    `capped_width()` (dispatcher._prompt_routing_stamp ->
    routing["measured_capacity"] -> parallel_prompt_worker._workers_for).
    Measured on the operator box, client concurrency_ceiling 100, probe
    available 2500: the banner said "concurrency plan 8" and the wave ran
    100. The audit record built to PROVE a mode was itself wrong, and wrong in
    the direction that reassures.

F16 -- ULTRA WAS COSMETIC (review section 6).
    Measured on the operator box: ultra ceiling=100 concurrency=3 width=100;
    standard ceiling=100 concurrency=3 width=100 -- BYTE-IDENTICAL. Only
    economy differed. `mode_ceiling()` handed every mode the same
    ULTRA_OPERATOR_CEILING, so `capped_width()` -- a min() -- could not tell
    the two apart, and declaring ultra changed no number anywhere.

    The mode is NOT deleted (that call is Trevor's and has not been made).
    It is made honest instead, in the only two directions available:

      (a) WHEN CAPACITY IS MEASURED, ultra is genuinely wider. 100 is
          human-ratified and may not be raised, so the only truthful way for
          ultra to be wider is for standard to reach less far:
          STANDARD_MODE_CEILING = 25 (the review's own recommendation), which
          is still 3x the 8 the plan had been PROMISING standard all along.

          *** U3 (2026-09-07) REVERSED (a). *** The 25 was a review
          SUGGESTION whose own text read "Trevor's call"; that call was never
          made, and it was applied more broadly than the suggestion proposed.
          STANDARD_MODE_CEILING is back at the operator's 100. Consequence,
          stated rather than engineered around: ultra and standard are
          byte-identical in width again. That is NOT re-fixed by re-narrowing
          standard -- the two honest fixes (raise ultra, or let the operator
          set both numbers) are the operator's call and remain OPEN. What the
          engine does instead is say the axis is COSMETIC in every record.
          The four assertions below that asserted (a)'s width split are
          marked U3 and now assert the restored state; F15 (everything else
          in this file) is untouched, and tests/
          test_u3_standard_ceiling_restored.py is the undo's own regression
          test, proven in both directions.
      (b) WHEN CAPACITY IS NOT MEASURED, the mode axis is INERT and every
          record says so OUT LOUD -- instead of silently reporting the
          conservative floor 3 while the wave ran at whatever the probe found.
          An unmeasured client is never narrowed on the strength of an
          absence: all three modes keep the operator ceiling there, which is
          also the 2026-09-04 ruling (never re-clamp a measured width to a
          default).

WHAT MAKES EACH TEST A REGRESSION TEST: every assertion in sections 1-3 is
FALSE on pristine origin/main (ea331f82a) and true on this branch -- measured
by swapping `git show origin/main:model_router.py` over the branch file and
re-running: 13 failed / 4 passed there, 17 passed here.

Section 4 is the GUARDS: the doctrine this fix inherited, re-asserted against
the fix itself. Its two pure-doctrine tests pass in BOTH directions. Its other
two also fail on pristine, but only where they name a constant this branch
introduces -- their behavioural assertions (every width economy applies; the
cap is never a floor) pass on pristine, which is the control that "economy is
unchanged" is a measurement and not a claim.

Unit-level: no network, no spend, no deck, no render. The profile rig is
tests/test_fix11_mode_axis.py's, deliberately -- same fixtures, so the two
files cannot drift into testing different clients.
"""
from __future__ import annotations

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
# rig (identical to tests/test_fix11_mode_axis.py's)
# ---------------------------------------------------------------------------
def _wired(provider, models, **extra):
    return dict({"provider": provider, "consented": True, "detected": True,
                 "presence": True, "wired_models": list(models)}, **extra)


def _profile(ceiling=None):
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
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    if profile is not None:
        (cfg / resource_profile.PROFILE_FILENAME).write_text(
            json.dumps(profile, indent=2), encoding="utf-8")
    return cfg


_DS_PROVIDER = model_router.resolve_alias("deepseek-v4-flash")["provider"]


def _stamp(monkeypatch, tmp_path, *, mode, probe_available, ceiling=None):
    """The ONE place the engine decides the P4-PROMPT fan-out width.

    routing["measured_capacity"] IS the worker-slot count
    (parallel_prompt_worker._workers_for honours it verbatim), so this is the
    wave itself -- not a plan, not a record.
    """
    _env(monkeypatch, tmp_path, _profile(ceiling=ceiling), mode=mode)
    monkeypatch.setattr(capacity, "probe", lambda *a, **k: {
        "available": probe_available, "provider": _DS_PROVIDER,
        "status": "measured", "detection_source": "test-fixture"})
    return dispatcher._prompt_routing_stamp(run_dir=tmp_path)


def _stub_engine(monkeypatch, tmp_path):
    """tests/test_fix11_mode_axis.py's launcher rig: a REAL child interpreter
    runs a one-line stub engine, so the launcher's own banner and its own
    sidecar writer really run. Nothing here mocks Popen."""
    monkeypatch.setattr(capacity, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(capacity, "HARNESS_SETTINGS_CANDIDATES",
                        (tmp_path / "absent-settings.json",))
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    # An ambient profile/router env in the operator's shell must never decide
    # whether this proof passes: the unmeasured case is the POINT of it.
    for var in ("PRESENTATION_RESOURCE_PROFILE_DIR",
                "PRESENTATION_RESOURCE_PROFILE",
                "PRESENTATION_MODEL_ROUTER", "PRESENTATION_MODES"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", "/usr/bin/true")
    monkeypatch.setattr(capacity, "measure_working_concurrent",
                        lambda: (0, "stub", True))
    monkeypatch.setattr(launcher, "resolve_scripts_dir", lambda: tmp_path)
    (tmp_path / "presentation_job.py").write_text(
        "import sys\nsys.exit(0)\n", encoding="utf-8")
    return cfg


# ===========================================================================
# 1. F15 -- THE RECORD REPORTS THE NUMBER THE RUN WILL ACTUALLY USE
# ===========================================================================
def test_the_planned_concurrency_is_the_width_the_wave_is_capped_to():
    """THE F15 DEFECT, stated as an equality.

    `mode_concurrency()` is what the banner and `.mode-plan.json` print;
    `capped_width()` is what cuts the wave. Feed capped_width a width far
    above any ceiling so that what survives IS the mode's own cap, and the
    two must agree for every measured client.

    PRISTINE origin/main: standard on a client measured at 100 planned 8 and
    was capped to 100; economy on a client measured at 2,500 planned 833 and
    was capped to 100. Both lied in the reassuring direction. ALL THREE modes
    are held to the equality -- economy's WIDTH is unchanged (its cost policy
    was already being min()'d against the same ceiling), only its REPORT.
    """
    for ceiling in (3, 8, 25, 100, 2500, "UNBOUNDED"):
        prof = _profile(ceiling=ceiling)
        for want in model_router.MODES:
            plan = model_router.mode_concurrency(want, profile=prof)
            wave = model_router.capped_width(10_000, want, profile=prof)
            assert plan["concurrency"] == wave["width"], (want, ceiling,
                                                          plan, wave)


def test_an_unmeasured_client_is_the_one_case_that_answers_undetermined():
    """The equality above needs a measured client to be meaningful. On an
    unmeasured one the honest answer for a CAPACITY mode is None -- there is
    no reading to report -- while economy still answers, because its width was
    never a capacity reading in the first place."""
    prof = _profile()
    for want in ("ultra", "standard"):
        assert model_router.mode_concurrency(want, profile=prof)["concurrency"] \
            is None
    econ = model_router.mode_concurrency("economy", profile=prof)
    assert econ["concurrency"] == \
        model_router.capped_width(10_000, "economy", profile=prof)["width"] == 1


def test_standard_stops_reporting_the_worker_fallback_as_its_plan():
    """The 8 in "concurrency plan 8" was parallel_prompt_worker's fallback for
    a MISSING capacity reading. It was never a width any step applied, and
    printing it next to a 100-wide wave is the lie K3 names."""
    prof = _profile(ceiling=2500)
    plan = model_router.mode_concurrency("standard", profile=prof)
    assert plan["concurrency"] != model_router.STANDARD_WORKER_DEFAULT, plan
    assert plan["concurrency"] == model_router.STANDARD_MODE_CEILING, plan
    # and the constant survives, as the WORKER fallback it actually is
    assert model_router.STANDARD_WORKER_DEFAULT == 8


def test_the_recorded_plan_carries_the_mode_ceiling_that_produced_it():
    """The record must be auditable without re-deriving it: which ceiling was
    in force, and was the mode axis in force at all."""
    prof = _profile(ceiling=2500)
    plan = model_router.mode_concurrency("standard", profile=prof)
    assert plan["mode_operator_ceiling"] == model_router.STANDARD_MODE_CEILING
    assert plan["operator_ceiling"] == model_router.ULTRA_OPERATOR_CEILING
    # U3: the ceiling that produced the plan is still recorded -- but the axis
    # flag now tells the truth about whether it BOUGHT anything, and with
    # standard restored to 100 the table differentiates nothing.
    assert plan["mode_axis_in_force"] is False
    ultra = model_router.mode_concurrency("ultra", profile=prof)
    assert ultra["mode_operator_ceiling"] == model_router.ULTRA_OPERATOR_CEILING


# ===========================================================================
# 2. F16 -- ULTRA IS GENUINELY WIDER WHEN CAPACITY IS MEASURED
# ===========================================================================
def test_ultra_and_standard_widths_track_the_ratified_ceilings():
    """U3 REWROTE THIS TEST. It used to assert `ultra > standard`, which was
    only ever true because F16 narrowed standard to 25 without approval. What
    is actually invariant is that each mode's applied width IS its own
    ratified ceiling -- so the day an operator sets two different numbers this
    test proves the split, and today it proves there is none."""
    prof = _profile(ceiling=2500)
    ultra = model_router.capped_width(2500, "ultra", profile=prof)["width"]
    standard = model_router.capped_width(2500, "standard", profile=prof)["width"]
    assert ultra == model_router.ULTRA_OPERATOR_CEILING
    assert standard == model_router.STANDARD_MODE_CEILING
    assert (ultra > standard) is (model_router.STANDARD_MODE_CEILING <
                                  model_router.ULTRA_OPERATOR_CEILING)


def test_the_prompt_wave_itself_runs_at_each_modes_ratified_ceiling(
        monkeypatch, tmp_path):
    """U3 REWROTE THIS TEST -- same reason as the one above. Not the plan: the
    number parallel_prompt_worker._workers_for is handed. It must equal the
    mode's own ceiling, whatever the operator has ratified that to be; with
    standard back at 100 both modes run the same 100-wide wave."""
    ultra = _stamp(monkeypatch, tmp_path, mode="ultra",
                   probe_available=2500, ceiling=2500)["measured_capacity"]
    standard = _stamp(monkeypatch, tmp_path, mode="standard",
                      probe_available=2500, ceiling=2500)["measured_capacity"]
    assert (ultra, standard) == (model_router.ULTRA_OPERATOR_CEILING,
                                 model_router.STANDARD_MODE_CEILING)


def test_an_unbounded_client_gets_each_modes_ratified_ceiling():
    """U3 REWROTE THE LAST ASSERTION (it demanded ultra > standard, which only
    held because of the unapproved 25). A bring-your-own-capacity client
    DECLARED its capacity; that is a determined state, not an absence, so the
    per-mode ceiling applies there -- and provider advertising still never
    raises the operator ceiling."""
    prof = _profile(ceiling="UNBOUNDED")
    assert model_router.mode_ceiling("ultra", profile=prof)["ceiling"] == 100
    assert model_router.mode_ceiling("standard", profile=prof)["ceiling"] == \
        model_router.STANDARD_MODE_CEILING
    assert model_router.capped_width(2500, "standard", profile=prof)["width"] \
        == model_router.STANDARD_MODE_CEILING


# ===========================================================================
# 3. F16 -- AN UNMEASURED CLIENT IS SAID OUT LOUD, NOT PAPERED OVER WITH 3
# ===========================================================================
def test_an_unmeasured_run_reports_undetermined_not_the_conservative_floor():
    """PRISTINE origin/main answered 3 -- a number nothing downstream applied
    (the wave ran at whatever the probe reported). UNDETERMINED is the correct
    answer, and it is louder than a wrong number."""
    for want in ("ultra", "standard"):
        plan = model_router.mode_concurrency(want, profile=_profile())
        assert plan["concurrency"] is None, plan
        assert plan["measured"] is False, plan
        assert plan["mode_axis_in_force"] is False, plan
        assert "UNMEASURED CLIENT CEILING" in plan["reason"], plan


def test_an_unmeasured_ultra_run_says_ultra_buys_nothing_here():
    """The specific loud sentence: a client nobody measured gets a run that is
    byte-identical to standard, and the record says so rather than implying a
    mode was bought."""
    plan = model_router.mode_concurrency("ultra", profile=_profile())
    assert "ULTRA BUYS NOTHING HERE" in plan["reason"], plan
    assert plan["warning"], plan
    standard = model_router.mode_concurrency("standard", profile=_profile())
    assert "ULTRA BUYS NOTHING HERE" not in standard["reason"], standard


def test_the_unmeasured_notice_reaches_the_mode_plan_record():
    """`.mode-plan.json` is written straight from mode_plan(); the warning has
    to survive into the record an operator reads AFTER the fact."""
    plan = model_router.mode_plan("ultra", profile=_profile())
    assert plan["warnings"], plan
    assert any("UNMEASURED CLIENT CEILING" in w for w in plan["warnings"]), plan
    assert plan["mode_axis"]["in_force"] is False, plan
    measured = model_router.mode_plan("ultra", profile=_profile(ceiling=100))
    # U3: still no `warnings` -- capacity WAS determined here, and warnings[]
    # means "no width could be determined", which is F15's meaning and stays.
    assert not measured.get("warnings"), measured
    # U3: but the axis is out of force, because standard is 100 again and the
    # ceiling table differentiates nothing. See test_u3_standard_ceiling_
    # restored.py section 3.
    assert measured["mode_axis"]["in_force"] is False, measured


def test_the_launcher_banner_and_sidecar_carry_the_notice(monkeypatch,
                                                          tmp_path, capsys):
    """END TO END through the REAL launcher, with no edit to launcher.py: the
    banner prints mode_concurrency()'s own reason string, so making the reason
    loud makes the banner loud."""
    _stub_engine(monkeypatch, tmp_path)
    monkeypatch.delenv(model_router.MODE_ENV, raising=False)
    run_dir = tmp_path / "run"
    assert launcher.dispatch(str(run_dir), client="acme", deck_type="standard",
                             background=False, mode="ultra") == 0
    out = capsys.readouterr()
    banner = out.out + out.err
    assert "ULTRA BUYS NOTHING HERE" in banner, banner[-2000:]
    record = json.loads((run_dir / ".mode-plan.json").read_text(encoding="utf-8"))
    assert record["concurrency"]["concurrency"] is None, record["concurrency"]
    assert record["warnings"], record
    # the operator ceiling key keeps its old meaning: the global human-ratified
    # maximum, not the mode's share of it
    assert record["concurrency"]["operator_ceiling"] == 100


# ===========================================================================
# 4. GUARDS -- the doctrine this fix inherited, re-asserted against the fix
#    itself. The first three BEHAVIOURAL blocks below hold on pristine
#    origin/main too; that is the point of them, and for economy it is the
#    control proving "economy is unchanged" was measured, not claimed. (Two of
#    these tests still fail on pristine, but only on their closing reference to
#    a constant this branch introduces -- never on a width.)
# ===========================================================================
def test_no_mode_exceeds_the_operator_ceiling_or_the_client_ceiling():
    for ceiling, cap in ((3, 3), (2500, 100), ("UNBOUNDED", 100), (None, 100)):
        prof = _profile(ceiling=ceiling)
        for want in model_router.MODES:
            cut = model_router.capped_width(10_000, want, profile=prof)
            assert cut["width"] <= cap, (want, ceiling, cut)
            assert cut["width"] <= model_router.ULTRA_OPERATOR_CEILING


def test_the_ceiling_is_still_a_cap_never_a_floor_and_never_a_target():
    """Ultra does not lift a client measured at 3 to 100, in any mode."""
    for want in model_router.MODES:
        for measured in (1, 2, 3, 8, 17):
            cut = model_router.capped_width(measured, want,
                                            profile=_profile(ceiling=2500))
            assert cut["width"] <= measured, (want, measured, cut)
    assert model_router.capped_width(3, "ultra",
                                     profile=_profile(ceiling=3))["width"] == 3
    assert model_router.mode_concurrency(
        "ultra", profile=_profile(ceiling=3))["concurrency"] == 3


def test_an_unmeasured_client_is_never_narrowed_by_the_mode_axis(monkeypatch,
                                                                 tmp_path):
    """The 2026-09-04 ruling: never re-clamp a measured width down to a
    default. Nothing was measured about the CLIENT here, so the mode axis
    contributes no ceiling of its own and the wave keeps the probe's width in
    ultra AND standard. (Economy is excluded on purpose: it narrows by COST
    policy, which is not a capacity reading.)"""
    for probe in (8, 24, 100):
        for want in ("ultra", "standard"):
            stamp = _stamp(monkeypatch, tmp_path, mode=want,
                           probe_available=probe, ceiling=None)
            assert stamp["measured_capacity"] == probe, (want, probe, stamp)


def test_economys_applied_width_is_untouched_by_f15_and_f16():
    """The review's instruction was "Economy stays as is". Every width economy
    APPLIES is byte-for-byte what it was; only the number it REPORTS on a
    client whose cost width exceeded its own ceiling changed, and it changed
    to the number that was already being applied."""
    for ceiling, expect in ((None, 1), (3, 1), (25, 8), (99, 33), (100, 33),
                            (2500, 100), ("UNBOUNDED", 2)):
        prof = _profile(ceiling=ceiling)
        assert model_router.capped_width(
            10_000, "economy", profile=prof)["width"] == expect, (ceiling,
                                                                  expect)
    # its CEILING never became standard's smaller share
    assert model_router.mode_ceiling(
        "economy", profile=_profile(ceiling=2500))["ceiling"] == 100
    assert model_router.MODE_OPERATOR_CEILING["economy"] == \
        model_router.ULTRA_OPERATOR_CEILING
    # and the cheap-model re-point, economy's other half, is untouched
    assert set(model_router.ECONOMY_FLASH_REPOINT) == {"authoring",
                                                       "prompt_authoring"}


def test_the_operator_ceiling_constant_is_untouched():
    """100 is human-ratified and neither F16 nor U3 moved it: F16 lowered
    STANDARD's reach to 25, U3 put it back at 100. Nothing may exceed the
    ratified 100, and standard may never again be quietly cut below the
    number the operator actually has -- the two bounds that survive whatever
    he decides next."""
    assert model_router.ULTRA_OPERATOR_CEILING == 100
    assert model_router.STANDARD_MODE_CEILING <= model_router.ULTRA_OPERATOR_CEILING
    assert model_router.STANDARD_MODE_CEILING == 100, (
        "U3: standard is the operator's 100 -- see tests/"
        "test_u3_standard_ceiling_restored.py")
    assert model_router.STANDARD_MODE_CEILING > model_router.STANDARD_WORKER_DEFAULT
    assert model_router.MODE_OPERATOR_CEILING["ultra"] == \
        model_router.ULTRA_OPERATOR_CEILING


def test_an_unknown_mode_is_still_refused_everywhere():
    for fn in (model_router.mode_concurrency, model_router.mode_ceiling):
        try:
            fn("turbo", profile=_profile(ceiling=100))
        except ValueError:
            continue
        raise AssertionError(f"{fn.__name__} accepted an unknown mode")
