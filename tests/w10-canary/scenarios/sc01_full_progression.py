#!/usr/bin/env python3
"""sc01_full_progression.py — acceptance row SC-01 (S75-W10-U1 scenario matrix).

Condition (SCENARIO-MATRIX.json, row SC-01, verbatim):
    "Whole 12-stage synthetic progression with controlled provider/transport
     fixtures through final delivery, including crashes and user revisions"

Required result (verbatim):
    "POSITIVE: all 12 stages advance in order with recorded per-stage
     artifacts; a crash mid-stage is recovered without repeating a completed
     stage; a user revision re-enters only the affected stage"

Every stage move runs through the REAL core modules of the tree under test
(state_store.py + spend_ledger.py + job_recovery.py). Only the provider and
its transport are fixtures: an in-process recorder that returns deterministic
bytes, makes no network call and buys nothing.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  --dry-run   identical checks, receipt marked mode=dry-run
  selftest    re-run the scenario under deliberate defects and REQUIRE the
              named assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc01"
TITLE = "whole 12-stage synthetic progression (crash + user revision)"
RUN_ID = "runSC01"
CRASH_STAGE = "video-generation"
REVISION_STAGE = "script-lyrics"
PAID_STAGES = ("music", "image-keyframes", "video-generation")


# --------------------------------------------------------------------------
# controlled provider / transport fixture — in-process, no network
# --------------------------------------------------------------------------
class FixtureTransport(object):
    """Records every dispatch and returns deterministic bytes. Never sends."""

    def __init__(self, run_id):
        self.run_id = run_id
        self.calls = []

    def _record(self, kind, stage, attempt):
        self.calls.append({"kind": kind, "stage": stage, "attempt": attempt})

    def submit(self, stage, attempt="a1"):
        self._record("submit", stage, attempt)
        return "fixture-task-%s-%s" % (stage, attempt)

    def poll(self, stage, revision=1, attempt="a1"):
        self._record("poll", stage, attempt)
        body = "stage=%s run=%s revision=%d" % (stage, self.run_id, revision)
        return json.dumps({"schema": "blackceo.sc01.stage-artifact/v1",
                           "run_id": self.run_id, "stage": stage,
                           "revision": revision, "body": body},
                          sort_keys=True).encode("utf-8")

    def count(self, kind, stage=None):
        return sum(1 for c in self.calls
                   if c["kind"] == kind and (stage is None or c["stage"] == stage))

    def submit_order(self):
        seen, order = set(), []
        for c in self.calls:
            if c["kind"] == "submit" and c["stage"] not in seen:
                seen.add(c["stage"])
                order.append(c["stage"])
        return order


class ArtifactLog(object):
    """Per-stage artifact files + sha256 manifest, written inside the scratch."""

    def __init__(self, root, run_id):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.records = []
        self.history = {}

    def record(self, stage, revision, data):
        path = self.root / ("%s.r%d.json" % (stage, revision))
        path.write_bytes(data)
        rec = {"stage": stage, "revision": revision, "path": str(path),
               "sha256": hashlib.sha256(data).hexdigest(),
               "bytes": len(data)}
        self.records.append(rec)
        self.history.setdefault(stage, []).append(rec)
        return rec

    def latest(self, stage):
        rows = self.history.get(stage) or []
        return rows[-1] if rows else None

    def write_manifest(self):
        H.write_json(self.root / "manifest.json",
                     {"schema": "blackceo.sc01.artifact-manifest/v1",
                      "run_id": self.run_id, "artifacts": self.records})


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# module binding
# --------------------------------------------------------------------------
def load_core(core):
    ss = H.load_file(core / "state_store.py", "state_store")
    sl = H.load_file(core / "spend_ledger.py", "spend_ledger")
    jr = H.load_file(core / "job_recovery.py", "sc01_job_recovery")
    F = H.load_pkg(core, "intake_preflight.factory")
    return ss, sl, jr, F


def snapshot(st, stages):
    return {s: (st.get(RUN_ID, s)["state"], st.get(RUN_ID, s)["version"])
            for s in stages}


def drive_stage(st, sl, tr, arts, spend_db, stage, worker, revision=1,
                lease_s=300, crash=False, skip_spend=False):
    """One stage through the real state machine, provider call via fixture."""
    row = st.get(RUN_ID, stage)
    if row["state"] == "NOT_STARTED":
        st.transition(RUN_ID, stage, "READY", worker)
    st.claim(RUN_ID, stage, worker, lease_s=lease_s)

    paid = stage in PAID_STAGES and not skip_spend
    key, attempt = stage + ".job", "a1"
    if paid:
        sl.plan(spend_db, RUN_ID, key, attempt,
                request_digest=hashlib.sha256(
                    ("%s|r%d" % (stage, revision)).encode()).hexdigest()[:16],
                estimated_cost=5, stage=stage)
        sl.reserve(spend_db, RUN_ID, key, attempt)
        remote = tr.submit(stage, attempt)
        sl.mark_submitted(spend_db, RUN_ID, key, attempt, remote)
    else:
        tr.submit(stage, attempt)

    if crash:
        return "crashed"  # process dies: no collect, no artifact, no transition

    data = tr.poll(stage, revision, attempt)
    arts.record(stage, revision, data)
    if paid:
        sl.mark_terminal(spend_db, RUN_ID, key, attempt, "succeeded")

    st.transition(RUN_ID, stage, "QC", worker)
    st.transition(RUN_ID, stage, "COMPLETE", worker)
    if stage == "delivery":
        art = arts.latest("delivery")
        H.write_json(arts.root / "delivery-receipt.json",
                     {"schema": "blackceo.sc01.delivery-receipt/v1",
                      "run_id": RUN_ID, "stage": "delivery",
                      "delivered": True, "artifact_path": art["path"],
                      "artifact_sha256": art["sha256"]})
    return "complete"


def scenario(core, muts=frozenset()):
    ss, sl, jr, F = load_core(core)
    stages = list(F.CANONICAL_STAGES)
    c = H.Checks(ROW, TITLE)
    print("SC01 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    if len(stages) != 12:
        c.check("sc01:canonical-stage-table-is-twelve", False,
                "got %d stages" % len(stages))
        return c

    with H.Scratch() as tmp:
        tmp = Path(tmp)
        db = str(tmp / "state.db")
        spend_db = str(tmp / "spend.db")
        tr = FixtureTransport(RUN_ID)
        arts = ArtifactLog(tmp / "artifacts", RUN_ID)

        st = ss.Store(db)
        try:
            st.init_run(RUN_ID, stages)
            sl.init_run(spend_db, RUN_ID, ceiling=10000, repair_cap=2)

            crash_i = stages.index(CRASH_STAGE)
            before = stages[:crash_i]

            # ---- stages before the crash --------------------------------
            for s in before:
                drive_stage(st, sl, tr, arts, spend_db, s, "worker-a")

            pre_states = snapshot(st, before)
            pre_submits = {s: tr.count("submit", s) for s in before}

            # ---- crash mid-stage ---------------------------------------
            drive_stage(st, sl, tr, arts, spend_db, CRASH_STAGE,
                        "worker-crash", lease_s=0.15, crash=True)
            crashed = st.get(RUN_ID, CRASH_STAGE)
            st.close()
            time.sleep(0.2)                 # the crashed process's lease expires
            st = ss.Store(db)               # restart against the same files
            row = st.get(RUN_ID, CRASH_STAGE)

            c.check("sc01:crash-leaves-mid-stage-running",
                    crashed["state"] == "RUNNING"
                    and row["state"] == "RUNNING"
                    and row["owner"] == "worker-crash"
                    and (row["lease_expires"] or 0) < time.time(),
                    "state=%s owner=%s lease_expired=%s"
                    % (row["state"], row["owner"],
                       (row["lease_expires"] or 0) < time.time()))

            # deliberate defect: recovery re-runs an already-completed stage
            if "repeat_completed" in muts:
                redo = "music"
                st.mark_stale(RUN_ID, redo, "defect: recovery replayed a"
                                            " completed stage")
                drive_stage(st, sl, tr, arts, spend_db, redo,
                            "worker-resume", skip_spend=True)

            # ---- recovery: poll, never resubmit ------------------------
            dup = sl.plan(spend_db, RUN_ID, CRASH_STAGE + ".job", "a2",
                          request_digest="d" * 16, estimated_cost=5,
                          stage=CRASH_STAGE)
            c.check("sc01:crash-recovery-refuses-duplicate-paid-submission",
                    dup.get("reason_code") == "DUPLICATE_LOGICAL_JOB",
                    "a2 reason=%s" % dup.get("reason_code"))

            plan = jr.recover(spend_db, RUN_ID)
            jobs = [j for j in (plan.get("evidence") or {}).get("jobs", [])
                    if j.get("logical_key") == CRASH_STAGE + ".job"]
            c.check("sc01:crash-recovery-plans-poll-not-resubmit",
                    plan.get("outcome") == "ok" and len(jobs) == 1
                    and jobs[0].get("action") == "POLL"
                    and jobs[0].get("attempt_id") == "a1",
                    "%d job(s) action=%s"
                    % (len(jobs), jobs[0].get("action") if jobs else None))

            st.claim(RUN_ID, CRASH_STAGE, "worker-resume", lease_s=300)
            resumed = st.get(RUN_ID, CRASH_STAGE)
            c.check("sc01:crash-recovery-claims-expired-stage",
                    resumed["state"] == "RUNNING"
                    and resumed["owner"] == "worker-resume",
                    "owner=%s" % resumed["owner"])

            data = tr.poll(CRASH_STAGE, 1, "a1")
            arts.record(CRASH_STAGE, 1, data)
            sl.mark_terminal(spend_db, RUN_ID, CRASH_STAGE + ".job", "a1",
                             "succeeded")
            st.transition(RUN_ID, CRASH_STAGE, "QC", "worker-resume")
            st.transition(RUN_ID, CRASH_STAGE, "COMPLETE", "worker-resume")

            post_states = snapshot(st, before)
            repeated = [s for s in before
                        if post_states[s] != pre_states[s]
                        or tr.count("submit", s) != pre_submits[s]]
            c.check("sc01:crash-recovery-does-not-repeat-completed-stages",
                    not repeated,
                    "repeated=%s" % (repeated or "none"))

            c.check("sc01:recovered-stage-produces-one-artifact",
                    len(arts.history.get(CRASH_STAGE) or []) == 1
                    and tr.count("submit", CRASH_STAGE) == 1,
                    "artifacts=%d submits=%d"
                    % (len(arts.history.get(CRASH_STAGE) or []),
                       tr.count("submit", CRASH_STAGE)))

            # ---- stages after the crash --------------------------------
            for s in stages[crash_i + 1:]:
                drive_stage(st, sl, tr, arts, spend_db, s, "worker-a")

            # ---- user revision: only the affected stage re-enters ------
            target = REVISION_STAGE
            pre_rev = snapshot(st, stages)
            pre_calls = {s: (tr.count("submit", s), tr.count("poll", s))
                         for s in stages}

            st.mark_stale(RUN_ID, target,
                          "user revision: hook line changed on re-approval")
            if "revision_fanout" in muts:
                for s in stages[stages.index(target) + 1:]:
                    st.mark_stale(RUN_ID, s,
                                  "defect: revision fanned out downstream")
            drive_stage(st, sl, tr, arts, spend_db, target,
                        "worker-revision", revision=2)
            post_rev = snapshot(st, stages)

            moved = sorted(s for s in stages if post_rev[s] != pre_rev[s])
            c.check("sc01:revision-reenters-only-affected-stage",
                    moved == [target],
                    "moved=%s" % (moved or "none"))

            others = [s for s in stages if s != target]
            c.check("sc01:revision-keeps-completed-stages-complete",
                    all(post_rev[s][0] == "COMPLETE" for s in others),
                    "not complete=%s"
                    % ([s for s in others if post_rev[s][0] != "COMPLETE"]
                       or "none"))

            refired = [s for s in others
                       if (tr.count("submit", s), tr.count("poll", s))
                       != pre_calls[s]]
            c.check("sc01:revision-does-not-refire-unaffected-transport-calls",
                    not refired, "refired=%s" % (refired or "none"))

            hist = arts.history.get(target) or []
            c.check("sc01:revision-advances-artifact-and-keeps-history",
                    len(hist) == 2
                    and [h["revision"] for h in hist] == [1, 2]
                    and hist[0]["sha256"] != hist[1]["sha256"],
                    "revisions=%s distinct=%s"
                    % ([h["revision"] for h in hist],
                       len(hist) == 2 and hist[0]["sha256"] != hist[1]["sha256"]))

            arts.write_manifest()

            # deliberate defect: tamper with the delivered artifact bytes
            if "artifact_corrupt" in muts:
                p = Path(arts.latest("delivery")["path"])
                blob = bytearray(p.read_bytes())
                blob[-2] ^= 0xFF
                p.write_bytes(bytes(blob))

            # ---- final delivery ----------------------------------------
            observed = tr.submit_order()
            c.check("sc01:twelve-stages-advance-in-order",
                    observed == stages,
                    "observed=%d stages in canonical order=%s"
                    % (len(observed), observed == stages))

            mismatched = []
            for s in stages:
                art = arts.latest(s)
                if not art or not Path(art["path"]).is_file():
                    mismatched.append(s)
                elif file_sha(art["path"]) != art["sha256"]:
                    mismatched.append(s)
            c.check("sc01:every-stage-artifact-recorded",
                    len(arts.records) >= 12 and not mismatched,
                    "records=%d bad=%s"
                    % (len(arts.records), mismatched or "none"))

            c.check("sc01:paid-stage-transport-called-once",
                    all(tr.count("submit", s) == 1 for s in PAID_STAGES),
                    "submits=%s"
                    % {s: tr.count("submit", s) for s in PAID_STAGES})

            c.check("sc01:all-twelve-complete-after-revision",
                    all(st.get(RUN_ID, s)["state"] == "COMPLETE"
                        for s in stages),
                    "incomplete=%s"
                    % ([s for s in stages
                        if st.get(RUN_ID, s)["state"] != "COMPLETE"]
                       or "none"))

            receipt = json.loads(
                (arts.root / "delivery-receipt.json").read_text("utf-8"))
            art = arts.latest("delivery")
            c.check("sc01:delivery-receipt-matches-delivered-artifact",
                    receipt.get("delivered") is True
                    and receipt.get("artifact_sha256") == art["sha256"]
                    and file_sha(art["path"]) == receipt.get("artifact_sha256"),
                    "receipt_sha=%s file_sha=%s"
                    % (str(receipt.get("artifact_sha256"))[:12],
                       file_sha(art["path"])[:12]))
        finally:
            st.close()
    return c


# --------------------------------------------------------------------------
# selftest — prove the harness turns RED under deliberate defects
# --------------------------------------------------------------------------
MUTATIONS = {
    "repeat_completed": [
        "sc01:crash-recovery-does-not-repeat-completed-stages",
        "sc01:paid-stage-transport-called-once",
    ],
    "revision_fanout": [
        "sc01:revision-reenters-only-affected-stage",
        "sc01:revision-keeps-completed-stages-complete",
    ],
    "artifact_corrupt": [
        "sc01:every-stage-artifact-recorded",
        "sc01:delivery-receipt-matches-delivered-artifact",
    ],
}


def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and len(failed) >= 2
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
        args = H.add_args(description="sc01 selftest").parse_args(argv[1:])
        core = H.resolve_core(args)
        return selftest(core)

    ap = H.add_args(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    core = H.resolve_core(args)
    result = scenario(core)
    if args.out:
        path = Path(args.out) / "receipts"
        code = result.finish(path)
        receipt = path / "sc01.scenario.json"
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
