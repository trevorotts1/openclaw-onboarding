"""Issue 96 (ruling X-96-1): an upsell/downsell follow-up stops on a purchase of the offer
it FOLLOWS (purchased-<offer_id>), never on the launch-wide buyer tag, which the main-offer
buyer already carries.  pre_launch and main_launch still stop on any verified launch purchase.

Run: python3 -m pytest 44-convert-and-flow-operator/tools/engine/tests/test_follow_up_purchase_gate.py -q
"""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import test_launch_step_compiler as base  # noqa: E402
from cli_anything.gohighlevel.utils import launch_step_compiler as lsc  # noqa: E402
from cli_anything.gohighlevel.utils import workflow_builder as wb  # noqa: E402

plan_reader = base.plan_reader
LAUNCH_TAG = lsc.purchase_tag("bf-test")
FOLLOWED = "off-up1"
FOLLOWED_TAG = "purchased-%s" % FOLLOWED
MAIN_BUYER = {LAUNCH_TAG, "purchased-off-main"}
FOLLOWED_BUYER = MAIN_BUYER | {FOLLOWED_TAG}

FOLLOW_STOP = {"rule": "stop_on_verified_purchase", "purchase_of": "followed_offer",
               "scope": "this_campaign_only"}
FOLLOW_LIFECYCLE = {
    "stop_rules": [FOLLOW_STOP, {"rule": "stop_on_unsubscribe", "scope": "this_campaign_only"}],
    "suppression_rules": plan_reader.DEFAULT_LIFECYCLE["suppression_rules"],
}


def _doc(follow_lifecycle=FOLLOW_LIFECYCLE, followed=FOLLOWED):
    unit = lambda uid, fam, tpl, wait: {  # noqa: E731
        "id": uid, "family": fam, "template": tpl, "build_rail": "skill44_engine",
        "draft_only": True, "trigger": {"type": "tag_added"}, "waits_for": [wait]}
    seq = lambda sid, kind, n: {  # noqa: E731
        "id": sid, "kind": kind, "provider": "skill50", "email_count": n,
        "draft_only": True, "waits_for": ["page_landing"] if kind != "welcome_access" else []}
    follow = unit("auto_upsell_branch", "upsell_downsell", "launch-b/upsell-downsell-branch",
                  "email_upsell_1")
    if followed is not None:
        follow["followed_offer_id"] = followed
    plan = {
        "schema_version": "1.0.0", "launch_id": "bf-test",
        "offer": {"name": "Synthetic", "price_usd": 1, "currency": "USD", "payment_plans": False},
        "a2p_ready": False, "conversation_ai": {"requested": False, "mode": "none"},
        "launch_calendar": {"launch_at": "2026-11-27T12:00:00-05:00",
                            "doors_open_at": "2026-11-27T09:00:00-05:00",
                            "doors_close_at": "2026-12-01T23:59:00-05:00",
                            "timezone": "America/New_York"},
        "pages": [{"id": "page_landing", "kind": "landing", "url": "https://example.com/l",
                   "waits_for": []}],
        "email_sequences": [seq("email_pre_launch", "pre_launch", 5),
                            seq("email_main_launch", "main_launch", 5),
                            seq("email_upsell_1", "upsell_followup", 2)],
        "text_sets": [],
        "automations": [
            unit("auto_pre_launch", "pre_launch", "launch-a/launch-a-prelaunch-window",
                 "email_pre_launch"),
            unit("auto_main_launch", "pre_launch", "launch-a/launch-a-prelaunch-window",
                 "email_main_launch"),
            follow],
    }
    parsed = plan_reader.read_launch_plan(plan)
    plans = {"email_pre_launch": base._build_plan("email_pre_launch", 5, "launch:pre",
                                                  base.AUTHORED_LIFECYCLE),
             "email_main_launch": base._build_plan("email_main_launch", 5, "launch:main",
                                                   base.AUTHORED_LIFECYCLE),
             "email_upsell_1": base._build_plan("email_upsell_1", 2, "launch:up1",
                                                follow_lifecycle)}
    bound = {k: (k, v, plan_reader.read_build_plan(v, k)) for k, v in plans.items()}
    return plan_reader.build_document("plan", parsed, bound, [], [], now=base.NOW)


