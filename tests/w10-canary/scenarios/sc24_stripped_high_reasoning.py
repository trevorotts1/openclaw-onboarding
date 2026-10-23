#!/usr/bin/env python3
"""sc24_stripped_high_reasoning.py — acceptance row SC-24 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-24, verbatim):
    "Stripped high-reasoning detection"

Required result (verbatim):
    "NEGATIVE: a response with the high-reasoning signal stripped is detected
     and refused/reported, never accepted as a valid high-reasoning result"

The honest-reasoning planner is the REAL ``capability_control.effort`` and the
dispatch boundary is the REAL ``choice_card.intake_card.ai_models`` of the tree
under test. Catalog values are read from the tree's own ``ai_models.json``.
No network, no paid provider, no channel, no graph mutation.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  --dry-run   identical checks, receipt marked mode=dry-run
  selftest    re-run under deliberate defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc24"
TITLE = "stripped high-reasoning signal refused and reported, never accepted"

MIMO = "openrouter/xiaomi/mimo-v2.6-pro"
GLM = "openrouter/z-ai/glm-5.3"
FLASH = "openrouter/deepseek/deepseek-v4-flash"


def load_core(core):
    cc = H.load_pkg(core, "capability_control")
    am = H.load_pkg(core, "choice_card.intake_card.ai_models")
    return cc, am


def caps_for(cc, am, model_id):
    r = am.MODELS[model_id].get("reasoning") or {}
    return cc.ModelCaps(model_id=model_id,
                        reasoning=bool(r.get("supported")),
                        effort_selector=bool(r.get("effort_selector")),
                        tools="tool_use" in (am.MODELS[model_id].get("capabilities") or []),
                        provider=am.MODELS[model_id].get("route") or "")


def manifest_for(cc):
    auth = {
        MIMO: {"supported_parameters": [], "owned_by": "openrouter",
               "provenance_revision": "rev-1"},
        GLM: {"supported_parameters": ["reasoning_effort"],
              "owned_by": "openrouter", "provenance_revision": "rev-1"},
    }
    host = {
        MIMO: {"capabilities": {"reasoning": True, "tools": True},
               "owned_by": "openrouter", "provenance_revision": "rev-1",
               "provenance_fetched_at": "2026-10-22T00:00:00Z"},
        GLM: {"capabilities": {"reasoning": True, "tools": True},
              "owned_by": "openrouter", "provenance_revision": "rev-1",
              "provenance_fetched_at": "2026-10-22T00:00:00Z"},
    }
    surfaces = {"selectable": [MIMO, GLM],
                "allowlist": {"enabled": [MIMO, GLM], "disabled": []},
                "provider_entries": [], "role_bindings": [],
                "scheduler_jobs": [], "caches": []}
    return cc.resolve_manifest("sc24-fixture", auth, host, surfaces)


def apply_mutation(am, name):
    saved = {}
    if name == "fabricate_mimo_effort":
        saved = copy.deepcopy(am.MODELS[MIMO]["reasoning"])
        am.MODELS[MIMO]["reasoning"]["effort_selector"] = True
        am.MODELS[MIMO]["reasoning"]["efforts"] = ["low", "high"]
    elif name == "glm_effort_dropped":
        saved = copy.deepcopy(am.MODELS[GLM]["reasoning"])
        am.MODELS[GLM]["reasoning"]["effort_selector"] = False
        am.MODELS[GLM]["reasoning"]["efforts"] = []
    return saved


def restore_mutation(am, name, saved):
    if name == "fabricate_mimo_effort" and saved:
        am.MODELS[MIMO]["reasoning"] = saved
    elif name == "glm_effort_dropped" and saved:
        am.MODELS[GLM]["reasoning"] = saved


def scenario(core, muts=frozenset()):
    cc, am = load_core(core)
    c = H.Checks(ROW, TITLE)
    print("SC24 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    saved = {name: apply_mutation(am, name) for name in sorted(muts)
             if name in ("fabricate_mimo_effort", "glm_effort_dropped")}
    try:
        with H.Scratch() as tmp:
            run_dir = str(Path(tmp) / "run")
            bound = am.bind_roles(run_dir, "mimo", "GLM 5.3")
            if not bound.get("ok"):
                c.check("sc24:role-bindings-stored", False,
                        "bind_roles ok=%r message=%r"
                        % (bound.get("ok"), bound.get("message")))
                return c
            c.check("sc24:role-bindings-stored", True,
                    "bind_roles ok=%r build=%r check=%r"
                    % (bound.get("ok"),
                       bound["bindings"]["build"]["model_id"],
                       bound["bindings"]["check"]["model_id"]))

            mimo_caps = caps_for(cc, am, MIMO)
            plan = cc.plan_request(mimo_caps, "high", required=True)
            c.check("sc24:mimo-high-effort-refused-not-fabricated",
                    plan.refusal is not None and plan.fabricated is True
                    and plan.params is None,
                    "refusal=%r fabricated=%r params=%r"
                    % (plan.refusal, plan.fabricated, plan.params))

            honest = cc.plan_request(mimo_caps, None, required=True)
            c.check("sc24:mimo-without-effort-stays-honest",
                    honest.refusal is None and honest.params == {}
                    and honest.claim == "reasoning_without_effort_selector",
                    "refusal=%r params=%r claim=%r"
                    % (honest.refusal, honest.params, honest.claim))

            glm_plan = cc.plan_request(caps_for(cc, am, GLM), "high",
                                       required=True)
            c.check("sc24:glm-high-effort-is-a-real-parameter",
                    glm_plan.refusal is None
                    and glm_plan.params == {"reasoning_effort": "high"},
                    "refusal=%r params=%r claim=%r"
                    % (glm_plan.refusal, glm_plan.params, glm_plan.claim))

            flash_plan = cc.plan_request(caps_for(cc, am, FLASH), "high",
                                         required=True)
            c.check("sc24:non-reasoning-model-refuses-effort",
                    flash_plan.refusal == "UNSUPPORTED_EFFORT"
                    and flash_plan.fabricated is True,
                    "refusal=%r fabricated=%r params=%r"
                    % (flash_plan.refusal, flash_plan.fabricated,
                       flash_plan.params))

            log = cc.thinking_log_proof("thinking=max accepted by runtime")
            c.check("sc24:stripped-thinking-log-never-proves-the-parameter",
                    log["proves_model_parameter"] is False,
                    "proves_model_parameter=%r reason=%r"
                    % (log["proves_model_parameter"], log["reason"][:90]))

            adm_mimo = am.admit_dispatch(run_dir, "build", "mimo",
                                         reasoning_request={"effort": "high"})
            c.check("sc24:dispatch-refuses-effort-on-model-without-selector",
                    adm_mimo.get("ok") is False
                    and adm_mimo.get("error_code") == "REASONING_NOT_SUPPORTED"
                    and "no effort selector" in str(adm_mimo.get("reason")),
                    "ok=%r error_code=%r reason=%r"
                    % (adm_mimo.get("ok"), adm_mimo.get("error_code"),
                       (adm_mimo.get("reason") or "")[:90]))

            adm_glm = am.admit_dispatch(run_dir, "check", "GLM 5.3",
                                        reasoning_request={"effort": "high"})
            c.check("sc24:dispatch-admits-only-proven-effort",
                    adm_glm.get("ok") is True
                    and adm_glm.get("reasoning_request") == {"effort": "high"},
                    "ok=%r reasoning_request=%r verification=%r"
                    % (adm_glm.get("ok"), adm_glm.get("reasoning_request"),
                       (adm_glm.get("reasoning_verification") or "")[:80]))

            adm_turbo = am.admit_dispatch(run_dir, "check", "GLM 5.3",
                                          reasoning_request={"effort": "turbo"})
            c.check("sc24:dispatch-refuses-unlisted-effort",
                    adm_turbo.get("ok") is False
                    and adm_turbo.get("error_code") == "REASONING_NOT_SUPPORTED"
                    and "low or high or max" in str(adm_turbo.get("reason")),
                    "ok=%r error_code=%r reason=%r"
                    % (adm_turbo.get("ok"), adm_turbo.get("error_code"),
                       (adm_turbo.get("reason") or "")[:90]))

            adm_empty = am.admit_dispatch(run_dir, "check", "GLM 5.3",
                                          reasoning_request={})
            c.check("sc24:dispatch-refuses-effort-without-a-value",
                    adm_empty.get("ok") is False
                    and "must name an effort" in str(adm_empty.get("reason")),
                    "ok=%r reason=%r"
                    % (adm_empty.get("ok"),
                       (adm_empty.get("reason") or "")[:90]))

            man = manifest_for(cc)
            findings = cc.effort_claims_findings(man, {MIMO: "high"})
            c.check("sc24:effort-claim-on-unselectored-model-reported",
                    len(findings) == 1
                    and findings[0].code == "UNSUPPORTED_EFFORT_CLAIM",
                    "findings=%r"
                    % ([f.code for f in findings] or "none"))

            clean = cc.effort_claims_findings(man, {GLM: "high"})
            c.check("sc24:effort-claim-on-effort-selector-model-clean",
                    clean == [],
                    "findings=%r" % ([f.code for f in clean] or "none"))
    finally:
        for name in sorted(saved):
            restore_mutation(am, name, saved[name])
    return c


MUTATIONS = {
    "fabricate_mimo_effort": [
        "sc24:mimo-high-effort-refused-not-fabricated",
        "sc24:dispatch-refuses-effort-on-model-without-selector",
    ],
    "glm_effort_dropped": [
        "sc24:glm-high-effort-is-a-real-parameter",
        "sc24:dispatch-admits-only-proven-effort",
    ],
}


def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and len(failed) >= 1
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good
                 else "DID NOT FAIL AS EXPECTED", failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s"
          % ("harness fails on every defect" if ok
             else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "selftest":
        args = H.add_args(description="sc24 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))

    ap = H.add_args(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    core = H.resolve_core(args)
    result = scenario(core)
    if args.out:
        path = Path(args.out) / "receipts"
        code = result.finish(path)
        receipt = path / "sc24.scenario.json"
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
