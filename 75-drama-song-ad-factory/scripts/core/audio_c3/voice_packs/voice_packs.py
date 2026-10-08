#!/usr/bin/env python3
"""Per-character Suno voice packs: distinct-voice registry + spoken-only packs.

SUPERSEDED (owner order 2026-10-08, manual Part F F1): the spoken-only
separate-take pack route is superseded by the one-track soundtrack rule --
every spoken line is performed inside the ONE Suno track's lyrics
(``core/audio_c3/soundtrack.py``, ``SPOKEN_SOURCE = "in-song-lyrics"``).
Nothing routes spoken lines to separate packs any more; the distinct-voice
REGISTRY below still governs (no two characters share a voice) and this code
path is kept record-only.

Owner BUILD-OUT 6 (2026-10-07), reference recipe ``hybrid-occ-5min-rnb-flow``,
plan 6.12 / 6.6, owner Decision 20. stdlib only.

Rules implemented:
1. DISTINCT-VOICE REGISTRY. Every character registers its own voice identity
   (voice_id, gender, age, tone, role, pitch_center, optional measured_hz).
   No two characters ever share a voice: a repeated voice_id, a second
   registration of the same character, or a same-gender identity that cannot
   be told apart (age and tone equal AND pitch gap < DISTINCT_HZ - declared
   centers, or measured takes when both are measured) is refused at
   registration. Cross-gender pairs can never collide: the D17 bands do not
   overlap (85-155 male, 165-255 female), which the suite asserts.
2. PACK GENERATION RECORDS THE IDENTITY. Every pack carries the character's
   full voice identity plus provider suno, pack_kind spoken-only, cut_into
   lead-vocal-stem, recipe hybrid-occ-5min-rnb-flow and the dry close-mic
   negative tags (D22a / D37: no reverb, echo, delay or hall, ever; spoken
   parts never use "spacious", "cinematic" or "choir").
3. COLLISION PATH - the reference recipe. The main take gave the female
   guests the same pitch as the lead, so the host and the HR voicemail became
   SUNO VOICE-PACK GENERATIONS, SPOKEN ONLY, cut into the lead-vocal stem.
   ``find_collisions`` groups same-gender characters whose main-take
   measurements sit closer than DISTINCT_HZ; ``collision_packs`` then issues a
   spoken-only pack for every colliding character who is not the hero - the
   hero keeps the main take. The HR voicemail is not a collision, it is a
   device line: request it directly with trigger "device-voicemail"
   (phone band-pass recorded on the pack).
4. A pack take that misses its own gender band, or lands within DISTINCT_HZ
   of another registered character's voice, is regenerated (generator
   injected) up to MAX_REGENERATIONS and then refused fail-closed as
   "voice-pack-unresolved" - never assembled, never revoiced by another tool.
5. No pitch-shifting of voices (D37): a non-zero pitch shift on a pack request
   is refused. The reference's HR "+2.5 semitones" predates that ruling; only
   the phone band-pass survives.

Generator injected, no transport of its own: the tests spend nothing.

Run: python3 core/audio_c3/voice_packs/test_voice_packs.py
"""
from __future__ import annotations

from ..voice_casting import (DISTINCT_HZ, GENDERS, ID_RE, MAX_REGENERATIONS,
                             PITCH_RANGE, voice_tag)

SCHEMA_VERSION = "blackceo.audio-c3/voice-packs/v1"
PACK_SCHEMA_VERSION = "blackceo.audio-c3/voice-packs/pack/v1"
TOOL_VERSION = "0.1.0"
EXIT = {"ok": 0, "error": 1, "rejected": 4}

#: Binding production recipe (owner BUILD-OUT 6 source: reference receipt).
RECIPE_ID = "hybrid-occ-5min-rnb-flow"
PROVIDER = "suno"
PACK_KIND = "spoken-only"
CUT_INTO = "lead-vocal-stem"

#: The lead keeps the main take; colliding non-lead characters get packs.
LEAD_ROLE = "hero"

#: D22a / D37: dry close-microphone vocal, these are set as negative tags.
NEGATIVE_TAGS = ("reverb", "echo", "delay", "hall", "ethereal", "ambient",
                  "choir pad")
#: D22a: a spoken part never asks for these style words.
SPOKEN_BANNED_STYLE_WORDS = ("spacious", "cinematic", "choir")

#: Device lines (the HR voicemail) get a band-pass, never a pitch shift.
DEVICE_BANDPASS = {"phone": (300.0, 3400.0)}

