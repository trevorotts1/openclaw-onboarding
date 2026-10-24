"""Rich-scene and legacy-compatibility validation for Skill 75 (S75-T11 / S75-A11).

Reuses the released S75-T03 contracts (story_first_contracts) rather than
restating the scene schema. Adds the script-level checks the contract names:

  * one-line placeholder scenes are refused for new authoring
  * beat-only bypasses (beats present, no scenes) are refused
  * legacy records that predate the contract stay readable, are marked
    COMPATIBILITY_LIMITED with their unresolved rich fields listed, and are
    never regenerated, rewritten or reported as accepted rich scenes

Stdlib only. Pure functions: no IO, no model dispatch, no mutation of input.
"""
from __future__ import annotations

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import story_first_contracts as C  # noqa: E402

ORIGIN_NEW = "NEW"
ORIGIN_LEGACY = "LEGACY"

# ponytail: a scene must carry at least this many written words across its
# spoken/sung lines, and at least two real lines, to count as authored rather
# than a placeholder. Raise with reviewer evidence; silent scenes are exempt.
MIN_SCENE_LINE_WORDS = 8
MIN_SCENE_LINES = 2

# ponytail: free-text quality claims are held to a word floor plus one function
# word, the cheapest structural stand-in for "this is a statement, not a
# keyword list". Raise the floors with reviewer evidence.
MIN_CLAIM_WORDS = 4

# Closed-class English words that any clause carries and a bare keyword list
# does not. This is a structural test, never a list of banned values.
_FUNCTION_WORDS = frozenset("""
a an the of to in on at for with from by about into over under before after
and or but because so that when while as than through against between
her his their its it they she he we you i me him them us
must wants want chooses choose forces force keeps keep makes make
is are was were be been being has have had do does did
""".split())

_EMOTION_FIELDS = ("emotion_before", "emotion_after")
_CLAIM_FIELDS = (("dramatic_purpose", C.MIN_PURPOSE_WORDS),
                 ("visible_action", C.MIN_ACTION_WORDS),
                 ("consequential_choice", C.MIN_CHOICE_WORDS),
                 ("turn_trigger", 3))

RICH_SCHEMA_VERSIONS = (C.SCENE_SCHEMA_VERSION, "s75.script.v1")

COMPATIBILITY_LIMITED = "COMPATIBILITY_LIMITED"

PLACEHOLDER_TEXT = ("...", "…", "tbd", "todo", "line here", "placeholder")

# Rich fields whose absence makes a legacy record compatibility-limited.
_RICH_FIELDS = (
    "dramatic_purpose", "time", "location_id", "world_revision", "cast_ids",
    "immediate_want", "obstacle", "visible_action", "consequential_choice",
    "emotion_before", "emotion_after", "turn_trigger", "spoken_dialogue",
    "sung_lyrics", "performance_order", "sound_music_cues",
    "framing_movement_intent", "duration_seconds", "transition",
    "visible_lip_sync",
)


def _defect(code, field, detail=None):
    out = {"code": code, "field": field}
    if detail is not None:
        out["detail"] = detail
    return out


def _script_defects(script):
    """Structural defects in the container, before any scene is examined."""
    scenes = script.get("scenes")
    if scenes is not None and not isinstance(scenes, list):
        return [_defect("NOT_A_LIST", "scenes")]
    if scenes:
        return []
    if script.get("beats"):
        return [_defect("BEAT_ONLY_BYPASS", "scenes",
                        "beats are not a script; write and validate every scene")]
    return [_defect("EMPTY", "scenes", "no scenes")]


def is_legacy(script):
    """A record provably predates the rich-scene contract.

    Acceptance is not a missing-field bypass: the record must carry both an
    origin marker and a stable artifact identity, so a newly authored one-line
    object cannot be relabelled into acceptance.
    """
    if not isinstance(script, dict):
        return False
    if script.get("legacy") is not True and script.get("record_origin") != ORIGIN_LEGACY:
        if script.get("schema_version") in (None, *RICH_SCHEMA_VERSIONS):
            return False
    return bool(script.get("artifact_id") or script.get("content_digest")
                or script.get("run_id"))


def _legacy_identity(script):
    if script.get("artifact_id") or script.get("content_digest") or script.get("run_id"):
        return []
    return [_defect("LEGACY_UNPROVEN", "artifact_id",
                    "legacy claim without artifact identity; treated as new authoring")]


def _line_words(scene):
    total = 0
    for field in ("spoken_dialogue", "sung_lyrics"):
        for line in scene.get(field) or []:
            if isinstance(line, dict):
                total += C._words(line.get("text"))
    return total


def _tokens(text):
    if not isinstance(text, str):
        return []
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    return [t for t in cleaned.split() if t]


def is_keyword_only(text):
    """True for a bare keyword list: too short, or no clause structure at all."""
    words = _tokens(text)
    if len(words) < MIN_CLAIM_WORDS:
        return True
    return not any(word in _FUNCTION_WORDS for word in words)


