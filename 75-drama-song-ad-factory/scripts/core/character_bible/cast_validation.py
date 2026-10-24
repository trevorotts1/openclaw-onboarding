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
  them. An absent cast field fails closed;
* a crowd referenced by a scene must list that scene in its own ``scene_ids``:
  existence is not permission;
* every substantive cast and crowd field is judged by TYPE AND CONTENT, never
  by presence -- a boolean, a number, ``""`` and a one-character token fail;
* there is exactly ONE content predicate (``_token_ok`` / ``_real_text``) and
  every string-content judgement is routed through it. Length is not content:
  "zzz", "abc", "asdf", "x y z" and any filler token fail, and a dict is judged
  on its VALUES so ``age_range={"a": 1}`` is refused;
* closed-vocabulary fields are validated by MEMBERSHIP, never by length:
  ``episode_role`` against EPISODE_ROLE_VOCABULARY, crowd ``dialogue`` against
  CROWD_DIALOGUE_VOCABULARY.

Standard library only, no IO on import, no provider or network call.
"""

from __future__ import annotations

import re

from story_first_contracts import CAST_ENTRY_FIELDS, validate_cast_manifest

__all__ = [
    "CastValidationError",
    "CROWD_REQUIRED",
    "CROWD_DIALOGUE_VOCABULARY",
    "FILLER_TOKENS",
    "ANONYMOUS_SPEAKER_PATTERNS",
    "SPEAKER_SOURCES",
    "SPEAKER_CONTENT_KEYS",
    "EPISODE_ROLE_HEADS",
    "EPISODE_ROLE_VOCABULARY",
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

#: Closed crowd-dialogue policy. Membership, never length: an unknown token
#: ("zzz", "ALLOW ANYTHING") is refused even though it is non-empty text.
CROWD_DIALOGUE_VOCABULARY = (
    "PROHIBITED", "NONE", "SILENT", "INDIVIDUALIZED_ONLY", "ALLOWED",
)

#: The content-bearing key of each speaker-source entry, judged by the ONE
#: content predicate. ``performance_order`` entries carry references only and
#: therefore have no content surface -- that is deliberate, not an oversight.
SPEAKER_CONTENT_KEYS = {
    "spoken_dialogue": ("text",),
    "sung_lyrics": ("text",),
    "named_actions": ("action",),
    "featured_reactions": ("reaction",),
    "singled_out": ("reason", "note", "detail"),
}

#: The ONE content predicate. A token is real content only if it is alphabetic,
#: at least 3 characters, carries a vowel, is not one repeated character, is not
#: a keyboard run and is not filler. Length alone never counts: every
#: string-content surface routes through ``_token_ok`` / ``_real_text``.
FILLER_TOKENS = frozenset((
    "zzz", "abc", "aaa", "bbb", "foo", "bar", "baz", "test", "stuff",
    "things", "blah", "lorem", "ipsum", "placeholder", "tbd", "na",
    "none", "xyz",
))
_VOWELS = frozenset("aeiou")
_KEYBOARD_RUNS = ("qwertyuiop", "asdfghjkl", "zxcvbnm",
                  "qaz", "wsx", "edc", "rfv", "tgb", "yhn", "ujm")

#: Every substantive cast and crowd field is judged by TYPE AND CONTENT, never
#: by presence alone: a boolean, a number, ``""`` and a one-character token are
#: all refused even though each is "present". Extend these two sets when the
#: story vocabulary grows; never accept an unknown role word by default.
EPISODE_ROLE_HEADS = frozenset((
    "lead", "colead", "protagonist", "deuteragonist", "antagonist", "supporting",
    "secondary", "narrator", "mentor", "foil", "cameo", "guest", "extra",
    "background", "ensemble", "chorus", "catalyst", "bystander", "observer",
    "villain", "hero", "antihero", "victim", "survivor", "detective", "rival",
    "partner", "friend", "ally", "confidant", "opponent", "witness", "agent",
    "parent", "sibling", "child", "adult", "elder", "stranger", "worker",
    "customer", "boss", "manager", "clerk", "teacher", "student", "coach",
    "guide", "singer", "musician", "reporter", "lawyer", "doctor", "nurse",
    "driver", "captain", "officer", "soldier", "spy", "mechanic", "barista",
    "waiter", "waitress", "baker", "vendor", "neighbor", "colleague",
    "classmate", "teammate", "roommate", "passenger", "crew", "staff",
    "resident", "citizen", "villager", "tourist", "informant", "guard",
))
EPISODE_ROLE_VOCABULARY = EPISODE_ROLE_HEADS | frozenset((
    "co", "best", "former", "young", "old", "new", "local", "comic", "relief",
    "love", "interest", "deputy", "chief", "senior", "junior", "assistant",
    "family", "mother", "father", "sister", "brother", "daughter", "son",
    "wife", "husband", "grandmother", "grandfather", "uncle", "aunt",
    "cousin", "fiance", "widow", "widower", "orphan", "twin",
))


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


def _is_anonymous(value):
    if not _text(value):
        return False
    lowered = " ".join(value.strip().lower().split())
    return any(lowered == p or lowered.startswith(p + " ") for p in ANONYMOUS_SPEAKER_PATTERNS)


def _token_ok(token):
    """THE content predicate. One token is real content only if it passes all of:
    alphabetic, >= 3 characters, has a vowel, not one repeated character, not a
    keyboard run, not filler. This is the only test of "does this say something".
    """
    if not isinstance(token, str):
        return False
    t = token.strip().lower()
    if len(t) < 3 or not t.isalpha():
        return False
    if not (_VOWELS & set(t)) or len(set(t)) == 1:
        return False
    if t in FILLER_TOKENS:
        return False
    for run in _KEYBOARD_RUNS:
        if t in run or t in run[::-1]:
            return False
    return True


def _tokens(value):
    return re.findall(r"[A-Za-z]+", value) if isinstance(value, str) else []


def _pure_filler(value):
    """A single filler-shaped token: filler set, one repeated character, a
    keyboard run or a stub under 3 characters. Never real content in a list."""
    if not _text(value):
        return True
    words = _tokens(value)
    if len(words) != 1:
        return False
    t = words[0].lower()
    return not _token_ok(t)


def _real_text(value):
    """Real content: text that says something. Booleans, numbers, "x", "zzz",
    "abc" and "x y z" all fail because no token in them passes ``_token_ok``."""
    return _text(value) and any(_token_ok(t) for t in _tokens(value))


def _episode_role_ok(value):
    """A role is a word from the story vocabulary, not free filler."""
    if not _real_text(value):
        return False
    words = re.findall(r"[a-z]+", value.lower())
    return bool(words) and all(w in EPISODE_ROLE_VOCABULARY for w in words) \
        and any(w in EPISODE_ROLE_HEADS for w in words)


def _id_ok(value):
    """An identifier is opaque SHAPE, not prose.

    A coded id ("identity-digest-1", "3f2a9c") is judged on shape, because a
    digest is real without being a word. A purely alphabetic id must still look
    like a word, so it goes through the one content predicate: "bdf", "gym",
    "zzz", "asdf" are refused. Whitespace, stubs under 3 characters and bare
    filler are refused in every case.
    """
    if not _text(value):
        return False
    t = value.strip()
    if any(c.isspace() for c in t):
        return False
    if len(t) < 3 or t.lower() in FILLER_TOKENS or len(set(t.lower())) == 1:
        return False
    if t.isalpha():
        return _token_ok(t)
    return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", t) is not None


def _content_issue(value, kind):
    """The named reason ``value`` fails to be ``kind`` of real content, else None.

    Kinds: ``id`` (an identifier string), ``text`` (non-empty prose), ``text_list``
    (non-empty list of real strings), ``text_or_list``, ``prose`` (text, a list
    of real strings, or a record judged on its VALUES). Every kind routes its
    string judgements through the one predicate, ``_token_ok``. Presence never
    counts as content, and a record is never content merely for being non-empty.
    """
    if kind == "id":
        return None if _id_ok(value) else "not an id string"
    if kind == "text":
        if not _text(value):
            return "not a string"
        return None if _real_text(value) else "no real content"
    if kind == "text_list":
        if not isinstance(value, (list, tuple)):
            return "not a list"
        if not value:
            return "empty"
        # Every entry must be a string that is not bare filler, and the list as
        # a whole must carry at least one token that passes the predicate. A
        # one-item list of filler is refused by both limbs.
        if not all(isinstance(v, str) and not _pure_filler(v) for v in value):
            return "list entries must be strings with real content"
        return None if any(_real_text(v) for v in value) \
            else "list entries must be strings with real content"
    if kind == "text_or_list":
        if isinstance(value, (list, tuple)):
            return _content_issue(value, "text_list")
        return _content_issue(value, "text")
    if kind == "prose":
        if isinstance(value, dict):
            if not value:
                return "no real content"
            # Judge the VALUES, not the container: {"a": 1} is refused because
            # no value says anything, however non-empty the record looks.
            return None if any(_content_issue(v, "prose") is None
                               for v in value.values()) else "no real content"
        if isinstance(value, (list, tuple)):
            return _content_issue(value, "text_list")
        return _content_issue(value, "text")
    raise ValueError("unknown content kind: %r" % (kind,))


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
    if "crowd_group_id" in group and _blank(gid):
        defects.append(_defect("crowd_groups.crowd_group_id", "empty", ref,
                               "crowd_groups.crowd_group_id: key present but empty; give the group a stable ID"))
    elif "crowd_group_id" in group:
        issue = _content_issue(gid, "id")
        if issue:
            defects.append(_defect("crowd_groups.crowd_group_id", issue, ref,
                                   "crowd_groups.crowd_group_id: a crowd group id is a non-empty string"))

    composition = group.get("composition")
    composition_ok = _content_issue(composition, "prose") is None
    if not composition_ok:
        defects.append(_defect("crowd_groups.composition",
                               "no explicit composition of the crowd", ref,
                               "crowd_groups.composition: state who the crowd is, not 'people'"))
    if "count" in group and not _positive_count(group.get("count")):
        defects.append(_defect("crowd_groups.count",
                               "not a positive count or min<=max range", ref))
    if _blank(group.get("age_range")):
        defects.append(_defect("crowd_groups.age_range", "empty", ref))
    else:
        issue = _content_issue(group.get("age_range"), "prose")
        if issue:
            defects.append(_defect("crowd_groups.age_range", issue, ref))
    roles = group.get("roles")
    if _content_issue(roles, "text_list") is not None:
        defects.append(_defect("crowd_groups.roles", "no relevant roles", ref))

    group_scenes = group.get("scene_ids")
    if not (isinstance(group_scenes, list) and group_scenes and all(_id_ok(s) for s in group_scenes)):
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
            elif _content_issue(placements.get(sid), "prose") is not None:
                defects.append(_defect("crowd_groups.location_placement",
                                       "placement is not real text", dict(ref, scene_id=sid)))

    for field in ("collective_behavior", "permitted_motion", "attention_direction",
                  "interaction_with_leads", "wardrobe_palette", "camera_limits",
                  "entry_exit_rule", "recurrence", "reference_provenance"):
        value = group.get(field)
        if _blank(value):
            defects.append(_defect("crowd_groups." + field, "not specified", ref))
            continue
        issue = _content_issue(value, "prose")
        if issue:
            defects.append(_defect("crowd_groups." + field, issue, ref))

    # A crowd may not carry dialogue unless every speaking member is individualized.
    raw_individual = group.get("individualized_member_ids")
    if raw_individual is None:
        raw_individual = group.get("singled_out_members")
    if raw_individual is None:
        individual = []
    elif isinstance(raw_individual, (list, tuple)):
        individual = list(raw_individual)
        if not individual:
            defects.append(_defect("crowd_groups.individualized_member_ids",
                                   "empty", ref,
                                   "crowd_groups.individualized_member_ids: listed but empty; "
                                   "name the members or drop the key"))
    else:
        individual = [raw_individual]
        defects.append(_defect("crowd_groups.individualized_member_ids",
                               "not a list of character ids", ref))
    dialogue = group.get("dialogue")
    dialogue_value = dialogue.strip().upper() if _text(dialogue) else None
    if _blank(dialogue):
        defects.append(_defect("crowd_groups.dialogue",
                               "dialogue rule missing (use PROHIBITED)", ref))
    elif not _text(dialogue):
        defects.append(_defect("crowd_groups.dialogue",
                               "dialogue rule is not a string", ref))
    elif dialogue_value not in CROWD_DIALOGUE_VOCABULARY:
        # Membership, not length: "zzz" and "ALLOW ANYTHING" are non-empty text
        # and are still refused because neither is a declared dialogue policy.
        defects.append(_defect("crowd_groups.dialogue",
                               "dialogue rule is not a declared dialogue policy", ref,
                               "crowd_groups.dialogue: '%s' is not a dialogue policy; use one of %s"
                               % (dialogue_value, ", ".join(CROWD_DIALOGUE_VOCABULARY))))
    elif dialogue_value not in _CROWD_DIALOGUE_PROHIBITED and not individual:
        defects.append(_defect("crowd_groups.dialogue",
                               "dialogue permits members never individualized", ref))
    for member in individual:
        if _is_anonymous(member):
            defects.append(_defect("crowd_groups.individualized_member_ids",
                                   "anonymous description where a character_id is required",
                                   dict(ref, member=member),
                                   "promote '%s' to a full identity with a stable ID" % member))
        elif _content_issue(member, "id") is not None:
            defects.append(_defect("crowd_groups.individualized_member_ids",
                                   "member is not an individual character_id", ref))
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


def _scene_defects(scene, cast_ids, crowd_ids, crowd_scenes=None):
    defects = []
    sid = scene.get("scene_id") if isinstance(scene, dict) else None
    if not isinstance(scene, dict):
        return [_defect("scene_plan", "scene not an object")]
    if _blank(sid):
        defects.append(_defect("scene.scene_id", "empty",
                               {"scene_id": sid},
                               "scene: scene_id must be a non-empty string"))
    elif _content_issue(sid, "id") is not None:
        defects.append(_defect("scene.scene_id", "not an id string",
                               {"scene_id": sid},
                               "scene: scene_id must be a real identifier, not filler"))
    # The scene cast field fails closed: absent, empty and malformed are each
    # refused by name. A scene that names real people can never hide behind an
    # omitted cast list.
    if "cast_ids" not in scene:
        defects.append(_defect("scene.cast_ids", "missing",
                               {"scene_id": sid},
                               "scene %s: cast field absent; declare cast_ids explicitly" % sid))
        scene_cast = []
    else:
        scene_cast = scene.get("cast_ids")
        if _blank(scene_cast):
            defects.append(_defect("scene.cast_ids", "empty",
                                   {"scene_id": sid},
                                   "scene %s: cast field present but empty; list the characters on camera" % sid))
            scene_cast = []
        elif not isinstance(scene_cast, list):
            defects.append(_defect("scene.cast_ids", "not a list",
                                   {"scene_id": sid},
                                   "scene %s: cast field must be a list of character_ids" % sid))
            scene_cast = []
    scene_cast_set = {c for c in scene_cast if _id_ok(c)}

    for cid in scene_cast:
        if _blank(cid):
            defects.append(_defect("scene.cast_ids", "cast id empty",
                                   {"scene_id": sid, "character_id": cid},
                                   "scene %s: cast_ids entry is empty; each entry is a declared character_id" % sid))
        elif not _id_ok(cid) or cid not in cast_ids:
            defects.append(_defect("scene.cast_ids", "cast id not declared in manifest",
                                   {"scene_id": sid, "character_id": cid}))

    crowd_refs = scene.get("crowd_group_ids") or []
    if not isinstance(crowd_refs, (list, tuple)):
        defects.append(_defect("scene.crowd_group_ids", "not a list",
                               {"scene_id": sid},
                               "scene %s: crowd_group_ids must be a list of crowd_group_id" % sid))
        crowd_refs = []
    for cgid in crowd_refs:
        ref = {"scene_id": sid, "crowd_group_id": cgid}
        if not _id_ok(cgid):
            defects.append(_defect("scene.crowd_group_ids", "crowd group id is not text", ref))
        elif cgid not in crowd_ids:
            defects.append(_defect("scene.crowd_group_ids", "undefined crowd group", ref))
        elif crowd_scenes is not None:
            # Existence is not permission: the group's own record must allow
            # THIS scene, or the reference is refused even though the group exists.
            allowed = crowd_scenes.get(cgid)
            if allowed is None:
                defects.append(_defect("scene.crowd_group_ids",
                                       "crowd group membership unprovable", ref,
                                       "scene %s: crowd group %s has no usable scene_ids; "
                                       "membership cannot be proven" % (sid, cgid)))
            elif sid not in allowed:
                defects.append(_defect("scene.crowd_group_ids",
                                       "crowd group not permitted in this scene", ref,
                                       "scene %s: crowd group %s allows only %s; a crowd may not sit "
                                       "in a scene its own record forbids" % (sid, cgid, sorted(allowed))))

    # The words on screen are content too: a line, an action or a reaction whose
    # payload is filler is refused on the same predicate as everything else.
    for field, keys in SPEAKER_CONTENT_KEYS.items():
        for index, entry in enumerate(scene.get(field) or []):
            if not isinstance(entry, dict):
                continue
            for key in keys:
                if key not in entry:
                    continue
                if _blank(entry[key]):
                    defects.append(_defect("scene." + field, "empty " + key,
                                           {"scene_id": sid, "line_id": entry.get("line_id")},
                                           "scene %s: %s has no %s; write the words or drop the entry"
                                           % (sid, field, key)))
                elif _content_issue(entry[key], "prose") is not None:
                    defects.append(_defect("scene." + field, "no real content in " + key,
                                           {"scene_id": sid, "line_id": entry.get("line_id"),
                                            "index": index},
                                           "scene %s: %s %s is filler, not content" % (sid, field, key)))

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

    try:
        defects = list(validate_cast_manifest(manifest, scenes))
    except TypeError:
        # The S75-T03 envelope hashes character_id, so a list or record there
        # raises instead of reporting. A bad id is a defect, never a crash.
        defects = [_defect("cast.character_id", "not a usable id", {"character_id": None},
                           "cast entry: character_id must be a plain string id; "
                           "a list or record is refused, not coerced")]
    # The S75-T03 envelope reports field/issue; this packet adds one message.
    for defect in defects:
        defect.setdefault("message", "%s: %s" % (defect.get("field"), defect.get("issue")))
    cast = manifest.get("cast")
    entries = [e for e in cast if isinstance(e, dict)] if isinstance(cast, list) else []
    # Absent keys are already refused by the S75-T03 envelope ("missing"); a key
    # that is present but null, empty text or an empty list is refused here.
    for entry in entries:
        cid = entry.get("character_id")
        ref = {"character_id": cid if _text(cid) else None}
        for field in CAST_ENTRY_FIELDS:
            if field not in entry:
                continue
            value = entry[field]
            if _blank(value):
                defects.append(_defect("cast." + field, "empty", ref,
                                       "cast entry %s: '%s' is present but empty; write the value or drop the member"
                                       % (ref["character_id"], field)))
                continue
            if field in ("character_id", "identity_digest"):
                issue = _content_issue(value, "id")
                if issue:
                    defects.append(_defect("cast." + field, "not text", ref,
                                           "cast entry: '%s' must be a string" % field))
            elif field == "episode_role":
                # By type AND content: 0 and False are refused as types, and a
                # free word like "wizard banana" is refused as content.
                if not _text(value):
                    defects.append(_defect("cast.episode_role", "not a string", ref,
                                           "cast entry %s: episode_role must be a string role word"
                                           % ref["character_id"]))
                elif not _episode_role_ok(value):
                    defects.append(_defect("cast.episode_role", "not in the episode role vocabulary", ref,
                                           "cast entry %s: '%s' is not an episode role; use a role word "
                                           "(lead, supporting partner, antagonist, ...)"
                                           % (ref["character_id"], value)))
            elif field == "immediate_story_function":
                if not _text(value):
                    defects.append(_defect("cast.immediate_story_function", "not a string", ref,
                                           "cast entry %s: immediate_story_function must be a string, "
                                           "never a boolean" % ref["character_id"]))
                elif _content_issue(value, "text") is not None:
                    defects.append(_defect("cast.immediate_story_function", "no real content", ref,
                                           "cast entry %s: immediate_story_function must say what the "
                                           "character does in this episode" % ref["character_id"]))
            elif field == "choice_or_consequence":
                issue = _content_issue(value, "text_or_list")
                if issue:
                    defects.append(_defect("cast.choice_or_consequence", issue, ref,
                                           "cast entry %s: choice_or_consequence must be a string or a "
                                           "list of strings with real content" % ref["character_id"]))
            elif field == "scene_ids" and not (isinstance(value, list) and value
                                               and all(_id_ok(s) for s in value)):
                defects.append(_defect("cast.scene_ids", "not a list of scene ids", ref,
                                       "cast entry %s: scene_ids must be a non-empty list of scene ids" % ref["character_id"]))
            elif field == "identity_revision":
                is_int = isinstance(value, int) and not isinstance(value, bool)
                # A revision record is judged on its VALUES: {"a": 1} is refused.
                is_record = isinstance(value, dict) and _content_issue(value, "prose") is None
                if not (is_int or is_record):
                    defects.append(_defect("cast.identity_revision", "not a revision", ref,
                                           "cast entry %s: identity_revision must be an integer or a revision record" % ref["character_id"]))
    cast_ids = {e.get("character_id") for e in entries if _id_ok(e.get("character_id"))}
    scene_ids = {s.get("scene_id") for s in scenes
                 if isinstance(s, dict) and _text(s.get("scene_id"))}

    for entry in entries:
        listed = entry.get("scene_ids")
        for sid in (listed if isinstance(listed, (list, tuple)) else []):
            if not _id_ok(sid):
                defects.append(_defect("cast.scene_ids", "not a scene id",
                                       {"character_id": entry.get("character_id"),
                                        "scene_id": sid if isinstance(sid, str) else None}))
            elif scene_ids and sid not in scene_ids:
                defects.append(_defect("cast.scene_ids", "undefined scene",
                                       {"character_id": entry.get("character_id"),
                                        "scene_id": sid}))

    groups = manifest.get("crowd_groups") or []
    if not isinstance(groups, list):
        defects.append(_defect("crowd_groups", "not a list"))
        groups = []
    crowd_ids = set()
    crowd_scenes = {}
    for group in groups:
        gid = group.get("crowd_group_id") if isinstance(group, dict) else None
        gid = gid if _id_ok(gid) else None
        if gid and gid in crowd_ids:
            defects.append(_defect("crowd_groups", "duplicate crowd_group_id", gid))
        if gid:
            crowd_ids.add(gid)
            listed = group.get("scene_ids") if isinstance(group, dict) else None
            crowd_scenes[gid] = set(listed) if (isinstance(listed, (list, tuple))
                                                and listed and all(_id_ok(s) for s in listed)) else None
        defects.extend(validate_crowd_group(group, scene_ids or None, cast_ids))

    for scene in scenes:
        defects.extend(_scene_defects(scene, cast_ids, crowd_ids, crowd_scenes))

    seen = set()
    unique = []
    for defect in defects:
        key = (defect["field"], defect["issue"],
               repr(sorted((str(k), repr(v)) for k, v in (defect.get("ref") or {}).items())))
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
