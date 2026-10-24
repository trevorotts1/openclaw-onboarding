#!/usr/bin/env python3
"""S75-T06: author a complete episode cast through the supported dispatcher.

A cast is people with wants, fears, beliefs and speech — not a face list. This
module:

  1. takes the exact foundation envelope (research revision + digest, premise,
     reusable library revision + identities, scene ids, new/existing/mixed
     selection);
  2. asks the ONE supported author dispatcher — injected, never imported — for
     full identity profiles plus the episode manifest material, recording the
     prompt digest and the exact response digest in a dispatch receipt;
  3. seals every identity at its revision, binds each selected identity's
     revision and digest from the resolved record (never from model text), and
     builds the ``episode_cast_manifest``;
  4. refuses an incomplete cast BY NAME — every lead, supporting, speaking,
     reacting, recurring and meaningful-background person must carry
     background, wants, fears, beliefs, wound, mistaken belief, contradiction,
     habits, voice and pressure behaviour. A face-only record cannot pass;
  5. refuses anonymous speakers, unknowns, stale revisions, dangling scenes,
     crowd groups that speak or single a member out, and a cast file supplied
     in the request instead of authored by the dispatch.

No provider call lives here. ``dispatch`` is a required callable
(``dispatch(prompt: dict) -> dict``); with none the writer refuses with
``NO_DISPATCHER`` before anything else happens. Tests inject a fake and never
touch a network. Standard library only.

Run the focused tests::

    python3 75-drama-song-ad-factory/scripts/core/character_bible/test_cast_writer_s75_t06.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import string
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import story_first_contracts as C  # noqa: E402  (S75-T03 envelope + cast schema)

__all__ = [
    "CastWriteError", "author_cast", "build_prompt", "canonical_digest",
    "derive_speakers", "derive_crowds", "library_digest", "profile_defects",
    "verify_receipt",
    "seed_from_legacy_bible", "MANIFEST_SCHEMA_VERSION", "LIBRARY_SCHEMA_VERSION",
    "ROLES", "SELECTIONS", "PROFILE_FIELDS", "ANONYMOUS_SPEAKERS", "CROWD_REQUIRED",
    "GENERIC_DESCRIPTOR_HEADS",
]

MANIFEST_SCHEMA_VERSION = "s75.cast_manifest.v1"
LIBRARY_SCHEMA_VERSION = "s75.character_library.v1"

#: Roles that entitle a person to individual lines, reactions or consequence.
ROLES = ("lead", "supporting", "recurring", "speaking", "reacting",
         "meaningful_background")
SELECTIONS = ("new", "existing", "mixed")

DRAFT_COMPLETE = "DRAFT_COMPLETE"

#: Bookkeeping is not story content, so it never enters the content digest.
_BOOKKEEPING = frozenset({
    "content_digest", "approval_bindings", "draft_state",
    "shared_source", "local_cache", "sync_state",
})

#: A crowd group is allowed only with every one of these rules present.
CROWD_REQUIRED = (
    "crowd_group_id", "composition", "count", "age_range", "roles",
    "location_placement", "collective_behavior", "permitted_motion",
    "attention_direction", "interaction_with_leads", "wardrobe_palette",
    "camera_limits", "entry_exit_rule", "recurrence", "dialogue",
    "reference_provenance", "scene_ids",
)

#: The story substance a person needs before they can act on screen.
PROFILE_FIELDS = (
    "identity_summary", "relevant_background_history", "occupation",
    "competence", "social_context", "wants", "fears", "beliefs",
    "emotional_wound", "mistaken_belief", "contradictions", "habits", "voice",
    "behavior_under_pressure", "appearance_traits", "provenance_by_field",
)

_TEXT_FIELDS = (
    "identity_summary", "occupation", "social_context", "emotional_wound",
    "mistaken_belief", "behavior_under_pressure", "appearance_traits",
)
_LIST_FIELDS = (
    "relevant_background_history", "competence", "fears", "beliefs",
    "contradictions", "habits",
)
_VOICE_FIELDS = ("rhythm", "vocabulary", "restraint")
_WANT_FIELDS = ("external", "internal")


class CastWriteError(Exception):
    """One actionable refusal packet. Nothing partial is ever returned."""

    def __init__(self, code, message, packet=None):
        super().__init__(message)
        self.code = code
        self.packet = packet or {}


# --- digests ----------------------------------------------------------------

def canonical_digest(record, exclude=()):
    """SHA-256 over canonical JSON, ignoring the named bookkeeping fields."""
    body = {k: v for k, v in record.items() if k not in exclude}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def library_digest(snapshot):
    """Digest of the identity snapshot a manifest is bound to.

    Matches S75-T05's ``identity.library_digest`` so the two modules agree at
    merge: same canonical JSON, same excluded cache bookkeeping.
    """
    return canonical_digest(snapshot or {}, exclude=frozenset({"local_cache", "sync_state"}))


# --- small predicates -------------------------------------------------------

def _text(value):
    return isinstance(value, str) and value.strip() != ""


def _text_list(value):
    return (isinstance(value, list) and len(value) >= 1
            and all(_text(item) for item in value))


#: Punctuation and quoting that can dress a descriptor up without changing
#: what it is: brackets, quotes, dashes, sentence marks, underscores.
_DRESSING = string.punctuation + "“”‘’«»‹›—– "

_POSSESSIVE = re.compile(r"(?:'s|’s)\s*$")
_POSSESSIVE_LEAD = re.compile(r"^\s*(?:'s|’s)")
_SPACES = re.compile(r"\s+")

#: Determiners, articles and quantifiers dress a descriptor; they never name a
#: person, so they come off the front of a candidate, repeatedly.
_DETERMINERS = frozenset({"a", "an", "the", "some", "any", "another", "one"})

#: Function words. A personal name has none of them, so one anywhere inside a
#: candidate means the words describe a person instead of naming one.
_FUNCTION_WORDS = _DETERMINERS | frozenset({
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "into", "onto",
    "over", "under", "behind", "beside", "near", "across", "through", "during",
    "before", "after", "above", "below", "between", "against", "about", "around",
    "along", "among", "within", "without", "toward", "towards", "per", "via",
    "and", "or", "but", "as", "than", "that", "which", "who", "whose", "when",
    "where", "while", "if", "then", "this", "these", "those", "there", "here",
    "her", "his", "their", "its", "my", "your", "our", "is", "was", "are", "were",
    "be", "been", "out", "up", "down", "off", "again", "very", "just", "also",
    "only", "not", "no",
})

#: The closed vocabulary of generic person-descriptor heads. Not a phrase list:
#: whatever the dressing, a candidate is refused when it IS one of these, or
#: when it opens on one and never becomes a personal name.
GENERIC_DESCRIPTOR_HEADS = frozenset({
    "woman", "women", "man", "men", "girl", "girls", "boy", "boys",
    "person", "persons", "people", "child", "children", "kid", "kids",
    "guy", "guys", "lady", "ladies", "fellow", "fellows",
    "narrator", "narrators", "manager", "managers", "boss", "bosses",
    "guard", "guards", "officer", "officers", "driver", "drivers",
    "waiter", "waiters", "waitress", "waitresses", "server", "servers",
    "host", "hosts", "clerk", "clerks", "nurse", "nurses", "doctor", "doctors",
    "teacher", "teachers", "student", "students", "stranger", "strangers",
    "figure", "figures", "silhouette", "silhouettes", "voice", "voices",
    "character", "characters",
    "worker", "workers", "customer", "customers", "bystander", "bystanders",
    "someone", "somebody", "anyone", "anybody", "crowd", "crowds",
})

#: Descriptor heads that may stand in front of a personal name as its title
#: ("Officer Dan Whitfield"). Any other head at the front is refused outright,
#: so "the manager East Wing" cannot borrow a name's shape.
_TITLE_HEADS = frozenset({"officer", "doctor", "nurse"})

#: Exported name kept for callers of the round-3 surface; it is now the
#: descriptor-head vocabulary above rather than a list of dressed phrases.
ANONYMOUS_SPEAKERS = GENERIC_DESCRIPTOR_HEADS


def _strip_dressing(text):
    """Punctuation, quotes, brackets and possessives off BOTH ends, to stability.

    The dressing is peeled from whichever end carries it, over and over, until
    a pass changes nothing — so no amount of padding at the front survives.
    """
    while True:
        new = _POSSESSIVE_LEAD.sub("", _POSSESSIVE.sub("", text.strip(_DRESSING)))
        new = _SPACES.sub(" ", new).strip(_DRESSING)
        if new == text:
            return text
        text = new


def _bare(text):
    """Inner punctuation flattened to spaces too, so ``"a woman, leader"``
    cannot hide from the descriptor rule behind a comma."""
    return _SPACES.sub(" ",
                       "".join(" " if ch in _DRESSING else ch for ch in text)).strip()


def _identity_tokens(value):
    """The core words of a candidate, dressing gone from both ends.

    Case is kept: a name is judged on its shape, and shape needs the capitals.
    """
    return [tok for tok in _bare(_strip_dressing(value or "")).split(" ") if tok]


def _normalise_identity(value):
    """Case-folded core of a name or id, dressing gone from both ends."""
    return " ".join(_identity_tokens(value)).casefold()


def _personal_name(tokens, heads):
    """A given name plus a surname is a person, even when a word inside it is a
    descriptor (``"Dana Woman"``). The shape says so: every word capitalised,
    no function words, and not every word a descriptor."""
    return (len(tokens) >= 2
            and all(tok[:1].isupper() for tok in tokens)
            and all(tok.casefold() not in _FUNCTION_WORDS for tok in tokens)
            and not all(heads))


def _anonymous(value):
    """A generic descriptor is not an identity, whatever it is wearing.

    Structural, never a list of dressed strings: determiners come off the
    front, dressing comes off both ends, and what remains is refused when it is
    a descriptor head, or opens on one without turning into a personal name.

    Both positions — ``display_name`` and ``character_id`` — ask this same
    question, so a descriptor refused as a name is refused as an id.
    """
    tokens = _identity_tokens(value)
    while tokens and tokens[0].casefold() in _DETERMINERS:
        tokens = tokens[1:]
    if not tokens:
        return True
    lowered = [tok.casefold() for tok in tokens]
    heads = [tok in GENERIC_DESCRIPTOR_HEADS for tok in lowered]
    if not any(heads):
        return False
    if heads[0] and lowered[0] not in _TITLE_HEADS:
        return True
    return not _personal_name(tokens, heads)


def _defect(character_id, display_name, field, issue):
    return {"character_id": character_id, "display_name": display_name,
            "field": field, "issue": issue}


def _label(defect):
    name = defect.get("display_name") or "(no display name)"
    return "%s (%s) missing %s" % (defect["character_id"], name, defect["field"])


# --- profile completeness ---------------------------------------------------

def profile_defects(record):
    """Every reason this record is a face/name rather than a story identity."""
    if not isinstance(record, dict):
        return [_defect("<record>", "", "<record>", "not an object")]
    cid = record.get("character_id")
    name = record.get("display_name")
    out = []
    for field in _TEXT_FIELDS:
        if not _text(record.get(field)):
            out.append(_defect(cid, name, field, "required substantive content"))
    for field in _LIST_FIELDS:
        if not _text_list(record.get(field)):
            out.append(_defect(cid, name, field,
                               "required non-empty list of specific statements"))
    wants = record.get("wants")
    if not isinstance(wants, dict):
        out.append(_defect(cid, name, "wants", "required external/internal object"))
    else:
        for key in _WANT_FIELDS:
            if not _text(wants.get(key)):
                out.append(_defect(cid, name, "wants." + key, "required"))
    voice = record.get("voice")
    if not isinstance(voice, dict):
        out.append(_defect(cid, name, "voice", "required rhythm/vocabulary/restraint"))
    else:
        for key in _VOICE_FIELDS:
            if not _text(voice.get(key)):
                out.append(_defect(cid, name, "voice." + key, "required speech direction"))
    provenance = record.get("provenance_by_field")
    if not (isinstance(provenance, dict) and provenance):
        out.append(_defect(cid, name, "provenance_by_field",
                           "every substantive assertion needs an origin"))
    if not _text(record.get("display_name")):
        out.append(_defect(cid, name, "display_name", "required"))
    elif _anonymous(str(name)):
        out.append(_defect(cid, name, "display_name",
                           "a generic descriptor is not an identity"))
    if not _text(record.get("character_id")):
        out.append(_defect(cid, name, "character_id", "required stable ID"))
    elif _anonymous(str(cid)):
        out.append(_defect(cid, name, "character_id",
                           "a generic descriptor is not an identity"))
    return out


def _contract_defects(record):
    return [_defect(record.get("character_id"), record.get("display_name"),
                    d.get("field"), d.get("issue"))
            for d in C.validate_identity(record)]


# --- identity sealing -------------------------------------------------------

def _draft(raw, client_id, revision):
    """Episode/library bookkeeping defaults; the model never owns these."""
    rec = dict(raw or {})
    rec["client_id"] = client_id
    rec["schema_version"] = C.IDENTITY_SCHEMA_VERSION
    rec["revision"] = int(revision)
    rec.setdefault("aliases", [])
    rec.setdefault("story_status", "FICTION")
    rec.setdefault("reference_ids", [])
    rec.setdefault("approval_bindings", [])
    rec.setdefault("shared_source", None)
    rec.setdefault("local_cache", None)
    rec.setdefault("sync_state", "LOCAL_ONLY")
    rec["draft_state"] = DRAFT_COMPLETE
    rec.pop("content_digest", None)
    return rec


def _seal(record):
    sealed = dict(record)
    sealed["content_digest"] = canonical_digest(sealed, exclude=_BOOKKEEPING)
    return sealed


# --- scene participants -----------------------------------------------------

#: Every scene field that declares who is in the scene: the participant surface
#: of SCENE-SCRIPT-CONTRACT.md (``cast_ids``, ``identity_revisions``,
#: ``crowd_group_ids``) plus the fields that name reaction people and
#: meaningful extras by another key.
_PARTICIPANT_KEYS = frozenset({
    "cast_ids", "identity_revisions", "crowd_group_ids",
    "participants", "participant_ids", "cast",
    "reaction_people", "reaction_ids", "reacting_ids",
    "meaningful_extras", "extras", "extra_ids",
    "background_people", "background_ids", "background_cast",
    "speakers", "speaker_ids", "performers", "performer_ids",
    "actors", "actor_ids", "singers", "singer_ids", "voices", "voice_ids",
    "onlookers", "witnesses", "audience_ids", "member_ids",
    "subjects", "subject_ids", "shot_subjects", "id_to_detail_map",
    "detail_map",
})

#: A person reference written as a per-line or per-shot binding.
_PERSON_ID_KEYS = frozenset({
    "character_id", "performer_id", "speaker_id", "actor_id",
    "person_id", "singer_id", "member_id", "subject_id",
})

#: Any other scene key that plausibly carries a participant.
_NAME_HINTS = (
    "cast", "character", "performer", "participant", "speaker",
    "people", "person", "actor", "extras", "extra_", "reaction", "reacting",
    "background", "crowd", "witness", "onlooker", "audience",
    "voice", "singer", "member",
)

def _declares_people(key):
    low = (key or "").lower()
    return (low in _PARTICIPANT_KEYS or low in _PERSON_ID_KEYS
            or any(hint in low for hint in _NAME_HINTS))

def _ref_like(value):
    """A short whitespace-free token, not a sentence of prose."""
    return (isinstance(value, str) and 0 < len(value) <= 64
            and not any(ch.isspace() for ch in value))

def _add_person(value, bucket):
    """A person reference: a stable id, or a short generic descriptor that the
    anonymous rule must refuse. Prose longer than 64 characters is not a name."""
    if isinstance(value, str) and 0 < len(value) <= 64 and value not in bucket:
        bucket.append(value)

def _walk_refs(node, key, persons, crowds):
    """Collect every participant reference in a scene's declared surface."""
    if isinstance(node, dict):
        # A map like ``identity_revisions`` or ``shots[].subjects`` names its
        # people as its keys.
        if _declares_people(key):
            bucket = crowds if "crowd" in (key or "").lower() else persons
            crowd_map = "crowd" in (key or "").lower()
            for sub_key, value in node.items():
                # The keys of a declared-person map name people, so they meet
                # the same rule as a value: a descriptor written as a key with
                # a space in it cannot slip past a whitespace-free id check.
                if crowd_map:
                    if _ref_like(sub_key) and sub_key not in bucket:
                        bucket.append(sub_key)
                else:
                    _add_person(sub_key, bucket)
                if isinstance(value, (dict, list)):
                    # A nested binding carries its own keys; the outer key is a
                    # role, not a person, so the descent drops it.
                    _walk_refs(value, "", persons, crowds)
                elif not crowd_map and _declares_people(sub_key):
                    # A per-line or per-shot binding carries its person as the
                    # VALUE under a person-id key; that value is a reference.
                    _add_person(value, bucket)
            return
        for sub_key, value in node.items():
            _walk_refs(value, str(sub_key), persons, crowds)
    elif isinstance(node, list):
        for item in node:
            _walk_refs(item, key, persons, crowds)
    elif _declares_people(key):
        # Crowd membership is always an id; a person may also be named by the
        # generic descriptor the anonymous rule has to refuse.
        if "crowd" in (key or "").lower():
            if _ref_like(node) and node not in crowds:
                crowds.append(node)
        else:
            _add_person(node, persons)

