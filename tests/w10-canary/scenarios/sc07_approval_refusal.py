#!/usr/bin/env python3
"""sc07_approval_refusal.py — acceptance row SC-07 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-07, verbatim):
    "Missing / corrupt approval records"

Required result (verbatim):
    "NEGATIVE: advance is refused with a named error (missing or corrupt
     approval) and no paid work is dispatched"

Proves, against the REAL core modules of the tree under test
(intake_preflight.preflight + intake_preflight.factory + spend_ledger):

  * the paid-work gate names the refusal for a missing authorization
    (``approval-missing``), an expired one (``approval-expired``) and one
    bound to another scope (``approval-out-of-scope``);
  * a valid authorization clears the approval gate specifically: the gate
    then stops on the NEXT precondition (the unanswered choice card) instead
    of inventing an approval failure;
  * the completion resolver refuses advance when the approvals file is
    MISSING, UNPARSEABLE, the wrong SHAPE, or STALE against the plan revision
    — every case fails closed on the named reason "approvals not current",
    never a crash and never a silent pass;
  * current approvals for every approval-gated required stage are what turn
    the same resolver to delivered, so the refusal is caused by the defect
    and not by a blanket refusal;
  * no paid work is dispatched: the run's spend ledger stays at zero
    planned/committed cost and zero generation calls through every refusal.

Only the transport is a fixture: a scratch run dir of files and a scratch
SQLite spend ledger. No network, no paid provider, no live channel, no graph
mutation, no subprocess.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  selftest    re-run under deliberate fixture defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc07"
TITLE = "missing / corrupt approval records refuse advance"
RUN_ID = "runSC07"
RECEIPTS = "delivery/receipts.json"
DIGEST = "campaign-digest-sc07"
CARD = {"answers": {"video_style": "Lifelike 3D",
                    "audio_style": "Soul Ballad", "length": 60,
                    "video_model": "MiniMax H3 768P"},
        "who": "fixture", "at": "2026-10-23T09:00:00Z"}

# --------------------------------------------------------------------------
def load_core(core):
    PF = H.load_pkg(core, "intake_preflight.preflight")
    F = H.load_pkg(core, "intake_preflight.factory")
    SL = H.load_file(core / "spend_ledger.py", "spend_ledger")
    return PF, F, SL

def approvals_for(F, plan_rev=3):
    out = {}
    for stage, meta in F.STAGE_REGISTRY.items():
        if not meta.get("required") or meta.get("approval_policy") == "none":
            continue
        out[stage] = {"state": "approved", "plan_revision": plan_rev}
    return out

def write_run(rd, F, mode="current", plan_rev=3):
    """The run dir the production collector reads. ``mode`` selects the
    approval-record defect under test."""
    rd = Path(rd)
    rd.mkdir(parents=True, exist_ok=True)
    H.write_json(rd / "control" / "plan-revision.json", {"revision": plan_rev})
    H.write_json(rd / "control" / "skip-reasons.json", {})
    H.write_json(rd / "final-qc" / "record.json",
                 {"gate": "PASS",
                  "producer": F.STAGE_REGISTRY["final-qc"]["qc_producer"]})
    for stage, meta in F.STAGE_REGISTRY.items():
        if not meta.get("required"):
            continue
        for rel in meta.get("required_artifacts") or []:
            if rel in (RECEIPTS, "final-qc/record.json"):
                continue
            p = rd / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"stage": stage, "fixture": True}) + "\n",
                         encoding="utf-8")
    H.write_json(rd / RECEIPTS, [{"destination": "telegram",
                                  "status": "delivered"}])

    path = rd / "control" / "approvals.json"
    if mode == "missing":
        if path.exists():
            path.unlink()
    elif mode == "corrupt":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"creative-strategy": {"state": "approv', encoding="utf-8")
    elif mode == "wrong-shape":
        H.write_json(path, [{"stage": "creative-strategy", "state": "approved"}])
    elif mode == "stale":
        H.write_json(path, approvals_for(F, plan_rev - 1))
    else:
        H.write_json(path, approvals_for(F, plan_rev))
    return str(rd)

def preflight(payload):
    return payload.get("outcome"), payload.get("reason_code"), \
        (payload.get("checks") or {}).get("readiness")

def ledger_state(SL, db, run_id):
    s = SL.summary(db, run_id)
    ev = s.get("evidence") or {}
    return (s.get("outcome"), int(ev.get("number_of_generation_calls") or 0),
            float(ev.get("committed_cost") or 0)
            + float(ev.get("unknown_or_reserved_cost") or 0))

# --------------------------------------------------------------------------
def scenario(core, muts=frozenset()):
    PF, F, SL = load_core(core)
    got = {s: "COMPLETE" for s in F.CANONICAL_STAGES}
    c = H.Checks(ROW, TITLE)
    print("SC07 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    with H.Scratch() as tmp:
        tmp = Path(tmp)
        base = {"storage_dir": str(tmp), "approved_root": str(tmp)}
        caps = {"media": ["music"], "duration_s": 60}

        # ---- the paid-work gate names each approval refusal --------------
        no_auth = PF.check(dict(base, capabilities=dict(caps)))
        if "supply_auth" in muts:
            no_auth = dict(no_auth, outcome="ok", reason_code="preflight-pass")
        c.check("sc07:missing-authorization-named-approval-missing",
                preflight(no_auth)[:2] == ("rejected", "approval-missing"),
                "outcome=%s reason=%s" % preflight(no_auth)[:2])

        expired = PF.check(dict(base, capabilities=dict(caps),
                                auth={"scope": "campaign",
                                      "expires_unix": 1}))
        if "supply_auth" in muts:
            expired = PF.check(dict(base, capabilities=dict(caps),
                                    auth={"scope": "campaign",
                                          "expires_unix": 4102444800}))
        c.check("sc07:expired-authorization-named-approval-expired",
                preflight(expired)[:2] == ("rejected", "approval-expired"),
                "outcome=%s reason=%s" % preflight(expired)[:2])

        outside = PF.check(dict(base, capabilities=dict(caps),
                                auth={"scope": "someone-else"},
                                summary_digest=DIGEST))
        if "supply_auth" in muts:
            outside = dict(outside, outcome="ok", reason_code="preflight-pass")
        c.check("sc07:out-of-scope-authorization-named",
                preflight(outside)[:2]
                == ("rejected", "approval-out-of-scope"),
                "outcome=%s reason=%s" % preflight(outside)[:2])

        good_auth = PF.check(dict(base, capabilities=dict(caps),
                                  auth={"scope": DIGEST},
                                  summary_digest=DIGEST,
                                  run_state={"card_receipt": CARD}))
        c.check("sc07:valid-authorization-clears-the-approval-gate",
                good_auth.get("reason_code") == "CARD_UNANSWERED"
                and not str(good_auth.get("reason_code") or "").startswith(
                    "approval-"),
                "outcome=%s reason=%s (gate moved to the card precondition)"
                % (good_auth.get("outcome"), good_auth.get("reason_code")))

        # ---- the completion resolver refuses a bad approval record ------
        reason = "approvals not current"
        results = {}
        for mode in ("missing", "corrupt", "wrong-shape", "stale"):
            rd = write_run(tmp / mode, F, mode=mode)
            results[mode] = F.evaluate_completion(rd, got)
        if "grant_everything" in muts:
            for mode in list(results):
                rd = write_run(tmp / (mode + "-good"), F, mode="current")
                results[mode] = F.evaluate_completion(rd, got)

        for mode, name in (("missing", "missing-approval-record-refused"),
                           ("corrupt", "corrupt-approval-record-refused"),
                           ("wrong-shape", "wrong-shape-approval-refused"),
                           ("stale", "stale-approval-revision-refused")):
            delivered, report = results[mode]
            c.check("sc07:" + name,
                    delivered is False
                    and reason in (report.get("reasons") or []),
                    "delivered=%s reasons=%s"
                    % (delivered, report.get("reasons")))

        current = write_run(tmp / "current", F)
        delivered_ok, report_ok = F.evaluate_completion(current, got)
        c.check("sc07:current-approvals-deliver",
                delivered_ok is True and report_ok.get("reasons") == [],
                "delivered=%s reasons=%s"
                % (delivered_ok, report_ok.get("reasons")))

        # ---- no paid work dispatched ------------------------------------
        db = str(tmp / "spend.sqlite3")
        init = SL.init_run(db, RUN_ID, ceiling=10000, repair_cap=2)
        if "dispatch_paid_job" in muts:
            SL.plan(db, RUN_ID, "music.job", "a1",
                    request_digest=DIGEST, estimated_cost=5, stage="music")
            SL.reserve(db, RUN_ID, "music.job", "a1")
        outcome, calls, spend = ledger_state(SL, db, RUN_ID)
        refusals = [preflight(no_auth), preflight(expired),
                    preflight(outside)]
        c.check("sc07:no-paid-work-dispatched",
                init.get("outcome") == "ok" and outcome == "ok"
                and calls == 0 and spend == 0.0
                and all(r[0] != "ok" for r in refusals)
                and all(r[2] != "full" for r in refusals),
                "generation_calls=%d spend=%.2f readiness=%s"
                % (calls, spend, [r[2] for r in refusals]))
    return c

# --------------------------------------------------------------------------
# selftest — deliberate fixture defects must turn the named assertions RED
# --------------------------------------------------------------------------
MUTATIONS = {
    "supply_auth": [
        "sc07:missing-authorization-named-approval-missing",
        "sc07:out-of-scope-authorization-named",
    ],
    "grant_everything": [
        "sc07:missing-approval-record-refused",
        "sc07:corrupt-approval-record-refused",
        "sc07:wrong-shape-approval-refused",
        "sc07:stale-approval-revision-refused",
    ],
    "dispatch_paid_job": [
        "sc07:no-paid-work-dispatched",
    ],
}

def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and bool(failed)
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good else "DID NOT FAIL AS EXPECTED",
                 failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s" % ("harness fails on all three defects"
                             if ok else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "selftest":
        args = H.add_args(description="sc07 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))
    args = H.add_args(description=__doc__).parse_args(argv)
    return scenario(H.resolve_core(args)).finish(args.out)

if __name__ == "__main__":
    sys.exit(main())
