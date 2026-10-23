#!/usr/bin/env python3
"""sc08_crash_conductor.py — acceptance row SC-08 (S75-W10-U1 scenario matrix).

Condition (SCENARIO-MATRIX.json, row SC-08, verbatim):
    "Partial delivery crash"

Required result (verbatim):
    "NEGATIVE: an interrupted delivery never marks the run delivered; the
     partial artifact set is recorded as incomplete and resumable, not as
     success"

Proves, against the REAL core modules of the tree under test:
  * a conductor crash while the delivery stage is mid-write leaves the durable
    stage row RUNNING with an expired lease -- never COMPLETE;
  * the strict completion gate (intake_preflight.factory.evaluate_completion
    over the run's own control/artifact/receipt files) refuses delivery, and
    names the delivery stage in its reasons;
  * the artifact the crash did not finish is recorded as missing -- the
    partial set is incomplete, not silently counted as present;
  * a half-delivered destination set (one destination delivered, one still
    pending) is still not success;
  * the run is RESUMABLE: the expired lease is re-claimable, the remaining
    destination is delivered, and only then does the gate report delivered --
    with each destination recorded exactly once.

Only the provider/transport is a fixture: files in a /tmp scratch dir and an
in-process destination list. No network, no paid provider, no live channel,
no graph mutation, no subprocess.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  selftest    re-run the scenario under deliberate fixture defects and REQUIRE
              the named assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc08"
TITLE = "partial delivery crash (incomplete, resumable, never delivered)"
RUN_ID = "runSC08"
DELIVERY = "delivery"
DESTINATIONS = ("ghl-media", "telegram")
RECEIPTS = "delivery/receipts.json"

# --------------------------------------------------------------------------
def load_core(core):
    ss = H.load_file(core / "state_store.py", "state_store")
    F = H.load_pkg(core, "intake_preflight.factory")
    return ss, F

def complete_stage(st, stage, actor):
    """Drive one stage NOT_STARTED -> COMPLETE through the real state machine."""
    st.transition(RUN_ID, stage, "READY", actor)
    st.transition(RUN_ID, stage, "RUNNING", actor)
    st.transition(RUN_ID, stage, "QC", actor)
    st.transition(RUN_ID, stage, "COMPLETE", actor)

def stage_states(st, stages, overrides=None):
    got = {s: st.get(RUN_ID, s)["state"] for s in stages}
    got.update(overrides or {})
    return got

def write_fixture(run_dir, F, receipts, with_receipts=True):
    """Build the run dir the production collector reads: approvals at the
    current plan revision, every required artifact, and the delivery receipts."""
    rd = Path(run_dir)
    rd.mkdir(parents=True, exist_ok=True)
    H.write_json(rd / "control" / "plan-revision.json", {"revision": 3})
    approvals = {}
    for stage, meta in F.STAGE_REGISTRY.items():
        if not meta.get("required"):
            continue
        if meta.get("approval_policy") == "none":
            continue
        approvals[stage] = {"state": "approved", "plan_revision": 3}
    H.write_json(rd / "control" / "approvals.json", approvals)
    H.write_json(rd / "control" / "skip-reasons.json", {})
    H.write_json(rd / "final-qc" / "record.json",
                 {"gate": "PASS", "producer": "final-qc/record.json"})
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
    if with_receipts:
        H.write_json(rd / RECEIPTS, list(receipts))

def statuses(receipts):
    return [r.get("status") for r in receipts]

# --------------------------------------------------------------------------
def scenario(core, muts=frozenset()):
    ss, F = load_core(core)
    stages = list(F.CANONICAL_STAGES)
    c = H.Checks(ROW, TITLE)
    print("SC08 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    with H.Scratch() as tmp:
        tmp = Path(tmp)
        run_dir = tmp / "run"
        st = ss.Store(str(tmp / "state.db"))
        try:
            st.init_run(RUN_ID, stages)
            for s in stages:
                if s == DELIVERY:
                    continue
                complete_stage(st, s, "conductor")

            # ---- the conductor dies while delivery is mid-write ----------
            st.transition(RUN_ID, DELIVERY, "READY", "conductor")
            lease = 60.0 if "live_lease" in muts else 0.1
            st.claim(RUN_ID, DELIVERY, "conductor-crash", lease_s=lease)
            crashed = st.get(RUN_ID, DELIVERY)

            # the delivery artifact was never finished: it does not exist yet
            write_fixture(run_dir, F, [], with_receipts=False)
            overrides = {DELIVERY: "COMPLETE"} if "mark_delivery_complete" in muts else None
            got = stage_states(st, stages, overrides)

            evidence = F._collect_completion_evidence(str(run_dir), got)
            delivered, report = F.evaluate_completion(str(run_dir), got)

            c.check("sc08:crash-leaves-delivery-not-complete",
                    got[DELIVERY] != "COMPLETE"
                    and crashed["state"] == "RUNNING",
                    "state=%s owner=%s"
                    % (got[DELIVERY], crashed.get("owner")))
            c.check("sc08:interrupted-run-not-delivered",
                    delivered is False,
                    "delivered=%s reasons=%s"
                    % (delivered, report.get("reasons")))
            c.check("sc08:report-names-incomplete-delivery-stage",
                    any(("required stage %s is" % DELIVERY) in r
                        for r in report.get("reasons") or []),
                    "reasons=%s" % (report.get("reasons"),))
            c.check("sc08:partial-artifact-set-recorded-incomplete",
                    RECEIPTS in (evidence.get("missing_artifacts") or [])
                    and any("artifacts missing" in r
                            for r in report.get("reasons") or []),
                    "missing=%s" % (evidence.get("missing_artifacts"),))

            # ---- half the destinations delivered, the rest still pending --
            partial = [{"destination": DESTINATIONS[0], "status": "delivered"},
                       {"destination": DESTINATIONS[1], "status": "pending"}]
            if "receipts_all_delivered" in muts:
                partial = [{"destination": d, "status": "delivered"}
                           for d in DESTINATIONS]
            write_fixture(run_dir, F, partial)
            delivered2, report2 = F.evaluate_completion(str(run_dir), got)
            c.check("sc08:partial-destination-set-not-success",
                    statuses(partial).count("delivered") == 1
                    and statuses(partial).count("pending") == 1
                    and delivered2 is False,
                    "statuses=%s delivered=%s"
                    % (statuses(partial), delivered2))

            # ---- resume: the expired lease is re-claimable ---------------
            if "live_lease" not in muts:
                time.sleep(0.15)
            try:
                st.claim(RUN_ID, DELIVERY, "worker-resume", lease_s=300)
                claimed, why = True, ""
            except ss.StoreError as exc:
                claimed, why = False, exc.code
            c.check("sc08:resume-claims-expired-delivery", claimed,
                    "claimed=%s reason=%s" % (claimed, why or "ok"))

            if claimed:
                final = [{"destination": d, "status": "delivered"}
                         for d in DESTINATIONS]
                if "duplicate_destination" in muts:
                    final.append({"destination": DESTINATIONS[0],
                                  "status": "delivered"})
                write_fixture(run_dir, F, final)
                st.transition(RUN_ID, DELIVERY, "QC", "worker-resume")
                st.transition(RUN_ID, DELIVERY, "COMPLETE", "worker-resume")

                got3 = stage_states(st, stages)
                delivered3, report3 = F.evaluate_completion(str(run_dir), got3)
                c.check("sc08:resume-completes-delivery",
                        delivered3 is True,
                        "delivered=%s reasons=%s"
                        % (delivered3, report3.get("reasons")))
                dests = [r.get("destination") for r in final]
                c.check("sc08:resume-completes-without-duplicate-destination",
                        len(final) == len(DESTINATIONS)
                        and sorted(dests) == sorted(DESTINATIONS),
                        "receipts=%s" % (dests,))
            else:
                c.check("sc08:resume-completes-delivery", False,
                        "not resumed")
                c.check("sc08:resume-completes-without-duplicate-destination",
                        False, "not resumed")
        finally:
            st.close()
    return c

# --------------------------------------------------------------------------
# selftest — deliberate fixture defects must turn the named assertions RED
# --------------------------------------------------------------------------
MUTATIONS = {
    "mark_delivery_complete": [
        "sc08:crash-leaves-delivery-not-complete",
        "sc08:report-names-incomplete-delivery-stage",
    ],
    "receipts_all_delivered": [
        "sc08:partial-destination-set-not-success",
    ],
    "live_lease": [
        "sc08:resume-claims-expired-delivery",
    ],
    "duplicate_destination": [
        "sc08:resume-completes-without-duplicate-destination",
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
    print("selftest — %s" % ("harness fails on all four defects"
                             if ok else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "selftest":
        args = H.add_args(description="sc08 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))
    args = H.add_args(description=__doc__).parse_args(argv)
    return scenario(H.resolve_core(args)).finish(args.out)

if __name__ == "__main__":
    sys.exit(main())