def derive_speakers(scenes):
    """Every individual the scenes declare: speakers, singers, actors,
    reaction people, meaningful extras and per-line/per-shot bindings.

    Reads the full declared-participant surface of each scene, not only the
    dialogue fields, so a scene binding id cannot hide an undeclared person.
    """
    persons, _ = _scene_participants(scenes)
    return persons

def derive_crowds(scenes):
    """Every crowd group a scene declares, across the whole scene surface."""
    _, crowds = _scene_participants(scenes)
    return crowds

def _scene_participants(scenes):
    persons, crowds = [], []
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        _walk_refs(scene, "", persons, crowds)
    return persons, crowds


# --- crowd ------------------------------------------------------------------

def _crowd_defects(groups, scene_ids):
    out = []
    for index, group in enumerate(groups or []):
        where = "crowd_groups[%d]" % index
        if not isinstance(group, dict):
            out.append({"field": where, "issue": "crowd group must be an object"})
            continue
        for field in CROWD_REQUIRED:
            value = group.get(field)
            if field == "count":
                if not (isinstance(value, int) and not isinstance(value, bool) and value > 0):
                    out.append({"field": where + ".count", "issue": "positive integer required"})
            elif field in ("roles", "scene_ids"):
                if not _text_list(value):
                    out.append({"field": where + "." + field,
                                "issue": "non-empty list of rules required"})
            elif value is None or (isinstance(value, str) and not value.strip()):
                out.append({"field": where + "." + field,
                            "issue": "crowd rule required"})
        if group.get("dialogue") != "forbidden":
            out.append({"field": where + ".dialogue",
                        "issue": "a crowd may not speak; individualize the member first"})
        if group.get("singled_out"):
            out.append({"field": where + ".singled_out",
                        "issue": "a singled-out member must become a full identity"})
        for sid in group.get("scene_ids") or []:
            if scene_ids is not None and sid not in scene_ids:
                out.append({"field": where + ".scene_ids",
                            "issue": "unknown scene '%s'" % (sid,)})
    return out


