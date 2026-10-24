#!/usr/bin/env python3
"""S75-T15: client-scoped identity persistence, as a cache of Notion.

Fixture only. No client workspace, credential or network call is used.
Run: python3 test_notion_store_s75_t15.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
SKILL = os.path.dirname(os.path.dirname(CORE))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from character_bible import identity  # noqa: E402
from character_library import cache as cache_mod  # noqa: E402
from character_library import notion_adapter  # noqa: E402
from character_library import notion_store as store_mod  # noqa: E402

FIXTURE = os.path.join(SKILL, "tests", "fixtures", "text_first_character.json")
NS_A = "fixture-client-a"
NS_B = "fixture-client-b"
CHAR = "chr-fixture-marcus"


def load_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def for_client(namespace):
    record = load_fixture()
    record["client_id"] = namespace
    return record


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s75-t15-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # a. a text identity is complete with no image anywhere
    def test_text_identity_saves_without_image(self):
        store = store_mod.NotionStore(self.root, NS_A)
        saved = store.put_identity(load_fixture())
        identity.validate_identity(saved)          # raises if damaged
        self.assertEqual(saved["reference_ids"], [])
        self.assertEqual(saved["draft_state"], "DRAFT_INCOMPLETE")
        self.assertEqual(saved["client_id"], NS_A)
        self.assertEqual(saved["local_cache"]["local_role"], "sync-state-cache")
        self.assertEqual(store.get_identity(CHAR), saved)

    # b. a later image updates the same identity, never a duplicate
    def test_image_attachment_updates_same_identity(self):
        store = store_mod.NotionStore(self.root, NS_A)
        saved = store.put_identity(load_fixture())
        self.assertEqual(len(store.identities()), 1)

        updated = store.attach_image(CHAR, "img-ref-001")
        self.assertEqual(updated["character_id"], saved["character_id"])
        self.assertEqual(updated["reference_ids"], ["img-ref-001"])
        self.assertEqual(updated["revision"], saved["revision"] + 1)
        self.assertEqual(len(store.identities()), 1)

        again = store.attach_image(CHAR, "img-ref-001")   # idempotent
        self.assertEqual(again["reference_ids"], ["img-ref-001"])
        self.assertEqual(again["revision"], updated["revision"])

        store.attach_image(CHAR, "img-ref-002")
        self.assertEqual(len(store.identities()), 1)
        self.assertEqual(store.get_identity(CHAR)["reference_ids"],
                         ["img-ref-001", "img-ref-002"])

    def test_image_never_creates_an_identity(self):
        store = store_mod.NotionStore(self.root, NS_A)
        with self.assertRaises(store_mod.StoreError):
            store.attach_image("chr-does-not-exist", "img-ref-003")
        self.assertEqual(store.identities(), [])

    # c. one client's library never resolves inside another client's
    def test_client_libraries_do_not_bleed(self):
        a = store_mod.NotionStore(self.root, NS_A)
        b = store_mod.NotionStore(self.root, NS_B)
        a.put_identity(load_fixture())

        self.assertIsNotNone(a.get_identity(CHAR))
        self.assertIsNone(b.get_identity(CHAR))
        self.assertEqual(b.identities(), [])

        b.put_identity(for_client(NS_B))
        self.assertEqual(a.get_identity(CHAR)["client_id"], NS_A)
        self.assertEqual(b.get_identity(CHAR)["client_id"], NS_B)

        with self.assertRaises(store_mod.StoreError):      # A's record into B
            b.put_identity(load_fixture())
        with self.assertRaises(store_mod.StoreError):      # A's registry into B
            b.save_registry({"client_namespace": NS_A,
                             "library_page_id": "lib-a",
                             "data_source_id": "ds-a"})
        self.assertIsNone(b.load_registry())

    def test_registry_persists_ids_through_the_adapter(self):
        store = store_mod.NotionStore(self.root, NS_A)
        registry = {"schema": notion_adapter.SCHEMA_REGISTRY,
                    "client_namespace": NS_A,
                    "connection_ref": "secure-connection-handle-only",
                    "library_page_id": "lib-a",
                    "data_source_id": "ds-a",
                    "catalog_revision": ""}
        store.save_registry(registry)
        self.assertEqual(store.load_registry(), registry)
        # the remote read path is the merged adapter, not a second client
        self.assertIs(store_mod.adapter.list_character_revisions,
                      notion_adapter.list_character_revisions)

    # d. approval is always an explicit, ordered step
    def test_draft_never_promotes_implicitly(self):
        store = store_mod.NotionStore(self.root, NS_A)
        store.put_identity(load_fixture())

        with self.assertRaises(store_mod.StoreError):      # skips a state
            store.promote(CHAR, "APPROVED")
        with self.assertRaises(store_mod.StoreError):      # not a step
            store.promote(CHAR, "DRAFT_INCOMPLETE")

        store.promote(CHAR, "DRAFT_COMPLETE")
        with self.assertRaises(store_mod.StoreError):      # approval without a receipt
            store.promote(CHAR, "APPROVED")

        approved = store.promote(CHAR, "APPROVED",
                                 approval={"approver": "client",
                                           "receipt_id": "receipt-001"})
        self.assertEqual(approved["draft_state"], "APPROVED")
        self.assertEqual(len(approved["approval_bindings"]), 1)
        self.assertEqual(approved["approval_bindings"][0]["approver"], "client")
        with self.assertRaises(store_mod.StoreError):      # already approved
            store.promote(CHAR, "APPROVED")

        implicit = dict(approved)
        implicit["draft_state"] = "DRAFT_COMPLETE"         # a save is not a transition
        with self.assertRaises(store_mod.StoreError):
            store.put_identity(implicit)

    def test_record_cannot_be_created_already_approved(self):
        store = store_mod.NotionStore(self.root, NS_A)
        record = load_fixture()
        record["draft_state"] = "APPROVED"
        with self.assertRaises(store_mod.StoreError):
            store.put_identity(record)

    # cache declaration and recovery
    def test_local_storage_declares_it_is_a_cache_of_notion(self):
        declared = cache_mod.describe()
        self.assertEqual(declared["source_of_truth"], "notion")
        self.assertEqual(declared["local_role"], "sync-state-cache")
        self.assertTrue(declared["local_is_cache"])

        store = store_mod.NotionStore(self.root, NS_A)
        store.put_identity(load_fixture())
        envelope = store.cache.load(store_mod._doc(CHAR))
        self.assertEqual(envelope["source_of_truth"], "notion")
        self.assertEqual(envelope["local_role"], "sync-state-cache")
        self.assertEqual(store.sync_state(CHAR, 1), "IN_SYNC")
        self.assertEqual(store.sync_state(CHAR, 2), "STALE")
        self.assertEqual(store.sync_state("chr-absent", 1), "MISSING")

    def test_missing_cache_is_rebuilt_from_notion_without_inventing(self):
        store = store_mod.NotionStore(self.root, NS_A)
        store.put_identity(load_fixture())
        self.assertTrue(store.cache.drop(store_mod._doc(CHAR)))
        self.assertIsNone(store.get_identity(CHAR))

        restored = store.restore_from_notion([load_fixture()])
        self.assertEqual(restored, [CHAR])
        self.assertEqual(store.get_identity(CHAR)["client_id"], NS_A)

        empty = store_mod.NotionStore(self.root, "fixture-client-empty")
        self.assertEqual(empty.restore_from_notion([]), [])
        self.assertEqual(empty.identities(), [])
        with self.assertRaises(cache_mod.CacheUnrecoverable):
            empty.cache.recover("identity-chr-ghost", None)


def receipt(over=None):
    """A receipt in its real shape, bound to this fixture character."""
    binding = {
        "kind": identity.RECEIPT_KIND,
        "receipt_id": "receipt-001",
        "approver": "client",
        "character_id": CHAR,
        "from_state": "DRAFT_COMPLETE",
        "to_state": "APPROVED",
    }
    binding.update(over or {})
    return binding


def with_bindings(bindings, state="APPROVED", namespace=NS_A):
    record = for_client(namespace)
    record["draft_state"] = state
    record["approval_bindings"] = bindings
    record.pop("content_digest", None)
    return record


class ForgedApprovalTest(unittest.TestCase):
    """A binding is a verified receipt or it is refused. Never a bare list."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s75-t15-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def store(self, namespace=NS_A):
        return store_mod.NotionStore(self.root, namespace)

    def refused(self, record, contains=None):
        """The save raises and NOTHING is stored."""
        store = self.store()
        with self.assertRaises(store_mod.StoreError) as caught:
            store.put_identity(record)
        self.assertIsNone(store.get_identity(record["character_id"]))
        if contains:
            self.assertIn(contains, str(caught.exception))
        return str(caught.exception)

    # --- the reported probes ---------------------------------------------

    def test_probe_list_of_junk_is_refused(self):
        self.refused(with_bindings([{"not": "a receipt"}]))

    def test_probe_empty_object_binding_is_refused(self):
        self.refused(with_bindings([{}]))

    def test_probe_hand_forged_receipt_is_refused(self):
        self.refused(with_bindings([receipt({"receipt_id": "forged-001"})]))
        # the shape a hand-written forgery takes: no kind, no binding to a record
        self.refused(with_bindings([{"from_state": "DRAFT_COMPLETE",
                                    "to_state": "APPROVED",
                                    "approver": "nobody",
                                    "receipt_id": "forged-005"}]))

    def test_probe_forged_receipt_parked_on_a_draft_is_refused(self):
        self.refused(with_bindings([receipt({"receipt_id": "forged-002"})],
                                  state="DRAFT_INCOMPLETE"))

    def test_a_save_never_stores_approved(self):
        message = self.refused(with_bindings([]))
        self.assertIn("never stores APPROVED", message)

    # --- type confusion on the binding -----------------------------------

    def test_binding_type_confusion_is_refused(self):
        for bogus in ("receipt-001", "receipt", {"receipt_id": "r"},
                      [["receipt-001"]], ["receipt-001"], [None], [False],
                      [0], [[]], [""], [set()], {"a": {"b": []}}):
            with self.subTest(binding=bogus):
                self.refused(with_bindings(bogus))

    def test_binding_with_unknown_keys_is_not_a_receipt(self):
        self.refused(with_bindings([receipt({"note": "hand written"})]))
        self.refused(with_bindings([receipt({"kind": "gift_card"})]))
        self.refused(with_bindings([receipt({"kind": None})]))
        self.refused(with_bindings([receipt({"character_id": ""})]))

    def test_binding_must_resolve_to_the_record_it_claims(self):
        self.refused(with_bindings([receipt({"character_id": "chr-someone-else"})]))
        self.refused(with_bindings([receipt({"from_state": "DRAFT_INCOMPLETE"})]))
        self.refused(with_bindings([receipt({"from_state": "APPROVED"})]))
        self.refused(with_bindings([receipt({"to_state": "DRAFT_COMPLETE"})]))
        self.refused(with_bindings([receipt({"approver": "   "})]))
        self.refused(with_bindings([receipt({"receipt_id": 7})]))
        self.refused(with_bindings([receipt(), receipt({"receipt_id": "receipt-001"})]))

    def test_a_draft_carries_no_receipt_at_all(self):
        self.refused(with_bindings([receipt()], state="DRAFT_COMPLETE"))
        self.refused(with_bindings([receipt()], state="DRAFT_INCOMPLETE"))

    # --- validate_identity rejects the binding itself --------------------

    def sealed(self, bindings, state="APPROVED"):
        return identity.seal_identity(with_bindings(bindings, state))

    def test_validate_identity_rejects_a_malformed_binding(self):
        for bogus in ([{"not": "a receipt"}], [{}], [receipt({"kind": "cash"})],
                      [receipt({"character_id": "chr-other"})],
                      [receipt({"from_state": "DRAFT_INCOMPLETE"})],
                      ["receipt-001"], "receipt-001", {"receipt_id": "r"},
                      [["r"]], [[]], [None], [False]):
            with self.subTest(binding=bogus):
                with self.assertRaises(identity.IdentityDefect) as caught:
                    identity.validate_identity(self.sealed(bogus))
                self.assertTrue(caught.exception.defects)

    def test_validate_identity_accepts_only_a_resolved_receipt(self):
        identity.validate_identity(self.sealed([receipt()]))
        with self.assertRaises(identity.IdentityDefect):
            identity.validate_identity(self.sealed([]))  # approved, no receipt

    # --- the honest path still works -------------------------------------

    def test_promotion_writes_one_resolvable_receipt(self):
        store = self.store()
        store.put_identity(load_fixture())
        store.promote(CHAR, "DRAFT_COMPLETE")
        approved = store.promote(CHAR, "APPROVED",
                                approval={"approver": "client",
                                          "receipt_id": "receipt-001"})
        self.assertEqual(approved["draft_state"], "APPROVED")
        self.assertEqual(approved["approval_bindings"], [receipt()])
        self.assertIsNone(identity.resolve_receipt(approved["approval_bindings"][0],
                                                   approved))
        identity.validate_identity(approved)

    def test_a_saved_approved_record_cannot_gain_or_lose_a_receipt(self):
        store = self.store()
        store.put_identity(load_fixture())
        store.promote(CHAR, "DRAFT_COMPLETE")
        approved = store.promote(CHAR, "APPROVED",
                                 approval={"approver": "client",
                                           "receipt_id": "receipt-001"})

        for bogus in (with_bindings([receipt({"receipt_id": "forged-003"})]),
                      with_bindings([receipt(), receipt({"receipt_id": "extra"})]),
                      with_bindings([])):
            with self.subTest(bindings=bogus["approval_bindings"]):
                with self.assertRaises(store_mod.StoreError):
                    store.put_identity(bogus)
                self.assertEqual(store.get_identity(CHAR), approved)

        # the one receipt the promotion wrote is kept exactly, never re-minted
        self.assertEqual(store.put_identity(with_bindings([receipt()])), approved)

    def test_restore_refuses_a_notion_record_with_a_forged_receipt(self):
        store = self.store()
        hand_forged = {"from_state": "DRAFT_COMPLETE", "to_state": "APPROVED",
                       "approver": "nobody", "receipt_id": "forged-004"}
        for bogus in ([{"not": "a receipt"}], [{}], [hand_forged],
                      [receipt({"character_id": "chr-someone-else"})]):
            with self.subTest(binding=bogus):
                with self.assertRaises(store_mod.StoreError):
                    store.restore_from_notion([with_bindings(bogus)])
                self.assertEqual(store.identities(), [])

    def test_restore_accepts_a_notion_record_with_a_real_receipt(self):
        source = self.store()
        source.put_identity(load_fixture())
        source.promote(CHAR, "DRAFT_COMPLETE")
        approved = source.promote(CHAR, "APPROVED",
                                  approval={"approver": "client",
                                            "receipt_id": "receipt-001"})
        self.assertTrue(source.cache.drop(store_mod._doc(CHAR)))

        target = self.store("fixture-client-restored")
        record = dict(approved)
        record["client_id"] = "fixture-client-restored"
        self.assertEqual(target.restore_from_notion([record]), [CHAR])
        self.assertEqual(target.get_identity(CHAR)["approval_bindings"], [receipt()])

    # --- the rest of the row stays intact --------------------------------

    def test_no_credential_is_hardcoded_in_the_store(self):
        store = self.store()
        registry = {"schema": notion_adapter.SCHEMA_REGISTRY,
                    "client_namespace": NS_A,
                    "connection_ref": "secure-connection-handle-only",
                    "library_page_id": "lib-a",
                    "data_source_id": "ds-a",
                    "catalog_revision": ""}
        store.save_registry(registry)
        self.assertEqual(store.load_registry(), registry)   # a handle, never a token

        with self.assertRaises(notion_adapter.DiscoveryError):
            store.save_registry({**registry, "notion_token": "ntn_deadbeef"})

        for name in ("notion_store.py", "cache.py"):
            with open(os.path.join(HERE, name), encoding="utf-8") as f:
                source = f.read()
            self.assertNotRegex(source, r"ntn_[A-Za-z0-9]|sk-[A-Za-z0-9]{8}|"
                                        r"secret_[A-Za-z0-9]|Bearer\s+\S+")

    def test_adapter_is_reused_and_namespaces_stay_separate(self):
        self.assertIs(store_mod.adapter.list_character_revisions,
                      notion_adapter.list_character_revisions)
        a, b = self.store(NS_A), self.store(NS_B)
        a.put_identity(load_fixture())
        self.assertIsNone(b.get_identity(CHAR))
        self.assertEqual(b.identities(), [])
        self.assertIsNone(b.load_registry())
        self.assertRaises(store_mod.StoreError, b.put_identity, load_fixture())


if __name__ == "__main__":
    unittest.main(verbosity=2)
