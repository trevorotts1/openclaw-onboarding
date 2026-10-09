#!/usr/bin/env python3
"""Canvas to Life style bible (owner decisions D21/D29, plan 6.11). Stdlib only.

The Canvas to Life look is a 2D HAND-PAINTED cartoon that SWITCHES to real
footage and back. "Real footage" means the real-looking live-action shots
whose exact recipe lives in `style-bibles/realism-cinematic.md` (decision
D19). Realism is NOT 3D animation.

This module never takes the 2D-to-3D path. That path is a separate look with
a separate bible, and every entry point here refuses a 3-D target by name
(`2D_TO_3D_NOT_USED`), so nothing in this file can render, plan or compile one.

What this module does:

1. `looks()` / `assert_look()` -- the one look this bible serves, plus the
   3-D refusal that fails closed on any 3-D target name.
2. `identity_lock(...)` / `assert_identity_lock(...)` -- the character is the
   same person on both sides of every switch: same face, hair, glasses and
   accessories, governed by reference-image keyframes and the lock id, which
   is stamped on every plan entry and every compiled prompt.
3. `plan_hybrid(shots, lock)` -- per-shot painted / realism / golden-realism
   plan from the storyboard beats, honoring the 6.11 switching rules: hold
   each style at least 3 seconds (no flicker), switch on a 0.3-0.4 s dissolve,
   no lip-sync on painted shots. A GOLDEN FINALE IS NOT REQUIRED: golden
   realism plays when the storyboard's beats call for it and is never demanded
   (it is only ever refused when it appears somewhere other than the end).
4. `realism_block()` -- the exact `[STYLE]...[/STYLE]` recipe text read from
   `style-bibles/realism-cinematic.md`, byte-for-byte. Missing or malformed
   recipe -> refuse (fail closed), naming every path searched.
5. `compile_prompt(shot, mode, lock, ...)` -- deterministic prompt compile. The
   realism segment of a realism or golden prompt IS the recipe block, the
   identity-lock block rides on every prompt, and no prompt ever carries a
   3-D style.

Flare rule and prompt caps belong to core/product_style_bible/bible.py; this
module composes blocks only, it never renders, calls a provider or spends.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

try:
    from product_style_bible import bible as _bible
except ImportError as _e:  # imported as core.style_bibles.canvas_to_life
    if "product_style_bible" not in str(_e):
        raise
    _bible = None

TOOL_NAME = "canvas_to_life_bible"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.style-bibles.canvas_to_life/v1"

#: Plan 6.11 switching constants.
HOLD_MIN_SECONDS = 3.0              # hold each style at least 3 s (no flicker)
DISSOLVE_SECONDS = (0.3, 0.4)       # short dissolve on matching poses/framings

#: Plan 6.11: which beats take which style (the painted half of the hybrid).
PAINTED_BEATS = frozenset(("comedy", "setup", "everyday", "doubt", "transition"))
REALISM_BEATS = frozenset(("pain", "shock", "humiliation", "numbness", "anger",
                           "exhaustion", "fear", "turn", "revelation"))
#: Optional: golden realism only ever plays here, never demanded.
GOLDEN_BEATS = frozenset(("transformation", "payoff"))

MODE_PAINTED = "painted"
MODE_REALISM = "realism"
MODE_GOLDEN = "golden-realism"
MODES = (MODE_PAINTED, MODE_REALISM, MODE_GOLDEN)

PAINTED_STYLE_ID = "canvas-painted-01"
REALISM_STYLE_ID = "realism-cinematic-01"   # recipe style_id, from the D19 look
LOOK_ID = "canvas-to-life"

#: The one look this bible serves. Nothing else is offered from here.
LOOKS = {
    "canvas-to-life": {
        "label": "Canvas to Life",
        "description": ("2D hand-painted cartoon switching to real footage and "
                        "back; golden realism finale when the story earns it"),
        "target": "realism",
    },
}

#: Refused by name, case/separator-insensitive normal form. Any target whose
#: normalised name carries "3d" is refused by assert_look, whatever it is.
BANNED_3D_ALIASES = frozenset((
    "versione", "canvas3d", "hybrid3d", "hybrid3danimation",
    "2dto3d", "2dcartoon3d", "cartoon3d", "painted3d", "sketch3d",
))

RECIPE_ENV_VAR = "CANVAS_TO_LIFE_REALISM_RECIPE"
RECIPE_RELATIVE = os.path.join("style-bibles", "realism-cinematic.md")

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))     # .../canvas_to_life
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


class CanvasToLifeError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


# -------------------------------------------------------- painted half ----

#: Full Style Bible record for the painted half. Valid against
#: product_style_bible.bible.validate_style when that module is importable.
PAINTED_STYLE = {
    "schema_version": "1.0.0",
    "style_id": PAINTED_STYLE_ID,
    "aspect_ratio": "9:16",
    "aesthetic": ("2D hand-painted cartoon: expressive stylised characters on "
                  "painterly backgrounds staged like live-action drama; "
                  "clearly a painting, never photoreal, never a 3-D render"),
    "rendering_style": ("hand-painted 2D animation with confident line art, "
                        "visible brush texture and soft cel shading on "
                        "characters; no photoreal skin texture and no 3-D "
                        "render shading"),
    "camera_language": ("eye-level medium shots and slow deliberate moves, "
                        "staging readable at phone width; framing matches the "
                        "realism shot the dissolve lands on"),
    "lens_tendencies": ("flat animated depth with gentle layering; no lens "
                        "distortion and no photographic depth of field"),
    "lighting_doctrine": ("painted key and fill with readable shadow shapes; "
                          "light is painted, never rendered"),
    "contrast_architecture": ("stable painted midtones with warm rolled "
                              "highlights; no photographic tone curve"),
    "environment_texture": ("lived-in painterly sets in the same brush family "
                            "as the character layer"),
    "grain_sharpness": ("fine animation grain and crisp line edges; no "
                        "photographic grain and no sharpening halo"),
    "color_palette": ["warm amber", "deep teal", "soft cream", "coral accent"],
    "visual_continuity_constraints": [
        "the character is identical across painted and realism: same face, "
        "hair, glasses and accessories (reference-image keyframes and the "
        "identity lock govern both halves)",
        "same palette, brush family and line weight across every painted shot",
        "no photoreal texture and no 3-D render anywhere in painted mode",
    ],
    "banned_visual_cliches": [
        "photoreal skin in painted mode",
        "3-D render in painted mode",
        "2D-to-3D style switching",
        "lens dust overlays",
        "stock cinematic b-roll",
    ],
}


def validate_painted():
    """Error list (empty = the painted record is a valid Style Bible)."""
    if _bible is None:
        raise CanvasToLifeError(
            "STYLE_BIBLE_UNAVAILABLE",
            "product_style_bible not importable; run from core/")
    return _bible.validate_style(PAINTED_STYLE)


def painted_style(aspect_ratio=None):
    """Copy of the painted record; optional aspect override (validated later)."""
    rec = dict(PAINTED_STYLE)
    rec["color_palette"] = list(PAINTED_STYLE["color_palette"])
    rec["visual_continuity_constraints"] = \
        list(PAINTED_STYLE["visual_continuity_constraints"])
    rec["banned_visual_cliches"] = list(PAINTED_STYLE["banned_visual_cliches"])
    if aspect_ratio is not None:
        rec["aspect_ratio"] = aspect_ratio
    return rec


# ------------------------------------------------------------ offering ----

def _norm(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def looks():
    """The look menu of this bible (decision D29). Exactly one entry."""
    return {lid: dict(rec) for lid, rec in LOOKS.items()}


def assert_look(look_id):
    """Refuse every look this bible does not serve, 3-D first and by name.

    The 2D-to-3D path is never used here: any target whose name normalises to
    something carrying "3d" is refused with `2D_TO_3D_NOT_USED` before any
    other check, so a 3-D request can never fall through to this bible.
    """
    norm = _norm(look_id)
    if norm in BANNED_3D_ALIASES or "3d" in norm:
        raise CanvasToLifeError(
            "2D_TO_3D_NOT_USED",
            "%r: the 2D-to-3D path is never used by this bible; Canvas to "
            "Life switches to REAL FOOTAGE only (its 3-D sibling is a "
            "separate look with its own bible)"
            % (look_id,))
    if norm not in {_norm(k) for k in LOOKS}:
        raise CanvasToLifeError("STYLE_NOT_OFFERED",
                                "%r is not offered by this bible: %s"
                                % (look_id, ", ".join(sorted(LOOKS))))
    return LOOK_ID


# --------------------------------------------------------- identity lock --

LOCK_RULE = ("the character is identical across painted and realism: same "
             "face, hair, glasses and accessories; reference-image keyframes "
             "and the identity lock govern both halves of every switch")


def identity_lock(character_id, reference_image_ids, traits):
    """Build the identity lock that must cover both sides of every switch.

    Fail closed on an empty character, an empty reference set or empty traits:
    a lock with nothing pinned cannot prove the person did not change.
    """
    def _strs(v, what):
        if not isinstance(v, (list, tuple)) or not v or \
                any(not isinstance(i, str) or not i.strip() for i in v):
            raise CanvasToLifeError(
                "IDENTITY_LOCK_INVALID",
                "%s must be a non-empty list of non-empty strings" % what)
        return [i.strip() for i in v]

    if not isinstance(character_id, str) or not character_id.strip():
        raise CanvasToLifeError("IDENTITY_LOCK_INVALID",
                                "character_id must be a non-empty string")
    refs = _strs(reference_image_ids, "reference_image_ids")
    owns = _strs(traits, "traits")
    canon = json.dumps({
        "character_id": character_id.strip(),
        "reference_image_ids": sorted(refs),
        "traits": owns,
        "rule": LOCK_RULE,
    }, sort_keys=True, separators=(",", ":"))
    return {
        "lock_id": hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16],
        "character_id": character_id.strip(),
        "reference_image_ids": refs,
        "traits": owns,
        "rule": LOCK_RULE,
    }


def lock_valid(lock):
    """True when lock has a lock_id and pinned content (structure only)."""
    if not isinstance(lock, dict):
        return False
    if not isinstance(lock.get("lock_id"), str) or not lock.get("lock_id"):
        return False
    if not isinstance(lock.get("character_id"), str) or \
            not lock.get("character_id").strip():
        return False
    for key in ("reference_image_ids", "traits"):
        v = lock.get(key)
        if not isinstance(v, (list, tuple)) or not v:
            return False
        if any(not isinstance(i, str) or not i.strip() for i in v):
            return False
    return True


def _require_lock(lock):
    if not lock_valid(lock):
        raise CanvasToLifeError("IDENTITY_LOCK_INVALID",
                                "a populated identity lock is required on "
                                "every plan and every prompt")
    return lock


def identity_lock_block(lock):
    """The `[IDENTITY_LOCK]...[/IDENTITY_LOCK]` block for a prompt."""
    _require_lock(lock)
    return ("[IDENTITY_LOCK] character_id: %s | lock_id: %s | pinned traits: "
            "%s | references: %s | rule: %s [/IDENTITY_LOCK]"
            % (lock["character_id"], lock["lock_id"],
               ", ".join(lock["traits"]),
               ", ".join(lock["reference_image_ids"]),
               lock["rule"]))


def assert_identity_lock(plan, lock):
    """Raise unless every plan entry carries this lock on both style sides.

    Codes: IDENTITY_LOCK_INVALID (lock unusable), IDENTITY_LOCK_MISSING
    (entry never stamped), IDENTITY_LOCK_MISMATCH (stamped with another lock),
    IDENTITY_LOCK_MIXED (entries disagree with each other),
    IDENTITY_LOCK_ONE_SIDED (the lock does not span the switch, so the
    painted->real hand-over is unguarded).
    """
    _require_lock(lock)
    if not isinstance(plan, list) or not plan:
        raise CanvasToLifeError("IDENTITY_LOCK_MISSING",
                                "plan is empty; nothing to lock")
    seen, modes = [], set()
    for e in plan:
        got = e.get("identity_lock_id") if isinstance(e, dict) else None
        if not got:
            raise CanvasToLifeError(
                "IDENTITY_LOCK_MISSING",
                "shot %s carries no identity_lock_id"
                % (e.get("shot_id") if isinstance(e, dict) else "?"))
        if got != lock["lock_id"]:
            raise CanvasToLifeError(
                "IDENTITY_LOCK_MISMATCH",
                "shot %s is locked to %s, expected %s"
                % (e.get("shot_id"), got, lock["lock_id"]))
        if seen and got != seen[0]:
            raise CanvasToLifeError(
                "IDENTITY_LOCK_MIXED",
                "shot %s carries lock %s while earlier entries carry %s"
                % (e.get("shot_id"), got, seen[0]))
        seen.append(got)
        modes.add(e.get("mode"))
    if not (modes & {MODE_PAINTED, MODE_REALISM}) or \
            not (MODE_PAINTED in modes and MODE_REALISM in modes):
        raise CanvasToLifeError(
            "IDENTITY_LOCK_ONE_SIDED",
            "the lock must span the switch: plan covers %s, needs both %s "
            "and %s" % (", ".join(sorted(m for m in modes if m)),
                        MODE_PAINTED, MODE_REALISM))
    return True


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
    CanvasToLifeError and names every path searched (negative-result rule).
    """
    path = find_recipe(explicit, lane_dir)
    searched = recipe_candidate_paths(explicit, lane_dir)
    if path is None:
        raise CanvasToLifeError(
            "REALISM_RECIPE_MISSING",
            "style-bibles/realism-cinematic.md not found; searched: %s"
            % "; ".join(searched))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as e:
        raise CanvasToLifeError("REALISM_RECIPE_UNREADABLE",
                                "%s: %s" % (path, e))
    block = extract_recipe(text)
    if block is None:
        raise CanvasToLifeError(
            "REALISM_RECIPE_INVALID",
            "%s has no [STYLE][/STYLE] block carrying the D19 phrases" % path)
    return block


