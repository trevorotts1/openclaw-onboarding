"""Issue 3: launch text sets have a build-with-copy path (reader -> compiler -> refusal -> delivery).

Fail-before: nothing bound Skill 50's SMS copy into a Skill 44 build, so every compiled SMS step stayed
``copy_pending`` and the build went ahead; a launch that elected texts could never be completed.
Pass-after: a text set with no approved copy blocks the builds that elected it; with copy the reader binds
``bindings.sms_copy``, the compiled SMS steps carry the bodies (``copy_pending`` False), a step the copy never
reached is a named compile refusal, and the set is delivered only from the saved SMS steps.

Run: python3 -m pytest 44-convert-and-flow-operator/automation-templates/launch-c/tests/test_plan_reader_text_sets.py -q
"""
import copy as _copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
LAUNCH_C = HERE.parent
SKILL = LAUNCH_C.parents[1]
REPO = SKILL.parent
ENGINE = SKILL / "tools" / "engine"
sys.path.insert(0, str(ENGINE))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


plan_reader = _load("text_sets_plan_reader", LAUNCH_C / "plan_reader.py")
emit_text_sets = _load("text_sets_emit", REPO / "50-email-engine" / "tools" / "emit_text_sets.py")
_l07 = _load("text_sets_l07", ENGINE / "tests" / "test_workflow_builder_l07.py")
from cli_anything.gohighlevel.utils import delivery_export, launch_text  # noqa: E402
from cli_anything.gohighlevel.utils import workflow_builder as wb  # noqa: E402

SET_ID = "text_abandoned_checkout"
BODIES = [
    "Looks like your checkout did not finish. Your cart is still open: {link}\nReply YES and I'll resend the link. Reply STOP to opt out.",
    "Still thinking it over? Your order is saved at {link}\nReply YES with questions. Reply STOP to opt out.",
]


def launch_plan():
    plan = json.loads(json.dumps(_l07_plan()))
    return plan


def _l07_plan():
    return {
        "schema_version": "1.0.0", "launch_id": "txt-1", "a2p_ready": True,
        "conversation_ai": {"requested": False, "mode": "none"},
        "offer": {"name": "Synthetic", "price_usd": 1, "currency": "USD", "payment_plans": False},
        "launch_calendar": dict(_l07.CALENDAR),
        "pages": [{"id": "page_landing", "kind": "landing", "url": "https://example.test", "waits_for": []}],
        "email_sequences": [
            {"id": "email_abandoned_checkout", "kind": "abandoned_checkout", "provider": "skill50",
             "email_count": 3, "draft_only": True, "waits_for": []},
            {"id": "email_welcome_access", "kind": "welcome_access", "provider": "skill50",
             "email_count": 2, "draft_only": True, "waits_for": []}],
        "text_sets": [{"id": SET_ID, "kind": "abandoned_checkout", "messages": 2, "promotional": True,
                       "draft_only": True, "opt_out_keyword": "STOP", "includes_reply_invitation": True,
                       "send_window": {"start": "08:00", "end": "21:00", "timezone": "recipient_local"},
                       "waits_for": ["page_landing"]}],
        "automations": [
            {"id": "auto_post_sale", "family": "post_sale", "template": "launch-b/launch-post-sale-purchase",
             "build_rail": "skill44_engine", "draft_only": True, "trigger": {"type": "payment_succeeded"},
             "waits_for": ["email_welcome_access", "page_landing"]},
            {"id": "auto_abandoned_checkout", "family": "abandoned_checkout",
             "template": "launch-b/abandoned-checkout-recovery", "build_rail": "skill44_engine",
             "draft_only": True, "trigger": {"type": "tag_added"},
             "waits_for": ["email_abandoned_checkout", SET_ID]}],
    }


def read(tmp_path, copy_dir=None, plan=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan or launch_plan()))
    argv = ["--launch-plan", str(plan_path), "--out", str(tmp_path / "out.json"), "--now", _l07.NOW]
    for seq_id, count in (("email_abandoned_checkout", 3), ("email_welcome_access", 2)):
        path = tmp_path / ("%s.json" % seq_id)
        path.write_text(json.dumps(_l07._build_plan(seq_id, count)))
        argv += ["--build-plan", str(path)]
    if copy_dir is not None:
        argv += ["--text-copy-dir", str(copy_dir)]
    rc = plan_reader.main(argv)
    return rc, json.loads((tmp_path / "out.json").read_text())


