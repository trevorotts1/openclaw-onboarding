"""RFX-004: approved text-set copy binds to SMS steps by an explicit step-id map, and every SMS step
carries its native eligibility conditions (WF-25 / WF-16).

Fail-before: bound-sequence mode installed only email and wait steps, so approved SMS copy (access_1,
doors_open_1, nurture_*) landed in no step and the elected builds were refused SMS-COPY-UNBOUND; template
tokens nothing bound kept the template graphs from compiling; and no SMS step carried the sms-subscribed,
sms-opted-out, 08:00-21:00 recipient-local window, contact-cap or doors-close conditions.

Offline: the real launch-c reader over synthetic files; no provider, no send, no credential. Run:
    python3 -m pytest 44-convert-and-flow-operator/tools/engine/tests/test_launch_sms_binding.py -q
"""
import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1]
SKILL = ENGINE.parents[1]
sys.path.insert(0, str(ENGINE))

from cli_anything.gohighlevel.utils import launch_step_compiler as lsc  # noqa: E402
from cli_anything.gohighlevel.utils import workflow_builder as wb  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


plan_reader = _load("rfx004_plan_reader", SKILL / "automation-templates" / "launch-c" / "plan_reader.py")
sms_eligibility = _load("rfx004_sms_eligibility",
                        SKILL / "automation-templates" / "launch-text" / "sms_eligibility.py")
graph_validator = _load("rfx004_validate_graph", SKILL / "tools" / "validate_graph.py")

NOW = "2026-11-01T00:00:00-05:00"
CALENDAR = {"launch_at": "2026-11-03T12:00:00-05:00", "doors_open_at": "2026-11-03T09:00:00-05:00",
            "doors_close_at": "2026-11-10T23:59:00-05:00", "timezone": "America/New_York"}
WINDOW = {"start": "08:00", "end": "21:00", "timezone": "recipient_local"}
SHA = "0" * 64
COPY = {  # synthetic approved copy, keyed by Skill 50 step id
    "text_access_link": {"access_1": "You're in. Your access: {link} Reply YES for next steps. Reply STOP to opt out."},
    "text_doors_open": {"doors_open_1": "Doors are open: {link} Reply YES for details. Reply STOP to opt out."},
    "text_abandoned_checkout": {
        "cart_1": "Your checkout did not finish: {link} Reply YES and I'll resend it. Reply STOP to opt out.",
        "cart_2": "Your order is still saved: {link} Reply YES with questions. Reply STOP to opt out."},
}
KINDS = {"text_access_link": ("access_link", False), "text_doors_open": ("doors_open", True),
         "text_abandoned_checkout": ("abandoned_checkout", True)}


def _text_set(set_id):
    kind, promotional = KINDS[set_id]
    return {"id": set_id, "kind": kind, "messages": len(COPY[set_id]), "promotional": promotional,
            "draft_only": True, "opt_out_keyword": "STOP", "includes_reply_invitation": True,
            "send_window": dict(WINDOW), "waits_for": ["page_landing"]}


def _build_plan(seq_id, count, purchase_of=None):
    templates = []
    for i in range(count):
        templates.append({"id": "%s-e%d" % (seq_id, i), "type": "email", "name": "Email %d" % i,
                          "attributes": {"subject": "synthetic %d" % i, "body": "<p>synthetic</p>",
                                         "html": "<p>synthetic</p>", "fromName": "Synthetic Sender"}})
        if i < count - 1:
            templates.append({"id": "%s-w%d" % (seq_id, i), "type": "wait", "name": "Wait 1 Days",
                              "attributes": {"type": "time",
                                             "startAfter": {"type": "days", "value": 1, "when": "after"}}})
    lifecycle = copy.deepcopy(plan_reader.DEFAULT_LIFECYCLE)
    if purchase_of:
        lifecycle["stop_rules"][0]["purchase_of"] = purchase_of
    return {"folder": "Synthetic Drafts",
            "_meta": {"sequence_id": seq_id, "draft_only": True, "deploy_mode": "draft-only",
                      "lifecycle": lifecycle,
                      "enrollment_conditions": copy.deepcopy(plan_reader.DEFAULT_ENROLLMENT_CONDITIONS),
                      "sender_config_refs": copy.deepcopy(plan_reader.DEFAULT_SENDER)},
            seq_id: {"name": "%s (DRAFT)" % seq_id, "tag": "launch:%s" % seq_id.replace("_", "-"),
                     "status": "draft", "templates": templates}}