# --- the dispatch -----------------------------------------------------------

def build_prompt(request, library_snapshot):
    """The exact author operation payload. Pure data; no side effects."""
    research = request.get("research_bundle") or {}
    return {
        "task": "author_complete_episode_cast",
        "identity_schema_version": C.IDENTITY_SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "client_id": request["client_id"],
        "episode_id": request["episode_id"],
        "selection": request["selection"],
        "premise": request["premise"],
        "research": {
            "revision": research["revision"],
            "content_digest": research["content_digest"],
        },
        "library": {
            "revision": library_snapshot["revision"],
            "content_digest": library_digest(library_snapshot),
            "characters": library_snapshot["characters"],
        },
        "scene_ids": list(request.get("scene_ids") or []),
        "people_free": bool(request.get("people_free")),
        "requirements": {
            "full_profile_fields": list(PROFILE_FIELDS),
            "roles": list(ROLES),
            "individualize": ("any speaking, reacting, recurring or causally "
                              "consequential person needs a full identity; a crowd "
                              "may not speak or single a member out"),
            "label_fiction": "new material is labelled FICTION with provenance",
            "no_extras": "do not add an unexplained man/woman/worker",
        },
    }


def _require_input(request):
    missing = []
    if not _text(request.get("client_id")):
        missing.append("client_id")
    if not _text(request.get("episode_id")):
        missing.append("episode_id")
    if not _text(request.get("premise")):
        missing.append("premise")
    research = request.get("research_bundle")
    if not isinstance(research, dict):
        missing.append("research_bundle")
    else:
        for key in ("revision", "content_digest"):
            if not _text(str(research.get(key) or "")):
                missing.append("research_bundle." + key)
    library = request.get("library")
    if not isinstance(library, dict):
        missing.append("library")
    else:
        if not _text(library.get("client_id")):
            missing.append("library.client_id")
        if not isinstance(library.get("revision"), int):
            missing.append("library.revision")
        if not isinstance(library.get("characters"), list):
            missing.append("library.characters")
    if request.get("selection") not in SELECTIONS:
        missing.append("selection (one of %s)" % (list(SELECTIONS),))
    if missing:
        raise CastWriteError(
            "MISSING_INPUT",
            "cast authoring needs %s" % ", ".join(missing),
            {"missing": missing})
    if request["library"]["client_id"] != request["client_id"]:
        raise CastWriteError(
            "CLIENT_MISMATCH",
            "the reusable library belongs to another client namespace",
            {"request_client_id": request["client_id"],
             "library_client_id": request["library"]["client_id"]})


