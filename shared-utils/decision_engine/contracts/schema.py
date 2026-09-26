#!/usr/bin/env python3
"""D02 decision-envelope + persona-bundle contract (JEV spec 1.1, section 10).

Stdlib only. No network, no provider access, no state writes. Validators never
raise on malformed input: a bad envelope/bundle is a ``(False, errors)`` result,
never an exception (fail-closed for validators).

Extension strategy (explicit, per spec 10.2):
  * Unknown OPTIONAL top-level or nested fields are accepted and preserved
    verbatim by ``normalize_*`` / ``canonical_envelope_json`` (never stripped).
  * ``schemaVersion`` (envelope) and ``bundle_version`` (bundle, optional) carry
    the compatibility gate: same major version ``1`` accepted (``1``, ``1.0``,
    ``1.x``); any other major or unparsable value is rejected as incompatible.
  * New REQUIRED fields arrive only with a new major version, which old code
    rejects loudly instead of misreading.
"""

from __future__ import annotations

import copy
import json
import math
import sys
from datetime import datetime

ENVELOPE_SCHEMA_VERSION = "1.0"
BUNDLE_VERSION = "1.0"
BUNDLE_VERSION_MAJOR = "1"

STATUS_ENUM = (
    "proposed",
    "pending_confirmation",
    "committed",
    "superseded",
    "failed",
)
EXECUTION_MODE_ENUM = (
    "delegated",
    "owner_direct",
    "named_worker",
    "existing_execution",
)
CONFIGURED_MODE_ENUM = ("auto", "shadow", "legacy", "off")
# Spec section 4.1 message-intent values.
INTENT_ENUM = (
    "answer_only",
    "task_request",
    "mixed_answer_and_task",
    "existing_task_control",
    "clarification_response",
    "social_conversation",
    "unresolved",
)
# persona_blend.py resolve_audience() sources + mechanical "n/a".
AUDIENCE_SOURCE_ENUM = (
    "onboarding_icp",
    "operator_confirmed",
    "asked",
    "n/a",
)
# persona_blend.py _GOAL_SOURCES + mechanical "n/a".
GOAL_SOURCE_ENUM = (
    "operator_confirmed",
    "skill6_intake",
    "template_inferred",
    "asked",
    "n/a",
)
# Company-identity keys a bundle (or future extension) may carry. Any present
# non-null value must equal the envelope companyId, else company mismatch.
COMPANY_ID_KEYS = (
    "companyId",
    "company_id",
    "company",
    "tenant_id",
    "tenantId",
)
MAX_TASK_PERSONAS = 10  # up-to-10 task-persona slots (spec 8.1, blend cap)

# Spec 10.1 canonical envelope: every field required; None allowed only where
# the type includes null.
REQUIRED_ENVELOPE_FIELDS = (
    "schemaVersion",
    "decisionId",
    "companyId",
    "requestId",
    "taskId",
    "scopeId",
    "inputRevision",
    "decisionRevision",
    "status",
    "intent",
    "executionMode",
    "executorAgentId",
    "departmentId",
    "roleId",
    "sopId",
    "personaBundle",
    "inputHash",
    "bundleHash",
    "policyVersion",
    "candidateCatalogVersion",
    "providerRequested",
    "providerUsed",
    "modelRequested",
    "modelReturned",
    "candidateIds",
    "retrievalEvidence",
    "judgments",
    "reasonCodes",
    "supportingEvidenceRefs",
    "fallbackReason",
    "confirmation",
    "preparationId",
    "preparationDeadlineAt",
    "preparationGeneration",
    "configRevision",
    "configuredMode",
    "effectivePath",
    "authorizationEvidenceRefs",
    "budgetReservationRefs",
    "stageTimings",
    "elapsedMs",
    "measuredUsage",
)
NULLABLE_ENVELOPE_FIELDS = frozenset({
    "taskId",
    "executorAgentId",
    "departmentId",
    "roleId",
    "sopId",
    "personaBundle",
    "bundleHash",
    "providerRequested",
    "modelRequested",
    "modelReturned",
    "fallbackReason",
    "confirmation",
    "measuredUsage",
})

