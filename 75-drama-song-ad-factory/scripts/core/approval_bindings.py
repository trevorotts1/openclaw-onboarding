#!/usr/bin/env python3
"""Whole-package approval bindings (S75-T12 / S75-A12). Stdlib only.

ONE approval covers the whole creative package: every foundation artifact plus
the script and the lyrics, each bound at its exact revision and digest. Nothing
here opens a per-scene or per-character approval loop -- a kind that is not a
package component is refused, never bound.

A binding that would claim an artifact kind another binding already owns is
refused: component ownership never overlaps, so two approvals can never
disagree about the same revision.

Preference is never artifact approval. A changed dependency invalidates only
the receipts that bind it. A missing approval is a refusal, never a default.

The component list is the same table ``check_stage`` reads
(``story_first_contracts.APPROVAL_BINDS``) and EVERY judgement about the
client's words is the existing ``script_approval.approval_events`` interpreter
(``interpret_reply``, ``is_affirmative``, ``is_preference_reply``): only an
unambiguous affirmative reply from a real client with a real approver, at its
real time, approves. Refusal, revision, ambiguous, unseen and foreign replies
all leave the gate closed. This module adds no second decision rule, no writer
and no IO: it records decisions the caller already has and refuses everything
else.
"""
from __future__ import annotations

import hashlib

try:  # loaded with scripts/core on sys.path
    import story_first_contracts as C  # type: ignore
except ImportError:  # pragma: no cover - loaded as a package
    from . import story_first_contracts as C  # type: ignore

try:
    from script_approval import approval_events as AE  # type: ignore
except ImportError:  # pragma: no cover - preference check unavailable
    AE = None

SCHEMA_VERSION = "s75.approval_bindings.v1"
PACKAGE_APPROVAL = "package_approval"

#: The exact set the whole-package approval must cover. Not a suggestion:
#: an incomplete package cannot be approved.
COMPONENTS = tuple(C.APPROVAL_BINDS[PACKAGE_APPROVAL])

#: Artifact kinds whose names mark them as granular. Binding one would be a
#: per-scene or per-character approval loop, which this project forbids.
_GRANULAR_PREFIXES = ("scene", "character", "cast_entry", "keyframe")

ACTIVE = "active"
INVALIDATED = "invalidated"


class BindingError(C.ContractError):
    """A binding refusal. ``code`` names the invariant that refused it."""


def _granular(kind):
    """A granular kind names ONE scene or ONE character, not a whole artifact.

    ``scene_plan`` is the whole plan and is a legitimate component; a dotted or
    suffixed per-scene kind is not. Membership is decided first, so this only
    classifies kinds the package does not own.
    """
    if not isinstance(kind, str) or kind in COMPONENTS:
        return False
    return kind.lower().startswith(_GRANULAR_PREFIXES)


def _require_component_kind(kind):
    """Refuse any kind that is not a whole-package component."""
    if kind in COMPONENTS:
        return
    if _granular(kind):
        raise BindingError(
            "NO_GRANULAR_APPROVAL_LOOP",
            "%r would open a per-scene or per-character approval loop" % (kind,),
            {"kind": kind, "components": list(COMPONENTS)})
    raise BindingError(
        "KIND_NOT_PACKAGE_COMPONENT",
        "%r is not part of the whole creative package" % (kind,),
        {"kind": kind, "components": list(COMPONENTS)})


def _normalise(entry):
    if not isinstance(entry, dict):
        return {}
    return {"revision": entry.get("revision"), "digest": entry.get("digest")}


def validate_components(components):
    """Defects for one candidate package binding. Empty list means complete."""
    if not isinstance(components, dict):
        return [{"kind": "components", "issue": "not an object"}]
    defects = []
    for kind in components:
        if kind in COMPONENTS:
            if not _normalise(components[kind]).get("digest"):
                defects.append({"kind": kind, "issue": "no digest"})
        elif _granular(kind):
            defects.append({"kind": kind, "issue": "NO_GRANULAR_APPROVAL_LOOP"})
        else:
            defects.append({"kind": kind, "issue": "KIND_NOT_PACKAGE_COMPONENT"})
    for kind in COMPONENTS:
        if kind not in components:
            defects.append({"kind": kind, "issue": "missing"})
    return defects


def binding_digest(components):
    """Canonical sha256 of the exact versions one approval covers."""
    body = {k: _normalise(v) for k, v in components.items() if k in COMPONENTS}
    return C.artifact_digest(body)


