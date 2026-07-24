#!/usr/bin/env python3
"""intake_interview.py — Shared adaptive intake interview for survey / page / funnel builds.

Sits at Wiring-Map Step 1 (Request → Intake) and feeds Step 2 (Persona) and
Step 3 (Think).  Never blocks a build — always overridable, always skips anything
already inferable.

Public API
----------
run_interview(task, ask_fn, *, executor=None, env=None) -> IntakeResult

    Parameters
    ----------
    task      : dict
        The incoming board task.  Recognised top-level keys are described in
        _TASK_KEY_MAP below.  Anything that cannot be inferred triggers a
        question; anything already present is silently skipped.
    ask_fn    : Callable[[Question], str]
        Synchronous callable presented with the current Question; returns the
        user's raw answer string.  Wire Telegram, CLI input, or any IO adapter
        here — the module itself has no IO.
    executor  : optional
        A model_router-compatible executor callable.  Required for the
        "think for me" branch; if None the branch is skipped and
        ``proposed_structure`` is left None in the result.
    env       : optional dict
        Passed straight to model_router.select(); defaults to os.environ.

    Returns
    -------
    IntakeResult dict — see TYPE section below.

"Think for me" branch
---------------------
Triggered when (a) the intent mode is UNSURE_WANTS_SUGGESTION or (b) the user
answers any question with a "you decide" / "think for me" phrase.

When triggered with an executor present:
  1. Calls model_router.select(executor, role='reasoning', env=env)
     (model_router is now role-aware; a TypeError fallback to the role-blind
      signature is retained for defensive compatibility only).
  2. The chosen rung is stored in think_model_receipt.
  3. A lightweight structure is proposed (slide/page count, element types, options,
     conditional-logic stubs, capture fields) and presented to the user via ask_fn
     as a single confirmation question.
  4. If the user confirms, proposed_structure is set and confirmed=True; otherwise
     the proposed structure is discarded and the interview continues normally.

WS-A NOTE (resolved):  model_router.select() is role-aware (Workstream A has
landed).  This module calls select() with ``role='reasoning'``; the TypeError
fallback path is retained for defensive compatibility only.

Model sovereignty
-----------------
This module never names or selects an Anthropic model.  The executor that drives
the "think for me" proposal is provided by the caller (typically model_router,
which enforces the Anthropic hard-block itself).

Wired into v2_dispatcher as Step 1 (_run_intake) — run_interview() is called
at the start of every v2_dispatcher build run.
"""
from __future__ import annotations

import os
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Intent-mode constants (mirrored from funnel_matcher for clean import)
# ---------------------------------------------------------------------------
MODE_EXPLICIT  = "EXPLICIT_USER_SPEC"
MODE_UNSURE    = "UNSURE_WANTS_SUGGESTION"
MODE_HANDSOFF  = "HANDS_OFF_DO_IT_ALL"

# Build types understood by this module.
BUILD_TYPE_FUNNEL = "funnel"
BUILD_TYPE_PAGE   = "page"
BUILD_TYPE_SURVEY = "survey"
KNOWN_BUILD_TYPES = (BUILD_TYPE_FUNNEL, BUILD_TYPE_PAGE, BUILD_TYPE_SURVEY)

# Maximum total questions asked in a single run (across all types).
MAX_QUESTIONS = 7

# ---------------------------------------------------------------------------
# Question definition
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Question:
    """A single interview question with its inference metadata.

    Attributes
    ----------
    qid          : stable identifier used as the answer dict key.
    text         : the question string shown to the user (plain language, never
                   technical jargon).
    hint         : optional parenthetical hint shown after the question.
    task_keys    : task-dict keys checked (in order) for a pre-existing answer.
    brief_patterns: compiled regex patterns run against ``task["brief"]``;
                   the first match group (or the whole match) becomes the
                   inferred answer.
    options      : if set, the valid choices are shown after the question text.
                   The user's answer is matched case-insensitively.
    required     : if True, the question is always asked even when an ambiguous
                   brief match is found (only skipped on an exact task-key hit).
    """
    qid: str
    text: str
    hint: str = ""
    task_keys: tuple = ()
    brief_patterns: tuple = ()          # compiled re.Pattern objects
    options: Optional[tuple] = None
    required: bool = False

    def formatted_text(self) -> str:
        """Return the full question string, including options and hint."""
        out = self.text
        if self.options:
            out += "\n  Options: " + " / ".join(self.options)
        if self.hint:
            out += f"\n  ({self.hint})"
        return out


# ---------------------------------------------------------------------------
# Per-type question sets (PRD §5.D)
# ---------------------------------------------------------------------------

def _p(*patterns: str) -> tuple:
    """Compile a sequence of pattern strings into re.Pattern objects."""
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