# Spec 10.2 preservation mapped onto the real build_bundle()/CC output shape.
REQUIRED_BUNDLE_FIELDS = (
    "mode",
    "persona_id",
    "persona_name",
    "persona_version",
    "task_category",
    "content_task",
    "topic",
    "resolved_audience",
    "confirm_required",
    "voice",
    "blend_directive",
    "task_personas",
    "conversion_goal",
    "goal_source",
    "goal_confirm_required",
    "resolved_goal",
    "rationale",
    "funnel",
    "fallbacks",
    "catalog_version",
)


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_finite_number(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, float) and math.isfinite(v)


def _version_major(v) -> str | None:
    """Major component of a ``<major>[.<minor>[.<patch>]]`` version, else None."""
    if not isinstance(v, str):
        return None
    parts = v.strip().split(".")
    if not parts or not parts[0].isdigit():
        return None
    if any(not p.isdigit() for p in parts[1:]):
        return None
    return parts[0]


def _find_nonfinite(node, path: str = "$"):
    """Path of first non-finite float in ``node``, else None."""
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


def _need_str(errors: list, obj: dict, key: str, *, nullable: bool = False) -> None:
    v = obj.get(key)
    if v is None:
        if not nullable:
            errors.append(f"{key!r}: required non-null string, got null")
        return
    if not isinstance(v, str) or not v.strip():
        errors.append(f"{key!r}: required non-empty string, got {v!r}")


def _need_int_ge0(errors: list, obj: dict, key: str) -> None:
    v = obj.get(key)
    if not _is_int(v) or v < 0:
        errors.append(f"{key!r}: required int >= 0, got {v!r}")


def _need_str_list(errors: list, obj: dict, key: str) -> None:
    v = obj.get(key)
    if not isinstance(v, list):
        errors.append(f"{key!r}: required list, got {type(v).__name__}")
        return
    for i, item in enumerate(v):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{key!r}[{i}]: required non-empty string, got {item!r}")


def _need_obj_list(errors: list, obj: dict, key: str) -> None:
    v = obj.get(key)
    if not isinstance(v, list):
        errors.append(f"{key!r}: required list, got {type(v).__name__}")
        return
    for i, item in enumerate(v):
        if not isinstance(item, dict):
            errors.append(f"{key!r}[{i}]: required object, got {type(item).__name__}")


def _check_enum(errors: list, obj: dict, key: str, allowed: tuple) -> None:
    v = obj.get(key)
    if v not in allowed:
        errors.append(f"{key!r}: value {v!r} not in {list(allowed)}")


