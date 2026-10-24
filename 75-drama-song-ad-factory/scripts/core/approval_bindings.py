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

SCOPE IS BOUND IN BOTH DIRECTIONS. An approval names what it approves: a reply
that names nothing specific ("approved", "yes", "approve one of them") is an
ambiguity and mints nothing; a reply that names part of the package ("the scene
plan is approved") mints exactly that part and leaves the rest unapproved; a
reply that names the package (or every component) is the one whole-package
approval. The receipt covers what the client named and nothing more.

The component list is the same table ``check_stage`` reads
(``story_first_contracts.APPROVAL_BINDS``) and EVERY judgement about the
client's words is the existing ``script_approval.approval_events`` interpreter
(``interpret_reply``, ``is_affirmative``, ``is_preference_reply``) read against
the scope the reply itself names: only an unambiguous affirmative reply from a
real client with a real approver, at its real time, approves. Refusal,
revision, ambiguous, unseen and foreign replies all leave the gate closed, and
a reply that names no artifact and no package approves nothing specific -- it
mints nothing. This module adds no second decision rule, no writer and no IO:
it records decisions the caller already has and refuses everything else.
"""
from __future__ import annotations

import hashlib
import re

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


#: A name the client's words can carry, and every presented token it can stand
#: for. ``character_images`` and ``episode_cast_manifest`` are the same
#: artifact under two names, so the words work in either presentation.
_CANON_EQUIV = {
    "research_bundle": ("research_bundle",),
    "character_images": ("character_images", "episode_cast_manifest"),
    "episode_cast_manifest": ("episode_cast_manifest", "character_images"),
    "episode_world": ("episode_world",),
    "causal_story_beats": ("causal_story_beats",),
    "scene_plan": ("scene_plan",),
    "script": ("script",),
    "lyrics": ("lyrics",),
    "creative_package_manifest": ("creative_package_manifest",),
    "storyboard": ("storyboard", "storyboard_approval"),
    "music": ("music",),
}

#: The words that name one artifact, matched longest phrase first, so
#: "story beats" beats "story" and "song lyrics" beats "song". The canonical
#: name is then looked up in _CANON_EQUIV for the presented token it stands for.
_ARTIFACT_PHRASES = (
    ("creative_package_manifest", "creative package manifest"),
    ("creative_package_manifest", "package manifest"),
    ("creative_package_manifest", "creative manifest"),
    ("creative_package_manifest", "manifest"),
    ("causal_story_beats", "causal story beats"),
    ("causal_story_beats", "story beats"),
    ("causal_story_beats", "causal beats"),
    ("causal_story_beats", "beats"),
    ("character_images", "episode cast manifest"),
    ("character_images", "cast manifest"),
    ("character_images", "cast list"),
    ("character_images", "character manifest"),
    ("character_images", "character list"),
    ("character_images", "character images"),
    ("character_images", "character pictures"),
    ("character_images", "character photos"),
    ("character_images", "characters"),
    ("character_images", "pictures"),
    ("character_images", "images"),
    ("character_images", "cast"),
    ("episode_world", "episode world"),
    ("episode_world", "world bible"),
    ("episode_world", "setting"),
    ("episode_world", "world"),
    ("research_bundle", "research bundle"),
    ("research_bundle", "research pack"),
    ("research_bundle", "research notes"),
    ("research_bundle", "research"),
    ("scene_plan", "scene plans"),
    ("scene_plan", "scene list"),
    ("scene_plan", "scene plan"),
    ("scene_plan", "scenes"),
    ("scene_plan", "scene"),
    ("lyrics", "song lyrics"),
    ("lyrics", "lyric sheet"),
    ("lyrics", "song text"),
    ("lyrics", "song words"),
    ("lyrics", "lyrics"),
    ("lyrics", "lyric"),
    ("lyrics", "words"),
    ("script", "screenplay"),
    ("script", "script"),
    ("script", "story"),
    ("storyboard", "shot list"),
    ("storyboard", "storyboard"),
    ("storyboard", "shots"),
    ("music", "soundtrack"),
    ("music", "music"),
    ("music", "audio"),
)

#: The package, named as one thing. Naming one of these names every
#: component. A bare "yes", "approved" or "all of those" names none of them.
_PACKAGE_PHRASES = (
    "drama song ad", "song ad", "creative package", "package",
    "deliverables", "deliverable", "artifacts", "artifact",
    "everything else", "everything", "it all", "all of it",
    "the whole thing", "the entire thing", "the rest of it",
    "the ad", "ad",
)

#: one index, longest phrase first: "creative package manifest" must be read
#: as one artifact before "package" is read as the whole package
_SCOPE_INDEX = tuple(sorted(
    tuple(("artifact", canon, phrase) for canon, phrase in _ARTIFACT_PHRASES) +
    tuple(("package", None, phrase) for phrase in _PACKAGE_PHRASES),
    key=lambda row: (-len(row[2].split()), -len(row[2]), row[2])))


def _norm_words(text):
    return re.sub(r"\s+", " ",
                  re.sub(r"[^a-z0-9+' ]+", " ", str(text or "").lower())).strip()


#: every word that NAMES what a reply may approve -- the artifact phrases, the
#: package phrases and the canonical kinds. The idiom register allows exactly
#: these as content words, so an approval can name its referent and nothing
#: else can hide beside it.
_SCOPE_WORDS = frozenset(
    w for _, phrase in _ARTIFACT_PHRASES for w in phrase.split()) | frozenset(
    w for phrase in _PACKAGE_PHRASES for w in phrase.split()) | frozenset(
    w for name in _CANON_EQUIV for w in name.split("_"))


def _presented_revision(pairs, token):
    for kind, revision, _digest in pairs:
        if _ae_kind(kind) == token:
            return revision
    return None


def _phrase_re(phrase):
    return re.compile(r"\b%s\b" % re.escape(phrase).replace(r"\ ", r"\s+"))


def _scan_scope(text):
    """(named canonicals, package named?) from the reply's own words.

    A phrase is consumed once, so "the story beats" names the beats and never
    the script, and "the song lyrics" never becomes the music.
    """
    norm = _norm_words(text)
    canon, taken, package = [], [], False
    for kind, target, phrase in _SCOPE_INDEX:
        for m in _phrase_re(phrase).finditer(norm):
            span = (m.start(), m.end())
            if any(not (span[1] <= a or span[0] >= b) for a, b in taken):
                continue
            taken.append(span)
            if kind == "package":
                package = True
            elif target not in canon:
                canon.append(target)
    return canon, package


def _resolve_scope(text, tokens):
    """Which presented tokens this reply approves. Four answers:

    ("all", tokens, [])     names the package, or every presented artifact
    ("some", subset, [])    names part of the package -- mints exactly that
    ("unknown", [], names)  names an artifact that was never presented
    ("none", [], [])        names nothing -- approves nothing specific

    An artifact that was never presented refuses the whole reply, even beside a
    package name: naming one thing that exists never licenses another that does
    not.
    """
    tokens = list(tokens)
    canon, package = _scan_scope(text)
    named, unknown = [], []
    for name in canon:
        token = next((t for t in _CANON_EQUIV.get(name, (name,)) if t in tokens), None)
        if token is None:
            unknown.append(name)
        elif token not in named:
            named.append(token)
    if unknown:
        return "unknown", [], sorted(set(unknown))
    if package:
        return "all", tokens, []
    if named:
        return ("all" if set(named) >= set(tokens) else "some"), sorted(named), []
    return "none", [], []


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
        ``script_approval.approval_events`` interpreter and the scope the
        reply itself names: an unambiguous affirmative reply that names the
        package, or the artifacts it approves, is a decision at that scope;
        refusal, revision, question, quote, conditional, selection, edit,
        preference, unseen and foreign replies are not. The evidence is never
        invented -- no approver, no source, no timestamp. This is the one
        decision rule: ``approve`` and ``elect`` both go through it.
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
        reason = read.get("reason_code")
        if intent == "preference":
            raise BindingError("PREFERENCE_IS_NOT_APPROVAL",
                               "a viewing choice or preference does not approve artifacts",
                               {"intent": intent})
        tokens = list(presented["asks"][0]["kinds"])
        status, kinds, unknown = _resolve_scope(text, tokens)
        # THE REFERENT IS BOUND IN BOTH DIRECTIONS. A revision the reply names
        # must be one this presentation showed, for every artifact it approves:
        # a receipt never binds a revision the reply did not name, and a reply
        # that names a revision that was never presented mints nothing.
        named_revision = AE.named_revision(text) if AE is not None else None
        if named_revision is not None:
            check = tokens if status == "all" else list(kinds)
            off = sorted(t for t in check
                         if _presented_revision(pairs, t) != named_revision)
            if off:
                raise BindingError(
                    "APPROVAL_NAMES_UNSEEN_REVISION",
                    read.get("question") or (
                        "revision %d was never presented for %s"
                        % (named_revision, ", ".join(off))),
                    {"named_revision": named_revision, "kinds": off,
                     "presented": {t: _presented_revision(pairs, t) for t in off},
                     "intent": intent, "reason_code": reason})
        if status == "unknown":
            raise BindingError(
                "APPROVAL_NAMES_UNKNOWN_ARTIFACT",
                read.get("question") or ("%s is not part of the presented package"
                                         % ", ".join(unknown)),
                {"named": unknown, "components": list(COMPONENTS)})
        if intent == "unseen":
            # AN UNSEEN REFERENT IS A REFUSAL, NAMED. The interpreter's read
            # stands. The single reply it does not refuse is the one whose
            # referent IS presented under a name its own vocabulary cannot
            # carry ("the characters", the package's own name): the scope above
            # resolved those words to artifacts this exact presentation shows,
            # and the reply named no revision of its own. Every other "unseen"
            # names a revision or an artifact that was never presented.
            name_gap = (reason == "REPLY_NAMES_UNSEEN_KIND"
                        and status in ("all", "some") and named_revision is None)
            if not name_gap:
                raise BindingError(
                    "APPROVAL_NAMES_UNSEEN_REVISION" if named_revision is not None
                    else "APPROVAL_NAMES_UNSEEN_ARTIFACT",
                    read.get("question")
                    or "that reply names something that was never presented",
                    {"intent": intent, "reason_code": reason,
                     "named": list(unknown or kinds),
                     "components": list(COMPONENTS)})
        # The interpreter's form screens still decide what KIND of reply this
        # is: a question, a quote, a condition, a selection, an edit request or
        # a negation never approves. Two of its reads are only its vocabulary
        # failing to name what the client named ("the scene plan", "the
        # characters") -- when the scope above resolves those words to a
        # presented artifact, the reply stands. The third is its idiom register
        # ("Green light the drama song ad package.") -- a clear affirmative
        # that names its referent and passes the very same screens.
        reads_as_decision = (
            (intent == "approve" and AE.is_affirmative(text))
            or (reason == "REPLY_NAMES_NO_WHOLE_ARTIFACT" and status in ("all", "some"))
            or (status in ("all", "some") and AE.is_idiom_approval(text, _SCOPE_WORDS)))
        if not reads_as_decision:
            raise BindingError("APPROVAL_NOT_ACTUAL",
                               "that reply is not an approval: %s" % (intent,),
                               {"intent": intent, "reason_code": reason})
        if status == "none":
            raise BindingError(
                "APPROVAL_SCOPE_AMBIGUOUS",
                "that reply approves nothing specific: it names no artifact and no package",
                {"named": [], "components": list(COMPONENTS)})
        return text.strip(), approver.strip(), timestamp.strip(), list(kinds)

    def approve(self, binding_id, ctx):
        """Record the client's approval from an actual reply, at its own scope.

        The receipt covers exactly what the reply named -- every component for
        an approval of the package, only the named components for a partial
        one, and nothing at all for a reply that names nothing specific. It
        refuses without a real client reply from a real approver, refuses a
        preference, and never invents an approver, a timestamp or a decision.
        """
        binding = self._bindings.get(binding_id)
        if binding is None:
            raise BindingError("BINDING_ABSENT", "%r is not bound" % (binding_id,),
                               {"binding_id": binding_id})
        ctx = ctx or {}
        pairs = [(kind, v.get("revision"), v.get("digest"))
                 for kind, v in binding["components"].items()]
        text, approver, timestamp, kinds = self._decision(pairs, binding, ctx)
        whole = set(kinds) == set(binding["components"])
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "receipt_id": ("receipt:%s:%s" % (binding_id, binding["binding_digest"][:16])
                           if whole else "receipt:%s:%s:partial:%s:%s" % (
                               binding_id, binding["binding_digest"][:16],
                               "+".join(sorted(kinds)), _sha(text)[:8])),
            "binding_id": binding_id,
            "package": PACKAGE_APPROVAL,
            "decision": "approved",
            "scope": PACKAGE_APPROVAL if whole else "partial",
            "binding_digest": binding["binding_digest"],
            "components": {k: dict(binding["components"][k]) for k in kinds},
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
        self._receipts.setdefault(binding_id, []).append(receipt)
        return receipt

    def receipt_for(self, binding_id):
        """The latest receipt for this binding -- whole-package or partial."""
        receipts = self._receipts.get(binding_id) or []
        return receipts[-1] if receipts else None

    def receipts_for(self, binding_id):
        return list(self._receipts.get(binding_id) or [])

    def coverage(self, binding_id):
        """What the approvals cover and what is still unapproved."""
        want = set((self._bindings.get(binding_id) or {}).get("components") or COMPONENTS)
        covered = set()
        for receipt in self._receipts.get(binding_id) or []:
            if receipt.get("state") == ACTIVE:
                covered |= set(receipt.get("components") or {})
        return {"approved": sorted(covered & want), "missing": sorted(want - covered)}

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
        text, approver, timestamp, kinds = self._decision(
            [(kind, revision, digest)], ctx, ctx)
        back = {_ae_kind(kind): kind}
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "receipt_id": "elected:%s:%s" % (kind, digest),
            "binding_id": None,
            "package": None,
            "decision": "approved",
            "binding_digest": None,
            "components": {back[t]: {"revision": revision, "digest": digest}
                           for t in kinds},
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
        out = []
        for receipts in self._receipts.values():
            out.extend(receipts)
        return out + list(self._elected.values())

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
        """May work that needs this package approval proceed? Fails closed.

        A partial approval leaves the gate closed. It opens only when the live
        receipts between them cover every component at the revision and digest
        the binding holds now.
        """
        binding = self._bindings.get(binding_id)
        if binding is None:
            return {"ok": False, "code": "BINDING_ABSENT", "binding_id": binding_id}
        receipts = self._receipts.get(binding_id) or []
        if not receipts:
            return {"ok": False, "code": "APPROVAL_MISSING", "binding_id": binding_id}
        live = [r for r in receipts
                if r.get("state") == ACTIVE and _covers_current(binding, r)]
        covered = set()
        for receipt in live:
            covered |= set(receipt.get("components") or {})
        if covered >= set(COMPONENTS):
            for receipt in live:
                if (set(receipt.get("components") or {}) >= set(COMPONENTS)
                        and receipt.get("binding_digest") != binding.get("binding_digest")):
                    return {"ok": False, "code": "APPROVAL_STALE", "binding_id": binding_id,
                            "approved_digest": receipt.get("binding_digest"),
                            "current_digest": binding.get("binding_digest")}
            return {"ok": True, "code": "APPROVED", "binding_id": binding_id,
                    "binding_digest": binding["binding_digest"]}
        if not live:
            return {"ok": False, "code": "APPROVAL_INVALIDATED",
                    "binding_id": binding_id,
                    "invalidated_by": receipts[-1].get("invalidated_by")}
        return {"ok": False, "code": "APPROVAL_INCOMPLETE", "binding_id": binding_id,
                "approved": sorted(covered), "missing": sorted(set(COMPONENTS) - covered)}


def _covers_current(binding, receipt):
    """Every component this receipt covers is still the version it approved."""
    for kind, value in (receipt.get("components") or {}).items():
        current = (binding.get("components") or {}).get(kind) or {}
        if (current.get("digest") != value.get("digest")
                or current.get("revision") != value.get("revision")):
            return False
    return True


def _selfcheck():
    """Refusal texts never open the gate; scope is bound in both directions.
    Run: python3 approval_bindings.py"""
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
    for text in ("approved", "yes", "approve one of them", "all of those",
                 "the ones we discussed", "sounds good"):
        try:
            book.approve("package", ctx(text))
        except BindingError:
            pass
        else:
            raise AssertionError("%r minted an approval" % (text,))
        assert book.receipt_for("package") is None, text
    receipt = book.approve("package", ctx("The scene plan is approved."))
    assert set(receipt["components"]) == {"scene_plan"}, receipt["components"]
    assert book.admissibility("package")["code"] == "APPROVAL_INCOMPLETE"
    receipt = book.approve("package", ctx("I approve the whole creative package."))
    assert set(receipt["components"]) == set(COMPONENTS)
    assert book.admissibility("package")["ok"] is True
    assert receipt["approved_by"] == "client_001" and receipt["source"] == "client"
    assert receipt["timestamp"] == "2026-10-24T12:00:00Z"
    print("self-check ok")


if __name__ == "__main__":
    _selfcheck()
