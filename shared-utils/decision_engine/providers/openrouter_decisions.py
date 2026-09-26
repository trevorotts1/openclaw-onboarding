#!/usr/bin/env python3
"""D05 OpenRouter decisions transport (JEV spec 1.1, ss 3.1/3.2/3.4/3.7).

Stdlib only. No state writes. Validators never raise on malformed input:
a bad response is ``(False, errors)``, never an exception (fail-closed).

Contract (spec 3.2): decisions API, NOT chat completions::

    POST https://openrouter.ai/api/alpha/decisions
    model: typesafe/jev-1.13
    key:   OPENROUTER_API_KEY (bearer)

Body holds ``model`` + ``state`` + typed ``questions`` only. Never fabricate
``messages``, ``reasoning_effort``, temperature, or tool-call semantics.

Response validation (spec 3.7): required question IDs, matching answer
types, allowed candidate IDs, finite numerics, bounds, complete expected
probability keys, approx unit-sum within PROBABILITY_SUM_TOLERANCE.
Returned model snapshot may differ from the requested family string
(dated snapshot); accept snapshot-in-family, reject snapshot-foreign.

Error classes (spec 3.4): auth_rejected / request_defect(422) /
retry_later(429) / overload(5xx incl 529) / transport_error / invalid
(low-confidence or malformed judgment -> caller falls back, never coerces).
"""

from __future__ import annotations

import json
import math
import urllib.request
import urllib.error

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
REQUESTED_MODEL = "typesafe/jev-1.13"
MODEL_FAMILY = "typesafe/jev-1.13"
API_KEY_NAME = "OPENROUTER_API_KEY"
PACK_TOKEN_TARGET = 24000  # conservative common target, spec 3.7
PROBABILITY_SUM_TOLERANCE = 1e-6
REQUEST_TIMEOUT_S = 30
FORBIDDEN_BODY_KEYS = (
    "messages",
    "reasoning_effort",
    "temperature",
    "tools",
    "tool_calls",
)
_RETRYABLE = ("retry_later", "overload", "transport_error")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_finite_number(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, float) and math.isfinite(v)


def _find_nonfinite(node, path="$"):
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


def is_placeholder_key(value) -> bool:
    """True when a key value must be rejected before any call (spec 3.3)."""
    if not isinstance(value, str) or not value.strip():
        return True
    upper = value.strip().upper()
    return any(
        tag in upper for tag in ("PLACEHOLDER", "PASTE_", "EXAMPLE", "REDACTED")
    )


def resolve_key(explicit=None, env=None) -> tuple[str | None, str]:
    """Resolve OPENROUTER_API_KEY without touching os.environ or disk.

    Returns ``(key_or_None, source)``; source is ``explicit`` / ``env`` /
    ``missing``. Never raises, never echoes the value.
    """
    try:
        if isinstance(explicit, str) and not is_placeholder_key(explicit):
            return explicit, "explicit"
        if isinstance(env, dict):
            cand = env.get(API_KEY_NAME)
            if isinstance(cand, str) and not is_placeholder_key(cand):
                return cand, "env"
        return None, "missing"
    except Exception:
        return None, "missing"


def estimate_tokens(payload: dict) -> int:
    """Conservative size estimate: serialized chars // 4. Honest label."""
    try:
        return len(json.dumps(payload, ensure_ascii=False)) // 4
    except Exception:
        return PACK_TOKEN_TARGET + 1  # fail-closed: treat as over budget


def build_request(state, questions: list, model: str = REQUESTED_MODEL) -> dict:
    """Pack ``{model, state, questions}``. No chat-completions fields."""
    body = {"model": model, "state": state, "questions": list(questions)}
    for key in FORBIDDEN_BODY_KEYS:
        body.pop(key, None)
    return body