def validate_envelope(env: dict) -> tuple[bool, list[str]]:
    """Validate a decision envelope. Returns ``(ok, errors)``; never raises."""
    try:
        if not isinstance(env, dict):
            return False, [f"envelope is not an object (got {type(env).__name__})"]

        errors: list[str] = []
        for key in REQUIRED_ENVELOPE_FIELDS:
            if key not in env:
                errors.append(f"missing required key: {key!r}")

        hit = _find_nonfinite(env)
        if hit is not None:
            errors.append(f"non-finite number at {hit} (NaN/Inf rejected)")

        if _version_major(env.get("schemaVersion")) != "1":
            errors.append(
                f"'schemaVersion': incompatible version {env.get('schemaVersion')!r} "
                f"(this contract accepts major 1, e.g. {ENVELOPE_SCHEMA_VERSION!r})"
            )

        for key in (
            "decisionId", "companyId", "requestId", "scopeId", "inputHash",
            "policyVersion", "candidateCatalogVersion", "providerUsed",
            "preparationId", "preparationDeadlineAt", "configRevision",
            "effectivePath",
        ):
            _need_str(errors, env, key)
        for key in (
            "taskId", "executorAgentId", "departmentId", "roleId", "sopId",
            "bundleHash", "providerRequested", "modelRequested", "modelReturned",
            "fallbackReason",
        ):
            _need_str(errors, env, key, nullable=True)
        for key in ("inputRevision", "decisionRevision", "preparationGeneration", "elapsedMs"):
            _need_int_ge0(errors, env, key)

        _check_enum(errors, env, "status", STATUS_ENUM)
        _check_enum(errors, env, "intent", INTENT_ENUM)
        _check_enum(errors, env, "executionMode", EXECUTION_MODE_ENUM)
        _check_enum(errors, env, "configuredMode", CONFIGURED_MODE_ENUM)

        _need_str_list(errors, env, "candidateIds")
        _need_str_list(errors, env, "reasonCodes")
        _need_str_list(errors, env, "supportingEvidenceRefs")
        _need_str_list(errors, env, "authorizationEvidenceRefs")
        _need_str_list(errors, env, "budgetReservationRefs")
        _need_obj_list(errors, env, "retrievalEvidence")
        _need_obj_list(errors, env, "judgments")
        _need_obj_list(errors, env, "stageTimings")

        for i, j in enumerate(env.get("judgments") or []):
            if isinstance(j, dict) and (
                not isinstance(j.get("question_id"), str) or not j["question_id"].strip()
            ):
                errors.append(f"judgments[{i}]: required non-empty 'question_id'")

        for i, s in enumerate(env.get("stageTimings") or []):
            if isinstance(s, dict):
                if not isinstance(s.get("stage"), str) or not s["stage"].strip():
                    errors.append(f"stageTimings[{i}]: required non-empty 'stage'")
                if not _is_int(s.get("ms")) or s["ms"] < 0:
                    errors.append(f"stageTimings[{i}]: required int 'ms' >= 0")

        for key in ("confirmation", "measuredUsage"):
            v = env.get(key)
            if v is not None and not isinstance(v, dict):
                errors.append(f"{key!r}: required object or null, got {type(v).__name__}")

        try:
            datetime.fromisoformat(str(env.get("preparationDeadlineAt")))
        except (ValueError, TypeError):
            errors.append("'preparationDeadlineAt': required ISO-8601 datetime string")

        # Status cross-field rules.
        if env.get("status") == "failed" and not (
            isinstance(env.get("fallbackReason"), str) and env["fallbackReason"].strip()
        ):
            errors.append("status='failed' requires a non-empty 'fallbackReason'")
        if env.get("status") == "committed" and not isinstance(env.get("personaBundle"), dict):
            errors.append("status='committed' requires a 'personaBundle' object")

        bundle = env.get("personaBundle")
        if bundle is not None:
            if not isinstance(bundle, dict):
                errors.append(f"'personaBundle': required object or null, got {type(bundle).__name__}")
            else:
                ok_b, errs_b = validate_persona_bundle(bundle, company_id=env.get("companyId"))
                errors.extend(f"personaBundle.{e}" for e in errs_b)

        return (len(errors) == 0), errors
    except Exception as exc:  # fail-closed: validator never raises
        return False, [f"validator error: {exc}"]


def _check_voice(errors: list, voice) -> None:
    if not isinstance(voice, dict):
        errors.append("'voice': required object")
        return
    if voice.get("collapsed") is not True and voice.get("collapsed") is not False:
        errors.append("'voice.collapsed': required boolean")
        return
    collapsed = voice["collapsed"]
    cpid = voice.get("collapsed_persona_id")
    if collapsed:
        if not isinstance(cpid, str) or not cpid.strip():
            errors.append("'voice.collapsed_persona_id': required non-empty string when collapsed")
    elif cpid is not None:
        errors.append("'voice.collapsed_persona_id': must be null when not collapsed")
    for slot in ("audience_persona", "topic_persona"):
        p = voice.get(slot)
        if p is not None:
            if not isinstance(p, dict):
                errors.append(f"'voice.{slot}': required object or null")
            elif p.get("id") is not None and (
                not isinstance(p.get("id"), str) or not p["id"].strip()
            ):
                errors.append(f"'voice.{slot}.id': required non-empty string or null")


def _check_audience(errors: list, ra) -> None:
    if not isinstance(ra, dict):
        errors.append("'resolved_audience': required object")
        return
    if ra.get("source") not in AUDIENCE_SOURCE_ENUM:
        errors.append(f"'resolved_audience.source': {ra.get('source')!r} not in {list(AUDIENCE_SOURCE_ENUM)}")
    cands = ra.get("candidates")
    if not isinstance(cands, list):
        errors.append("'resolved_audience.candidates': required list")
    else:
        for i, c in enumerate(cands):
            if not isinstance(c, dict):
                if not isinstance(c, str) or not c.strip():
                    errors.append(f"'resolved_audience.candidates[{i}]': required object or non-empty string")
            elif not isinstance(c.get("label"), str) or not c["label"].strip():
                errors.append(f"'resolved_audience.candidates[{i}].label': required non-empty string")
    if ra.get("confirm_required") is not True and ra.get("confirm_required") is not False:
        errors.append("'resolved_audience.confirm_required': required boolean")
    for key in ("label", "ask"):
        v = ra.get(key)
        if v is not None and not isinstance(v, str):
            errors.append(f"'resolved_audience.{key}': required string or null")


