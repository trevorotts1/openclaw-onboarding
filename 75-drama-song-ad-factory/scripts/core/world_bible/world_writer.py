#!/usr/bin/env python3
"""world_bible.world_writer: EARLY episode-world authoring (S75-T08).

The world is authored BEFORE the script and BEFORE music. It answers where the
story can happen and under what physical and social conditions: locations,
light, palette, texture, era, sound, plus a never-list of what this world must
never contain.

It is deliberately SEPARATE from reusable character identity. ``cast_refs``
carries reference IDs only -- a character id and an identity revision -- and the
validator refuses any mutation-shaped identity field (name, background,
appearance, psychology) in that list. That separation is what lets a character
survive a change of setting: move a scene from a neighbourhood workshop to a
formal building and the same person ID is still the same person, while the
world, the scene plan, the script and the visual outputs go stale.

Validator scope: a world with NO locations or NO light doctrine is refused.

Standard library only.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys

SCHEMA_VERSION = "1.0.0"
WORLD_KIND = "episode_world"

#: Sections every authored world must carry. Missing ones are named in errors.
REQUIRED_SECTIONS = (
    "premise", "era", "locations", "light", "palette", "texture", "sound",
    "never_list", "cast_refs", "continuity",
)

#: Identity fields that belong to the CHARACTER BIBLE, never to a world record.
#: Their presence in ``cast_refs`` means the two foundations have been merged and
#: a later setting change would silently rewrite a person.
IDENTITY_FIELDS = (
    "name", "display_name", "full_name", "background", "backstory", "biography",
    "appearance", "physique", "ethnicity", "age", "personality", "psychology",
    "motivation", "want", "wound", "voice", "voice_notes", "relationships",
)

#: Outputs a setting change invalidates. Character identity is NOT in this list.
SETTING_DEPENDENTS = ("scene_plan", "script", "visual_outputs")

LOCATION_ID_RE = re.compile(r"^loc_[A-Za-z0-9][A-Za-z0-9_.-]*$")
CHARACTER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class WorldError(ValueError):
    """Raised when a world record is refused by the validator."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _nonempty(value):
    return isinstance(value, str) and value.strip() != ""


def _nonempty_list(value):
    return isinstance(value, list) and len(value) > 0