def skill50_copy(tmp_path, step_ids=("auto_abandoned_checkout-n9", "auto_abandoned_checkout-n18")):
    out = tmp_path / "working" / "text"
    emit_text_sets.emit(launch_plan(), {"sets": {SET_ID: [
        {"step_id": step_ids[0], "body": BODIES[0]}, {"step_id": step_ids[1], "body": BODIES[1]}]}}, out)
    return out


def build(document, unit="auto_abandoned_checkout"):
    return next(b for b in document["builds"] if b["id"] == unit)


def test_text_set_without_copy_blocks_the_build_that_elected_it(tmp_path):
    rc, doc = read(tmp_path, copy_dir=tmp_path / "working" / "text")
    assert rc == 4
    assert build(doc)["state"] == "blocked"
    assert "text_set:%s copy" % SET_ID in build(doc)["blocked_by"]
    text = doc["text_builds"][0]
    assert text["id"] == SET_ID and text["template"] == "launch-text-set" and text["state"] == "blocked"
    assert plan_reader.blocked_builds(doc)  # the reader exits 4


def test_with_copy_the_build_is_ready_and_carries_the_bodies(tmp_path):
    rc, doc = read(tmp_path, copy_dir=skill50_copy(tmp_path))
    assert rc == 0, doc and [b["blocked_by"] for b in doc["builds"]]
    assert build(doc)["state"] == "ready" and build(doc)["text_sets"] == [SET_ID]
    assert build(doc)["bindings"]["sms_copy"] == {"auto_abandoned_checkout-n9": BODIES[0],
                                                  "auto_abandoned_checkout-n18": BODIES[1]}
    text = doc["text_builds"][0]
    assert text["state"] == "ready" and text["automations"] == ["auto_abandoned_checkout"]
    assert set(text["categories"].values()) == {"marketing"}
    assert "bindings" not in build(doc, "auto_post_sale")  # no elected text, no binding


def test_compiled_sms_steps_carry_the_approved_copy(tmp_path):
    _rc, doc = read(tmp_path, copy_dir=skill50_copy(tmp_path))
    campaign = wb.compile_launch_builds(doc)
    launch_text.enforce_sms_copy(campaign, doc)
    assert not campaign.refusals, campaign.refusals
    steps = [s for wf in campaign.values() if wf["source_unit"] == "auto_abandoned_checkout"
             for s in wf["templates"] if s["type"] == "sms"]
    assert [s["attributes"]["body"] for s in steps] == BODIES
    assert all(s["attributes"]["copy_pending"] is False for s in steps)


def test_a_step_the_copy_never_reached_is_a_named_refusal(tmp_path):
    # copy keyed to step ids that exist in no SMS step: the template steps stay copy_pending
    _rc, doc = read(tmp_path, copy_dir=skill50_copy(tmp_path, step_ids=("nope-1", "nope-2")))
    campaign = launch_text.enforce_sms_copy(wb.compile_launch_builds(doc), doc)
    refusal = next(r for r in campaign.refusals if r["id"] == "auto_abandoned_checkout")
    assert refusal["code"] == launch_text.CODE_PENDING
    assert not [wf for wf in campaign.values() if wf["source_unit"] == "auto_abandoned_checkout"]
    assert [wf for wf in campaign.values() if wf["source_unit"] == "auto_post_sale"]  # others continue


def test_compile_launch_builds_alone_refuses_pending_copy(tmp_path):
    # Only the production entry point (no direct enforce_sms_copy call): removing its wiring turns this red.
    _rc, doc = read(tmp_path, copy_dir=skill50_copy(tmp_path, step_ids=("nope-1", "nope-2")))
    campaign = wb.compile_launch_builds(doc, require_ready=True)
    refusal = next(r for r in campaign.refusals if r["id"] == "auto_abandoned_checkout")
    assert refusal["code"] == "SMS-COPY-PENDING" and refusal["detail"]["pending"]
    assert not [wf for wf in campaign.values() if wf["source_unit"] == "auto_abandoned_checkout"]
    assert [wf for wf in campaign.values() if wf["source_unit"] == "auto_post_sale"]


def test_compile_launch_builds_alone_refuses_copy_that_landed_in_no_step(tmp_path):
    _rc, doc = read(tmp_path, copy_dir=skill50_copy(tmp_path))
    build(doc)["bindings"]["sms_copy"]["auto_abandoned_checkout-n99"] = "Approved copy for a step that is not there."
    campaign = wb.compile_launch_builds(doc, require_ready=True)
    refusal = next(r for r in campaign.refusals if r["id"] == "auto_abandoned_checkout")
    assert refusal["code"] == "SMS-COPY-UNBOUND" and refusal["detail"]["unbound"] == ["auto_abandoned_checkout-n99"]
    assert not [wf for wf in campaign.values() if wf["source_unit"] == "auto_abandoned_checkout"]


