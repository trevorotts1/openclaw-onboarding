#!/usr/bin/env python3
"""opening_choices.py: the sensational-opening acceptance contract (W2B-T01-r1 isolated lane file).

Doctrine: references/sensational-openings.md.

ONE contract for the opening, used by the story command, the lyric command, the
script authoring writer and the script-approval gate.

What the contract proves (and what it refuses to pretend):

* Three genuinely different candidates, each with the six doctrine fields, a
  named crisis type, a scene, ONE dramatic question and finite 0-5 scores.
* The highest legitimate total is recommended, or a written veto names that
  candidate and its doctrine ground.
* The chosen candidate binds to the EXACT first performed SPOKEN line, the EXACT
  first physical action and the digest of the ACTUAL scene.
* Doctrine section 3 negatives are REJECT-ONLY: a hit refuses, a miss proves
  nothing about quality.
* Semantic quality requires a review RETURNED BY A CONFIGURED CHECKER through
  the host's own review channel, bound to the current subject digests. There is
  no import from a caller-supplied string, no CLI authority flag, and no review
  file read out of the document under review: a review written by the maker, a
  PASS written into the script, and a caller-named module are all worthless
  here. A missing channel is a named, satisfiable refusal, never a silent pass
  and never an unconditional dead end: the composition root installs the
  channel once with ``configure_host_channel``.

Stdlib only. No network, no model dispatch, no writes, no side effects on
import.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import sys

SCHEMA = "blackceo.opening-gate/v2"
RESULT_SCHEMA = "blackceo.opening-review-result/v1"
CONTRACT_VERSION = "2.0.0"

CANDIDATE_FIELDS = (
    "opening_line",
    "headline",
    "first_action",
    "question",
    "why_this_audience",
    "offer_link",
)
CRISIS_TYPES = ("revelation", "confrontation", "discovery",
                "humiliation", "reversal", "catastrophe")
SCORE_FIELDS = ("shock", "curiosity", "relevance")
BINDING_FIELDS = ("scene_id", "scene_sha256", "first_spoken_line", "first_action")
CANDIDATE_COUNT = 3
LABELS = ("FICTIONAL_PLOT_EVENT", "COMPOSITE", "CLIENT_SUPPLIED_TRUE")

#: The configured independent checker role (department wiring / role library).
#: A fixed constant: no caller names a checker, no CLI flag assigns one.
CONFIGURED_CHECKER_ROLE = "qc-specialist-video"
CHECKER_ROLES = (CONFIGURED_CHECKER_ROLE,)

AUTHORITY_UNAVAILABLE = "OPENING_REVIEW_AUTHORITY_UNAVAILABLE"
REVIEW_MISSING_RESULT = "OPENING_REVIEW_MISSING_RESULT"
REVIEW_AUTHORITY_ERROR = "OPENING_REVIEW_AUTHORITY_ERROR"
REVIEW_INVALID = "OPENING_REVIEW_INVALID"
REVIEW_NOT_INDEPENDENT = "OPENING_REVIEW_NOT_INDEPENDENT"
REVIEW_STALE = "OPENING_REVIEW_STALE"
REVIEW_ASSIGNMENT_MISMATCH = "OPENING_REVIEW_ASSIGNMENT_MISMATCH"
REVIEW_REJECTED = "OPENING_REVIEW_REJECTED"
DECLARATION_CONFLICT = "OPENING_DECLARATION_CONFLICT"
PROJECTION_PARENT_REQUIRED = "OPENING_PROJECTION_PARENT_REQUIRED"
PROJECTION_STALE = "OPENING_PROJECTION_STALE"
PROJECTION_LINES = "OPENING_PROJECTION_LINES"
PROJECTION_CONTEXT = "OPENING_PROJECTION_CONTEXT"
PROJECTION_BINDING = "OPENING_PROJECTION_BINDING"
PROJECTION_OPENING = "OPENING_PROJECTION_OPENING"
PROJECTION_MISSING = "OPENING_PROJECTION_MISSING"
REVIEW_PAYLOAD_REQUIRED = "OPENING_REVIEW_PAYLOAD_REQUIRED"
REVIEW_PAYLOAD_INVALID = "OPENING_REVIEW_PAYLOAD_INVALID"
REVIEW_PAYLOAD_CONFLICT = "OPENING_REVIEW_PAYLOAD_CONFLICT"
REVIEW_ARTIFACT_CONFLICT = "OPENING_REVIEW_ARTIFACTS_INVALID"
REVIEW_SUBJECT_CONFLICT = "OPENING_REVIEW_SUBJECT_CONFLICT"
PAYLOAD_FIELDS = ("script", "lyrics")

REQUIRED_AUTHORITY = (
    "an independent semantic review returned by the configured checker role "
    "(%r) through the host review channel, bound to the exact subject digests "
    "of the package being consumed; a PASS written by the maker, a review file "
    "inside the document, or a caller-named module is not authority"
    % CONFIGURED_CHECKER_ROLE)

#: Doctrine section 3 negatives. REJECT-ONLY; narrow on purpose.
_NEGATIVES = (
    ("biography", re.compile(r"^(?:hi[,!. ]+)?my name is\b", re.I)),
    ("biography", re.compile(r"^(?:i am|i'm|i’m)\s+[A-Z][a-z]+")),
    ("biography", re.compile(r"^i grew up\b", re.I)),
    ("business-introduction", re.compile(
        r"\b(?:founder|co-?founder|owner|president|ceo)\s+(?:of|at)\b", re.I)),
    ("business-introduction", re.compile(
        r"^(?:we are|we're|we’re)\s+(?:a|an)\s+(?:family|company|business)\b", re.I)),
    ("logo-or-title-card", re.compile(r"^(?:welcome to|welcome back to)\b", re.I)),
    ("scenery", re.compile(
        r"^(?:the\s+)?(?:sunrise|sunset|skyline|waves|traffic|drone shot|"
        r"beautiful (?:sunrise|sunset|beach|sky|city))\b", re.I)),
    ("generic-question", re.compile(
        r"^(?:are|do|have)\s+(?:you|we)\b.*\b(?:tired|struggl\w*|fed up|sick of)\b",
        re.I)),
    ("story-announcement", re.compile(
        r"\blet me tell you (?:my|the) story\b", re.I)),
)
_SCENERY_ACTION = re.compile(
    r"^(?:a\s+)?(?:wide shot|skyline|sunrise|sunset|drone shot|traffic|logo|"
    r"title card|beautiful (?:sunrise|sunset|beach|sky|city))\b", re.I)
_MECHANISM = re.compile(
    r"\b(?:because|so that|which means|therefore|leads to|causes|makes|"
    r"results in|so)\b", re.I)
_REAL_CLAIM = re.compile(
    r"\b(?:verified|real customer|actual results|studies show|guaranteed)\b", re.I)


class OpeningRefused(Exception):
    def __init__(self, code, message, packet=None):
        super().__init__(message)
        self.code = code
        self.packet = packet or {}


def digest(record):
    blob = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def text_sha256(value):
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _blank(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def _index(value):
    return (isinstance(value, int) and not isinstance(value, bool)
            and 0 <= value < CANDIDATE_COUNT)


def _score(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value)) and 0.0 <= float(value) <= 5.0


def _defect(error, detail, **refs):
    out = {"error": error, "detail": detail}
    out.update(refs)
    return out


def _payload_defects(payload):
    """The payload the checker must judge: the COMPLETE in-memory script and
    lyrics of the candidate that exists now.

    A digest-only or empty payload is an omission, never permission: an empty
    object carrying a convincing ``payload_sha256`` is refused here, and the
    digest is always recomputed from the bytes (``review_subject`` /
    ``accept_review``) rather than read from the caller.
    """
    if payload is None:
        return [_defect(
            REVIEW_PAYLOAD_REQUIRED,
            "the review payload is required: the complete in-memory script and "
            "lyrics the checker must judge, not digests alone")]
    if not isinstance(payload, dict):
        return [_defect(REVIEW_PAYLOAD_INVALID,
                        "the review payload must be an object carrying %s"
                        % ", ".join(PAYLOAD_FIELDS))]
    out = []
    for field in PAYLOAD_FIELDS:
        value = payload.get(field)
        if _blank(value):
            out.append(_defect(
                REVIEW_PAYLOAD_INVALID,
                "payload.%s is required and must not be empty: the checker reviews "
                "the actual content, and an omitted or empty payload is never "
                "authority" % field, field=field))
        elif field == "script" and not isinstance(value, dict):
            out.append(_defect(
                REVIEW_PAYLOAD_INVALID,
                "payload.script must be the full script document object",
                field=field))
        elif field == "lyrics" and not isinstance(value, (dict, list, str)):
            out.append(_defect(
                REVIEW_PAYLOAD_INVALID,
                "payload.lyrics must be the lyric document, line list or exact "
                "lyric text", field=field))
    return out


def _script_approval():
    """The ONE owner of the approval-domain identities, imported lazily.

    ``script_approval`` imports nothing from this module, so there is no cycle.
    The identities are NOT re-derived here: the presented review artifacts and
    the approval gate must never drift into two hashes for one package.
    """
    try:
        from script_approval import script_approval as _SA  # noqa: PLC0415
    except ImportError:
        core = os.path.dirname(os.path.abspath(__file__))
        if core not in sys.path:
            sys.path.insert(0, core)
        from script_approval import script_approval as _SA  # noqa: PLC0415
    return _SA


def payload_lyrics(document):
    """The exact lyric content a presented document carries -- never invented.

    The review payload must be the COMPLETE in-memory material, so the lyrics
    ride with the script document the caller handed in, not a disk re-read.
    """
    if not isinstance(document, dict):
        return None
    lyrics = document.get("lyrics")
    if isinstance(lyrics, str) and lyrics.strip():
        return lyrics
    if isinstance(lyrics, list) and lyrics:
        return lyrics
    sheet = document.get("sheet")
    if isinstance(sheet, list):
        text = "\n".join(str(line) for section in sheet
                         if isinstance(section, dict)
                         for line in section.get("lines") or [])
        if text.strip():
            return text
    return lyrics if lyrics is not None else None


def approval_artifacts(document, lyrics=None):
    """The APPROVAL-domain identities the presented review artifacts ARE.

    ``script_approval.current_digests`` owns the definition (title, story and the
    spoken non-``end`` sheet; the stripped lyric text). It is called, never
    copied, so the review subject cannot describe a different package identity
    than the gate the client's approval binds.
    """
    SA = _script_approval()
    text = payload_lyrics(document) if lyrics is None else lyrics
    if not isinstance(text, str):
        text = "" if text is None else "\n".join(str(item) for item in text)
    document = document if isinstance(document, dict) else {}
    return SA.current_digests(document.get("title") or "Your song",
                              document.get("story") or [],
                              document.get("sheet") or [], text)


def lyric_artifacts(lyrics_doc, parent_script):
    """The LYRIC review domain: the two complete DOCUMENT digests."""
    out = {"lyrics": digest(lyrics_doc)}
    if isinstance(parent_script, dict):
        out["script"] = digest(parent_script)
    return out


def _artifact_defects(supplied, expected):
    """A supplied identity mapping is an ASSERTION, never authority."""
    if not supplied:
        return []
    if not isinstance(supplied, dict):
        return [_defect(REVIEW_ARTIFACT_CONFLICT,
                        "artifacts must be the current package's identity mapping")]
    if dict(supplied) != dict(expected):
        return [_defect(REVIEW_ARTIFACT_CONFLICT,
                        "the supplied artifact digests are not the current package's "
                        "identity: they are computed from the current content, and a "
                        "caller-supplied hash may only assert them",
                        supplied=dict(supplied), expected=dict(expected))]
    return []


def _payload_conflicts(supplied, expected):
    """The supplied payload must BE the complete current content, not a claim."""
    if supplied is None:
        return []
    if supplied == expected:
        return []
    return [_defect(
        REVIEW_PAYLOAD_CONFLICT,
        "the review payload is not the complete current content: it must be exactly "
        "the script and lyrics of the candidate that exists now, so a foreign "
        "document, a digest-only placeholder or altered payload text is refused "
        "before any external review")]


def _chosen_facts(opening):
    chosen = chosen_candidate(opening) or {}
    opening = opening if isinstance(opening, dict) else {}
    return {
        "question": chosen.get("question"),
        "offer_link": chosen.get("offer_link"),
        "labels": list(chosen.get("labels") or []),
        "recommended": opening.get("recommended"),
        "chosen": opening.get("chosen"),
        "candidates": list(opening.get("candidates") or []),
    }


def _document_facts(script_doc, kind):
    """The facts a script document's OWN bytes derive, or None when unreadable."""
    if not isinstance(script_doc, dict):
        return None
    checked = check_document(script_doc, kind)
    if checked["outcome"] != "ok":
        return None
    revision = checked["revision"]
    facts = {
        "document_sha256": revision["document_sha256"],
        "opening_sha256": revision["opening_sha256"],
        "candidate_set_sha256": revision["candidate_set_sha256"],
        "selection_sha256": revision["selection_sha256"],
        "scene_sha256": revision["actual"]["scene_sha256"],
        "first_line_sha256": revision["first_line_sha256"],
        "first_action_sha256": text_sha256(revision["actual"]["first_action"]),
        "first_spoken_line": revision["actual"]["first_spoken_line"],
        "first_action": revision["actual"]["first_action"],
    }
    facts.update(_chosen_facts(script_doc.get("opening")))
    return facts


