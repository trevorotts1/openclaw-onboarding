"""storyboard_director.py: QC gate before video spend + adversarial review (directive 14.1, 14.4). Stdlib only.

adversarial_review() challenges a bound shot plan against all twelve 14.4
criteria with a fresh reviewer identity. It is a content check, not a flag
check: generic cinematic filler fails even when every field is non-empty.
video_spend_allowed() is the 14.1 gate: no clip spend until every shot is
storyboard_approved AND the adversarial review passes.
"""
from __future__ import annotations

import re

SCHEMA_VERSION = "1.0.0"
TOOL_VERSION = "1.0.0"

# Directive 14.4: the twelve challenge criteria, one key each.
CRITERIA = (
    "boring_repetition",
    "unclear_storytelling",
    "missing_emotional_beat",
    "product_too_early",
    "product_too_late",
    "continuity_mistakes",
    "unsupported_claim_visualization",
    "impossible_generation_requirements",
    "weak_camera_variety",
    "pacing_mismatch",
    "cost_inefficiency",
    "shots_that_cannot_be_visually_qcd",
)

PRODUCT_SHOT_VISIBILITY = frozenset({"featured", "hero", "packshot"})

# ponytail: fixed thresholds pending W2-02 story-arc reveal beats and the
# skill-67 generation catalog; adopt those inputs when they land.
EARLY_PRODUCT_CUTOFF = 0.15   # first product shot before 15% of song = too early
LATE_PRODUCT_CUTOFF = 0.75    # first product shot after 75% of song = too late
MAX_SINGLE_SHOT_S = 30.0      # longer than this cannot be one generated clip
MIN_CAMERA_VARIETY = 3        # distinct camera directions for a 3+ shot plan

FILLER_PATTERNS = [
    r"\bcinematic\b",
    r"\bb-?roll\b",
    r"\bstock footage\b",
    r"\bslow-?motion\b",
    r"\baerial (shot|view|footage)\b",
    r"\bcityscape\b",
    r"\bcool visuals?\b",
    r"\blooks? (cool|nice|good|amazing|great)\b",
    r"\bjust (a |some )?filler\b",
    r"\bnice (background|visuals?|shots?)\b",
    r"\bvibes\b",
    r"\baesthetic\b",
    r"\bmontage of (the )?(city|clouds?|traffic|waves?|lights?)\b",
    r"^(n/a|tbd|todo|t\.b\.d\.|same as above|see above|filler)\.?$",
    r"\bnot (really |strictly )?necessary\b",
]
_FILLER_RES = [re.compile(p, re.IGNORECASE) for p in FILLER_PATTERNS]

CLAIM_PATTERNS = [
    r"\bbest\b", r"#1\b", r"\bnumber one\b", r"\bguaranteed\b",
    r"\bproven\b", r"\bclinically\b", r"\bfda\b", r"\bcures?\b",
    r"\bmiracle\b", r"\bnever (fails|breaks)\b", r"\balways works\b",
]
_CLAIM_RES = [re.compile(p, re.IGNORECASE) for p in CLAIM_PATTERNS]
_SUBSTANTIATED_RES = [re.compile(p, re.IGNORECASE) for p in
                      (r"\bclaim\b", r"\bsubstantia", r"\blegal\b", r"\bproof\b",
                       r"\bdisclaimer\b", r"\bapproval\b")]


class ReviewError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _text(v):
    return v if isinstance(v, str) else ""


def _finder(criterion, shot_id, detail):
    return {"criterion": criterion, "shot_id": shot_id, "detail": detail}


def is_filler(shot, contract=None):
    """True when the shot is generic cinematic filler (directive 14.3).

    Inspects the actual words in visual_objective plus the contract's
    understanding/action/necessity text. A record with every field filled
    still fails when the words say nothing ("cinematic b-roll", "N/A").
    """
    texts = [_text((shot or {}).get("visual_objective"))]
    if isinstance(contract, dict):
        texts += [_text(contract.get("viewer_understanding")),
                  _text(contract.get("character_action")),
                  _text(contract.get("necessity"))]
    return any(rx.search(t.strip()) for t in texts for rx in _FILLER_RES
               if t.strip())


def _duration(shot):
    return shot["song_end"] - shot["song_start"]