def _steps(build_id, doc=None):
    """Compile through the production path (workflow_builder -> compile_installable)."""
    build = copy.deepcopy(base.build_of(doc or _doc(), build_id))
    compiled = wb.compile_automation_build(build, purchase_tag_set=True)
    return next(iter(compiled.values()))["templates"]


def _sends_reached(steps, tags):
    """Walk the compiled graph for a contact holding ``tags``; the emails it receives."""
    by_id = {s["id"]: s for s in steps}
    pointed = {s.get("next") for s in steps} | {v for s in steps
                                                for v in (s.get("branches") or {}).values()}
    cur = next(s for s in steps if s["id"] not in pointed)
    sent = []
    while cur is not None:
        if cur["type"] == "email":
            sent.append(cur["id"])
        if cur["type"] == "if_else" and cur.get("branches"):
            has = any(c.get("value") in tags for c in cur["attributes"]["conditions"])
            nxt = cur["branches"]["true" if has else "false"]
        else:
            nxt = cur.get("next")
        cur = by_id.get(nxt)
    return sent


class FollowUpGate(unittest.TestCase):
    def test_main_offer_buyer_keeps_receiving_the_upsell_follow_up(self):
        self.assertEqual(len(_sends_reached(_steps("auto_upsell_branch"), MAIN_BUYER)), 2)

    def test_buyer_of_the_followed_offer_stops(self):
        steps = _steps("auto_upsell_branch")
        self.assertEqual(len(_sends_reached(steps, set())), 2)
        self.assertEqual(_sends_reached(steps, FOLLOWED_BUYER), [])

    def test_gate_reads_the_followed_offer_tag_not_the_launch_tag(self):
        steps = _steps("auto_upsell_branch")
        gates = [s for s in steps if s["id"].endswith("-purchase-gate")]
        goals = [s for s in steps if s["type"] == "workflow_goal" and s["attributes"].get("goal") == "purchased"]
        self.assertEqual(len(gates), 2)
        self.assertEqual({g["attributes"]["conditions"][0]["value"] for g in gates}, {FOLLOWED_TAG})
        self.assertEqual({g["attributes"]["tag"] for g in goals}, {FOLLOWED_TAG})

    def test_pre_launch_and_main_launch_still_stop_on_any_verified_launch_purchase(self):
        for build_id in ("auto_pre_launch", "auto_main_launch"):
            steps = _steps(build_id)
            self.assertEqual(len(_sends_reached(steps, set())), 5, build_id)
            self.assertEqual(_sends_reached(steps, {LAUNCH_TAG}), [], build_id)
            self.assertEqual(_sends_reached(steps, {FOLLOWED_TAG}), _sends_reached(steps, set()))

    def test_document_compiler_gate_tag_is_the_followed_offer_tag(self):
        build = base.build_of(_doc(), "auto_upsell_branch")
        result = lsc.compile_build(build, bindings=dict(base.BINDINGS, slot="upsell_1",
                                                        offer_id=FOLLOWED),
                                   purchase_tag_set=True)
        self.assertEqual(result["status"], "ok", result["blocked_by"])
        self.assertEqual(result["workflows"]["auto_upsell_branch__flow"]["purchase_tag"],
                         FOLLOWED_TAG)
        pre = lsc.compile_build(base.build_of(_doc(), "auto_pre_launch"),
                                bindings=base.BINDINGS, purchase_tag_set=True)
        self.assertEqual(pre["workflows"]["auto_pre_launch__flow"]["purchase_tag"], LAUNCH_TAG)

    def test_follow_up_stop_rule_without_purchase_of_is_refused(self):
        lifecycle = copy.deepcopy(FOLLOW_LIFECYCLE)
        del lifecycle["stop_rules"][0]["purchase_of"]
        doc = _doc(lifecycle)
        build = base.build_of(doc, "auto_upsell_branch")
        self.assertEqual(build["state"], "blocked")  # the reader refuses it
        self.assertTrue(any("stop_on_verified_purchase.purchase_of" in b
                            for b in build["blocked_by"]), build["blocked_by"])
        # the compiler refuses it on its own too, even for a reader-ready build
        ready = copy.deepcopy(build)
        ready.update(state="ready", blocked_by=[])
        result = lsc.compile_build(ready, bindings=base.BINDINGS, purchase_tag_set=True)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any("stop_on_verified_purchase.purchase_of" in b
                            for b in result["blocked_by"]), result["blocked_by"])
        self.assertEqual(result["workflows"], {})

    def test_reader_refuses_a_blank_or_whitespace_purchase_of(self):
        for blank in ("", "  ", "\t\n"):
            lifecycle = copy.deepcopy(FOLLOW_LIFECYCLE)
            lifecycle["stop_rules"][0]["purchase_of"] = blank
            build = base.build_of(_doc(lifecycle), "auto_upsell_branch")
            self.assertEqual(build["state"], "blocked", repr(blank))
            self.assertTrue(any("stop_on_verified_purchase.purchase_of" in b
                                for b in build["blocked_by"]), (blank, build["blocked_by"]))
            self.assertEqual(plan_reader._compile_guard_issues(lifecycle, "upsell_followup"),
                             ["stop_on_verified_purchase.purchase_of"], repr(blank))

    def test_workflow_builder_refuses_a_follow_up_stop_rule_without_purchase_of(self):
        lifecycle = copy.deepcopy(FOLLOW_LIFECYCLE)
        del lifecycle["stop_rules"][0]["purchase_of"]
        build = copy.deepcopy(base.build_of(_doc(), "auto_upsell_branch"))
        build["lifecycle"] = lifecycle
        with self.assertRaises(wb.WorkflowCompileError) as raised:
            wb.compile_automation_build(build, purchase_tag_set=True)
        self.assertEqual(raised.exception.code, "MISSING-GUARDS")
        self.assertIn("purchase_of", str(raised.exception))
        # and the same build with purchase_of compiles, gated on the followed-offer tag
        ok = wb.compile_automation_build(copy.deepcopy(base.build_of(_doc(), "auto_upsell_branch")),
                                         purchase_tag_set=True)
        steps = next(iter(ok.values()))["templates"]
        self.assertEqual({s["attributes"]["purchase_tag"] for s in steps
                          if s["id"].endswith("-purchase-gate")}, {FOLLOWED_TAG})

    def test_follow_up_without_a_declared_followed_offer_is_blocked(self):
        doc = _doc(followed=None)
        result = lsc.compile_build(
            dict(base.build_of(doc, "auto_upsell_branch"), state="ready", blocked_by=[]),
            bindings=base.BINDINGS, purchase_tag_set=True)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("followed_offer_unset:auto_upsell_branch", result["blocked_by"])
        with self.assertRaises(wb.WorkflowCompileError) as raised:
            wb.compile_automation_build(base.build_of(doc, "auto_upsell_branch"),
                                        purchase_tag_set=True)
        self.assertIn("followed_offer_unset", str(raised.exception))

    def test_compiler_blocks_an_unusable_followed_offer_id(self):
        for bad in ("bad offer", "", "-x", 7):
            build = dict(base.build_of(_doc(), "auto_upsell_branch"), followed_offer_id=bad)
            result = lsc.compile_build(build, bindings=base.BINDINGS, purchase_tag_set=True)
            self.assertIn("followed_offer_unset:auto_upsell_branch", result["blocked_by"], bad)

    def test_a_compiled_follow_up_without_purchase_of_fails_contract_validation(self):
        build = copy.deepcopy(base.build_of(_doc(), "auto_upsell_branch"))
        campaign = wb.compile_automation_build(build, purchase_tag_set=True)
        self.assertEqual(wb._contract_errors(campaign), [])
        wf = next(iter(campaign.values()))
        self.assertEqual(wf["source_family"], "upsell_downsell")
        del wf["lifecycle"]["stop_rules"][0]["purchase_of"]
        errors = wb._contract_errors(campaign)
        self.assertTrue(any("stop_on_verified_purchase.purchase_of" in e for e in errors), errors)

    def test_a_main_launch_stop_rule_needs_no_purchase_of(self):
        self.assertEqual(wb._missing_guards(plan_reader.DEFAULT_LIFECYCLE, promotional=True), [])
        self.assertEqual(
            wb._missing_guards(plan_reader.DEFAULT_LIFECYCLE, promotional=True, follow_up=True),
            ["stop_on_verified_purchase.purchase_of"])
        self.assertEqual(plan_reader._compile_guard_issues(plan_reader.DEFAULT_LIFECYCLE,
                                                           "main_launch"), [])
        self.assertEqual(plan_reader._compile_guard_issues(plan_reader.DEFAULT_LIFECYCLE,
                                                           "downsell_followup"),
                         ["stop_on_verified_purchase.purchase_of"])

    def test_every_stop_rule_must_name_its_purchase_and_blank_does_not_count(self):
        both = {"stop_rules": [FOLLOW_STOP, {"rule": "stop_on_verified_purchase",
                                             "scope": "this_campaign_only"}]}
        blank = {"stop_rules": [dict(FOLLOW_STOP, purchase_of="  ")]}
        self.assertFalse(lsc.missing_purchase_of({"stop_rules": [FOLLOW_STOP]}))
        self.assertTrue(lsc.missing_purchase_of(both))
        self.assertTrue(lsc.missing_purchase_of(blank))
        self.assertFalse(lsc.missing_purchase_of({"stop_rules": [
            {"rule": "stop_on_unsubscribe", "scope": "this_campaign_only"}]}))

    def test_document_compiler_gate_node_reads_the_followed_offer_tag(self):
        # a follow-up whose resolved template does carry sends gets the followed-offer gate
        build = dict(base.build_of(_doc(), "auto_pre_launch"), family="upsell_downsell",
                     lifecycle=FOLLOW_LIFECYCLE, followed_offer_id=FOLLOWED)
        result = lsc.compile_build(build, bindings=base.BINDINGS, purchase_tag_set=True)
        self.assertEqual(result["status"], "ok", result["blocked_by"])
        steps = result["workflows"]["auto_pre_launch__flow"]["templates"]
        gates = [s for s in steps if s["id"].endswith("-purchase-gate")]
        self.assertTrue(gates)
        self.assertEqual({g["attributes"]["purchase_tag"] for g in gates}, {FOLLOWED_TAG})

    def test_installable_without_a_followed_offer_builds_no_gate_and_names_the_tag_when_unset(self):
        build = copy.deepcopy(dict(base.build_of(_doc(followed=None), "auto_upsell_branch")))
        workflow = build["workflows"][0]
        blocked = lsc.compile_installable(workflow, build, promotional=True,
                                          purchase_tag_set=True)
        self.assertIn("followed_offer_unset:auto_upsell_branch", blocked["blocked_by"])
        self.assertFalse([s for s in blocked["steps"] if s["id"].endswith("-purchase-gate")])
        # not promotional: nothing to gate, nothing to refuse
        quiet = lsc.compile_installable(workflow, build, promotional=False, purchase_tag_set=True)
        self.assertNotIn("followed_offer_unset:auto_upsell_branch", quiet["blocked_by"])
        # gate not yet installable: the note names the followed-offer tag, not the launch tag
        build["followed_offer_id"] = FOLLOWED
        unset = lsc.compile_installable(workflow, build, promotional=True, purchase_tag_set=False)
        self.assertIn("purchase_gate_unset:%s" % FOLLOWED_TAG, unset["notes"])

    def test_reader_carries_the_followed_offer_and_rejects_a_bad_one(self):
        self.assertEqual(base.build_of(_doc(), "auto_upsell_branch")["followed_offer_id"], FOLLOWED)
        self.assertIsNone(base.build_of(_doc(), "auto_pre_launch")["followed_offer_id"])
        for bad in ("bad offer", 7):
            with self.assertRaises(plan_reader.ReaderError, msg=repr(bad)):
                _doc(followed=bad)

    def test_follow_up_kinds_match_the_compiler_family(self):
        self.assertEqual(plan_reader.FOLLOW_UP_KINDS, {"upsell_followup", "downsell_followup"})
        self.assertIn(lsc.FOLLOW_UP_FAMILY, lsc.PROMO_FAMILIES)