def _lyric_document_facts(lyrics_doc, parent_script):
    """The facts the derived lyrics derive against their REQUIRED parent."""
    if not isinstance(lyrics_doc, dict) or verify_lyric_projection(lyrics_doc, parent_script):
        return None
    receipt, found = validate_opening(lyrics_doc.get("opening"))
    if found:
        return None
    actual = actual_content(parent_script, "authored")
    facts = {
        "document_sha256": digest(lyrics_doc),
        "opening_sha256": receipt["opening_sha256"],
        "candidate_set_sha256": receipt["candidate_set_sha256"],
        "selection_sha256": receipt["selection_sha256"],
        "scene_sha256": actual["scene_sha256"],
        "first_line_sha256": text_sha256(actual["first_spoken_line"]),
        "first_action_sha256": text_sha256(actual["first_action"]),
        "first_spoken_line": actual["first_spoken_line"],
        "first_action": actual["first_action"],
    }
    facts.update(_chosen_facts(lyrics_doc.get("opening")))
    return facts


def payload_domains(payload):
    """Every ``(domain, facts, artifacts)`` the payload's own bytes support.

    The domain is DERIVED, never declared by the caller: a payload is only the
    content behind a subject when its own document reproduces that subject's
    facts and identities. A caller cannot name a domain, supply a token or
    assert a boolean to make a foreign payload fit.
    """
    if not isinstance(payload, dict):
        return []
    script_doc = payload.get("script")
    lyrics_doc = payload.get("lyrics")
    if not isinstance(script_doc, dict):
        return []
    found = []
    if lyrics_doc == payload_lyrics(script_doc):
        artifacts = approval_artifacts(script_doc, lyrics_doc)
        for kind in ("presented", "authored"):
            if kind == "authored" and "scenes" not in script_doc:
                continue
            facts = _document_facts(script_doc, kind)
            if facts is not None:
                found.append((kind, facts, artifacts))
    if isinstance(lyrics_doc, dict):
        facts = _lyric_document_facts(lyrics_doc, script_doc)
        if facts is not None:
            found.append(("lyrics", facts, lyric_artifacts(lyrics_doc, script_doc)))
    return found


