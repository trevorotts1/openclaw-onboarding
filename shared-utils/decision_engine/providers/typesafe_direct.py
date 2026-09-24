#!/usr/bin/env python3
"""D04 TypeSafe direct transport (JEV spec 1.1, sections 3.1/3.2/3.4/3.7).

Stdlib only. No network at import. No disk reads. No ``os.environ`` reads
or writes: the caller resolves the credential from approved company-scoped
stores and passes the value in explicitly.

Contract points (spec ranges 3.1/3.2, 3.4, 3.7):

* Endpoint ``POST https://api.typesafe.ai/v1/systemone``, pinned request
  model ``jev-1.13.0``. Decisions API, NOT chat completions: the body is
  exactly ``{model, state, questions}``. ``messages``, ``reasoning_effort``,
  ``temperature`` and tool-call semantics are never sent.
* Direct key name is ``TYPESAFE_API_KEY``; ``JEV_API_KEY`` is the explicitly
  documented project compatibility alias (not TypeSafe's native SDK name).
  Key presence means ``configured``, never ``verified working``. Empty,
  placeholder and malformed-reference values are rejected before any call.
  Key material never appears in results, diagnostics or logs.
* Response normalization (3.7): required question IDs, matching answer
  types, allowed candidate IDs, finite numbers, bounds, complete expected
  probability keys, approximate unit-sum with documented tolerance
  (``UNIT_SUM_TOLERANCE``). Score validated against caller-supplied ordered
  levels, never a hardcoded 0-10 range. ``noul`` carries a probability value
  and no confidence field is ever synthesized. Unknown extra metadata is
  preserved verbatim. A bad judgment is rejected with a diagnostic, never
  coerced into a winner. One documented repack (``MAX_REPACKS = 1``) or the
  no-JEV fallback — never an unbounded retry loop.
* HTTP outcomes map to the 3.4 handling table (auth_rejected,
  rate_limited, overloaded, network_error, timeout, integration_defect);
  this module performs ONE attempt per call and never replays.
"""

from __future__ import annotations

import copy
import json
import math
import urllib.error
import urllib.request

# ── pinned contract (spec 3.2) ───────────────────────────────────────────
TYPESAFE_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
TYPESAFE_MODEL = "jev-1.13.0"

DIRECT_KEY_PRIMARY = "TYPESAFE_API_KEY"
DIRECT_KEY_ALIAS = "JEV_API_KEY"  # documented project alias, not native SDK name
DIRECT_KEY_NAMES = (DIRECT_KEY_PRIMARY, DIRECT_KEY_ALIAS)

REQUIRED_BODY_KEYS = ("model", "state", "questions")
# Chat-completion semantics that must never ride a decisions request (3.2).
FORBIDDEN_BODY_KEYS = frozenset({
    "messages",
    "reasoning_effort",
    "temperature",
    "tools",
    "tool_calls",
    "functions",
    "function_call",
})

# ── normalization + packing bounds (spec 3.7) ────────────────────────────
UNIT_SUM_TOLERANCE = 1e-6
PACKING_TARGET_TOKENS = 24000  # conservative common target until measured
DIRECT_HARD_LIMIT_STATE_ALL = 64000  # state + all questions
DIRECT_HARD_LIMIT_STATE_LONGEST = 32000  # state + longest question
MAX_REPACKS = 1  # one documented repack, then no-JEV fallback
ESTIMATOR_LABEL = "conservative-chars/4 (estimate, not a tokenizer)"

DEFAULT_TIMEOUT_S = 2.5
LOW_CONFIDENCE_DEFAULT_MIN_TOP_PROB = 0.6

# Values that are references/placeholders, never transmittable secrets.
_MALFORMED_PREFIXES = ("$", "${", "@", "file:", "ref:", "secret:", "arn:")
_PLACEHOLDER_MARKERS = (
    "PASTE", "TODO", "CHANGE_ME", "CHANGEME", "EXAMPLE", "YOUR_",
    "REPLACE", "SAMPLE", "XXX", "DUMMY", "<", ">", "...",
)

