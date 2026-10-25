#!/usr/bin/env python3
"""production.py -- S75-T26 late production continuity. Stdlib only.

Contract sources (read-only):
  * WORLD-AND-CONTINUITY.md "Late production-continuity schema" and
    "Change impact and preservation".
  * SPEC.md "Safe change propagation" gate.

Two things are deliberately kept apart:

  * REUSABLE IDENTITY -- the stable person record (character_id, facial
    structure, eyes, hair, build, expression range, prohibited drift). It is
    authored once, reused across episodes, and a world change must never
    rewrite it.
  * LATE PRODUCTION CONTINUITY -- approved reference assets, episode outfit,
    blocking, props, audio timecodes. This is authored after the song and it
    is the half a world change legitimately rewrites.

Each late record points at its identity by digest (``identity_ref``); it holds
no copy of the identity, so a world change physically cannot reach it.

Change propagation walks exact ``depends_on`` edges only. A world change marks
the world, the continuity built on it, the keyframes built on those and the
approvals that actually bind those revisions. Unrelated scenes, other
characters and approvals that never bound the changed revision keep standing.

No provider call, no spend, no media file, no client write. A stale paid
artifact is preserved with its provider job id as historical evidence; this
module never queues it for regeneration.

Run: python3 scripts/core/continuity/production.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

_CORE = str(pathlib.Path(__file__).resolve().parents[1])
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from storyboard import timing as _timing      # noqa: E402  (core/ on sys.path)

TOOL_NAME = "production_continuity"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.production-continuity/v1"
SOURCE = ("WORLD-AND-CONTINUITY.md late production continuity + change impact; "
          "SPEC.md safe change propagation")

FIXTURE_RELATIVE = ("tests", "fixtures", "timed_continuity.json")

#: Reusable identity: stable across episodes and across world changes.
IDENTITY_FIELDS = (
    "character_id",
    "age_band",
    "skin_tone_complexion",
    "facial_structure",
    "eyes",
    "nose",
    "mouth",
    "hair",
    "body_build",
    "distinguishing_features",
    "wardrobe_rules",
    "expression_range",
    "prohibited_drift",
)

#: World-bound fields a world change may legally carry.
WORLD_FIELDS = (
    "world_id",
    "revision",
    "location",
    "layout",
    "light",
    "props",
    "social_rule",
    "sound",
    "wardrobe_intent",
)

#: Late continuity a world or music change may legally rewrite.
LATE_CHANGE_FIELDS = ("world", "wardrobe", "blocking", "props",
                      "reference_assets")

#: Artifact kinds that carry provider cost. Regenerating one of these is a
#: paid act, so a stale one is preserved rather than queued.
MEDIA_KINDS = ("audio", "keyframe", "video", "final_delivery")


class ContinuityError(ValueError):
    """Machine-readable refusal. A caller bug is BAD_INPUT, never a verdict."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ContinuityError("BAD_INPUT",
                              "%s must be a non-empty string, got %r"
                              % (name, value))
    return value.strip()


def _record(value, name):
    if not isinstance(value, dict):
        raise ContinuityError("BAD_INPUT",
                              "%s must be a record, got %s"
                              % (name, type(value).__name__))
    return value


def _canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"))


def _digest(obj):
    return "sha256:" + hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def identity_digest(character):
    """Digest of the REUSABLE half of a character record.

    Missing identity fields are a refusal, never a silent omission: an absent
    field must not read as "unchanged".
    """
    _record(character, "character")
    missing = [field for field in IDENTITY_FIELDS if field not in character]
    if missing:
        raise ContinuityError("BAD_IDENTITY",
                              "missing identity fields: %s"
                              % (", ".join(missing),))
    projection = {field: character[field] for field in IDENTITY_FIELDS}
    return _digest(projection)


