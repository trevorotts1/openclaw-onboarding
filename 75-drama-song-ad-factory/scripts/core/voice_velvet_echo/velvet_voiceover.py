#!/usr/bin/env python3
"""Velvet Voiceover -- the Google voiceover version (owner Decision 28 / D25,
Decision 31 rename, plan section 6.12.1; choice card section 4.1). Stdlib only.

Second option on the choice card's Voice line:

    Voice:  All Suno (default)  /  Velvet Voiceover (Google voiceover with the
            song underneath)

Owner Decision 31 (2026-10-07) renamed this option to "Velvet Voiceover" and
banned the echo: a plain voiceover with the song playing underneath. The old
slug ``velvet_echo`` still normalizes to the new id, so nothing that carried the
earlier name breaks.

What this module owns (plan 6.12.1):
1. the choice-card Voice line and its two options -- All Suno stays the default
   (Decision 27); this is the only place a second voice option exists;
2. one distinct Google text-to-speech voice per character, every voice of that
   character's own gender (static catalog table, no API call);
3. the sung-under mix: under each spoken line the song's own sung line plays
   softly beneath the talking while the music bed dips so the words stay clear;
4. the lip-sync gate (plan 6.6 / Decision 26): a mouth only ever moves to that
   on-screen character's own isolated line -- never the sung layer, never the
   music bed, never a narrator, never another character;
5. D17 QC, delegated to the sibling ``qc_voice_match`` package so the pitch
   bands, the on-screen speaker rule and the same-gender distinctness check
   live in exactly one place.

Google text-to-speech is the ONLY exception to D22's no-Google rule and it is
allowed only when the voice choice is ``velvet_voiceover``.

No network module and no provider call in this file: the catalog is a table,
the tests synthesize fixture WAVs locally, and the one paid call -- the
Velvet spoken line -- is built here as Skill 74 request JSON (a
``google/gemini-*-tts`` model) and dispatched by ``kie_dispatch`` like every
other paid call (manual M2).
"""
from __future__ import annotations

import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

try:
    # Sibling D17 checker: bands, on-screen rule and distinctness live there.
    from qc_voice_match import (  # noqa: F401
        PITCH_RANGES_HZ,
        SAME_GENDER_MIN_SEPARATION_HZ,
        evaluate,
        refuse_before_assembly,
        speaker_onscreen_ok,
    )
except ImportError as exc:  # fail closed: never re-implement D17 here
    raise ImportError(
        "voice_velvet_echo needs the sibling package qc_voice_match in %s"
        % (_CORE,)
    ) from exc

TOOL_NAME = "velvet_voiceover"
TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = "blackceo.velvet-voiceover/plan/v1"
ASSIGN_SCHEMA = "blackceo.velvet-voiceover/voice-assignment/v1"
MIX_SCHEMA = "blackceo.velvet-voiceover/sung-under-mix/v1"
LIPSYNC_SCHEMA = "blackceo.velvet-voiceover/lipsync-input/v1"
D17_REPORT_SCHEMA = "blackceo.qc-voice-match/report/v1"   # what evaluate() takes

# ---- choice card (plan 4.1, Decision 27 default, Decision 28 option) --------
ALL_SUNO_ID = "all_suno"
VELVET_ID = "velvet_voiceover"
LEGACY_VELVET_IDS = ("velvet_echo",)        # Decision 31 rename, old slug kept
DEFAULT_VOICE_ID = ALL_SUNO_ID              # Decision 27: All Suno stays default
VOICE_LINE_PREFIX = "Voice:"

# ---- Decision 31: plain voiceover, no echo ---------------------------------
EFFECT_BAN = ("echo", "reverb", "delay")

