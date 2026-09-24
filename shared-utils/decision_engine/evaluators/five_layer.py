#!/usr/bin/env python3
"""D17 five-layer scorer (JEV spec 1.1, ss 8.5/8.6, gated by 8.2 + D16).

Scores one candidate on the five retained alignment dimensions (spec 8.5):

  1. mission        — Company mission.
  2. owner_values   — Owner values and explicit style preferences.
  3. company_kpis   — Current company goals/KPIs.
  4. dept_kpis      — Department objectives, when a department applies.
  5. task_fit       — This task's method and subject fit (ACTUAL task-part,
                      descriptive rubric levels — never "rate 1-10", spec 8.6).

READS, never rebuilds, the existing mechanisms:

  * weights   — ``shared-utils/adaptive_weights.py``: caller overrides win;
    otherwise ``get_weights_for_task(task_text, mode)`` (category-aware
    adaptive policy); otherwise ``DEFAULT_WEIGHTS`` (20/25/20/20/15).
    Layer keys here are IDENTICAL to that module's keys, so the adaptive
    set applies verbatim (``_normalize`` guards rounding drift).
  * scoring   — D03 ``policies/__init__.py`` ``normalize_score`` (level /
    (N - 1), raises on bad input — never a silent 0 or 0.6) and
    ``aggregate_fit`` (configured weights over APPLICABLE dims only, i.e.
    renormalization over legitimately N/A layers is inherent).
  * gating    — D16 ``personas/evidence_profiles.py``
    ``assess_blend_applicability`` runs FIRST when the caller does not
    supply an applicability result; a supplied result is NEVER re-decided.
    Blend-not-applicable modes (mechanical/answer) carry no audience voice,
    so skipped layers cite the D16 mode + reason_code as provenance.
  * judgments — D02 ``contracts/schema.py``: per-layer
    ``{question_id, chosen_level, evidence_refs}`` satisfies the envelope
    ``judgments`` type (only ``question_id`` non-empty is required), so
    emitted judgments round-trip through ``validate_envelope``.

Spec 8.5 N/A rules enforced, not silently papered over:

  * no selected department (``department_id is None``) forces
    ``dept_kpis`` to ``not_applicable``; an applicable caller input for it
    in that state RAISES (a fabricated department score is forbidden);
  * missing mission/value information is marked N/A with a reason — never
    a synthetic neutral score (the old 0.6 heuristic default is rejected
    here: every applicable layer needs an explicit descriptive level);
  * every N/A layer carries a non-empty reason (provenance).

Uncertainty: per-layer confidence (D16 ``CONFIDENCE_LEVELS``) travels with
the normalized distribution; the spread (max - min of applicable
normalized scores) is stored separately from the aggregate; the aggregate
confidence is the WEAKEST applicable layer (min ordinal) — aggregate
certainty can never exceed its weakest required evidence.

Batch: candidates score independently under shared context; ranking is by
aggregate descending with ties broken deterministically by candidate id
ascending (stable, no randomness, no cross-candidate reads — spec 8.7).

Stdlib only. No network, no provider access, no state writes. Validators
never raise on malformed input (``(ok=False, errors)`` fail-closed);
scoring builders DO raise ValueError on missing/invalid answers, mirroring
D03/D16: a bad answer must never become a silent default.

ponytail: aggregate confidence is min-ordinal (weakest link), ceiling is a
calibrated model; upgrade path is a calibrated aggregator behind the same
``confidence`` field (no API change).
"""

from __future__ import annotations

import math
from pathlib import Path

# Five retained alignment dimensions (spec 8.5). Keys intentionally match
# shared-utils/adaptive_weights.py weight keys exactly.
LAYERS = ("mission", "owner_values", "company_kpis", "dept_kpis", "task_fit")

# D16 modes where no audience-facing communication is created: no voice or
# audience blend applies, so skipped layers cite this path as provenance.
NON_BLEND_MODES = ("mechanical", "answer", "unresolved")

# Confidence ordinals (D16 CONFIDENCE_LEVELS order). Aggregate never exceeds
# the weakest applicable layer.
_CONFIDENCE_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
_CONFIDENCE_NAMES = ("none", "low", "medium", "high")