try:  # reuse repo secret predicates where available (spec 3.3)
    from secret_helper import looks_like_real_key as _canon_real_key
    from secret_helper import is_placeholder as _canon_placeholder
    _CANON = True
except Exception:
    _CANON = False

__all__ = [
    "TYPESAFE_ENDPOINT",
    "TYPESAFE_MODEL",
    "DIRECT_KEY_PRIMARY",
    "DIRECT_KEY_ALIAS",
    "DIRECT_KEY_NAMES",
    "REQUIRED_BODY_KEYS",
    "FORBIDDEN_BODY_KEYS",
    "UNIT_SUM_TOLERANCE",
    "PACKING_TARGET_TOKENS",
    "DIRECT_HARD_LIMIT_STATE_ALL",
    "DIRECT_HARD_LIMIT_STATE_LONGEST",
    "MAX_REPACKS",
    "ESTIMATOR_LABEL",
    "DEFAULT_TIMEOUT_S",
    "LOW_CONFIDENCE_DEFAULT_MIN_TOP_PROB",
    "resolve_direct_key",
    "describe_availability",
    "build_request",
    "check_body_clean",
    "estimate_tokens",
    "request_estimate_tokens",
    "packing_verdict",
    "batch_questions",
    "normalize_response",
    "post_decisions",
    "is_approved_model",
]


def _is_usable_value(value: object) -> tuple[bool, str]:
    """(usable, reason) for a candidate credential string. Never logs value."""
    if not isinstance(value, str) or not value.strip():
        return False, "empty_value"
    v = value.strip()
    if v.startswith(_MALFORMED_PREFIXES):
        return False, "malformed_reference"
    if _CANON:
        try:
            if _canon_placeholder(v) or not _canon_real_key(v):
                return False, "placeholder_value"
        except Exception:
            pass
    elif (
        any(m in v.upper() for m in _PLACEHOLDER_MARKERS)
        or len(v) < 8
    ):
        return False, "placeholder_value"
    return True, "usable"


def resolve_direct_key(mapping: dict) -> dict:
    """Resolve direct credential from an explicit caller-built mapping.

    Tries ``TYPESAFE_API_KEY`` then the ``JEV_API_KEY`` alias. Returns
    ``{"state", "key_name", "value", "reason"}``; ``state`` is
    ``"configured"`` or ``"absent"``. ``reason`` is a machine code, never
    the value. ``mapping`` is read-only; global environment untouched.
    """
    if not isinstance(mapping, dict):
        return {"state": "absent", "key_name": None,
                "value": None, "reason": "no_mapping"}
    first_problem = "absent"
    for name in DIRECT_KEY_NAMES:
        if name not in mapping:
            continue
        ok, reason = _is_usable_value(mapping[name])
        if ok:
            return {"state": "configured", "key_name": name,
                    "value": mapping[name].strip(), "reason": "usable_value"}
        if first_problem == "absent":
            first_problem = reason
    return {"state": "absent", "key_name": None,
            "value": None, "reason": first_problem}


def describe_availability(mapping: dict) -> dict:
    """Presence report: ``configured`` never implies ``verified working``."""
    resolved = resolve_direct_key(mapping)
    return {
        "provider": "typesafe_direct",
        "endpoint": TYPESAFE_ENDPOINT,
        "model": TYPESAFE_MODEL,
        "state": resolved["state"],
        "key_name": resolved["key_name"],
        "verified": False,
    }


