"""Offline tests for the Skill 44 → Skill 06 form/survey dependency handoff
contract (Skill 06 v3.0 §3.2, checklist C7, scenarios B06-B08).

WHAT IS LOCKED IN HERE
----------------------
  B06  pre-existing fields/tags are REUSED; a lookup MISS stops BEFORE mutation
       and never licenses a duplicate custom field.
  B07  an uncertain save is RECONCILED (read-back) before any retry, and a
       restart/resume REUSES the recorded native object id instead of building
       a second object.
  B08  survey branching/convergence fails CLOSED (unsubmittable topology is a
       hard stop at preflight, before any browser action).
  §3.2 matching location/account identity on BOTH sides; four distinct
       operations with separate receipts; no invented native tag setting;
       ``zhc_`` keys / ``ZHC `` containers preserved; the ``ghl_survey_rest``
       capture gate is untouched.

HERMETIC: no network, no browser, no GHL, no live writes. Every browser/CLI seam
is either a pure function or monkeypatched. Synthetic fixtures only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for _p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ghl_form_survey_handoff as ho   # noqa: E402
import ghl_form_builder as fb          # noqa: E402
import ghl_survey_builder as sb        # noqa: E402
import ghl_survey_rest as srest        # noqa: E402

LOC = "LOC_TEST_0001"
ACC = "ACC_TEST_0001"

REF = {"location_id": LOC, "account_id": ACC, "approved": True, "source": "test"}

FORM_PLAN = {
    "custom_fields": [
        {"field_key": "zhc_podcast_rating", "action": "create"},
        {"field_key": "zhc_facebook_url", "action": "reuse"},
    ],
    "tags": [{"tag": "zhc_podcast_lead", "action": "create"}],
    "tag_attachment": {"method": "workflow"},
}

FORM_RESULTS = {
    "location_id": LOC,
    "account_id": ACC,
    "custom_fields": [
        {"field_key": "zhc_podcast_rating", "id": "CF_RATING", "action": "create"},
        {"field_key": "zhc_facebook_url", "id": "CF_FB", "action": "reuse"},
    ],
    "tags": [{"tag": "zhc_podcast_lead", "id": "TG_LEAD", "action": "create"}],
}


def _ready_handoff(**overrides):
    rec = ho.make_handoff("form", REF, FORM_PLAN, object_name="ZHC Podcast Signup")
    results = dict(FORM_RESULTS)
    results.update(overrides.pop("results", {}))
    ho.record_dependency_results(rec, **results)
    ho.verify_dependencies(rec, readback_field_keys=["zhc_podcast_rating", "zhc_facebook_url"],
                           readback_tag_names=["zhc_podcast_lead"])
    for k, v in overrides.items():
        rec[k] = v
    return rec


# ───────────────────────── §3.2 conventions preserved ─────────────────────────

def test_zhc_machine_key_and_zhc_container_conventions_unchanged():
    """zhc_ keys/tags stay lowercase-no-space; the container NAME keeps 'ZHC '."""
    assert fb.zhc_field_key("Podcast Rating") == "zhc_podcast_rating"
    assert fb.zhc_field_key("zhc_podcast_rating") == "zhc_podcast_rating"  # never double
    assert fb.zhc_tag("Podcast Lead") == "zhc_podcast_lead"
    assert fb.ensure_zhc_name("Podcast Signup Form") == "ZHC Podcast Signup Form"
    assert fb.ensure_zhc_name("ZHC Podcast Signup Form") == "ZHC Podcast Signup Form"
    assert sb._resolve_field_key({"label": "Podcast Rating"}) == ("zhc_podcast_rating", "zhc")
    # engine-owned verbatim keys are byte-for-byte, never zhc-prefixed
    assert sb._resolve_field_key(
        {"key": "podcast_survey__additional_info", "key_policy": "verbatim"}
    ) == ("podcast_survey__additional_info", "verbatim")


# ───────────────────────────── B06: reuse, no dupes ───────────────────────────

def test_b06_preexisting_fields_and_tags_are_reused():
    rec = _ready_handoff()
    ho.assert_ready_for_native_build(rec, build_location_id=LOC,
                                     tag_attachment_method="workflow")
    actions = {f["field_key"]: f["action"] for f in rec["dependency_results"]["custom_fields"]}
    assert actions["zhc_facebook_url"] == "reuse"
    assert actions["zhc_podcast_rating"] == "create"


def test_b06_missing_dependency_stops_before_mutation():
    """A field with NO result at all stops the build before a browser step."""
    rec = ho.make_handoff("form", REF, FORM_PLAN)
    ho.record_dependency_results(
        rec, location_id=LOC,
        custom_fields=[{"field_key": "zhc_podcast_rating", "id": "CF_RATING",
                        "action": "create"}],
        tags=[])
    v = ho.verify_dependencies(rec)
    assert v["ok"] is False
    with pytest.raises(ho.HandoffIncomplete):
        ho.assert_ready_for_native_build(rec)


@pytest.mark.parametrize("action", ["not_found", "create_failed", "unknown", ""])
def test_b06_lookup_miss_never_licenses_a_duplicate(action):
    """The whole point of B06: a browser/lookup miss is a STOP, never a re-create."""
    rec = ho.make_handoff("form", REF, FORM_PLAN)
    ho.record_dependency_results(
        rec, location_id=LOC,
        custom_fields=[
            {"field_key": "zhc_podcast_rating", "id": None, "action": action},
            {"field_key": "zhc_facebook_url", "id": "CF_FB", "action": "reuse"},
        ],
        tags=[{"tag": "zhc_podcast_lead", "id": "TG_LEAD", "action": "create"}])
    assert ho.verify_dependencies(rec)["ok"] is False
    with pytest.raises(ho.HandoffIncomplete):
        ho.assert_ready_for_native_build(rec)


def test_b06_duplicate_names_are_resolved_by_id_not_label():
    """Two same-LABEL fields with different ids: identity is the key, never the label."""
    rec = ho.make_handoff("form", REF, FORM_PLAN)
    ho.record_dependency_results(
        rec, location_id=LOC,
        custom_fields=[
            # right key, wrong id source
            {"field_key": "zhc_podcast_rating", "id": "CF_RATING", "action": "reuse"},
            {"field_key": "zhc_facebook_url", "id": "CF_FB", "action": "reuse"},
            # a DECOY with the same label but a different key — must be ignored
            {"field_key": "zhc_facebook_url_old", "id": "CF_FB_OLD", "action": "reuse"},
        ],
        tags=[{"tag": "zhc_podcast_lead", "id": "TG_LEAD", "action": "create"}])
    ho.verify_dependencies(rec, readback_field_keys=["zhc_podcast_rating", "zhc_facebook_url"],
                           readback_tag_names=["zhc_podcast_lead"])
    ho.assert_ready_for_native_build(rec)
    ids = {f["field_key"]: f["id"] for f in rec["dependency_results"]["custom_fields"]}
    assert ids["zhc_facebook_url"] == "CF_FB"


def test_b06_create_claimed_but_absent_from_readback_fails():
    rec = ho.make_handoff("form", REF, FORM_PLAN)
    ho.record_dependency_results(rec, **FORM_RESULTS)
    v = ho.verify_dependencies(rec, readback_field_keys=["zhc_facebook_url"],
                               readback_tag_names=["zhc_podcast_lead"])
    assert v["ok"] is False
    assert any("zhc_podcast_rating" in p for p in v["problems"])


# ─────────────────── wrong location / account identity both sides ─────────────

def test_wrong_location_refuses_and_records_nothing():
    rec = ho.make_handoff("form", REF, FORM_PLAN)
    with pytest.raises(ho.LocationMismatch):
        ho.record_dependency_results(rec, location_id="LOC_OTHER", custom_fields=[],
                                     tags=[])
    assert rec["dependency_results"]["location_id"] is None


def test_wrong_account_refuses():
    rec = ho.make_handoff("form", REF, FORM_PLAN)
    with pytest.raises(ho.LocationMismatch):
        ho.record_dependency_results(rec, location_id=LOC, account_id="ACC_OTHER",
                                     custom_fields=[], tags=[])


def test_build_side_location_must_match_approved():
    rec = _ready_handoff()
    with pytest.raises(ho.LocationMismatch):
        ho.assert_ready_for_native_build(rec, build_location_id="LOC_ELSEWHERE")


def test_unapproved_location_refuses_even_when_proven():
    rec = ho.make_handoff("form", {**REF, "approved": False}, FORM_PLAN)
    ho.record_dependency_results(rec, **FORM_RESULTS)
    ho.verify_dependencies(rec)
    with pytest.raises(ho.HandoffIncomplete):
        ho.assert_ready_for_native_build(rec)


def test_missing_location_id_refused_at_construction():
    with pytest.raises(ValueError):
        ho.make_handoff("form", {"account_id": ACC}, FORM_PLAN)


# ──────────────── four distinct operations, four separate receipts ───────────

def test_four_operations_have_separate_receipts():
    rec = _ready_handoff()
    ho.operation_receipt(rec, "native_create", state="done", native_id="FORM123",
                         evidence={"id_source": "iframe_src", "name": "ZHC Podcast Signup"})
    ho.operation_receipt(rec, "field_create", state="done", native_id="FORM123")
    ho.operation_receipt(rec, "embed", state="done", evidence={"snippet_len": 140})
    ho.operation_receipt(rec, "workflow_wiring", state="pending")
    status = ho.operations_complete(rec)
    assert status["complete"] is False
    assert status["missing"] == ["workflow_wiring"]
    ho.operation_receipt(rec, "workflow_wiring", state="done", native_id="WF9")
    assert ho.operations_complete(rec)["complete"] is True
    # each operation keeps its OWN id — embedding does not overwrite creation
    assert rec["operations"]["native_create"]["native_id"] == "FORM123"
    assert rec["operations"]["workflow_wiring"]["native_id"] == "WF9"


def test_operation_cannot_silently_retarget_the_native_object():
    rec = _ready_handoff()
    ho.operation_receipt(rec, "native_create", state="done", native_id="FORM123")
    with pytest.raises(ho.OperationContradiction):
        ho.operation_receipt(rec, "native_create", state="done", native_id="FORM999")


def test_unknown_operation_refused():
    rec = _ready_handoff()
    with pytest.raises(ValueError):
        ho.operation_receipt(rec, "make_coffee", state="done")


# ─────────────── no invented native tag setting (§3.2) ───────────────────────

@pytest.mark.parametrize("method", ["native_setting", "form_setting", "auto", "inline"])
def test_invented_tag_attachment_methods_refused(method):
    rec = _ready_handoff()
    with pytest.raises(ho.TagAttachmentUnsupported):
        ho.validate_tag_attachment(rec, method=method)


def test_documented_tag_attachment_methods_accepted():
    rec = _ready_handoff()
    block = ho.validate_tag_attachment(rec, method="workflow")
    assert block["owner_skill"] == "44-convert-and-flow-operator"
    assert block["tags"] == ["zhc_podcast_lead"]
    assert ho.validate_tag_attachment(rec, method="hidden_field")["method"] == "hidden_field"
    # the gate rejects an invented method through the same path
    with pytest.raises(ho.TagAttachmentUnsupported):
        ho.assert_ready_for_native_build(rec, tag_attachment_method="native_setting")


# ─────────────────── B07: reconcile before retry, resume by id ───────────────

def test_b07_uncertain_save_reconciles_before_retry():
    rec = _ready_handoff()
    ho.operation_receipt(rec, "native_create", state="done", native_id="FORM123",
                         evidence={"name": "ZHC Podcast Signup"})
    # (a) the object IS there → adopt it, never save again
    assert ho.reconcile_uncertain_save(
        rec, readback={"objects": [{"id": "FORM123", "name": "ZHC Podcast Signup"}]}
    )["verdict"] == ho.VERDICT_REUSE
    # (b) proven absent → a retry is safe
    assert ho.reconcile_uncertain_save(
        rec, readback={"objects": []})["verdict"] == ho.VERDICT_CREATE
    # (c) the read itself failed → UNKNOWN, never a blind retry
    assert ho.reconcile_uncertain_save(
        rec, readback={"error": "timeout"})["verdict"] == ho.VERDICT_BLOCKED
    assert ho.reconcile_uncertain_save(rec, readback=None)["verdict"] == ho.VERDICT_BLOCKED
    # (d) same NAME, different id → this is exactly how duplicates are born
    verdict = ho.reconcile_uncertain_save(
        rec, readback={"objects": [{"id": "FORM_OTHER", "name": "ZHC Podcast Signup"}]})
    assert verdict["verdict"] == ho.VERDICT_BLOCKED
    assert verdict["native_id"] == "FORM_OTHER"


def test_b07_restart_resume_reuses_native_object_id():
    rec = _ready_handoff()
    assert ho.resume_target(rec) is None          # nothing built yet
    ho.operation_receipt(rec, "native_create", state="done", native_id="FORM123")
    assert ho.resume_target(rec) == "FORM123"
    # the id survives a serialize/deserialize (a restart reads it off disk)
    round_tripped = json.loads(json.dumps(rec))
    assert ho.resume_target(round_tripped) == "FORM123"


def test_handoff_persists_and_reloads(tmp_path):
    rec = _ready_handoff()
    ho.operation_receipt(rec, "native_create", state="done", native_id="FORM123")
    path = ho.write_handoff(str(tmp_path), rec)
    assert path == ho.handoff_path(str(tmp_path))
    assert os.path.basename(path) == "form-survey-handoff.json"
    loaded = ho.load_handoff(str(tmp_path))
    assert loaded is not None and loaded["schema"] == ho.HANDOFF_SCHEMA
    assert ho.resume_target(loaded) == "FORM123"
    assert ho.load_handoff(os.path.join(str(tmp_path), "absent.json")) is None


def test_unparseable_handoff_is_none_not_a_pass(tmp_path):
    routing = tmp_path / "routing"
    routing.mkdir()
    (routing / "form-survey-handoff.json").write_text("{not json", encoding="utf-8")
    assert ho.load_handoff(str(tmp_path)) is None


# ─────────── builder integration: the gate runs in preflight (B06) ───────────

def test_form_preflight_hard_stops_on_incomplete_handoff(tmp_path):
    """F-P11: an unproven dependency stops the FORM before any browser step."""
    incomplete = ho.make_handoff("form", REF, FORM_PLAN)
    ho.record_dependency_results(
        incomplete, location_id=LOC,
        custom_fields=[{"field_key": "zhc_podcast_rating", "id": None,
                        "action": "not_found"}],
        tags=[])
    ho.verify_dependencies(incomplete)
    task = {"location_id": LOC, "form_name": "Podcast Signup",
            "form_fields": fb._reference_fields()}
    out = fb.build_form(task, str(tmp_path), dry_run=True, handoff=incomplete)
    assert out["preflight"]["pass"] is False
    check = next(c for c in out["preflight"]["checks"]
                 if c["check"] == "F-P11:dependency_handoff")
    assert check["pass"] is False
    assert out["form_url"] == "" and out["embed_code"] == ""


def test_form_preflight_passes_with_a_proven_handoff(tmp_path):
    task = {"location_id": LOC, "form_name": "Podcast Signup",
            "form_fields": fb._reference_fields()}
    out = fb.build_form(task, str(tmp_path), dry_run=True, handoff=_ready_handoff())
    check = next(c for c in out["preflight"]["checks"]
                 if c["check"] == "F-P11:dependency_handoff")
    assert check["pass"] is True
    assert out["preflight"]["pass"] is True


def test_form_preflight_wrong_location_handoff_stops(tmp_path):
    task = {"location_id": "LOC_ELSEWHERE", "form_name": "Podcast Signup",
            "form_fields": fb._reference_fields()}
    out = fb.build_form(task, str(tmp_path), dry_run=True, handoff=_ready_handoff())
    assert out["preflight"]["pass"] is False
    check = next(c for c in out["preflight"]["checks"]
                 if c["check"] == "F-P11:dependency_handoff")
    assert "LocationMismatch" in check["detail"]


def test_form_preflight_without_handoff_is_deferred_not_claimed(tmp_path):
    task = {"location_id": LOC, "form_name": "Podcast Signup",
            "form_fields": fb._reference_fields()}
    out = fb.build_form(task, str(tmp_path), dry_run=True)
    check = next(c for c in out["preflight"]["checks"]
                 if c["check"] == "F-P11:dependency_handoff")
    assert check["pass"] is True
    assert "DEFERRED" in check["detail"]


def test_form_build_picks_up_a_handoff_record_from_disk(tmp_path):
    """A handoff on disk means the caller opted into the gate — no silent bypass."""
    incomplete = ho.make_handoff("form", REF, FORM_PLAN)
    ho.write_handoff(str(tmp_path), incomplete)
    task = {"location_id": LOC, "form_name": "Podcast Signup",
            "form_fields": fb._reference_fields()}
    out = fb.build_form(task, str(tmp_path), dry_run=True)
    assert out["preflight"]["pass"] is False


def test_survey_preflight_hard_stops_on_incomplete_handoff(tmp_path):
    incomplete = ho.make_handoff("survey", REF, FORM_PLAN)
    task = {"location_id": LOC, "title": "Test Survey",
            "_handoff_record": incomplete}
    out = sb._run_preflight(task, str(tmp_path))
    assert out["pass"] is False
    check = next(c for c in out["checks"] if c["check"] == "P6b:dependency_handoff")
    assert check["pass"] is False


def test_survey_preflight_without_handoff_is_deferred(tmp_path):
    task = {"location_id": LOC, "title": "Test Survey"}
    out = sb._run_preflight(task, str(tmp_path))
    check = next(c for c in out["checks"] if c["check"] == "P6b:dependency_handoff")
    assert check["pass"] is True and "DEFERRED" in check["detail"]


def test_survey_with_no_planned_dependencies_is_ready():
    rec = ho.make_handoff("survey", REF, {"custom_fields": [], "tags": []})
    assert ho.verify_dependencies(rec)["ok"] is True
    ho.assert_ready_for_native_build(rec, build_location_id=LOC)


# ──────────────── B08: survey branching fails closed ─────────────────────────

def _branchy_survey():
    """A 3-question survey with a router on slide 1 and two branch slides."""
    return {
        "location_id": LOC,
        "title": "Branch Survey",
        "survey_fields": [
            {"type": "radio", "label": "Attended before?", "options": ["Yes", "No"],
             "required": True},
            {"type": "single_line", "label": "Alumni note", "required": True},
            {"type": "single_line", "label": "First-timer note", "required": True},
        ],
        "slides": [
            {"name": "Router", "fields": ["Attended before?"]},
            {"name": "Alumni", "fields": ["Alumni note"]},
            {"name": "First Timer", "fields": ["First-timer note"]},
            {"name": "Wrap", "fields": []},
        ],
        "conditional_logic": [
            {"if_field": "Attended before?", "if_value": "Yes",
             "then_slide": "Alumni"},
            {"if_field": "Attended before?", "if_value": "No",
             "then_slide": "First Timer"},
        ],
    }


def test_b08_convergent_branches_are_valid():
    task = {**_branchy_survey(), "converge_slide": "Wrap"}
    fields = sb._resolve_fields(task)
    slides = sb._plan_slides(task, fields)
    rules = sb._resolve_conditional_rules(task)
    assert sb._validate_topology(task, fields, slides, rules) == []


def test_b08_non_converging_branches_fail_closed():
    """No converge_slide → each branch falls through into its sibling. HARD STOP."""
    task = _branchy_survey()
    fields = sb._resolve_fields(task)
    slides = sb._plan_slides(task, fields)
    rules = sb._resolve_conditional_rules(task)
    errors = sb._validate_topology(task, fields, slides, rules)
    assert errors
    assert any("convergence" in e or "falls through" in e for e in errors)


def test_b08_dangling_branch_target_fails_closed():
    task = {**_branchy_survey(), "converge_slide": "Wrap"}
    task["conditional_logic"] = [
        {"if_field": "Attended before?", "if_value": "Yes", "then_slide": "Nowhere"},
    ]
    fields = sb._resolve_fields(task)
    slides = sb._plan_slides(task, fields)
    rules = sb._resolve_conditional_rules(task)
    errors = sb._validate_topology(task, fields, slides, rules)
    assert any("dangling then_slide" in e for e in errors)


def test_b08_dangling_converge_ref_fails_closed():
    task = {**_branchy_survey(), "converge_slide": "No Such Slide"}
    fields = sb._resolve_fields(task)
    slides = sb._plan_slides(task, fields)
    rules = sb._resolve_conditional_rules(task)
    errors = sb._validate_topology(task, fields, slides, rules)
    assert any("does not resolve" in e for e in errors)


def test_b08_orphan_field_fails_closed():
    task = {**_branchy_survey(), "converge_slide": "Wrap"}
    task["survey_fields"].append({"type": "single_line", "label": "Unplaced field"})
    fields = sb._resolve_fields(task)
    slides = sb._plan_slides(task, fields)
    rules = sb._resolve_conditional_rules(task)
    errors = sb._validate_topology(task, fields, slides, rules)
    assert any("orphan" in e for e in errors)


def test_b08_survey_preflight_stops_before_any_browser_action(tmp_path):
    """The topology gate is a PREFLIGHT check — it runs before any mutation."""
    task = _branchy_survey()   # deliberately non-converging
    out = sb._run_preflight(task, str(tmp_path))
    assert out["pass"] is False
    check = next(c for c in out["checks"] if c["check"] == "P4:topology_valid")
    assert check["pass"] is False
    assert "convergence" in check["detail"] or "falls through" in check["detail"]


# ─────────── required / hidden / consent flags + embed behaviour ─────────────

def test_required_and_hidden_are_mutually_exclusive():
    task = {"form_fields": [
        {"source": "standard", "element": "Email", "label": "Email",
         "required": True, "hidden": True},
    ]}
    fields = fb._resolve_fields(task)
    assert fields[0]["required"] is True
    assert fields[0]["hidden"] is False
    assert "required+hidden" in fields[0].get("_warning", "")


def test_hidden_flag_survives_when_not_required():
    task = {"form_fields": [
        {"source": "standard", "element": "Email", "label": "Email", "hidden": True},
    ]}
    fields = fb._resolve_fields(task)
    assert fields[0]["hidden"] is True and fields[0]["required"] is False


def test_custom_field_carries_zhc_key_and_merge_token():
    task = {"form_fields": [
        {"source": "custom", "element": "Single Line", "label": "Personal Facebook URL",
         "field_key": "facebook_url"},
    ]}
    fields = fb._resolve_fields(task)
    assert fields[0]["field_key"] == "zhc_facebook_url"
    assert fields[0]["merge_token"] == "{{contact.zhc_facebook_url}}"
    assert fields[0]["add_via"] == "add_object_fields"


def test_embed_is_a_distinct_operation_with_its_own_receipt():
    rec = _ready_handoff()
    ho.operation_receipt(rec, "native_create", state="done", native_id="FORM123")
    ho.operation_receipt(rec, "embed", state="done",
                         evidence={"target": "funnel_step", "snippet_len": 140})
    assert rec["operations"]["embed"]["native_id"] is None
    assert rec["operations"]["embed"]["evidence"]["snippet_len"] == 140
    assert rec["operations"]["native_create"]["native_id"] == "FORM123"


def test_tag_attachment_is_never_a_native_form_setting():
    """The plan documents workflow | hidden_field ONLY; nothing is invented."""
    dep = fb.plan_dependencies(fb._resolve_fields({"form_fields": fb._reference_fields()}),
                               {"tags": ["podcast lead"]})
    attach = dep["tag_attachment"]
    assert attach["method"] in ho.TAG_ATTACHMENT_METHODS
    assert attach["workflow"]["owner_skill"] == "44-convert-and-flow-operator"
    assert attach["workflow"]["tags"] == ["zhc_podcast_lead"]


# ─────────── the ghl_survey_rest evidence gate is untouched (C7) ─────────────

def test_survey_rest_capture_gate_still_refuses_a_blind_post(tmp_path):
    with pytest.raises(srest.CaptureRequired):
        srest.require_capture(str(tmp_path))
    with pytest.raises(srest.CaptureRequired):
        srest.survey_save_route({"method": "POST"})
    with pytest.raises(srest.CaptureRequired):
        srest.survey_save_route({"url": "https://x/other", "method": "POST"})
    # a guessed endpoint is never derived, even from a survey-looking URL
    with pytest.raises(srest.CaptureRequired):
        srest.survey_save_route({"url": "https://backend/surveys/1", "method": "GET"})


def test_survey_rest_selftest_still_passes():
    assert srest._selftest() == 0


def test_handoff_selftest_still_passes():
    assert ho._selftest() == 0


def test_form_builder_selftest_still_passes():
    assert fb._selftest() == 0
