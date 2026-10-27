#!/usr/bin/env python3
"""S75-T15: client-scoped identity persistence, as a cache of Notion.

Fixture only. No client workspace, credential or network call is used.
Run: python3 test_notion_store_s75_t15.py
"""
import gc
import hashlib
import hmac
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


def minted(store, over=None):
    """The receipt this store's REAL promotion step produced for a claim.

    Round 5: a caller cannot mint, and there is no test-only mint either. This
    helper earns each receipt by performing the promotion step itself -- put,
    promote DRAFT_COMPLETE, promote APPROVED -- so a receipt in these tests can
    only ever be one a promotion step actually produced. The store's cache is
    put back exactly as it was found, so building a fixture never leaves a
    record behind. A claim the store already approved is answered from the
    record it holds rather than by promoting a second time.

    Round 4's version of this helper called ``identity.register_character`` and
    ``identity.mint_receipt`` directly. That was the acceptance row's conjunct-4
    breach dressed as fixture convenience, and it is gone.
    """
    fields = receipt(over)
    fields.pop(identity.MINT_FIELD, None)
    character_id = fields["character_id"]

    held = store.get_identity(character_id)
    if held is not None and held.get("draft_state") == "APPROVED":
        for binding in held.get("approval_bindings") or []:
            if all(type(binding.get(key)) is str and binding.get(key) == value
                   for key, value in fields.items()):
                return dict(binding)

    document = store_mod._doc(character_id)
    prior = store.cache.load(document)
    try:
        record = for_client(store.client_namespace)
        record["character_id"] = character_id
        record["draft_state"] = "DRAFT_INCOMPLETE"
        record["approval_bindings"] = []
        record.pop("content_digest", None)
        store.cache.drop(document)
        store.put_identity(record)
        store.promote(character_id, "DRAFT_COMPLETE")
        approved = store.promote(
            character_id, "APPROVED",
            approval={"approver": fields["approver"],
                      "receipt_id": fields["receipt_id"]})
        return dict(approved["approval_bindings"][0])
    finally:
        store.cache.drop(document)
        if prior is not None:
            store.cache.store(document, prior["value"],
                              revision=prior.get("revision", 1),
                              source=prior.get("source", "LOCAL"))


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
        identity.validate_identity(self.sealed([minted(self.store())]))
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
        self.assertEqual(approved["approval_bindings"], [minted(store)])
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
        self.assertEqual(store.put_identity(with_bindings([minted(store)])), approved)
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
        # CONTRACT CHANGE (round 4, stated in the round-4 report): this test
        # used to restore a receipt minted by one store into ANOTHER store's
        # cache and require it to be accepted. That shape is exactly the replay
        # the round-3 verdict counted as a single-use breach (F3), so it is
        # refused now. The replacement is strictly stronger: the same record is
        # accepted where the promotion step happened and refused everywhere
        # else, proved in both directions below.
        source = self.store()
        source.put_identity(load_fixture())
        source.promote(CHAR, "DRAFT_COMPLETE")
        approved = source.promote(CHAR, "APPROVED",
                                  approval={"approver": "client",
                                            "receipt_id": "receipt-001"})
        self.assertTrue(source.cache.drop(store_mod._doc(CHAR)))
        self.assertIsNone(source.get_identity(CHAR))

        # this store rebuilds its own cache from the record it approved
        self.assertEqual(source.restore_from_notion([approved]), [CHAR])
        self.assertEqual(source.get_identity(CHAR)["approval_bindings"],
                         [minted(source)])
        self.assertIsNone(identity.resolve_receipt(
            source.get_identity(CHAR)["approval_bindings"][0],
            source.get_identity(CHAR), scope=source.approval_scope()))

        # another client's store never accepts that receipt
        other = self.store("fixture-client-restored")
        record = dict(approved)
        record["client_id"] = "fixture-client-restored"
        with self.assertRaises(store_mod.StoreError):
            other.restore_from_notion([record])
        self.assertIsNone(other.get_identity(CHAR))

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

        real = minted(self.store())
        binding = dict(real, kind=LyingStr("junk"))
        reason = identity.resolve_receipt(binding, self.approved_record([binding]))
        self.assertIsNotNone(reason)
        self.assertIn("must be a plain string", reason)

        record = with_bindings([dict(real)])
        record["draft_state"] = LyingStr("DRAFT_INCOMPLETE")
        record.pop("content_digest", None)
        with self.assertRaises(identity.IdentityDefect):
            identity.validate_identity(identity.seal_identity(record))

        poisoned = with_bindings([dict(real)])
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
            store.restore_from_notion(LyingList([with_bindings([minted(store)])]))
        self.assertEqual(store.identities()[0]["character_id"], CHAR)
        self.assertEqual(store.identities()[0]["approval_bindings"], [])

    # --- 5. one receipt id, two characters; and one step, two receipts ----

    def test_receipt_id_is_single_use_and_never_moves_to_another_character(self):
        mine = minted(self.store(), {"receipt_id": "rcp-reuse"})
        transplanted = dict(mine, character_id="chr-someone-else")
        reason = identity.resolve_receipt(transplanted,
                                          self.approved_record([transplanted]))
        self.assertIsNotNone(reason)
        self.assertIn("was not minted by the approval step", reason)

        with self.assertRaises(identity.IdentityDefect) as caught:
            minted(self.store(),
                   {"receipt_id": "rcp-reuse", "character_id": "chr-someone-else"})
        self.assertIn("single-use", str(caught.exception))

    def test_two_receipts_for_one_promotion_step_are_refused(self):
        store = self.store()
        elsewhere = tempfile.mkdtemp(prefix="s75-t15-else-")
        try:
            other = store_mod.NotionStore(elsewhere, NS_A)
            first = minted(store, {"receipt_id": "rcp-step-first"})
            # round 4: a second receipt for that step cannot even be minted in
            # the store that already approved it
            with self.assertRaises(identity.IdentityDefect) as caught:
                minted(store, {"receipt_id": "rcp-step-second"})
            self.assertIn("one promotion step", str(caught.exception))
            # a second store mints its own receipt for the same step ...
            second = minted(other, {"receipt_id": "rcp-step-second"})

            self.assertIsNone(identity.resolve_receipt(first,
                                                       self.approved_record([first])))
            self.assertIsNone(identity.resolve_receipt(second,
                                                       self.approved_record([second])))

            # round 4: a second receipt never resolves against a record this
            # promotion step already approved. The rule sits on the validation
            # entry point itself, not only in the per-record pass below.
            reason = identity.resolve_receipt(second, self.approved_record([first]))
            self.assertIsNotNone(reason)
            self.assertIn("one promotion step", reason)

            record = with_bindings([first, second])
            with self.assertRaises(identity.IdentityDefect) as caught:
                identity.validate_identity(identity.seal_identity(record))
            self.assertTrue(any("one promotion step" in d["message"]
                                for d in caught.exception.defects))

            with self.assertRaises(store_mod.StoreError):
                store.restore_from_notion([record])
            self.assertEqual(store.identities(), [])
        finally:
            shutil.rmtree(elsewhere, ignore_errors=True)

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


