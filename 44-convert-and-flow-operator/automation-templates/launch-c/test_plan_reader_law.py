"""launch-c plan reader law checks (U-skill44-02: S44-02, S44-07, S44-08, S44-28).

Synthetic-local only: no provider call, no send, no credential.
Run: python3 -m pytest 44-convert-and-flow-operator/automation-templates/launch-c/test_plan_reader_law.py -q
"""

import contextlib
import copy
import importlib.util
import inspect
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("plan_reader_law", HERE / "plan_reader.py")
plan_reader = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plan_reader)

CONTRACT_DIR = plan_reader._launch_contract()[1].parent
HAS_CALENDAR_LAW = (CONTRACT_DIR / "calendar_law.py").is_file()

ZONE = "America/New_York"
STANDARD = {
    "launch_at": "2026-11-03T12:00:00-05:00",
    "doors_open_at": "2026-11-03T09:00:00-05:00",
    "doors_close_at": "2026-11-10T23:59:00-05:00",
    "timezone": ZONE,
}
BLACK_FRIDAY = {
    "launch_at": "2026-11-27T00:00:00-05:00",
    "doors_open_at": "2026-11-27T00:00:00-05:00",
    "doors_close_at": "2026-12-01T00:00:00-05:00",
    "timezone": ZONE,
    "black_friday": {
        "teaser_at": "2026-11-20T09:00:00-05:00",
        "countdown_at": "2026-11-24T09:00:00-05:00",
        "cyber_monday_at": "2026-11-30T00:00:00-05:00",
        "last_call_at": "2026-11-30T20:00:00-05:00",
    },
}
LONG_AGO = datetime.fromisoformat("2026-10-01T00:00:00-04:00")


def at(text):
    return datetime.fromisoformat(text)


# Buildable template per family (Skill 49 TEMPLATE_BY_FAMILY; keys of _matcher/buildable-templates.json).
FAMILY_TEMPLATE = {
    "pre_launch": "launch-a/launch-a-prelaunch-window",
    "abandoned_checkout": "launch-b/abandoned-checkout-recovery",
    "post_sale": "launch-b/launch-post-sale-purchase",
    "win_back": "launch-c/launch-win-back-closed-no-purchase",
}


def automation(unit_id, family, waits, template=None):
    return {"id": unit_id, "family": family, "template": template or FAMILY_TEMPLATE[family],
            "build_rail": "skill44_engine", "draft_only": True,
            "trigger": {"type": "tag_added"}, "waits_for": waits}


def launch_plan(calendar=None, sequences=(("email_pre_launch", "pre_launch", 4),),
                automations=None):
    return {
        "schema_version": "1.0.0",
        "launch_id": "law-synthetic",
        "offer": {"name": "Synthetic", "price_usd": 1, "currency": "USD",
                  "payment_plans": False},
        "launch_calendar": copy.deepcopy(calendar or STANDARD),
        "a2p_ready": False,
        "conversation_ai": {"requested": False, "mode": "none"},
        "pages": [{"id": "page_landing", "kind": "landing",
                   "url": "https://example.com/landing", "waits_for": []}],
        "email_sequences": [
            {"id": seq_id, "kind": kind, "provider": "skill50", "email_count": count,
             "draft_only": True, "waits_for": []} for seq_id, kind, count in sequences],
        "text_sets": [],
        "automations": automations or [
            automation("auto_pre_launch", "pre_launch", [s[0] for s in sequences])],
    }


def build_plan(seq_id, count, wait_days=1):
    templates = []
    for index in range(count):
        templates.append({"id": "e%d" % index, "type": "email", "name": "Email %d" % index,
                          "attributes": {"subject": "s", "body": "<p>b</p>",
                                         "html": "<p>b</p>", "fromName": "Synthetic"}})
        if index < count - 1:
            templates.append({"id": "w%d" % index, "type": "wait", "name": "Wait",
                              "attributes": {"type": "time", "startAfter": {
                                  "type": "days", "value": wait_days, "when": "after"}}})
    return {"folder": "Synthetic Drafts",
            "_meta": {"sequence_id": seq_id, "draft_only": True, "deploy_mode": "draft-only"},
            seq_id: {"name": seq_id, "status": "draft", "templates": templates}}


