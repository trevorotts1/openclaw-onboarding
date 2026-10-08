#!/usr/bin/env python3
"""Suno C3 voice casting: profiles -> lyric tags, distinctness, regenerate rule.

Owner decision D22 (2026-10-07), plan 6.12 + 6.6. stdlib only.

Rules implemented:
1. Every speaking/singing character carries a voice profile: character_id,
   gender, age, tone, role, pitch_center. A pitch_center outside the D17 range
   for its gender (85-155 Hz male, 165-255 Hz female) is refused at cast time,
   so no cast can be built that QC could never pass.
2. Every lyric line is bound to its character and emitted with a Suno lyric
   tag, e.g. ``[Female voice - coworker, hushed]``. ``render_lyrics`` never
   emits an untagged line: unknown speaker or bad cast => outcome rejected.
3. Two same-gender characters must be measurably different voices: pitch gap
   >= DISTINCT_HZ, or a different age, or a different tone (plan 6.6).
   Cross-gender pairs cannot collide - the male and female ranges do not
   overlap (asserted by the test suite).
4. Regenerate-on-mismatch: a take whose measured pitch misses the gender
   range is regenerated in Suno (attempt +1) up to MAX_REGENERATIONS, then
   refused fail-closed as ``voice-mismatch-unresolved`` - never assembled.
   This module has no TTS path and no network call of its own: the generator
   is injected, and the tests inject a fake, so zero paid calls.

``core/qc_voice_match`` (unit V2B-AUDIO-U3) is the independent measuring
instrument over real audio; ``assess_pitch`` here is only the casting-side
gate the generator must clear, not a replacement for it.

Out of scope here: extending Character DNA (core/character_continuity) to
carry voice_profile - this unit owns core/audio_c3/ only. Narrator-inherits-
hero-gender (6.6) needs a voice_group exemption from distinctness; add it
when a campaign ships narrator lines. ponytail: both ceilings above.

Run: python3 core/audio_c3/test_voice_casting.py
"""
from __future__ import annotations

import re

SCHEMA_VERSION = "blackceo.audio-c3/voice-casting/v1"
TOOL_VERSION = "0.1.0"
EXIT = {"ok": 0, "error": 1, "rejected": 4}

#: D17 pitch ranges, Hz inclusive. Male max < female min: no cross-gender
#: collision is possible by construction.
PITCH_RANGE = {"male": (85.0, 155.0), "female": (165.0, 255.0)}

#: Minimum same-gender pitch gap before age/tone may carry distinctness.
DISTINCT_HZ = 15.0

#: Regenerations allowed after the initial take before a line is refused.
MAX_REGENERATIONS = 3

GENDERS = frozenset(PITCH_RANGE)
DELIVERIES = frozenset(("spoken", "sung"))
PROFILE_FIELDS = ("character_id", "gender", "age", "tone", "role", "pitch_center")
#: Campaign-schema lyric fields plus the speaker binding this unit adds.
LINE_FIELDS = ("line_id", "speaker_id", "text", "delivery", "critical",
               "pronunciation_map")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _norm(s):
    return s.strip().casefold()


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_profile(p):
    """Error list for one voice profile (empty = valid). Fail-closed."""
    if not isinstance(p, dict):
        return ["NOT_A_RECORD"]
    errs = []
    for k in sorted(p):
        if k not in PROFILE_FIELDS:
            errs.append("UNKNOWN_FIELD:%s" % k)
    for k in PROFILE_FIELDS:
        if k not in p:
            errs.append("MISSING:%s" % k)
    if errs:
        return errs
    cid = p["character_id"]
    if not isinstance(cid, str) or not ID_RE.match(cid):
        errs.append("BAD_CHARACTER_ID:%r" % (cid,))
    if p["gender"] not in GENDERS:
        errs.append("BAD_GENDER:%r" % (p["gender"],))
    for k in ("age", "tone", "role"):
        v = p[k]
        if not isinstance(v, str) or not v.strip():
            errs.append("BAD_TEXT:%s" % k)
    pc = p["pitch_center"]
    if not _is_number(pc):
        errs.append("BAD_PITCH_CENTER:%r" % (pc,))
    elif p["gender"] in GENDERS:
        lo, hi = PITCH_RANGE[p["gender"]]
        if not (lo <= float(pc) <= hi):
            errs.append("PITCH_CENTER_OUT_OF_RANGE:%s=%.1f not in %s"
                        % (cid, float(pc), PITCH_RANGE[p["gender"]]))
    return errs