class OutOfProcessMintTest(unittest.TestCase):
    """Round four: the mint lives outside this process.

    Every shape the round-3 verifier accepted gets a probe here in the form it
    took then: a caller-minted receipt (F1), a consumed receipt replayed into a
    second store (F2), a second receipt for one promotion step (F3) and one
    receipt id honoured on many records (F4).
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s75-t15-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def store(self, namespace=NS_A, root=None):
        return store_mod.NotionStore(root or self.root, namespace)

    def approved(self, store, receipt_id):
        store.put_identity(for_client(store.client_namespace))
        store.promote(CHAR, "DRAFT_COMPLETE")
        return store.promote(CHAR, "APPROVED",
                             approval={"approver": "client",
                                       "receipt_id": receipt_id})

    # --- the mechanism ---------------------------------------------------

    def test_no_secret_no_registry_and_no_mint_live_in_this_process(self):
        for name in ("_MINT_KEY", "_MINTED", "_mark", "_verify_mint"):
            self.assertIsNone(getattr(identity, name, None), name)
        for module in (identity, store_mod):
            self.assertEqual([name for name, value in vars(module).items()
                              if isinstance(value, (bytes, bytearray))], [])

    def test_no_object_in_this_process_reproduces_a_mint_mark(self):
        approved = self.approved(self.store(), "rcp-round4-mark")
        binding = approved["approval_bindings"][0]
        claim = {k: binding[k] for k in sorted(identity.CLAIM_KEYS)}
        body = json.dumps(claim, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8")
        reproduced = set()
        for obj in gc.get_objects():        # every route the gc graph offers
            if isinstance(obj, (bytes, bytearray)) and len(obj) == 32:
                try:
                    reproduced.add(hmac.new(bytes(obj), body,
                                            hashlib.sha256).hexdigest())
                except Exception:
                    continue
        self.assertTrue(binding[identity.MINT_FIELD])
        self.assertNotIn(binding[identity.MINT_FIELD], reproduced)

    # --- F1: hand-built claim, minted by the caller, promote() zero times --

    def test_f1_a_caller_cannot_mint_a_receipt_at_all(self):
        fields = receipt({"receipt_id": "rcp-round4-f1"})
        fields.pop(identity.MINT_FIELD, None)

        with self.assertRaises(identity.IdentityDefect) as caught:
            identity.mint_receipt(fields)              # no store at all
        self.assertEqual(caught.exception.defects[0]["code"],
                         "RECEIPT_MINT_REFUSED")

        store = self.store()
        with self.assertRaises(identity.IdentityDefect) as caught:
            identity.mint_receipt(fields, scope=store.approval_scope())
        self.assertEqual(caught.exception.defects[0]["code"],
                         "RECEIPT_MINT_REFUSED")
        self.assertIn("did not happen", str(caught.exception))

        for bogus in (fields, receipt({"receipt_id": "rcp-round4-f1b"}),
                      {**fields, identity.MINT_FIELD: "0" * 64}):
            with self.subTest(binding=bogus):
                with self.assertRaises(store_mod.StoreError):
                    store.restore_from_notion([with_bindings([bogus])])
                self.assertEqual(store.identities(), [])

    # --- F2: a consumed receipt replayed into a second store --------------

    def test_f2_a_consumed_receipt_never_replays_into_a_second_store(self):
        source = self.store()
        approved = self.approved(source, "rcp-round4-f2")
        real = approved["approval_bindings"][0]

        other_client = self.store(NS_B)                # same cache, other client
        replayed = dict(approved)
        replayed["client_id"] = NS_B
        with self.assertRaises(store_mod.StoreError):
            other_client.restore_from_notion([replayed])
        self.assertIsNone(other_client.get_identity(CHAR))

        elsewhere = tempfile.mkdtemp(prefix="s75-t15-else-")
        try:
            other_cache = self.store(NS_A, elsewhere)  # same client, other cache
            with self.assertRaises(store_mod.StoreError):
                other_cache.restore_from_notion([dict(approved)])
            self.assertEqual(other_cache.identities(), [])
        finally:
            shutil.rmtree(elsewhere, ignore_errors=True)

        self.assertIsNone(identity.resolve_receipt(real, approved,
                                                   scope=source.approval_scope()))

    # --- F3: a second receipt for one promotion step ----------------------

    def test_f3_a_second_receipt_for_one_step_never_resolves_or_stores(self):
        store = self.store()
        approved = self.approved(store, "rcp-round4-f3a")
        first = approved["approval_bindings"][0]

        # the step is already approved here, so no second receipt can even be
        # minted for it in this store
        with self.assertRaises(identity.IdentityDefect) as caught:
            minted(store, {"receipt_id": "rcp-round4-f3b"})
        self.assertIn("one promotion step", str(caught.exception))

        # and a receipt minted elsewhere for the same step never resolves here
        elsewhere = tempfile.mkdtemp(prefix="s75-t15-else-")
        try:
            second = minted(store_mod.NotionStore(elsewhere, NS_A),
                            {"receipt_id": "rcp-round4-f3b"})
            reason = identity.resolve_receipt(second, approved)
            self.assertIsNotNone(reason)
            self.assertIn("one promotion step", reason)

            with self.assertRaises(store_mod.StoreError):
                store.restore_from_notion([with_bindings([first, second])])
            self.assertEqual(store.get_identity(CHAR), approved)
        finally:
            shutil.rmtree(elsewhere, ignore_errors=True)

    # --- F4: one receipt id, many records ---------------------------------

    def test_f4_one_receipt_id_honours_one_record_only(self):
        store = self.store()
        approved = self.approved(store, "rcp-round4-f4")
        real = approved["approval_bindings"][0]

        with self.assertRaises(identity.IdentityDefect) as caught:
            minted(store, {"receipt_id": "rcp-round4-f4",
                           "character_id": "chr-someone-else"})
        self.assertIn("single-use", str(caught.exception))

        moved = dict(real, character_id="chr-someone-else")
        other = for_client(NS_A)
        other["character_id"] = "chr-someone-else"
        other["draft_state"] = "APPROVED"
        other["approval_bindings"] = [moved]
        other.pop("content_digest", None)
        with self.assertRaises(store_mod.StoreError):
            store.restore_from_notion([other])
        self.assertEqual(store.identities(), [approved])
        self.assertIsNotNone(identity.resolve_receipt(moved,
                                                      identity.seal_identity(other)))


    # --- the boundary, stated rather than hidden -------------------------

    def test_the_promotion_step_is_not_a_caller_reachable_transport(self):
        # Round 4 asserted the opposite here: that a caller may ask the mint
        # directly, that the store will accept what comes back, and that "no
        # call-site gate can sit in front of it inside one process". That is
        # precisely the acceptance row's conjunct-4 breach (a caller reaching
        # APPROVED with a genuine receipt while promote() was never called), so
        # the assertion is inverted rather than removed. The rule now: the mint
        # request is built inside NotionStore.promote() and nowhere else, and
        # the caller-declared state table it used to consult no longer exists.
        store = self.store()
        store.put_identity(for_client(NS_A))
        store.promote(CHAR, "DRAFT_COMPLETE")
        fields = receipt({"receipt_id": "rcp-round5-transport"})
        fields.pop(identity.MINT_FIELD, None)

        for kwargs in ({}, {"scope": store.approval_scope()}):
            with self.subTest(kwargs=sorted(kwargs)):
                with self.assertRaises(identity.IdentityDefect) as caught:
                    identity.mint_receipt(fields, **kwargs)
                self.assertEqual(caught.exception.defects[0]["code"],
                                 "RECEIPT_MINT_REFUSED")

        # passing a scope is not what decides it: the same refusal, the same
        # code, whether the store holds the character or not
        self.assertFalse(hasattr(identity, "register_character"))
        self.assertNotIn("mint_receipt", identity.__all__)
        self.assertNotIn("register_character", identity.__all__)

        # nothing was minted, nothing reached the store, and the record is still
        # exactly where the last explicit step left it
        self.assertEqual(store.get_identity(CHAR)["draft_state"], "DRAFT_COMPLETE")
        self.assertEqual(store.get_identity(CHAR)["approval_bindings"], [])

    # --- round 6: the module namespace cannot mint, and the signer checks ---

    def test_the_module_namespace_carries_no_mint_at_all(self):
        # Round 5's decisive counterexample, probe A1c: a plain caller imports
        # character_bible.identity and asks its request function for a mint. It
        # got a genuine signer-minted receipt, which restore_from_notion stored
        # as APPROVED with NotionStore.promote() called zero times. The round-5
        # report claimed no such callable was reachable; one leading underscore
        # was the only thing standing in the way. It is an allowlist in code now.
        store = self.store()
        store.put_identity(for_client(NS_A))
        store.promote(CHAR, "DRAFT_COMPLETE")
        fields = receipt({"receipt_id": "rcp-round6-a1c"})
        fields.pop(identity.MINT_FIELD, None)
        scope = store.approval_scope()

        asked = (("mint", {"scope": scope[1], "client": scope[0],
                           "claim": dict(fields, to_state="APPROVED")}),
                 ("capability", {"scope": scope[1], "client": scope[0]}),
                 ("register", {"scope": scope[1], "client": scope[0]}))
        for op, extra in asked:
            with self.subTest(op=op):
                reply = identity._signer_request({"op": op, **extra})
                self.assertFalse(reply.get("ok"))
                self.assertIn("verify", reply.get("reason", ""))

        # nothing was minted and nothing was stored: the record is where the
        # last explicit promotion step left it
        self.assertEqual(store.get_identity(CHAR)["draft_state"], "DRAFT_COMPLETE")
        self.assertEqual(store.get_identity(CHAR)["approval_bindings"], [])

    def test_the_module_namespace_carries_no_mint_request(self):
        # Round 5's probe A1c, kept under its round-6 name. The request shape is
        # what is pinned here beyond the allowlist test above: a caller's own
        # payload must come back untouched (no copy is handed to the signer in
        # its place and no field is written into it), and a ``capability`` field
        # typed by hand must not be a way around the allowlist. Rounds 6 to 8
        # moved the transport off this namespace and behind a per-promotion
        # authority; the module request still answers ``verify`` and nothing else.
        store = self.store()
        store.put_identity(for_client(NS_A))          # holds DRAFT_INCOMPLETE
        store.promote(CHAR, "DRAFT_COMPLETE")         # holds DRAFT_COMPLETE
        fields = receipt({"receipt_id": "rcp-round6-a1c-request"})
        fields.pop(identity.MINT_FIELD, None)
        scope = store.approval_scope()

        asked = (
            {"op": "mint", "scope": scope[1], "client": scope[0],
             "claim": dict(fields, to_state="APPROVED")},
            {"op": "hold", "scope": scope[1], "client": scope[0],
             "character_id": CHAR, "state": "APPROVED"},
            {"op": "mint", "scope": scope[1], "client": scope[0],
             "claim": dict(fields, to_state="APPROVED"),
             "capability": "typed-by-hand"},
        )
        for payload in asked:
            with self.subTest(op=payload["op"],
                              typed="capability" in payload):
                before = json.loads(json.dumps(payload))
                reply = identity._signer_request(payload)
                self.assertFalse(reply.get("ok"))
                self.assertIsNone(reply.get("receipt"))
                self.assertEqual(payload, before)   # never mutated in place
                self.assertIn("verify", reply.get("reason") or "")

        # and the same hand-typed receipt is refused on the Notion side, with
        # nothing written: the record stays exactly where the last explicit
        # promotion step left it
        with self.assertRaises(store_mod.StoreError):
            store.restore_from_notion(
                [with_bindings([dict(fields, to_state="APPROVED")])])
        self.assertEqual(store.get_identity(CHAR)["draft_state"],
                         "DRAFT_COMPLETE")
        self.assertEqual(store.get_identity(CHAR)["approval_bindings"], [])

    def test_the_signer_refuses_a_claim_the_store_does_not_hold(self):
        # Round 5 deleted the caller-writable CHARS table and took the signer's
        # only precondition with it: it then minted for any claim a caller built.
        # The check is restored against a source no caller writes -- the store's
        # own cache directory. The reach below is the store's own transport,
        # used here on purpose: it is the only surface left that can ask for a
        # mint, and the point of the test is that even there the claim has to
        # name a state this store actually holds.
        store = self.store()
        store.put_identity(for_client(NS_A))
        store.promote(CHAR, "DRAFT_COMPLETE")
        scope = store.approval_scope()
        # Reach whichever transport this build mints through, so the test runs
        # against the pre-round-6 code too and fails on the missing check rather
        # than on a method name that did not exist yet.
        send = getattr(store, "_NotionStore__transact", None)
        if send is None:                       # round 5 and earlier: the module
            def send(payload, authority=None):
                return identity._signer_request(payload)
        get_cap = getattr(store, "_NotionStore__store_capability",
                          lambda authority=None: "")
        capability = get_cap()

        for wrong in ("APPROVED", "DRAFT_INCOMPLETE", "NOT_A_STATE", None):
            claim = dict(receipt({"receipt_id": "rcp-round6-held-%s" % wrong}),
                         to_state="APPROVED")
            claim.pop(identity.MINT_FIELD, None)
            claim["from_state"] = wrong
            with self.subTest(from_state=wrong):
                # Round 8: a mint now needs this promotion's own nonce. The
                # object() below is a FORGED one -- a caller who reaches this
                # store's name-mangled members can make one, which is the
                # residual the module states plainly at the top. It is passed
                # here only so the request reaches the signer and the signer's
                # own held-state check is what this test measures.
                reply = send({"op": "mint", "scope": scope[1],
                              "client": scope[0], "capability": capability,
                              "claim": claim}, object())
                self.assertFalse(reply.get("ok"))
                self.assertIn("no %r to approve" % (wrong,),
                              reply.get("reason", ""))

        # and the state the store DOES hold is still the only one it will mint
        self.assertEqual(store.get_identity(CHAR)["draft_state"], "DRAFT_COMPLETE")
        self.assertEqual(store.get_identity(CHAR)["approval_bindings"], [])


class RoundSevenTest(unittest.TestCase):
    """Round 7: the raw signer channel, inverted exactly as the probe did it."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s75-t15-")
        # ONE counting instrument, used for both directions below: every call
        # NotionStore.promote() receives is recorded, so a promote_calls=0
        # reading is a fact about the target and not about the counter.
        self.promote_calls = []
        self.real_promote = store_mod.NotionStore.promote
        calls = self.promote_calls

        def counted(instance, *args, **kwargs):
            calls.append((args, kwargs))
            return self.real_promote(instance, *args, **kwargs)

        store_mod.NotionStore.promote = counted

    def tearDown(self):
        store_mod.NotionStore.promote = self.real_promote
        shutil.rmtree(self.root, ignore_errors=True)

    def test_the_channel_inversion_cannot_reach_approved_and_the_honest_path_can(self):
        # THE INVERSION, built exactly as the round-6b probe built it: a public
        # constructor, put_identity at DRAFT_COMPLETE, store.approval_scope()
        # from a public method, then the signer's raw channel -- and the two
        # newline-delimited JSON requests a caller wrote onto the ends it
        # returned ('capability', then 'mint' with that token), then the genuine
        # receipt back through the public restore_from_notion().
        attacked = store_mod.NotionStore(self.root, NS_A)
        record = for_client(NS_A)
        record["draft_state"] = "DRAFT_COMPLETE"
        record["approval_bindings"] = []
        record.pop("content_digest", None)
        attacked.put_identity(record)
        scope = attacked.approval_scope()
        claim = receipt({"receipt_id": "rcp-r7-inversion"})
        claim.pop(identity.MINT_FIELD, None)
        self.assertEqual(self.promote_calls, [])

        # the accessor the probe used is not a name on the module any more, and
        # neither is any other signer transport: what identity keeps is one
        # verify-only function and the verify-only hook this store installs.
        # Neither holds a file descriptor -- `_SIGNER_VERIFY` is a callable, and
        # it refuses anything that is not a verify.
        for name in ("_signer_channel", "_signer_start", "_signer_drop",
                     "_SIGNER_PIPES", "_SIGNER_LOCK"):
            self.assertIsNone(getattr(identity, name, None), name)
        leaky = sorted(n for n in vars(identity)
                       if ("signer" in n.lower() or "pipe" in n.lower())
                       and n not in ("_signer_request", "_SIGNER_SOURCE",
                                     "_SIGNER_VERIFY"))
        self.assertEqual(leaky, [])
        self.assertTrue(callable(identity._SIGNER_VERIFY))
        self.assertFalse(identity._SIGNER_VERIFY(
            {"op": "mint", "client": scope[0], "scope": scope[1],
             "claim": dict(claim, to_state="APPROVED")}).get("ok"))

        # and every request a caller can still make refuses in code
        asked = ({"op": "capability", "client": scope[0], "scope": scope[1]},
                 {"op": "mint", "client": scope[0], "scope": scope[1],
                  "capability": "token-the-signer-issued-to-nobody",
                  "claim": dict(claim, to_state="APPROVED")},
                 {"op": "register", "client": scope[0], "scope": scope[1]})
        for payload in asked:
            with self.subTest(op=payload["op"]):
                reply = identity._signer_request(payload)
                self.assertFalse(reply.get("ok"))
                self.assertIn("verify", reply.get("reason", ""))

        # nothing was minted, so nothing a caller hands to restore_from_notion
        # carries a mark the signer will honour
        forged = for_client(NS_A)
        forged["draft_state"] = "APPROVED"
        forged["approval_bindings"] = [claim]
        forged.pop("content_digest", None)
        with self.assertRaises(store_mod.StoreError):
            attacked.restore_from_notion([forged])
        self.assertEqual(self.promote_calls, [])
        self.assertEqual(attacked.get_identity(CHAR)["draft_state"],
                         "DRAFT_COMPLETE")
        self.assertEqual(attacked.get_identity(CHAR)["approval_bindings"], [])

        # THE HONEST PATH, on the same instrument: the promotion step is still
        # what mints, and it still takes exactly two calls to reach APPROVED
        honest = store_mod.NotionStore(self.root, NS_A + "-honest")
        honest.put_identity(for_client(NS_A + "-honest"))
        honest.promote(CHAR, "DRAFT_COMPLETE")
        approved = honest.promote(
            CHAR, "APPROVED",
            approval={"approver": "client", "receipt_id": "rcp-r7-honest"})
        self.assertEqual(len(self.promote_calls), 2)
        self.assertEqual(approved["draft_state"], "APPROVED")
        self.assertEqual(len(approved["approval_bindings"]), 1)
        self.assertEqual(
            len(approved["approval_bindings"][0][identity.MINT_FIELD]), 64)

    def test_verify_without_a_scope_still_binds_the_receipt_to_its_client(self):
        # Round 7, same class one level down: 'verify' with scope=None used to
        # look the binding up under a key that is always a (scope, receipt_id)
        # pair, find nothing, and skip both binding checks. It is refused for
        # another client's record now. (The cross-store half still needs a
        # scope; see the declared residual in the round-7 report.)
        store = store_mod.NotionStore(self.root, NS_A)
        real = minted(store, {"receipt_id": "rcp-r7-scope"})

        other = for_client(NS_B)
        other["character_id"] = CHAR
        other["draft_state"] = "APPROVED"
        other["approval_bindings"] = [real]
        other.pop("content_digest", None)
        sealed = identity.seal_identity(other)

        reason = identity.resolve_receipt(real, sealed)     # no scope at all
        self.assertIsNotNone(reason)
        self.assertIn("client", reason)
        with self.assertRaises(identity.IdentityDefect):
            identity.validate_identity(sealed)