def _library_snapshot(request):
    library = request["library"]
    return {
        "schema_version": LIBRARY_SCHEMA_VERSION,
        "client_id": request["client_id"],
        "revision": int(library["revision"]),
        "characters": [dict(c) for c in library.get("characters") or []],
    }


# --- authoring --------------------------------------------------------------

def author_cast(request, *, dispatch, model="", clock=None):
    """Author identities + manifest through ``dispatch``. Refuses incomplete casts.

    ``plan`` returns ``{"identities": [...], "cast": [...],
    "crowd_groups": [...], "people_free": bool, "people_free_reason": str}``.
    Nothing is written unless the whole cast is complete.
    """
    if not isinstance(request, dict):
        raise CastWriteError("MISSING_INPUT", "request must be an object", {})
    _require_input(request)
    if not callable(dispatch):
        raise CastWriteError(
            "NO_DISPATCHER",
            "no supported author dispatcher supplied; refusing to guess a cast",
            {"dispatch": repr(dispatch)})

    client_id = request["client_id"]
    scene_ids = list(request.get("scene_ids") or [])
    known_scenes = set(scene_ids) if scene_ids else None
    selection = request["selection"]

    snapshot = _library_snapshot(request)
    existing = {c.get("character_id"): c for c in snapshot["characters"]
                if isinstance(c, dict)}

    prompt = build_prompt(request, snapshot)
    prompt_digest = canonical_digest(prompt)
    try:
        response = dispatch(prompt)
    except CastWriteError:
        raise
    except Exception as exc:  # noqa: BLE001 - a dispatch failure is a refusal
        raise CastWriteError("DISPATCH_FAILED", "author dispatch failed: %s" % (exc,),
                             {"error": type(exc).__name__}) from exc
    if not isinstance(response, dict):
        raise CastWriteError("DISPATCH_FAILED",
                             "author dispatch did not answer with a JSON object",
                             {"type": type(response).__name__})
    receipt = {
        "task": "author_complete_episode_cast",
        "model": model,
        "calls": 1,
        "prompt_digest": prompt_digest,
        "response_digest": canonical_digest(response),
        "research_revision": request["research_bundle"]["revision"],
        "research_digest": request["research_bundle"]["content_digest"],
        "premise_digest": canonical_digest({"premise": request["premise"]}),
        "library_revision": snapshot["revision"],
        "library_digest": library_digest(snapshot),
        "selection": selection,
    }

    people_free = response.get("people_free") is True
    reason = response.get("people_free_reason")

    raw_identities = response.get("identities")
    raw_cast = response.get("cast")
    if raw_identities is None and raw_cast is None:
        raise CastWriteError(
            "MISSING_CAST",
            "the author response carried no identities and no cast; omission is "
            "not an empty cast",
            {"receipt": receipt})

    # A request-supplied cast is never the answer: only the dispatch response is.
    authored = []

    # --- identities ---
    seen = set()
    library_by_id = dict(existing)
    for index, raw in enumerate(raw_identities or []):
        cid = raw.get("character_id") if isinstance(raw, dict) else None
        if not _text(cid):
            raise CastWriteError(
                "INCOMPLETE_CAST",
                "identity[%d] has no stable character_id and cannot be named or "
                "selected" % index,
                {"incomplete": [_defect("<unnamed>", "", "character_id", "required")]})
        if cid in seen:
            raise CastWriteError("DUPLICATE_IDENTITY",
                                 "character_id '%s' authored twice" % cid,
                                 {"character_id": cid})
        seen.add(cid)
        if cid in existing:
            raise CastWriteError(
                "IDENTITY_OVERWRITE",
                "'%s' already exists in the reusable library; changing who the "
                "person is needs a deliberate new revision, not a cast write" % cid,
                {"character_id": cid, "library_revision": existing[cid].get("revision")})
        if selection == "existing":
            raise CastWriteError(
                "SELECTION_NEW_REFUSED",
                "selection 'existing' may not author new person '%s'" % cid,
                {"character_id": cid, "selection": selection})
        authored.append(_seal(_draft(raw, client_id, 1)))

    # --- existing identities bound at their exact revision ---
    bound = {c["character_id"]: c for c in authored}
    for cid, record in existing.items():
        if not isinstance(record, dict):
            raise CastWriteError("LIBRARY_INVALID",
                                 "library entry '%s' is not an object" % cid,
                                 {"character_id": cid})
        if record.get("client_id") not in (None, client_id):
            raise CastWriteError(
                "CLIENT_MISMATCH",
                "library identity '%s' belongs to another client namespace" % cid,
                {"character_id": cid, "client_id": record.get("client_id")})
        digest = record.get("content_digest")
        if _text(digest) and digest != canonical_digest(record, exclude=_BOOKKEEPING):
            raise CastWriteError(
                "STALE_IDENTITY",
                "'%s' (%s) has a content_digest that no longer matches its content"
                % (cid, record.get("display_name")),
                {"character_id": cid, "field": "content_digest",
                 "issue": "stale or hand-edited identity"})
        library_by_id[cid] = _seal(_draft(record, client_id,
                                          record.get("revision") or 1))
        bound[cid] = library_by_id[cid]

    # --- completeness, every profile by name ---
    incomplete = []
    for cid, record in sorted(bound.items()):
        defects = profile_defects(record) + _contract_defects(record)
        for edge in record.get("relationships") or []:
            target = edge.get("character_id") if isinstance(edge, dict) else None
            if target and target not in bound and not edge.get("external"):
                defects.append(_defect(cid, record.get("display_name"),
                                       "relationships",
                                       "dangling relationship '%s'" % target))
        if defects:
            incomplete.extend(defects)
    if incomplete:
        names = "; ".join(_label(d) for d in incomplete[:12])
        more = "" if len(incomplete) <= 12 else " (+%d more)" % (len(incomplete) - 12)
        raise CastWriteError(
            "INCOMPLETE_CAST",
            "incomplete cast, nothing authored: " + names + more,
            {"incomplete": incomplete, "receipt": receipt})

    # --- the cast selection ---
    if people_free:
        if raw_cast:
            raise CastWriteError(
                "PEOPLE_FREE_CONTRADICTION",
                "the episode declares itself people-free but selects %d cast members"
                % len(raw_cast),
                {"cast_ids": [e.get("character_id") for e in raw_cast
                              if isinstance(e, dict)]})
        if not _text(reason):
            raise CastWriteError("PEOPLE_FREE",
                                 "a people-free episode must state its reason explicitly",
                                 {})
        if authored:
            raise CastWriteError(
                "PEOPLE_FREE_CONTRADICTION",
                "the author response declared people-free yet authored identities",
                {"character_ids": [c["character_id"] for c in authored]})
    elif raw_cast is None:
        raise CastWriteError(
            "MISSING_CAST",
            "the author response omitted the cast list; a missing cast field is a "
            "missing requirement, never an empty cast",
            {"receipt": receipt})
    elif not raw_cast:
        raise CastWriteError(
            "CAST_EMPTY",
            "a narrative with people cannot have an empty cast",
            {"receipt": receipt})

    cast_entries = []
    selected = set()
    defects = []
    for index, entry in enumerate(raw_cast or []):
        if not isinstance(entry, dict):
            defects.append({"field": "cast[%d]" % index,
                            "issue": "cast entry must be an object"})
            continue
        cid = entry.get("character_id")
        if not _text(cid):
            defects.append({"field": "cast[%d].character_id" % index,
                            "issue": "every selected person needs an explicit ID"})
            continue
        if cid in selected:
            defects.append({"field": "cast[%d].character_id" % index,
                            "issue": "'%s' selected twice" % cid})
            continue
        selected.add(cid)
        record = bound.get(cid) or library_by_id.get(cid)
        if record is None:
            defects.append({"field": "cast[%d].character_id" % index,
                            "issue": "'%s' is not in the library or the authored "
                                     "identities" % cid})
            continue
        if selection == "new" and cid in existing:
            defects.append({"field": "cast[%d].character_id" % index,
                            "issue": "selection 'new' may not reuse '%s'" % cid})
        if selection == "existing" and cid not in existing:
            defects.append({"field": "cast[%d].character_id" % index,
                            "issue": "selection 'existing' cannot select unknown '%s'" % cid})
        role = entry.get("episode_role")
        if role not in ROLES:
            defects.append({"field": "cast[%d].episode_role" % index,
                            "issue": "episode_role must be one of %s" % (list(ROLES),)})
        for key in ("immediate_story_function", "choice_or_consequence"):
            if not _text(entry.get(key)):
                defects.append({"field": "cast[%d].%s" % (index, key),
                                "issue": "'%s' is required for %s" % (key, cid)})
        entry_scenes = entry.get("scene_ids")
        if not _text_list(entry_scenes):
            defects.append({"field": "cast[%d].scene_ids" % index,
                            "issue": "'%s' needs at least one scene" % cid})
        elif known_scenes is not None:
            for sid in entry_scenes:
                if sid not in known_scenes:
                    defects.append({"field": "cast[%d].scene_ids" % index,
                                    "issue": "'%s' references unknown scene '%s'"
                                             % (cid, sid)})
        changes = entry.get("relationship_changes", [])
        if not isinstance(changes, list):
            defects.append({"field": "cast[%d].relationship_changes" % index,
                            "issue": "must be a list"})
        cast_entries.append({
            "character_id": cid,
            "identity_revision": record["revision"],
            "identity_digest": record["content_digest"],
            "episode_role": role,
            "scene_ids": list(entry_scenes or []),
            "immediate_story_function": entry.get("immediate_story_function"),
            "choice_or_consequence": entry.get("choice_or_consequence"),
            "relationship_changes": list(changes),
        })

    # --- every individual the scenes declare must be selected ---
    scenes = request.get("scenes")
    if isinstance(scenes, dict):
        scenes = scenes.get("scenes")
    if scenes is None and isinstance(request.get("scene_plan"), dict):
        scenes = request["scene_plan"].get("scenes")

    # --- crowd rules ---
    groups = response.get("crowd_groups") or []
    defects.extend(_crowd_defects(groups, known_scenes))
    member_ids = {g.get("crowd_group_id") for g in groups
                  if isinstance(g, dict) and _text(g.get("crowd_group_id"))}
    if len(member_ids) != len(groups):
        defects.append({"field": "crowd_groups",
                        "issue": "duplicate or missing crowd_group_id"})

    # A scene may only draw its crowd from groups the manifest actually declares.
    for crowd_id in derive_crowds(scenes):
        if crowd_id not in member_ids:
            defects.append({"field": "crowd_group_ids",
                            "issue": "scene declares crowd group '%s' but the manifest "
                                     "declares no such group" % crowd_id})

    for speaker in derive_speakers(scenes):
        if _anonymous(str(speaker)):
            defects.append({"field": "speakers",
                            "issue": "'%s' is a generic descriptor; declare the person "
                                     "with explicit wants, fears and speech" % speaker})
        elif speaker not in selected:
            defects.append({"field": "speakers",
                            "issue": "'%s' is declared in a scene — line, reaction or "
                                     "binding — but has no cast profile" % speaker})

    if defects:
        raise CastWriteError(
            "INCOMPLETE_CAST",
            "cast refused: " + "; ".join(
                "%s: %s" % (d.get("field"), d.get("issue")) for d in defects[:12]),
            {"defects": defects, "receipt": receipt})

    # --- manifest ---
    # Library order is stable: existing identities keep their place, new ones
    # are appended so a rerun cannot reshuffle revisions.
    ordered = [library_by_id[c["character_id"]] for c in snapshot["characters"]
               if isinstance(c, dict) and c["character_id"] in library_by_id]
    ordered += [c for c in authored if c["character_id"] not in existing]
    final_snapshot = dict(snapshot)
    final_snapshot["revision"] = snapshot["revision"] + (1 if authored else 0)
    final_snapshot["characters"] = ordered

    receipt["authored_character_ids"] = [c["character_id"] for c in authored]
    receipt["selected_character_ids"] = [e["character_id"] for e in cast_entries]
    receipt["library_digest_written"] = library_digest(final_snapshot)

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "client_id": client_id,
        "episode_id": request["episode_id"],
        "revision": 1,
        "library_revision": final_snapshot["revision"],
        "library_digest": library_digest(final_snapshot),
        "research_binding": {
            "revision": request["research_bundle"]["revision"],
            "content_digest": request["research_bundle"]["content_digest"],
        },
        "selection": selection,
        "cast": cast_entries,
        "crowd_groups": list(groups),
        "people_free": bool(people_free),
        "people_free_reason": reason if people_free else None,
        "draft_state": DRAFT_COMPLETE,
        "approval_bindings": [],
        "dispatch_receipt": receipt,
    }

    return {
        "state": "COMPLETE",
        "identities": final_snapshot["characters"],
        "library": final_snapshot,
        "manifest": manifest,
        "dispatch_receipt": receipt,
        "dispatch_response": response,
    }


