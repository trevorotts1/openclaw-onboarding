#!/usr/bin/env python3
"""Synthetic-local regression proofs for the launch-text pre-send gate.

No network, no provider, no live send: every case is a fixture or an
in-memory contact state.

    python3 test_sms_eligibility.py          # direct
    python3 -m unittest test_sms_eligibility # via unittest
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from sms_eligibility import (  # noqa: E402
    EXPECTED_CONDITIONS,
    MARKETING_CAP,
    category,
    count_segments,
    evaluate_send,
    export_category,
    main as cli_main,
    verify_saved_conditions,
    verify_saved_export,
)


def fixture(name: str) -> dict:
    return json.loads((HERE / "fixtures" / name).read_text(encoding="utf-8"))


def evaluate_fixture(name: str) -> tuple[dict, dict]:
    case = fixture(name)
    return case, evaluate_send(copy.deepcopy(case["send"]))


class ClassificationTests(unittest.TestCase):
    def test_marketing_and_operational_are_separate(self):
        for kind in ("doors_open", "last_call", "abandoned_checkout"):
            self.assertEqual(category(kind), "marketing")
        for kind in ("opt_in_confirmation", "keyword_opt_in",
                     "event_reminder", "access_link"):
            self.assertEqual(category(kind), "operational")

    def test_unknown_kind_is_refused_not_guessed(self):
        with self.assertRaises(ValueError):
            category("newsletter")


class FixtureRegressionTests(unittest.TestCase):
    def assertExpectation(self, case, result):
        expect = case["expect"]
        self.assertEqual(result["action"], expect["action"], result["reason"])
        self.assertEqual(result["category"], expect["category"])
        if "reason" in expect:
            self.assertEqual(result["reason"], expect["reason"])
        if "send_at" in expect:
            self.assertEqual(result["send_at"], expect["send_at"])
        if "encoding" in expect:
            self.assertEqual(result["encoding"], expect["encoding"])

    def test_held_to_next_window(self):
        case, result = evaluate_fixture("send_marketing_held.json")
        self.assertExpectation(case, result)
        self.assertEqual(result["send_at"], "2026-10-23T08:00:00")
        self.assertGreaterEqual(result["segments"], 1)
        self.assertAlmostEqual(
            result["cost_usd"], round(result["segments"] * 0.01, 6))

    def test_deadline_conflict_moves_earlier_never_later(self):
        case, result = evaluate_fixture("send_deadline_moved_earlier.json")
        self.assertExpectation(case, result)
        self.assertLess(result["send_at"], case["send"]["deadline"])

    def test_suppression_wins_after_build(self):
        case, result = evaluate_fixture("send_suppressed.json")
        self.assertExpectation(case, result)
        check = next(c for c in result["checks"] if c["rule"] == "not_suppressed")
        self.assertFalse(check["ok"])

    def test_aggregate_contact_cap_blocks_the_sixth_marketing_send(self):
        case, result = evaluate_fixture("send_cap_reached.json")
        self.assertExpectation(case, result)
        check = next(c for c in result["checks"]
                     if c["rule"] == "aggregate_contact_cap")
        self.assertFalse(check["ok"])
        self.assertIn(str(MARKETING_CAP), check["detail"])

    def test_operational_after_deadline_is_not_blocked(self):
        case, result = evaluate_fixture("send_operational_after_deadline.json")
        self.assertExpectation(case, result)
        check = next(c for c in result["checks"]
                     if c["rule"] == "aggregate_contact_cap")
        self.assertTrue(check["ok"])
        self.assertIn("operational", check["detail"])

    def test_ucs2_over_segment_ceiling_is_refused(self):
        case, result = evaluate_fixture("send_content_ucs2_over_cap.json")
        self.assertExpectation(case, result)
        self.assertGreater(result["segments"], 1)

    def test_http_and_shortener_links_are_refused(self):
        case, result = evaluate_fixture("send_link_refused.json")
        self.assertExpectation(case, result)
        self.assertIn("content", result["reason"])

    def test_event_reminder_outside_window_skips_rather_than_lies(self):
        case, result = evaluate_fixture("send_event_reminder_conflict.json")
        self.assertExpectation(case, result)


class SendTimeTests(unittest.TestCase):
    def base(self):
        return fixture("send_marketing_held.json")["send"]

    def test_08_00_is_allowed_and_21_00_is_not(self):
        send = self.base()
        send["anchor"] = "2026-10-22T06:00:00"
        send["send_at"] = "2026-10-22T08:00:00"
        send["now"] = "2026-10-22T08:00:00"
        self.assertEqual(evaluate_send(send)["action"], "send")
        send["send_at"] = "2026-10-22T21:00:00"
        send["now"] = "2026-10-22T12:00:00"
        held = evaluate_send(send)
        self.assertEqual(held["action"], "hold")
        self.assertEqual(held["send_at"], "2026-10-23T08:00:00")

    def test_past_due_never_sends_late(self):
        send = self.base()
        send["send_at"] = "2026-10-22T10:00:00"
        send["now"] = "2026-10-22T10:05:00"
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        self.assertEqual(result["reason"], "past_due")

    def test_marketing_deadline_passed_skips(self):
        send = self.base()
        send["send_at"] = "2026-10-22T09:00:00"
        send["now"] = "2026-10-22T09:00:00"
        send["deadline"] = "2026-10-22T08:30:00"
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        self.assertEqual(result["reason"], "failed: launch_deadline")


    def test_hold_candidate_before_anchor_skips(self):
        send = self.base()
        send["send_at"] = "2026-10-22T07:00:00"
        send["now"] = "2026-10-22T06:00:00"
        send["anchor"] = "2026-10-22T09:00:00"
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        self.assertEqual(result["reason"], "before_anchor")

    def test_unknown_timezone_blocks_never_crashes(self):
        send = self.base()
        send["send_at"] = "2026-10-22T10:00:00+00:00"
        send["now"] = "2026-10-22T10:00:00+00:00"
        send["timezone"] = "Bogus/Zone"
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        self.assertIn("quiet_hours", result["reason"])


class ConsentAndA2PTests(unittest.TestCase):
    def test_consent_is_read_immediately_before_send(self):
        send = fixture("send_marketing_held.json")["send"]
        send["send_at"] = "2026-10-22T10:00:00"
        send["now"] = "2026-10-22T10:00:00"
        send["contact"]["consent"] = "pending"
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        self.assertIn("consent", result["reason"])

    def test_opt_in_confirmation_may_run_on_pending_consent(self):
        send = {
            "kind": "opt_in_confirmation",
            "template": "{{first_name}}, you're in. {{business_name}} will text you "
                        "about {{offer_name}}. Msg frequency varies. Reply HELP for "
                        "help or STOP to opt out.",
            "variables": {"first_name": "Ada", "business_name": "Example Co",
                          "offer_name": "Signature Launch"},
            "send_at": "2026-10-22T10:00:00",
            "now": "2026-10-22T10:00:00",
            "a2p_ready": True,
            "contact": {"consent": "pending", "sms_subscribed": False,
                        "tags": ["text-optin-pending"], "suppression": [],
                        "marketing_sends": 0, "operational_sends": 0},
        }
        result = evaluate_send(send)
        self.assertEqual(result["action"], "send", result["reason"])

    def test_a2p_not_ready_blocks_every_set(self):
        send = fixture("send_marketing_held.json")["send"]
        send["a2p_ready"] = False
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        self.assertIn("a2p_ready", result["reason"])


class ContentTests(unittest.TestCase):
    def test_gsm7_segment_math(self):
        self.assertEqual(count_segments("a" * 160), ("gsm7", 1))
        self.assertEqual(count_segments("a" * 161), ("gsm7", 2))
        self.assertEqual(count_segments("{" + "a" * 159), ("gsm7", 2))
        self.assertEqual(count_segments("€" * 80), ("gsm7", 1))
        self.assertEqual(count_segments("€" * 81), ("gsm7", 2))

    def test_ucs2_segment_math(self):
        self.assertEqual(count_segments("a" * 70), ("gsm7", 1))
        self.assertEqual(count_segments("Ж" * 70), ("ucs2", 1))
        self.assertEqual(count_segments("Ж" * 71), ("ucs2", 2))

    def test_unknown_placeholder_is_refused(self):
        send = fixture("send_marketing_held.json")["send"]
        send["template"] = "{{first_name}}, {{mystery_token}} Reply STOP"
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        check = next(c for c in result["checks"] if c["rule"] == "content")
        self.assertIn("unknown placeholder", check["detail"])

    def test_copy_is_validated_after_merge(self):
        send = fixture("send_marketing_held.json")["send"]
        send["variables"]["first_name"] = "Zoë"  # UCS-2 but still 1 segment
        result = evaluate_send(send)
        self.assertEqual(result["action"], "hold")
        self.assertEqual(result["encoding"], "ucs2")


class NativeConditionTests(unittest.TestCase):
    def test_saved_native_conditions_pass(self):
        snapshot = fixture("native_export_ok.json")
        for cat in ("marketing", "operational"):
            result = verify_saved_conditions(snapshot, cat)
            self.assertTrue(result["ok"], result["missing"])

    def test_prose_alone_never_satisfies_a_rule(self):
        snapshot = fixture("native_export_prose_only.json")
        result = verify_saved_conditions(snapshot, "marketing")
        self.assertFalse(result["ok"])
        self.assertEqual(sorted(result["missing"]),
                         sorted(rule for rule, _ in EXPECTED_CONDITIONS["marketing"]))
        self.assertTrue(result["prose_only"])
        self.assertIn("suppression", result["prose_only"])

    def test_one_missing_native_condition_fails_the_export(self):
        snapshot = fixture("native_export_ok.json")
        snapshot["steps"] = [
            step for step in snapshot["steps"]
            if step.get("name") != "Aggregate contact cap?"
        ]
        result = verify_saved_conditions(snapshot, "marketing")
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing"], ["aggregate_contact_cap"])

    def test_disabled_condition_does_not_count(self):
        snapshot = fixture("native_export_ok.json")
        snapshot["steps"][0]["disabled"] = True
        result = verify_saved_conditions(snapshot, "marketing")
        self.assertIn("suppression", result["missing"])


def as_saved_export(snapshot: dict, with_sms: bool = True, keep_fixture_sms: bool = False) -> dict:
    """The snapshot fixture re-expressed the way a saved workflow export keeps it: conditions and
    prose under each template's `attributes` (S44-32, what qc-built-workflow.sh WF-25 reads)."""
    templates = []
    for step in snapshot["steps"]:
        if not keep_fixture_sms and "sms" in str(step.get("type", "")).lower():
            continue  # the fixture's own send steps; this helper adds exactly the SMS node a test asks for
        attrs = {"conditions": step.get("conditions") or []}
        for key in ("purpose", "copy", "message", "notes", "description"):
            if key in step:
                attrs[key] = step[key]
        templates.append({"id": "t%d" % len(templates), "type": step["type"], "name": step.get("name", ""),
                          "disabled": step.get("disabled", False), "attributes": attrs})
    if with_sms:
        templates.append({"id": "sms1", "type": "sms", "name": "Send",
                          "attributes": {"body": "x", "fromNumber": "+15555550100"}})
    return {"workflowData": {"templates": templates}}


