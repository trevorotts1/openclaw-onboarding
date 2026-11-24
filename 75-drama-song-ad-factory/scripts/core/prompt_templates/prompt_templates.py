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
import math
import os
import re
import sys
from pathlib import Path

TOOL_NAME = "prompt_templates"
TOOL_VERSION = "0.1.0"

#: Path anchors first: the mode list below reads `modes/` at import, so these
#: must exist before `_mode_stems()` runs.
CORE_DIR = Path(__file__).resolve().parents[1]         # .../<skill>/scripts/core
SKILL_ROOT = CORE_DIR.parents[1]                       # .../<skill>
TEMPLATES_DIR = SKILL_ROOT / "references" / "prompt-templates"

#: The five render modes and the five card looks (design 2.1, fixed vocabulary).
#: N-35/N-37: the mode list is read from `modes/` so a look added by its owner
#: (the sixth, stylized-3d) is picked up at load; the canonical order keeps the
#: emitted text and the tests stable on either tree.
_MODES_CANONICAL = ("lifelike-3d", "painted-2d", "sketch-ink", "realism",
                    "golden-realism", "stylized-3d")
def _mode_stems():
    try:
        return {p.stem for p in (TEMPLATES_DIR / "modes").glob("*.json")}
    except OSError:
        return set()
MODES = tuple(m for m in _MODES_CANONICAL if m in _mode_stems()) or \
    _MODES_CANONICAL[:5]
def _look_stems():
    """Look ids whose look file AND every mode it names are on this tree.

    A look is listed only when it can be assembled: N-37 adds `stylized-3d`
    (U-MODES owns the card entry, U-LOOK owns `modes/stylized-3d.json`), so on a
    branch that carries the look file before its mode file the look stays out
    of the list instead of breaking every look x mode check.
    """
    try:
        files = sorted((TEMPLATES_DIR / "looks").glob("*.json"))
    except OSError:
        return set()
    stems = {p.stem for p in files}
    mstems = _mode_stems()
    out = set()
    for p in files:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        modes = (doc.get("modes") or []) if isinstance(doc, dict) else []
        if modes and all(m in mstems for m in modes):
            out.add(p.stem)
    return out or stems
#: The six card looks (N-37 adds stylized-3d), derived from the look files.
_LOOKS_CANONICAL = ("lifelike-3d", "2d-hand-painted", "sketch-to-life",
                    "canvas-to-life", "canvas-to-3d", "stylized-3d")
LOOKS = tuple(l for l in _LOOKS_CANONICAL if l in _look_stems()) or \
    _LOOKS_CANONICAL[:5]
SHOT_TYPES = ("talking-closeup", "motion-broll", "struggle-beat", "product-book",
              "style-switch", "end-card")

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
        row = _catalog_prompt(model, root=root)
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

#: Which catalog directory answers each kind. The ONE locator is
#: ``prompt_limits.find_catalogs()`` (S75-060); this table only names the
#: directory a test tree may hold, so no walk lives here.
_CATALOG_DIRS = {"video": "67-kie-video", "audio": "68-kie-audio"}

def catalog_path(kind, root=None):
    """Skill 67 (kind="video") or 68 (kind="audio") models.json, or None.

    ``root`` is a test hook: when given, the catalog is looked for directly
    beneath it, never walked. Otherwise the path comes from the one locator,
    ``prompt_limits.find_catalogs()``.
    """
    if root is not None:
        cand = templates_dir(root) / _CATALOG_DIRS[kind] / "models.json"
        return cand if cand.is_file() else None
    audio, video = _prompt_limits().find_catalogs()
    return video if kind == "video" else audio

def _prompt_limits():
    """U6's catalog reader (core/prompt_limits.py), imported lazily."""
    if CORE_DIR not in sys.path:
        sys.path.insert(0, CORE_DIR)
    import prompt_limits as PL
    return PL

def _catalog_prompt(model, root=None):
    """Video/avatar prompt cap from the 67 catalog, through U6's prompt_limits.

    A model the 67 catalog does not carry (or carries with no published cap)
    returns None, so the manifest answers; that is the design 2.2 order. A
    model the manifest itself caps (the Kling avatar row) stays with the
    manifest, so its documented source and status are the ones reported.
    """
    PL = _prompt_limits()
    video = catalog_path("video", root=root)
    if video is None:
        return None
    try:
        row = PL.video_caps(model, models_path=video)
    except PL.PromptLimitError:
        return None
    if row.get("prompt") is None:
        return None
    if model in PL.OVERRIDES and _manifest_cap(model, "prompt", root=root) is not None:
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
# Lip-sync: no prompt at all (N-08, S-42, 3A.3).
# The lip-sync model is OmniHuman 2.0 (`omnihuman-2-0`) on every run and is
# given one picture plus the audio: it takes NO prompt. The Kling avatar
# template, `assemble_kling_avatar` and `check_kling_avatar` are retired. Every
# name below is kept only so an old caller fails with the reason instead of an
# ImportError, and nothing can assemble a lip-sync prompt any more.

LIPSYNC_MODEL = "omnihuman-2-0"
LIPSYNC_PROMPT_PRESENT = "LIPSYNC_PROMPT_PRESENT"
_RETIRED_KLING = ("LIPSYNC_MODEL_MISMATCH: the lip-sync model is OmniHuman 2.0 "
                  "(%s), and it takes NO prompt (N-08, S-42). The Kling avatar "
                  "prompt is retired; the face, wardrobe, look and expression "
                  "live in the picture alone." % LIPSYNC_MODEL)

def kling_avatar_model(root=None):
    """RETIRED (N-08). Raises instead of returning a prompt template."""
    raise PromptTemplateError("LIPSYNC_MODEL_MISMATCH", _RETIRED_KLING)

def assemble_kling_avatar(*_a, **_k):
    """RETIRED (N-08). No lip-sync prompt may be assembled."""
    raise PromptTemplateError(LIPSYNC_PROMPT_PRESENT, _RETIRED_KLING)