# ---- plan 6.12.1 item 3: sung under the talking, bed dipped ----------------
# Levels are relative to the spoken voice (0.0 dB = the voice itself).
VOICE_REF_DB = 0.0
SUNG_UNDER_DB = -6.0                        # sung line softly beneath the words
SUNG_UNDER_BAND_DB = (-12.0, -2.0)          # audible, never louder than this
MIN_SUNG_HEADROOM_DB = 3.0                  # words must stay clearly on top
BED_DIP_DB = -8.0                           # music bed dips under spoken lines
BED_DIP_BAND_DB = (-16.0, -4.0)             # a dip is mandatory, never a boost

DELIVERIES = ("spoken", "sung")             # mirrors core/audio_c3.DELIVERIES

# Narrator / off-screen voice (Decision 26): fine as voice-over, never as a
# moving mouth. The canonical narrator rule lives in core/lip_sync/; this is
# the same gate applied to the Velvet Voiceover path.
NARRATOR_TOKENS = frozenset({
    "narrator", "narration", "voice-over", "voiceover", "off-screen",
    "offscreen", "host", "announcer",
})

# Google Cloud text-to-speech voices. One table, no API call, no spend.
# Gender is the catalog's own label and is what D17's pitch band is checked on.
GOOGLE_VOICES = (
    ("en-US-Wavenet-A", "male"),
    ("en-US-Wavenet-B", "female"),
    ("en-US-Wavenet-C", "female"),
    ("en-US-Wavenet-D", "male"),
    ("en-US-Wavenet-E", "male"),
    ("en-US-Wavenet-F", "female"),
    ("en-US-Wavenet-G", "male"),
    ("en-US-Wavenet-H", "female"),
    ("en-US-Wavenet-I", "female"),
    ("en-US-Wavenet-J", "male"),
    ("en-US-Neural2-A", "male"),
    ("en-US-Neural2-B", "female"),
    ("en-US-Neural2-C", "female"),
    ("en-US-Neural2-D", "male"),
    ("en-US-Neural2-F", "female"),
    ("en-US-Neural2-H", "female"),
)

GOOGLE_EXCEPTION_RULE = (
    "Google text-to-speech is the only exception to D22's no-Google rule and "
    "it applies only to the Velvet Voiceover choice."
)

GOOGLE_VOICES_BY_GENDER = {
    "male": [v for v, g in GOOGLE_VOICES if g == "male"],
    "female": [v for v, g in GOOGLE_VOICES if g == "female"],
}


# ---- manual M2: Velvet spoken lines ride Skill 74 with a gemini TTS model ---
# Skill 74's registry carries the KIE Market catalog; the TTS models on it are
# google/gemini-*-tts, whose speaker schema wants a Gemini voice name (Zephyr,
# Kore, ...), NOT the Wavenet/Neural2 catalog ids above. The static table below
# therefore maps each catalog gender to a real registry model + a valid
# voice_name for that gender, so model selection stays a table lookup with no
# API call (manual M2 step 3; dispatch stays in kie_dispatch).
SKILL74_TOOL = "74-kie-live-adapter"
GEMINI_TTS_SCHEMA_VERSION = "blackceo.velvet-voiceover/skill74-request/v1"

# Gender -> (registry model id, Gemini TTS voice name, accent).
# voice_name values are taken from the Skill 74 registry enum for the model
# (30 valid names on gemini-2-5-pro-tts / gemini-3-1-flash-tts); accent is a
# registry enum value too. Flash-lite is the cheap everyday line; Pro is an
# explicit fallback. Gender labels stay Google's own catalog labels.
GEMINI_TTS_BY_GENDER = {
    "female": {
        "model": "google/gemini-3-1-flash-tts",
        "voice_name": "Leda",
        "accent": "Neutral",
    },
    "male": {
        "model": "google/gemini-3-1-flash-tts",
        "voice_name": "Orus",
        "accent": "Neutral",
    },
}
GEMINI_TTS_FALLBACK_MODEL = "google/gemini-2-5-pro-tts"
GEMINI_TTS_MODEL_PREFIX = "google/gemini-"
GEMINI_TTS_MODEL_SUFFIX = "-tts"
GEMINI_TTS_MAX_TURN_CHARS = 10000    # registry dialogue_turns text cap