class SavedExportTests(unittest.TestCase):
    """verify-saved: the per-build QC entry point over a saved workflow export."""

    def test_export_with_every_rule_saved_passes_and_is_marketing_by_default(self):
        result = verify_saved_export(as_saved_export(fixture("native_export_ok.json")))
        self.assertTrue(result["ok"], result["missing"])
        self.assertEqual((result["category"], result["sms_nodes"]), ("marketing", 1))

    def test_prose_only_export_fails_with_the_prose_reported(self):
        result = verify_saved_export(as_saved_export(fixture("native_export_prose_only.json"),
                                                     with_sms=False, keep_fixture_sms=True))
        self.assertFalse(result["ok"])
        self.assertIn("suppression", result["prose_only"])

    def test_workflow_without_sms_has_nothing_to_prove(self):
        result = verify_saved_export(as_saved_export(fixture("native_export_prose_only.json"), with_sms=False))
        self.assertTrue(result["ok"])
        self.assertEqual(result["sms_nodes"], 0)

    def test_operational_is_chosen_only_when_every_sms_node_says_so(self):
        export = as_saved_export(fixture("native_export_ok.json"))
        export["workflowData"]["templates"][-1]["attributes"]["category"] = "operational"
        self.assertEqual(verify_saved_export(export)["category"], "operational")
        export["workflowData"]["templates"].append({"id": "sms2", "type": "sms", "attributes": {}})
        self.assertEqual(verify_saved_export(export)["category"], "marketing")

    def test_export_with_no_step_list_is_unreadable_never_ok(self):
        result = verify_saved_export({"id": "x"})
        self.assertFalse(result["ok"])
        self.assertTrue(result["unreadable"])

    def test_cli_exit_codes(self):
        import io
        import tempfile
        from contextlib import redirect_stdout
        tmp = Path(tempfile.mkdtemp())
        good, bad = tmp / "good.json", tmp / "bad.json"
        good.write_text(json.dumps(as_saved_export(fixture("native_export_ok.json"))))
        bad.write_text(json.dumps(as_saved_export(fixture("native_export_prose_only.json"))))
        (tmp / "junk.json").write_text("{not json")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli_main(["verify-saved", "--export", str(good)]), 0)
            self.assertEqual(cli_main(["verify-saved", "--export", str(bad)]), 1)
            self.assertEqual(cli_main(["verify-saved", "--export", str(tmp / "junk.json")]), 2)
            self.assertEqual(cli_main(["verify-saved", "--export", str(tmp / "missing.json")]), 2)