def model_in_family(returned, requested: str = REQUESTED_MODEL) -> bool:
    """Snapshot-in-family: equal, or requested + separator + suffix.

    Accepts ``typesafe/jev-1.13-20260901``; rejects ``typesafe/jev-1.130``,
    ``typesafe/jev-1.12``, ``typesafe/jev-2.0``, other providers, empty.
    """
    if not isinstance(returned, str) or not returned.strip():
        return False
    if returned == requested:
        return True
    if returned.startswith(requested):
        rest = returned[len(requested):]
        return bool(rest) and rest[0] in "-.:+/@_ "
    return False


def classify_status(status) -> str:
    """Map HTTP status to a spec 3.4 handling class."""
    try:
        code = int(status)
    except (TypeError, ValueError):
        return "transport_error"
    if code == 200:
        return "ok"
    if code in (401, 403):
        return "auth_rejected"
    if code == 422:
        return "request_defect"
    if code == 429:
        return "retry_later"
    if code in (500, 502, 503, 529):
        return "overload"
    return "transport_error"


def validate_response(
    body: dict,
    expected: list,
    allowed_candidates: tuple | list = (),
) -> tuple[bool, list[str], dict]:
    """Validate an OpenRouter decisions body. Never raises.

    ``expected`` entries: ``{"question_id": str, "answer": "choice" |
    "score" | "distribution", "choices"?: [...], "levels"?: N,
    "candidates"?: [...]}``. Distribution keys must exactly equal the
    per-question ``candidates`` or the global ``allowed_candidates``.
    Returns ``(ok, errors, normalized)``; normalized preserves unknown
    extra metadata verbatim.
    """
    try:
        errors: list[str] = []
        if not isinstance(body, dict):
            return False, [f"response is not an object (got {type(body).__name__})"], {}
        allowed = list(allowed_candidates or [])

        model = body.get("model")
        if not isinstance(model, str) or not model.strip():
            errors.append("'model': required non-empty string (returned snapshot)")
        elif not model_in_family(model):
            errors.append(
                f"'model': snapshot-foreign {model!r} (family {MODEL_FAMILY!r})"
            )

        judgments = body.get("judgments")
        if not isinstance(judgments, list):
            errors.append(
                f"'judgments': required list, got {type(judgments).__name__}"
            )
            return False, errors, {"model": model}

        hit = _find_nonfinite(judgments)
        if hit is not None:
            errors.append(f"non-finite number at judgments{hit[1:]} (NaN/Inf rejected)")

        by_id: dict[str, dict] = {}
        for i, judgment in enumerate(judgments):
            if not isinstance(judgment, dict):
                errors.append(f"judgments[{i}]: required object")
                continue
            qid = judgment.get("question_id")
            if not isinstance(qid, str) or not qid.strip():
                errors.append(f"judgments[{i}]: required non-empty 'question_id'")
                continue
            if qid in by_id:
                errors.append(f"judgments: duplicate question_id {qid!r}")
            else:
                by_id[qid] = judgment

        for spec in expected or []:
            qid = spec.get("question_id")
            kind = spec.get("answer")
            judgment = by_id.get(qid)
            if judgment is None:
                errors.append(f"missing required answer: question_id {qid!r}")
                continue
            if kind == "choice":
                choices = spec.get("choices") or []
                answer = judgment.get("answer")
                if not isinstance(answer, str):
                    errors.append(
                        f"{qid!r}: choice answer must be string, got {answer!r}"
                    )
                elif choices and answer not in choices:
                    errors.append(f"{qid!r}: answer {answer!r} not in {choices}")
                cands = spec.get("candidates") or allowed
                if (
                    isinstance(answer, str)
                    and cands
                    and "candidate" in qid.lower()
                    and answer not in cands
                ):
                    errors.append(
                        f"{qid!r}: unknown candidate {answer!r} (allowed {cands})"
                    )
            elif kind == "score":
                levels = spec.get("levels")
                level = judgment.get("level")
                if not _is_int(level):
                    errors.append(
                        f"{qid!r}: score level must be int, got {level!r}"
                    )
                elif _is_int(levels) and not (0 <= level < levels):
                    errors.append(
                        f"{qid!r}: level {level} out of bounds [0, {levels})"
                    )
            elif kind == "distribution":
                cands = spec.get("candidates") or allowed
                probs = judgment.get("probabilities")
                if not isinstance(probs, dict):
                    errors.append(f"{qid!r}: probabilities must be object")
                    continue
                if cands and set(probs.keys()) != set(cands):
                    errors.append(
                        f"{qid!r}: probability keys {sorted(probs.keys())} "
                        f"!= expected {sorted(cands)}"
                    )
                for cand, prob in probs.items():
                    if not _is_finite_number(prob):
                        errors.append(
                            f"{qid!r}: probability {cand!r} not finite ({prob!r})"
                        )
                    elif not 0.0 <= float(prob) <= 1.0:
                        errors.append(
                            f"{qid!r}: probability {cand!r}={prob!r} out of [0,1]"
                        )
                vals = [
                    float(v)
                    for v in probs.values()
                    if _is_finite_number(v)
                ]
                if len(vals) == len(probs) and vals:
                    total = math.fsum(vals)
                    if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
                        errors.append(
                            f"{qid!r}: probabilities sum {total!r} != 1.0 "
                            f"(tolerance {PROBABILITY_SUM_TOLERANCE})"
                        )
            else:
                errors.append(f"{qid!r}: unknown expected answer kind {kind!r}")

        normalized = {
            "model_requested": REQUESTED_MODEL,
            "model_returned": model,
            "judgments": [dict(j) for j in judgments if isinstance(j, dict)],
        }
        for key, value in body.items():
            if key not in ("model", "judgments"):
                normalized.setdefault(key, value)
        return (len(errors) == 0), errors, normalized
    except Exception as exc:  # fail-closed
        return False, [f"validator error: {exc}"], {}