def check_distinctness(profiles):
    """Same-gender pairs must differ measurably: pitch, age or tone.

    Input is assumed pre-validated (validate_cast feeds it the valid subset).
    """
    errs = []
    n = len(profiles)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = profiles[i], profiles[j]
            if a["gender"] != b["gender"]:
                continue
            gap = abs(float(a["pitch_center"]) - float(b["pitch_center"]))
            if gap >= DISTINCT_HZ:
                continue
            if _norm(a["age"]) != _norm(b["age"]):
                continue
            if _norm(a["tone"]) != _norm(b["tone"]):
                continue
            errs.append("NOT_DISTINCT:%s+%s" % (a["character_id"],
                                                b["character_id"]))
    return errs


def validate_cast(profiles):
    """Full cast error list: per-profile errors, duplicates, distinctness."""
    if not isinstance(profiles, list) or not profiles:
        return ["NO_PROFILES"]
    errs = []
    seen = set()
    valid = []
    for p in profiles:
        perrs = validate_profile(p)
        if perrs:
            errs.extend(perrs)
            continue
        cid = p["character_id"]
        if cid in seen:
            errs.append("DUPLICATE_CHARACTER_ID:%s" % cid)
            continue
        seen.add(cid)
        valid.append(p)
    errs.extend(check_distinctness(valid))
    return errs


def build_cast(profiles):
    """character_id -> profile. Raises ValueError listing every cast error."""
    errs = validate_cast(profiles)
    if errs:
        raise ValueError("; ".join(errs))
    return {p["character_id"]: dict(p) for p in profiles}


def voice_tag(profile):
    """Suno lyric tag: [Female voice - coworker, hushed].

    pitch_center is deliberately absent - Suno takes gender/role/tone words;
    the Hz value is the measurable QC anchor, not prompt text.
    """
    return "[%s voice - %s, %s]" % (str(profile["gender"]).capitalize(),
                                    profile["role"].strip(),
                                    profile["tone"].strip())


def _line_errors(line):
    if not isinstance(line, dict):
        return ["NOT_A_RECORD:line"]
    errs = []
    for k in sorted(line):
        if k not in LINE_FIELDS:
            errs.append("UNKNOWN_FIELD:%s" % k)
    for k in ("line_id", "speaker_id", "text"):
        if k not in line:
            errs.append("MISSING:%s" % k)
    if errs:
        return errs
    lid, sid = line["line_id"], line["speaker_id"]
    if not isinstance(lid, str) or not ID_RE.match(lid):
        errs.append("BAD_LINE_ID:%r" % (lid,))
    if not isinstance(sid, str) or not ID_RE.match(sid):
        errs.append("BAD_SPEAKER_ID:%r" % (sid,))
    if not isinstance(line["text"], str) or not line["text"].strip():
        errs.append("BAD_TEXT:%s" % "text")
    delivery = line.get("delivery", "spoken")
    if delivery not in DELIVERIES:
        errs.append("BAD_DELIVERY:%r" % (delivery,))
    return errs


def _render_envelope(outcome, reason_code, errors, cast, lines):
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "outcome": outcome,
        "reason_code": reason_code,
        "errors": errors,
        "cast": cast,
        "lines": lines,
        "next_action": (
            "Send the tagged lyrics to the Suno C3 generation path (D22)."
            if outcome == "ok" else
            "Fix the listed cast/line errors; no line ships untagged."
        ),
    }


def render_lyrics(lines, profiles):
    """Bind every line to its character's voice tag. Never emits a bare line."""
    errors = ["cast:%s" % e for e in validate_cast(profiles)]
    if errors:
        return _render_envelope("rejected", "cast-invalid", errors, [], [])

    cast = build_cast(profiles)
    cast_view = [
        dict(c, tag=voice_tag(c), pitch_range=list(PITCH_RANGE[c["gender"]]))
        for c in cast.values()
    ]
    if not isinstance(lines, list) or not lines:
        return _render_envelope("rejected", "lyrics-empty",
                                ["lyrics must be a non-empty list"],
                                cast_view, [])

    tagged = []
    for line in lines:
        errs = _line_errors(line)
        lid = line.get("line_id") if isinstance(line, dict) else None
        if errs:
            errors.extend("line:%s:%s" % (lid, e) for e in errs)
            continue
        speaker = line["speaker_id"]
        if speaker not in cast:
            # Fail closed: an unknown speaker gets no tag, so it is dropped
            # from output and the render is rejected.
            errors.append("line:%s:UNTAGGED_LINE(no voice profile for %s)"
                          % (lid, speaker))
            continue
        profile = cast[speaker]
        tagged.append({
            "line_id": line["line_id"],
            "speaker_id": speaker,
            "delivery": line.get("delivery", "spoken"),
            "tag": voice_tag(profile),
            "text": line["text"],
        })
    if errors:
        return _render_envelope("rejected", "line-untagged" if any(
            "UNTAGGED_LINE" in e for e in errors) else "line-invalid",
            errors, cast_view, tagged)
    return _render_envelope("ok", "", [], cast_view, tagged)


