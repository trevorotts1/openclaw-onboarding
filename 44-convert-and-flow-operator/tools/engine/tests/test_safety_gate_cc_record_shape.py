"""A record in Command Center's launch_approvals shape (scope JSON string, plan_hash 'sha256:<hex>',
client_identity_ref) is accepted when it binds this write and refused on any mismatch.

Run: python3 -m pytest 44-convert-and-flow-operator/tools/engine/tests/test_safety_gate_cc_record_shape.py -q
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from test_safety_gate_approval import _Base, LOC, PLAN, ACTION, OBJ  # noqa: E402


def _cc(**over):
    rec = {
        "approval_id": "appr_12345678", "tenant_id": "t1", "kind": "automation_write",
        "client_identity_ref": "owner@client", "plan_hash": "sha256:" + PLAN,
        "scope": json.dumps({"location_id": LOC, "action": ACTION, "object_key": OBJ}),
        "cap_minor": None, "currency": None, "source_message_ref": "msg-1", "revoked": False,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    rec.update(over)
    return rec


class TestCcShape(_Base):
    def refused(self, rec):
        with self.assertRaises(self.sg.SafetyRefused):
            self.write(rec)

    def test_cc_shaped_matching_record_allowed(self):
        self.write(_cc())

    def test_prefix_and_case_of_plan_hash_do_not_matter(self):
        self.write(_cc(plan_hash="sha256:" + PLAN.upper()))

    def test_wrong_plan_hash_refused(self):
        self.refused(_cc(plan_hash="sha256:" + "b" * 64))

    def test_wrong_location_refused(self):
        self.refused(_cc(scope=json.dumps({"location_id": "OTHER", "action": ACTION, "object_key": OBJ})))

    def test_wrong_action_refused(self):
        self.refused(_cc(scope=json.dumps({"location_id": LOC, "action": "x", "object_key": OBJ})))

    def test_wrong_object_refused(self):
        self.refused(_cc(scope=json.dumps({"location_id": LOC, "action": ACTION, "object_key": "Other"})))

    def test_revoked_refused(self):
        self.refused(_cc(revoked=True))

    def test_expired_refused(self):
        self.refused(_cc(expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()))

    def test_wrong_kind_refused(self):
        self.refused(_cc(kind="publish"))

    def test_free_text_chat_scope_refused(self):
        self.refused(_cc(scope="images, pages"))

    def test_missing_identity_refused(self):
        rec = _cc()
        del rec["client_identity_ref"]
        self.refused(rec)

    def test_garbage_plan_hash_refused(self):
        self.refused(_cc(plan_hash="sha256:nothex"))

    def test_native_fields_win_over_scope(self):
        # native fields present and wrong must refuse even if scope would match
        self.refused(_cc(location_id="OTHER", action=ACTION, object_key=OBJ, plan_sha256=PLAN,
                         approver="o", verification_class="authenticated_platform_record"))


class TestNative645Shape(_Base):
    """GET /api/launch-approvals/<id> after CC PR 645: gate fields returned natively next to the CC columns."""

    def rec(self, **over):
        r = _cc(location_id=LOC, action=ACTION, object_key=OBJ, plan_sha256="sha256:" + PLAN,
                approver="owner@client", verification_class="authenticated_platform_record",
                request_id="req_abc123")
        r.update(over)
        return r

    def test_645_record_passes(self):
        self.write(self.rec())

    def test_645_record_wrong_plan_hash_refused(self):
        with self.assertRaises(self.sg.SafetyRefused):
            self.write(self.rec(plan_sha256="sha256:" + "c" * 64))
