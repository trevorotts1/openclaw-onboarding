#!/usr/bin/env python3
"""Prompt template data layer (U15a, design 2.2/2.4): load() and caps(). Stdlib only.

One copy of every look text: the five mode blocks under
`references/prompt-templates/modes/` are THE text, built once from the style
records the bibles already carry (design 2.4). A test asserts each block still
carries its record's key phrases (realism: RECIPE_REQUIRED_PHRASES).

caps() reuses core/prompt_limits.py (FU-U6). The catalogs come first
(67-kie-video/models.json, 68-kie-audio/models.json); the manifest's own table
only fills what the catalogs lack (the Kling avatar row, which no catalog
carries) and is the documented fallback. No second caps table lives here.

Run the test: python3 scripts/core/prompt_templates/test_prompt_templates_u15.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TOOL_NAME = "prompt_templates"
TOOL_VERSION = "0.1.0"

#: The five render modes and the five card looks (design 2.1, fixed vocabulary).
MODES = ("lifelike-3d", "painted-2d", "sketch-ink", "realism", "golden-realism")
LOOKS = ("lifelike-3d", "2d-hand-painted", "sketch-to-life", "canvas-to-life",
         "canvas-to-3d")
SHOT_TYPES = ("talking-closeup", "motion-broll", "struggle-beat", "product-book",
              "style-switch", "end-card")

CORE_DIR = Path(__file__).resolve().parents[1]         # .../<skill>/scripts/core
SKILL_ROOT = CORE_DIR.parents[1]                       # .../<skill>
TEMPLATES_DIR = SKILL_ROOT / "references" / "prompt-templates"

class PromptTemplateError(ValueError):
    """A template layer is missing or malformed. Fail closed, name the path."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code

# ---------------------------------------------------------------------------
# Layer loading.

_LAYER_FILES = {
    "manifest": ("manifest.json",),
    "length_classes": ("length-classes.json",),
    "model": ("models", "%s.json"),
    "mode": ("modes", "%s.json"),
    "look": ("looks", "%s.json"),
    "shot_type": ("shot-types", "%s.json"),
    "music": ("music", "%s.json"),
}

def templates_dir(root=None):
    """The prompt-templates directory; `root` overrides for tests."""
    return Path(root) if root else TEMPLATES_DIR

def load(layer, name=None, root=None, required=True):
    """One template layer, parsed. Raises PromptTemplateError naming the path.

    ``layer`` is a key of ``_LAYER_FILES``; ``name`` is the file stem for the
    per-name layers. A missing file (or one that is not a JSON object) refuses
    unless ``required=False``, when it returns None.
    """
    if layer not in _LAYER_FILES:
        raise PromptTemplateError("PROMPT_TEMPLATE_UNKNOWN_LAYER",
                                  "unknown layer %r; known: %s"
                                  % (layer, ", ".join(sorted(_LAYER_FILES))))
    parts = _LAYER_FILES[layer]
    if len(parts) == 2:
        if not name:
            raise PromptTemplateError("PROMPT_TEMPLATE_NAME_REQUIRED",
                                      "layer %r needs a name" % layer)
        rel = parts[0] + "/" + (parts[1] % name)
    else:
        rel = parts[0]
    path = templates_dir(root) / rel
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        if not required:
            return None
        raise PromptTemplateError("PROMPT_TEMPLATE_UNREADABLE",
                                  "%s (%s)" % (path, exc))
    if not isinstance(doc, dict):
        if not required:
            return None
        raise PromptTemplateError("PROMPT_TEMPLATE_NOT_AN_OBJECT",
                                  "%s holds %s" % (path, type(doc).__name__))
    return doc

# ---------------------------------------------------------------------------
# caps(): the catalogs first, the manifest second.

def _manifest_cap(model, field, root=None):
    doc = load("manifest", root=root)
    entry = (doc.get("caps") or {}).get(model)
    if entry is None and model == "suno-generate":
        entry = (doc.get("caps") or {}).get("suno-generate:V6")
    if not isinstance(entry, dict):
        return None
    row = entry.get(field)
    if isinstance(row, dict) and "max" in row:
        return {"cap": row["max"], "status": row.get("status", "UNKNOWN"),
                "source": "references/prompt-templates/manifest.json caps[%r][%r]: %s"
                          % (model, field, row.get("source", "")),
                "field": field, "model": model}
    return None