def build_continuity(timed_storyboard, inputs):
    """Build ``production_continuity`` bound to the timed storyboard.

    Every scene binds the exact music / script / lyric revision, the cast
    identity revisions, the world revision and the selected visual identity.
    """
    _record(timed_storyboard, "timed_storyboard")
    _record(inputs, "inputs")
    for key in ("cast", "world", "script_revision", "lyrics_revision",
                "visual_identity", "scenes"):
        if key not in inputs:
            raise ContinuityError("BAD_INPUT",
                                  "inputs.%s is required" % (key,))

    cast = {}
    for character in inputs["cast"]:
        _record(character, "cast member")
        character_id = _text(character.get("character_id"), "character_id")
        if character_id in cast:
            raise ContinuityError("DUPLICATE_CHARACTER_ID", character_id)
        cast[character_id] = identity_digest(character)

    world = _record(inputs["world"], "world")
    world_id = _text(world.get("world_id"), "world_id")
    world_revision = _text(world.get("revision"), "revision")
    visual_identity = _text(inputs["visual_identity"], "visual_identity")

    timeline = {scene["scene_id"]: scene for scene in timed_storyboard["scenes"]}
    scenes = []
    for planned in inputs["scenes"]:
        _record(planned, "scene")
        scene_id = _text(planned.get("scene_id"), "scene_id")
        if scene_id not in timeline:
            raise ContinuityError("UNKNOWN_SCENE",
                                  "%r is not in the timed storyboard"
                                  % (scene_id,))
        slot = timeline[scene_id]
        realizations = []
        for realization in planned.get("characters", []):
            _record(realization, "character realization")
            character_id = _text(realization.get("character_id"),
                                 "character_id")
            if character_id not in cast:
                raise ContinuityError(
                    "UNDEFINED_CAST",
                    "scene %r features %r, which is not in the cast"
                    % (scene_id, character_id))
            realizations.append({
                "character_id": character_id,
                # reference, not a copy: a world change cannot reach identity
                "identity_ref": cast[character_id],
                "outfit": realization.get("outfit"),
                "blocking": realization.get("blocking"),
                "reference_asset_ids":
                    list(realization.get("reference_asset_ids", [])),
            })
        scenes.append({
            "scene_id": scene_id,
            "start_s": slot["start_s"],
            "end_s": slot["end_s"],
            "duration_s": slot["duration_s"],
            "characters": realizations,
            "props": list(planned.get("props", [])),
            "audio": planned.get("audio", {}),
        })

    continuity = {
        "schema_version": SCHEMA_VERSION,
        "bindings": {
            "music": {
                "track_id": timed_storyboard["track_id"],
                "revision": timed_storyboard["track_revision"],
                "duration_s": timed_storyboard["total_s"],
            },
            "script_revision": _text(inputs["script_revision"],
                                     "script_revision"),
            "lyrics_revision": _text(inputs["lyrics_revision"],
                                     "lyrics_revision"),
            "world": {"world_id": world_id, "revision": world_revision},
            "cast_identity_refs": dict(sorted(cast.items())),
            "visual_identity": visual_identity,
        },
        "scenes": scenes,
    }
    continuity["digest"] = _digest(continuity["scenes"])
    return continuity


def apply_world_change(continuity, change):
    """Apply a world change to LATE continuity and leave identity untouched.

    Refuses outright if the change carries an identity field: an identity
    rewrite is not a world change and cannot ride in on one.
    """
    _record(continuity, "continuity")
    _record(change, "change")

    identity_attempts = sorted(set(change) & set(IDENTITY_FIELDS))
    if identity_attempts:
        raise ContinuityError(
            "IDENTITY_REWRITE_REFUSED",
            "world change may not rewrite reusable identity: %s"
            % (", ".join(identity_attempts),))
    unknown = sorted(set(change) - set(LATE_CHANGE_FIELDS))
    if unknown:
        raise ContinuityError("BAD_CHANGE",
                              "not a late-continuity field: %s"
                              % (", ".join(unknown),))
    if "world" not in change:
        raise ContinuityError("BAD_CHANGE", "change.world is required")

    world = _record(change["world"], "world")
    new_world = {
        "world_id": _text(world.get("world_id"), "world_id"),
        "revision": _text(world.get("revision"), "revision"),
    }
    stray = sorted(set(world) - set(WORLD_FIELDS))
    if stray:
        raise ContinuityError("IDENTITY_REWRITE_REFUSED",
                              "world record carried non-world fields: %s"
                              % (", ".join(stray),))

    previous_identities = dict(continuity["bindings"]["cast_identity_refs"])
    updated = json.loads(json.dumps(continuity))
    updated["bindings"]["world"] = new_world

    wardrobe = change.get("wardrobe") or {}
    for scene in updated["scenes"]:
        for realization in scene["characters"]:
            character_id = realization["character_id"]
            if character_id in wardrobe:
                realization["outfit"] = wardrobe[character_id]
    if "blocking" in change:
        blocking = _record(change["blocking"], "blocking")
        for scene in updated["scenes"]:
            for realization in scene["characters"]:
                key = "%s:%s" % (scene["scene_id"],
                                 realization["character_id"])
                if key in blocking:
                    realization["blocking"] = blocking[key]

    if updated["bindings"]["cast_identity_refs"] != previous_identities:
        raise ContinuityError(
            "IDENTITY_REWRITE_REFUSED",
            "world change altered reusable identity digests")
    for scene in updated["scenes"]:
        for realization in scene["characters"]:
            if realization["identity_ref"] != \
                    previous_identities[realization["character_id"]]:
                raise ContinuityError(
                    "IDENTITY_REWRITE_REFUSED",
                    "%s identity_ref changed in scene %r"
                    % (realization["character_id"], scene["scene_id"]))

    updated["digest"] = _digest(updated["scenes"])
    return {
        "continuity": updated,
        "previous": continuity,
        "identity_digests": dict(sorted(previous_identities.items())),
        "identity_rewrites": [],
        "identity_preserved": True,
        "changed_world": new_world,
    }


