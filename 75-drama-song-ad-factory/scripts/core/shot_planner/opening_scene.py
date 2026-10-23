"""opening_scene.py: the APPROVED opening line and its visible action reach the
generated scene plan and the shot sequence (S75X-W4-U1, directive items 3/5E).

The approved script already names the opening (``script_approval`` shows
``OPENING SPOKEN HOOK``). Documentation alone is not enough: the first scene
and the first shot must CARRY that exact line and that exact visible action,
so the picture cannot drift away from the approved words.

Ambiguity is explicit, never inferred from the image. A visible action can
read as the opposite emotion -- tears at an award night read as joy when the
intended meaning is a breakdown. When the approved opening is ambiguous (by
declaration or by a cue pair such as tears + award), a plan with no reading
context is REFUSED (``OPENING_AMBIGUOUS``): the context and a matching
negative constraint must ride into the shot, where ``prompt_spec_for`` puts
them in front of the image model.

Stdlib only. Additive: nothing here changes the behaviour of the existing
planner functions.
"""
from __future__ import annotations

import re

try:
    from .shot_planner import PlanError
except ImportError:                      # imported as a top-level module
    from shot_planner import PlanError   # type: ignore

#: The four facts that must survive into the scene plan and the shot.
OPENING_KEYS = ("line", "action", "intended_emotion", "reading_context")

SCENE_ID = "scene-opening"
SCENE_INDEX = 0

#: A cue pair can read as the opposite emotion. (visible cue, company it keeps,
#: the opposite reading the image would silently invite). Conservative on
#: purpose: a hit demands context, it never guesses the emotion.
OPPOSITE_READINGS = (
    (r"\b(tears?|crying|sobs?|weeping|weeps?)\b",
     r"\b(award|wins?|winning|troph(?:y|ies)|stage|applause|celebrat\w*|"
     r"confetti|champagne|victory|graduat\w*|wedding)\b",
     "joy"),
    (r"\b(smil(?:e|es|ing)|laugh(?:s|ing)?|grin(?:s|ning)?)\b",
     r"\b(funeral|grave|grief|loss|lost|diagnos\w*|terminal|divorce|"
     r"fired|bankrupt\w*)\b",
     "relief or denial"),
)

_CUE_RES = tuple((re.compile(a, re.I), re.compile(b, re.I), opposite)
                 for a, b, opposite in OPPOSITE_READINGS)

#: Script fields that carry the opening, in priority order. ``elements`` (the
#: shape ``script_approval.stage`` reads) wins over a top-level copy.
_LINE_KEYS = ("opening_spoken_hook", "opening_line")
_ACTION_KEYS = ("opening_visible_action", "opening_action", "first_visible_action")
_EMOTION_KEYS = ("opening_visible_emotion", "opening_emotion", "opening_intended_emotion")
_CONTEXT_KEYS = ("opening_reading_context", "opening_context")
_AMBIGUITY_KEYS = ("opening_ambiguity", "opening_ambiguity_risk")


def _text(v):
    return v.strip() if isinstance(v, str) else ""


def _first_text(record, keys):
    for k in keys:
        v = record.get(k) if isinstance(record, dict) else None
        if isinstance(v, (list, tuple)):
            v = next((x for x in v if isinstance(x, str) and x.strip()), None)
        v = _text(v)
        if v:
            return v
    return ""


def _spoken(section):
    """True for a spoken (not sung) non-``end`` lyric section."""
    tag = str(section.get("tag") or "").strip().lower()
    return (tag != "end"
            and str(section.get("delivery") or "spoken").strip().lower() != "sung")


def infer_opposite_reading(action, scene_text=""):
    """The opposite emotion an ambiguous image could silently communicate.

    Returns ``{"opposite_emotion", "cue", "risk"}`` on a cue hit, else None.
    Cue pairs only -- this never invents an emotion for a plain action.
    """
    body = "%s %s" % (_text(action), _text(scene_text))
    for cue_re, company_re, opposite in _CUE_RES:
        cue = cue_re.search(body)
        company = company_re.search(body)
        if cue and company:
            return {"opposite_emotion": opposite,
                    "cue": cue.group(0).lower(),
                    "risk": ("'%s' surrounded by '%s' can read as %s, not the "
                             "approved emotion" % (cue.group(0), company.group(0),
                                                   opposite))}
    return None


