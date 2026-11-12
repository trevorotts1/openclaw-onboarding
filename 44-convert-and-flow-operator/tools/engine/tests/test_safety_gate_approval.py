"""S44-16: the write gate needs a verified approval record, not an env var or a ZHC- name.

Run: python3 -m pytest 44-convert-and-flow-operator/tools/engine/tests/test_safety_gate_approval.py -q
"""
from __future__ import annotations

import importlib
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

LOC, PLAN, ACTION, OBJ = "LOC123", "a" * 64, "workflows.build", "Black Friday Promo"
URL = "https://backend.leadconnectorhq.com/workflow/LOC123"


def _rec(**over):
    rec = {
        "approval_id": "appr_12345678", "kind": "automation_write", "location_id": LOC,
        "action": ACTION, "object_key": OBJ, "plan_sha256": PLAN, "approver": "owner@client",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "revoked": False, "verification_class": "authenticated_platform_record",
    }
    rec.update(over)
    return rec


class _Base(unittest.TestCase):
    ENV = {
        "CAF_ALLOWED_LOCATION_IDS": LOC, "CAF_WRITE_ACTION": ACTION, "CAF_PLAN_SHA256": PLAN,
        "CAF_APPROVAL_ID": "appr_12345678",
    }

    def setUp(self):
        for k in ("CAF_DRY_RUN", "CAF_APPROVAL_TOKEN", "CAF_DRAFT_ONLY", "CAF_APPROVAL_ID",
                  "CAF_WRITE_ACTION", "CAF_PLAN_SHA256", "CAF_OBJECT_KEY", "MISSION_CONTROL_URL",
                  "MC_API_TOKEN", "GHL_LOCATION_ID"):
            os.environ.pop(k, None)
        os.environ.update(self.ENV)
        mod = "cli_anything.gohighlevel.utils.safety_gate"
        sys.modules.pop(mod, None)
        self.sg = importlib.import_module(mod)

    def tearDown(self):
        for k in list(self.ENV) + ["CAF_APPROVAL_TOKEN", "CAF_DRAFT_ONLY", "GHL_LOCATION_ID", "CAF_OBJECT_KEY"]:
            os.environ.pop(k, None)

    def write(self, rec, **kw):
        kw.setdefault("workflow_name", OBJ)
        with patch.object(self.sg, "_fetch_record", return_value=rec):
            self.sg.check_write("POST", URL, {}, location_id=LOC, **kw)


