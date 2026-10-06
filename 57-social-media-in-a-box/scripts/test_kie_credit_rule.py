#!/usr/bin/env python3
"""Skill 57 credit rule: required = max(estimate x 1.30, 200); body code must be 200."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import preflight_gate as pg

plan = {"images": True}
def run(est, bal):
    cfg = {"probes": {"kieCredits": bal}}
    if est is not None:
        cfg["creditEstimates"] = {"images": est}
    return pg.check_kie_credits(cfg, live=False, plan=plan)

assert run(None, 200) == [] and run(None, 199)            # absolute floor, no estimate
assert run(1000, 1300) == [] and run(1000, 1299)          # estimate x 1.30
assert run(50, 200) == [] and run(50, 199)                # floor still applies
assert pg.KIE_BALANCE_MULTIPLIER == 1.30
print("test_kie_credit_rule: PASS")