def check_kling_avatar(prompt, line="", emotion="", root=None):
    """RETIRED (N-08). Any lip-sync prompt is refused, never judged."""
    return {"pass": False, "verdict": "REFUSE", "chars": len(str(prompt or "")),
            "sentences": 0, "errors": [LIPSYNC_PROMPT_PRESENT + " " + _RETIRED_KLING],
            "limits": {}, "cap_status": "RETIRED"}

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

def locked_look_block(spec, root=None):
    """The exact style text the assembler placed for this spec's look/mode.

    The N-35 banned-word scan strips this block before scanning, so the lock's
    own words (a 3D block's 'soft pores') never trip the scan. Re-derived from
    the look/mode files, never copied by hand. Returns "" when the files do
    not resolve.
    """
    try:
        block = _look_block(spec, root=root)
    except PromptTemplateError:
        return ""
    # The assembler writes "<label> look, <mode> mode. <block>"; the strip
    # must remove the block text AND its lead-in, which can itself carry a
    # banned word ("never photoreal live-action").
    return block or ""

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
#: (reference, policy, negatives, book, pages) and the identity/action facts
#: stay whole: they are what the clip is graded against, and a trimmed
#: negative list (or a half-cut book contract, U15g) lets a defect back in.
#: ``look`` is last because its text is already the short form.
_KLING_TRIM_ORDER = ("beats", "subject", "lens_light", "physics", "header",
                     "continuity", "look")
#: Section ids restored, best first, when the scaled prompt fell under the
#: floor: the facts that carry the shot, restored from the H3 text.
_KLING_RESTORE_ORDER = ("beats", "subject", "lens_light", "physics", "header",
                        "continuity")

#: The book states a spec may declare (U15g). Any other value is refused: a
#: half-named book block must never silently drop the contract wording.
BOOK_STATES = ("closed", "open")

