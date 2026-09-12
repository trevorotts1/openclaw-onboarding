#!/usr/bin/env python3
"""test_u3_standard_ceiling_restored.py -- standard's ceiling is the
OPERATOR's 100, and the mode axis is not allowed to claim otherwise.

WHAT U3 UNDOES
--------------
`model_router.STANDARD_MODE_CEILING` was 100 in every version of that module
until commit `86662bb67` (F15+F16, 2026-09-06 20:50; on the operator box at
07:07 the next morning) set it to **25**. The commit's stated authority was
"the review's own recommendation" -- and the review's own words at that item
are *"Make ultra mean something, or delete it (Trevor's call; my
recommendation below)"*. The call was never made. It was also applied MORE
BROADLY than the review proposed: the review suggested a smaller share for
the fan-out QC phases, while the constant went into `mode_ceiling()` ->
`capped_width()`, which cuts EVERY width decision including the P4-PROMPT
wave. Narrowing standard was never a requirement of any fix; it existed only
to make ultra look different from standard.

This file is the regression test for the UNDO.

WHAT U3 DOES **NOT** UNDO -- and this file guards that too
----------------------------------------------------------
`86662bb67` also carried F15, which made the mode plan HONEST: before it,
`.mode-plan.json` and the launcher banner printed "concurrency plan 8" for
standard while `capped_width()` ran the wave at 100 (review K3). That fix is
good and survives untouched. Section 2 below re-asserts it against the undo,
so a future "just revert the commit" cannot quietly take the lie back.

THE CONSEQUENCE, ASSERTED RATHER THAN HIDDEN
--------------------------------------------
With standard == ultra == 100 the per-mode width axis differentiates nothing
again -- which is the exact defect F16 was written to remove. U3 does not
re-narrow standard to manufacture a difference (that is what got us here),
and it does not raise ultra either: both change a number only the operator
may change. Section 3 asserts that the engine SAYS the axis is cosmetic --
in `mode_axis_in_force`, in the `reason` string the launcher banner prints
verbatim, and in `.mode-plan.json`'s `mode_axis` block.

PROVEN IN BOTH DIRECTIONS, ON THE SAME INSTRUMENT
-------------------------------------------------
Every test in sections 1 and 3 FAILS on pristine `origin/main` (`6b9068105`,
`STANDARD_MODE_CEILING = 25`) and PASSES on `fix/u3-restore-standard`,
measured by swapping origin/main's `model_router.py` over the branch file and
re-running this file with the same interpreter, same rig, same directory.
Section 2 is the CONTROL: its F15 assertions pass in BOTH directions, which
is what proves the swap actually ran a different module and that section 1's
failures are the constant and not a broken harness.

Unit-level: no network, no spend, no deck, no render. The profile rig is
tests/test_fix11_mode_axis.py's / tests/test_f15f16_mode_truth.py's,
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
                                      ["deepseek-flash", "deepseek-v4-pro"]),
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


_DS_PROVIDER = model_router.resolve_alias("deepseek-flash")["provider"]


def _stamp(monkeypatch, tmp_path, *, mode, probe_available, ceiling=None):
    """The ONE place the engine decides the P4-PROMPT fan-out width.

    routing["measured_capacity"] IS the worker-slot count
    (parallel_prompt_worker._workers_for honours it verbatim), so this is the
    wave itself -- not a plan, not a record."""
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
# 1. THE UNDO -- STANDARD REACHES 100 AGAIN, EVERYWHERE IT IS CUT
#    Every assertion in this section is FALSE on origin/main (6b9068105).
# ===========================================================================
def test_the_standard_mode_ceiling_constant_is_the_operators_100():
    """THE ONE LINE. `model_router.py` STANDARD_MODE_CEILING was 100 until
    86662bb67 made it 25 on a recommendation the review itself labelled
    "Trevor's call". 25 was never ratified; 100 was what he had."""
    assert model_router.STANDARD_MODE_CEILING == 100, (
        "standard was narrowed again -- 100 is the operator's number")
    assert model_router.ULTRA_OPERATOR_CEILING == 100, (
        "the human-ratified operator ceiling must not move either")
    assert model_router.MODE_OPERATOR_CEILING["standard"] == 100
    assert model_router.MODE_OPERATOR_CEILING["ultra"] == 100
    assert model_router.MODE_OPERATOR_CEILING["economy"] == 100


def test_a_standard_run_is_capped_at_100_not_25_at_every_ceiling_gate():
    """The constant is only interesting because of what reads it. These are
    the three gates in order: mode_ceiling() -> capped_width() is what cuts a
    width, and mode_concurrency() is what the record prints.

    On origin/main every one of these answered 25 for a client measured at or
    above 100."""
    for ceiling in (100, 2500):
        prof = _profile(ceiling=ceiling)
        assert model_router.mode_ceiling("standard",
                                         profile=prof)["ceiling"] == 100
        assert model_router.capped_width(10_000, "standard",
                                         profile=prof)["width"] == 100
        assert model_router.mode_concurrency(
            "standard", profile=prof)["concurrency"] == 100


def test_the_standard_prompt_wave_itself_runs_100_wide_again(monkeypatch,
                                                             tmp_path):
    """Not the plan -- the number `parallel_prompt_worker._workers_for` is
    handed, at `dispatcher._prompt_routing_stamp`. This is the width the
    P4-PROMPT wave and (since F6) all nine fan-out phases actually run at.

    origin/main: 25. This is the slow-down nobody approved."""
    stamp = _stamp(monkeypatch, tmp_path, mode="standard",
                   probe_available=2500, ceiling=2500)
    assert stamp["measured_capacity"] == 100, stamp
    ultra = _stamp(monkeypatch, tmp_path, mode="ultra",
                   probe_available=2500, ceiling=2500)
    assert ultra["measured_capacity"] == 100, ultra


def test_an_unbounded_client_is_not_narrowed_under_standard_either():
    """A bring-your-own-capacity client DECLARED its capacity -- a determined
    state, not an absence -- so F16's narrowing bit there too. It no longer
    does, and provider advertising still never raises the operator ceiling."""
    prof = _profile(ceiling="UNBOUNDED")
    assert model_router.mode_ceiling("standard",
                                     profile=prof)["ceiling"] == 100
    assert model_router.capped_width(2500, "standard",
                                     profile=prof)["width"] == 100
    assert model_router.mode_concurrency(
        "standard", profile=prof)["concurrency"] == 100


def test_standard_and_ultra_are_the_same_width_and_that_is_the_restored_state():
    """Stated as the equality it is, so nobody can "fix" ultra later by
    quietly shaving standard: the two are IDENTICAL, and any future
    difference must come from a number the operator ratified."""
    for ceiling in (100, 2500, "UNBOUNDED"):
        prof = _profile(ceiling=ceiling)
        ultra = model_router.capped_width(10_000, "ultra", profile=prof)["width"]
        standard = model_router.capped_width(10_000, "standard",
                                             profile=prof)["width"]
        assert ultra == standard == 100, (ceiling, ultra, standard)


# ===========================================================================
# 2. CONTROL -- F15 SURVIVES THE UNDO.
#    These assertions hold on origin/main AND here. They are what proves the
#    both-directions swap really ran a different module: if these ever come
#    back failing on pristine, the harness is broken, not the code.
# ===========================================================================
def test_control_the_planned_concurrency_is_still_the_width_that_is_applied():
    """F15's equality, the half of 86662bb67 that must NOT be undone: what
    `.mode-plan.json` and the launcher banner print is exactly what
    capped_width() will apply. TRUE on origin/main and true here."""
    for ceiling in (3, 8, 25, 100, 2500, "UNBOUNDED"):
        prof = _profile(ceiling=ceiling)
        for want in model_router.MODES:
            plan = model_router.mode_concurrency(want, profile=prof)
            wave = model_router.capped_width(10_000, want, profile=prof)
            assert plan["concurrency"] == wave["width"], (want, ceiling,
                                                          plan, wave)


def test_control_an_unmeasured_client_still_answers_undetermined_out_loud():
    """F15/F16(b): no comforting number nothing applies. TRUE in both
    directions."""
    prof = _profile()
    for want in ("ultra", "standard"):
        plan = model_router.mode_concurrency(want, profile=prof)
        assert plan["concurrency"] is None, plan
        assert plan["measured"] is False, plan
        assert "UNMEASURED CLIENT CEILING" in plan["reason"], plan
    assert model_router.mode_concurrency("economy",
                                         profile=prof)["concurrency"] == 1


def test_control_standard_never_reports_the_8_wide_worker_fallback_as_a_plan():
    """The "concurrency plan 8" lie (review K3) stays fixed. TRUE in both
    directions -- on origin/main standard planned 25, here it plans 100;
    neither is the worker fallback."""
    plan = model_router.mode_concurrency("standard",
                                         profile=_profile(ceiling=2500))
    assert plan["concurrency"] != model_router.STANDARD_WORKER_DEFAULT, plan
    assert model_router.STANDARD_WORKER_DEFAULT == 8


def test_control_economys_applied_width_is_untouched_by_the_undo():
    """Economy was never the argument and must not move. Every one of these
    widths is byte-identical on origin/main -- the control proving "economy is
    unchanged" is a measurement and not a claim."""
    for ceiling, expect in ((None, 1), (3, 1), (25, 8), (99, 33), (100, 33),
                            (2500, 100), ("UNBOUNDED", 2)):
        prof = _profile(ceiling=ceiling)
        assert model_router.capped_width(
            10_000, "economy", profile=prof)["width"] == expect, (ceiling,
                                                                  expect)


