#!/usr/bin/env python3
"""tests/unit/u116-comms-audience-trigger-proof.test.py — U116 (E6-2; closes
G8): the communication TRIGGER + audience-confirmation prompt, proven against
the master-spec E6-2 BINARY acceptance criteria for this unit's ONB
(openclaw-onboarding) leg.

  (a) each outside-world comms type — page, blog, email, text/SMS, social
      post — produces an artifact carrying the blend directive + guardrail
      with the TOPIC slot populated (one individually-failable assertion per
      type, `test_<type>_produces_governed_topic_populated_artifact`) —
      PASS/FAIL each.
  (b) before writing, the system emits the audience-confirmation prompt and,
      with no override, proceeds under the STANDARD audience recording
      `audience_source=standard` (fixture) — PASS/FAIL.
  (c) a per-message override selects a SPECIFIC audience and the artifact is
      written under it, recording `audience_source=specific` + the chosen
      audience (fixture) — PASS/FAIL.
  (d) a comms artifact produced with the topic un-factored or with no
      audience decision recorded is refused/flagged (hands to U117), never
      silently written — PASS/FAIL.
  (e) OWED — the Command Center leg (board card renders the chosen audience
      alongside the persona-blend chips, `PersonaSlotChips`). Out of scope
      for this repo/leg, same per-repo/offline split already established for
      A-U5/U115; NOT exercised here.

Also locks:
  * the SMS/text-message ROUTING DECISION (`shared-utils/
    comms_audience_trigger.py`'s own module docstring): `comms_type="sms"`
    is live-exercised through the SAME generic trigger as every other type,
    and the two SMS-adjacent surfaces U111 read stay confirmed NOT-FOUND
    (persona/blend consumers) — a stale-finding regression guard, same
    pattern as U111's own `test_text_message_engine_is_recorded_not_found`.
  * the revert doctrine: `COMMS_AUDIENCE_PROMPT=0` degrades to a plain
    `persona_blend.build_bundle(...)` pass-through — today's per-task
    resolution, no forced content_task, no topic-refusal gate.
  * `persona_blend.build_bundle`'s new `force_content_task` kwarg is
    additive-only — the default (unset) path is byte-identical to pre-U116
    behavior.

Reuses the SAME hermetic patch harness pattern as
`23-ai-workforce-blueprint/scripts/test-a-u5-scoped-bundle.py` /
`test-u115-part-persona-governance.py` (persona_blend's cached selector/
decompose module instances monkeypatched) — never reads/writes a live
persona DB or the operator's own workspace, never touches live n8n/GHL.

Run:
    python3 tests/unit/u116-comms-audience-trigger-proof.test.py
    or: pytest tests/unit/u116-comms-audience-trigger-proof.test.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = _REPO_ROOT / "23-ai-workforce-blueprint" / "scripts"
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
_FIXTURE_13 = _SCRIPTS / "testdata" / "persona-categories.fixture.json"

for _p in (_SHARED_UTILS,):
    sp = str(_p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pb = _load(_SCRIPTS / "persona_blend.py", "persona_blend_u116")
cat = _load(_SHARED_UTILS / "comms_audience_trigger.py", "comms_audience_trigger_u116")
CAT13 = json.loads(_FIXTURE_13.read_text())

GUARDRAIL_MARK = "STYLE-INSPIRED, NEVER IMPERSONATION"

ICP_FOUNDERS = {"company": {"ideal_customer": "Black women entrepreneurs building wealth"}}


# --------------------------------------------------------------------------- #
# Hermetic patch harness (mirrors test-a-u5-scoped-bundle.py's _hermetic /
# test-u115-part-persona-governance.py's _hermetic) — module-level cached
# selector/decompose instances are monkeypatched so this file never reads or
# writes a live persona DB or the operator's own workspace.
# --------------------------------------------------------------------------- #
def _fake_dt_select_persona(subtask_text, dept, mode, weights, paths, db_path, variety=True):
    pid = "task-persona-" + str(abs(hash(subtask_text)) % 100000)
    return {"persona_id": pid, "persona_name": pid.replace("-", " ").title(),
            "score": 0.8, "layers": {"task_fit": 0.8}, "interaction_mode": mode}


def _fake_sel_semantic(task, dept, mode, weights, paths, db_path, variety=True, **kw):
    return {"persona_id": "aliche-get-good-with-money",
            "funnel": {"pool": 7, "category": 6, "semantic": 3}, "score": 0.72}


def _hermetic(catalog_path=_FIXTURE_13, company_cfg=None):
    company_cfg = company_cfg if company_cfg is not None else ICP_FOUNDERS
    os.environ["OPENCLAW_PERSONA_CATEGORIES"] = str(catalog_path)
    os.environ.pop("OPENCLAW_AUDIENCE", None)
    sel = pb._selector()
    dt = pb._decompose()
    sel.load_company_config = lambda paths: company_cfg
    sel.select_persona = _fake_sel_semantic
    sel.is_db_found = lambda p: False
    dt.select_persona = _fake_dt_select_persona
    dt.record_selection = lambda *a, **k: None
    dt.get_openclaw_paths = lambda: {}
    dt.find_dashboard_db = lambda: Path("/nonexistent/hermetic.db")
    dt.is_db_found = lambda p: False
    # comms_audience_trigger.py does its OWN `import persona_blend` (a box-
    # portable dynamic import, mirroring persona_canonical.py's pattern) —
    # that resolves to a SEPARATE module instance/cache from this file's
    # `pb` (loaded under a distinct module name via importlib). Pin it to
    # the SAME hermetic, monkeypatched `pb` so cat.build_comms_trigger sees
    # this harness's patches too, never the real selector/decompose modules.
    cat._load_persona_blend = lambda: pb
    paths = {"persona_categories": Path(catalog_path),
             "soul_md": Path("/nonexistent/SOUL.md")}
    return paths, Path("/nonexistent/hermetic.db")


def _governed_topic_populated(result: dict) -> bool:
    """The shared 'is this a governed, topic-populated comms artifact'
    predicate every per-type check below applies: not refused, non-empty
    blend_directive ending in the mandatory guardrail, and a non-empty topic
    on both the trigger result AND the bundle it produced."""
    if not isinstance(result, dict) or result.get("refused"):
        return False
    bundle = result.get("bundle") or {}
    directive = bundle.get("blend_directive") or ""
    if not directive or GUARDRAIL_MARK not in directive:
        return False
    if not (result.get("topic") or "").strip():
        return False
    if bundle.get("topic") != result.get("topic"):
        return False
    return bool(bundle.get("content_task"))


# --------------------------------------------------------------------------- #
# (a) each of the five comms types — one individually-failable assertion.
# --------------------------------------------------------------------------- #
def test_page_produces_governed_topic_populated_artifact():
    paths, db = _hermetic()
    r = cat.build_comms_trigger(
        "page", "the opt-in offer for the free budgeting workbook", None,
        paths=paths, db_path=db, use_llm=False, record=False)
    assert _governed_topic_populated(r), "page comms not governed/topic-populated: %r" % r
    assert r["comms_type"] == "page"


def test_blog_produces_governed_topic_populated_artifact():
    paths, db = _hermetic()
    r = cat.build_comms_trigger(
        "blog", "5 lessons from a failed product launch", None,
        paths=paths, db_path=db, use_llm=False, record=False)
    assert _governed_topic_populated(r), "blog comms not governed/topic-populated: %r" % r


def test_email_produces_governed_topic_populated_artifact():
    paths, db = _hermetic()
    r = cat.build_comms_trigger(
        "email", "a 3-email nurture sequence about budgeting wins", None,
        paths=paths, db_path=db, use_llm=False, record=False)
    assert _governed_topic_populated(r), "email comms not governed/topic-populated: %r" % r


def test_sms_produces_governed_topic_populated_artifact():
    paths, db = _hermetic()
    r = cat.build_comms_trigger(
        "sms", "a reminder text about the debt-payoff webinar tonight", None,
        paths=paths, db_path=db, use_llm=False, record=False)
    assert _governed_topic_populated(r), "sms comms not governed/topic-populated: %r" % r


def test_social_produces_governed_topic_populated_artifact():
    paths, db = _hermetic()
    r = cat.build_comms_trigger(
        "social", "a carousel post about small automated saving steps", None,
        paths=paths, db_path=db, use_llm=False, record=False)
    assert _governed_topic_populated(r), "social comms not governed/topic-populated: %r" % r


# --------------------------------------------------------------------------- #
# (b) no override -> STANDARD audience, recorded, never a silent skip.
# --------------------------------------------------------------------------- #
def test_no_override_defaults_to_standard_audience_recorded():
    paths, db = _hermetic()
    r = cat.build_comms_trigger(
        "email", "budgeting tips for the fall launch", None,
        paths=paths, db_path=db, use_llm=False, record=False)
    assert not r["refused"], "unexpected refusal: %r" % r
    ac = r["audience_confirmation"]
    assert ac["prompt"] == cat.STANDARD_OR_SPECIFIC_PROMPT
    assert ac["audience_source"] == "standard"
    bundle = r["bundle"]
    assert bundle["audience_source"] == "standard"
    assert bundle["audience_confirmation_prompt"] == cat.STANDARD_OR_SPECIFIC_PROMPT
    # the standard audience resolves from the ICP fixture, never fabricated.
    assert ac["chosen_audience"], "standard audience must resolve from the ICP, not be empty"


# --------------------------------------------------------------------------- #
# (c) a per-message override selects a SPECIFIC audience.
# --------------------------------------------------------------------------- #
def test_override_selects_specific_audience_recorded():
    paths, db = _hermetic()
    r = cat.build_comms_trigger(
        "email", "budgeting tips for the fall launch", None,
        paths=paths, db_path=db, use_llm=False, record=False,
        audience_override="debt strugglers")
    assert not r["refused"], "unexpected refusal: %r" % r
    ac = r["audience_confirmation"]
    assert ac["audience_source"] == "specific"
    assert ac["chosen_audience"] == "debt strugglers"
    bundle = r["bundle"]
    assert bundle["audience_source"] == "specific"
    # the SPECIFIC override actually reaches the resolved bundle's audience —
    # never silently dropped in favor of the standard ICP audience.
    assert bundle["resolved_audience"]["label"] == "debt strugglers"
    assert bundle["resolved_audience"]["source"] == "operator_confirmed"


def test_standard_and_specific_are_independently_recorded_not_a_shared_default():
    paths, db = _hermetic()
    r_std = cat.build_comms_trigger(
        "social", "a carousel about saving automatically", None,
        paths=paths, db_path=db, use_llm=False, record=False)
    r_spec = cat.build_comms_trigger(
        "social", "a carousel about saving automatically", None,
        paths=paths, db_path=db, use_llm=False, record=False,
        audience_override="founders")
    assert r_std["audience_confirmation"]["audience_source"] == "standard"
    assert r_spec["audience_confirmation"]["audience_source"] == "specific"
    assert r_std["audience_confirmation"]["chosen_audience"] != r_spec["audience_confirmation"]["chosen_audience"]


# --------------------------------------------------------------------------- #
# (d) fail-closed: un-factored topic / unrecorded audience -> refused, never
# a silent write.
# --------------------------------------------------------------------------- #
def test_unfactored_topic_is_refused_not_silently_written():
    paths, db = _hermetic()
    # A bare comms-type-only brief with NO real topic signal beyond the
    # comms label word itself — never a fabricated topic.
    r = cat.build_comms_trigger(
        "email", "write an email", None,
        paths=paths, db_path=db, use_llm=False, record=False)
    assert r["refused"] is True
    assert r["refusal_reason"] == "topic_not_factored"
    assert r["bundle"] is None, "a refused comms artifact must never carry a written bundle"


def test_unrecorded_audience_is_refused_fail_closed():
    """Fail-closed backstop: even if resolve_comms_audience somehow returned
    neither 'standard' nor 'specific' (should never happen in the real
    module), build_comms_trigger must refuse rather than write. Proven by
    monkeypatching resolve_comms_audience for this one call only."""
    paths, db = _hermetic()
    real = cat.resolve_comms_audience
    try:
        cat.resolve_comms_audience = lambda *a, **k: {
            "audience_source": None, "prompt": cat.STANDARD_OR_SPECIFIC_PROMPT,
            "chosen_audience": None, "resolve_audience": {}}
        r = cat.build_comms_trigger(
            "blog", "a post about real launch-sequence topic signal", None,
            paths=paths, db_path=db, use_llm=False, record=False)
        assert r["refused"] is True
        assert r["refusal_reason"] == "audience_not_recorded"
        assert r["bundle"] is None
    finally:
        cat.resolve_comms_audience = real


# --------------------------------------------------------------------------- #
# SMS routing decision — live-exercised through the SAME generic trigger,
# never a second bespoke engine; the NOT-FOUND finding stays current.
# --------------------------------------------------------------------------- #
def test_sms_routes_through_the_same_generic_trigger_as_every_other_type():
    paths, db = _hermetic()
    r_email = cat.build_comms_trigger(
        "email", "a nurture email about credit repair basics", None,
        paths=paths, db_path=db, use_llm=False, record=False)
    r_sms = cat.build_comms_trigger(
        "sms", "a nurture text about credit repair basics", None,
        paths=paths, db_path=db, use_llm=False, record=False)
    assert not r_email["refused"] and not r_sms["refused"]
    # both governed by the IDENTICAL mechanism — same guardrail, same
    # audience-confirmation contract, same refusal rules — no special-cased
    # "SMS is different" branch anywhere in the trigger.
    assert GUARDRAIL_MARK in r_email["bundle"]["blend_directive"]
    assert GUARDRAIL_MARK in r_sms["bundle"]["blend_directive"]
    assert r_sms["audience_confirmation"]["prompt"] == cat.STANDARD_OR_SPECIFIC_PROMPT


def test_sms_adjacent_surfaces_stay_confirmed_not_found_not_stale():
    """Regression guard mirroring U111's own `test_text_message_engine_
    is_recorded_not_found_and_routed_to_u116` — fails loud if either named
    SMS-adjacent surface starts referencing persona_for_job/blend_directive
    without this module (the routing DECISION's owner) being updated to
    match, so the ROUTE-not-BUILD decision never silently goes stale."""
    sms_workflow_spec = (_REPO_ROOT / "38-conversational-ai-system" / "templates"
                         / "sms-workflow-ai-prompt-template.md")
    wf5_builder = (_REPO_ROOT / "44-convert-and-flow-operator" / "tools" / "engine"
                   / "builders" / "wf5-ht-interest-builder.py")
    for surface in (sms_workflow_spec, wf5_builder):
        assert surface.is_file(), "expected SMS-adjacent surface missing at %s" % surface
        text = surface.read_text(encoding="utf-8")
        assert "persona_for_job" not in text and "blend_directive" not in text, (
            "%s now references persona_for_job/blend_directive — the ROUTE "
            "(not build-a-second-engine) decision this module documents is "
            "STALE; update comms_audience_trigger.py's module docstring AND "
            "this test to match the new in-tree SMS writer" % surface)


# --------------------------------------------------------------------------- #
# revert doctrine — COMMS_AUDIENCE_PROMPT=0 falls back to today's per-task
# audience resolution (no forced content_task, no topic-refusal gate).
# --------------------------------------------------------------------------- #
def test_flag_off_degrades_to_plain_build_bundle_passthrough():
    paths, db = _hermetic()
    os.environ[cat.COMMS_AUDIENCE_PROMPT_FLAG] = "0"
    try:
        assert cat.flag_enabled() is False
        # the SAME bare, topic-less brief that (d) refuses under the flag
        # must NOT be refused when reverted — "falls back to today's
        # per-task audience resolution", never a new failure mode.
        r = cat.build_comms_trigger(
            "email", "write an email", None,
            paths=paths, db_path=db, use_llm=False, record=False)
        assert r["refused"] is False
        assert r["flag_enabled"] is False
        assert r["audience_confirmation"] is None
        assert "audience_source" not in r["bundle"]
        assert "audience_confirmation_prompt" not in r["bundle"]
    finally:
        os.environ.pop(cat.COMMS_AUDIENCE_PROMPT_FLAG, None)
    assert cat.flag_enabled() is True, "flag must default back ON once unset"


# --------------------------------------------------------------------------- #
# regression: persona_blend.build_bundle's new force_content_task kwarg is
# additive-only — default (unset) path byte-identical to pre-U116.
# --------------------------------------------------------------------------- #
def test_force_content_task_default_off_is_unchanged_behavior():
    paths, db = _hermetic()
    mechanical = "restart the nightly backup cron job"
    b_default = pb.build_bundle(mechanical, "engineering", paths=paths, db_path=db,
                                use_llm=False, record=False)
    b_explicit_false = pb.build_bundle(mechanical, "engineering", paths=paths, db_path=db,
                                       use_llm=False, record=False, force_content_task=False)
    assert b_default.get("content_task") is False
    assert b_explicit_false.get("content_task") is False
    assert b_default.get("no_persona_required") is True


def test_force_content_task_true_overrides_the_keyword_heuristic():
    paths, db = _hermetic()
    non_keyword_brief = "explain the new pricing tiers to prospective customers"
    assert pb.is_content_task(non_keyword_brief) is False, (
        "fixture assumption broke: this brief now trips is_content_task() on "
        "its own, so it no longer proves force_content_task is doing anything")
    b_forced = pb.build_bundle(non_keyword_brief, "web-development", paths=paths, db_path=db,
                               use_llm=False, record=False, force_content_task=True,
                               topic_hint="pricing tiers")
    assert b_forced.get("content_task") is True
    assert "comms_governance" in b_forced["rationale"]


def test_unknown_comms_type_raises_value_error():
    try:
        cat.build_comms_trigger("carrier-pigeon", "write something", "marketing")
        raise AssertionError("expected ValueError for an unknown comms_type")
    except ValueError:
        pass


_ALL_TESTS = [
    test_page_produces_governed_topic_populated_artifact,
    test_blog_produces_governed_topic_populated_artifact,
    test_email_produces_governed_topic_populated_artifact,
    test_sms_produces_governed_topic_populated_artifact,
    test_social_produces_governed_topic_populated_artifact,
    test_no_override_defaults_to_standard_audience_recorded,
    test_override_selects_specific_audience_recorded,
    test_standard_and_specific_are_independently_recorded_not_a_shared_default,
    test_unfactored_topic_is_refused_not_silently_written,
    test_unrecorded_audience_is_refused_fail_closed,
    test_sms_routes_through_the_same_generic_trigger_as_every_other_type,
    test_sms_adjacent_surfaces_stay_confirmed_not_found_not_stale,
    test_flag_off_degrades_to_plain_build_bundle_passthrough,
    test_force_content_task_default_off_is_unchanged_behavior,
    test_force_content_task_true_overrides_the_keyword_heuristic,
    test_unknown_comms_type_raises_value_error,
]


def main() -> int:
    ok = True
    for fn in _ALL_TESTS:
        try:
            fn()
            print("  [PASS] %s" % fn.__name__)
        except AssertionError as e:
            ok = False
            print("  [FAIL] %s: %s" % (fn.__name__, e))
        except Exception as e:  # pragma: no cover - defensive
            ok = False
            print("  [ERROR] %s: %r" % (fn.__name__, e))
    print("  [OWED] (e) board-card audience chip render — Command Center leg, "
          "not exercised here (same per-repo/offline split as A-U5/U115).")
    print("== U116 comms-audience-trigger proof: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