def _node(node):
    _record(node, "node")
    artifact_id = _text(node.get("artifact_id"), "artifact_id")
    return {
        "artifact_id": artifact_id,
        "kind": _text(node.get("kind"), "kind"),
        "revision": node.get("revision"),
        "depends_on": [_text(dependency, "depends_on entry")
                       for dependency in node.get("depends_on", [])],
        "paid": bool(node.get("paid", False)),
        "provider_job_id": node.get("provider_job_id"),
    }


def impact(nodes, changed_ids):
    """Transitive closure of a change over EXACT dependency edges.

    Only real dependants go stale. Paid artifacts that do go stale are routed
    to ``preserved_paid_assets`` with their provider job id; they never appear
    in ``safe_to_regenerate``.
    """
    if not isinstance(nodes, list) or not nodes:
        raise ContinuityError("BAD_GRAPH", "nodes must be a non-empty list")
    by_id = {}
    for raw in nodes:
        node = _node(raw)
        if node["artifact_id"] in by_id:
            raise ContinuityError("DUPLICATE_ARTIFACT_ID", node["artifact_id"])
        by_id[node["artifact_id"]] = node

    unknown = sorted(set(changed_ids) - set(by_id))
    if unknown:
        raise ContinuityError("UNKNOWN_ARTIFACT",
                              "changed ids not in graph: %s"
                              % (", ".join(unknown),))

    stale = set(changed_ids)
    growing = True
    while growing:                       # forward closure, real edges only
        growing = False
        for artifact_id, node in by_id.items():
            if artifact_id in stale:
                continue
            if any(dependency in stale for dependency in node["depends_on"]):
                stale.add(artifact_id)
                growing = True

    cause = {}
    for artifact_id in sorted(stale):
        cause[artifact_id] = sorted(
            dependency for dependency in by_id[artifact_id]["depends_on"]
            if dependency in stale)

    stale_outputs = sorted(
        artifact_id for artifact_id in stale
        if by_id[artifact_id]["kind"] != "approval")
    stale_approvals = sorted(
        artifact_id for artifact_id in stale
        if by_id[artifact_id]["kind"] == "approval")
    preserved_paid = [
        {"artifact_id": artifact_id,
         "provider_job_id": by_id[artifact_id]["provider_job_id"],
         "revision": by_id[artifact_id]["revision"]}
        for artifact_id in sorted(stale)
        if by_id[artifact_id]["paid"]]
    safe_to_regenerate = sorted(
        artifact_id for artifact_id in stale
        if by_id[artifact_id]["kind"] in MEDIA_KINDS
        and not by_id[artifact_id]["paid"])

    return {
        "changed": sorted(stale),
        "stale_outputs": stale_outputs,
        "stale_approvals": stale_approvals,
        "unaffected": sorted(set(by_id) - stale),
        "preserved_paid_assets": preserved_paid,
        "safe_to_regenerate": safe_to_regenerate,
        "cause": cause,
        "deleted": [],               # retain stale work as historical evidence
    }


def no_paid_regeneration(result):
    """True when a change plan queues no paid asset for regeneration."""
    paid_ids = {entry["artifact_id"]
                for entry in result.get("preserved_paid_assets", [])}
    return not (paid_ids & set(result.get("safe_to_regenerate", [])))


