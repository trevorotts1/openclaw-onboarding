#!/usr/bin/env python3
"""F4 -- the routing stamp probes THE PROVIDER IT WILL DISPATCH TO, and
--declare-capacity declares a provider instead of PARKing the run.

TWO DEFECTS, one root cause: a capacity answer about ONE provider was being
used as the answer about ALL of them.

DEFECT A -- `_routing_stamp` called `capacity.probe()` with no arguments.
`probe()` answers about exactly ONE provider: whichever one detection resolved,
or -- before F1/F2 -- whichever single provider `capacity_override.json`
happened to name. `_routing_stamp` then compares that provider against the
provider the phase actually routes to and, on a mismatch, refuses the width
down to `capacity.DEFAULT_CONSERVATIVE` (3). The refusal is CORRECT for the
question it was asked. The QUESTION was the defect: on a two-provider client
there is no single global answer that is right for both routes, so one provider
is always wrong.

    MEASURED by Fable on this box, 2026-09-07, isolated scratch config dir,
    live profile md5 unchanged before and after:
      * `record_plan_answer('ollama-cloud', '$100/month')` -> `capacity.probe()`
        answers `MEASURED ollama-cloud $100/month available=8`
      * P4-PROMPT routes to deepseek (catalog spelling) -> canonical
        `deepseek-direct` -> providers_match False
      * -> `_refuse_unmeasured_width` -> `measured_capacity` 3, sidecar
        `capacity_width_refused`, with a real 2,500 measurement one keyword
        argument away.

DEFECT B -- `ensure_capacity_override` hard-coded
`{"provider": "deepseek-direct", "max_concurrent": N}`. deepseek-direct joined
the STRUCTURAL cap table on 2026-09-04 (`CAP_TABLE` gained v4-flash=2500 and
v4-pro=500; `NO_CAP_PROVIDERS` shrank to `{'openrouter'}`), and a cap-table
provider declared with no plan hits `capacity._resolve_override` case 2 and
PARKS.

    MEASURED by Fable, scratch dir 2: with exactly that record,
    `capacity.probe()` -> `status=PARKED provider=deepseek-direct plan=None
    available=None autofail=AF-CAPACITY-UNMEASURED`, and
    `dispatcher.resolve_max_workers(...)` -> 3.
    `--declare-capacity 100` -- the flag whose whole job is to WIDEN a run --
    narrowed it to 3.

WHAT THIS FILE DOES NOT CHANGE, asserted here so nobody "tidies" it later:
  * the identity guard stays (a probe that answers about somebody else is still
    refused -- see the two guard tests below);
  * the refusal branch stays for PARKED/UNDETERMINED about the ROUTED provider;
  * `resolve_max_workers` keeps its NO-ARG probe: it sizes the work-order POOL
    that serves every route, and the governor's per-provider `max_inflight`
    bounds any one provider inside that pool.

THE PROBE DOUBLE below implements the AGREED signature
`probe(config_dir=None, *, provider=None, model=None)` (L1's contract). It is
deliberately callable BOTH ways, so the same fixture runs against pristine main
(which calls `probe()`) and against this branch (which calls
`probe(provider=..., model=...)`) -- the difference in outcome is the proof,
not a difference in the fixture. On a capacity build that predates the kwarg
the dispatcher degrades to today's global probe and records
`probe_scope='global-no-arg'` on the stamp; that degradation is pinned by
test_the_global_fallback_is_recorded_never_hidden.

Unit-level: no network, no spend, no deck, no render. Every profile and every
override file lives in a tmp config dir the capacity/profile env points at.
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


# ---------------------------------------------------------------------------
# rig
# ---------------------------------------------------------------------------
#: A phase whose capability (prompt_authoring) routes to DeepSeek on the
#: shipped catalog, and a phase whose capability (vision_ocr) falls back to
#: Ollama Cloud once deepseek-v4-pro is not among the client's wired models.
#: MEASURED against the shipped model_catalog.json on this box 2026-09-07 --
#: test_the_fixture_really_does_split_the_two_routes re-proves it every run
#: instead of trusting this comment.
PHASE_DEEPSEEK = "P4-PROMPT"
PHASE_OLLAMA = "P-TYPO-QC"


def _wired(provider, models):
    return {"provider": provider, "consented": True, "detected": True,
            "presence": True, "wired_models": list(models)}


def _two_provider_profile():
    """A client who owns BOTH providers and has NO measured client ceiling.

    No `concurrency_ceiling` anywhere on purpose: the profile-wide `min()` in
    model_router.measured_client_ceiling is a DIFFERENT defect (Path B, lane
    L2). Leaving the ceiling unmeasured keeps every number in this file
    attributable to the stamp's own probe question and to the operator mode
    ceiling (100), so an L2 regression cannot make an L3 test lie either way."""
    return {
        ".schema_version": 1,
        "providers": {
            "deepseek-direct": _wired("deepseek-direct", ["deepseek-v4-flash"]),
            "ollama-cloud": _wired("ollama-cloud", ["glm-ocr"]),
        },
        "creative_prefs": {}, "consent": {}, "interview": {},
    }


def _env(monkeypatch, tmp_path, profile=None, mode="ultra"):
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    for var in ("PRESENTATION_RESOURCE_PROFILE_DIR",
                "PRESENTATION_RESOURCE_PROFILE",
                "PRESENTATION_MODEL_ROUTER", "PRESENTATION_MODES"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv(model_router.MODE_ENV, raising=False)
    if mode is not None:
        monkeypatch.setenv(model_router.MODE_ENV, mode)
    # Selection, not credentials: the FIX 114 key gate is satisfied for every
    # provider and no real key is ever read.
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    # steps (b)/(c) structurally unreachable, so capacity.detect() answers from
    # the override file or from an explicitly installed detector double only.
    monkeypatch.setattr(capacity, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(capacity, "HARNESS_SETTINGS_CANDIDATES",
                        (tmp_path / "absent-settings.json",))
    if profile is not None:
        (cfg / resource_profile.PROFILE_FILENAME).write_text(
            json.dumps(profile, indent=2), encoding="utf-8")
    return cfg


def _install_probe(monkeypatch, *, answers, default_provider):
    """A capacity.probe double on the AGREED per-provider signature.

    `answers` maps a CANONICAL provider id onto the reading for that provider.
    `default_provider` is what the no-arg (whole-client) call answers about --
    the single global answer that is right for at most one route. Every call is
    recorded so a test can assert WHAT WAS ASKED, not only what came back."""
    calls = []

    def probe(config_dir=None, *, provider=None, model=None):
        calls.append({"provider": provider, "model": model})
        who = capacity.normalize_provider(provider) if provider else default_provider
        answer = dict(answers.get(who) or {
            "available": None, "provider": who, "status": capacity.STATUS_PARKED})
        answer.setdefault("provider", who)
        answer.setdefault("status", capacity.STATUS_MEASURED)
        answer.setdefault("detection_source", "test-fixture")
        answer["provider_requested"] = provider
        return answer

    monkeypatch.setattr(capacity, "probe", probe)
    return calls


_DEEPSEEK_2500 = {"available": 2500, "provider": capacity.PROVIDER_DEEPSEEK_DIRECT,
                  "status": capacity.STATUS_MEASURED,
                  "detection_source": "test-fixture-deepseek"}
_OLLAMA_8 = {"available": 8, "provider": capacity.PROVIDER_OLLAMA_CLOUD,
             "status": capacity.STATUS_MEASURED,
             "detection_source": "test-fixture-ollama"}
_OPENROUTER_UNBOUNDED = {"available": capacity.UNBOUNDED,
                         "provider": capacity.PROVIDER_OPENROUTER,
                         "status": capacity.STATUS_MEASURED,
                         "detection_source": "test-fixture-openrouter"}
_BOTH = {capacity.PROVIDER_DEEPSEEK_DIRECT: _DEEPSEEK_2500,
         capacity.PROVIDER_OLLAMA_CLOUD: _OLLAMA_8,
         capacity.PROVIDER_OPENROUTER: _OPENROUTER_UNBOUNDED}


# ===========================================================================
# 0. THE PREMISE, measured rather than asserted from memory.
# ===========================================================================

def _declared(record, provider):
    """The sub-record a v2 declaration holds for *provider*.

    L3 wrote these assertions against the v1 FLAT shape
    ({"provider": ..., "plan": ...}) because L1 had not merged yet. L1's F1
    made the file per-provider -- {"schema": 2, "providers": {<canonical>:
    {...}}} -- which is the entire point of the fix: a declaration about one
    provider must not speak for the box. The old assertion was
    `record["provider"] == <p>`; it is replaced rather than deleted because
    the thing it pinned still matters, and now reads: the record names THIS
    provider and nobody else's entry was disturbed.
    """
    assert record.get("schema") == 2, f"expected a v2 per-provider record: {record}"
    providers = record.get("providers") or {}
    assert provider in providers, (
        f"the declaration does not name {provider}: {record}")
    return providers[provider]

def test_the_fixture_really_does_split_the_two_routes(monkeypatch, tmp_path):
    """If a catalog change ever routes both phases to the same provider, this
    file stops reproducing the defect -- say so, loudly, instead of quietly
    testing nothing."""
    _env(monkeypatch, tmp_path, _two_provider_profile())
    ds = model_router.resolve_route(PHASE_DEEPSEEK, mode="ultra")
    oc = model_router.resolve_route(PHASE_OLLAMA, mode="ultra")
    assert capacity.normalize_provider(ds["route"]["provider"]) == \
        capacity.PROVIDER_DEEPSEEK_DIRECT, ds
    assert capacity.normalize_provider(oc["route"]["provider"]) == \
        capacity.PROVIDER_OLLAMA_CLOUD, oc
    assert ds["route"]["provider"] != oc["route"]["provider"], (
        "both phases now route to the same provider; this file no longer "
        "reproduces the two-provider client F4 was written for")


# ===========================================================================
# 1. DEFECT A -- the stamp asks about ITS OWN ROUTE.
# ===========================================================================
def test_the_stamp_asks_capacity_about_the_provider_it_will_dispatch_to(
        monkeypatch, tmp_path):
    """The direct evidence: WHAT WAS ASKED.

    On pristine main the recorded call is `{'provider': None, 'model': None}`
    -- the no-arg whole-client probe. There is no way to get a per-route width
    out of a question that never names the route."""
    _env(monkeypatch, tmp_path, _two_provider_profile())
    calls = _install_probe(monkeypatch, answers=_BOTH,
                           default_provider=capacity.PROVIDER_OLLAMA_CLOUD)

    stamp = dispatcher._routing_stamp(run_dir=tmp_path, phase_id=PHASE_DEEPSEEK)

    assert calls, "the stamp never probed capacity at all"
    asked = calls[0]
    assert capacity.normalize_provider(asked["provider"]) == \
        capacity.PROVIDER_DEEPSEEK_DIRECT, (
        "F4: the stamp must probe the ROUTED provider, not the whole client. "
        f"It asked {asked!r} while routing to {stamp.get('routed_provider')!r}")
    assert asked["model"] == "deepseek-v4-flash", (
        "the route's model resolves the plan tier for that provider "
        f"(capacity._plan_from_model_slug); it must be handed over: {asked!r}")
    assert stamp["probe_scope"] == "routed-provider", stamp


def test_a_deepseek_route_is_not_capped_by_an_ollama_plan_answer(
        monkeypatch, tmp_path):
    """THE HEADLINE. The client answered the capacity interview about
    ollama-cloud ($100/month -> 8). That answer must not touch a DeepSeek
    route, which measured 2,500 and is legitimately cut only by the operator
    mode ceiling (100).

    Pristine main: the global probe answers ollama-cloud/8, the routed provider
    is deepseek-direct, providers_match is False -> refusal -> width 3."""
    _env(monkeypatch, tmp_path, _two_provider_profile())
    _install_probe(monkeypatch, answers=_BOTH,
                   default_provider=capacity.PROVIDER_OLLAMA_CLOUD)

    stamp = dispatcher._routing_stamp(run_dir=tmp_path, phase_id=PHASE_DEEPSEEK)

    assert "capacity_refusal" not in stamp, (
        "a DeepSeek route was refused because somebody answered a question "
        f"about Ollama Cloud: {stamp}")
    assert stamp["measured_capacity"] == 100, (
        "expected the real 2,500 measurement cut to the operator ceiling 100; "
        f"got {stamp.get('measured_capacity')} -- {stamp}")
    assert stamp["capacity_status"].startswith("measured"), stamp
    assert stamp["capacity_source"].startswith("test-fixture-deepseek"), (
        "the width must be sourced from the probe about THIS route: "
        f"{stamp}")
    assert stamp["measured_capacity"] > capacity.DEFAULT_CONSERVATIVE, stamp


def test_an_ollama_route_gets_its_own_reserve_not_the_deepseek_number(
        monkeypatch, tmp_path):
    """The mirror image, and the operator's reserve ruling in one assertion:
    the Ollama-routed QC phase runs at the client's OWN 8 -- not at DeepSeek's
    2,500 (which would blow through a deliberate reserve) and not at the
    conservative floor 3 (which is what pristine main gives it)."""
    _env(monkeypatch, tmp_path, _two_provider_profile())
    _install_probe(monkeypatch, answers=_BOTH,
                   default_provider=capacity.PROVIDER_DEEPSEEK_DIRECT)

    stamp = dispatcher._routing_stamp(run_dir=tmp_path, phase_id=PHASE_OLLAMA)

    assert "capacity_refusal" not in stamp, stamp
    assert stamp["measured_capacity"] == 8, (
        "the Ollama reserve (8 for $100/month, operator ruling 2026-09-04) is "
        f"the width for an Ollama-routed phase: {stamp}")
    assert stamp["capacity_source"].startswith("test-fixture-ollama"), stamp


def test_neither_route_is_refused_when_the_global_answer_is_a_third_provider(
        monkeypatch, tmp_path):
    """The proof that the CONTRACT was the bug, not the fixture: with the
    whole-client answer about a provider NEITHER route uses, pristine main
    refuses BOTH routes to 3. There is no global answer that satisfies a
    two-provider client -- only a per-route question does."""
    _env(monkeypatch, tmp_path, _two_provider_profile())
    _install_probe(monkeypatch, answers=_BOTH,
                   default_provider=capacity.PROVIDER_OPENROUTER)

    ds = dispatcher._routing_stamp(run_dir=tmp_path, phase_id=PHASE_DEEPSEEK)
    oc = dispatcher._routing_stamp(run_dir=tmp_path, phase_id=PHASE_OLLAMA)

    assert "capacity_refusal" not in ds, ds
    assert "capacity_refusal" not in oc, oc
    assert (ds["measured_capacity"], oc["measured_capacity"]) == (100, 8), (ds, oc)


# ===========================================================================
# 2. WHAT MUST NOT CHANGE -- the guards stay. (Regression guards: these pass
#    on pristine main by design; they exist so the F4 widening cannot be
#    mistaken for permission to accept any number from anywhere.)
# ===========================================================================
def test_a_parked_routed_provider_still_refuses_loudly(monkeypatch, tmp_path):
    """The honest 'ask the client for THIS provider's plan' case. Asking about
    the right provider and getting PARKED back is not a licence to guess."""
    _env(monkeypatch, tmp_path, _two_provider_profile())
    _install_probe(monkeypatch, answers={
        capacity.PROVIDER_DEEPSEEK_DIRECT: {
            "available": None, "provider": capacity.PROVIDER_DEEPSEEK_DIRECT,
            "status": capacity.STATUS_PARKED, "detection_source": "test-fixture"},
    }, default_provider=capacity.PROVIDER_DEEPSEEK_DIRECT)

    stamp = dispatcher._routing_stamp(run_dir=tmp_path, phase_id=PHASE_DEEPSEEK)

    assert stamp["capacity_refusal"]["code"] == dispatcher.CAPACITY_REFUSAL_CODE
    assert stamp["measured_capacity"] == capacity.DEFAULT_CONSERVATIVE, stamp
    assert stamp["measured_capacity"] != dispatcher.DEFAULT_MAX_WORKERS, (
        "a fabricated 8 is indistinguishable from the operator's Ollama "
        f"reserve -- U1 removed it and F4 does not put it back: {stamp}")


def test_a_probe_that_answers_about_someone_else_is_still_refused(
        monkeypatch, tmp_path):
    """The identity guard becomes a tautology once capacity honours the
    kwarg -- but only THEN. A capacity build that ignores the question and
    answers about a different provider must still be refused, never trusted
    because we asked nicely."""
    _env(monkeypatch, tmp_path, _two_provider_profile())

    def liar(config_dir=None, *, provider=None, model=None):
        return {"available": 2500, "provider": capacity.PROVIDER_OLLAMA_CLOUD,
                "status": capacity.STATUS_MEASURED,
                "detection_source": "test-fixture-liar",
                "provider_requested": provider}
    monkeypatch.setattr(capacity, "probe", liar)

    stamp = dispatcher._routing_stamp(run_dir=tmp_path, phase_id=PHASE_DEEPSEEK)

    assert stamp["capacity_refusal"]["code"] == dispatcher.CAPACITY_REFUSAL_CODE
    assert stamp["measured_capacity"] == capacity.DEFAULT_CONSERVATIVE, stamp


def test_an_unresolvable_provider_identity_is_still_loud(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, _two_provider_profile())

    def unknown(config_dir=None, *, provider=None, model=None):
        return {"available": 2500, "provider": "some-random-unknown-llm",
                "status": capacity.STATUS_MEASURED,
                "detection_source": "test-fixture", "provider_requested": provider}
    monkeypatch.setattr(capacity, "probe", unknown)

    stamp = dispatcher._routing_stamp(run_dir=tmp_path, phase_id=PHASE_DEEPSEEK)

    assert stamp["capacity_status"].startswith("provider-unresolved"), stamp
    assert stamp["capacity_refusal"]["code"] == dispatcher.CAPACITY_REFUSAL_CODE


def test_the_global_fallback_is_recorded_never_hidden(monkeypatch, tmp_path):
    """A capacity build with no per-provider probe (pre-F1, or a rollback)
    degrades to today's global answer. That is a DEGRADATION of a fix, so it is
    stamped `probe_scope='global-no-arg'` and readable in the sidecar -- never
    a silent revert to the defect."""
    _env(monkeypatch, tmp_path, _two_provider_profile())

    def legacy(config_dir=None):          # the pre-F1 signature, exactly
        return {"available": 2500, "provider": capacity.PROVIDER_DEEPSEEK_DIRECT,
                "status": capacity.STATUS_MEASURED,
                "detection_source": "test-fixture-legacy"}
    monkeypatch.setattr(capacity, "probe", legacy)

    stamp = dispatcher._routing_stamp(run_dir=tmp_path, phase_id=PHASE_DEEPSEEK)

    assert stamp["probe_scope"] == "global-no-arg", stamp
    assert "probe_requested" not in stamp, stamp
    assert stamp["measured_capacity"] == 100, (
        "the legacy path must still behave exactly as it does on main: "
        f"{stamp}")


def test_resolve_max_workers_keeps_its_whole_client_probe(monkeypatch,
                                                          tmp_path):
    """DO NOT 'FIX' THIS ONE. resolve_max_workers sizes the work-order POOL,
    which serves every route in the run; naming one provider there would cap
    the whole pool at one provider's ceiling -- Defect 1 rebuilt in a second
    place. Per-provider bounding is the governor's `max_inflight`, applied per
    lease."""
    _env(monkeypatch, tmp_path, _two_provider_profile())
    calls = _install_probe(monkeypatch, answers=_BOTH,
                           default_provider=capacity.PROVIDER_DEEPSEEK_DIRECT)

    dispatcher.resolve_max_workers(tmp_path, None)

    assert calls, "resolve_max_workers never probed capacity"
    assert all(c["provider"] is None for c in calls), (
        "the work-order pool must ask the WHOLE-CLIENT question, with no "
        f"provider: {calls}")


# ===========================================================================
# 3. THE OPERATOR MESSAGE -- stop handing out the advice that breaks the
#    other provider.
# ===========================================================================
def test_the_refusal_no_longer_tells_the_operator_to_write_a_client_override(
        monkeypatch, tmp_path, capsys):
    """The old text said "Declare capacity_override.json for this provider".
    THAT ADVICE IS THE OTHER HALF OF DEFECT 1: before F1/F2 that file is a
    single-provider, whole-client answer that pre-empts detection, so an
    operator following it to widen route A pinned every other route to A's
    plan. Point at the two doors that are per-provider instead."""
    _env(monkeypatch, tmp_path, _two_provider_profile())
    _install_probe(monkeypatch, answers={}, default_provider=None)

    stamp = dispatcher._routing_stamp(run_dir=tmp_path, phase_id=PHASE_OLLAMA)
    err = capsys.readouterr().err

    assert stamp["capacity_refusal"], stamp
    assert "Declare capacity_override.json for this provider" not in err, (
        "the refusal still tells the operator to write a whole-client "
        f"override: {err}")
    assert "--declare-provider" in err, err
    assert "--capacity" in err, err
    assert capacity.PROVIDER_OLLAMA_CLOUD in err, (
        "the message must NAME the provider whose plan is missing, so the "
        f"operator answers for the right one: {err}")


# ===========================================================================
# 4. DEFECT B -- --declare-capacity declares a PROVIDER, and never PARKs.
# ===========================================================================
def _dept(tmp_path):
    """A dept_root whose `scripts` dir exists, so ensure_capacity_override's
    sys.path insert is a no-op and the already-imported capacity module (env
    redirected by _env) is the one it uses."""
    dept = tmp_path / "dept"
    (dept / "scripts").mkdir(parents=True, exist_ok=True)
    return dept


def test_declare_capacity_for_a_named_provider_never_parks(monkeypatch,
                                                           tmp_path):
    """MEASURED defect: the hard-coded `{provider: deepseek-direct,
    max_concurrent: N}` record PARKS (deepseek-direct is a cap-table provider
    since 2026-09-04, and a cap-table provider with no plan is
    _resolve_override case 2). The declaration must resolve MEASURED."""
    cfg = _env(monkeypatch, tmp_path, _two_provider_profile())

    path = dispatcher.ensure_capacity_override(
        _dept(tmp_path), max_concurrent=100,
        provider="deepseek-direct", model="deepseek-v4-flash")

    assert path is not None and path.is_file(), path
    record = json.loads(path.read_text(encoding="utf-8"))
    entry = _declared(record, capacity.PROVIDER_DEEPSEEK_DIRECT)
    assert entry.get("plan") == "v4-flash", (
        "without a plan the record PARKs the run it was meant to widen: "
        f"{record}")

    result = capacity.probe(cfg)
    assert result["status"] == capacity.STATUS_MEASURED, (
        f"--declare-capacity 100 PARKED the run: {result['status']} "
        f"{result.get('notes')}")
    assert result["available"] == 100, result
    assert result["autofail_code"] is None, result


def test_declare_capacity_refuses_when_no_provider_can_be_established(
        monkeypatch, tmp_path):
    """No --declare-provider, and detection resolves nobody. Pristine main
    writes a deepseek-direct record anyway -- a GUESS, and the one guess that
    PARKs. Refuse, and write NOTHING."""
    cfg = _env(monkeypatch, tmp_path, _two_provider_profile())

    with pytest.raises(dispatcher.CapacityDeclarationRefused) as exc:
        dispatcher.ensure_capacity_override(_dept(tmp_path), max_concurrent=100)

    assert not (cfg / capacity.OVERRIDE_FILENAME).exists(), (
        "a refusal that still wrote the file is not a refusal")
    assert "--declare-provider" in str(exc.value), exc.value


def test_declare_capacity_refuses_a_cap_table_provider_with_no_plan(
        monkeypatch, tmp_path):
    """The exact record Fable measured as PARKED is never written again."""
    cfg = _env(monkeypatch, tmp_path, _two_provider_profile())

    with pytest.raises(dispatcher.CapacityDeclarationRefused) as exc:
        dispatcher.ensure_capacity_override(_dept(tmp_path), max_concurrent=100,
                                            provider="deepseek-direct")

    assert not (cfg / capacity.OVERRIDE_FILENAME).exists()
    assert "PARK" in str(exc.value).upper(), exc.value
    assert "--declare-plan" in str(exc.value), exc.value


def test_declare_capacity_takes_the_plan_from_the_profile_lock(monkeypatch,
                                                               tmp_path):
    """The resource profile is the per-provider store of plan answers (F1/F2).
    A client who answered the interview for ollama-cloud does not have to
    re-type the tier on the command line."""
    profile = _two_provider_profile()
    profile["providers"]["ollama-cloud"].update(
        {"plan_tier": "$100/month", "plan_known": True, "locked": True,
         "concurrency_ceiling": 8})
    cfg = _env(monkeypatch, tmp_path, profile)

    path = dispatcher.ensure_capacity_override(
        _dept(tmp_path), max_concurrent=5, provider="ollama-cloud")

    record = json.loads(path.read_text(encoding="utf-8"))
    entry = _declared(record, capacity.PROVIDER_OLLAMA_CLOUD)
    assert entry["plan"] == "$100/month", record
    result = capacity.probe(cfg)
    assert result["status"] == capacity.STATUS_MEASURED, result
    # a declared number may only LOWER a cap-table row, never raise it
    assert result["available"] == 5, result


def test_declare_capacity_never_hardcodes_deepseek_direct(monkeypatch,
                                                          tmp_path):
    """With no --declare-provider, the provider is the one THIS BOX detected.
    On a client whose 9Router routes to Ollama Cloud, writing a deepseek-direct
    record is a claim about a provider they do not use."""
    cfg = _env(monkeypatch, tmp_path, _two_provider_profile())
    monkeypatch.setattr(capacity, "detect_from_9router", lambda *a, **k: {
        "hit": True, "provider": capacity.PROVIDER_OLLAMA_CLOUD,
        "plan": "$100/month", "detail": "test-fixture"})

    dispatcher.ensure_capacity_override(_dept(tmp_path), max_concurrent=8)

    # read the FILE, not the return value: pristine main returns None while
    # still writing, and the defect is what landed on disk.
    written = cfg / capacity.OVERRIDE_FILENAME
    assert written.is_file(), "nothing was declared"
    record = json.loads(written.read_text(encoding="utf-8"))
    _declared(record, capacity.PROVIDER_OLLAMA_CLOUD)  # names the DETECTED
    assert capacity.PROVIDER_DEEPSEEK_DIRECT not in (record.get("providers") or {}), (
        "the declaration must be about the provider this box actually "
        f"detected, never a hard-coded deepseek-direct: {record}")
    assert capacity.probe(cfg)["status"] == capacity.STATUS_MEASURED


def test_declare_capacity_refuses_an_unknown_provider_name(monkeypatch,
                                                           tmp_path):
    cfg = _env(monkeypatch, tmp_path, _two_provider_profile())
    with pytest.raises(dispatcher.CapacityDeclarationRefused):
        dispatcher.ensure_capacity_override(
            _dept(tmp_path), max_concurrent=100, provider="some-random-unknown-llm")
    assert not (cfg / capacity.OVERRIDE_FILENAME).exists()


def test_declare_capacity_is_still_idempotent(monkeypatch, tmp_path):
    """REGRESSION GUARD: an existing declaration is the client's, not ours."""
    cfg = _env(monkeypatch, tmp_path, _two_provider_profile())
    existing = {"provider": "ollama-cloud", "plan": "$20/month"}
    (cfg / capacity.OVERRIDE_FILENAME).write_text(json.dumps(existing),
                                                  encoding="utf-8")

    dispatcher.ensure_capacity_override(_dept(tmp_path), max_concurrent=100,
                                        provider="deepseek-direct",
                                        model="deepseek-v4-flash")

    assert json.loads((cfg / capacity.OVERRIDE_FILENAME).read_text(
        encoding="utf-8")) == existing


