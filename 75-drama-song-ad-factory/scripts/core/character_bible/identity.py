#!/usr/bin/env python3
"""S75-T05: reusable character identity schema and full-cast refusals.

Three records stay separate on purpose:

* ``character_identity`` -- who the person is, forever. Face, age, hair,
  wardrobe *rules*, continuity constraints and the reusable prompt block live
  here. The record survives a change of episode setting: the same
  ``character_id`` and history appear at a backyard barbecue and at the White
  House.
* ``episode_setting`` -- where and when this episode happens, plus the one
  wardrobe instance worn there. Setting fields never enter an identity record.
* ``episode_cast_manifest`` -- which identities were selected at which exact
  revision, what each person does in this story, and the crowd rules.

A face-and-clothes file is not a story bible, so an identity also has to carry
wants, fears, beliefs and speech. Validation is structural: keys, types, IDs,
references and substantive non-empty content. It refuses an incomplete cast,
an undeclared or anonymous speaker, a dangling relationship or scene, a stale
identity revision, and any crowd group that singles a member out without
promoting that member to a full identity.

Standard library only. Run the focused tests with::

    python3 75-drama-song-ad-factory/scripts/core/character_bible/test_identity_s75_t05.py
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets

__all__ = [
    "CastDefect", "IdentityDefect", "canonical_digest", "library_digest",
    "validate_episode_setting", "validate_identity", "validate_library",
    "validate_cast", "seal_identity", "receipt_digest", "resolve_receipt",
    "mint_receipt",
    "SCHEMA_VERSION", "MANIFEST_SCHEMA_VERSION", "EPISODE_SCHEMA_VERSION",
    "EPISODE_ONLY_FIELDS", "ROLES", "CROWD_REQUIRED",
    "ANONYMOUS_SPEAKER_PATTERNS", "APPROVAL_BINDING_KEYS", "CLAIM_KEYS",
    "RECEIPT_KIND", "MINT_FIELD",
]

SCHEMA_VERSION = "s75.identity.v1"
MANIFEST_SCHEMA_VERSION = "s75.cast_manifest.v1"
EPISODE_SCHEMA_VERSION = "s75.episode_setting.v1"

#: Episode/setting fields. Presence inside an identity record is a hard defect:
#: changing the venue must never rewrite who the person is.
EPISODE_ONLY_FIELDS = frozenset({
    "setting", "setting_name", "location", "venue", "era", "time_period",
    "season", "time_of_day", "episode_setting", "episode_world",
    "wardrobe_instance", "outfit_today", "scene_location",
})

STORY_STATUS = frozenset({"FICTION", "OWNER_SUPPLIED", "REAL_PERSON"})
#: The only forward order. Skipping or going back is refused everywhere.
DRAFT_ORDER = ("DRAFT_INCOMPLETE", "DRAFT_COMPLETE", "APPROVED")
DRAFT_STATES = frozenset(DRAFT_ORDER)
SYNC_STATES = frozenset({"PENDING", "OFFLINE", "CONFLICTED", "SYNCED", "LOCAL_ONLY"})

#: Every cast role that entitles a person to individual lines, reactions or
#: causal consequence. Each one requires a full identity, never a crowd slot.
ROLES = frozenset({
    "lead", "supporting", "recurring", "speaking", "reacting",
    "meaningful_background",
})

#: Generic descriptors that hide an undeclared individual. A line or an action
#: attributed to one of these is refused; the person must be declared by ID.
ANONYMOUS_SPEAKER_PATTERNS = (
    "a woman", "a man", "a worker", "a customer", "someone", "somebody",
    "a person", "the crowd", "people in background", "background people",
    "a bystander", "the manager", "a voice",
)

CROWD_REQUIRED = (
    "crowd_group_id", "composition", "count", "age_range", "roles",
    "location_placement", "collective_behavior", "permitted_motion",
    "attention_direction", "interaction_with_leads", "wardrobe_palette",
    "camera_limits", "entry_exit_rule", "recurrence", "dialogue",
    "reference_provenance", "scene_ids",
)

#: Identity fields that are bookkeeping, not content. They are excluded from the
#: content digest so an approval receipt or cache refresh cannot look like a
#: rewrite of the person.
_DIGEST_EXCLUDED = frozenset({
    "content_digest", "approval_bindings", "draft_state",
    "shared_source", "local_cache", "sync_state",
})


class IdentityDefect(ValueError):
    """One actionable packet of every identity/library defect found."""

    def __init__(self, defects):
        self.defects = list(defects)
        super().__init__("; ".join(d["message"] for d in self.defects))


class CastDefect(ValueError):
    """One actionable packet of every cast/selection defect found."""

    def __init__(self, defects):
        self.defects = list(defects)
        super().__init__("; ".join(d["message"] for d in self.defects))


def _defect(field, code, message):
    return {"field": field, "code": code, "message": message}


# --- reading caller-supplied values -----------------------------------------
#
# SECURITY (do not loosen in a later round): nothing below reaches a security
# decision through overridable dispatch. ``isinstance`` is deliberately not
# used for these gates. A dict subclass can lie in ``get()``/``keys()``/
# ``__len__``/``__bool__``, a str subclass can lie in ``__eq__`` (Python even
# calls the subclass's reflected ``__eq__`` first), and a list subclass can lie
# in ``__bool__``/``__len__``. So every subclass is refused outright with a
# named reason instead of being believed, and every decision runs on one plain
# builtin copy built here.

def _plain(value):
    """One builtin dict copy of a caller mapping, or None if it is not exactly
    a builtin dict. Decide on the copy, never on the caller's object."""
    if type(value) is not dict:
        return None
    return {k: v for k, v in value.items()}


