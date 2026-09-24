#!/usr/bin/env python3
"""D03 versioned question/rubric policy packs (JEV spec 1.1, ss 2.2/4.1/4.4/8.6).

Stdlib only. No network, no provider access, no state writes. Validators never
raise on malformed input: a bad pack is an ``(ok=False, errors)`` result, never
an exception (fail-closed). Scoring helpers DO raise ValueError on
missing/invalid answers: per spec 8.6 a bad answer must never become a silent
zero or 0.6.

Layout (this directory is the unit's exclusive lane)::

    policies/
      question_pack.json / task_pack.json / mixed_pack.json / control_pack.json
      packs.d.ts          # TypeScript types for the JSON packs (spec 2.2)
      __init__.py         # this loader (stdlib only)

Each pack carries ``pack_version`` + ``policy_version``: ``policy_version``
matches the D02 envelope ``policyVersion`` so envelope/pack consistency is
testable. Rubrics are descriptive N-level (spec 8.6), never "rate 1-10":
``normalize_score(level, N) == level / (N - 1)``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

PACK_SCHEMA_VERSION = "1.0"
POLICY_VERSION = "decision-policy-v1"
PACK_FILES = (
    "question_pack.json",
    "task_pack.json",
    "mixed_pack.json",
    "control_pack.json",
)
PACK_KINDS = ("question", "task", "mixed", "control")
# Spec 4.1 message-intent values (mirrors contracts/schema.py INTENT_ENUM;
# parity asserted in tests/unit/test_decision_policies.py).
INTENT_ENUM = (
    "answer_only",
    "task_request",
    "mixed_answer_and_task",
    "existing_task_control",
    "clarification_response",
    "social_conversation",
    "unresolved",
)
REQUIRED_PACK_FIELDS = (
    "schemaVersion",
    "pack_id",
    "pack_version",
    "policy_version",
    "kind",
    "departments",
    "roles",
    "questions",
    "rubrics",
    "fixtures",
)


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_finite_number(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, float) and math.isfinite(v)


def _major(v) -> str | None:
    if not isinstance(v, str):
        return None
    parts = v.strip().split(".")
    if not parts or not parts[0].isdigit():
        return None
    if any(not p.isdigit() for p in parts[1:]):
        return None
    return parts[0]


def _find_nonfinite(node, path: str = "$"):
    if isinstance(node, float) and not math.isfinite(node):
        return path
    if isinstance(node, dict):
        for k, v in node.items():
            hit = _find_nonfinite(v, f"{path}.{k}")
            if hit is not None:
                return hit
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            hit = _find_nonfinite(v, f"{path}[{i}]")
            if hit is not None:
                return hit
    return None


def pack_dir() -> Path:
    return Path(__file__).parent


def load_pack(filename: str) -> dict:
    """Load one pack JSON file from this directory."""
    return json.loads((pack_dir() / filename).read_text(encoding="utf-8"))


def iter_packs() -> list[tuple[str, dict]]:
    """Load all four kind packs in stable order."""
    return [(name, load_pack(name)) for name in PACK_FILES]


def validate_pack(pack: dict) -> tuple[bool, list[str]]:
    """Validate a policy pack. Returns ``(ok, errors)``; never raises."""
    try:
        if not isinstance(pack, dict):
            return False, [f"pack is not an object (got {type(pack).__name__})"]
        errors: list[str] = []
        for key in REQUIRED_PACK_FIELDS:
            if key not in pack:
                errors.append(f"missing required key: {key!r}")

        hit = _find_nonfinite(pack)
        if hit is not None:
            errors.append(f"non-finite number at {hit} (NaN/Inf rejected)")

        if _major(pack.get("schemaVersion")) != "1":
            errors.append(
                f"'schemaVersion': incompatible version {pack.get('schemaVersion')!r} "
                "(this loader accepts major 1)"
            )
        if _major(pack.get("pack_version")) != "1":
            errors.append(
                f"'pack_version': incompatible version {pack.get('pack_version')!r} "
                "(major 1 accepted)"
            )
        pid = pack.get("pack_id")
        if not isinstance(pid, str) or not pid.strip():
            errors.append(f"'pack_id': required non-empty string, got {pid!r}")
        pv = pack.get("policy_version")
        if not isinstance(pv, str) or not pv.strip():
            errors.append(f"'policy_version': required non-empty string, got {pv!r}")
        if pack.get("kind") not in PACK_KINDS:
            errors.append(f"'kind': {pack.get('kind')!r} not in {list(PACK_KINDS)}")

        for key in ("departments", "roles"):
            v = pack.get(key)
            if not isinstance(v, list) or not v:
                errors.append(f"{key!r}: required non-empty list, got {v!r}")
            elif any(not isinstance(x, str) or not x.strip() for x in v):
                errors.append(f"{key!r}: every entry must be a non-empty string")

        rubrics = pack.get("rubrics")
        if not isinstance(rubrics, dict) or not rubrics:
            errors.append("'rubrics': required non-empty object")
            rubrics = {}
        for rid, rub in rubrics.items():
            levels = rub.get("levels") if isinstance(rub, dict) else None
            if not isinstance(levels, list) or len(levels) < 2:
                errors.append(f"rubrics[{rid!r}]: required >= 2 levels")
            elif any(not isinstance(s, str) or not s.strip() for s in levels):
                errors.append(f"rubrics[{rid!r}]: every level needs a non-empty description")
            elif len(set(levels)) != len(levels):
                errors.append(f"rubrics[{rid!r}]: levels must be distinct (no 1-10 mush)")

        questions = pack.get("questions")
        if not isinstance(questions, list) or not questions:
            errors.append("'questions': required non-empty list")
            questions = []
        seen_q: set[str] = set()
        for i, q in enumerate(questions):
            if not isinstance(q, dict):
                errors.append(f"questions[{i}]: required object")
                continue
            qid = q.get("question_id")
            if not isinstance(qid, str) or not qid.strip():
                errors.append(f"questions[{i}]: required non-empty 'question_id'")
            elif qid in seen_q:
                errors.append(f"questions[{i}]: duplicate question_id {qid!r}")
            else:
                seen_q.add(qid)
            if not isinstance(q.get("prompt"), str) or not q["prompt"].strip():
                errors.append(f"questions[{i}]: required non-empty 'prompt'")
            w = q.get("weight")
            if not _is_finite_number(w) or w < 0:
                errors.append(f"questions[{i}]: required finite 'weight' >= 0, got {w!r}")
            has_choices = isinstance(q.get("choices"), list)
            has_rubric = isinstance(q.get("rubric"), str)
            if has_choices == has_rubric:
                errors.append(
                    f"questions[{i}]: exactly one of 'choices' / 'rubric' required"
                )
            if has_choices:
                if not q["choices"] or any(
                    not isinstance(c, str) or not c.strip() for c in q["choices"]
                ):
                    errors.append(f"questions[{i}]: 'choices' needs non-empty strings")
                if isinstance(qid, str) and qid.startswith("q_intent_"):
                    bad = [c for c in q["choices"] if c not in INTENT_ENUM]
                    if bad:
                        errors.append(f"questions[{i}]: choices {bad} not in intent enum")
            if has_rubric and q["rubric"] not in rubrics:
                errors.append(f"questions[{i}]: rubric {q['rubric']!r} not defined")

        fixtures = pack.get("fixtures")
        if not isinstance(fixtures, list) or not fixtures:
            errors.append("'fixtures': required non-empty list")
        else:
            for i, f in enumerate(fixtures):
                if not isinstance(f, dict):
                    errors.append(f"fixtures[{i}]: required object")
                    continue
                if not isinstance(f.get("message"), str) or not f["message"].strip():
                    errors.append(f"fixtures[{i}]: required non-empty 'message'")
                if f.get("expected_intent") not in INTENT_ENUM:
                    errors.append(
                        f"fixtures[{i}]: expected_intent {f.get('expected_intent')!r} "
                        f"not in {list(INTENT_ENUM)}"
                    )
                note = f.get("note")
                if note is not None and not isinstance(note, str):
                    errors.append(f"fixtures[{i}]: 'note' must be a string")

        return (len(errors) == 0), errors
    except Exception as exc:  # fail-closed: validator never raises
        return False, [f"validator error: {exc}"]


def canonical_pack_json(pack: dict) -> str:
    """Deterministic canonical JSON: sorted keys, compact separators.

    Raises ValueError on non-finite floats (allow_nan=False) — fail-closed
    serialization: such packs are invalid and must never be persisted.
    """
    return (
        json.dumps(
            pack,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def normalize_score(level: int, levels: int) -> float:
    """N-level score to [0, 1]: ``level / (levels - 1)`` (spec 8.6).

    Raises ValueError on any missing/invalid input — never a silent 0 or 0.6.
    """
    if not _is_int(level) or not _is_int(levels):
        raise ValueError(f"level/levels must be ints, got {level!r}/{levels!r}")
    if levels < 2:
        raise ValueError(f"levels must be >= 2, got {levels}")
    if not 0 <= level < levels:
        raise ValueError(f"level {level} out of range for {levels} levels")
    return level / (levels - 1)


def aggregate_fit(dims: dict[str, dict]) -> dict:
    """Weighted aggregate over applicable dimensions (spec 8.6).

    ``dims`` maps dimension name to ``{"level": int, "levels": int,
    "weight": number}``. Returns ``{"aggregate": float, "distribution": {dim:
    normalized}, "total_weight": float}``. Distribution and aggregate stay
    separate; a normalized score is not a calibrated probability. Raises
    ValueError on empty input, non-positive total weight, or any bad entry.
    """
    if not isinstance(dims, dict) or not dims:
        raise ValueError("dims must be a non-empty object")
    distribution: dict[str, float] = {}
    weights: dict[str, float] = {}
    for dim, spec in dims.items():
        if not isinstance(spec, dict):
            raise ValueError(f"dim {dim!r}: spec must be an object")
        try:
            level, nlevels, weight = spec["level"], spec["levels"], spec["weight"]
        except KeyError as exc:
            raise ValueError(f"dim {dim!r}: missing key {exc}") from exc
        norm = normalize_score(level, nlevels)  # raises on bad level/levels
        if not _is_finite_number(weight) or weight < 0:
            raise ValueError(f"dim {dim!r}: weight must be finite >= 0, got {weight!r}")
        distribution[dim] = norm
        weights[dim] = weight
    total = math.fsum(weights.values())
    if total <= 0:
        raise ValueError("total applicable weight must be > 0")
    aggregate = math.fsum(distribution[d] * weights[d] for d in distribution) / total
    return {"aggregate": aggregate, "distribution": distribution, "total_weight": total}


def fixture_lookup(message: str, packs: list[dict]) -> str | None:
    """Exact-match fixture lookup: known 4.4 message -> expected intent.

    Returns None for anything not in the packs. Unknown input is never
    guessed — the caller must route it to a real classifier, not a phantom.
    """
    for pack in packs:
        if not isinstance(pack, dict):
            continue
        for f in pack.get("fixtures") or []:
            if isinstance(f, dict) and f.get("message") == message:
                return f.get("expected_intent")
    return None