def run(plan, builds=(), now=LONG_AGO, extra=()):
    """Run the reader CLI. Returns (rc, output document or None, stderr text)."""
    temp = Path(tempfile.mkdtemp())
    plan_path, out = temp / "plan.json", temp / "out.json"
    plan_path.write_text(json.dumps(plan))
    argv = ["--launch-plan", str(plan_path), "--out", str(out), "--now", now.isoformat()]
    for seq_id, count in builds:
        path = temp / ("build-%s.json" % seq_id)
        path.write_text(json.dumps(build_plan(seq_id, count)))
        argv += ["--build-plan", str(path)]
    argv += list(extra)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = plan_reader.main(argv)
    return rc, (json.loads(out.read_text()) if out.exists() else None), err.getvalue()


class BlackFridayTests(unittest.TestCase):
    def test_calendar_nodes_carry_all_four_black_friday_phases_in_time_order(self):
        rc, doc, _ = run(launch_plan(BLACK_FRIDAY))  # no build plan: blocked, calendar still compiled
        nodes = doc["builds"][0]["schedule"]["calendar_nodes"]
        phases = [n["phase"] for n in nodes]
        for phase in ("teaser", "countdown", "cyber_monday", "last_call"):
            self.assertIn(phase, phases)
        self.assertEqual(phases[0], "teaser")
        self.assertEqual(phases[-1], "doors_close")
        by_phase = {n["phase"]: n for n in nodes}
        for phase, text in (("teaser", "2026-11-20T09:00:00-05:00"),
                            ("countdown", "2026-11-24T09:00:00-05:00"),
                            ("cyber_monday", "2026-11-30T00:00:00-05:00"),
                            ("last_call", "2026-11-30T20:00:00-05:00")):
            self.assertEqual(at(by_phase[phase]["at"]), at(text))
            self.assertEqual(by_phase[phase]["kind"], "absolute")
        self.assertEqual(doc["calendar"]["black_friday"]["teaser_at"],
                         "2026-11-20T09:00:00-05:00")

    def test_plain_launch_keeps_its_three_calendar_nodes(self):
        _, doc, _ = run(launch_plan(STANDARD))
        self.assertEqual([n["phase"] for n in doc["builds"][0]["schedule"]["calendar_nodes"]],
                         ["doors_open", "launch", "doors_close"])

    def test_pre_launch_starts_at_the_teaser_not_packed_before_doors_open(self):
        rc, doc, _ = run(launch_plan(BLACK_FRIDAY, sequences=(("email_pre_launch", "pre_launch", 2),)),
                         builds=[("email_pre_launch", 2)])
        self.assertEqual(rc, 0)
        build = doc["builds"][0]
        nodes = build["schedule"]["nodes"]
        self.assertEqual([n["anchor"] for n in nodes], ["teaser_at"] * 2)
        self.assertEqual(at(nodes[0]["at"]), at("2026-11-20T09:00:00-05:00"))
        self.assertEqual(at(nodes[1]["at"]), at("2026-11-21T09:00:00-05:00"))

    def test_each_black_friday_kind_gets_its_own_absolute_send_point(self):
        kinds = (("email_teaser", "teaser", 1), ("email_countdown", "countdown", 1),
                 ("email_cyber_monday", "cyber_monday", 1), ("email_last_call", "last_call", 1))
        plan = launch_plan(BLACK_FRIDAY, sequences=kinds)
        # The shared contract enum does not list these kinds yet (it is not this unit's file);
        # prove the reader's own compile by stubbing the shared check only.
        original = plan_reader._shared_errors
        plan_reader._shared_errors = lambda _plan: []
        try:
            rc, doc, _ = run(plan, builds=[(k[0], k[2]) for k in kinds])
        finally:
            plan_reader._shared_errors = original
        self.assertEqual(rc, 0)
        sends = {}
        for node in doc["builds"][0]["schedule"]["nodes"]:
            sends.setdefault(node["phase"], []).append(node)
        for kind, anchor in (("teaser", "2026-11-20T09:00:00-05:00"),
                             ("countdown", "2026-11-24T09:00:00-05:00"),
                             ("cyber_monday", "2026-11-30T00:00:00-05:00"),
                             ("last_call", "2026-11-30T20:00:00-05:00")):
            self.assertEqual(sends[kind][0]["anchor"], kind + "_at")
            self.assertEqual(at(sends[kind][0]["at"]), at(anchor))
            self.assertEqual(sends[kind][0]["kind"], "absolute")
            self.assertEqual(sends[kind][0]["status"], "scheduled")

    def test_black_friday_kind_without_a_black_friday_calendar_is_refused(self):
        plan = launch_plan(STANDARD, sequences=(("email_last_call", "last_call", 1),))
        original = plan_reader._shared_errors
        plan_reader._shared_errors = lambda _plan: []
        try:
            rc, doc, err = run(plan)
        finally:
            plan_reader._shared_errors = original
        self.assertEqual(rc, 2)
        self.assertIsNone(doc)
        self.assertIn("CALENDAR-BLACK-FRIDAY", err)