def _plain_list(value):
    """One builtin list copy of a caller sequence, or None if it is not exactly
    a builtin list. Emptiness and length are tested on THIS copy."""
    if type(value) is not list:
        return None
    return list(value)


def _is_text(value, expected):
    """Exact builtin str compared to an exact builtin str. No subclass eq: with
    a str subclass on either side Python calls the subclass's reflected
    ``__eq__`` first and the caller would answer the question."""
    return type(value) is str and type(expected) is str and value == expected


def _in(value, allowed):
    """Membership for a caller value: exact builtin str only."""
    return type(value) is str and value in allowed


def _text(value):
    return type(value) is str and value.strip() != ""


def _text_list(value, minimum=1):
    return (type(value) is list and len(value) >= minimum
            and all(_text(item) for item in value))


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_digest(obj, *, exclude=_DIGEST_EXCLUDED):
    """SHA-256 over canonical JSON, ignoring bookkeeping fields."""
    body = {k: v for k, v in dict(obj).items() if k not in exclude}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def seal_identity(record):
    """Attach the content digest an identity record is addressed by."""
    sealed = _plain(record)
    if sealed is None:
        raise IdentityDefect([_defect("<record>", "NOT_OBJECT",
                                      "identity record must be a plain object, "
                                      "not %s" % type(record).__name__)])
    sealed.setdefault("schema_version", SCHEMA_VERSION)
    sealed["content_digest"] = canonical_digest(sealed)
    return sealed


def library_digest(snapshot):
    """Digest of the selected library snapshot the manifest binds to."""
    return canonical_digest(snapshot, exclude=frozenset({"local_cache", "sync_state"}))


# --- approval receipts ------------------------------------------------------

#: One approval binding is ONE receipt, and a receipt is a closed shape. Any
#: other key is a forged or hand-written object, not a record of an approval.
MINT_FIELD = "mint_mark"
RECEIPT_KIND = "approval_receipt"
APPROVAL_BINDING_KEYS = frozenset({
    "kind", "receipt_id", "approver", "character_id", "from_state", "to_state",
    MINT_FIELD,
})
#: The claim a receipt makes. The mint mark is computed over exactly this.
CLAIM_KEYS = frozenset(APPROVAL_BINDING_KEYS - {MINT_FIELD})

#: SECURITY (do not loosen in a later round): the mint key lives in process
#: memory only. It is never written to disk, never stored in a record, never
#: logged. A receipt typed by hand, and a receipt rebuilt from a JSON file any
#: other run wrote, cannot both carry a mark this key reproduces -- so both are
#: refused. This is what makes "the explicit promotion step is the sole minter"
#: a property of the code instead of a claim in a docstring.
_MINT_KEY = secrets.token_bytes(32)
#: receipt_id -> the exact claim body that id was minted for. Memory only.
#: Single use: an id is minted once, so it can never be re-pointed at another
#: character or another promotion step.
_MINTED = {}


def _claim(receipt):
    return {k: receipt[k] for k in sorted(CLAIM_KEYS) if k in receipt}


