#!/usr/bin/env python3
"""Hybrid style bible (owner decision D21, plan section 6.11). Stdlib only.

The Hybrid look is a black-and-white hand-drawn sketch in the Diary of a
Wimpy Kid style (wobbly ink line art, comic sound words like "HONK", speech
bubbles) that SWITCHES to realism and back, and ends in a warm golden realism
finale. "Realism" means real-looking live-action shots from the approved
elevator look, whose exact recipe lives in `style-bibles/realism-cinematic.md`
(decision D19). Realism is NOT 3D animation. A 2D-to-3D COMBINATION is never
offered by this bible (decision D18: 2D-to-3D is not hybrid). Plan 6.11 gives
Canvas to 3D its own look with its own bible, outside core/style_bibles/hybrid/;
nothing in this module ever renders or offers 2D-to-3D.

What this module does:

1. `offered_styles()` / `assert_offered()` -- the styles this bible compiles are
   2D, Lifelike 3D and Hybrid; any 2D+3D combination is refused by name.
2. `plan_hybrid(shots)` -- per-shot sketch / realism / golden-realism plan from
   the storyboard beats, honoring the switching rules: hold each style at
   least 3 seconds (no flicker), switch on a 0.3-0.4 s dissolve, golden
   realism only as the finale, no lip-sync on sketch shots.
3. `realism_block()` -- the exact `[STYLE]...[/STYLE]` recipe text read from
   `style-bibles/realism-cinematic.md`, byte-for-byte. Missing or malformed
   recipe -> refuse (fail closed), naming every path searched.
4. `compile_prompt(shot, mode, ...)` -- deterministic prompt compile. The
   realism segment of a realism or golden prompt IS the recipe block; the
   golden finale adds a separate `[FINALE]` block after it and never edits the
   recipe.

Flare rule and prompt caps belong to core/product_style_bible/bible.py; this
module composes blocks only, it never renders, calls a provider or spends.
"""
from __future__ import annotations

import hashlib
import os
import re

try:
    from product_style_bible import bible as _bible
except ImportError as _e:  # imported as core.style_bibles.hybrid
    if "product_style_bible" not in str(_e):
        raise
    _bible = None

TOOL_NAME = "hybrid_bible"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.style-bibles.hybrid/v1"

#: Plan 6.11 switching constants.
HOLD_MIN_SECONDS = 3.0              # hold each style at least 3 s (no flicker)
DISSOLVE_SECONDS = (0.3, 0.4)       # short dissolve on matching poses/framings

#: Plan 6.11: which beats take which style.
SKETCH_BEATS = frozenset(("comedy", "setup", "everyday", "doubt", "transition"))
REALISM_BEATS = frozenset(("pain", "shock", "humiliation", "numbness", "anger",
                           "exhaustion", "fear", "turn", "revelation"))
GOLDEN_BEATS = frozenset(("transformation", "payoff"))

MODE_SKETCH = "sketch"
MODE_REALISM = "realism"
MODE_GOLDEN = "golden-realism"
MODES = (MODE_SKETCH, MODE_REALISM, MODE_GOLDEN)

SKETCH_STYLE_ID = "hybrid-sketch-bw-01"
REALISM_STYLE_ID = "realism-cinematic-01"   # recipe style_id, from D19 look

#: The styles this bible compiles (decision D18 for the three-way menu; the
#: plan 6.11 five-look card is core/choice_card/looks/, not this module).
#: Hybrid is sketch switching to realism; Lifelike 3D is a style of its own,
#: never a hybrid target, and no 2D-to-3D combination exists in this module.
OFFERED = {
    "2d-hand-painted": {
        "label": "2D",
        "description": "hand-painted 2D cartoon (current Style Bible block)",
    },
    "lifelike-3d": {
        "label": "Lifelike 3D",
        "description": "cinematic CGI animation; clearly animated, lifelike faces",
    },
    "hybrid-sketch-realism": {
        "label": "Hybrid",
        "description": ("black-and-white Wimpy-Kid sketch switching to realism "
                        "and back, warm golden realism finale"),
    },
}