class RoundEightTest(unittest.TestCase):
    """Round 8: route D3 -- one module attribute, vars(), and public methods.

    The round-7 verdict measured a full breach at 9add5de8e through exactly
    this route and no private name at all. This test runs that route against the
    shipped code and asserts it cannot reach APPROVED with ``promote()`` called
    zero times, then runs the honest path on the SAME counter.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s75-t15-")
        # ONE counting instrument, both directions: every call
        # NotionStore.promote() receives is recorded.
        self.promote_calls = []
        self.real_promote = store_mod.NotionStore.promote
        calls = self.promote_calls

        def counted(instance, *args, **kwargs):
            calls.append((args, kwargs))
            return self.real_promote(instance, *args, **kwargs)

        store_mod.NotionStore.promote = counted

    def tearDown(self):
        store_mod.NotionStore.promote = self.real_promote
        shutil.rmtree(self.root, ignore_errors=True)

    @staticmethod
    def public_callables(obj):
        return sorted(n for n, v in vars(obj).items()
                      if not n.startswith("_") and callable(v))

    def test_no_module_namespace_returns_a_file_descriptor_at_all(self):
        # Requirement 1 of the round-8 brief, measured structurally: no entry on
        # either module namespace, public or private, hands back a file
        # descriptor. The transport holds the ends and exposes request/reply.
        for name in ("start", "channel", "drop", "trip", "__start", "__channel",
                     "__held"):
            self.assertFalse(hasattr(store_mod._SignerTransport, name),
                             "_SignerTransport still exposes %r" % name)
        for name in ("_NotionStore__signer_channel", "_NotionStore__signer_start",
                     "_NotionStore__signer_drop"):
            self.assertIsNone(getattr(store_mod.NotionStore, name, None), name)
        self.assertEqual(self.public_callables(store_mod._SignerTransport),
                         ["verify"])
        # and nothing reachable from either namespace is a signer transport but
        # the one private class attribute of NotionStore
        self.assertIs(store_mod.NotionStore._NotionStore__transport.__class__,
                      store_mod._SignerTransport)
        transports = [n for n, v in vars(store_mod).items()
                      if isinstance(v, type) and hasattr(v, "verify")]
        self.assertEqual(transports, ["_SignerTransport"])

    def test_route_d3_through_vars_and_public_methods_cannot_reach_approved(self):
        attacked = store_mod.NotionStore(self.root, NS_A)
        record = for_client(NS_A)
        record["draft_state"] = "DRAFT_COMPLETE"
        record["approval_bindings"] = []
        record.pop("content_digest", None)
        attacked.put_identity(record)
        scope = attacked.approval_scope()
        claim = receipt({"receipt_id": "rcp-r8-route-d3"})
        claim.pop(identity.MINT_FIELD, None)
        self.assertEqual(self.promote_calls, [])

        # (5) one module attribute, the public builtin vars(), scanned
        # structurally for an object exposing callable channel() and start().
        entries = [name for name, obj in vars(store_mod.NotionStore).items()
                   if callable(getattr(obj, "channel", None))
                   and callable(getattr(obj, "start", None))]
        self.assertEqual(entries, [], "a transport is still reachable via vars()")
        entries += [name for name, obj in vars(store_mod).items()
                    if callable(getattr(obj, "channel", None))
                    and callable(getattr(obj, "start", None))]
        self.assertEqual(entries, [])

        # (6) the public route, attempted anyway -- and by SHAPE, not by name,
        # so a rename cannot make this pass. Every public callable on the live
        # store and on the live transport is tried with the arguments the probe
        # used, and NOTHING that comes back may contain an open file descriptor.
        leaked = []

        def live_fds(value):
            if type(value) is int:
                try:
                    os.fstat(value)
                except OSError:
                    return
                leaked.append(value)
            elif isinstance(value, (tuple, list)):
                for item in value:
                    live_fds(item)

        holders = (attacked, store_mod.NotionStore._NotionStore__transport)
        for holder in holders:
            for name in sorted(vars(holder.__class__)):
                if name.startswith("_") or name == "promote":
                    continue        # promote is the instrument, never called
                fn = getattr(holder.__class__, name, None)
                if not callable(fn):
                    continue
                for args in ((), (attacked,), (attacked, lambda: None),
                             (None,), ({"op": "mint"},)):
                    try:
                        live_fds(fn(*args))
                    except Exception:
                        continue
        self.assertEqual(leaked, [],
                         "a file descriptor is still handed to a caller")

        # (7)+(8) the two hand-written requests and the receipt they carry:
        # with no ends there is nothing to write them onto, and the requests a
        # caller can still make refuse in code.
        scope_reply = identity._signer_request(
            {"op": "capability", "client": scope[0], "scope": scope[1]})
        self.assertFalse(scope_reply.get("ok"))
        mint_reply = identity._signer_request(
            {"op": "mint", "client": scope[0], "scope": scope[1],
             "capability": "token-issued-to-nobody", "claim": dict(claim)})
        self.assertFalse(mint_reply.get("ok"))
        self.assertIsNone(mint_reply.get("receipt"))

        # and the mint this store's own transport would send needs this
        # promotion's own authority, which nothing outside promote() carries
        blocked = attacked._NotionStore__transact(
            {"op": "mint", "scope": scope[1], "client": scope[0],
             "capability": "token-issued-to-nobody", "claim": dict(claim)})
        self.assertFalse(blocked.get("ok"))

        # (9) the genuine receipt a caller would have to bring back
        forged = for_client(NS_A)
        forged["draft_state"] = "APPROVED"
        forged["approval_bindings"] = [dict(claim, to_state="APPROVED")]
        forged.pop("content_digest", None)
        with self.assertRaises(store_mod.StoreError):
            attacked.restore_from_notion([forged])

        self.assertEqual(self.promote_calls, [])
        held = attacked.get_identity(CHAR)
        self.assertEqual(held["draft_state"], "DRAFT_COMPLETE")
        self.assertEqual(held["approval_bindings"], [])

        # THE HONEST PATH on the same counter: still exactly two promote() calls
        honest = store_mod.NotionStore(self.root, NS_A + "-honest")
        honest.put_identity(for_client(NS_A + "-honest"))
        honest.promote(CHAR, "DRAFT_COMPLETE")
        approved = honest.promote(
            CHAR, "APPROVED",
            approval={"approver": "client", "receipt_id": "rcp-r8-honest"})
        self.assertEqual(len(self.promote_calls), 2)
        self.assertEqual(approved["draft_state"], "APPROVED")
        self.assertEqual(len(approved["approval_bindings"]), 1)
        self.assertEqual(
            len(approved["approval_bindings"][0][identity.MINT_FIELD]), 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