def caps(model, field, root=None):
    """{model, field, cap, status, source} for one model field, catalogs first.

    The 67 catalog answers video and avatar rows (via U6's prompt_limits, so
    there is one catalog reader) and the 68 catalog answers Suno generate
    fields. The manifest's own table answers only what the catalogs lack, and
    the source text says which answered.
    """
    field = str(field)
    if field == "prompt" and model not in ("suno-generate", "suno-extend"):
        row = _catalog_prompt(model)
        if row is not None:
            return row
    elif model in ("suno-generate", "suno-extend") or _is_suno_field(field):
        row = _catalog_suno(model, field)
        if row is not None:
            return row
    row = _manifest_cap(model, field, root=root)
    if row is not None:
        return row
    raise PromptTemplateError("PROMPT_TEMPLATE_NO_CAP",
                              "no cap for model %r field %r in the 67/68 catalogs "
                              "or the manifest" % (model, field))

def _is_suno_field(field):
    return field in ("lyrics", "style", "title", "negative_tags", "duration")

#: Where each catalog sits, walked up from the skill root. The 999 tree keeps
#: the catalogs under installer-registration/helpers/ (video_router's own list),
#: which U6's ancestor walk cannot see from here; the reading itself still
#: happens in prompt_limits, this only hands it the path.
_CATALOG_RELS = {
    "video": (("67-kie-video", "models.json"),
              ("installer-registration", "helpers", "67-kie-video", "models.json")),
    "audio": (("68-kie-audio", "models.json"),
              ("installer-registration", "helpers", "68-kie-audio", "models.json")),
}

def catalog_path(kind, root=None):
    """Skill 67 (kind="video") or 68 (kind="audio") models.json, or None."""
    start = templates_dir(root).resolve()
    for parent in (start,) + tuple(start.parents):
        for rel in _CATALOG_RELS[kind]:
            cand = parent.joinpath(*rel)
            if cand.is_file():
                return cand
    return None

def _prompt_limits():
    """U6's catalog reader (core/prompt_limits.py), imported lazily."""
    if CORE_DIR not in sys.path:
        sys.path.insert(0, CORE_DIR)
    import prompt_limits as PL
    return PL

def _catalog_prompt(model):
    """Video/avatar prompt cap from the 67 catalog, through U6's prompt_limits.

    A model the 67 catalog does not carry (or carries with no published cap)
    returns None, so the manifest answers; that is the design 2.2 order.
    """
    PL = _prompt_limits()
    if model in PL.OVERRIDES:
        return None
    video = catalog_path("video")
    if video is None:
        return None
    try:
        row = PL.video_caps(model, models_path=video)
    except PL.PromptLimitError:
        return None
    if row.get("prompt") is None:
        return None
    return {"model": model, "field": "prompt", "cap": row["prompt"],
            "status": row["status"],
            "source": "%s/%s" % (video.parent.name, row["source"])}

def _catalog_suno(model, field):
    """Suno generate field cap from the 68 catalog, through U6's prompt_limits."""
    PL = _prompt_limits()
    if field in ("negative_tags", "duration"):
        return None                     # the 68 catalog holds no cap for these
    audio = catalog_path("audio")
    if audio is None:
        return None
    row = PL.suno_caps(models_path=audio)
    if row.get(field) is None:
        return None
    return {"model": model, "field": field, "cap": row[field], "status": row["status"],
            "source": "%s/%s" % (audio.parent.name, row["source"])}

# ---------------------------------------------------------------------------
# U15b: the H3 assembler, band guard, expand/trim and receipt.

import hashlib
import re

#: The U16 carry-in: a villain shot type and its guidance live in the bible
#: (product_style_bible.bible VILLAIN_*), never forked here (U16 owns them).
VILLAIN_SHOT_TYPE_NAME = "villain"

def band(model, root=None):
    """The owner band for one video model, from the manifest ``bands`` map.

    minimax-h3/* carries floor 5000 / target 5000-6800 / hard max 7000
    (Trevor 2026-10-08). Raises PromptTemplateError when no band matches,
    so an unbanded paid model can never be assembled silently.
    """
    doc = load("manifest", root=root)
    bands = doc.get("bands") or {}
    if model in bands:
        return dict(bands[model])
    family = model.split("/")[0] + "/*"
    if family in bands:
        return dict(bands[family])
    raise PromptTemplateError("PROMPT_TEMPLATE_NO_BAND",
                              "no band for model %r in the manifest" % (model,))

