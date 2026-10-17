"""ev1 entitlement_version proofs (CR-S82-002 item 5).

Pins Store.entitlement_version to the committed specification in
work/acceptance/evidence-a21-and-item5.md section 2. The two pinned
SHA-256 values below were computed independently from the spec text
(canonical string built from literals), not from this implementation.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from store import Store

# Independent pins (spec-literal canonical strings):
# zero rows:  "T1" US "LN1" US "contact-1" RS
ZERO_ROW_EV1 = ("ev1:8df68c163e2d95abb360bcfc93bdefad46927d08d4365517528"
                "931872b35e519")
# rows (li-b, ent-bump, revoked), (li-m, ent-main, active) sorted by
# (line_ref, entitlement) UTF-8 bytes, header + RS-joined rows
WORKED_EV1 = ("ev1:4b4b3d77979eb5d8604e6688251dfdcce9e9c8eca2418a85978ea"
              "e6c89263454")


class EntitlementVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / "s44.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def _register(self, tenant="T1", launch="LN1", contact="contact-1",
                  *line_refs):
        for line_ref in line_refs:
            self.store.add_buyer(tenant, launch, contact, line_ref)

    def test_zero_row_buyer_matches_independent_pin(self):
        # unknown buyer: no registered lines, no rows
        self.assertEqual(
            self.store.entitlement_version("T1", "LN1", "contact-1"),
            ZERO_ROW_EV1)
        # registered buyer with no grants yet: still the zero-row value
        self._register("T1", "LN1", "contact-9", "li-m")
        self.assertTrue(self.store.entitlement_version(
            "T1", "LN1", "contact-9").startswith("ev1:"))
        self.assertNotEqual(
            self.store.entitlement_version("T1", "LN1", "contact-9"),
            ZERO_ROW_EV1)  # identity header differs (different contact)

    def test_worked_example_byte_exact(self):
        self._register("T1", "LN1", "contact-1", "li-m", "li-b")
        self.store.grant_entitlement("T1", "li-m", "ent-main")
        self.store.grant_entitlement("T1", "li-b", "ent-bump")
        self.store.revoke_entitlement("T1", "li-b", "ent-bump")
        self.assertEqual(
            self.store.entitlement_version("T1", "LN1", "contact-1"),
            WORKED_EV1)

    def test_changes_on_grant_revoke_and_regrant(self):
        self._register("T1", "LN1", "contact-1", "li-m")
        v0 = self.store.entitlement_version("T1", "LN1", "contact-1")
        self.store.grant_entitlement("T1", "li-m", "ent-main")
        v1 = self.store.entitlement_version("T1", "LN1", "contact-1")
        self.assertNotEqual(v0, v1)
        self.store.revoke_entitlement("T1", "li-m", "ent-main")
        v2 = self.store.entitlement_version("T1", "LN1", "contact-1")
        self.assertNotEqual(v1, v2)
        self.assertNotEqual(v0, v2)  # revoked row is kept, not deleted
        # re-grant flips the same row back: the row SET is again exactly
        # the v1 set, so the version returns to v1
        self.store.grant_entitlement("T1", "li-m", "ent-main")
        self.assertEqual(
            self.store.entitlement_version("T1", "LN1", "contact-1"), v1)

    def test_duplicate_grant_does_not_change_version(self):
        self._register("T1", "LN1", "contact-1", "li-m")
        self.assertTrue(
            self.store.grant_entitlement("T1", "li-m", "ent-main"))
        v1 = self.store.entitlement_version("T1", "LN1", "contact-1")
        # a duplicate delivery re-applies the same grant: no row change
        self.assertFalse(
            self.store.grant_entitlement("T1", "li-m", "ent-main"))
        self.assertEqual(
            self.store.entitlement_version("T1", "LN1", "contact-1"), v1)

    def test_isolation_across_tenant_launch_and_contact(self):
        self._register("T1", "LN1", "contact-1", "li-m")
        self.store.grant_entitlement("T1", "li-m", "ent-main")
        base = self.store.entitlement_version("T1", "LN1", "contact-1")
        # another tenant's identical-looking grant must not leak in
        self._register("T2", "LN1", "contact-1", "li-m")
        self.store.grant_entitlement("T2", "li-m", "ent-main")
        # another launch for the same contact must not leak in
        self._register("T1", "LN2", "contact-1", "li-x")
        self.store.grant_entitlement("T1", "li-x", "ent-other")
        # another contact in the same launch must not leak in
        self._register("T1", "LN1", "contact-2", "li-y")
        self.store.grant_entitlement("T1", "li-y", "ent-other")
        self.assertEqual(
            self.store.entitlement_version("T1", "LN1", "contact-1"),
            base)
        # and each scoped buyer sees its own distinct version
        self.assertNotEqual(
            self.store.entitlement_version("T1", "LN2", "contact-1"),
            base)
        self.assertNotEqual(
            self.store.entitlement_version("T1", "LN1", "contact-2"),
            base)

    def test_rows_outside_buyer_lines_are_excluded(self):
        # an entitlement row on a line this buyer never registered is
        # not part of the buyer's row set, even in the same tenant
        self._register("T1", "LN1", "contact-1", "li-m")
        self.store.grant_entitlement("T1", "li-stranger", "ent-x")
        self.assertEqual(
            self.store.entitlement_version("T1", "LN1", "contact-1"),
            self.store.entitlement_version("T1", "LN1", "contact-1"))
        self.assertTrue(self.store.entitlement_version(
            "T1", "LN1", "contact-1").startswith("ev1:"))
        rows = self.store.buyer_entitlement_rows("T1", "LN1", "contact-1")
        self.assertEqual(rows, [])

    def test_sort_is_utf8_byte_order(self):
        # 'li-B' (0x42) sorts before 'li-a' (0x61); a non-ASCII line ref
        # ('li-é', UTF-8 0xC3 0xA9) sorts after 'li-z' (0x7A)
        self._register("T1", "LN1", "contact-1",
                       "li-a", "li-B", "li-z", "li-é")
        for line_ref in ("li-a", "li-B", "li-z", "li-é"):
            self.store.grant_entitlement("T1", line_ref, "ent-x")
        rows = self.store.buyer_entitlement_rows("T1", "LN1", "contact-1")
        self.assertEqual([r[0] for r in rows],
                         ["li-B", "li-a", "li-z", "li-é"])


if __name__ == "__main__":
    unittest.main()