def _subject_conflicts(subject):
    """Reasons the subject's own facts are not the facts of its payload."""
    payload = subject.get("payload") if isinstance(subject, dict) else None
    found = payload_domains(payload)
    if not found:
        return [_defect(
            REVIEW_SUBJECT_CONFLICT,
            "the payload is not the current script and lyrics of any supported "
            "subject: its own document is missing, unreadable or not this "
            "package's content")]
    for _domain, facts, artifacts in found:
        if (facts["document_sha256"] == subject.get("document_sha256")
                and all(subject.get(key) == value for key, value in facts.items())
                and subject.get("artifacts") == artifacts):
            return []
    stale = sorted(key for key in found[0][1] if subject.get(key) != found[0][1][key])
    if subject.get("artifacts") != found[0][2]:
        stale.append("artifacts")
    return [_defect(
        REVIEW_SUBJECT_CONFLICT,
        "the review subject does not describe its own payload: %s do not match"
        % ", ".join(stale), stale=stale)]


# --------------------------------------------------------------------------- #
# candidate set
# --------------------------------------------------------------------------- #

def validate_opening(opening):
    """(receipt, defects) for one declared opening block. Deterministic."""
    defects = []
    receipt = {"schema": SCHEMA, "contract_version": CONTRACT_VERSION}
    if not isinstance(opening, dict):
        return receipt, [_defect("OPENING_DECLARATION_REQUIRED",
                                 "an opening block is required")]

    candidates = opening.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != CANDIDATE_COUNT:
        defects.append(_defect(
            "OPENING_CANDIDATE_COUNT",
            "exactly %d opening candidates are required" % CANDIDATE_COUNT))
        candidates = candidates if isinstance(candidates, list) else []

    rows = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            defects.append(_defect("OPENING_CANDIDATE_INVALID",
                                   "candidate %d is not an object" % index,
                                   candidate=index))
            continue
        for field in CANDIDATE_FIELDS:
            if _blank(candidate.get(field)):
                defects.append(_defect("OPENING_FIELD_MISSING",
                                       "candidate %d: %s is required" % (index, field),
                                       candidate=index, field=field))
        crisis = str(candidate.get("crisis_type") or "").strip().lower()
        if crisis not in CRISIS_TYPES:
            defects.append(_defect(
                "OPENING_CRISIS_TYPE",
                "candidate %d: crisis_type must be one of %s"
                % (index, list(CRISIS_TYPES)), candidate=index))
        question = candidate.get("question")
        if isinstance(question, str):
            if not question.strip().endswith("?") or question.count("?") != 1:
                defects.append(_defect(
                    "OPENING_QUESTION_NOT_SINGULAR",
                    "candidate %d: the dramatic question must be ONE question "
                    "ending in '?'" % index, candidate=index))
        action = _text(candidate.get("first_action"))
        if action and (_SCENERY_ACTION.search(action) or len(action.split()) < 3):
            defects.append(_defect(
                "OPENING_FIRST_ACTION_INVALID",
                "candidate %d: first_action must be one unambiguous physical "
                "action, not scenery or a situation" % index, candidate=index))
        link = _text(candidate.get("offer_link"))
        if link and not _MECHANISM.search(link):
            defects.append(_defect(
                "OPENING_OFFER_LINK_NOT_MECHANISM",
                "candidate %d: offer_link must state the causal mechanism into "
                "the offer, not a transition" % index, candidate=index))
        labels = candidate.get("labels")
        if not isinstance(labels, list) or not any(str(x) in LABELS for x in labels):
            defects.append(_defect(
                "OPENING_LABEL_MISSING",
                "candidate %d: label each invented event FICTIONAL_PLOT_EVENT / "
                "COMPOSITE, or the client's true story CLIENT_SUPPLIED_TRUE"
                % index, candidate=index))
        elif any(str(x) in ("FICTIONAL_PLOT_EVENT", "COMPOSITE") for x in labels):
            combined = " ".join(_text(candidate.get(f))
                                for f in ("opening_line", "headline", "offer_link"))
            if _REAL_CLAIM.search(combined):
                defects.append(_defect(
                    "OPENING_REAL_ATTRIBUTION",
                    "candidate %d: an invented event is presented as a verified "
                    "real fact" % index, candidate=index))
        scores = candidate.get("scores")
        if not isinstance(scores, dict):
            defects.append(_defect("OPENING_SCORES_MISSING",
                                   "candidate %d: scores are required" % index,
                                   candidate=index))
            continue
        for field in SCORE_FIELDS:
            if field not in scores:
                defects.append(_defect("OPENING_SCORES_MISSING",
                                       "candidate %d: score %s is required"
                                       % (index, field), candidate=index, field=field))
            elif not _score(scores.get(field)):
                defects.append(_defect(
                    "OPENING_SCORE_INVALID",
                    "candidate %d: %s must be a finite 0-5 number (booleans and "
                    "text are refused)" % (index, field), candidate=index, field=field))
        rows.append({
            "opening_line": candidate.get("opening_line"),
            "headline": candidate.get("headline"),
            "first_action": candidate.get("first_action"),
            "question": candidate.get("question"),
            "why_this_audience": candidate.get("why_this_audience"),
            "offer_link": candidate.get("offer_link"),
            "crisis_type": crisis,
            "scene": candidate.get("scene"),
            "labels": labels if isinstance(labels, list) else [],
            "scores": dict(scores),
            "total": (sum(float(scores[f]) for f in SCORE_FIELDS)
                      if all(_score(scores.get(f)) for f in SCORE_FIELDS) else None),
        })

    if len(rows) == CANDIDATE_COUNT:
        for field in ("crisis_type", "scene", "question", "opening_line"):
            values = [str(row.get(field) or "").strip() for row in rows]
            if len(set(values)) != CANDIDATE_COUNT:
                defects.append(_defect(
                    "OPENING_CANDIDATES_NOT_DISTINCT",
                    "the three candidates must differ in %s, not be one candidate "
                    "written three times" % field, field=field))
        totals = [row["total"] for row in rows]
        if all(total is not None for total in totals):
            highest = totals.index(max(totals))
            recommended = opening.get("recommended")
            if not _index(recommended):
                defects.append(_defect(
                    "OPENING_RECOMMENDATION_MISSING",
                    "recommended must be the index (0-%d) of one candidate"
                    % (CANDIDATE_COUNT - 1)))
            elif recommended != highest:
                veto = opening.get("recommendation_veto")
                if (not isinstance(veto, dict) or veto.get("candidate") != highest
                        or _blank(veto.get("reason"))):
                    defects.append(_defect(
                        "OPENING_RECOMMENDATION_NOT_STRONGEST",
                        "recommended candidate %d is not the highest total "
                        "(candidate %d scores %s); a written veto naming candidate "
                        "%d and its doctrine ground is required otherwise"
                        % (recommended, highest, max(totals), highest)))
            chosen = opening.get("chosen")
            if not _index(chosen):
                defects.append(_defect(
                    "OPENING_CHOICE_MISSING",
                    "chosen must be the index (0-%d) of the candidate actually used"
                    % (CANDIDATE_COUNT - 1)))
            elif recommended != chosen and _blank(opening.get("selection_note")):
                defects.append(_defect(
                    "OPENING_CHOICE_NOTE_MISSING",
                    "chosen candidate %d differs from the recommendation %d; "
                    "record the client's selection_note" % (chosen, recommended)))
            frozen = {k: opening.get(k) for k in
                      ("candidates", "recommended", "chosen", "recommendation_veto",
                       "selection_note")}
            receipt.update({
                "candidates": len(rows),
                "totals": totals,
                "recommended": recommended if _index(recommended) else None,
                "chosen": chosen if _index(chosen) else None,
                "highest_total_candidate": highest,
                "recommendation_is_strongest": _index(recommended) and recommended == highest,
                "candidate_set_sha256": digest(rows),
                # The FROZEN selection: everything except the scene binding. The
                # authored scene legitimately differs from the plan, so this is
                # the value that must survive authoring unchanged.
                "selection_sha256": digest(frozen),
                "opening_sha256": digest(frozen),
            })
    return receipt, defects