def _h3_model(root=None):
    return load("model", "minimax-h3", root=root)

def _look_block(spec, root=None):
    """`<Look label> look, <mode> mode.` + the mode's h3_block."""
    look = load("look", spec["look"], root=root)
    if spec["mode"] not in (look.get("modes") or []):
        raise PromptTemplateError("MODE_NOT_IN_LOOK",
                                  "%s is not a mode of %s"
                                  % (spec["mode"], spec["look"]))
    mode = load("mode", spec["mode"], root=root)
    if mode.get("extends"):
        base = load("mode", mode["extends"], root=root)
        text = base["h3_block"].replace(
            "{palette}", base.get("palette_default", ""))
        text = text + " " + mode["h3_block_suffix"]
    else:
        palette = ((look.get("palette_override") or {}).get(spec["mode"])
                   or mode.get("palette_default", ""))
        text = mode["h3_block"].replace("{palette}", palette)
    return "%s look, %s mode. %s" % (look["label"], spec["mode"],
                                     re.sub(r"\s+", " ", text).strip())

def _villain_extra(spec):
    """The U16 guidance block when the shot type is the villain."""
    if spec.get("shot_type") != VILLAIN_SHOT_TYPE_NAME:
        return None
    try:
        if CORE_DIR not in sys.path:
            sys.path.insert(0, CORE_DIR)
        from product_style_bible import bible as BB
        return BB.VILLAIN_SHOT_GUIDANCE
    except (ImportError, AttributeError) as exc:
        raise PromptTemplateError("VILLAIN_GUIDANCE_UNAVAILABLE",
                                  "U16 carry-in missing: %s" % exc)

def _kling_video_model(root=None):
    return load("model", "kling-video", root=root)

def kling_section_limits(scale=None, root=None):
    """Per-section char budget for a Kling video prompt: H3's min/max * scale.

    The scale is ``models/kling-video.json``'s ``section_scale`` (0.38, design
    3.5). Never a second table: it is H3's own section table, compressed.
    """
    if scale is None:
        scale = float(_kling_video_model(root=root)["section_scale"])
    out = {}
    for s in _h3_model(root=root)["sections"]:
        mx = s["max"]
        out[s["id"]] = {"min": int(s["min"] * scale),
                        "max": int(round(mx * scale)) if mx else 0}
    return out

def _kling_look_block(spec, root=None):
    """The look in Kling's short form: the mode's ``kling_block``.

    Same clause as the H3 look (`<Look label> look, <mode> mode.`) but the
    block is the 181-450 char ``kling_block`` (design 3.5). A mode that
    carries none (sketch-ink, golden-realism) falls back to a scaled H3 block,
    so no shot is ever refused for a missing short form.
    """
    look = load("look", spec["look"], root=root)
    if spec["mode"] not in (look.get("modes") or []):
        raise PromptTemplateError("MODE_NOT_IN_LOOK",
                                  "%s is not a mode of %s"
                                  % (spec["mode"], spec["look"]))
    mode = load("mode", spec["mode"], root=root)
    text = mode.get("kling_block")
    if not text and mode.get("extends"):
        base = load("mode", mode["extends"], root=root)
        text = base.get("kling_block")
        if text and mode.get("h3_block_suffix"):
            text = text + " " + mode["h3_block_suffix"]
    if not text:
        return None
    return "%s look, %s mode. %s" % (look["label"], spec["mode"],
                                     re.sub(r"\s+", " ", text).strip())

def _kling_cut(text, limit):
    """Cut to ``limit`` chars at a sentence end, else a clause end, else word.

    Kling takes the move in plain words, so nothing here may emit a bracket
    (design 3.5) and nothing may be padded to reach a floor. The cut lands on
    the latest sentence end inside the limit, then the latest comma, semicolon
    or colon, and only then a word end: a dangling half-clause reads as an
    instruction to the model.
    """
    if limit <= 0 or len(text) <= limit:
        return text
    head = text[:limit]

    def last(pat, floor):
        ms = [m.end() for m in re.finditer(pat, head)]
        if ms and ms[-1] >= floor:
            return head[:ms[-1]].strip()
        return None

    got = last(r"[.!?](?=\s|$)", limit * 0.5)
    if got:
        return got
    got = last(r"[,;:](?=\s)", limit * 0.6)
    if got:
        return got.rstrip(" ,;:") + "."
    return (head.rsplit(" ", 1)[0] or head).rstrip(" ,;:-") + "."

