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

# ---------------------------------------------------------------------------
# U15h: the length-class table -- ONE table the card, the planner and QC read.

#: The six card lengths (design 6). The table keys are these strings.
LENGTH_CLASSES_S = (60, 90, 120, 180, 300, 600)

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
           "VILLAIN_SHOT_TYPE_NAME", "band", "assemble_h3", "check", "expand",
           "receipt", "has_receipt",
           "LENGTH_CLASSES_S", "CLASS_FIELDS", "LANE_MIN_SONG_S",
           "LANE_TARGET_S", "KIE_PER_WINDOW", "KIE_LANE_SHARE_NUM",
           "lane_source", "length_class_code", "length_class",
           "product_seconds_bounds", "check_product_seconds"]
