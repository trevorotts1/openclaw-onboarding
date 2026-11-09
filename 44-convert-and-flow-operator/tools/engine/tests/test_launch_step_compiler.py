"""Launch step compiler (U-skill44-04): offline, no provider, no send, no credential.

Run: python3 -m pytest 44-convert-and-flow-operator/tools/engine/tests/test_launch_step_compiler.py -q
"""
import copy
import importlib.util
import sys
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
from cli_anything.gohighlevel.utils import launch_step_compiler as lsc  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "plan_reader_u44_04", HERE.parents[3] / "automation-templates" / "launch-c" / "plan_reader.py")
plan_reader = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plan_reader)

NOW = datetime.fromisoformat("2026-11-01T00:00:00-05:00")
AUTHORED_LIFECYCLE = {
    "stop_rules": plan_reader.DEFAULT_LIFECYCLE["stop_rules"] + [
        {"rule": "stop_on_refund", "scope": "this_campaign_only"}],
    "suppression_rules": plan_reader.DEFAULT_LIFECYCLE["suppression_rules"],
}
VARIANT = "variant tag (main / upsell-N / downsell-N)"
BINDINGS = {VARIANT: ["variant-main"], "every launch promotional tag on the buyer": ["launch:pre"],
            "until": {"indoc_4_at": "2026-11-26T09:00:00-05:00",
                      "precart_sms_at": "2026-11-26T18:00:00-05:00"}}


def _email(i):
    return {"id": "e%s" % i, "type": "email", "name": "Email %s" % i,
            "attributes": {"subject": "s%s" % i, "body": "<p>b</p>", "html": "<p>b</p>",
                           "fromName": "Synthetic Sender"}}


def _wait(i):
    return {"id": "w%s" % i, "type": "wait", "name": "Wait 1 Days",
            "attributes": {"type": "time", "startAfter": {"type": "days", "value": 1, "when": "after"}}}


def _build_plan(seq_id, count, tag, lifecycle=None):
    templates = []
    for i in range(count):
        templates.append(_email("%s%d" % (seq_id[-3:], i)))
        if i < count - 1:
            templates.append(_wait("%s%d" % (seq_id[-3:], i)))
    meta = {"sequence_id": seq_id, "draft_only": True, "deploy_mode": "draft-only"}
    if lifecycle:
        meta["lifecycle"] = lifecycle
    return {"folder": "Synthetic Drafts", "_meta": meta,
            seq_id: {"name": seq_id, "tag": tag, "status": "draft", "templates": templates}}


def make_document(post_sale_trigger="tag_added", lifecycle=AUTHORED_LIFECYCLE):
    plan = {
        "schema_version": "1.0.0", "launch_id": "bf-test",
        "offer": {"name": "Synthetic", "price_usd": 1, "currency": "USD", "payment_plans": False},
        "a2p_ready": False,
        "conversation_ai": {"requested": False, "mode": "none"},
        "launch_calendar": {"launch_at": "2026-11-27T12:00:00-05:00",
                            "doors_open_at": "2026-11-27T09:00:00-05:00",
                            "doors_close_at": "2026-12-01T23:59:00-05:00",
                            "timezone": "America/New_York"},
        "pages": [{"id": "page_landing", "kind": "landing", "url": "https://example.com/l", "waits_for": []}],
        "email_sequences": [
            {"id": "email_pre_launch", "kind": "pre_launch", "provider": "skill50", "email_count": 5,
             "draft_only": True, "waits_for": ["page_landing"]},
            {"id": "email_welcome_access", "kind": "welcome_access", "provider": "skill50",
             "email_count": 1, "draft_only": True, "waits_for": []}],
        "text_sets": [],
        "automations": [
            {"id": "auto_pre_launch", "family": "pre_launch", "template": "launch-a/launch-a-prelaunch-window", "build_rail": "skill44_engine",
             "draft_only": True, "trigger": {"type": "tag_added"}, "waits_for": ["email_pre_launch"]},
            {"id": "auto_post_sale", "family": "post_sale", "template": "launch-b/launch-post-sale-purchase", "build_rail": "skill44_engine",
             "draft_only": True, "trigger": {"type": post_sale_trigger}, "waits_for": ["email_welcome_access"]}],
    }
    parsed = plan_reader.read_launch_plan(plan)
    pre = _build_plan("email_pre_launch", 5, "launch:pre", lifecycle)
    welcome = _build_plan("email_welcome_access", 1, "launch:welcome")
    bound = {"email_pre_launch": ("pre", pre, plan_reader.read_build_plan(pre, "pre")),
             "email_welcome_access": ("welcome", welcome, plan_reader.read_build_plan(welcome, "welcome"))}
    return plan_reader.build_document("plan", parsed, bound, [], [], now=NOW)