def _mark(claim):
    """The mint mark over a receipt's own claim fields. Only the mint produces it."""
    return hmac.new(_MINT_KEY, _canonical(claim).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _verify_mint(body):
    """Recompute the mint mark. Returns the refusal reason, or None."""
    mark = body[MINT_FIELD]
    if len(mark) != 64:
        return ("an approval receipt carries a 64-character mint mark only the "
                "approval step can produce; this one has none")
    if not hmac.compare_digest(mark, _mark(_claim(body))):
        return ("the mint mark does not match the receipt's own fields, so this "
                "receipt was not minted by the approval step")
    if _MINTED.get(body["receipt_id"]) != _claim(body):
        return ("receipt id %r was never minted by the approval step; a receipt "
                "is single-use and cannot be typed by hand or reloaded from a "
                "JSON file" % body["receipt_id"])
    return None


def mint_receipt(fields):
    """The single minting path: stamp a receipt with a mark only this module can
    make. Only the explicit promotion step calls this.

    ``receipt_id`` is single use. Minting the same id again for a different
    character or a different promotion step is refused, so a receipt can never
    be replayed onto a second approval.
    """
    body = _plain(fields)
    if body is None:
        raise IdentityDefect([_defect("approval_bindings", "NOT_PLAIN_OBJECT",
                                      "a receipt is minted from a plain object, "
                                      "not %s" % type(fields).__name__)])
    if set(body) != set(CLAIM_KEYS):
        raise IdentityDefect([_defect("approval_bindings", "RECEIPT_SHAPE",
                                      "a receipt is minted from exactly %s"
                                      % (sorted(CLAIM_KEYS),))])
    for field in sorted(CLAIM_KEYS):
        if type(body[field]) is not str:
            raise IdentityDefect([_defect(field, "RECEIPT_FIELD",
                                          "receipt field %r must be a plain "
                                          "string, not %s"
                                          % (field, type(body[field]).__name__))])
    claim = _claim(body)
    prior = _MINTED.get(claim["receipt_id"])
    if prior is not None and prior != claim:
        raise IdentityDefect([_defect("receipt_id", "RECEIPT_REUSE",
                                      "receipt id %r is already minted for one "
                                      "promotion step and cannot be minted again "
                                      "for another; a receipt is single-use"
                                      % claim["receipt_id"])])
    _MINTED[claim["receipt_id"]] = claim
    return {**claim, MINT_FIELD: _mark(claim)}


def receipt_digest(receipt):
    """The digest a receipt is addressed by. Stable across key order."""
    return canonical_digest(_claim(_plain(receipt) or {}),
                            exclude=frozenset({"content_digest"}))


def resolve_receipt(binding, record):
    """Resolve one binding against the approval record it claims.

    Returns ``None`` only when the binding is a receipt the approval step
    actually minted for THIS record: exact builtin types, the closed shape, a
    mint mark that recomputes over the receipt's own fields, an approved id,
    and exactly the one promotion step that put the record into its current
    state. Otherwise the plain-English reason the binding is refused. A
    non-empty list is never enough, and a receipt typed by hand or reloaded
    from JSON never resolves.
    """
    body = _plain(binding)
    if body is None:
        return ("an approval binding must be a receipt object, not %s"
                % type(binding).__name__)
    target = _plain(record)
    if target is None:
        return ("the identity record must be an object, not %s"
                % type(record).__name__)
    unknown = sorted(k for k in body if k not in APPROVAL_BINDING_KEYS)
    if unknown:
        return ("an approval receipt carries only %s; %s is not a receipt"
                % (sorted(APPROVAL_BINDING_KEYS), unknown))
    missing = sorted(k for k in APPROVAL_BINDING_KEYS if k not in body)
    if missing:
        return ("an approval receipt carries exactly %s; %s is missing, so this "
                "was not minted by the approval step"
                % (sorted(APPROVAL_BINDING_KEYS), missing))
    for field in sorted(APPROVAL_BINDING_KEYS):
        if type(body[field]) is not str:
            return ("an approval receipt field %r must be a plain string, not %s"
                    % (field, type(body[field]).__name__))
    reason = _verify_mint(body)
    if reason is not None:
        return reason
    if not _is_text(body["kind"], RECEIPT_KIND):
        return "an approval binding must declare kind %r" % (RECEIPT_KIND,)
    for field in ("receipt_id", "approver"):
        if not body[field].strip():
            return "an approval receipt needs a non-empty %s" % field
    owner = body["character_id"]
    if not owner.strip():
        return "an approval receipt must name the character it approves"
    record_id = target.get("character_id")
    if not _is_text(record_id, owner):
        return ("approval receipt %r belongs to %r, not %r"
                % (body["receipt_id"], owner, record_id))
    state = target.get("draft_state")
    if not _is_text(state, "APPROVED"):
        return ("approval receipt %r claims an approved identity, but this "
                "record is %r" % (body["receipt_id"], state))
    start, end = body["from_state"], body["to_state"]
    if not _in(start, DRAFT_ORDER[:-1]):
        return "an approval receipt must name the draft state it promotes from"
    if end != "APPROVED":
        return "an approval receipt approves; its to_state must be 'APPROVED'"
    if end != DRAFT_ORDER[DRAFT_ORDER.index(start) + 1]:
        return ("approval receipt %r claims %r to %r, which is not one promotion "
                "step" % (body["receipt_id"], start, end))
    return None


def _validate_approval_bindings(record):
    """Every binding must resolve as a receipt the approval step minted.

    Dedupe is keyed on BOTH the receipt id and the promotion step the receipt
    claims: one receipt id is single use, and one promotion step takes exactly
    one receipt.
    """
    out = []
    approvals = _plain_list(record.get("approval_bindings", []))
    if approvals is None:
        return [_defect("approval_bindings", "APPROVALS",
                        "approval_bindings must be a plain list of approval "
                        "receipts; a list subclass is refused because it can "
                        "lie about being empty; never synthesize receipts")]
    if not approvals:          # tested on the builtin copy, never on the caller
        if _is_text(record.get("draft_state"), "APPROVED"):
            out.append(_defect("approval_bindings", "APPROVALS",
                               "an approved identity must carry the receipt that "
                               "approved it; approval is never a default"))
        return out
    if not _is_text(record.get("draft_state"), "APPROVED"):
        out.append(_defect("approval_bindings", "APPROVALS",
                           "only an approved identity carries approval receipts; "
                           "a draft carries none, so a receipt cannot be parked "
                           "on a draft"))
    seen_ids = {}
    seen_steps = {}
    for index, binding in enumerate(approvals):
        where = "approval_bindings[%d]" % index
        reason = resolve_receipt(binding, record)
        if reason is not None:
            out.append(_defect(where, "APPROVALS", "%s: %s" % (where, reason)))
            continue
        claim = _plain(binding)
        key = claim["receipt_id"]
        step = (claim["character_id"], claim["from_state"], claim["to_state"])
        if key in seen_ids:
            out.append(_defect(where, "APPROVALS",
                               "%s: receipt id %r is already bound at "
                               "approval_bindings[%d]; a receipt is single-use"
                               % (where, key, seen_ids[key])))
            continue
        if step in seen_steps:
            out.append(_defect(where, "APPROVALS",
                               "%s: %r to %r for %r is one promotion step and it "
                               "is already approved at approval_bindings[%d]; "
                               "one step takes exactly one receipt"
                               % (where, step[1], step[2], step[0],
                                  seen_steps[step])))
            continue
        seen_ids[key] = index
        seen_steps[step] = index
    return out


# --- identity ---------------------------------------------------------------

_PLAIN_REQUIRED = (
    "client_id", "character_id", "display_name", "identity_summary",
    "occupation", "social_context", "emotional_wound", "mistaken_belief",
    "behavior_under_pressure", "appearance_traits",
)
_LIST_REQUIRED = (
    "relevant_background_history", "competence", "fears", "beliefs",
    "contradictions", "habits",
)
_VISUAL_REQUIRED = ("face", "age", "hair", "wardrobe_rules",
                    "continuity_constraints", "prompt_block")


def _validate_identity(record):
    out = []
    given = record
    record = _plain(given)
    if record is None:
        return [_defect("<record>", "NOT_OBJECT",
                        "identity record must be a plain object, not %s; a dict "
                        "subclass is refused because it can lie in get() and "
                        "__len__" % type(given).__name__)]

    for field in sorted(EPISODE_ONLY_FIELDS & set(record)):
        out.append(_defect(field, "SETTING_IN_IDENTITY",
                           f"'{field}' is an episode-setting field; it does not belong in "
                           f"the reusable identity and must change without a new revision"))

    for field in _PLAIN_REQUIRED:
        if not _text(record.get(field)):
            out.append(_defect(field, "IDENTITY_INCOMPLETE",
                               f"'{field}' is required substantive content"))

    for field in _LIST_REQUIRED:
        if not _text_list(record.get(field)):
            out.append(_defect(field, "IDENTITY_INCOMPLETE",
                               f"'{field}' must be a non-empty list of non-empty strings"))

    if not _is_text(record.get("schema_version"), SCHEMA_VERSION):
        out.append(_defect("schema_version", "SCHEMA_VERSION",
                           f"expected '{SCHEMA_VERSION}'"))
    revision = record.get("revision")
    if type(revision) is not int or revision < 1:
        out.append(_defect("revision", "REVISION",
                           "revision must be a positive integer"))
    digest = record.get("content_digest")
    if type(digest) is not str or len(digest) != 64:
        out.append(_defect("content_digest", "DIGEST",
                           "content_digest must be a 64-character sha256"))
    elif digest != canonical_digest(record):
        out.append(_defect("content_digest", "DIGEST_MISMATCH",
                           "content_digest does not match the record content"))

    if not _in(record.get("story_status"), STORY_STATUS):
        out.append(_defect("story_status", "STORY_STATUS",
                           f"story_status must be one of {sorted(STORY_STATUS)}"))

    aliases = record.get("aliases", [])
    if type(aliases) is not list or not all(_text(a) for a in aliases):
        out.append(_defect("aliases", "ALIASES", "aliases must be a list of strings"))

    # wants / voice: typed, not embedded prose.
    wants = record.get("wants")
    if not (type(wants) is dict and _text(wants.get("external"))
            and _text(wants.get("internal"))):
        out.append(_defect("wants", "WANTS",
                           "wants must carry external and internal drivers"))
    voice = record.get("voice")
    if not (type(voice) is dict and _text(voice.get("rhythm"))
            and _text(voice.get("vocabulary")) and _text(voice.get("restraint"))):
        out.append(_defect("voice", "VOICE",
                           "voice must carry rhythm, vocabulary and restraint"))

    visual = record.get("identity_visual")
    if type(visual) is not dict:
        out.append(_defect("identity_visual", "VISUAL",
                           "identity_visual must carry face, age, hair, wardrobe_rules, "
                           "continuity_constraints and prompt_block"))
    else:
        for field in _VISUAL_REQUIRED:
            value = visual.get(field)
            ok = _text_list(value) if field in ("wardrobe_rules",
                                                "continuity_constraints") else _text(value)
            if not ok:
                out.append(_defect(f"identity_visual.{field}", "VISUAL",
                                   f"identity_visual.{field} is required"))
        # wardrobe RULES, not a look: setting-specific outfits stay in production.
        for field in sorted(EPISODE_ONLY_FIELDS & set(visual)):
            out.append(_defect(f"identity_visual.{field}", "SETTING_IN_IDENTITY",
                               f"'{field}' is setting-specific and belongs to the episode"))

    references = record.get("reference_ids", [])
    if type(references) is not list or not all(_text(r) for r in references):
        out.append(_defect("reference_ids", "REFERENCES",
                           "reference_ids must be a list of strings; an empty list is valid"))
    # Text identity must be complete before any image exists.

    provenance = record.get("provenance_by_field")
    if type(provenance) is not dict or not provenance:
        out.append(_defect("provenance_by_field", "PROVENANCE",
                           "every substantive assertion needs a provenance entry"))
    elif any(not _text(str(v)) for v in provenance.values()):
        out.append(_defect("provenance_by_field", "PROVENANCE",
                           "provenance values must name a real origin"))

    if not _in(record.get("draft_state"), DRAFT_STATES):
        out.append(_defect("draft_state", "DRAFT_STATE",
                           f"draft_state must be one of {sorted(DRAFT_STATES)}"))
    # A binding is a receipt or it is refused: never "a non-empty list".
    out.extend(_validate_approval_bindings(record))
    for key in ("shared_source", "local_cache"):
        if record.get(key) is not None and type(record.get(key)) is not dict:
            out.append(_defect(key, "SYNC", f"{key} must be an object or null"))
    if not _in(record.get("sync_state"), SYNC_STATES):
        out.append(_defect("sync_state", "SYNC",
                           f"sync_state must be one of {sorted(SYNC_STATES)}"))

    relationships = record.get("relationships", [])
    if type(relationships) is not list:
        out.append(_defect("relationships", "RELATIONSHIPS",
                           "relationships must be a list"))
    else:
        own_id = record.get("character_id")
        for index, edge in enumerate(relationships):
            where = f"relationships[{index}]"
            edge = _plain(edge)
            if edge is None:
                out.append(_defect(where, "RELATIONSHIPS", "relationship must be an object"))
                continue
            for field in ("character_id", "type", "history", "present_tension",
                          "dependency"):
                if not _text(edge.get(field)):
                    out.append(_defect(f"{where}.{field}", "RELATIONSHIPS",
                                       f"relationship requires '{field}'"))
            if _is_text(edge.get("character_id"), own_id):
                out.append(_defect(f"{where}.character_id", "SELF_RELATIONSHIP",
                                   "a character cannot relate to itself"))
    return out


def validate_identity(record):
    """Validate one reusable identity; raise IdentityDefect with every defect."""
    defects = _validate_identity(record)
    if defects:
        raise IdentityDefect(defects)
    return record


# --- library snapshot -------------------------------------------------------

def validate_library(snapshot):
    """Validate a client-scoped library snapshot; duplicate/dangling IDs fail."""
    given = snapshot
    snapshot = _plain(given)
    if snapshot is None:
        raise IdentityDefect([_defect("<snapshot>", "NOT_OBJECT",
                                      "library snapshot must be a plain object, "
                                      "not %s" % type(given).__name__)])
    out = []
    owner = snapshot.get("client_id")
    if not _text(owner):
        out.append(_defect("client_id", "CLIENT", "library snapshot needs a client_id"))
    characters = _plain_list(snapshot.get("characters", []))
    if not characters:
        out.append(_defect("characters", "LIBRARY_EMPTY",
                           "library snapshot must contain at least one character"))
        characters = []

    seen = set()
    for index, record in enumerate(characters):
        defects = _validate_identity(record)
        out.extend({**d, "field": f"characters[{index}].{d['field']}"} for d in defects)
        rec = _plain(record)
        cid = rec.get("character_id") if rec is not None else None
        if type(cid) is str:
            if cid in seen:
                out.append(_defect(f"characters[{index}].character_id", "DUPLICATE_ID",
                                   f"duplicate character_id '{cid}'"))
            seen.add(cid)
        if rec is not None and not _is_text(rec.get("client_id"), owner):
            out.append(_defect(f"characters[{index}].client_id", "CLIENT_MISMATCH",
                               "character belongs to a different client namespace"))

    for index, record in enumerate(characters):
        rec = _plain(record)
        if rec is None:
            continue
        edges = _plain_list(rec.get("relationships", [])) or []
        for edge_index, edge in enumerate(edges):
            edge = _plain(edge)
            target = edge.get("character_id") if edge is not None else None
            # A relationship may leave the client library only if it is
            # explicitly marked external; otherwise the ID must resolve.
            external = edge is not None and edge.get("external") is True
            if (type(target) is not str or target not in seen) and not external:
                out.append(_defect(
                    f"characters[{index}].relationships[{edge_index}].character_id",
                    "DANGLING_RELATIONSHIP",
                    f"relationship '{target}' does not resolve in this library"))
    if out:
        raise IdentityDefect(out)
    return snapshot


# --- episode setting --------------------------------------------------------

def validate_episode_setting(record):
    """Validate the episode-owned setting record; identity fields never appear here."""
    out = []
    given = record
    record = _plain(given)
    if record is None:
        raise IdentityDefect([_defect("<record>", "NOT_OBJECT",
                                      "episode setting must be a plain object, "
                                      "not %s" % type(given).__name__)])
    if not _is_text(record.get("schema_version"), EPISODE_SCHEMA_VERSION):
        out.append(_defect("schema_version", "SCHEMA_VERSION",
                           f"expected '{EPISODE_SCHEMA_VERSION}'"))
    for field in ("episode_id", "setting_name", "location", "era"):
        if not _text(record.get(field)):
            out.append(_defect(field, "SETTING_INCOMPLETE",
                               f"episode setting requires '{field}'"))
    for field in ("identity_summary", "wants", "fears", "identity_visual",
                  "emotional_wound", "mistaken_belief"):
        if field in record:
            out.append(_defect(field, "IDENTITY_IN_SETTING",
                               f"'{field}' belongs to the reusable identity record"))
    if out:
        raise IdentityDefect(out)
    return record


# --- cast manifest ----------------------------------------------------------

def _anonymous(speaker):
    low = speaker.strip().lower()
    return any(low == p or low.startswith(p + " ") for p in ANONYMOUS_SPEAKER_PATTERNS)


def _validate_crowd(group, index, scene_ids):
    out = []
    where = f"crowd_groups[{index}]"
    group = _plain(group)
    if group is None:
        return [_defect(where, "CROWD", "crowd group must be an object")]
    for field in CROWD_REQUIRED:
        value = group.get(field)
        if value is None:
            out.append(_defect(f"{where}.{field}", "CROWD_RULES",
                               f"crowd group requires '{field}'"))
        elif field in ("roles", "scene_ids"):
            if not _text_list(value):
                out.append(_defect(f"{where}.{field}", "CROWD_RULES",
                                   f"crowd '{field}' must be a non-empty list"))
        elif field == "count":
            if not (type(value) is int and value > 0):
                out.append(_defect(f"{where}.count", "CROWD_RULES",
                                   "crowd count must be a positive integer"))
        elif not _text(value):
            out.append(_defect(f"{where}.{field}", "CROWD_RULES",
                               f"crowd '{field}' must be non-empty"))

    if not _is_text(group.get("dialogue"), "forbidden"):
        out.append(_defect(f"{where}.dialogue", "CROWD_DIALOGUE",
                           "a crowd group may not speak; individualize the member first"))
    singled = group.get("singled_out")
    if singled is not None and type(singled) is not bool:
        out.append(_defect(f"{where}.singled_out", "CROWD_SINGLED_OUT",
                           "singled_out must be true or false"))
    elif singled is True:
        out.append(_defect(f"{where}.singled_out", "CROWD_SINGLED_OUT",
                           "a singled-out crowd member must be promoted to a full identity "
                           "with its own character_id and removed from the crowd group"))
    for sid in _plain_list(group.get("scene_ids", [])) or []:
        if scene_ids is not None and (type(sid) is not str or sid not in scene_ids):
            out.append(_defect(f"{where}.scene_ids", "UNKNOWN_SCENE",
                               f"crowd group references unknown scene '{sid}'"))
    if not _text(group.get("crowd_group_id")):
        out.append(_defect(f"{where}.crowd_group_id", "CROWD_RULES",
                           "crowd_group_id must be a stable ID"))
    return out


def validate_cast(manifest, library, *, speakers=None, scene_ids=None):
    """Refuse an incomplete cast, stale identity, dangling ref or hidden speaker.

    ``speakers`` are the lines/performers derived from the scenes; every one must
    resolve to an individual cast identity. ``scene_ids`` are the episode's real
    scene IDs; every reference must resolve.
    """
    out = []
    given = manifest
    manifest = _plain(given)
    if manifest is None:
        raise CastDefect([_defect("<manifest>", "NOT_OBJECT",
                                  "cast manifest must be a plain object, not %s"
                                  % type(given).__name__)])
    library = _plain(library) or {}
    characters = _plain_list(library.get("characters", [])) or []
    by_id = {}
    for candidate in characters:
        plain = _plain(candidate)
        if plain is not None and type(plain.get("character_id")) is str:
            by_id[plain["character_id"]] = plain
    known_scenes = None
    if scene_ids is not None:
        known_scenes = set(s for s in (scene_ids or []) if type(s) is str)

    if not _is_text(manifest.get("schema_version"), MANIFEST_SCHEMA_VERSION):
        out.append(_defect("schema_version", "SCHEMA_VERSION",
                           f"expected '{MANIFEST_SCHEMA_VERSION}'"))
    for field in ("client_id", "episode_id"):
        if not _text(manifest.get(field)):
            out.append(_defect(field, "CAST_INCOMPLETE",
                               f"cast manifest requires '{field}'"))
    if not _is_text(manifest.get("library_digest"), library_digest(library)):
        out.append(_defect("library_digest", "LIBRARY_BINDING",
                           "cast manifest was not bound to this library snapshot"))

    cast_raw = manifest.get("cast")
    cast = _plain_list(cast_raw)
    people_free = manifest.get("people_free") is True
    if people_free:
        if cast or (cast is None and cast_raw is not None):
            out.append(_defect("cast", "PEOPLE_FREE_CONTRADICTION",
                               "a people-free episode cannot select cast members"))
        if not _text(manifest.get("people_free_reason")):
            out.append(_defect("people_free_reason", "PEOPLE_FREE",
                               "a people-free episode must state its reason explicitly"))
    elif cast is None or cast_raw is None:
        out.append(_defect("cast", "CAST_INCOMPLETE",
                           "cast list is required; omission is not an empty cast"))
    elif not cast:
        out.append(_defect("cast", "CAST_EMPTY",
                           "a narrative with people cannot have an empty cast"))

    selected = {}
    for index, entry in enumerate(cast or []):
        where = f"cast[{index}]"
        entry = _plain(entry)
        if entry is None:
            out.append(_defect(where, "CAST_INCOMPLETE", "cast entry must be an object"))
            continue
        cid = entry.get("character_id")
        if not _text(cid):
            out.append(_defect(f"{where}.character_id", "CAST_INCOMPLETE",
                               "every selected person needs an explicit character_id"))
        elif cid in selected:
            out.append(_defect(f"{where}.character_id", "DUPLICATE_CAST",
                               f"'{cid}' is selected twice"))
        else:
            selected[cid] = entry

        record = by_id.get(cid)
        if cid and record is None:
            out.append(_defect(f"{where}.character_id", "UNKNOWN_IDENTITY",
                               f"'{cid}' is not in the bound library snapshot"))
        elif record is not None:
            want = entry.get("identity_revision")
            have = record.get("revision")
            if not (type(want) is int and type(have) is int and want == have):
                out.append(_defect(f"{where}.identity_revision", "STALE_REVISION",
                                   f"'{cid}' is selected at revision "
                                   f"{entry.get('identity_revision')}, library has "
                                   f"{record.get('revision')}"))
            if not _is_text(entry.get("identity_digest"), record.get("content_digest")):
                out.append(_defect(f"{where}.identity_digest", "DIGEST_MISMATCH",
                                   f"'{cid}' selection does not bind the library content"))

        if not _in(entry.get("episode_role"), ROLES):
            out.append(_defect(f"{where}.episode_role", "CAST_ROLE",
                               f"episode_role must be one of {sorted(ROLES)}"))
        for field in ("immediate_story_function", "choice_or_consequence"):
            if not _text(entry.get(field)):
                out.append(_defect(f"{where}.{field}", "CAST_INCOMPLETE",
                                   f"'{field}' is required for a selected person"))
        if type(entry.get("relationship_changes", [])) is not list:
            out.append(_defect(f"{where}.relationship_changes", "CAST_INCOMPLETE",
                               "relationship_changes must be a list"))
        entry_scenes = entry.get("scene_ids")
        if not _text_list(entry_scenes):
            out.append(_defect(f"{where}.scene_ids", "CAST_INCOMPLETE",
                               "every selected person needs at least one scene_id"))
        else:
            for sid in entry_scenes:
                if known_scenes is not None and (type(sid) is not str
                                                 or sid not in known_scenes):
                    out.append(_defect(f"{where}.scene_ids", "UNKNOWN_SCENE",
                                       f"unknown scene '{sid}'"))
        if _anonymous(str(cid)) or _anonymous(str(entry.get("display_name_hint", ""))):
            out.append(_defect(f"{where}.character_id", "ANONYMOUS_IDENTITY",
                               "a generic descriptor is not an identity"))

    groups = _plain_list(manifest.get("crowd_groups", []))
    if groups is None:
        out.append(_defect("crowd_groups", "CROWD", "crowd_groups must be a list"))
        groups = []
    seen_groups = set()
    for index, group in enumerate(groups):
        out.extend(_validate_crowd(group, index, known_scenes))
        plain_group = _plain(group)
        gid = plain_group.get("crowd_group_id") if plain_group is not None else None
        if type(gid) is str:
            if gid in seen_groups:
                out.append(_defect(f"crowd_groups[{index}].crowd_group_id", "DUPLICATE_GROUP",
                                   f"duplicate crowd_group_id '{gid}'"))
            seen_groups.add(gid)

    for speaker in speakers or []:
        if not _text(speaker):
            out.append(_defect("speakers", "UNDECLARED_SPEAKER",
                               "an empty speaker cannot be resolved"))
        elif _anonymous(speaker):
            out.append(_defect("speakers", "ANONYMOUS_SPEAKER",
                               f"'{speaker}' is a generic descriptor; declare the person "
                               f"with an explicit character_id"))
        elif speaker not in selected:
            out.append(_defect("speakers", "UNDECLARED_SPEAKER",
                               f"speaker '{speaker}' is not in the cast manifest"))

    if out:
        raise CastDefect(out)
    return manifest