SOURCES = frozenset(("main-take", "spoken-only-pack"))
TRIGGERS = frozenset(("main-take-pitch-collision", "device-voicemail",
                      "requested"))
TRIGGER_COLLISION = "main-take-pitch-collision"
TRIGGER_DEVICE = "device-voicemail"
TRIGGER_REQUESTED = "requested"

IDENTITY_FIELDS = ("character_id", "voice_id", "gender", "age", "tone",
                   "role", "pitch_center")
OPTIONAL_FIELDS = ("measured_hz", "source", "pack_id")
ALL_FIELDS = IDENTITY_FIELDS + OPTIONAL_FIELDS


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _norm(s):
    return str(s).strip().casefold()


def _env(outcome, reason_code, errors, **extra):
    out = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "outcome": outcome,
        "reason_code": reason_code,
        "errors": list(errors),
    }
    out.update(extra)
    return out


def _entries(registry):
    """Registry voice map, or (None, error-list) when the registry is bad."""
    if not isinstance(registry, dict):
        return None, ["REGISTRY_INVALID"]
    voices = registry.get("voices")
    if not isinstance(voices, dict):
        return None, ["REGISTRY_INVALID"]
    for cid, ident in voices.items():
        if not isinstance(ident, dict) or ident.get("character_id") != cid:
            return None, ["REGISTRY_ENTRY_CORRUPT:%s" % cid]
    return voices, []


# ---------------------------------------------------------- registry -------

def validate_identity(identity):
    """Error list for one voice identity (empty = valid). Fail-closed."""
    if not isinstance(identity, dict):
        return ["NOT_A_RECORD"]
    errs = []
    for k in sorted(identity):
        if k not in ALL_FIELDS:
            errs.append("UNKNOWN_FIELD:%s" % k)
    for k in IDENTITY_FIELDS:
        if k not in identity:
            errs.append("MISSING:%s" % k)
    if errs:
        return errs
    cid = identity["character_id"]
    if not isinstance(cid, str) or not ID_RE.match(cid):
        errs.append("BAD_CHARACTER_ID:%r" % (cid,))
    vid = identity["voice_id"]
    if not isinstance(vid, str) or not ID_RE.match(vid):
        errs.append("BAD_VOICE_ID:%r" % (vid,))
    if identity["gender"] not in GENDERS:
        errs.append("BAD_GENDER:%r" % (identity["gender"],))
    for k in ("age", "tone", "role"):
        v = identity[k]
        if not isinstance(v, str) or not v.strip():
            errs.append("BAD_TEXT:%s" % k)
    pc = identity["pitch_center"]
    if not _num(pc):
        errs.append("BAD_PITCH_CENTER:%r" % (pc,))
    elif identity["gender"] in PITCH_RANGE:
        lo, hi = PITCH_RANGE[identity["gender"]]
        if not (lo <= float(pc) <= hi):
            errs.append("PITCH_CENTER_OUT_OF_RANGE:%s=%.1f not in %s"
                        % (cid, float(pc), PITCH_RANGE[identity["gender"]]))
    mz = identity.get("measured_hz")
    if mz is not None and not _num(mz):
        errs.append("BAD_MEASURED_HZ:%r" % (mz,))
    src = identity.get("source")
    if src is not None and src not in SOURCES:
        errs.append("BAD_SOURCE:%r" % (src,))
    pid = identity.get("pack_id")
    if pid is not None and (not isinstance(pid, str) or not ID_RE.match(pid)):
        errs.append("BAD_PACK_ID:%r" % (pid,))
    return errs


def _pair_errors(a, b):
    """Distinctness for one same-gender pair (D20 / plan 6.12 cast table).

    Axes are OR: a different age or a different tone is already "clearly
    different"; only when age and tone match does the pitch gap have to
    reach DISTINCT_HZ. The pitch read is the measured take when both
    characters have one, otherwise the declared center.
    """
    if a["gender"] != b["gender"]:
        return []
    if _norm(a["age"]) != _norm(b["age"]):
        return []
    if _norm(a["tone"]) != _norm(b["tone"]):
        return []
    ma, mb = a.get("measured_hz"), b.get("measured_hz")
    if _num(ma) and _num(mb):
        gap = abs(float(ma) - float(mb))
    else:
        gap = abs(float(a["pitch_center"]) - float(b["pitch_center"]))
    if gap < DISTINCT_HZ:
        return ["NOT_DISTINCT:%s+%s" % (a["character_id"], b["character_id"])]
    return []


def new_registry():
    """Empty distinct-voice registry."""
    return {"schema_version": SCHEMA_VERSION, "voices": {}}


