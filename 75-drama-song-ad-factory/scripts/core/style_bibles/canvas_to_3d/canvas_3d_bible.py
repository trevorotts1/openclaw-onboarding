#!/usr/bin/env python3
"""Canvas to 3D style bible (owner decisions D21/D29, plan section 6.11).

The Canvas to 3D look is a 2D hand-painted cartoon opening that SWITCHES to
lifelike 3D cinematic CGI and back. It is the Version E recipe
(`creative-fidelity-h3/final-9x16-h3-spoken-E-hybrid3d.mp4`), offered by the
owner on 2026-10-07 after he reversed his earlier "2D-to-3D is not hybrid"
ruling. This look never touches realism: the golden-realism finale rule
belongs to Sketch to Life and Canvas to Life, not here. Canvas to 3D ends on
lifelike 3D, exactly as Version E does.

What this module does:

1. `offered_look()` / `assert_offered()` -- one look, id ``canvas-to-3d``.
2. `identity_lock(character)` -- the identity lock: one fingerprint over face,
   hair, glasses, accessories and wardrobe that both halves must carry, so the
   character is the same person painted and rendered (plan 6.11).
3. `plan_switches(shots, identity, version_e=False)` -- per-shot
   painted-2d / lifelike-3d plan from the storyboard beats, honoring the
   switching rules: switch ON MATCHING POSES OR FRAMINGS (refused otherwise),
   0.3-0.4 s dissolve (0.4 s on every switch when ``version_e``), hold each
   style at least 3 s (7.2 s for Version E), no flicker, no lip-sync on
   painted shots, finale in lifelike 3D.
4. `validate_plan` / `assert_identity_lock` / `assert_version_e` -- the rules
   as checkable error lists.
5. `version_e_schedule()` -- reads the real Version E receipt and returns its
   segment list, switch times, crossfade and minimum hold. Fail closed: a
   missing receipt names every path searched.
6. `compile_prompt(shot, mode, identity, ...)` -- deterministic prompt
   compile. Each prompt carries the compiled mark the consumption gate
   requires, the right `[STYLE]` block and the identity lock.

Flare rule, prompt caps and the `[compiled:style=` gate belong to
core/product_style_bible/bible.py; this module composes blocks only -- it
never renders, calls a provider or spends. stdlib only, zero network.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

try:
    from product_style_bible import bible as _bible
except ImportError as _e:  # imported as core.style_bibles.canvas_to_3d
    if "product_style_bible" not in str(_e):
        raise
    _bible = None

TOOL_NAME = "canvas_3d_bible"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.style-bibles.canvas-to-3d/v1"

#: Plan 6.11 switching constants (all hybrid looks).
HOLD_MIN_SECONDS = 3.0              # hold each style at least 3 s (no flicker)
DISSOLVE_SECONDS = (0.3, 0.4)       # short dissolve on matching poses/framings

#: Version E constants, transcribed from the approved receipt
#: (final-9x16-h3-spoken-E-hybrid3d.mp4.receipt.json). version_e_schedule()
#: re-reads the receipt and the test suite asserts this parity.
VERSION_E_DISSOLVE_SECONDS = 0.4    # "0.4s alpha crossfade centered on switch"
VERSION_E_MIN_HOLD_SECONDS = 7.2    # receipt min_hold_s (declared floor)
VERSION_E_SWITCHES_S = (5.1, 15.3, 31.7, 45.5, 52.7)
VERSION_E_MODES = ("painted-2d", "lifelike-3d", "painted-2d", "lifelike-3d",
                   "painted-2d", "lifelike-3d")
# ponytail: the receipt declares min_hold_s 7.2 but its own first segment runs
# 5.1s; the DECLARED figure is the enforced floor (stricter = no flicker).
# version_e_schedule() also reports the measured floor as
# measured_min_hold_s. Upgrade path: owner ruling to enforce the measured
# floor instead.

#: Plan 6.11: which beats take which style.
PAINTED_BEATS = frozenset(("comedy", "setup", "everyday", "doubt", "transition"))
THREED_BEATS = frozenset(("pain", "shock", "humiliation", "numbness", "anger",
                          "exhaustion", "fear", "turn", "revelation",
                          "transformation", "payoff"))

MODE_PAINTED = "painted-2d"
MODE_3D = "lifelike-3d"
MODES = (MODE_PAINTED, MODE_3D)

PAINTED_STYLE_ID = "canvas-painted-2d-01"
THREED_STYLE_ID = "lifelike-3d-cinematic-01"

#: Decision D21/D29: the one look this module serves.
LOOK_ID = "canvas-to-3d"
OFFERED = {
    LOOK_ID: {
        "label": "Canvas to 3D",
        "description": ("2D hand-painted cartoon that switches to lifelike 3D "
                        "and back (Version E), offered from 2026-10-07"),
        "style_ids": {"painted": PAINTED_STYLE_ID, "3d": THREED_STYLE_ID},
        "reference": ("creative-fidelity-h3/"
                      "final-9x16-h3-spoken-E-hybrid3d.mp4"),
    },
}

#: Refused by name: this look is painted <-> lifelike 3D and never realism.
BANNED_STYLE_ALIASES = frozenset((
    "canvas2realism", "canvastolife", "sketchto3d", "sketch3d",
    "goldencanvas3d", "photoreal3d", "realism3d",
))

#: The look must not render as anything but painted 2D or lifelike 3D CGI;
#: photoreal film footage is a different look (Canvas to Life / Sketch to Life).
BANNED_PROMPT_PHRASES = (
    "photoreal cinematic live-action look",
    "golden realism finale",
)

RECEIPT_ENV_VAR = "CANVAS_3D_VERSION_E_RECEIPT"
RECEIPT_FILENAME = "final-9x16-h3-spoken-E-hybrid3d.mp4.receipt.json"

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))          # .../canvas_to_3d
# C3: operator-Mac home-folder defaults are gone from shipped code. This look
# never reads realism-cinematic.md (realism is banned here); its candidate
# search is for the Version E receipt only.

_STYLE_BLOCK_RE = re.compile(r"\[STYLE\][^\[]*?\[/STYLE\]", re.DOTALL)
_CROSSFADE_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*s\s+alpha\s+crossfade",
                           re.IGNORECASE)

#: Identity fields the lock covers (plan 6.11: same face, hair, glasses,
#: accessories across both halves).
IDENTITY_FIELDS = ("character", "face", "hair", "glasses", "accessories",
                   "wardrobe")


class Canvas3DError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


# --------------------------------------------------------------- styles ----

#: Full Style Bible record for the painted half (D13/D21 2D hand-painted).
#: Valid against product_style_bible.bible.validate_style.
PAINTED_STYLE = {
    "schema_version": "1.0.0",
    "style_id": PAINTED_STYLE_ID,
    "aspect_ratio": "9:16",
    "aesthetic": ("hand-painted 2D cartoon: confident brush strokes, "
                  "stylised characters with clear silhouettes, painterly "
                  "backgrounds staged like live-action drama"),
    "rendering_style": ("painted 2D animation, visible brush texture on "
                        "characters and sets, soft cel shading, clean "
                        "contour line; no photoreal skin, no 3D render"),
    "camera_language": ("eye-level medium shots and close-ups, slow "
                        "deliberate moves, frames readable at phone width"),
    "lens_tendencies": ("flat illustrated depth with layered painted "
                        "planes; focus is drawn, never a photographic lens"),
    "lighting_doctrine": ("warm painted key with soft cool fill, motivated "
                          "practicals, readable painted shadow shapes"),
    "contrast_architecture": ("lifted painted shadows, warm rolled "
                              "highlights, stable midtone contrast"),
    "environment_texture": ("lived-in painterly sets in the same brush "
                            "family as the characters"),
    "grain_sharpness": ("fine canvas grain, crisp brush edges, no "
                        "photographic grain and no sharpening halo"),
    "color_palette": ["warm amber", "deep teal", "soft cream", "coral accent"],
    "visual_continuity_constraints": [
        "the character is identical painted and rendered: same face, hair, "
        "glasses, accessories and wardrobe (reference-image keyframes and "
        "the identity lock govern both halves)",
        "same brush family, palette and line weight across every painted "
        "shot",
        "painted mode carries no photoreal texture and no 3D render",
        "no lip-sync on painted shots; reactions are acted out",
    ],
    "banned_visual_cliches": [
        "3D render in painted mode",
        "photoreal skin in painted mode",
        "style flicker: any style hold shorter than 3 seconds",
        "switching off a matching pose or framing",
    ],
}

#: Full Style Bible record for the lifelike 3D half (D13/D21 cinematic CGI).
LIFELIKE_3D_STYLE = {
    "schema_version": "1.0.0",
    "style_id": THREED_STYLE_ID,
    "aspect_ratio": "9:16",
    "aesthetic": ("lifelike 3D cinematic CGI animation: clearly animated, "
                  "expressive lifelike faces and hands, film-grade staging; "
                  "animation, never live-action footage"),
    "rendering_style": ("physically-based 3D render with subsurface skin "
                        "scattering, groomed hair, cloth simulation and "
                        "soft global illumination; clearly a render, never "
                        "a cartoon drawing and never a camera original"),
    "camera_language": ("cinematic eye-level coverage: medium shots, slow "
                        "pushes and close-ups framed for lip-sync"),
    "lens_tendencies": ("virtual cinema lens with shallow depth of field, "
                        "gentle bokeh, no lens distortion"),
    "lighting_doctrine": ("key/fill/rim three-point lighting with motivated "
                          "practicals, soft shadows, warm key over cool "
                          "ambient"),
    "contrast_architecture": ("filmic tone curve, controlled highlights, "
                              "open shadows, stable midtone contrast"),
    "environment_texture": ("detailed CG environments with material "
                            "variation and atmospheric depth"),
    "grain_sharpness": ("clean render with light film grain, crisp "
                        "silhouettes, no sharpening halo"),
    "color_palette": ["warm amber", "deep teal", "soft cream",
                      "coral accent"],
    "visual_continuity_constraints": [
        "the character is identical painted and rendered: same face, hair, "
        "glasses, accessories and wardrobe (reference-image keyframes and "
        "the identity lock govern both halves)",
        "same palette and material set across every 3D shot; the palette "
        "matches the painted half so the switch reads as one world",
        "3D mode carries no pencil or brush texture and no live-action "
        "photoreal footage",
        "lip-sync only on short, front-facing 3D close-ups",
    ],
    "banned_visual_cliches": [
        "pencil or brush texture in 3D mode",
        "flat cartoon shading in 3D mode",
        "live-action photoreal footage in 3D mode",
        "style flicker: any style hold shorter than 3 seconds",
    ],
}


def validate_painted():
    """Error list (empty = the painted record is a valid Style Bible)."""
    if _bible is None:
        raise Canvas3DError("STYLE_BIBLE_UNAVAILABLE",
                            "product_style_bible not importable; run from core/")
    return _bible.validate_style(PAINTED_STYLE)


def validate_3d():
    """Error list (empty = the lifelike 3D record is a valid Style Bible)."""
    if _bible is None:
        raise Canvas3DError("STYLE_BIBLE_UNAVAILABLE",
                            "product_style_bible not importable; run from core/")
    return _bible.validate_style(LIFELIKE_3D_STYLE)


def style_record(mode, aspect_ratio=None):
    """Style Bible record for a mode; optional aspect override."""
    if mode not in MODES:
        raise Canvas3DError("MODE_INVALID",
                            "mode %r: expected one of %s"
                            % (mode, ", ".join(MODES)))
    rec = dict(PAINTED_STYLE if mode == MODE_PAINTED else LIFELIKE_3D_STYLE)
    for key in ("color_palette", "visual_continuity_constraints",
                "banned_visual_cliches"):
        rec[key] = list(rec[key])
    if aspect_ratio is not None:
        rec["aspect_ratio"] = aspect_ratio
    return rec


def style_block(mode, aspect_ratio=None):
    """The `[STYLE]...[/STYLE]` text for a mode (fields in bible order)."""
    rec = style_record(mode, aspect_ratio)
    lines = ["%s: %s" % (k, rec[k]) for k in (
        "aesthetic", "rendering_style", "camera_language", "lens_tendencies",
        "lighting_doctrine", "contrast_architecture", "environment_texture",
        "grain_sharpness")]
    lines.append("color_palette: %s" % " | ".join(rec["color_palette"]))
    lines.append("visual_continuity_constraints: %s" % " | ".join(
        rec["visual_continuity_constraints"]))
    lines.append("banned_visual_cliches: %s" % " | ".join(
        rec["banned_visual_cliches"]))
    return "[STYLE]\n" + "\n".join(lines) + "\n[/STYLE]"


# ------------------------------------------------------------- offering ----

def _norm(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def offered_look():
    """The Canvas to 3D look entry (one look, plan 6.11 / D21)."""
    return {LOOK_ID: dict(OFFERED[LOOK_ID])}


def assert_offered(look_id):
    """Refuse anything that is not this look, by name.

    Canvas to Life, Sketch to 3D and any realism blend are refused: this
    module only ever compiles painted 2D <-> lifelike 3D (D21/D29).
    """
    if not isinstance(look_id, str):
        raise Canvas3DError("LOOK_NOT_OFFERED",
                            "look id must be a string, got %r"
                            % (type(look_id).__name__,))
    norm = _norm(look_id)
    if norm in BANNED_STYLE_ALIASES:
        raise Canvas3DError(
            "LOOK_NOT_OFFERED",
            "%r is a different look; Canvas to 3D only ever switches painted "
            "2D <-> lifelike 3D. Offered here: %s" % (look_id, LOOK_ID))
    if norm != _norm(LOOK_ID):
        raise Canvas3DError("LOOK_NOT_OFFERED",
                            "%r is not this look; offered: %s"
                            % (look_id, LOOK_ID))
    return LOOK_ID


# ---------------------------------------------------------- identity -------

def _clean_token(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def identity_fingerprint(record):
    """Stable fingerprint over the locked identity fields."""
    norm = "\n".join("%s=%s" % (f, _clean_token(record.get(f)))
                     for f in IDENTITY_FIELDS)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def identity_lock(character):
    """Lock a character: one fingerprint both halves must carry.

    Requires a character name; every other locked field defaults to empty and
    is still part of the fingerprint, so adding glasses in the 3D half breaks
    the lock instead of passing silently.
    """
    if not isinstance(character, dict):
        raise Canvas3DError("IDENTITY_INVALID",
                            "identity must be a dict, got %r"
                            % (type(character).__name__,))
    name = str(character.get("character") or character.get("name") or "").strip()
    if not name:
        raise Canvas3DError("IDENTITY_INVALID",
                            "identity needs a character name "
                            "(fields: %s)" % ", ".join(IDENTITY_FIELDS))
    rec = {f: str(character.get(f, "") or "").strip() for f in IDENTITY_FIELDS}
    rec["character"] = name
    rec["fingerprint"] = identity_fingerprint(rec)
    return rec


def assert_identity_lock(plan, identity=None):
    """Raise unless every plan entry carries the same identity fingerprint."""
    errs = identity_errors(plan, identity)
    if errs:
        raise Canvas3DError("IDENTITY_LOCK_BROKEN", "; ".join(errs))
    return plan


def identity_errors(plan, identity=None):
    """Error list for the identity lock across a plan."""
    errs = []
    if not isinstance(plan, list) or not plan:
        return ["PLAN_EMPTY"]
    expected = None
    if identity is not None:
        expected = identity.get("fingerprint") if isinstance(identity, dict) \
            else None
        if not expected:
            expected = identity_lock(identity)["fingerprint"]
    for entry in plan:
        got = entry.get("identity_lock") if isinstance(entry, dict) else None
        sid = entry.get("shot_id") if isinstance(entry, dict) else None
        if not got:
            errs.append("IDENTITY_MISSING:%s" % sid)
            continue
        if expected is None:
            expected = got
        elif got != expected:
            errs.append("IDENTITY_LOCK_BROKEN:%s" % sid)
    return errs


# ------------------------------------------------------------- offering ----

def beat_mode(beat):
    """Storyboard beat -> mode (plan 6.11: sketch/painted beats vs the
    hard-hitting beats that carry the weight; Canvas to 3D plays those in
    lifelike 3D)."""
    b = str(beat).strip().lower()
    if b in THREED_BEATS:
        return MODE_3D
    if b in PAINTED_BEATS:
        return MODE_PAINTED
    raise Canvas3DError("BEAT_UNKNOWN",
                        "beat %r is not one of: %s"
                        % (beat, ", ".join(sorted(PAINTED_BEATS | THREED_BEATS))))


def _validate_shots(shots):
    if not isinstance(shots, list) or not shots:
        raise Canvas3DError("SHOTS_INVALID", "shots must be a non-empty list")
    for s in shots:
        if not isinstance(s, dict) or not s.get("shot_id"):
            raise Canvas3DError("SHOT_INVALID",
                                "shot record with shot_id required")
        try:
            secs = float(s.get("seconds"))
        except (TypeError, ValueError):
            raise Canvas3DError("SHOT_INVALID",
                                "shot %s needs numeric seconds" % s.get("shot_id"))
        if secs <= 0:
            raise Canvas3DError("SHOT_INVALID",
                                "shot %s seconds must be > 0" % s.get("shot_id"))


def _merge(modes, seconds, hold_min):
    """Absorb any run shorter than the hold into its neighbor (no flicker)."""
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
            if total >= hold_min:
                continue
            target = runs[r_idx - 1][0] if r_idx > 0 else runs[r_idx + 1][0]
            for k in idxs:
                out[k] = target
            changed = True
            break
    return out


def switch_match(shot, nxt):
    """The matching key a switch rides on: 'pose', 'framing' or None.

    Plan 6.11: switch on matching poses or framings. A switch with neither
    is refused by the planner instead of silently crossfading a jump cut.
    """
    for key in ("framing", "pose"):
        a, b = shot.get(key), nxt.get(key)
        if isinstance(a, str) and a.strip() and a == b:
            return key
    return None


def dissolve_seconds(shot, nxt, version_e=False):
    """Dissolve for a switch: 0.3-0.4 s, short end on a matched framing.

    version_e=True forces the receipt's 0.4 s alpha crossfade.
    """
    if version_e:
        return VERSION_E_DISSOLVE_SECONDS
    matched = switch_match(shot, nxt)
    if matched == "framing":
        return DISSOLVE_SECONDS[0]
    if matched == "pose":
        return 0.35                                # midway between 0.3 and 0.4
    return DISSOLVE_SECONDS[1]


def _lipsync(mode, shot):
    """Plan 6.11: in Canvas to 3D, lip-sync only on short front-facing
    lifelike 3D close-ups. Painted shots never lip-sync."""
    if mode != MODE_3D:
        return False
    if not shot.get("front_facing"):
        return False
    if str(shot.get("kind", "")).lower() not in ("close-up", "closeup"):
        return False
    return float(shot["seconds"]) <= 5.0


def plan_switches(shots, identity, version_e=False):
    """Per-shot Canvas-to-3D plan from the storyboard (plan 6.11 rules).

    Raises Canvas3DError with a code for every refused storyboard:
    SHOTS_INVALID / SHOT_INVALID, BEAT_UNKNOWN, FINALE_NOT_3D (the look ends
    on lifelike 3D, as Version E does), NO_SWITCH (a plan that never leaves
    painted mode is not this look), SWITCH_POSE_MISMATCH (a switch without a
    matching pose or framing), FINALE_HOLD (finale shorter than the hold),
    IDENTITY_INVALID.

    version_e=True builds to the Version E receipt: 0.4 s crossfade on every
    switch and a 7.2 s minimum hold. Plans only ever carry painted-2d and
    lifelike-3d; realism and golden realism never appear.
    """
    lock = identity_lock(identity)   # recomputes the fingerprint, never trusted
    _validate_shots(shots)
    hold_min = VERSION_E_MIN_HOLD_SECONDS if version_e else HOLD_MIN_SECONDS
    seconds = [float(s["seconds"]) for s in shots]
    beats = [str(s.get("beat", "")).strip().lower() for s in shots]
    modes = [beat_mode(b) for b in beats]
    modes = _merge(modes, seconds, hold_min)

    if modes[-1] != MODE_3D:
        raise Canvas3DError(
            "FINALE_NOT_3D",
            "storyboard ends on beat %r (%s); Canvas to 3D ends on lifelike "
            "3D like Version E" % (beats[-1], modes[-1]))
    if not any(m == MODE_PAINTED for m in modes):
        raise Canvas3DError("NO_SWITCH",
                            "plan is all lifelike 3D; Canvas to 3D requires a "
                            "2D painted section that switches to 3D")

    final_run = seconds[-1]
    k = len(modes) - 2
    while k >= 0 and modes[k] == MODE_3D:
        final_run += seconds[k]
        k -= 1
    if final_run < hold_min:
        raise Canvas3DError("FINALE_HOLD",
                            "finale is %.2fs; lifelike 3D must hold at least "
                            "%.1fs" % (final_run, hold_min))

    for i in range(len(shots) - 1):
        if modes[i + 1] == modes[i]:
            continue
        matched = switch_match(shots[i], shots[i + 1])
        if matched is None:
            raise Canvas3DError(
                "SWITCH_POSE_MISMATCH",
                "switch %s -> %s has no matching pose or framing (plan 6.11 "
                "switch-on-matching-pose): %r vs %r"
                % (shots[i]["shot_id"], shots[i + 1]["shot_id"],
                   {kk: shots[i].get(kk) for kk in ("pose", "framing")},
                   {kk: shots[i + 1].get(kk) for kk in ("pose", "framing")}))

    plan = []
    for i, shot in enumerate(shots):
        mode = modes[i]
        nxt = shots[i + 1] if i + 1 < len(shots) else None
        entry = {
            "shot_id": shot["shot_id"],
            "beat": beats[i],
            "mode": mode,
            "seconds": seconds[i],
            "identity_lock": lock["fingerprint"],
            "lip_sync": _lipsync(mode, shot),
        }
        if nxt is not None and modes[i + 1] != mode:
            entry["transition_out"] = {
                "kind": "dissolve",
                "dissolve_seconds": dissolve_seconds(shot, nxt, version_e),
                "match_on": switch_match(shot, nxt),
                "note": "switch on matching poses or framings",
            }
        else:
            entry["transition_out"] = {"kind": "cut" if nxt is None else "hold"}
        plan.append(entry)
    return plan


def validate_plan(plan, identity=None):
    """Error list (empty = plan obeys every switching and identity rule)."""
    errs = []
    if not isinstance(plan, list) or not plan:
        return ["PLAN_EMPTY"]
    for e in plan:
        if not isinstance(e, dict):
            return ["PLAN_INVALID"]
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
            if tr.get("match_on") not in ("pose", "framing"):
                errs.append("SWITCH_NO_MATCH_KEY:%s" % e.get("shot_id"))
        if mode == MODE_PAINTED and e.get("lip_sync"):
            errs.append("PAINTED_LIPSYNC:%s" % e.get("shot_id"))
    if plan[-1].get("mode") != MODE_3D:
        errs.append("FINALE_NOT_3D:%s" % plan[-1].get("shot_id"))
    modes = [e.get("mode") for e in plan]
    if not any(m == MODE_PAINTED for m in modes):
        errs.append("NO_SWITCH")
    if any(modes[i] == modes[i + 1] and
           (plan[i].get("transition_out") or {}).get("kind") == "dissolve"
           for i in range(len(modes) - 1)):
        errs.append("DISSOLVE_INSIDE_RUN")
    run_mode, run_secs = None, 0.0
    for e in plan:
        if e.get("mode") != run_mode:
            if run_mode is not None and run_secs < HOLD_MIN_SECONDS:
                errs.append("HOLD_TOO_SHORT:%s" % run_mode)
            run_mode, run_secs = e.get("mode"), 0.0
        run_secs += float(e.get("seconds") or 0)
    if run_mode is not None and run_secs < HOLD_MIN_SECONDS:
        errs.append("HOLD_TOO_SHORT:%s" % run_mode)
    errs.extend(identity_errors(plan, identity))
    return errs


# --------------------------------------------------------- Version E --------

def receipt_candidate_paths(explicit=None, lane_dir=None):
    """Ordered absolute paths where the Version E receipt may live.

    An explicit path is authoritative: it is the only candidate, so a pinned
    receipt that is absent refuses instead of silently loading another file.
    Otherwise C3 order: the skill's own folder first (receipt-shaped
    candidates only — realism-cinematic.md is a different file and this look
    bans realism), then an env override, then a lane fixture, then a walk up
    from this module. Operator-Mac defaults are not searched.
    """
    out = []

    def add(path):
        path = os.path.abspath(path)
        if path not in out:
            out.append(path)

    def add_receipt_roots(roots):
        for root in roots:
            add(os.path.join(root, RECEIPT_FILENAME))
            add(os.path.join(root, "creative-fidelity-h3", RECEIPT_FILENAME))

    if explicit:
        add(explicit)
        return out
    env = os.environ.get(RECEIPT_ENV_VAR)
    if env:
        add(env)
    if lane_dir:
        add_receipt_roots([os.path.abspath(lane_dir)])
    # Walk up from this module: canvas_to_3d/ -> style_bibles/ -> core/ ->
    # scripts/ -> skill root and any further ancestors.
    parents = []
    p = MODULE_DIR
    for _ in range(6):
        p = os.path.dirname(p)
        parents.append(p)
    add_receipt_roots(parents)
    return out


def find_receipt(explicit=None, lane_dir=None):
    """First existing Version E receipt, else None. Existence only."""
    for path in receipt_candidate_paths(explicit, lane_dir):
        if os.path.isfile(path):
            return path
    return None


def _segment_mode(label, where):
    lab = str(label).strip().upper()
    if lab == "2D" or lab.startswith("2D "):
        return MODE_PAINTED
    if lab == "3D" or lab.startswith("3D "):
        return MODE_3D
    raise Canvas3DError("VERSION_E_RECEIPT_INVALID",
                        "%s: segment mode %r is neither 2D nor 3D"
                        % (where, label))


def version_e_schedule(explicit=None, lane_dir=None):
    """The real Version E schedule, read from its receipt. Fail closed.

    Returns {"source", "segments", "modes", "switches_s", "dissolve_seconds",
    "min_hold_s", "duration_s", "transition"}. A missing or malformed receipt
    raises Canvas3DError naming every path searched (negative-result rule).
    """
    path = find_receipt(explicit, lane_dir)
    searched = receipt_candidate_paths(explicit, lane_dir)
    if path is None:
        raise Canvas3DError(
            "VERSION_E_RECEIPT_MISSING",
            "%s not found; searched: %s"
            % (RECEIPT_FILENAME, "; ".join(searched)))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as e:
        raise Canvas3DError("VERSION_E_RECEIPT_UNREADABLE", "%s: %s" % (path, e))
    except ValueError as e:
        raise Canvas3DError("VERSION_E_RECEIPT_INVALID",
                            "%s: %s" % (path, e))
    if not isinstance(data, dict):
        raise Canvas3DError("VERSION_E_RECEIPT_INVALID",
                            "%s: receipt is not a JSON object" % path)
    segments = data.get("segments")
    if not isinstance(segments, list) or not segments or \
            any(not isinstance(s, list) or len(s) < 3 for s in segments):
        raise Canvas3DError("VERSION_E_RECEIPT_INVALID",
                            "%s: segments must be a non-empty list of "
                            "[start, end, mode, note]" % path)
    modes = [_segment_mode(s[2], path) for s in segments]
    for i in range(len(modes) - 1):
        if modes[i + 1] == modes[i]:
            raise Canvas3DError(
                "VERSION_E_RECEIPT_INVALID",
                "%s: segments %d and %d are both %s; Version E alternates "
                "2D and 3D" % (path, i, i + 1, modes[i]))
    switches = data.get("switches_s")
    if not isinstance(switches, list) or len(switches) != len(segments) - 1:
        raise Canvas3DError("VERSION_E_RECEIPT_INVALID",
                            "%s: switches_s must hold %d switch times"
                            % (path, len(segments) - 1))
    switches = [float(t) for t in switches]
    if switches != sorted(switches) or len(set(switches)) != len(switches):
        raise Canvas3DError("VERSION_E_RECEIPT_INVALID",
                            "%s: switch times must strictly increase" % path)
    transition = str(data.get("transition", ""))
    m = _CROSSFADE_RE.search(transition)
    if m is None:
        raise Canvas3DError("VERSION_E_RECEIPT_INVALID",
                            "%s: transition %r has no alpha crossfade"
                            % (path, transition))
    dissolve = round(float(m.group(1)), 2)
    if abs(dissolve - VERSION_E_DISSOLVE_SECONDS) > 1e-6:
        raise Canvas3DError(
            "VERSION_E_RECEIPT_INVALID",
            "%s: crossfade is %ss, the Version E recipe is %ss"
            % (path, dissolve, VERSION_E_DISSOLVE_SECONDS))
    try:
        min_hold = float(data.get("min_hold_s"))
    except (TypeError, ValueError):
        raise Canvas3DError("VERSION_E_RECEIPT_INVALID",
                            "%s: min_hold_s missing" % path)
    if min_hold < HOLD_MIN_SECONDS:
        raise Canvas3DError("VERSION_E_RECEIPT_INVALID",
                            "%s: min_hold_s %.2f is under the plan 6.11 hold "
                            "of %.1fs" % (path, min_hold, HOLD_MIN_SECONDS))
    duration = float(segments[-1][1])
    for i in range(len(segments)):
        start, end = float(segments[i][0]), float(segments[i][1])
        if not (0 <= start < end <= duration):
            raise Canvas3DError("VERSION_E_RECEIPT_INVALID",
                                "%s: bad segment window %s-%s" % (path, start, end))
        if i == len(segments) - 1:
            continue
        # switches_s holds the boundaries: switch i sits on the seam where
        # segment i ends and segment i+1 begins.
        nxt, nxt_start = switches[i], float(segments[i + 1][0])
        if abs(nxt - end) > 1e-6 or abs(nxt - nxt_start) > 1e-6:
            raise Canvas3DError(
                "VERSION_E_RECEIPT_INVALID",
                "%s: switch %ss does not sit on the seam of segments %d and "
                "%d (%s-%s / %s-%s)"
                % (path, nxt, i, i + 1, start, end, nxt_start,
                   float(segments[i + 1][1])))
    measured = min(float(s[1]) - float(s[0]) for s in segments)
    return {
        "source": path,
        "segments": segments,
        "modes": modes,
        "switches_s": tuple(switches),
        "dissolve_seconds": dissolve,
        "min_hold_s": min_hold,
        "measured_min_hold_s": round(measured, 3),
        "duration_s": duration,
        "transition": transition,
    }


def version_e_errors(plan, identity=None):
    """Error list: does this plan satisfy the Version E receipt numbers?"""
    errs = list(validate_plan(plan, identity))
    if not plan:
        return errs
    for e in plan:
        tr = e.get("transition_out") or {}
        if tr.get("kind") == "dissolve" and \
                float(tr.get("dissolve_seconds") or 0) != \
                VERSION_E_DISSOLVE_SECONDS:
            errs.append("VERSION_E_DISSOLVE:%s:%s"
                        % (e.get("shot_id"), tr.get("dissolve_seconds")))
    modes = [e.get("mode") for e in plan]
    run_mode, run_secs = None, 0.0
    for i, e in enumerate(plan):
        if e.get("mode") != run_mode:
            if run_mode is not None and run_secs < VERSION_E_MIN_HOLD_SECONDS:
                errs.append("VERSION_E_HOLD_TOO_SHORT:%s:%.2f"
                            % (run_mode, run_secs))
            if i and modes[i] == modes[i - 1]:
                errs.append("VERSION_E_NOT_ALTERNATING:%s" % e.get("shot_id"))
            run_mode, run_secs = e.get("mode"), 0.0
        run_secs += float(e.get("seconds") or 0)
    if run_mode is not None and run_secs < VERSION_E_MIN_HOLD_SECONDS:
        errs.append("VERSION_E_HOLD_TOO_SHORT:%s:%.2f" % (run_mode, run_secs))
    if modes and modes[-1] != MODE_3D:
        errs.append("VERSION_E_FINALE_NOT_3D")
    return errs


def assert_version_e(plan, identity=None):
    """Raise unless the plan matches the Version E receipt (0.4 s crossfade,
    7.2 s minimum hold, alternating 2D/3D, lifelike 3D finale)."""
    errs = version_e_errors(plan, identity)
    if errs:
        raise Canvas3DError("VERSION_E_VIOLATION", "; ".join(errs))
    return plan


# -------------------------------------------------------------- compile ----

def compile_prompt(shot, mode, identity, aspect_ratio="9:16",
                   transition_out=None, video=False):
    """Deterministic prompt compile for one Canvas-to-3D shot. Mockable, no spend.

    mode "painted-2d"  -> painted [STYLE] block; never lip-sync.
    mode "lifelike-3d" -> lifelike 3D [STYLE] block; lip-sync only on short
        front-facing 3D close-ups.

    Every prompt carries the `[compiled:style=` mark the consumption gate
    demands, the `[IDENTITY-LOCK ...]` fingerprint that must be identical on
    both halves, and the transition when the shot leaves a style.

    Returns {"prompt", "mode", "style_block", "identity_lock", "lip_sync",
    "look"}. Raises Canvas3DError on bad inputs (fail closed).
    """
    if mode not in MODES:
        raise Canvas3DError("MODE_INVALID",
                            "mode %r: expected one of %s"
                            % (mode, ", ".join(MODES)))
    if not isinstance(shot, dict) or not shot.get("shot_id") or \
            not str(shot.get("base_prompt", "")).strip():
        raise Canvas3DError("SHOT_INVALID",
                            "shot dict with shot_id and base_prompt required")
    if _bible is None:
        raise Canvas3DError("STYLE_BIBLE_UNAVAILABLE",
                            "product_style_bible not importable; run from core/")
    if aspect_ratio not in _bible.ASPECTS:
        raise Canvas3DError("ASPECT_INVALID",
                            "aspect %r is not a routed aspect (%s)"
                            % (aspect_ratio, ", ".join(sorted(_bible.ASPECTS))))
    if transition_out is not None and not isinstance(transition_out, dict):
        raise Canvas3DError("TRANSITION_INVALID",
                            "transition_out must be a dict, got %r"
                            % (type(transition_out).__name__,))
    lock = identity_lock(identity)   # recomputes the fingerprint, never trusted
    style_id = PAINTED_STYLE_ID if mode == MODE_PAINTED else THREED_STYLE_ID
    block = style_block(mode, aspect_ratio)
    base = str(shot["base_prompt"]).strip()
    for banned in BANNED_PROMPT_PHRASES:
        if banned in base.lower():
            raise Canvas3DError(
                "PROMPT_PHRASE_BANNED",
                "%s carries %r, which belongs to the realism looks, not "
                "Canvas to 3D" % (shot["shot_id"], banned))
    if video:
        # U15b video path: no square-bracket markers anywhere (H3 reads them
        # as camera commands) and no generic [MOTION] line; per-shot motion
        # comes from the shot spec. The block text itself is unchanged.
        body = block
        if body.startswith("[STYLE]"):
            body = body[len("[STYLE]"):]
        if body.rstrip().endswith("[/STYLE]"):
            body = body.rstrip()[:-len("[/STYLE]")]
        vparts = ["%s, %s mode. %s" % (style_id, mode, body.strip()),
                  "Identity lock fingerprint %s for character %s."
                  % (lock["fingerprint"], lock["character"])]
        tr = transition_out or {}
        if tr.get("kind") == "dissolve":
            d = tr.get("dissolve_seconds")
            if not isinstance(d, (int, float)) or \
                    not (DISSOLVE_SECONDS[0] <= float(d) <= DISSOLVE_SECONDS[1]):
                raise Canvas3DError("DISSOLVE_OUT_OF_RANGE",
                                    "%s: dissolve %r outside %.1f-%.1fs"
                                    % (shot["shot_id"], d,
                                       DISSOLVE_SECONDS[0], DISSOLVE_SECONDS[1]))
            vparts.append("Switch on the matching pose or framing at %.2f "
                          "seconds into the clip; hold each style at least "
                          "%.1f seconds; no flicker."
                          % (float(d), HOLD_MIN_SECONDS))
        vparts.append(base)
        prompt = " ".join(vparts)
        if "[" in prompt or "]" in prompt:
            raise Canvas3DError("VIDEO_PROMPT_BRACKETS",
                                "a video prompt may carry no square brackets")
        return {
            "prompt": prompt,
            "mode": mode,
            "style_block": block,
            "identity_lock": lock["fingerprint"],
            "lip_sync": _lipsync(mode, shot),
            "look": LOOK_ID,
            "video": True,
        }
    parts = [
        "[compiled:style=%s mode=%s aspect=%s look=%s]"
        % (style_id, mode, aspect_ratio, LOOK_ID),
        block,
        "[IDENTITY-LOCK fingerprint=%s character=%s]"
        % (lock["fingerprint"], lock["character"]),
    ]
    tr = transition_out or {}
    if tr.get("kind") == "dissolve":
        d = tr.get("dissolve_seconds")
        if not isinstance(d, (int, float)) or \
                not (DISSOLVE_SECONDS[0] <= float(d) <= DISSOLVE_SECONDS[1]):
            raise Canvas3DError("DISSOLVE_OUT_OF_RANGE",
                                "%s: dissolve %r outside %.1f-%.1fs"
                                % (shot["shot_id"], d,
                                   DISSOLVE_SECONDS[0], DISSOLVE_SECONDS[1]))
        parts.append("[DISSOLVE:%.2fs] switch on matching pose or framing; "
                     "hold each style at least %.1fs; no flicker [/DISSOLVE]"
                     % (float(d), HOLD_MIN_SECONDS))
    parts.append("[SHOT:%s] %s [/SHOT]" % (shot["shot_id"], base))
    # Part F F12: the clip prompt asks for motion (clips must move).
    parts.append("[MOTION] The subject moves naturally through the frame "
                 "[/MOTION]")
    return {
        "prompt": "\n".join(parts),
        "mode": mode,
        "style_block": block,
        "identity_lock": lock["fingerprint"],
        "lip_sync": _lipsync(mode, shot),
        "look": LOOK_ID,
    }