def book_fragments(spec, st, frag, root=None):
    """The book/pages sections for this spec -- the ONE wording home (U15g).

    The wording is only ever read from minimax-h3.json's ``BOOK_CLOSED``,
    ``BOOK_OPEN_MOTION`` and ``PRINTED_PAGES`` fragments. A shot type that
    declares ``required_blocks_when_book`` (product-book) demands the block:
    a spec that does not carry it, or carries a book value the assembler does
    not know, is refused ``BOOK_FRAGMENTS_REQUIRED`` instead of assembling a
    book prompt with no contract in it. An open book also needs the
    printed-pages block (the shot type's own declaration).

    Returns {section_id: text}; both assemblers ``.update()`` it.
    """
    declared = st.get("required_blocks_when_book") or []
    value = spec.get("book")
    if declared and value not in BOOK_STATES:
        raise PromptTemplateError(
            "BOOK_FRAGMENTS_REQUIRED",
            "%s declares %s and the spec carries book=%r: supply the book "
            "block (closed or open) with the fragment wording"
            % (spec.get("shot_type"), ", ".join(declared), value))
    if value is not None and value not in BOOK_STATES:
        raise PromptTemplateError(
            "BOOK_FRAGMENTS_REQUIRED",
            "book=%r is not one of %s; the wording never guesses"
            % (value, "/".join(BOOK_STATES)))
    if value == "open" and any("pages" in b for b in declared) \
            and spec.get("pages") != "texture":
        raise PromptTemplateError(
            "BOOK_FRAGMENTS_REQUIRED",
            "an open book needs the printed-pages block (pages=%r), the "
            "shot type declares it" % (spec.get("pages"),))
    out = {}
    if value in BOOK_STATES:
        out["book"] = frag["BOOK_CLOSED"] + (
            " " + frag["BOOK_OPEN_MOTION"] if value == "open" else "")
    if spec.get("pages") == "texture":
        out["pages"] = frag["PRINTED_PAGES"]
    return out

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
    full.update(book_fragments(spec, st, frag, root=root))
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

    # book/pages are fixed contract fragments (never_trim): unscaled, uncut.
    fixed = ("book", "pages")
    sec = {k: (v if k in fixed else _kling_scale(v, scale))
           for k, v in full.items()}
    # Over the band: shorten, worst first, but never the fixed fragments.
    sec = {k: (v if k in fixed or k not in lim or lim[k]["max"] <= 0 else
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

def check_kling(prompt, sections, model, root=None, mode_id=None,
                banned_words=None, locked_block=None):
    """The Kling guard: the band, no bracket syntax, and the shared rules.

    Same verdict vocabulary as ``check()``: REFUSE beats TRIM beats FLAG beats
    PASS. REFUSE covers the hard max, ANY square bracket (Kling takes the move
    in plain words, so a bracket is a defect, not a camera command), a banned
    phrase and a duplicate sentence. The band and the hard max come from the
    manifest; the cap's status (VERIFIED / UNVERIFIED) is passed through by
    ``band_cap`` so an UNVERIFIED ceiling is never silently promoted.
    N-35 / 3B.3: the look's banned words outside the locked block are refused
    (STYLE_WORD_BANNED), same validator as ``check()``.
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
    # F-KLING-TEXT-BAIT: letter-bait prompt refuses here too, so a
    # hand-built Kling prompt that skips dispatch still cannot pass the
    # template checker. never_again owns the word list; this gate only
    # reports its refusal.
    try:
        if CORE_DIR not in sys.path:
            sys.path.insert(0, CORE_DIR)
        import never_again as _na
        _bait = _na.check_kling_prompt_text(prompt)
    except (ImportError, AttributeError):
        _bait = None
    if _bait is not None and _bait.get("code") == "TEXT_BAIT":
        reasons.append("KLING_TEXT_BAIT %s" % (_bait.get("detail"),))
    eff_banned = (list(banned_words) if banned_words is not None
                  else _banned_words_for(mode_id, root=root))
    if eff_banned:
        sw = check_style_words(prompt, eff_banned,
                               locked_block=locked_block or "")
        if sw.get("verdict") == "REFUSE":
            reasons.append("STYLE_WORD_BANNED %r: not this look's word; it may "
                           "appear only inside the locked block"
                           % (sw.get("hits") or [],))
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

# ---------------------------------------------------------------------------
# H3 native audio. minimax-h3/* always returns a stereo audio track and the
# provider exposes no flag to turn it off (references/prompt-templates/models/
# minimax-h3.json native_audio). "Silent clip" is therefore a POST-PROCESSING
# intent, never a provider flag: the request records the decision, the receipt
# echoes it plus what was actually observed, and a soundtrack may not be
# layered over a take that still carries its generated track.

#: retain = keep the generated track as the mix bed; reduce_music = keep
#: dialogue/ambience, duck the generated music; strip = remove the generated
#: track and lay the approved soundtrack over the take.
H3_NATIVE_AUDIO_DECISIONS = ("retain", "reduce_music", "strip")

#: The contract default: the Suno master is the soundtrack (video_router
#: 16.2), so the generated track is stripped in post. A request that names no
#: decision is recorded as this and is never left blank.
H3_NATIVE_AUDIO_DEFAULT = "strip"


def native_audio_block(spec=None):
    """The native-audio policy stamp for one H3 request and its receipt.

    ``decision`` comes from ``spec["native_audio"]`` (a string, or a dict with
    ``decision``); absent -> H3_NATIVE_AUDIO_DEFAULT. An unknown value raises
    H3_NATIVE_AUDIO_UNKNOWN -- a typo never silently becomes a strip.

    ``observed`` is what the delivered take actually carried
    (``{"has_audio": bool, "removed": bool}``); None means not established.
    ``provider_can_disable`` is always False: H3 cannot be asked for silence,
    so no caller may record a provider-side "no audio" flag.
    """
    raw = spec.get("native_audio") if isinstance(spec, dict) else None
    if isinstance(raw, dict):
        decision = raw.get("decision") or H3_NATIVE_AUDIO_DEFAULT
        observed = raw.get("observed")
    elif raw in (None, ""):
        decision, observed = H3_NATIVE_AUDIO_DEFAULT, None
    else:
        decision, observed = raw, None
    if decision not in H3_NATIVE_AUDIO_DECISIONS:
        raise PromptTemplateError(
            "H3_NATIVE_AUDIO_UNKNOWN",
            "%r is not one of %s"
            % (decision, ", ".join(H3_NATIVE_AUDIO_DECISIONS)))
    if observed is not None and not isinstance(observed, dict):
        raise PromptTemplateError(
            "H3_NATIVE_AUDIO_UNKNOWN",
            "observed must be a dict or None, got %r" % (observed,))
    return {"decision": decision,
            "provider_can_disable": False,
            "enforcement": "post_processing",
            "prompt_ambition": "silent",
            "observed": observed}


def layering_refusal(native_audio, soundtrack=False, audio_dropped=False):
    """-> None, or a refusal when a song would ride generated audio.

    Fires when an approved soundtrack is combined with a take that still
    carries its generated track: ``retain`` keeps it by definition, and a
    strip/reduce decision whose observed take shows audio present but not
    removed. A missing or unknown decision fails closed here -- the mixing
    decision cannot be audited, so it is never assumed safe.

    ``audio_dropped`` lets a caller that provably discards the take's own
    audio channel (final_assembler maps only the song) pass an unmeasured
    take; every other caller gets NATIVE_AUDIO_UNVERIFIED when the delivery
    was never measured, because unknown is not the same as removed.
    """
    if not soundtrack:
        return None
    block = native_audio if isinstance(native_audio, dict) else None
    decision = block.get("decision") if block else None
    if decision not in H3_NATIVE_AUDIO_DECISIONS:
        return {"reason_code": "DOUBLE_MUSIC",
                "detail": "a soundtrack is layered over a take with no valid "
                          "native_audio decision (%r); the mixing decision "
                          "cannot be audited" % (decision,)}
    if decision == "retain":
        return {"reason_code": "DOUBLE_MUSIC",
                "detail": "native_audio=retain keeps the generated track and "
                          "an approved soundtrack is layered over it; use "
                          "strip, or reduce_music with the music ducked"}
    observed = block.get("observed")
    if isinstance(observed, dict) and observed.get("has_audio") and \
            not observed.get("removed"):
        return {"reason_code": "DOUBLE_MUSIC",
                "detail": "native_audio=%s but the delivered take still "
                          "carries its generated track (observed.has_audio "
                          "set, removed not set) and a soundtrack is layered "
                          "over it" % decision}
    if observed is None and not audio_dropped:
        return {"reason_code": "NATIVE_AUDIO_UNVERIFIED",
                "detail": "native_audio=%s but the delivered take was never "
                          "measured; a soundtrack may not be layered over "
                          "audio whose removal is unproven" % decision}
    return None


def _text_record_clause(spec, frag):
    """N-27 / T-2 / 3A.3: one sentence per written object, then the pin.

    ``spec["text_on_screen"]`` is the text record slice for this shot: a list of
    {object, lines[]} entries (3A.2). Nothing is invented: an entry with no
    words is skipped, and a shot with no record carries the pin sentence alone.
    """
    rec = spec.get("text_on_screen")
    if not isinstance(rec, list):
        return ""
    items = []
    for e in rec:
        if not isinstance(e, dict):
            continue
        lines = [str(x) for x in (e.get("lines") or []) if str(x).strip()]
        obj = str(e.get("object") or "").strip()
        if not lines or not obj:
            continue
        quoted = ", ".join('"%s"' % x for x in lines)
        items.append("The %s reads exactly, in clear printed English: %s." % (obj, quoted))
    if not items:
        return ""
    return frag["TEXT_RECORD"].replace("{items}", " ".join(items))

def _prop_facing_clause(spec, frag):
    """N-120 / 3P: one fixed sentence per used prop, from the text record.

    Each ``spec["text_on_screen"]`` entry carries ``user``, ``faces`` and
    ``viewer_must_read`` (3P). The prop faces its user unless the record says
    the camera may read it; an insert sentence is used when the viewer must
    read it but the prop still faces its user. Nothing is invented: no words,
    no sentence. An older template root without the fragments returns "".
    """
    if not frag.get("PROP_FACING_USER"):
        return ""
    rec = spec.get("text_on_screen")
    out = []
    for e in rec if isinstance(rec, list) else []:
        if not isinstance(e, dict):
            continue
        obj = str(e.get("object") or "").strip()
        if not obj:
            continue
        words = ", ".join('"%s"' % str(x) for x in (e.get("lines") or [])
                          if str(x).strip())
        user = str(e.get("user") or "").strip()
        poss = ("%s'" % user) if user.endswith("s") else (
            "%s's" % user if user else "their")
        faces = str(e.get("faces") or "").strip().lower()
        if faces == "camera":
            if words:
                out.append(frag["PROP_FACING_CAMERA"].format(obj=obj, words=words))
        elif e.get("viewer_must_read"):
            if words:
                out.append(frag["PROP_FACING_INSERT"].format(
                    obj=obj, user_poss=poss, words=words))
        elif user or faces == "other person":
            out.append(frag["PROP_FACING_USER"].format(
                obj=obj, user=user or "the person who takes it",
                user_poss=poss))
    return " ".join(out)

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
    # N-121 / 3M.4: a prompt says who is there. When the beat's crowd state is
    # not empty, the planner supplies its own sentence for this place.
    if spec.get("crowd_sentence"):
        sec["subject"] += " " + spec["crowd_sentence"]
    # N-120 / 3P: every used prop states which way its reading side faces.
    facing = _prop_facing_clause(spec, frag)
    if facing:
        sec["subject"] += " " + facing
    act = "Start: %s End: %s Direction: %s" % (a["start"], a["end"],
                                               a["direction"])
    if spec.get("line_over_picture"):
        # N-21: a line plays over this picture, so nobody mouths it.
        act += " " + frag["MOUTHS_CLOSED"]
    elif st.get("mouth_rule"):
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
    sec.update(book_fragments(spec, st, frag, root=root))
    sec["physics"] = spec["motion_physics"]
    sec["beats"] = " ".join("%s: %s" % (t, d) for t, d in spec["beats"])
    # N-121 / 3M.4: the crowd is stated by the shot's own crowd state. The
    # blanket "no extra people" line is gone; it survives only for an empty room.
    crowd = str(spec.get("crowd_state") or "").strip().lower()
    if crowd == "empty" and frag.get("CROWD_EMPTY"):
        sec["subject"] = sec["subject"] + " " + frag["CROWD_EMPTY"]
    elif crowd and frag.get("CROWD_STATE"):
        sec["subject"] = sec["subject"] + " " + frag["CROWD_STATE"]
    sec["policy"] = frag["SOUND_AND_TEXT"]
    # N-27 / T-2: H3 describes the words that are already in the picture.
    text_clause = _text_record_clause(spec, frag)
    if text_clause:
        sec["policy"] = sec["policy"] + " " + text_clause
    neg = (list(frag["BASE_NEGATIVES"]) + st.get("negatives", [])
           + spec.get("negatives_extra", []))
    sec["negatives"] = "; ".join(neg[:16]) + "."
    order = [s["id"] for s in h3["sections"]]
    leads = {s["id"]: s["lead"] for s in h3["sections"]}
    parts = ["%s: %s" % (leads[k], sec[k]) for k in order if k in sec]
    return "\n".join(parts), {k: len(v) for k, v in sec.items()}

#: F-PM-5 / R-2: stillness and angle-cheat phrases refused in every prompt.
#: Multiword only, so the camera command [Static shot] never matches.
#: Whole-performance stillness instructions only. A single beat ("she stays
#: still for a blink") or a camera on a tripod ("locked off") is legitimate
#: and never matched; what is refused is a sentence that freezes the take.
STILLNESS_PHRASES = (
    "minimal head movement", "minimal movement at all", "no body movement",
    "no movement at all", "frozen in place", "frozen body",
    "steady locked camera", "settle and hold", "held stillness",
    "hold completely still", "the body does not move at all",
)
ANGLE_CHEAT_PHRASES = (
    "cheat the angle", "angle cheat", "cheat the cut", "hide the mouth",
    "cover the mouth with", "crop out the", "freeze the frame",
)
#: F-PIC-3: three places stacked into one frame, or a panel/split-screen
#: layout, is refused unless the run owner approved it on the storyboard.
MULTI_LOCATION_PHRASES = (
    "split screen", "split-screen", "two panels", "three panels",
    "panel layout", "collage of", "montage of places",
    "two places at once", "three places at once",
    "two locations in frame", "three locations in frame",
    "at the same time in two places", "in two rooms at once",
)
#: G-STORY-04 / N-14: a sentence that empties a room the story says is full.
#: Applied only when the shot's cast says the place is full (more singers than
#: ``empty_room_singer_min``); an empty-room shot keeps its own sentence.
EMPTY_ROOM_PHRASES = (
    "no congregation", "no extra people", "empty pews", "the pews are empty",
    "empty room", "nobody else in the room", "no one else is present",
    "no crowd", "without a congregation",
)

#: F-PIC-3: markers of a second or third place in one frame, and of a
#: split-screen or panel layout. Prose only; the words are ordinary nouns a
#: one-place prompt never needs twice.
MULTI_LOCATION_MARKERS = (
    "cut to", "meanwhile in", "at the same time across", "across the street in",
    "we see both", "in two rooms", "from the kitchen to the", "through to the",
    "in the background room", "upstairs and the", "inside and outside",
    "living room and the kitchen", "split screen", "split-screen", "panel",
    "panels", "triptych", "side by side scenes", "two places at once",
)
SPLIT_FRAME_MARKERS = ("split screen", "split-screen", "triptych",
                       "grid of scenes", "collage of", "panel layout",
                       "comic panel", "divided into panels", "four panels")

def _grams8(text):
    """The set of 8-word runs in a text, lowercased, punctuation stripped."""
    words = re.findall(r"[a-z0-9']+", str(text or "").lower())
    return {" ".join(words[i:i + 8]) for i in range(len(words) - 7)}

def _without_run(text, run):
    """``text`` with one occurrence of ``run`` removed (never counted twice)."""
    if not run or run not in text:
        return text
    return text.replace(run, " ", 1)

def _banned_words_for(mode_id, root=None):
    """N-35 / 3B.3: the named mode's banned list.

    The mode file's own ``banned_words`` wins when present (U-LOOK carries one;
    extended modes inherit through ``extends``). Until then the manifest's per-
    category list answers: the 3D/2D looks ban the photoreal set, the realism
    looks ban the animated set. Returns [] when neither names one, so a look
    with no list is never refused by invention.
    """
    if not mode_id:
        return []
    mode = load("mode", mode_id, root=root, required=False) or {}
    words = mode.get("banned_words")
    if words:
        return [str(w) for w in words if str(w).strip()]
    if mode.get("extends"):
        base_words = _banned_words_for(mode["extends"], root=root)
        if base_words:
            return base_words
    qr = load("manifest", root=root)["quality_rules"]
    cats = qr.get("banned_style_words") or {}
    mode_id = str(mode_id or "").lower()
    if any(k in mode_id for k in ("realism", "golden", "live")):
        return [str(w) for w in (cats.get("realism") or [])]
    return [str(w) for w in (cats.get("animated") or [])]

def check(prompt, sections, model="minimax-h3/image-to-video", root=None,
          picture_text=None, look_text=None, identity_text=None,
          cast=None, expression=None, mode_id=None, banned_words=None,
          locked_block=None, style_lock=None):
    """The band guard and the quality rules.

    -> {"verdict": REFUSE|FLAG|TRIM|PASS, "chars", "reasons"}. REFUSE wins over
    everything: a prompt never leaves this function over the hard max, over one
    bracket group, or carrying a banned phrase or a duplicate sentence.
    ``mode_id`` selects the look's banned words for N-35 / 3B.3; an explicit
    ``banned_words`` list wins, and ``locked_block`` is the exact style text the
    lock placed in the prompt, so the look's own words (a 3D block that says
    'soft pores') never trip the scan. ``style_lock`` is the run's look-lock
    record; when the spec carries one, the receipt (see ``receipt()``) stamps
    it and the banned scan strips its block.
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
    # F-PIC-3: one place per frame. Three places stacked in one frame, a
    # split-screen or a panel layout without approval is refused.
    low2 = prompt.lower()
    places = [w for w in MULTI_LOCATION_MARKERS if w in low2]
    if len(places) > 2 or any(w in low2 for w in SPLIT_FRAME_MARKERS):
        reasons.append("H3_MULTI_LOCATION %d place marker(s) %s: one shot is "
                       "one place; split the shots instead"
                       % (len(places), places[:4]))
    # F-PM-5 / R-2: stillness words and angle cheats are refused. A stillness
    # instruction wins over every other motion word and freezes the take; an
    # angle cheat hides a defect the checks must see. The camera command
    # [Static shot] is a bracket token and never matches a phrase here.
    low = prompt.lower()
    for ph in STILLNESS_PHRASES:
        if ph in low:
            reasons.append("STILLNESS_WORD %r: brief one body action instead, "
                           "or split the shot" % ph)
    for ph in ANGLE_CHEAT_PHRASES:
        if ph in low:
            reasons.append("ANGLE_CHEAT %r: never hide a defect by cheating the "
                           "angle, cropping, freezing or stretching" % ph)
    # F-PM-3: no re-description of the picture, no identity overload. The
    # identity/continuity section is the ONE place the face may be named;
    # anywhere else an 8-word run shared with the shot's picture prompt or the
    # look/bible text repeats what the reference picture already carries.
    ident = "" if identity_text is None else str(identity_text)
    cap = qr.get("identity_cap_chars", 1400)
    if identity_text is not None and len(ident) > cap:
        reasons.append("H3_IDENTITY_OVER_CAP %d > %s: trim the identity block; "
                       "the reference pictures carry the face" % (len(ident), cap))
    if picture_text or look_text:
        ident_grams = _grams8(ident)
        body = _without_run(prompt, ident) if ident else prompt
        shared = ((_grams8(body) & _grams8(picture_text or ""))
                  | (_grams8(body) & _grams8(look_text or ""))) - ident_grams
        if shared:
            reasons.append("H3_REDESCRIBES_PICTURE %d shared 8-word run(s), "
                           "first %r" % (len(shared), sorted(shared)[0][:80]))
    # G-STORY-04 / N-14: never order an empty room on a shot the story says is
    # full. A cast that lists more singers than the small-room line is a full
    # place; an Avoid or negative sentence that empties it is refused.
    if cast is not None:
        singers = cast.get("singers") if isinstance(cast, dict) else cast
        try:
            n_singers = int(singers or 0)
        except (TypeError, ValueError):
            n_singers = 0
        if n_singers > qr.get("empty_room_singer_min", 4):
            hit = [ph for ph in EMPTY_ROOM_PHRASES if ph in low]
            if hit:
                reasons.append("H3_EMPTY_ROOM %r: the beat shows %d singers in "
                               "this place, so the prompt says who is there, "
                               "never that the room is empty (G-STORY-04)"
                               % (hit[0], n_singers))
    # N-35 / 3B.3: the look's banned words outside the locked block are refused
    # (STYLE_WORD_BANNED). The locked block is stripped before the scan, so a
    # 3D block's own 'soft pores' never trips its own list.
    eff_banned = (list(banned_words) if banned_words is not None
                  else _banned_words_for(mode_id, root=root))
    strip_block = locked_block or ""
    if not strip_block and isinstance(style_lock, dict):
        strip_block = (style_lock.get("h3_block")
                       or (style_lock.get("blocks") or {}).get("h3_block") or "")
    if eff_banned:
        sw = check_style_words(prompt, eff_banned, locked_block=strip_block)
        if sw.get("verdict") == "REFUSE":
            reasons.append("STYLE_WORD_BANNED %r: not this look's word; it may "
                           "appear only inside the locked block" % (sw.get("hits") or [],))
    # G-MOTION-01: on a singing shot the stillness template sentence is refused
    # by the STILLNESS_WORD list above, which is the whole rule for a prompt --
    # brief one downbeat body action (sway, clap, robe swing) instead.
    if reasons:
        return {"verdict": "REFUSE", "chars": n, "reasons": reasons,
                "repeat_8gram": round(rep, 4)}
    # F-PM-1 / N-77: a section-thin or below-floor prompt is a REFUSE, never a
    # FLAG build() would let ship (build blocks only REFUSE/TRIM). It routes
    # through expand(), which raises H3_THIN_SPEC naming the empty slots, so
    # the planner supplies the facts instead of shipping a thin prompt.
    if section_reasons:
        return {"verdict": "REFUSE", "chars": n, "reasons": section_reasons,
                "repeat_8gram": round(rep, 4)}
    if b.get("floor") is not None and n < b["floor"]:
        return {"verdict": "REFUSE", "chars": n,
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

#: The shot's OWN sections. The lock blocks (look, continuity/identity, policy,
#: reference, negatives) are copied whole by design and are never compared.
_OWN_SECTIONS = ("header", "subject", "action", "camera", "lens_light",
                 "physics", "beats")

def check_run(prompts, root=None):
    """Per-run cross-prompt repeat check (F-PM-3, QM-03).

    ``prompts`` is a list of prompt strings, or of {"prompt", "sections"} dicts.
    Across a run no 8-word run of the shot's own sections may appear in more
    than ``quality_rules.cross_prompt_repeat.max_shared_run_ratio`` of them: one
    writer copying another's action or framing is a re-description of a shot it
    has not seen. File-wide lock blocks are exempt by design.
    Returns {"verdict": "REFUSE"|"PASS", "reasons", "shared", "checked"}.
    """
    qr = (load("manifest", root=root)["quality_rules"]
          .get("cross_prompt_repeat") or {})
    limit = float(qr.get("max_shared_run_ratio", 0.15))
    texts = []
    for p in prompts or []:
        if isinstance(p, dict):
            sec = p.get("sections") or {}
            own = " ".join(sec.get(k, "") if isinstance(sec.get(k), str) else ""
                           for k in _OWN_SECTIONS) or str(p.get("prompt") or "")
            texts.append(own)
        else:
            texts.append(str(p or ""))
    n = len(texts)
    if n < 2:
        return {"verdict": "PASS", "reasons": [], "shared": [], "checked": n}
    seen = {}
    for t in texts:
        for g in _grams8(t):
            seen[g] = seen.get(g, 0) + 1
    over = sorted(g for g, c in seen.items() if c / n > limit)
    if over:
        return {"verdict": "REFUSE", "checked": n, "shared": over[:20],
                "reasons": ["CROSS_PROMPT_REPEAT %d 8-word run(s) appear in "
                            "more than %.0f%% of the run's %d prompts, first %r"
                            % (len(over), limit * 100, n, over[0][:80])]}
    return {"verdict": "PASS", "reasons": [], "shared": [], "checked": n}

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
    # F-PM-1: check() now returns REFUSE for a section-thin or below-floor
    # prompt; both route here, and both raise H3_THIN_SPEC. A bare FLAG is
    # still accepted so no older caller breaks.
    thin = v == "FLAG" or (
        v == "REFUSE" and reasons
        and all(r.startswith(("SECTION_THIN", "H3_BELOW_FLOOR")) for r in reasons))
    if not thin:
        return prompt, verdict
    under_floor = any(r.startswith("H3_BELOW_FLOOR") for r in reasons)
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
           if (v == "FLAG" or under_floor) else "section-thin",
           ", ".join(empty) if empty else "(none named by the shot type)",
           "; ".join(reasons) or "H3_BELOW_FLOOR"))