def canonical_digest(record):
    """SHA-256 over canonical JSON, excluding ``content_digest`` itself."""
    body = {k: v for k, v in record.items() if k != "content_digest"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _validate_locations(record, errors):
    locations = record.get("locations")
    if not _nonempty_list(locations):
        errors.append("world has no locations: at least one location record is required")
        return
    seen = set()
    for index, loc in enumerate(locations):
        pointer = "locations[%d]" % index
        if not isinstance(loc, dict):
            errors.append("%s must be an object" % pointer)
            continue
        loc_id = loc.get("location_id")
        if not _nonempty(loc_id):
            errors.append("%s.location_id is required" % pointer)
        elif not LOCATION_ID_RE.match(loc_id):
            errors.append("%s.location_id %r must match loc_<slug>" % (pointer, loc_id))
        elif loc_id in seen:
            errors.append("%s.location_id %r is duplicated" % (pointer, loc_id))
        else:
            seen.add(loc_id)
        if not _nonempty(loc.get("name")):
            errors.append("%s.name is required" % pointer)
        if not _nonempty(loc.get("function")):
            errors.append("%s.function is required (what the place does in the story)" % pointer)
        if not isinstance(loc.get("interior"), bool):
            errors.append("%s.interior must be true or false" % pointer)


def _validate_light(record, errors):
    light = record.get("light")
    if not isinstance(light, dict):
        errors.append("world has no light doctrine: light must be an object with sources")
        return
    sources = light.get("sources")
    if not _nonempty_list(sources):
        errors.append("world has no light doctrine: at least one motivated light source is required")
        return
    for index, src in enumerate(sources):
        pointer = "light.sources[%d]" % index
        if not isinstance(src, dict):
            errors.append("%s must be an object" % pointer)
            continue
        if not _nonempty(src.get("source")):
            errors.append("%s.source is required" % pointer)
        if not _nonempty(src.get("direction")):
            errors.append("%s.direction is required" % pointer)
    if not _nonempty(light.get("doctrine")):
        errors.append("light.doctrine is required: the rule every scene's light must obey")


def _validate_era(record, errors):
    era = record.get("era")
    if not isinstance(era, dict):
        errors.append("era must be an object with period and time_of_day")
        return
    for key in ("period", "time_of_day"):
        if not _nonempty(era.get(key)):
            errors.append("era.%s is required" % key)
    if not isinstance(era.get("time_jumps"), list):
        errors.append("era.time_jumps must be a list (empty when the story is continuous)")


def _validate_atmosphere(record, errors):
    for key in ("palette", "texture"):
        values = record.get(key)
        if not _nonempty_list(values):
            errors.append("%s must be a non-empty list" % key)
            continue
        if not all(_nonempty(v) for v in values):
            errors.append("%s entries must be non-empty strings" % key)
        elif len({v.strip().lower() for v in values}) != len(values):
            errors.append("%s repeats a value; repetition cannot stand in for the atmosphere" % key)


def _validate_sound(record, errors):
    sound = record.get("sound")
    if not isinstance(sound, dict):
        errors.append("sound must be an object with ambience")
        return
    if not _nonempty(sound.get("ambience")):
        errors.append("sound.ambience is required")
    for key in ("off_screen", "silence"):
        if key in sound and not isinstance(sound[key], list):
            errors.append("sound.%s must be a list" % key)


def _validate_never_list(record, errors):
    never = record.get("never_list")
    if not _nonempty_list(never):
        errors.append("never_list must be a non-empty list of things this world must never contain")
        return
    if not all(_nonempty(v) for v in never):
        errors.append("never_list entries must be non-empty strings")
    elif len({v.strip().lower() for v in never}) != len(never):
        errors.append("never_list repeats an entry")


def _validate_cast(record, errors):
    cast = record.get("cast_refs")
    if not isinstance(cast, list):
        errors.append("cast_refs must be a list of character reference IDs")
        return
    for index, ref in enumerate(cast):
        pointer = "cast_refs[%d]" % index
        if not isinstance(ref, dict):
            errors.append("%s must be an object" % pointer)
            continue
        cid = ref.get("character_id")
        if not _nonempty(cid) or not CHARACTER_ID_RE.match(cid):
            errors.append("%s.character_id is required" % pointer)
        if not isinstance(ref.get("identity_revision"), int) or ref["identity_revision"] < 1:
            errors.append("%s.identity_revision must be a positive integer" % pointer)
        leaked = sorted(set(ref) & set(IDENTITY_FIELDS))
        if leaked:
            errors.append(
                "%s copies reusable identity field(s) %s; a world holds reference IDs only"
                % (pointer, ", ".join(leaked))
            )


def _validate_scenes(record, errors):
    scenes = record.get("scenes")
    if scenes is None:
        return
    if not isinstance(scenes, list):
        errors.append("scenes must be a list")
        return
    defined = {
        loc.get("location_id")
        for loc in record.get("locations") or []
        if isinstance(loc, dict) and _nonempty(loc.get("location_id"))
    }
    for index, scene in enumerate(scenes):
        pointer = "scenes[%d]" % index
        if not isinstance(scene, dict):
            errors.append("%s must be an object" % pointer)
            continue
        loc_id = scene.get("location_id")
        if loc_id not in defined:
            errors.append("%s.location_id %r does not resolve to any location" % (pointer, loc_id))


def validate(record):
    """Return the list of refusal reasons. Empty list means the world is usable."""
    errors = []
    if not isinstance(record, dict):
        return ["world record must be a JSON object"]
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be %r" % SCHEMA_VERSION)
    if record.get("kind") != WORLD_KIND:
        errors.append("kind must be %r" % WORLD_KIND)
    for key in ("artifact_id", "run_id"):
        if not _nonempty(record.get(key)):
            errors.append("%s is required" % key)
    if not isinstance(record.get("revision"), int) or record["revision"] < 1:
        errors.append("revision must be a positive integer")
    for key in REQUIRED_SECTIONS:
        if key not in record:
            errors.append("required section %r is missing" % key)
    if not _nonempty(record.get("premise")):
        errors.append("premise is required")
    if record.get("fiction_classification") not in ("proposed_fiction", "sourced"):
        errors.append("fiction_classification must be 'proposed_fiction' or 'sourced'")
    if not isinstance(record.get("continuity"), dict) or not _nonempty_list(
            (record.get("continuity") or {}).get("must_persist")):
        errors.append("continuity.must_persist must list what survives between scenes")
    _validate_locations(record, errors)
    _validate_light(record, errors)
    _validate_era(record, errors)
    _validate_atmosphere(record, errors)
    _validate_sound(record, errors)
    _validate_never_list(record, errors)
    _validate_cast(record, errors)
    _validate_scenes(record, errors)
    return errors


def _seal(record):
    record = copy.deepcopy(record)
    record["content_digest"] = canonical_digest(record)
    return record


def author_world(payload, *, artifact_id, run_id, revision=1, provenance=None,
                 dependencies=None):
    """Author and validate one ``episode_world`` record.

    ``payload`` is the world body. The envelope fields are supplied here so every
    authored world carries the same identity, revision and digest discipline.
    Raises :class:`WorldError` when the validator refuses the result.
    """
    if not isinstance(payload, dict):
        raise WorldError(["world payload must be a JSON object"])
    record = copy.deepcopy(payload)
    record.update({
        "schema_version": SCHEMA_VERSION,
        "kind": WORLD_KIND,
        "artifact_id": artifact_id,
        "run_id": run_id,
        "revision": revision,
        "provenance": provenance or {},
        "dependencies": dependencies or {},
    })
    errors = validate(record)
    if errors:
        raise WorldError(errors)
    return _seal(record)


def change_setting(record, *, locations, reason, era=None):
    """Move the story to a new setting without touching reusable character identity.

    Returns a dict holding the new world revision, the character identity IDs that
    were preserved verbatim, and only the dependent outputs that went stale.
    """
    errors = validate(record)
    if errors:
        raise WorldError(errors)
    if not _nonempty(reason):
        raise WorldError(["a setting change needs a stated reason"])

    new_world = copy.deepcopy(record)
    new_world["revision"] = record["revision"] + 1
    new_world["locations"] = copy.deepcopy(locations)
    if era is not None:
        new_world["era"] = copy.deepcopy(era)
    # The scene plan depends on the setting, so it goes stale with it rather than
    # carrying location IDs that no longer resolve.
    new_world.pop("scenes", None)
    new_world["previous_revision"] = record["revision"]
    new_world["change_reason"] = reason

    errors = validate(new_world)
    if errors:
        raise WorldError(errors)
    if new_world["cast_refs"] != record["cast_refs"]:
        raise WorldError(["a setting change must not rewrite reusable character identity"])

    return {
        "world": _seal(new_world),
        "preserved_character_identity": [
            {"character_id": ref["character_id"],
             "identity_revision": ref["identity_revision"]}
            for ref in record["cast_refs"]
        ],
        "invalidated": list(SETTING_DEPENDENTS),
        "reason": reason,
    }


def _load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Author or validate an episode world (S75-T08).")
    parser.add_argument("--validate", metavar="FILE", help="validate an existing world record")
    parser.add_argument("--author", metavar="FILE", help="author a world body into a sealed record")
    parser.add_argument("--artifact-id", default="world_draft_001")
    parser.add_argument("--run-id", default="run_local_001")
    parser.add_argument("--out", metavar="FILE", help="write the sealed record here")
    args = parser.parse_args(argv)

    if not args.validate and not args.author:
        parser.error("choose --validate or --author")

    if args.validate:
        errors = validate(_load(args.validate))
        if errors:
            for line in errors:
                print("REFUSED: %s" % line, file=sys.stderr)
            return 1
        print("OK: world record is usable")
        return 0

    try:
        record = author_world(_load(args.author), artifact_id=args.artifact_id,
                              run_id=args.run_id)
    except WorldError as exc:
        for line in exc.errors:
            print("REFUSED: %s" % line, file=sys.stderr)
        return 1
    blob = json.dumps(record, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(blob + "\n")
        print("wrote %s (revision %d, digest %s)" % (args.out, record["revision"],
                                                     record["content_digest"]))
    else:
        print(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
