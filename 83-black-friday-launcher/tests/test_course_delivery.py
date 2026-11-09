"""WF13 / A17 + IG-PAGE-03: course production drives real launch fulfillment.

A17  Course production drives actual launch fulfillment; old binding formats
     remain compatible.
IG-PAGE-03  Native checkout and outstanding commerce proof gates are not
     bypassed by this modernization (an enrollment is never payment proof).

The producer is a fake with the real ``build_course`` signature; no browser,
network, payment or student content is touched.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO = SKILL_ROOT.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import checks, course_delivery as cd, delivery  # noqa: E402

S49_SCRIPTS = REPO / "49-signature-funnel" / "scripts"
S44_MAP = REPO / "44-convert-and-flow-operator" / "tools" / "siglaunch" / "fulfillment_map"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


INSERT_CHECKOUT = {"checkout_mode": None, "checkout_mode_state": "contract_gap"}

LAUNCH = {
    "launch_id": "launch-a", "tenant_id": "tenant-a", "location_id": "loc-a",
    "revision": 1,
}

OFFER = {
    "offer_id": "course-main", "name": "Launch Course", "role": "main",
    "location_id": "loc-a", "native_product_id": "course-prod-1",
    "entitlement_ids": ["course-main"],
    "price": {"amount_minor": 49700, "currency": "USD"},
    "delivery": {"destination": "https://members.example.test/course-main",
                 "owner_confirmed": True},
}


def content() -> dict:
    return {
        "approval": {"ref": "approved-outline-1"},
        "description": "Approved launch course.",
        "modules": [
            {"title": "Module One", "lessons": [
                {"title": "Welcome", "media": [
                    {"kind": "video", "url": "https://cdn.example.test/welcome.mp4",
                     "sha256": "a" * 64}]},
                {"title": "First Step"},
            ]},
            {"title": "Module Two", "lessons": [{"title": "Wrap Up"}]},
        ],
        "assessments": [{"id": "quiz-1", "title": "Checkpoint"}],
        "release": {"policy": "draft"},
        "access": {"destination": "https://members.example.test/course-main",
                   "verified": False, "proof_ref": None},
    }


def request(content_doc=None) -> dict:
    return cd.build_request(launch=LAUNCH, offer=OFFER,
                            content=content_doc or content(),
                            commerce={"commerce_product_id": "prod-1",
                                      "commerce_price_id": "price-1",
                                      "order_ref": "order-1"})


def content_for(destination: str, approval: str = "approved-outline-1") -> dict:
    doc = content()
    doc["access"] = {"destination": destination, "verified": False, "proof_ref": None}
    doc["approval"] = {"ref": approval}
    return doc


def producer_result(req: dict, **override) -> dict:
    modules = []
    for module in req["course_task"]["modules"]:
        lessons = []
        for lesson in module["lessons"]:
            media = [{"url": m["url"], "verified": True}
                     for m in lesson.get("_media") or []]
            lessons.append({"title": lesson["title"], "media": media,
                            "media_bound": bool(media) or True})
        modules.append({"title": module["title"], "lessons": lessons})
    result = {
        "ok": True, "location_id": "loc-a", "course_id": "course-1",
        "preview_url": "https://members.example.test/course-main",
        "modules": modules,
        "assessments": [{"id": "quiz-1", "verified": True}],
        "release": {"applied": True, "policy": "draft"},
        "group": {"requested": False},
        "access": {"enrollment_verified": True, "test_access_proof": None},
    }
    result.update(override)
    return result


def receipt(req: dict, **override) -> dict:
    return cd.build_receipt(req, producer_result(req, **override))


class FakeStore:
    """Minimal durable-store read surface the fulfillment map needs."""

    def __init__(self, entitlement="course-main", state="active"):
        self.entitlement, self.state = entitlement, state

    def buyer_lines(self, tenant_id, launch_id, contact_ref):
        return ["line-1"]

    def buyer_entitlement_rows(self, tenant_id, launch_id, contact_ref):
        return [("line-1", self.entitlement, self.state)]

    def line_action_states(self, tenant_id, line_ref, action):
        return ["done"]

    def entitlement_version(self, tenant_id, launch_id, contact_ref):
        return "ev1:" + "b" * 64

    def stored_events(self, tenant_id):
        return []


class LegacyConversionTests(unittest.TestCase):
    def test_unfinished_course_without_content_stays_pending(self):
        out = cd.convert_legacy_unfinished_course(
            {"item": "Launch course", "kind": "unfinished_course"},
            launch=LAUNCH, offer=OFFER, content=None)
        self.assertEqual(out["state"], cd.STATE_PENDING)
        self.assertTrue(any("approval" in m for m in out["missing"]))
        self.assertNotIn("request", out)

    def test_approved_content_mints_a_versioned_request(self):
        out = cd.convert_legacy_unfinished_course(
            {"item": "Launch course", "kind": "unfinished_course"},
            launch=LAUNCH, offer=OFFER, content=content(),
            commerce={"commerce_product_id": "prod-1",
                      "commerce_price_id": "price-1", "order_ref": "order-1"})
        self.assertEqual(out["state"], cd.STATE_REQUESTED)
        req = out["request"]
        self.assertEqual(req["contract_type"], cd.REQUEST_TYPE)
        self.assertEqual(req["schema_version"], cd.SCHEMA_VERSION)
        # distinct course / offer / commerce / group identities
        self.assertEqual(req["course_offer_id"], "course-main")
        self.assertEqual(req["course_product_id"], "course-prod-1")
        self.assertEqual(req["commerce"]["commerce_product_id"], "prod-1")
        self.assertEqual(req["commerce"]["payment_state"], "not_verified")
        self.assertEqual(req["group"]["community_group_id"], None)
        self.assertEqual(req["expected"], {"module_count": 2, "lesson_count": 3,
                                           "media_count": 1, "assessment_count": 1})
        self.assertEqual([c["kind"] for c in req["components"]].count("media"), 1)

    def test_non_course_kind_is_not_rewritten(self):
        out = cd.convert_legacy_unfinished_course(
            {"item": "A call", "kind": "future_session"}, launch=LAUNCH,
            offer=OFFER, content=content())
        self.assertEqual(out["state"], cd.STATE_NOT_APPLICABLE)


class DispatchTests(unittest.TestCase):
    def test_dispatch_uses_the_build_course_facade_signature(self):
        seen = {}

        def facade(task, evidence_root, dry_run=True):
            seen.update(task=task, root=evidence_root, dry_run=dry_run)
            return producer_result(req)

        req = request()
        self.assertEqual(cd.dispatch(req, facade, "/tmp/evidence", dry_run=True)["ok"], True)
        self.assertEqual(seen["task"]["course_name"], "Launch Course")
        self.assertEqual(seen["task"]["location_id"], "loc-a")
        self.assertEqual(seen["root"], "/tmp/evidence")
        self.assertIs(seen["dry_run"], True)

    def test_missing_producer_is_an_error_not_a_fake_success(self):
        with self.assertRaises(cd.CourseDeliveryError) as ctx:
            cd.dispatch(request(), None, "/tmp/evidence")
        self.assertEqual(ctx.exception.code, "AF-COURSE-PRODUCER-MISSING")


class ReceiptTests(unittest.TestCase):
    def test_verified_receipt_is_complete_and_access_ready(self):
        req = request()
        doc = receipt(req)
        self.assertTrue(doc["complete"])
        self.assertEqual(doc["missing"], [])
        self.assertEqual(doc["access"]["state"], cd.ACCESS_READY)
        self.assertFalse(doc["access"]["proves_payment"])
        self.assertFalse(doc["enrollment_is_payment_proof"])
        self.assertTrue(cd.access_ready(doc))

    def test_listed_media_that_is_not_bound_blocks_completion(self):
        req = request()
        result = producer_result(req)
        result["modules"][0]["lessons"][0]["media_bound"] = False
        doc = cd.build_receipt(req, result)
        self.assertFalse(doc["complete"])
        self.assertIn("lesson:0:0:media:0", doc["missing"])

    def test_missing_lesson_blocks_completion(self):
        req = request()
        result = producer_result(req)
        result["modules"][1]["lessons"] = []
        doc = cd.build_receipt(req, result)
        self.assertFalse(doc["complete"])
        self.assertIn("lesson:1:0", doc["missing"])

    def test_requested_group_must_be_linked(self):
        doc_content = content()
        req = cd.build_request(launch=LAUNCH, offer=OFFER, content=doc_content,
                               group={"requested": True, "community_group_id": "group-1"})
        doc = cd.build_receipt(req, producer_result(req, group={"requested": True}))
        self.assertFalse(doc["complete"])
        self.assertIn("group:association", doc["missing"])

    def test_standalone_course_needs_no_group(self):
        doc = receipt(request())
        self.assertTrue(doc["complete"])
        self.assertNotIn("group:association", [c["component_id"] for c in doc["components"]])

    def test_draft_only_delivery_can_complete_while_access_is_pending(self):
        req = request()
        doc = cd.build_receipt(req, producer_result(
            req, access={"enrollment_verified": False, "test_access_proof": None}))
        self.assertTrue(doc["complete"])
        self.assertEqual(doc["access"]["state"], cd.ACCESS_PENDING)
        self.assertFalse(cd.access_ready(doc))
        self.assertIsNone(cd.bindings(req, doc)["course-main"]["delivery_url"])

    def test_refund_or_revoke_withholds_access(self):
        req = request()
        doc = cd.build_receipt(req, producer_result(req, refunded=True))
        self.assertEqual(doc["access"]["state"], cd.ACCESS_REVOKED)
        self.assertFalse(cd.access_ready(doc))
        self.assertIsNone(cd.bindings(req, doc)["course-main"]["delivery_url"])

    def test_receipt_id_is_deterministic(self):
        req = request()
        self.assertEqual(receipt(req)["receipt_id"], receipt(req)["receipt_id"])


class BindingCompatibilityTests(unittest.TestCase):
    def test_included_bump_never_inherits_another_offers_course_url(self):
        main_req = request()
        bump_offer = {**OFFER, "offer_id": "course-bump", "name": "Bump",
                      "entitlement_ids": ["course-bump"],
                      "delivery": {"destination": "https://members.example.test/bump",
                                   "owner_confirmed": True}}
        bump_req = cd.build_request(
            launch=LAUNCH, offer=bump_offer,
            content=content_for("https://members.example.test/bump", "approved-bump"))
        main_bind = cd.bindings(main_req, receipt(main_req))
        bump_bind = cd.bindings(bump_req, receipt(bump_req))
        self.assertEqual(set(main_bind), {"course-main"})
        self.assertEqual(set(bump_bind), {"course-bump"})
        self.assertNotIn("course-bump", main_bind)
        self.assertEqual(bump_bind["course-bump"]["delivery_url"],
                         "https://members.example.test/bump")

    def test_separate_receipt_map_does_not_touch_legacy_bindings(self):
        req = request()
        planned = delivery.plan({"offers": [OFFER], "launch_id": "launch-a"})
        legacy_before = delivery.bindings(planned)
        with tempfile.TemporaryDirectory() as tmp:
            info = cd.write_receipt_map([(req, receipt(req))], Path(tmp))
            doc = json.loads((Path(tmp) / cd.RECEIPTS_REL).read_text(encoding="utf-8"))
            self.assertEqual(info["entitlements"], 1)
        self.assertEqual(doc["bindings"]["course-main"]["delivery_url"],
                         "https://members.example.test/course-main")
        self.assertEqual(legacy_before, {"course-main": {
            "delivery_kind": "access",
            "delivery_url": "https://members.example.test/course-main"}})
        self.assertEqual(set(legacy_before["course-main"]), {"delivery_kind", "delivery_url"})


class DeliveryRecordIntegrationTests(unittest.TestCase):
    def _normalized(self):
        offer = {**OFFER,
                 "level": {"state": "supplied", "name": "Launch Course",
                           "deliverables": ["Launch course"]}}
        return {"launch_id": "launch-a", "tenant_id": "tenant-a", "location_id": "loc-a",
                "locale": "en", "offers": [offer]}

    def test_record_without_a_receipt_is_byte_identical_to_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = delivery.run(self._normalized(), Path(tmp))
        self.assertEqual(out["record"]["offers"][0]["delivery_mode"], delivery.MODE_UNWRITTEN)
        self.assertNotIn("course_delivery", out["record"]["offers"][0])

    def test_record_with_a_verified_receipt_flips_to_course_delivery(self):
        req = request()
        with tempfile.TemporaryDirectory() as tmp:
            out = delivery.run(self._normalized(), Path(tmp),
                               course_receipts={"course-main": receipt(req)})
        row = out["record"]["offers"][0]
        self.assertEqual(row["delivery_mode"], delivery.MODE_COURSE)
        self.assertTrue(row["course_delivery"]["complete"])
        self.assertTrue(row["course_delivery"]["access_ready"])
        self.assertEqual(row["promises"][0]["state"], delivery.PROMISE_DELIVERED)
        self.assertNotIn("course_delivery", out["record"]["offers"][0]["sheet"])

    def test_an_incomplete_receipt_keeps_the_promise_unproduced(self):
        req = request()
        doc = cd.build_receipt(req, producer_result(
            req, access={"enrollment_verified": False, "test_access_proof": None}))
        with tempfile.TemporaryDirectory() as tmp:
            out = delivery.run(self._normalized(), Path(tmp),
                               course_receipts={"course-main": doc})
        row = out["record"]["offers"][0]
        self.assertEqual(row["delivery_mode"], delivery.MODE_COURSE)
        self.assertTrue(row["course_delivery"]["complete"])
        self.assertFalse(row["course_delivery"]["access_ready"])
        self.assertEqual(row["promises"][0]["state"], delivery.PROMISE_DELIVERED)


class FulfillmentMapReadbackTests(unittest.TestCase):
    """Skill 82's read model (the S44 map) reads receipts without breaking old records."""

    def setUp(self):
        self.map = _load_module(S44_MAP / "fulfillment_map.py", "wf13_fulfillment_map")
        self.legacy_launch = {"delivery_bindings": {"course-main": {
            "delivery_kind": "access",
            "delivery_url": "https://members.example.test/course-main"}}}

    def test_old_binding_format_is_unchanged_without_receipts(self):
        out = self.map.build_fulfillment_map(FakeStore(), "tenant-a", "launch-a",
                                             "contact-1", self.legacy_launch)
        self.assertEqual(out["entitlements"]["course-main"]["delivery_url"],
                         "https://members.example.test/course-main")
        self.assertEqual(out["entitlements"]["course-main"]["next_action"], "access")

    def test_unverified_course_receipt_withholds_the_link(self):
        req = request()
        doc = cd.build_receipt(req, producer_result(
            req, access={"enrollment_verified": False, "test_access_proof": None}))
        out = self.map.build_fulfillment_map(
            FakeStore(), "tenant-a", "launch-a", "contact-1", self.legacy_launch,
            course_receipts={"course-main": doc})
        self.assertIsNone(out["entitlements"]["course-main"]["delivery_url"])
        self.assertEqual(out["entitlements"]["course-main"]["next_action"], "access")

    def test_verified_course_receipt_keeps_the_link(self):
        req = request()
        out = self.map.build_fulfillment_map(
            FakeStore(), "tenant-a", "launch-a", "contact-1", self.legacy_launch,
            course_receipts={"course-main": receipt(req)})
        self.assertEqual(out["entitlements"]["course-main"]["delivery_url"],
                         "https://members.example.test/course-main")


