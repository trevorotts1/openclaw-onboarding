"""U-products-03: what the 83 bridge writes into the Skill 49 launch record.

PRD-25 cumulative entitlements and `requires`; DTY-23 delivery bindings that Skill 44's fulfillment map
reads; STR-11 structure choices bound into the approved plan hash and a copy-form cross-check; PRD-02
approval ref taken from the verified record; ENF-02 the front door runs before dispatch. Free: Skill 49's
dispatch is replaced by a spy that records the call and stops, so no page is built and nothing is spent.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = SKILL_ROOT / "fixtures"
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

import substrate  # noqa: E402
import adapters  # noqa: E402
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))
from test_only_readback import paid_image_plan, patch_paid_budget  # noqa: E402
from launcher_core import image_plan, intake, launch_bridge, route  # noqa: E402

BRAND = str(Path(tempfile.gettempdir()) / "test-brand.json")


def payload(**plan) -> dict:
    doc = json.loads((FIXTURES / "elevation" / "intake.json").read_text(encoding="utf-8"))
    doc["image_plan"] = {"brand_file": BRAND, "brand_owner": "TEST-ONLY Client", **plan}
    return doc


def record(doc: dict, **kw) -> dict:
    normalized = intake.validate(doc)
    inputs, _ = image_plan.resolve(normalized.get("image_plan"), test_only=normalized["test_only"])
    return launch_bridge.to_launch_record(normalized, route.compile_route(normalized), inputs, **kw)


def plan_hash(launch: dict) -> str:
    return substrate.dispatch().vlp.plan_document_hash(launch)


def three_levels() -> dict:
    """Essential < Professional < Elite, each level listed as included in the bigger ones."""
    doc = payload()
    rel = {"MAIN-ESS": {"included_in": ["MAIN-PRO", "MAIN-ELITE"]}, "MAIN-PRO": {"included_in": ["MAIN-ELITE"]},
           "U1": {"requires": ["MAIN-ESS"]}}
    for offer in doc["offers"]:
        if offer["offer_id"] in rel:
            offer["relationships"] = rel[offer["offer_id"]]
    return doc


class StructureBindingTests(unittest.TestCase):
    def test_copy_form_page_set_style_and_extra_pages_each_change_the_plan_hash(self):
        base = plan_hash(record(payload()))
        self.assertEqual(plan_hash(record(payload())), base)
        changed = {
            "copy_profile": plan_hash(record({**payload(), "copy_profile": "long-form"})),
            "landing page set": plan_hash(record(payload(), landing_pages=["sales"])),
            "design style": plan_hash(record(payload(design_style="B"))),
            "extra pages": plan_hash(record(payload(), extra_pages=("downsell_2",))),
        }
        for what, digest in changed.items():
            self.assertNotEqual(digest, base, what)
        self.assertEqual(len(set(changed.values())), 4)

    def test_the_recommended_page_set_is_recorded_when_the_client_did_not_choose(self):
        launch = record(payload())
        self.assertIn("launcher-structure:landing_pages=landing,sales", launch["source_refs"])
        self.assertEqual(plan_hash(record(payload(), landing_pages=["sales", "landing"])), plan_hash(launch))
        self.assertEqual(launch_bridge.check_launch_record(launch), [])


class CumulativeEntitlementTests(unittest.TestCase):
    def test_a_three_level_intake_gives_level_three_all_three_levels(self):
        launch = record(three_levels())
        ents = {o["offer_id"]: o["entitlement_ids"] for o in launch["offers"]}
        self.assertEqual(set(ents["MAIN-ELITE"]), {"main-elite", "main-pro", "main-ess"})
        self.assertEqual(set(ents["MAIN-PRO"]), {"main-pro", "main-ess"})
        self.assertEqual(ents["MAIN-ESS"], ["main-ess"])
        self.assertEqual(ents["MAIN-ELITE"][0], "main-elite")
        self.assertEqual(launch_bridge.check_launch_record(launch), [])

    def test_requires_reaches_the_record_and_unrelated_offers_stay_plain(self):
        launch = record(three_levels())
        by_id = {o["offer_id"]: o for o in launch["offers"]}
        self.assertEqual(by_id["U1"]["requires"], ["MAIN-ESS"])
        self.assertEqual((by_id["BUMP"]["entitlement_ids"], by_id["BUMP"]["requires"]), (["bump"], []))

    def test_a_bump_included_in_a_level_is_not_folded_into_that_levels_grant(self):
        doc = payload()
        next(o for o in doc["offers"] if o["offer_id"] == "BUMP")["relationships"] = {"included_in": ["MAIN-PRO"]}
        launch = record(doc)
        pro = next(o for o in launch["offers"] if o["offer_id"] == "MAIN-PRO")
        self.assertEqual(pro["entitlement_ids"], ["main-pro"])
        self.assertEqual(launch_bridge.check_launch_record(launch), [])


class DeliveryBindingTests(unittest.TestCase):
    def normalized_with_delivery(self, doc=None):
        normalized = intake.validate(doc or three_levels())
        for offer in normalized["offers"]:  # the owner-confirmed destination the intake carries per offer
            offer["delivery"] = {"destination": f"https://members.example.test/{offer['offer_id'].lower()}",
                                 "owner_confirmed": True}
        return normalized

    def to_record(self, normalized):
        inputs, _ = image_plan.resolve(normalized.get("image_plan"), test_only=True)
        return launch_bridge.to_launch_record(normalized, route.compile_route(normalized), inputs)

    def test_every_entitlement_carries_a_binding_and_skill_44_reads_the_url(self):
        launch = self.to_record(self.normalized_with_delivery())
        granted = {e for o in launch["offers"] for e in o["entitlement_ids"]}
        self.assertEqual(set(launch["delivery_bindings"]), granted)
        self.assertEqual(launch["delivery_bindings"]["main-ess"],
                         {"delivery_kind": "access", "delivery_url": "https://members.example.test/main-ess"})
        self.assertEqual(launch_bridge.check_launch_record(launch), [])

        fmap = substrate.load("44-convert-and-flow-operator/tools/siglaunch/fulfillment_map/fulfillment_map.py",
                              "launcher_s44_fulfillment_map")

        class Store:  # a buyer whose every entitlement is fulfilled
            def buyer_lines(self, *_):
                return ["line-1"]

            def buyer_entitlement_rows(self, *_):
                return [("line-1", e, "active") for e in sorted(granted)]

            def stored_events(self, *_):
                return []

            def line_action_states(self, *_):
                return ["done"]

            def entitlement_version(self, *_):
                return 1

        built = fmap.build_fulfillment_map(Store(), launch["tenant_id"], launch["launch_id"], "contact-1",
                                           launch_record=launch)["entitlements"]
        self.assertEqual({e: v["delivery_url"] for e, v in built.items()},
                         {e: launch["delivery_bindings"][e]["delivery_url"] for e in granted})
        self.assertTrue(all(v["delivery_url"].startswith("https://") for v in built.values()))

    def test_a_validated_intake_always_carries_a_destination_per_offer_so_every_entitlement_is_bound(self):
        # intake.validate now refuses an offer with no delivery (CHK-16), so a record built from a real
        # intake always carries bindings; the "absent means no bindings" encoding is the bridge's, below.
        launch = record(payload())
        granted = {e for o in launch["offers"] for e in o["entitlement_ids"]}
        self.assertEqual(set(launch["delivery_bindings"]), granted)

    def test_a_normalized_intake_with_no_destinations_carries_no_bindings_key(self):
        normalized = intake.validate(payload())
        for offer in normalized["offers"]:
            offer.pop("delivery")
        self.assertNotIn("delivery_bindings", self.to_record(normalized))

    def test_a_missing_unconfirmed_or_non_https_destination_is_refused_by_name(self):
        for mutate in (lambda n: n["offers"][0].pop("delivery"),
                       lambda n: n["offers"][0]["delivery"].update(owner_confirmed=False),
                       lambda n: n["offers"][0]["delivery"].update(destination="http://members.example.test/x"),
                       lambda n: n["offers"][0]["delivery"].update(destination="https://a.test/has space")):
            normalized = self.normalized_with_delivery()
            mutate(normalized)
            with self.assertRaises(launch_bridge.BridgeError) as ctx:
                self.to_record(normalized)
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-DELIVERY")


class RunGateTests(unittest.TestCase):
    """bridge.run against a spy for Skill 49's dispatch: what it is handed, and in what order."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "run"
        self.calls = []
        patch_paid_budget(self)

    def spy(self):
        real, calls = substrate.dispatch(), self.calls

        def stop(launch, approval, **kwargs):
            calls.append(("dispatch", launch))
            raise real.DispatchError("spy: stopped at the call")

        class Spy:
            vlp, clr, pset, DispatchError, swarm = real.vlp, real.clr, real.pset, real.DispatchError, real.swarm
            executor_from_config = staticmethod(lambda *a, **k: None)
            dispatch = staticmethod(stop)
        return Spy

    def run_bridge(self, doc, approval, **kw):
        kw.setdefault("adapters_config", {"adapters": {}})
        # this spy checks what Skill 49 is handed; the allow-list is proved in AdapterAllowListTests
        with mock.patch.object(launch_bridge, "_validate_supplied_adapters", lambda *a, **k: None), \
                mock.patch.object(launch_bridge.substrate, "dispatch", return_value=self.spy()):
            return launch_bridge.run(doc, self.out, approval=approval, client_identity_ref="client-1",
                                     worker_identity_ref="worker-9", **kw)

    def live(self):
        doc = payload(**paid_image_plan(9))
        doc["test_only"] = False
        return doc

    def dispatched(self):
        return [launch for kind, launch in self.calls if kind == "dispatch"]

    def test_the_approval_ref_comes_from_the_verified_record_and_a_differing_intake_is_refused(self):
        doc = self.live()
        digest = plan_hash(record(doc))
        approval = {"approval_id": "APPR-LIVE-1", "plan_hash": digest}
        with mock.patch.object(substrate.dispatch().swarm, "kie_limiter", return_value=object()):
            with self.assertRaises(launch_bridge.BridgeError) as refused:
                self.run_bridge(doc, approval)  # the intake still names its placeholder approval
            self.assertEqual(refused.exception.code, "AF-LAUNCH-BRIDGE-APPROVAL")
            self.assertEqual(self.dispatched(), [])
            doc["approval"] = {"ref": "APPR-LIVE-1", "hash": digest}
            with self.assertRaises(launch_bridge.BridgeError) as stopped:
                self.run_bridge(doc, approval)
            self.assertEqual(stopped.exception.code, "AF-LAUNCH-BRIDGE-DISPATCH")  # got as far as the spy
        self.assertEqual(self.dispatched()[0]["plan_approval_ref"], "APPR-LIVE-1")

    def test_a_test_only_run_takes_the_record_ref_over_the_placeholder(self):
        digest = plan_hash(record(payload()))
        with self.assertRaises(launch_bridge.BridgeError):
            self.run_bridge(payload(), {"approval_id": "APPR-TEST-1", "plan_hash": digest})
        self.assertEqual(self.dispatched()[0]["plan_approval_ref"], "APPR-TEST-1")

    def test_the_front_door_runs_before_dispatch_and_a_tripped_gate_builds_nothing(self):
        gate = mock.Mock(side_effect=lambda: self.calls.append(("front_door", None)))
        with mock.patch.object(launch_bridge.substrate, "front_door_check", gate, create=True):
            with self.assertRaises(launch_bridge.BridgeError):
                self.run_bridge(payload(), {})
            kinds = [kind for kind, _ in self.calls]  # the gate runs once per Skill 49 script the bridge loads
            self.assertEqual((kinds[0], kinds[-1], kinds.count("dispatch")), ("front_door", "dispatch", 1))
            self.assertEqual(set(kinds[:-1]), {"front_door"})  # nothing but the gate runs before dispatch
            self.calls.clear()
            gate.side_effect = SystemExit("ABORT [HASH-PIN]: a pinned file changed")
            with self.assertRaises(SystemExit):
                self.run_bridge(payload(), {})
        self.assertEqual(self.calls, [])

    def bridge_config(self, version, **landing):
        path = Path(self.tmp.name) / f"bridge-{version}.json"
        path.write_text(json.dumps({"landing": {"page_version": version, **landing}}), encoding="utf-8")
        return str(path)

    def test_a_bridge_page_version_that_differs_from_the_approved_copy_form_is_refused(self):
        doc = {**payload(), "copy_profile": "long-form"}
        wrong = self.bridge_config("standard")
        for kw in ({"adapter_inputs": {"bridge_config": wrong}, "adapters_config": None},
                   {"adapters_config": {"adapters": {"landing": {"command": ["py", "x", "--bridge-config", wrong]}}}}):
            with self.assertRaises(launch_bridge.BridgeError) as ctx:
                self.run_bridge(doc, {}, **kw)
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-COPY-FORM")
        self.assertEqual(self.calls, [])

    def test_matching_forms_pass_and_the_opt_in_page_needs_long_form(self):
        ok = {"adapters_config": {"adapters": {"landing": {"command": [
            "py", "x", "--bridge-config", self.bridge_config("long-form")]}}}}
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            self.run_bridge({**payload(), "copy_profile": "long-form"}, {}, **ok)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-DISPATCH")  # reached the spy
        opt_in = self.bridge_config("standard", opt_in={"run_dir": "/x"})
        with self.assertRaises(launch_bridge.BridgeError) as refused:
            self.run_bridge(payload(), {}, adapters_config={"adapters": {"landing": {"command": [
                "py", "x", "--bridge-config", opt_in]}}})
        self.assertEqual(refused.exception.code, "AF-LAUNCH-BRIDGE-COPY-FORM")