def _urllib_transport(url, headers, body_bytes, timeout):
    """Default POST transport. Returns ``(status, body_dict_or_None)``."""
    req = urllib.request.Request(
        url, data=body_bytes, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip() else None
        except Exception:
            parsed = None
        return exc.code, parsed
    except Exception:
        return None, None


def send_decisions(
    state,
    questions: list,
    expected: list,
    api_key=None,
    env=None,
    allowed_candidates: tuple | list = (),
    transport=None,
    timeout: int = REQUEST_TIMEOUT_S,
    endpoint: str = ENDPOINT,
) -> tuple[str, dict]:
    """One bounded OpenRouter attempt. Never raises; never logs the key.

    Outcomes: ``ok`` | ``missing_key`` | ``over_budget`` |
    ``auth_rejected`` | ``request_defect`` | ``retry_later`` | ``overload``
    | ``transport_error`` | ``invalid_judgment`` | ``model_foreign``.
    Single attempt only: bounded backoff/retry lives with the caller.
    """
    try:
        key, source = resolve_key(api_key, env)
        if key is None:
            return "missing_key", {
                "errors": [f"{API_KEY_NAME}: not configured (source {source})"],
                "key_source": source,
            }
        body = build_request(state, questions)
        if estimate_tokens(body) > PACK_TOKEN_TARGET:
            return "over_budget", {
                "errors": [
                    f"packing {estimate_tokens(body)} est tokens exceeds "
                    f"target {PACK_TOKEN_TARGET}"
                ]
            }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        if transport is not None:
            status, resp_body = transport(endpoint, headers, payload)
        else:
            status, resp_body = _urllib_transport(
                endpoint, headers, payload, timeout
            )
        outcome = classify_status(status)
        if outcome != "ok":
            return outcome, {"status": status, "errors": [f"HTTP {status}"]}
        if not isinstance(resp_body, dict):
            return "invalid_judgment", {"errors": ["response body not a JSON object"]}
        ok, errs, normalized = validate_response(
            resp_body, expected, allowed_candidates
        )
        if not ok:
            if any("snapshot-foreign" in e for e in errs):
                return "model_foreign", {"errors": errs}
            return "invalid_judgment", {"errors": errs}
        normalized["key_source"] = source
        return "ok", normalized
    except Exception as exc:  # fail-closed
        return "transport_error", {"errors": [f"transport failure: {type(exc).__name__}"]}