# -- self-check --------------------------------------------------------------

def _fixture():
    path = pathlib.Path(__file__).resolve()
    for parent in (path.parent, path.parents[1], path.parents[2],
                   path.parents[3]):
        candidate = parent.joinpath(*FIXTURE_RELATIVE)
        if candidate.exists():
            return json.loads(candidate.read_text())
    raise ContinuityError("NO_FIXTURE",
                          "tests/fixtures/timed_continuity.json absent")


def _timed(fixture, track_name="intended", anchors=None):
    return _timing.time_scenes(fixture["scene_plan"],
                               fixture["track"][track_name],
                               anchors=anchors)


def selfcheck():
    fixture = _fixture()
    timed = _timed(fixture, anchors=fixture["anchors"])
    built = build_continuity(timed, fixture["continuity_inputs"])

    # clause 2: a world change rewrites late continuity, not reusable identity
    before_identities = dict(built["bindings"]["cast_identity_refs"])
    change = fixture["world_change"]
    moved = apply_world_change(built, change)
    assert moved["identity_preserved"] is True
    assert moved["identity_rewrites"] == []
    after = moved["continuity"]
    assert after["bindings"]["cast_identity_refs"] == before_identities
    assert after["bindings"]["world"]["revision"] != \
        built["bindings"]["world"]["revision"]
    for scene_before, scene_after in zip(built["scenes"], after["scenes"]):
        for real_before, real_after in zip(scene_before["characters"],
                                           scene_after["characters"]):
            assert real_before["identity_ref"] == real_after["identity_ref"]
    for attempt in fixture["identity_rewrite_attempts"]:
        try:
            apply_world_change(built, attempt)
        except ContinuityError as exc:
            assert exc.code == "IDENTITY_REWRITE_REFUSED", exc.code
        else:
            raise AssertionError("identity rewrite accepted: %r" % (attempt,))

    # clause 3: only exact dependants go stale
    world_plan = impact(fixture["graph"]["nodes"],
                        fixture["graph"]["world_change_ids"])
    assert world_plan["stale_outputs"] == \
        fixture["graph"]["expected_world_stale_outputs"]
    assert world_plan["stale_approvals"] == \
        fixture["graph"]["expected_world_stale_approvals"]
    assert world_plan["unaffected"] == \
        fixture["graph"]["expected_world_unaffected"]
    assert world_plan["cause"]["production_continuity"] == \
        fixture["graph"]["expected_production_continuity_cause"]
    assert "cast_identity_r1" in world_plan["unaffected"]
    assert "music_audio" in world_plan["unaffected"]

    music_plan = impact(fixture["graph"]["nodes"],
                        fixture["graph"]["music_change_ids"])
    assert music_plan["stale_approvals"] == \
        fixture["graph"]["expected_music_stale_approvals"]
    assert music_plan["unaffected"] == \
        fixture["graph"]["expected_music_unaffected"]

    # clause 4: no paid asset is ever queued for regeneration
    for plan in (world_plan, music_plan):
        assert no_paid_regeneration(plan) is True
        assert plan["deleted"] == []
        paid_ids = {entry["artifact_id"]
                    for entry in plan["preserved_paid_assets"]}
        assert not (paid_ids & set(plan["safe_to_regenerate"]))
    assert world_plan["safe_to_regenerate"] == \
        fixture["graph"]["expected_world_safe_to_regenerate"]
    assert music_plan["safe_to_regenerate"] == \
        fixture["graph"]["expected_music_safe_to_regenerate"]
    assert [entry["artifact_id"]
            for entry in world_plan["preserved_paid_assets"]] == \
        fixture["graph"]["expected_world_preserved_paid"]
    assert [entry["artifact_id"]
            for entry in music_plan["preserved_paid_assets"]] == \
        fixture["graph"]["expected_music_preserved_paid"]
    for entry in music_plan["preserved_paid_assets"]:
        if entry["artifact_id"] == "music_audio":
            assert entry["provider_job_id"] == "suno_job_88117"

    print("continuity.production selfcheck OK -- %d scenes, %d identities"
          % (len(after["scenes"]), len(before_identities)))
    return 0


if __name__ == "__main__":
    raise SystemExit(selfcheck())