#: Refused by name, case/separator-insensitive normal form.
BANNED_STYLE_ALIASES = frozenset((
    "versione", "hybrid3d", "hybrid3danimation", "2dto3d", "2dcartoon3d",
    "cartoon3d", "sketch3d",
))

RECIPE_ENV_VAR = "HYBRID_REALISM_RECIPE"
RECIPE_RELATIVE = os.path.join("style-bibles", "realism-cinematic.md")

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))          # <lane>/core/style_bibles/hybrid
# C3: the recipe ships with the skill (references/style-bibles/). Operator-Mac
# home-folder defaults are gone from shipped code.

_STYLE_BLOCK_RE = re.compile(r"\[STYLE\][^\[]*?\[/STYLE\]", re.DOTALL)

#: Phrases the recipe must carry or it is not the D19 look (fail closed).
RECIPE_REQUIRED_PHRASES = (
    "photoreal cinematic live-action look",
    "natural skin texture",
    "shallow depth of field",
    "35mm film grade",
    "no cartoon",
)


class HybridError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


# --------------------------------------------------------------- sketch ----

#: Full Style Bible record for the sketch half. Valid against
#: product_style_bible.bible.validate_style when that module is importable.
SKETCH_STYLE = {
    "schema_version": "1.0.0",
    "style_id": SKETCH_STYLE_ID,
    "aspect_ratio": "9:16",
    "aesthetic": ("black-and-white hand-drawn comic sketch in the Diary of a "
                  "Wimpy Kid style: wobbly ink line art, simple rounded "
                  "shapes, deadpan comic staging; comic sound words like HONK "
                  "and speech bubbles carry the dialogue"),
    "rendering_style": ("monochrome pen-and-ink drawing on white paper, single "
                        "line weight with hand-hatched shading; no colour, no "
                        "gradients, no photoreal texture, no 3D render"),
    "camera_language": ("flat comic-panel staging, eye-level medium and wide "
                        "shots, characters fully readable at phone width; "
                        "exaggerated reaction framing for comedy beats"),
    "lens_tendencies": ("no photographic depth; flat comic perspective with "
                        "clear foreground line art and simple background sets"),
    "lighting_doctrine": ("white paper base with black ink shading and grey "
                          "hatching; light is drawn, never rendered"),
    "contrast_architecture": ("high-contrast black ink on white paper, "
                              "mid-grey hatch only for shadow shapes"),
    "environment_texture": ("hand-drawn sets in the same ink line family as "
                            "the characters: simple furniture, doorframes and "
                            "props with visible sketch strokes"),
    "grain_sharpness": ("clean paper grain, crisp ink edges, no photographic "
                        "grain and no sharpening halo"),
    "color_palette": ["black ink", "white paper", "mid grey hatch"],
    "visual_continuity_constraints": [
        "the character is identical across sketch and realism: same face, "
        "hair, glasses and accessories (reference-image keyframes and the "
        "identity lock govern both halves)",
        "same ink line family and paper tone across every sketch shot",
        "dialogue appears as speech bubbles; comic sound words (HONK, CLANG, "
        "THUD) may punctuate action; no lip-sync on sketch shots",
        "no colour, no photorealism and no 3D render anywhere in sketch mode",
    ],
    "banned_visual_cliches": [
        "colour in sketch mode",
        "photoreal skin in sketch mode",
        "3D render in sketch mode",
        "2D-to-3D style switching",
    ],
}

SOUND_WORDS = ("HONK", "CLANG", "THUD", "RING", "SLAM", "GULP")


def validate_sketch():
    """Error list (empty = the sketch record is a valid Style Bible)."""
    if _bible is None:
        raise HybridError("STYLE_BIBLE_UNAVAILABLE",
                          "product_style_bible not importable; run from core/")
    return _bible.validate_style(SKETCH_STYLE)