def launch_plan():
    return {
        "schema_version": "1.0.0", "launch_id": "rfx-sms", "a2p_ready": False,
        "conversation_ai": {"requested": False, "mode": "none"},
        "offer": {"name": "Synthetic", "price_usd": 1, "currency": "USD", "payment_plans": False,
                  "packages": [{"offer_id": "OFFER-MAIN", "slot": "main"},
                               {"offer_id": "OFFER-UP1", "slot": "upsell_1"}]},
        "launch_calendar": dict(CALENDAR),
        "pages": [{"id": "page_landing", "kind": "landing", "url": "https://example.test", "waits_for": []}],
        "email_sequences": [
            {"id": "email_main_launch", "kind": "main_launch", "provider": "skill50", "email_count": 3,
             "draft_only": True, "waits_for": []},
            {"id": "email_welcome_access", "kind": "welcome_access", "provider": "skill50",
             "email_count": 2, "draft_only": True, "waits_for": []},
            {"id": "email_abandoned_checkout", "kind": "abandoned_checkout", "provider": "skill50",
             "email_count": 3, "draft_only": True, "waits_for": []},
            {"id": "email_upsell_1", "kind": "upsell_followup", "provider": "skill50", "email_count": 1,
             "draft_only": True, "waits_for": []}],
        "text_sets": [_text_set(s) for s in COPY],
        "automations": [
            {"id": "auto_main_launch", "family": "pre_launch", "template": "launch-a/launch-a-prelaunch-window",
             "build_rail": "skill44_engine", "draft_only": True, "trigger": {"type": "tag_added"},
             "waits_for": ["email_main_launch", "text_doors_open"]},
            {"id": "auto_post_sale", "family": "post_sale", "template": "launch-b/launch-post-sale-purchase",
             "build_rail": "skill44_engine", "draft_only": True, "trigger": {"type": "payment_succeeded"},
             "waits_for": ["email_welcome_access", "text_access_link"], "variant_tag": "main"},
            {"id": "auto_abandoned_checkout", "family": "abandoned_checkout",
             "template": "launch-b/abandoned-checkout-recovery", "build_rail": "skill44_engine",
             "draft_only": True, "trigger": {"type": "tag_added"},
             "waits_for": ["email_abandoned_checkout", "text_abandoned_checkout"]},
            {"id": "auto_upsell_1", "family": "upsell_downsell", "template": "launch-b/upsell-downsell-branch",
             "build_rail": "skill44_engine", "draft_only": True, "trigger": {"type": "tag_added"},
             "waits_for": ["email_upsell_1"], "followed_offer_id": "OFFER-UP1"}],
    }


def read(plan=None, copy_by_set=None):
    tmp = Path(tempfile.mkdtemp(prefix="rfx004-sms-"))
    plan = plan or launch_plan()
    (tmp / "plan.json").write_text(json.dumps(plan))
    text = tmp / "text"
    text.mkdir()
    for set_id, messages in (COPY if copy_by_set is None else copy_by_set).items():
        category = "marketing" if KINDS[set_id][1] else "operational"
        (text / ("%s.sms.json" % set_id)).write_text(json.dumps({
            "set_id": set_id, "profile_sha256": SHA,
            "messages": [{"step_id": k, "body": v, "category": category} for k, v in messages.items()]}))
    argv = ["--launch-plan", str(tmp / "plan.json"), "--out", str(tmp / "out.json"), "--now", NOW,
            "--text-copy-dir", str(text)]
    for seq in plan["email_sequences"]:
        path = tmp / ("%s.json" % seq["id"])
        follow = "OFFER-UP1" if seq["kind"] in plan_reader.FOLLOW_UP_KINDS else None
        path.write_text(json.dumps(_build_plan(seq["id"], seq["email_count"], follow)))
        argv += ["--build-plan", str(path)]
    rc = plan_reader.main(argv)
    return rc, json.loads((tmp / "out.json").read_text())


def _emails(n):
    return [{"id": "e%d" % i, "type": "email", "name": "E", "attributes": {"subject": "s", "body": "b"}}
            for i in range(n)]


def unit(campaign, unit_id):
    return [wf for wf in campaign.values() if wf["source_unit"] == unit_id]


def sms_of(campaign, unit_id):
    return [s for wf in unit(campaign, unit_id) for s in wf["templates"] if s["type"] == "sms"]