class CalendarOrderTests(unittest.TestCase):
    def test_reader_keeps_no_private_calendar_order(self):
        self.assertNotIn("CALENDAR-PHASE-ORDER", inspect.getsource(plan_reader.read_calendar))
        # launch at the moment the doors open is lawful (shared law: doors_open <= launch)
        calendar = dict(STANDARD, launch_at=STANDARD["doors_open_at"])
        compiled, times = plan_reader.read_calendar(calendar)
        self.assertEqual(times["launch_at"], times["doors_open_at"])
        rc, _, _ = run(launch_plan(calendar), builds=[("email_pre_launch", 4)])
        self.assertEqual(rc, 0)

    @unittest.skipUnless(HAS_CALENDAR_LAW, "shared calendar_law.py (U-skill44-01) not on this base")
    def test_read_calendar_delegates_order_to_the_shared_law(self):
        with self.assertRaises(plan_reader.ReaderError) as caught:
            plan_reader.read_calendar(dict(STANDARD, launch_at="2026-11-03T08:00:00-05:00"))
        self.assertEqual(caught.exception.code, "CALENDAR-PHASE-ORDER")
        # a Black Friday-kind launch whose calendar lacks the black_friday block is refused too
        with self.assertRaises(plan_reader.ReaderError) as caught:
            plan_reader.read_calendar(dict(STANDARD), black_friday_required=True)
        self.assertEqual(caught.exception.code, "CALENDAR-PHASE-ORDER")
        # teaser == countdown is out of order under the Black Friday law
        calendar = copy.deepcopy(BLACK_FRIDAY)
        calendar["black_friday"]["countdown_at"] = calendar["black_friday"]["teaser_at"]
        with self.assertRaises(plan_reader.ReaderError) as caught:
            plan_reader.read_calendar(calendar)
        self.assertEqual(caught.exception.code, "CALENDAR-PHASE-ORDER")
        plan_reader.read_calendar(copy.deepcopy(BLACK_FRIDAY), black_friday_required=True)

    @unittest.skipUnless(HAS_CALENDAR_LAW, "shared calendar_law.py (U-skill44-01) not on this base")
    def test_shared_calendar_law_decides_order(self):
        calendar = dict(STANDARD, launch_at="2026-11-03T08:00:00-05:00")
        rc, doc, err = run(launch_plan(calendar))
        self.assertEqual(rc, 2)
        self.assertIsNone(doc)
        self.assertIn("LAUNCH-PLAN-CONTRACT", err)


class SharedValidatorFirstTests(unittest.TestCase):
    def test_plan_failing_the_shared_validator_is_refused_with_its_exact_text(self):
        plan = launch_plan()
        plan["conversation_ai"] = {"requested": True, "mode": "none"}
        plan["pages"][0]["waits_for"] = ["no_such_unit"]
        module, schema_path = plan_reader._launch_contract()
        errors = module.validate_plan(plan, module.load_json(schema_path))
        self.assertTrue(errors)
        rc, doc, err = run(plan)
        self.assertEqual(rc, 2)
        self.assertIsNone(doc)
        for error in errors:
            self.assertIn(error, err)

    def test_shared_validator_runs_before_the_readers_own_checks(self):
        plan = launch_plan()
        plan["conversation_ai"] = {"requested": True, "mode": "none"}
        plan["pages"][0]["api_key"] = "x"   # reader-only refusal (CREDENTIAL-IN-PLAN)
        rc, _, err = run(plan)
        self.assertEqual(rc, 2)
        self.assertIn("LAUNCH-PLAN-CONTRACT", err)
        self.assertNotIn("CREDENTIAL-IN-PLAN", err)

    def test_a_plan_the_shared_validator_accepts_is_not_refused_by_a_private_rule(self):
        # elevation.json is the contract's own fixture. Its template ids predate the buildable
        # manifest, so the only refusal is the buildability gate; mapped to the buildable
        # keys the reader takes it.
        fixture = CONTRACT_DIR / "fixtures" / "elevation.json"
        plan = json.loads(fixture.read_text())
        rc, doc, err = run(copy.deepcopy(plan))
        self.assertEqual((rc, doc), (2, None))
        self.assertIn("LAUNCH-PLAN-TEMPLATE-UNBUILDABLE", err)
        for item in plan["automations"]:
            item["template"] = FAMILY_TEMPLATE[item["family"]]
        rc, doc, _ = run(plan)
        self.assertEqual(rc, 4)   # parsed and compiled; blocked only for want of build plans
        self.assertEqual(doc["launch_id"], "elevation-2026-11")