def build_of(doc, build_id):
    return next(b for b in doc["builds"] if b["id"] == build_id)


def assert_graph_closed(test, steps):
    ids = {s["id"] for s in steps}
    for s in steps:
        for target in [s.get("next")] + list((s.get("branches") or {}).values()):
            test.assertTrue(target is None or target in ids, (s["id"], target))


class TemplateResolution(unittest.TestCase):
    def test_template_resolves_to_buildable_spec(self):
        spec, key, reason = lsc.resolve_template({"family": "post_sale", "template": "new"})
        self.assertIsNone(reason)
        self.assertEqual(key, "launch-b/launch-post-sale-purchase")
        types = {n["type"] for n in spec["build_graph"]}
        self.assertTrue({"sms", "if_else", "workflow_goal"} <= types)

    def test_unbuildable_and_unknown_templates_are_named_blocks(self):
        # abandoned_checkout is a buildable family now; unbuildable is a family whose
        # template key is absent from the manifest (here: a manifest without it).
        manifest = {"launch-a/launch-a-prelaunch-window": {"path": "launch-a/prelaunch-window.json"}}
        _spec, _key, reason = lsc.resolve_template(
            {"family": "abandoned_checkout", "template": "new"}, manifest=manifest)
        self.assertEqual(reason, "template_unbuildable:launch-b/abandoned-checkout-recovery")
        _spec, _key, reason = lsc.resolve_template({"family": "pre_launch", "template": "no-such-template"})
        self.assertEqual(reason, "template_unresolved:no-such-template")


class Triggers(unittest.TestCase):
    def test_payment_succeeded_is_blocked_not_defaulted_to_tag_added(self):  # S44-05 proof
        doc = make_document(post_sale_trigger="payment_succeeded")
        result = lsc.compile_build(build_of(doc, "auto_post_sale"), bindings=BINDINGS)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("trigger_unverified:payment_succeeded", result["blocked_by"])
        self.assertEqual(result["workflows"], {})
        self.assertIsNone(result["trigger"])
        self.assertEqual([r["action"] for r in result["browser_steps"] if r["action"] == "set_trigger"],
                         ["set_trigger"])

    def test_verified_tag_trigger_compiles_non_default_payload(self):
        doc = make_document()
        result = lsc.compile_build(build_of(doc, "auto_post_sale"), bindings=BINDINGS)
        self.assertEqual(result["status"], "ok", result["blocked_by"])
        self.assertEqual(result["trigger"]["type"], "contact_tag")
        self.assertEqual(result["trigger"]["conditions"][0]["value"], "launch:welcome")