def test_an_elected_text_build_that_compiles_no_sms_step_is_a_named_refusal(tmp_path):
    # auto_post_sale compiles no SMS step; mark it as electing the set and the approved copy has nowhere to land.
    _rc, doc = read(tmp_path, copy_dir=skill50_copy(tmp_path))
    build(doc, "auto_post_sale").update(text_sets=[SET_ID], bindings={"sms_copy": {}})
    campaign = wb.compile_launch_builds(doc, require_ready=True)
    refusal = next(r for r in campaign.refusals if r["id"] == "auto_post_sale")
    assert refusal["code"] == launch_text.CODE_UNBOUND
    assert "the build compiles no SMS step to carry the approved copy" in refusal["reason"]
    assert not [wf for wf in campaign.values() if wf["source_unit"] == "auto_post_sale"]
    assert [wf for wf in campaign.values() if wf["source_unit"] == "auto_abandoned_checkout"]


def test_a_build_with_no_elected_text_keeps_todays_behaviour(tmp_path):
    _rc, doc = read(tmp_path, copy_dir=skill50_copy(tmp_path))
    campaign = launch_text.enforce_sms_copy(wb.compile_launch_builds(doc), doc)
    assert not any(r["id"] == "auto_post_sale" for r in campaign.refusals)


def test_reader_refuses_copy_that_is_not_the_plans_shape(tmp_path):
    out = skill50_copy(tmp_path)
    path = out / ("%s.sms.json" % SET_ID)
    doc = json.loads(path.read_text())
    doc["messages"] = doc["messages"][:1]  # the plan promises 2
    path.write_text(json.dumps(doc))
    _rc, built = read(tmp_path, copy_dir=out)
    assert build(built)["state"] == "blocked"
    copy, problem = plan_reader.read_text_copy(out, SET_ID, 2)
    assert copy is None and "1 message" in problem


# ---- one test per shape check of read_text_copy, so none hides another -------------------------------

def _copy_doc(out):
    return json.loads((out / ("%s.sms.json" % SET_ID)).read_text())


def _refused_for(tmp_path, edit, expected_messages=2):
    out = skill50_copy(tmp_path)
    doc = _copy_doc(out)
    edit(doc)
    (out / ("%s.sms.json" % SET_ID)).write_text(json.dumps(doc))
    copy, problem = plan_reader.read_text_copy(out, SET_ID, expected_messages)
    _rc, built = read(tmp_path, copy_dir=out)
    return copy, problem, built


def test_the_unedited_copy_file_is_accepted_by_the_reader(tmp_path):
    out = skill50_copy(tmp_path)
    copy, problem = plan_reader.read_text_copy(out, SET_ID, 2)
    assert problem is None and copy["set_id"] == SET_ID


@pytest.mark.parametrize("label,edit,why", [
    ("another set's id", lambda d: d.update(set_id="text_some_other_set"), "is not a Skill 50 sms set"),
    ("profile_sha256 is not a sha256", lambda d: d.update(profile_sha256="not-a-hash"), "is not a Skill 50 sms set"),
    ("profile_sha256 absent", lambda d: d.pop("profile_sha256"), "is not a Skill 50 sms set"),
    ("no messages", lambda d: d.update(messages=[]), "is not a Skill 50 sms set"),
    ("a repeated step_id", lambda d: d["messages"][1].update(step_id=d["messages"][0]["step_id"]),
     "repeats a step_id"),
    ("an empty body", lambda d: d["messages"][0].update(body="  "), "without step_id, body and category"),
    ("no category", lambda d: d["messages"][1].pop("category"), "without step_id, body and category"),
    ("an empty step_id", lambda d: d["messages"][0].update(step_id=""), "without step_id, body and category"),
    ("a message that is not an object", lambda d: d["messages"].__setitem__(1, "text"),
     "without step_id, body and category"),
])
def test_reader_blocks_the_build_on_each_copy_shape_defect(tmp_path, label, edit, why):
    copy, problem, built = _refused_for(tmp_path, edit)
    assert copy is None and why in problem, (label, problem)
    assert build(built)["state"] == "blocked", label
    assert "text_set:%s copy" % SET_ID in build(built)["blocked_by"], label


