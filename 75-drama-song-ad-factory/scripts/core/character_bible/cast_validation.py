#!/usr/bin/env python3
"""S75-T07: crowd, singled-out and undeclared-speaker validation.

Complements the S75-T03 envelope (``story_first_contracts``) with the three
checks that need the whole cast and every scene at once:

* a crowd is a *group* record with explicit composition, collective behaviour
  and per-location placement -- "people in background" is refused;
* the moment a crowd member speaks, reacts, is named in an action or gains a
  continuing identity, that member must be an individual ``character_id``
  declared in the cast; a group ID is never a speaker;
* every speaker / performer / reacting or acting person in every scene must
  resolve to a cast entry, and to that scene's ``cast_ids`` when it declares
  them. An absent cast field fails closed.

Standard library only, no IO on import, no provider or network call.
"""

from __future__ import annotations

import re

from story_first_contracts import validate_cast_manifest

__all__ = [
    "CastValidationError",
    "CROWD_REQUIRED",
    "ANONYMOUS_SPEAKER_PATTERNS",
    "SPEAKER_SOURCES",
    "validate_crowd_group",
    "derive_speakers",
    "validate_cast",
    "assert_valid_cast",
]

CROWD_REQUIRED = (
    "crowd_group_id",
    "composition",
    "count",
    "age_range",
    "roles",
    "location_placement",
    "collective_behavior",
    "permitted_motion",
    "attention_direction",
    "interaction_with_leads",
    "wardrobe_palette",
    "camera_limits",
    "entry_exit_rule",
    "recurrence",
    "dialogue",
    "reference_provenance",
    "scene_ids",
)

#: Generic descriptors that hide an undeclared person. A line or action
#: attributed to one of these is refused; the person needs an individual ID.
ANONYMOUS_SPEAKER_PATTERNS = (
    "a woman", "a man", "a worker", "a customer", "someone", "somebody",
    "a person", "the crowd", "people in background", "background people",
    "a bystander", "the manager", "a voice", "a girl", "a boy",
)

#: Scene fields whose entries carry an individual ``character_id`` and are
#: therefore refusable when the ID is undeclared.
SPEAKER_SOURCES = (
    ("spoken_dialogue", "speaker"),
    ("sung_lyrics", "singer"),
    ("performance_order", "performer"),
    ("named_actions", "named action"),
    ("featured_reactions", "featured reaction"),
    ("singled_out", "singled-out person"),
)

_CROWD_DIALOGUE_PROHIBITED = ("PROHIBITED", "NONE", "SILENT")


class CastValidationError(ValueError):
    """One actionable packet of every cast defect found. No per-person loop."""

    def __init__(self, packet):
        self.packet = packet
        super().__init__(
            "cast refused: %d defect(s): %s"
            % (packet["defect_count"],
               "; ".join(d["message"] for d in packet["defects"][:5]))
        )


def _defect(field, issue, ref=None, message=None):
    out = {"field": field, "issue": issue}
    if ref is not None:
        out["ref"] = ref
    out["message"] = message or "%s: %s" % (field, issue)
    return out


