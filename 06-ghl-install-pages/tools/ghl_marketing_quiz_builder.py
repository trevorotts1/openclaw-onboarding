#!/usr/bin/env python3
"""ghl_marketing_quiz_builder.py — Skill 06 STANDALONE MARKETING QUIZ builder.

WHY THIS EXISTS
---------------
Before this module the repository had NO executable standalone marketing quiz:
  * ``funnel-templates/lead/survey-quiz.{md,json}`` is a PAGE LAYOUT recipe, not a
    builder;
  * ``23-ai-workforce-blueprint/templates/role-library/quiz-builder/`` is a
    department ROLE, not a builder;
  * ``v2_dispatcher._resolve_builder_for_task`` silently mapped
    ``job_type='quiz'`` onto ``ghl_survey_builder.build_survey``, so a "quiz"
    became an ordinary survey with no scoring, no outcome rule, no result copy,
    no consent policy and no lead-capture verification;
  * no ``quiz`` ObjectRoute existed in ``ghl_object_router``.

This module supplies the missing thing: a MANAGED-BROWSER marketing quiz
coordinator with the same PLAN / EXECUTE / VERIFY separation as the form and
survey builders. It plans, scores, maps outcomes and verifies lead capture. It
does NOT re-implement the clicker: the native question/capture slides are built
by the existing managed survey builder (``ghl_survey_builder.build_survey``),
which remains the single managed rail. This module owns the quiz CONTRACT and
the verification; the click script stays in one place.

HARD RULES ENFORCED HERE (each a refusal, never a warning)
----------------------------------------------------------
1. **A marketing quiz is NOT a course lesson quiz** (B21 / Document 1 section
   30.4). The plan's rail/endpoint must be ``managed_browser`` and must not name
   a course-lesson-quiz endpoint. A course quiz endpoint here is refused before
   any plan is emitted.
2. **Every outcome must be reachable and boundaries must be exact.** Score
   ranges must be contiguous, non-overlapping and cover the whole reachable
   score band; every outcome is proven by at least one boundary answer set.
3. **Branching must terminate forward.** A branch may only jump to a LATER
   question; a backward/self jump is a loop and is refused at validation.
4. **Consent is part of the capture contract.** If contact capture is required,
   consent must be required, non-empty, and stored in its own field. A submission
   without consent is refused, never recorded as a lead.
5. **No unnecessary sensitive data.** Field keys/sources named like a government
   identifier, payment credential, health detail or password are refused.
6. **Page gates stay on** (IG-PAGE-01): wireframes (desktop+mobile), mockups
   (desktop+mobile), design-style intake (block/hybrid/circular), copy/prompt
   budgets, native full-width, populated SEO, and native (un-bypassed) checkout
   are all required before a build step is emitted.
7. **A synthetic fixture is never live proof.** ``verify_acceptance`` refuses a
   fixture whose ``trust`` is not ``FAKE`` and always returns ``live: false``.

Everything here is pure: no network, no browser, no GHL client, no login code.
``--selftest`` is fully offline.

CLI
---
    python3 ghl_marketing_quiz_builder.py --selftest
    python3 ghl_marketing_quiz_builder.py --validate <plan.json>
    python3 ghl_marketing_quiz_builder.py --survey-task <plan.json>
    python3 ghl_marketing_quiz_builder.py --steps <plan.json>
    python3 ghl_marketing_quiz_builder.py --fixture <plan.json> <fixture.json>
    python3 ghl_marketing_quiz_builder.py --cp01 <plan.json> <fixture.json>
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

PLAN_SCHEMA = "skill6-marketing-quiz-plan/1"
FIXTURE_SCHEMA = "skill6-marketing-quiz-fixture/1"
CP01_ID = "WF34-CP01"
BUILDER_VERSION = "v0.1.0"

#: The ONLY accepted rail. A standalone marketing quiz is a managed-browser
#: build; there is no verified public marketing-quiz contract yet.
ACCEPTED_RAIL = "managed_browser"

#: Markers that identify a COURSE LESSON QUIZ contract. Never a marketing quiz.
COURSE_QUIZ_MARKERS = (
    "courses/",
    "courses.",
    "course_quiz",
    "courses_quiz",
    "lesson_quiz",
    "lessons/quiz",
    "course_lesson",
)

QUESTION_TYPES = ("single_choice", "multi_choice", "short_text", "email", "consent")
SCORED_TYPES = ("single_choice", "multi_choice")

#: Plan question type -> native survey field type (ghl_survey_builder vocabulary).
FIELD_TYPE = {
    "single_choice": "Radio",
    "multi_choice": "Checkbox",
    "short_text": "Single Line",
    "email": "Email",
    "consent": "Checkbox",
}

DESIGN_STYLES = ("block", "hybrid", "circular")

PAGE_GATE_KEYS = (
    "wireframes",
    "mockups",
    "design_style_intake",
    "copy_budget",
    "native_full_width",
    "seo",
    "native_checkout",
)

SENSITIVE_MARKERS = (
    "ssn",
    "social_security",
    "social-security",
    "driver_license",
    "driver-license",
    "passport",
    "credit_card",
    "credit-card",
    "card_number",
    "card-number",
    "cvv",
    "cvc",
    "bank_account",
    "bank-account",
    "routing_number",
    "diagnosis",
    "medical_record",
    "password",
    "date_of_birth",
    "date-of-birth",
)

DEFAULT_OUTCOME_FIELD = "zhc_quiz_outcome"
DEFAULT_SCORE_FIELD = "zhc_quiz_score"
DEFAULT_CONSENT_FIELD = "zhc_quiz_consent"

SEO_TITLE_MAX = 60
SEO_DESC_MAX = 155

#: Selector file this builder is allowed to use. Dedicated to WF34.
SELECTORS_REL = os.path.join("tools", "selectors-live-marketing-quiz.json")


class QuizPlanInvalid(ValueError):
    """The plan does not satisfy the marketing-quiz contract (fail closed)."""


class CourseQuizEndpointRefused(QuizPlanInvalid):
    """A course/lesson quiz contract was offered where a marketing quiz is required."""


class PageGateIncomplete(QuizPlanInvalid):
    """A required page gate (wireframe/mockup/style/budget/full-width/SEO/checkout) is absent."""


class SensitiveFieldRefused(QuizPlanInvalid):
    """The plan would collect unnecessary sensitive information."""


class QuizAnswersIncomplete(QuizPlanInvalid):
    """A required question has no answer."""


class ConsentRequired(QuizPlanInvalid):
    """Lead capture was attempted without the required consent."""


class CaptureIncomplete(QuizPlanInvalid):
    """A required capture field is missing."""


class OutcomeContradiction(AssertionError):
    """The observed outcome/effect disagrees with the plan or the fixture."""


class FixtureNotSynthetic(ValueError):
    """A fixture that is not declared FAKE cannot be used as acceptance proof."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _s(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _as_int(value: Any, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise QuizPlanInvalid(f"{label} must be an integer score, got {value!r}")


def repo_root() -> str:
    """Skill 06 root (the directory that holds ``tools/``)."""
    return os.path.dirname(_TOOLS_DIR)


def selectors_path() -> str:
    return os.path.join(repo_root(), SELECTORS_REL)