def chosen_candidate(opening):
    candidates = opening.get("candidates") if isinstance(opening, dict) else None
    chosen = opening.get("chosen") if isinstance(opening, dict) else None
    if isinstance(candidates, list) and _index(chosen) and chosen < len(candidates):
        candidate = candidates[chosen]
        return candidate if isinstance(candidate, dict) else None
    return None


def selection(opening):
    """The frozen selection record, or None when the block is not readable."""
    chosen = chosen_candidate(opening)
    if chosen is None:
        return None
    candidates = opening.get("candidates") or []
    receipt, defects = validate_opening(opening)
    if defects:
        return None
    return {
        "selection_sha256": receipt["selection_sha256"],
        "candidate_set_sha256": receipt["candidate_set_sha256"],
        "recommended": opening.get("recommended"),
        "chosen": opening.get("chosen"),
        "opening_line": chosen.get("opening_line"),
        "first_action": chosen.get("first_action"),
        "question": chosen.get("question"),
        "offer_link": chosen.get("offer_link"),
        "labels": list(chosen.get("labels") or []),
        "candidates": candidates,
    }


def compare_selection(planned, authored):
    """Defects when the authored opening is not the PLAN's frozen selection.

    Compares the selection only. The scene binding is compared separately
    against the authored scene, because the authored scene naturally differs
    from the plan's scene.
    """
    plan = selection(planned)
    seen = selection(authored)
    if plan is None:
        return [_defect("OPENING_PLAN_SELECTION_INVALID",
                        "the resolved scene plan carries no valid frozen opening "
                        "selection; resolve the plan's opening before dispatch")]
    if seen is None:
        return [_defect("OPENING_SELECTION_MISSING",
                        "the authored response carries no valid opening selection")]
    defects = []
    if seen["selection_sha256"] != plan["selection_sha256"]:
        defects.append(_defect(
            "OPENING_SELECTION_CHANGED",
            "the authored opening selection is not the plan's frozen selection",
            planned=plan["selection_sha256"], authored=seen["selection_sha256"]))
    for field in ("chosen", "recommended"):
        if seen[field] != plan[field]:
            defects.append(_defect(
                "OPENING_SELECTION_CHANGED",
                "the authored opening changed %s" % field,
                field=field, planned=plan[field], authored=seen[field]))
    for field in ("opening_line", "first_action"):
        if seen[field] != plan[field]:
            defects.append(_defect(
                "OPENING_SELECTION_CHANGED",
                "the authored opening changed the chosen %s" % field,
                field=field, planned=plan[field], authored=seen[field]))
    return defects


def negative_shapes(line):
    value = str(line or "").strip()
    return [name for name, pattern in _NEGATIVES if pattern.search(value)]


# --------------------------------------------------------------------------- #
# binding to the actual performed content
# --------------------------------------------------------------------------- #

def _first(values):
    for value in values:
        if not _blank(value):
            return value
    return None


def _spoken_section(section):
    """THE spoken-section rule, identical to script_approval._elements()."""
    return str(section.get("delivery") or "spoken").strip().lower() != "sung"


def _performed_sections(sheet):
    return [s for s in sheet
            if isinstance(s, dict)
            and str(s.get("tag") or "").strip().lower() != "end"
            and _spoken_section(s)]


def _presented_scene(document):
    """The first SPOKEN, non-``end`` sheet section -- never a sung section and
    never the ``end`` tag, which carry no performed opening."""
    sheet = document.get("sheet")
    if isinstance(sheet, list):
        for section in _performed_sections(sheet):
            return section
    scene = document.get("scene")
    return scene if isinstance(scene, dict) else None


def _presented_first_line(document, scene):
    if isinstance(scene, dict):
        lines = scene.get("lines") or []
        if isinstance(lines, list):
            value = _first(lines)
            if value is not None:
                return value
    story = document.get("story")
    if isinstance(story, list):
        for act in story:
            if isinstance(act, (list, tuple)) and len(act) >= 2 and isinstance(act[1], list):
                value = _first(act[1])
                if value is not None:
                    return value
    return _first([document.get("first_spoken_line")])


def _authored_scene(document):
    scenes = document.get("scenes")
    if isinstance(scenes, list) and scenes and isinstance(scenes[0], dict):
        return scenes[0]
    return None


def _authored_first_line(scene):
    if not isinstance(scene, dict):
        return None
    lines = [ln for ln in scene.get("spoken_dialogue") or [] if isinstance(ln, dict)]
    lines.sort(key=lambda ln: float(ln.get("start_s")) if isinstance(
        ln.get("start_s"), (int, float)) and not isinstance(ln.get("start_s"), bool) else 0.0)
    return _first([ln.get("text") for ln in lines])


def _lyrics_scene(document):
    for key in ("first_scene", "scene"):
        if isinstance(document.get(key), dict):
            return document[key]
    lines = document.get("lines")
    if isinstance(lines, list) and lines and isinstance(lines[0], dict):
        return lines[0]
    return None


def _lyrics_first_line(document):
    scene = _lyrics_scene(document)
    if isinstance(scene, dict):
        value = _first([scene.get("first_spoken_line")])
        if value is not None:
            return value
    value = document.get("first_spoken_line")
    if not _blank(value):
        return value
    lines = document.get("lines")
    if isinstance(lines, list):
        for line in lines:
            if isinstance(line, dict):
                return _first([line.get("text")])
    return None


def actual_content(document, kind=None):
    """The actual scene, first performed spoken line and first physical action."""
    if kind is None:
        if isinstance(document, dict) and "scenes" in document:
            kind = "authored"
        elif isinstance(document, dict) and "sheet" in document:
            kind = "presented"
        else:
            kind = "lyrics"
    if kind == "authored":
        scene = _authored_scene(document)
        first_line = _authored_first_line(scene)
    elif kind == "presented":
        scene = _presented_scene(document)
        first_line = _presented_first_line(document, scene)
    else:
        scene = _lyrics_scene(document)
        first_line = _lyrics_first_line(document)
    action = scene.get("visible_action") if isinstance(scene, dict) else None
    if _blank(action):
        action = document.get("first_action") if isinstance(document, dict) else None
    scene_id = None
    if isinstance(scene, dict):
        scene_id = _first([scene.get("scene_id"), scene.get("tag"), scene.get("line_id")])
    return {
        "kind": kind,
        "scene": scene,
        "scene_id": scene_id,
        "scene_sha256": digest(scene) if scene is not None else None,
        "first_spoken_line": first_line,
        "first_action": action,
    }


def declared_openings(document):
    """EVERY explicitly declared opener alias, as ``(source, value)`` pairs.

    ``elements.opening_spoken_hook`` and the top-level ``opening_spoken_hook``
    are independent declarations: BOTH are reconciled against the performed
    line. A matching alias can never shadow a conflicting one.
    """
    found = []
    if not isinstance(document, dict):
        return found
    elements = document.get("elements")
    if isinstance(elements, dict):
        value = elements.get("opening_spoken_hook")
        if not _blank(value):
            found.append(("elements.opening_spoken_hook", value))
    value = document.get("opening_spoken_hook")
    if not _blank(value):
        found.append(("opening_spoken_hook", value))
    return found


def declared_opening(document):
    """The first explicitly declared opener alias (``declared_openings`` order).
    Derived content is never written into it. Reconciliation happens in
    ``check_document``, which compares EVERY present alias."""
    found = declared_openings(document)
    return found[0][1] if found else None


