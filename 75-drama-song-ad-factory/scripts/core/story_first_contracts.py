"""Story-first artifact order and record contracts for Skill 75. Stdlib only.

Mandated order (S75-T03 / S75-A03):

  research/premise -> complete cast + episode world -> causal beats + full scene
  plan -> full script/lyrics -> whole-package approval -> music -> timed
  storyboard -> keyframes -> storyboard approval -> video -> assembly

Importing this module has no side effects: it defines the stage graph, the
artifact envelope, the identity/world/scene schemas and the validators. It never
writes, dispatches a model, or reaches the network.
"""
from __future__ import annotations

import hashlib
import json

SCHEMA_VERSION = "s75.contracts.v1"
IDENTITY_SCHEMA_VERSION = "s75.identity.v1"
WORLD_SCHEMA_VERSION = "s75.world.v1"
SCENE_SCHEMA_VERSION = "s75.scene.v1"

DRAFT = "DRAFT"
COMPLETE = "COMPLETE"
APPROVED = "APPROVED"
_READY_STATES = (COMPLETE, APPROVED)

# ponytail: word floors are the only automated stand-in for semantic richness.
# Raise them if reviewers still see filler; lower only with evidence.
MIN_PURPOSE_WORDS = 5
MIN_ACTION_WORDS = 8
MIN_CHOICE_WORDS = 4
MIN_LINE_WORDS = 3

STAGE_ORDER = (
    "research_premise",
    "cast_and_world",
    "story_plan",
    "script_lyrics",
    "package_approval",
    "music",
    "timed_storyboard",
    "keyframes",
    "storyboard_approval",
    "video",
    "assembly",
)

STAGE_PRODUCES = {
    "research_premise": ("research_bundle",),
    "cast_and_world": ("episode_cast_manifest", "episode_world"),
    "story_plan": ("causal_story_beats", "scene_plan"),
    "script_lyrics": ("script", "lyrics"),
    "package_approval": ("creative_package_manifest", "package_approval"),
    "music": ("selected_music",),
    "timed_storyboard": ("timed_storyboard", "production_continuity"),
    "keyframes": ("keyframes",),
    "storyboard_approval": ("storyboard_approval",),
    "video": ("video_checks",),
    "assembly": ("final_delivery",),
}

_FOUNDATION = (
    "research_bundle",
    "episode_cast_manifest",
    "episode_world",
    "causal_story_beats",
    "scene_plan",
)

STAGE_REQUIRES = {
    "research_premise": (),
    "cast_and_world": ("research_bundle",),
    "story_plan": ("research_bundle", "episode_cast_manifest", "episode_world"),
    "script_lyrics": _FOUNDATION,
    "package_approval": _FOUNDATION + ("script", "lyrics"),
    "music": _FOUNDATION + ("script", "lyrics", "creative_package_manifest", "package_approval"),
    "timed_storyboard": _FOUNDATION + ("script", "lyrics", "selected_music"),
    "keyframes": ("timed_storyboard", "production_continuity"),
    "storyboard_approval": ("timed_storyboard", "production_continuity", "keyframes"),
    "video": ("timed_storyboard", "production_continuity", "keyframes", "storyboard_approval"),
    "assembly": ("video_checks", "storyboard_approval"),
}

# Approval artifact -> artifacts whose exact current digest it must bind.
APPROVAL_BINDS = {
    "package_approval": _FOUNDATION + ("script", "lyrics", "creative_package_manifest"),
    "storyboard_approval": ("timed_storyboard", "production_continuity", "keyframes"),
}

