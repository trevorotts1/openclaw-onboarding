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
import re
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
# Kling avatar (U15e): the one assembler and checker for the lip-sync prompt.
# Design 5.1: three sentences, ONE emotion, the `who` descriptor from the look's
# mode (`modes/*.json` kling_who), never a hard-coded look.

KLING_AVATAR_MODEL = "kling-ai-avatar-standard"
KLING_VERBS = ("sings", "says", "raps")
KLING_FRAMING_DEFAULT = "chest-up framing, eyes to the lens"
KLING_FRAMING_ALT = "medium close-up, eyes to the lens"
KLING_HEAD_EXTRAS = ("", ", a small nod on the strong beat", ", a slight head tilt")
#: file 17's forbidden mouth-driving phrases plus quoted lyric text.
KLING_FORBIDDEN = ("lips open", "in time with", "every syllable",
                   "mouths the words", '"')

def kling_avatar_model(root=None):
    """The Kling avatar model block (sentences + caps). One copy: the JSON."""
    return load("model", KLING_AVATAR_MODEL, root=root)

def assemble_kling_avatar(mode, noun, verb, emotion, poss, head_extra="",
                          framing=None, root=None):
    """The lip-sync prompt for one line (design 5.1), assembled from the mode.

    ``mode`` is one of MODES; ``noun`` the cast noun; ``verb`` one of
    KLING_VERBS; ``emotion`` ONE word; ``poss`` His/Her/Their. A mode whose
    block forbids lip-sync (sketch-ink, golden-realism) raises
    LIPSYNC_NOT_ALLOWED_FOR_MODE; over the hard cap raises
    KLING_AVATAR_OVER_HARD_MAX. Nothing is ever truncated.
    """
    m = load("mode", mode, root=root)
    if not m.get("lipsync_allowed") or not m.get("kling_who"):
        raise PromptTemplateError(
            "LIPSYNC_NOT_ALLOWED_FOR_MODE",
            "%s may not be lip-synced (%s)" % (mode, m.get("lipsync_note", "no kling_who")))
    if verb not in KLING_VERBS:
        raise PromptTemplateError("BAD_VERB", "%r not in %s" % (verb, KLING_VERBS))
    if head_extra not in KLING_HEAD_EXTRAS:
        raise PromptTemplateError("BAD_HEAD_EXTRA",
                                  "%r not in KLING_HEAD_EXTRAS" % (head_extra,))
    if framing is None:
        framing = KLING_FRAMING_DEFAULT
    elif framing not in (KLING_FRAMING_DEFAULT, KLING_FRAMING_ALT):
        raise PromptTemplateError("BAD_FRAMING", "%r is not an allowed framing" % (framing,))
    t = kling_avatar_model(root=root)["prompt_template"]
    prompt = " ".join(s.format(who_descriptor=m["kling_who"], character_noun=noun,
                               verb=verb, emotion=emotion, head_extra=head_extra,
                               framing=framing, Poss=poss) for s in t["sentences"])
    if len(prompt) > t["hard_max"]:
        raise PromptTemplateError(
            "KLING_AVATAR_OVER_HARD_MAX",
            "%d chars > hard max %d (%s); never truncated"
            % (len(prompt), t["hard_max"], t.get("hard_max_status", "")))
    return prompt

def check_kling_avatar(prompt, line="", emotion="", root=None):
    """Judge an avatar prompt (design 8.7). -> {pass, chars, sentences, errors,
    limits, cap_status}. 1-3 sentences, at most the target max, ONE emotion, no
    lyric run from ``line``, no forbidden mouth-driving phrase, over the hard
    max refused. The hard cap is UNVERIFIED for the KIE wrapper and guarded."""
    t = kling_avatar_model(root=root)["prompt_template"]
    errs = []
    n = len(prompt)
    sents = len(re.findall(r"[.!?](?:\s|$)", prompt))
    if n > t["char_target_max"]:
        errs.append("OVER_TARGET %d > %d" % (n, t["char_target_max"]))
    if n > t["hard_max"]:
        errs.append("OVER_HARD_MAX %d > %d" % (n, t["hard_max"]))
    if not 1 <= sents <= 3:
        errs.append("SENTENCES %d (want 1-3)" % sents)
    if emotion and ("," in emotion or " and " in emotion):
        errs.append("MORE_THAN_ONE_EMOTION %r" % emotion)
    lw = re.findall(r"[a-z']+", line.lower())
    pw = " ".join(re.findall(r"[a-z']+", prompt.lower()))
    if any(" ".join(lw[i:i + 4]) in pw for i in range(max(0, len(lw) - 3))):
        errs.append("LYRIC_RUN_IN_PROMPT")
    errs += ["FORBIDDEN %r" % b for b in KLING_FORBIDDEN if b in prompt.lower()]
    return {"pass": not errs, "chars": n, "sentences": sents, "errors": errs,
            "limits": {"target_max": t["char_target_max"], "hard_max": t["hard_max"]},
            "cap_status": t.get("hard_max_status", "")}

__all__ = ["TOOL_NAME", "TOOL_VERSION", "MODES", "LOOKS", "SHOT_TYPES",
           "CORE_DIR", "SKILL_ROOT", "TEMPLATES_DIR", "PromptTemplateError",
           "templates_dir", "catalog_path", "load", "caps",
           "KLING_AVATAR_MODEL", "KLING_VERBS", "KLING_FRAMING_DEFAULT",
           "KLING_FRAMING_ALT", "KLING_HEAD_EXTRAS", "kling_avatar_model",
           "assemble_kling_avatar", "check_kling_avatar"]