# --- FUNNEL (3 core + 2 shared copy-context = up to 5 questions) -----------
FUNNEL_QUESTIONS: List[Question] = [
    Question(
        qid="goal",
        text="What is the main goal for this funnel?",
        hint="e.g. collect leads, sell a product, book a call",
        task_keys=("goal", "funnel_goal", "objective", "funnel_objective"),
        brief_patterns=_p(
            r"goal[:\s]+(.+?)[\.\n]",
            r"objective[:\s]+(.+?)[\.\n]",
            r"to (?:generate|collect|capture|sell|book|get)\s(.+?)[\.\n]",
        ),
        required=True,
    ),
    Question(
        qid="page_count",
        text="How many pages should it have?",
        hint="Enter a number, or type 'you decide' and I will choose",
        task_keys=("page_count", "num_pages", "length", "pages"),
        brief_patterns=_p(
            r"(\d+)[- ]?page",
            r"(\d+)[- ]?step",
        ),
        required=False,
    ),
    Question(
        qid="audience_offer",
        text="Who is the target audience, and what is the offer?",
        hint="e.g. 'coaches who want to scale, offering a 6-week program'",
        task_keys=("audience", "offer", "target_audience", "product", "service",
                   "audience_offer"),
        brief_patterns=_p(
            r"audience[:\s]+(.+?)[\.\n]",
            r"offer[:\s]+(.+?)[\.\n]",
            r"for\s+(.+?),\s+offering\s+(.+?)[\.\n]",
        ),
        required=True,
    ),
]

# --- PAGE (3 core + 2 shared copy-context = up to 5 questions) -------------
PAGE_QUESTIONS: List[Question] = [
    Question(
        qid="page_type",
        text="What type of page is this?",
        hint="opt-in, sales, booking, or thank-you",
        task_keys=("page_type", "funnel_type", "type", "page_kind"),
        brief_patterns=_p(
            r"\b(opt-?in|optin)\b",
            r"\b(sales)\s+page\b",
            r"\b(booking|appointment)\s+page\b",
            r"\b(thank[- ]you|thankyou|ty)\s+page\b",
        ),
        options=("opt-in", "sales", "booking", "thank-you"),
        required=True,
    ),
    Question(
        qid="cta_offer",
        text="What is the call-to-action and the offer?",
        hint="e.g. 'Download the free guide / 7-day email course'",
        task_keys=("cta", "offer", "call_to_action", "cta_offer", "button_text"),
        brief_patterns=_p(
            r"cta[:\s]+(.+?)[\.\n]",
            r"call[- ]to[- ]action[:\s]+(.+?)[\.\n]",
            r"offer[:\s]+(.+?)[\.\n]",
        ),
        required=True,
    ),
    Question(
        qid="has_copy",
        text="Do you already have copy, or should I write it?",
        hint="'I have copy' or 'write it for me'",
        task_keys=("has_copy", "copy", "copy_provided", "copy_ready"),
        brief_patterns=_p(
            r"\b(have|have the|my own)\s+copy\b",
            r"\bwrite\s+(the|my|it)\b",
            r"\bcopy\s+is\s+ready\b",
        ),
        options=("I have copy", "write it for me"),
        required=False,
    ),
]

# --- COPY-CONTEXT (shared; appended to FUNNEL + PAGE) ----------------------
# FIX-COPY-04(i): capture the two copy-depth/voice signals the copywriter needs
# so the P2 brief and funnel-spec are never authored voice-unanchored or at the
# wrong length. Both are OPTIONAL and skip cleanly when already inferable, so the
# per-type set stays well within MAX_QUESTIONS=7 (funnel 3→5, page 3→5).
COPY_CONTEXT_QUESTIONS: List[Question] = [
    Question(
        qid="traffic_source",
        text="Where will visitors come from — paste the ad or email headline they'll click.",
        hint="e.g. the Facebook ad hook or the email subject line that sends them here",
        task_keys=("traffic_source", "ad_headline", "email_headline", "source_headline",
                   "traffic"),
        brief_patterns=_p(
            r"traffic\s+source[:\s]+(.+?)[\.\n]",
            r"from\s+(?:a|an|the)\s+(facebook|instagram|google|youtube|tiktok|email|newsletter)\s+ad",
            r"ad\s+headline[:\s]+(.+?)[\.\n]",
        ),
        required=False,
    ),
    Question(
        qid="copy_depth",
        text="How deep should the copy go?",
        hint="short (punchy), standard (balanced), or long-form (full direct-response)",
        task_keys=("copy_depth", "depth", "copy_length", "length_class"),
        brief_patterns=_p(
            r"\b(short[- ]?form|short|punchy|minimal)\b",
            r"\b(standard|balanced|medium)\b",
            r"\b(long[- ]?form|long|detailed|in[- ]?depth)\b",
        ),
        options=("short", "standard", "long-form"),
        required=False,
    ),
]

# Extend the funnel + page sets in place (same list objects QUESTION_SETS binds).
FUNNEL_QUESTIONS.extend(COPY_CONTEXT_QUESTIONS)
PAGE_QUESTIONS.extend(COPY_CONTEXT_QUESTIONS)


