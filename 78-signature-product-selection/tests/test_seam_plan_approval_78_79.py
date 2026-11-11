"""Issue 71 seam: the same approved launch record gets the same verdict from Skill 78 and from Skill 79.

78 lets a `recommended_unapproved` price onto the selection page when the plan approval covers it
(selection_core.plan_approval_covers, with a verifier). 79's production checkout gate asks the shared verifier the
same question about the same reference and plan hash. Both are driven here through the REAL shared verifier
(shared-utils approval_record.verify) against one loopback Command Center, so an approval the authority confirms
passes both gates, and one it refuses (wrong plan, wrong kind, revoked, unknown id) stops both.
"""
import copy
import http.server
import importlib.util
import json
import os
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
sys.path.insert(0, str(REPO / "79-signature-order-form" / "scripts"))

from build_selection_plan import SELF_TEST_LAUNCH  # noqa: E402
from selection_core import Violation, validate_catalog  # noqa: E402
from validate_checkout import CheckoutValidationError, validate_request  # noqa: E402

KIND, REF, PLAN_HASH = "launch_plan_build", "APPR-20261110-0002", "cd" * 32
NOW = "2026-11-10T12:00:00Z"
_spec = importlib.util.spec_from_file_location(
    "approval_record_seam", REPO / "shared-utils" / "signature_launch_contract" / "approval_record.py")
approval_record = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(approval_record)


class _CommandCenter(http.server.BaseHTTPRequestHandler):
    record = {}

    def do_GET(self):  # noqa: N802
        known = self.path.rstrip("/").endswith(self.record["approval_id"])
        body = json.dumps({"approval": self.record} if known else {}).encode()
        self.send_response(200 if known else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def approved_launch(ref=REF):
    launch = copy.deepcopy(SELF_TEST_LAUNCH)
    launch.update(status="approved", plan_approval_ref=ref, test_only=False)
    for offer in launch["offers"]:
        offer.pop("test_only", None)
        for price in offer["prices"]:
            price["approval_status"] = "recommended_unapproved"
    return launch


def checkout_request(launch):
    offer = launch["offers"][0]
    price = offer["prices"][0]

    def price_choice(p, o):
        return {"price_choice_id": p["price_choice_id"], "currency": p["currency"], "currency_exponent": 2,
                "amount_minor": p["amount_minor"], "billing_type": "one_time", "native_product_id": o["native_product_id"],
                "native_price_id": p["native_price_id"], "approval_status": p["approval_status"]}
    return {
        "tenant_id": launch["tenant_id"], "location_id": launch["location_id"], "launch_id": launch["launch_id"],
        "launch_revision": launch["revision"], "launch_plan_approval_ref": launch["plan_approval_ref"],
        "approved_plan_hash": PLAN_HASH, "checkout_mode": "combined_single_offer", "main_offer_id": offer["offer_id"],
        "main_price": price_choice(price, offer), "quantity": 1, "selection_ref": None, "selection_revision": None,
        "main_entitlement_ids": ["EM"], "previously_purchased_entitlement_ids": [], "bump": None,
        "brand_ref": "b", "brand_revision": "r", "terms_ref": "t", "native_capability_evidence_ref": "n",
        "successful_payment_next_route": "r", "fulfillment_mapping_ref": "f", "test_only": False, "consent_ref": "c",
        "failed_pending_requirements": {"failed_state_copy_ref": "x", "pending_state_copy_ref": "y",
                                        "retry_policy": "reconcile_native_records_first"}}


def verdicts(launch):
    """(78 verdict, 79 verdict) as 'accepted' or the refusal code, for the same launch record."""
    def covered_by_authority(record):  # what Skill 83 hands Skill 78: the shared verifier, veto = False
        try:
            return approval_record.verify(record["plan_approval_ref"], KIND, PLAN_HASH, [KIND], test_only=False)["ok"]
        except (approval_record.ApprovalRefused, approval_record.ApprovalUnavailable):
            return False
    try:
        validate_catalog(launch, approval_verifier=covered_by_authority)
        mine = "accepted"
    except Violation as v:
        mine = v.code
    try:
        validate_request(checkout_request(launch), now=NOW)  # Skill 79's default: the shared verifier itself
        theirs = "accepted"
    except CheckoutValidationError:
        theirs = "refused"
    return mine, theirs


class SameRecordSameVerdict(unittest.TestCase):
    def setUp(self):
        _CommandCenter.record = {
            "approval_id": REF, "kind": "plan_build", "plan_hash": PLAN_HASH, "client_identity_ref": "client-person",
            "tenant_id": "TEST-TENANT", "source_message_ref": "msg-1", "scope": KIND, "revoked": False,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
        server = http.server.HTTPServer(("127.0.0.1", 0), _CommandCenter)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        env = {"MISSION_CONTROL_URL": f"http://127.0.0.1:{server.server_address[1]}", "MC_API_TOKEN": "loopback-token",
               "COMPANY_SLUG": "TEST-TENANT"}
        patch = mock.patch.dict(os.environ, env, clear=True)
        patch.start()
        self.addCleanup(patch.stop)

    def test_an_approved_launch_record_passes_both_skills(self):
        self.assertEqual(verdicts(approved_launch()), ("accepted", "accepted"))

    def test_an_approval_the_authority_refuses_stops_both_skills(self):
        _CommandCenter.record["kind"] = "paid_asset_budget"
        self.assertEqual(verdicts(approved_launch()), ("S78-UNAPPROVED-PRICE", "refused"))

    def test_a_revoked_approval_stops_both_skills(self):
        _CommandCenter.record["revoked"] = True
        self.assertEqual(verdicts(approved_launch()), ("S78-UNAPPROVED-PRICE", "refused"))

    def test_a_reference_the_authority_does_not_know_stops_both_skills(self):
        self.assertEqual(verdicts(approved_launch(ref="APPR-NOT-MINTED-1")), ("S78-UNAPPROVED-PRICE", "refused"))

    def test_a_plan_bound_to_another_hash_stops_both_skills(self):
        _CommandCenter.record["plan_hash"] = "ef" * 32
        self.assertEqual(verdicts(approved_launch()), ("S78-UNAPPROVED-PRICE", "refused"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