def opening_from_script(script):
    """The approved opening from the signed-off script record.

    Reads ``elements`` first (the same shape ``script_approval.stage`` hands
    the presentation), then the top-level fields. The line falls back to the
    first spoken section's first line -- approved words, never invented. The
    action does not fall back: an image action the script never named is not
    approved, so the caller decides whether to demand it.
    """
    if not isinstance(script, dict):
        raise PlanError("BAD_SCRIPT", "the approved script must be an object")
    elements = script.get("elements") if isinstance(script.get("elements"), dict) else {}
    line = _first_text(elements, _LINE_KEYS) or _first_text(script, _LINE_KEYS)
    if not line:
        for sec in script.get("sheet") or []:
            if isinstance(sec, dict) and _spoken(sec):
                line = _first_text(sec, ("lines",))
                if line:
                    break
    if not line:
        raise PlanError("OPENING_LINE_MISSING",
                        "the approved script names no opening line and carries "
                        "no spoken section to take one from")
    action = _first_text(elements, _ACTION_KEYS) or _first_text(script, _ACTION_KEYS)
    emotion = _first_text(elements, _EMOTION_KEYS) or _first_text(script, _EMOTION_KEYS)
    context = _first_text(elements, _CONTEXT_KEYS) or _first_text(script, _CONTEXT_KEYS)
    declared = None
    for src in (elements, script):
        v = src.get("opening_ambiguity")
        if isinstance(v, dict):
            declared = dict(v)
            break
        risk = _first_text(src, _AMBIGUITY_KEYS)
        if risk:
            declared = {"risk": risk}
            break
    return {"line": line, "action": action, "intended_emotion": emotion,
            "reading_context": context, "declared_ambiguity": declared}


def build_opening_scene(opening):
    """The opening scene record. Refuses a plan that cannot be read safely.

    An ambiguous opening (declared, or a cue hit) requires
    ``reading_context``: one plain sentence saying how the image must be
    read. The context and the matching negative constraint are carried on the
    scene so they can reach the shot and the prompt.
    """
    if not isinstance(opening, dict):
        raise PlanError("BAD_OPENING", "opening must be an object")
    line = _text(opening.get("line"))
    action = _text(opening.get("action"))
    if not line:
        raise PlanError("OPENING_LINE_MISSING", "the approved opening line is required")
    if not action:
        raise PlanError("OPENING_ACTION_MISSING",
                        "the approved script names no first visible action; the "
                        "scene plan cannot invent one")
    emotion = _text(opening.get("intended_emotion"))
    context = _text(opening.get("reading_context"))
    declared = opening.get("declared_ambiguity")
    ambiguity = None
    if isinstance(declared, dict) and declared:
        opposite = _text(declared.get("opposite_emotion")
                         or declared.get("opposite")) or "the opposite emotion"
        ambiguity = {"source": "declared", "opposite_emotion": opposite,
                     "risk": _text(declared.get("risk"))
                     or "the approved opening can read as %s" % opposite}
    else:
        detected = infer_opposite_reading(action, " ".join(
            _text(opening.get(k)) for k in ("line", "intended_emotion")))
        if detected:
            ambiguity = dict(detected, source="detected")
    if ambiguity:
        if not context:
            raise PlanError(
                "OPENING_AMBIGUOUS",
                "the opening image can silently communicate the opposite "
                "emotion (%s). Name how it must be read in "
                "opening_reading_context before planning the scene."
                % ambiguity["risk"])
        ambiguity["negative_constraint"] = (
            "no %s reading; the image reads as %s"
            % (ambiguity["opposite_emotion"],
               emotion or "the approved emotion"))
    return {"scene_id": SCENE_ID, "scene_index": SCENE_INDEX, "line": line,
            "action": action, "intended_emotion": emotion,
            "reading_context": context, "ambiguity": ambiguity,
            "shot_id": None}


def _head_index(shots):
    """Index of the first shot in song order (stable on ties)."""
    return min(range(len(shots)), key=lambda i: float(shots[i].get("song_start", 0)))


def _carry(target, key, value, code):
    """Set ``target[key]`` when empty; refuse when it already says otherwise."""
    have = _text(target.get(key))
    if have and have != value:
        raise PlanError(code, "%s is already %r, the approved opening is %r"
                        % (key, have, value))
    target[key] = value


