#!/usr/bin/env python3
"""S75-T15: client-scoped character identities persisted as a Notion sync cache.

Notion is the source of truth for the client's shared library. This module
keeps, per client:

  * the library page / data source IDs and their identity and revision,
  * each character's identity record (revision, content digest),
  * the draft and approved states, plus explicit approval bindings,
  * the references (images attach later; a text identity needs none).

Nothing here is authoritative. The cache states that itself, and a missing or
stale copy is rebuilt from the Notion side without inventing a record.

Remote access reuses :mod:`character_library.notion_adapter`; this module adds
no second Notion client and no new dependency. Stdlib only; no credential is
read, held or stored.
"""
from __future__ import annotations

import os
import sys

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from character_bible import identity  # noqa: E402
from character_library import cache as cache_mod  # noqa: E402
from character_library import notion_adapter as adapter  # noqa: E402

__all__ = [
    "NotionStore", "StoreError", "IDENTITY_DOC_PREFIX", "DRAFT_ORDER",
    "REGISTRY_DOC",
]

IDENTITY_DOC_PREFIX = "identity"
REGISTRY_DOC = "notion_registry"
#: The only forward order. Skipping or going back is refused.
DRAFT_ORDER = identity.DRAFT_ORDER


class StoreError(ValueError):
    """Plain-English reason a record was refused."""


def _doc(character_id):
    return "%s-%s" % (IDENTITY_DOC_PREFIX, character_id)


# SECURITY (do not loosen in a later round): a caller-supplied object never
# answers a security question about itself. ``isinstance`` is deliberately not
# used for these gates -- a dict subclass can lie in ``get()``/``keys()``/
# ``__len__``/``__bool__``, a str subclass can lie in ``__eq__`` (Python calls
# the subclass's reflected ``__eq__`` first), and a list subclass can lie in
# ``__bool__``/``__len__``, which is exactly how a forged receipt on a draft
# got through before. A subclass is refused outright with a named StoreError,
# and every decision below runs on one plain builtin copy.

def _mapping(value):
    """One plain builtin dict copy, or None when it is not an exact builtin dict."""
    if type(value) is not dict:
        return None
    return {k: v for k, v in value.items()}


def _sequence(value):
    """One plain builtin list copy, or None when it is not an exact builtin list.
    Emptiness and length are always tested on the returned copy."""
    if type(value) is not list:
        return None
    return list(value)


def _plain_object(value, what):
    copy = _mapping(value)
    if copy is None:
        raise StoreError(
            "A %s must be a plain object, not %s. A subclass is refused because "
            "it can lie in get() and __len__ about what it holds."
            % (what, type(value).__name__))
    return copy


def _plain_sequence(value, what):
    copy = _sequence(value)
    if copy is None:
        raise StoreError(
            "A %s must be a plain list, not %s. A subclass is refused because it "
            "can lie in __bool__ and __len__ about being empty."
            % (what, type(value).__name__))
    return copy


def _plain_text(value, what):
    if type(value) is not str:
        raise StoreError(
            "A %s must be a plain string, not %s. A subclass is refused because "
            "it can lie in __eq__." % (what, type(value).__name__))
    return value


def _validated(record, scope):
    """Seal and validate, refusing every defect as a plain StoreError."""
    sealed = identity.seal_identity(record)
    try:
        identity.validate_identity(sealed, scope=scope)
    except identity.IdentityDefect as defect:
        raise StoreError(str(defect)) from defect
    return sealed