def _kling_scale(text, scale):
    """One H3 section text scaled to ``scale``, cut at a sentence end."""
    return _kling_cut(text, int(round(len(text) * scale)))

#: Section ids the band trim may shorten, worst first. The fixed fragments
#: (reference, policy, negatives) and the identity/action facts stay whole:
#: they are what the clip is graded against, and a trimmed negative list lets
#: a defect back in. ``look`` is last because its text is already the short
#: form.
_KLING_TRIM_ORDER = ("beats", "subject", "lens_light", "physics", "header",
                     "continuity", "pages", "book", "look")
#: Section ids restored, best first, when the scaled prompt fell under the
#: floor: the facts that carry the shot, restored from the H3 text.
_KLING_RESTORE_ORDER = ("beats", "subject", "lens_light", "physics", "header",
                        "continuity")

def _kling_join(sec, order, leads):
    """The assembled prompt body; ``total()`` below mirrors this exactly."""
    return "\n".join("%s: %s" % (leads[k], sec[k])
                     for k in order if k in sec)

def assemble_kling_video(spec, characters, root=None):
    """Assemble one Kling video prompt from a shot spec (design 3.5).

    Same section order as H3, scaled to ``section_scale`` (0.38), sized into
    the manifest band for the shot's Kling model. Three differences from H3:
    the camera is PLAIN WORDS after the subject's motion (no bracket group),
    the look is the mode's ``kling_block``, and the negatives stay IN the
    prompt (the 67 catalog lists no negative_prompt field for these rows).

    Returns ``(prompt, sections)``; ``sections`` is the char count per section
    id. Facts only: every byte comes from the spec, the character record, the
    template layers or the fixed fragments in minimax-h3.json. Never padded.
    """
    kling = _kling_video_model(root=root)
    if spec["model"] not in (kling.get("applies_to") or []):
        raise PromptTemplateError("KLING_MODEL_NOT_IN_BLOCK", spec["model"])
    h3 = _h3_model(root=root)
    st = load("shot_type", spec["shot_type"], root=root)
    ch = characters[spec["character"]]
    a, cam = spec["action"], spec["camera"]
    brackets = h3["camera_vocabulary"]["bracket_commands"]
    if cam["command"] not in brackets and \
            not re.fullmatch(r"\[[A-Za-z ,]+\]", cam["command"]):
        raise PromptTemplateError("CAMERA_NOT_IN_VOCABULARY", cam["command"])
    main = cam["command"].strip("[]").split(",")[0].strip()
    if main not in [c.strip("[]") for c in st["camera_allowed"]]:
        raise PromptTemplateError("CAMERA_NOT_ALLOWED_FOR_SHOT_TYPE",
                                  "%s for %s" % (cam["command"],
                                                 spec["shot_type"]))
    scale = float(kling["section_scale"])
    frag = h3["fragments"]
    full = {}
    full["header"] = ("%s, %s, %d seconds, %s vertical, story beat %s. %s"
                      % (spec["shot_id"], spec["shot_type"].replace("-", " "),
                         spec["duration_s"], spec["aspect"],
                         spec["beat"].replace("_", " "), spec["intent"]))
    full["subject"] = "%s %s" % (spec["subject"], spec["composition"])
    act = "Start: %s End: %s Direction: %s" % (a["start"], a["end"],
                                               a["direction"])
    if st.get("mouth_rule"):
        act += " " + st["mouth_rule"]
    if spec.get("match_pose"):
        act += " " + spec["match_pose"]
    villain = _villain_extra(spec)
    if villain:
        act += " " + villain
    full["action"] = act
    full["reference"] = frag["REFERENCE_FRAME"]
    # Design 3.5: the camera is the move in plain words, AFTER the subject's
    # motion. No bracket group anywhere -- check_kling refuses one.
    full["camera"] = "Camera movement follows the action above: %s." % (
        re.sub(r"\s+", " ", cam["plain"]).strip())
    full["lens_light"] = spec["lens_light"]
    full["continuity"] = (
        "%s In this scene she wears %s. %s Visible emotion: %s."
        % (ch["identity"], ch["wardrobe"][spec["wardrobe"]],
           ch["do_not_change"], spec["visible_emotion"]))
    look = _kling_look_block(spec, root=root)
    full["look"] = look if look else _look_block(spec, root=root)
    if spec.get("book"):
        full["book"] = frag["BOOK_CLOSED"] + (
            " " + frag["BOOK_OPEN_MOTION"] if spec["book"] == "open" else "")
    if spec.get("pages") == "texture":
        full["pages"] = frag["PRINTED_PAGES"]
    full["physics"] = spec["motion_physics"]
    full["beats"] = " ".join("%s: %s" % (t, d) for t, d in spec["beats"])
    full["policy"] = frag["SOUND_AND_TEXT"]
    neg = (list(frag["BASE_NEGATIVES"]) + st.get("negatives", [])
           + spec.get("negatives_extra", []))
    full["negatives"] = "; ".join(neg[:16]) + "."

    order = [s["id"] for s in h3["sections"]]
    leads = {s["id"]: s["lead"] for s in h3["sections"]}
    lim = kling_section_limits(scale=scale, root=root)

    def body_len(sec):
        return len(_kling_join(sec, order, leads))

    sec = {k: _kling_scale(v, scale) for k, v in full.items()}
    # Over the band: shorten, worst first, but never the fixed fragments.
    sec = {k: (v if k not in lim or lim[k]["max"] <= 0 else
               _kling_cut(v, lim[k]["max"])) for k, v in sec.items()}
    b = band(spec["model"], root=root)
    target_max = b["target_max"]
    guard = 0
    while body_len(sec) > target_max and guard < 64:
        guard += 1
        moved = False
        for sid in _KLING_TRIM_ORDER:
            if sid not in sec or len(sec[sid]) <= 40:
                continue
            smaller = _kling_cut(sec[sid], int(len(sec[sid]) * 0.9))
            if len(smaller) < len(sec[sid]):
                sec[sid] = smaller
                moved = True
            if body_len(sec) <= target_max:
                break
        if not moved:
            break
    # Under the floor: restore the shot-carrying facts from the H3 text.
    floor = b.get("floor")
    guard = 0
    while floor and body_len(sec) < floor and guard < 32:
        guard += 1
        moved = False
        for sid in _KLING_RESTORE_ORDER:
            if sid in full and len(sec.get(sid, "")) < len(full[sid]):
                sec[sid] = full[sid]
                moved = True
                if body_len(sec) >= floor:
                    break
        if not moved:
            break
    prompt = _kling_join(sec, order, leads)
    return prompt, {k: len(v) for k, v in sec.items()}