def apply_opening(scene, shots, contracts=None):
    """Write the opening scene into the shot sequence. Returns a receipt.

    The FIRST shot in song order carries the record under ``shot["opening"]``;
    its 14.3 contract carries the same line as ``lyric_text`` and the same
    action as ``character_action``. The ambiguity context and negative
    constraint are appended to the shot's continuity/negative constraints --
    the exact lists ``prompt_spec_for`` hands the image model. Shot order is
    never changed and no other shot is touched.
    """
    if not isinstance(scene, dict) or not _text(scene.get("line")):
        raise PlanError("BAD_SCENE", "scene must be the build_opening_scene record")
    if not isinstance(shots, list) or not shots:
        raise PlanError("OPENING_NO_SHOTS", "no shots to carry the opening")
    for i, sh in enumerate(shots):
        if not isinstance(sh, dict) or "song_start" not in sh:
            raise PlanError("OPENING_NO_SHOTS", "shot %d has no song_start" % i)
    idx = _head_index(shots)
    head = shots[idx]
    record = {"line": scene["line"], "action": scene["action"],
              "intended_emotion": scene.get("intended_emotion", ""),
              "reading_context": scene.get("reading_context", ""),
              "ambiguity": scene.get("ambiguity")}
    head["opening"] = record
    if scene.get("ambiguity") and scene["ambiguity"].get("negative_constraint"):
        neg = scene["ambiguity"]["negative_constraint"]
        if neg not in head.setdefault("negative_constraints", []):
            head["negative_constraints"].append(neg)
    if scene.get("reading_context"):
        cc = head.setdefault("continuity_constraints", [])
        if scene["reading_context"] not in cc:
            cc.append(scene["reading_context"])
    if contracts is not None:
        if not isinstance(contracts, dict):
            raise PlanError("CONTRACT_INVALID", "contracts must map shot_id")
        sid = head.get("shot_id")
        contract = contracts.setdefault(sid, {})
        if not isinstance(contract, dict):
            raise PlanError("CONTRACT_INVALID", "contract for %s must be a record" % sid)
        _carry(contract, "lyric_text", scene["line"], "OPENING_CONFLICT")
        _carry(contract, "character_action", scene["action"], "OPENING_CONFLICT")
        if scene.get("intended_emotion"):
            _carry(contract, "visible_emotion", scene["intended_emotion"],
                   "OPENING_CONFLICT")
        if scene.get("reading_context"):
            _carry(contract, "viewer_understanding",
                   scene["reading_context"], "OPENING_CONFLICT")
    scene = dict(scene, shot_id=head.get("shot_id"))
    return {"scene_id": scene["scene_id"], "shot_id": scene["shot_id"],
            "shot_index": idx,
            "shot_order": [sh.get("shot_id") for sh in sorted(
                shots, key=lambda s: float(s.get("song_start", 0)))]}


def validate_opening(scene, shots, contracts=None):
    """Every way the opening can silently drop out of the plan ([] = intact)."""
    errs = []
    if not isinstance(scene, dict):
        return ["OPENING_SCENE_MISSING: no opening scene plan"]
    if not isinstance(shots, list) or not shots:
        return ["OPENING_NO_SHOTS: no shot sequence"]
    idx = _head_index(shots)
    head = shots[idx]
    rec = head.get("opening")
    if not isinstance(rec, dict):
        return ["OPENING_LOST: the first shot carries no opening record"]
    for key in ("line", "action"):
        want = _text(scene.get(key))
        got = _text(rec.get(key))
        if got != want:
            errs.append("OPENING_LOST: shot %s opening %s is %r, approved %r"
                        % (head.get("shot_id"), key, got, want))
    amb = scene.get("ambiguity")
    if amb:
        ctx = _text(scene.get("reading_context"))
        if not ctx:
            errs.append("OPENING_AMBIGUOUS: ambiguity declared with no reading context")
        elif ctx not in (head.get("continuity_constraints") or []):
            errs.append("OPENING_CONTEXT_LOST: the reading context does not reach "
                        "shot %s continuity_constraints" % head.get("shot_id"))
        neg = _text(amb.get("negative_constraint"))
        if neg and neg not in (head.get("negative_constraints") or []):
            errs.append("OPENING_CONTEXT_LOST: the opposite-reading negative "
                        "constraint does not reach shot %s"
                        % head.get("shot_id"))
    if contracts is not None:
        contract = contracts.get(head.get("shot_id")) if isinstance(contracts, dict) else None
        if not isinstance(contract, dict):
            errs.append("OPENING_LOST: no contract for the opening shot %s"
                        % head.get("shot_id"))
        else:
            for key, want in (("lyric_text", scene.get("line")),
                              ("character_action", scene.get("action"))):
                if _text(contract.get(key)) != _text(want):
                    errs.append("OPENING_LOST: contract %s is %r, approved %r"
                                % (key, _text(contract.get(key)), _text(want)))
    return errs


def plan_opening(script, shots, contracts=None):
    """Load -> scene plan -> shot sequence -> proof, in one call.

    Returns ``{"scene", "shots", "contracts", "receipt"}``. Raises PlanError
    (OPENING_LINE_MISSING / OPENING_ACTION_MISSING / OPENING_AMBIGUOUS /
    OPENING_CONFLICT / OPENING_LOST) rather than returning a half-bound plan.
    """
    opening = opening_from_script(script)
    scene = build_opening_scene(opening)
    receipt = apply_opening(scene, shots, contracts)
    errs = validate_opening(scene, shots, contracts)
    if errs:
        raise PlanError("OPENING_LOST", "; ".join(errs))
    return {"scene": scene, "shots": shots, "contracts": contracts,
            "receipt": receipt}