class VelvetError(Exception):
    """Structural problem in the input itself (never a silent pass)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------- choice card -

def voice_options():
    """The two options on the choice card's Voice line, in card order."""
    return (
        {
            "id": ALL_SUNO_ID,
            "label": "All Suno (default)",
            "engine": "suno",
            "default": True,
            "google": False,
        },
        {
            "id": VELVET_ID,
            "label": "Velvet Voiceover (Google voiceover with the song underneath)",
            "engine": "google_tts",
            "default": False,
            "google": True,
        },
    )


def normalize_voice_choice(raw):
    """Canonical voice id. Unknown values fail closed; the old slug still works."""
    if raw is None:
        return DEFAULT_VOICE_ID
    if not isinstance(raw, str):
        raise VelvetError("VOICE_CHOICE_UNKNOWN",
                          "voice choice must be a string, got %r" % (raw,))
    value = raw.strip().lower()
    if not value:
        return DEFAULT_VOICE_ID
    if value in LEGACY_VELVET_IDS:
        return VELVET_ID
    allowed = {opt["id"] for opt in voice_options()}
    if value not in allowed:
        raise VelvetError("VOICE_CHOICE_UNKNOWN",
                          "voice choice %r is not one of %s"
                          % (raw, sorted(allowed)))
    return value


def google_allowed(voice_choice):
    """True only for the Velvet Voiceover choice (D22 exception gate)."""
    return normalize_voice_choice(voice_choice) == VELVET_ID


def voice_line(selected=None):
    """The card's Voice line, exactly two options, All Suno marked default.

    Also validates ``selected``: an unknown choice raises instead of rendering.
    """
    normalize_voice_choice(selected)
    labels = [opt["label"] for opt in voice_options()]
    return "%s       %s" % (VOICE_LINE_PREFIX, "  /  ".join(labels))


def choice_card_voice_field(selected=None):
    """Machine-readable Voice field for the choice card."""
    choice = normalize_voice_choice(selected)
    options = [dict(opt) for opt in voice_options()]
    for opt in options:
        opt["selected"] = opt["id"] == choice
    return {
        "schema_version": SCHEMA_VERSION,
        "field": "Voice",
        "line": voice_line(selected),
        "options": options,
        "selected": choice,
        "default": DEFAULT_VOICE_ID,
        "option_count": len(options),
    }


def check_effects(effects):
    """Decision 31: no echo, no reverb, no delay on the voiceover."""
    if effects is None:
        return []
    if isinstance(effects, str):
        effects = [effects]
    cleaned = []
    for effect in effects:
        name = str(effect).strip()
        if not name:
            continue
        lowered = name.lower()
        if any(banned in lowered for banned in EFFECT_BAN):
            raise VelvetError(
                "ECHO_EFFECT_FORBIDDEN",
                "Velvet Voiceover is a plain voiceover: %r banned (Decision 31)"
                % (name,))
        cleaned.append(name)
    return cleaned


# --------------------------------------------------- Google voice assignment --