def test_a_blocked_text_set_is_a_blocked_build_even_when_no_automation_is_blocked_by_it():
    ready = {"id": "auto_x", "state": "ready", "workflows": [{"key": "k"}]}
    blocked = {"builds": [ready], "text_builds": [{"id": "text_x", "state": "blocked"}]}
    assert plan_reader.blocked_builds(blocked) == ["text_x"]
    ok = {"builds": [ready], "text_builds": [{"id": "text_x", "state": "ready"}]}
    assert plan_reader.blocked_builds(ok) == []


# ---- delivery: the set is delivered only from the saved SMS steps ---------------------------------

def _proven(doc, unit="auto_abandoned_checkout"):
    campaign = wb.compile_launch_builds(doc)
    steps = next(wf for wf in campaign.values() if wf["source_unit"] == unit)["templates"]
    return {unit: [{"workflow_id": "wf-1", "templates": steps}]}


def test_text_set_is_delivered_from_the_saved_sms_steps(tmp_path):
    _rc, doc = read(tmp_path, copy_dir=skill50_copy(tmp_path))
    path, reasons = delivery_export.export_text_set(doc["text_builds"][0], "txt-1", _proven(doc),
                                                    tmp_path / "exports")
    assert reasons == []
    export = json.loads(path.read_text())
    assert export["contract"] == "skill44.sms-set.v1" and export["unit_key"] == "txt-1/" + SET_ID
    assert export["produced_by"] == "caf workflows build --from-automation-build"
    assert [m["step_id"] for m in export["messages"]] == ["auto_abandoned_checkout-n18",
                                                          "auto_abandoned_checkout-n9"]
    assert {m["category"] for m in export["messages"]} == {"marketing"}
    assert "body" not in export["messages"][0]  # the journal rule: hashes, not message bodies


def test_text_set_is_refused_when_a_body_is_not_in_a_saved_step_or_the_unit_is_not_delivered(tmp_path):
    _rc, doc = read(tmp_path, copy_dir=skill50_copy(tmp_path))
    proven = _proven(doc)
    for step in proven["auto_abandoned_checkout"][0]["templates"]:
        if step["type"] == "sms":
            step["attributes"]["body"] = "someone edited this in the provider"
    path, reasons = delivery_export.export_text_set(doc["text_builds"][0], "txt-1", proven,
                                                    tmp_path / "exports")
    assert path is None and any("not the body of any saved SMS step" in r for r in reasons)
    path, reasons = delivery_export.export_text_set(doc["text_builds"][0], "txt-1", {},
                                                    tmp_path / "exports")
    assert path is None and any("not delivered" in r for r in reasons)
    _rc, blocked = read(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path,
                        copy_dir=tmp_path / "nowhere")
    path, reasons = delivery_export.export_text_set(blocked["text_builds"][0], "txt-1", proven,
                                                    tmp_path / "exports")
    assert path is None and reasons == ["text_set:%s copy" % SET_ID]


def test_end_to_end_skill50_copy_reaches_the_saved_workflow_and_delivery_follows_the_unit(tmp_path):
    """Skill 50 emit -> reader -> compile -> build + read-back (fake provider): the approved bodies are the
    bodies of the SAVED SMS steps, and the set is delivered exactly when its electing automation is."""
    from cli_anything.gohighlevel.utils.workflow_builder import BuildJournal, _readback_templates
    _rc, doc = read(tmp_path, copy_dir=skill50_copy(tmp_path))
    campaign = wb.compile_launch_builds(doc)
    assert not campaign.refusals, campaign.refusals
    client = _l07.FakeClient()
    stats = wb.CampaignBuilder(client).build(campaign, folder_name="F", journal=str(tmp_path / "j.jsonl"))
    assert not stats["errors"], stats["errors"]
    saved = [s["attributes"]["body"] for wf in client.workflows.values() for s in wf["templates"]
             if s.get("type") == "sms"]
    assert saved == BODIES, saved
    plan_path = tmp_path / "plan.json"
    summary = delivery_export.export_build(
        doc, campaign, stats, journal=BuildJournal(tmp_path / "j.jsonl"),
        read_templates=lambda wid: _readback_templates(client, _l07.LOC, wid),
        deliveries_path=str(tmp_path / "deliveries.json"), launch_plan=str(plan_path))
    rows = json.loads((tmp_path / "deliveries.json").read_text())
    assert (SET_ID in rows) == ("auto_abandoned_checkout" in rows), summary
    if SET_ID in rows:
        assert rows[SET_ID]["lane_validation"]["contract"] == "skill44.sms-set.v1"
    else:  # refused by name, never silently absent
        assert SET_ID in summary["refused"] and "auto_abandoned_checkout" in summary["refused"]


