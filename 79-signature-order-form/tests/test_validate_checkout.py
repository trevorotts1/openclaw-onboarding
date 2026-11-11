"""Issue 71 (decision D-C): a `recommended_unapproved` price at the production checkout gate.

Skill 78 accepts a recommended price when the client's plan approval covers it
(selection_core.price_is_approved). Skill 79 used to refuse the same price outright, so the
same approved launch record built a selection page and was then refused at checkout. The 79
gate now accepts `recommended_unapproved` when, and only when, the request's
`launch_plan_approval_ref` is a `launch_plan_build` approval for `approved_plan_hash` that the
ONE shared verifier (shared-utils approval_record.verify, a Command Center read) confirms.
Everything else is refused as before. Hermetic: a stub verifier, plus one loopback Command
Center that exercises the real verifier end to end.
"""
import copy
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(HERE.parent))

import validate_checkout  # noqa: E402
from validate_checkout import CheckoutValidationError, validate_request  # noqa: E402
from test_validate_checkout_production import BASE, NOW  # noqa: E402

KIND = "launch_plan_build"


class Refused(Exception):
    """Stands in for approval_record.ApprovalRefused / ApprovalUnavailable."""


def stub_verifier(*, ok=True, kind=KIND, authority="command-center", approval_id=None, raises=None):
    calls = []

    def verify(ref, wanted_kind, plan_hash, scope, **kw):
        calls.append({"ref": ref, "kind": wanted_kind, "plan_hash": plan_hash, "scope": list(scope), **kw})
        if raises is not None:
            raise raises
        return {"ok": ok, "kind": kind, "authority": authority, "approval_id": approval_id or ref}

    verify.calls = calls
    return verify


def recommended(request, *, main=True, bump=False):
    if main:
        request["main_price"]["approval_status"] = "recommended_unapproved"
    if bump:
        request["bump"]["price"]["approval_status"] = "recommended_unapproved"


def run(mutate, verifier, now=NOW):
    """Validate a mutated BASE request with `verifier` standing in for the shared one (None: the real one)."""
    request = copy.deepcopy(BASE)
    mutate(request)
    if verifier is None:
        validate_request(request, now=now)
    else:
        with mock.patch.object(validate_checkout, "_shared_verify", return_value=verifier):
            validate_request(request, now=now)
    return request


class RecommendedPriceNeedsAVerifiedPlanApproval(unittest.TestCase):
    def test_verified_plan_approval_accepts_a_recommended_main_price(self):
        verifier = stub_verifier()
        run(lambda r: recommended(r), verifier)
        self.assertEqual(len(verifier.calls), 1)
        call = verifier.calls[0]
        self.assertEqual((call["ref"], call["kind"], call["plan_hash"], call["scope"]),
                         ("a", KIND, "h", [KIND]))
        self.assertIs(call["test_only"], False)  # a production gate never reads a local record

    def test_verified_plan_approval_accepts_recommended_main_and_bump(self):
        run(lambda r: recommended(r, bump=True), stub_verifier())

    def test_a_recommended_bump_alone_is_covered_the_same_way(self):
        run(lambda r: recommended(r, main=False, bump=True), stub_verifier())

    def test_unverifiable_approval_is_refused_for_main_and_for_bump(self):
        for name, mutate in (("main", lambda r: recommended(r)),
                             ("bump", lambda r: recommended(r, main=False, bump=True))):
            with self.subTest(name), self.assertRaises(CheckoutValidationError) as ctx:
                run(mutate, stub_verifier(raises=Refused("APPROVAL-HASH: bound to a different plan")))
            self.assertIn("plan approval", str(ctx.exception))
            self.assertIn("APPROVAL-HASH", str(ctx.exception))

    def test_a_verifier_that_does_not_confirm_is_refused(self):
        for name, verifier in (
                ("ok false", stub_verifier(ok=False)),
                ("another kind", stub_verifier(kind="paid_asset_budget")),
                ("another approval id", stub_verifier(approval_id="SOME-OTHER-APPROVAL")),
                ("not from Command Center", stub_verifier(authority="local-test-record")),
                ("no verdict at all", lambda *a, **k: None)):
            with self.subTest(name), self.assertRaises(CheckoutValidationError):
                run(lambda r: recommended(r), verifier)

    def test_blank_reference_or_hash_is_refused_without_asking_the_verifier(self):
        for key in ("launch_plan_approval_ref", "approved_plan_hash"):
            verifier = stub_verifier()
            with self.subTest(key), self.assertRaises(CheckoutValidationError):
                run(lambda r: (recommended(r), r.update({key: "   "})), verifier)
            self.assertEqual(verifier.calls, [])

    def test_approved_prices_never_need_the_verifier(self):
        verifier = stub_verifier(raises=Refused("must not be called"))
        run(lambda r: None, verifier)
        self.assertEqual(verifier.calls, [])

    def test_the_approval_does_not_widen_to_other_unsafe_statuses(self):
        verifier = stub_verifier()
        with self.assertRaises(CheckoutValidationError):
            run(lambda r: r["main_price"].update(approval_status="test_only"), verifier)
        with self.assertRaises(CheckoutValidationError):  # still zero-priced, native ids still required
            run(lambda r: (recommended(r), r["main_price"].update(amount_minor=0)), verifier)
        with self.assertRaises(CheckoutValidationError):
            run(lambda r: (recommended(r), r["main_price"].update(native_product_id=None)), verifier)

    def test_test_only_requests_do_not_consult_the_verifier(self):
        verifier = stub_verifier(raises=Refused("must not be called"))

        def mutate(r):
            r.update(test_only=True)
            r["main_price"].update(approval_status="test_only", native_product_id=None, native_price_id=None)
        run(mutate, verifier, now=None)
        self.assertEqual(verifier.calls, [])