def _claim_defects(value, field, min_words, code="KEYWORD_ONLY_CLAIM"):
    """A quality claim must state something, not name it."""
    if not isinstance(value, str):
        return [_defect(code, field, "claim must be written text")]
    if C._words(value) < min_words:
        return [_defect(code, field, "claim is too short to state a job")]
    if is_keyword_only(value):
        return [_defect(code, field, "keyword list, not a stated claim")]
    return []


def _sound_cue_defects(scene):
    defects = []
    for entry in scene.get("sound_music_cues") or []:
        if not isinstance(entry, str) or not entry.strip():
            defects.append(_defect("KEYWORD_ONLY_CLAIM", "sound_music_cues",
                                   "cue must be written text"))
        else:
            defects.extend(_claim_defects(entry, "sound_music_cues", MIN_CLAIM_WORDS))
    return defects


def _emotion_change_defects(scene):
    """A scene must move its performers; identical before/after is no turn."""
    before = scene.get("emotion_before")
    after = scene.get("emotion_after")
    if not isinstance(before, str) or not isinstance(after, str):
        return []
    if " ".join(_tokens(before)) == " ".join(_tokens(after)):
        return [_defect("EMOTION_STAGNANT", "emotion_after",
                        "emotion_before and emotion_after name no change")]
    return []


def _context_defects(world, cast_manifest):
    defects = []
    if world is None:
        defects.append(_defect("WORLD_REQUIRED", "world",
                               "episode world must be supplied for new authoring"))
    if cast_manifest is None:
        defects.append(_defect("CAST_REQUIRED", "cast_manifest",
                               "cast manifest must be supplied for new authoring"))
    return defects


def _geography_defects(scene, world):
    """location_id must exist in the supplied world and world_revision be current."""
    defects = []
    known = C.world_location_ids(world)
    location = scene.get("location_id")
    if not known or location not in known:
        defects.append(_defect("LOCATION_UNKNOWN", "location_id",
                               {"scene_id": scene.get("scene_id"), "location_id": location}))
    revision = scene.get("world_revision")
    if revision is None:
        defects.append(_defect("WORLD_REVISION_MISSING", "world_revision",
                               scene.get("scene_id")))
    elif revision != (world or {}).get("revision"):
        defects.append(_defect("WORLD_REVISION_STALE", "world_revision",
                               {"scene_id": scene.get("scene_id"),
                                "scene": revision, "world": (world or {}).get("revision")}))
    return defects


def _performer_defects(scenes, cast_manifest):
    """Every performer named anywhere must be declared in the cast manifest."""
    declared = {entry.get("character_id") for entry in
                (cast_manifest or {}).get("cast") or [] if isinstance(entry, dict)}
    defects = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        sid = scene.get("scene_id")
        named = set(scene.get("cast_ids") or [])
        for field in ("spoken_dialogue", "sung_lyrics"):
            for line in scene.get(field) or []:
                if isinstance(line, dict):
                    named.add(line.get("character_id"))
        for cid in sorted(n for n in named if n):
            if cid not in declared:
                defects.append(_defect("PERFORMER_UNDECLARED", "cast_ids",
                                       {"scene_id": sid, "character_id": cid}))
    return defects


def _is_placeholder(scene):
    """A one-line placeholder scene: unstructured, or a single stub line."""
    if isinstance(scene, str):
        return True
    if not isinstance(scene, dict):
        return False
    if scene.get("silent_scene"):
        return False
    texts = []
    for field in ("spoken_dialogue", "sung_lyrics"):
        for line in scene.get(field) or []:
            if isinstance(line, dict):
                texts.append(str(line.get("text") or "").strip().lower())
    real = [t for t in texts if t and t not in PLACEHOLDER_TEXT]
    if not real:
        return True
    if len(real) < MIN_SCENE_LINES or _line_words(scene) < MIN_SCENE_LINE_WORDS:
        return True
    return any(t in PLACEHOLDER_TEXT for t in texts)


def _lip_sync_defects(scene):
    value = scene.get("visible_lip_sync")
    if not isinstance(value, dict):
        return [_defect("LIP_SYNC_DESIGNATION", "visible_lip_sync", "explicit designation required")]
    defects = []
    intervals = value.get("intervals")
    if not isinstance(intervals, list):
        defects.append(_defect("LIP_SYNC_DESIGNATION", "visible_lip_sync.intervals",
                               "proposed or actual intervals required"))
    else:
        speaks = not scene.get("silent_scene") and _line_words(scene) > 0
        if speaks and not intervals:
            defects.append(_defect("LIP_SYNC_EMPTY_CLAIM", "visible_lip_sync.intervals",
                                   "lines are performed on screen; declare real intervals"))
        duration = scene.get("duration_seconds")
        for interval in intervals:
            if not isinstance(interval, (list, tuple)) or len(interval) != 2 or \
                    not all(isinstance(n, (int, float)) and not isinstance(n, bool)
                            for n in interval):
                defects.append(_defect("LIP_SYNC_INTERVAL", "visible_lip_sync.intervals",
                                       "interval is not a numeric start/end pair"))
                continue
            start, end = interval
            if start < 0 or end <= start:
                defects.append(_defect("LIP_SYNC_INTERVAL", "visible_lip_sync.intervals",
                                       "empty or negative interval"))
            elif isinstance(duration, (int, float)) and end > duration:
                defects.append(_defect("LIP_SYNC_INTERVAL", "visible_lip_sync.intervals",
                                       "interval exceeds declared duration"))
    performer = value.get("performer")
    if performer is not None and performer not in (scene.get("cast_ids") or []):
        defects.append(_defect("LIP_SYNC_PERFORMER", "visible_lip_sync.performer",
                               "performer is not in cast_ids"))
    return defects