IDENTITY_FIELDS = (
    "client_id", "character_id", "revision", "content_digest", "schema_version",
    "display_name", "aliases", "story_status", "identity_summary",
    "relevant_background_history", "occupation", "competence", "social_context",
    "relationships", "wants", "fears", "emotional_wound", "mistaken_belief",
    "contradictions", "habits", "voice", "behavior_under_pressure",
    "appearance_traits", "reference_ids", "provenance_by_field", "draft_state",
    "approval_bindings", "shared_source", "local_cache", "sync_state",
)
IDENTITY_NONEMPTY = (
    "client_id", "character_id", "display_name", "story_status", "identity_summary",
    "relevant_background_history", "occupation", "wants", "fears",
    "emotional_wound", "mistaken_belief", "contradictions", "habits", "voice",
    "behavior_under_pressure", "appearance_traits", "provenance_by_field", "draft_state",
)

WORLD_FIELDS = (
    "episode_id", "world_id", "schema_version", "revision", "content_digest",
    "premise", "era_and_timeline", "locations", "layout_and_geography",
    "social_rules", "physical_and_story_rules", "light_color_atmosphere",
    "sound_environment", "set_dressing_and_props", "cast_world_relations",
    "wardrobe_intent", "continuity_rules", "sources_and_unknowns",
    "draft_state", "approval_bindings",
)
LOCATION_FIELDS = (
    "location_id", "name", "story_function", "interior_exterior", "access",
    "entrances_exits", "visible_geography",
)

SCENE_FIELDS = (
    "scene_id", "sequence", "causal_predecessor", "causal_outcome",
    "dramatic_purpose", "time", "location_id", "world_revision", "cast_ids",
    "identity_revisions", "crowd_group_ids", "immediate_want", "obstacle",
    "visible_action", "consequential_choice", "emotion_before", "emotion_after",
    "turn_trigger", "spoken_dialogue", "sung_lyrics", "performance_order",
    "subtext_and_behavior", "sound_music_cues", "framing_movement_intent",
    "duration_seconds", "timing_basis", "transition", "visible_lip_sync",
    "claims", "references", "approval_bindings",
)
CAST_ENTRY_FIELDS = (
    "character_id", "identity_revision", "identity_digest", "episode_role",
    "scene_ids", "immediate_story_function", "choice_or_consequence",
)


class ContractError(Exception):
    def __init__(self, code, message, packet=None):
        super().__init__(message)
        self.code = code
        self.packet = packet or {}


def artifact_digest(record):
    """Canonical sha256 for any JSON-able record."""
    blob = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _words(value):
    if not isinstance(value, str):
        return 0
    return len(value.replace("…", " ").replace(".", " ").split())