def check_style_words(prompt, banned_words, locked_block=""):
    """N-35 / 3B.3: refuse a look's banned words outside the locked block.

    ``banned_words`` is the chosen look's own list (each mode file carries it);
    ``locked_block`` is the exact style text the lock placed in the prompt, so
    the look's own words (a 3D block that says 'soft pores', say) never trip on
    themselves. A word found anywhere in the rest of the prompt is
    STYLE_WORD_BANNED. Pure: the caller passes the list, so this works before
    U-LOOK's mode_files module is on the tree; wire it to mode_files.load_mode's
    list at dispatch.
    Returns {"verdict": "REFUSE"|"PASS", "code", "hits"}.
    """
    body = _without_run(str(prompt or ""), locked_block) if locked_block else str(prompt or "")
    low = body.lower()
    hits = [str(w) for w in (banned_words or []) if str(w).lower() in low]
    if hits:
        return {"verdict": "REFUSE", "code": "STYLE_WORD_BANNED",
                "hits": hits,
                "detail": "style words %r are not from the locked block" % (hits[:5],)}
    return {"verdict": "PASS", "code": None, "hits": []}


def style_stamp(lock, block_text=""):
    """N-34 / 3B.3: the style-lock stamp for one prompt.

    ``lock`` is the run's look-lock record (a dict with ``version`` and the
    style blocks / their fingerprint). The stamp records the lock version and
    the sha256 of the locked block the prompt carries, so the dispatcher can
    refuse an unstamped, stale or altered style section
    (STYLE_BLOCK_NOT_FROM_LOCK, U-DISPATCH). Returns None when no lock is held:
    a prompt with no lock is never silently treated as stamped.
    """
    if not isinstance(lock, dict):
        return None
    version = lock.get("version") or lock.get("lock_version")
    block = block_text or lock.get("h3_block") or (lock.get("blocks") or {}).get("h3_block") or ""
    return {"lock_version": version,
            "block_sha256": hashlib.sha256(str(block).encode("utf-8")).hexdigest()}