def assess_pitch(profile, measured_hz):
    """Casting-side D17 gate for one take (instrument: qc_voice_match, U3)."""
    if not _is_number(measured_hz):
        return {"ok": False, "reason_code": "no-measurement",
                "measured_hz": None,
                "range_hz": list(PITCH_RANGE[profile["gender"]])}
    lo, hi = PITCH_RANGE[profile["gender"]]
    m = float(measured_hz)
    return {"ok": lo <= m <= hi,
            "reason_code": "" if lo <= m <= hi else "pitch-out-of-range",
            "measured_hz": m,
            "range_hz": [lo, hi]}


def _regen_envelope(outcome, reason_code, line, profile, attempts,
                    regenerated, errors):
    lid = line.get("line_id") if isinstance(line, dict) else None
    sid = line.get("speaker_id") if isinstance(line, dict) else None
    tag = voice_tag(profile) if not validate_profile(profile) else None
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "outcome": outcome,
        "reason_code": reason_code,
        "errors": errors,
        "line_id": lid,
        "speaker_id": sid,
        "tag": tag,
        "delivery": line.get("delivery", "spoken") if isinstance(line, dict)
        else "spoken",
        "attempts": attempts,
        "regenerated": regenerated,
        "next_action": (
            "Proceed with the matched take." if outcome == "ok" else
            "Line refused before assembly: regenerate in Suno or rewrite; "
            "no other voice tool is ever used (D22)."
        ),
    }


def generate_to_match(line, profile, generator, measured_hz,
                      max_attempts=MAX_REGENERATIONS):
    """Regenerate-on-mismatch rule (plan 6.6 / 6.12).

    ``generator(line, attempt, profile) -> measured_hz`` of a fresh Suno take.
    Injected: the tests pass a fake, so zero paid calls. Attempt 0 is the
    take already in hand (``measured_hz``); a match keeps it and never calls
    the generator. A mismatch regenerates up to ``max_attempts`` times, then
    the line is refused fail-closed - never retried by a different voice tool.
    """
    perrs = validate_profile(profile)
    if perrs:
        return _regen_envelope("rejected", "cast-invalid", line, profile, [],
                               False, perrs)
    if not isinstance(line, dict) or _line_errors(line):
        errs = _line_errors(line) if isinstance(line, dict) else [
            "NOT_A_RECORD:line"]
        return _regen_envelope("rejected", "line-invalid", line, profile, [],
                               False, errs)

    attempts = []
    first = assess_pitch(profile, measured_hz)
    attempts.append({"attempt": 0, "measured_hz": first["measured_hz"],
                     "ok": first["ok"], "reason_code": first["reason_code"]})
    if first["ok"]:
        return _regen_envelope("ok", "", line, profile, attempts, False, [])

    try:
        limit = int(max_attempts)
    except (TypeError, ValueError):
        limit = MAX_REGENERATIONS
    for attempt in range(1, max(limit, 0) + 1):
        m = generator(line, attempt, profile)
        a = assess_pitch(profile, m)
        attempts.append({"attempt": attempt,
                         "measured_hz": a["measured_hz"],
                         "ok": a["ok"], "reason_code": a["reason_code"]})
        if a["ok"]:
            return _regen_envelope("ok", "", line, profile, attempts, True, [])
    # Regenerated at least once and still mismatched -> unresolved.
    # Regeneration disabled (limit < 1) -> refuse with the original reason.
    regenerated = any(a["attempt"] >= 1 for a in attempts)
    reason = ("voice-mismatch-unresolved" if regenerated
              else (attempts[-1]["reason_code"] or "voice-mismatch-unresolved"))
    return _regen_envelope("rejected", reason, line, profile, attempts,
                           regenerated, [])