def verify_receipt(result):
    """Prove the output still corresponds to the captured dispatch response."""
    if not isinstance(result, dict):
        return False
    receipt = result.get("dispatch_receipt") or {}
    response = result.get("dispatch_response")
    if response is None or not receipt:
        return False
    if receipt.get("response_digest") != canonical_digest(response):
        return False
    names = {c.get("character_id") for c in result.get("identities") or []}
    return all(cid in names for cid in receipt.get("selected_character_ids") or [])


# --- legacy adapter ---------------------------------------------------------

def seed_from_legacy_bible(record, client_id, character_id):
    """Map an existing ``character_bible.record()`` into an authoring seed.

    The legacy bible carries a name, description, background, ethnicity and
    voice notes — no wants, fears, beliefs or behaviour, so this is a SEED for
    the author dispatch, never a complete identity and never sealed.
    """
    if not isinstance(record, dict):
        raise CastWriteError("LEGACY_INVALID", "legacy bible record must be an object",
                             {"record": type(record).__name__})
    if not _text(record.get("character_name")):
        raise CastWriteError("LEGACY_INVALID", "legacy bible record has no character_name",
                             {"client_id": client_id})
    return {
        "client_id": client_id,
        "character_id": character_id,
        "display_name": record["character_name"].strip(),
        "identity_summary": record.get("character_description") or "",
        "relevant_background_history": [record["character_background"]]
        if _text(record.get("character_background")) else [],
        "appearance_traits": record.get("character_ethnicity") or "",
        "voice_hint": record.get("voice_notes") or "",
        "reference_ids": list(record.get("reference_images") or []),
        "story_status": "OWNER_SUPPLIED",
        "seed_state": "SEED_ONLY_INCOMPLETE",
    }