class NoWayToHandTheGateAVerifier(unittest.TestCase):
    def test_the_gate_takes_no_verifier_argument(self):
        with self.assertRaises(TypeError):
            validate_request(copy.deepcopy(BASE), now=NOW, approval_verifier=stub_verifier())

    def test_a_request_cannot_carry_one_either(self):
        request = copy.deepcopy(BASE)
        recommended(request)
        request["approval_verifier"] = "always"
        with self.assertRaises(CheckoutValidationError):  # the closed request schema refuses the extra key
            validate_request(request, now=NOW)


class DefaultVerifierIsTheSharedOne(unittest.TestCase):
    """No stub: the module must reach the shared approval_record, never a shape-only pass."""

    def test_without_command_center_a_recommended_price_is_refused(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(CheckoutValidationError) as ctx:
            run(lambda r: (recommended(r), r.update(launch_plan_approval_ref="APPR-20261110-1")), None)
        self.assertIn("plan approval", str(ctx.exception))

    def test_a_file_or_dict_is_not_an_approval(self):
        with tempfile.TemporaryDirectory() as td:
            record = Path(td) / "approval.json"
            record.write_text(json.dumps({"kind": KIND, "scope": [KIND], "revoked": False}))
            with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(CheckoutValidationError):
                run(lambda r: (recommended(r), r.update(launch_plan_approval_ref=str(record))), None)


class _CommandCenter(http.server.BaseHTTPRequestHandler):
    record = {}

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/").endswith(self.record["approval_id"]) and \
                self.headers.get("Authorization") == "Bearer loopback-token":
            body, code = json.dumps({"approval": self.record}).encode(), 200
        else:
            body, code = b"{}", 404
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class RealVerifierEndToEnd(unittest.TestCase):
    """The shared approval_record.verify against a loopback Command Center: proves the kind, scope,
    plan hash and tenant binding this gate sends are the ones the real verifier accepts."""

    PLAN_HASH = "ab" * 32
    REF = "APPR-20261110-0001"

    def setUp(self):
        _CommandCenter.record = {
            "approval_id": self.REF, "kind": "plan_build", "plan_hash": self.PLAN_HASH,
            "client_identity_ref": "client-person", "tenant_id": "loopback-tenant",
            "source_message_ref": "msg-1", "scope": KIND, "revoked": False,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
        self.server = http.server.HTTPServer(("127.0.0.1", 0), _CommandCenter)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.env = {"MISSION_CONTROL_URL": f"http://127.0.0.1:{self.server.server_address[1]}",
                    "MC_API_TOKEN": "loopback-token", "COMPANY_SLUG": "loopback-tenant"}

    def accept(self, **changes):
        def mutate(r):
            recommended(r)
            r.update(launch_plan_approval_ref=self.REF, approved_plan_hash=self.PLAN_HASH)
        with mock.patch.dict(os.environ, self.env, clear=True):
            request = copy.deepcopy(BASE)
            mutate(request)
            request.update(changes)
            validate_request(request, now=NOW)

    def test_a_command_center_approval_for_this_plan_is_accepted(self):
        self.accept()

    def test_the_wrong_plan_hash_is_refused(self):
        with self.assertRaises(CheckoutValidationError) as ctx:
            self.accept(approved_plan_hash="cd" * 32)
        self.assertIn("APPROVAL-HASH", str(ctx.exception))

    def test_another_kind_of_approval_is_refused(self):
        _CommandCenter.record["kind"] = "paid_asset_budget"
        with self.assertRaises(CheckoutValidationError) as ctx:
            self.accept()
        self.assertIn("APPROVAL-KIND", str(ctx.exception))

    def test_a_revoked_approval_is_refused(self):
        _CommandCenter.record["revoked"] = True
        with self.assertRaises(CheckoutValidationError) as ctx:
            self.accept()
        self.assertIn("APPROVAL-REVOKED", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