def _blank(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def _defect(field, issue, ref=None):
    out = {"field": field, "issue": issue}
    if ref is not None:
        out["ref"] = ref
    return out


def _require_fields(record, fields):
    return [_defect(f, "missing") for f in fields if f not in record]


# --- identity -------------------------------------------------------------

def validate_identity(record):
    """Defects for one reusable character identity record."""
    if not isinstance(record, dict):
        return [_defect("record", "not an object")]
    defects = _require_fields(record, IDENTITY_FIELDS)
    for field in IDENTITY_NONEMPTY:
        if field in record and _blank(record[field]):
            defects.append(_defect(field, "empty"))
    voice = record.get("voice")
    if isinstance(voice, dict):
        defects.extend(_defect("voice." + k, "missing") for k in
                       ("rhythm", "vocabulary", "restraint") if _blank(voice.get(k)))
    elif voice is not None:
        defects.append(_defect("voice", "not an object"))
    wants = record.get("wants")
    if isinstance(wants, dict):
        defects.extend(_defect("wants." + k, "missing") for k in
                       ("external", "internal") if _blank(wants.get(k)))
    elif wants is not None:
        defects.append(_defect("wants", "not an object"))
    for rel in record.get("relationships") or []:
        if not isinstance(rel, dict) or _blank(rel.get("character_id")):
            defects.append(_defect("relationships", "entry without character_id"))
        elif rel.get("character_id") == record.get("character_id"):
            defects.append(_defect("relationships", "self reference"))
    if record.get("schema_version") not in (None, IDENTITY_SCHEMA_VERSION):
        defects.append(_defect("schema_version", "expected " + IDENTITY_SCHEMA_VERSION))
    return defects


# --- episode world --------------------------------------------------------

def validate_world(record):
    """Defects for one early episode-world record."""
    if not isinstance(record, dict):
        return [_defect("record", "not an object")]
    defects = _require_fields(record, WORLD_FIELDS)
    for field in ("episode_id", "world_id", "premise", "era_and_timeline",
                  "layout_and_geography", "social_rules", "physical_and_story_rules",
                  "light_color_atmosphere", "sound_environment",
                  "set_dressing_and_props", "cast_world_relations",
                  "wardrobe_intent", "continuity_rules", "sources_and_unknowns"):
        if field in record and _blank(record[field]):
            defects.append(_defect(field, "empty"))
    locations = record.get("locations")
    if isinstance(locations, list):
        if not locations:
            defects.append(_defect("locations", "empty"))
        seen = set()
        for loc in locations:
            if not isinstance(loc, dict):
                defects.append(_defect("locations", "entry not an object"))
                continue
            defects.extend(_defect("locations." + f, "missing")
                           for f in LOCATION_FIELDS if f not in loc)
            loc_id = loc.get("location_id")
            if loc_id and loc_id in seen:
                defects.append(_defect("locations", "duplicate location_id", loc_id))
            seen.add(loc_id)
    elif locations is not None:
        defects.append(_defect("locations", "not a list"))
    if record.get("schema_version") not in (None, WORLD_SCHEMA_VERSION):
        defects.append(_defect("schema_version", "expected " + WORLD_SCHEMA_VERSION))
    return defects


def world_location_ids(record):
    return {loc.get("location_id") for loc in (record or {}).get("locations") or []
            if isinstance(loc, dict)}


# --- cast -----------------------------------------------------------------

def validate_cast_manifest(manifest, scenes=None):
    """Defects for the episode cast manifest, optionally checked against scenes."""
    if not isinstance(manifest, dict):
        return [_defect("cast_manifest", "missing")]
    cast = manifest.get("cast")
    if not isinstance(cast, list) or not cast:
        return [_defect("cast", "empty; a missing cast field is a missing requirement")]
    defects = []
    known = set()
    for entry in cast:
        if not isinstance(entry, dict):
            defects.append(_defect("cast", "entry not an object"))
            continue
        defects.extend(_defect("cast." + f, "missing")
                       for f in CAST_ENTRY_FIELDS if f not in entry)
        cid = entry.get("character_id")
        if not cid:
            defects.append(_defect("cast.character_id", "empty"))
        elif cid in known:
            defects.append(_defect("cast", "duplicate character_id", cid))
        known.add(cid)
    for scene in (scenes or []):
        if not isinstance(scene, dict):
            continue
        sid = scene.get("scene_id")
        for cid in scene.get("cast_ids") or []:
            if cid not in known:
                defects.append(_defect("cast_ids", "undefined speaker", {"scene_id": sid, "character_id": cid}))
        for line in (scene.get("performance_order") or []):
            if isinstance(line, dict) and line.get("character_id") not in known:
                defects.append(_defect("performance_order", "undefined performer",
                                       {"scene_id": sid, "character_id": line.get("character_id")}))
    return defects


# --- causal scene ---------------------------------------------------------

def _validate_lines(scene, field):
    defects = []
    cast = set(scene.get("cast_ids") or [])
    for line in scene.get(field) or []:
        if not isinstance(line, dict):
            defects.append(_defect(field, "line not an object"))
            continue
        for key in ("line_id", "character_id", "text"):
            if _blank(line.get(key)):
                defects.append(_defect(field + "." + key, "missing"))
        if line.get("character_id") and line["character_id"] not in cast:
            defects.append(_defect(field, "performer not in cast_ids", line.get("character_id")))
        if _words(line.get("text")) < MIN_LINE_WORDS:
            defects.append(_defect(field, "placeholder or one-word line", line.get("line_id")))
    return defects


def validate_scene(record, world=None):
    """Defects for one rich causal scene. A one-line scene is refused."""
    if not isinstance(record, dict):
        return [_defect("scene", "not an object")]
    defects = _require_fields(record, SCENE_FIELDS)
    for field in SCENE_FIELDS:
        if field in ("spoken_dialogue", "sung_lyrics", "performance_order", "claims",
                     "references", "approval_bindings", "crowd_group_ids",
                     "causal_predecessor"):
            continue
        if field in record and _blank(record[field]):
            defects.append(_defect(field, "empty"))

    if _words(record.get("dramatic_purpose")) < MIN_PURPOSE_WORDS:
        defects.append(_defect("dramatic_purpose", "not a specific dramatic job"))
    if _words(record.get("visible_action")) < MIN_ACTION_WORDS:
        defects.append(_defect("visible_action", "not a filmable action"))
    if _words(record.get("consequential_choice")) < MIN_CHOICE_WORDS:
        defects.append(_defect("consequential_choice", "no consequential choice"))

    spoken = record.get("spoken_dialogue") or []
    sung = record.get("sung_lyrics") or []
    defects.extend(_validate_lines(record, "spoken_dialogue"))
    defects.extend(_validate_lines(record, "sung_lyrics"))
    if not record.get("silent_scene") and not spoken and not sung:
        defects.append(_defect("dialogue", "no spoken or sung line and not declared silent"))

    scenes_with_cause = record.get("causal_predecessor") is not None
    if not scenes_with_cause and record.get("sequence") not in (0, 1):
        defects.append(_defect("causal_predecessor", "missing cause"))

    duration = record.get("duration_seconds")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
        defects.append(_defect("duration_seconds", "not a positive number"))

    cast = record.get("cast_ids")
    revs = record.get("identity_revisions")
    if isinstance(cast, list) and isinstance(revs, dict):
        for cid in cast:
            if cid not in revs:
                defects.append(_defect("identity_revisions", "cast id has no revision", cid))

    if world is not None:
        known = world_location_ids(world)
        if known and record.get("location_id") not in known:
            defects.append(_defect("location_id", "undefined location", record.get("location_id")))
        if record.get("world_revision") is not None and \
                record.get("world_revision") != world.get("revision"):
            defects.append(_defect("world_revision", "stale world revision",
                                   {"scene": record.get("world_revision"),
                                    "world": world.get("revision")}))
    return defects


def validate_scene_plan(plan, world=None, manifest=None):
    """Defects for the full scene plan; every scene must be rich and resolvable."""
    scenes = plan.get("scenes") if isinstance(plan, dict) else None
    if not isinstance(scenes, list) or not scenes:
        return [_defect("scene_plan", "empty; every planned scene is required")]
    defects = []
    seen = set()
    for scene in scenes:
        sid = scene.get("scene_id") if isinstance(scene, dict) else None
        if sid in seen:
            defects.append(_defect("scene_id", "duplicate", sid))
        seen.add(sid)
        for defect in validate_scene(scene, world=world):
            ref = defect.get("ref")
            if not isinstance(ref, dict):
                ref = {"detail": ref} if ref is not None else {}
            defect["ref"] = dict(ref, scene_id=sid)
            defects.append(defect)
    if manifest is not None:
        defects.extend(validate_cast_manifest(manifest, scenes))
    return defects


# --- registry and stage order --------------------------------------------

class RunRegistry:
    """Current artifact per kind for one client run. No persistence, no IO."""

    def __init__(self):
        self._artifacts = {}

    def put(self, kind, payload=None, state=COMPLETE, revision=1,
            digest=None, artifact_id=None, approved_digests=None):
        if state not in (DRAFT, COMPLETE, APPROVED):
            raise ContractError("BAD_STATE", "unknown artifact state %r" % (state,))
        if digest is None and payload is not None:
            digest = artifact_digest(payload)
        self._artifacts[kind] = {
            "kind": kind,
            "artifact_id": artifact_id or kind,
            "revision": revision,
            "digest": digest,
            "state": state,
            "payload": payload,
            "approved_digests": dict(approved_digests or {}),
        }
        return self._artifacts[kind]

    def get(self, kind):
        return self._artifacts.get(kind)

    def kinds(self):
        return tuple(sorted(self._artifacts))

    def digest_of(self, kind):
        record = self._artifacts.get(kind)
        return record.get("digest") if record else None

    def payload_of(self, kind):
        record = self._artifacts.get(kind)
        return record.get("payload") if record else None


def _approval_defects(kind, registry):
    record = registry.get(kind)
    if not record:
        return [{"approval": kind, "issue": "absent"}]
    defects = []
    if record.get("state") != APPROVED:
        defects.append({"approval": kind, "issue": "not approved", "state": record.get("state")})
    bound = record.get("approved_digests") or {}
    for target in APPROVAL_BINDS.get(kind, ()):
        current = registry.digest_of(target)
        if current is None:
            defects.append({"approval": kind, "issue": "binds absent artifact", "target": target})
        elif bound.get(target) != current:
            defects.append({"approval": kind, "issue": "stale or mismatched binding", "target": target})
    return defects


def _artifact_ready(kind, registry):
    record = registry.get(kind)
    if not record:
        return False
    if kind in APPROVAL_BINDS:
        return not _approval_defects(kind, registry)
    return record.get("state") in _READY_STATES and bool(record.get("digest"))


def _payload_defects(kind, registry):
    payload = registry.payload_of(kind)
    if payload is None:
        return []
    if kind == "episode_cast_manifest":
        return validate_cast_manifest(payload, (registry.payload_of("scene_plan") or {}).get("scenes"))
    if kind == "episode_world":
        return validate_world(payload)
    if kind == "scene_plan":
        return validate_scene_plan(payload, world=registry.payload_of("episode_world"),
                                   manifest=registry.payload_of("episode_cast_manifest"))
    return []


def check_stage(stage, registry):
    """Admit `stage`, or raise ContractError with a precise missing-input packet."""
    if stage not in STAGE_ORDER:
        raise ContractError("UNKNOWN_STAGE", "unknown stage %r" % (stage,),
                            {"stage": stage, "known": list(STAGE_ORDER)})

    index = STAGE_ORDER.index(stage)
    unfinished = [s for s in STAGE_ORDER[:index]
                  if not all(_artifact_ready(k, registry) for k in STAGE_PRODUCES[s])]
    absent = [k for k in STAGE_REQUIRES[stage] if registry.get(k) is None]
    draft = [k for k in STAGE_REQUIRES[stage]
             if k not in APPROVAL_BINDS and registry.get(k) is not None
             and registry.get(k).get("state") not in _READY_STATES]
    approvals = [d for k in STAGE_REQUIRES[stage] if k in APPROVAL_BINDS
                 for d in _approval_defects(k, registry) if d.get("issue") != "absent"]
    defects = [d for k in STAGE_REQUIRES[stage] for d in _payload_defects(k, registry)]
    missing = absent + draft

    if unfinished or absent or draft or approvals or defects:
        packet = {"stage": stage, "missing": missing, "unfinished_stages": unfinished,
                  "approval_defects": approvals, "schema_defects": defects}
        if unfinished:
            code = "ORDER"
        elif absent or draft:
            code = "MISSING_INPUT"
        elif approvals:
            code = "APPROVAL"
        else:
            code = "SCHEMA"
        raise ContractError(code, "%s not admissible" % stage, packet)
    return {"stage": stage, "admitted": True, "requires": list(STAGE_REQUIRES[stage])}


def next_stage(stage):
    if stage not in STAGE_ORDER:
        raise ContractError("UNKNOWN_STAGE", "unknown stage %r" % (stage,))
    index = STAGE_ORDER.index(stage)
    return STAGE_ORDER[index + 1] if index + 1 < len(STAGE_ORDER) else None