def check_kling(prompt, sections, model, root=None):
    """The Kling guard: the band, no bracket syntax, and the shared rules.

    Same verdict vocabulary as ``check()``: REFUSE beats TRIM beats FLAG beats
    PASS. REFUSE covers the hard max, ANY square bracket (Kling takes the move
    in plain words, so a bracket is a defect, not a camera command), a banned
    phrase and a duplicate sentence. The band and the hard max come from the
    manifest; the cap's status (VERIFIED / UNVERIFIED) is passed through by
    ``band_cap`` so an UNVERIFIED ceiling is never silently promoted.
    """
    b = band(model, root=root)
    qr = load("manifest", root=root)["quality_rules"]
    n = len(prompt)
    reasons = []
    groups = re.findall(r"\[[^\]]*\]", prompt)
    if groups:
        reasons.append("KLING_BRACKET_SYNTAX %d %r: Kling takes the move in "
                       "plain words" % (len(groups), groups[0][:40]))
    if n > b["hard_max"]:
        reasons.append("KLING_OVER_HARD_MAX %d > %d" % (n, b["hard_max"]))
    for ph in qr["banned_phrases_any_model"]:
        if ph in prompt:
            reasons.append("BANNED_PHRASE %r" % ph)
    cut = qr["max_duplicate_sentence_chars"]
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", prompt)
             if len(s.strip()) >= cut]
    dup = {s for s in sents if sents.count(s) > 1}
    if dup:
        reasons.append("DUPLICATE_SENTENCE x%d" % len(dup))
    words = re.findall(r"[a-z0-9']+", prompt.lower())
    grams = [" ".join(words[i:i + 8]) for i in range(len(words) - 7)]
    rep = (len(grams) - len(set(grams))) / max(len(grams), 1)
    if rep > qr["max_repeated_8gram_ratio"]:
        reasons.append("REPEATED_8GRAMS %.3f" % rep)
    if re.search(r"\b(left|right)\b", prompt, re.I) and \
            "camera's point of view" not in prompt:
        reasons.append("DIRECTION_WITHOUT_REFERENCE_FRAME")
    if reasons:
        return {"verdict": "REFUSE", "chars": n, "reasons": reasons,
                "repeat_8gram": round(rep, 4)}
    if b.get("floor") is not None and n < b["floor"]:
        return {"verdict": "FLAG", "chars": n,
                "reasons": ["KLING_BELOW_FLOOR %d < %d: expand from the spec "
                            "or refuse KLING_THIN_SPEC" % (n, b["floor"])],
                "repeat_8gram": round(rep, 4)}
    if n > b["target_max"]:
        return {"verdict": "TRIM", "chars": n,
                "reasons": ["KLING_OVER_TARGET %d > %d: trim (the assembler "
                            "already trims; a spec this heavy needs less)"
                            % (n, b["target_max"])],
                "repeat_8gram": round(rep, 4)}
    return {"verdict": "PASS", "chars": n, "reasons": [],
            "repeat_8gram": round(rep, 4)}

