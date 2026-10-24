#!/usr/bin/env python3
"""Tests for tenant_identity.py (T-11, DATA-CONTRACTS 1).

Run from the skill root:
  python3 -m unittest discover -s tools/tests -p 'test_*.py'
or:
  python3 tools/tests/test_tenant_identity.py
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import tenant_identity as ti  # noqa: E402


class IdentityTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self._tmp.name, "identity.sqlite3")
        self.ident = ti.TenantIdentity(self.db)
        self.ident.register_tenant("tenant-a", "Tenant A")
        self.ident.register_tenant("tenant-b", "Tenant B")
        self.cid = self.ident.bind(
            "tenant-a",
            [("fb_psid", "fb-100", True), ("email", "Person@Example.com", True)],
        )

    def tearDown(self):
        self._tmp.cleanup()


class TestResolution(IdentityTestBase):
    def test_cross_channel_same_tenant_one_canonical_contact(self):
        cid_ig = self.ident.bind(
            "tenant-a",
            [("ig_psid", "ig-200", True), ("email", "person@example.com", True)],
        )
        self.assertEqual(self.cid, cid_ig)
        self.assertEqual(
            self.ident.resolve_channel("tenant-a", "fb", "fb-100"), self.cid
        )
        self.assertEqual(
            self.ident.resolve_channel("tenant-a", "instagram", "ig-200"),
            self.cid,
        )
        self.assertEqual(
            self.ident.resolve("tenant-a", "email", "PERSON@example.com"),
            self.cid,
        )

    def test_canonical_id_is_deterministic_and_tenant_scoped(self):
        again = ti.canonical_contact_id_for(
            "tenant-a", "email", "person@example.com"
        )
        other = ti.canonical_contact_id_for(
            "tenant-b", "email", "person@example.com"
        )
        self.assertEqual(again, self.cid)
        self.assertNotEqual(other, self.cid)

    def test_unknown_identifier_resolves_to_none(self):
        self.assertIsNone(
            self.ident.resolve("tenant-a", "email", "missing@example.com")
        )

    def test_phone_is_not_case_folded(self):
        cid = self.ident.bind(
            "tenant-a", [("sms_number", "+15551234567", True)]
        )
        self.assertEqual(
            self.ident.resolve_channel("tenant-a", "sms", "+15551234567"),
            cid,
        )


class TestCrossTenantNegative(IdentityTestBase):
    def test_same_person_in_two_tenants_never_resolves_together(self):
        shared_email = "person@example.com"
        cid_b = self.ident.bind(
            "tenant-b",
            [("ig_psid", "ig-900", True), ("email", shared_email, True)],
        )

        self.assertNotEqual(self.cid, cid_b)
        self.assertEqual(
            self.ident.resolve("tenant-a", "email", shared_email), self.cid
        )
        self.assertEqual(
            self.ident.resolve("tenant-b", "email", shared_email), cid_b
        )
        # Channel refs from one tenant do not resolve in the other.
        self.assertIsNone(
            self.ident.resolve_channel("tenant-b", "fb", "fb-100")
        )
        self.assertIsNone(
            self.ident.resolve_channel("tenant-a", "ig", "ig-900")
        )

    def test_verify_rejects_another_tenants_contact(self):
        cid_b = self.ident.bind(
            "tenant-b", [("fb_psid", "fb-b", True)]
        )
        with self.assertRaises(ti.VerificationError) as raised:
            self.ident.verify("tenant-a", cid_b)
        self.assertIn("another tenant", str(raised.exception))
        with self.assertRaises(ti.VerificationError):
            self.ident.verify("tenant-b", self.cid)
        self.assertIsNone(self.ident.contact("tenant-a", cid_b))
        self.assertIsNone(self.ident.contact("tenant-b", self.cid))

    def test_merge_cannot_cross_tenants(self):
        cid_b = self.ident.bind(
            "tenant-b", [("fb_psid", "fb-b", True)]
        )
        with self.assertRaises(ti.VerificationError):
            self.ident.merge("tenant-a", cid_b, self.cid)


class TestVerificationRejections(IdentityTestBase):
    def test_unknown_tenant_rejected_everywhere(self):
        with self.assertRaises(ti.UnknownTenant):
            self.ident.bind("tenant-z", [("email", "x@y.z", True)])
        with self.assertRaises(ti.UnknownTenant):
            self.ident.resolve("tenant-z", "email", "x@y.z")
        with self.assertRaises(ti.UnknownTenant):
            self.ident.verify("tenant-z", self.cid)
        with self.assertRaises(ti.UnknownTenant):
            self.ident.bind("", [("email", "x@y.z", True)])
        with self.assertRaises(ti.UnknownTenant):
            self.ident.bind(None, [("email", "x@y.z", True)])

    def test_empty_contact_rejected(self):
        with self.assertRaises(ti.VerificationError):
            self.ident.bind("tenant-a", [])
        with self.assertRaises(ti.VerificationError):
            self.ident.bind("tenant-a", [("email", "   ", True)])
        with self.assertRaises(ti.VerificationError):
            self.ident.verify("tenant-a", "")
        with self.assertRaises(ti.VerificationError):
            self.ident.verify("tenant-a", None)

    def test_public_placement_never_carries_a_canonical_contact(self):
        with self.assertRaises(ti.VerificationError) as raised:
            self.ident.bind(
                "tenant-a",
                [("fb_psid", "fb-777", True)],
                provenance=ti.PROVENANCE_PUBLIC_PLACEMENT,
            )
        self.assertIn("public placement", str(raised.exception))

    def test_verify_rejects_a_placement_sourced_row(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "INSERT INTO contacts (tenant_id, canonical_contact_id,"
                " provenance, suppression, unknown_sends, reminder_total,"
                " created_at) VALUES (?, ?, ?, 'none', 0, 0, 0)",
                ("tenant-a", "cc_placement", ti.PROVENANCE_PUBLIC_PLACEMENT),
            )
        with self.assertRaises(ti.VerificationError) as raised:
            self.ident.verify("tenant-a", "cc_placement")
        self.assertIn("public placement", str(raised.exception))

    def test_contact_without_verified_identifier_rejected(self):
        with self.assertRaises(ti.VerificationError) as raised:
            self.ident.bind("tenant-a", [("phone", "+15550000000", False)])
        self.assertIn("verified", str(raised.exception))


class TestUnverifiedAndMerge(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self._tmp.name, "identity.sqlite3")
        self.ident = ti.TenantIdentity(self.db)
        self.ident.register_tenant("tenant-a")

    def tearDown(self):
        self._tmp.cleanup()

    def test_unverified_claim_cannot_reconcile(self):
        first = self.ident.bind(
            "tenant-a",
            [("fb_psid", "fb-1", True), ("email", "a@example.com", True)],
        )
        second = self.ident.bind(
            "tenant-a",
            [("ig_psid", "ig-1", True), ("email", "a@example.com", False)],
        )
        self.assertNotEqual(first, second)
        self.assertEqual(
            self.ident.resolve("tenant-a", "email", "a@example.com"), first
        )
        # The unverified claim did not move the verified email row.
        self.assertEqual(
            self.ident.resolve("tenant-a", "ig_psid", "ig-1"), second
        )
        self.assertEqual(
            self.ident.resolve("tenant-a", "email", "a@example.com", verified_only=False),
            first,
        )

    def test_bind_merges_when_two_verified_identifiers_join_two_contacts(self):
        by_facebook = self.ident.bind(
            "tenant-a", [("fb_psid", "fb-1", True)]
        )
        by_phone = self.ident.bind(
            "tenant-a",
            [("phone", "+15551112222", True), ("ig_psid", "ig-1", True)],
        )
        self.assertNotEqual(by_facebook, by_phone)
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "UPDATE contacts SET unknown_sends = 2 WHERE tenant_id = ?"
                " AND canonical_contact_id = ?",
                ("tenant-a", by_facebook),
            )
            conn.execute(
                "UPDATE contacts SET unknown_sends = 5 WHERE tenant_id = ?"
                " AND canonical_contact_id = ?",
                ("tenant-a", by_phone),
            )

        # A verified FB id and a verified phone id now prove one person.
        merged = self.ident.bind(
            "tenant-a",
            [("fb_psid", "fb-1", True), ("phone", "+15551112222", True)],
        )
        expected = min(by_facebook, by_phone)
        retired = max(by_facebook, by_phone)
        self.assertEqual(merged, expected)
        self.assertIsNone(self.ident.contact("tenant-a", retired))
        self.assertEqual(self.ident.verify("tenant-a", expected)["unknown_sends"], 7)
        types = {
            i["ident_type"]
            for i in self.ident.identifiers("tenant-a", expected)
        }
        self.assertEqual(types, {"fb_psid", "phone", "ig_psid"})

    def test_merge_preserves_stricter_suppression_and_totals(self):
        first = self.ident.bind(
            "tenant-a",
            [("fb_psid", "fb-1", True), ("email", "a@example.com", True)],
        )
        second = self.ident.bind(
            "tenant-a",
            [("ig_psid", "ig-1", True), ("phone", "+15550001111", True)],
        )
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "UPDATE contacts SET suppression = ?, unknown_sends = ?,"
                " reminder_total = ? WHERE tenant_id = ? AND"
                " canonical_contact_id = ?",
                (ti.SUPPRESSION_GLOBAL_STOP, 2, 3, "tenant-a", first),
            )
            conn.execute(
                "UPDATE contacts SET suppression = ?, unknown_sends = ?,"
                " reminder_total = ? WHERE tenant_id = ? AND"
                " canonical_contact_id = ?",
                (ti.SUPPRESSION_CHANNEL_OPT_OUT, 5, 1, "tenant-a", second),
            )
        target = self.ident.merge("tenant-a", second, first, "verified match")
        self.assertEqual(target, first)
        contact = self.ident.verify("tenant-a", first)
        self.assertEqual(contact["suppression"], ti.SUPPRESSION_GLOBAL_STOP)
        self.assertEqual(contact["unknown_sends"], 7)
        self.assertEqual(contact["reminder_total"], 4)
        self.assertIsNone(self.ident.contact("tenant-a", second))
        types = {i["ident_type"] for i in self.ident.identifiers("tenant-a", first)}
        self.assertEqual(types, {"fb_psid", "email", "ig_psid", "phone"})


if __name__ == "__main__":
    unittest.main()