def register(registry, identity):
    """Register one character's voice identity. Refuses a shared voice."""
    errs = validate_identity(identity)
    cid = identity.get("character_id") if isinstance(identity, dict) else None
    vid = identity.get("voice_id") if isinstance(identity, dict) else None
    if errs:
        return _env("rejected", "identity-invalid", errs,
                    character_id=cid, voice_id=vid)
    voices, rerrs = _entries(registry)
    if voices is None:
        return _env("rejected", "registry-invalid", rerrs,
                    character_id=cid, voice_id=vid)
    if cid in voices:
        return _env("rejected", "character-registered",
                    ["DUPLICATE_CHARACTER_ID:%s" % cid],
                    character_id=cid, voice_id=vid)
    pair_errs = []
    for other_id in sorted(voices):
        other = voices[other_id]
        if other["voice_id"] == vid:
            return _env(
                "rejected", "voice-shared",
                ["VOICE_ID_SHARED:%s+%s (no two characters ever share a "
                 "voice)" % (other_id, cid)],
                character_id=cid, voice_id=vid)
        pair_errs.extend(_pair_errors(other, identity))
    if pair_errs:
        return _env("rejected", "voices-not-distinct", pair_errs,
                    character_id=cid, voice_id=vid)
    voices[cid] = dict(identity)
    return _env("ok", "", [], character_id=cid, voice_id=vid)


def voices(registry):
    """Every registered voice identity, sorted by character_id."""
    entries, errs = _entries(registry)
    if entries is None:
        raise ValueError("; ".join(errs))
    return [dict(entries[cid]) for cid in sorted(entries)]


def assert_distinct(registry):
    """Whole-registry distinctness check: error list, empty = distinct."""
    entries, errs = _entries(registry)
    if entries is None:
        return list(errs)
    out = []
    cids = sorted(entries)
    for i, a in enumerate(cids):
        for b in cids[i + 1:]:
            A, B = entries[a], entries[b]
            if A["voice_id"] == B["voice_id"]:
                out.append("VOICE_ID_SHARED:%s+%s" % (a, b))
            out.extend(_pair_errors(A, B))
    return out


# ------------------------------------------------- collision detection -----

def find_collisions(registry, measured):
    """Group same-gender main-take measurements closer than DISTINCT_HZ.

    ``measured`` is character_id -> Hz of the take already in hand. Fail
    closed: every registered character must be measured, no unknown names,
    no non-numeric values. Returns the collision groups and the characters
    that need a spoken-only pack (every group member who is not the hero).
    """
    entries, rerrs = _entries(registry)
    if entries is None:
        return _env("rejected", "registry-invalid", rerrs,
                    collisions=[], pack_characters=[])
    if not isinstance(measured, dict):
        return _env("rejected", "measurements-invalid",
                    ["MEASUREMENTS_MUST_BE_A_MAP"],
                    collisions=[], pack_characters=[])
    errs = []
    for cid in sorted(entries):
        if cid not in measured:
            errs.append("MISSING_MEASUREMENT:%s" % cid)
    for cid in sorted(measured):
        if cid not in entries:
            errs.append("UNKNOWN_CHARACTER:%s" % cid)
        elif not _num(measured[cid]):
            errs.append("BAD_MEASUREMENT:%s=%r" % (cid, measured[cid]))
    if errs:
        return _env("rejected", "measurements-incomplete", errs,
                    collisions=[], pack_characters=[])

    groups = []
    by_gender = {}
    for cid in sorted(entries):
        by_gender.setdefault(entries[cid]["gender"], []).append(cid)
    for gender in sorted(by_gender):
        chain = sorted(by_gender[gender],
                       key=lambda c: (float(measured[c]), c))
        run = []
        for cid in chain:
            if run and (abs(float(measured[cid]) - float(measured[run[-1]]))
                        < DISTINCT_HZ):
                run.append(cid)
                continue
            if len(run) > 1:
                groups.append((gender, run))
            run = [cid]
        if len(run) > 1:
            groups.append((gender, run))

    collisions = []
    pack_characters = []
    for gender, members in groups:
        collisions.append({
            "gender": gender,
            "members": list(members),
            "measured_hz": {c: float(measured[c]) for c in members},
        })
        non_lead = [c for c in members
                    if _norm(entries[c]["role"]) != LEAD_ROLE]
        for cid in (non_lead or members):
            if cid not in pack_characters:
                pack_characters.append(cid)
    return _env("ok", "", [], collisions=collisions,
                pack_characters=pack_characters)


# ------------------------------------------------------- pack generation ----