def test_declare_capacity_uses_capacity_declare_capacity_when_it_exists(
        monkeypatch, tmp_path):
    """F1 ships `capacity.declare_capacity(provider, *, plan, max_concurrent,
    config_dir)` -- the per-provider writer that preserves every OTHER
    provider's sub-record. The dispatcher must route through it rather than
    hand-rolling a whole-file write that clobbers them."""
    _env(monkeypatch, tmp_path, _two_provider_profile())
    seen = {}

    def declare_capacity(provider, *, plan=None, max_concurrent=None,
                         config_dir=None):
        seen.update({"provider": provider, "plan": plan,
                     "max_concurrent": max_concurrent})
        return tmp_path / "written-by-capacity.json"

    monkeypatch.setattr(capacity, "declare_capacity", declare_capacity,
                        raising=False)

    dispatcher.ensure_capacity_override(_dept(tmp_path), max_concurrent=100,
                                        provider="deepseek-direct",
                                        model="deepseek-v4-flash")

    assert seen == {"provider": capacity.PROVIDER_DEEPSEEK_DIRECT,
                    "plan": "v4-flash", "max_concurrent": 100}, seen


# ===========================================================================
# 5. THE CLI DOOR
# ===========================================================================
def test_the_cli_exposes_declare_provider_and_declare_plan():
    args = dispatcher.build_parser().parse_args(
        ["--run-dir", "/tmp/x", "--declare-capacity", "100",
         "--declare-provider", "ollama-cloud", "--declare-plan", "$100/month"])
    assert args.declare_capacity == 100
    assert args.declare_provider == "ollama-cloud"
    assert args.declare_plan == "$100/month"