def _sha(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


#: The interpreter's own vocabulary is keyed by its artifact names. A kind it
#: cannot name (a foundation artifact) is covered by an unambiguous approval of
#: the one ask and can never be singled out in a reply.
_AE_KIND_ALIASES = {"storyboard_approval": "storyboard"}
_AE_FALLBACK_VOCAB = ("script", "lyrics", "character_images", "music", "storyboard")


def _ae_kind(kind):
    return _AE_KIND_ALIASES.get(kind, kind)


def _ae_vocabulary():
    words = getattr(AE, "_KIND_WORDS", None) if AE is not None else None
    return set(words or _AE_FALLBACK_VOCAB)


def _presented(pairs, scope, ctx):
    """The one presentation this reply must answer, as the interpreter's record.

    Nothing in it is approved: ``approvals`` is empty, so the reply alone can
    decide. ``scope`` is the binding's tenant/run, so a reply from another one
    reads as ``foreign``.
    """
    scope, ctx = scope or {}, ctx or {}
    artifacts, tokens = {}, []
    for kind, revision, digest in pairs:
        token = _ae_kind(kind)
        artifacts[token] = {"revision": revision, "sha256": digest}
        if token not in tokens:
            tokens.append(token)
    return {
        "artifacts": artifacts,
        "asks": [{"ask_id": "presented:%s" % ",".join(tokens), "kinds": tokens,
                  "message_id": ctx.get("presented_message_id"),
                  "revisions": {k: artifacts[k]["revision"] for k in tokens},
                  "state": "open"}],
        "approvals": [],
        "sent": True,
        "run_id": scope.get("run_id"),
        "tenant_id": scope.get("tenant_id"),
    }


class ApprovalBook:
    """Bindings and receipts for one client run. In memory, no IO, no sending.

    ``bindings`` owns artifact kinds exclusively; ``receipts`` holds one
    receipt per approval, each bound to the exact ``binding_digest`` it saw.
    """

    def __init__(self):
        self._bindings = {}
        self._claims = {}
        self._receipts = {}
        self._elected = {}

    # -- bindings ---------------------------------------------------------

    def bind(self, binding_id, components, tenant_id=None, run_id=None):
        """Create the one binding for this package, or refuse.

        Refuses an incomplete package, a granular (scene/character) kind, and
        any kind already claimed by a different binding.
        """
        if binding_id in self._bindings:
            raise BindingError("BINDING_EXISTS", "%r is already bound" % (binding_id,),
                               {"binding_id": binding_id})
        defects = validate_components(components)
        if defects:
            code = ("NO_GRANULAR_APPROVAL_LOOP"
                    if any(d["issue"] == "NO_GRANULAR_APPROVAL_LOOP" for d in defects)
                    else "BINDING_INCOMPLETE")
            raise BindingError(code, "the creative package is not complete",
                               {"binding_id": binding_id, "defects": defects})
        overlap = sorted(k for k in components if self._claims.get(k) not in (None, binding_id))
        if overlap:
            raise BindingError(
                "BINDING_OVERLAP",
                "another binding already owns %s" % ", ".join(overlap),
                {"binding_id": binding_id, "overlap": overlap,
                 "owners": {k: self._claims[k] for k in overlap}})
        binding = {
            "schema_version": SCHEMA_VERSION,
            "binding_id": binding_id,
            "tenant_id": tenant_id,
            "run_id": run_id,
            "package": PACKAGE_APPROVAL,
            "components": {k: _normalise(v) for k, v in components.items()},
            "binding_digest": binding_digest(components),
        }
        self._bindings[binding_id] = binding
        for kind in binding["components"]:
            self._claims[kind] = binding_id
        return binding

    def binding(self, binding_id):
        return self._bindings.get(binding_id)

    def component(self, binding_id, kind):
        return ((self._bindings.get(binding_id) or {}).get("components") or {}).get(kind)

    def update_component(self, binding_id, kind, revision, digest):
        """Move one component forward. Only this binding's receipt can go stale."""
        binding = self._bindings.get(binding_id)
        if binding is None:
            raise BindingError("BINDING_ABSENT", "%r is not bound" % (binding_id,),
                               {"binding_id": binding_id})
        _require_component_kind(kind)
        old = binding["components"].get(kind) or {}
        if old.get("digest") == digest and old.get("revision") == revision:
            return {"changed": False, "binding_id": binding_id, "invalidated": []}
        binding["components"][kind] = {"revision": revision, "digest": digest}
        binding["binding_digest"] = binding_digest(binding["components"])
        return {"changed": True, "binding_id": binding_id,
                "invalidated": self.note_change([kind])["invalidated"]}

    # -- receipts ---------------------------------------------------------

    def _decision(self, pairs, scope, ctx):
        """The client's decision on exactly this presentation, or a refusal.

        The words are judged ONLY by the existing
        ``script_approval.approval_events`` interpreter: an unambiguous
        affirmative reply approves, and refusal, revision, ambiguous, unseen
        and foreign replies do not. The evidence is never invented -- no
        approver, no source, no timestamp. This is the one decision rule:
        ``approve`` and ``elect`` both go through it.
        """
        ctx = ctx or {}
        text = ctx.get("reply_text")
        if not isinstance(text, str) or not text.strip():
            raise BindingError("APPROVAL_NOT_ACTUAL",
                               "an approval needs the actual client reply",
                               {"reply_text": ctx.get("reply_text")})
        if str(ctx.get("source") or "").strip().lower() != "client":
            raise BindingError("APPROVAL_NOT_ACTUAL",
                               "only a real client reply approves artifacts",
                               {"source": ctx.get("source")})
        if AE is None:
            raise BindingError("PREFERENCE_CHECK_UNAVAILABLE",
                               "cannot prove the reply is a decision, not a preference")
        if AE.is_preference_reply(text):
            raise BindingError("PREFERENCE_IS_NOT_APPROVAL",
                               "a viewing choice or preference does not approve artifacts")
        approver = ctx.get("approved_by")
        if not isinstance(approver, str) or not approver.strip():
            raise BindingError("APPROVAL_NOT_ACTUAL",
                               "an approval needs the approving identity",
                               {"approved_by": ctx.get("approved_by")})
        timestamp = ctx.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp.strip():
            raise BindingError("APPROVAL_NOT_ACTUAL",
                               "an approval needs its real time; no timestamp is invented",
                               {"timestamp": ctx.get("timestamp")})
        presented = _presented(pairs, scope, ctx)
        read = AE.interpret_reply(text, presented, ctx)
        intent = read.get("intent")
        if intent == "preference":
            raise BindingError("PREFERENCE_IS_NOT_APPROVAL",
                               "a viewing choice or preference does not approve artifacts",
                               {"intent": intent})
        if intent != "approve" or not AE.is_affirmative(text):
            raise BindingError("APPROVAL_NOT_ACTUAL",
                               "that reply is not an approval: %s" % (intent,),
                               {"intent": intent, "reason_code": read.get("reason_code")})
        decided = set(read.get("kinds") or ())
        partial = sorted(t for t in presented["asks"][0]["kinds"]
                         if t in _ae_vocabulary() and t not in decided)
        if partial:
            raise BindingError("APPROVAL_NOT_WHOLE_PACKAGE",
                               "that reply approves only %s, not the whole package"
                               % ", ".join(sorted(decided) or ("nothing",)),
                               {"not_approved": partial, "approved": sorted(decided)})
        return text.strip(), approver.strip(), timestamp.strip()

    def approve(self, binding_id, ctx):
        """Record the client's whole-package approval from an actual reply.

        Refuses without a real client reply from a real approver, refuses a
        preference, and refuses any reply the interpreter does not read as an
        unambiguous affirmative answer to the presented package. It never
        invents an approver, a timestamp or a decision.
        """
        binding = self._bindings.get(binding_id)
        if binding is None:
            raise BindingError("BINDING_ABSENT", "%r is not bound" % (binding_id,),
                               {"binding_id": binding_id})
        ctx = ctx or {}
        pairs = [(kind, v.get("revision"), v.get("digest"))
                 for kind, v in binding["components"].items()]
        text, approver, timestamp = self._decision(pairs, binding, ctx)
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "receipt_id": "receipt:%s:%s" % (binding_id, binding["binding_digest"][:16]),
            "binding_id": binding_id,
            "package": PACKAGE_APPROVAL,
            "decision": "approved",
            "binding_digest": binding["binding_digest"],
            "components": {k: dict(v) for k, v in binding["components"].items()},
            "tenant_id": binding.get("tenant_id"),
            "run_id": binding.get("run_id"),
            "approved_by": approver,
            "reply_text_sha": _sha(text),
            "reply_to_message_id": ctx.get("reply_to_message_id"),
            "source": "client",
            "source_ref": ctx.get("source_ref"),
            "timestamp": timestamp,
            "state": ACTIVE,
            "invalidated_by": None,
        }
        self._receipts[binding_id] = receipt
        return receipt

    def receipt_for(self, binding_id):
        return self._receipts.get(binding_id)

    def elect(self, kind, revision, digest, ctx):
        """A separately elected approval, preserved as its own receipt.

        Only for kinds already outside the package; a package component is
        covered by the one package approval and cannot be elected separately.
        It needs the very same evidence as a package approval and invents
        nothing: no approver, no source, no timestamp.
        """
        if kind in COMPONENTS:
            raise BindingError(
                "COMPONENT_ALREADY_COVERED",
                "%r is bound by the whole-package approval" % (kind,),
                {"kind": kind})
        if _granular(kind):
            raise BindingError("NO_GRANULAR_APPROVAL_LOOP",
                               "%r would open a per-scene or per-character loop" % (kind,),
                               {"kind": kind})
        ctx = ctx or {}
        text, approver, timestamp = self._decision(
            [(kind, revision, digest)], ctx, ctx)
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "receipt_id": "elected:%s:%s" % (kind, digest),
            "binding_id": None,
            "package": None,
            "decision": "approved",
            "binding_digest": None,
            "components": {kind: {"revision": revision, "digest": digest}},
            "tenant_id": ctx.get("tenant_id"),
            "run_id": ctx.get("run_id"),
            "approved_by": approver,
            "reply_text_sha": _sha(text),
            "reply_to_message_id": ctx.get("reply_to_message_id"),
            "source": "client",
            "source_ref": ctx.get("source_ref"),
            "timestamp": timestamp,
            "state": ACTIVE,
            "invalidated_by": None,
        }
        self._elected[kind] = receipt
        return receipt

    def elected(self, kind):
        return self._elected.get(kind)

    # -- change propagation ----------------------------------------------

    def receipt_list(self):
        return list(self._receipts.values()) + list(self._elected.values())

    def note_change(self, changed):
        """Invalidate only the receipts that bind a changed kind."""
        changed = set(changed or ())
        invalidated = []
        for receipt in self.receipt_list():
            if receipt.get("state") != ACTIVE:
                continue
            hit = sorted(changed & set(receipt.get("components") or {}))
            if not hit:
                continue
            receipt["state"] = INVALIDATED
            receipt["invalidated_by"] = {"kinds": hit}
            invalidated.append(receipt["receipt_id"])
        return {"changed": sorted(changed), "invalidated": invalidated}

    # -- the gate ---------------------------------------------------------

    def admissibility(self, binding_id):
        """May work that needs this package approval proceed? Fails closed."""
        binding = self._bindings.get(binding_id)
        if binding is None:
            return {"ok": False, "code": "BINDING_ABSENT", "binding_id": binding_id}
        receipt = self._receipts.get(binding_id)
        if receipt is None:
            return {"ok": False, "code": "APPROVAL_MISSING", "binding_id": binding_id}
        if receipt.get("state") != ACTIVE:
            return {"ok": False, "code": "APPROVAL_INVALIDATED",
                    "binding_id": binding_id,
                    "invalidated_by": receipt.get("invalidated_by")}
        if receipt.get("binding_digest") != binding.get("binding_digest"):
            return {"ok": False, "code": "APPROVAL_STALE", "binding_id": binding_id,
                    "approved_digest": receipt.get("binding_digest"),
                    "current_digest": binding.get("binding_digest")}
        return {"ok": True, "code": "APPROVED", "binding_id": binding_id,
                "binding_digest": binding["binding_digest"]}