def check_document(document, kind=None):
    """Opening declaration + exact binding to the document's own performed content."""
    if not isinstance(document, dict):
        return {"outcome": "rejected", "reason_code": "OPENING_DOCUMENT_INVALID",
                "errors": [_defect("OPENING_DOCUMENT_INVALID",
                                   "the document being checked is not an object")],
                "binding": None, "revision": None}
    opening = document.get("opening")
    receipt, defects = validate_opening(opening)
    if defects:
        return {"outcome": "rejected", "reason_code": defects[0]["error"],
                "errors": defects, "binding": None, "revision": receipt}
    actual = actual_content(document, kind)
    chosen = chosen_candidate(opening)
    binding = opening.get("binding")
    if not isinstance(binding, dict):
        defects.append(_defect("OPENING_BINDING_MISSING",
                               "opening.binding is required: %s"
                               % ", ".join(BINDING_FIELDS)))
        binding = {}
    for field in BINDING_FIELDS:
        if _blank(binding.get(field)):
            defects.append(_defect("OPENING_BINDING_MISSING",
                                   "opening.binding.%s is required" % field, field=field))
    if actual["scene"] is None:
        defects.append(_defect("OPENING_SCENE_UNBOUND",
                               "the %s document carries no actual performed scene "
                               "to bind" % actual["kind"]))
    if _blank(actual["first_spoken_line"]):
        defects.append(_defect("OPENING_LINE_UNBOUND",
                               "the document carries no first SPOKEN line to bind "
                               "(a sung lyric is not the spoken opener)"))
    if _blank(actual["first_action"]):
        defects.append(_defect("OPENING_ACTION_UNBOUND",
                               "the document carries no first physical action to bind"))
    if chosen is None:
        defects.append(_defect("OPENING_CHOICE_MISSING",
                               "the chosen candidate is not readable"))
    declared_aliases = declared_openings(document)
    if not _blank(actual["first_spoken_line"]):
        for source, declared in declared_aliases:
            if str(declared) != str(actual["first_spoken_line"]):
                defects.append(_defect(
                    DECLARATION_CONFLICT,
                    "the declared opening_spoken_hook (%s) is not the first "
                    "performed spoken line; it cannot be presented as the opening"
                    % source,
                    alias=source, declared=str(declared),
                    actual=str(actual["first_spoken_line"])))
    if chosen is not None and not _blank(actual["first_spoken_line"]):
        if str(chosen.get("opening_line")) != str(actual["first_spoken_line"]):
            defects.append(_defect(
                "OPENING_LINE_MISMATCH",
                "the chosen opening_line is not the document's exact first spoken line",
                chosen=str(chosen.get("opening_line")),
                actual=str(actual["first_spoken_line"])))
        if binding.get("first_spoken_line") != actual["first_spoken_line"]:
            defects.append(_defect(
                "OPENING_LINE_MISMATCH",
                "opening.binding.first_spoken_line is not the exact first spoken line",
                actual=str(actual["first_spoken_line"])))
        if chosen.get("first_action") != actual["first_action"]:
            defects.append(_defect(
                "OPENING_ACTION_MISMATCH",
                "the chosen first_action is not the document's exact first physical action",
                chosen=str(chosen.get("first_action")),
                actual=str(actual["first_action"])))
        if binding.get("first_action") != actual["first_action"]:
            defects.append(_defect(
                "OPENING_ACTION_MISMATCH",
                "opening.binding.first_action is not the exact first physical action",
                actual=str(actual["first_action"])))
    if actual["scene"] is not None:
        if binding.get("scene_id") != actual["scene_id"]:
            defects.append(_defect(
                "OPENING_SCENE_MISMATCH",
                "opening.binding.scene_id is not the actual scene",
                actual=actual["scene_id"]))
        if binding.get("scene_sha256") != actual["scene_sha256"]:
            defects.append(_defect(
                "OPENING_SCENE_STALE",
                "opening.binding.scene_sha256 is not the digest of the actual scene "
                "revision", actual=actual["scene_sha256"]))
    for label, value in (("opening_line", chosen.get("opening_line") if chosen else None),
                         ("first_spoken_line", actual["first_spoken_line"])):
        if not _blank(value):
            shapes = negative_shapes(value)
            if shapes:
                defects.append(_defect(
                    "OPENING_NEGATIVE_SHAPE",
                    "%s carries a doctrine section 3 negative shape (%s)"
                    % (label, ", ".join(shapes)), shapes=shapes))
    revision = dict(receipt)
    revision.update({
        "binding": dict(binding),
        "actual": {k: actual[k] for k in
                   ("kind", "scene_id", "scene_sha256", "first_spoken_line",
                    "first_action")},
        "document_sha256": digest(document),
        "first_line_sha256": text_sha256(actual["first_spoken_line"]),
    })
    if defects:
        return {"outcome": "rejected", "reason_code": defects[0]["error"],
                "errors": defects, "binding": actual, "revision": revision}
    return {"outcome": "ok", "reason_code": "OPENING_OK", "errors": [],
            "binding": actual, "revision": revision}


# --------------------------------------------------------------------------- #
# the configured host review channel
# --------------------------------------------------------------------------- #

class ReviewChannel:
    """One configured checker assignment and the transport that returns its result.

    ``resolve(subject)`` must dispatch to the assigned checker and return the
    checker's OWN typed result (``RESULT_SCHEMA``) for that exact subject. It is
    composed by the host, never named by a document and never parsed out of a
    caller-supplied module string.
    """

    def __init__(self, checker_role, resolve, assignment=None):
        if checker_role not in CHECKER_ROLES:
            raise OpeningRefused(
                REVIEW_ASSIGNMENT_MISMATCH,
                "checker role %r is not the configured role %r"
                % (checker_role, CONFIGURED_CHECKER_ROLE))
        if not callable(resolve):
            raise OpeningRefused(AUTHORITY_UNAVAILABLE,
                                 "the review channel needs a callable resolver")
        self.checker_role = checker_role
        self.resolve = resolve
        self.assignment = dict(assignment or {})

    def __repr__(self):
        return "ReviewChannel(checker_role=%r)" % (self.checker_role,)


_HOST_CHANNEL = None


def is_review_channel(value):
    """True for a channel object: the configured role plus a callable resolver.

    Structural on purpose. Class identity is not a security property here -- the
    authority comes from the FIXED role constant, the host-only installation and
    the subject-bound typed result, any of which a bare object cannot satisfy.
    (It also keeps the gate working when a test harness imports this module twice.)
    """
    return (value is not None
            and getattr(value, "checker_role", None) in CHECKER_ROLES
            and callable(getattr(value, "resolve", None)))


#: Process-wide, so one host composition installs one channel even if this module
#: object is reached twice (an embedded host, a test harness). It is NOT stored
#: anywhere a document, reply or CLI argument can write.
_HOST_ATTR = "_blackceo_opening_review_channel"


def configure_host_channel(channel):
    """Install the host's configured review channel (composition root only).

    Called once by the host composition (the factory that already owns client
    reply provenance). Nothing in a document, a CLI flag or an artifact can
    install or replace it: a caller with a string gets a refusal, not authority.
    """
    if not is_review_channel(channel):
        raise OpeningRefused(
            AUTHORITY_UNAVAILABLE,
            "the host review channel must carry the configured checker role (%r) "
            "and a callable resolver; %r does not"
            % (CONFIGURED_CHECKER_ROLE, type(channel).__name__))
    setattr(sys, _HOST_ATTR, channel)
    return channel


def host_channel():
    return getattr(sys, _HOST_ATTR, None)


def clear_host_channel():
    """Test/diagnostic reset only; it grants nothing."""
    if hasattr(sys, _HOST_ATTR):
        delattr(sys, _HOST_ATTR)