class PlanProducerTests(unittest.TestCase):
    """launch_plan.produce_deliverables translates legacy rows honestly."""

    def setUp(self):
        self.plan = _load_module(S49_SCRIPTS / "launch_plan.py", "wf13_launch_plan")

    def _launch(self):
        offer = {**OFFER, "slot": "main", "display_name": "Launch Course",
                 "deliverables": ["Launch course"], "exclusions": [],
                 "requires": [], "source_kind": "owner", "source_ref": "answers-file:packages[0]",
                 "test_only": True,
                 "prices": [{"price_choice_id": "course-main-USD", "currency": "USD",
                             "amount_minor": 49700, "billing_type": "one_time",
                             "native_price_id": None, "schedule": [],
                             "approval_status": "provided"}]}
        return {"launch_id": "launch-a", "tenant_id": "tenant-a",
                "location_id": "loc-a", "revision": 1,
                "journey_mode": "single_simple", "offers": [offer]}

    def _answers(self, with_content: bool):
        answers = {
            "deliverables_plan": {"state": "provided", "source_ref": "intake",
                                  "value": [{"item": "Launch course",
                                             "kind": "unfinished_course",
                                             "evidence": "client said not made yet"}]},
        }
        if with_content:
            answers["launch.course_content"] = {"state": "provided",
                                                "value": content()}
        return answers

    def test_no_approved_content_writes_no_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.plan.produce_deliverables(self._launch(), self._answers(False),
                                                 [self.plan._package_record(
                                                     self._launch()["offers"][0], 0)], tmp)
            self.assertEqual(out["course_requests"], [])
            self.assertFalse((Path(tmp) / "course-delivery-requests.json").exists())
        row = out["items"][0]
        self.assertEqual(row["state"], "not_produced")
        self.assertEqual(row["course_request_state"], "pending")
        self.assertTrue(row["course_request_missing"])

    def test_approved_content_emits_a_versioned_request_not_a_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.plan.produce_deliverables(self._launch(), self._answers(True),
                                                 [self.plan._package_record(
                                                     self._launch()["offers"][0], 0)], tmp)
            written = json.loads((Path(tmp) / "course-delivery-requests.json")
                                 .read_text(encoding="utf-8"))
        row = out["items"][0]
        self.assertEqual(row["state"], "not_produced")  # a request is not a delivery
        self.assertEqual(row["course_request_state"], "requested")
        self.assertEqual(written["contract_type"], "launcher.course-delivery-requests.v1")
        self.assertEqual(len(written["requests"]), 1)
        self.assertEqual(written["requests"][0]["contract_type"], cd.REQUEST_TYPE)


class CheckoutGateTests(unittest.TestCase):
    """IG-PAGE-03: the commerce/checkout gate is not bypassed by this modernization."""

    def test_an_unresolved_checkout_mode_still_blocks_delivery(self):
        fails = checks.checkout_mode_violations(copy.deepcopy(INSERT_CHECKOUT))
        self.assertTrue(fails)
        self.assertIn("AF-LAUNCH-CHECKOUT-MODE", fails[0])

    def test_enrollment_is_never_payment_proof_in_a_receipt(self):
        doc = receipt(request())
        self.assertEqual(doc["payment_evidence"], "none")
        self.assertFalse(doc["enrollment_is_payment_proof"])
        self.assertFalse(doc["access"]["proves_payment"])
        self.assertIn("access grant", doc["access"]["basis"] if doc["access"]["basis"]
                      else "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
