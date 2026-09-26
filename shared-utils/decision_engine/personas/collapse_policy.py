#!/usr/bin/env python3
"""D19 single-persona collapse policy (JEV spec 1.1, ss 8.8/8.9/8.10; topic-fit 8.6).

(a) Collapse: one persona covers voice AND topic only on INDEPENDENT
    voice-fit AND topic-fit evidence with caller-set thresholds. Never
    collapses on cheap storage, tag overlap, previous winner, or
    topic-strength without a voice check. Separate personas stay when
    collapse loses expertise or audience fit. Dimension scores + reason
    code returned in every decision (spec 8.8 log).
(b) Per-part guidance: coherent shared campaign voice by default; a part
    differs only with recorded justification; a per-part audience change
    invalidates affected decisions + dependent parents only (spec 8.10).
(c) Decomposition guard: exactly one of blend|planner|sop_slot per scope;
    SOP-slot/hint propagation check (spec 8.9).

Extends D16 evidence_profiles, D18 voice_match, D17 five_layer, D03
policies: their types/levels imported by file location, never redefined.
Stdlib only. No network, no provider access, no state writes. Validators
return ``(ok, errors)`` fail-closed; deciders raise ValueError on bad
input (never a silent default).

ponytail: fit inputs are caller-supplied normalized/level scores, ceiling
is caller rubric quality; upgrade path is calibrated fit behind the same
decision-dict schema (no API change).
"""

from __future__ import annotations

import math
from pathlib import Path

__all__ = [
    "CONFIDENCE_LEVELS",
    "RESPONSIBILITIES",
    "BASIS_VALUES",
    "LAYERS",
    "normalize_score",
    "aggregate_fit",
    "DECISIONS",
    "COLLAPSE_REASONS",
    "SINGLE_PATHS",
    "GUIDANCE_JUSTIFICATIONS",
    "validate_collapse_request",
    "decide_collapse",
    "per_part_guidance",
    "assert_single_decomposition",
    "check_slot_hint_propagation",
]


def _by_path(mod_name, path):
    """Load the REAL module at path (offline test convention)."""
    import importlib.util
    import sys
    existing = sys.modules.get(mod_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


_here = Path(__file__).resolve()
_de = _here.parent.parent
_shared = _de.parent

_pol = _by_path("d19_policies", _de / "policies" / "__init__.py")
_ep = _by_path("d19_evidence", _de / "personas" / "evidence_profiles.py")
_vm = _by_path("d19_voice_match", _de / "personas" / "voice_match.py")
_fl = _by_path("d19_five_layer", _de / "evaluators" / "five_layer.py")

# D16/D18/D17/D03 types and levels, re-exported — never redefined here.
CONFIDENCE_LEVELS = _ep.CONFIDENCE_LEVELS
RESPONSIBILITIES = _ep.RESPONSIBILITIES
BASIS_VALUES = _vm.BASIS_VALUES
LAYERS = _fl.LAYERS
normalize_score = _pol.normalize_score
aggregate_fit = _pol.aggregate_fit

# Spec 8.8: collapse or keep_separate, nothing in between.
DECISIONS = ("collapse", "keep_separate")

# Spec 8.8: every decision carries one of these reason codes.
COLLAPSE_REASONS = (
    "voice-and-topic-fit",
    "below-threshold",
    "voice-unchecked",
    "topic-unchecked",
    "tag-overlap-only",
    "cheap-storage-only",
    "previous-winner-only",
    "expertise-loss",
    "audience-changed",
)

# Forbidden collapse shortcuts (spec 8.8 "do not collapse solely because").
_FORBIDDEN_BASIS = {
    "tag_overlap": "tag-overlap-only",
    "cheap_storage": "cheap-storage-only",
    "previous_winner": "previous-winner-only",
}
_ALLOWED_BASIS = frozenset({"voice_topic_fit"} | set(_FORBIDDEN_BASIS))

# Spec 8.9: exactly one decomposition owner per scope.
SINGLE_PATHS = ("blend", "planner", "sop_slot")

# Spec 8.10: justification vocabulary for per-part voice differences.
GUIDANCE_JUSTIFICATIONS = (
    "shared-coherent-voice",
    "audience-change",
    "brand-change",
    "topic-requirement",
)

_FIT_KEYS = frozenset({"level", "levels", "score", "evidence_refs", "checked"})


def _is_finite_number(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, float) and math.isfinite(v)


def _check_fit(fit, name: str) -> list[str]:
    """Validate one fit dict. Returns error list (empty = valid)."""
    errs: list[str] = []
    if not isinstance(fit, dict):
        return [f"{name}: spec must be an object"]
    unknown = set(fit) - _FIT_KEYS
    if unknown:
        errs.append(f"{name}: unknown field(s) {sorted(unknown)}")
    has_level = "level" in fit or "levels" in fit
    has_score = "score" in fit
    if has_level and has_score:
        errs.append(f"{name}: supply level/levels OR score, not both")
    elif has_level:
        level, levels = fit.get("level"), fit.get("levels")
        if not isinstance(level, int) or isinstance(level, bool):
            errs.append(f"{name}.level: required int descriptive level (spec 8.6, never 0-10 float)")
        if not isinstance(levels, int) or isinstance(levels, bool) or levels < 2:
            errs.append(f"{name}.levels: required int >= 2")
        elif isinstance(level, int) and not isinstance(level, bool) and not 0 <= level < levels:
            errs.append(f"{name}: level {level} out of range for {levels} levels")
    elif has_score:
        s = fit.get("score")
        if not _is_finite_number(s) or not 0.0 <= float(s) <= 1.0:
            errs.append(f"{name}.score: required finite number in [0, 1], got {s!r}")
    else:
        errs.append(f"{name}: supply level/levels OR score")
    refs = fit.get("evidence_refs")
    if not isinstance(refs, list) or not refs or any(
            not isinstance(r, str) or not r.strip() for r in refs):
        errs.append(f"{name}.evidence_refs: required non-empty list of non-empty strings")
    if fit.get("checked") is not True and fit.get("checked") is not False:
        errs.append(f"{name}.checked: required boolean (independent check performed?)")
    return errs


def _fit_score(fit, name: str) -> float:
    """Normalize one fit to [0, 1] via REAL D03 normalize_score. Raises."""
    if "level" in fit or "levels" in fit:
        try:
            return _pol.normalize_score(fit["level"], fit["levels"])
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"{name}: {exc}") from exc
    return float(fit["score"])