def review_subject(revision, artifacts=None, payload=None):
    """The exact subject a checker must review: current content digests, the
    quoted opening facts AND the complete in-memory payload.

    ``payload`` is the EXACT material being judged -- the full script document
    and the full derived lyrics of the candidate that actually exists now (the
    edited candidate, never a re-read of an older on-disk file). It is
    deep-copied and bound by ``payload_sha256``, which is computed HERE from the
    copied bytes, so a result produced for other content cannot satisfy this
    subject and a caller-supplied digest is never trusted.

    The payload also SOURCES the subject: every fact and the ``artifacts``
    identity mapping are derived from the payload's own bytes and must equal the
    supplied ``revision`` facts, so a payload cannot be described by another
    document's facts. ``artifacts`` is an assertion of the current identities
    only; a conflicting mapping refuses before any transport call.
    """
    actual = revision["actual"]
    chosen = revision.get("chosen_candidate") or {}
    subject = {
        "document_sha256": revision["document_sha256"],
        "opening_sha256": revision["opening_sha256"],
        "candidate_set_sha256": revision["candidate_set_sha256"],
        "selection_sha256": revision["selection_sha256"],
        "scene_sha256": actual["scene_sha256"],
        "first_line_sha256": revision["first_line_sha256"],
        "first_action_sha256": text_sha256(actual["first_action"]),
        "first_spoken_line": actual["first_spoken_line"],
        "first_action": actual["first_action"],
        "question": chosen.get("question"),
        "offer_link": chosen.get("offer_link"),
        "labels": list(chosen.get("labels") or []),
        "recommended": chosen.get("recommended"),
        "chosen": chosen.get("index"),
        "candidates": list(revision.get("candidates") or []),
        "artifacts": dict(artifacts or {}),
    }
    if payload is not None:
        defects = _payload_defects(payload)
        if defects:
            raise OpeningRefused(defects[0]["error"],
                                defects[0]["detail"], {"payload": defects})
        subject["payload"] = copy.deepcopy(payload)
        subject["payload_sha256"] = digest(subject["payload"])
        found = payload_domains(subject["payload"])
        match = next((row for row in found
                      if row[1]["document_sha256"] == subject["document_sha256"]
                      and all(subject.get(key) == value
                              for key, value in row[1].items())), None)
        if match is None:
            raise OpeningRefused(
                REVIEW_SUBJECT_CONFLICT,
                "the payload is not the current content these facts describe; the "
                "subject is derived from the payload's own bytes, never asserted")
        conflicts = _artifact_defects(artifacts, match[2])
        if conflicts:
            raise OpeningRefused(conflicts[0]["error"], conflicts[0]["detail"],
                                 {"artifacts": conflicts})
        subject["artifacts"] = dict(match[2])
    return subject


def _refusal(code, detail, subject, affected_action, run_dir=None, **extra):
    packet = {
        "reason_code": code,
        "affected_action": affected_action,
        "review_file_ignored": ("creative/opening-review.json"
                                if run_dir is None else
                                str(run_dir).rstrip("/") + "/creative/opening-review.json"),
        "required_authority": REQUIRED_AUTHORITY,
        "configured_checker_role": CONFIGURED_CHECKER_ROLE,
        "supported_path": ("configure_host_channel(ReviewChannel("
                           "CONFIGURED_CHECKER_ROLE, resolve)) once in the host "
                           "composition root, where resolve(subject) dispatches to "
                           "the assigned checker and returns its own "
                           "%r for that exact subject" % RESULT_SCHEMA),
        "required_subject": subject,
        "detail": detail,
    }
    packet.update(extra)
    return packet


def accept_review(subject, *, channel=None, maker=None, maker_session=None,
                  affected_action="production continuation", run_dir=None):
    """Accept only the configured checker's OWN successful result for ``subject``.

    No document field, no file and no module string can satisfy this. Every
    refusal is named and satisfiable.

    The expected subject is deep-copied BEFORE the transport runs and the
    transport receives its own separate copy: a resolver that mutates nested
    payload, candidates or artifacts changes only its own copy, so a mutated
    result can never match the scope it was meant to certify. The payload is
    mandatory: digests alone are never a reviewable subject.
    """
    expected_subject = copy.deepcopy(subject)
    transport_subject = copy.deepcopy(expected_subject)
    chan = channel if channel is not None else host_channel()
    if not is_review_channel(chan):
        return dict(_refusal(
            AUTHORITY_UNAVAILABLE,
            "no configured opening-review channel is composed for this run; the "
            "affected action (%s) stays closed until the host installs the "
            "configured checker" % affected_action,
            subject, affected_action, run_dir), ok=False)
    if chan.checker_role not in CHECKER_ROLES:
        return dict(_refusal(
            REVIEW_ASSIGNMENT_MISMATCH,
            "the channel is not assigned the configured checker role",
            expected_subject, affected_action, run_dir), ok=False)
    # The payload is the material being judged, so it cannot be omitted or faked
    # by a digest: the shape is checked and the digest is recomputed HERE.
    payload_problems = _payload_defects(expected_subject.get("payload"))
    if payload_problems:
        return dict(_refusal(
            payload_problems[0]["error"], payload_problems[0]["detail"],
            expected_subject, affected_action, run_dir,
            payload=payload_problems), ok=False)
    if expected_subject.get("payload_sha256") != digest(expected_subject["payload"]):
        return dict(_refusal(
            REVIEW_PAYLOAD_INVALID,
            "payload_sha256 is not the digest of the payload being reviewed; the "
            "binding is recomputed from the bytes, never trusted from a caller",
            expected_subject, affected_action, run_dir), ok=False)
    # The subject's facts AND artifact identities must be the payload's own: a
    # hand-built subject cannot attach old document facts to freshly chosen
    # content, and a recomputed payload digest cannot launder foreign material.
    conflicts = _subject_conflicts(expected_subject)
    if conflicts:
        return dict(_refusal(
            conflicts[0]["error"], conflicts[0]["detail"],
            expected_subject, affected_action, run_dir,
            stale=conflicts[0].get("stale")), ok=False)
    try:
        result = chan.resolve(transport_subject)
    except Exception as exc:  # noqa: BLE001 - a broken authority never passes
        return dict(_refusal(
            REVIEW_AUTHORITY_ERROR,
            "the configured review transport failed: %s" % str(exc)[:200],
            expected_subject, affected_action, run_dir), ok=False)
    # Everything below judges the ORIGINAL expected scope, never the copy the
    # transport was allowed to touch.
    subject = expected_subject
    if result is None:
        return dict(_refusal(
            REVIEW_MISSING_RESULT,
            "the configured checker returned no result for this subject",
            subject, affected_action, run_dir), ok=False)
    if not isinstance(result, dict):
        return dict(_refusal(REVIEW_INVALID,
                             "the checker result is not an object",
                             subject, affected_action, run_dir), ok=False)
    problems = []
    if result.get("schema") != RESULT_SCHEMA:
        problems.append("schema must be %r" % RESULT_SCHEMA)
    if result.get("status") != "success":
        problems.append("status must be \"success\" (an error/absent session is no "
                        "review)")
    if result.get("checker_role") != chan.checker_role:
        problems.append("checker_role %r is not the assigned channel role %r"
                        % (result.get("checker_role"), chan.checker_role))
    session = result.get("session")
    if not isinstance(session, str) or not session.strip():
        problems.append("the checker session is required")
    reviewer = result.get("reviewer")
    if not isinstance(reviewer, dict) or _blank(reviewer.get("identity")):
        problems.append("reviewer.identity is required")
    if problems:
        return dict(_refusal(REVIEW_INVALID, "; ".join(problems), subject,
                             affected_action, run_dir), ok=False)
    identity = str(reviewer.get("identity")).strip().lower()
    if maker and identity == str(maker).strip().lower():
        return dict(_refusal(REVIEW_NOT_INDEPENDENT,
                             "reviewer %r is the maker" % reviewer.get("identity"),
                             subject, affected_action, run_dir), ok=False)
    if maker_session and str(session).strip().lower() == str(maker_session).strip().lower():
        return dict(_refusal(REVIEW_NOT_INDEPENDENT,
                             "the checker session is the maker session",
                             subject, affected_action, run_dir), ok=False)
    if reviewer.get("session") and str(reviewer["session"]) != str(session):
        return dict(_refusal(REVIEW_INVALID,
                             "reviewer.session differs from the returned session",
                             subject, affected_action, run_dir), ok=False)
    returned = result.get("subject")
    if not isinstance(returned, dict):
        return dict(_refusal(REVIEW_MISSING_RESULT,
                             "the checker result carries no reviewed subject",
                             subject, affected_action, run_dir), ok=False)
    stale = sorted(key for key, value in subject.items()
                   if returned.get(key) != value)
    if stale:
        return dict(_refusal(REVIEW_STALE,
                             "the review is stale for the current content: %s do "
                             "not match" % ", ".join(stale),
                             subject, affected_action, run_dir,
                             stale=stale,
                             reviewed_subject={k: returned.get(k) for k in subject}),
                    ok=False)
    review = result.get("review")
    if not isinstance(review, dict):
        return dict(_refusal(REVIEW_INVALID,
                             "the checker result carries no semantic review",
                             subject, affected_action, run_dir), ok=False)
    sem = []
    if review.get("verdict") != "PASS":
        return dict(_refusal(REVIEW_REJECTED,
                             "the configured checker did not pass this opening "
                             "(verdict %r)" % (review.get("verdict"),),
                             subject, affected_action, run_dir), ok=False)
    for field, expected in (("reviewed_line", subject["first_spoken_line"]),
                            ("reviewed_action", subject["first_action"]),
                            ("reviewed_question", subject.get("question"))):
        if _blank(review.get(field)):
            sem.append("%s is required" % field)
        elif str(review.get(field)) != str(expected):
            sem.append("%s does not quote the reviewed content" % field)
    differences = review.get("differences")
    if (not isinstance(differences, list) or len(differences) != CANDIDATE_COUNT
            or any(_blank(str(x)) for x in differences)
            or len({str(x).strip() for x in differences}) != CANDIDATE_COUNT):
        sem.append("differences must assess each of the three candidates distinctly")
    if _blank(review.get("mechanism")):
        sem.append("mechanism is required")
    elif str(review.get("mechanism")) != str(subject.get("offer_link")):
        sem.append("mechanism does not state the chosen offer mechanism")
    if review.get("recommendation") != subject.get("recommended"):
        sem.append("recommendation does not match the reviewed recommendation")
    if list(review.get("fiction_attribution") or []) != list(subject.get("labels") or []):
        sem.append("fiction_attribution does not match the reviewed candidate labels")
    if sem:
        return dict(_refusal(REVIEW_INVALID, "; ".join(sem), subject,
                             affected_action, run_dir), ok=False)
    return {"ok": True, "reason_code": "OPENING_REVIEW_ACCEPTED",
            "configured_checker_role": chan.checker_role,
            "reviewer": {"identity": reviewer.get("identity"), "session": session},
            "review_sha256": digest(result), "required_subject": subject}