def realism_sha256(block):
    return hashlib.sha256(block.encode("utf-8")).hexdigest()


# ------------------------------------------------------------- planning ----

def beat_mode(beat):
    """Storyboard beat -> Canvas to Life mode (plan 6.11)."""
    b = str(beat).strip().lower()
    if b in GOLDEN_BEATS:
        return MODE_GOLDEN
    if b in REALISM_BEATS:
        return MODE_REALISM
    if b in PAINTED_BEATS:
        return MODE_PAINTED
    raise CanvasToLifeError(
        "BEAT_UNKNOWN",
        "beat %r is not one of: %s"
        % (beat, ", ".join(sorted(
            PAINTED_BEATS | REALISM_BEATS | GOLDEN_BEATS))))


def _validate_shots(shots):
    if not isinstance(shots, list) or not shots:
        raise CanvasToLifeError("SHOTS_INVALID", "shots must be a non-empty list")
    for s in shots:
        if not isinstance(s, dict) or not s.get("shot_id"):
            raise CanvasToLifeError("SHOT_INVALID",
                                    "shot record with shot_id required")
        try:
            secs = float(s.get("seconds"))
        except (TypeError, ValueError):
            raise CanvasToLifeError(
                "SHOT_INVALID", "shot %s needs numeric seconds" % s.get("shot_id"))
        if secs <= 0:
            raise CanvasToLifeError("SHOT_INVALID",
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


def _golden_before_end(modes):
    """True when golden realism appears anywhere before the trailing run.

    The finale may span several shots (transformation + payoff); only golden
    that is interrupted by another style is a rule break.
    """
    k = len(modes) - 1
    while k >= 0 and modes[k] == MODE_GOLDEN:
        k -= 1
    return any(m == MODE_GOLDEN for m in modes[:k + 1])


def _lipsync(mode, shot):
    """Plan 6.11: lip-sync only on short, front-facing realism close-ups."""
    if mode != MODE_REALISM:
        return False
    if not shot.get("front_facing"):
        return False
    if str(shot.get("kind", "")).lower() not in ("close-up", "closeup"):
        return False
    return float(shot["seconds"]) <= 5.0


def plan_hybrid(shots, lock):
    """Per-shot Canvas to Life plan from the storyboard (plan 6.11 rules).

    Every entry is stamped with the identity lock, so the same person is
    pinned across the painted and the real half.

    A golden realism finale IS NOT REQUIRED: it is produced when the beats
    call for it and never demanded. Golden realism outside the end of the ad
    is still refused (GOLDEN_NOT_FINALE).

    Plans only ever carry painted / realism / golden-realism; a 3-D mode
    never exists here.
    """
    _require_lock(lock)
    _validate_shots(shots)
    seconds = [float(s["seconds"]) for s in shots]
    beats = [str(s.get("beat", "")).strip().lower() for s in shots]
    modes = [beat_mode(b) for b in beats]
    if _golden_before_end(modes):
        raise CanvasToLifeError("GOLDEN_NOT_FINALE",
                                "golden realism only plays at the end")
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
            "identity_lock_id": lock["lock_id"],
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
    """Error list (empty = plan obeys every switching rule).

    Deliberately does NOT require a golden finale (unit rule: golden finale
    not required). It does require the plan to actually switch, because this
    look is a hybrid and a single-style plan is the wrong bible.
    """
    errs = []
    if not isinstance(plan, list) or not plan:
        return ["PLAN_EMPTY"]
    for i, e in enumerate(plan):
        mode = e.get("mode")
        if isinstance(mode, str) and "3d" in _norm(mode):
            errs.append("2D_TO_3D_NOT_USED:%s" % mode)
        elif mode not in MODES:
            errs.append("MODE_INVALID:%s" % (mode,))
        if not e.get("identity_lock_id"):
            errs.append("IDENTITY_LOCK_MISSING:%s" % e.get("shot_id"))
        tr = e.get("transition_out") or {}
        if tr.get("kind") == "dissolve":
            d = tr.get("dissolve_seconds")
            if not isinstance(d, (int, float)) or \
                    not (DISSOLVE_SECONDS[0] <= float(d) <= DISSOLVE_SECONDS[1]):
                errs.append("DISSOLVE_OUT_OF_RANGE:%s:%s"
                            % (e.get("shot_id"), d))
        if mode == MODE_PAINTED and e.get("lip_sync"):
            errs.append("PAINTED_LIPSYNC:%s" % e.get("shot_id"))
    lock_ids = {e.get("identity_lock_id") for e in plan}
    if len(lock_ids) > 1:
        errs.append("IDENTITY_LOCK_MIXED")
    k = len(plan) - 1
    while k >= 0 and plan[k].get("mode") == MODE_GOLDEN:
        k -= 1
    for e in plan[:k + 1]:
        if e.get("mode") == MODE_GOLDEN:
            errs.append("GOLDEN_NOT_FINALE:%s" % e.get("shot_id"))
    run_mode, run_secs = None, 0.0
    for e in plan:
        if e.get("mode") != run_mode:
            if run_mode is not None and run_secs < HOLD_MIN_SECONDS:
                errs.append("HOLD_TOO_SHORT:%s" % run_mode)
            run_mode, run_secs = e.get("mode"), 0.0
        run_secs += float(e.get("seconds") or 0)
    if run_mode is not None and run_secs < HOLD_MIN_SECONDS:
        errs.append("HOLD_TOO_SHORT:%s" % run_mode)
    if len({e.get("mode") for e in plan}) < 2:
        errs.append("SWITCH_MISSING")
    return errs


def enforce_switch(plan):
    """Raise unless the plan really switches painted <-> realism."""
    errs = [e for e in validate_plan(plan)
            if e.startswith(("SWITCH", "HOLD_TOO_SHORT", "2D_TO_3D",
                             "IDENTITY_LOCK", "PAINTED_LIPSYNC",
                             "DISSOLVE", "MODE_INVALID"))]
    if errs:
        raise CanvasToLifeError("SWITCH_RULE_BROKEN", "; ".join(errs))
    return plan


# -------------------------------------------------------------- compile ----

FINALE_BLOCK = ("[FINALE] warm golden realism finale: golden-hour key light, "
                "warm amber highlights on skin, soft golden rim, hopeful "
                "closure; the transformation and payoff play here, and the "
                "ad ends on this warmth. [/FINALE]")

_PAINTED_KEYS = ("aesthetic", "rendering_style", "camera_language",
                 "lens_tendencies", "lighting_doctrine", "contrast_architecture",
                 "environment_texture", "grain_sharpness")


def painted_block(aspect_ratio="9:16"):
    """The painted half's `[STYLE]` block, rendered from PAINTED_STYLE."""
    rec = painted_style(aspect_ratio)
    return "[STYLE]\n" + "\n".join(
        "%s: %s" % (k, rec[k]) for k in _PAINTED_KEYS) + \
        "\ncolor_palette: %s" % " | ".join(rec["color_palette"]) + \
        "\nvisual_continuity_constraints: %s" % " | ".join(
            rec["visual_continuity_constraints"]) + \
        "\nbanned_visual_cliches: %s" % " | ".join(
            rec["banned_visual_cliches"]) + "\n[/STYLE]"


def compile_prompt(shot, mode, lock, aspect_ratio="9:16",
                   realism_block_path=None, lane_dir=None, video=False):
    """Deterministic prompt compile for one Canvas to Life shot. No spend.

    mode "painted"       -> the painted [STYLE] block, identity lock, shot.
    mode "realism"       -> the realism recipe block verbatim, identity lock,
                            shot (real footage: this is the switch target).
    mode "golden-realism"-> the recipe block verbatim, then the separate
                            [FINALE] block, then identity lock and shot; the
                            recipe itself is never edited.

    Every prompt carries the identity lock, so the character is the same
    person on both sides of the switch. A 3-D mode is refused by name before
    anything else (`2D_TO_3D_NOT_USED`).

    U15b: ``video=True`` is the VIDEO path: no square-bracket markers, no
    generic [MOTION] line (H3 reads brackets as camera commands; per-shot
    motion comes from the shot spec). The keyframe path is unchanged.

    Returns {"prompt", "mode", "style_block", "recipe_sha256", "lip_sync",
             "identity_lock_id"}.
    Raises CanvasToLifeError when the recipe is missing (fail closed, paths
    named).
    """
    if isinstance(mode, str) and ("3d" in _norm(mode) or
                                  _norm(mode) in BANNED_3D_ALIASES):
        raise CanvasToLifeError(
            "2D_TO_3D_NOT_USED",
            "mode %r: this bible never compiles a 3-D prompt; Canvas to Life "
            "switches to real footage only" % (mode,))
    if mode not in MODES:
        raise CanvasToLifeError("MODE_INVALID",
                                "mode %r: expected one of %s"
                                % (mode, ", ".join(MODES)))
    if not isinstance(shot, dict) or not shot.get("shot_id") or \
            not str(shot.get("base_prompt", "")).strip():
        raise CanvasToLifeError("SHOT_INVALID",
                                "shot dict with shot_id and base_prompt required")
    _require_lock(lock)
    lock_block = identity_lock_block(lock)
    header = "[compiled:canvas-to-life=%s mode=%s aspect=%s]"
    if mode == MODE_PAINTED:
        style_id = PAINTED_STYLE_ID
        block = painted_block(aspect_ratio)
    else:
        block = realism_block(realism_block_path, lane_dir)   # raises if absent
        style_id = REALISM_STYLE_ID
    if video:
        # U15b video path: no square-bracket markers anywhere; the block text
        # between [STYLE] and [/STYLE] is unchanged and the identity lock
        # rides as plain words.
        body = block
        if body.startswith("[STYLE]"):
            body = body[len("[STYLE]"):]
        if body.rstrip().endswith("[/STYLE]"):
            body = body.rstrip()[:-len("[/STYLE]")]
        parts = ["%s, %s mode. %s" % (style_id, mode, body.strip())]
        if mode != MODE_PAINTED and mode == MODE_GOLDEN:
            parts.append(FINALE_BLOCK.replace("[FINALE]", "")
                         .replace("[/FINALE]", "").strip())
        parts.append(lock_block.replace("[IDENTITY_LOCK]", "Identity lock:")
                     .replace("[/IDENTITY_LOCK]", "").strip())
        parts.append(str(shot["base_prompt"]).strip())
        prompt = " ".join(parts)
        if "[" in prompt or "]" in prompt:
            raise CanvasToLifeError(
                "VIDEO_PROMPT_BRACKETS",
                "a video prompt may carry no square brackets")
    else:
        if mode == MODE_PAINTED:
            parts = [header % (style_id, mode, aspect_ratio), block, lock_block]
        else:
            parts = [header % (style_id, mode, aspect_ratio), block]
            if mode == MODE_GOLDEN:
                parts.append(FINALE_BLOCK)
            parts.append(lock_block)
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
        "recipe_sha256": realism_sha256(block) if mode != MODE_PAINTED else None,
        "lip_sync": mode == MODE_REALISM and _lipsync(mode, shot),
        "identity_lock_id": lock["lock_id"],
        "video": bool(video),
    }