def validate_collapse_request(
    voice,
    topic,
    *,
    thresholds=None,
    audience_kept,
    expertise_loss,
    basis=None,
) -> tuple[bool, list[str]]:
    """Validate a collapse request. Returns ``(ok, errors)``; never raises."""
    try:
        errs: list[str] = []
        errs.extend(_check_fit(voice, "voice"))
        errs.extend(_check_fit(topic, "topic"))
        if not isinstance(thresholds, dict):
            errs.append("thresholds: required object (caller-set, never defaulted)")
        else:
            if set(thresholds) != {"voice_min", "topic_min"}:
                errs.append(
                    "thresholds: required exactly {voice_min, topic_min}, "
                    f"got {sorted(thresholds)}"
                )
            for key in ("voice_min", "topic_min"):
                val = thresholds.get(key)
                if not _is_finite_number(val) or not 0.0 <= float(val) <= 1.0:
                    errs.append(f"thresholds.{key}: required finite number in [0, 1], got {val!r}")
        if audience_kept is not True and audience_kept is not False:
            errs.append(f"audience_kept: required boolean, got {audience_kept!r}")
        if expertise_loss is not True and expertise_loss is not False:
            errs.append(f"expertise_loss: required boolean, got {expertise_loss!r}")
        if basis is not None and basis not in _ALLOWED_BASIS:
            errs.append(
                f"basis: {basis!r} not in {sorted(_ALLOWED_BASIS)} "
                "(tag overlap / cheap storage / previous winner are keep_separate, not input)"
            )
        return (len(errs) == 0), errs
    except Exception as exc:  # fail-closed: validator never raises
        return False, [f"validator error: {exc}"]