def _pack(request, outcome, reason_code, errors, attempt, measured_hz,
          next_action):
    pack = dict(request or {})
    pack.setdefault("character_id", None)
    pack.setdefault("voice", None)
    pack.setdefault("trigger", TRIGGER_REQUESTED)
    pack.setdefault("collides_with", [])
    pack.setdefault("device", None)
    pack.setdefault("bandpass_hz", None)
    pack.update({
        "schema_version": PACK_SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "pack_id": "pack-%s" % pack["character_id"] if pack["character_id"]
        else None,
        "delivery": "spoken",
        "outcome": outcome,
        "reason_code": reason_code,
        "errors": list(errors),
        "attempt": attempt,
        "measured_hz": measured_hz,
        "next_action": next_action,
    })
    return pack


def build_pack_request(registry, character_id, trigger=TRIGGER_REQUESTED,
                       collides_with=(), device=None,
                       pitch_shift_semitones=0.0):
    """Envelope carrying the spoken-only pack request (static fields).

    Refused fail-closed on an unknown character, an unknown device, or any
    non-zero pitch shift (D37 bans pitch-shifting of voices).
    """
    entries, rerrs = _entries(registry)
    if entries is None:
        return _env("rejected", "registry-invalid", rerrs, request=None)
    errs = []
    if trigger not in TRIGGERS:
        errs.append("BAD_TRIGGER:%r" % (trigger,))
    if not _num(pitch_shift_semitones) or float(pitch_shift_semitones) != 0.0:
        errs.append("PITCH_SHIFT_REFUSED:%r (D37: no pitch-shifting of "
                    "voices)" % (pitch_shift_semitones,))
    bandpass = None
    if device is not None:
        if device not in DEVICE_BANDPASS:
            errs.append("UNKNOWN_DEVICE:%r (known: %s)"
                        % (device, ", ".join(sorted(DEVICE_BANDPASS))))
        else:
            bandpass = list(DEVICE_BANDPASS[device])
    if character_id not in entries:
        errs.append("UNKNOWN_CHARACTER:%s" % character_id)
        return _env("rejected", "unknown-character", errs, request=None)
    if errs:
        return _env("rejected", "pack-request-refused", errs, request=None)

    identity = dict(entries[character_id])
    prompt = "%s, spoken only, dry close-microphone vocal" % voice_tag(
        identity)
    request = {
        "character_id": character_id,
        "voice": identity,
        "provider": PROVIDER,
        "pack_kind": PACK_KIND,
        "cut_into": CUT_INTO,
        "recipe": RECIPE_ID,
        "trigger": trigger,
        "collides_with": [c for c in collides_with if c != character_id],
        "device": device,
        "bandpass_hz": bandpass,
        "pitch_shift_semitones": 0.0,
        "dry_close_mic": True,
        "negative_tags": list(NEGATIVE_TAGS),
        "style_words_banned": list(SPOKEN_BANNED_STYLE_WORDS),
        "prompt": prompt,
    }
    return _env("ok", "", [], request=request)


def _take_ok(entries, character_id, measured_hz):
    """True when this take is its gender's band and nobody else's voice."""
    ident = entries[character_id]
    lo, hi = PITCH_RANGE[ident["gender"]]
    if not (lo <= measured_hz <= hi):
        return False, "pitch-out-of-range"
    for other_id in sorted(entries):
        if other_id == character_id:
            continue
        other = entries[other_id]
        if other["gender"] != ident["gender"]:
            continue
        ref = other.get("measured_hz")
        ref = float(ref) if _num(ref) else float(other["pitch_center"])
        if abs(measured_hz - ref) < DISTINCT_HZ:
            return False, "voice-collides-with:%s" % other_id
    return True, ""