def build_request(state: dict, questions: list, model: str = TYPESAFE_MODEL) -> dict:
    """Build the exact decisions body ``{model, state, questions}``.

    Raises ``ValueError``/``TypeError`` on bad inputs (caller bug, not a
    transport outcome). Deep-copies inputs so later caller mutation cannot
    alter the packed body.
    """
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string")
    if not isinstance(state, dict):
        raise TypeError(f"state must be an object, got {type(state).__name__}")
    if not isinstance(questions, list) or not questions:
        raise ValueError("questions must be a non-empty list")
    seen = set()
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            raise TypeError(f"questions[{i}] must be an object")
        qid, qtype = q.get("id"), q.get("type")
        if not isinstance(qid, str) or not qid.strip():
            raise ValueError(f"questions[{i}]: required non-empty 'id'")
        if not isinstance(qtype, str) or not qtype.strip():
            raise ValueError(f"questions[{i}]: required non-empty 'type'")
        if qid in seen:
            raise ValueError(f"questions[{i}]: duplicate id {qid!r}")
        seen.add(qid)
    return {"model": model, "state": copy.deepcopy(state),
            "questions": copy.deepcopy(questions)}


def check_body_clean(body: dict) -> list[str]:
    """Violations in a decisions body; empty list means clean to send."""
    violations: list[str] = []
    if not isinstance(body, dict):
        return ["body_not_object"]
    for key in REQUIRED_BODY_KEYS:
        if key not in body:
            violations.append(f"missing required key: {key!r}")
    for key in sorted(FORBIDDEN_BODY_KEYS & set(body)):
        violations.append(f"forbidden chat-completion key: {key!r}")
    return violations


