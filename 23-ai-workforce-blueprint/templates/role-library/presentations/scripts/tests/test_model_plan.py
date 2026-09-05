#!/usr/bin/env python3
"""test_model_plan.py -- the client's model choice is the client's.

OPERATOR REQUIREMENT (2026-09-04, verbatim):
    "whatever is forcing this thing to use DeepSeek V4 Pro, I don't want to be
     forced to do anything. So as a client should be able to choose whatever
     they want to be their primary workhorse or authoring model."

WHAT THIS FILE PINS, mechanically, in order:

  1. A declared workhorse BEATS model_router.CAPABILITY_CANDIDATES. That table
     is now the default for a client who declares nothing, not the only answer.
     (test_declared_workhorse_beats_the_department_default -- this is the test
     that FAILS on unmodified main, where P4-COPY routes to deepseek-direct no
     matter what the client asked for.)
  2. FLOORS still hold, and a client can still overrule them ON PURPOSE. A
     standard-context workhorse does NOT silently serve a long-context class:
     it falls back VISIBLY (decision["client_plan_floor"]). Naming that model
     explicitly for the reasoning slot, with the class waived, DOES route it --
     "not forced" cuts both ways.
  3. A judge can be pointed at a provider the judge class never had a candidate
     for (ollama-cloud), which is impossible on unmodified main.
  4. NO REGRESSION for a client who declares nothing -- and the default table
     is never MUTATED by a client's choice (the copies-vs-refs trap:
     _mode_candidates returns the LIVE list object for non-economy modes).
  5. The plan SURVIVES THE REDACTION FILTER. resource_profile.redact_record
     drops any key matching (...|auth|...) on every save and load; "authoring"
     contains "auth". The counterfactual is asserted too, so this test can
     actually detect the fault it pins.
  6. The REAL, unmodified deck-intake-driver.py records a plan from a real
     merged-turn answer, and REFUSES a model the provider does not wire -- at
     intake, with the wired inventory named, not at dispatch time.
  7. The LAUNCHER refuses (AF-MODEL-PLAN-UNSATISFIED, nothing spawned) when a
     class the client's plan covers has no eligible route.

Unit-level: no network, no spend, no engine. Every profile is written into a
tmp config dir the capacity/profile env points at.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import launcher  # noqa: E402
from presentation_job import model_router  # noqa: E402
from presentation_job import resource_profile  # noqa: E402

DRIVER = SCRIPTS / "deck-intake-driver.py"


# ---------------------------------------------------------------------------
# rig
# ---------------------------------------------------------------------------
def _wired(provider, models, **extra):
    return dict({"provider": provider, "consented": True, "detected": True,
                 "presence": True, "wired_models": list(models)}, **extra)


TWO_PROVIDER_PROFILE = {
    ".schema_version": 1,
    "providers": {
        "deepseek-direct": _wired("deepseek-direct",
                                  ["deepseek-v4-flash", "deepseek-v4-pro"]),
        "openrouter": _wired("openrouter",
                             ["z-ai/glm-5.3-flash", "z-ai/glm-5.3"]),
    },
    "creative_prefs": {}, "consent": {}, "interview": {},
}


def _profile_env(monkeypatch, tmp_path, profile=None):
    """Point the profile store at a tmp config dir and (optionally) seed it.

    Uses PRESENTATION_CAPACITY_CONFIG_DIR -- the operator-controlled redirect
    resource_profile.department_config_dir() follows -- exactly as
    test_capacity_detection.py does."""
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    monkeypatch.delenv("PRESENTATION_RESOURCE_PROFILE_DIR", raising=False)
    monkeypatch.delenv("PRESENTATION_RESOURCE_PROFILE", raising=False)
    monkeypatch.delenv("PRESENTATION_MODEL_ROUTER", raising=False)
    monkeypatch.delenv("PRESENTATION_MODES", raising=False)
    # FIX 114 key gate: the router refuses a provider with no resolvable
    # credential. These tests are about SELECTION, not credentials, so the gate
    # is satisfied for every provider and nothing here ever reads a real key.
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    if profile is not None:
        (cfg / resource_profile.PROFILE_FILENAME).write_text(
            json.dumps(profile, indent=2), encoding="utf-8")
    return cfg


def _with_plan(plan, providers=None):
    prof = copy.deepcopy(TWO_PROVIDER_PROFILE)
    if providers is not None:
        prof["providers"] = providers
    prof["model_plan"] = plan
    return prof


def _default_route_for(capability):
    """What the department default resolves to for this class -- read from
    CAPABILITY_CANDIDATES itself, never hardcoded, so a later reorder of the
    table cannot make this file quietly assert the wrong thing."""
    alias = str((model_router.CAPABILITY_CANDIDATES[capability] or [{}])[0]
                .get("alias") or "")
    alias_def = model_router.resolve_alias(alias)
    provider = alias_def["provider"]
    return {"provider": provider,
            "model": model_router._served_model(alias_def, provider)}


# ---------------------------------------------------------------------------
# 1. THE REQUIREMENT: a declared workhorse beats the department default
# ---------------------------------------------------------------------------
def test_declared_workhorse_beats_the_department_default(monkeypatch, tmp_path):
    """FAILS on unmodified main: P4-COPY routes to the authoring table's first
    eligible candidate (deepseek-direct) regardless of what the client owns,
    wants, or declared."""
    _profile_env(monkeypatch, tmp_path, _with_plan({
        "workhorse": {"provider": "openrouter", "model": "z-ai/glm-5.3-flash"},
        "reasoning": None, "judge": None, "thinking": None,
        "floor_waivers": [], "source": "interview",
    }))
    decision = model_router.resolve_route("P4-COPY")
    assert decision["route"] == {"provider": "openrouter",
                                 "model": "z-ai/glm-5.3-flash"}, decision
    assert decision["client_plan"]["slot"] == "workhorse"
    assert decision["client_plan"]["applied"] is True
    assert decision["client_plan"]["floor"] == "ok"


def test_the_default_is_still_the_default_without_a_declaration(monkeypatch, tmp_path):
    """The same profile, no model_plan: the pre-change answer, unchanged."""
    _profile_env(monkeypatch, tmp_path, copy.deepcopy(TWO_PROVIDER_PROFILE))
    decision = model_router.resolve_route("P4-COPY")
    assert decision["route"] == _default_route_for("authoring"), decision
    assert "client_plan" not in decision
    assert "client_plan_floor" not in decision


def test_a_declared_workhorse_governs_every_workhorse_class(monkeypatch, tmp_path):
    _profile_env(monkeypatch, tmp_path, _with_plan({
        "workhorse": {"provider": "openrouter", "model": "z-ai/glm-5.3-flash"},
        "floor_waivers": [],
    }))
    for phase in ("P4-COPY", "P4-PROMPT", "P0A-INTAKE", "PF-DESIGN"):
        decision = model_router.resolve_route(phase)
        assert decision["route"] == {"provider": "openrouter",
                                     "model": "z-ai/glm-5.3-flash"}, (phase, decision)


def test_the_workhorse_never_spills_into_the_judge_class(monkeypatch, tmp_path):
    """Judge independence: the module exists partly because 'QC judges could
    silently ride the same model identity that authored the artifact'. An
    UNNAMED judge slot keeps the department default -- the workhorse does not
    reach it."""
    _profile_env(monkeypatch, tmp_path, _with_plan({
        "workhorse": {"provider": "openrouter", "model": "z-ai/glm-5.3-flash"},
        "floor_waivers": [],
    }))
    decision = model_router.resolve_route("P1Q-COPY-QC")
    assert decision["route"] == _default_route_for("judge"), decision
    assert "client_plan" not in decision


# ---------------------------------------------------------------------------
# 2. FLOORS: visible fallback, and an explicit waiver that really routes
# ---------------------------------------------------------------------------
def test_a_standard_workhorse_falls_back_visibly_on_a_long_context_class(
        monkeypatch, tmp_path):
    _profile_env(monkeypatch, tmp_path, _with_plan({
        "workhorse": {"provider": "deepseek-direct", "model": "deepseek-v4-flash"},
        "floor_waivers": [],
    }))
    decision = model_router.resolve_route("P3-ARC")
    assert decision["capability"] == "reasoning_long"
    assert decision["route"]["model"] == "deepseek-v4-pro", decision
    assert "client_plan" not in decision
    floor = decision["client_plan_floor"]
    assert floor["via"] == "workhorse-spill"
    assert floor["declared"]["model"] == "deepseek-v4-flash"
    assert floor["floor"]["ok"] is False
    assert "long" in floor["floor"]["reason"]
    assert floor["fallback_alias"] == "deepseek-v4-pro"


def test_an_explicitly_waived_reasoning_slot_is_honoured(monkeypatch, tmp_path):
    """Trevor: not forced. A client who NAMES a standard-context model for the
    reasoning slot and waives the class GETS that model."""
    _profile_env(monkeypatch, tmp_path, _with_plan({
        "workhorse": {"provider": "deepseek-direct", "model": "deepseek-v4-flash"},
        "reasoning": {"provider": "deepseek-direct", "model": "deepseek-v4-flash"},
        "floor_waivers": ["reasoning_long"],
    }))
    decision = model_router.resolve_route("P3-ARC")
    assert decision["route"] == {"provider": "deepseek-direct",
                                 "model": "deepseek-v4-flash"}, decision
    assert decision["client_plan"]["floor"] == "waived"
    assert decision["client_plan"]["slot"] == "reasoning"
    assert decision["client_plan"]["applied"] is True


def test_a_waiver_does_not_leak_to_an_unwaived_class(monkeypatch, tmp_path):
    """reasoning_long waived does not silently waive long_synthesis."""
    _profile_env(monkeypatch, tmp_path, _with_plan({
        "reasoning": {"provider": "deepseek-direct", "model": "deepseek-v4-flash"},
        "floor_waivers": ["reasoning_long"],
    }))
    assert model_router.resolve_route("P3-ARC")["route"]["model"] == "deepseek-v4-flash"
    other = model_router.resolve_route("P-CONVERTER")
    assert other["capability"] == "long_synthesis"
    assert other["route"]["model"] == "deepseek-v4-pro", other
    assert other["client_plan_floor"]["floor"]["ok"] is False


def test_an_unknown_wired_id_never_clears_a_long_floor(monkeypatch, tmp_path):
    """Nobody measured an arbitrary wired id's context window. UNKNOWN is the
    absence of a reading, never evidence of a longer one -- the same doctrine
    that stops an unmeasured capacity ceiling from becoming a wide one."""
    _profile_env(monkeypatch, tmp_path, _with_plan({
        "workhorse": {"provider": "openrouter", "model": "z-ai/glm-5.3-flash"},
        "reasoning": {"provider": "openrouter", "model": "some-unlisted-id"},
        "floor_waivers": [],
    }, providers={"openrouter": _wired("openrouter", ["z-ai/glm-5.3-flash",
                                                      "z-ai/glm-5.3",
                                                      "some-unlisted-id"])}))
    decision = model_router.resolve_route("P3-ARC")
    assert decision["route"]["model"] == "z-ai/glm-5.3", decision
    assert decision["client_plan_floor"]["floor"]["context_class"] == "unknown"


# ---------------------------------------------------------------------------
# 3. A judge on a provider the judge class never had a candidate for
# ---------------------------------------------------------------------------
def test_judge_can_be_pointed_at_ollama_cloud(monkeypatch, tmp_path):
    """Impossible on unmodified main: the judge class's candidates are
    deepseek-v4-flash / glm-flash / glm-5.3, none of them on ollama-cloud."""
    providers = {
        "deepseek-direct": _wired("deepseek-direct",
                                  ["deepseek-v4-flash", "deepseek-v4-pro"]),
        "ollama-cloud": _wired("ollama-cloud", ["glm-5.3-flash"]),
    }
    _profile_env(monkeypatch, tmp_path, _with_plan({
        "judge": {"provider": "ollama-cloud", "model": "glm-5.3-flash"},
        "floor_waivers": [],
    }, providers=providers))
    decision = model_router.resolve_route("P1Q-COPY-QC")
    assert decision["route"] == {"provider": "ollama-cloud",
                                 "model": "glm-5.3-flash"}, decision
    assert decision["client_plan"]["slot"] == "judge"
    assert not any(model_router._norm_provider(
        model_router.resolve_alias(c["alias"]).get("provider")) == "ollama-cloud"
        for c in model_router.CAPABILITY_CANDIDATES["judge"]), (
        "the judge class must still carry NO ollama-cloud default candidate -- "
        "otherwise this test proves nothing about the client plan")


# ---------------------------------------------------------------------------
# 4. NO REGRESSION + the mutation guard
# ---------------------------------------------------------------------------
def test_the_default_candidate_table_is_never_mutated(monkeypatch, tmp_path):
    """_mode_candidates() returns the LIVE CAPABILITY_CANDIDATES list object
    for every non-economy mode. Prepending a client's choice IN PLACE would
    rewrite the department default process-wide -- every later phase, every
    other client in the same process, permanently."""
    _profile_env(monkeypatch, tmp_path, _with_plan({
        "workhorse": {"provider": "openrouter", "model": "z-ai/glm-5.3-flash"},
        "judge": {"provider": "openrouter", "model": "z-ai/glm-5.3-flash"},
        "floor_waivers": [],
    }))
    before = copy.deepcopy(model_router.CAPABILITY_CANDIDATES)
    authoring_list_id = id(model_router.CAPABILITY_CANDIDATES["authoring"])
    for _ in range(50):
        model_router.resolve_route("P4-COPY")
        model_router.resolve_route("P1Q-COPY-QC")
    assert model_router.CAPABILITY_CANDIDATES == before
    assert model_router.CAPABILITY_CANDIDATES["authoring"] == before["authoring"]
    assert id(model_router.CAPABILITY_CANDIDATES["authoring"]) == authoring_list_id
    assert len(model_router.CAPABILITY_CANDIDATES["authoring"]) == \
        len(before["authoring"])


def test_a_client_choice_jumps_the_queue_never_the_gate(monkeypatch, tmp_path):
    """A declared model the provider does not wire is judged by the SAME
    _eligible() every default candidate faces -- it does not route, the run
    falls back to the default, and the rejection is on the record."""
    _profile_env(monkeypatch, tmp_path, _with_plan({
        "workhorse": {"provider": "openrouter", "model": "z-ai/glm-not-wired"},
        "floor_waivers": [],
    }))
    decision = model_router.resolve_route("P4-COPY")
    assert decision["route"] == _default_route_for("authoring"), decision
    assert decision["client_plan"]["applied"] is False
    assert "not in openrouter's wired inventory" in \
        decision["client_plan"]["rejected_reason"]


def test_a_plan_on_a_provider_less_profile_cannot_be_recorded(monkeypatch, tmp_path):
    """A plan with no providers is INVISIBLE, not merely unused: resolve_route
    reports profile_state 'absent' and the dispatcher falls back to its default
    model. record_model_plan refuses rather than telling the client 'recorded'
    and then overriding them on every call."""
    _profile_env(monkeypatch, tmp_path, {".schema_version": 1, "providers": {}})
    with pytest.raises(ValueError) as exc:
        resource_profile.record_model_plan(
            {"workhorse": "deepseek-v4-flash@deepseek-direct"}, source="cli")
    assert "NO providers" in str(exc.value)
    assert "--capacity" in str(exc.value)
    decision = model_router.resolve_route("P4-COPY")
    assert decision["profile_state"] == "absent"


# ---------------------------------------------------------------------------
# 5. THE REDACTION FILTER (and the counterfactual that proves it detects it)
# ---------------------------------------------------------------------------
def test_the_plan_survives_a_real_save_load_round_trip(monkeypatch, tmp_path):
    cfg = _profile_env(monkeypatch, tmp_path, copy.deepcopy(TWO_PROVIDER_PROFILE))
    resource_profile.record_model_plan(
        {"workhorse": "z-ai/glm-5.3-flash@openrouter",
         "judge": "z-ai/glm-5.3@openrouter",
         "thinking": "max"},
        source="interview")
    reloaded = resource_profile.load_profile(cfg)
    plan = reloaded["model_plan"]
    assert plan["workhorse"] == {"provider": "openrouter",
                                 "model": "z-ai/glm-5.3-flash"}
    assert plan["judge"] == {"provider": "openrouter", "model": "z-ai/glm-5.3"}
    assert plan["thinking"] == "max"
    assert plan["source"] == "interview" and plan["declared_at"]
    assert reloaded["interview"]["model_plan"][-1]["source"] == "interview"
    # and the router reads exactly that, off disk, with no profile handed in
    assert model_router.resolve_route("P4-COPY")["route"] == {
        "provider": "openrouter", "model": "z-ai/glm-5.3-flash"}


def test_the_redaction_filter_really_would_have_eaten_authoring_model():
    """The counterfactual. Without it, the round-trip test above proves only
    that SOMETHING survived, not that the naming choice was the reason."""
    kept = resource_profile.redact_record(
        {"model_plan": {"workhorse": {"provider": "openrouter",
                                      "model": "z-ai/glm-5.3-flash"},
                        "reasoning": None, "judge": None, "thinking": "max",
                        "floor_waivers": ["reasoning_long"]}})
    assert kept["model_plan"]["workhorse"]["model"] == "z-ai/glm-5.3-flash"
    assert set(kept["model_plan"]) == {"workhorse", "reasoning", "judge",
                                       "thinking", "floor_waivers"}
    eaten = resource_profile.redact_record(
        {"authoring_model": "z-ai/glm-5.3-flash", "api_key_name": "x",
         "workhorse": "kept"})
    assert "authoring_model" not in eaten, (
        "redact_record must still drop an 'auth'-matching key -- if it does "
        "not, this file's naming rationale is stale")
    assert eaten == {"workhorse": "kept"}


def test_record_model_plan_names_the_wired_inventory_it_checked(monkeypatch, tmp_path):
    _profile_env(monkeypatch, tmp_path, copy.deepcopy(TWO_PROVIDER_PROFILE))
    with pytest.raises(ValueError) as exc:
        resource_profile.record_model_plan(
            {"workhorse": "nope@deepseek-direct"}, source="cli")
    msg = str(exc.value)
    assert "not in deepseek-direct's wired inventory" in msg
    assert "deepseek-v4-flash" in msg and "deepseek-v4-pro" in msg


def test_record_model_plan_names_the_providers_that_do_exist(monkeypatch, tmp_path):
    _profile_env(monkeypatch, tmp_path, copy.deepcopy(TWO_PROVIDER_PROFILE))
    with pytest.raises(ValueError) as exc:
        resource_profile.record_model_plan(
            {"workhorse": "glm-ocr@ollama-cloud"}, source="cli")
    msg = str(exc.value)
    assert "does not carry provider 'ollama-cloud'" in msg
    assert "deepseek-direct" in msg and "openrouter" in msg


def test_a_context_shortfall_is_waived_but_a_modality_shortfall_is_refused(
        monkeypatch, tmp_path):
    """Modality is physics; context is judgement. A standard-window model named
    for reasoning is HONOURED with a recorded waiver; an image model named for
    a text slot is REFUSED, because no waiver makes it able to do the job."""
    cfg = _profile_env(monkeypatch, tmp_path, copy.deepcopy(TWO_PROVIDER_PROFILE))
    prof = resource_profile.record_model_plan(
        {"reasoning": "deepseek-v4-flash@deepseek-direct"}, source="cli")
    assert "reasoning_long" in prof["model_plan"]["floor_waivers"]
    assert "long_synthesis" in prof["model_plan"]["floor_waivers"]
    assert prof["interview"]["model_plan"][-1]["waiver_reasons"]
    assert model_router.resolve_route("P3-ARC", config_dir=cfg)[
        "client_plan"]["floor"] == "waived"

    prof["providers"]["kie"] = _wired("kie", ["gpt-image-2"])
    resource_profile.save_profile(prof, cfg)
    with pytest.raises(ValueError) as exc:
        resource_profile.record_model_plan(
            {"workhorse": "gpt-image-2@kie"}, source="cli")
    assert "no waiver crosses it" in str(exc.value)


def test_a_catalog_alias_is_accepted_and_routes_to_the_served_id(
        monkeypatch, tmp_path):
    """A client may name the catalog ALIAS ("glm-flash") rather than the id
    OpenRouter serves for it ("z-ai/glm-5.3-flash"). The wired-inventory check
    must consider the served id -- checking only the alias would refuse a
    declaration that routes perfectly."""
    cfg = _profile_env(monkeypatch, tmp_path, copy.deepcopy(TWO_PROVIDER_PROFILE))
    prof = resource_profile.record_model_plan({"workhorse": "glm-flash@openrouter"},
                                              source="cli")
    assert prof["model_plan"]["workhorse"] == {"provider": "openrouter",
                                               "model": "glm-flash"}
    assert model_router.resolve_route("P4-COPY", config_dir=cfg)["route"] == {
        "provider": "openrouter", "model": "z-ai/glm-5.3-flash"}


def test_a_later_answer_updates_the_plan_and_appends_an_audit_row(
        monkeypatch, tmp_path):
    """A client changing their workhorse must never need an operator."""
    cfg = _profile_env(monkeypatch, tmp_path, copy.deepcopy(TWO_PROVIDER_PROFILE))
    resource_profile.record_model_plan(
        {"workhorse": "deepseek-v4-flash@deepseek-direct"}, source="interview")
    prof = resource_profile.record_model_plan(
        {"workhorse": "z-ai/glm-5.3-flash@openrouter"}, source="interview")
    assert prof["model_plan"]["workhorse"] == {"provider": "openrouter",
                                               "model": "z-ai/glm-5.3-flash"}
    assert len(prof["interview"]["model_plan"]) == 2
    assert model_router.resolve_route("P4-COPY", config_dir=cfg)["route"] == {
        "provider": "openrouter", "model": "z-ai/glm-5.3-flash"}


# ---------------------------------------------------------------------------
# 6. THE REAL DRIVER, end to end
# ---------------------------------------------------------------------------
def _driver(run_dir, cfg, qid, text):
    env = dict(os.environ)
    env[capacity.CONFIG_DIR_ENV] = str(cfg)
    env.pop("PRESENTATION_RESOURCE_PROFILE_DIR", None)
    return subprocess.run(
        [sys.executable, str(DRIVER), "--run-dir", str(run_dir),
         "--answer", qid, text],
        capture_output=True, text=True, env=env)


def test_the_real_driver_records_a_model_plan_from_one_merged_turn(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / resource_profile.PROFILE_FILENAME).write_text(
        json.dumps({".schema_version": 1, "providers": {
            "deepseek-direct": _wired("deepseek-direct",
                                      ["deepseek-v4-flash", "deepseek-v4-pro"]),
            "ollama-cloud": _wired("ollama-cloud", ["glm-5.3-flash"]),
        }}, indent=2), encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    proc = _driver(run_dir, cfg, "resource_plan",
                   "plan: v4-flash; workhorse: deepseek-v4-flash@deepseek-direct; "
                   "qc: glm-5.3-flash@ollama-cloud; thinking: max")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    plan = json.loads((cfg / resource_profile.PROFILE_FILENAME)
                      .read_text(encoding="utf-8"))["model_plan"]
    assert plan["workhorse"] == {"provider": "deepseek-direct",
                                 "model": "deepseek-v4-flash"}
    assert plan["judge"] == {"provider": "ollama-cloud", "model": "glm-5.3-flash"}
    assert plan["thinking"] == "max"
    assert plan["source"] == "interview"

    ledger = json.loads((run_dir / "working" / "interview" /
                         "intake_ledger.json").read_text(encoding="utf-8"))
    entries = ledger["entries"]
    for key, expected in (("WORKHORSE_MODEL", "deepseek-v4-flash@deepseek-direct"),
                          ("QC_MODEL", "glm-5.3-flash@ollama-cloud"),
                          ("THINKING_MODE", "max")):
        assert key in entries, sorted(entries)
        assert entries[key]["value"] == expected, (key, entries[key])
    assert entries["REASONING_MODEL"]["value"] == ""


def test_the_real_driver_refuses_an_unwired_model_at_intake(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / resource_profile.PROFILE_FILENAME).write_text(
        json.dumps({".schema_version": 1, "providers": {
            "deepseek-direct": _wired("deepseek-direct",
                                      ["deepseek-v4-flash", "deepseek-v4-pro"]),
        }}, indent=2), encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    proc = _driver(run_dir, cfg, "resource_plan",
                   "workhorse: nope@deepseek-direct")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    err = json.loads(proc.stdout.strip().splitlines()[-1])["error"]
    assert "not in deepseek-direct's wired inventory" in err
    assert "deepseek-v4-flash" in err
    stored = json.loads((cfg / resource_profile.PROFILE_FILENAME)
                        .read_text(encoding="utf-8"))
    assert "model_plan" not in stored, "a refused answer must not half-land"


def test_the_bank_still_carries_exactly_twenty_three_turns():
    """Trevor ruling, binding: the model-choice fields EXTEND the existing
    resource_plan turn. They never add a 24th."""
    bank = json.loads((SCRIPTS.parent / "intake" / "deck-intake-questions.json")
                      .read_text(encoding="utf-8"))
    assert bank["session_budget"]["max_turns"] == 23
    turns = [q for q in bank["questions"] if q.get("kind") == "merged"]
    assert len(turns) == 23, [q["id"] for q in turns]
    rp = [q for q in bank["questions"] if q["id"] == "resource_plan"][0]
    assert set(rp["subfields"]) == {"resource_plan", "workhorse_model",
                                    "reasoning_model", "qc_model",
                                    "thinking_mode"}
    assert "model@provider" in rp["prompt"]
    assert "API key" in rp["prompt"] and "endpoint" in rp["prompt"]


# ---------------------------------------------------------------------------
# 7. THE LAUNCH GATE
# ---------------------------------------------------------------------------
def _stub_engine(tmp_path, monkeypatch):
    """Copied from tests/test_capacity_detection.py: a real child interpreter
    runs a one-line stub engine that proves it ran by touching a marker file,
    so 'nothing was spawned' is proven by an absent process, not by a mock."""
    monkeypatch.setattr(capacity, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(capacity, "HARNESS_SETTINGS_CANDIDATES",
                        (tmp_path / "absent-settings.json",))
    monkeypatch.setattr(capacity, "measure_working_concurrent",
                        lambda: (0, "stub", True))
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", "/usr/bin/true")
    monkeypatch.setenv("PRESENTATION_OCR_VERIFY", "0")
    monkeypatch.setattr(launcher, "resolve_scripts_dir", lambda: tmp_path)
    marker = tmp_path / "engine_ran.marker"
    (tmp_path / "presentation_job.py").write_text(
        "import pathlib, sys\n"
        f"pathlib.Path(r'''{marker}''').write_text('ran')\n"
        "sys.exit(0)\n", encoding="utf-8")
    return marker


UNSERVABLE_PROFILE = {
    ".schema_version": 1,
    # openrouter is owned and consented, but wires NOTHING the authoring class
    # can use -- and the client declared a workhorse it does not wire either.
    "providers": {"openrouter": _wired("openrouter", ["some-unrelated-id"])},
    "model_plan": {"workhorse": {"provider": "openrouter",
                                 "model": "a-model-nobody-wires"},
                   "floor_waivers": []},
}


def test_launch_refuses_when_a_covered_class_has_no_route(monkeypatch, tmp_path):
    marker = _stub_engine(tmp_path, monkeypatch)
    _profile_env(monkeypatch, tmp_path, UNSERVABLE_PROFILE)
    rc = launcher.dispatch(str(tmp_path / "run"), client="acme",
                           deck_type="standard", background=False)
    assert rc == launcher.DISPATCH_MODEL_PLAN_REFUSED, rc
    assert not marker.is_file(), "the engine must not have run"
    assert not (tmp_path / "run" / ".model-plan.json").is_file(), (
        "a refused launch must not leave a plan sidecar")


def test_launch_refusal_names_the_class_and_every_rejected_candidate(
        monkeypatch, tmp_path, capsys):
    _stub_engine(tmp_path, monkeypatch)
    _profile_env(monkeypatch, tmp_path, UNSERVABLE_PROFILE)
    launcher.dispatch(str(tmp_path / "run"), client="acme",
                      deck_type="standard", background=False)
    err = capsys.readouterr().err
    assert launcher.MODEL_PLAN_AUTOFAIL_CODE in err
    assert "authoring" in err
    assert "a-model-nobody-wires" in err
    assert "not in openrouter's wired inventory" in err


def test_launch_stamps_the_sidecar_and_the_banner_when_the_plan_is_servable(
        monkeypatch, tmp_path, capsys):
    marker = _stub_engine(tmp_path, monkeypatch)
    _profile_env(monkeypatch, tmp_path, _with_plan({
        "workhorse": {"provider": "openrouter", "model": "z-ai/glm-5.3-flash"},
        "thinking": "high", "floor_waivers": [],
    }))
    run_dir = tmp_path / "run"
    rc = launcher.dispatch(str(run_dir), client="acme", deck_type="standard",
                           background=False)
    assert rc != launcher.DISPATCH_MODEL_PLAN_REFUSED
    assert marker.is_file()
    sidecar = json.loads((run_dir / ".model-plan.json").read_text(encoding="utf-8"))
    rows = {r["capability"]: r for r in sidecar["plan"]["classes"]}
    assert rows["authoring"]["source"] == "client-plan"
    assert rows["authoring"]["model"] == "z-ai/glm-5.3-flash"
    assert rows["reasoning_long"]["floor"] == "failed", rows["reasoning_long"]
    assert rows["judge"]["source"] == "department-default"
    out = capsys.readouterr().out
    assert "client model plan stamped" in out
    assert "authoring=openrouter/z-ai/glm-5.3-flash" in out
    assert "thinking=high" in out


def test_the_gate_is_inert_for_a_client_who_declared_nothing(monkeypatch, tmp_path):
    """A client with no plan must reach dispatch byte-for-byte as before: no
    refusal, and no sidecar written."""
    marker = _stub_engine(tmp_path, monkeypatch)
    _profile_env(monkeypatch, tmp_path, copy.deepcopy(TWO_PROVIDER_PROFILE))
    run_dir = tmp_path / "run"
    rc = launcher.dispatch(str(run_dir), client="acme", deck_type="standard",
                           background=False)
    assert rc != launcher.DISPATCH_MODEL_PLAN_REFUSED
    assert marker.is_file()
    assert not (run_dir / ".model-plan.json").is_file()


# ---------------------------------------------------------------------------
# 8. The transport/eligibility key-name seam (T5)
# ---------------------------------------------------------------------------
def test_eligibility_and_transport_read_the_same_key_names():
    """A route that passes eligibility on OLLAMA_API_KEY used to die at
    transport on 'OLLAMA_CLOUD_API_KEY not set'. One table now, not two."""
    from presentation_job import dispatcher
    for provider, names in model_router._PROVIDER_KEY_NAMES.items():
        assert dispatcher._provider_key_names(provider) == tuple(names), provider
    assert "OLLAMA_API_KEY" in dispatcher._provider_key_names("ollama-cloud")


def test_transport_names_every_accepted_key_when_none_is_set(monkeypatch):
    from presentation_job import dispatcher
    for name in ("OLLAMA_CLOUD_API_KEY", "OLLAMA_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(dispatcher.DeepSeekCallError) as exc:
        dispatcher._openai_compat_complete("s", "u", provider="ollama-cloud",
                                           model="glm-5.3-flash")
    assert "OLLAMA_CLOUD_API_KEY" in str(exc.value)
    assert "OLLAMA_API_KEY" in str(exc.value)