def test_control_a_ceiling_is_still_a_cap_never_a_floor_and_never_a_target():
    """Restoring 100 must not turn the ceiling into a target: a client
    measured at 3 still runs 3, in every mode. TRUE in both directions."""
    for want in model_router.MODES:
        for measured in (1, 2, 3, 8, 17, 99):
            cut = model_router.capped_width(measured, want,
                                            profile=_profile(ceiling=2500))
            assert cut["width"] <= measured, (want, measured, cut)
    assert model_router.capped_width(
        3, "standard", profile=_profile(ceiling=3))["width"] == 3


def test_control_an_unmeasured_client_is_never_narrowed_by_the_mode_axis(
        monkeypatch, tmp_path):
    """The 2026-09-04 ruling: never re-clamp a measured width down to a
    default. TRUE in both directions -- it is the doctrine the undo inherits,
    not something the undo introduces."""
    for probe in (8, 24, 100):
        for want in ("ultra", "standard"):
            stamp = _stamp(monkeypatch, tmp_path, mode=want,
                           probe_available=probe, ceiling=None)
            assert stamp["measured_capacity"] == probe, (want, probe, stamp)


# ===========================================================================
# 3. THE HONEST CONSEQUENCE -- THE ENGINE SAYS "COSMETIC" INSTEAD OF
#    PRETENDING THE AXIS BOUGHT SOMETHING.
#    FALSE on origin/main (where the axis really did differentiate).
# ===========================================================================
def test_the_mode_axis_reports_itself_out_of_force_while_it_differentiates_nothing():
    """`mode_axis_in_force` exists to answer, after the fact, "did declaring
    ultra buy anything?". With the table uniform the answer is NO, on a
    MEASURED client too -- and reporting True there would be the K3 lie
    reintroduced by this very undo."""
    for ceiling in (100, 2500, "UNBOUNDED"):
        prof = _profile(ceiling=ceiling)
        for want in model_router.MODES:
            plan = model_router.mode_concurrency(want, profile=prof)
            cap = model_router.mode_ceiling(want, profile=prof)
            assert plan["mode_axis_in_force"] is False, (want, ceiling, plan)
            assert cap["mode_axis_in_force"] is False, (want, ceiling, cap)
    assert model_router._mode_axis_differentiates() is False