# ---- sweep round 1: why a copy file cannot be bound, and one verdict per text set -------------------

def _copy_file(tmp_path, **edit):
    """The valid Skill 50 file for SET_ID, with `edit` applied (a key set to _GONE is removed)."""
    path = skill50_copy(tmp_path) / ("%s.sms.json" % SET_ID)
    doc = json.loads(path.read_text())
    for key, value in edit.items():
        if value is _GONE:
            doc.pop(key)
        else:
            doc[key] = value
    path.write_text(json.dumps(doc))
    return path.parent, doc


_GONE = object()


def test_read_text_copy_binds_a_valid_file_and_names_why_it_refuses_any_other(tmp_path):
    rtc = plan_reader.read_text_copy
    assert rtc(None, SET_ID, 2) == (None, "no --text-copy-dir given")
    assert rtc("", SET_ID, 2) == (None, "no --text-copy-dir given")
    assert rtc(tmp_path / "nowhere", SET_ID, 2) == (None, "%s.sms.json is absent" % SET_ID)
    copy_dir, good = _copy_file(tmp_path)
    assert rtc(copy_dir, SET_ID, 2) == (good, None)
    assert rtc(copy_dir, SET_ID, None) == (good, None)  # a plan that names no count binds any count
    assert "has 2 message(s), the launch plan says 3" in rtc(copy_dir, SET_ID, 3)[1]
    assert rtc(copy_dir, SET_ID, 3)[0] is None


@pytest.mark.parametrize("label,edit,why", [
    ("not an object", None, "is not a Skill 50 sms set for"),
    ("other set id", {"set_id": "text_other"}, "is not a Skill 50 sms set for"),
    ("no set id", {"set_id": _GONE}, "is not a Skill 50 sms set for"),
    ("no messages", {"messages": []}, "is not a Skill 50 sms set for"),
    ("messages not a list", {"messages": "two"}, "is not a Skill 50 sms set for"),
    ("no profile hash", {"profile_sha256": _GONE}, "is not a Skill 50 sms set for"),
    ("profile hash not a hash", {"profile_sha256": "abc"}, "is not a Skill 50 sms set for"),
    ("profile hash not a string", {"profile_sha256": 5}, "is not a Skill 50 sms set for"),
    ("a message that is not an object", {"messages": ["text", "text"]},
     "has a message without step_id, body and category"),
    ("a blank body", {"messages": [{"step_id": "a", "body": " ", "category": "marketing"},
                                   {"step_id": "b", "body": "x", "category": "marketing"}]},
     "has a message without step_id, body and category"),
    ("a message without a category", {"messages": [{"step_id": "a", "body": "x"},
                                                   {"step_id": "b", "body": "y", "category": "marketing"}]},
     "has a message without step_id, body and category"),
    ("a repeated step id", {"messages": [{"step_id": "a", "body": "x", "category": "marketing"},
                                         {"step_id": "a", "body": "y", "category": "marketing"}]},
     "repeats a step_id"),
])
def test_read_text_copy_refuses_each_malformed_file_by_name(tmp_path, label, edit, why):
    copy_dir, _good = _copy_file(tmp_path)
    path = copy_dir / ("%s.sms.json" % SET_ID)
    if edit is None:
        path.write_text("[]")
    else:
        doc = json.loads(path.read_text())
        for key, value in edit.items():
            doc.pop(key) if value is _GONE else doc.__setitem__(key, value)
        path.write_text(json.dumps(doc))
    copy, problem = plan_reader.read_text_copy(copy_dir, SET_ID, 2)
    assert copy is None and why in problem, (label, problem)


def test_read_text_copy_calls_an_unparseable_file_unreadable(tmp_path):
    copy_dir, _good = _copy_file(tmp_path)
    (copy_dir / ("%s.sms.json" % SET_ID)).write_text("not json")
    copy, problem = plan_reader.read_text_copy(copy_dir, SET_ID, 2)
    assert copy is None and "is unreadable" in problem