def _selfcheck():
    """Refusal texts never open the gate. Run: python3 approval_bindings.py"""
    def ctx(text, **extra):
        base = {"reply_text": text, "source": "client", "source_ref": "msg-1",
                "approved_by": "client_001", "timestamp": "2026-10-24T12:00:00Z"}
        base.update(extra)
        return base

    parts = lambda: {k: {"revision": 1, "digest": "d-" + k} for k in COMPONENTS}
    for text in ("no", "I do not approve", "revise the ending", "not yet"):
        book = ApprovalBook()
        book.bind("package", parts())
        try:
            book.approve("package", ctx(text))
        except BindingError:
            pass
        else:
            raise AssertionError("%r opened the gate" % (text,))
        assert book.admissibility("package")["ok"] is False
    for bad in ({}, ctx("go", source="agent"),
                ctx("show me the script first"), ctx("go", timestamp=None)):
        book = ApprovalBook()
        book.bind("package", parts())
        try:
            book.elect("storyboard_approval", 1, "d-story", bad)
        except BindingError:
            pass
        else:
            raise AssertionError("elect minted an approval from %r" % (bad,))
    book = ApprovalBook()
    book.bind("package", parts())
    receipt = book.approve("package", ctx("yes, approve"))
    assert book.admissibility("package")["ok"] is True
    assert receipt["approved_by"] == "client_001" and receipt["source"] == "client"
    assert receipt["timestamp"] == "2026-10-24T12:00:00Z"
    print("self-check ok")


if __name__ == "__main__":
    _selfcheck()