class StepCompile(unittest.TestCase):
    def test_post_sale_compiles_sms_if_else_goal_and_sets_purchase_tag(self):
        result = lsc.compile_build(build_of(make_document(), "auto_post_sale"), bindings=BINDINGS)
        self.assertEqual(result["status"], "ok", result["blocked_by"])
        wf = result["workflows"]["auto_post_sale__flow"]
        types = [s["type"] for s in wf["templates"]]
        for expected in ("sms", "if_else", "workflow_goal", "email", "add_contact_tag"):
            self.assertIn(expected, types)
        ptag = lsc.purchase_tag("bf-test")
        self.assertTrue(any(s["type"] == "add_contact_tag" and ptag in s["attributes"]["tags"]
                            for s in wf["templates"]))
        self.assertEqual(lsc.verify_readback(wf, wf["templates"]), [])
        assert_graph_closed(self, wf["templates"])
        # free-text condition has no verified payload: a named browser step, not a guess
        self.assertTrue(any(r["action"] == "configure_if_else_condition" for r in result["browser_steps"]))

    def test_unbound_placeholder_tag_blocks(self):
        result = lsc.compile_build(build_of(make_document(), "auto_post_sale"))
        self.assertTrue(any(b.startswith("tag_unresolved:") for b in result["blocked_by"]))
        self.assertEqual(result["workflows"], {})


class PurchaseGuards(unittest.TestCase):
    def _promo(self, doc=None, **kw):
        doc = doc or make_document()
        return lsc.compile_build(build_of(doc, "auto_pre_launch"), bindings=BINDINGS,
                                 purchase_tag_set=True, **kw)

    def test_promo_workflow_gets_goal_and_gate_on_purchase_tag(self):
        result = self._promo()
        self.assertEqual(result["status"], "ok", result["blocked_by"])
        wf = result["workflows"]["auto_pre_launch__flow"]
        ptag = lsc.purchase_tag("bf-test")
        goals = [s for s in wf["templates"] if s["type"] == "workflow_goal" and s["attributes"].get("tag") == ptag]
        gates = [s for s in wf["templates"] if s["id"].endswith("-purchase-gate")]
        sends = [s for s in wf["templates"] if s["type"] in ("email", "sms")]
        self.assertEqual(len(goals), 1)
        self.assertEqual(len(gates), len(sends))
        for gate in gates:
            self.assertEqual(gate["branches"]["true"], goals[0]["id"])
            self.assertEqual(gate["attributes"]["conditions"][0]["value"], ptag)
        for s in sends:  # the synthetic verified_purchase field is no longer relied on
            self.assertFalse(any(c.get("id") == "guard-purchase-suppression"
                                 for c in s["attributes"].get("conditions", [])))
        assert_graph_closed(self, wf["templates"])
        self.assertEqual(lsc.verify_readback(wf, wf["templates"]), [])

    def test_readback_catches_missing_goal_and_gate(self):
        wf = self._promo()["workflows"]["auto_pre_launch__flow"]
        stripped = [s for s in wf["templates"]
                    if s["type"] != "workflow_goal" and not s["id"].endswith("-purchase-gate")]
        findings = lsc.verify_readback(wf, stripped)
        self.assertTrue(any(f.startswith("purchase_goal_missing") for f in findings))
        self.assertTrue(any(f.startswith("purchase_gate_missing") for f in findings))

    def test_absent_lifecycle_is_blocked(self):  # S44-09 proof
        for build in (self._lifecycle_removed(), self._reader_default()):
            result = lsc.compile_build(build, bindings=BINDINGS, purchase_tag_set=True)
            self.assertEqual(result["status"], "blocked")
            self.assertTrue(any(b.startswith("guards:auto_pre_launch:") for b in result["blocked_by"]),
                            result["blocked_by"])
            self.assertEqual(result["workflows"], {})

    def _lifecycle_removed(self):
        build = copy.deepcopy(build_of(make_document(), "auto_pre_launch"))
        build.pop("lifecycle")
        return build

    def _reader_default(self):
        # a plan with no lifecycle meta: the reader synthesizes the contract default
        return build_of(make_document(lifecycle=None), "auto_pre_launch")

    def test_default_lifecycle_constant_matches_reader(self):
        self.assertEqual(lsc.CONTRACT_DEFAULT_LIFECYCLE, plan_reader.DEFAULT_LIFECYCLE)

    def test_promo_without_a_post_sale_that_sets_the_tag_is_blocked(self):
        doc = make_document(post_sale_trigger="payment_succeeded")  # post-sale blocked -> tag never set
        out = lsc.compile_launch_document(doc, bindings=BINDINGS)
        self.assertIn("purchase_tag_unset", out["blocked"]["auto_pre_launch"])
        ok = lsc.compile_launch_document(make_document(), bindings=BINDINGS)
        self.assertEqual(ok["blocked"], {}, ok["blocked"])
        self.assertEqual(sorted(ok["campaign"]), ["auto_post_sale__flow", "auto_pre_launch__flow"])