def adversarial_review(shots, contracts=None, timing=None, budget_minor=None,
                       reviewer="adversarial-reviewer"):
    """Challenge a bound shot plan on all twelve 14.4 criteria.

    shots: list of 14.2 records (sorted by song_start internally).
    contracts: {shot_id: 14.3 contract} or None (contract-dependent
      criteria report missing contracts instead of passing silently).
    timing: normalized timing map (load_timing_map output) or raw 12.4
      map; duration used for product/pacing positions.
    budget_minor: integer minor-unit ceiling for the cost criterion.
    Returns {"outcome": "pass"|"fail", ...} with one finding per defect.
    """
    if not isinstance(shots, list) or not shots:
        raise ReviewError("EMPTY_PLAN", "nothing to review")
    ordered = sorted(shots, key=lambda s: (s["song_start"], s["song_end"]))
    contracts = contracts if isinstance(contracts, dict) else {}
    findings = []
    n = len(ordered)

    if timing is not None:
        if isinstance(timing, dict) and "lines" not in timing \
                and isinstance(timing.get("sections"), list):
            # Raw 12.4 map: derive duration inline (no cross-package import).
            ends = [ln.get("end", 0) for sec in timing["sections"]
                    if isinstance(sec, dict)
                    for ln in (sec.get("lyrics") or [])
                    if isinstance(ln, dict)]
            timing = {"duration_seconds": timing.get("duration_seconds")
                      or (max(ends) if ends else 0)}
        duration = timing.get("duration_seconds") if isinstance(timing, dict) else None
    else:
        duration = None
    if not (isinstance(duration, (int, float)) and not isinstance(duration, bool)
            and duration > 0):
        duration = max(_duration(s) + s["song_start"] for s in ordered)

    def contract_of(sid):
        return contracts.get(sid)

    # 1. boring repetition: adjacent shots, same place + same camera.
    for a, b in zip(ordered, ordered[1:]):
        if (a["location_id"].strip().lower() == b["location_id"].strip().lower()
                and a["camera_direction"].strip().lower()
                == b["camera_direction"].strip().lower()):
            findings.append(_finder("boring_repetition", b["shot_id"],
                                    "%s repeats %s: same location '%s' + same camera '%s'"
                                    % (b["shot_id"], a["shot_id"],
                                       b["location_id"], b["camera_direction"])))
        if (a["visual_objective"].strip().lower()
                == b["visual_objective"].strip().lower()):
            findings.append(_finder("boring_repetition", b["shot_id"],
                                    "%s repeats %s visual objective verbatim"
                                    % (b["shot_id"], a["shot_id"])))

    for s in ordered:
        sid, c = s["shot_id"], contract_of(s["shot_id"])
        if c is None:
            findings.append(_finder("unclear_storytelling", sid,
                                    "no 14.3 lyric-to-visual contract; storytelling unverifiable"))
        else:
            # 2. unclear storytelling: blank stage or understanding.
            if not _text(s["story_stage"]).strip() \
                    or not _text(c.get("viewer_understanding")).strip():
                findings.append(_finder("unclear_storytelling", sid,
                                        "story_stage or viewer_understanding is blank"))
            # 3. missing emotional beat.
            emo = _text(c.get("visible_emotion")).strip().lower()
            if not emo or emo in ("none", "n/a"):
                findings.append(_finder("missing_emotional_beat", sid,
                                        "no visible emotion named"))
            # 14.3 filler check doubles as a review criterion under repetition.
            if is_filler(s, c):
                findings.append(_finder("boring_repetition", sid,
                                        "generic cinematic filler, not a lyric-bound visual"))
        # 7. unsupported claim visualization.
        shown = "%s %s" % (_text(s["visual_objective"]),
                           _text((c or {}).get("viewer_understanding")))
        if any(rx.search(shown) for rx in _CLAIM_RES) and not any(
                rx.search(_text(q)) for q in s["qc_requirements"]
                for rx in _SUBSTANTIATED_RES):
            findings.append(_finder("unsupported_claim_visualization", sid,
                                    "visualizes a claim ('%s') with no claim QC requirement"
                                    % shown.strip()[:80]))
        # 8. impossible generation requirements.
        if _duration(s) > MAX_SINGLE_SHOT_S:
            findings.append(_finder("impossible_generation_requirements", sid,
                                    "%.1fs single shot exceeds %.0fs generatable clip ceiling"
                                    % (_duration(s), MAX_SINGLE_SHOT_S)))
        # 10. pacing mismatch: many lines crammed, or one line stretched.
        nlines = len(s["lyric_line_ids"])
        if (nlines >= 3 and _duration(s) < 4.0) or (nlines == 1 and _duration(s) > 20.0):
            findings.append(_finder("pacing_mismatch", sid,
                                    "%d lyric line(s) in %.1fs" % (nlines, _duration(s))))
        # 12. shots that cannot be visually QC'd.
        if not s["qc_requirements"]:
            findings.append(_finder("shots_that_cannot_be_visually_qcd", sid,
                                    "qc_requirements empty; nothing to verify against"))

    # 4/5. product timing against song position.
    product_positions = sorted(s["song_start"] / duration for s in ordered
                               if s["product_visibility"] in PRODUCT_SHOT_VISIBILITY)
    if product_positions:
        if product_positions[0] < EARLY_PRODUCT_CUTOFF:
            findings.append(_finder("product_too_early", ordered[0]["shot_id"],
                                    "first product visual at %.0f%% of song (cutoff %.0f%%)"
                                    % (product_positions[0] * 100,
                                       EARLY_PRODUCT_CUTOFF * 100)))
        if product_positions[0] > LATE_PRODUCT_CUTOFF:
            findings.append(_finder("product_too_late", ordered[-1]["shot_id"],
                                    "first product visual at %.0f%% of song (cutoff %.0f%%)"
                                    % (product_positions[0] * 100,
                                       LATE_PRODUCT_CUTOFF * 100)))
    else:
        findings.append(_finder("product_too_late", None,
                                "no product visibility in any shot"))

    # 6. continuity: returning character, changed wardrobe, no constraint note.
    by_char = {}
    for s in ordered:
        for ch in s["character_ids"]:
            by_char.setdefault(ch, []).append(s)
    for ch, seq in by_char.items():
        for a, b in zip(seq, seq[1:]):
            if set(a["wardrobe_ids"]) != set(b["wardrobe_ids"]):
                noted = any(re.search(r"wardrobe|change|costume", _text(x), re.IGNORECASE)
                            for x in (a["continuity_constraints"]
                                      + b["continuity_constraints"]))
                if not noted:
                    findings.append(_finder("continuity_mistakes", b["shot_id"],
                                            "character '%s' wardrobe changed %s -> %s "
                                            "with no continuity constraint" % (
                                                ch, a["wardrobe_ids"],
                                                b["wardrobe_ids"])))

    # 9. weak camera variety across the plan.
    cams = {s["camera_direction"].strip().lower() for s in ordered}
    if len(cams) < min(MIN_CAMERA_VARIETY, n):
        findings.append(_finder("weak_camera_variety", None,
                                "only %d distinct camera direction(s) in %d shots"
                                % (len(cams), n)))

    # 11. cost inefficiency: over ceiling, or one shot eating the budget.
    costs = [s["cost_estimate"] for s in ordered]
    total = sum(costs)
    if isinstance(budget_minor, int) and not isinstance(budget_minor, bool) \
            and total > budget_minor:
        findings.append(_finder("cost_inefficiency", None,
                                "plan cost %d exceeds ceiling %d"
                                % (total, budget_minor)))
    if n >= 3:
        med = sorted(costs)[n // 2]
        for s in ordered:
            if med > 0 and s["cost_estimate"] > 2 * med:
                findings.append(_finder("cost_inefficiency", s["shot_id"],
                                        "cost %d exceeds 2x plan median %d"
                                        % (s["cost_estimate"], med)))

    ok = not findings
    return {"outcome": "pass" if ok else "fail",
            "reason_code": "storyboard-accepted"
            if ok else "adversarial-changes-required",
            "reviewer": reviewer, "criteria": list(CRITERIA),
            "shots_reviewed": [s["shot_id"] for s in ordered],
            "findings": findings,
            "next_action": "Release to video generation."
            if ok else "Repair the shot plan before generating the clip."}


def video_spend_allowed(shots, review):
    """Directive 14.1 gate: True only when every shot is storyboard_approved
    AND the adversarial review passed. Anything else blocks video spend."""
    if not isinstance(shots, list) or not shots:
        return {"allowed": False, "reason_code": "no-approved-storyboard",
                "next_action": "Bind a shot plan and pass adversarial review first."}
    unapproved = [s["shot_id"] for s in shots
                  if s.get("status") != "storyboard_approved"]
    if unapproved:
        return {"allowed": False, "reason_code": "storyboard-not-approved",
                "unapproved": unapproved,
                "next_action": "Approve storyboards for: %s." % ", ".join(unapproved)}
    if not isinstance(review, dict) or review.get("outcome") != "pass":
        return {"allowed": False, "reason_code": "adversarial-review-not-passed",
                "next_action": "Repair the shot plan before generating the clip."}
    return {"allowed": True, "reason_code": "storyboard-gate-open",
            "next_action": "Release to video generation."}