class TemplateBuildabilityTests(unittest.TestCase):
    """S44-12: the reader refuses a template its own manifest cannot build."""

    def plan_with(self, template, **extra):
        plan = launch_plan()
        plan["automations"][0]["template"] = template
        plan["automations"][0].update(extra)
        return plan

    def test_template_outside_the_manifest_is_refused(self):
        rc, doc, err = run(self.plan_with("cart-open-cart-close-launch-sequence"))
        self.assertEqual((rc, doc), (2, None))
        self.assertIn("LAUNCH-PLAN-TEMPLATE-UNBUILDABLE", err)

    def test_new_without_an_approved_new_template_is_refused(self):
        for extra in ({}, {"new_template": {"owner_approved_reason": "  ", "compile_spec": {"a": 1}}},
                      {"new_template": {"owner_approved_reason": "owner said so"}}):
            rc, doc, err = run(self.plan_with("new", **extra))
            self.assertEqual((rc, doc), (2, None), extra)
            self.assertIn("LAUNCH-PLAN-TEMPLATE-UNBUILDABLE", err)

    def test_new_with_reason_and_compile_spec_passes_the_gate(self):
        rc, doc, _ = run(self.plan_with("new", new_template={
            "owner_approved_reason": "owner approved a small custom reminder",
            "compile_spec": {"build_graph": []}}))
        self.assertIsNotNone(doc)

    def test_manifest_keys_pass_and_a_missing_manifest_refuses_everything(self):
        rc, doc, _ = run(self.plan_with("launch-a/launch-a-prelaunch-window"))
        self.assertIsNotNone(doc)
        plan_reader._buildable_keys.cache_clear()
        original = plan_reader.Path
        try:
            class Gone(type(HERE)):
                def read_text(self, *args, **kwargs):
                    raise OSError("manifest missing")
            plan_reader.Path = Gone
            plan_reader._buildable_keys.cache_clear()
            self.assertEqual(plan_reader._buildable_keys(), frozenset())
        finally:
            plan_reader.Path = original
            plan_reader._buildable_keys.cache_clear()
        self.assertIn("launch-a/launch-a-prelaunch-window", plan_reader._buildable_keys())


class BlockedExitTests(unittest.TestCase):
    def assertSchemaValid(self, doc):
        plan_reader.validate_output(doc)  # raises ReaderError on any schema violation

    def test_blocked_build_exits_4_and_output_still_validates(self):
        rc, doc, err = run(launch_plan())   # no build plan bound
        self.assertEqual(rc, plan_reader.EXIT_BLOCKED)
        self.assertEqual(rc, 4)
        self.assertEqual(doc["builds"][0]["state"], "blocked")
        self.assertIn("BLOCKED", err)
        self.assertSchemaValid(doc)

    def test_ready_builds_exit_0(self):
        rc, doc, _ = run(launch_plan(), builds=[("email_pre_launch", 4)])
        self.assertEqual(rc, 0)
        self.assertEqual({b["state"] for b in doc["builds"]}, {"ready"})
        self.assertSchemaValid(doc)

    def test_no_builds_at_all_is_empty_and_exits_4(self):
        plan = launch_plan(automations=[])
        plan["automations"] = []
        rc, doc, _ = run(plan)
        self.assertEqual((rc, doc["builds"]), (4, []))
        self.assertSchemaValid(doc)

    def test_build_with_no_workflow_is_blocked_and_its_dependant_is_upstream_blocked(self):
        plan = launch_plan(
            sequences=(("email_pre_launch", "pre_launch", 4),),
            automations=[
                automation("auto_cart", "abandoned_checkout", ["page_landing"]),
                automation("auto_after_cart", "win_back", ["auto_cart"]),
            ])
        rc, doc, _ = run(plan)
        builds = {b["id"]: b for b in doc["builds"]}
        self.assertEqual(rc, 4)
        self.assertEqual(builds["auto_cart"]["state"], "blocked")
        self.assertIn("no_buildable_workflow", builds["auto_cart"]["blocked_by"])
        self.assertIn("upstream:auto_cart", builds["auto_after_cart"]["blocked_by"])
        self.assertFalse([b for b in doc["builds"] if b["state"] == "ready" and not b["workflows"]])

    def test_output_that_breaks_the_schema_is_refused_before_it_is_written(self):
        _, doc, _ = run(launch_plan(), builds=[("email_pre_launch", 4)])
        doc["builds"][0]["state"] = "maybe"
        with self.assertRaises(plan_reader.ReaderError) as caught:
            plan_reader.validate_output(doc)
        self.assertEqual(caught.exception.code, "OUTPUT-SCHEMA")