class AbsoluteDates(unittest.TestCase):
    def test_main_launch_sends_are_gated_by_wait_until_date_steps(self):  # S44-11 proof
        build = build_of(make_document(), "auto_pre_launch")
        result = lsc.compile_build(build, bindings=BINDINGS, purchase_tag_set=True)
        self.assertEqual(result["status"], "ok", result["blocked_by"])
        wf = result["workflows"]["auto_pre_launch__flow"]
        by_id = {s["id"]: s for s in wf["templates"]}
        schedule = {n["step_id"]: n["at"] for n in build["schedule"]["nodes"]}
        for email_id, at in schedule.items():
            referrers = [s for s in wf["templates"] if s.get("next") == email_id
                         or email_id in (s.get("branches") or {}).values()]
            self.assertEqual(len(referrers), 1)
            gate = referrers[0]
            self.assertEqual(gate["attributes"]["conditions"][0]["value"], lsc.purchase_tag("bf-test"))
            waits = [s for s in wf["templates"] if s["type"] == "wait" and s.get("next") == gate["id"]]
            self.assertEqual(len(waits), 1, email_id)
            self.assertEqual(waits[0]["attributes"]["type"], "until_date")
            self.assertEqual(datetime.fromisoformat(waits[0]["attributes"]["untilDate"]),
                             datetime.fromisoformat(at))
            self.assertEqual(waits[0]["rail"], "managed_browser")
        ledger = [r for r in result["browser_steps"] if r["action"] == "wait_until_date"]
        self.assertGreaterEqual(len(ledger), 5)
        self.assertTrue(all(r["status"] == "pending" and r["ledger_id"] for r in ledger))
        self.assertTrue(wf["requires_browser"])
        # export read-back (WF-9): a graph missing one date fails
        exported = [s for s in wf["templates"] if s["id"] != by_id[next(iter(schedule))].get("id")
                    or s["type"] != "email"]
        dropped = copy.deepcopy(wf["templates"])
        for s in dropped:
            if s["type"] == "wait" and s["attributes"].get("untilDate") == ledger[0]["at"]:
                s["attributes"]["untilDate"] = "2030-01-01T00:00:00-05:00"
        self.assertTrue(any(f.startswith("wait_until_missing") for f in lsc.verify_readback(wf, dropped)))
        self.assertTrue(exported)

    def test_blocked_absolute_wait_unsupported_when_browser_steps_disallowed(self):
        build = build_of(make_document(), "auto_pre_launch")
        result = lsc.compile_build(build, bindings=BINDINGS, purchase_tag_set=True,
                                   allow_browser_steps=False)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(b.startswith("absolute_wait_unsupported:") for b in result["blocked_by"]))
        self.assertEqual(result["workflows"], {})

    def test_unresolved_template_date_token_is_blocked(self):
        build = build_of(make_document(), "auto_pre_launch")
        result = lsc.compile_build(build, bindings={}, purchase_tag_set=True)
        self.assertTrue(any(b.startswith("absolute_wait_unsupported:") for b in result["blocked_by"]))

    def test_ledger_rows_append_as_jsonl(self):
        import json
        import tempfile
        result = lsc.compile_build(build_of(make_document(), "auto_pre_launch"), bindings=BINDINGS,
                                   purchase_tag_set=True)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            lsc.append_browser_ledger(path, result["browser_steps"])
            rows = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(len(rows), len(result["browser_steps"]))


if __name__ == "__main__":
    unittest.main()
