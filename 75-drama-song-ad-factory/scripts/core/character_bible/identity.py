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
import json

__all__ = [
    "CastDefect", "IdentityDefect", "canonical_digest", "library_digest",
    "validate_episode_setting", "validate_identity", "validate_library",
    "validate_cast", "seal_identity", "SCHEMA_VERSION", "MANIFEST_SCHEMA_VERSION",
    "EPISODE_SCHEMA_VERSION", "EPISODE_ONLY_FIELDS", "ROLES", "CROWD_REQUIRED",
    "ANONYMOUS_SPEAKER_PATTERNS",
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
DRAFT_STATES = frozenset({"DRAFT_INCOMPLETE", "DRAFT_COMPLETE", "APPROVED"})
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


def _text(value):
    return isinstance(value, str) and value.strip() != ""


def _text_list(value, minimum=1):
    return (isinstance(value, list) and len(value) >= minimum
            and all(_text(item) for item in value))


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_digest(obj, *, exclude=_DIGEST_EXCLUDED):
    """SHA-256 over canonical JSON, ignoring bookkeeping fields."""
    body = {k: v for k, v in obj.items() if k not in exclude}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def seal_identity(record):
    """Attach the content digest an identity record is addressed by."""
    sealed = dict(record)
    sealed.setdefault("schema_version", SCHEMA_VERSION)
    sealed["content_digest"] = canonical_digest(sealed)
    return sealed


def library_digest(snapshot):
    """Digest of the selected library snapshot the manifest binds to."""
    return canonical_digest(snapshot, exclude=frozenset({"local_cache", "sync_state"}))


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
    if not isinstance(record, dict):
        return [_defect("<record>", "NOT_OBJECT", "identity record must be an object")]

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

    if record.get("schema_version") != SCHEMA_VERSION:
        out.append(_defect("schema_version", "SCHEMA_VERSION",
                           f"expected '{SCHEMA_VERSION}'"))
    revision = record.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        out.append(_defect("revision", "REVISION",
                           "revision must be a positive integer"))
    digest = record.get("content_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        out.append(_defect("content_digest", "DIGEST",
                           "content_digest must be a 64-character sha256"))
    elif digest != canonical_digest(record):
        out.append(_defect("content_digest", "DIGEST_MISMATCH",
                           "content_digest does not match the record content"))

    if record.get("story_status") not in STORY_STATUS:
        out.append(_defect("story_status", "STORY_STATUS",
                           f"story_status must be one of {sorted(STORY_STATUS)}"))

    aliases = record.get("aliases", [])
    if not isinstance(aliases, list) or not all(_text(a) for a in aliases):
        out.append(_defect("aliases", "ALIASES", "aliases must be a list of strings"))

    # wants / voice: typed, not embedded prose.
    wants = record.get("wants")
    if not (isinstance(wants, dict) and _text(wants.get("external"))
            and _text(wants.get("internal"))):
        out.append(_defect("wants", "WANTS",
                           "wants must carry external and internal drivers"))
    voice = record.get("voice")
    if not (isinstance(voice, dict) and _text(voice.get("rhythm"))
            and _text(voice.get("vocabulary")) and _text(voice.get("restraint"))):
        out.append(_defect("voice", "VOICE",
                           "voice must carry rhythm, vocabulary and restraint"))

    visual = record.get("identity_visual")
    if not isinstance(visual, dict):
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
    if not isinstance(references, list) or not all(_text(r) for r in references):
        out.append(_defect("reference_ids", "REFERENCES",
                           "reference_ids must be a list of strings; an empty list is valid"))
    # Text identity must be complete before any image exists.

    provenance = record.get("provenance_by_field")
    if not isinstance(provenance, dict) or not provenance:
        out.append(_defect("provenance_by_field", "PROVENANCE",
                           "every substantive assertion needs a provenance entry"))
    elif any(not _text(str(v)) for v in provenance.values()):
        out.append(_defect("provenance_by_field", "PROVENANCE",
                           "provenance values must name a real origin"))

    if record.get("draft_state") not in DRAFT_STATES:
        out.append(_defect("draft_state", "DRAFT_STATE",
                           f"draft_state must be one of {sorted(DRAFT_STATES)}"))
    approvals = record.get("approval_bindings", [])
    if not isinstance(approvals, list):
        out.append(_defect("approval_bindings", "APPROVALS",
                           "approval_bindings must be a list; never synthesize receipts"))
    for key in ("shared_source", "local_cache"):
        if record.get(key) is not None and not isinstance(record.get(key), dict):
            out.append(_defect(key, "SYNC", f"{key} must be an object or null"))
    if record.get("sync_state") not in SYNC_STATES:
        out.append(_defect("sync_state", "SYNC",
                           f"sync_state must be one of {sorted(SYNC_STATES)}"))

    relationships = record.get("relationships", [])
    if not isinstance(relationships, list):
        out.append(_defect("relationships", "RELATIONSHIPS",
                           "relationships must be a list"))
    else:
        for index, edge in enumerate(relationships):
            where = f"relationships[{index}]"
            if not isinstance(edge, dict):
                out.append(_defect(where, "RELATIONSHIPS", "relationship must be an object"))
                continue
            for field in ("character_id", "type", "history", "present_tension",
                          "dependency"):
                if not _text(edge.get(field)):
                    out.append(_defect(f"{where}.{field}", "RELATIONSHIPS",
                                       f"relationship requires '{field}'"))
            if edge.get("character_id") == record.get("character_id"):
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
    if not isinstance(snapshot, dict):
        raise IdentityDefect([_defect("<snapshot>", "NOT_OBJECT",
                                      "library snapshot must be an object")])
    out = []
    if not _text(snapshot.get("client_id")):
        out.append(_defect("client_id", "CLIENT", "library snapshot needs a client_id"))
    characters = snapshot.get("characters")
    if not isinstance(characters, list) or not characters:
        out.append(_defect("characters", "LIBRARY_EMPTY",
                           "library snapshot must contain at least one character"))
        characters = []

    seen = set()
    for index, record in enumerate(characters):
        defects = _validate_identity(record)
        out.extend({**d, "field": f"characters[{index}].{d['field']}"} for d in defects)
        cid = record.get("character_id") if isinstance(record, dict) else None
        if cid in seen:
            out.append(_defect(f"characters[{index}].character_id", "DUPLICATE_ID",
                               f"duplicate character_id '{cid}'"))
        seen.add(cid)
        if isinstance(record, dict) and record.get("client_id") != snapshot.get("client_id"):
            out.append(_defect(f"characters[{index}].client_id", "CLIENT_MISMATCH",
                               "character belongs to a different client namespace"))

    for index, record in enumerate(characters):
        if not isinstance(record, dict):
            continue
        for edge_index, edge in enumerate(record.get("relationships") or []):
            target = edge.get("character_id") if isinstance(edge, dict) else None
            # A relationship may leave the client library only if it is
            # explicitly marked external; otherwise the ID must resolve.
            external = isinstance(edge, dict) and edge.get("external") is True
            if target not in seen and not external:
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
    if not isinstance(record, dict):
        raise IdentityDefect([_defect("<record>", "NOT_OBJECT",
                                      "episode setting must be an object")])
    if record.get("schema_version") != EPISODE_SCHEMA_VERSION:
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
    if not isinstance(group, dict):
        return [_defect(where, "CROWD", "crowd group must be an object")]
    for field in CROWD_REQUIRED:
        value = group.get(field)
        ok = value if field == "count" else value
        if value is None:
            out.append(_defect(f"{where}.{field}", "CROWD_RULES",
                               f"crowd group requires '{field}'"))
        elif field in ("roles", "scene_ids"):
            if not _text_list(value):
                out.append(_defect(f"{where}.{field}", "CROWD_RULES",
                                   f"crowd '{field}' must be a non-empty list"))
        elif field == "count":
            if not (isinstance(value, int) and not isinstance(value, bool) and value > 0):
                out.append(_defect(f"{where}.count", "CROWD_RULES",
                                   "crowd count must be a positive integer"))
        elif not _text(value):
            out.append(_defect(f"{where}.{field}", "CROWD_RULES",
                               f"crowd '{field}' must be non-empty"))

    if group.get("dialogue") != "forbidden":
        out.append(_defect(f"{where}.dialogue", "CROWD_DIALOGUE",
                           "a crowd group may not speak; individualize the member first"))
    if group.get("singled_out"):
        out.append(_defect(f"{where}.singled_out", "CROWD_SINGLED_OUT",
                           "a singled-out crowd member must be promoted to a full identity "
                           "with its own character_id and removed from the crowd group"))
    for sid in group.get("scene_ids") or []:
        if scene_ids is not None and sid not in scene_ids:
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
    if not isinstance(manifest, dict):
        raise CastDefect([_defect("<manifest>", "NOT_OBJECT",
                                  "cast manifest must be an object")])
    characters = (library or {}).get("characters") or []
    by_id = {c.get("character_id"): c for c in characters if isinstance(c, dict)}
    known_scenes = set(scene_ids) if scene_ids is not None else None

    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        out.append(_defect("schema_version", "SCHEMA_VERSION",
                           f"expected '{MANIFEST_SCHEMA_VERSION}'"))
    for field in ("client_id", "episode_id"):
        if not _text(manifest.get(field)):
            out.append(_defect(field, "CAST_INCOMPLETE",
                               f"cast manifest requires '{field}'"))
    if manifest.get("library_digest") != library_digest(library):
        out.append(_defect("library_digest", "LIBRARY_BINDING",
                           "cast manifest was not bound to this library snapshot"))

    cast = manifest.get("cast")
    people_free = manifest.get("people_free") is True
    if people_free:
        if cast:
            out.append(_defect("cast", "PEOPLE_FREE_CONTRADICTION",
                               "a people-free episode cannot select cast members"))
        if not _text(manifest.get("people_free_reason")):
            out.append(_defect("people_free_reason", "PEOPLE_FREE",
                               "a people-free episode must state its reason explicitly"))
    elif not isinstance(cast, list):
        out.append(_defect("cast", "CAST_INCOMPLETE",
                           "cast list is required; omission is not an empty cast"))
    elif not cast:
        out.append(_defect("cast", "CAST_EMPTY",
                           "a narrative with people cannot have an empty cast"))

    selected = {}
    for index, entry in enumerate(cast or []):
        where = f"cast[{index}]"
        if not isinstance(entry, dict):
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
            if entry.get("identity_revision") != record.get("revision"):
                out.append(_defect(f"{where}.identity_revision", "STALE_REVISION",
                                   f"'{cid}' is selected at revision "
                                   f"{entry.get('identity_revision')}, library has "
                                   f"{record.get('revision')}"))
            if entry.get("identity_digest") != record.get("content_digest"):
                out.append(_defect(f"{where}.identity_digest", "DIGEST_MISMATCH",
                                   f"'{cid}' selection does not bind the library content"))

        if entry.get("episode_role") not in ROLES:
            out.append(_defect(f"{where}.episode_role", "CAST_ROLE",
                               f"episode_role must be one of {sorted(ROLES)}"))
        for field in ("immediate_story_function", "choice_or_consequence"):
            if not _text(entry.get(field)):
                out.append(_defect(f"{where}.{field}", "CAST_INCOMPLETE",
                                   f"'{field}' is required for a selected person"))
        if not isinstance(entry.get("relationship_changes", []), list):
            out.append(_defect(f"{where}.relationship_changes", "CAST_INCOMPLETE",
                               "relationship_changes must be a list"))
        entry_scenes = entry.get("scene_ids")
        if not _text_list(entry_scenes):
            out.append(_defect(f"{where}.scene_ids", "CAST_INCOMPLETE",
                               "every selected person needs at least one scene_id"))
        else:
            for sid in entry_scenes:
                if known_scenes is not None and sid not in known_scenes:
                    out.append(_defect(f"{where}.scene_ids", "UNKNOWN_SCENE",
                                       f"unknown scene '{sid}'"))
        if _anonymous(str(cid)) or _anonymous(str(entry.get("display_name_hint", ""))):
            out.append(_defect(f"{where}.character_id", "ANONYMOUS_IDENTITY",
                               "a generic descriptor is not an identity"))

    groups = manifest.get("crowd_groups", [])
    if not isinstance(groups, list):
        out.append(_defect("crowd_groups", "CROWD", "crowd_groups must be a list"))
        groups = []
    seen_groups = set()
    for index, group in enumerate(groups):
        out.extend(_validate_crowd(group, index, known_scenes))
        gid = group.get("crowd_group_id") if isinstance(group, dict) else None
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