def problems(document, *, kind=None, channel=None, maker=None, maker_session=None,
             artifacts=None, payload=None, affected_action="production continuation",
             require_review=True, run_dir=None):
    """Every blocking problem; [] only for an accepted opening for these digests.

    ``require_review=False`` judges the declaration and the exact binding only,
    for the pre-dispatch authoring prerequisite. It never certifies quality.

    ``payload`` is the COMPLETE in-memory script and lyrics the checker must
    judge -- the candidate that actually exists now, including an edited one.
    It is required whenever a semantic review is required; digests alone are
    refused (``OPENING_REVIEW_PAYLOAD_REQUIRED``) and an empty object carrying a
    digest is refused (``OPENING_REVIEW_PAYLOAD_INVALID``). A supplied payload
    that is not EXACTLY this document and its current lyrics is refused before
    any transport call (``OPENING_REVIEW_PAYLOAD_CONFLICT``), and supplied
    ``artifacts`` may only assert the APPROVAL-domain identities computed from
    those bytes (``OPENING_REVIEW_ARTIFACTS_INVALID``).
    """
    checked = check_document(document, kind)
    out = [dict(d) for d in checked["errors"]]
    if checked["outcome"] != "ok" or not require_review:
        return out
    defects = _payload_defects(payload)
    if defects:
        return out + [dict(item) for item in defects]
    lyrics = payload_lyrics(document)
    canonical = {"script": document, "lyrics": lyrics}
    bound = _payload_conflicts(payload, canonical)
    bound += _artifact_defects(artifacts, approval_artifacts(document, lyrics))
    if bound:
        return out + [dict(item) for item in bound]
    revision = dict(checked["revision"])
    chosen = chosen_candidate(document.get("opening"))
    revision["candidates"] = list((document.get("opening") or {}).get("candidates") or [])
    revision["chosen_candidate"] = {
        "index": (document.get("opening") or {}).get("chosen"),
        "recommended": (document.get("opening") or {}).get("recommended"),
        "question": (chosen or {}).get("question"),
        "offer_link": (chosen or {}).get("offer_link"),
        "labels": list((chosen or {}).get("labels") or []),
    }
    subject = review_subject(revision, artifacts, canonical)
    verdict = accept_review(subject, channel=channel,
                            maker=maker if maker is not None else
                            (document.get("maker") if isinstance(document, dict) else None),
                            maker_session=maker_session,
                            affected_action=affected_action, run_dir=run_dir)
    if not verdict["ok"]:
        out.append({"error": verdict["reason_code"], "detail": verdict["detail"],
                    "review": verdict})
    return out


# --------------------------------------------------------------------------- #
# the lyric projection: derived lyrics must carry the SAME opening
# --------------------------------------------------------------------------- #

def derive_lyric_lines(scenes):
    """Canonical lyric records derived from the scenes' own performance lines."""
    lines = []
    for scene in scenes:
        for line in scene.get("sung_lyrics") or []:
            if not isinstance(line, dict):
                continue
            lines.append({
                "line_id": line.get("line_id"),
                "character_id": line.get("character_id"),
                "text": line.get("text"),
                "scene_id": scene.get("scene_id"),
                "section": line.get("section") or scene.get("song_section") or "verse",
                "repeat_of": line.get("repeat_of"),
            })
    return lines


def lyric_projection(script, opening):
    """The opening + first-scene context + parent digest that ride the lyrics.

    Built from the FINAL script artifact, after construction, so the projection
    digests are the real ones and no review of the authored document is copied
    onto a different projection.
    """
    scenes = script.get("scenes") or []
    scene = scenes[0] if scenes and isinstance(scenes[0], dict) else None
    actual = actual_content(script, "authored")
    block = dict(opening or {})
    block["binding"] = {
        "scene_id": actual["scene_id"],
        "scene_sha256": actual["scene_sha256"],
        "first_spoken_line": actual["first_spoken_line"],
        "first_action": actual["first_action"],
    }
    return {
        "opening": block,
        "first_scene": {
            "scene_id": actual["scene_id"],
            "first_spoken_line": actual["first_spoken_line"],
            "first_action": actual["first_action"],
            "sha256": actual["scene_sha256"],
        },
        "parent_script_digest": digest(script),
        "scene_plan_digest_hint": (script.get("bound_foundation") or {}
                                   .get("scene_plan", {}).get("digest")),
        "context_scene_present": scene is not None,
    }