# ---- end to end: a Skill 49 launch plan -> Skill 44 --------------------------------------
ROOT = HERE.parents[4]
REGISTRY = {f["kind"]: f["lifecycle"] for f in json.loads(
    (ROOT / "50-email-engine" / "profiles" / "launch-email-families.json")
    .read_text(encoding="utf-8"))["families"]}
# Skill 49 takes each sequence's length from this registry (issue 58), so the end-to-end checks below expect
# exactly the registry's email_count for the follow-up unit's own sequence rather than a number typed here.
EMAIL_COUNT = {f["kind"]: f["email_count"] for f in json.loads(
    (ROOT / "50-email-engine" / "profiles" / "launch-email-families.json")
    .read_text(encoding="utf-8"))["families"]}
FOLLOW_KIND = {"auto_upsell_1": "upsell_followup", "auto_downsell_1": "downsell_followup"}
OFFERS = {"main": "off-main", "upsell_1": "off-up1", "downsell_1": "off-down1"}
ANSWERS_49 = {
    "launch.launch_at": "2026-11-03T12:00:00-05:00",
    "launch.doors_open_at": "2026-11-03T09:00:00-05:00",
    "launch.doors_close_at": "2026-11-10T23:59:00-05:00",
    "launch.timezone": "America/New_York", "launch.channels": ["email"],
    "launch.a2p_ready": False, "launch.conversation_ai": False,
    "launch.landing_url": "https://example.com/landing",
    "launch.sales_page_url": "https://example.com/sales",
    "launch.checkout_url": "https://example.com/order",
    "launch.thank_you_url": "https://example.com/thanks",
}