def receipt(spec, prompt, sections, verdict, root=None):
    """The prompt receipt: sha256 + template version + section char map.

    Also echoes the native-audio decision (native_audio_block): the mixing
    decision travels with the exact prompt bytes it applies to, so no paid H3
    take can be assembled without one.
    """
    man = templates_dir(root) / "manifest.json"
    rec = {"shot_id": spec["shot_id"], "model": spec["model"],
           "look": spec["look"], "mode": spec["mode"],
           "shot_type": spec["shot_type"],
           "template_version": load("manifest", root=root)["template_version"],
           "manifest_sha256": hashlib.sha256(man.read_bytes()).hexdigest(),
           "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
           "chars": len(prompt), "band": band(spec["model"], root=root),
           "sections": sections, "check": verdict,
           "native_audio": native_audio_block(spec)}
    # N-34: the style stamp travels with the prompt when the spec carries the
    # run's look lock; the dispatcher refuses STYLE_BLOCK_NOT_FROM_LOCK.
    stamp = style_stamp(spec.get("style_lock"))
    if stamp is not None:
        rec["style_stamp"] = stamp
    return rec

def has_receipt(prompt_sha256, receipts):
    """True when one receipt in ``receipts`` matches this prompt's sha256."""
    for r in receipts or []:
        if isinstance(r, dict) and r.get("prompt_sha256") == prompt_sha256:
            return True
    return False