def test_each_text_set_is_judged_on_its_own_copy_and_carries_its_own_facts(tmp_path):
    plan = launch_plan()
    plan["text_sets"].append({"id": "text_extra", "kind": "abandoned_checkout", "messages": 1,
                              "promotional": False, "draft_only": True, "opt_out_keyword": "STOP",
                              "includes_reply_invitation": True,
                              "send_window": {"start": "08:00", "end": "21:00", "timezone": "recipient_local"},
                              "waits_for": ["page_landing"]})
    copy_dir = skill50_copy(tmp_path)  # a file for SET_ID only
    sha = json.loads((copy_dir / ("%s.sms.json" % SET_ID)).read_text())["profile_sha256"]
    rc, doc = read(tmp_path, copy_dir=copy_dir, plan=plan)
    by_id = {t["id"]: t for t in doc["text_builds"]}
    assert sorted(by_id) == sorted(["text_extra", SET_ID])
    ready, extra = by_id[SET_ID], by_id["text_extra"]
    assert (ready["state"], ready["blocked_by"], ready["automations"]) == (
        "ready", [], ["auto_abandoned_checkout"])
    assert ready["profile_sha256"] == sha and ready["unit_key"] == "txt-1/" + SET_ID
    assert ready["bindings"]["sms_copy"] == {"auto_abandoned_checkout-n9": BODIES[0],
                                             "auto_abandoned_checkout-n18": BODIES[1]}
    assert ready["categories"] == {"auto_abandoned_checkout-n9": "marketing",
                                   "auto_abandoned_checkout-n18": "marketing"}
    assert (extra["state"], extra["blocked_by"], extra["automations"]) == (
        "blocked", ["text_set:text_extra copy"], [])
    assert extra["bindings"] == {"sms_copy": {}} and extra["categories"] == {}
    assert extra["profile_sha256"] is None
    assert rc == 4 and plan_reader.blocked_builds(doc) == ["text_extra"]


def test_a_plan_with_no_text_sets_emits_no_text_builds_at_all(tmp_path):
    plan = launch_plan()
    plan["text_sets"] = []
    next(a for a in plan["automations"] if a["id"] == "auto_abandoned_checkout")["waits_for"] = [
        "email_abandoned_checkout"]
    rc, doc = read(tmp_path, copy_dir=None, plan=plan)
    assert rc == 0 and "text_builds" not in doc
    assert "text_sets" not in build(doc)


# ---- malformed shapes: a campaign or document with nulls is judged, never a traceback (ruling WP-06b-9) -------

class _Campaign(dict):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.refusals = []


def test_sms_steps_skips_campaign_entries_templates_and_steps_that_are_not_objects():
    sms = {"id": "s1", "type": "sms"}
    campaign = {"junk": "a bare string, not a workflow",
                "no_templates": {"source_unit": "u", "templates": None},
                "ok": {"source_unit": "u", "templates": ["a bare string", sms, {"type": "email"}]},
                "other_unit": {"source_unit": "v", "templates": [{"id": "s2", "type": "sms"}]}}
    assert launch_text.sms_steps(campaign, "u") == [sms]


def test_enforce_sms_copy_with_null_or_non_object_builds_changes_nothing_and_does_not_crash():
    campaign = _Campaign(wf={"source_unit": "u", "templates": []})
    assert launch_text.enforce_sms_copy(campaign, {"builds": None}) is campaign
    assert launch_text.enforce_sms_copy(campaign, {"builds": ["a bare string", None, {"id": "u"}]}) is campaign
    assert campaign.refusals == [] and "wf" in campaign


def test_enforce_sms_copy_with_null_attributes_bindings_and_sms_copy_is_judged_not_a_traceback():
    for bindings in (None, {"sms_copy": None}):
        campaign = _Campaign(wf={"source_unit": "u", "templates": [
            {"id": "s1", "type": "sms", "attributes": None}]})
        build = {"id": "u", "text_sets": ["t"], "bindings": bindings}
        assert launch_text.enforce_sms_copy(campaign, {"builds": [build]}) is campaign
        assert campaign.refusals == [] and "wf" in campaign


def test_enforce_sms_copy_refuses_a_build_that_elected_texts_but_compiles_no_sms_step():
    campaign = _Campaign(wf={"source_unit": "u", "templates": [{"id": "e1", "type": "email"}]})
    launch_text.enforce_sms_copy(campaign, {"builds": [{"id": "u", "text_sets": ["t"]}]})
    assert [r["code"] for r in campaign.refusals] == [launch_text.CODE_UNBOUND]
    assert "compiles no SMS step" in campaign.refusals[0]["reason"] and "wf" not in campaign