def assign_google_voices(cast, effects=()):
    """One distinct Google voice per character, each of that character's gender.

    Fail closed: empty cast, duplicate character, unknown gender, or a cast
    bigger than the catalog's bucket for a gender raises VelvetError instead of
    handing two characters the same voice.
    """
    check_effects(effects)
    if not isinstance(cast, (list, tuple)) or not cast:
        raise VelvetError("CAST_EMPTY", "cast must be a non-empty list")

    order = {"male": [], "female": []}
    seen = set()
    for entry in cast:
        if not isinstance(entry, dict):
            raise VelvetError("CAST_MALFORMED", "cast entries must be objects")
        cid = entry.get("character_id")
        gender = entry.get("gender")
        cid = cid.strip() if isinstance(cid, str) else cid
        gender = gender.strip().lower() if isinstance(gender, str) else gender
        if not cid:
            raise VelvetError("CHARACTER_ID_MISSING",
                              "cast entry has no character_id")
        if cid in seen:
            raise VelvetError("CHARACTER_ID_DUPLICATE",
                              "character_id %r appears twice" % (cid,))
        seen.add(cid)
        if gender not in order:
            raise VelvetError("GENDER_UNKNOWN",
                              "character %r has gender %r; D17 needs male/female"
                              % (cid, entry.get("gender")))
        order[gender].append(cid)

    assignments = []
    cursor = {"male": 0, "female": 0}
    for entry in cast:
        cid = entry.get("character_id").strip()
        gender = entry.get("gender").strip().lower()
        bucket = GOOGLE_VOICES_BY_GENDER.get(gender, ())
        index = cursor[gender]
        if index >= len(bucket):
            raise VelvetError(
                "VOICE_CATALOG_EXHAUSTED",
                "no unused %s Google voice left for %r (%d in catalog)"
                % (gender, cid, len(bucket)))
        cursor[gender] = index + 1
        assignments.append({
            "character_id": cid,
            "gender": gender,
            "google_voice": bucket[index],
            "pitch_band_hz": list(PITCH_RANGES_HZ[gender]),
        })

    voices = [a["google_voice"] for a in assignments]
    if len(set(voices)) != len(voices):
        raise VelvetError("VOICE_NOT_DISTINCT", "two characters share a voice")

    return {
        "schema_version": ASSIGN_SCHEMA,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "voice_choice": VELVET_ID,
        "engine": "google_tts",
        "google_allowed": True,
        "effects": [],
        "assignments": assignments,
        "distinct_within_gender": True,
        "pitch_ranges_hz": {k: list(v) for k, v in sorted(PITCH_RANGES_HZ.items())},
        "d17_rule": "same-gender characters get clearly different voices",
        "exception_rule": GOOGLE_EXCEPTION_RULE,
    }


# ------------------------------------------------- Skill 74 request builder --

def gemini_tts_model_for(gender):
    """Static model pick for one line's gender (no API call, no spend).

    Accepts the gender label the catalog and D17 use (male/female). Unknown
    genders fail closed like the rest of the module.
    """
    if not isinstance(gender, str):
        raise VelvetError("GENDER_UNKNOWN", "gender must be 'male' or 'female'")
    g = gender.strip().lower()
    if g not in GEMINI_TTS_BY_GENDER:
        raise VelvetError(
            "GENDER_UNKNOWN",
            "gender %r has no gemini TTS mapping; D17 needs male/female"
            % (gender,))
    return GEMINI_TTS_BY_GENDER[g]["model"]