def validate_script(script, origin=ORIGIN_NEW, world=None, cast_manifest=None):
    """Validate one script revision.

    Returns a verdict dict. `ok` is True when the revision is acceptable for
    the requested origin. Legacy revisions are readable but carry
    `compatibility_limited: True`, the unresolved rich fields and the reason,
    and are never regenerated (`regenerate` is always False).
    """
    verdict = {
        "ok": False,
        "origin": origin,
        "legacy": False,
        "compatibility_limited": False,
        "unresolved": [],
        "defects": [],
        "regenerate": False,
        "scene_count": 0,
    }
    before = copy.deepcopy(script)

    if not isinstance(script, dict):
        verdict["defects"] = [_defect("NOT_AN_OBJECT", "script")]
        return verdict

    legacy = is_legacy(script)
    verdict["legacy"] = legacy

    if legacy:
        if origin != ORIGIN_LEGACY:
            verdict["defects"] = [_defect(
                "LEGACY_NOT_NEW_AUTHORING", "script",
                "a pre-contract record cannot satisfy new generation")]
            return verdict
        defects = _legacy_identity(script) + _script_defects(script)
        scene_list = script.get("scenes") or []
        unresolved = set()
        for scene in scene_list:
            if not isinstance(scene, dict):
                unresolved.update(_RICH_FIELDS)
                continue
            for field in _RICH_FIELDS:
                if C._blank(scene.get(field)):
                    unresolved.add(field)
        verdict["scene_count"] = len(scene_list)
        verdict["unresolved"] = sorted(unresolved)
        verdict["defects"] = defects
        verdict["ok"] = not defects
        verdict["compatibility_limited"] = not defects
        assert json.dumps(script, sort_keys=True) == json.dumps(before, sort_keys=True)
        return verdict

    defects = _script_defects(script) + _context_defects(world, cast_manifest)
    scenes = script.get("scenes") or []
    verdict["scene_count"] = len(scenes) if isinstance(scenes, list) else 0
    seen = set()
    previous = None
    for scene in scenes if isinstance(scenes, list) else []:
        sid = scene.get("scene_id") if isinstance(scene, dict) else None
        if _is_placeholder(scene):
            defects.append(_defect("PLACEHOLDER_SCENE", "scenes", sid or "unstructured scene"))
            continue
        if sid in seen:
            defects.append(_defect("DUPLICATE_SCENE_ID", "scene_id", sid))
        seen.add(sid)
        for item in C.validate_scene(scene, world=world):
            defects.append(_defect("SCENE_SCHEMA", item.get("field"), item))
        defects.extend(_lip_sync_defects(scene))
        defects.extend(_emotion_change_defects(scene))
        defects.extend(_sound_cue_defects(scene))
        for field, min_words in _CLAIM_FIELDS:
            defects.extend(_claim_defects(scene.get(field), field, min_words))
        for field in ("framing_movement_intent", "transition"):
            defects.extend(_claim_defects(scene.get(field), field, MIN_CLAIM_WORDS))
        if world is not None:
            defects.extend(_geography_defects(scene, world))
        predecessor = scene.get("causal_predecessor")
        if predecessor is not None and previous is not None and predecessor != previous:
            defects.append(_defect("CAUSAL_CHAIN", "causal_predecessor",
                                   {"scene_id": sid, "expected": previous,
                                    "got": predecessor}))
        previous = sid
    if cast_manifest is not None:
        for item in C.validate_cast_manifest(cast_manifest, scenes):
            defects.append(_defect("CAST", item.get("field"), item))
        defects.extend(_performer_defects(scenes, cast_manifest))

    verdict["defects"] = defects
    verdict["ok"] = not defects and verdict["scene_count"] > 0
    assert json.dumps(script, sort_keys=True) == json.dumps(before, sort_keys=True)
    return verdict


def assert_new_generation(script, **kwargs):
    """Raise ContractError unless `script` is acceptable new authoring."""
    verdict = validate_script(script, origin=ORIGIN_NEW, **kwargs)
    if not verdict["ok"]:
        raise C.ContractError("SCRIPT_INVALID", "script rejected for new generation", verdict)
    return verdict