def _launch_plan_49(offers=OFFERS):
    scripts = ROOT / "49-signature-funnel" / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        spec = importlib.util.spec_from_file_location("launch_plan_49", scripts / "launch_plan.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(scripts))
    launch = {"launch_id": "bf-test", "journey_mode": "single_simple",
              "extras": {"upsell_1": True, "downsell_1": True, "upsell_2": False},
              "offers": [dict({"slot": slot, "display_name": slot,
                               "prices": [{"amount_minor": 1000, "currency": "USD"}]},
                              **({"offer_id": offer_id} if offer_id else {}))
                         for slot, offer_id in offers.items()]}
    result = module.build_launch_plan(launch, ANSWERS_49)
    assert result["state"] == "ready", result["missing"]
    return result["plan"]


def _skill_44_document(plan):
    """The plan through Skill 44's reader, every email bound to its Skill 50 registry lifecycle."""
    bound = {}
    for seq in plan["email_sequences"]:
        built = base._build_plan(seq["id"], seq["email_count"], "launch:" + seq["id"],
                                 REGISTRY[seq["kind"]])
        bound[seq["id"]] = (seq["id"], built, plan_reader.read_build_plan(built, seq["id"]))
    return plan_reader.build_document("plan", plan_reader.read_launch_plan(plan), bound, [], [],
                                      now=base.NOW)


class Skill49PlanToSkill44(unittest.TestCase):
    def test_plan_emits_one_follow_up_unit_per_followed_offer(self):
        plan = _launch_plan_49()
        units = [a for a in plan["automations"] if a["family"] == "upsell_downsell"]
        self.assertEqual([(u["id"], u["followed_offer_id"], u["waits_for"]) for u in units],
                         [("auto_upsell_1", "off-up1", ["email_upsell_1"]),
                          ("auto_downsell_1", "off-down1", ["email_downsell_1"])])
        self.assertEqual([a["id"] for a in plan["automations"] if "followed_offer_id" in a],
                         ["auto_upsell_1", "auto_downsell_1"])
        self.assertEqual({(u["template"], u["trigger"]["type"], u["build_rail"], u["draft_only"])
                          for u in units},
                         {("launch-b/upsell-downsell-branch", "upsell_decision",
                           "skill44_engine", True)})

    def test_an_offer_without_a_usable_id_leaves_the_unit_undeclared_and_skill_44_blocks_it(self):
        for unusable in (None, "", "   ", 7):
            plan = _launch_plan_49(dict(OFFERS, upsell_1=unusable))
            unit = next(a for a in plan["automations"] if a["id"] == "auto_upsell_1")
            self.assertNotIn("followed_offer_id", unit, repr(unusable))
            build = base.build_of(_skill_44_document(plan), "auto_upsell_1")
            result = lsc.compile_build(dict(build, state="ready", blocked_by=[]),
                                       bindings=base.BINDINGS, purchase_tag_set=True)
            self.assertIn("followed_offer_unset:auto_upsell_1", result["blocked_by"], repr(unusable))

    def test_the_followed_offer_id_is_the_trimmed_package_offer_id(self):
        plan = _launch_plan_49(dict(OFFERS, upsell_1="  off-up1 "))
        unit = next(a for a in plan["automations"] if a["id"] == "auto_upsell_1")
        self.assertEqual(unit["followed_offer_id"], "off-up1")

    def test_skill_44_compiles_each_unit_with_no_blocker_gated_on_its_own_offer(self):
        doc = _skill_44_document(_launch_plan_49())
        for unit_id, offer in (("auto_upsell_1", "off-up1"), ("auto_downsell_1", "off-down1")):
            build = base.build_of(doc, unit_id)
            self.assertEqual((build["state"], build["blocked_by"], build["followed_offer_id"]),
                             ("ready", [], offer), unit_id)
            doc_result = lsc.compile_build(copy.deepcopy(build), purchase_tag_set=True,
                                           bindings=dict(base.BINDINGS, offer_id=offer))
            # The document compiler still reports the template's own trigger/tag bindings
            # (trigger_unverified:upsell_decision, tag_unresolved:*), which this issue does not
            # touch; what must be gone is every follow-up blocker.
            self.assertEqual([b for b in doc_result["blocked_by"]
                              if b.startswith(("followed_offer_unset", "guards:"))], [], unit_id)
            # the production path (workflow_builder) raises on any blocker: it compiles clean
            steps = _steps(unit_id, doc)
            gates = [s for s in steps if s["id"].endswith("-purchase-gate")]
            goals = [s for s in steps if s["type"] == "workflow_goal" and s["attributes"].get("goal") == "purchased"]
            self.assertEqual(len(gates), EMAIL_COUNT[FOLLOW_KIND[unit_id]], unit_id)
            self.assertEqual({g["attributes"]["conditions"][0]["value"] for g in gates},
                             {"purchased-" + offer}, unit_id)
            self.assertEqual({g["attributes"]["tag"] for g in goals}, {"purchased-" + offer})
            main_buyer = {LAUNCH_TAG, "purchased-off-main"}
            self.assertEqual(len(_sends_reached(steps, main_buyer)), EMAIL_COUNT[FOLLOW_KIND[unit_id]], unit_id)
            self.assertEqual(_sends_reached(steps, main_buyer | {"purchased-" + offer}), [], unit_id)
        # a buyer of the upsell is still sent the downsell follow-up (its own offer is unbought)
        down = _steps("auto_downsell_1", doc)
        self.assertEqual(len(_sends_reached(down, {LAUNCH_TAG, "purchased-off-up1"})), EMAIL_COUNT["downsell_followup"])


if __name__ == "__main__":
    unittest.main()