def load_selectors(path: Optional[str] = None) -> dict:
    """Load the dedicated marketing-quiz selector map. Missing/!dict is a refusal."""
    target = path or selectors_path()
    try:
        with open(target, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise QuizPlanInvalid(f"marketing-quiz selector file is unusable: {target!r}: {exc}")
    if not isinstance(data, dict):
        raise QuizPlanInvalid(f"marketing-quiz selector file {target!r} is not an object")
    anchors = data.get("anchors")
    if not isinstance(anchors, list):
        # The shipped file groups anchors under objects.marketing_quiz.anchors;
        # flatten it so callers have ONE list to validate against.
        objects = data.get("objects")
        quiz = objects.get("marketing_quiz") if isinstance(objects, dict) else None
        anchors = quiz.get("anchors") if isinstance(quiz, dict) else None
    if not isinstance(anchors, list) or not anchors:
        raise QuizPlanInvalid(
            f"marketing-quiz selector file {target!r} has no anchors list "
            "(top-level or objects.marketing_quiz.anchors)")
    data = dict(data)
    data["anchors"] = anchors
    return data


# ---------------------------------------------------------------------------
# Plan normalization + validation
# ---------------------------------------------------------------------------
def _index_questions(plan: dict) -> Dict[str, Tuple[int, dict]]:
    return {_s(q.get("id")): (i, q) for i, q in enumerate(plan["questions"])}


def _refuse_course_quiz(plan: dict) -> None:
    """Rule 1 — never substitute a course lesson quiz for a marketing quiz."""
    transport = plan.get("transport") if isinstance(plan.get("transport"), dict) else {}
    declared = [
        _s(plan.get("rail")),
        _s(plan.get("endpoint")),
        _s(plan.get("operation_id")),
        _s(transport.get("endpoint")),
        _s(transport.get("operation_id")),
    ]
    for value in declared:
        low = value.lower()
        if not low:
            continue
        for marker in COURSE_QUIZ_MARKERS:
            if marker in low:
                raise CourseQuizEndpointRefused(
                    f"declared transport {value!r} is a COURSE QUIZ contract "
                    f"(matched {marker!r}). A standalone marketing quiz must use the "
                    f"managed-browser rail; course lesson quiz endpoints are never a "
                    "substitute (B21 / Document 1 section 30.4)."
                )
    rail = _s(plan.get("rail")).lower()
    if rail != ACCEPTED_RAIL:
        raise CourseQuizEndpointRefused(
            f"rail must be {ACCEPTED_RAIL!r} for a standalone marketing quiz, got "
            f"{rail or 'absent'!r}. No verified public marketing-quiz contract exists; "
            "do not claim one."
        )


def _refuse_sensitive(plan: dict) -> None:
    """Rule 5 — no unnecessary sensitive information."""
    names: List[str] = []
    cap = plan.get("capture") or {}
    for f in cap.get("fields", []) or []:
        if isinstance(f, dict):
            names.append(_s(f.get("field_key")))
            names.append(_s(f.get("source")))
    consent = cap.get("consent") or {}
    if isinstance(consent, dict):
        names.append(_s(consent.get("field_key")))
    mapping = plan.get("field_tag_mapping") or {}
    for f in mapping.get("custom_fields", []) or []:
        if isinstance(f, dict):
            names.append(_s(f.get("field_key")))
    for name in names:
        low = name.lower()
        for marker in SENSITIVE_MARKERS:
            if marker in low:
                raise SensitiveFieldRefused(
                    f"capture field {name!r} looks like sensitive data (matched {marker!r}); "
                    "a lead-generation quiz must not collect it."
                )


def _assert_page_gates(plan: dict) -> None:
    """Rule 6 — the page gates must all be present and satisfied (IG-PAGE-01)."""
    gates = plan.get("page_gates")
    if not isinstance(gates, dict):
        raise PageGateIncomplete(
            "page_gates block is missing; wireframes, mockups, design-style intake, "
            "copy/prompt budgets, native full-width, SEO and native checkout are "
            "required for every created page (IG-PAGE-01)"
        )
    missing = [k for k in PAGE_GATE_KEYS if k not in gates]
    if missing:
        raise PageGateIncomplete(f"page_gates is missing required gate(s): {missing}")

    for k in ("wireframes", "mockups"):
        block = gates.get(k)
        if not isinstance(block, dict) or not _s(block.get("desktop")) or not _s(block.get("mobile")):
            raise PageGateIncomplete(
                f"page_gates.{k} must name BOTH a desktop and a mobile artifact")

    style = gates.get("design_style_intake")
    if not isinstance(style, dict) or not style.get("approved"):
        raise PageGateIncomplete("page_gates.design_style_intake must be an approved block")
    if _s(style.get("style")).lower() not in DESIGN_STYLES:
        raise PageGateIncomplete(
            f"page_gates.design_style_intake.style must be one of {DESIGN_STYLES}, "
            f"got {style.get('style')!r}"
        )

    budget = gates.get("copy_budget")
    if not isinstance(budget, dict):
        raise PageGateIncomplete("page_gates.copy_budget must be an object of positive caps")
    for key in ("headline_max", "body_max", "image_prompt_max"):
        if _as_int(budget.get(key), f"page_gates.copy_budget.{key}") <= 0:
            raise PageGateIncomplete(f"page_gates.copy_budget.{key} must be a positive cap")

    if gates.get("native_full_width") is not True:
        raise PageGateIncomplete(
            "page_gates.native_full_width must be True — full-width CSS inside a code "
            "block is not a substitute for the builder/container setting"
        )

    seo = gates.get("seo")
    if not isinstance(seo, dict):
        raise PageGateIncomplete("page_gates.seo must be a populated block")
    title, desc = _s(seo.get("title")), _s(seo.get("description"))
    canonical = _s(seo.get("canonical"))
    if not title or len(title) > SEO_TITLE_MAX:
        raise PageGateIncomplete(f"page_gates.seo.title must be 1..{SEO_TITLE_MAX} chars")
    if not desc or len(desc) > SEO_DESC_MAX:
        raise PageGateIncomplete(f"page_gates.seo.description must be 1..{SEO_DESC_MAX} chars")
    if not canonical.startswith("https://"):
        raise PageGateIncomplete("page_gates.seo.canonical must be an https:// URL")

    checkout = gates.get("native_checkout")
    if not isinstance(checkout, dict) or checkout.get("bypassed"):
        raise PageGateIncomplete(
            "page_gates.native_checkout must show the native checkout path is used and "
            "NOT bypassed (no raw card fields)"
        )
    if _s(checkout.get("mode")).lower() != "native":
        raise PageGateIncomplete("page_gates.native_checkout.mode must be 'native'")


def _assert_questions(plan: dict) -> None:
    questions = plan.get("questions")
    if not isinstance(questions, list) or not questions:
        raise QuizPlanInvalid("plan.questions must be a non-empty list")

    seen_q: List[str] = []
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            raise QuizPlanInvalid(f"question #{i + 1} is not an object")
        qid = _s(q.get("id"))
        if not qid:
            raise QuizPlanInvalid(f"question #{i + 1} has no id")
        if qid in seen_q:
            raise QuizPlanInvalid(f"duplicate question id {qid!r}")
        seen_q.append(qid)
        if not _s(q.get("prompt")):
            raise QuizPlanInvalid(f"question {qid!r} has no prompt")
        qtype = _s(q.get("type")).lower()
        if qtype not in QUESTION_TYPES:
            raise QuizPlanInvalid(
                f"question {qid!r} type {qtype!r} must be one of {QUESTION_TYPES}")

        choices = q.get("choices")
        if qtype in SCORED_TYPES:
            if not isinstance(choices, list) or len(choices) < 2:
                raise QuizPlanInvalid(f"question {qid!r} ({qtype}) needs at least 2 choices")
            seen_c: List[str] = []
            for c in choices:
                if not isinstance(c, dict):
                    raise QuizPlanInvalid(f"question {qid!r} has a non-object choice")
                cid = _s(c.get("id"))
                if not cid:
                    raise QuizPlanInvalid(f"question {qid!r} has a choice without id")
                if cid in seen_c:
                    raise QuizPlanInvalid(f"question {qid!r} duplicate choice id {cid!r}")
                seen_c.append(cid)
                if not _s(c.get("label")):
                    raise QuizPlanInvalid(f"question {qid!r} choice {cid!r} has no label")
                _as_int(c.get("score", 0), f"question {qid!r} choice {cid!r} score")
        elif choices not in (None, []):
            raise QuizPlanInvalid(
                f"question {qid!r} type {qtype} must not carry scored choices; "
                "only single_choice/multi_choice are scored"
            )

    # Branching must terminate FORWARD (rule 3).
    index = {_s(q.get("id")): i for i, q in enumerate(questions)}
    for i, q in enumerate(questions):
        qid = _s(q.get("id"))
        branch = q.get("branch")
        if branch is None:
            continue
        if not isinstance(branch, dict):
            raise QuizPlanInvalid(f"question {qid!r} branch must be an object")
        when = _s(branch.get("when_choice"))
        goto = _s(branch.get("goto"))
        if not when or when not in [_s(c.get("id")) for c in q.get("choices", []) or []]:
            raise QuizPlanInvalid(
                f"question {qid!r} branch.when_choice {when!r} is not one of its choice ids"
            )
        if goto not in index:
            raise QuizPlanInvalid(f"question {qid!r} branch.goto {goto!r} is not a question id")
        if index[goto] <= i:
            raise QuizPlanInvalid(
                f"question {qid!r} branch.goto {goto!r} is not strictly forward "
                "(backward/self jumps loop forever)"
            )


def reachable_score_range(plan: dict) -> Tuple[int, int]:
    """(min,max) score reachable through the plan's branching (memoized DAG walk)."""
    questions = plan["questions"]
    index = {_s(q.get("id")): i for i, q in enumerate(questions)}
    memo: Dict[int, Tuple[int, int]] = {}

    def rng(i: int) -> Tuple[int, int]:
        if i >= len(questions):
            return (0, 0)
        if i in memo:
            return memo[i]
        lo: Optional[int] = None
        hi: Optional[int] = None
        q = questions[i]
        for choice in q.get("choices", []) or []:
            score = _as_int(choice.get("score", 0), "choice score")
            nxt = i + 1
            branch = q.get("branch") or {}
            if _s(branch.get("when_choice")) == _s(choice.get("id")):
                nxt = index[_s(branch.get("goto"))]
            sub_lo, sub_hi = rng(nxt)
            cand_lo, cand_hi = score + sub_lo, score + sub_hi
            lo = cand_lo if lo is None else min(lo, cand_lo)
            hi = cand_hi if hi is None else max(hi, cand_hi)
        if lo is None:  # a question with no choices contributes nothing
            lo, hi = rng(i + 1)
        memo[i] = (lo, hi)
        return memo[i]

    return rng(0)


def _assert_outcomes(plan: dict) -> Tuple[int, int]:
    """Validate outcomes; return the reachable (min,max) score band it must cover."""
    outcomes = plan.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        raise QuizPlanInvalid("plan.outcomes must be a non-empty list")

    seen: List[str] = []
    for o in outcomes:
        if not isinstance(o, dict):
            raise QuizPlanInvalid("outcome entries must be objects")
        key = _s(o.get("key"))
        if not key:
            raise QuizPlanInvalid("an outcome has no key")
        if key in seen:
            raise QuizPlanInvalid(f"duplicate outcome key {key!r}")
        seen.append(key)
        if not _s(o.get("title")):
            raise QuizPlanInvalid(f"outcome {key!r} has no title")
        if not _s(o.get("result_copy")):
            raise QuizPlanInvalid(f"outcome {key!r} has no result_copy")
        lo = _as_int(o.get("score_min"), f"outcome {key!r} score_min")
        hi = _as_int(o.get("score_max"), f"outcome {key!r} score_max")
        if hi < lo:
            raise QuizPlanInvalid(f"outcome {key!r} score_max {hi} < score_min {lo}")

    band = reachable_score_range(plan)
    ordered = sorted((_as_int(o["score_min"], "score_min"),
                      _as_int(o["score_max"], "score_max"), _s(o["key"]))
                     for o in outcomes)
    cursor = band[0]
    for lo, hi, key in ordered:
        if lo != cursor:
            if lo < cursor:
                raise QuizPlanInvalid(
                    f"outcome {key!r} overlaps a previous outcome at score {lo} "
                    f"(coverage cursor {cursor})"
                )
            raise QuizPlanInvalid(
                f"score gap {cursor}..{lo - 1} is not covered by any outcome "
                f"(next outcome {key!r} starts at {lo})"
            )
        cursor = hi + 1
    if cursor - 1 != band[1]:
        raise QuizPlanInvalid(
            f"outcome score ranges end at {cursor - 1} but the reachable maximum is "
            f"{band[1]} — an outcome boundary is unreachable or uncovered"
        )

    routers: List[Tuple[str, str, str]] = []
    indexed = _index_questions(plan)
    for o in outcomes:
        router = o.get("router")
        if router is None:
            continue
        key = _s(o.get("key"))
        if not isinstance(router, dict):
            raise QuizPlanInvalid(f"outcome {key!r} router must be an object")
        qid, cid = _s(router.get("question_id")), _s(router.get("choice_id"))
        if qid not in indexed:
            raise QuizPlanInvalid(f"outcome {key!r} router.question_id {qid!r} unknown")
        q = indexed[qid][1]
        if cid not in [_s(c.get("id")) for c in q.get("choices", []) or []]:
            raise QuizPlanInvalid(
                f"outcome {key!r} router.choice_id {cid!r} is not a choice of {qid!r}"
            )
        for other_q, other_c, other_key in routers:
            if (other_q, other_c) == (qid, cid):
                raise QuizPlanInvalid(
                    f"outcomes {other_key!r} and {key!r} both route on "
                    f"{qid}/{cid} — ambiguous routing"
                )
        routers.append((qid, cid, key))

    return band


def capture_policy(plan: dict) -> dict:
    """The normalized contact-capture + consent policy (never inferred)."""
    cap = plan.get("capture") or {}
    consent = cap.get("consent") or {}
    fields: List[dict] = []
    for f in cap.get("fields", []) or []:
        if not isinstance(f, dict):
            continue
        fields.append({
            "field_key": _s(f.get("field_key")),
            "source": _s(f.get("source")) or _s(f.get("field_key")),
            "required": bool(f.get("required", True)),
        })
    return {
        "required": bool(cap.get("required", False)),
        "fields": fields,
        "consent_required": bool(consent.get("required", False)),
        "consent_text": _s(consent.get("text")),
        "consent_field_key": _s(consent.get("field_key")) or DEFAULT_CONSENT_FIELD,
    }


def normalize_plan(plan: dict) -> dict:
    """Validate and return a canonical deep copy. Raises on any contract breach."""
    if not isinstance(plan, dict):
        raise QuizPlanInvalid("plan must be a JSON object")
    if _s(plan.get("schema")) != PLAN_SCHEMA:
        raise QuizPlanInvalid(
            f"plan.schema must be {PLAN_SCHEMA!r}, got {plan.get('schema')!r}")

    normalized = copy.deepcopy(plan)
    normalized.setdefault("questions", [])
    normalized.setdefault("outcomes", [])
    normalized.setdefault("capture", {})
    normalized.setdefault("field_tag_mapping", {})
    normalized.setdefault("followup_workflows", [])

    _refuse_course_quiz(normalized)
    _refuse_sensitive(normalized)
    _assert_page_gates(normalized)
    _assert_questions(normalized)
    _assert_outcomes(normalized)

    if not _s(normalized.get("quiz_name")):
        raise QuizPlanInvalid("plan.quiz_name is required")
    if not _s(normalized.get("location_id")):
        raise QuizPlanInvalid("plan.location_id is required (the approved build location)")

    policy = capture_policy(normalized)
    if policy["required"] and not policy["consent_required"]:
        raise QuizPlanInvalid(
            "capture.required is true so consent.required must be true (never capture a "
            "lead without the consent the plan promises)"
        )
    if policy["consent_required"] and not policy["consent_text"]:
        raise QuizPlanInvalid(
            "capture.consent.text must be non-empty when consent is required")

    keys = [f["field_key"] for f in policy["fields"]]
    if len(set(keys)) != len(keys):
        raise QuizPlanInvalid(f"capture.fields has duplicate field_key(s): {keys}")
    for key in keys:
        if not key.startswith("zhc_"):
            raise QuizPlanInvalid(
                f"capture field_key {key!r} must use the idempotent 'zhc_' prefix "
                "(the same key Skill 44 creates; never a second field for the same label)"
            )

    mapping = normalized["field_tag_mapping"]
    for f in mapping.get("custom_fields", []) or []:
        key = _s(f.get("field_key")) if isinstance(f, dict) else ""
        if key and not key.startswith("zhc_"):
            raise QuizPlanInvalid(f"field_tag_mapping custom field {key!r} needs 'zhc_'")
    for t in mapping.get("tags", []) or []:
        name = _s(t.get("tag") if isinstance(t, dict) else t)
        if name and not name.startswith("zhc_"):
            raise QuizPlanInvalid(f"field_tag_mapping tag {name!r} needs 'zhc_'")

    outcome_keys = {_s(o.get("key")) for o in normalized["outcomes"]}
    seen_wf: List[str] = []
    for wf in normalized["followup_workflows"]:
        if not isinstance(wf, dict):
            raise QuizPlanInvalid("followup_workflows entries must be objects")
        key = _s(wf.get("key"))
        if not key:
            raise QuizPlanInvalid("a followup workflow has no key")
        if key in seen_wf:
            raise QuizPlanInvalid(f"duplicate followup workflow key {key!r}")
        seen_wf.append(key)
        if _s(wf.get("outcome")) not in outcome_keys:
            raise QuizPlanInvalid(
                f"followup workflow {key!r} names unknown outcome {wf.get('outcome')!r}"
            )
        if wf.get("approved") is not True:
            raise QuizPlanInvalid(
                f"followup workflow {key!r} is not approved — only an approved follow-up "
                "may be planned (never a speculative automation)"
            )

    return normalized


# ---------------------------------------------------------------------------
# Outcome mapping + scoring (the deterministic contract)
# ---------------------------------------------------------------------------
def _max_remaining(plan: dict, start: int) -> int:
    """Highest additional score obtainable from question index ``start`` onward."""
    questions = plan["questions"]
    index = {_s(q.get("id")): i for i, q in enumerate(questions)}
    memo: Dict[int, int] = {}

    def best(i: int) -> int:
        if i >= len(questions):
            return 0
        if i in memo:
            return memo[i]
        q = questions[i]
        candidates: List[int] = []
        for choice in q.get("choices", []) or []:
            score = _as_int(choice.get("score", 0), "choice score")
            nxt = i + 1
            branch = q.get("branch") or {}
            if _s(branch.get("when_choice")) == _s(choice.get("id")):
                nxt = index[_s(branch.get("goto"))]
            candidates.append(score + best(nxt))
        memo[i] = max(candidates) if candidates else best(i + 1)
        return memo[i]

    return best(start)


def _answers_for_score(plan: dict, target: int,
                       outcome_key: Optional[str] = None) -> Dict[str, Any]:
    """An answer set scoring ``target`` AND resolving to ``outcome_key``.

    A plain greedy walk is not enough because a router answer can override the
    score band (outcome selection is router-first). This does a bounded depth-first
    search over the branch DAG, pruning on the reachable maximum, and accepts only
    a path whose real ``select_outcome`` result is the requested outcome. If no
    such path exists the plan's boundary is genuinely unreachable and we raise.
    """
    questions = plan["questions"]
    index = {_s(q.get("id")): i for i, q in enumerate(questions)}
    budget = [40000]

    def walk(i: int, remaining: int, answers: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        budget[0] -= 1
        if budget[0] < 0:
            return None
        if i >= len(questions):
            if remaining != 0:
                return None
            if outcome_key is None:
                return dict(answers)
            outcome = select_outcome(plan, answers, target)
            return dict(answers) if _s(outcome.get("key")) == outcome_key else None

        q = questions[i]
        qid = _s(q.get("id"))
        qtype = _s(q.get("type")).lower()
        choices = q.get("choices", []) or []
        if qtype not in SCORED_TYPES or not choices:
            nxt_answers = dict(answers)
            if qtype == "consent":
                nxt_answers[qid] = True
            elif qtype == "email":
                nxt_answers[qid] = "synthetic-fixture@example.test"
            else:
                nxt_answers[qid] = "synthetic"
            return walk(i + 1, remaining, nxt_answers)

        for choice in sorted(choices, key=lambda c: _as_int(c.get("score", 0), "score")):
            score = _as_int(choice.get("score", 0), "score")
            left = remaining - score
            if left < 0:
                break  # sorted ascending: every later choice is worse
            nxt = i + 1
            branch = q.get("branch") or {}
            if _s(branch.get("when_choice")) == _s(choice.get("id")):
                nxt = index[_s(branch.get("goto"))]
            if left > _max_remaining(plan, nxt):
                continue
            nxt_answers = dict(answers)
            nxt_answers[qid] = _s(choice.get("id"))
            found = walk(nxt, left, nxt_answers)
            if found is not None:
                return found
        return None

    found = walk(0, target, {})
    if found is None:
        raise OutcomeContradiction(
            f"no answer path reaches score {target} with outcome {outcome_key!r} "
            "(this boundary is unreachable)")
    return found


def _chosen(question: dict, answer: Any) -> List[str]:
    """Normalize an answer into a list of chosen choice ids."""
    valid = [_s(c.get("id")) for c in question.get("choices", []) or []]
    qtype = _s(question.get("type")).lower()
    if qtype not in SCORED_TYPES or not valid:
        # Free-text / email / consent answers are not choice ids; presence is the
        # only thing that matters and it is checked by the caller.
        return []
    if qtype == "multi_choice":
        if isinstance(answer, (list, tuple)):
            chosen = [_s(a) for a in answer]
        elif isinstance(answer, str) and "," in answer:
            chosen = [_s(a) for a in answer.split(",")]
        elif answer in (None, ""):
            chosen = []
        else:
            chosen = [_s(answer)]
        for c in chosen:
            if c and c not in valid:
                raise QuizPlanInvalid(
                    f"question {_s(question.get('id'))!r} answer {c!r} is not a choice id"
                )
        return [c for c in chosen if c]
    if answer in (None, ""):
        return []
    got = _s(answer)
    if got not in valid:
        raise QuizPlanInvalid(
            f"question {_s(question.get('id'))!r} answer {got!r} is not a choice id"
        )
    return [got]


def score_answers(plan: dict, answers: Dict[str, Any]) -> dict:
    """Walk the plan with an answer set -> score, outcome, path and skipped questions."""
    p = normalize_plan(plan)
    questions = p["questions"]
    index = {_s(q.get("id")): i for i, q in enumerate(questions)}
    if not isinstance(answers, dict):
        raise QuizPlanInvalid("answers must be an object of {question_id: answer}")

    score = 0
    path: List[str] = []
    skipped: List[str] = []
    by_question: Dict[str, List[str]] = {}
    i = 0
    guard = 0
    while i < len(questions):
        guard += 1
        if guard > len(questions) * 4:
            raise QuizPlanInvalid("answer walk did not terminate (branch loop)")
        q = questions[i]
        qid = _s(q.get("id"))
        required = bool(q.get("required", True))
        if qid not in answers or answers[qid] in (None, "", []):
            if required:
                raise QuizAnswersIncomplete(f"required question {qid!r} has no answer")
            skipped.append(qid)
            i += 1
            continue
        chosen = _chosen(q, answers[qid])
        if _s(q.get("type")).lower() in SCORED_TYPES:
            score_map = {_s(c.get("id")): _as_int(c.get("score", 0), "score")
                         for c in q.get("choices", []) or []}
            score += sum(score_map.get(c, 0) for c in chosen)
        by_question[qid] = chosen
        path.append(qid)
        branch = q.get("branch") or {}
        if branch and _s(branch.get("when_choice")) in chosen:
            i = index[_s(branch.get("goto"))]
        else:
            i += 1

    outcome = select_outcome(p, answers, score)
    return {
        "score": score,
        "outcome": _s(outcome.get("key")),
        "outcome_title": _s(outcome.get("title")),
        "result_copy": _s(outcome.get("result_copy")),
        "path": path,
        "skipped": skipped,
        "score_by_question": by_question,
    }


def select_outcome(plan: dict, answers: Dict[str, Any], score: int) -> dict:
    """Router answers win; otherwise the contiguous score band decides."""
    for outcome in plan["outcomes"]:
        router = outcome.get("router")
        if not isinstance(router, dict):
            continue
        qid, cid = _s(router.get("question_id")), _s(router.get("choice_id"))
        raw = answers.get(qid)
        chosen = [raw] if not isinstance(raw, (list, tuple)) else list(raw)
        if cid and cid in [_s(c) for c in chosen]:
            return outcome
    for outcome in plan["outcomes"]:
        lo = _as_int(outcome["score_min"], "score_min")
        hi = _as_int(outcome["score_max"], "score_max")
        if lo <= score <= hi:
            return outcome
    raise OutcomeContradiction(
        f"score {score} matches no outcome (validation should prevent this)")


def outcome_boundaries(plan: dict) -> List[dict]:
    """Every outcome with a concrete answer set landing exactly on each edge.

    The returned sets are the PROOF that a boundary is reachable: each one is
    scored through the real scoring path, so a boundary that cannot be produced
    is surfaced here rather than discovered live.
    """
    p = normalize_plan(plan)
    rows: List[dict] = []
    for outcome in sorted(p["outcomes"], key=lambda o: _as_int(o["score_min"], "score_min")):
        lo = _as_int(outcome["score_min"], "score_min")
        hi = _as_int(outcome["score_max"], "score_max")
        for label, target in (("min", lo), ("max", hi)):
            answers = _answers_for_score(p, target, _s(outcome.get("key")))
            got = score_answers(p, answers)
            if got["score"] != target or got["outcome"] != _s(outcome["key"]):
                raise OutcomeContradiction(
                    f"outcome {outcome['key']!r} {label} boundary {target} is NOT reachable: "
                    f"answers scored {got['score']} -> {got['outcome']!r}"
                )
            rows.append({
                "outcome": _s(outcome["key"]),
                "boundary": label,
                "score": target,
                "answers": answers,
            })
    return rows


# ---------------------------------------------------------------------------
# Lead capture + routing (the CRM half of the contract)
# ---------------------------------------------------------------------------
def compute_lead_effects(plan: dict, submission: dict) -> dict:
    """What one submission must do to the CRM. Refuses an unconsented lead."""
    p = normalize_plan(plan)
    scored = score_answers(p, submission.get("answers") or {})
    policy = capture_policy(p)
    consent_given = bool(submission.get("consent", False))

    if policy["consent_required"] and not consent_given:
        raise ConsentRequired(
            "submission has no consent but capture.consent.required is true — "
            "never record an unconsented lead"
        )
    if policy["required"] and not submission.get("capture"):
        raise CaptureIncomplete(
            "capture.required is true but the submission carries no capture values")

    captured = submission.get("capture") or {}
    if not isinstance(captured, dict):
        raise CaptureIncomplete("submission.capture must be an object")

    fields: Dict[str, Any] = {}
    for field in policy["fields"]:
        key = field["field_key"]
        value = captured.get(key, captured.get(field["source"]))
        if value in (None, ""):
            if field["required"]:
                raise CaptureIncomplete(f"required capture field {key!r} has no value")
            continue
        fields[key] = value
    if policy["consent_required"]:
        fields[policy["consent_field_key"]] = True

    mapping = p["field_tag_mapping"]
    outcome_field = _s(mapping.get("outcome_field_key")) or DEFAULT_OUTCOME_FIELD
    score_field = _s(mapping.get("score_field_key")) or DEFAULT_SCORE_FIELD
    fields[outcome_field] = scored["outcome"]
    fields[score_field] = scored["score"]

    outcome_row = next(o for o in p["outcomes"] if _s(o.get("key")) == scored["outcome"])
    tags: List[str] = []
    for t in mapping.get("tags", []) or []:
        name = _s(t.get("tag") if isinstance(t, dict) else t)
        if name:
            tags.append(name)
    for t in outcome_row.get("tags", []) or []:
        name = _s(t)
        if name and name not in tags:
            tags.append(name)

    known = {_s(wf.get("key")) for wf in p["followup_workflows"]}
    workflows: List[str] = [
        _s(wf.get("key")) for wf in p["followup_workflows"]
        if _s(wf.get("outcome")) == scored["outcome"]
    ]
    for extra in outcome_row.get("followup_workflows", []) or []:
        key = _s(extra)
        if key and key not in workflows:
            workflows.append(key)
    unknown = [w for w in workflows if w not in known]
    if unknown:
        raise QuizPlanInvalid(
            f"outcome {scored['outcome']!r} names unapproved follow-up workflow(s) {unknown}"
        )

    email = (captured.get("Email") or captured.get("email")
             or next((v for k, v in fields.items() if "email" in k.lower()), None))
    result_page = outcome_row.get("result_page")
    return {
        "contact": {"email": email},
        "fields": fields,
        "tags": tags,
        "workflows": workflows,
        "consent": {"given": consent_given, "field_key": policy["consent_field_key"]},
        "score": scored["score"],
        "outcome": scored["outcome"],
        "result_copy": scored["result_copy"],
        "result_page": _s(result_page.get("path")) if isinstance(result_page, dict) else "",
    }


def apply_submission_to_crm(crm: dict, effects: dict) -> dict:
    """Pure fake-CRM reducer: one contact with its fields, tags and enrollments."""
    state = copy.deepcopy(crm if isinstance(crm, dict) else {})
    state.setdefault("contacts", [])
    state.setdefault("fields", [])
    state.setdefault("tags", [])
    state.setdefault("enrollments", [])

    contact_id = f"CT_{len(state['contacts']) + 1}"
    contact = {
        "id": contact_id,
        "email": effects["contact"].get("email") or "",
        "fields": dict(effects["fields"]),
        "tags": list(effects["tags"]),
    }
    state["contacts"].append(contact)
    for key in effects["fields"]:
        if key not in state["fields"]:
            state["fields"].append(key)
    for tag in effects["tags"]:
        if tag not in state["tags"]:
            state["tags"].append(tag)
    for wf in effects["workflows"]:
        state["enrollments"].append({"contact_id": contact_id, "workflow": wf})
    return state


# ---------------------------------------------------------------------------
# EXECUTE translation — the managed survey builder does the clicking
# ---------------------------------------------------------------------------
def _short(text: str, limit: int = 44) -> str:
    text = _s(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def slide_name_for(plan: dict, question_id: str) -> str:
    """Stable ``Q{n} {prompt}`` slide name for a question (used by branch targets)."""
    index = {_s(q.get("id")): i for i, q in enumerate(plan["questions"])}
    i = index[question_id]
    return f"Q{i + 1} {_short(plan['questions'][i].get('prompt', ''))}"


def to_survey_task(plan: dict, *, business_name: str = "[BUSINESS NAME]",
                   campaign: str = "") -> dict:
    """Translate the quiz plan into a ``ghl_survey_builder`` task payload.

    The survey builder owns the clicker; this function owns the translation and
    refuses to lose anything: every question becomes a slide field, every branch
    becomes a conditional-logic rule, and every branch re-converges on the capture
    slide so a branch can never fall through into a sibling's required fields.
    """
    p = normalize_plan(plan)
    fields: List[dict] = []
    slides: List[dict] = []
    for i, q in enumerate(p["questions"]):
        qid = _s(q.get("id"))
        field = {
            "key": _s(q.get("field_key")) or f"zhc_quiz_q{i + 1}",
            "label": _s(q.get("prompt")),
            "type": FIELD_TYPE[_s(q.get("type")).lower()],
            "required": bool(q.get("required", True)),
            "slide_name": slide_name_for(p, qid),
        }
        fields.append(field)
        slides.append({"name": field["slide_name"], "fields": [field["label"]]})

    rules: List[dict] = []
    for q in p["questions"]:
        branch = q.get("branch")
        if not branch:
            continue
        when = _s(branch.get("when_choice"))
        label = next((_s(c.get("label")) for c in q.get("choices", []) or []
                      if _s(c.get("id")) == when), when)
        rules.append({
            "if_field": _s(q.get("prompt")),
            "if_value": label,
            "then_slide": slide_name_for(p, _s(branch.get("goto"))),
            "kind": "quiz_branch",
        })

    policy = capture_policy(p)
    return {
        "job_type": "quiz",
        "build_type": "marketing_quiz",
        "rail": ACCEPTED_RAIL,
        "location_id": _s(p.get("location_id")),
        "survey_name": _s(p.get("quiz_name")),
        "quiz_name": _s(p.get("quiz_name")),
        "business_name": business_name,
        "campaign": campaign or _s(p.get("quiz_name")),
        "survey_fields": fields,
        "slides": slides,
        "conditional_logic": rules,
        # Branches re-join the tail at the capture slide — the survey builder
        # derives one forward convergence jump per branch from this.
        "converge_slide": "Contact Capture",
        "capture_required": policy["required"],
        "capture_consent": {
            "required": policy["consent_required"],
            "text": policy["consent_text"],
            "field_key": policy["consent_field_key"],
        },
        "tag_attachment": "workflow",
        "field_creation": "api",
        "dependent_fields": [f["key"] for f in fields],
        "note": ("Native question/capture slides are built by ghl_survey_builder. "
                 "Scoring/outcome mapping is the marketing-quiz coordinator's contract; "
                 "GHL surveys do not compute a weighted score natively, so outcome and "
                 "score are persisted as custom fields and routed by workflow."),
    }


def dependency_plan(plan: dict,
                    existing_field_keys: Optional[List[str]] = None,
                    existing_tags: Optional[List[str]] = None) -> dict:
    """Skill 44 create/reuse plan for the quiz's fields and tags (never duplicates)."""
    p = normalize_plan(plan)
    have_fields = {_s(k).lower() for k in (existing_field_keys or [])}
    have_tags = {_s(k).lower() for k in (existing_tags or [])}

    policy = capture_policy(p)
    mapping = p["field_tag_mapping"]
    field_keys: List[str] = [_s(q.get("field_key")) for q in p["questions"]]
    field_keys += [f["field_key"] for f in policy["fields"]]
    field_keys.append(_s(mapping.get("outcome_field_key")) or DEFAULT_OUTCOME_FIELD)
    field_keys.append(_s(mapping.get("score_field_key")) or DEFAULT_SCORE_FIELD)
    if policy["consent_required"]:
        field_keys.append(policy["consent_field_key"])
    for f in mapping.get("custom_fields", []) or []:
        field_keys.append(_s(f.get("field_key")) if isinstance(f, dict) else "")

    seen: List[str] = []
    for key in field_keys:
        if not key:
            continue
        if not key.startswith("zhc_"):
            raise QuizPlanInvalid(f"dependent field key {key!r} must use the 'zhc_' prefix")
        if key not in seen:
            seen.append(key)

    tags: List[str] = []
    for t in mapping.get("tags", []) or []:
        name = _s(t.get("tag") if isinstance(t, dict) else t)
        if name and name not in tags:
            tags.append(name)
    for o in p["outcomes"]:
        for t in o.get("tags", []) or []:
            name = _s(t)
            if name and name not in tags:
                tags.append(name)

    return {
        "schema_version": "1.0",
        "generated_at": _ts(),
        "owner_skill": "44-convert-and-flow-operator",
        "idempotency": {
            "live_get_required": not (existing_field_keys or existing_tags),
            "rule": "GET existing custom fields + tags; REUSE any matching zhc_ key; "
                    "only CREATE the remainder. Never duplicate.",
        },
        "custom_fields": [
            {"field_key": key, "action": "reuse" if key.lower() in have_fields else "create"}
            for key in seen
        ],
        "tags": [
            {"tag": tag, "action": "reuse" if tag.lower() in have_tags else "create"}
            for tag in tags
        ],
        "tag_attachment": {
            "method": "workflow",
            "owner_skill": "44-convert-and-flow-operator",
            "trigger": "Quiz submitted (native survey)",
            "action": "Add Contact Tag",
            "tags": tags,
            "note": ("Built AFTER the native quiz id exists; a native survey has no "
                     "'add tag' setting."),
        },
    }


# ---------------------------------------------------------------------------
# EXECUTE step plan (managed browser), every selector resolved from the file
# ---------------------------------------------------------------------------
STEP_DEFS: List[Tuple[str, str, str, str, str]] = [
    ("open_quiz_list", "Open the Sites -> Surveys list for the approved location",
     "OPEN_LIST", "quiz.nav.surveys_link",
     "route contains /survey-builder/main and the location id matches the plan"),
    ("create_scratch", "Add survey -> Start from Scratch -> Create",
     "CREATE_SCRATCH", "quiz.list.add_survey",
     "builder route contains /survey-builder-v2/<id>"),
    ("rename_quiz", "Rename the native object to the plan's quiz_name",
     "RENAME", "quiz.builder.title",
     "read-back shows exactly the planned quiz_name"),
    ("build_questions", "Place and rename one question slide per planned question",
     "DELEGATE_SURVEY_BUILDER", "quiz.builder.add_slide",
     "slide count and every question label match the plan"),
    ("build_branching", "Wire each planned branch as a Jump-To rule",
     "DELEGATE_SURVEY_BUILDER", "quiz.builder.conditional_logic",
     "every branch target resolves; no branch falls into a sibling"),
    ("capture_and_consent", "Add the capture slide with the consent checkbox",
     "DELEGATE_SURVEY_BUILDER", "quiz.builder.capture_slide",
     "consent checkbox present and required when the policy requires it"),
    ("save_and_capture_id", "Save, then capture the native quiz id/URL",
     "CAPTURE_ID", "quiz.builder.save",
     "native id captured and persisted; nothing left with the default name"),
    ("result_pages", "Create one result page per outcome with its result copy",
     "DELEGATE_PAGE_BUILDER", "quiz.result.page_copy",
     "each outcome's result copy renders on its own page"),
    ("field_tag_workflows", "Create/reuse fields and tags, then the approved follow-ups",
     "DELEGATE_SKILL_44", "quiz.integrate.tags",
     "every dependent field/tag has a proven create/reuse result"),
    ("render_gates", "Hydrated-DOM, console, full-width and mobile checks",
     "VERIFY_RENDER", "quiz.verify.preview",
     "desktop + mobile render pass with zero console errors"),
    ("lead_capture", "Submit a synthetic contact and verify the CRM effect",
     "VERIFY_LEAD_CAPTURE", "quiz.verify.submit",
     "one contact with the mapped fields/tags and only the intended workflow"),
]

MUTATING_MODES = (
    "CREATE_SCRATCH",
    "RENAME",
    "CAPTURE_ID",
    "DELEGATE_SURVEY_BUILDER",
    "DELEGATE_PAGE_BUILDER",
    "DELEGATE_SKILL_44",
)


def build_step_plan(plan: dict, selectors: Optional[dict] = None) -> dict:
    """The ordered EXECUTE plan. Refuses an unknown selector id (fail closed)."""
    p = normalize_plan(plan)
    sel = selectors or load_selectors()
    known = {_s(a.get("id")) for a in sel["anchors"]}
    missing = sorted({d[3] for d in STEP_DEFS if d[3] not in known})
    if missing:
        raise QuizPlanInvalid(
            f"dedicated marketing-quiz selector file is missing anchor id(s): {missing}"
        )

    steps: List[dict] = []
    for idx, (step_id, action, mode, anchor, verify) in enumerate(STEP_DEFS, 1):
        steps.append({
            "step": idx,
            "id": step_id,
            "action": action,
            "mode": mode,
            "selector": anchor,
            "verify": verify,
            "network_mutation": mode in MUTATING_MODES,
        })

    return {
        "schema": "skill6-marketing-quiz-steps/1",
        "generated_at": _ts(),
        "builder_version": BUILDER_VERSION,
        "rail": ACCEPTED_RAIL,
        "quiz_name": _s(p.get("quiz_name")),
        "location_id": _s(p.get("location_id")),
        "selector_file": os.path.relpath(selectors_path(), repo_root()),
        "selector_file_version": _s(sel.get("version")),
        "steps": steps,
        "survey_task": to_survey_task(p),
        "dependency_plan": dependency_plan(p),
        "note": ("Steps 4-6 delegate to ghl_survey_builder (the single managed clicker); "
                 "step 8 delegates to the page builder; step 9 to Skill 44. This lane owns "
                 "the contract, the selectors and the verification, never a second clicker."),
    }


# ---------------------------------------------------------------------------
# VERIFY — outcome boundaries + lead capture against a FAKE browser/CRM fixture
# ---------------------------------------------------------------------------
def verify_acceptance(plan: dict, fixture: dict) -> dict:
    """Prove the quiz contract end-to-end against a synthetic fixture.

    Always returns ``live: false``. A fixture that does not declare ``trust:
    FAKE`` is refused: a fake result may never be reported as live proof.
    """
    p = normalize_plan(plan)
    if not isinstance(fixture, dict):
        raise FixtureNotSynthetic("fixture must be a JSON object")
    if _s(fixture.get("schema")) != FIXTURE_SCHEMA:
        raise FixtureNotSynthetic(f"fixture.schema must be {FIXTURE_SCHEMA!r}")
    if _s(fixture.get("trust")).upper() != "FAKE":
        raise FixtureNotSynthetic(
            f"fixture.trust must be 'FAKE' (got {fixture.get('trust')!r}); a non-fake "
            "fixture cannot be used as offline acceptance proof"
        )

    problems: List[str] = []
    checks: List[str] = []
    outcome_keys = [_s(o.get("key")) for o in p["outcomes"]]

    # 1. every outcome is reachable at both boundaries (plan-only proof)
    boundaries = outcome_boundaries(p)
    checks.append("outcome_boundaries_reachable")

    # 2. every outcome appears in the fixture's submissions and matches
    crm = copy.deepcopy(fixture.get("crm") or {})
    seen_outcomes: List[str] = []
    capture_failed = False
    for sub in fixture.get("submissions", []) or []:
        label = _s(sub.get("name")) or "submission"
        expected = _s(sub.get("expected_outcome"))
        if expected not in outcome_keys:
            problems.append(f"{label}: expected_outcome {expected!r} is not a plan outcome")
            continue
        got = score_answers(p, sub.get("answers") or {})
        if got["outcome"] != expected:
            problems.append(
                f"{label}: scored outcome {got['outcome']!r} != expected {expected!r}")
            continue
        seen_outcomes.append(expected)
        try:
            effects = compute_lead_effects(p, sub)
        except QuizPlanInvalid as exc:
            capture_failed = True
            problems.append(f"{label}: lead capture refused: {exc}")
            continue
        expected_effect = sub.get("expected_effect")
        if isinstance(expected_effect, dict):
            for key in ("tags", "workflows"):
                if key in expected_effect and list(expected_effect[key]) != effects[key]:
                    problems.append(
                        f"{label}: {key} {effects[key]!r} != fixture expected "
                        f"{list(expected_effect[key])!r}"
                    )
            for fk, fv in (expected_effect.get("fields") or {}).items():
                if effects["fields"].get(fk) != fv:
                    problems.append(
                        f"{label}: field {fk!r}={effects['fields'].get(fk)!r} != "
                        f"fixture expected {fv!r}"
                    )
        before = len(crm.get("contacts", []) or [])
        crm = apply_submission_to_crm(crm, effects)
        if len(crm["contacts"]) != before + 1:
            problems.append(f"{label}: exactly one contact should be created")
        contact = crm["contacts"][-1]
        if not contact["email"]:
            problems.append(f"{label}: the created contact has no email (lead not routable)")
        allowed = {_s(w.get("key")) for w in p["followup_workflows"]
                   if _s(w.get("outcome")) == expected}
        for wf in effects["workflows"]:
            if wf not in allowed:
                problems.append(f"{label}: workflow {wf!r} is not approved for {expected!r}")

    for key in outcome_keys:
        if key not in seen_outcomes:
            problems.append(f"outcome {key!r} has no passing fixture submission")
    if not problems:
        checks.append("every_outcome_verified")
        checks.append("lead_capture_and_routing_verified")

    # 3. branch coverage: each declared branch must be exercised by some submission
    branches = [_s(q.get("id")) for q in p["questions"] if q.get("branch")]
    branch_problems: List[str] = []
    for qid in branches:
        q = next(x for x in p["questions"] if _s(x.get("id")) == qid)
        choice = _s((q.get("branch") or {}).get("when_choice"))
        goto = _s((q.get("branch") or {}).get("goto"))
        hit = False
        for sub in fixture.get("submissions", []) or []:
            answers = sub.get("answers") or {}
            chosen = answers.get(qid)
            chosen_list = [_s(c) for c in
                           (chosen if isinstance(chosen, (list, tuple)) else [chosen])]
            if choice in chosen_list:
                hit = True
                break
        if not hit:
            branch_problems.append(
                f"branch {qid}/{choice} -> {goto} is never exercised by the fixture")
    problems.extend(branch_problems)
    if branches and not branch_problems:
        checks.append("branch_paths_verified")

    # 4. render + result-copy gates (the fake browser half)
    browser = fixture.get("browser") or {}
    render = browser.get("render") or {}
    render_problems: List[str] = []
    for viewport in ("desktop", "mobile"):
        row = render.get(viewport)
        if not isinstance(row, dict):
            render_problems.append(f"browser.render.{viewport} is missing")
            continue
        if row.get("hydrated_dom") is not True:
            render_problems.append(f"browser.render.{viewport}.hydrated_dom is not true")
        if row.get("native_full_width") is not True:
            render_problems.append(
                f"browser.render.{viewport}.native_full_width is not true")
        errors = row.get("console_errors")
        if not isinstance(errors, list) or errors:
            render_problems.append(
                f"browser.render.{viewport}.console_errors must be an empty list")
    rendered_copy = browser.get("result_copy_rendered") or {}
    for outcome in p["outcomes"]:
        key = _s(outcome.get("key"))
        if _s(rendered_copy.get(key)) != _s(outcome.get("result_copy")):
            render_problems.append(
                f"result copy for outcome {key!r} does not match the rendered page")
    problems.extend(render_problems)
    if not render_problems:
        checks.append("render_and_result_copy_verified")

    # 5. required questions are actually enforced
    required_problems: List[str] = []
    for q in p["questions"]:
        if not q.get("required", True):
            continue
        first_outcome = p["outcomes"][0]
        probe = _answers_for_score(
            p, _as_int(first_outcome["score_min"], "score_min"),
            _s(first_outcome.get("key")))
        probe.pop(_s(q.get("id")), None)
        try:
            score_answers(p, probe)
        except QuizAnswersIncomplete:
            continue
        required_problems.append(
            f"required question {q.get('id')!r} was not enforced (walk succeeded without it)")
    problems.extend(required_problems)
    if not required_problems:
        checks.append("required_fields_enforced")

    return {
        "schema": "skill6-marketing-quiz-verification/1",
        "live": False,
        "trust": "FAKE",
        "verified_at": _ts(),
        "quiz_name": _s(p.get("quiz_name")),
        "location_id": _s(p.get("location_id")),
        "outcomes": outcome_keys,
        "boundaries": boundaries,
        "contacts_created": len((crm or {}).get("contacts", []) or []),
        "enrollments": (crm or {}).get("enrollments", []) or [],
        "checks": checks,
        "problems": problems,
        "capture_refused": capture_failed,
        "ok": not problems,
        "reason": ("all marketing-quiz acceptance checks passed on a FAKE fixture"
                   if not problems else "; ".join(problems)),
    }


# ---------------------------------------------------------------------------
# CP01 — the frozen interface (plan/outcome mapping + fake fixture)
# ---------------------------------------------------------------------------
def cp01_record(plan: dict, fixture: dict, fixture_path: Optional[str] = None) -> dict:
    """Deterministic WF34-CP01 record: the frozen plan/outcome mapping contract."""
    p = normalize_plan(plan)
    band = reachable_score_range(p)
    boundaries = outcome_boundaries(p)
    digest = ""
    if fixture_path and os.path.isfile(fixture_path):
        with open(fixture_path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
    return {
        "checkpoint_id": CP01_ID,
        "workflow_id": "WF34",
        "contract": "BCM-GHL-HYBRID-2026-11-08",
        "revision": "3.0",
        "plan_schema": PLAN_SCHEMA,
        "fixture_schema": FIXTURE_SCHEMA,
        "rail": ACCEPTED_RAIL,
        "course_quiz_substitution": "refused",
        "score_band": {"min": band[0], "max": band[1]},
        "outcome_mapping": [
            {"outcome": _s(o.get("key")),
             "score_min": _as_int(o["score_min"], "score_min"),
             "score_max": _as_int(o["score_max"], "score_max"),
             "router": o.get("router") or None,
             "followup_workflows": [_s(w.get("key")) for w in p["followup_workflows"]
                                    if _s(w.get("outcome")) == _s(o.get("key"))]}
            for o in p["outcomes"]
        ],
        "boundary_answers": boundaries,
        "capture_policy": capture_policy(p),
        "dependent_fields": dependency_plan(p),
        "consumers": ["WF07", "WF09", "WF22", "WF23"],
        "fixture_sha256": digest,
        "note": ("Outcome is router-answer first, then the contiguous score band. "
                 "Weighted scoring is computed by this coordinator and persisted as "
                 "zhc_quiz_outcome/zhc_quiz_score; GHL surveys do not score natively."),
    }


# ---------------------------------------------------------------------------
# Build entrypoint (delegates the clicking)
# ---------------------------------------------------------------------------
def build_quiz(plan: dict, evidence_root: str, *, dry_run: bool = True,
               business_name: str = "[BUSINESS NAME]", campaign: str = "") -> dict:
    """Plan + delegate to the managed survey builder. Dry-run by default."""
    p = normalize_plan(plan)
    steps = build_step_plan(p)
    result: Dict[str, Any] = {
        "schema": "skill6-marketing-quiz-build/1",
        "rail": ACCEPTED_RAIL,
        "dry_run": bool(dry_run),
        "quiz_name": _s(p.get("quiz_name")),
        "steps": steps,
        "delegated_builder": "ghl_survey_builder.build_survey",
        "build_result": None,
    }
    if dry_run:
        result["status"] = "PLANNED"
        return result
    import ghl_survey_builder as _survey  # lazy: the ONE managed clicker
    task = to_survey_task(p, business_name=business_name, campaign=campaign)
    result["build_result"] = _survey.build_survey(task, evidence_root, dry_run=False)
    result["status"] = "BUILT"
    return result


# ---------------------------------------------------------------------------
# Selftest — fully offline
# ---------------------------------------------------------------------------
SELFTEST_GATES = {
    "wireframes": {"desktop": "wf-d.png", "mobile": "wf-m.png"},
    "mockups": {"desktop": "mk-d.png", "mobile": "mk-m.png"},
    "design_style_intake": {"style": "hybrid", "approved": True},
    "copy_budget": {"headline_max": 90, "body_max": 400, "image_prompt_max": 600},
    "native_full_width": True,
    "seo": {"title": "Marketing Quiz", "description": "Find your build stage.",
            "canonical": "https://example.test/quiz"},
    "native_checkout": {"mode": "native", "bypassed": False},
}


def _selftest_plan() -> dict:
    return {
        "schema": PLAN_SCHEMA,
        "quiz_name": "ZHC Build Stage Quiz",
        "location_id": "LOC_TEST_0001",
        "rail": ACCEPTED_RAIL,
        "page_gates": copy.deepcopy(SELFTEST_GATES),
        "questions": [
            {"id": "q1", "prompt": "How far along is your offer?", "type": "single_choice",
             "required": True, "field_key": "zhc_quiz_q1",
             "choices": [{"id": "a", "label": "Idea only", "score": 0},
                         {"id": "b", "label": "Live offer", "score": 3}]},
            {"id": "q2", "prompt": "What is your monthly revenue?", "type": "single_choice",
             "required": True, "field_key": "zhc_quiz_q2",
             "choices": [{"id": "a", "label": "Under 1k", "score": 0},
                         {"id": "b", "label": "1k-10k", "score": 2},
                         {"id": "c", "label": "10k+", "score": 4}],
             "branch": {"when_choice": "c", "goto": "q4"}},
            {"id": "q3", "prompt": "Do you have a team?", "type": "single_choice",
             "required": True, "field_key": "zhc_quiz_q3",
             "choices": [{"id": "a", "label": "Just me", "score": 0},
                         {"id": "b", "label": "Small team", "score": 1}]},
            {"id": "q4", "prompt": "What is your email?", "type": "email", "required": True},
        ],
        "outcomes": [
            {"key": "starter", "title": "Starter", "result_copy": "Start with the offer.",
             "score_min": 0, "score_max": 2, "tags": ["zhc_quiz_starter"]},
            {"key": "scaler", "title": "Scaler", "result_copy": "Systemise and scale.",
             "score_min": 3, "score_max": 5, "tags": ["zhc_quiz_scaler"]},
            {"key": "operator", "title": "Operator", "result_copy": "Lead the team.",
             "score_min": 6, "score_max": 7, "tags": ["zhc_quiz_operator"],
             "router": {"question_id": "q2", "choice_id": "c"}},
        ],
        "capture": {
            "required": True,
            "consent": {"required": True, "text": "I agree to be contacted.",
                        "field_key": "zhc_quiz_consent"},
            "fields": [{"field_key": "zhc_quiz_email", "source": "Email", "required": True}],
        },
        "field_tag_mapping": {"outcome_field_key": "zhc_quiz_outcome",
                              "score_field_key": "zhc_quiz_score",
                              "custom_fields": [
                                  {"field_key": "zhc_quiz_outcome", "data_type": "text"},
                                  {"field_key": "zhc_quiz_score", "data_type": "number"}],
                              "tags": [{"tag": "zhc_quiz_lead"}]},
        "followup_workflows": [
            {"key": "wf_starter", "outcome": "starter", "approved": True},
            {"key": "wf_scaler", "outcome": "scaler", "approved": True},
            {"key": "wf_operator", "outcome": "operator", "approved": True},
        ],
    }


def _selftest_fixture(plan: dict) -> dict:
    subs: List[dict] = []
    for b in outcome_boundaries(plan):
        answers = dict(b["answers"])
        answers.setdefault("q4", "synthetic@example.test")
        eff = compute_lead_effects(plan, {
            "answers": answers, "consent": True,
            "capture": {"zhc_quiz_email": "synthetic@example.test"}})
        subs.append({"name": f"{b['outcome']} {b['boundary']}", "answers": answers,
                     "consent": True,
                     "capture": {"zhc_quiz_email": "synthetic@example.test"},
                     "expected_outcome": b["outcome"],
                     "expected_effect": {"tags": eff["tags"],
                                         "workflows": eff["workflows"]}})
    return {
        "schema": FIXTURE_SCHEMA, "trust": "FAKE",
        "crm": {"contacts": [], "fields": [], "tags": [], "enrollments": []},
        "browser": {
            "render": {"desktop": {"hydrated_dom": True, "native_full_width": True,
                                   "console_errors": []},
                       "mobile": {"hydrated_dom": True, "native_full_width": True,
                                  "console_errors": []}},
            "result_copy_rendered": {_s(o["key"]): _s(o["result_copy"])
                                     for o in plan["outcomes"]},
        },
        "submissions": subs,
    }


def _selftest() -> int:  # noqa: C901
    errors: List[str] = []

    def check(label: str, cond: bool) -> None:
        if not cond:
            errors.append(label)

    def expect(label: str, exc, fn, *args, **kwargs) -> None:
        try:
            fn(*args, **kwargs)
        except exc:
            return
        except Exception as other:  # noqa: BLE001
            errors.append(f"{label}: raised {type(other).__name__} not {exc.__name__}")
            return
        errors.append(f"{label}: did not raise {exc.__name__}")

    plan = _selftest_plan()

    # 1. happy path + score band
    p = normalize_plan(plan)
    check("normalize copies", p is not plan)
    check("score band", reachable_score_range(p) == (0, 7))

    # 2. course-quiz substitution is refused
    for bad in ({"rail": "courses.lessons.quiz"},
                {"rail": ACCEPTED_RAIL, "endpoint": "courses/lessons/1/quiz"},
                {"rail": ACCEPTED_RAIL, "operation_id": "lesson_quiz.create"}):
        expect(f"course quiz refused {bad}", CourseQuizEndpointRefused,
               normalize_plan, {**plan, **bad})
    expect("rail must be managed_browser", CourseQuizEndpointRefused, normalize_plan,
           {**plan, "rail": "public_rest"})

    # 3. page gates (IG-PAGE-01)
    broken = copy.deepcopy(plan); broken["page_gates"]["native_full_width"] = False
    expect("full-width gate", PageGateIncomplete, normalize_plan, broken)
    broken = copy.deepcopy(plan); del broken["page_gates"]["mockups"]
    expect("mockup gate", PageGateIncomplete, normalize_plan, broken)
    broken = copy.deepcopy(plan); broken["page_gates"]["seo"]["title"] = "x" * 61
    expect("seo title budget", PageGateIncomplete, normalize_plan, broken)
    broken = copy.deepcopy(plan); broken["page_gates"]["native_checkout"]["bypassed"] = True
    expect("native checkout gate", PageGateIncomplete, normalize_plan, broken)
    broken = copy.deepcopy(plan)
    broken["page_gates"]["design_style_intake"]["style"] = "freehand"
    expect("design style gate", PageGateIncomplete, normalize_plan, broken)
    broken = copy.deepcopy(plan); broken["page_gates"]["copy_budget"]["headline_max"] = 0
    expect("copy budget gate", PageGateIncomplete, normalize_plan, broken)
    broken = copy.deepcopy(plan); broken.pop("page_gates")
    expect("missing page gates", PageGateIncomplete, normalize_plan, broken)

    # 4. sensitive capture refused
    broken = copy.deepcopy(plan)
    broken["capture"]["fields"].append({"field_key": "zhc_ssn", "source": "SSN"})
    expect("sensitive field refused", SensitiveFieldRefused, normalize_plan, broken)

    # 5. branching must be forward + resolvable
    broken = copy.deepcopy(plan)
    broken["questions"][1]["branch"] = {"when_choice": "c", "goto": "q1"}
    expect("backward branch refused", QuizPlanInvalid, normalize_plan, broken)
    broken = copy.deepcopy(plan)
    broken["questions"][1]["branch"] = {"when_choice": "zz", "goto": "q4"}
    expect("unknown branch choice refused", QuizPlanInvalid, normalize_plan, broken)

    # 6. outcome coverage must be exact and contiguous
    broken = copy.deepcopy(plan); broken["outcomes"][0]["score_max"] = 1
    expect("score gap refused", QuizPlanInvalid, normalize_plan, broken)
    broken = copy.deepcopy(plan); broken["outcomes"][2]["score_max"] = 8
    expect("short coverage refused", QuizPlanInvalid, normalize_plan, broken)
    broken = copy.deepcopy(plan); broken["outcomes"][2].pop("router")
    broken["outcomes"][1]["score_max"] = 4
    expect("overlap refused", QuizPlanInvalid, normalize_plan, broken)

    # 7. scoring + router precedence
    starter = score_answers(p, {"q1": "a", "q2": "a", "q3": "a", "q4": "a@example.test"})
    check("starter score", starter["score"] == 0 and starter["outcome"] == "starter")
    op = score_answers(p, {"q1": "a", "q2": "c", "q4": "a@example.test"})
    check("router wins over the score band",
          op["outcome"] == "operator" and op["score"] == 4)
    check("branch path", op["path"] == ["q1", "q2", "q4"])

    # 8. boundaries are reachable
    bounds = outcome_boundaries(p)
    check("boundary count", len(bounds) == 6)
    check("boundary outcomes", {b["outcome"] for b in bounds}
          == {"starter", "scaler", "operator"})

    # 9. required answers enforced
    expect("missing required answer", QuizAnswersIncomplete, score_answers, p, {"q1": "a"})

    # 10. consent + capture enforcement
    sub = {"answers": {"q1": "a", "q2": "a", "q3": "a", "q4": "a@example.test"},
           "consent": False, "capture": {"zhc_quiz_email": "a@example.test"}}
    expect("consent required", ConsentRequired, compute_lead_effects, p, sub)
    sub["consent"] = True
    sub["capture"] = {}
    expect("capture required", CaptureIncomplete, compute_lead_effects, p, sub)
    sub["capture"] = {"zhc_quiz_email": "a@example.test"}
    effects = compute_lead_effects(p, sub)
    check("outcome field", effects["fields"]["zhc_quiz_outcome"] == "starter")
    check("score field", effects["fields"]["zhc_quiz_score"] == 0)
    check("consent stored", effects["fields"]["zhc_quiz_consent"] is True)
    check("tags include outcome", "zhc_quiz_starter" in effects["tags"])
    check("workflow routed", effects["workflows"] == ["wf_starter"])

    # 11. fake CRM reducer
    crm = apply_submission_to_crm({}, effects)
    check("one contact", len(crm["contacts"]) == 1)
    check("enrollment recorded",
          crm["enrollments"] == [{"contact_id": "CT_1", "workflow": "wf_starter"}])

    # 12. selector file + step plan
    sel = load_selectors()
    check("selector anchors", isinstance(sel["anchors"], list) and len(sel["anchors"]) >= 11)
    steps = build_step_plan(p, sel)
    check("step count", len(steps["steps"]) == len(STEP_DEFS))
    check("survey task fields", len(steps["survey_task"]["survey_fields"]) == 4)
    check("conditional rules", len(steps["survey_task"]["conditional_logic"]) == 1)
    check("dependency plan", any(f["field_key"] == "zhc_quiz_outcome"
                                 for f in steps["dependency_plan"]["custom_fields"]))
    expect("unknown selector refused", QuizPlanInvalid, build_step_plan, p,
           {"anchors": [{"id": "quiz.list.add_survey"}], "version": "x"})

    # 13. fixture guards + acceptance
    fixture = _selftest_fixture(p)
    receipt = verify_acceptance(p, fixture)
    check("acceptance ok", receipt["ok"])
    if not receipt["ok"]:
        errors.extend(receipt.get("problems", []))
    check("acceptance is not live", receipt["live"] is False)
    check("every outcome verified", "every_outcome_verified" in receipt["checks"])
    check("branch verified", "branch_paths_verified" in receipt["checks"])
    check("render verified", "render_and_result_copy_verified" in receipt["checks"])
    check("required verified", "required_fields_enforced" in receipt["checks"])

    expect("non-fake fixture refused", FixtureNotSynthetic, verify_acceptance, p,
           {**fixture, "trust": "LIVE"})
    bad = copy.deepcopy(fixture)
    bad["browser"]["render"]["mobile"]["console_errors"] = ["500"]
    check("console error fails", not verify_acceptance(p, bad)["ok"])
    bad = copy.deepcopy(fixture)
    bad["browser"]["result_copy_rendered"]["starter"] = "wrong"
    check("result copy mismatch fails", not verify_acceptance(p, bad)["ok"])
    bad = copy.deepcopy(fixture); bad["submissions"] = bad["submissions"][:2]
    check("uncovered outcome fails", not verify_acceptance(p, bad)["ok"])
    bad = copy.deepcopy(fixture)
    bad["submissions"][0]["expected_outcome"] = "scaler"
    check("wrong outcome fails", not verify_acceptance(p, bad)["ok"])
    bad = copy.deepcopy(fixture)
    bad["submissions"][0]["consent"] = False
    check("unconsented fixture submission fails", not verify_acceptance(p, bad)["ok"])

    # 14. CP01 record is the frozen mapping
    rec = cp01_record(p, fixture)
    check("cp01 id", rec["checkpoint_id"] == CP01_ID)
    check("cp01 band", rec["score_band"] == {"min": 0, "max": 7})
    check("cp01 mapping", [m["outcome"] for m in rec["outcome_mapping"]]
          == ["starter", "scaler", "operator"])
    check("cp01 refuses course quiz", rec["course_quiz_substitution"] == "refused")
    check("cp01 consumers", set(rec["consumers"]) == {"WF07", "WF09", "WF22", "WF23"})

    # 15. dry-run build never touches a browser
    built = build_quiz(p, "/nonexistent-run", dry_run=True)
    check("dry run planned", built["status"] == "PLANNED" and built["build_result"] is None)
    check("dry run delegated",
          built["delegated_builder"] == "ghl_survey_builder.build_survey")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        print(f"\n[selftest] FAIL — {len(errors)} error(s)")
        return 1
    print("[selftest] PASS — marketing quiz is standalone (course quiz refused); "
          "outcome boundaries exact and reachable; branches forward-only; capture + "
          "consent enforced; sensitive fields refused; page gates enforced; lead capture "
          "and routing verified against a FAKE fixture; CP01 mapping frozen (offline)")
    return 0


def _load_json(path: str, label: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise QuizPlanInvalid(f"{label} {path!r} is not a JSON object")
    return data


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="ghl_marketing_quiz_builder",
        description="Skill 06 standalone marketing quiz coordinator (offline).")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--validate", metavar="PLAN_JSON")
    ap.add_argument("--survey-task", metavar="PLAN_JSON")
    ap.add_argument("--steps", metavar="PLAN_JSON")
    ap.add_argument("--fixture", nargs=2, metavar=("PLAN_JSON", "FIXTURE_JSON"))
    ap.add_argument("--cp01", nargs=2, metavar=("PLAN_JSON", "FIXTURE_JSON"))
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    try:
        if args.validate:
            normalize_plan(_load_json(args.validate, "plan"))
            print(f"VALID: {PLAN_SCHEMA} plan accepted")
            return 0
        if args.survey_task:
            plan = normalize_plan(_load_json(args.survey_task, "plan"))
            print(json.dumps(to_survey_task(plan), indent=2))
            return 0
        if args.steps:
            plan = normalize_plan(_load_json(args.steps, "plan"))
            print(json.dumps(build_step_plan(plan), indent=2))
            return 0
        if args.fixture:
            plan = normalize_plan(_load_json(args.fixture[0], "plan"))
            receipt = verify_acceptance(plan, _load_json(args.fixture[1], "fixture"))
            print(json.dumps(receipt, indent=2))
            return 0 if receipt["ok"] else 1
        if args.cp01:
            plan = normalize_plan(_load_json(args.cp01[0], "plan"))
            print(json.dumps(cp01_record(plan, _load_json(args.cp01[1], "fixture"),
                                         fixture_path=args.cp01[1]), indent=2))
            return 0
    except (QuizPlanInvalid, FixtureNotSynthetic) as exc:
        print(f"REFUSED ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