def band_cap(model, root=None):
    """The hard max with its provenance: {cap, status, source, model, field}.

    Design 3.5/8: an UNVERIFIED cap guards at its number and PRINTS its
    status; it is never silently promoted to VERIFIED. The number is the
    owner band's ``hard_max``; the status comes from the manifest caps table
    (the catalogs first, through ``caps()``), so a model whose catalog row is
    NOT_PUBLISHED stays UNVERIFIED.
    """
    b = band(model, root=root)
    cap = b.get("hard_max")
    if cap is None:
        return None
    status, source = "UNKNOWN", ("references/prompt-templates/manifest.json "
                                 "band %r hard_max (%s)"
                                 % (model, b.get("owner", "")))
    row = _manifest_cap(model, "prompt", root=root)
    if row is None:
        try:
            row = caps(model, "prompt", root=root)
        except PromptTemplateError:
            row = None
    if row:
        status, source = row.get("status", status), row.get("source", source)
    return {"model": model, "field": "prompt", "cap": cap, "status": status,
            "source": source}

def assemble_h3(spec, characters, root=None):
    """Assemble one H3 prompt from a shot spec (the planner's facts).

    Returns ``(prompt, sections)``; ``sections`` is the char count per section
    id. Facts only: every byte comes from the spec, the character record, the
    template layers or the fixed fragments in minimax-h3.json. No padding.
    """
    h3 = _h3_model(root=root)
    st = load("shot_type", spec["shot_type"], root=root)
    ch = characters[spec["character"]]
    a, cam = spec["action"], spec["camera"]
    brackets = h3["camera_vocabulary"]["bracket_commands"]
    if cam["command"] not in brackets and \
            not re.fullmatch(r"\[[A-Za-z ,]+\]", cam["command"]):
        raise PromptTemplateError("CAMERA_NOT_IN_VOCABULARY", cam["command"])
    main = cam["command"].strip("[]").split(",")[0].strip()
    if main not in [c.strip("[]") for c in st["camera_allowed"]]:
        raise PromptTemplateError("CAMERA_NOT_ALLOWED_FOR_SHOT_TYPE",
                                  "%s for %s" % (cam["command"],
                                                 spec["shot_type"]))
    frag = h3["fragments"]
    sec = {}
    sec["header"] = ("%s, %s, %d seconds, %s vertical, story beat %s. %s"
                     % (spec["shot_id"], spec["shot_type"].replace("-", " "),
                        spec["duration_s"], spec["aspect"],
                        spec["beat"].replace("_", " "), spec["intent"]))
    sec["subject"] = "%s %s" % (spec["subject"], spec["composition"])
    act = "Start: %s End: %s Direction: %s" % (a["start"], a["end"],
                                               a["direction"])
    if st.get("mouth_rule"):
        act += " " + st["mouth_rule"]
    if spec.get("match_pose"):
        act += " " + spec["match_pose"]
    villain = _villain_extra(spec)
    if villain:
        act += " " + villain
    sec["action"] = act
    sec["reference"] = frag["REFERENCE_FRAME"]
    sec["camera"] = "%s %s" % (cam["command"], cam["plain"])
    sec["lens_light"] = spec["lens_light"]
    sec["continuity"] = (
        "%s In this scene she wears %s. %s The first frame of the clip is the "
        "approved keyframe and the clip continues from it without any change "
        "of face, hair, glasses or wardrobe. Visible emotion: %s."
        % (ch["identity"], ch["wardrobe"][spec["wardrobe"]],
           ch["do_not_change"], spec["visible_emotion"]))
    sec["look"] = _look_block(spec, root=root)
    if spec.get("book"):
        sec["book"] = frag["BOOK_CLOSED"] + (
            " " + frag["BOOK_OPEN_MOTION"] if spec["book"] == "open" else "")
    if spec.get("pages") == "texture":
        sec["pages"] = frag["PRINTED_PAGES"]
    sec["physics"] = spec["motion_physics"]
    sec["beats"] = " ".join("%s: %s" % (t, d) for t, d in spec["beats"])
    sec["policy"] = frag["SOUND_AND_TEXT"]
    neg = (list(frag["BASE_NEGATIVES"]) + st.get("negatives", [])
           + spec.get("negatives_extra", []))
    sec["negatives"] = "; ".join(neg[:16]) + "."
    order = [s["id"] for s in h3["sections"]]
    leads = {s["id"]: s["lead"] for s in h3["sections"]}
    parts = ["%s: %s" % (leads[k], sec[k]) for k in order if k in sec]
    return "\n".join(parts), {k: len(v) for k, v in sec.items()}

