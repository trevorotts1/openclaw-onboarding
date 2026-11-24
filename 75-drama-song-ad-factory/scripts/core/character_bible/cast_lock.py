#!/usr/bin/env python3
"""cast_lock.py: the Cast Lock, everyone on screen is locked first (N-119, section 3C.9). Stdlib only.

The cast list comes from the Story Beats. Every person who appears is on it:
named characters, people known only by a relation, one-scene side characters,
and every crowd as a group. Everyone on the list is locked before any
storyboard picture is drawn, and code -- never a person -- attaches the locked
references to a job.

Every character has their own identity text; one character's lock is never
pasted onto another. Before the set is approved the bible is checked as a
line-up, so two cast members who would be confused are caught by name. On
every picture and clip the cast-consistency check names a stranger, a
mismatched member and a missing member.

Stdlib only, no IO, no provider call.
"""
from __future__ import annotations

SCHEMA_VERSION = "blackceo.cast-lock/v1"

CAST_NOT_IN_BIBLE = "CAST_NOT_IN_BIBLE"
CAST_REFERENCE_MISSING = "CAST_REFERENCE_MISSING"
CAST_LOOKALIKE = "CAST_LOOKALIKE"
IDENTITY_BLOCK_WRONG_CHARACTER = "IDENTITY_BLOCK_WRONG_CHARACTER"
UNLISTED_PERSON = "UNLISTED_PERSON"
CAST_MEMBER_MISSING = "CAST_MEMBER_MISSING"


def _defect(code, character_id, detail, **extra):
    out = {"code": code, "character_id": character_id, "detail": detail}
    out.update(extra)
    return out


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def cast_entries(manifest):
    if not isinstance(manifest, dict):
        return []
    return [e for e in (manifest.get("cast") or []) if isinstance(e, dict)]


def cast_ids(manifest):
    return [e.get("character_id") for e in cast_entries(manifest)
            if _text(e.get("character_id"))]


def _lock_characters(lock):
    if not isinstance(lock, dict):
        return {}
    chars = lock.get("characters")
    return chars if isinstance(chars, dict) else {}


def _lock_refs(entry):
    if not isinstance(entry, dict):
        return []
    refs = entry.get("refs")
    if refs is None:
        refs = entry.get("reference_ids")
    return refs if isinstance(refs, list) else []


def check_cast_lock(manifest, lock):
    """Every cast entry is locked, carries its own identity text and references.

    Returns {"outcome", "findings", "codes"}. A missing lock entry is
    CAST_NOT_IN_BIBLE: the run must create and lock the character before any
    shot uses them (section 3C.10).
    """
    findings = []
    chars = _lock_characters(lock)
    by_identity = {}
    by_look = {}
    for entry in cast_entries(manifest):
        cid = _text(entry.get("character_id"))
        if not cid:
            continue
        locked = chars.get(cid)
        if not isinstance(locked, dict):
            findings.append(_defect(CAST_NOT_IN_BIBLE, cid,
                                    "cast entry has no locked character-bible entry"))
            continue
        refs = _lock_refs(locked)
        if not refs or any(not isinstance(r, (str, dict)) or not r for r in refs):
            findings.append(_defect(CAST_REFERENCE_MISSING, cid,
                                    "locked entry carries no reference pictures"))
        identity = _text(locked.get("identity_block"))
        if not identity:
            findings.append(_defect(CAST_REFERENCE_MISSING, cid,
                                    "locked entry carries no identity text"))
        else:
            by_identity.setdefault(identity, []).append(cid)
        look = _text(entry.get("look_signature") or locked.get("look_signature"))
        if look:
            by_look.setdefault(look, []).append(cid)
    for identity, owners in sorted(by_identity.items()):
        if len(owners) > 1:
            findings.append(_defect(
                IDENTITY_BLOCK_WRONG_CHARACTER, owners[0],
                "one identity block is pasted onto %s" % ", ".join(sorted(owners)),
                characters=sorted(owners)))
    for look, owners in sorted(by_look.items()):
        if len(owners) > 1:
            findings.append(_defect(
                CAST_LOOKALIKE, owners[0],
                "cast members share a look signature: %s" % ", ".join(sorted(owners)),
                characters=sorted(owners)))
    return _packet(findings)


def check_cast_in_beats(beats, manifest):
    """A person a beat names with no cast entry is refused at plan time."""
    known = set(cast_ids(manifest))
    findings = []
    for beat in beats or []:
        if not isinstance(beat, dict):
            continue
        beat_id = beat.get("beat_id") or beat.get("beat_number")
        for cid in _beat_cast(beat):
            if cid not in known:
                findings.append(_defect(
                    CAST_NOT_IN_BIBLE, cid,
                    "beat %r names a person with no cast entry" % (beat_id,),
                    beat_id=beat_id))
    return _packet(findings)


def _beat_cast(beat):
    out = []
    for key in ("cast_ids", "characters", "who"):
        raw = beat.get(key)
        if isinstance(raw, list):
            for item in raw:
                cid = item.get("character_id") if isinstance(item, dict) else item
                if _text(cid):
                    out.append(cid)
    return out


def check_cast_consistency(seen_faces, cast, crowd_ids=()):
    """Any visible face that is neither cast nor its declared crowd is a stranger."""
    known = {c if isinstance(c, str) else (c or {}).get("character_id")
             for c in (cast or [])}
    known.discard(None)
    crowd = set(crowd_ids or [])
    findings = []
    for face in seen_faces or []:
        if isinstance(face, dict):
            cid = face.get("character_id") or face.get("id")
            where = face.get("shot_id")
        else:
            cid, where = face, None
        if not _text(cid):
            findings.append(_defect(UNLISTED_PERSON, None,
                                    "a visible face has no identity", shot_id=where))
        elif cid not in known and cid not in crowd:
            findings.append(_defect(UNLISTED_PERSON, cid,
                                    "person on screen is not in the cast list",
                                    shot_id=where))
    return _packet(findings)


def check_cast_members_present(required_ids, seen_faces):
    """A cast member the beat says is here but the frame never shows."""
    seen = set()
    for face in seen_faces or []:
        cid = face.get("character_id") if isinstance(face, dict) else face
        if _text(cid):
            seen.add(cid)
    findings = []
    for cid in required_ids or []:
        if _text(cid) and cid not in seen:
            findings.append(_defect(CAST_MEMBER_MISSING, cid,
                                    "beat says this person is here; the frame does not show them"))
    return _packet(findings)


def _packet(findings):
    return {"schema_version": SCHEMA_VERSION,
            "outcome": "pass" if not findings else "fail",
            "findings": findings,
            "codes": sorted({f["code"] for f in findings})}


__all__ = [
    "SCHEMA_VERSION", "CAST_NOT_IN_BIBLE", "CAST_REFERENCE_MISSING",
    "CAST_LOOKALIKE", "IDENTITY_BLOCK_WRONG_CHARACTER", "UNLISTED_PERSON",
    "CAST_MEMBER_MISSING", "cast_entries", "cast_ids", "check_cast_lock",
    "check_cast_in_beats", "check_cast_consistency", "check_cast_members_present",
]