def decide_collapse(
    voice,
    topic,
    *,
    thresholds=None,
    audience_kept,
    expertise_loss,
    basis=None,
) -> dict:
    """Decide single-persona collapse. Raises ValueError on bad input.

    Deterministic order: forbidden shortcut > voice-unchecked >
    topic-unchecked > audience-changed > expertise-loss > thresholds.
    Collapse needs voice AND topic at/above caller-set minimums with the
    audience kept and no expertise loss. Every return carries dimension
    scores + reason code (spec 8.8 log).
    """
    ok, errs = validate_collapse_request(
        voice, topic, thresholds=thresholds,
        audience_kept=audience_kept, expertise_loss=expertise_loss,
        basis=basis,
    )
    if not ok:
        raise ValueError("; ".join(errs))
    voice_score = _fit_score(voice, "voice")
    topic_score = _fit_score(topic, "topic")
    evidence = {
        "voice": list(voice["evidence_refs"]),
        "topic": list(topic["evidence_refs"]),
    }
    limits = {"voice_min": float(thresholds["voice_min"]),
              "topic_min": float(thresholds["topic_min"])}

    def _result(decision: str, reason: str) -> dict:
        return {
            "decision": decision,
            "reason_code": reason,
            "voice_score": voice_score,
            "topic_score": topic_score,
            "thresholds": dict(limits),
            "evidence_refs": {k: list(v) for k, v in evidence.items()},
            "log": {
                "decision": decision,
                "reason_code": reason,
                "voice_score": voice_score,
                "topic_score": topic_score,
                "thresholds": dict(limits),
                "audience_kept": audience_kept,
                "expertise_loss": expertise_loss,
                "basis": basis,
            },
        }

    if basis in _FORBIDDEN_BASIS:
        return _result("keep_separate", _FORBIDDEN_BASIS[basis])
    if voice["checked"] is not True:
        return _result("keep_separate", "voice-unchecked")
    if topic["checked"] is not True:
        return _result("keep_separate", "topic-unchecked")
    if audience_kept is not True:
        return _result("keep_separate", "audience-changed")
    if expertise_loss is True:
        return _result("keep_separate", "expertise-loss")
    if voice_score >= limits["voice_min"] and topic_score >= limits["topic_min"]:
        return _result("collapse", "voice-and-topic-fit")
    return _result("keep_separate", "below-threshold")


def _opt_str(value, field: str, where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}.{field}: must be a non-empty string or null")
    return value.strip()


def per_part_guidance(parts, shared_blend, audience, brand) -> dict:
    """Per-part topic/voice guidance under one campaign blend. Raises.

    Default: shared coherent voice (voice_override None, justification
    ``shared-coherent-voice``). A part whose audience/brand differs gets a
    voice_override plus a justification naming the difference. Audience
    changes invalidate affected decisions + dependent parents only;
    siblings survive. Returns ``{per_part, invalidated, shared}`` with
    ``invalidated`` sorted for determinism.
    """
    if not isinstance(parts, list) or not parts:
        raise ValueError("parts must be a non-empty list")
    if not isinstance(shared_blend, dict):
        raise ValueError("shared_blend must be an object")
    shared_voice = shared_blend.get("voice")
    if not isinstance(shared_voice, str) or not shared_voice.strip():
        raise ValueError("shared_blend.voice: required non-empty string")
    shared_voice = shared_voice.strip()
    if not isinstance(audience, str) or not audience.strip():
        raise ValueError("audience: required non-empty campaign audience string")
    if not isinstance(brand, str) or not brand.strip():
        raise ValueError("brand: required non-empty campaign brand string")
    audience, brand = audience.strip(), brand.strip()

    seen: set[str] = set()
    per_part: list[dict] = []
    invalidated: set[str] = set()
    for i, part in enumerate(parts):
        where = f"parts[{i}]"
        if not isinstance(part, dict):
            raise ValueError(f"{where}: required object")
        unknown = set(part) - {
            "part_id", "audience", "brand", "topic",
            "decision_id", "parents",
        }
        if unknown:
            raise ValueError(f"{where}: unknown field(s) {sorted(unknown)}")
        pid = part.get("part_id")
        if not isinstance(pid, str) or not pid.strip():
            raise ValueError(f"{where}.part_id: required non-empty string")
        pid = pid.strip()
        if pid in seen:
            raise ValueError(f"{where}: duplicate part_id {pid!r}")
        seen.add(pid)
        part_aud = _opt_str(part.get("audience"), "audience", where) or audience
        part_brand = _opt_str(part.get("brand"), "brand", where) or brand
        topic = _opt_str(part.get("topic"), "topic", where)
        decision_id = part.get("decision_id", pid)
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError(f"{where}.decision_id: required non-empty string")
        decision_id = decision_id.strip()
        parents = part.get("parents", [])
        if isinstance(parents, str):
            parents = [parents]
        if not isinstance(parents, (list, tuple)) or any(
                not isinstance(p, str) or not p.strip() for p in parents):
            raise ValueError(f"{where}.parents: string or list of non-empty strings")
        parents = [p.strip() for p in parents]

        aud_changed = part_aud != audience
        brand_changed = part_brand != brand
        if not aud_changed and not brand_changed:
            per_part.append({
                "part_id": pid,
                "topic_guidance": topic,
                "voice_override": None,
                "justification": "shared-coherent-voice",
                "audience": part_aud,
                "brand": part_brand,
            })
            continue
        reasons: list[str] = []
        if aud_changed:
            reasons.append(f"audience-change:{part_aud}")
        if brand_changed:
            reasons.append(f"brand-change:{part_brand}")
        if topic is not None:
            reasons.append(f"topic-requirement:{topic}")
        per_part.append({
            "part_id": pid,
            "topic_guidance": topic,
            "voice_override": {
                "voice": shared_voice,
                "audience": part_aud,
                "brand": part_brand,
            },
            "justification": ";".join(reasons),
            "audience": part_aud,
            "brand": part_brand,
        })
        if aud_changed:
            invalidated.add(decision_id)
            invalidated.update(parents)
    return {
        "per_part": per_part,
        "invalidated": sorted(invalidated),
        "shared": {"voice": shared_voice, "audience": audience, "brand": brand},
    }