def _check_task_personas(errors: list, rows) -> None:
    if not isinstance(rows, list):
        errors.append("'task_personas': required list")
        return
    if len(rows) > MAX_TASK_PERSONAS:
        errors.append(f"'task_personas': {len(rows)} rows exceed up-to-{MAX_TASK_PERSONAS} cap")
    seen_seq = set()
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            errors.append(f"'task_personas[{i}]': required object")
            continue
        seq = r.get("seq")
        if not _is_int(seq):
            errors.append(f"'task_personas[{i}].seq': required int")
        elif seq in seen_seq:
            errors.append(f"'task_personas[{i}].seq': duplicate seq {seq}")
        else:
            seen_seq.add(seq)
        if "persona_id" not in r:
            errors.append(f"'task_personas[{i}]': missing 'persona_id' key")
        elif r.get("no_persona_required") is True:
            if r.get("persona_id") is not None:
                errors.append(f"'task_personas[{i}]': no_persona_required with persona_id set")
        elif not isinstance(r.get("persona_id"), str) or not r["persona_id"].strip():
            errors.append(f"'task_personas[{i}].persona_id': required non-empty string")


def validate_persona_bundle(bundle: dict, company_id: str | None = None) -> tuple[bool, list[str]]:
    """Validate a PersonaBundleVNext bundle. Returns ``(ok, errors)``; never raises."""
    try:
        if not isinstance(bundle, dict):
            return False, [f"bundle is not an object (got {type(bundle).__name__})"]
        errors: list[str] = []
        for key in REQUIRED_BUNDLE_FIELDS:
            if key not in bundle:
                errors.append(f"missing required key: {key!r}")

        hit = _find_nonfinite(bundle)
        if hit is not None:
            errors.append(f"non-finite number at {hit} (NaN/Inf rejected)")

        bv = bundle.get("bundle_version", bundle.get("bundleVersion"))
        if bv is not None and _version_major(bv) != BUNDLE_VERSION_MAJOR:
            errors.append(f"'bundle_version': incompatible version {bv!r} (major 1 accepted)")

        mechanical = bundle.get("no_persona_required") is True
        if mechanical:
            if bundle.get("persona_id") is not None:
                errors.append("mechanical bundle: 'persona_id' must be null")
            if bundle.get("persona_name") is not None:
                errors.append("mechanical bundle: 'persona_name' must be null")
            if bundle.get("content_task") is not False:
                errors.append("mechanical bundle: 'content_task' must be false")
            _need_str(errors, bundle, "governance_persona_id")
        else:
            _need_str(errors, bundle, "persona_id")
            _need_str(errors, bundle, "persona_name")

        if bundle.get("mode") != "blend":
            errors.append(f"'mode': {bundle.get('mode')!r} must be 'blend'")
        if bundle.get("content_task") is not True and bundle.get("content_task") is not False:
            errors.append("'content_task': required boolean")
        _need_str(errors, bundle, "topic")
        _need_str(errors, bundle, "task_category")
        _need_str(errors, bundle, "catalog_version")
        if bundle.get("confirm_required") is not True and bundle.get("confirm_required") is not False:
            errors.append("'confirm_required': required boolean")
        if bundle.get("goal_confirm_required") is not True and bundle.get("goal_confirm_required") is not False:
            errors.append("'goal_confirm_required': required boolean")
        pv = bundle.get("persona_version")
        if not _is_int(pv) or pv < 1:
            errors.append(f"'persona_version': required int >= 1, got {pv!r}")

        directive = bundle.get("blend_directive")
        if not isinstance(directive, str) or not directive.strip():
            errors.append("'blend_directive': required non-empty string")
        elif not ("style-inspired" in directive.lower() and "impersonation" in directive.lower()):
            errors.append("'blend_directive': missing mandatory style-inspired-NOT-impersonation guardrail")

        _check_voice(errors, bundle.get("voice"))
        _check_audience(errors, bundle.get("resolved_audience"))
        _check_task_personas(errors, bundle.get("task_personas"))

        if not isinstance(bundle.get("conversion_goal"), str):
            errors.append("'conversion_goal': required string (empty when unresolved)")
        if bundle.get("goal_source") not in GOAL_SOURCE_ENUM:
            errors.append(f"'goal_source': {bundle.get('goal_source')!r} not in {list(GOAL_SOURCE_ENUM)}")
        rg = bundle.get("resolved_goal")
        if not isinstance(rg, dict):
            errors.append("'resolved_goal': required object")
        else:
            if not isinstance(rg.get("value"), str):
                errors.append("'resolved_goal.value': required string")
            if rg.get("source") not in GOAL_SOURCE_ENUM:
                errors.append(f"'resolved_goal.source': {rg.get('source')!r} not in {list(GOAL_SOURCE_ENUM)}")
            if isinstance(bundle.get("goal_source"), str) and rg.get("source") != bundle["goal_source"]:
                errors.append("'goal_source' must equal 'resolved_goal.source'")

        for key in ("rationale", "funnel", "fallbacks"):
            if key in bundle and not isinstance(bundle[key], dict):
                errors.append(f"{key!r}: required object")
        if "score" in bundle and bundle["score"] is not None and not _is_finite_number(bundle["score"]):
            errors.append(f"'score': required finite number or null, got {bundle['score']!r}")

        # Audience confirm lockstep (build_bundle sets both to one truth).
        ra = bundle.get("resolved_audience")
        if (
            isinstance(ra, dict)
            and isinstance(bundle.get("confirm_required"), bool)
            and isinstance(ra.get("confirm_required"), bool)
            and ra["confirm_required"] != bundle["confirm_required"]
        ):
            errors.append("'confirm_required' must equal 'resolved_audience.confirm_required'")

        # Legacy mirror must name the resolved voice winner.
        voice = bundle.get("voice")
        if isinstance(voice, dict) and not mechanical:
            aud = (voice.get("audience_persona") or {}) if isinstance(voice.get("audience_persona"), dict) else {}
            top = (voice.get("topic_persona") or {}) if isinstance(voice.get("topic_persona"), dict) else {}
            winner = voice.get("collapsed_persona_id") if voice.get("collapsed") else (aud.get("id") or top.get("id"))
            if isinstance(winner, str) and isinstance(bundle.get("persona_id"), str):
                if bundle["persona_id"] != winner:
                    errors.append(f"'persona_id' {bundle['persona_id']!r} must mirror voice winner {winner!r}")

        # Company mismatch: any carried company identity must match the envelope.
        if company_id is not None:
            for key in COMPANY_ID_KEYS:
                if key in bundle and bundle[key] is not None and bundle[key] != company_id:
                    errors.append(f"company mismatch: bundle {key}={bundle[key]!r} != envelope companyId={company_id!r}")

        return (len(errors) == 0), errors
    except Exception as exc:  # fail-closed: validator never raises
        return False, [f"validator error: {exc}"]