def test_the_reason_string_the_banner_prints_says_the_word_cosmetic():
    """The launcher banner prints `mode_concurrency()["reason"]` verbatim, so
    the reason string is the only place this reaches a human at launch."""
    prof = _profile(ceiling=2500)
    for want in ("ultra", "standard"):
        reason = model_router.mode_concurrency(want, profile=prof)["reason"]
        assert "MODE WIDTH AXIS IS COSMETIC" in reason, (want, reason)
        assert "OPERATOR decision" in reason, (want, reason)
        assert model_router.mode_ceiling(want, profile=prof)["reason"].count(
            "MODE WIDTH AXIS IS COSMETIC") == 1


def test_the_unmeasured_ultra_notice_no_longer_promises_a_100_vs_25_split():
    """Before U3 the unmeasured notice told the operator that measuring his
    client would make "ultra a real 100-wide run against standard's 25".
    Measuring would now buy him nothing, and promising otherwise is the same
    reassuring-direction lie in a new place."""
    plan = model_router.mode_concurrency("ultra", profile=_profile())
    assert "ULTRA BUYS NOTHING HERE" in plan["reason"], plan
    assert "MODE WIDTH AXIS IS COSMETIC" in plan["reason"], plan
    assert "becomes a real" not in plan["reason"], plan


