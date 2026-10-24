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


if __name__ == "__main__":
    unittest.main(verbosity=2)