def check(prompt, sections, model="minimax-h3/image-to-video", root=None):
    """The band guard and the quality rules.

    -> {"verdict": REFUSE|FLAG|TRIM|PASS, "chars", "reasons"}. REFUSE wins over
    everything: a prompt never leaves this function over the hard max, over one
    bracket group, or carrying a banned phrase or a duplicate sentence.
    """
    b = band(model, root=root)
    qr = load("manifest", root=root)["quality_rules"]
    n = len(prompt)
    reasons = []
    if n > b["hard_max"]:
        return {"verdict": "REFUSE", "chars": n,
                "reasons": ["H3_OVER_HARD_MAX %d > %d" % (n, b["hard_max"])]}
    # Section min/max (design rule 3). A violated section is a FLAG: the
    # spec is missing a fact, which expand() turns into H3_THIN_SPEC -- it is
    # never something padding may fix.
    section_reasons = []
    if sections:
        for s in _h3_model(root=root)["sections"]:
            if s.get("conditional"):
                continue
            got = sections.get(s["id"], 0)
            if got < s["min"]:
                section_reasons.append("SECTION_THIN %s %d < %d"
                                       % (s["id"], got, s["min"]))
            if got > s["max"]:
                section_reasons.append("SECTION_LONG %s %d > %s"
                                       % (s["id"], got, s["max"]))
    groups = re.findall(r"\[[^\]]*\]", prompt)
    if len(groups) != 1:
        reasons.append("CAMERA_BRACKETS %d (need exactly 1)" % len(groups))
    elif len([x for x in groups[0].strip("[]").split(",") if x.strip()]) > 3:
        reasons.append("CAMERA_MOVES_OVER_3")
    for ph in qr["banned_phrases_any_model"]:
        if ph in prompt:
            reasons.append("BANNED_PHRASE %r" % ph)
    cut = qr["max_duplicate_sentence_chars"]
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", prompt)
             if len(s.strip()) >= cut]
    dup = {s for s in sents if sents.count(s) > 1}
    if dup:
        reasons.append("DUPLICATE_SENTENCE x%d" % len(dup))
    words = re.findall(r"[a-z0-9']+", prompt.lower())
    grams = [" ".join(words[i:i + 8]) for i in range(len(words) - 7)]
    rep = (len(grams) - len(set(grams))) / max(len(grams), 1)
    if rep > qr["max_repeated_8gram_ratio"]:
        reasons.append("REPEATED_8GRAMS %.3f" % rep)
    if re.search(r"\b(left|right)\b", prompt, re.I) and \
            "camera's point of view" not in prompt:
        reasons.append("DIRECTION_WITHOUT_REFERENCE_FRAME")
    if reasons:
        return {"verdict": "REFUSE", "chars": n, "reasons": reasons,
                "repeat_8gram": round(rep, 4)}
    if section_reasons:
        return {"verdict": "FLAG", "chars": n, "reasons": section_reasons,
                "repeat_8gram": round(rep, 4)}
    if b.get("floor") is not None and n < b["floor"]:
        return {"verdict": "FLAG", "chars": n,
                "reasons": ["H3_BELOW_FLOOR %d < %d: expand from the spec "
                            "(expand_priority) or refuse H3_THIN_SPEC"
                            % (n, b["floor"])],
                "repeat_8gram": round(rep, 4)}
    if n > b["target_max"]:
        return {"verdict": "TRIM", "chars": n,
                "reasons": ["H3_OVER_TARGET %d > %d: trim (trim_priority)"
                            % (n, b["target_max"])],
                "repeat_8gram": round(rep, 4)}
    return {"verdict": "PASS", "chars": n, "reasons": [],
            "repeat_8gram": round(rep, 4)}