class ProvenanceInTheRecordTests(unittest.TestCase):  # PRD-03: prices carry the client's answer, never a constant
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_a_suggested_main_price_is_recommended_unapproved_in_launch_json(self):
        answers = json.loads((FIXTURES / "elevation" / "answers.json").read_text(encoding="utf-8"))
        answers["answers"]["packages"]["status"] = "suggested"
        (self.root / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
        doc = payload()
        doc["answers_file"] = str(self.root / "answers.json")
        out = self.root / "run"
        approval = {"approval_id": "APPR-TEST-1", "plan_hash": plan_hash(record(doc))}
        with self.assertRaises(launch_bridge.BridgeError):  # no adapters: it stops after launch.json is written
            launch_bridge.run(doc, out, approval=approval, client_identity_ref="c", worker_identity_ref="w")
        launch = json.loads((out / "launch.json").read_text(encoding="utf-8"))
        for o in launch["offers"]:
            want = ("recommended_unapproved", "recommendation") if o["slot"] == "main" else ("provided", "owner")
            self.assertEqual((o["prices"][0]["approval_status"], o["source_kind"]), want, o["offer_id"])
            self.assertTrue(o["source_ref"].startswith("answers-file:"), o["offer_id"])
        self.assertFalse([r for r in launch["source_refs"] if r.startswith("launcher-intake:")])

    def test_an_offer_with_no_provenance_never_becomes_an_approved_record(self):
        normalized = intake.validate(payload())
        bare = {k: v for k, v in normalized["offers"][0].items() if k != "canonical"}
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            launch_bridge._offer(normalized, bare, {})
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-PROVENANCE")

    def test_billing_and_status_come_from_the_answers_entry_not_a_literal(self):
        launch = record(payload())
        for o in launch["offers"]:
            self.assertEqual((o["prices"][0]["billing_type"], o["prices"][0]["approval_status"], o["source_kind"]),
                             ("one_time", "provided", "owner"), o["offer_id"])


class RunArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "run"

    def approval(self, doc):
        return {"approval_id": "APPR-TEST-1", "plan_hash": plan_hash(record(doc))}

    def test_the_validated_intake_is_written_before_the_adapter_refusal(self):  # ENF-03
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            launch_bridge.run(payload(), self.out, approval=self.approval(payload()),
                              client_identity_ref="c", worker_identity_ref="w")
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-ADAPTERS")
        snapshot = self.out / "intake-at-dispatch.json"
        self.assertTrue(snapshot.is_file())
        self.assertEqual(json.loads(snapshot.read_text(encoding="utf-8")), intake.validate(payload()))


    def test_the_approved_checkout_terms_are_staged_beside_the_launch_record(self):
        doc = payload()
        with self.assertRaises(launch_bridge.BridgeError):
            launch_bridge.run(doc, self.out, approval=self.approval(doc), client_identity_ref="c",
                              worker_identity_ref="w")
        staged = json.loads((self.out / "checkout-terms.json").read_text(encoding="utf-8"))
        self.assertEqual(staged, {"checkout_terms": doc["checkout_terms"]})  # verbatim, nothing added


class AdapterAllowListTests(unittest.TestCase):  # ENF-08
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.marker = self.root / "marker"

    def refused(self, doc, config):
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            launch_bridge.run(doc, self.root / "run", approval={}, client_identity_ref="c",
                              worker_identity_ref="w", adapters_config=config)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-ADAPTERS")
        self.assertIn("adapter not in allow-list", ctx.exception.detail)
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.root / "run" / "dispatch").exists())

    def test_a_supplied_adapter_the_allow_list_refuses_never_runs(self):
        config = {"adapters": {"landing": {"command": [
            "python3", "-c", f"open({str(self.marker)!r},'w').write('x')"]}}}
        stub = mock.Mock(side_effect=adapters.AdapterError("adapter not in allow-list: python3 -c"))
        with mock.patch.object(adapters, "validate_adapter_config", stub, create=True):
            self.refused(payload(), config)
        self.assertEqual(stub.call_args.kwargs, {"test_only": True})

    @unittest.skipUnless(hasattr(adapters, "validate_adapter_config"),
                         "U-structure-01's allow-list is not in this tree")
    def test_the_real_allow_list_refuses_the_paid_fake_consumer_config(self):
        patch_paid_budget(self)
        doc = payload(**paid_image_plan(9))
        doc["test_only"] = False
        command = [sys.executable, str(SKILL_ROOT / "tests" / "lane83_fake_consumer.py"), "{request}", "{result}"]
        self.refused(doc, {"adapters": {"landing": {"command": command}}})


