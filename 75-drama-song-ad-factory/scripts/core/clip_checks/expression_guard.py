#!/usr/bin/env python3
"""expression_guard.py: run-level guard on the expression check (N-89, section 10C).

Three rules from 10C item 12, in code:

  * a plain contradiction fails;
  * a borderline answer is flagged, not remade;
  * intensity 1 only flags;
  * when more than 3 in 10 of a batch fail on expression, automatic remakes
    stop and the check is re-read against its control pair.

``vision.ExpressionGuard`` holds the per-observation judgement; this module
runs it over a whole batch and turns the stop into the one instruction a run
needs: stop remakes, re-read the controls. It never downgrades a finding.

stdlib only, no spend.
"""
from __future__ import annotations

from . import severity as _SV
from . import vision as _V

TOOL_NAME = "clip_checks.expression_guard"
TOOL_VERSION = "1.0.0"

EXPRESSION_GUARD_REVIEW = "EXPRESSION_GUARD_REVIEW"
CONTROL_REREAD_REQUIRED = "CONTROL_REREAD_REQUIRED"


def run(observations):
    """``observations``: one dict per item, ``{verdict, intensity}``.

    ``verdict`` is 'pass' | 'plain_contradiction' | 'borderline' |
    'unavailable'. Returns the guard's result plus the batch instruction.
    """
    guard = _V.ExpressionGuard()
    for obs in observations or []:
        obs = obs if isinstance(obs, dict) else {}
        guard.observe(obs.get("verdict"), obs.get("intensity", 2))
    out = guard.result()
    if out["stop_remakes"]:
        out["instruction"] = {
            "code": EXPRESSION_GUARD_REVIEW,
            "level": _SV.MEDIUM,
            "action": "stop automatic remakes; re-read the expression check "
                      "against its known-good and known-bad controls "
                      "(%s)" % CONTROL_REREAD_REQUIRED,
        }
    else:
        out["instruction"] = None
    return out


if __name__ == "__main__":
    # Control: borderline and intensity 1 never remake; a plain contradiction
    # does; and a batch over 3 in 10 stops the remakes and asks for a re-read.
    out = run([{"verdict": "borderline", "intensity": 3}])
    assert out["findings"] == [] and out["flags"][0]["action"].startswith("flagged")
    out = run([{"verdict": "plain_contradiction", "intensity": 1}])
    assert out["findings"] == [] and out["flags"]
    out = run([{"verdict": "plain_contradiction", "intensity": 2}])
    assert _SV.only_major(out["findings"]) and out["stop_remakes"] is True
    assert out["instruction"]["code"] == EXPRESSION_GUARD_REVIEW
    batch = [{"verdict": "plain_contradiction", "intensity": 2}] * 2 + \
            [{"verdict": "pass"}] * 8
    assert run(batch)["stop_remakes"] is False          # 2 in 10 does not stop
    assert run([{"verdict": "unavailable"}])["findings"][0]["item"] == 15
    print("expression_guard: control PASS")