class NotionStore:
    """One client's cached identity records. Scoped, never shared."""

    def __init__(self, root, client_namespace):
        self.cache = cache_mod.Cache(root, client_namespace)
        self.client_namespace = self.cache.client_namespace

    def approval_scope(self):
        """The scope a promotion receipt is minted for and bound to.

        One client namespace in one cache directory. A receipt is bound to both
        at the mint, so a receipt consumed here is never honoured by another
        store's cache: replaying one is refused by the promotion step itself.
        """
        return (self.client_namespace, os.path.abspath(self.cache.dir()))

    # --- library / page / database IDs -----------------------------------

    def registry_path(self):
        return os.path.join(self.cache.dir(), REGISTRY_DOC + ".json")

    def save_registry(self, registry):
        """Persist this client's library, page and data source IDs."""
        plain = _mapping(registry)
        if plain is None:
            raise StoreError(
                "The library registry must be a plain object, not %s. A "
                "subclass is refused because it can lie in get()."
                % type(registry).__name__)
        owner = plain.get("client_namespace")
        if type(owner) is not str or owner != self.client_namespace:
            raise StoreError(
                "The library registry belongs to a different client namespace.")
        return adapter.save_registry(self.registry_path(), plain)

    def load_registry(self):
        """The stored mapping, or None. A handle only, never a token."""
        registry = _mapping(adapter.load_registry(self.registry_path()))
        if registry is None:
            return None
        owner = registry.get("client_namespace")
        if type(owner) is not str or owner != self.client_namespace:
            return None
        return registry

    # --- identities ------------------------------------------------------

    def get_identity(self, character_id):
        """This client's record, or None. Another client's record never resolves."""
        if not str(character_id or "").strip():
            return None
        return self.cache.value(_doc(character_id))

    def identities(self):
        """Every cached identity for this client, ordered by character id."""
        find = []
        for document, envelope in self.cache.documents().items():
            if not document.startswith(IDENTITY_DOC_PREFIX + "-"):
                continue
            record = envelope.get("value")
            if isinstance(record, dict):
                find.append(record)
        return sorted(find, key=lambda r: str(r.get("character_id", "")))

    def put_identity(self, record, *, revision=None):
        """Create or update ONE identity under this client. Never duplicates.

        The record is sealed and validated. An image is not required: a text
        identity is complete on its own. The draft state is never advanced by a
        save — only :meth:`promote` moves it, and only explicitly. A save never
        stores APPROVED and never writes an approval receipt: those exist only
        on the record the promotion step approved, with the receipt it produced.
        """
        given = record
        record = _mapping(given)
        if record is None:
            raise StoreError(
                "An identity record must be a plain object, not %s. A subclass "
                "is refused because it can lie in get() and __len__."
                % type(given).__name__)
        owner = record.get("client_id")
        if type(owner) is not str or owner != self.client_namespace:
            raise StoreError(
                "This identity belongs to a different client namespace, so it "
                "cannot be stored in this client's library.")
        raw_id = record.get("character_id")
        if type(raw_id) is not str:
            raise StoreError("An identity record needs a character_id.")
        character_id = raw_id.strip()
        if not character_id:
            raise StoreError("An identity record needs a character_id.")

        existing = self.get_identity(character_id)
        prepared = dict(record)
        prepared.setdefault("sync_state", "LOCAL_ONLY")
        prepared.setdefault("approval_bindings", [])
        prepared.setdefault("reference_ids", [])
        # The local copy always declares what it is: a cache of Notion.
        prepared["local_cache"] = cache_mod.describe()
        state = prepared.get("draft_state")
        if type(state) is not str or state not in DRAFT_ORDER:
            raise StoreError("draft_state must be one of %s." % (DRAFT_ORDER,))
        supplied = _sequence(prepared.get("approval_bindings"))
        if supplied is None:
            raise StoreError(
                "approval_bindings must be a plain list of approval receipts. "
                "A list subclass is refused because it can lie in __bool__ and "
                "__len__ about being empty.")
        prepared["approval_bindings"] = supplied
        if existing is None:
            if state == "APPROVED":
                raise StoreError(
                    "A character cannot be created already approved. Approval "
                    "is an explicit step, never a default, and a save never "
                    "stores APPROVED.")
            if supplied:          # tested on the plain copy, never on the caller
                raise StoreError(
                    "A draft carries no approval receipt. A receipt is written "
                    "only by the explicit promotion step, so one cannot be "
                    "parked on a record at save time.")
        else:
            held_state = existing.get("draft_state")
            if type(held_state) is not str or state != held_state:
                raise StoreError(
                    "A draft state changes only through an explicit approval "
                    "step; refusing an implicit transition from %r to %r."
                    % (held_state, state))
            raw_held = existing.get("approval_bindings")
            held = list(raw_held) if type(raw_held) is list else []
            if "approval_bindings" in record and supplied != held:
                raise StoreError(
                    "An approval binding changes only through the explicit "
                    "promotion step; refusing a save that forges, edits or "
                    "drops a receipt.")
            prepared["approval_bindings"] = held
            want = prepared.get("revision")
            have = existing.get("revision")
            want = 1 if want is None else want
            have = 1 if have is None else have
            if type(want) is not int or type(have) is not int:
                raise StoreError("revision must be a positive integer.")
            prepared["revision"] = max(want, have)
        sealed = _validated(prepared, self.approval_scope())
        self.cache.store(_doc(character_id), sealed,
                         revision=revision if revision is not None else sealed["revision"])
        return sealed

    def attach_image(self, character_id, reference_id):
        """Attach one image reference to the SAME identity. No duplicate record."""
        if type(reference_id) is not str:
            raise StoreError("An image needs a reference id.")
        reference = reference_id.strip()
        if not reference:
            raise StoreError("An image needs a reference id.")
        existing = self.get_identity(character_id)
        if existing is None:
            raise StoreError(
                "No identity %r in this client's library. Attaching an image "
                "never creates a character." % (character_id,))
        updated = dict(existing)
        raw_references = updated.get("reference_ids")
        references = list(raw_references) if type(raw_references) is list else []
        if reference in references:
            return updated  # idempotent: same identity, same reference
        references.append(reference)
        updated["reference_ids"] = references
        prior = existing.get("revision")
        prior = 1 if prior is None else prior
        if type(prior) is not int:
            raise StoreError("revision must be a positive integer.")
        updated["revision"] = prior + 1
        sealed = _validated(updated, self.approval_scope())
        self.cache.store(_doc(character_id), sealed, revision=sealed["revision"])
        return sealed

    def promote(self, character_id, to_state, *, approval=None):
        """Move a draft forward one explicit step. Implicit promotion refused.

        Approving is the only place an approval receipt is ever minted, and the
        mint request is built in this method body: the promotion signer is a
        separate process that holds the mint secret in its own memory, and it
        mints only for a store that binds the receipt to this client and this
        cache. Nothing in this process can produce a mark, so a dict typed by
        hand, a mark recomputed from module state and a dict reloaded from a
        JSON file all carry none that verifies.

        There is no mint function to call instead. Round 4 exposed one
        (``identity.mint_receipt``) and a caller could reach APPROVED with a
        genuine receipt while this method was never called; round 5 removes the
        function, the caller-writable state table it consulted, and every other
        path to the signer's mint. See ``identity.mint_receipt``: it is now a
        refusal for every caller and every argument.
        """
        existing = self.get_identity(character_id)
        if existing is None:
            raise StoreError("No identity %r in this client's library." % (character_id,))
        current = existing.get("draft_state")
        if type(to_state) is not str or to_state not in DRAFT_ORDER:
            raise StoreError("Unknown draft state %r." % (to_state,))
        expected = DRAFT_ORDER[DRAFT_ORDER.index(current) + 1] if current in DRAFT_ORDER[:-1] else None
        if to_state != expected:
            raise StoreError(
                "Refusing an out-of-order transition from %r to %r; the next "
                "explicit step is %r." % (current, to_state, expected))
        raw_bindings = existing.get("approval_bindings")
        bindings = list(raw_bindings) if type(raw_bindings) is list else []
        if to_state == "APPROVED":
            plain = _mapping(approval)
            if plain is None:
                raise StoreError(
                    "Approval is explicit: an approval binding with an approver "
                    "and receipt is required; refusing an implicit promotion. "
                    "A subclass is refused because it can lie in get().")
            approver = plain.get("approver")
            receipt_id = plain.get("receipt_id")
            if type(approver) is not str or not approver.strip() \
                    or type(receipt_id) is not str or not receipt_id.strip():
                raise StoreError("An approval binding needs an approver and a receipt id.")
        updated = dict(existing)
        updated["draft_state"] = to_state
        updated["approval_bindings"] = bindings
        if to_state == "APPROVED":
            # THE RULE: a receipt is minted here and nowhere else. The signer's
            # ``mint`` request is built in this method body -- not by a module
            # function and not by a store method -- so there is no callable that
            # a caller can reach to obtain a receipt without this promotion step
            # running. identity.mint_receipt() is a named refusal, and the
            # caller-writable state table it used to depend on no longer exists.
            scope = self.approval_scope()
            claim = {
                "kind": identity.RECEIPT_KIND,
                "receipt_id": receipt_id.strip(),
                "approver": approver.strip(),
                "character_id": str(existing.get("character_id") or "").strip(),
                "from_state": current,
                "to_state": to_state,
            }
            reply = identity._signer_request({
                "op": "mint", "scope": scope[1], "client": scope[0],
                "claim": claim})
            receipt = reply.get("receipt")
            if reply.get("ok") is not True or type(receipt) is not dict:
                # The signer's own refusal, surfaced unchanged: a second receipt
                # for one step, one receipt id asked to name a second record, or
                # nothing minted at all. IdentityDefect is the mint's own error
                # type, and promote() does not downgrade it.
                raise identity.IdentityDefect([{
                    "field": "approval_bindings",
                    "code": "RECEIPT_MINT_REFUSED",
                    "message": reply.get("reason") or (
                        "the promotion step refused to mint an approval receipt"),
                }])
            bindings.append(dict(receipt))
        sealed = _validated(updated, self.approval_scope())
        self.cache.store(_doc(character_id), sealed, revision=sealed["revision"])
        return sealed

    # --- Notion side -----------------------------------------------------

    def remote_catalog(self, connection, registry=None):
        """The client's current catalog, read through the merged adapter."""
        reg = registry or self.load_registry()
        if reg is None:
            raise StoreError("No library has been resolved for this client yet.")
        catalog, _trace = adapter.list_character_revisions(connection, reg)
        return catalog

    def restore_from_notion(self, remote_records):
        """Rebuild missing or stale cached copies from the Notion side.

        ``remote_records`` are full identity records supplied by the Notion
        side. A character Notion does not have is never created locally. A
        record carrying a hand-written approval receipt is refused and NOTHING
        is written: a receipt is only ever the one the promotion step minted for
        this client and this store, never a dict a caller typed, reloaded from a
        JSON file, or replayed from another store's promotion.
        """
        records = [] if remote_records is None else _plain_sequence(
            remote_records, "Notion record list")
        restored = []
        for remote in records:
            given = remote
            remote = _mapping(given)
            if remote is None:
                raise StoreError(
                    "A Notion record must be a plain object, not %s. A subclass "
                    "is refused because it can lie in get()."
                    % type(given).__name__)
            owner = remote.get("client_id")
            if type(owner) is not str or owner != self.client_namespace:
                raise StoreError(
                    "A Notion record for another client cannot be restored here.")
            prepared = dict(remote)
            prepared["local_cache"] = cache_mod.describe()
            sealed = _validated(prepared, self.approval_scope())
            self.cache.recover(_doc(sealed["character_id"]), sealed,
                               revision=sealed["revision"])
            restored.append(sealed["character_id"])
        return sorted(restored)

    def sync_state(self, character_id, remote_revision):
        """MISSING, STALE or IN_SYNC for one cached identity."""
        return self.cache.state(_doc(character_id), remote_revision)