@pytest.fixture(scope="module")
def compiled():
    rc, doc = read()
    assert rc == 0, [(b["id"], b["blocked_by"]) for b in doc["builds"]]
    return doc, wb.compile_launch_builds(doc)


# ── binding: approved copy lands in the right step, by id ────────────────────────────────────────
def test_reader_carries_the_explicit_step_id_map(compiled):
    doc, _campaign = compiled
    build = next(b for b in doc["builds"] if b["id"] == "auto_abandoned_checkout")
    assert build["bindings"]["sms_sets"] == [{
        "set_id": "text_abandoned_checkout", "kind": "abandoned_checkout", "category": "marketing",
        "step_ids": ["cart_1", "cart_2"]}]
    upsell = next(b for b in doc["builds"] if b["id"] == "auto_upsell_1")
    assert upsell["followed_offer_slot"] == "upsell_1" and upsell["compile_spec"] is None


def test_fixture_launch_compiles_with_every_sms_body_bound_to_its_step(compiled):
    _doc, campaign = compiled
    assert not campaign.refusals, campaign.refusals
    bound = {s["attributes"]["copy_step_id"]: s["attributes"]["body"]
             for u in ("auto_main_launch", "auto_post_sale", "auto_abandoned_checkout")
             for s in sms_of(campaign, u)}
    assert bound == {k: v for messages in COPY.values() for k, v in messages.items()}
    for u in ("auto_main_launch", "auto_post_sale", "auto_abandoned_checkout"):
        assert all(s["attributes"]["copy_pending"] is False for s in sms_of(campaign, u))


def test_template_slots_take_the_set_in_order(compiled):
    _doc, campaign = compiled
    [wf] = unit(campaign, "auto_abandoned_checkout")
    assert wf["compile_mode"] == "template_graph"
    by_slot = {s["id"]: s["attributes"]["copy_step_id"] for s in sms_of(campaign, "auto_abandoned_checkout")}
    assert by_slot == {"auto_abandoned_checkout-n9": "cart_1", "auto_abandoned_checkout-n18": "cart_2"}


def test_bound_sequence_places_access_text_after_the_first_email(compiled):
    _doc, campaign = compiled
    [wf] = unit(campaign, "auto_post_sale")
    assert wf["compile_mode"] == "bound_sequence"
    [sms] = sms_of(campaign, "auto_post_sale")
    assert sms["attributes"]["copy_step_id"] == "access_1"
    by_id = {s["id"]: s for s in wf["templates"]}
    guard = by_id[sms["parentKey"]]  # the eligibility if/else sits between the email and the text
    assert guard["type"] == "if_else" and guard["branches"]["true"] == sms["id"]
    assert by_id[guard["parentKey"]]["type"] in ("email", "if_else")


def test_doors_open_text_is_gated_by_the_plans_own_calendar_instant(compiled):
    _doc, campaign = compiled
    [sms] = sms_of(campaign, "auto_main_launch")
    assert sms["attributes"]["copy_step_id"] == "doors_open_1"
    [wf] = unit(campaign, "auto_main_launch")
    waits = [s for s in wf["templates"] if s["type"] == "wait"
             and (s["attributes"].get("untilDate") or "").startswith("2026-11-03T09:00")]
    assert waits, "doors-open text must be gated by a wait-until-date at doors_open_at"
    assert any(r["action"] == "wait_until_date" and r["at"].startswith("2026-11-03T09:00")
               for r in wf["browser_steps"])


def test_plan_tokens_bind_from_plan_fields(compiled):
    _doc, campaign = compiled
    [wf] = unit(campaign, "auto_upsell_1")
    assert wf["compile_mode"] == "bound_sequence"  # 1 approved email, 0 template email slots
    assert "template_graph_skipped:approved_emails_1_template_slots_0" in wf["compile_notes"]
    spec, key, _ = lsc.resolve_template({"family": "upsell_downsell", "template": "launch-b/upsell-downsell-branch"})
    trial = {"unit_key": "rfx-sms/u", "blocked_by": [], "browser_steps": []}
    binds = lsc.plan_bindings({"followed_offer_id": "OFFER-UP1", "followed_offer_slot": "upsell_1"})
    steps = lsc._compile_graph(trial, spec["build_graph"], "u", [], binds, True, None, "b", "upsell_downsell")
    assert trial["blocked_by"] == []
    tags = {t for s in steps for t in (s.get("attributes") or {}).get("tags", [])}
    assert {"bought-upsell_1", "declined-OFFER-UP1", "option-branch:upsell_1:OFFER-UP1"} <= tags