def verify_lyric_projection(lyrics_doc, parent_script):
    """Refuse a lyric document whose opening/context does not match its parent.

    A standalone lyric record can be self-consistent and still describe another
    script: the parent is REQUIRED and is recomputed here, so self-bound metadata
    certifies nothing.

    The whole contract is enforced, not a summary of it: the projected opening
    must pass ``validate_opening`` on its own (three candidates, recommendation,
    veto, choice, scores, labels), every digest is RECOMPUTED from the projected
    records rather than read from an optional supplied field, the COMPLETE frozen
    selection is compared with the parent's own frozen selection, and EVERY
    binding field (scene id, scene digest, first spoken line, first action) is
    compared with the parent script's actual first scene.
    """
    defects = []
    if not isinstance(lyrics_doc, dict):
        return [_defect(PROJECTION_MISSING,
                        "the lyric document is not an object")]
    if not isinstance(lyrics_doc.get("opening"), dict):
        defects.append(_defect(PROJECTION_MISSING,
                               "the derived lyrics carry no opening projection; the "
                               "first sung lyric is not the spoken opener"))
    if not isinstance(parent_script, dict):
        defects.append(_defect(
            PROJECTION_PARENT_REQUIRED,
            "the parent script is required: a self-bound lyric record cannot "
            "certify which script it came from"))
        return defects
    if lyrics_doc.get("parent_script_digest") != digest(parent_script):
        defects.append(_defect(PROJECTION_STALE,
                               "the lyric projection is stale for this parent script"))
    expected = derive_lyric_lines(parent_script.get("scenes") or [])
    actual = lyrics_doc.get("lines")
    if not isinstance(actual, list):
        defects.append(_defect(PROJECTION_LINES,
                               "the lyric document carries no ordered line list"))
    else:
        def key(row):
            return (row.get("line_id"), row.get("character_id"),
                    " ".join(str(row.get("text") or "").split()).lower())
        if [key(r) for r in actual if isinstance(r, dict)] != [key(r) for r in expected]:
            defects.append(_defect(
                PROJECTION_LINES,
                "the lyric lines are not the parent script's sung lines in order"))
    first = actual_content(parent_script, "authored")
    context = lyrics_doc.get("first_scene")
    if not isinstance(context, dict):
        defects.append(_defect(PROJECTION_CONTEXT,
                               "the lyrics carry no first-scene context"))
    else:
        for field, expected_value in (("scene_id", first["scene_id"]),
                                      ("first_spoken_line", first["first_spoken_line"]),
                                      ("first_action", first["first_action"]),
                                      ("sha256", first["scene_sha256"])):
            if context.get(field) != expected_value:
                defects.append(_defect(
                    PROJECTION_CONTEXT,
                    "the lyric first-scene %s is not the parent script's" % field,
                    field=field))
    opening = lyrics_doc.get("opening")
    if not isinstance(opening, dict):
        return defects
    # 1. the projection must satisfy the COMPLETE opening contract itself. The
    #    receipt (and every digest in it) is RECOMPUTED here; a supplied
    #    candidate_set/selection/opening digest is compared, never trusted.
    receipt, found = validate_opening(opening)
    for item in found:
        defects.append(_defect(
            PROJECTION_OPENING,
            "the projected opening is not a valid opening contract: %s"
            % (item.get("detail") or item.get("error")),
            opening_error=item.get("error"), candidate=item.get("candidate"),
            field=item.get("field")))
    for field in ("opening_sha256", "selection_sha256", "candidate_set_sha256"):
        if field in opening and opening.get(field) != receipt.get(field):
            defects.append(_defect(
                PROJECTION_OPENING,
                "the projected %s is not the recomputed digest of the projected "
                "opening; a supplied digest is never trusted" % field, field=field))
    if found:
        return defects
    # 2. the COMPLETE frozen selection must be the parent script's own: all three
    #    candidates, the recommendation (and any veto), the choice, the chosen
    #    line and the chosen action.
    _plan_receipt, plan_found = validate_opening(parent_script.get("opening"))
    if plan_found:
        defects.append(_defect(
            PROJECTION_OPENING,
            "the parent script carries no valid frozen opening selection to "
            "compare against"))
    else:
        defects.extend(compare_selection(parent_script.get("opening"), opening))
    chosen = chosen_candidate(opening)
    if chosen is None:
        defects.append(_defect(PROJECTION_OPENING,
                               "the lyric opening carries no chosen candidate"))
    else:
        if str(chosen.get("opening_line")) != str(first["first_spoken_line"]):
            defects.append(_defect(
                PROJECTION_OPENING,
                "the lyric opening is not the parent script's first spoken line"))
        if chosen.get("first_action") != first["first_action"]:
            defects.append(_defect(
                PROJECTION_OPENING,
                "the lyric opening's first action is not the parent script's "
                "first physical action"))
    # 3. EVERY binding field against the parent's ACTUAL first scene.
    binding = opening.get("binding") if isinstance(opening.get("binding"), dict) else {}
    for field, expected_value in (("scene_id", first["scene_id"]),
                                  ("scene_sha256", first["scene_sha256"]),
                                  ("first_spoken_line", first["first_spoken_line"]),
                                  ("first_action", first["first_action"])):
        if binding.get(field) != expected_value:
            defects.append(_defect(
                PROJECTION_BINDING,
                "the lyric opening binding %s is not the parent script's actual "
                "first scene" % field, field=field))
    return defects


def lyric_problems(lyrics_doc, parent_script, *, channel=None, maker=None,
                   maker_session=None, artifacts=None, payload=None,
                   affected_action="lyric validation", require_review=True,
                   run_dir=None):
    """The lyric front door: projection first, then the package review.

    ``payload`` is the COMPLETE in-memory material of the candidate being judged
    -- the parent script and this very lyric document (the edited candidate when
    one exists). It is required for a semantic review and is deep-copied, bound
    by a digest computed here and never re-read from disk. A supplied payload
    that is not EXACTLY this lyric document and its parent script is refused
    before any transport call (``OPENING_REVIEW_PAYLOAD_CONFLICT``), and supplied
    ``artifacts`` may only assert the LYRIC review identities -- the two complete
    document digests -- computed from those bytes.
    """
    out = [dict(d) for d in verify_lyric_projection(lyrics_doc, parent_script)]
    if out or not require_review:
        return out
    defects = _payload_defects(payload)
    if defects:
        return out + [dict(item) for item in defects]
    canonical = {"script": parent_script, "lyrics": lyrics_doc}
    bound = _payload_conflicts(payload, canonical)
    bound += _artifact_defects(artifacts, lyric_artifacts(lyrics_doc, parent_script))
    if bound:
        return out + [dict(item) for item in bound]
    opening = lyrics_doc.get("opening") if isinstance(lyrics_doc.get("opening"), dict) else {}
    receipt, found = validate_opening(opening)
    if found:                       # ``verify_lyric_projection`` refused already
        return out + [dict(item) for item in found]
    actual = actual_content(parent_script, "authored")
    # Every digest here is RECOMPUTED from the projected opening and the parent
    # script. Nothing an optional supplied field says is trusted as authority.
    revision = dict(receipt)
    revision.update({
        "document_sha256": digest(lyrics_doc),
        "first_line_sha256": text_sha256(actual["first_spoken_line"]),
        "actual": {"first_spoken_line": actual["first_spoken_line"],
                   "first_action": actual["first_action"],
                   "scene_sha256": actual["scene_sha256"]},
    })
    chosen = chosen_candidate(lyrics_doc.get("opening")) or {}
    revision["candidates"] = list((lyrics_doc.get("opening") or {}).get("candidates") or [])
    revision["chosen_candidate"] = {
        "index": (lyrics_doc.get("opening") or {}).get("chosen"),
        "recommended": (lyrics_doc.get("opening") or {}).get("recommended"),
        "question": chosen.get("question"),
        "offer_link": chosen.get("offer_link"),
        "labels": list(chosen.get("labels") or []),
    }
    subject = review_subject(revision, artifacts, canonical)
    verdict = accept_review(subject, channel=channel, maker=maker,
                            maker_session=maker_session,
                            affected_action=affected_action, run_dir=run_dir)
    if not verdict["ok"]:
        out.append({"error": verdict["reason_code"], "detail": verdict["detail"],
                    "review": verdict})
    return out


def inspect_legacy(document, kind=None):
    """Read an OLD record for inspection only; grants no production authority."""
    return {
        "production_authority": False,
        "inspection_only": True,
        "next_action": ("Legacy read only: this record is not admissible for new "
                        "generation without the production opening gate."),
        "document_sha256": digest(document) if isinstance(document, dict) else None,
        "kind": kind,
    }


def first_problem_class(problems_list):
    return problems_list[0]["error"] if problems_list else None