def normalize_bundle(bundle: dict) -> dict:
    """Deep copy preserving every field, including unknown extension fields."""
    return copy.deepcopy(bundle)


def normalize_envelope(env: dict) -> dict:
    """Deep copy preserving every field, including unknown extension fields."""
    return copy.deepcopy(env)


def canonical_envelope_json(env: dict) -> str:
    """Deterministic canonical JSON: sorted keys, compact separators.

    Raises ValueError on non-finite floats (allow_nan=False) — fail-closed
    serialization: such envelopes are invalid and must never be persisted.
    """
    return (
        json.dumps(
            normalize_envelope(env),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: schema.py --check FILE.json [FILE.json ...]")
        print("       schema.py --canonicalize FILE.json")
        return 0 if argv else 2
    if argv[0] == "--check":
        rc = 0
        for path in argv[1:]:
            try:
                with open(path, encoding="utf-8") as f:
                    env = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"FAIL {path}: cannot read/parse: {exc}")
                rc = 1
                continue
            ok, errs = validate_envelope(env)
            if ok:
                print(f"OK {path}")
            else:
                print(f"FAIL {path}:")
                for e in errs:
                    print(f"  - {e}")
                rc = 1
        return rc
    if argv[0] == "--canonicalize" and len(argv) == 2:
        with open(argv[1], encoding="utf-8") as f:
            env = json.load(f)
        ok, errs = validate_envelope(env)
        if not ok:
            for e in errs:
                print(f"  - {e}")
            return 1
        sys.stdout.write(canonical_envelope_json(env))
        return 0
    print("usage: schema.py --check FILE.json [FILE.json ...]")
    print("       schema.py --canonicalize FILE.json")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