def build_skill74_tts_request(line, model=None, scene=None, temperature=None,
                              timeout=None):
    """Build the Skill 74 request JSON for one spoken Velvet line, no network.

    The shape is the one Skill 74's ``submit`` validates and sends to KIE:
    ``{"model": <google/gemini-*-tts id>, "input": {speakers, dialogue_turns}}``
    -- speakers carry the Gemini voice_name picked from the static table by the
    speaker's gender, dialogue_turns carry the line text. Everything
    ``kie_dispatch.dispatch`` adds on top (ledger ids, save_dir, cost) is its
    own concern; this function holds no import of kie_dispatch, makes no
    network call and dispatches nothing (manual M2 step 3: dispatch goes
    through kie_dispatch like every other paid call).

    Raises (fail closed, same codes as the rest of the module):
    - LINE_MALFORMED   line is not an object, or has no speaker/text
    - GENDER_UNKNOWN   speaker gender has no static model mapping
    - MODEL_UNKNOWN    explicit model is not a google/gemini-*-tts id
    - TEXT_TOO_LONG    text exceeds the registry's per-turn cap
    - LINE_MALFORMED   scene/temperature/timeout settings malformed
    """
    if not isinstance(line, dict):
        raise VelvetError("LINE_MALFORMED", "line must be an object")
    speaker = line.get("speaker")
    text = line.get("text")
    if not isinstance(speaker, str) or not speaker.strip():
        raise VelvetError("LINE_MALFORMED", "line has no speaker")
    if not isinstance(text, str) or not text.strip():
        raise VelvetError("LINE_MALFORMED", "line has no spoken text")
    speaker = speaker.strip()
    text = text.strip()
    if len(text) > GEMINI_TTS_MAX_TURN_CHARS:
        raise VelvetError(
            "TEXT_TOO_LONG",
            "spoken text is %d chars; the gemini TTS turn cap is %d"
            % (len(text), GEMINI_TTS_MAX_TURN_CHARS))

    if model is not None:
        if not isinstance(model, str) or not (
            model.startswith(GEMINI_TTS_MODEL_PREFIX)
            and model.endswith(GEMINI_TTS_MODEL_SUFFIX)
        ):
            raise VelvetError(
                "MODEL_UNKNOWN",
                "model %r is not a google/gemini-*-tts id (Skill 74 KIE "
                "Market catalog)" % (model,))
        chosen = model
        entry = None
    else:
        gender = line.get("gender")
        if not isinstance(gender, str):
            raise VelvetError(
                "GENDER_UNKNOWN",
                "Velvet line needs a speaker gender for the static gemini "
                "TTS table, got %r" % (gender,))
        chosen = gemini_tts_model_for(gender)
        entry = GEMINI_TTS_BY_GENDER[gender.strip().lower()]

    if entry:
        voice_name = entry["voice_name"]
        accent = entry["accent"]
    else:
        # Explicit model override: keep the default table's voice pair (the
        # registry enum carries both names on every google/gemini-*-tts model).
        entry = GEMINI_TTS_BY_GENDER["female"]
        voice_name = entry["voice_name"]
        accent = entry["accent"]

    envelope = {
        "schema_version": GEMINI_TTS_SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "skill74_skill": SKILL74_TOOL,
        "voice_choice": VELVET_ID,
        "request": {
            "model": chosen,
            "input": {
                "speakers": [{
                    "speaker_id": speaker,
                    "voice_name": voice_name,
                    "accent": accent,
                }],
                "dialogue_turns": [{
                    "speaker_id": speaker,
                    "text": text,
                }],
            },
        },
        "dispatch_via": "kie_dispatch",
        "note": GOOGLE_EXCEPTION_RULE,
    }
    if scene is not None:
        if not isinstance(scene, str):
            raise VelvetError("LINE_MALFORMED", "scene must be a string")
        envelope["request"]["input"]["scene"] = scene
    if temperature is not None:
        if (not isinstance(temperature, (int, float))
                or isinstance(temperature, bool)
                or not 0.0 <= temperature <= 2.0):
            raise VelvetError(
                "LINE_MALFORMED",
                "temperature must be a number in 0..2, got %r"
                % (temperature,))
        envelope["request"]["input"]["temperature"] = temperature
    if timeout is not None:
        if (not isinstance(timeout, (int, float))
                or isinstance(timeout, bool) or timeout <= 0):
            raise VelvetError(
                "LINE_MALFORMED",
                "timeout must be a positive number of seconds, got %r"
                % (timeout,))
        envelope["request"]["timeout"] = timeout
    return envelope


# ------------------------------------------------------- sung-under mix plan --