def _canon_path(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"decomposition path {value!r}: required non-empty string")
    canon = value.strip().lower().replace("-", "_")
    if canon.startswith("--"):
        canon = canon[2:]
    if canon not in SINGLE_PATHS:
        raise ValueError(
            f"decomposition path {value!r}: must be one of {list(SINGLE_PATHS)} "
            "(standalone/--combined alongside blend is a double-run)"
        )
    return canon


def assert_single_decomposition(path_used) -> dict:
    """Accept exactly one of blend|planner|sop_slot. Raises otherwise.

    Rejects double-runs (blend + standalone scope, multi-entry lists, or
    multi-key maps). Returns ``{path, ok}``.
    """
    if isinstance(path_used, str):
        if "+" in path_used or "," in path_used:
            raise ValueError(
                f"double-run rejected: {path_used!r} runs two decompositions "
                "for one scope (spec 8.9: blend owns its internal decomposition)"
            )
        return {"path": _canon_path(path_used), "ok": True}
    if isinstance(path_used, (list, tuple)):
        if len(path_used) != 1:
            raise ValueError(
                f"double-run rejected: {len(path_used)} paths for one scope "
                "(spec 8.9: run the approved mechanism once)"
            )
        return {"path": _canon_path(path_used[0]), "ok": True}
    if isinstance(path_used, dict):
        if len(path_used) != 1:
            raise ValueError(
                f"double-run rejected: {len(path_used)} paths for one scope "
                "(spec 8.9: persist one result, then evaluate those parts)"
            )
        return {"path": _canon_path(next(iter(path_used))), "ok": True}
    raise ValueError(
        f"path_used must be a string, single-entry list, or single-key object "
        f"(got {type(path_used).__name__})"
    )


def check_slot_hint_propagation(declared_slots, consumed_hints) -> dict:
    """Compare declared SOP slots vs consumed hints. Never raises.

    Returns ``{ok, missing, undeclared, errors}``: ``missing`` slots were
    declared but never consumed (propagation break); ``undeclared`` hints
    were consumed without a declaration. ``ok`` needs zero missing and
    well-formed inputs.
    """
    try:
        errors: list[str] = []
        declared: list[str] = []
        consumed: list[str] = []
        if not isinstance(declared_slots, (list, tuple)):
            errors.append(
                f"declared_slots: required list (got {type(declared_slots).__name__})"
            )
        else:
            for i, slot in enumerate(declared_slots):
                if not isinstance(slot, str) or not slot.strip():
                    errors.append(f"declared_slots[{i}]: required non-empty string")
                else:
                    declared.append(slot.strip())
        if not isinstance(consumed_hints, (list, tuple)):
            errors.append(
                f"consumed_hints: required list (got {type(consumed_hints).__name__})"
            )
        else:
            for i, hint in enumerate(consumed_hints):
                if not isinstance(hint, str) or not hint.strip():
                    errors.append(f"consumed_hints[{i}]: required non-empty string")
                else:
                    consumed.append(hint.strip())
        declared_set, consumed_set = set(declared), set(consumed)
        missing = sorted(declared_set - consumed_set)
        undeclared = sorted(consumed_set - declared_set)
        return {
            "ok": (not missing and not errors),
            "missing": missing,
            "undeclared": undeclared,
            "errors": errors,
        }
    except Exception as exc:  # fail-closed: check helper never raises
        return {"ok": False, "missing": [], "undeclared": [],
                "errors": [f"check error: {exc}"]}