# --- SURVEY (up to 4 questions) -------------------------------------------
SURVEY_QUESTIONS: List[Question] = [
    Question(
        qid="purpose",
        text="What is the purpose of this survey?",
        hint="intake, qualification, or feedback",
        task_keys=("purpose", "survey_purpose", "survey_type", "type"),
        brief_patterns=_p(
            r"\b(intake)\b",
            r"\b(qualification|qualify|qualifying)\b",
            r"\b(feedback|satisfaction)\b",
        ),
        options=("intake", "qualification", "feedback"),
        required=True,
    ),
    Question(
        qid="capture_fields",
        text="Which fields should we capture from respondents?",
        hint="e.g. 'name, email, business stage, how they heard about us'",
        task_keys=("fields", "capture_fields", "custom_fields", "form_fields",
                   "data_to_capture"),
        brief_patterns=_p(
            r"capture[:\s]+(.+?)[\.\n]",
            r"fields?[:\s]+(.+?)[\.\n]",
            r"collect[:\s]+(.+?)[\.\n]",
        ),
        required=True,
    ),
    Question(
        qid="response_routing",
        text="Where should responses route — which persona and department?",
        hint="e.g. 'sales team, business-development persona'",
        task_keys=("routing", "department", "persona", "response_routing",
                   "route_to"),
        brief_patterns=_p(
            r"route\s+to\s+(.+?)[\.\n]",
            r"send\s+to\s+(.+?)[\.\n]",
            r"department[:\s]+(.+?)[\.\n]",
        ),
        required=False,
    ),
    Question(
        qid="propose_questions",
        text="Want me to propose the survey questions, or do you already have them?",
        hint="'propose them' or 'I have the questions'",
        task_keys=("questions", "survey_questions", "question_list"),
        brief_patterns=_p(
            r"\b(propose|suggest|generate|create)\s+(?:the\s+)?questions\b",
            r"\bI\s+have\s+(?:the\s+)?questions\b",
            r"\bquestions\s+already\b",
        ),
        options=("propose them", "I have the questions"),
        # If task["questions"] is already a non-empty list, this is skipped.
        required=False,
    ),
]

# Master map build_type -> ordered question list.
QUESTION_SETS: Dict[str, List[Question]] = {
    BUILD_TYPE_FUNNEL: FUNNEL_QUESTIONS,
    BUILD_TYPE_PAGE:   PAGE_QUESTIONS,
    BUILD_TYPE_SURVEY: SURVEY_QUESTIONS,
}

# ---------------------------------------------------------------------------
# "Think for me" trigger phrases
# ---------------------------------------------------------------------------
_THINK_FOR_ME_PATTERNS = re.compile(
    r"\b(?:you\s+decide|think\s+for\s+me|up\s+to\s+you|whatever\s+you\s+think|"
    r"suggest\s+(?:it|something)|not\s+sure|unsure|no\s+preference|"
    r"you\s+choose|your\s+call|i\s+don['’]?t\s+know)\b",
    re.IGNORECASE,
)

def _wants_suggestion(text: str) -> bool:
    """Return True if the text signals 'you decide / think for me'."""
    return bool(_THINK_FOR_ME_PATTERNS.search(text or ""))


# ---------------------------------------------------------------------------
# Answer inference helpers
# ---------------------------------------------------------------------------
def _first_nonempty(task: dict, keys: tuple) -> Optional[str]:
    """Return the first non-empty string value from *task* matching any key in *keys*."""
    for k in keys:
        v = task.get(k)
        if isinstance(v, list) and v:
            return ", ".join(str(x) for x in v)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _infer_from_brief(task: dict, question: Question) -> Optional[str]:
    """Try to extract an answer from ``task["brief"]`` using the question's
    brief_patterns.  Returns the match group (or full match) on the first hit,
    or None."""
    brief = task.get("brief", "") or task.get("text", "") or task.get("description", "")
    if not brief or not question.brief_patterns:
        return None
    for pat in question.brief_patterns:
        m = pat.search(brief)
        if m:
            # Return the first capture group if present, else the whole match.
            return (m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)).strip()
    return None


def _infer_answer(task: dict, question: Question) -> Optional[str]:
    """Try to infer an answer for *question* from the task dict.

    Precedence:
    1. Explicit task key match  (exact; always wins even for required questions).
    2. Brief-pattern match       (heuristic; skipped if ``required=True``, since
                                  required questions are confirmed verbatim with the user).
    Returns None if no inference is possible.
    """
    # 1. Explicit key hit.
    v = _first_nonempty(task, question.task_keys)
    if v:
        return v

    # 2. Brief pattern (only for non-required questions to avoid silent errors).
    if not question.required:
        return _infer_from_brief(task, question)

    return None


# ---------------------------------------------------------------------------
# Build-type detection
# ---------------------------------------------------------------------------
_TYPE_PATTERNS: Dict[str, re.Pattern] = {
    BUILD_TYPE_SURVEY: re.compile(
        r"\b(?:survey|form|questionnaire|quiz)\b", re.IGNORECASE
    ),
    BUILD_TYPE_PAGE: re.compile(
        r"\b(?:page|landing[- ]?page|opt[- ]?in|sales[- ]?page|booking[- ]?page|"
        r"thank[- ]?you[- ]?page)\b",
        re.IGNORECASE,
    ),
    BUILD_TYPE_FUNNEL: re.compile(
        r"\b(?:funnel|flow|sequence|campaign)\b", re.IGNORECASE
    ),
}