def test_the_cli_exits_2_on_a_refusal_and_dispatches_nothing(monkeypatch,
                                                             tmp_path,
                                                             capsys):
    swept = []
    monkeypatch.setattr(dispatcher, "sweep_run_dir",
                        lambda *a, **k: swept.append(a) or [])

    def refuse(*a, **k):
        raise dispatcher.CapacityDeclarationRefused("no provider, no write")
    monkeypatch.setattr(dispatcher, "ensure_capacity_override", refuse)

    rc = dispatcher.main(["--run-dir", str(tmp_path), "--once",
                          "--declare-capacity", "100"])

    assert rc == 2, rc
    assert swept == [], "a refused declaration must not dispatch anything"
    assert "no provider, no write" in capsys.readouterr().err


def test_the_cli_passes_the_declared_provider_through(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(dispatcher, "sweep_run_dir", lambda *a, **k: [])
    monkeypatch.setattr(dispatcher, "ensure_capacity_override",
                        lambda dept_root, **k: seen.update(k))

    dispatcher.main(["--run-dir", str(tmp_path), "--once",
                     "--declare-capacity", "100",
                     "--declare-provider", "ollama-cloud",
                     "--declare-plan", "$100/month"])

    assert seen == {"max_concurrent": 100, "provider": "ollama-cloud",
                    "plan": "$100/month"}, seen
