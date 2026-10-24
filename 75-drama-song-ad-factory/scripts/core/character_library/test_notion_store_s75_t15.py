#!/usr/bin/env python3
"""S75-T15: client-scoped identity persistence, as a cache of Notion.

Fixture only. No client workspace, credential or network call is used.
Run: python3 test_notion_store_s75_t15.py
"""
import json
import os
import shutil
import subprocess
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
    """A receipt in its real shape, written out by hand. No mint, no promotion."""
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


def minted(over=None):
    """The receipt the explicit promotion step mints, mint mark and all.

    This is the ONLY way to get a receipt the store will accept, and it is the
    same call ``promote()`` makes.
    """
    fields = receipt(over)
    fields.pop(identity.MINT_FIELD, None)
    return identity.mint_receipt(fields)


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
        identity.validate_identity(self.sealed([minted()]))
        with self.assertRaises(identity.IdentityDefect):
            identity.validate_identity(self.sealed([]))  # approved, no receipt
        # a receipt written out by hand has no mint mark and never resolves
        with self.assertRaises(identity.IdentityDefect):
            identity.validate_identity(self.sealed([receipt()]))

    # --- the honest path still works -------------------------------------

    def test_promotion_writes_one_resolvable_receipt(self):
        store = self.store()
        store.put_identity(load_fixture())
        store.promote(CHAR, "DRAFT_COMPLETE")
        approved = store.promote(CHAR, "APPROVED",
                                approval={"approver": "client",
                                          "receipt_id": "receipt-001"})
        self.assertEqual(approved["draft_state"], "APPROVED")
        self.assertEqual(approved["approval_bindings"], [minted()])
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
        self.assertEqual(store.put_identity(with_bindings([minted()])), approved)
        # a hand-written copy of that same receipt is still refused
        with self.assertRaises(store_mod.StoreError):
            store.put_identity(with_bindings([receipt()]))
        self.assertEqual(store.get_identity(CHAR), approved)

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
        self.assertEqual(target.get_identity(CHAR)["approval_bindings"], [minted()])

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


def tree_bytes(root):
    """Every byte on disk under the cache root, keyed by relative path."""
    found = {}
    for base, _dirs, names in os.walk(root):
        for name in sorted(names):
            path = os.path.join(base, name)
            with open(path, "rb") as f:
                found[os.path.relpath(path, root)] = f.read()
    return found


class LyingStr(str):
    """A str whose __eq__ always says yes. Refused by exact type, never asked."""

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    def __hash__(self):
        return hash(str(self))


class LyingDict(dict):
    """A dict whose get() always reports the field the caller wishes it had."""

    def get(self, key, default=None):
        if key in ("kind", "draft_state"):
            return {"kind": identity.RECEIPT_KIND,
                    "draft_state": "APPROVED"}[key]
        return dict.get(self, key, default)


class LyingList(list):
    """A list that reports itself empty while holding a forged receipt."""

    def __bool__(self):
        return False

    def __len__(self):
        return 0