def _detect_build_type(task: dict) -> str:
    """Determine the build type from the task dict.

    Checks (in order):
    1. Explicit ``task["build_type"]`` / ``task["type"]`` if it matches a known type.
    2. Text scan of ``task["brief"]`` / ``task["text"]`` / ``task["description"]``
       for type keywords (survey > page > funnel precedence).
    Defaults to ``"funnel"`` when nothing matches.
    """
    # 1. Explicit field.
    for k in ("build_type", "type", "funnel_type", "job_type"):
        v = (task.get(k) or "").strip().lower()
        if v in KNOWN_BUILD_TYPES:
            return v
        # partial match on explicit field
        for bt, pat in _TYPE_PATTERNS.items():
            if pat.search(v):
                return bt

    # 2. Scan the brief/text.
    # Precedence: survey (most specific) > funnel > page.  "Funnel" before "page"
    # prevents "3-page funnel" from matching the PAGE pattern before FUNNEL.
    text = (
        task.get("brief", "")
        or task.get("text", "")
        or task.get("description", "")
    )
    for bt in (BUILD_TYPE_SURVEY, BUILD_TYPE_FUNNEL, BUILD_TYPE_PAGE):
        if _TYPE_PATTERNS[bt].search(text):
            return bt

    return BUILD_TYPE_FUNNEL   # safe default


# ---------------------------------------------------------------------------
# "Think for me" branch
# ---------------------------------------------------------------------------
def _run_think_for_me_branch(
    task: dict,
    build_type: str,
    answers: dict,
    executor,
    env: Optional[dict],
    ask_fn: Callable,
) -> dict:
    """Run the 'think for me' branch.

    Selects the reasoning model via model_router, then generates a lightweight
    proposed structure and asks the user to confirm it.

    Returns a dict:
      {
        "proposed_structure": dict | None,
        "think_model_receipt": dict | None,
        "confirmed": bool,
      }
    """
    think_receipt: Optional[dict] = None
    proposed: Optional[dict] = None
    confirmed = False

    if executor is None:
        return {"proposed_structure": None, "think_model_receipt": None,
                "confirmed": False, "_skip_reason": "no_executor"}

    # Import model_router lazily (sibling module; do not hard-fail at import time).
    try:
        import importlib
        import sys as _sys
        _tools_dir = os.path.dirname(os.path.abspath(__file__))
        if _tools_dir not in _sys.path:
            _sys.path.insert(0, _tools_dir)
        model_router = importlib.import_module("model_router")
    except ImportError as exc:
        return {"proposed_structure": None, "think_model_receipt": None,
                "confirmed": False, "_skip_reason": f"model_router import failed: {exc}"}

    # Call select() with role='reasoning' — model_router is now role-aware
    # (Workstream A landed).  The TypeError fallback is retained for defensive
    # compatibility only.
    try:
        think_receipt = model_router.select(executor, role="reasoning", env=env)
    except TypeError:
        try:
            think_receipt = model_router.select(executor, env=env)
        except Exception as exc:
            return {"proposed_structure": None, "think_model_receipt": None,
                    "confirmed": False, "_skip_reason": f"model_router.select failed: {exc}"}
    except Exception as exc:
        return {"proposed_structure": None, "think_model_receipt": None,
                "confirmed": False, "_skip_reason": f"model_router.select failed: {exc}"}

    chosen = (think_receipt or {}).get("chosen") or {}
    chosen_slug = chosen.get("model") or chosen.get("slug") or "unknown"

    # Build a lightweight proposed structure.  This is a scaffold that the THINK
    # phase fills in; the actual model inference call is made by the executor in
    # the THINK phase (Step 3).  Here we assemble what we know from the answers
    # collected so far and leave placeholders for the model to fill.
    proposed = _scaffold_structure(build_type, answers)
    proposed["_reasoning_model"] = chosen_slug
    proposed["_note"] = (
        "This structure was generated from your answers. "
        "The THINK phase will fill in full copy, options, and conditional logic."
    )

    # Present to user for confirmation.
    summary = _format_proposed_structure(proposed, build_type)
    confirm_q = Question(
        qid="_think_confirm",
        text=(
            f"Here is a proposed structure based on your answers:\n\n"
            f"{summary}\n\n"
            f"Should I build this? (yes / no — type 'no' to answer the questions yourself)"
        ),
        hint="",
        task_keys=(),
    )
    raw_confirm = (ask_fn(confirm_q) or "").strip().lower()
    confirmed = raw_confirm in ("yes", "y", "sure", "ok", "sounds good", "go ahead",
                                "build it", "looks good", "correct", "confirmed")

    if not confirmed:
        proposed = None   # discard; interview continues normally

    return {
        "proposed_structure": proposed,
        "think_model_receipt": think_receipt,
        "confirmed": confirmed,
    }