def test_a_missing_plan_field_is_refused_by_name_not_guessed():
    spec, _key, _ = lsc.resolve_template({"family": "upsell_downsell", "template": "launch-b/upsell-downsell-branch"})
    trial = {"unit_key": "rfx-sms/u", "blocked_by": [], "browser_steps": []}
    lsc._compile_graph(trial, spec["build_graph"], "u", [], {"offer_id": "OFFER-UP1"}, True, None, "b", None)
    assert "tag_unresolved:n4:needs:followed_offer_slot" in trial["blocked_by"]
    spec, _key, _ = lsc.resolve_template({"family": "opt_in", "template": "launch-a/launch-optin-register-login"})
    trial = {"unit_key": "rfx-sms/u", "blocked_by": [], "browser_steps": []}
    lsc._compile_graph(trial, spec["build_graph"], "u", _emails(2), {}, True, None, "b", None)
    assert "tag_unresolved:n1:needs:variant_tag" in trial["blocked_by"]
    ok = {"unit_key": "rfx-sms/u", "blocked_by": [], "browser_steps": []}
    steps = lsc._compile_graph(ok, spec["build_graph"], "u", _emails(2),
                               lsc.plan_bindings({"variant_tag": "launch-registered"}), True, None, "b", None)
    assert ok["blocked_by"] == []
    assert {"launch-registered", "launch-registered-started"} <= {
        t for s in steps for t in (s.get("attributes") or {}).get("tags", [])}


def test_event_clock_binds_only_with_a_purchase_identity():
    graph = lsc.resolve_template({"family": "onboarding_review", "template": "new"})[0]["build_graph"]
    assert lsc._unresolved_until(graph, {}) == "onboard_start_at+1day:needs:purchase_identity"
    binds = lsc.plan_bindings({"purchase_identity": {"transaction_id": "ghl.transaction.id"}})
    assert lsc._unresolved_until(graph, {}, binds) is None
    out = {"unit_key": "rfx-sms/u", "blocked_by": [], "browser_steps": []}
    steps = lsc._compile_graph(out, graph, "u", _emails(5), binds, False,
                               None, "b", None)
    waits = [s for s in steps if s["type"] == "wait" and s["attributes"].get("type") == "event_relative"]
    assert [(w["attributes"]["offset"], w["attributes"]["unit"]) for w in waits] == [(1, "days"), (7, "days")]
    clock = [r["action"] for r in out["browser_steps"]
             if r["action"] in ("set_event_start_time", "wait_until_event")]
    assert clock == ["set_event_start_time", "wait_until_event", "wait_until_event"]


def test_owner_approved_compile_spec_is_compiled():
    spec = {"build_graph": [
        {"id": "t", "type": "trigger", "attributes": {"event": "Tag Added"}},
        {"id": "n1", "type": "email", "after": "t", "attributes": {"message": "E1"}},
        {"id": "n2", "type": "sms", "after": "n1", "attributes": {"message": "S1", "text_set_kind": "access_link"}}]}
    got, key, reason = lsc.resolve_template({"id": "auto_x", "template": "new", "compile_spec": spec})
    assert reason is None and key == "new_template:auto_x" and got["build_graph"] == spec["build_graph"]
    assert lsc.resolve_template({"template": "new", "compile_spec": {"build_graph": []}})[2] \
        == "template_unbuildable:new_template.compile_spec"


# ── native SMS conditions on every SMS step ──────────────────────────────────────────────────────
def test_every_sms_step_carries_subscribed_optout_window_cap_and_deadline(compiled):
    _doc, campaign = compiled
    for u in ("auto_main_launch", "auto_abandoned_checkout"):
        for sms in sms_of(campaign, u):
            rules = {c["rule"]: c for c in sms["attributes"]["conditions"]}
            assert set(rules) == {"consent", "suppression", "aggregate_contact_cap", "quiet_hours",
                                  "launch_deadline"}, (u, sorted(rules))
            assert rules["consent"]["value"] == "sms-subscribed"
            assert (rules["suppression"]["type"], rules["suppression"]["value"]) == ("tag_absent", "sms-opted-out")
            assert (rules["quiet_hours"]["start"], rules["quiet_hours"]["end"],
                    rules["quiet_hours"]["timezone"]) == ("08:00", "21:00", "recipient_local")
            assert rules["aggregate_contact_cap"]["value"] == sms_eligibility.MARKETING_CAP
            assert rules["launch_deadline"]["anchor"] == "doors_close_at"
            assert rules["launch_deadline"]["value"] == "2026-11-10T23:59:00-05:00"