def _blank(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def _text(value):
    return isinstance(value, str) and value.strip() != ""


def _word_count(value):
    return len(value.split()) if _text(value) else 0


def _is_anonymous(value):
    if not _text(value):
        return False
    lowered = " ".join(value.strip().lower().split())
    return any(lowered == p or lowered.startswith(p + " ") for p in ANONYMOUS_SPEAKER_PATTERNS)


def _positive_count(count):
    if isinstance(count, bool):
        return False
    if isinstance(count, int):
        return count > 0
    if isinstance(count, dict):
        lo, hi = count.get("min"), count.get("max")
        if isinstance(lo, int) and isinstance(hi, int) and not isinstance(lo, bool) \
                and not isinstance(hi, bool):
            return 0 < lo <= hi
    return False


def _placement_map(placement):
    """Normalise ``location_placement`` to {scene_id: text}. None when malformed."""
    if isinstance(placement, dict):
        return {str(k): v for k, v in placement.items()}
    if isinstance(placement, list):
        out = {}
        for item in placement:
            if not isinstance(item, dict) or _blank(item.get("scene_id")):
                return None
            out[str(item["scene_id"])] = item.get("placement")
        return out
    return None


def validate_crowd_group(group, scene_ids=None, cast_ids=None):
    """Defects for one crowd group record. Explicit composition/behaviour/placement."""
    if not isinstance(group, dict):
        return [_defect("crowd_groups", "not an object")]
    defects = [_defect("crowd_groups." + f, "missing")
               for f in CROWD_REQUIRED if f not in group]
    gid = group.get("crowd_group_id")
    ref = {"crowd_group_id": gid}

    composition = group.get("composition")
    if isinstance(composition, list):
        composition_ok = bool(composition) and all(_text(c) for c in composition)
    else:
        composition_ok = _word_count(composition) >= 3
    if not composition_ok:
        defects.append(_defect("crowd_groups.composition",
                               "no explicit composition of the crowd", ref,
                               "crowd_groups.composition: state who the crowd is, not 'people'"))
    if "count" in group and not _positive_count(group.get("count")):
        defects.append(_defect("crowd_groups.count",
                               "not a positive count or min<=max range", ref))
    if _blank(group.get("age_range")):
        defects.append(_defect("crowd_groups.age_range", "empty", ref))
    roles = group.get("roles")
    if not (isinstance(roles, list) and roles and all(_text(r) for r in roles)):
        defects.append(_defect("crowd_groups.roles", "no relevant roles", ref))

    group_scenes = group.get("scene_ids")
    if not (isinstance(group_scenes, list) and group_scenes and all(_text(s) for s in group_scenes)):
        defects.append(_defect("crowd_groups.scene_ids", "no allowed scene", ref))
        group_scenes = []
    elif scene_ids is not None:
        for sid in group_scenes:
            if sid not in scene_ids:
                defects.append(_defect("crowd_groups.scene_ids", "undefined scene",
                                       dict(ref, scene_id=sid)))

    placements = _placement_map(group.get("location_placement"))
    if placements is None:
        defects.append(_defect("crowd_groups.location_placement",
                               "no per-scene placement map", ref))
    else:
        for sid in group_scenes:
            if _blank(placements.get(sid)):
                defects.append(_defect("crowd_groups.location_placement",
                                       "no placement for scene", dict(ref, scene_id=sid)))

    for field in ("collective_behavior", "permitted_motion", "attention_direction",
                  "interaction_with_leads", "wardrobe_palette", "camera_limits",
                  "entry_exit_rule", "recurrence", "reference_provenance"):
        value = group.get(field)
        if isinstance(value, list):
            ok = bool(value) and all(_text(v) for v in value)
        elif isinstance(value, dict):
            ok = not _blank(value)
        else:
            ok = _word_count(value) > 0
        if not ok:
            defects.append(_defect("crowd_groups." + field, "not specified", ref))

    # A crowd may not carry dialogue unless every speaking member is individualized.
    individual = group.get("individualized_member_ids") or group.get("singled_out_members") or []
    if not isinstance(individual, list):
        individual = [individual]
    dialogue = group.get("dialogue")
    dialogue_value = dialogue.strip().upper() if _text(dialogue) else None
    if _blank(dialogue):
        defects.append(_defect("crowd_groups.dialogue",
                               "dialogue rule missing (use PROHIBITED)", ref))
    elif dialogue_value not in _CROWD_DIALOGUE_PROHIBITED and not individual:
        defects.append(_defect("crowd_groups.dialogue",
                               "dialogue permits members never individualized", ref))
    for member in individual:
        if not _text(member):
            defects.append(_defect("crowd_groups.individualized_member_ids",
                                   "member is not an individual character_id", ref))
        elif _is_anonymous(member):
            defects.append(_defect("crowd_groups.individualized_member_ids",
                                   "anonymous description where a character_id is required",
                                   dict(ref, member=member),
                                   "promote '%s' to a full identity with a stable ID" % member))
        elif cast_ids is not None and member not in cast_ids:
            defects.append(_defect("crowd_groups.individualized_member_ids",
                                   "singled-out member is not in the cast",
                                   dict(ref, member=member)))
    return defects


def derive_speakers(scenes):
    """Every individually attributed line, action or reaction, in scene order."""
    out = []
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        sid = scene.get("scene_id")
        for field, kind in SPEAKER_SOURCES:
            for entry in scene.get(field) or []:
                if not isinstance(entry, dict):
                    out.append({"scene_id": sid, "field": field, "source": kind,
                                "character_id": None})
                    continue
                out.append({
                    "scene_id": sid,
                    "field": field,
                    "source": kind,
                    "line_id": entry.get("line_id"),
                    "character_id": entry.get("character_id"),
                })
    return out


def _scene_defects(scene, cast_ids, crowd_ids):
    defects = []
    sid = scene.get("scene_id") if isinstance(scene, dict) else None
    if not isinstance(scene, dict):
        return [_defect("scene_plan", "scene not an object")]
    scene_cast = scene.get("cast_ids")
    scene_cast_set = set(scene_cast) if isinstance(scene_cast, list) else set()

    for cid in scene_cast if isinstance(scene_cast, list) else []:
        if cid not in cast_ids:
            defects.append(_defect("scene.cast_ids", "cast id not declared in manifest",
                                   {"scene_id": sid, "character_id": cid}))

    for cgid in scene.get("crowd_group_ids") or []:
        if cgid not in crowd_ids:
            defects.append(_defect("scene.crowd_group_ids", "undefined crowd group",
                                   {"scene_id": sid, "crowd_group_id": cgid}))

    for entry in derive_speakers([scene]):
        cid = entry.get("character_id")
        ref = {"scene_id": sid, "field": entry["field"], "line_id": entry.get("line_id"),
               "character_id": cid}
        if _blank(cid):
            defects.append(_defect("scene." + entry["field"], "anonymous %s with no declared cast ID" % entry["source"], ref,
                                   "scene %s: %s has no character_id; declare the person in the cast" % (sid, entry["source"])))
        elif cid in crowd_ids:
            defects.append(_defect("scene." + entry["field"],
                                   "crowd group used as an individual %s" % entry["source"], ref,
                                   "scene %s: %s is a crowd group; a singled-out member needs its own character_id and profile" % (sid, cid)))
        elif _is_anonymous(cid):
            defects.append(_defect("scene." + entry["field"], "anonymous speaker", ref,
                                   "scene %s: '%s' is a description, not a cast character_id" % (sid, cid)))
        elif cid not in cast_ids:
            defects.append(_defect("scene." + entry["field"], "speaker not declared in cast", ref,
                                   "scene %s: %s '%s' is not in the episode cast manifest" % (sid, entry["source"], cid)))
        elif scene_cast_set and cid not in scene_cast_set:
            defects.append(_defect("scene." + entry["field"],
                                   "speaker not declared in this scene's cast", ref,
                                   "scene %s: add %s to cast_ids or remove the %s" % (sid, cid, entry["source"])))
    return defects


def validate_cast(manifest, scenes=None):
    """One actionable packet for the full cast against every scene."""
    scenes = list(scenes or [])
    if not isinstance(manifest, dict):
        return {"ok": False, "defect_count": 1,
                "defects": [_defect("cast_manifest", "missing; cast fields cannot be omitted")]}

    defects = list(validate_cast_manifest(manifest, scenes))
    # The S75-T03 envelope reports field/issue; this packet adds one message.
    for defect in defects:
        defect.setdefault("message", "%s: %s" % (defect.get("field"), defect.get("issue")))
    cast = manifest.get("cast")
    entries = [e for e in cast if isinstance(e, dict)] if isinstance(cast, list) else []
    cast_ids = {e.get("character_id") for e in entries if _text(e.get("character_id"))}
    scene_ids = {s.get("scene_id") for s in scenes
                 if isinstance(s, dict) and _text(s.get("scene_id"))}

    for entry in entries:
        for sid in entry.get("scene_ids") or []:
            if scene_ids and sid not in scene_ids:
                defects.append(_defect("cast.scene_ids", "undefined scene",
                                       {"character_id": entry.get("character_id"),
                                        "scene_id": sid}))

    groups = manifest.get("crowd_groups") or []
    if not isinstance(groups, list):
        defects.append(_defect("crowd_groups", "not a list"))
        groups = []
    crowd_ids = set()
    for group in groups:
        gid = group.get("crowd_group_id") if isinstance(group, dict) else None
        if gid and gid in crowd_ids:
            defects.append(_defect("crowd_groups", "duplicate crowd_group_id", gid))
        if gid:
            crowd_ids.add(gid)
        defects.extend(validate_crowd_group(group, scene_ids or None, cast_ids))

    for scene in scenes:
        defects.extend(_scene_defects(scene, cast_ids, crowd_ids))

    seen = set()
    unique = []
    for defect in defects:
        key = (defect["field"], defect["issue"], repr(sorted((defect.get("ref") or {}).items())))
        if key not in seen:
            seen.add(key)
            unique.append(defect)
    return {"ok": not unique, "defect_count": len(unique), "defects": unique}


def assert_valid_cast(manifest, scenes=None):
    """Return the passing packet or raise one CastValidationError packet."""
    packet = validate_cast(manifest, scenes)
    if not packet["ok"]:
        raise CastValidationError(packet)
    return packet