class MintMarkTest(unittest.TestCase):
    """Round three: a receipt is a receipt only when the system minted it."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s75-t15-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def store(self, namespace=NS_A):
        return store_mod.NotionStore(self.root, namespace)

    def approved_record(self, bindings):
        return identity.seal_identity(with_bindings(bindings))

    # --- 1. a hand-built receipt, promote() never called ------------------

    def test_hand_built_receipt_never_resolves_and_never_reaches_disk(self):
        hand_built = receipt({"receipt_id": "rcp-HANDWRITTEN-NOT-MINTED"})
        record = with_bindings([hand_built])
        self.assertIsNotNone(identity.resolve_receipt(
            hand_built, identity.seal_identity(record)))
        with self.assertRaises(identity.IdentityDefect):
            identity.validate_identity(identity.seal_identity(record))

        store = self.store()
        before = tree_bytes(self.root)
        with self.assertRaises(store_mod.StoreError) as caught:
            store.restore_from_notion([record])
        self.assertIn("mint", str(caught.exception))
        self.assertEqual(tree_bytes(self.root), before)   # zero side effects
        self.assertEqual(store.identities(), [])
        self.assertNotIn(b"rcp-HANDWRITTEN-NOT-MINTED",
                         b"".join(tree_bytes(self.root).values()))

        with self.assertRaises(store_mod.StoreError):
            store.put_identity(record)
        self.assertEqual(store.identities(), [])

    def test_a_mint_mark_is_what_makes_a_receipt_a_receipt(self):
        store = self.store()
        store.put_identity(load_fixture())
        store.promote(CHAR, "DRAFT_COMPLETE")
        approved = store.promote(CHAR, "APPROVED",
                                 approval={"approver": "client",
                                           "receipt_id": "receipt-001"})
        minted_receipt = approved["approval_bindings"][0]
        self.assertTrue(minted_receipt[identity.MINT_FIELD])

        # strip the mark: the same dict a caller can type, refused
        bare = {k: v for k, v in minted_receipt.items()
                if k != identity.MINT_FIELD}
        self.assertIsNotNone(identity.resolve_receipt(bare, approved))
        # the mark belongs to the fields it covers: rewriting one field breaks it
        rewritten = dict(minted_receipt, approver="someone else")
        self.assertIsNotNone(identity.resolve_receipt(rewritten, approved))

    # --- 2. a str subclass that lies in __eq__ ----------------------------

    def test_str_subclass_lying_in_eq_is_refused_by_name(self):
        # the threat is real: this is what a naive != check would believe
        self.assertTrue(LyingStr("junk") == identity.RECEIPT_KIND)
        self.assertFalse(LyingStr("DRAFT_INCOMPLETE") != "APPROVED")

        binding = dict(minted({"receipt_id": "rcp-lying-str"}),
                       kind=LyingStr("junk"))
        reason = identity.resolve_receipt(binding, self.approved_record([binding]))
        self.assertIsNotNone(reason)
        self.assertIn("must be a plain string", reason)

        record = with_bindings([minted()])
        record["draft_state"] = LyingStr("DRAFT_INCOMPLETE")
        record.pop("content_digest", None)
        with self.assertRaises(identity.IdentityDefect):
            identity.validate_identity(identity.seal_identity(record))

        poisoned = with_bindings([minted()])
        poisoned["approval_bindings"][0]["to_state"] = LyingStr("APPROVED")
        poisoned.pop("content_digest", None)
        with self.assertRaises(identity.IdentityDefect):
            identity.validate_identity(identity.seal_identity(poisoned))
        store = self.store()
        with self.assertRaises(store_mod.StoreError):
            store.restore_from_notion([poisoned])
        self.assertEqual(store.identities(), [])

    # --- 3. a dict subclass whose get() lies ------------------------------

    def test_dict_subclass_lying_in_get_is_refused_by_name(self):
        binding = LyingDict(receipt({"receipt_id": "rcp-lying-dict"}))
        # the threat is real: get() would have answered every question right
        self.assertEqual(binding.get("kind"), identity.RECEIPT_KIND)
        reason = identity.resolve_receipt(binding,
                                          self.approved_record([binding]))
        self.assertIsNotNone(reason)
        self.assertIn("LyingDict", reason)

        store = self.store()
        with self.assertRaises(store_mod.StoreError) as caught:
            store.restore_from_notion([LyingDict(with_bindings([binding]))])
        self.assertIn("plain object", str(caught.exception))
        self.assertEqual(store.identities(), [])
        self.assertEqual(tree_bytes(self.root), {})

    # --- 4. a list subclass whose __bool__ and __len__ lie ----------------

    def test_list_subclass_lying_about_being_empty_is_refused_by_name(self):
        smuggled = LyingList([receipt({"receipt_id": "rcp-smuggled"})])
        # the threat is real: the draft check would have seen "no receipts"
        self.assertFalse(smuggled)
        self.assertEqual(len(smuggled), 0)

        record = with_bindings(smuggled, state="DRAFT_COMPLETE")
        with self.assertRaises(identity.IdentityDefect) as caught:
            identity.validate_identity(identity.seal_identity(record))
        self.assertTrue(any("plain list" in d["message"]
                            for d in caught.exception.defects))

        store = self.store()
        store.put_identity(load_fixture())
        before = tree_bytes(self.root)
        with self.assertRaises(store_mod.StoreError):
            store.put_identity(with_bindings(smuggled, state="DRAFT_COMPLETE"))
        self.assertEqual(tree_bytes(self.root), before)

        with self.assertRaises(store_mod.StoreError):
            store.restore_from_notion(LyingList([with_bindings([minted()])]))
        self.assertEqual(store.identities()[0]["character_id"], CHAR)
        self.assertEqual(store.identities()[0]["approval_bindings"], [])

    # --- 5. one receipt id, two characters; and one step, two receipts ----

    def test_receipt_id_is_single_use_and_never_moves_to_another_character(self):
        mine = minted({"receipt_id": "rcp-reuse"})
        transplanted = dict(mine, character_id="chr-someone-else")
        reason = identity.resolve_receipt(transplanted,
                                          self.approved_record([transplanted]))
        self.assertIsNotNone(reason)
        self.assertIn("was not minted by the approval step", reason)

        with self.assertRaises(identity.IdentityDefect) as caught:
            minted({"receipt_id": "rcp-reuse", "character_id": "chr-someone-else"})
        self.assertIn("single-use", str(caught.exception))

    def test_two_receipts_for_one_promotion_step_are_refused(self):
        first = minted({"receipt_id": "rcp-step-first"})
        second = minted({"receipt_id": "rcp-step-second"})
        self.assertIsNone(identity.resolve_receipt(first,
                                                   self.approved_record([first])))
        self.assertIsNone(identity.resolve_receipt(second,
                                                   self.approved_record([second])))

        record = with_bindings([first, second])
        with self.assertRaises(identity.IdentityDefect) as caught:
            identity.validate_identity(identity.seal_identity(record))
        self.assertTrue(any("one promotion step" in d["message"]
                            for d in caught.exception.defects))

        store = self.store()
        with self.assertRaises(store_mod.StoreError):
            store.restore_from_notion([record])
        self.assertEqual(store.identities(), [])

    # --- the legitimate flow still seals end to end -----------------------

    def test_the_legitimate_flow_still_seals_and_reads_back(self):
        store = self.store()
        saved = store.put_identity(load_fixture())
        self.assertEqual(saved["draft_state"], "DRAFT_INCOMPLETE")
        store.promote(CHAR, "DRAFT_COMPLETE")
        approved = store.promote(CHAR, "APPROVED",
                                 approval={"approver": "client",
                                           "receipt_id": "receipt-001"})

        self.assertEqual(approved["draft_state"], "APPROVED")
        self.assertEqual(len(approved["approval_bindings"]), 1)
        self.assertIsNone(identity.resolve_receipt(approved["approval_bindings"][0],
                                                   approved))
        identity.validate_identity(approved)

        on_disk = tree_bytes(self.root)
        self.assertIn(b"approval_receipt", b"".join(on_disk.values()))
        self.assertIn(b"mint_mark", b"".join(on_disk.values()))
        self.assertEqual(store.get_identity(CHAR), approved)
        self.assertEqual(store.sync_state(CHAR, approved["revision"]), "IN_SYNC")

    # --- a receipt reloaded from JSON written by another run --------------

    def test_a_receipt_reloaded_from_json_written_by_another_run_is_refused(self):
        child = (
            "import json, sys\n"
            "sys.path.insert(0, %r)\n"
            "from character_library import notion_store as store_mod\n"
            "store = store_mod.NotionStore(sys.argv[1], %r)\n"
            "store.put_identity(json.load(open(sys.argv[2], encoding='utf-8')))\n"
            "store.promote(%r, 'DRAFT_COMPLETE')\n"
            "approved = store.promote(%r, 'APPROVED',\n"
            "                         approval={'approver': 'client',\n"
            "                                   'receipt_id': 'receipt-001'})\n"
            "json.dump(approved, sys.stdout)\n"
            % (CORE, NS_A, CHAR, CHAR)
        )
        else_root = tempfile.mkdtemp(prefix="s75-t15-else-")
        try:
            proc = subprocess.run(
                [sys.executable, "-c", child, else_root, FIXTURE],
                capture_output=True, text=True, check=True)
        finally:
            shutil.rmtree(else_root, ignore_errors=True)

        reloaded = json.loads(proc.stdout)          # exactly a dict from JSON
        self.assertEqual(reloaded["approval_bindings"][0]["receipt_id"],
                         "receipt-001")
        self.assertIsNotNone(identity.resolve_receipt(reloaded["approval_bindings"][0],
                                                      reloaded))

        target = self.store()
        with self.assertRaises(store_mod.StoreError):
            target.restore_from_notion([reloaded])
        self.assertEqual(target.identities(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