def test_operational_access_text_keeps_consent_optout_and_window_without_cap_or_deadline(compiled):
    _doc, campaign = compiled
    [sms] = sms_of(campaign, "auto_post_sale")
    assert {c["rule"] for c in sms["attributes"]["conditions"]} == {"consent", "suppression", "quiet_hours"}


def test_each_sms_step_sits_behind_a_native_guard_the_wf25_verifier_accepts(compiled):
    _doc, campaign = compiled
    for wf in campaign.values():
        sms = [s for s in wf["templates"] if s["type"] == "sms"]
        if not sms:
            continue
        export = {"workflowData": {"templates": wf["templates"]}}
        result = sms_eligibility.verify_saved_export(export, "marketing" if wf["promotional"] else "auto")
        assert result["ok"], (wf["source_unit"], result)
        by_id = {s["id"]: s for s in wf["templates"]}
        for s in sms:
            guard = by_id[s["attributes"]["sms_guard"]]
            assert guard["type"] == "if_else" and guard["branches"]["true"] == s["id"]
            assert guard["attributes"]["conditions"] == s["attributes"]["conditions"]
            assert any(r["action"] == "configure_if_else_condition" and r["step_id"] == guard["id"]
                       for r in wf["browser_steps"])


def test_guarded_graphs_pass_the_graph_validator(compiled):
    _doc, campaign = compiled
    for wf in campaign.values():
        verdict = graph_validator.graph({}, wf["templates"], None)
        assert verdict["verdict"] != "FAIL", (wf["source_unit"], verdict["failures"])


def test_drafts_only(compiled):
    _doc, campaign = compiled
    assert campaign and all(wf["status"] == "draft" for wf in campaign.values())


# ── refusals stay refusals ───────────────────────────────────────────────────────────────────────
def test_a_missing_text_body_is_still_refused():
    partial = {k: dict(v) for k, v in COPY.items()}
    partial["text_abandoned_checkout"].pop("cart_2")
    rc, doc = read(copy_by_set=partial)
    assert rc == 4
    build = next(b for b in doc["builds"] if b["id"] == "auto_abandoned_checkout")
    assert build["state"] == "blocked" and "text_set:text_abandoned_checkout copy" in build["blocked_by"]
    campaign = wb.compile_launch_builds(doc, require_ready=True)
    assert not unit(campaign, "auto_abandoned_checkout")
    assert any(r["id"] == "auto_abandoned_checkout" for r in campaign.refusals)


def test_copy_with_no_send_point_is_refused_and_named():
    plan = launch_plan()
    plan["automations"][1]["waits_for"].append("text_doors_open")  # post-sale bound sequence: doors-open is promo
    rc, doc = read(plan=plan)
    assert rc == 0
    campaign = wb.compile_launch_builds(doc)
    refusal = next(r for r in campaign.refusals if r["id"] == "auto_post_sale")
    assert refusal["code"] == "SMS-COPY-UNBOUND"
    assert "doors_open_1:" in refusal["reason"] and refusal["detail"]["unplaced"]


def test_explicit_after_step_places_a_text_the_contract_cannot_time():
    plan = launch_plan()
    plan["automations"][1]["waits_for"].append("text_doors_open")
    tmp_copy = {k: dict(v) for k, v in COPY.items()}
    rc, doc = read(plan=plan, copy_by_set=tmp_copy)
    build = next(b for b in doc["builds"] if b["id"] == "auto_post_sale")
    entry = next(s for s in build["bindings"]["sms_sets"] if s["set_id"] == "text_doors_open")
    entry["after_steps"] = {"doors_open_1": "email_welcome_access-e1"}
    campaign = wb.compile_launch_builds(doc)
    assert not any(r["id"] == "auto_post_sale" for r in campaign.refusals), campaign.refusals
    ids = [s.get("attributes", {}).get("copy_step_id") or s["id"]
           for s in unit(campaign, "auto_post_sale")[0]["templates"]]
    assert ids.index("doors_open_1") > ids.index("email_welcome_access-e1")