def test_the_mode_plan_record_carries_the_cosmetic_verdict(monkeypatch,
                                                           tmp_path):
    """`.mode-plan.json` is what an operator reads AFTER the fact. It must
    carry the same verdict, with both ends of the axis printed so the numbers
    can be compared without re-deriving them."""
    plan = model_router.mode_plan("ultra", profile=_profile(ceiling=2500))
    assert plan["mode_axis"]["in_force"] is False, plan
    assert plan["mode_axis"]["ultra_ceiling"] == 100
    assert plan["mode_axis"]["standard_ceiling"] == 100
    assert plan["concurrency"]["concurrency"] == 100
    assert "MODE WIDTH AXIS IS COSMETIC" in plan["concurrency"]["reason"]


def test_the_launcher_banner_carries_it_end_to_end(monkeypatch, tmp_path,
                                                   capsys):
    """END TO END through the REAL launcher, with no edit to launcher.py: it
    already prints mode_concurrency()'s reason, so making the reason honest
    makes the banner honest."""
    cfg = _stub_engine(monkeypatch, tmp_path)
    (cfg / resource_profile.PROFILE_FILENAME).write_text(
        json.dumps(_profile(ceiling=2500), indent=2), encoding="utf-8")
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    monkeypatch.delenv(model_router.MODE_ENV, raising=False)
    run_dir = tmp_path / "run"
    assert launcher.dispatch(str(run_dir), client="acme",
                             deck_type="standard", background=False,
                             mode="ultra") == 0
    banner = "".join(capsys.readouterr())
    assert "MODE WIDTH AXIS IS COSMETIC" in banner, banner[-2500:]
    record = json.loads(
        (run_dir / ".mode-plan.json").read_text(encoding="utf-8"))
    assert record["concurrency"]["concurrency"] == 100, record["concurrency"]
    assert record["mode_axis"]["in_force"] is False, record["mode_axis"]
    assert record["concurrency"]["operator_ceiling"] == 100


# ===========================================================================
# 4. GUARD -- the undo did not widen anything the operator did not ask for.
# ===========================================================================
def test_nothing_anywhere_exceeds_the_human_ratified_100():
    """100 is human-ratified. U3 restores standard TO it and never past it,
    and never raises ultra above it to manufacture a difference -- raising
    ultra is one of the two options left OPEN for the operator, not taken."""
    for ceiling in (3, 25, 100, 2500, "UNBOUNDED", None):
        prof = _profile(ceiling=ceiling)
        for want in model_router.MODES:
            cut = model_router.capped_width(10_000, want, profile=prof)
            assert cut["width"] <= 100, (want, ceiling, cut)
            assert cut["width"] <= model_router.ULTRA_OPERATOR_CEILING
    assert max(model_router.MODE_OPERATOR_CEILING.values()) == \
        model_router.ULTRA_OPERATOR_CEILING


def test_an_unknown_mode_is_still_refused_everywhere():
    for fn in (model_router.mode_concurrency, model_router.mode_ceiling):
        try:
            fn("turbo", profile=_profile(ceiling=100))
        except ValueError:
            continue
        raise AssertionError(f"{fn.__name__} accepted an unknown mode")