class LateStartTests(unittest.TestCase):
    OPEN = at("2026-11-03T09:00:00-05:00")

    def late(self, now, extra=()):
        # 4 pre-launch emails a day apart, last one 60 s before the doors open
        return run(launch_plan(), builds=[("email_pre_launch", 4)], now=now, extra=extra)

    def test_past_sends_are_dropped_and_the_build_stays_ready(self):
        now = self.OPEN - timedelta(days=2, hours=12)   # first email (open - 3 d - 60 s) is past
        rc, doc, _ = self.late(now)
        self.assertEqual(rc, 0)
        build = doc["builds"][0]
        self.assertEqual(build["state"], "ready", build["blocked_by"])
        self.assertEqual(build["blocked_by"], [])
        statuses = [n["status"] for n in build["schedule"]["nodes"]]
        self.assertEqual(statuses, ["suppressed", "scheduled", "scheduled", "scheduled"])
        self.assertEqual([(d["step_id"], d["reason"]) for d in build["dropped_sends"]],
                         [("e0", "PAST-TIME-SUPPRESSED")])
        self.assertEqual(build["suppressed"], build["dropped_sends"])
        plan_reader.validate_output(doc)

    def test_owner_acknowledgement_lists_the_dropped_sends_and_must_match(self):
        now = self.OPEN - timedelta(days=1, hours=12)   # emails 0 and 1 are past
        rc, doc, _ = self.late(now)
        ack = doc["owner_acknowledgement"]
        self.assertEqual(rc, 0)
        self.assertTrue(ack["required"])
        self.assertFalse(ack["acknowledged"])
        self.assertEqual([d["step_id"] for d in ack["dropped_sends"]], ["e0", "e1"])
        self.assertEqual({d["automation"] for d in ack["dropped_sends"]}, {"auto_pre_launch"})
        rc, doc, _ = self.late(now, extra=["--acknowledge-dropped-sends", ack["dropped_sends_hash"]])
        self.assertEqual(rc, 0)
        self.assertTrue(doc["owner_acknowledgement"]["acknowledged"])
        rc, doc, err = self.late(now, extra=["--acknowledge-dropped-sends", "0" * 64])
        self.assertEqual(rc, 2)
        self.assertIsNone(doc)
        self.assertIn("ACKNOWLEDGEMENT-MISMATCH", err)

    def test_on_time_start_needs_no_acknowledgement(self):
        _, doc, _ = self.late(LONG_AGO)
        self.assertEqual(doc["owner_acknowledgement"]["required"], False)
        self.assertEqual(doc["builds"][0]["dropped_sends"], [])

    def test_when_every_send_is_past_nothing_is_left_to_build(self):
        rc, doc, _ = self.late(self.OPEN)
        self.assertEqual(rc, 4)
        build = doc["builds"][0]
        self.assertEqual(build["state"], "blocked")
        self.assertIn("no_future_sends", build["blocked_by"])
        self.assertTrue(doc["owner_acknowledgement"]["required"])

    def test_a_send_that_cannot_land_before_doors_close_still_blocks(self):
        calendar = dict(STANDARD, doors_close_at="2026-11-03T09:30:00-05:00",
                        launch_at="2026-11-03T09:00:00-05:00")
        plan = launch_plan(calendar, sequences=(("email_main_launch", "main_launch", 2),),
                           automations=[automation("auto_main", "pre_launch", ["email_main_launch"])])
        rc, doc, _ = run(plan, builds=[("email_main_launch", 2)])  # 2nd email is 1 day after launch
        self.assertEqual(rc, 4)
        self.assertIn("schedule_suppressed:email_main_launch", doc["builds"][0]["blocked_by"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