def _load_deps():
    """Return (pol, de, ep, aw): the REAL D03/D02/D16/adaptive modules.

    File-location loading (offline test convention, mirrors ladder.py):
    works whether five_layer.py is imported as a package or loaded
    standalone. The adaptive-weights module lives at shared-utils/ root,
    not in the decision_engine package, so it is located by path.
    """
    import importlib.util
    import sys
    here = Path(__file__).resolve()
    de_dir = here.parent.parent
    shared = de_dir.parent

    def _by_path(mod_name, path):
        existing = sys.modules.get(mod_name)
        if existing is not None:
            return existing
        spec = importlib.util.spec_from_file_location(mod_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        return module

    pol = _by_path("d17_policies", de_dir / "policies" / "__init__.py")
    de = _by_path("d17_schema", de_dir / "contracts" / "schema.py")
    ep = _by_path("d17_evidence", de_dir / "personas" / "evidence_profiles.py")
    aw = _by_path("d17_adaptive_weights", shared / "adaptive_weights.py")
    return pol, de, ep, aw


_pol, _de, _ep, _aw = _load_deps()

CONFIDENCE_LEVELS = _ep.CONFIDENCE_LEVELS

__all__ = [
    "LAYERS",
    "NON_BLEND_MODES",
    "CONFIDENCE_LEVELS",
    "default_weights",
    "validate_layer_input",
    "validate_result",
    "score_candidate",
    "score_batch",
]


def default_weights(task_text=None, mode: str = "leadership") -> dict:
    """Adaptive default weights (READS shared-utils/adaptive_weights.py).

    Caller overrides (see ``score_candidate(weights=...)``) always win.
    Otherwise the category-aware adaptive policy applies when a task text
    is given; with no task text the documented DEFAULT_WEIGHTS apply.
    Never raises on bad mode — falls back to DEFAULT_WEIGHTS fail-closed.
    """
    try:
        if isinstance(task_text, str) and task_text.strip():
            got = _aw.get_weights_for_task(task_text, mode or "leadership")
            if isinstance(got, dict) and set(got) == set(LAYERS):
                return dict(got)
    except Exception:
        pass
    return dict(_aw.DEFAULT_WEIGHTS)


def _is_finite_number(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, float) and math.isfinite(v)


def validate_layer_input(layer: str, spec) -> tuple[bool, list[str]]:
    """Validate one layer input. Returns ``(ok, errors)``; never raises."""
    try:
        if layer not in LAYERS:
            return False, [f"layer {layer!r} not in {list(LAYERS)}"]
        if not isinstance(spec, dict):
            return False, [f"{layer}: spec must be an object"]
        if spec.get("not_applicable") is True:
            reason = spec.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                return False, [f"{layer}: N/A layer needs a non-empty 'reason' (provenance)"]
            return True, []
        errors: list[str] = []
        if not isinstance(spec.get("question_id", layer), str) or not spec.get("question_id", layer).strip():
            errors.append(f"{layer}: 'question_id' must be a non-empty string")
        level, levels = spec.get("level"), spec.get("levels")
        if not isinstance(level, int) or isinstance(level, bool):
            errors.append(f"{layer}: 'level' must be an int descriptive level (never a 0-10 float)")
        if not isinstance(levels, int) or isinstance(levels, bool) or levels < 2:
            errors.append(f"{layer}: 'levels' must be an int >= 2")
        elif isinstance(level, int) and not isinstance(level, bool) and not 0 <= level < levels:
            errors.append(f"{layer}: level {level} out of range for {levels} levels")
        if levels == 10:
            desc = spec.get("descriptions")
            if not isinstance(desc, list) or len(desc) != 10 or any(
                    not isinstance(s, str) or not s.strip() for s in desc):
                errors.append(f"{layer}: 10-level input without 10 descriptions is 'rate 1-10' — rejected")
            elif len(set(desc)) != len(desc):
                errors.append(f"{layer}: rubric descriptions must be distinct (no 1-10 mush)")
        refs = spec.get("evidence_refs")
        if not isinstance(refs, list) or not refs or any(
                not isinstance(r, str) or not r.strip() for r in refs):
            errors.append(f"{layer}: 'evidence_refs' must be a non-empty list of non-empty strings")
        if spec.get("confidence") not in _CONFIDENCE_NAMES:
            errors.append(f"{layer}: 'confidence' must be one of {list(_CONFIDENCE_NAMES)}")
        return (len(errors) == 0), errors
    except Exception as exc:  # fail-closed: validator never raises
        return False, [f"{layer}: validator error: {exc}"]


def _resolve_applicability(*, applicability, message, task_type, artifact_intent):
    """D16 blend applicability FIRST. A supplied result is never re-decided."""
    if isinstance(applicability, dict) and applicability.get("mode"):
        return dict(applicability), "caller"
    if isinstance(message, str) and message.strip():
        out = _ep.assess_blend_applicability(
            message, artifact_intent=artifact_intent or "unknown",
            task_type=task_type or "unknown")
        return out, "d16"
    return {
        "mode": "unresolved", "audience_facing": False,
        "task_persona_needed": False, "answer_only": False,
        "mechanical_only": False, "reason_code": "no-message-supplied",
        "note": "no message and no caller applicability; scores stand on explicit levels only",
    }, "none"


def _resolve_weights(weights, *, task_text, mode):
    if weights is None:
        return default_weights(task_text, mode or "leadership"), "adaptive-default"
    if not isinstance(weights, dict):
        raise ValueError("weights must be an object keyed by layer")
    if set(weights) != set(LAYERS):
        raise ValueError(f"weights must cover exactly {list(LAYERS)}, got {sorted(weights)}")
    for layer, w in weights.items():
        if not _is_finite_number(w) or w < 0:
            raise ValueError(f"weights[{layer!r}]: must be finite >= 0, got {w!r}")
    if math.fsum(weights.values()) <= 0:
        raise ValueError("total weights must be > 0")
    return dict(weights), "caller-override"


def score_candidate(
    candidate_id,
    layer_inputs,
    *,
    weights=None,
    task_text=None,
    mode: str = "leadership",
    department_id=None,
    applicability=None,
    message=None,
    task_type: str = "unknown",
    artifact_intent: str = "unknown",
) -> dict:
    """Score one candidate on the five layers. Raises ValueError on bad input.

    ``layer_inputs`` maps layer name to an applicable spec
    ``{level, levels, evidence_refs, confidence[, question_id][,
    descriptions]}`` or an N/A spec ``{not_applicable: True, reason}``.
    ``department_id=None`` forces ``dept_kpis`` N/A (spec 8.5); an
    applicable caller input for it then raises instead of fabricating.
    """
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("candidate_id must be a non-empty string")
    if not isinstance(layer_inputs, dict):
        raise ValueError("layer_inputs must be an object keyed by layer")
    if set(layer_inputs) != set(LAYERS):
        raise ValueError(f"layer_inputs must cover exactly {list(LAYERS)}, got {sorted(layer_inputs)}")

    app, decided_by = _resolve_applicability(
        applicability=applicability, message=message,
        task_type=task_type, artifact_intent=artifact_intent)
    app_mode = app.get("mode", "unresolved")

    eff: dict = {}
    na_layers: dict = {}
    for layer in LAYERS:
        spec = layer_inputs[layer]
        if department_id is None and layer == "dept_kpis":
            if isinstance(spec, dict) and spec.get("not_applicable") is True:
                reason = spec.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    raise ValueError("dept_kpis N/A needs a non-empty 'reason'")
                eff[layer] = {"not_applicable": True, "reason": reason.strip()}
            elif isinstance(spec, dict) and "level" in spec:
                raise ValueError(
                    "dept_kpis: no department selected — department-goal fit is "
                    "not_applicable, not a fabricated score (spec 8.5)")
            else:
                eff[layer] = {
                    "not_applicable": True,
                    "reason": "spec 8.5: no department selected — department-goal fit "
                              "is not_applicable, not a fabricated score",
                }
            na_layers[layer] = eff[layer]["reason"]
            continue
        ok, errs = validate_layer_input(layer, spec)
        if not ok:
            raise ValueError(f"{layer}: " + "; ".join(errs))
        if isinstance(spec, dict) and spec.get("not_applicable") is True:
            eff[layer] = {"not_applicable": True, "reason": spec["reason"].strip()}
            na_layers[layer] = eff[layer]["reason"]
        else:
            eff[layer] = spec

    weights_used, weights_source = _resolve_weights(
        weights, task_text=task_text, mode=mode)

    dims: dict = {}
    for layer in LAYERS:
        if layer in na_layers:
            continue
        spec = eff[layer]
        dims[layer] = {
            "level": spec["level"], "levels": spec["levels"],
            "weight": weights_used[layer],
        }
    if not dims:
        raise ValueError("all five layers N/A: nothing to score")
    agg = _pol.aggregate_fit(dims)  # raises on bad level/levels; renormalizes over applicable

    total_w = agg["total_weight"]
    renorm = {layer: (weights_used[layer] / total_w if layer in dims else 0.0)
              for layer in LAYERS}

    ords = {layer: _CONFIDENCE_ORDER[eff[layer]["confidence"]] for layer in dims}
    weakest = min(ords.values())
    spread = (max(agg["distribution"].values()) - min(agg["distribution"].values())) \
        if len(agg["distribution"]) > 1 else 0.0

    judgments: list[dict] = []
    for layer in LAYERS:
        if layer in na_layers:
            judgments.append({
                "question_id": (eff[layer].get("question_id") if isinstance(
                    eff.get(layer), dict) and eff[layer].get("question_id") else f"{candidate_id}:{layer}"),
                "chosen_level": None,
                "levels": None,
                "normalized": None,
                "evidence_refs": [],
                "confidence": "none",
                "status": "not_applicable",
                "reason": na_layers[layer],
            })
            continue
        spec = eff[layer]
        judgments.append({
            "question_id": spec.get("question_id") or f"{candidate_id}:{layer}",
            "chosen_level": spec["level"],
            "levels": spec["levels"],
            "normalized": agg["distribution"][layer],
            "evidence_refs": list(spec["evidence_refs"]),
            "confidence": spec["confidence"],
            "status": "scored",
        })

    return {
        "candidate_id": candidate_id,
        "aggregate": agg["aggregate"],
        "distribution": dict(agg["distribution"]),
        "spread": spread,
        "confidence": _CONFIDENCE_NAMES[weakest],
        "confidence_ordinal": weakest,
        "per_layer_confidence": {layer: eff[layer]["confidence"] for layer in dims},
        "judgments": judgments,
        "weights": renorm,
        "weights_source": weights_source,
        "total_applicable_weight": total_w,
        "na_layers": dict(na_layers),
        "provenance": {
            "applicability_mode": app_mode,
            "applicability_reason": app.get("reason_code", ""),
            "applicability_decided_by": decided_by,
            "blend_applicable": bool(app.get("audience_facing")),
            "department_id": department_id,
        },
    }


def score_batch(candidates, **shared) -> list[dict]:
    """Score N candidates independently; rank aggregate desc, id asc ties.

    Every candidate is scored by ``score_candidate`` with the same shared
    context — no candidate reads another's output (spec 8.7 independence).
    Raises ValueError on malformed batch input (never a silent partial).
    """
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a non-empty list")
    seen: set[str] = set()
    results: list[dict] = []
    for i, item in enumerate(candidates):
        if not isinstance(item, dict):
            raise ValueError(f"candidates[{i}]: required object")
        cid = item.get("candidate_id")
        if not isinstance(cid, str) or not cid.strip():
            raise ValueError(f"candidates[{i}]: required non-empty 'candidate_id'")
        if cid in seen:
            raise ValueError(f"candidates[{i}]: duplicate candidate_id {cid!r}")
        seen.add(cid)
        layers = item.get("layers")
        if not isinstance(layers, dict):
            raise ValueError(f"candidates[{i}]: required 'layers' object")
        results.append(score_candidate(cid, layers, **shared))
    results.sort(key=lambda r: (-r["aggregate"], r["candidate_id"]))
    return results


def validate_result(res) -> tuple[bool, list[str]]:
    """Validate a score result. Returns ``(ok, errors)``; never raises."""
    try:
        if not isinstance(res, dict):
            return False, [f"result is not an object (got {type(res).__name__})"]
        errors: list[str] = []
        if not isinstance(res.get("candidate_id"), str) or not res["candidate_id"].strip():
            errors.append("'candidate_id': required non-empty string")
        agg = res.get("aggregate")
        if not _is_finite_number(agg) or not 0.0 <= float(agg) <= 1.0:
            errors.append(f"'aggregate': required finite number in [0, 1], got {agg!r}")
        dist = res.get("distribution")
        if not isinstance(dist, dict) or not dist:
            errors.append("'distribution': required non-empty object")
        else:
            for layer, v in dist.items():
                if layer not in LAYERS:
                    errors.append(f"'distribution': unknown layer {layer!r}")
                elif not _is_finite_number(v) or not 0.0 <= float(v) <= 1.0:
                    errors.append(f"'distribution[{layer}]': required finite in [0, 1], got {v!r}")
        if res.get("confidence") not in _CONFIDENCE_NAMES:
            errors.append(f"'confidence': must be one of {list(_CONFIDENCE_NAMES)}")
        jud = res.get("judgments")
        if not isinstance(jud, list) or not jud:
            errors.append("'judgments': required non-empty list")
        else:
            for i, j in enumerate(jud):
                if not isinstance(j, dict):
                    errors.append(f"'judgments[{i}]': required object")
                elif not isinstance(j.get("question_id"), str) or not j["question_id"].strip():
                    errors.append(f"'judgments[{i}]': required non-empty 'question_id' (D02 type)")
        w = res.get("weights")
        if not isinstance(w, dict) or set(w) != set(LAYERS):
            errors.append(f"'weights': must cover exactly {list(LAYERS)}")
        prov = res.get("provenance")
        if not isinstance(prov, dict) or not prov.get("applicability_mode"):
            errors.append("'provenance.applicability_mode': required (D16 decided first)")
        return (len(errors) == 0), errors
    except Exception as exc:  # fail-closed
        return False, [f"validator error: {exc}"]
