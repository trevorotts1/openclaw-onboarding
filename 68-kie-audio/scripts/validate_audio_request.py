#!/usr/bin/env python3
"""validate_audio_request.py -- deterministic pre-dispatch validator for KIE audio.

Skill 68 (kie-audio). Validates a payload JSON file against the FIRST-PARTY
limits frozen in models.json / references (base verified 2026-08-26; Suno current envelope reconciled 2026-10-06 per planning/provider-contracts.md). Offline, except that Skill 74 (optional) is asked to validate a named model missing from models.json and, for stt, to report from a free catalog GET.
No API side effects. Exit codes:

  0 -- valid (or warning-level advisory; see report)
  2 -- hard violation (payload must NOT be dispatched)

Sub-domains:
  tts   -- generic KIE Market createTask (Gemini + ElevenLabs routes)
  music -- Suno: CURRENT createTask envelope (ai-music-api/*, V6 default) AND
           LEGACY dedicated /api/v1/generate* family (V4..V5_5, live-marked
           Discontinued -- accepted with a warning, never dropped)
  stt   -- ADVERTISED_NOT_YET_VERIFIED: no endpoint, no dispatch (hard error)

Usage:
  python3 validate_audio_request.py --domain tts   --payload req.json
  python3 validate_audio_request.py --domain music --payload req.json
  python3 validate_audio_request.py --domain stt   --payload req.json
  python3 validate_audio_request.py --self-test

Every numeric limit below is quoted from first-party KIE docs (base 2026-08-26; Suno current envelope 2026-10-06)
(see references/tts.md and references/music.md for the verbatim quotes and
source URLs). The validator never invents a limit: what is VERIFIED is
enforced; what is UNDETERMINED is reported as a warning, never hard-rejected.

KIE prompt rule 12 (owner order 2026-10-05): a DESCRIPTIVE music field (Suno style,
the non-custom song description, the sounds prompt, add-vocals style, add-instrumental
tags) is 95 to 100 percent of its character max, hard floor 80 percent, hard ceiling
100 percent, checked by the shared enforcer shared-utils/kie_prompt_enforcer.py (limit
from Skill 74 prompt-budget, else the first-party limit below as the policy-owner
fallback). VERBATIM fields (TTS text, custom-mode lyrics) are exempt from the floor and
keep only their ceilings below.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def _load_enforcer():
    """Find shared-utils/kie_prompt_enforcer.py (repo checkout or installed skills tree) and import it."""
    envd = os.environ.get("OPENCLAW_SKILLS_DIR")
    dirs = [p / "shared-utils" for p in Path(__file__).resolve().parents]
    dirs += ([Path(envd) / "shared-utils"] if envd else []) + [
        Path.home() / ".openclaw" / "skills" / "shared-utils", Path("/data/.openclaw/skills/shared-utils")]
    for d in dirs:
        if (d / "kie_prompt_enforcer.py").is_file():
            sys.path.insert(0, str(d))
            import kie_prompt_enforcer
            return kie_prompt_enforcer
    raise ImportError("shared-utils/kie_prompt_enforcer.py not found; install or update the onboarding skills")


KPE = _load_enforcer()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter_bridge  # noqa: E402  (Skill 74 bridge; optional at runtime)

# ---------------------------------------------------------------------------
# Verified facts (source: first-party KIE docs pages fetched 2026-08-26)
# ---------------------------------------------------------------------------

GEMINI_TTS_MODELS = ("google/gemini-3-1-flash-tts", "google/gemini-2-5-pro-tts")

GEMINI_VOICES = [
    "Achernar", "Achird", "Algenib", "Algieba", "Alnilam", "Aoede", "Autonoe",
    "Callirrhoe", "Charon", "Despina", "Enceladus", "Erinome", "Fenrir",
    "Gacrux", "Iapetus", "Kore", "Laomedeia", "Leda", "Orus", "Puck",
    "Pulcherrima", "Rasalgethi", "Sadachbia", "Sadaltager", "Schedar",
    "Sulafat", "Umbriel", "Vindemiatrix", "Zephyr", "Zubenelgenubi",
]
GEMINI_ACCENTS = [
    "Neutral", "American (Gen)", "American (Valley)", "American (South)",
    "British (RP)", "British (Brixton)", "Transatlantic", "Australian",
]
GEMINI_STYLES = [
    "Vocal Smile", "Newscaster", "Whisper", "Empathetic", "Promo/Hype",
    "Deadpan",
]
GEMINI_PACES = ["Natural", "Rapid Fire", "The Drift", "Staccato"]

GEMINI_PER_TURN_MAX = 10000       # input.dialogue_turns[].text maxLength (pages A/B)
GEMINI_TEMP_MIN, GEMINI_TEMP_MAX = 0, 2
SPEAKER_ID_RE = re.compile(r"^Speaker\s+\d+$")

ELEVENLABS_MODELS = (
    "elevenlabs/text-to-dialogue-v3",
    "elevenlabs/text-to-speech-multilingual-v2",
    "elevenlabs/text-to-speech-turbo-2-5",
)
EL_DIALOGUE_COMBINED_MAX = 5000   # "total character count of all text fields combined must not exceed 5000 characters."
EL_TEXT_MAX = 5000                # input.text maxLength 5000 (multilingual-v2, turbo-2-5)
EL_STABILITY_ENUM = (0, 0.5, 1)   # dialogue-v3 only
EL_SPEED_MIN, EL_SPEED_MAX = 0.7, 1.2

# Layered Suno versions (W0-02 contract, live docs 2026-10-06): the legacy
# dedicated routes (/api/v1/generate family) keep V4..V5_5; the current createTask
# envelope (ai-music-api/*) defaults V6 with V6_MINI/V6_WILD live. V4..V5_5 are
# marked Discontinued on the live pages -- accepted with a warning, never dropped.
LEGACY_SUNO_MODELS = ("V4", "V4_5", "V4_5PLUS", "V4_5ALL", "V5", "V5_5")
CURRENT_SUNO_MODELS = ("V6", "V6_MINI", "V6_WILD")
SUNO_MODELS = LEGACY_SUNO_MODELS + CURRENT_SUNO_MODELS
# Top-level route models for the current envelope: POST /api/v1/jobs/createTask.
# ONLY ai-music-api/* rides createTask; legacy dedicated routes stay dedicated.
AI_MUSIC_API_MODELS = ("ai-music-api/generate", "ai-music-api/extend",
                       "ai-music-api/upload-and-extend-audio",
                       "ai-music-api/generate-persona", "ai-music-api/sounds")
# Sounds input.model enum per the live registry snapshot (no V4 family).
SOUNDS_CURRENT_MODELS = ("V5", "V5_5", "V6", "V6_WILD", "V6_MINI")
SUNO_CUSTOM_PROMPT_MAX = {
    "V4": 3000,
    "V4_5": 5000, "V4_5PLUS": 5000, "V4_5ALL": 5000, "V5": 5000, "V5_5": 5000,
    "V6": 5000, "V6_MINI": 5000, "V6_WILD": 5000,
}
# Non-custom song description: the generate-music page says 3000, the generate-mashup page says 500, and the
# conflict is unresolved (UNDETERMINED). Rule 12: an unknown limit has NO floor, and the ceiling is the smallest
# documented value, so the field is checked ceiling-only at 500 until the owner settles it.
SUNO_NON_CUSTOM_PROMPT_DOCUMENTED = (500, 3000)
SUNO_NON_CUSTOM_PROMPT_MAX = min(SUNO_NON_CUSTOM_PROMPT_DOCUMENTED)
SUNO_CUSTOM_STYLE_MAX = {"V4": 200, "V4_5": 1000, "V4_5PLUS": 1000,
                         "V4_5ALL": 1000, "V5": 1000, "V5_5": 1000,
                         "V6": 1000, "V6_MINI": 1000, "V6_WILD": 1000}
SUNO_TITLE_MAX = 80                 # generate: "title length limit: 80 characters (all models)"
SUNO_V55_DURATION = (10, 360)       # legacy note said V5_5-only; live docs add the V6 family (custom only)
SUNO_DURATION_MODELS = ("V5_5", "V6", "V6_MINI", "V6_WILD")  # duration effective: custom_mode true + one of these
SUNO_SOUNDS_PROMPT_MAX = 500
SUNO_SOUND_TEMPO = (1, 300)
SUNO_PERSONA_WINDOW = (10, 30)      # vocalEnd-vocalStart 10-30s
SUNO_MASHUP_URLS = 2                # "must contain exactly 2 audio file URLs"
SUNO_REPLACE_MIN_SEC = 10           # replacement min 10 sec
SUNO_REPLACE_MAX_PCT = 50           # max 50% of original duration
SUNO_VOCAL_REMOVAL_MAX_MB = 20      # audioUrl max 20MB

CREDIT_NAMES = {"separate_vocal": 10, "split_stem": 50, "split_stem_advanced": 20}

errors = []
warnings = []  # advisory only -- does not affect the exit code

def _err(msg):
    errors.append(msg)

def _warn(msg):
    warnings.append(msg)

def _descriptive(label, model, text, cap):
    """Rule 12 for a descriptive music field through the shared enforcer. `cap` is the first-party character
    limit (the policy-owner fallback when Skill 74 has no schema for this dedicated Suno route)."""
    v = KPE.check("suno/%s" % model, text if isinstance(text, str) else "", "descriptive", fallback_max=cap)
    if not v["ok"]:
        _err("music: %s: %s" % (label, v["message"]))
    elif v["status"] == "BELOW_TARGET":
        _warn("music: %s is %d chars; the target is 95-100%% of %d (add %d chars)" % (
            label, v["chars"], cap, v["target_min"] - v["chars"]))


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]

def _txt_len(s):
    return len(s) if isinstance(s, str) else 0


# Known-field vocabulary per route, mirrored from the 66-kie-image post-fix
# pattern: built from the route's models.json caps / references/tts.md schemas
# plus the universal fields this file validates. Unknown keys WARN only --
# advisory, exit stays 0 for warning-only paths (SKILL.md exit contract).
KNOWN_TOP_FIELDS = {"model", "input", "callBackUrl"}
GEMINI_INPUT_FIELDS = {"temperature", "speakers", "dialogue_turns"}
GEMINI_SPEAKER_FIELDS = {"speaker_id", "voice_name", "accent", "style", "pace"}
GEMINI_TURN_FIELDS = {"speaker_id", "text"}
EL_DIALOGUE_INPUT_FIELDS = {"dialogue", "stability", "language_code"}
EL_TTS_INPUT_FIELDS = {"text", "voice", "stability", "similarity_boost", "style",
                       "speed", "timestamps", "previous_text", "next_text",
                       "language_code"}
EL_DIALOGUE_ITEM_FIELDS = {"text", "voice"}

def _warn_unknown_fields(obj, known, label):
    if not isinstance(obj, dict):
        return
    for k in obj.keys():
        if k not in known:
            _warn(f"tts: unknown {label} field {k!r} not in the documented schema "
                  "(advisory; dispatch proceeds if no hard errors)")


# ---------------------------------------------------------------------------
# TTS sub-domain
# ---------------------------------------------------------------------------

def _validate_tts_via_adapter(p, model):
    """A TTS model not in models.json (a live model KIE added later): Skill 74 validates the payload against the
    live schema (registry snapshot fallback). Only an explicitly named model is checked; it is never selected or
    made a default. Returns True when Skill 74 answered (errors/warnings recorded), False to fall through."""
    inp = p.get("input")
    if not isinstance(inp, dict):
        return False
    got = adapter_bridge.validate(model, inp)
    if not got:
        return False
    if got.get("state") == "validated":
        cap = got.get("capability") or ""
        # Text to Speech only. Anything that is speech to text (the closed STT gate) or unknown is refused.
        if re.search(r"speech[ -]to[ -]text", cap, re.I) or not re.search(r"text[ -]to[ -]speech", cap, re.I):
            _err(f"tts: model {model!r} is not a Text to Speech model per Skill 74 "
                 f"(capability {cap or 'unknown'}); refusing")
        else:
            _warn(f"tts: model {model!r} is not in models.json; validated by Skill 74 against its schema "
                  "(explicit pick only, never auto-default)")
        return True
    if got.get("error"):
        _err("tts: Skill 74 schema validation: %s" % got["error"].get("msg"))
        return True
    return False


def validate_tts(p):
    model = p.get("model")
    if model not in GEMINI_TTS_MODELS + ELEVENLABS_MODELS:
        if isinstance(model, str) and model and _validate_tts_via_adapter(p, model):
            return
        _err(f"tts: unknown or unsupported model {model!r}; expect one of "
             f"{', '.join(GEMINI_TTS_MODELS + ELEVENLABS_MODELS)}")
        return
    inp = p.get("input")
    if not isinstance(inp, dict):
        _err("tts: 'input' object is required")
        return

    # API family guard: TTS must ride the generic Market createTask route.
    top = set(p.keys())
    if "callBackUrl" not in top:
        _warn("tts: callBackUrl absent -- polling via recordInfo is the documented fallback")
    if "input" not in top:
        _err("tts: payload has no 'input' -- Suno-style flat payload rejected here")
        return

    if model in GEMINI_TTS_MODELS:
        _validate_gemini_tts(p, inp)
    else:
        _validate_elevenlabs_tts(p, inp)


def _validate_gemini_tts(p, inp):
    temp = inp.get("temperature")
    if temp is not None:
        if not isinstance(temp, (int, float)) or not (GEMINI_TEMP_MIN <= temp <= GEMINI_TEMP_MAX):
            _err(f"tts: temperature must be number {GEMINI_TEMP_MIN}-{GEMINI_TEMP_MAX} (default 1), got {temp!r}")

    speakers = inp.get("speakers")
    if not isinstance(speakers, list) or not speakers:
        _err("tts: 'speakers' array is required for Gemini TTS")
        speakers = []
    for s in speakers:
        if not isinstance(s, dict):
            _err("tts: each speakers[] item must be an object")
            continue
        sid = s.get("speaker_id")
        if not isinstance(sid, str) or not SPEAKER_ID_RE.match(sid):
            _err(f"tts: speaker_id must match 'Speaker N' format (e.g. 'Speaker 1'), got {sid!r}")
        vn = s.get("voice_name")
        if vn not in GEMINI_VOICES:
            _err(f"tts: voice_name {vn!r} not in the 30-voice enum")
        ac = s.get("accent")
        if ac is not None and ac not in GEMINI_ACCENTS:
            _err(f"tts: accent {ac!r} not in the 8-accent enum")
        st = s.get("style")
        if st is not None and st not in GEMINI_STYLES:
            _err(f"tts: style {st!r} not in the 6-style enum")
        pc = s.get("pace")
        if pc is not None and pc not in GEMINI_PACES:
            _err(f"tts: pace {pc!r} not in the 4-pace enum")

    turns = inp.get("dialogue_turns")
    if not isinstance(turns, list) or not turns:
        _err("tts: 'dialogue_turns' array is required for Gemini TTS")
        turns = []
    total = 0
    for t in turns:
        if not isinstance(t, dict):
            _err("tts: each dialogue_turns[] item must be an object")
            continue
        sid = t.get("speaker_id")
        if not isinstance(sid, str) or not SPEAKER_ID_RE.match(sid):
            _err(f"tts: dialogue_turns[].speaker_id must be 'Speaker N', got {sid!r}")
        text = t.get("text", "")
        n = _txt_len(text)
        total += n
        if n > GEMINI_PER_TURN_MAX:
            _err(f"tts: dialogue_turns[].text is {n} chars > {GEMINI_PER_TURN_MAX} per-turn max")
        elif n > 9500:
            _warn(f"tts: per-turn text {n} chars is above the ~9500 safe ceiling (rule B, 10000 hard cap)")

    # House band note: per-turn 10000 governs; combined production script is
    # NOT capped by a single field, so a band warning is informational.
    if total > 0:
        _warn(f"tts: combined dialogue script {total} chars across {len(turns)} turns "
              "(per-turn 10000 governs; split turns to stay legal)")


def _validate_elevenlabs_tts(p, inp):
    model = p["model"]
    # Unknown-field advisory: warn on top-level keys the schemas do not document
    # (verified 2026-08-27 -- typical first cause of a silent 422 on dispatch).
    known_top = {"model", "input", "callBackUrl"}
    unknown = [k for k in p if k not in known_top and not k.startswith("_")]
    if unknown:
        _warn(f"tts: unknown top-level field(s) {', '.join(sorted(unknown))} -- not in the "
              f"documented schema for {model}; remove or rename before dispatch")
    if model == "elevenlabs/text-to-dialogue-v3":
        dialogue = inp.get("dialogue")
        if not isinstance(dialogue, list) or not dialogue:
            _err("tts: input.dialogue[] required for dialogue-v3")
            dialogue = []
        combined = 0
        for d in dialogue:
            if not isinstance(d, dict):
                _err("tts: each dialogue[] item must be an object")
                continue
            combined += _txt_len(d.get("text"))
        if combined > EL_DIALOGUE_COMBINED_MAX:
            _err(f"tts: dialogue-v3 combined text is {combined} chars > "
                 f"{EL_DIALOGUE_COMBINED_MAX} (\"total character count of all text fields "
                 f"combined must not exceed 5000 characters.\")")
        elif combined > 4900:
            _warn(f"tts: dialogue-v3 combined {combined} chars above 4900 safe ceiling (rule B)")
        # previous_text/next_text apply to ALL ElevenLabs models, dialogue-v3 included
        # (same 5000-char schema max; verified 2026-08-27).
        prev_d = _txt_len(inp.get("previous_text"))
        nxt_d = _txt_len(inp.get("next_text"))
        if prev_d > EL_TEXT_MAX:
            _err(f"tts: previous_text {prev_d} chars > {EL_TEXT_MAX}")
        if nxt_d > EL_TEXT_MAX:
            _err(f"tts: next_text {nxt_d} chars > {EL_TEXT_MAX}")
        stab = inp.get("stability")
        if stab is not None and stab not in EL_STABILITY_ENUM:
            _err(f"tts: stability must be one of 0/0.5/1 (default 0.5), got {stab!r}")
    else:
        text = inp.get("text", "")
        n = _txt_len(text)
        if n > EL_TEXT_MAX:
            _err(f"tts: {model} text is {n} chars > {EL_TEXT_MAX}")
        elif n > 4900:
            _warn(f"tts: {model} text {n} chars above 4900 safe ceiling (rule B)")
        prev = _txt_len(inp.get("previous_text"))
        nxt = _txt_len(inp.get("next_text"))
        if prev > EL_TEXT_MAX:
            _err(f"tts: previous_text {prev} chars > {EL_TEXT_MAX}")
        if nxt > EL_TEXT_MAX:
            _err(f"tts: next_text {nxt} chars > {EL_TEXT_MAX}")
        speed = inp.get("speed")
        if speed is not None:
            try:
                speed_ok = EL_SPEED_MIN <= float(speed) <= EL_SPEED_MAX
            except (TypeError, ValueError):
                speed_ok = False
            if not speed_ok:
                _err(f"tts: speed must be {EL_SPEED_MIN}-{EL_SPEED_MAX} (default 1), got {speed!r}")
        # dialogue-v3 fields apply per input.text too; non-dialogue EL models document
        # language_code (2-char, max 500 chars on the add-language route is wrong here --
        # the TTS schema's language field is a 2-letter code, not free text; cap the raw
        # value at the documented input length to stay safe).
        lang = inp.get("language_code") or inp.get("languageCode")
        if lang is not None and _txt_len(lang) > 500:
            _err(f"tts: language_code {_txt_len(lang)} chars > 500")


# ---------------------------------------------------------------------------
# Music sub-domain (Suno dedicated family)
# ---------------------------------------------------------------------------

def validate_music(p):
    # Two Suno routes (W0-02 contract, live docs 2026-10-06):
    # CURRENT: POST /api/v1/jobs/createTask with top-level model ai-music-api/*
    # (version nested at input.model, default V6).
    # LEGACY: dedicated /api/v1/generate family (V4..V5_5, marked Discontinued
    # on the live pages -- accepted with a warning, never dropped).
    endpoint = p.get("endpoint") or _infer_endpoint(p)
    if not endpoint:
        _warn("music: no 'endpoint' field in payload; endpoint inferred from required fields")

    if "createTask" in endpoint:
        return _validate_ai_music_envelope(p)

    model = p.get("model")
    if model not in SUNO_MODELS:
        _err(f"music: model must be one of {', '.join(SUNO_MODELS)}, got {model!r}")
        return
    if model in LEGACY_SUNO_MODELS:
        _warn(f"music: model {model} is marked Discontinued on the live KIE pages; "
              "the current family is V6/V6_MINI/V6_WILD")
    # Route/model coherence (repair cycle 2, owner policy): the legacy DEDICATED
    # routes (/api/v1/generate*) accept ONLY the legacy dedicated families
    # (references/music.md: "Legacy dedicated route models: V4..V5_5"). V6/current
    # families ride ONLY the market createTask envelope (ai-music-api/* or
    # input.model on top-level route). Crossing them is a hard reject.
    if model in CURRENT_SUNO_MODELS and "createTask" not in endpoint:
        _err("music: current Suno family (V6/V6_MINI/V6_WILD) rides ONLY the market "
             "createTask envelope (ai-music-api/* ids); the legacy dedicated routes "
             "/api/v1/generate* accept only V4..V5_5. Route/model mismatch -- rejected.")
        return

    op = _infer_operation(endpoint, p)

    if op in ("generate", "extend", "cover", "vocal-removal", "mp4", "wav"):
        if "callBackUrl" not in p:
            _err(f"music: callBackUrl is a required field for {op}")
    if "taskId" not in p and "audioId" not in p and "uploadUrlList" not in p:
        _warn("music: neither taskId/audioId/uploadUrlList present -- this looks like a "
              "generate call; required fields: prompt/customMode/instrumental/model/callBackUrl (non-custom)")

    if op == "sounds":
        validate_sounds(p)
    elif op == "extend":
        validate_extend(p)
    elif op == "mashup":
        validate_mashup(p)
    elif op == "replace-section":
        validate_replace_section(p)
    elif op == "generate-persona":
        validate_persona(p)
    elif op == "vocal-removal":
        validate_vocal_removal(p)
    elif op == "add-instrumental":
        validate_add_instrumental(p)
    elif op == "add-vocals":
        validate_add_vocals(p)
    elif op == "cover":
        validate_cover(p)
    elif op in ("mp4", "wav", "get-timestamped-lyrics"):
        validate_task_audio_ops(p, op)
    elif op in ("upload-cover", "upload-extend", "lyrics", "midi"):
        validate_generic_op_checks(p, op)
    else:
        validate_generate(p)


def _validate_ai_music_envelope(p):
    """Current Suno envelope: POST /api/v1/jobs/createTask, top-level model
    ai-music-api/*, version at input.model (live default V6). ONLY
    ai-music-api/* rides createTask; any other model on createTask is rejected."""
    model = p.get("model")
    if model not in AI_MUSIC_API_MODELS:
        _err("music: createTask carries Suno ONLY as ai-music-api/* "
             f"({', '.join(AI_MUSIC_API_MODELS)}), got {model!r}. "
             "Legacy Suno routes stay on the dedicated /api/v1/generate family.")
        return
    inp = p.get("input")
    if not isinstance(inp, dict):
        _err("music: createTask Suno envelope requires an 'input' object "
             "(route model at top-level 'model', version at 'input.model')")
        return
    ver = inp.get("model", "V6")  # live schema default
    if ver not in SUNO_MODELS:
        _err(f"music: input.model must be one of {', '.join(SUNO_MODELS)} (default V6), got {ver!r}")
        return
    if ver in LEGACY_SUNO_MODELS:
        _warn(f"music: input.model {ver} is marked Discontinued on the live KIE pages; "
              "the current family is V6/V6_MINI/V6_WILD")

    # Normalize snake_case envelope keys to the legacy camelCase shape and
    # delegate caps to the existing validators (one transport, one set of caps).
    norm = dict(inp)
    for snake, camel in (("custom_mode", "customMode"), ("vocal_gender", "vocalGender"),
                         ("negative_tags", "negativeTags"), ("style_weight", "styleWeight"),
                         ("weirdness_constraint", "weirdnessConstraint"),
                         ("audio_weight", "audioWeight"), ("persona_id", "personaId"),
                         ("persona_model", "personaModel"), ("continue_at", "continueAt"),
                         ("upload_url", "uploadUrl"), ("upload_url_list", "uploadUrlList"),
                         ("audio_id", "audioId"), ("task_id", "taskId"),
                         ("sound_loop", "soundLoop"), ("sound_tempo", "soundTempo"),
                         ("sound_key", "soundKey"), ("grab_lyrics", "grabLyrics"),
                         ("vocal_start", "vocalStart"), ("vocal_end", "vocalEnd"),
                         ("infill_start_s", "infillStartS"), ("infill_end_s", "infillEndS")):
        if snake in norm and camel not in norm:
            norm[camel] = norm[snake]
    norm["model"] = ver
    if p.get("callBackUrl") and "callBackUrl" not in norm:
        norm["callBackUrl"] = p["callBackUrl"]

    if model == "ai-music-api/generate":
        for f in ("custom_mode", "instrumental"):
            if f not in inp:
                _err(f"music: createTask generate requires input.{f} (live registry)")
                return
        norm["endpoint"] = "/api/v1/generate"
        validate_generate(norm)
    elif model == "ai-music-api/extend":
        for f in ("audio_id",):
            if f not in inp and "audioId" not in inp:
                _err("music: createTask extend requires input.audio_id (live registry)")
                return
        norm["endpoint"] = "/api/v1/generate/extend"
        validate_extend(norm)
    elif model == "ai-music-api/upload-and-extend-audio":
        if "upload_url" not in inp and "uploadUrl" not in inp:
            _err("music: createTask upload-and-extend-audio requires input.upload_url (live registry)")
            return
        if "callBackUrl" not in norm:
            _warn("music: upload-and-extend-audio without callBackUrl -- polling fallback undocumented for Suno")
        for f, cap in (("title", 100), ("prompt", 5000), ("lyrics", 5000), ("style", 1000)):
            v = norm.get(f)
            if v is not None and _txt_len(v) > cap:
                _err(f"music: upload-and-extend-audio {f} {_txt_len(v)} chars > {cap}")
    elif model == "ai-music-api/generate-persona":
        for f in ("task_id", "audio_id", "name", "description"):
            if f not in inp and f.replace("_", "") not in inp and f not in norm:
                _err(f"music: createTask generate-persona requires input.{f} (live registry)")
                return
        norm.setdefault("vocalStart", 0)  # live defaults
        norm.setdefault("vocalEnd", 30)
        validate_persona(norm)
    elif model == "ai-music-api/sounds":
        if "prompt" not in inp:
            _err("music: createTask sounds requires input.prompt (live registry)")
            return
        if ver not in SOUNDS_CURRENT_MODELS:
            _err(f"music: sounds input.model must be one of {', '.join(SOUNDS_CURRENT_MODELS)}, got {ver!r}")
            return
        norm["endpoint"] = "/api/v1/generate/sounds"
        validate_sounds(norm)


def _infer_endpoint(p):
    for k in ("endpoint", "url", "route"):
        v = p.get(k)
        if isinstance(v, str):
            return v
    return ""


def _infer_operation(endpoint, p):
    e = endpoint
    if "generate/sounds" in e or p.get("soundLoop") is not None:
        return "sounds"
    if "generate/extend" in e or p.get("audioId") is not None and "extend" in e:
        return "extend"
    if "mashup" in e or p.get("uploadUrlList") is not None:
        return "mashup"
    if "replace-section" in e or p.get("infillStartS") is not None:
        return "replace-section"
    if "generate-persona" in e or p.get("vocalStart") is not None:
        return "generate-persona"
    if "vocal-removal" in e or p.get("type") in CREDIT_NAMES:
        return "vocal-removal"
    if "add-instrumental" in e:
        return "add-instrumental"
    if "cover/generate" in e:
        return "cover"
    if "mp4" in e:
        return "mp4"
    if "wav" in e:
        return "wav"
    if "get-timestamped-lyrics" in e:
        return "get-timestamped-lyrics"
    if "upload-cover" in e:
        return "upload-cover"
    if "upload-extend" in e:
        return "upload-extend"
    if "add-vocals" in e:
        return "add-vocals"
    if "lyrics" in e or "/api/v1/lyrics" == e:
        return "lyrics"
    if "midi" in e:
        return "midi"
    return "generate"


def _validate_prompt_caps(p, model, prompt, style, title, custom_mode):
    if custom_mode:
        cap = SUNO_CUSTOM_PROMPT_MAX[model]
        if _txt_len(prompt) > cap:
            _err(f"music: custom prompt {_txt_len(prompt)} chars > {cap} for {model}")
        if style is not None:  # descriptive: rule 12 (floor 80 percent, ceiling 100 percent of the style max)
            _descriptive("style", model, style, SUNO_CUSTOM_STYLE_MAX[model])
    else:
        v = KPE.check("suno/%s" % model, prompt if isinstance(prompt, str) else "", "verbatim",
                      fallback_max=SUNO_NON_CUSTOM_PROMPT_MAX)  # unknown limit: no floor, smallest documented ceiling
        if not v["ok"]:
            _err("music: non-custom song description: %s" % v["message"])
        _warn("music: non-custom prompt limit UNDETERMINED -- generate-music page says 3000, generate-mashup page "
              "says 500; no floor is enforced and the ceiling is the smallest documented value (%d)"
              % SUNO_NON_CUSTOM_PROMPT_MAX)
    if title is not None and _txt_len(title) > SUNO_TITLE_MAX:
        _err(f"music: title {_txt_len(title)} chars > {SUNO_TITLE_MAX}")


def validate_generate(p):
    model = p["model"]
    custom_mode = p.get("customMode")
    if custom_mode is None:
        _err("music: customMode is a required field on generate")
        custom_mode = True  # continue validating with best-effort
    prompt = p.get("prompt", "")
    style = p.get("style")
    title = p.get("title")
    instrumental = p.get("instrumental")
    _validate_prompt_caps(p, model, prompt, style, title, bool(custom_mode))

    dur = p.get("duration")
    if dur is not None:
        lo, hi = SUNO_V55_DURATION
        if not (custom_mode and model in SUNO_DURATION_MODELS):
            _warn(f"music: duration={dur} ignored -- effective only when custom_mode is "
                  f"true and model is one of {', '.join(SUNO_DURATION_MODELS)} "
                  f"(got customMode={custom_mode}, model={model})")
        elif not (isinstance(dur, (int, float)) and lo <= dur <= hi):
            _warn(f"music: duration={dur} outside {lo}-{hi} (default 20) -- provider ignores "
                  "out-of-range duration (effective only for V5_5/V6-family custom)")

    if instrumental is True:
        if prompt:
            _warn("music: instrumental=true with a prompt is allowed on generate "
                  "(optional fields include prompt); instrumental-true PROHIBITS prompt only "
                  "on EXTEND")
    vg = p.get("vocalGender")
    if vg is not None and vg not in ("m", "f"):
        _err(f"music: vocalGender must be \"m\" or \"f\", got {vg!r}")
    lyr = p.get("lyrics")
    if lyr is not None and _txt_len(lyr) > 5000:
        _err(f"music: lyrics {_txt_len(lyr)} chars > 5000")
    pm = p.get("personaModel")
    if pm is not None and pm not in ("style_persona", "voice_persona"):
        _err(f"music: personaModel must be style_persona or voice_persona, got {pm!r}")


def validate_extend(p):
    model = p["model"]
    if "audioId" not in p:
        _err("music: audioId is a required field on extend")
    title = p.get("title")
    if title is not None:
        cap = {"V4": 80, "V4_5": 100, "V4_5PLUS": 100, "V4_5ALL": 80,
               "V5": 100, "V5_5": 100, "V6": 100, "V6_MINI": 100, "V6_WILD": 100}[model]
        if _txt_len(title) > cap:
            _err(f"music: extend title {_txt_len(title)} chars > {cap} for {model}")
    prompt = p.get("prompt", "")
    cap_p = SUNO_CUSTOM_PROMPT_MAX[model]
    if _txt_len(prompt) > cap_p:
        _err(f"music: extend prompt {_txt_len(prompt)} chars > {cap_p} for {model}")
    if p.get("instrumental") is True and (prompt or p.get("vocalGender")):
        _err("music: instrumental=true PROHIBITS passing prompt and vocalGender on extend")


def validate_sounds(p):
    model = p["model"]
    if model not in SOUNDS_CURRENT_MODELS:
        _err(f"music: sounds model must be one of {', '.join(SOUNDS_CURRENT_MODELS)}, got {model!r}")
    _descriptive("sounds prompt", model, p.get("prompt", ""), SUNO_SOUNDS_PROMPT_MAX)  # descriptive
    tempo = p.get("soundTempo")
    if tempo is not None:
        if not (SUNO_SOUND_TEMPO[0] <= tempo <= SUNO_SOUND_TEMPO[1]):
            _err(f"music: soundTempo must be {SUNO_SOUND_TEMPO[0]}-{SUNO_SOUND_TEMPO[1]} BPM, got {tempo!r}")


def validate_mashup(p):
    urls = _as_list(p.get("uploadUrlList") or p.get("uploadUrls"))
    if len(urls) != SUNO_MASHUP_URLS:
        _err(f"music: mashup uploadUrlList must contain exactly {SUNO_MASHUP_URLS} audio file URLs "
             f"(\"must contain exactly 2 audio file URLs\"), got {len(urls)}")


def validate_replace_section(p):
    s = p.get("infillStartS")
    e = p.get("infillEndS")
    if s is None or e is None:
        _err("music: replace-section requires infillStartS and infillEndS")
        return
    if not (s < e):
        _err("music: infillStartS must be < infillEndS")
    dur = p.get("totalDurationS") or p.get("duration")
    repl = p.get("replaceDurationS") or (e - s)
    if dur and repl:
        if repl < SUNO_REPLACE_MIN_SEC:
            _err(f"music: replacement {repl}s < minimum {SUNO_REPLACE_MIN_SEC}s")
        if repl > dur * SUNO_REPLACE_MAX_PCT / 100.0:
            _err(f"music: replacement {repl}s exceeds {SUNO_REPLACE_MAX_PCT}% of original "
                 f"duration {dur}s")


def validate_persona(p):
    vs = p.get("vocalStart")
    ve = p.get("vocalEnd")
    if vs is None or ve is None:
        _err("music: generate-persona requires vocalStart and vocalEnd")
        return
    window = ve - vs
    if not (SUNO_PERSONA_WINDOW[0] <= window <= SUNO_PERSONA_WINDOW[1]):
        _err(f"music: persona vocal window must be {SUNO_PERSONA_WINDOW[0]}-{SUNO_PERSONA_WINDOW[1]}s "
             f"(vocalEnd-vocalStart), got {window}s")


def validate_vocal_removal(p):
    t = p.get("type")
    if t not in CREDIT_NAMES:
        _err(f"music: vocal-removal type must be one of {', '.join(CREDIT_NAMES)}, got {t!r}")
    else:
        _warn(f"music: vocal-removal type {t} costs {CREDIT_NAMES[t]} credits (source page)")
    _validate_audio_url_size(p)


def _validate_audio_url_size(p):
    for k in ("audioUrl", "mp3Url"):
        v = p.get(k)
        if isinstance(v, str) and v.startswith("data:"):
            _err("music: data-URI audio uploads are not documented; use a hosted URL")


def validate_add_instrumental(p):
    if p.get("negativeTags") is not None and _txt_len(p.get("negativeTags")) > 200:
        _err("music: add-instrumental negativeTags max 200 chars")
    if p.get("tags") is not None:  # descriptive: rule 12
        _descriptive("add-instrumental tags", p.get("model") or "V5", p.get("tags"), 1000)

def validate_add_vocals(p):
    # add-vocals rides the same per-field limits as add-instrumental (same
    # audio-operations family, verified 2026-08-27 against references/).
    if p.get("negativeTags") is not None and _txt_len(p.get("negativeTags")) > 200:
        _err("music: add-vocals negativeTags max 200 chars")
    if p.get("style") is not None:  # descriptive: rule 12
        _descriptive("add-vocals style", p.get("model") or "V5", p.get("style"), 1000)
    if "audioId" not in p and "taskId" not in p:
        _err("music: add-vocals requires taskId/audioId")


def validate_cover(p):
    _warn("music: cover is a one-per-task generation (\"Each music task can only generate "
          "a Cover once\") -- second generation is prohibited")


def validate_task_audio_ops(p, op):
    if "audioId" not in p and "taskId" not in p:
        _err(f"music: {op} requires taskId/audioId")
    if op == "mp4":
        for f in ("author", "domainName"):
            v = p.get(f)
            if v is not None and _txt_len(v) > 50:
                _err(f"music: {f} max 50 chars (got {_txt_len(v)})")
    if op == "get-timestamped-lyrics" and p.get("instrumental"):
        _warn("music: instrumental tracks return no timestamped lyrics")


def validate_generic_op_checks(p, op):
    srcs = {
        "upload-cover": ["uploadUrl"],
        "upload-extend": ["audioId", "continueAt"],
        "add-vocals": [],
        "lyrics": [],
        "midi": ["taskId"],
    }
    for f in srcs.get(op, []):
        if f not in p:
            _err(f"music: {op} requires {f}")
    if op == "upload-cover" and p.get("customMode") is False and _txt_len(p.get("prompt", "")) > 500:
        _err("music: upload-cover non-custom prompt limit 500 chars")
    if op == "midi":
        _warn("music: midi generation requires a COMPLETED vocal-separation taskId")


# ---------------------------------------------------------------------------
# Stt sub-domain -- deliberately refuses to fabricate
# ---------------------------------------------------------------------------

STT_NEGATIVE_TRAIL = (
    "ADVERTISED_NOT_YET_VERIFIED -- dispatch disabled; no endpoint. Negative-result "
    "trail (2026-08-26): docs.kie.ai/sitemap.xml (EN+CN, ~460 URLs) zero hits for "
    "stt, asr, transcribe, transcription, whisper, speech-to-text, deepgram, google/speech; "
    "elevenlabs docs dir = exactly 4 models, all TTS/audio-isolation, none STT; "
    "kie.ai/market returned HTTP 403 to WebFetch; WebSearch variants returned zero. "
    "NOT checked: off-docs endpoints (cannot be ruled in or out). Do NOT fabricate "
    "an endpoint. Reference: references/stt.md"
)


def validate_stt(p):
    if p.get("dispatch") or p.get("model") or p.get("endpoint"):
        _err(f"stt: dispatch attempt rejected -- {STT_NEGATIVE_TRAIL}")
        return
    print("[stt] " + STT_NEGATIVE_TRAIL)
    cands = adapter_bridge.stt_candidates()  # free catalog GET; report only
    if cands is None:
        print("[stt] live catalog check: Skill 74 unavailable; status unchanged")
    elif cands:
        print("[stt] live catalog check (free GET): possible speech-to-text model(s): "
              + ", ".join(str(c.get("model")) for c in cands)
              + ". REPORT ONLY: dispatch_enabled stays false until the re-proof in references/stt.md passes.")
    else:
        print("[stt] live catalog check (free GET): no speech-to-text model in the live catalog")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="KIE audio pre-dispatch validator (Skill 68)")
    ap.add_argument("--domain", choices=["tts", "music", "stt"])
    ap.add_argument("--payload", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if args.domain is None or args.payload is None or not args.payload.is_file():
        print("error: --domain <tts|music|stt> and --payload <file.json> required "
              "(or --self-test)", file=sys.stderr)
        return 2
    p = json.loads(args.payload.read_text(encoding="utf-8"))

    if args.domain == "tts":
        validate_tts(p)
    elif args.domain == "music":
        validate_music(p)
    else:
        validate_stt(p)

    for w in warnings:
        print(f"  WARN: {w}")
    for e in errors:
        print(f"  ERROR: {e}")
    if errors:
        print(f"VALIDATION FAILED ({len(errors)} error(s)) -- do NOT dispatch")
        return 2
    print(f"VALIDATION PASSED ({len(warnings)} advisory warning(s))")
    return 0


def _expect_exit(path, domain, want, env=None, expect_out=None):
    import subprocess
    r = subprocess.run([sys.executable, __file__, "--domain", domain, "--payload", str(path)],
                       capture_output=True, text=True, env=env)
    rc = r.returncode
    if rc != want:
        raise SystemExit(f"SELF-TEST FAIL: {path.name} ({domain}) rc={rc} want={want}\n{r.stdout}\n{r.stderr}")
    if expect_out and expect_out not in r.stdout:
        raise SystemExit(f"SELF-TEST FAIL: {path.name} ({domain}) output lacks {expect_out!r}\n{r.stdout}")


def _fake_adapter_env(td, answers):
    """Env whose KIE_LIVE_ADAPTER_PATH is a stand-in Skill 74 answering by subcommand (validate, discover)."""
    script = td / "kie_live_adapter.py"
    (td / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
    script.write_text("import json, os, sys\n"
                      "a = json.load(open(os.path.join(os.path.dirname(__file__), 'answers.json')))\n"
                      "sys.stdout.write(json.dumps(a.get(sys.argv[1], {})))\n", encoding="utf-8")
    return dict(os.environ, KIE_LIVE_ADAPTER_PATH=str(script))


def self_test():
    import tempfile
    ok = 0
    os.environ["HOME"] = tempfile.mkdtemp()  # hermetic: no key and no cache, the adapter answers from its registry
    os.environ.pop("KIE_API_KEY", None)
    os.environ["KIE_LIVE_ADAPTER_PATH"] = ""  # hermetic: no sibling adapter, no network (children inherit)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        def write(name, obj):
            f = td / name
            f.write_text(json.dumps(obj), encoding="utf-8")
            return f

        # Gemini: 10000-char turn OK / 10001 exit 2
        gem_base = {
            "model": "google/gemini-3-1-flash-tts", "callBackUrl": "https://x/cb",
            "input": {"speakers": [{"speaker_id": "Speaker 1",
                                    "voice_name": "Achernar", "accent": "Neutral"}],
                      "dialogue_turns": []},
        }
        g1 = json.loads(json.dumps(gem_base)); g1["input"]["dialogue_turns"].append(
            {"speaker_id": "Speaker 1", "text": "x" * 10000})
        g2 = json.loads(json.dumps(gem_base)); g2["input"]["dialogue_turns"].append(
            {"speaker_id": "Speaker 1", "text": "x" * 10001})
        _expect_exit(write("g-ok.json", g1), "tts", 0)
        _expect_exit(write("g-err.json", g2), "tts", 2)

        # ElevenLabs dialogue: 5000 combined OK / 5001 exit 2
        el_base = {"model": "elevenlabs/text-to-dialogue-v3",
                   "callBackUrl": "https://x/cb", "input": {"dialogue": []}}
        e1 = json.loads(json.dumps(el_base)); e1["input"]["dialogue"].append({"text": "x" * 5000})
        e2 = json.loads(json.dumps(el_base)); e2["input"]["dialogue"] = [
            {"text": "x" * 2500}, {"text": "x" * 2501}]
        _expect_exit(write("el-ok.json", e1), "tts", 0)
        _expect_exit(write("el-err.json", e2), "tts", 2)

        # Suno V4 custom 3000 OK / 3001 exit 2
        s1 = {"endpoint": "/api/v1/generate", "model": "V4", "customMode": True,
              "instrumental": False, "prompt": "x" * 3000, "title": "t",
              "callBackUrl": "https://x/cb"}
        s2 = dict(s1); s2["prompt"] = "x" * 3001
        _expect_exit(write("suno-ok.json", s1), "music", 0)
        _expect_exit(write("suno-err.json", s2), "music", 2)

        # V5_5 duration 8 -> warning ignored (rc 0)
        s3 = {"endpoint": "/api/v1/generate", "model": "V5_5", "customMode": True,
              "instrumental": False, "prompt": "p", "duration": 8,
              "callBackUrl": "https://x/cb"}
        _expect_exit(write("suno-dur8.json", s3), "music", 0)

        # Sounds 500 OK / 501 exit 2
        so1 = {"endpoint": "/api/v1/generate/sounds", "model": "V5",
               "prompt": "x" * 500, "soundTempo": 166}
        so2 = dict(so1); so2["prompt"] = "x" * 501
        _expect_exit(write("sounds-ok.json", so1), "music", 0)
        _expect_exit(write("sounds-err.json", so2), "music", 2)

        # Mashup 3 URLs exit 2 (exactly 2 required)
        m1 = {"endpoint": "/api/v1/generate/mashup", "model": "V5",
              "uploadUrlList": ["https://a/1.mp3", "https://a/2.mp3", "https://a/3.mp3"],
              "callBackUrl": "https://x/cb"}
        _expect_exit(write("mashup-3.json", m1), "music", 2)

        # STT dispatch attempt exit 2
        _expect_exit(write("stt-attempt.json", {"model": "elevenlabs/stt", "dispatch": True}),
                     "stt", 2)
        # STT inspect-only (no dispatch) exit 0
        _expect_exit(write("stt-inspect.json", {}), "stt", 0)

        # Bad accent exit 2; speed 1.5 exit 2
        bad1 = json.loads(json.dumps(gem_base)); bad1["input"]["speakers"][0]["accent"] = "Klingon"
        _expect_exit(write("bad-accent.json", bad1), "tts", 2)
        bad2 = {"model": "elevenlabs/text-to-speech-multilingual-v2",
                "callBackUrl": "https://x/cb",
                "input": {"text": "hello", "speed": 1.5}}
        _expect_exit(write("bad-speed.json", bad2), "tts", 2)

        # Non-ai-music-api model on createTask -> exit 2 (only ai-music-api/* rides createTask)
        bad3 = {"endpoint": "/api/v1/jobs/createTask", "model": "V5",
                "input": {"prompt": "x"}, "callBackUrl": "https://x/cb"}
        _expect_exit(write("suno-viacreatetask.json", bad3), "music", 2)

        # CURRENT envelope (W0-02 contract): createTask + ai-music-api/generate, V6 default
        cg = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/generate",
              "input": {"custom_mode": True, "instrumental": False, "model": "V6",
                        "style": "x" * 950, "title": "t",
                        "lyrics": "verbatim lyrics are exempt from the floor"},
              "callBackUrl": "https://x/cb"}
        _expect_exit(write("cur-gen-ok.json", cg), "music", 0)
        # Legacy version on the legacy route: accepted with a Discontinued warning, rc 0
        cg_leg = {"endpoint": "/api/v1/generate", "model": "V4_5", "customMode": True,
                  "instrumental": False, "prompt": "lyrics are verbatim and exempt from the floor",
                  "style": "x" * 950, "title": "t", "callBackUrl": "https://x/cb"}
        _expect_exit(write("legacy-v45-ok.json", cg_leg), "music", 0, expect_out="Discontinued")
        # Legacy version inside the current envelope: same warning, rc 0
        cg_leg2 = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/generate",
                   "input": {"custom_mode": True, "instrumental": False, "model": "V5_5",
                             "style": "x" * 950, "title": "t", "duration": 30},
                   "callBackUrl": "https://x/cb"}
        _expect_exit(write("cur-gen-v55-ok.json", cg_leg2), "music", 0, expect_out="Discontinued")
        # V6 on the legacy dedicated route: REJECTED (route/model coherence, repair cycle 2)
        cg_v6leg = {"endpoint": "/api/v1/generate", "model": "V6", "customMode": True,
                    "instrumental": False, "prompt": "lyrics are verbatim and exempt",
                    "style": "x" * 950, "title": "t", "duration": 30,
                    "callBackUrl": "https://x/cb"}
        _expect_exit(write("legacy-route-v6-bad.json", cg_v6leg), "music", 2)
        # Current envelope missing a required input field -> exit 2
        cg_bad = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/generate",
                  "input": {"instrumental": False, "model": "V6"}, "callBackUrl": "https://x/cb"}
        _expect_exit(write("cur-gen-nocustom.json", cg_bad), "music", 2)
        # Current envelope unknown version -> exit 2
        cg_bad2 = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/generate",
                   "input": {"custom_mode": True, "instrumental": False, "model": "V9"},
                   "callBackUrl": "https://x/cb"}
        _expect_exit(write("cur-gen-badver.json", cg_bad2), "music", 2)
        # Current envelope without an input object -> exit 2
        cg_bad3 = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/generate",
                   "callBackUrl": "https://x/cb"}
        _expect_exit(write("cur-gen-noinput.json", cg_bad3), "music", 2)
        # Lyrics over 5000 -> exit 2; bad personaModel -> exit 2
        cg_bad4 = dict(cg); cg_bad4["input"] = dict(cg["input"]); cg_bad4["input"]["lyrics"] = "x" * 5001
        _expect_exit(write("cur-gen-biglyrics.json", cg_bad4), "music", 2)
        cg_bad5 = dict(cg); cg_bad5["input"] = dict(cg["input"]); cg_bad5["input"]["persona_model"] = "dj"
        _expect_exit(write("cur-gen-badpersona.json", cg_bad5), "music", 2)
        # Current sounds: V6 passes, V4 rejected (sounds enum has no V4 family)
        cs = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/sounds",
              "input": {"model": "V6", "prompt": "x" * 475, "sound_tempo": 120},
              "callBackUrl": "https://x/cb"}
        _expect_exit(write("cur-sounds-ok.json", cs), "music", 0)
        cs_bad = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/sounds",
                  "input": {"model": "V4", "prompt": "x" * 475}, "callBackUrl": "https://x/cb"}
        _expect_exit(write("cur-sounds-v4.json", cs_bad), "music", 2)
        # Current persona: full fields pass (10-30s window), missing fields exit 2
        cp = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/generate-persona",
              "input": {"task_id": "t1", "audio_id": "a1", "name": "n", "description": "d",
                        "vocal_start": 5, "vocal_end": 25}, "callBackUrl": "https://x/cb"}
        _expect_exit(write("cur-persona-ok.json", cp), "music", 0)
        cp_bad = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/generate-persona",
                  "input": {"name": "n"}, "callBackUrl": "https://x/cb"}
        _expect_exit(write("cur-persona-missing.json", cp_bad), "music", 2)
        # Current extend: audio_id passes, missing audio_id exits 2
        ce = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/extend",
              "input": {"audio_id": "a1", "model": "V6", "continue_at": 32},
              "callBackUrl": "https://x/cb"}
        _expect_exit(write("cur-extend-ok.json", ce), "music", 0)
        ce_bad = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/extend",
                  "input": {"model": "V6"}, "callBackUrl": "https://x/cb"}
        _expect_exit(write("cur-extend-missing.json", ce_bad), "music", 2)
        # Current upload-and-extend: upload_url passes, missing upload_url exits 2
        cu = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/upload-and-extend-audio",
              "input": {"upload_url": "https://res.example.com/src.mp3", "model": "V6_WILD",
                        "title": "t"}, "callBackUrl": "https://x/cb"}
        _expect_exit(write("cur-upext-ok.json", cu), "music", 0)
        cu_bad = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/upload-and-extend-audio",
                  "input": {"model": "V6"}, "callBackUrl": "https://x/cb"}
        _expect_exit(write("cur-upext-missing.json", cu_bad), "music", 2)

        # speed non-numeric -> exit 2 (was ValueError traceback rc=1 before the try/except)
        bad4 = {"model": "elevenlabs/text-to-speech-multilingual-v2",
                "callBackUrl": "https://x/cb",
                "input": {"text": "hello", "speed": "fast"}}
        _expect_exit(write("bad-speed-str.json", bad4), "tts", 2)
        # speed boundary 1.2 OK
        ok_speed = {"model": "elevenlabs/text-to-speech-multilingual-v2",
                    "callBackUrl": "https://x/cb",
                    "input": {"text": "hello", "speed": 1.2}}
        _expect_exit(write("ok-speed-max.json", ok_speed), "tts", 0)
        # unknown top-level key -> warn only, rc 0
        unk = {"model": "elevenlabs/text-to-speech-turbo-2-5",
               "callBackUrl": "https://x/cb", "input": {"text": "hi"},
               "bogus_key": 1}
        _expect_exit(write("unknown-key.json", unk), "tts", 0)
        # previous_text 6000 chars -> exit 2 (5000 cap, applies on the non-dialogue path)
        big_prev = {"model": "elevenlabs/text-to-speech-turbo-2-5",
                    "callBackUrl": "https://x/cb",
                    "input": {"text": "hi", "previous_text": "x" * 6000}}
        _expect_exit(write("big-prev.json", big_prev), "tts", 2)
        # add-vocals with oversized style -> exit 2
        av1 = {"endpoint": "/api/v1/generate/add-vocals", "model": "V5",
               "taskId": "t1", "style": "x" * 1001, "callBackUrl": "https://x/cb"}
        _expect_exit(write("addvoc-style.json", av1), "music", 2)
        # add-vocals negativeTags 201 -> exit 2 (models.json:290 cap 200)
        av1b = {"endpoint": "/api/v1/generate/add-vocals", "model": "V5",
                "taskId": "t1", "negativeTags": "x" * 201, "callBackUrl": "https://x/cb"}
        _expect_exit(write("addvoc-negtags.json", av1b), "music", 2)
        # add-vocals missing taskId/audioId -> exit 2
        av2 = {"endpoint": "/api/v1/generate/add-vocals", "model": "V5",
               "style": "pop", "callBackUrl": "https://x/cb"}
        _expect_exit(write("addvoc-notask.json", av2), "music", 2)
        # add-vocals complete -> rc 0
        av3 = {"endpoint": "/api/v1/generate/add-vocals", "model": "V5",
               "taskId": "t1", "callBackUrl": "https://x/cb"}
        _expect_exit(write("addvoc-ok.json", av3), "music", 0)

        # Rule 12 for DESCRIPTIVE music fields: Suno V5 custom style max 1000 -> floor 800, ceiling 1000.
        def style_req(n):
            return {"endpoint": "/api/v1/generate", "model": "V5", "customMode": True, "instrumental": False,
                    "prompt": "lyrics are verbatim and exempt from the floor", "style": "x" * n,
                    "title": "t", "callBackUrl": "https://x/cb"}
        _expect_exit(write("style-79.json", style_req(790)), "music", 2)    # 79 percent rejected
        _expect_exit(write("style-80.json", style_req(800)), "music", 0)    # 80 percent floor passes (target warning)
        _expect_exit(write("style-95.json", style_req(950)), "music", 0)    # 95 percent passes
        _expect_exit(write("style-100.json", style_req(1000)), "music", 0)  # 100 percent passes
        _expect_exit(write("style-101.json", style_req(1001)), "music", 2)  # 101 percent rejected
        # non-custom song description: limit UNDETERMINED (500 vs 3000), so no floor and the ceiling is 500
        nc = {"endpoint": "/api/v1/generate", "model": "V5", "customMode": False, "instrumental": False,
              "prompt": "x" * 20, "callBackUrl": "https://x/cb"}
        _expect_exit(write("noncustom-short.json", nc), "music", 0)      # no floor on an unknown limit
        nc2 = dict(nc); nc2["prompt"] = "x" * 500
        _expect_exit(write("noncustom-500.json", nc2), "music", 0)       # a 500-char description must pass
        nc3 = dict(nc); nc3["prompt"] = "x" * 501
        _expect_exit(write("noncustom-501.json", nc3), "music", 2)       # over the smallest documented value
        # sounds prompt (max 500): 79 percent rejected, 95 percent passes
        so3 = {"endpoint": "/api/v1/generate/sounds", "model": "V5", "prompt": "x" * 395, "soundTempo": 120}
        _expect_exit(write("sounds-79.json", so3), "music", 2)
        so4 = dict(so3); so4["prompt"] = "x" * 475
        _expect_exit(write("sounds-95.json", so4), "music", 0)
        # the exact add/cut counts appear in the report
        import subprocess
        r = subprocess.run([sys.executable, __file__, "--domain", "music", "--payload", str(td / "style-79.json")],
                           capture_output=True, text=True)
        if "ADD at least 10" not in r.stdout:
            raise SystemExit("SELF-TEST FAIL: style floor message must name the exact chars to add (10)\n" + r.stdout)
        # verbatim TTS text keeps only its ceiling: a short script is fine
        _expect_exit(write("tts-short.json", {"model": "elevenlabs/text-to-speech-turbo-2-5",
                                              "callBackUrl": "https://x/cb", "input": {"text": "hi"}}), "tts", 0)


        # Skill 74 wiring (fake adapter): a live TTS model not in models.json, explicit pick only
        tts_new = {"model": "newvendor/text-to-speech-9", "callBackUrl": "https://x/cb", "input": {"text": "hi"}}
        env_tts = _fake_adapter_env(td, {"validate": {"state": "validated", "capability": "Text to Speech", "error": None}})
        _expect_exit(write("new-tts.json", tts_new), "tts", 0, env=env_tts, expect_out="validated by Skill 74")
        env_vid = _fake_adapter_env(td, {"validate": {"state": "validated", "capability": "Text to Video", "error": None}})
        _expect_exit(write("new-notts.json", tts_new), "tts", 2, env=env_vid, expect_out="not a Text to Speech model")
        env_bad = _fake_adapter_env(td, {"validate": {"state": "fail", "error": {"code": "validation_failed", "msg": "input.text: longer than maxLength 10"}}})
        _expect_exit(write("new-tts-bad.json", tts_new), "tts", 2, env=env_bad, expect_out="Skill 74")
        _expect_exit(write("new-tts-offline.json", tts_new), "tts", 2)  # adapter unreachable -> old rejection
        env_stt_cap = _fake_adapter_env(td, {"validate": {"state": "validated", "capability": "Speech to Text", "error": None}})
        _expect_exit(write("new-stt-as-tts.json", tts_new), "tts", 2, env=env_stt_cap, expect_out="not a Text to Speech model")
        env_mixed = _fake_adapter_env(td, {"validate": {"state": "validated", "capability": "Text to Speech, Speech to Text", "error": None}})
        _expect_exit(write("new-mixed-cap.json", tts_new), "tts", 2, env=env_mixed, expect_out="not a Text to Speech model")
        env_nocap = _fake_adapter_env(td, {"validate": {"state": "validated", "capability": None, "error": None}})
        _expect_exit(write("new-nocap.json", tts_new), "tts", 2, env=env_nocap)
        # STT gate stays closed even when the live catalog lists a candidate; the candidate is only reported
        env_stt = _fake_adapter_env(td, {"discover": {"state": "validated", "data": {"models": [
            {"model": "elevenlabs/speech-to-text-v1", "taskType": ["Speech to Text"]},
            {"model": "elevenlabs/text-to-speech-turbo-2-5", "taskType": ["Text to Speech"]}]}}})
        _expect_exit(write("stt-inspect2.json", {}), "stt", 0, env=env_stt, expect_out="elevenlabs/speech-to-text-v1")
        _expect_exit(write("stt-attempt2.json", {"model": "elevenlabs/speech-to-text-v1", "dispatch": True}), "stt", 2, env=env_stt)
        env_none = _fake_adapter_env(td, {"discover": {"state": "validated", "data": {"models": []}}})
        _expect_exit(write("stt-inspect3.json", {}), "stt", 0, env=env_none, expect_out="no speech-to-text model")

        ok = 58
    print(f"SELF-TEST PASS: {ok} checks green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