def generate_pack(registry, character_id, generator=None,
                  trigger=TRIGGER_REQUESTED, collides_with=(), device=None,
                  pitch_shift_semitones=0.0, measured=None,
                  max_attempts=MAX_REGENERATIONS):
    """Generate one character's pack. The generator is injected.

    ``generator(request, attempt) -> measured_hz`` of a fresh Suno pack take.
    ``measured`` is the take already in hand (None means none). A take that
    passes its gender band AND stays DISTINCT_HZ away from every other
    registered voice is accepted at once and never calls the generator; a
    failing take is regenerated up to ``max_attempts`` times, then refused
    fail-closed as ``voice-pack-unresolved``. On acceptance the registry
    records the character's measured pitch, pack_id and source
    ``spoken-only-pack`` - the pack generation stamps per-character voice
    identity into both the pack and the registry.
    """
    req = build_pack_request(registry, character_id, trigger=trigger,
                             collides_with=collides_with, device=device,
                             pitch_shift_semitones=pitch_shift_semitones)
    if req["outcome"] != "ok":
        return _pack(None, "rejected",
                     req["reason_code"] or "pack-request-refused",
                     req["errors"], 0, None,
                     "Fix the pack request; nothing is generated.")
    request = req["request"]
    entries, _ = _entries(registry)

    try:
        limit = int(max_attempts)
    except (TypeError, ValueError):
        limit = MAX_REGENERATIONS
    history = []
    attempt = 0
    if measured is not None:
        if not _num(measured):
            return _pack(request, "rejected", "bad-measurement",
                         ["BAD_MEASURED_HZ:%r" % (measured,)], 0, None,
                         "Measure the take before packing it.")
        m = float(measured)
        ok, why = _take_ok(entries, character_id, m)
        history.append({"attempt": 0, "measured_hz": m, "ok": ok,
                        "reason_code": why})
        if ok:
            return _accept(registry, request, history, m, 0)
    if not callable(generator):
        return _pack(request, "rejected", "suno-pack-generator-required",
                     ["GENERATOR_MISSING: a pack is generated in Suno "
                      "(D22); no other voice tool ever takes its place"],
                     0, None, "Supply the Suno pack generator.")
    for attempt in range(1, max(limit, 0) + 1):
        raw = generator(dict(request), attempt)
        if not _num(raw):
            history.append({"attempt": attempt, "measured_hz": None,
                            "ok": False, "reason_code": "no-measurement"})
            continue
        m = float(raw)
        ok, why = _take_ok(entries, character_id, m)
        history.append({"attempt": attempt, "measured_hz": m, "ok": ok,
                        "reason_code": why})
        if ok:
            return _accept(registry, request, history, m, attempt)
    regenerated = any(h["attempt"] >= 1 for h in history)
    reason = ("voice-pack-unresolved" if regenerated else
              (history[-1]["reason_code"] if history else
               "voice-pack-unresolved"))
    return _pack(request, "rejected", reason, [], attempt,
                 history[-1]["measured_hz"] if history else None,
                 "Pack refused before assembly: regenerate in Suno or "
                 "rewrite the line; never revoice it with another tool (D22).")


def _accept(registry, request, history, measured_hz, attempt):
    entries, _ = _entries(registry)
    cid = request["character_id"]
    pack_id = "pack-%s" % cid
    entries[cid]["measured_hz"] = measured_hz
    entries[cid]["pack_id"] = pack_id
    entries[cid]["source"] = "spoken-only-pack"
    return _pack(request, "ok", "", [], attempt, measured_hz,
                 "Spoken-only pack accepted; cut into the %s (recipe %s)."
                 % (CUT_INTO, RECIPE_ID))


def collision_packs(registry, measured, generator, max_attempts=None):
    """Recipe path: main-take pitch collision -> spoken-only packs.

    Every colliding character who is not the hero gets its own pack; the
    hero keeps the main take. No collision means no pack and the generator is
    never called.
    """
    found = find_collisions(registry, measured)
    if found["outcome"] != "ok":
        return _env("rejected", found["reason_code"], found["errors"],
                    collisions=[], pack_characters=[], packs=[],
                    next_action="Fix the measurements; no pack is generated "
                                "from an incomplete read.")
    packs = []
    all_ok = True
    for cid in found["pack_characters"]:
        group = next(g for g in found["collisions"] if cid in g["members"])
        kwargs = {"trigger": TRIGGER_COLLISION,
                  "collides_with": [m for m in group["members"] if m != cid]}
        if max_attempts is not None:
            kwargs["max_attempts"] = max_attempts
        pack = generate_pack(registry, cid, generator, **kwargs)
        packs.append(pack)
        if pack["outcome"] != "ok":
            all_ok = False
    if not all_ok:
        return _env("rejected", "voice-pack-unresolved",
                    ["pack:%s:%s" % (p["character_id"], p["reason_code"])
                     for p in packs if p["outcome"] != "ok"],
                    collisions=found["collisions"],
                    pack_characters=found["pack_characters"], packs=packs,
                    next_action="Regenerate the refused pack in Suno; the "
                                "colliding character never ships on the main "
                                "take.")
    return _env("ok", "", [], collisions=found["collisions"],
                pack_characters=found["pack_characters"], packs=packs,
                next_action="Cut each spoken-only pack into the %s and keep "
                            "the hero on the main take (recipe %s)."
                            % (CUT_INTO, RECIPE_ID))