def _scaffold_structure(build_type: str, answers: dict) -> dict:
    """Return a lightweight scaffold dict for the proposed structure.

    The scaffold captures what the interview already knows and leaves
    the rest as placeholder strings for the THINK model to elaborate.
    """
    if build_type == BUILD_TYPE_SURVEY:
        return {
            "build_type": "survey",
            "purpose": answers.get("purpose", "[infer from context]"),
            "slides": [
                {"slide": 1, "name": "Welcome Slide", "elements": ["text block"]},
                {"slide": 2, "name": "Question 1", "elements": ["[field from brief]"],
                 "required": True},
                {"slide": "...", "name": "...", "elements": ["..."]},
                {"slide": "N", "name": "Capture Slide",
                 "elements": ["First Name", "Last Name", "Email", "Phone", "T & C"]},
            ],
            "capture_fields": answers.get("capture_fields", "[infer from context]"),
            "response_routing": answers.get("response_routing", "[infer from context]"),
            "conditional_logic": ["[THINK phase will fill in]"],
            "propose_questions": answers.get("propose_questions", "yes"),
        }
    elif build_type == BUILD_TYPE_PAGE:
        return {
            "build_type": "page",
            "page_type": answers.get("page_type", "[infer from context]"),
            "sections": [
                {"name": "Hero", "elements": ["headline", "subheadline", "CTA button"]},
                {"name": "Body", "elements": ["[THINK phase will fill in]"]},
                {"name": "Footer CTA", "elements": ["CTA button"]},
            ],
            "cta": answers.get("cta_offer", "[infer from context]"),
            "copy_source": answers.get("has_copy", "write it for me"),
            # FIX-COPY-04(i): thread copy depth + traffic source into the P2 brief.
            "copy_depth": answers.get("copy_depth", "standard"),
            "traffic_source": answers.get("traffic_source", "[infer from context]"),
        }
    else:  # funnel
        return {
            "build_type": "funnel",
            "goal": answers.get("goal", "[infer from context]"),
            "page_count": answers.get("page_count", "[THINK phase will decide]"),
            "audience_offer": answers.get("audience_offer", "[infer from context]"),
            # FIX-COPY-04(i): thread copy depth + traffic source into the funnel-spec.
            "copy_depth": answers.get("copy_depth", "standard"),
            "traffic_source": answers.get("traffic_source", "[infer from context]"),
            "pages": [
                {"page": 1, "type": "opt-in", "name": "Lead Capture"},
                {"page": "...", "type": "...", "name": "..."},
            ],
        }


def _format_proposed_structure(structure: dict, build_type: str) -> str:
    """Return a plain-language, 7th-grade summary of the proposed structure."""
    lines = []
    if build_type == BUILD_TYPE_SURVEY:
        lines.append(f"Survey purpose: {structure.get('purpose', '?')}")
        slides = structure.get("slides", [])
        lines.append(f"Slides: {len(slides)} (welcome + questions + capture)")
        fields = structure.get("capture_fields", "?")
        lines.append(f"Fields to capture: {fields}")
        routing = structure.get("response_routing", "?")
        lines.append(f"Responses route to: {routing}")
    elif build_type == BUILD_TYPE_PAGE:
        lines.append(f"Page type: {structure.get('page_type', '?')}")
        sections = structure.get("sections", [])
        lines.append(f"Sections: {', '.join(s['name'] for s in sections)}")
        lines.append(f"Call to action: {structure.get('cta', '?')}")
        lines.append(f"Copy: {structure.get('copy_source', '?')}")
    else:
        lines.append(f"Goal: {structure.get('goal', '?')}")
        lines.append(f"Pages: {structure.get('page_count', '?')}")
        lines.append(f"Audience and offer: {structure.get('audience_offer', '?')}")
    return "\n".join(f"  • {l}" for l in lines)


# ---------------------------------------------------------------------------
# IntakeResult type
# ---------------------------------------------------------------------------
# Using a plain dict (not TypedDict) for maximum backward compat; documented
# keys are listed here for IDE support.
#
# IntakeResult keys:
#   build_type        : str                  — "funnel" | "page" | "survey"
#   answers           : dict[str, str]       — question_id -> answer string
#   inferred          : list[str]            — qids answered from task keys / brief
#   skipped           : list[str]            — qids never asked (already in task)
#   mode              : str                  — intent mode (EXPLICIT / UNSURE / HANDSOFF)
#   proposed_structure: dict | None          — set when think-for-me confirmed
#   think_model_receipt: dict | None         — model_router receipt
#   confirmed         : bool                 — True iff proposed_structure was accepted
#   interview_complete: bool                 — always True on normal exit


