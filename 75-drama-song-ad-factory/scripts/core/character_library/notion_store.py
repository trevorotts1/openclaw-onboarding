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

import json
import os
import subprocess
import sys
import threading

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


class _SignerTransport:
    """The approval signer's pipe ends. One signer per process.

    SECURITY (do not loosen in a later round): the file descriptors are private
    state of THIS object and nothing else. They are not a module attribute of
    ``character_bible.identity`` (round 7 removed ``_signer_channel`` from that
    namespace, where any caller could take the raw ends and write the wire
    protocol onto them itself) and they are not a return value of anything a
    caller reaches without a live store. Every entry that can carry a ``mint``
    or ask for a ``capability`` takes the store that owns the request and
    refuses anything that is not a live ``NotionStore``. The one entry that
    needs no store is :meth:`verify`, which is an allowlist in code: it answers
    ``verify`` and refuses ``mint`` and ``capability``, exactly as
    ``identity._signer_request`` does.

    ponytail: this is reachability, not unforgeability. A caller holding a live
    store can reach this transport through that store's private members, and a
    caller willing to re-point the pipe or rewrite the module can answer as the
    signer. Both are the tampering-with-internals class rounds 5, 6 and 6b ruled
    out of scope. Making the channel unforgeable needs the signer under a
    different unix uid, which this environment cannot create.
    """

    def __init__(self):
        self.__pipes = {}
        self.__lock = threading.Lock()

    @staticmethod
    def __owner(owner):
        """The live store that owns the request, or None. A gate, not a check."""
        return owner if type(owner) is NotionStore else None

    def __start(self):
        """Spawn this process's signer and hand back its two pipe ends."""
        to_signer, send_fd = os.pipe()
        recv_fd, to_parent = os.pipe()
        proc = subprocess.Popen(
            [sys.executable, "-I", "-c", identity._SIGNER_SOURCE,
             str(os.getpid()), str(to_signer), str(to_parent)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True,
            pass_fds=(to_signer, to_parent))
        os.close(to_signer)
        os.close(to_parent)
        return (proc, send_fd, recv_fd)

    def __channel(self):
        """The live pipe ends, starting the signer on first use."""
        with self.__lock:
            held = self.__pipes.get(os.getpid())
            if held is None:
                held = self.__start()
                self.__pipes[os.getpid()] = held
            return held

    def __drop(self):
        """Forget this process's signer after a transport failure. Fails closed."""
        with self.__lock:
            held = self.__pipes.pop(os.getpid(), None)
        for fd in (held[1], held[2]) if held is not None else ():
            try:
                os.close(fd)
            except OSError:
                pass

    def start(self, owner):
        """Spawn this process's signer. A live store only."""
        if self.__owner(owner) is None:
            raise StoreError(
                "The approval signer's transport belongs to a live store.")
        return self.__start()

    def channel(self, owner, spawn):
        """The signer's raw pipe ends, ``spawn`` starting it on first use.

        A live store only -- see the ponytail above. ``spawn`` is that store's
        own ``__signer_start``, so the signer is always started by the store
        that owns the request.
        """
        if self.__owner(owner) is None:
            raise StoreError(
                "The approval signer's transport belongs to a live store.")
        with self.__lock:
            held = self.__pipes.get(os.getpid())
            if held is None:
                held = spawn()
                self.__pipes[os.getpid()] = held
            return held

    def drop(self, owner):
        """Forget this process's signer. A live store only. Fails closed."""
        if self.__owner(owner) is None:
            raise StoreError(
                "The approval signer's transport belongs to a live store.")
        return self.__drop()

    def __exchange(self, payload):
        """One request/reply on the signer's pipe. Private: no gate, no caller."""
        raw = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        reason = "the approval signer did not answer"
        for attempt in (0, 1):
            try:
                _proc, send_fd, recv_fd = self.__channel()
            except Exception as exc:
                return {"ok": False,
                        "reason": "the approval signer could not start (%s)"
                                  % exc}
            try:
                return self.trip(send_fd, recv_fd, raw)
            except Exception as exc:
                reason = "the approval signer is unreachable (%s)" % exc
                self.__drop()
                if attempt == 0:
                    continue
        return {"ok": False, "reason": reason}

    @staticmethod
    def trip(send_fd, recv_fd, raw):
        """One framed write/read on a pipe. Takes file descriptors, holds none.

        It is ``os.write`` plus framing: a caller who reaches it already holds
        the pipe ends, and it hands back the signer's own answer and nothing
        else.
        """
        os.write(send_fd, raw)
        data = b""
        while not data.endswith(b"\n"):
            chunk = os.read(recv_fd, 65536)
            if not chunk:
                raise OSError("the approval signer stopped")
            data += chunk
        reply = json.loads(data.decode("utf-8"))
        return reply if type(reply) is dict else {
            "ok": False, "reason": "the approval signer gave an unreadable "
                                   "answer"}

    def verify(self, payload):
        """One ``verify`` request. ``verify`` only, for any caller. Fails closed.

        THE ALLOWLIST: every other operation -- ``mint`` and ``capability``
        included -- is refused in code, for every caller and every argument.
        """
        if type(payload) is not dict or payload.get("op") != "verify":
            return {"ok": False, "reason": (
                "this transport answers only 'verify'; a receipt is minted only "
                "inside the store's own promotion step, which builds that "
                "request itself and carries a capability this module cannot "
                "supply")}
        return self.__exchange(payload)


class NotionStore:
    """One client's cached identity records. Scoped, never shared."""

    #: The signer's transport. Private to this class: the raw pipe ends live on
    #: it and are released only to a live store (round 7).
    __transport = _SignerTransport()

    def __init__(self, root, client_namespace):
        self.cache = cache_mod.Cache(root, client_namespace)
        self.client_namespace = self.cache.client_namespace
        # The token that names THIS store to the approval signer. It is a
        # BEARER TOKEN, not a capability: the signer hands the identical token
        # to anyone who asks for that (client, store), so ``compare_digest``
        # proves only that a request carried a token that was issued. What keeps
        # it away from a plain caller is reachability -- it is held on this
        # instance, fetched through this store's private transport, and never
        # returned by a public method. Nothing asks for it until a promotion
        # step needs it, so a store that never approves never speaks to the
        # signer.
        self.__capability = None

    # --- the approval signer's transport (round 7) -----------------------
    #
    # These three names used to be module functions in character_bible.identity
    # -- ``identity._signer_channel()`` handed the signer's raw pipe ends to any
    # caller, and a caller with zero standing wrote ``capability`` and ``mint``
    # onto them by hand and had the genuine receipt stored through the public
    # ``restore_from_notion()`` with ``promote()`` called zero times. They are
    # private members of this class now, and the pipe ends behind them are
    # private state of ``__transport``.

    def __signer_start(self):
        """Spawn this process's signer. Private member (round 7)."""
        return self.__transport.start(self)

    def __signer_channel(self):
        """The signer's raw pipe ends. Private member (round 7).

        What it hands back is a file descriptor pair, so a caller who gets here
        can write the signer's wire protocol itself. Getting here needs a live
        store and then a name-mangled private member of it -- the
        implementation-internal class rounds 5, 6 and 6b ruled out of scope.
        """
        return self.__transport.channel(self, self.__signer_start)

    def __signer_drop(self):
        """Forget this process's signer after a transport failure. Private."""
        return self.__transport.drop(self)

    @staticmethod
    def __signer_verify(payload):
        """The verify-only entry point ``character_bible.identity`` uses.

        An allowlist in code, exactly like ``identity._signer_request``: it
        answers ``verify`` and refuses ``mint`` and ``capability``, so nothing
        reachable through ``identity``'s namespace can produce a receipt.
        """
        return NotionStore.__transport.verify(payload)

    def __transact(self, payload):
        """One request to the approval signer, built and sent by THIS store.

        This method is the only place a ``mint`` request exists. Round 5 built
        it in promote() and then handed it to ``identity._signer_request``, a
        module-level function that carried ``{"op": "mint"}`` for any caller --
        a plain module call produced a genuine signer-minted receipt with
        ``promote()`` called zero times. identity's namespace now answers
        ``verify`` and refuses the rest in code, and it holds no signer
        transport at all (round 7): the raw pipe ends live behind this class's
        private members, reached through ``__signer_channel``. Getting to this
        method needs a live store instance.
        """
        raw = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        reason = "the approval signer did not answer"
        for attempt in (0, 1):
            try:
                _proc, send_fd, recv_fd = self.__signer_channel()
            except Exception as exc:
                return {"ok": False,
                        "reason": "the approval signer could not start (%s)"
                                  % exc}
            try:
                return self.__transport.trip(send_fd, recv_fd, raw)
            except Exception as exc:
                reason = "the approval signer is unreachable (%s)" % exc
                self.__signer_drop()
                if attempt == 0:
                    continue
        return {"ok": False, "reason": reason}

    def __store_capability(self):
        """This store's capability, fetched once from the signer and kept here."""
        if type(self.__capability) is str and self.__capability:
            return self.__capability
        scope = self.approval_scope()
        reply = self.__transact({"op": "capability",
                                 "client": scope[0], "scope": scope[1]})
        token = reply.get("capability")
        if reply.get("ok") is not True or type(token) is not str or not token:
            raise identity.IdentityDefect([{
                "field": "approval_bindings",
                "code": "RECEIPT_MINT_REFUSED",
                "message": reply.get("reason") or (
                    "the approval signer did not issue this store a capability, "
                    "so this store cannot perform a promotion step"),
            }])
        self.__capability = token
        return token

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
            # ``mint`` request is built in this method body and sent over this
            # store's own transport (``__transact``) carrying this store's own
            # capability. identity's module namespace answers ``verify`` and
            # refuses a mint in code, so there is no module-level callable that
            # hands out a receipt, and no callable at all outside a live store
            # instance. The signer then checks what this store actually holds:
            # it reads the record out of this cache and refuses a mint unless
            # the store holds the character at the claim's from_state. That is
            # the check the deleted CHARS table used to perform, restored
            # against a source no caller can write. identity.mint_receipt() is
            # a named refusal for every caller and every argument.
            scope = self.approval_scope()
            claim = {
                "kind": identity.RECEIPT_KIND,
                "receipt_id": receipt_id.strip(),
                "approver": approver.strip(),
                "character_id": str(existing.get("character_id") or "").strip(),
                "from_state": current,
                "to_state": to_state,
            }
            reply = self.__transact({
                "op": "mint", "scope": scope[1], "client": scope[0],
                "capability": self.__store_capability(), "claim": claim})
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


#: Install the verify-only entry point into ``character_bible.identity``.
#:
#: It is a CALLABLE, not a transport: identity's namespace never holds a pipe
#: end. The wiring is done at import time and bound to THIS module's ``identity``
#: object on purpose. The repository's pytest harness drops skill-tree modules
#: from ``sys.modules`` between files, so this module and ``identity`` can each
#: exist more than once in one interpreter; a run-time ``import`` from identity
#: would then bind whichever copy ``sys.modules`` held last, whose signer is a
#: different process with a different key, and a genuine receipt would stop
#: verifying (measured: 16 failures in this file's own suite under pytest).
identity._SIGNER_VERIFY = NotionStore._NotionStore__signer_verify
