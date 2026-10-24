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
DRAFT_ORDER = ("DRAFT_INCOMPLETE", "DRAFT_COMPLETE", "APPROVED")


class StoreError(ValueError):
    """Plain-English reason a record was refused."""


def _doc(character_id):
    return "%s-%s" % (IDENTITY_DOC_PREFIX, character_id)


class NotionStore:
    """One client's cached identity records. Scoped, never shared."""

    def __init__(self, root, client_namespace):
        self.cache = cache_mod.Cache(root, client_namespace)
        self.client_namespace = self.cache.client_namespace

    # --- library / page / database IDs -----------------------------------

    def registry_path(self):
        return os.path.join(self.cache.dir(), REGISTRY_DOC + ".json")

    def save_registry(self, registry):
        """Persist this client's library, page and data source IDs."""
        if not isinstance(registry, dict):
            raise StoreError("The library registry must be an object.")
        if registry.get("client_namespace") != self.client_namespace:
            raise StoreError(
                "The library registry belongs to a different client namespace.")
        return adapter.save_registry(self.registry_path(), registry)

    def load_registry(self):
        """The stored mapping, or None. A handle only, never a token."""
        registry = adapter.load_registry(self.registry_path())
        if registry is None:
            return None
        if registry.get("client_namespace") != self.client_namespace:
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
        save — only :meth:`promote` moves it, and only explicitly.
        """
        if not isinstance(record, dict):
            raise StoreError("An identity record must be an object.")
        if record.get("client_id") != self.client_namespace:
            raise StoreError(
                "This identity belongs to a different client namespace, so it "
                "cannot be stored in this client's library.")
        character_id = str(record.get("character_id") or "").strip()
        if not character_id:
            raise StoreError("An identity record needs a character_id.")

        existing = self.get_identity(character_id)
        prepared = dict(record)
        prepared.setdefault("sync_state", "LOCAL_ONLY")
        prepared.setdefault("approval_bindings", [])
        prepared.setdefault("reference_ids", [])
        # The local copy always declares what it is: a cache of Notion.
        prepared["local_cache"] = cache_mod.describe()
        if existing is not None:
            if prepared.get("draft_state") != existing.get("draft_state"):
                raise StoreError(
                    "A draft state changes only through an explicit approval "
                    "step; refusing an implicit transition from %r to %r."
                    % (existing.get("draft_state"), prepared.get("draft_state")))
            prepared["approval_bindings"] = list(existing.get("approval_bindings") or [])
            prepared["revision"] = max(
                int(prepared.get("revision") or 1), int(existing.get("revision") or 1))
        if prepared.get("draft_state") not in DRAFT_ORDER:
            raise StoreError("draft_state must be one of %s." % (DRAFT_ORDER,))
        if prepared.get("draft_state") == "APPROVED" \
                and not prepared.get("approval_bindings"):
            raise StoreError(
                "A character cannot be created already approved. Approval is an "
                "explicit step, never a default.")
        sealed = identity.seal_identity(prepared)
        identity.validate_identity(sealed)
        self.cache.store(_doc(character_id), sealed,
                         revision=revision if revision is not None else sealed["revision"])
        return sealed

    def attach_image(self, character_id, reference_id):
        """Attach one image reference to the SAME identity. No duplicate record."""
        reference = str(reference_id or "").strip()
        if not reference:
            raise StoreError("An image needs a reference id.")
        existing = self.get_identity(character_id)
        if existing is None:
            raise StoreError(
                "No identity %r in this client's library. Attaching an image "
                "never creates a character." % (character_id,))
        updated = dict(existing)
        references = list(updated.get("reference_ids") or [])
        if reference in references:
            return updated  # idempotent: same identity, same reference
        references.append(reference)
        updated["reference_ids"] = references
        updated["revision"] = int(existing.get("revision") or 1) + 1
        sealed = identity.seal_identity(updated)
        identity.validate_identity(sealed)
        self.cache.store(_doc(character_id), sealed, revision=sealed["revision"])
        return sealed

    def promote(self, character_id, to_state, *, approval=None):
        """Move a draft forward one explicit step. Implicit promotion refused."""
        existing = self.get_identity(character_id)
        if existing is None:
            raise StoreError("No identity %r in this client's library." % (character_id,))
        current = existing.get("draft_state")
        if to_state not in DRAFT_ORDER:
            raise StoreError("Unknown draft state %r." % (to_state,))
        expected = DRAFT_ORDER[DRAFT_ORDER.index(current) + 1] if current in DRAFT_ORDER[:-1] else None
        if to_state != expected:
            raise StoreError(
                "Refusing an out-of-order transition from %r to %r; the next "
                "explicit step is %r." % (current, to_state, expected))
        bindings = list(existing.get("approval_bindings") or [])
        if to_state == "APPROVED":
            if not isinstance(approval, dict):
                raise StoreError(
                    "Approval is explicit: an approval binding with an approver "
                    "and receipt is required; refusing an implicit promotion.")
            if not str(approval.get("approver") or "").strip() \
                    or not str(approval.get("receipt_id") or "").strip():
                raise StoreError("An approval binding needs an approver and a receipt id.")
        updated = dict(existing)
        updated["draft_state"] = to_state
        updated["approval_bindings"] = bindings
        if to_state == "APPROVED":
            bindings.append({
                "from_state": current,
                "to_state": to_state,
                "approver": str(approval["approver"]).strip(),
                "receipt_id": str(approval["receipt_id"]).strip(),
            })
        sealed = identity.seal_identity(updated)
        identity.validate_identity(sealed)
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
        side. A character Notion does not have is never created locally.
        """
        restored = []
        for remote in remote_records or []:
            if not isinstance(remote, dict):
                raise StoreError("A Notion record must be an object.")
            if remote.get("client_id") != self.client_namespace:
                raise StoreError(
                    "A Notion record for another client cannot be restored here.")
            prepared = dict(remote)
            prepared["local_cache"] = cache_mod.describe()
            sealed = identity.seal_identity(prepared)
            identity.validate_identity(sealed)
            self.cache.recover(_doc(sealed["character_id"]), sealed,
                               revision=sealed["revision"])
            restored.append(sealed["character_id"])
        return sorted(restored)

    def sync_state(self, character_id, remote_revision):
        """MISSING, STALE or IN_SYNC for one cached identity."""
        return self.cache.state(_doc(character_id), remote_revision)