def plan_line_mix(line, voice_choice, sung_db=SUNG_UNDER_DB,
                  bed_dip_db=BED_DIP_DB):
    """Levels for one line under the Velvet Voiceover (or All Suno) choice.

    Velvet spoken lines: the song's own sung line sits under the talking and
    the music bed dips, both inside the bands that keep the words clear.
    All Suno (the default) has no sung-under layer at all (Decision 27).
    """
    if not isinstance(line, dict):
        raise VelvetError("LINE_MALFORMED", "line must be an object")
    choice = normalize_voice_choice(voice_choice)
    delivery = line.get("delivery", "spoken")
    if not isinstance(delivery, str) or delivery not in DELIVERIES:
        raise VelvetError("DELIVERY_UNKNOWN",
                          "delivery must be one of %s, got %r"
                          % (list(DELIVERIES), line.get("delivery")))

    base = {
        "schema_version": MIX_SCHEMA,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "line_id": line.get("line_id"),
        "delivery": delivery,
        "voice_choice": choice,
        "voice_db": VOICE_REF_DB,
    }

    if choice != VELVET_ID:
        base.update({
            "sung_under": False,
            "sung_db": None,
            "bed_db": 0.0,
            "bed_dipped": False,
            "reason": "ALL_SUNO_NO_SUNG_UNDER",
        })
        return base
    if delivery != "spoken":
        base.update({
            "sung_under": False,
            "sung_db": None,
            "bed_db": 0.0,
            "bed_dipped": False,
            "reason": "NOT_A_SPOKEN_LINE",
        })
        return base

    low, high = SUNG_UNDER_BAND_DB
    if not (low <= sung_db <= high):
        raise VelvetError(
            "SUNG_LEVEL_OUT_OF_BAND",
            "sung layer %s dB sits outside %s..%s dB under the voice"
            % (sung_db, low, high))
    dip_low, dip_high = BED_DIP_BAND_DB
    if not (dip_low <= bed_dip_db <= dip_high):
        raise VelvetError(
            "BED_DIP_OUT_OF_BAND",
            "bed dip %s dB sits outside %s..%s dB (a dip is mandatory)"
            % (bed_dip_db, dip_low, dip_high))
    headroom = VOICE_REF_DB - sung_db
    if headroom < MIN_SUNG_HEADROOM_DB:
        raise VelvetError(
            "WORDS_NOT_CLEAR",
            "sung layer only %.1f dB under the voice; needs >= %.1f dB"
            % (headroom, MIN_SUNG_HEADROOM_DB))
    if not sung_db < VOICE_REF_DB:
        raise VelvetError("SUNG_NOT_UNDER_VOICE",
                          "sung layer must sit below the spoken voice")

    return {
        **base,
        "sung_under": True,
        "sung_db": sung_db,
        "bed_db": bed_dip_db,
        "bed_dipped": True,
        "headroom_db": round(headroom, 3),
        "words_clear": True,
        "reason": "SUNG_UNDER_WITH_DIPPED_BED",
        "band_sung_db": list(SUNG_UNDER_BAND_DB),
        "band_bed_dip_db": list(BED_DIP_BAND_DB),
    }


# ------------------------------------------------------------ lip-sync gate --

def _norm_token(value):
    return value.strip().lower() if isinstance(value, str) else ""