def _make_result(
    build_type: str,
    answers: dict,
    inferred: List[str],
    skipped: List[str],
    mode: str,
    proposed_structure: Optional[dict],
    think_model_receipt: Optional[dict],
    confirmed: bool,
) -> dict:
    return {
        "build_type": build_type,
        "answers": answers,
        "inferred": inferred,
        "skipped": skipped,
        "mode": mode,
        "proposed_structure": proposed_structure,
        "think_model_receipt": think_model_receipt,
        "confirmed": confirmed,
        "interview_complete": True,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_interview(
    task: dict,
    ask_fn: Callable,   # Callable[[Question], str]
    *,
    executor=None,
    env: Optional[dict] = None,
) -> dict:
    """Run the adaptive intake interview for a survey / page / funnel build.

    See module docstring for full parameter and return-value documentation.

    Guaranteed invariants:
    - At most MAX_QUESTIONS (7) questions are asked.
    - Questions whose answer is already present in *task* are silently skipped.
    - Required questions are always asked unless an exact task-key answer exists.
    - The mode is detected via funnel_matcher.detect_mode if available, else
      inferred from the task and collected answers.
    - Never raises — on unexpected errors an incomplete IntakeResult with
      ``interview_complete=False`` is returned.
    - Never names or selects an Anthropic model anywhere in this function.
    """
    env = env if env is not None else os.environ
    answers: Dict[str, str] = {}
    inferred: List[str] = []
    skipped: List[str] = []
    proposed_structure: Optional[dict] = None
    think_model_receipt: Optional[dict] = None
    confirmed = False
    think_triggered = False

    try:
        # ---- 1. Detect build type ----------------------------------------
        build_type = _detect_build_type(task)
        questions = QUESTION_SETS[build_type]

        # ---- 2. Detect intent mode (best-effort; falls back to UNSURE) ----
        mode = _detect_mode(task)

        # If HANDS_OFF, the model should propose everything; trigger think-for-me.
        if mode == MODE_HANDSOFF:
            think_triggered = True

        # ---- 3. Walk questions -------------------------------------------
        asked_count = 0

        for question in questions:
            if asked_count >= MAX_QUESTIONS:
                break

            # Try to infer the answer without asking.
            inferred_value = _infer_answer(task, question)

            if inferred_value is not None:
                # Already answered — check whether it signals "you decide".
                answers[question.qid] = inferred_value
                if _wants_suggestion(inferred_value):
                    think_triggered = True
                # Mark as inferred vs. skipped based on where it came from.
                if _first_nonempty(task, question.task_keys):
                    skipped.append(question.qid)
                else:
                    inferred.append(question.qid)
                continue

            # Ask the question.
            raw_answer = (ask_fn(question) or "").strip()
            asked_count += 1

            if not raw_answer:
                # U055: required field with empty answer -> re-ask with a
                # field-specific validation message ("{Field name} is required")
                # instead of silently skipping or showing a generic error.
                if question.required:
                    _req_reask = 0
                    while _req_reask < 3 and not raw_answer:
                        _req_reask += 1
                        _val_q = Question(
                            qid=question.qid,
                            text=question.text,
                            hint=(
                                f"{question.hint}; " if question.hint else ""
                            ) + f"'{question.qid.replace('_', ' ').title()}' is required. "
                                "Please provide an answer.",
                            task_keys=question.task_keys,
                            brief_patterns=question.brief_patterns,
                            options=question.options,
                            required=True,
                        )
                        raw_answer = (ask_fn(_val_q) or "").strip()
                    if not raw_answer:
                        # Exhausted re-asks - record empty and move on.
                        answers[question.qid] = ""
                        continue
                    # Re-ask succeeded - normalise and record the answer.
                    if question.options:
                        normed = _match_option(raw_answer, question.options)
                        answers[question.qid] = normed if normed else raw_answer
                    else:
                        answers[question.qid] = raw_answer
                    if _wants_suggestion(raw_answer):
                        think_triggered = True
                    continue

                # Empty answer -> treat as "you decide" for optional questions.
                think_triggered = True
                answers[question.qid] = "you decide"
                continue

            # Normalise options (case-insensitive match).
            if question.options:
                normed = _match_option(raw_answer, question.options)
                answers[question.qid] = normed if normed else raw_answer
            else:
                answers[question.qid] = raw_answer

            if _wants_suggestion(raw_answer):
                think_triggered = True

        # ---- 4. "Think for me" branch ------------------------------------
        # Runs at the end of questioning only when explicitly triggered.
        # We offer it proactively when mode=UNSURE AND at least one question
        # was actually asked (meaning the task wasn't pre-answered).  If all
        # answers were already in the task the client knows what they want —
        # no offer needed.
        if think_triggered or (mode == MODE_UNSURE and asked_count > 0):
            # First, offer the branch explicitly if not already triggered by an answer.
            if not think_triggered:
                branch_q = Question(
                    qid="_think_offer",
                    text="Want me to think about this and propose a structure for you?",
                    hint="'yes' to let me propose, 'no' to keep going",
                    task_keys=(),
                    options=("yes", "no"),
                )
                branch_raw = (ask_fn(branch_q) or "").strip().lower()
                asked_count += 1
                think_triggered = branch_raw not in ("no", "n", "nope", "no thanks")

            if think_triggered:
                branch_result = _run_think_for_me_branch(
                    task=task,
                    build_type=build_type,
                    answers=answers,
                    executor=executor,
                    env=env,
                    ask_fn=ask_fn,
                )
                proposed_structure = branch_result.get("proposed_structure")
                think_model_receipt = branch_result.get("think_model_receipt")
                confirmed = branch_result.get("confirmed", False)

                # If the proposed structure was confirmed, merge its
                # concrete answers back so THINK / persona-match skip them.
                if confirmed and proposed_structure:
                    _merge_structure_into_answers(proposed_structure, answers, build_type)

    except Exception as exc:  # noqa: BLE001 — intake must never block a build
        return {
            "build_type": task.get("build_type", "funnel"),
            "answers": answers,
            "inferred": inferred,
            "skipped": skipped,
            "mode": MODE_UNSURE,
            "proposed_structure": None,
            "think_model_receipt": None,
            "confirmed": False,
            "interview_complete": False,
            "_error": f"{type(exc).__name__}: {exc}",
        }

    return _make_result(
        build_type=build_type,
        answers=answers,
        inferred=inferred,
        skipped=skipped,
        mode=mode,
        proposed_structure=proposed_structure,
        think_model_receipt=think_model_receipt,
        confirmed=confirmed,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _detect_mode(task: dict) -> str:
    """Detect intent mode from the task, using funnel_matcher.detect_mode when
    available.  Falls back to a simple heuristic."""
    try:
        import sys as _sys
        _tools_dir = os.path.dirname(os.path.abspath(__file__))
        if _tools_dir not in _sys.path:
            _sys.path.insert(0, _tools_dir)
        import importlib
        fm = importlib.import_module("funnel_matcher")
        result = fm.detect_mode(task)
        return result.get("mode", MODE_UNSURE)
    except Exception:  # noqa: BLE001 — best-effort
        pass

    # Fallback heuristic.
    brief = task.get("brief", "") or task.get("text", "")
    if task.get("explicit_funnel") or task.get("user_steps") or task.get("spec"):
        return MODE_EXPLICIT
    if task.get("just_do_it"):
        return MODE_HANDSOFF
    if _wants_suggestion(brief):
        return MODE_UNSURE
    return MODE_UNSURE


def _match_option(text: str, options: tuple) -> Optional[str]:
    """Return the first option that the text matches (case-insensitive prefix or
    substring).  Returns None if nothing matches well enough."""
    text_lower = text.lower()
    # Exact match first.
    for opt in options:
        if opt.lower() == text_lower:
            return opt
    # Prefix match.
    for opt in options:
        if text_lower.startswith(opt.lower()):
            return opt
    # Substring match (the option appears in the user's answer).
    for opt in options:
        if opt.lower() in text_lower:
            return opt
    return None


def _merge_structure_into_answers(
    structure: dict, answers: dict, build_type: str
) -> None:
    """Merge concrete values from a confirmed proposed_structure back into answers
    so that downstream THINK / persona-match phases can skip them."""
    if build_type == BUILD_TYPE_SURVEY:
        for key in ("purpose", "capture_fields", "response_routing", "propose_questions"):
            if key in structure and key not in answers:
                answers[key] = str(structure[key])
    elif build_type == BUILD_TYPE_PAGE:
        _map = {"page_type": "page_type", "cta": "cta_offer",
                "copy_source": "has_copy",
                # FIX-COPY-04(i): carry the copy-context signals back.
                "copy_depth": "copy_depth", "traffic_source": "traffic_source"}
        for src, dst in _map.items():
            if src in structure and dst not in answers:
                answers[dst] = str(structure[src])
    else:  # funnel
        for key in ("goal", "page_count", "audience_offer",
                    "copy_depth", "traffic_source"):
            if key in structure and key not in answers:
                answers[key] = str(structure[key])


# ---------------------------------------------------------------------------
# Convenience: build-type-specific entry points (thin wrappers for callers
# that already know the type and want to skip auto-detection).
# ---------------------------------------------------------------------------
def run_funnel_interview(task: dict, ask_fn: Callable, **kwargs) -> dict:
    """Convenience wrapper: forces build_type='funnel' before running."""
    task = {**task, "build_type": BUILD_TYPE_FUNNEL}
    return run_interview(task, ask_fn, **kwargs)


def run_page_interview(task: dict, ask_fn: Callable, **kwargs) -> dict:
    """Convenience wrapper: forces build_type='page' before running."""
    task = {**task, "build_type": BUILD_TYPE_PAGE}
    return run_interview(task, ask_fn, **kwargs)


def run_survey_interview(task: dict, ask_fn: Callable, **kwargs) -> dict:
    """Convenience wrapper: forces build_type='survey' before running."""
    task = {**task, "build_type": BUILD_TYPE_SURVEY}
    return run_interview(task, ask_fn, **kwargs)


# ---------------------------------------------------------------------------
# CLI smoke-test (offline — no live executor needed)
# ---------------------------------------------------------------------------
def _selftest() -> int:
    """Offline smoke-test.  Run:
        python3 intake_interview.py --selftest
    Exits 0 on pass."""
    import json

    failures: List[str] = []

    # --- helper: collect questions without asking anything ---
    def _silent_ask(q: Question) -> str:
        return ""

    # 1. Build-type detection
    for (task, expected) in [
        ({"brief": "build me a survey for intake"}, BUILD_TYPE_SURVEY),
        ({"brief": "create a landing page"}, BUILD_TYPE_PAGE),
        ({"brief": "set up a 3-page funnel"}, BUILD_TYPE_FUNNEL),
        ({"build_type": "survey"}, BUILD_TYPE_SURVEY),
    ]:
        got = _detect_build_type(task)
        if got != expected:
            failures.append(f"detect_build_type({task!r}) -> {got!r}, want {expected!r}")

    # 2. Inference — explicit key wins
    q_goal = FUNNEL_QUESTIONS[0]
    result = _infer_answer({"goal": "get leads"}, q_goal)
    if result != "get leads":
        failures.append(f"infer goal explicit key: got {result!r}")

    # 3. Inference — brief pattern
    q_page_count = FUNNEL_QUESTIONS[1]
    result = _infer_from_brief({"brief": "build a 3-page funnel"}, q_page_count)
    if result != "3":
        failures.append(f"infer page_count from brief: got {result!r}")

    # 4. run_interview — all fields pre-filled (no questions asked)
    ask_calls = []
    def _recording_ask(q: Question) -> str:
        ask_calls.append(q.qid)
        return ""

    pre_filled_funnel_task = {
        "build_type": "funnel",
        "goal": "generate coaching leads",
        "page_count": "3",
        "audience_offer": "coaches, 6-week program",
        # FIX-COPY-04(i): the shared copy-context questions are part of the funnel
        # set now, so a fully pre-filled task must supply them too.
        "copy_depth": "standard",
        "traffic_source": "facebook ad — 'Scale your coaching to 6 figures'",
        "brief": "a simple 3-page funnel for coaches to generate leads",
    }
    result = run_interview(pre_filled_funnel_task, _recording_ask)
    if result["build_type"] != BUILD_TYPE_FUNNEL:
        failures.append(f"pre-filled funnel: build_type wrong: {result['build_type']!r}")
    if ask_calls:
        failures.append(f"pre-filled funnel: questions asked when none needed: {ask_calls}")
    if not result["interview_complete"]:
        failures.append("pre-filled funnel: interview_complete=False")

    # 5. run_interview — survey, all fields pre-filled
    ask_calls2: List[str] = []
    pre_filled_survey_task = {
        "build_type": "survey",
        "purpose": "intake",
        "capture_fields": "name, email, business stage",
        "response_routing": "sales department",
        "questions": ["Q1", "Q2"],
    }
    result2 = run_interview(pre_filled_survey_task, lambda q: ask_calls2.append(q.qid) or "")
    if result2["build_type"] != BUILD_TYPE_SURVEY:
        failures.append(f"pre-filled survey: build_type wrong")
    if result2["answers"].get("purpose") != "intake":
        failures.append(f"pre-filled survey: purpose wrong: {result2['answers'].get('purpose')!r}")

    # 6. _wants_suggestion
    for phrase in ("you decide", "think for me", "up to you", "not sure", "i don't know"):
        if not _wants_suggestion(phrase):
            failures.append(f"_wants_suggestion({phrase!r}) -> False, expected True")
    for phrase in ("3 pages", "lead generation", "opt-in"):
        if _wants_suggestion(phrase):
            failures.append(f"_wants_suggestion({phrase!r}) -> True, expected False")

    # 7. Option matching
    opts = ("opt-in", "sales", "booking", "thank-you")
    assert _match_option("Opt-In page", opts) == "opt-in", "option match case-insensitive"
    assert _match_option("sales page please", opts) == "sales", "option match substring"
    assert _match_option("something else", opts) is None, "option match no-hit"

    # 8. No Anthropic anywhere in answers or scaffolds
    for bt in KNOWN_BUILD_TYPES:
        scaffold = _scaffold_structure(bt, {})
        scaffold_str = json.dumps(scaffold).lower()
        for marker in ("anthropic", "claude", "opus", "sonnet", "haiku"):
            if marker in scaffold_str:
                failures.append(f"scaffold({bt}) contains Anthropic marker '{marker}'")

    # 9. U055: required field empty -> re-ask with field-specific message.
    _reask_log: list[tuple[str, str]] = []

    def _reask_tracking_ask(q: Question) -> str:
        _reask_log.append((q.qid, q.hint or ""))
        return ""

    _reask_log.clear()
    _req_page_task = {"build_type": "page", "brief": "create a landing page"}
    r9 = run_interview(_req_page_task, _reask_tracking_ask)
    pt_calls = [c for c in _reask_log if c[0] == "page_type"]
    if len(pt_calls) < 3:
        failures.append(
            f"U055: page_type re-ask: expected >=3, got {len(pt_calls)}: {pt_calls}"
        )
    if pt_calls and not any("required" in h.lower() for _, h in pt_calls if h):
        failures.append(f"U055: re-ask hint must include 'required': {pt_calls}")
    if r9.get("answers", {}).get("page_type") != "":
        failures.append(
            f"U055: page_type after exhausted re-asks: "
            f"{r9.get('answers',{}).get('page_type')!r}"
        )

    # 10. U055: required field accepted on re-ask (second attempt).
    _retry_log: list[str] = []

    def _retry_ask(q: Question) -> str:
        _retry_log.append(q.qid)
        if _retry_log.count(q.qid) == 1:
            return ""
        if q.qid == "cta_offer":
            return "download the guide"
        return "sales"

    _retry_log.clear()
    r10 = run_interview({"build_type": "page", "brief": "make a page"}, _retry_ask)
    if _retry_log.count("page_type") < 2:
        failures.append(
            f"U055: page_type re-ask: expected >=2, got {_retry_log.count('page_type')}: "
            f"{_retry_log}"
        )
    if r10.get("answers", {}).get("page_type") != "sales":
        failures.append(
            f"U055: page_type value: {r10.get('answers',{}).get('page_type')!r}"
        )

    # 11. U055 regression: non-required empty answer -> "you decide".
    _opt_log: list[str] = []

    def _opt_ask(q: Question) -> str:
        _opt_log.append(q.qid)
        return ""

    _opt_log.clear()
    r11 = run_interview(
        {"build_type": "page", "page_type": "sales",
         "cta_offer": "download", "brief": "make a page"},
        _opt_ask,
    )
    if r11.get("answers", {}).get("copy_depth") != "you decide":
        failures.append(
            f"U055 regression: copy_depth: {r11.get('answers',{}).get('copy_depth')!r}"
        )
    if "page_type" in _opt_log:
        failures.append(
            f"U055 regression: page_type was re-asked despite being pre-filled: {_opt_log}"
        )

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print("PASS — all intake_interview selftest checks OK")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(_selftest())

    print(__doc__)