GUARD = [{"type": "tag_present", "value": "sms-subscribed"}, {"type": "tag_absent", "value": "sms-opted-out"},
         {"type": "field_lt", "field": "contact_marketing_sends", "value": MARKETING_CAP},
         {"type": "time_window", "start": "08:00", "end": "21:00", "timezone": "recipient_local"},
         {"type": "deadline", "anchor": "doors_close_at"}]


def _guard_step(**over):
    step = {"id": "g1", "type": "filter", "attributes": {"conditions": GUARD}}
    step.update(over)
    return step


def _sms_step(**over):
    step = {"id": "s1", "type": "sms", "attributes": {"body": "x"}}
    step.update(over)
    return step


class SavedExportBranchTests(unittest.TestCase):
    """Every branch of the export reader: where the steps live, what counts as SMS, what counts as a guard."""

    def test_an_export_that_is_not_an_object_is_unreadable(self):
        for bad in ([], [1], "text", 5, None, True):
            result = verify_saved_export(bad)
            self.assertEqual(result, {"ok": False, "unreadable": True, "category": None, "sms_nodes": 0,
                                      "missing": ["workflow.steps"], "prose_only": [], "found": {}}, repr(bad))

    def test_the_steps_are_found_under_the_export_data_or_workflow_holder(self):
        steps = [_guard_step(), _sms_step()]
        for export in ({"workflowData": {"templates": steps}},
                       {"data": {"workflowData": {"templates": steps}}},
                       {"workflow": {"workflowData": {"templates": steps}}},
                       {"steps": steps}, {"actions": steps}, {"nodes": steps}, {"templates": steps},
                       {"data": {"steps": steps}}, {"workflow": {"nodes": steps}}):
            result = verify_saved_export(export)
            self.assertFalse(result["unreadable"], export)
            self.assertEqual((result["ok"], result["sms_nodes"]), (True, 1), export)

    def test_a_holder_that_is_not_an_object_is_skipped_for_the_next_one(self):
        steps = [_guard_step(), _sms_step()]
        for export in ({"data": "junk", "workflow": {"steps": steps}}, {"data": [1], "steps": steps}):
            self.assertEqual(verify_saved_export(export)["sms_nodes"], 1, export)
        for export in ({"data": "junk", "workflow": 3}, {"data": {}, "workflow": {}}, {"steps": "nope"}, {"steps": {}}):
            self.assertTrue(verify_saved_export(export)["unreadable"], export)

    def test_workflow_data_templates_win_over_the_other_step_keys(self):
        export = {"workflowData": {"templates": [_guard_step(), _sms_step()]}, "steps": [_sms_step(), _sms_step()]}
        self.assertEqual(verify_saved_export(export)["sms_nodes"], 1)

    def test_a_workflow_data_without_a_templates_list_falls_back_to_the_step_keys(self):
        steps = [_guard_step(), _sms_step()]
        for wd in ("junk", {"templates": "junk"}, {}, None):
            result = verify_saved_export({"workflowData": wd, "steps": steps})
            self.assertEqual(result["sms_nodes"], 1, wd)
        self.assertTrue(verify_saved_export({"workflowData": {"templates": "junk"}})["unreadable"])

    def test_the_first_step_key_that_holds_a_list_is_used_in_order(self):
        export = {"steps": "junk", "actions": [_guard_step(), _sms_step()], "nodes": [_sms_step(), _sms_step()]}
        self.assertEqual(verify_saved_export(export)["sms_nodes"], 1)

    def test_what_counts_as_an_sms_step(self):
        for kind in ("sms", "SMS", "send_sms", "Sms Message", "sms_step"):
            export = {"steps": [_guard_step(), _sms_step(type=kind)]}
            self.assertEqual(verify_saved_export(export)["sms_nodes"], 1, kind)
        for kind in ("email", "wait", "", None, 7):
            export = {"steps": [_guard_step(), _sms_step(type=kind)]}
            self.assertEqual(verify_saved_export(export)["sms_nodes"], 0, kind)
        self.assertEqual(verify_saved_export({"steps": ["sms", 4, None, _sms_step()]})["sms_nodes"], 1)

    def test_a_step_that_is_not_an_object_never_counts_and_never_breaks_the_read(self):
        export = {"steps": ["junk", None, 3, ["sms"], _guard_step(), _sms_step()]}
        result = verify_saved_export(export)
        self.assertEqual((result["ok"], result["sms_nodes"], result["unreadable"]), (True, 1, False))

    def test_guard_conditions_are_read_from_the_step_or_from_its_attributes(self):
        at_step = {"id": "g1", "type": "filter", "conditions": GUARD}
        at_attrs = _guard_step()
        for guard in (at_step, at_attrs):
            result = verify_saved_export({"steps": [guard, _sms_step()]})
            self.assertTrue(result["ok"], guard)
        both = {"id": "g1", "type": "filter", "conditions": [], "attributes": {"conditions": GUARD}}
        self.assertFalse(verify_saved_export({"steps": [both, _sms_step()]})["ok"])   # the step's own list wins
        for bad in ("junk", {"a": 1}, None, 7):
            step = {"id": "g1", "type": "filter", "conditions": bad, "attributes": {"conditions": bad}}
            self.assertFalse(verify_saved_export({"steps": [step, _sms_step()]})["ok"], repr(bad))

    def test_a_disabled_guard_proves_nothing_whichever_place_says_so(self):
        for guard in (_guard_step(disabled=True),
                      _guard_step(attributes={"conditions": GUARD, "disabled": True})):
            self.assertFalse(verify_saved_export({"steps": [guard, _sms_step()]})["ok"], guard)
        for guard in (_guard_step(disabled=False), _guard_step(disabled="true"),
                      _guard_step(attributes={"conditions": GUARD, "disabled": False})):
            self.assertTrue(verify_saved_export({"steps": [guard, _sms_step()]})["ok"], guard)

    def test_prose_is_read_from_the_step_or_its_attributes_and_never_satisfies_a_rule(self):
        for step in (_sms_step(purpose="respect STOP and sms-opted-out"),
                     _sms_step(attributes={"body": "x", "purpose": "respect STOP and sms-opted-out"})):
            result = verify_saved_export({"steps": [step]})
            self.assertFalse(result["ok"])
            self.assertIn("suppression", result["prose_only"])
        step = _sms_step(purpose="nothing to see", attributes={"body": "x", "purpose": "respect STOP"})
        self.assertNotIn("suppression", verify_saved_export({"steps": [step]})["prose_only"])   # the step's own text wins
        step = _sms_step(purpose=7, attributes={"body": "x", "purpose": "respect STOP"})
        self.assertIn("suppression", verify_saved_export({"steps": [step]})["prose_only"])      # 7 is no text: attributes used

    def test_the_category_is_operational_only_when_every_sms_step_declares_it(self):
        op_attr = _sms_step(attributes={"body": "x", "category": "operational"})
        op_step = {"id": "s2", "type": "sms", "category": "operational"}
        kind_attr = _sms_step(attributes={"body": "x", "kind": "access_link"})
        kind_step = {"id": "s3", "type": "sms", "kind": "event_reminder"}
        for sms in (op_attr, op_step, kind_attr, kind_step):
            self.assertEqual(verify_saved_export({"steps": [sms]})["category"], "operational", sms)
        for sms in (_sms_step(attributes={"body": "x", "category": "marketing"}),
                    _sms_step(attributes={"body": "x", "kind": "doors_open"}), _sms_step()):
            self.assertEqual(verify_saved_export({"steps": [sms]})["category"], "marketing", sms)
        mixed = {"steps": [op_attr, _sms_step()]}
        self.assertEqual(verify_saved_export(mixed)["category"], "marketing")
        self.assertEqual(verify_saved_export({"steps": [_sms_step(attributes="junk")]})["category"], "marketing")

    def test_export_category_of_no_sms_steps_is_the_stricter_marketing_set(self):
        self.assertEqual(export_category([]), "marketing")
        self.assertEqual(export_category([_sms_step(attributes={"category": "operational"})]), "operational")

    def test_an_explicit_category_overrides_the_automatic_one(self):
        steps = [{"id": "g", "type": "filter", "attributes": {"conditions": [GUARD[1], GUARD[3]]}}, _sms_step()]
        self.assertFalse(verify_saved_export({"steps": steps})["ok"])                    # auto: marketing needs more
        result = verify_saved_export({"steps": steps}, "operational")
        self.assertEqual((result["ok"], result["category"], result["sms_nodes"]), (True, "operational", 1))
        self.assertEqual(verify_saved_export({"steps": steps}, "marketing")["category"], "marketing")

    def test_no_sms_step_is_ok_with_the_full_result_shape(self):
        self.assertEqual(verify_saved_export({"steps": [_guard_step()]}),
                         {"ok": True, "unreadable": False, "category": None, "sms_nodes": 0,
                          "missing": [], "prose_only": [], "found": {}})

    def test_cli_prints_the_report_and_honours_category_and_names_the_read_error(self):
        import io
        import tempfile
        from contextlib import redirect_stdout
        tmp = Path(tempfile.mkdtemp())
        steps = [{"id": "g", "type": "filter", "attributes": {"conditions": [GUARD[1], GUARD[3]]}}, _sms_step()]
        (tmp / "e.json").write_text(json.dumps({"steps": steps}))
        (tmp / "junk.json").write_text("{not json")
        def run(*argv):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli_main(["verify-saved", *argv])
            if rc != 2:   # a verified report is printed with sorted keys
                self.assertEqual(buf.getvalue(), json.dumps(json.loads(buf.getvalue()), sort_keys=True) + "\n")
            return rc, json.loads(buf.getvalue())
        rc, report = run("--export", str(tmp / "e.json"))
        self.assertEqual((rc, report["ok"], report["category"]), (1, False, "marketing"))
        rc, report = run("--export", str(tmp / "e.json"), "--category", "operational")
        self.assertEqual((rc, report["ok"], report["category"], report["sms_nodes"]), (0, True, "operational", 1))
        rc, report = run("--export", str(tmp / "junk.json"))
        self.assertEqual((rc, report), (2, {"ok": False, "unreadable": True, "error": "JSONDecodeError"}))
        rc, report = run("--export", str(tmp / "absent.json"))
        self.assertEqual((rc, report["error"]), (2, "FileNotFoundError"))
        (tmp / "list.json").write_text("[]")
        rc, report = run("--export", str(tmp / "list.json"))
        self.assertEqual((rc, report["unreadable"]), (2, True))
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as caught:
            import contextlib
            with contextlib.redirect_stderr(io.StringIO()):
                cli_main(["verify-saved", "--export", str(tmp / "e.json"), "--category", "nonsense"])
        self.assertEqual(caught.exception.code, 2)
        with self.assertRaises(SystemExit) as caught:
            import contextlib
            with contextlib.redirect_stderr(io.StringIO()):
                cli_main(["verify-saved"])
        self.assertEqual(caught.exception.code, 2)
        with self.assertRaises(SystemExit) as caught:
            import contextlib
            with contextlib.redirect_stderr(io.StringIO()):
                cli_main([])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