class RouteLawTests(unittest.TestCase):  # ENF-24
    def test_a_route_law_violation_is_the_launchers_own_error(self):
        law = route.route_law
        with mock.patch.object(law, "compile_route",
                               side_effect=law.RouteInvariantError("missing contract edges: landing->checkout")):
            with self.assertRaises(route.RouteError) as ctx:
                route.compile_route(intake.validate(payload()))
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ROUTE-LAW")
        self.assertIn("missing contract edges", str(ctx.exception))


class LandingBridgeConfigTests(unittest.TestCase):  # STR-16
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "run"
        self.cap = image_plan.resolve(payload()["image_plan"], test_only=True)[0]["image_cap"]

    def config(self, **landing) -> str:
        brand, launch = self.root / "brand.json", self.root / "launch-placeholder.json"
        brand.write_text("{}", encoding="utf-8")
        launch.write_text("{}", encoding="utf-8")
        path = self.root / "bridge.json"
        path.write_text(json.dumps({
            "skill71": {"root": str(SKILL_ROOT.parent / "71-blackceo-signature-page")},
            "landing": {"run_dir": str(self.root / "landing-run"), "page_version": "standard",
                        "page_kind": "sales", "brand_owner": "TEST-ONLY Client", "image_cap": self.cap,
                        "launch_record": str(launch), "brand_file": str(brand), **landing}}), encoding="utf-8")
        return str(path)

    def run_to_adapter_builder(self, bridge_config):
        seen = []

        def stop(adapter_inputs, *args):
            seen.append(adapter_inputs)
            raise launch_bridge.BridgeError("AF-LAUNCH-BRIDGE-ADAPTERS", "spy: stopped at the adapter builder")

        with mock.patch.object(launch_bridge, "_build_adapters", side_effect=stop):
            with self.assertRaises(launch_bridge.BridgeError) as ctx:
                launch_bridge.run(payload(), self.out, approval={}, client_identity_ref="c",
                                  worker_identity_ref="w", adapter_inputs={"bridge_config": bridge_config})
        return ctx.exception, seen

    def test_the_landing_bridge_config_carries_the_approved_image_plan(self):
        error, seen = self.run_to_adapter_builder(self.config())
        self.assertEqual(error.detail, "spy: stopped at the adapter builder")
        written = json.loads((self.out / "image_inputs.json").read_text(encoding="utf-8"))
        landing = json.loads(Path(seen[0]["bridge_config"]).read_text(encoding="utf-8"))["landing"]
        inputs_path = str((self.out / "image_inputs.json").resolve())
        self.assertEqual(landing["image_inputs"], inputs_path)
        self.assertEqual(landing["image_plan"], {"image_inputs": inputs_path, **{
            k: written[k] for k in ("image_cap", "brand_owner", "design_style", "image_provider")}})
        self.assertIs(landing["draft"], False)
        landing_bridge = substrate.load("49-signature-funnel/scripts/landing_bridge.py", "launcher_s49_landing_bridge")
        landing_bridge.load_bridge_config(Path(seen[0]["bridge_config"]))  # Skill 49 accepts the file

    def test_a_config_that_disagrees_with_the_approved_plan_is_refused_before_any_adapter_is_built(self):
        wrong = self.config(image_cap=self.cap + 1)
        with mock.patch.object(launch_bridge, "_build_adapters") as build:
            with self.assertRaises(launch_bridge.BridgeError) as ctx:
                launch_bridge.run(payload(), self.out, approval={}, client_identity_ref="c",
                                  worker_identity_ref="w", adapter_inputs={"bridge_config": wrong})
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-IMAGE-PLAN")
        self.assertIn("image_cap", ctx.exception.detail)
        build.assert_not_called()

    def test_an_unreadable_config_or_one_with_no_landing_section_is_refused_before_dispatch(self):
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            launch_bridge._landing_bridge_config({"bridge_config": str(self.root / "absent.json")}, self.root,
                                                 {}, self.root / "image_inputs.json")
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-ADAPTERS")
        for text in ("{}", '{"landing": "x"}', "[]"):
            bare = self.root / "bare.json"
            bare.write_text(text, encoding="utf-8")
            error, seen = self.run_to_adapter_builder(str(bare))
            self.assertEqual(error.code, "AF-LAUNCH-BRIDGE-ADAPTERS")
            self.assertIn("no \"landing\" section", error.detail)
            self.assertIn("Nothing was dispatched", error.detail)
            self.assertEqual(seen, [])  # refused before the adapter builder, so before dl.dispatch

if __name__ == "__main__":
    unittest.main(verbosity=2)