def lipsync_input_check(line, stems, voice_choice=None):
    """Plan 6.6 / Decision 26: the input a moving mouth is allowed to use.

    Returns an envelope with outcome ``ok`` or ``refused`` -- never a pass by
    omission. A refusal names the rule that stopped it.
    """
    choice = normalize_voice_choice(voice_choice)
    if not isinstance(line, dict):
        return {
            "schema_version": LIPSYNC_SCHEMA, "outcome": "refused",
            "reason_code": "LINE_MALFORMED", "voice_choice": choice,
            "rule": "plan 6.6 / Decision 26",
        }
    line_id = line.get("line_id")
    speaker = _norm_token(line.get("speaker"))
    onscreen = _norm_token(line.get("onscreen"))

    def refuse(code, detail, narrator_ok=True):
        return {
            "schema_version": LIPSYNC_SCHEMA,
            "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "line_id": line_id,
            "voice_choice": choice,
            "outcome": "refused",
            "reason_code": code,
            "detail": detail,
            "rule": "plan 6.6 / Decision 26",
            "voice_over_still_allowed": narrator_ok,
            "input": None,
        }

    if not speaker:
        return refuse("SPEAKER_UNKNOWN", "line has no speaker", False)
    if speaker in NARRATOR_TOKENS:
        return refuse("NARRATOR_LIPSYNC_FORBIDDEN",
                      "a narrator's voice plays as voice-over and is never "
                      "lip-synced onto a person (Decision 26)")
    if not onscreen:
        return refuse("ONSCREEN_UNKNOWN", "no on-screen character recorded", False)

    # A device on screen is a voice-over shot: no mouth moves.
    if onscreen != speaker and speaker_onscreen_ok(speaker, onscreen):
        return refuse("NO_MOUTH_ON_SCREEN",
                      "on screen is the voice source (%r), not a mouth"
                      % (onscreen,))
    if not speaker_onscreen_ok(speaker, onscreen):
        return refuse("SPEAKER_MISMATCH",
                      "on screen %r but speaker is %r" % (onscreen, speaker))

    if not isinstance(stems, (list, tuple)) or not stems:
        return refuse("STEM_MISSING", "no lip-sync input stems given", False)

    wanted = "google_line" if choice == VELVET_ID else "suno_line"
    kinds = []
    for stem in stems:
        if not isinstance(stem, dict):
            return refuse("STEM_MALFORMED", "stem must be an object", False)
        kind = _norm_token(stem.get("kind"))
        kinds.append(kind)
        stem_speaker = _norm_token(stem.get("speaker_id"))
        if kind in ("sung", "song", "sung_layer"):
            return refuse("SUNG_STEM_PRESENT",
                          "the sung layer may never be a lip-sync input", False)
        if kind in ("music_bed", "bed", "music"):
            return refuse("MUSIC_STEM_PRESENT",
                          "the music bed may never be a lip-sync input", False)
        if kind and kind != wanted:
            return refuse("FOREIGN_STEM",
                          "stem kind %r is not the isolated %s line"
                          % (kind, wanted), False)
        if stem_speaker and stem_speaker != speaker:
            return refuse("OTHER_SPEAKER_STEM",
                          "stem belongs to %r, on-screen speaker is %r"
                          % (stem_speaker, speaker), False)
    if len(stems) != 1:
        return refuse("MIXED_STEM",
                      "lip-sync input must be exactly one isolated line, "
                      "got %d stems" % (len(stems)), False)

    stem = dict(stems[0])
    if stem.get("speaker_id") != speaker:
        return refuse("OTHER_SPEAKER_STEM",
                      "stem has no speaker_id for %r" % (speaker,), False)
    if not stem.get("isolated", False):
        return refuse("NOT_ISOLATED",
                      "stem must be flagged isolated=True (its own line only)",
                      False)

    return {
        "schema_version": LIPSYNC_SCHEMA,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "line_id": line_id,
        "voice_choice": choice,
        "outcome": "ok",
        "reason_code": "LIPSYNC_INPUT_OK",
        "detail": "one isolated %s line of the on-screen speaker" % wanted,
        "rule": "plan 6.6 / Decision 26",
        "input": {
            "stem_id": stem.get("stem_id"),
            "kind": stem.get("kind"),
            "speaker_id": stem.get("speaker_id"),
            "isolated": True,
        },
    }


def require_lipsync_input(envelope):
    """Fail closed: raise unless the lip-sync input was accepted."""
    if not isinstance(envelope, dict) or envelope.get("outcome") != "ok":
        code = (envelope or {}).get("reason_code", "LIPSYNC_INPUT_REFUSED")
        raise VelvetError(code, "lip-sync input refused: %s" % (code,))
    return envelope


# ----------------------------------------------------------------- D17 QC ----

def build_d17_report(run_id, stage, lines, characters=None):
    """A qc_voice_match report for this run (its schema, its rules)."""
    if not run_id or not stage:
        raise VelvetError("REPORT_IDS_MISSING", "run_id and stage are required")
    if not isinstance(lines, (list, tuple)) or not lines:
        raise VelvetError("REPORT_LINES_EMPTY", "lines must be a non-empty list")
    for line in lines:
        if not isinstance(line, dict):
            raise VelvetError("LINE_MALFORMED", "lines must be objects")
    report = {
        "schema_version": D17_REPORT_SCHEMA,
        "run_id": run_id,
        "stage": stage,
        "lines": [dict(line) for line in lines],
    }
    if characters:
        report["characters"] = [dict(c) for c in characters]
    return report


