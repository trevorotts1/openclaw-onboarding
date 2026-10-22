"""Honest reasoning/effort representation (finding D30, spec 7.5 / 15.3).

Rules enforced here, in code:

* A provider that supports reasoning WITHOUT an effort selector is represented
  honestly: reasoning on, no effort claim, no fabricated ladder.
* A UI ladder cannot create provider support. Any UI/alias-declared effort is
  ignored; only the authoritative catalog entry decides what is supported.
* A generic runtime `thinking=max` log is never proof of a model-specific
  parameter being honored.
* An unsupported required parameter is refused with a typed reason, never
  silently stripped from the request.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Claims we will never emit for a model without an effort selector.
FABRICATED_CLAIMS = ("high", "xhigh", "max", "medium", "low")


@dataclass
class ModelCaps:
    model_id: str
    reasoning: bool
    effort_selector: bool  # authoritative: catalog exposes reasoning_effort
    tools: bool = False
    provider: str = ""
    source_revision: str = ""
    fetched_at: str = ""


@dataclass
class EffortPlan:
    model_id: str
    params: Optional[Dict[str, Any]]
    claim: str
    refusal: Optional[str] = None
    fabricated: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "params": self.params,
            "claim": self.claim,
            "refusal": self.refusal,
            "fabricated": self.fabricated,
        }


def plan_request(caps: ModelCaps, requested_effort: Optional[str], required: bool = True,
                 ui_ladder: Optional[Dict[str, Any]] = None) -> EffortPlan:
    """Plan the actual request parameters for one model.

    `ui_ladder` is accepted only to be OVERRULED: it can never add effort
    support the authoritative catalog does not expose.
    """
    if not caps.reasoning:
        if requested_effort and required:
            return EffortPlan(caps.model_id, None, "reasoning_unsupported", refusal="UNSUPPORTED_EFFORT", fabricated=True)
        return EffortPlan(caps.model_id, {}, "reasoning_unsupported")

    if not caps.effort_selector:
        # Reasoning without an effort selector: represent honestly.
        if requested_effort and requested_effort != "none":
            if required:
                return EffortPlan(
                    caps.model_id, None,
                    "reasoning_without_effort_selector",
                    refusal="UNSUPPORTED_EFFORT: %s exposes reasoning but no effort selector" % caps.model_id,
                    fabricated=True,
                )
            return EffortPlan(caps.model_id, {}, "reasoning_without_effort_selector")
        return EffortPlan(caps.model_id, {}, "reasoning_without_effort_selector")

    # Effort selector supported: the requested value is a real parameter.
    params: Dict[str, Any] = {}
    claim = "reasoning_with_effort_selector"
    if requested_effort and requested_effort != "none":
        params = {"reasoning_effort": requested_effort}
        claim = "reasoning_effort=%s" % requested_effort
    return EffortPlan(caps.model_id, params, claim)


def thinking_log_proof(log_text: str) -> Dict[str, Any]:
    """A generic runtime thinking log is NEVER proof of a model parameter.

    Returns the only honest reading of such a log line.
    """
    return {
        "log": (log_text or "")[:200],
        "proves_model_parameter": False,
        "reason": "generic runtime thinking log shows the runtime attempted thinking; "
                  "it does not prove a model-specific parameter was accepted or honored",
    }