# ---------------------------------------------------------------------------
# U15h: the length-class table -- ONE table the card, the planner and QC read.

#: The six card lengths (design 6). The table keys are these strings.
#: S75-W05-U3: the scattered duration tuple is REMOVED (D12); THE one table is
#: suno_recipe.duration_registry.CANONICAL_DURATION_S. __getattr__ is defined
#: first so any import order resolves without an import cycle (the registry
#: leaf is zero-import), then the value is bound for this module's lookups.
_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

def __getattr__(name):
    if name == "LENGTH_CLASSES_S":
        try:
            from suno_recipe.duration_registry import CANONICAL_DURATION_S
        except ImportError:
            try:
                from duration_registry import CANONICAL_DURATION_S
            except ImportError:
                from ..suno_recipe.duration_registry import CANONICAL_DURATION_S
        globals()["LENGTH_CLASSES_S"] = CANONICAL_DURATION_S
        return CANONICAL_DURATION_S
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


try:
    from suno_recipe.duration_registry import CANONICAL_DURATION_S  # noqa: E402
except ImportError:
    try:
        from duration_registry import CANONICAL_DURATION_S  # noqa: E402
    except ImportError:
        from ..suno_recipe.duration_registry import CANONICAL_DURATION_S  # noqa: E402

LENGTH_CLASSES_S = CANONICAL_DURATION_S