def run_d17_qc(run_id, stage, lines, characters=None):
    """D17: pitch band, on-screen speaker, same-gender distinctness."""
    return evaluate(build_d17_report(run_id, stage, lines, characters))


def gate_before_assembly(result):
    """Raises unless D17 QC passed (assembly stays blocked on a rejection)."""
    return refuse_before_assembly(result)


def velvet_pipeline_check(run_id, stage, lines, characters=None,
                          voice_choice=None, effects=None):
    """One call for the Velvet path: choice, voices, lip-sync gate, D17 QC."""
    choice = normalize_voice_choice(voice_choice)
    check_effects(effects)

    cast = []
    for line in lines:
        speaker = _norm_token(line.get("speaker"))
        gender = _norm_token(line.get("gender"))
        if speaker and all(c["character_id"] != speaker for c in cast):
            cast.append({"character_id": speaker, "gender": gender})
    assignment = assign_google_voices(cast) if choice == VELVET_ID else None

    lipsync = [lipsync_input_check(line, line.get("stems"), choice)
               for line in lines]
    refused = [e for e in lipsync if e["outcome"] != "ok"]

    mix = [plan_line_mix(line, choice) for line in lines]
    result = run_d17_qc(run_id, stage, lines, characters)

    return {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "voice_choice": choice,
        "google_allowed": google_allowed(choice),
        "voice_assignment": assignment,
        "line_mixes": mix,
        "lipsync": lipsync,
        "lipsync_all_ok": not refused,
        "d17": result,
        "outcome": "ok" if (not refused and result["outcome"] == "ok")
                   else "rejected",
        "reason_code": (result["reason_code"] if not refused
                        else "+".join(sorted({e["reason_code"] for e in refused}))),
    }


__all__ = [
    "ALL_SUNO_ID",
    "ASSIGN_SCHEMA",
    "BED_DIP_BAND_DB",
    "BED_DIP_DB",
    "DEFAULT_VOICE_ID",
    "DELIVERIES",
    "D17_REPORT_SCHEMA",
    "EFFECT_BAN",
    "GOOGLE_VOICES",
    "GOOGLE_EXCEPTION_RULE",
    "GEMINI_TTS_BY_GENDER",
    "GEMINI_TTS_FALLBACK_MODEL",
    "GEMINI_TTS_MAX_TURN_CHARS",
    "GEMINI_TTS_MODEL_PREFIX",
    "GEMINI_TTS_MODEL_SUFFIX",
    "GEMINI_TTS_SCHEMA_VERSION",
    "SKILL74_TOOL",
    "LEGACY_VELVET_IDS",
    "LIPSYNC_SCHEMA",
    "MIN_SUNG_HEADROOM_DB",
    "MIX_SCHEMA",
    "NARRATOR_TOKENS",
    "PITCH_RANGES_HZ",
    "SAME_GENDER_MIN_SEPARATION_HZ",
    "SCHEMA_VERSION",
    "SUNG_UNDER_BAND_DB",
    "SUNG_UNDER_DB",
    "TOOL_NAME",
    "TOOL_VERSION",
    "VELVET_ID",
    "VelvetError",
    "VOICE_REF_DB",
    "assign_google_voices",
    "build_d17_report",
    "build_skill74_tts_request",
    "check_effects",
    "choice_card_voice_field",
    "gate_before_assembly",
    "gemini_tts_model_for",
    "google_allowed",
    "lipsync_input_check",
    "normalize_voice_choice",
    "plan_line_mix",
    "require_lipsync_input",
    "run_d17_qc",
    "velvet_pipeline_check",
    "voice_line",
    "voice_options",
]
