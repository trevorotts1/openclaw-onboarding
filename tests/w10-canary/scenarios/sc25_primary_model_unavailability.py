#!/usr/bin/env python3
"""sc25_primary_model_unavailability.py — acceptance row SC-25 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-25, verbatim):
    "Primary-model unavailability events"

Required result (verbatim):
    "NEGATIVE: primary-model unavailability is surfaced with the provider
     error; no silent substitution of a different model without a recorded,
     permitted fallback"

The classifier/breaker is the REAL ``capability_control.failures`` and the
dispatch boundary is the REAL ``choice_card.intake_card.ai_models`` of the tree
under test. Provider envelopes are fixture dicts. No network, no paid
provider, no channel, no graph mutation.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  --dry-run   identical checks, receipt marked mode=dry-run
  selftest    re-run under deliberate defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc25"
TITLE = "primary-model unavailability surfaced; no silent substitution"

MIMO = "openrouter/xiaomi/mimo-v2.6-pro"
GLM = "openrouter/z-ai/glm-5.3"
ACCT = "acct-sc25-primary"
SUSPENDED = {"status": 403,
             "message": "account suspended by provider: invalid billing state"}


def load_core(core):
    am = H.load_pkg(core, "choice_card.intake_card.ai_models")
    return am


def scenario(core, muts=frozenset()):
    am = load_core(core)
    c = H.Checks(ROW, TITLE)
    print("SC25 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    am.ACCOUNT_BREAKER.close(ACCT)
    try:
        with H.Scratch() as tmp:
            run_dir = str(Path(tmp) / "run")
            if "substitute_primary" in muts:
                bound = am.bind_roles(run_dir, "GLM 5.3", "mimo")
            else:
                bound = am.bind_roles(run_dir, "mimo", "GLM 5.3")
            if not bound.get("ok"):
                c.check("sc25:role-bindings-stored", False,
                        "bind_roles ok=%r message=%r"
                        % (bound.get("ok"), bound.get("message")))
                return c
            c.check("sc25:role-bindings-stored", True,
                    "bind_roles ok=%r build=%r check=%r"
                    % (bound.get("ok"),
                       bound["bindings"]["build"]["model_id"],
                       bound["bindings"]["check"]["model_id"]))

            available = am.selectable(availability={MIMO: "unavailable"})
            ids = [m["id"] for m in available]
            c.check("sc25:unavailable-primary-is-not-selectable",
                    MIMO not in ids and GLM in ids,
                    "selectable ids=%r (primary %r excluded by the availability "
                    "fact)" % (ids, MIMO))

            envelope = SUSPENDED
            if "no_breaker" in muts:
                # defect model: an unavailability treated as a transient blip,
                # so no breaker opens and the dead primary stays dispatchable
                envelope = {"status": 503,
                            "message": "temporarily unavailable"}
            event = am.record_account_failure(ACCT, envelope)
            c.check("sc25:unavailability-surfaces-a-typed-provider-error",
                    event is not None
                    and event.kind == "ACCOUNT_SUSPENDED"
                    and "suspended" in event.action,
                    "event kind=%r action=%r"
                    % (event.kind if event else None,
                       (event.action if event else None)))

            if "breaker_swarm" in muts:
                am.record_account_failure(ACCT + "-second", envelope)
            second = am.record_account_failure(ACCT, envelope)
            open_events = am.ACCOUNT_BREAKER.open_events()
            c.check("sc25:one-actionable-event-not-a-swarm",
                    second is None and len(open_events) == 1
                    and open_events[0].account == ACCT,
                    "second record=%r, open events=%r"
                    % (second.kind if second else None,
                       [e.account for e in open_events]))

            refused = am.admit_dispatch(run_dir, "build", "mimo",
                                        account=ACCT)
            c.check("sc25:dispatch-to-failed-primary-refused-with-the-error",
                    refused.get("ok") is False
                    and refused.get("error_code") == "ACCOUNT_FAILED"
                    and "ACCOUNT_SUSPENDED" in str(refused.get("reason")),
                    "ok=%r error_code=%r reason=%r"
                    % (refused.get("ok"), refused.get("error_code"),
                       (refused.get("reason") or "")[:90]))

            c.check("sc25:suppression-is-counted-not-silent",
                    am.ACCOUNT_BREAKER.suppressed_count(ACCT) >= 1,
                    "suppressed_count=%r for account=%r (dispatch was refused, "
                    "not substituted)"
                    % (am.ACCOUNT_BREAKER.suppressed_count(ACCT), ACCT))

            c.check("sc25:deterministic-work-continues-while-primary-is-down",
                    am.ACCOUNT_BREAKER.deterministic_admit() is True,
                    "deterministic_admit=%r while breaker open=%r"
                    % (am.ACCOUNT_BREAKER.deterministic_admit(),
                       am.ACCOUNT_BREAKER.is_open(ACCT)))

            swapped = am.admit_dispatch(run_dir, "build", "GLM 5.3")
            c.check("sc25:no-silent-substitution-of-a-different-model",
                    swapped.get("ok") is False
                    and swapped.get("error_code") == "MODEL_MISMATCH",
                    "requested=%r ok=%r error_code=%r reason=%r"
                    % ("GLM 5.3", swapped.get("ok"),
                       swapped.get("error_code"),
                       (swapped.get("reason") or "")[:80]))

            fb = am.admit_dispatch(run_dir, "build", "mimo",
                                   fallbacks=["claude sonnet 4.5"])
            c.check("sc25:unpermitted-fallback-refused",
                    fb.get("ok") is False
                    and fb.get("error_code") == "MODEL_NOT_PERMITTED",
                    "fallback=%r ok=%r error_code=%r"
                    % ("claude sonnet 4.5", fb.get("ok"),
                       fb.get("error_code")))

            closed = am.ACCOUNT_BREAKER.close(ACCT)
            reprieved = am.admit_dispatch(run_dir, "build", "mimo",
                                          account=ACCT)
            c.check("sc25:repaired-primary-admits-again",
                    closed is not None
                    and reprieved.get("ok") is True,
                    "close returned status=%r, admit ok=%r"
                    % (closed.status if closed else None,
                       reprieved.get("ok")))
    finally:
        am.ACCOUNT_BREAKER.close(ACCT)
        am.ACCOUNT_BREAKER.close(ACCT + "-second")
    return c


MUTATIONS = {
    "no_breaker": [
        "sc25:unavailability-surfaces-a-typed-provider-error",
        "sc25:dispatch-to-failed-primary-refused-with-the-error",
    ],
    "breaker_swarm": [
        "sc25:one-actionable-event-not-a-swarm",
    ],
    "substitute_primary": [
        "sc25:no-silent-substitution-of-a-different-model",
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
        args = H.add_args(description="sc25 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))

    ap = H.add_args(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    core = H.resolve_core(args)
    result = scenario(core)
    if args.out:
        path = Path(args.out) / "receipts"
        code = result.finish(path)
        receipt = path / "sc25.scenario.json"
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