def sketch_style(aspect_ratio=None):
    """Copy of the sketch record; optional aspect override (validated later)."""
    rec = dict(SKETCH_STYLE)
    rec["color_palette"] = list(SKETCH_STYLE["color_palette"])
    rec["visual_continuity_constraints"] = \
        list(SKETCH_STYLE["visual_continuity_constraints"])
    rec["banned_visual_cliches"] = list(SKETCH_STYLE["banned_visual_cliches"])
    if aspect_ratio is not None:
        rec["aspect_ratio"] = aspect_ratio
    return rec


# ------------------------------------------------------------- offering ----

def _norm(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def offered_styles():
    """The style menu (plan 6.11 / decision D18). Exactly three entries."""
    return {sid: dict(rec) for sid, rec in OFFERED.items()}


def assert_offered(style_id):
    """Refuse anything this bible does not compile.

    A 2D-to-3D combination is refused by name with 2D_TO_3D_NOT_OFFERED:
    decision D18 says 2D-to-3D is not hybrid, so this bible never offers one
    (plan 6.11's Canvas to 3D is a separate look with its own bible, outside
    core/style_bibles/hybrid/). Anything else outside OFFERED is refused with
    STYLE_NOT_OFFERED.
    """
    norm = _norm(style_id)
    if norm in BANNED_STYLE_ALIASES or ("2d" in norm and "3d" in norm):
        raise HybridError(
            "2D_TO_3D_NOT_OFFERED",
            "%r: a 2D-to-3D combination is not hybrid and is never offered by "
            "this bible (decision D18; Canvas to 3D is a separate look). "
            "Styles this bible compiles: %s"
            % (style_id, ", ".join(sorted(OFFERED))))
    if style_id not in OFFERED:
        raise HybridError("STYLE_NOT_OFFERED",
                          "%r is not one of the offered styles: %s"
                          % (style_id, ", ".join(sorted(OFFERED))))
    return style_id


# ------------------------------------------------------- realism recipe ----

def recipe_candidate_paths(explicit=None, lane_dir=None):
    """Ordered absolute paths where realism-cinematic.md may live.

    An explicit path is authoritative: it is the only candidate, so a pinned
    recipe that is absent refuses instead of silently loading another file.
    Otherwise C3 order: the skill's own folder first
    (MODULE_DIR/../../../references/style-bibles/realism-cinematic.md), then
    an env override, then a lane fixture, then a walk up from this module to
    the skill root and beyond. Operator-Mac defaults are not searched.
    """
    out = []

    def add(path):
        path = os.path.abspath(path)
        if path not in out:
            out.append(path)

    if explicit:
        add(explicit)
        return out
    # C3: skill's own folder first —
    # MODULE_DIR/../../../references/style-bibles/realism-cinematic.md
    add(os.path.join(MODULE_DIR, os.pardir, os.pardir, os.pardir,
                     "references", "style-bibles", "realism-cinematic.md"))
    env = os.environ.get(RECIPE_ENV_VAR)
    if env:
        add(env)
    if lane_dir:
        lane = os.path.abspath(lane_dir)
        add(os.path.join(lane, RECIPE_RELATIVE))
        add(os.path.join(lane, "references", "style-bibles",
                         "realism-cinematic.md"))
    # Walk up from this module: <look>/ -> style_bibles/ -> core/ -> scripts/
    # -> skill root (the shipped references/ copy) and any further ancestors.
    p = MODULE_DIR
    for _ in range(6):
        p = os.path.dirname(p)
        add(os.path.join(p, "references", "style-bibles",
                         "realism-cinematic.md"))
    return out


def find_recipe(explicit=None, lane_dir=None):
    """First existing realism-cinematic.md, else None. Existence only."""
    for path in recipe_candidate_paths(explicit, lane_dir):
        if os.path.isfile(path):
            return path
    return None


def extract_recipe(text):
    """The [STYLE]...[/STYLE] block of the recipe, verbatim (no trimming)."""
    m = _STYLE_BLOCK_RE.search(text) if isinstance(text, str) else None
    if m is None:
        return None
    block = m.group(0)
    low = block.lower()
    for phrase in RECIPE_REQUIRED_PHRASES:
        if phrase not in low:
            return None
    return block


def realism_available(explicit=None, lane_dir=None):
    """(path or None, searched paths). Never raises on absence."""
    searched = recipe_candidate_paths(explicit, lane_dir)
    return find_recipe(explicit, lane_dir), searched


def realism_block(explicit=None, lane_dir=None):
    """Exact [STYLE] block from style-bibles/realism-cinematic.md.

    Fail closed: missing file or a block without the D19 phrases raises
    HybridError and names every path searched (negative-result rule).
    """
    path = find_recipe(explicit, lane_dir)
    searched = recipe_candidate_paths(explicit, lane_dir)
    if path is None:
        raise HybridError("REALISM_RECIPE_MISSING",
                          "style-bibles/realism-cinematic.md not found; "
                          "searched: %s" % "; ".join(searched))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as e:
        raise HybridError("REALISM_RECIPE_UNREADABLE", "%s: %s" % (path, e))
    block = extract_recipe(text)
    if block is None:
        raise HybridError("REALISM_RECIPE_INVALID",
                          "%s has no [STYLE][/STYLE] block carrying the D19 "
                          "phrases" % path)
    return block


def realism_sha256(block):
    return hashlib.sha256(block.encode("utf-8")).hexdigest()


# ------------------------------------------------------------- planning ----

def beat_mode(beat):
    """Storyboard beat -> hybrid mode (plan 6.11)."""
    b = str(beat).strip().lower()
    if b in GOLDEN_BEATS:
        return MODE_GOLDEN
    if b in REALISM_BEATS:
        return MODE_REALISM
    if b in SKETCH_BEATS:
        return MODE_SKETCH
    raise HybridError("BEAT_UNKNOWN",
                      "beat %r is not one of: %s"
                      % (beat, ", ".join(sorted(
                          SKETCH_BEATS | REALISM_BEATS | GOLDEN_BEATS))))


def _validate_shots(shots):
    if not isinstance(shots, list) or not shots:
        raise HybridError("SHOTS_INVALID", "shots must be a non-empty list")
    for s in shots:
        if not isinstance(s, dict) or not s.get("shot_id"):
            raise HybridError("SHOT_INVALID", "shot record with shot_id required")
        try:
            secs = float(s.get("seconds"))
        except (TypeError, ValueError):
            raise HybridError("SHOT_INVALID",
                              "shot %s needs numeric seconds" % s.get("shot_id"))
        if secs <= 0:
            raise HybridError("SHOT_INVALID",
                              "shot %s seconds must be > 0" % s.get("shot_id"))


def _merge(modes, seconds):
    """Absorb any non-final run shorter than HOLD_MIN into its neighbor."""
    out = list(modes)
    changed = True
    while changed:
        changed = False
        runs = []
        i = 0
        while i < len(out):
            j = i
            while j + 1 < len(out) and out[j + 1] == out[i]:
                j += 1
            runs.append((out[i], list(range(i, j + 1))))
            i = j + 1
        for r_idx, (mode, idxs) in enumerate(runs):
            if r_idx == len(runs) - 1:
                continue
            total = sum(seconds[k] for k in idxs)
            if total >= HOLD_MIN_SECONDS:
                continue
            target = runs[r_idx - 1][0] if r_idx > 0 else runs[r_idx + 1][0]
            for k in idxs:
                out[k] = target
            changed = True
            break
    return out


def _dissolve_for(shot, nxt):
    """0.3-0.4 s dissolve; matched framing or pose takes the short end."""
    d = DISSOLVE_SECONDS[1]
    if isinstance(shot.get("framing"), str) and \
            shot.get("framing") == (nxt or {}).get("framing"):
        d = DISSOLVE_SECONDS[0]
    elif isinstance(shot.get("pose"), str) and \
            shot.get("pose") == (nxt or {}).get("pose"):
        d = 0.35
    return round(d, 2)


def _lipsync(mode, shot):
    """Plan 6.11: lip-sync only on short, front-facing realism close-ups."""
    if mode != MODE_REALISM:
        return False
    if not shot.get("front_facing"):
        return False
    if str(shot.get("kind", "")).lower() not in ("close-up", "closeup"):
        return False
    return float(shot["seconds"]) <= 5.0


def plan_hybrid(shots):
    """Per-shot hybrid plan from the storyboard (plan 6.11 rules).

    Raises HybridError with a code for every refused storyboard:
    FINALE_BEAT_INVALID (last beat is not transformation/payoff),
    GOLDEN_NOT_FINALE (golden realism outside the finale),
    FINALE_HOLD (finale shorter than the 3 s hold).
    Plans only ever carry sketch / realism / golden-realism; 3D never appears.
    """
    _validate_shots(shots)
    seconds = [float(s["seconds"]) for s in shots]
    beats = [str(s.get("beat", "")).strip().lower() for s in shots]
    if beats[-1] not in GOLDEN_BEATS:
        raise HybridError(
            "FINALE_BEAT_INVALID",
            "storyboard ends on beat %r; the warm golden realism finale "
            "requires the last beat to be transformation or payoff"
            % (beats[-1],))
    modes = [beat_mode(b) for b in beats]
    # Golden realism owns the whole trailing run (transformation AND payoff),
    # which is exactly what the FINALE_HOLD walk below measures. Only a golden
    # beat that stops before the end of the storyboard is outside the finale.
    tail = len(modes) - 1
    while tail >= 0 and modes[tail] == MODE_GOLDEN:
        tail -= 1
    if any(m == MODE_GOLDEN for m in modes[:tail + 1]):
        raise HybridError("GOLDEN_NOT_FINALE",
                          "golden realism only plays as the finale")
    final_run = seconds[-1]
    k = len(modes) - 2
    while k >= 0 and modes[k] == MODE_GOLDEN:
        final_run += seconds[k]
        k -= 1
    if final_run < HOLD_MIN_SECONDS:
        raise HybridError("FINALE_HOLD",
                          "finale is %.2fs; golden realism must hold at least "
                          "%.1fs" % (final_run, HOLD_MIN_SECONDS))
    modes = _merge(modes, seconds)
    plan = []
    for i, shot in enumerate(shots):
        mode = modes[i]
        nxt = shots[i + 1] if i + 1 < len(shots) else None
        entry = {
            "shot_id": shot["shot_id"],
            "beat": beats[i],
            "mode": mode,
            "seconds": seconds[i],
            "lip_sync": _lipsync(mode, shot),
        }
        if nxt is not None and modes[i + 1] != mode:
            entry["transition_out"] = {
                "kind": "dissolve",
                "dissolve_seconds": _dissolve_for(shot, nxt),
                "note": "switch on matching poses or framings",
            }
        else:
            entry["transition_out"] = {"kind": "cut" if nxt is None else "hold"}
        plan.append(entry)
    return plan


def validate_plan(plan):
    """Error list (empty = plan obeys every switching rule)."""
    errs = []
    if not isinstance(plan, list) or not plan:
        return ["PLAN_EMPTY"]
    for i, e in enumerate(plan):
        mode = e.get("mode")
        if mode not in MODES:
            errs.append("MODE_INVALID:%s" % (mode,))
        tr = e.get("transition_out") or {}
        if tr.get("kind") == "dissolve":
            d = tr.get("dissolve_seconds")
            if not isinstance(d, (int, float)) or \
                    not (DISSOLVE_SECONDS[0] <= float(d) <= DISSOLVE_SECONDS[1]):
                errs.append("DISSOLVE_OUT_OF_RANGE:%s:%s"
                            % (e.get("shot_id"), d))
        if mode == MODE_SKETCH and e.get("lip_sync"):
            errs.append("SKETCH_LIPSYNC:%s" % e.get("shot_id"))
    if plan[-1].get("mode") != MODE_GOLDEN:
        errs.append("FINALE_NOT_GOLDEN:%s" % plan[-1].get("shot_id"))
    # The trailing golden run is the finale (transformation + payoff); only a
    # golden entry that stops before the end of the plan is outside it.
    tail = len(plan) - 1
    while tail >= 0 and plan[tail].get("mode") == MODE_GOLDEN:
        tail -= 1
    for e in plan[:tail + 1]:
        if e.get("mode") == MODE_GOLDEN:
            errs.append("GOLDEN_NOT_FINALE:%s" % e.get("shot_id"))
    run_mode, run_secs = None, 0.0
    for i, e in enumerate(plan):
        if e.get("mode") != run_mode:
            if run_mode is not None and run_secs < HOLD_MIN_SECONDS:
                errs.append("HOLD_TOO_SHORT:%s" % run_mode)
            run_mode, run_secs = e.get("mode"), 0.0
        run_secs += float(e.get("seconds") or 0)
    if run_mode is not None and run_secs < HOLD_MIN_SECONDS:
        errs.append("HOLD_TOO_SHORT:%s" % run_mode)
    return errs


def enforce_finale(plan):
    """Raise unless the plan ends in the warm golden realism finale."""
    errs = [e for e in validate_plan(plan) if "FINALE" in e or "GOLDEN" in e]
    if errs:
        raise HybridError("FINALE_RULE_BROKEN", "; ".join(errs))
    return plan


# -------------------------------------------------------------- compile ----

FINALE_BLOCK = ("[FINALE] warm golden realism finale: golden-hour key light, "
                "warm amber highlights on skin, soft golden rim, hopeful "
                "closure; the transformation and payoff play here, and the "
                "ad ends on this warmth. [/FINALE]")


def compile_prompt(shot, mode, aspect_ratio="9:16",
                   realism_block_path=None, lane_dir=None):
    """Deterministic prompt compile for one hybrid shot. Mockable, no spend.

    mode "sketch"  -> sketch [STYLE] block only; no lip-sync.
    mode "realism" -> the realism recipe block, verbatim, nothing else.
    mode "golden-realism" -> the recipe block verbatim followed by the
        separate [FINALE] block; the recipe itself is never edited.

    Returns {"prompt", "mode", "style_block", "recipe_sha256", "lip_sync"}.
    Raises HybridError when the recipe is missing (fail closed, paths named).
    """
    if mode not in MODES:
        raise HybridError("MODE_INVALID",
                          "mode %r: expected one of %s" % (mode, ", ".join(MODES)))
    if not isinstance(shot, dict) or not shot.get("shot_id") or \
            not str(shot.get("base_prompt", "")).strip():
        raise HybridError("SHOT_INVALID",
                          "shot dict with shot_id and base_prompt required")
    header = "[compiled:hybrid-style=%s mode=%s aspect=%s]"
    if mode == MODE_SKETCH:
        style_id = SKETCH_STYLE_ID
        rec = sketch_style(aspect_ratio)
        block = "[STYLE]\n" + "\n".join(
            "%s: %s" % (k, rec[k]) for k in (
                "aesthetic", "rendering_style", "camera_language",
                "lens_tendencies", "lighting_doctrine", "contrast_architecture",
                "environment_texture", "grain_sharpness")) + \
            "\ncolor_palette: %s" % " | ".join(rec["color_palette"]) + \
            "\nvisual_continuity_constraints: %s" % " | ".join(
                rec["visual_continuity_constraints"]) + \
            "\nbanned_visual_cliches: %s" % " | ".join(
                rec["banned_visual_cliches"]) + "\n[/STYLE]"
        parts = [header % (style_id, mode, aspect_ratio), block]
    else:
        block = realism_block(realism_block_path, lane_dir)   # raises if absent
        style_id = REALISM_STYLE_ID
        parts = [header % (style_id, mode, aspect_ratio), block]
        if mode == MODE_GOLDEN:
            parts.append(FINALE_BLOCK)
    parts.append("[SHOT:%s] %s [/SHOT]"
                 % (shot["shot_id"], str(shot["base_prompt"]).strip()))
    # Part F F12: the clip prompt asks for motion (clips must move).
    parts.append("[MOTION] The subject moves naturally through the frame "
                 "[/MOTION]")
    prompt = "\n".join(parts)
    return {
        "prompt": prompt,
        "mode": mode,
        "style_block": block,
        "recipe_sha256": realism_sha256(block) if mode != MODE_SKETCH else None,
        "lip_sync": mode == MODE_REALISM and _lipsync(mode, shot),
    }
