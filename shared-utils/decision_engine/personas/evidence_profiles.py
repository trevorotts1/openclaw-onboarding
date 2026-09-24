#!/usr/bin/env python3
"""D16 persona evidence profiles (JEV spec 1.1, ss 8.1/8.2/8.3 + 10.2).

Per-responsibility evidence for the five communication responsibilities
(audience, voice, topic, task-part, outcome). Profiles stay SEPARATE per
responsibility — never a merged pool. Audience resolution follows the 8.3
priority (explicit > prior-confirmed > company-proposal > needs-clarification);
confidence never grants consent. Blend applicability follows 8.2: bare keywords
(write/script/post/video) never force a voice, answers never fill task-persona
slots. Emitted task-persona rows match the D02 contract
(contracts/schema.py task_personas rules: int seq, persona_id-or-governance,
up-to-10 cap).

Stdlib only. No network, no provider access, no state writes. Validators never
raise on malformed input: a bad profile/rows is ``(ok=False, errors)``, never
an exception (fail-closed). Builders (make_profile, resolve_audience) DO raise
ValueError on bad enums, mirroring D03 scoring: a bad answer must never become
a silent default.

ponytail: signal lists below are lexical heuristics, ceiling is keyword
coverage; upgrade path is a real classifier/JEV judgment feeding the same
profile schema (no API change).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Spec 8.1: five distinct responsibilities. Never confused, never merged.
RESPONSIBILITIES = ("audience", "voice", "topic", "task_part", "outcome")

# Spec 8.3: audience provenance states, per responsibility.
RESOLUTION_STATES = (
    "explicit",
    "prior_confirmed",
    "company_proposal",
    "needs_clarification",
)

# Explicit + valid prior need no re-ask (stop asking when owner answered).
CONFIRMED_STATES = ("explicit", "prior_confirmed")

CONFIDENCE_LEVELS = ("none", "low", "medium", "high")

# Spec 8.2: bare trigger words that must NEVER alone force a voice.
KEYWORD_TRIGGERS = ("write", "script", "post", "video")

# Matches D02 contracts/schema.py MAX_TASK_PERSONAS (parity asserted in tests).
MAX_TASK_PERSONAS = 10

DEFAULT_GOVERNANCE_PERSONA_ID = "covey-7-habits"

ANSWER_INTENTS = frozenset({"answer_only", "social_conversation"})
AUDIENCE_FACING_INTENTS = frozenset({
    "campaign", "audience_copy", "episode", "announcement", "sales", "content",
})
OPERATIONAL_INTENTS = frozenset({"operational", "maintenance"})
CODE_INTENTS = frozenset({"code", "code_task"})

_AUDIENCE_SIGNALS = (
    "sales email", "nurture", "newsletter", "landing page", "ad copy",
    "campaign", "announcement", "blog post", "social post", "episode script",
    "webinar", "vsl",
)
_CODE_SIGNALS = (
    "python script", ".py", "traceback", "def ", "import ", "compile",
    "unit test", "refactor", "parse csv", "parse json",
)
_MECHANICAL_SIGNALS = (
    "chmod", "file path", "repair", "permission", "mkdir", "move file",
    "rename file", "disk", "backup", "symlink",
)
_ANSWER_SIGNALS = (
    "explain", "what is", "what are", "how does", "define",
    "teach me", "in chat",
)


@dataclass
class PersonaEvidenceProfile:
    """Evidence for ONE responsibility. Never shared across responsibilities."""

    responsibility: str = ""
    resolution: str = ""
    evidence_refs: list = field(default_factory=list)
    confidence: str = "none"
    confirm_required: bool = True
    detail: str = ""
    scope_id: str = ""


def confirm_required_for(resolution: str) -> bool:
    """Lockstep: explicit/prior-confirmed need no re-ask; else confirm."""
    if resolution in CONFIRMED_STATES:
        return False
    if resolution in ("company_proposal", "needs_clarification"):
        return True
    raise ValueError(f"unknown resolution {resolution!r}")


def make_profile(
    responsibility: str,
    resolution: str,
    *,
    evidence_refs: tuple | list = (),
    confidence: str = "none",
    detail: str = "",
    scope_id: str = "",
) -> PersonaEvidenceProfile:
    """Build one profile. Raises ValueError on bad enums (never silent)."""
    if responsibility not in RESPONSIBILITIES:
        raise ValueError(f"responsibility {responsibility!r} not in {list(RESPONSIBILITIES)}")
    if resolution not in RESOLUTION_STATES:
        raise ValueError(f"resolution {resolution!r} not in {list(RESOLUTION_STATES)}")
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"confidence {confidence!r} not in {list(CONFIDENCE_LEVELS)}")
    refs = list(evidence_refs) if isinstance(evidence_refs, (list, tuple)) else None
    if refs is None or any(not isinstance(r, str) or not r.strip() for r in refs):
        raise ValueError("evidence_refs must be a list/tuple of non-empty strings")
    return PersonaEvidenceProfile(
        responsibility=responsibility,
        resolution=resolution,
        evidence_refs=refs,
        confidence=confidence,
        confirm_required=confirm_required_for(resolution),
        detail=detail if isinstance(detail, str) else "",
        scope_id=scope_id if isinstance(scope_id, str) else "",
    )


def validate_profile(profile) -> tuple[bool, list[str]]:
    """Validate one profile. Returns ``(ok, errors)``; never raises."""
    try:
        if not isinstance(profile, PersonaEvidenceProfile):
            return False, [f"profile is not a PersonaEvidenceProfile (got {type(profile).__name__})"]
        errors: list[str] = []
        if profile.responsibility not in RESPONSIBILITIES:
            errors.append(f"'responsibility': {profile.responsibility!r} not in {list(RESPONSIBILITIES)}")
        if profile.resolution not in RESOLUTION_STATES:
            errors.append(f"'resolution': {profile.resolution!r} not in {list(RESOLUTION_STATES)}")
        if profile.confidence not in CONFIDENCE_LEVELS:
            errors.append(f"'confidence': {profile.confidence!r} not in {list(CONFIDENCE_LEVELS)}")
        refs = profile.evidence_refs
        if not isinstance(refs, list):
            errors.append(f"'evidence_refs': required list, got {type(refs).__name__}")
        elif profile.resolution != "needs_clarification" and not refs:
            errors.append("'evidence_refs': required non-empty (only needs_clarification may carry none)")
        elif any(not isinstance(r, str) or not r.strip() for r in refs):
            errors.append("'evidence_refs': every entry must be a non-empty string")
        if profile.confirm_required is not True and profile.confirm_required is not False:
            errors.append("'confirm_required': required boolean")
        elif (
            profile.resolution in RESOLUTION_STATES
            and profile.confirm_required != confirm_required_for(profile.resolution)
        ):
            errors.append(
                f"'confirm_required'={profile.confirm_required!r} breaks lockstep for "
                f"resolution={profile.resolution!r} (confidence is not consent)"
            )
        if not isinstance(profile.detail, str):
            errors.append(f"'detail': required string, got {type(profile.detail).__name__}")
        if not isinstance(profile.scope_id, str):
            errors.append(f"'scope_id': required string, got {type(profile.scope_id).__name__}")
        return (len(errors) == 0), errors
    except Exception as exc:  # fail-closed: validator never raises
        return False, [f"validator error: {exc}"]


def resolve_audience(
    *,
    explicit=None,
    prior: dict | None = None,
    company=None,
    scope_id: str = "",
    confidence: str = "none",
) -> PersonaEvidenceProfile:
    """Spec 8.3 priority: explicit > valid prior > company proposal > clarify.

    A prior confirmation counts only for the same scope with unchanged audience
    data. ``confidence`` is recorded, never acted on: a high-confidence guess
    still requires confirmation (confidence is not consent).
    """
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"confidence {confidence!r} not in {list(CONFIDENCE_LEVELS)}")
    scope = scope_id if isinstance(scope_id, str) else ""
    if isinstance(explicit, str) and explicit.strip():
        return make_profile(
            "audience", "explicit",
            evidence_refs=[f"explicit:{explicit.strip()}"],
            confidence=confidence, scope_id=scope,
            detail=f"explicit audience supplied: {explicit.strip()}",
        )
    if isinstance(prior, dict):
        label = prior.get("label")
        if (
            isinstance(label, str) and label.strip()
            and prior.get("scope_match") is True
            and prior.get("data_unchanged") is True
        ):
            return make_profile(
                "audience", "prior_confirmed",
                evidence_refs=[f"prior:{label.strip()}"],
                confidence=confidence, scope_id=scope,
                detail=f"prior confirmation reused (same scope, unchanged data): {label.strip()}",
            )
    if isinstance(company, str) and company.strip():
        return make_profile(
            "audience", "company_proposal",
            evidence_refs=[f"company:{company.strip()}"],
            confidence=confidence, scope_id=scope,
            detail=f"company/onboarding audience as proposal (needs confirmation): {company.strip()}",
        )
    return make_profile(
        "audience", "needs_clarification",
        evidence_refs=[],
        confidence=confidence, scope_id=scope,
        detail="Single focused clarification required: who is this specific work for?",
    )


def assess_blend_applicability(
    message,
    *,
    artifact_intent: str = "unknown",
    task_type: str = "unknown",
    has_audience_hint: bool = False,
) -> dict:
    """Spec 8.2: is audience-facing communication being created?

    Returns ``mode`` in blend/mixed/task_only/mechanical/answer/unresolved.
    Bare keywords never force a voice; mixed operational+content work is never
    persona-free in its entirety; professional work never goes persona-free
    merely for containing an operational verb. Never raises.
    """
    def _unresolved(reason: str, note: str) -> dict:
        return {
            "mode": "unresolved",
            "audience_facing": False,
            "task_persona_needed": False,
            "answer_only": False,
            "mechanical_only": False,
            "reason_code": reason,
            "note": note,
        }

    try:
        text = message.lower() if isinstance(message, str) else ""
        intent = artifact_intent if isinstance(artifact_intent, str) else "unknown"
        ttype = task_type if isinstance(task_type, str) else "unknown"
        aud = (
            has_audience_hint is True
            or intent in AUDIENCE_FACING_INTENTS
            or any(s in text for s in _AUDIENCE_SIGNALS)
        )
        code = intent in CODE_INTENTS or any(s in text for s in _CODE_SIGNALS)
        mech = intent in OPERATIONAL_INTENTS or any(s in text for s in _MECHANICAL_SIGNALS)
        answ = (ttype in ANSWER_INTENTS) or (
            any(s in text for s in _ANSWER_SIGNALS) and not aud
        )

        def _base(mode, **kw) -> dict:
            out = {
                "mode": mode,
                "audience_facing": False,
                "task_persona_needed": False,
                "answer_only": False,
                "mechanical_only": False,
                "reason_code": "",
                "note": "",
            }
            out.update(kw)
            return out

        if aud and (mech or code):
            return _base(
                "mixed", audience_facing=True, task_persona_needed=True,
                reason_code="mixed-content-preserved",
                note="content parts keep voice/topic/task blend; operational parts carry light governance only",
            )
        if aud:
            return _base(
                "blend", audience_facing=True, task_persona_needed=True,
                reason_code="audience-facing-copy",
                note="audience/topic/task blend appropriate",
            )
        if answ:
            return _base(
                "answer", answer_only=True,
                reason_code="answer-not-task-persona",
                note="an answer, not a routed campaign; no task-persona slots consumed",
            )
        if mech:
            return _base(
                "mechanical", mechanical_only=True,
                reason_code="operational-governance-only",
                note="operational task: light governance, no full expert blueprint",
            )
        if code:
            return _base(
                "task_only", task_persona_needed=True,
                reason_code="code-is-not-copy",
                note="code/task work is not automatically audience-facing copy",
            )
        if any(k in text for k in KEYWORD_TRIGGERS) or not text.strip():
            return _unresolved(
                "keyword-alone-insufficient",
                "bare write/script/post/video with no audience evidence never requires a content voice",
            )
        return _unresolved("insufficient-evidence", "no audience, code, mechanical, or answer signal found")
    except Exception as exc:  # fail-closed
        return _unresolved("assessor-error", f"assessor failed closed: {exc}")


def build_task_persona_rows(
    parts,
    *,
    intent: str = "task_request",
    default_governance: str = DEFAULT_GOVERNANCE_PERSONA_ID,
) -> tuple[bool, list[dict], list[str]]:
    """Emit D02-compatible task-persona rows. Fail-closed: never raises.

    Answer intents never fill slots. Cap enforced at 10. ``seq`` auto-assigned
    1..n (unique). ``no_persona_required`` rows carry governance, never a
    persona_id — mirroring contracts/schema.py ``_check_task_personas``.
    """
    try:
        if not isinstance(parts, list):
            return False, [], [f"parts must be a list (got {type(parts).__name__})"]
        if not isinstance(intent, str):
            return False, [], [f"intent must be a string (got {type(intent).__name__})"]
        if intent in ANSWER_INTENTS:
            if parts:
                return False, [], [
                    f"intent={intent!r}: an answer must not fill task-persona slots "
                    f"({len(parts)} part(s) supplied)"
                ]
            return True, [], []
        if len(parts) > MAX_TASK_PERSONAS:
            return False, [], [
                f"task_personas: {len(parts)} rows exceed up-to-{MAX_TASK_PERSONAS} cap"
            ]
        rows: list[dict] = []
        for i, p in enumerate(parts):
            where = f"parts[{i}]"
            if not isinstance(p, dict):
                return False, [], [f"{where}: required object"]
            part = p.get("part")
            if not isinstance(part, str) or not part.strip():
                return False, [], [f"{where}.part: required non-empty string"]
            no_persona = p.get("no_persona_required", False)
            if no_persona is not True and no_persona is not False:
                return False, [], [f"{where}.no_persona_required: required boolean"]
            why = p.get("why", "")
            if not isinstance(why, str):
                return False, [], [f"{where}.why: required string"]
            category = p.get("task_category", "")
            if not isinstance(category, str):
                return False, [], [f"{where}.task_category: required string"]
            if no_persona:
                if p.get("persona_id") is not None:
                    return False, [], [f"{where}: no_persona_required with persona_id set"]
                gov = p.get("governance_persona_id") or default_governance
                if not isinstance(gov, str) or not gov.strip():
                    return False, [], [f"{where}.governance_persona_id: required non-empty string"]
                rows.append({
                    "seq": i + 1,
                    "part": part.strip(),
                    "persona_id": None,
                    "why": why,
                    "no_persona_required": True,
                    "governance_persona_id": gov.strip(),
                    "task_category": category,
                })
            else:
                pid = p.get("persona_id")
                if not isinstance(pid, str) or not pid.strip():
                    return False, [], [f"{where}.persona_id: required non-empty string"]
                gov = p.get("governance_persona_id")
                if gov is not None and (not isinstance(gov, str) or not gov.strip()):
                    return False, [], [f"{where}.governance_persona_id: required non-empty string or null"]
                rows.append({
                    "seq": i + 1,
                    "part": part.strip(),
                    "persona_id": pid.strip(),
                    "why": why,
                    "no_persona_required": False,
                    "governance_persona_id": gov,
                    "task_category": category,
                })
        return True, rows, []
    except Exception as exc:  # fail-closed: builder never raises
        return False, [], [f"builder error: {exc}"]


def build_evidence_set(profiles) -> tuple[bool, dict, list[str]]:
    """One profile per responsibility, each a distinct object. Never raises.

    Rejects merged-pool input: a single shared profile (or one resolution)
    covering several responsibilities.
    """
    try:
        if not isinstance(profiles, (list, tuple)):
            return False, {}, [f"profiles must be a list (got {type(profiles).__name__})"]
        if len(profiles) != len(RESPONSIBILITIES):
            return False, {}, [
                f"evidence set needs exactly {len(RESPONSIBILITIES)} profiles "
                f"(one per responsibility), got {len(profiles)}"
            ]
        for i, p in enumerate(profiles):
            ok, errs = validate_profile(p)
            if not ok:
                return False, {}, [f"profiles[{i}]: {e}" for e in errs]
        seen_ids: set[int] = set()
        for p in profiles:
            if id(p) in seen_ids:
                return False, {}, ["merged pool rejected: one profile object shared across responsibilities"]
            seen_ids.add(id(p))
        mapping = {p.responsibility: p for p in profiles}
        if set(mapping) != set(RESPONSIBILITIES):
            return False, {}, [
                f"responsibilities {sorted(mapping)} do not cover {list(RESPONSIBILITIES)}"
            ]
        return True, mapping, []
    except Exception as exc:  # fail-closed
        return False, {}, [f"builder error: {exc}"]


def voice_basis_ok(*, demographic_tags=(), suitability_evidence=()) -> bool:
    """Spec 8.3: voice never chosen from demographic stereotypes alone.

    A matching demographic word is not proof of an appropriate voice: explicit
    audience needs, context, brand preferences, or documented suitability must
    back it. Never raises (garbage returns False).
    """
    try:
        demo = tuple(demographic_tags) if isinstance(demographic_tags, (list, tuple)) else None
        suit = tuple(suitability_evidence) if isinstance(suitability_evidence, (list, tuple)) else None
        if demo is None or suit is None:
            return False
        if demo and not any(isinstance(s, str) and s.strip() for s in suit):
            return False
        return True
    except Exception:
        return False