def expand(spec, characters, prompt, verdict, root=None):
    """Under the floor or section-thin: refuse H3_THIN_SPEC, never pad.

    The assembler already consumes every fact the spec carries, so the only
    honest expansion is naming the slots the planner left empty and sending
    the spec back to it (expand_priority). Raises H3_THIN_SPEC with the empty
    slots; it never repeats a sentence and never adds filler. A verdict that
    is PASS or TRIM comes back unchanged.
    """
    v = verdict.get("verdict")
    reasons = verdict.get("reasons") or []
    thin = v == "FLAG" or (
        v == "REFUSE" and reasons
        and all(r.startswith("SECTION_THIN") for r in reasons))
    if not thin:
        return prompt, verdict
    st = load("shot_type", spec["shot_type"], root=root)
    empty = []
    for slot in st.get("required_spec") or []:
        head, _, tail = slot.partition(".")
        val = spec.get(head)
        if tail:
            val = val.get(tail) if isinstance(val, dict) else None
        if val in (None, "", [], {}):
            empty.append(slot)
    raise PromptTemplateError(
        "H3_THIN_SPEC",
        "shot %s is %s and the spec has no unused facts left; empty slots: "
        "%s. The planner must supply them. (%s)"
        % (spec.get("shot_id"),
           "under the floor (%s < %s)" % (verdict.get("chars"),
                                          band(spec["model"], root=root)["floor"])
           if v == "FLAG" else "section-thin",
           ", ".join(empty) if empty else "(none named by the shot type)",
           "; ".join(reasons) or "H3_BELOW_FLOOR"))

def receipt(spec, prompt, sections, verdict, root=None):
    """The prompt receipt: sha256 + template version + section char map."""
    man = templates_dir(root) / "manifest.json"
    return {"shot_id": spec["shot_id"], "model": spec["model"],
            "look": spec["look"], "mode": spec["mode"],
            "shot_type": spec["shot_type"],
            "template_version": load("manifest", root=root)["template_version"],
            "manifest_sha256": hashlib.sha256(man.read_bytes()).hexdigest(),
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "chars": len(prompt), "band": band(spec["model"], root=root),
            "sections": sections, "check": verdict}

def has_receipt(prompt_sha256, receipts):
    """True when one receipt in ``receipts`` matches this prompt's sha256."""
    for r in receipts or []:
        if isinstance(r, dict) and r.get("prompt_sha256") == prompt_sha256:
            return True
    return False

__all__ = ["TOOL_NAME", "TOOL_VERSION", "MODES", "LOOKS", "SHOT_TYPES",
           "CORE_DIR", "SKILL_ROOT", "TEMPLATES_DIR", "PromptTemplateError",
           "templates_dir", "catalog_path", "load", "caps",
           "VILLAIN_SHOT_TYPE_NAME", "band", "assemble_h3", "check", "expand",
           "receipt", "has_receipt", "assemble_kling_video", "check_kling",
           "kling_section_limits", "band_cap"]