#: W-G-008 minute-lanes (PR #96/#1710, merged to main 2026-10-09). U15h hook:
#: lane_planner.py is NOT on this base branch (unit/FU-U15b predates the
#: merge), so the constants below mirror lane_planner's own (LANE_MIN_SONG_S
#: 120, LANE_TARGET_S 60, KIE_PER_WINDOW 20, KIE_LANE_SHARE_NUM 18). When the
#: branch carries lane_planner.py, length_class_code() imports it and the
#: table becomes provably equal to the lane module itself; until then the
#: fallback formula is the same arithmetic, and PT.lane_source() says which
#: answered.
LANE_MIN_SONG_S = 120.0
LANE_TARGET_S = 60.0
KIE_PER_WINDOW = 20
KIE_LANE_SHARE_NUM = 18

def lane_source():
    """"lane_planner" when W-G-008's module is on this tree, else "hook"."""
    import importlib.util
    return ("lane_planner" if importlib.util.find_spec("lane_planner")
            else "hook")

def _lanes(L):
    """(lanes, per-lane NEW KIE requests per 10 s) for one chosen length."""
    import importlib.util
    if importlib.util.find_spec("lane_planner") is not None:
        import lane_planner as _LP                      # W-G-008's own module
        n = _LP.lane_count(L)
        return n, _LP.lane_share(n)
    n = 1 if L < LANE_MIN_SONG_S else int(math.ceil(L / LANE_TARGET_S))
    return n, (KIE_PER_WINDOW if n <= 1 else max(1, KIE_LANE_SHARE_NUM // n))

def length_class_code(L):
    """The class row COMPUTED from the code -- never a second formula.

    Reads length_formula.plan (song rows), lipsync_clips.budget (clip counts
    and seconds), shot_planner.plan_generation_count (ceil(D/4) shots), the
    H3 remainder (shots minus lip-sync), the lanes (lane_planner when it is
    on the tree, else its formula via _lanes) and the product band (10-15%
    of D, U13). The table in references/prompt-templates/length-classes.json
    must equal this for every card length.
    """
    import length_formula as _LF
    import lipsync_clips as _LC
    if CORE_DIR not in sys.path:
        sys.path.insert(0, CORE_DIR)
    from shot_planner import shot_planner as _SP
    L = int(L)
    D = L - 2                                            # END_EARLY_S master rule
    p = _LF.plan(L)
    b = _LC.budget(D)
    shots = _SP.plan_generation_count(D)
    lanes, share = _lanes(L)
    ext = p.get("extend") or []
    return {
        "chosen_s": L, "delivered_s": D, "bracket": p["bracket"],
        "shots_total": shots,
        "lipsync_clips": [b["min_clips"], b["max_clips"]],
        "lipsync_seconds": [round(b["total_min_s"], 1),
                            round(b["total_max_s"], 1)],
        "h3_shots": [shots - b["max_clips"], shots - b["min_clips"]],
        "h3_seconds": [round(D - b["total_max_s"], 1),
                       round(D - b["total_min_s"], 1)],
        "lanes": lanes, "kie_new_requests_per_lane_per_10s": share,
        "hooks": p["hook_repeats"],
        "song_words": {k: p["words"][k] for k in
                       ("total", "spoken", "sung", "opener_max")},
        "sections": dict(p["sections"]),
        "instrumental_breaks": {"count": p["instrumental"]["breaks"],
                                "seconds_each": p["instrumental"]["seconds_each"]},
        "spoken_share_planned_pct": p["spoken_share_pct_planned"],
        "product_seconds": [round(0.10 * D, 1), round(0.15 * D, 1)],
        "suno_generations": ("1 base" if not ext
                             else "1 base + %d extends" % len(ext)),
    }

#: Every field of the class row the table must equal the code on.
CLASS_FIELDS = ("delivered_s", "shots_total", "lipsync_clips",
                "lipsync_seconds", "h3_shots", "h3_seconds", "lanes",
                "kie_new_requests_per_lane_per_10s", "hooks", "song_words",
                "sections", "instrumental_breaks", "spoken_share_planned_pct",
                "product_seconds", "suno_generations")

def length_class(L, root=None):
    """The one table row for a chosen length, proved equal to the code.

    Returns the table row unchanged when every CLASS_FIELDS value equals
    length_class_code(L); raises PROMPT_LENGTH_CLASS_DRIFT naming each
    drifted field otherwise. This is the single reader the card, the planner
    and QC use: a stale table can never be read silently.
    """
    L = int(L)
    table = (load("length_classes", root=root).get("classes") or {})
    row = table.get(str(L))
    if not isinstance(row, dict):
        raise PromptTemplateError("PROMPT_LENGTH_CLASS_UNKNOWN",
                                  "no class %d in length-classes.json" % L)
    code = length_class_code(L)
    drift = {f: {"table": row.get(f), "code": code[f]} for f in CLASS_FIELDS
             if row.get(f) != code[f]}
    if drift:
        raise PromptTemplateError(
            "PROMPT_LENGTH_CLASS_DRIFT",
            "length-classes.json class %d disagrees with the code: %s"
            % (L, "; ".join("%s table=%r code=%r" % (f, d["table"], d["code"])
                            for f, d in sorted(drift.items()))))
    return row

def product_seconds_bounds(L):
    """The (floor, cap) of the product passage's seconds for one length."""
    D = int(L) - 2
    return (round(0.10 * D, 1), round(0.15 * D, 1))

def check_product_seconds(shots, chosen_length_s):
    """[] when the shot plan's product seconds fall in 10-15% of D (U13).

    The product shots are the ones the planner marked with a product
    visibility (shot_planner.PRODUCT_SHOT_VISIBILITY). Returns the reasons
    naming the measured seconds and the band otherwise. Cross-check only:
    the band itself lives in the class row (length_class_code), never here.
    ponytail: no stage calls this yet; wire it into the storyboard review
    when U13's card block lands.
    """
    if not isinstance(shots, list):
        raise PromptTemplateError("BAD_SHOTS", "shots must be a list")
    D = int(chosen_length_s) - 2
    if D <= 0:
        raise PromptTemplateError("BAD_LENGTH", "chosen length must exceed 2 s")
    if CORE_DIR not in sys.path:
        sys.path.insert(0, CORE_DIR)
    from shot_planner import shot_planner as _SP
    lo, hi = product_seconds_bounds(chosen_length_s)
    seconds = 0.0
    for s in shots:
        if not isinstance(s, dict) \
                or s.get("product_visibility") not in _SP.PRODUCT_SHOT_VISIBILITY:
            continue
        start, end = s.get("song_start"), s.get("song_end")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) \
                and end > start:
            seconds += float(end) - float(start)
        elif isinstance(s.get("dur"), (int, float)) and s["dur"] > 0:
            seconds += float(s["dur"])
    seconds = round(seconds, 1)
    if lo <= seconds <= hi:
        return []
    return ["product seconds %.1f outside %g-%g s (10-15%% of the %d s "
            "delivered length)" % (seconds, lo, hi, D)]

__all__ = ["TOOL_NAME", "TOOL_VERSION", "MODES", "LOOKS", "SHOT_TYPES",
           "CORE_DIR", "SKILL_ROOT", "TEMPLATES_DIR", "PromptTemplateError",
           "templates_dir", "catalog_path", "load", "caps",
           "KLING_AVATAR_MODEL", "assemble_kling_avatar", "check_kling_avatar",
           "LIPSYNC_MODEL", "LIPSYNC_PROMPT_PRESENT",
           "VILLAIN_SHOT_TYPE_NAME", "band", "assemble_h3", "check", "check_run", "expand",
           "STILLNESS_PHRASES", "ANGLE_CHEAT_PHRASES", "MULTI_LOCATION_MARKERS",
           "SPLIT_FRAME_MARKERS",
           "receipt", "has_receipt", "style_stamp", "check_style_words", "locked_look_block", "assemble_kling_video", "check_kling",
           "kling_section_limits", "band_cap",
           "LENGTH_CLASSES_S", "CLASS_FIELDS", "LANE_MIN_SONG_S",
           "LANE_TARGET_S", "KIE_PER_WINDOW", "KIE_LANE_SHARE_NUM",
           "lane_source", "length_class_code", "length_class",
           "product_seconds_bounds", "check_product_seconds"]
