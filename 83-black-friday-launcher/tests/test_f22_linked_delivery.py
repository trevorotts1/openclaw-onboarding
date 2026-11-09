"""F22: linked delivery pages and early capability checks.

Eleven items from BLACKCEO_LAUNCH_SUPPLEMENTAL_BUILD_SPEC.md section F22, each with
one check that fails on the parent commit (the behaviour did not exist) and passes
here. The checks drive the real modules: intake validation, the resource inventory,
the capability probes, the check rule and the fulfillment-map binding.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))

from launcher_core import capability_check, linked_delivery  # noqa: E402
from launcher_core.check_rules import linked_delivery as rule  # noqa: E402

FIXTURE = SKILL_ROOT / "fixtures" / "seven-figure-preneur" / "intake.json"


def setUpModule():
    """unittest never loads conftest.py; nothing to install: no read-back exists."""


def normalized(**overrides) -> dict:
    """The normalized-intake shape the modules read, without running the whole intake."""
    doc = {
        "tenant_id": "tenant-a",
        "location_id": "loc-a",
        "launch_id": "black-friday-2026",
        "revision": 1,
        "journey_mode": "single_simple",
        "allowed_write_target": "local_only",
        "test_only": True,
        "brand": {"ref": "brand-a", "hash": "a" * 64},
        "approval": {"ref": "approval-1", "hash": "b" * 64},
        "copy_profile": "signature_12_section",
        "offers": [{
            "offer_id": "main-1", "role": "main", "name": "Launch",
            "price": {"amount_minor": 49700, "currency": "USD"},
            "canonical": {"prices": [{"billing_type": "one_time"}]},
            "delivery": {"destination": "https://members.example.com/main-1",
                         "owner_confirmed": True},
        }],
        "linked_destinations": [],
    }
    doc.update(overrides)
    return doc


def new_build(key="access-page", page_key="thank_you", **overrides) -> dict:
    entry = {
        "key": key, "kind": "new_build", "page_key": page_key,
        "requirements": {name: f"TEST-ONLY-{name.upper()}-REF"
                         for name in linked_delivery.NEW_BUILD_REQUIREMENTS},
    }
    entry.update(overrides)
    return entry


def external(key="members-area", **overrides) -> dict:
    entry = {
        "key": key, "kind": "existing_client_owned",
        "url": "https://members.example.com/area",
        "evidence": {name: f"TEST-ONLY-{name.upper()}-REF"
                     for name in linked_delivery.EXTERNAL_EVIDENCE},
    }
    entry.update(overrides)
    return entry


def codes(record) -> list:
    return [b["code"] for b in record["blockers"]]


class Item01ResourceInventoryTests(unittest.TestCase):
    def test_item_01_inventory_carries_new_build_existing_and_third_party(self):
        doc = normalized(linked_destinations=[
            external("client-area"),
            {"key": "course-host", "kind": "third_party",
             "url": "https://courses.example.org/launch",
             "evidence": {n: f"TEST-ONLY-{n.upper()}-REF"
                          for n in linked_delivery.EXTERNAL_EVIDENCE}},
            new_build("access"),
        ])
        record = linked_delivery.resolve(doc)
        kinds = {r["key"]: r["kind"] for r in record["resources"]}
        self.assertEqual(kinds["client-area"], "existing_client_owned")
        self.assertEqual(kinds["course-host"], "third_party")
        self.assertEqual(kinds["access"], "new_build")
        # the intake's own owner-confirmed destination is inventoried too, never dropped
        self.assertEqual(kinds["offer:main-1"], "existing_client_owned")
        self.assertEqual(record["summary"]["counts"],
                         {"resources": 4, "new_build": 1, "external": 3, "blockers": 0})
        self.assertEqual(record["summary"]["state"], "resolved")

    def test_item_01_intake_accepts_the_declared_destinations(self):
        """The parent refuses this field outright as undeclared; the inventory cannot exist."""
        from launcher_core import intake
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["linked_destinations"] = [external("members-area")]
        normalized_doc = intake.validate(payload)
        self.assertEqual(normalized_doc["linked_destinations"][0]["key"], "members-area")
        self.assertEqual(normalized_doc["provenance"]["linked_destinations"], "supplied")


class Item02NewBuildTests(unittest.TestCase):
    def test_item_02_a_new_page_needs_a_registered_role_and_five_requirements(self):
        unknown = linked_delivery.resolve(normalized(linked_destinations=[
            new_build("x", page_key="members_login")]))
        self.assertIn("AF-LAUNCH-LINKED-ROLE", codes(unknown))

        incomplete = new_build("y")
        incomplete["requirements"] = {"brand": "TEST-ONLY-BRAND-REF"}
        missing = linked_delivery.resolve(normalized(linked_destinations=[incomplete]))
        self.assertEqual([c for c in codes(missing) if c == "AF-LAUNCH-LINKED-REQUIREMENT"],
                         ["AF-LAUNCH-LINKED-REQUIREMENT"] * 4)

        # a documented adapter to an existing applicable role is the permitted alternative
        adapted = {"key": "z", "kind": "new_build",
                   "adapter": {"role": "thank_you", "document_ref": "TEST-ONLY-ADAPTER-DOC"},
                   "requirements": {n: f"TEST-ONLY-{n.upper()}-REF"
                                    for n in linked_delivery.NEW_BUILD_REQUIREMENTS}}
        ok = linked_delivery.resolve(normalized(linked_destinations=[adapted]))
        self.assertEqual(ok["blockers"], [])
        self.assertEqual(ok["resources"][0]["role_source"], "documented_adapter")


class Item03ExternalTests(unittest.TestCase):
    def test_item_03_existing_and_third_party_need_six_evidence_facts(self):
        bare = external("bare", evidence={})
        record = linked_delivery.resolve(normalized(linked_destinations=[bare]))
        self.assertEqual([c for c in codes(record) if c == "AF-LAUNCH-LINKED-EVIDENCE"],
                         ["AF-LAUNCH-LINKED-EVIDENCE"] * len(linked_delivery.EXTERNAL_EVIDENCE))
        complete = linked_delivery.resolve(normalized(linked_destinations=[external()]))
        self.assertEqual(complete["blockers"], [])


class Item04FulfillmentTests(unittest.TestCase):
    def test_item_04_the_four_delivery_facts_stay_explicit(self):
        record = linked_delivery.resolve(normalized())
        row = record["fulfillment"][0]
        self.assertEqual(row["kind"], "purchased_product_or_service")
        self.assertEqual(row["kinds"], list(linked_delivery.FULFILLMENT_KINDS))
        self.assertEqual(row["evidence"]["excluded"], "a thank-you page visit")
        self.assertIn("a thank-you page visit is not proof", record["not_fulfillment"])
        self.assertTrue(row["transaction_triggered"])

    def test_item_04_a_free_lead_magnet_is_not_a_transaction_and_community_is_not_assumed(self):
        doc = normalized()
        doc["offers"] = [{"offer_id": "lead-1", "role": "free_lead", "name": "Lead magnet",
                          "price": {"amount_minor": 0, "currency": "USD"},
                          "canonical": {"prices": [{"billing_type": "free"}]},
                          "delivery": {"destination": "https://members.example.com/lead",
                                       "owner_confirmed": True}}]
        row = linked_delivery.resolve(doc)["fulfillment"][0]
        self.assertEqual(row["kind"], "free_lead_magnet")
        self.assertFalse(row["transaction_triggered"])
        # no recorded answer -> unknown, never a proven "no community"
        self.assertIsNone(row["community_access"])
        self.assertEqual(row["community_access_state"], "not_recorded")

        doc["offers"][0]["delivery"]["community_access"] = True
        recorded = linked_delivery.resolve(doc)["fulfillment"][0]
        self.assertTrue(recorded["community_access"])
        self.assertEqual(recorded["community_access_state"], "recorded")


class Item05EarlyGateTests(unittest.TestCase):
    """F22 item 5: the bridge consults the capability check BEFORE design work, fail closed."""

    def test_a_required_capability_that_cannot_be_proved_stops_the_dispatch(self):
        from launcher_core import launch_bridge
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            with self.assertRaises(launch_bridge.BridgeError) as ctx:
                launch_bridge.run(payload, out, approval={}, client_identity_ref="c",
                                  worker_identity_ref="w",
                                  observed_capabilities={"output_destination": {
                                      "location_id": "SOME-OTHER-LOCATION"}})
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-CAPABILITY")
            self.assertIn("Nothing was dispatched", ctx.exception.detail)
            # the refusal happened before any artifact existed: no page plan, no launch record
            self.assertFalse((out / "launch.json").exists())
            self.assertFalse((out / "image_inputs.json").exists())
            self.assertFalse((out / "pieces").exists())


class Item05CapabilityFailClosedTests(unittest.TestCase):
    def test_item_05_an_unproven_required_capability_refuses(self):
        live = normalized(test_only=False)
        for offer in live["offers"]:
            offer["canonical"] = {"prices": [{}]}
        record = capability_check.run(live)
        self.assertIn("billing_type", record["required"])
        self.assertEqual(record["capabilities"]["billing_type"]["state"], "unproven")
        self.assertIn("billing_type", record["blocked"])
        with self.assertRaises(capability_check.CapabilityError) as ctx:
            capability_check.assert_ready(record)
        self.assertEqual(str(ctx.exception).split(":", 1)[0], "AF-LAUNCH-CAPABILITY")

        # the same missing fact on a design-only run is NOT required: absence is not a pass,
        # it is recorded unproven and not selected, so the local work still proceeds.
        design = copy.deepcopy(live)
        design["test_only"] = True
        relaxed = capability_check.run(design)
        self.assertNotIn("billing_type", relaxed["required"])
        self.assertEqual(relaxed["capabilities"]["billing_type"]["state"], "not_required")
        capability_check.assert_ready(relaxed)


class Item06FoldedLevelsTests(unittest.TestCase):
    def test_item_06_folded_levels_reports_per_offer_instances_not_a_contract_gap(self):
        if not FIXTURE.is_file():
            self.skipTest("seven-figure-preneur fixture is not installed")
        from launcher_core import intake
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["journey_mode"] = "folded_levels"
        doc = intake.validate(payload)
        record = capability_check.run(doc)
        row = record["capabilities"]["journey_mapping"]
        self.assertEqual(row["state"], "proven", row["detail"])
        self.assertEqual(row["evidence"]["checkout_mode"], "combined_single_offer")
        self.assertEqual(row["evidence"]["realisation"], "per_offer_instances")
        self.assertNotIn("contract_gap", json.dumps(record))


class Item07BumpAndDownsellTests(unittest.TestCase):
    def test_item_07_bump_is_not_a_page_and_design_only_downsell_is_not_a_route(self):
        bump = linked_delivery.resolve(normalized(linked_destinations=[
            new_build("b", page_key="bump")]))
        self.assertIn("AF-LAUNCH-LINKED-BUMP", codes(bump))

        route = linked_delivery.resolve(normalized(linked_destinations=[
            new_build("d2", page_key="downsell_2", purchase_route=True)]))
        self.assertIn("AF-LAUNCH-LINKED-PURCHASE-ROUTE", codes(route))

        design_only = linked_delivery.resolve(normalized(linked_destinations=[
            new_build("d2", page_key="downsell_2", purchase_route=False)]))
        self.assertEqual(design_only["blockers"], [])
        self.assertTrue(design_only["resources"][0]["design_only"])


class Item08BlockerLanguageTests(unittest.TestCase):
    def test_item_08_every_blocker_has_plain_language_and_a_next_step(self):
        record = linked_delivery.resolve(normalized(linked_destinations=[
            new_build("one", page_key="nope"),
            external("two", evidence={}),
        ]))
        self.assertGreaterEqual(len(record["blockers"]), 2)  # one blocker never hides another
        for blocker in record["blockers"]:
            self.assertTrue(blocker["client_message"].strip())
            self.assertTrue(blocker["next_step"].strip())
            self.assertTrue(blocker["operator_detail"].strip())
        self.assertEqual(len(record["summary"]["client_blockers"]), len(record["blockers"]))
        self.assertEqual(len(record["summary"]["next_steps"]), len(record["blockers"]))


class Item09FulfillmentMapBindingTests(unittest.TestCase):
    def _map(self, td: Path, **overrides) -> Path:
        doc = {"version": "1.0.0", "tenant_id": "tenant-a",
               "launch_id": "black-friday-2026", "revision": 1,
               "entitlements": {"main-1": {"state": "granted"}}}
        doc.update(overrides)
        path = td / "fulfillment-map.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def test_item_09_a_map_is_bound_to_current_bytes_identity_and_entitlements(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            import hashlib
            path = self._map(td)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            bound = linked_delivery.verify_fulfillment_map(
                path, tenant_id="tenant-a", launch_id="black-friday-2026", revision=1,
                granted_entitlements=["main-1"], recorded_sha256=digest)
            self.assertEqual(bound["entitlements"], ["main-1"])
            self.assertEqual(bound["version"], "1.0.0")

            with self.assertRaises(linked_delivery.LinkedDeliveryError) as stale:
                linked_delivery.verify_fulfillment_map(
                    path, tenant_id="tenant-a", launch_id="black-friday-2026", revision=1,
                    granted_entitlements=["main-1"], recorded_sha256="0" * 64)
            self.assertEqual(stale.exception.code, "AF-LAUNCH-FULFILLMENT-MAP")

            foreign = self._map(td, tenant_id="tenant-b")
            with self.assertRaises(linked_delivery.LinkedDeliveryError):
                linked_delivery.verify_fulfillment_map(
                    foreign, tenant_id="tenant-a", launch_id="black-friday-2026", revision=1,
                    granted_entitlements=["main-1"])

            extra = self._map(td, entitlements={"main-1": {"state": "granted"},
                                                "ghost": {"state": "granted"}})
            with self.assertRaises(linked_delivery.LinkedDeliveryError):
                linked_delivery.verify_fulfillment_map(
                    extra, tenant_id="tenant-a", launch_id="black-friday-2026", revision=1,
                    granted_entitlements=["main-1"])


class Item10ConversationalTests(unittest.TestCase):
    PLAN = {"conversation_ai": {"requested": True, "mode": "playbook"}}

    def test_item_10_conversational_needs_one_responder_and_the_twelve_points(self):
        two = capability_check.run(normalized(), plan=self.PLAN,
                                   observed={"responders": ["a", "b"],
                                             "ghl_runtime_connected": True,
                                             "skill29_support": ["05", "10", "19"]})
        self.assertIn("conversational_workflows", two["required"])
        self.assertEqual(two["capabilities"]["conversational_workflows"]["state"], "unproven")
        self.assertIn("conversational_workflows", two["blocked"])

        prompt_only = capability_check.run(normalized(), plan=self.PLAN,
                                           observed={"responders": ["only"],
                                                     "ghl_runtime_connected": True,
                                                     "skill29_support": ["05", "10", "19"],
                                                     "workflow_build": {
                                                         "source_kind": "skill41_prompt",
                                                         "post_build_verification_points": 12,
                                                         "dependency_readback": True}})
        self.assertEqual(prompt_only["capabilities"]["conversational_workflows"]["state"],
                         "unproven")
        ok = capability_check.run(normalized(), plan=self.PLAN,
                                  observed={"responders": ["only"],
                                            "ghl_runtime_connected": True,
                                            "skill29_support": ["05", "10", "19"],
                                            "workflow_build": {
                                                "source_kind": "native_build",
                                                "post_build_verification_points": 12,
                                                "dependency_readback": True}})
        self.assertEqual(ok["capabilities"]["conversational_workflows"]["state"], "proven")
        # a page-only launch is never asked for the conversation contract
        self.assertNotIn("conversational_workflows", capability_check.run(normalized())["required"])


class Item11WorkflowAuthorizationTests(unittest.TestCase):
    # a workflow BUILD is being reported for this run, so item 11 is selected
    BUILD = {"source_kind": "native_build", "post_build_verification_points": 12,
             "dependency_readback": True}

    def test_item_11_workflow_authorization_fails_closed(self):
        cases = {
            "community_mcp": "community",
            "official_mcp_pit": "UNVERIFIED compatibility",
        }
        for mode, needle in cases.items():
            doc = capability_check.run(normalized(),
                                       plan={"automations": [{"id": "a"}]},
                                       observed={"auth_mode": mode,
                                                 "workflow_build": self.BUILD})
            self.assertIn("workflow_authorization", doc["required"])
            row = doc["capabilities"]["workflow_authorization"]
            self.assertEqual(row["state"], "unproven")
            self.assertIn(needle, row["detail"])

        switched = capability_check.run(normalized(),
                                        plan={"automations": [{"id": "a"}]},
                                        observed={"auth_mode": "pit_rest",
                                                  "transport_switching": True,
                                                  "workflow_build": self.BUILD})
        self.assertEqual(switched["capabilities"]["workflow_authorization"]["state"], "unproven")

        diagram = capability_check.run(normalized(),
                                       plan={"automations": [{"id": "a"}]},
                                       observed={"auth_mode": "official_mcp_oauth",
                                                 "publication_authority": "diagram_label",
                                                 "workflow_build": self.BUILD})
        self.assertEqual(diagram["capabilities"]["workflow_authorization"]["state"], "unproven")

        ok = capability_check.run(normalized(), plan={"automations": [{"id": "a"}]},
                                  observed={"auth_mode": "pit_rest",
                                            "publication_authority": "approval-77",
                                            "workflow_build": self.BUILD})
        self.assertEqual(ok["capabilities"]["workflow_authorization"]["state"], "proven")
        # a merely PLANNED automation is not a build here: not required at assembly
        planned = capability_check.run(normalized(), plan={"automations": [{"id": "a"}]})
        self.assertNotIn("workflow_authorization", planned["required"])


class DeterminismTests(unittest.TestCase):
    def test_same_inputs_give_the_same_page_set_and_fingerprint(self):
        first = normalized(linked_destinations=[external("b"), new_build("a"),
                                                external("c")])
        second = normalized(linked_destinations=[external("c"), external("b"),
                                                 new_build("a")])
        one, two = linked_delivery.resolve(first), linked_delivery.resolve(second)
        self.assertEqual(one["fingerprint"], two["fingerprint"])
        self.assertEqual([r["key"] for r in one["resources"]],
                         [r["key"] for r in two["resources"]])
        self.assertEqual(one["pages"], two["pages"])


class CheckRuleTests(unittest.TestCase):
    def _root(self, td: Path, doc: dict) -> Path:
        root = td / "run"
        root.mkdir()
        (root / "intake.json").write_text(json.dumps(doc), encoding="utf-8")
        return root

    def test_a_delivery_claim_with_an_unaccounted_destination_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            doc = normalized(linked_destinations=[new_build("x", page_key="nope")])
            root = self._root(td, doc)
            record = linked_delivery.resolve(doc)
            (root / "launch-resources.json").write_text(
                json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
            manifest = {"intake": {"path": "intake.json"}, "test_only": False,
                        "delivery_scope": "page_only",
                        "linked_delivery": {"path": "launch-resources.json",
                                            "fingerprint": record["fingerprint"]}}
            fails = rule.violations(manifest, root, SKILL_ROOT)
            self.assertTrue(any("AF-LAUNCH-LINKED-BLOCKED" in f for f in fails), fails)
            # a page-only design package records the same blocker without claiming delivery
            design = {**manifest, "test_only": True}
            self.assertEqual(rule.violations(design, root, SKILL_ROOT), [])

    def test_the_inventory_is_bound_at_assembly_and_drift_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            doc = normalized()
            root = self._root(td, doc)
            record = linked_delivery.resolve(doc)
            (root / "launch-resources.json").write_text(
                json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
            manifest = {"intake": {"path": "intake.json"}, "test_only": False,
                        "delivery_scope": "full_launch",
                        "linked_delivery": {"path": "launch-resources.json",
                                            "fingerprint": record["fingerprint"]}}
            self.assertEqual(rule.violations(manifest, root, SKILL_ROOT), [])
            changed = copy.deepcopy(record)
            changed["fingerprint"] = "0" * 64
            (root / "launch-resources.json").write_text(json.dumps(changed), encoding="utf-8")
            fails = rule.violations(manifest, root, SKILL_ROOT)
            self.assertTrue(any("AF-LAUNCH-LINKED-DRIFT" in f for f in fails), fails)


if __name__ == "__main__":
    unittest.main(verbosity=2)