class TestWriteNeedsRecord(_Base):
    def test_matching_automation_write_record_passes(self):
        self.write(_rec())

    def test_env_token_alone_is_insufficient(self):
        os.environ["CAF_APPROVAL_TOKEN"] = "any-non-empty-value"
        os.environ.pop("CAF_APPROVAL_ID")
        with self.assertRaises(self.sg.SafetyRefused):
            self.sg.check_write("POST", URL, {}, location_id=LOC, workflow_name=OBJ)

    def test_zhc_name_alone_is_insufficient(self):
        os.environ.pop("CAF_APPROVAL_ID")
        with self.assertRaises(self.sg.SafetyRefused):
            self.sg.check_write("POST", URL, {}, location_id=LOC, workflow_name="ZHC-promo")

    def test_approval_id_without_command_center_is_refused(self):
        # id set, no MISSION_CONTROL_URL/MC_API_TOKEN: real _fetch_record must fail closed
        with self.assertRaises(self.sg.SafetyRefused):
            self.sg.check_write("POST", URL, {}, location_id=LOC, workflow_name=OBJ)

    def test_each_binding_is_enforced(self):
        for field, bad in (
            ("plan_sha256", "b" * 64), ("action", "products.create"), ("approver", ""),
            ("location_id", "OTHERLOC"), ("object_key", "Other Promo"), ("kind", "publish"),
            ("revoked", True), ("verification_class", "recorded_consent_not_cryptographically_sealed"),
            ("expires_at", (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()),
        ):
            with self.subTest(field=field), self.assertRaises(self.sg.SafetyRefused):
                self.write(_rec(**{field: bad}))

    def test_missing_field_refused(self):
        rec = _rec()
        del rec["approver"]
        with self.assertRaises(self.sg.SafetyRefused):
            self.write(rec)

    def test_unknown_plan_or_action_refused(self):
        os.environ.pop("CAF_PLAN_SHA256")
        with self.assertRaises(self.sg.SafetyRefused):
            self.write(_rec())

    def test_get_still_passes(self):
        self.sg.check_write("GET", URL, None, location_id=None)

    def test_object_key_env_covers_every_write_of_one_plan(self):
        os.environ["CAF_OBJECT_KEY"] = OBJ
        self.write(_rec(), workflow_name="ZHC-Folder")
        self.write(_rec(), workflow_name="")

    def test_object_key_env_mismatch_refused(self):
        os.environ["CAF_OBJECT_KEY"] = OBJ
        with self.assertRaises(self.sg.SafetyRefused):
            self.write(_rec(object_key="Other Promo"), workflow_name="Other Promo")


class TestDraftOff(_Base):
    def setUp(self):
        super().setUp()
        os.environ["GHL_LOCATION_ID"] = LOC
        os.environ["CAF_OBJECT_KEY"] = OBJ

    def flag(self, rec):
        os.environ["CAF_DRAFT_ONLY"] = "false"
        with patch.object(self.sg, "_fetch_record", return_value=rec):
            return self.sg.draft_only_active_flag()

    def test_default_stays_draft(self):
        self.assertFalse(self.sg.draft_only_active_flag())

    def test_env_toggle_alone_stays_draft(self):
        os.environ["CAF_DRAFT_ONLY"] = "false"
        self.assertFalse(self.sg.draft_only_active_flag())

    def test_automation_write_record_does_not_publish(self):
        self.assertFalse(self.flag(_rec()))

    def test_publish_record_goes_live(self):
        self.assertTrue(self.flag(_rec(kind="publish", action="publish")))

    def test_publish_record_wrong_plan_stays_draft(self):
        self.assertFalse(self.flag(_rec(kind="publish", action="publish", plan_sha256="c" * 64)))


MSG_URL = "https://services.leadconnectorhq.com/conversations/messages"
OWNER = "ownerContact001"


class TestOwnerNoticeExemption(_Base):
    """A notice to the owner's OWN contact needs no approval record; everything else still does."""

    def setUp(self):
        super().setUp()
        for k in ("CAF_APPROVAL_ID", "CAF_WRITE_ACTION", "CAF_PLAN_SHA256"):
            os.environ.pop(k, None)           # the real failure: action and plan unknown
        os.environ["CAF_OWNER_CONTACT_ID"] = OWNER
        self.addCleanup(os.environ.pop, "CAF_OWNER_CONTACT_ID", None)

    def send(self, payload, url=MSG_URL, method="POST", loc=LOC):
        with patch.object(self.sg, "_fetch_record", side_effect=AssertionError("no record may be fetched")) as f:
            self.sg.check_write(method, url, payload, location_id=loc)
        return f

    def refused(self, payload, **kw):
        with self.assertRaises(self.sg.SafetyRefused):
            with patch.object(self.sg, "_fetch_record", side_effect=self.sg.SafetyRefused("no record")):
                self.sg.check_write(kw.get("method", "POST"), kw.get("url", MSG_URL), payload,
                                    location_id=kw.get("loc", LOC))

    def test_sms_to_owner_contact_passes_without_a_record(self):
        self.send({"type": "SMS", "contactId": OWNER, "message": "Your week is ready."})

    def test_email_to_owner_contact_passes_without_a_record(self):
        self.send({"type": "Email", "contactId": OWNER, "message": "Hi", "subject": "Notice"})

    def test_other_recipient_still_needs_approval(self):
        self.refused({"type": "SMS", "contactId": "someoneElse", "message": "Sale!"})

    def test_unset_owner_contact_exempts_nothing(self):
        os.environ.pop("CAF_OWNER_CONTACT_ID")
        self.refused({"type": "SMS", "contactId": OWNER, "message": "x"})
        os.environ["CAF_OWNER_CONTACT_ID"] = "   "
        self.refused({"type": "SMS", "contactId": OWNER, "message": "x"})

    def test_other_message_types_and_endpoints_are_not_exempt(self):
        self.refused({"type": "WhatsApp", "contactId": OWNER, "message": "x"})
        self.refused({"type": "SMS", "contactId": OWNER, "message": "x"}, url="https://x.test/contacts/")
        self.refused({"type": "SMS", "contactId": OWNER, "message": "x"}, url=MSG_URL + "/outbound")
        self.refused({"type": "SMS", "contactId": OWNER, "message": "x"}, url=MSG_URL + "?contactId=other")
        self.refused({"type": "SMS", "contactId": OWNER, "message": "x"}, method="PUT")
        self.refused({"type": "SMS", "contactId": OWNER, "message": "x"}, method="DELETE")

    def test_any_redirect_or_fan_out_field_defeats_the_exemption(self):
        for extra in ({"conversationId": "c1"}, {"toNumber": "+15555550100"}, {"emailTo": ["a@b.c"]},
                      {"emailCc": ["a@b.c"]}, {"emailBcc": ["a@b.c"]}, {"contactIds": ["x"]},
                      {"recipients": ["x"]}):
            self.refused({"type": "SMS", "contactId": OWNER, "message": "x", **extra})

    def test_contact_must_match_exactly_and_be_a_string(self):
        for bad in (OWNER + "x", OWNER.upper(), "", None, [OWNER], 7):
            self.refused({"type": "SMS", "contactId": bad, "message": "x"})
        self.refused(None)
        self.refused("not a dict")

    def test_location_still_has_to_be_whitelisted_and_match(self):
        with self.assertRaises(self.sg.SafetyRefused):
            self.sg.check_write("POST", MSG_URL, {"type": "SMS", "contactId": OWNER}, location_id="OTHERLOC")
        with self.assertRaises(self.sg.SafetyRefused):
            self.sg.check_write("POST", MSG_URL, {"type": "SMS", "contactId": OWNER}, location_id=None)
        self.refused({"type": "SMS", "contactId": OWNER, "locationId": "DIFFERENT"})
        self.send({"type": "SMS", "contactId": OWNER, "locationId": LOC})

    def test_dry_run_and_empty_whitelist_rules_come_first(self):
        os.environ.pop("CAF_ALLOWED_LOCATION_IDS")
        with self.assertRaises(self.sg.SafetyRefused):
            self.sg.check_write("POST", MSG_URL, {"type": "SMS", "contactId": OWNER}, location_id=LOC)

    def test_owner_exemption_does_not_open_other_writes(self):
        self.refused({"name": "workflow", "contactId": OWNER}, url="https://backend.leadconnectorhq.com/workflow/LOC123")


if __name__ == "__main__":
    unittest.main()
