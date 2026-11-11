"""Launch text sets: Skill 50's approved SMS copy must land in the built workflow (issue 3).

The reader (launch-c/plan_reader.py) binds ``bindings.sms_copy`` onto every build that waits on a
text set, and ``compile_automation_build`` already merges ``build["bindings"]`` into the compiler,
which writes each matching SMS step's body. What was missing is the refusal: a step the copy never
reached stayed ``copy_pending`` and the build went ahead. ``enforce_sms_copy`` turns that into a
named compile refusal for a build that ELECTED texts; a build with no elected text set keeps the
existing behaviour (its template SMS nodes stay ``copy_pending`` and are reported incomplete).
"""
from __future__ import annotations

from typing import Any, Mapping

CODE_PENDING = "SMS-COPY-PENDING"
CODE_UNBOUND = "SMS-COPY-UNBOUND"


def sms_steps(campaign: Mapping[str, Any], unit_id: str) -> list:
    return [step for wf in campaign.values()
            if isinstance(wf, Mapping) and wf.get("source_unit") == unit_id
            for step in wf.get("templates") or []
            if isinstance(step, Mapping) and step.get("type") == "sms"]


def enforce_sms_copy(campaign: Any, document: Mapping[str, Any]) -> Any:
    """Move every elected-text build with unbound or pending SMS copy from the campaign to its refusals."""
    for build in document.get("builds") or []:
        if not (isinstance(build, Mapping) and build.get("text_sets")):
            continue
        unit = build.get("id")
        steps = sms_steps(campaign, unit)
        bodies = {(s.get("attributes") or {}).get("body") for s in steps}
        pending = [s.get("id") for s in steps if (s.get("attributes") or {}).get("copy_pending")]
        copy = (build.get("bindings") or {}).get("sms_copy") or {}
        unbound = sorted(step_id for step_id, body in copy.items() if body not in bodies)
        if not (pending or unbound or not steps) or not any(
                wf.get("source_unit") == unit for wf in campaign.values()):
            continue
        code = CODE_PENDING if pending else CODE_UNBOUND
        reason = ("elected text set(s) %s: " % ", ".join(build["text_sets"])
                  + ("SMS step(s) %s are still copy_pending" % ", ".join(map(str, pending))
                     if pending else
                     "approved copy for step(s) %s landed in no SMS step"
                     % (", ".join(unbound) or "(none)") if steps else
                     "the build compiles no SMS step to carry the approved copy"))
        for key in [k for k, wf in campaign.items() if wf.get("source_unit") == unit]:
            del campaign[key]
        campaign.refusals.append({
            "id": unit, "unit_key": build.get("unit_key"), "state": "blocked", "code": code,
            "reason": reason, "detail": {"pending": pending, "unbound": unbound}})
    return campaign