def estimate_tokens(node: object) -> int:
    """Conservative token estimate: ``len(chars) // 4``, minimum 1."""
    try:
        text = json.dumps(node, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(node)
    return max(1, len(text) // 4)


def request_estimate_tokens(state: dict, questions: list,
                            instructions: str = "") -> int:
    """Estimated total for state + questions + instructions (all count)."""
    total = estimate_tokens(state) + estimate_tokens(questions)
    if instructions:
        total += estimate_tokens(instructions)
    return total


def packing_verdict(state: dict, questions: list,
                    instructions: str = "") -> dict:
    """Packing verdict against the 3.7 bounds; ``max_repacks`` is always 1."""
    longest = max((estimate_tokens(q) for q in questions), default=0)
    estimated = request_estimate_tokens(state, questions, instructions)
    return {
        "estimator": ESTIMATOR_LABEL,
        "estimated_tokens": estimated,
        "fits_target": estimated <= PACKING_TARGET_TOKENS,
        "fits_hard": (
            estimated <= DIRECT_HARD_LIMIT_STATE_ALL
            and estimate_tokens(state) + longest
            <= DIRECT_HARD_LIMIT_STATE_LONGEST
        ),
        "max_repacks": MAX_REPACKS,
    }


def batch_questions(questions: list, state: dict, instructions: str = "",
                    target: int = PACKING_TARGET_TOKENS) -> list[list]:
    """Greedy bounded batches; an oversize single question keeps its own batch.

    The caller may then perform the ONE documented repack (compact shared
    state) or take the no-JEV fallback. This function never loops retries.
    """
    base = estimate_tokens(state) + (estimate_tokens(instructions)
                                     if instructions else 0)
    batches: list[list] = []
    current: list = []
    current_tokens = base
    for q in questions:
        cost = estimate_tokens(q)
        if current and current_tokens + cost > target:
            batches.append(current)
            current, current_tokens = [], base
        current.append(q)
        current_tokens += cost
    if current:
        batches.append(current)
    return batches


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


def normalize_response(payload: dict, question_specs: dict,
                       min_top_prob: float = LOW_CONFIDENCE_DEFAULT_MIN_TOP_PROB
                       ) -> tuple[bool, list | None, list]:
    """Strict-normalize a decisions payload. Never raises on bad payload.

    ``question_specs`` maps ``question_id`` to
    ``{"type": "select"|"score"|"noul", "candidates": [...],
    "levels": [...], "prob_keys": [...]}`` (``prob_keys`` defaults to
    ``candidates`` for ``select``). Returns ``(ok, judgments, diagnostics)``.
    ``ok=True`` may still carry a ``low_confidence`` warning entry; a bad
    judgment yields ``(False, None, diagnostics)`` — rejected, never coerced.
    Unknown extra metadata is preserved verbatim. No ``confidence`` field is
    ever synthesized.
    """
    diags: list = []

    def bad(code: str, qid, detail: str):
        diags.append({"question_id": qid, "code": code, "detail": detail})
        return False, None, diags

    if not isinstance(payload, dict):
        return bad("malformed", None, "payload is not an object")
    if not isinstance(question_specs, dict) or not question_specs:
        return bad("malformed", None, "question_specs must be non-empty")
    judgments = payload.get("judgments")
    if not isinstance(judgments, list) or not judgments:
        return bad("missing_answer", None,
                   "'judgments' must be a non-empty list")

    by_id = {}
    for j in judgments:
        if isinstance(j, dict) and isinstance(j.get("question_id"), str):
            by_id.setdefault(j["question_id"], j)

    normalized: list = []
    for qid, spec in question_specs.items():
        if not isinstance(spec, dict) or spec.get("type") not in (
                "select", "score", "noul"):
            return bad("malformed", qid, "spec needs type select|score|noul")
        if qid not in by_id:
            return bad("missing_answer", qid, "no judgment for question")
        j = by_id[qid]
        if not isinstance(j, dict):
            return bad("malformed", qid, "judgment is not an object")
        if j.get("type", spec["type"]) != spec["type"]:
            return bad("type_mismatch", qid,
                       f"answer type {j.get('type')!r} != {spec['type']!r}")
        hit = _find_nonfinite(j)
        if hit is not None:
            return bad("nonfinite", qid, f"non-finite number at {hit}")
        out = copy.deepcopy(j)
        out["type"] = spec["type"]

        if spec["type"] == "select":
            candidates = spec.get("candidates")
            if not isinstance(candidates, list) or not candidates:
                return bad("malformed", qid, "select needs 'candidates'")
            answer = j.get("answer")
            if answer not in candidates:
                return bad("wrong_candidate", qid,
                           f"answer {answer!r} not in allowed candidates")
            keys = spec.get("prob_keys", candidates)
            probs = j.get("probabilities")
            if not isinstance(probs, dict):
                return bad("missing_answer", qid,
                           "'probabilities' required for select")
            if set(probs) != set(keys):
                return bad("incomplete_prob_keys", qid,
                           f"keys {sorted(probs)} != expected {sorted(keys)}")
            for k, p in probs.items():
                if isinstance(p, bool) or not isinstance(p, (int, float)):
                    return bad("malformed", qid,
                               f"probability {k!r} is not a number")
                if not 0.0 <= p <= 1.0:
                    return bad("out_of_bounds", qid,
                               f"probability {k!r}={p!r} outside [0,1]")
            if abs(sum(probs.values()) - 1.0) > UNIT_SUM_TOLERANCE:
                return bad("unit_sum_fail", qid,
                           f"probabilities sum to {sum(probs.values())!r}")
            if max(probs.values()) < min_top_prob:
                diags.append({"question_id": qid, "code": "low_confidence",
                              "detail": "valid but low top probability; use "
                                        "uncertainty handling, not another "
                                        "JEV endpoint"})
        elif spec["type"] == "score":
            levels = spec.get("levels")
            if not isinstance(levels, list) or not levels:
                return bad("malformed", qid, "score needs ordered 'levels'")
            value = j.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return bad("missing_answer", qid, "'value' required for score")
            if value not in levels:
                return bad("out_of_levels", qid,
                           f"value {value!r} not in ordered levels")
        else:  # noul: probability value, no confidence synthesis
            prob = j.get("probability")
            if isinstance(prob, bool) or not isinstance(prob, (int, float)):
                return bad("missing_answer", qid,
                           "'probability' required for noul")
            if not 0.0 <= prob <= 1.0:
                return bad("out_of_bounds", qid,
                           f"probability {prob!r} outside [0,1]")
        out.pop("confidence", None)  # never synthesize or echo confidence
        normalized.append(out)

    result: dict = {"judgments": normalized}
    for key, value in payload.items():
        if key != "judgments":
            result[key] = copy.deepcopy(value)  # preserve unknown metadata
    return True, normalized, diags


def _default_http_post(url: str, body: bytes, headers: dict,
                       timeout_s: float) -> tuple[int, dict | None]:
    """Single urllib POST. Returns (status, parsed-json-or-None)."""
    req = urllib.request.Request(url, data=body, headers=headers,
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read()
        except Exception:
            return exc.code, None
        try:
            parsed = json.loads(raw.decode("utf-8"))
            return exc.code, parsed if isinstance(parsed, dict) else None
        except (ValueError, UnicodeDecodeError):
            return exc.code, None
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return 200, None
    return 200, parsed if isinstance(parsed, dict) else None


def post_decisions(body: dict, *, api_key: str,
                   timeout_s: float = DEFAULT_TIMEOUT_S,
                   http_post=None) -> dict:
    """ONE decisions attempt. Returns an outcome dict, never raises.

    Outcomes follow the 3.4 table: ``ok``, ``not_configured``,
    ``integration_defect``, ``auth_rejected``, ``rate_limited``,
    ``overloaded``, ``network_error``, ``timeout``, ``invalid_response``.
    No retries here: the caller owns budgets and fallback. Key material
    never appears in the result.
    """
    if not isinstance(api_key, str) or not api_key.strip():
        return {"outcome": "not_configured", "status": None, "payload": None,
                "model_snapshot": None, "error_category": "config_missing"}
    usable, _ = _is_usable_value(api_key)
    if not usable:
        return {"outcome": "not_configured", "status": None, "payload": None,
                "model_snapshot": None, "error_category": "config_missing"}
    violations = check_body_clean(body)
    if violations:
        return {"outcome": "integration_defect", "status": None,
                "payload": None, "model_snapshot": None,
                "error_category": "integration_defect",
                "detail": "; ".join(violations)}
    sender = http_post or _default_http_post
    payload_bytes = json.dumps(body, allow_nan=False).encode("utf-8")
    headers = {"Authorization": "Bearer " + api_key.strip(),
               "Content-Type": "application/json"}
    try:
        status, parsed = sender(TYPESAFE_ENDPOINT, payload_bytes, headers,
                                timeout_s)
    except TimeoutError:
        return {"outcome": "timeout", "status": None, "payload": None,
                "model_snapshot": None, "error_category": "timeout"}
    except (OSError, ValueError) as exc:
        category = ("timeout" if isinstance(exc, TimeoutError)
                    else "network_error")
        return {"outcome": category, "status": None, "payload": None,
                "model_snapshot": None, "error_category": category}
    if status == 200 and isinstance(parsed, dict):
        model_snapshot = parsed.get("model")
        return {"outcome": "ok", "status": 200, "payload": parsed,
                "model_snapshot": model_snapshot
                if isinstance(model_snapshot, str) else None,
                "error_category": "none"}
    if status == 200:
        return {"outcome": "invalid_response", "status": 200,
                "payload": None, "model_snapshot": None,
                "error_category": "invalid_response"}
    mapping = {401: "auth_rejected", 422: "integration_defect",
               429: "rate_limited", 529: "overloaded"}
    if status in mapping:
        outcome = mapping[status]
    elif isinstance(status, int) and 400 <= status < 500:
        outcome = "integration_defect"
    else:
        outcome = "overloaded"
    return {"outcome": outcome, "status": status, "payload": None,
            "model_snapshot": None, "error_category": outcome}


def is_approved_model(returned: object,
                      requested: str = TYPESAFE_MODEL) -> bool:
    """Accept the requested snapshot or its dated family member.

    ``jev-1.13.0`` accepts ``jev-1.13.0`` and ``jev-1.13.<dated>``; an
    unrelated version string is rejected, not silently accepted.
    """
    if not isinstance(returned, str) or not returned.strip():
        return False
    if returned == requested:
        return True
    family = requested.rsplit(".", 1)[0] if "." in requested else requested
    return returned == family or returned.startswith(family + ".")
