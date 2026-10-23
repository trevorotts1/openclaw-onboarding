#!/usr/bin/env python3
"""sc09_no_channel_target.py — acceptance row SC-09 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-09, verbatim):
    "No channel target and no receipt"

Required result (verbatim):
    "NEGATIVE: with no channel target the run cannot claim delivered and
     records a named blocked delivery item (no fabricated receipt)"

Proves, against the REAL core modules of the tree under test
(intake_preflight.factory completion gate + cc_sync durable outbox):

  * with no delivery receipts at all the completion gate refuses delivery and
    names the delivery-receipt precondition; the collector never creates the
    receipts file, so no receipt is fabricated by merely reading the run;
  * a blocked delivery item is recorded BY NAME: its destination, status
    "blocked" and reason_code survive the collector verbatim, and a blocked
    item is never counted as a delivered receipt (nor is a mixed
    delivered+blocked set success);
  * the durable outbox refuses a blocked move without a named reason from the
    published set, refuses one without an ask, and when accepted stores the
    reason, the responsible human and the ask on the pending row;
  * with no channel target (no registered deliverable) a review or done move
    is refused by name instead of claiming the work landed;
  * after every refusal the outbox holds no deliverable row and nothing
    acknowledged: the run has no path to a delivered claim.

Only the transport is a fixture: a scratch run dir of files, a scratch SQLite
outbox and an in-process move call. No network, no paid provider, no live
channel, no graph mutation, no subprocess.

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

ROW = "sc09"
TITLE = "no channel target and no receipt (named blocked item, never delivered)"
RECEIPTS = "delivery/receipts.json"
BLOCKED = {"destination": "telegram", "status": "blocked",
           "reason_code": "NO_CHANNEL_TARGET",
           "ask": "Name the delivery channel for this run.",
           "blocked_on_human": "owner"}
DELIVERED = {"destination": "ghl-media", "status": "delivered"}

# --------------------------------------------------------------------------
def load_core(core):
    F = H.load_pkg(core, "intake_preflight.factory")
    CS = H.load_file(core / "cc_sync.py", "cc_sync")
    return F, CS

def write_run(rd, F):
    """Every other completion precondition green, so delivery receipts are the
    ONLY thing the gate can fail on."""
    rd = Path(rd)
    rd.mkdir(parents=True, exist_ok=True)
    H.write_json(rd / "control" / "plan-revision.json", {"revision": 3})
    approvals = {}
    for stage, meta in F.STAGE_REGISTRY.items():
        if not meta.get("required") or meta.get("approval_policy") == "none":
            continue
        approvals[stage] = {"state": "approved", "plan_revision": 3}
    H.write_json(rd / "control" / "approvals.json", approvals)
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
    return str(rd)

def statuses(receipts):
    return [r.get("status") for r in receipts]

# --------------------------------------------------------------------------
def scenario(core, muts=frozenset()):
    F, CS = load_core(core)
    got = {s: "COMPLETE" for s in F.CANONICAL_STAGES}
    c = H.Checks(ROW, TITLE)
    print("SC09 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    with H.Scratch() as tmp:
        tmp = Path(tmp)

        # ---- no receipts at all: refused, and nothing fabricated ---------
        bare = write_run(tmp / "bare", F)
        receipts_path = Path(bare) / RECEIPTS
        if "fabricate_receipt" in muts:
            H.write_json(receipts_path, [DELIVERED])
        existed_before = receipts_path.exists()
        evidence = F._collect_completion_evidence(bare, got)
        delivered, report = F.evaluate_completion(bare, got)
        exists_after = receipts_path.exists()

        c.check("sc09:no-receipts-cannot-claim-delivered",
                delivered is False
                and "destination delivery receipts not all successful"
                in (report.get("reasons") or []),
                "delivered=%s reasons=%s"
                % (delivered, report.get("reasons")))
        c.check("sc09:collector-does-not-fabricate-receipt",
                evidence.get("delivery_receipts_ok") is False
                and existed_before is False and exists_after is False,
                "ok=%s before=%s after=%s"
                % (evidence.get("delivery_receipts_ok"), existed_before,
                   exists_after))

        # ---- a blocked item is recorded by name, never as delivered -----
        run = write_run(tmp / "blocked", F)
        blocked = [dict(BLOCKED)]
        if "blocked_as_delivered" in muts:
            blocked = [dict(BLOCKED, status="delivered")]
        H.write_json(Path(run) / RECEIPTS, blocked)
        ev_blocked = F._collect_completion_evidence(run, got)
        blocked_delivered, blocked_report = F.evaluate_completion(run, got)
        stored = json.loads((Path(run) / RECEIPTS).read_text(encoding="utf-8"))

        c.check("sc09:blocked-item-recorded-by-name",
                stored == [BLOCKED]
                and stored[0].get("reason_code") == "NO_CHANNEL_TARGET"
                and stored[0].get("ask") == BLOCKED["ask"],
                "stored_status=%s reason=%s"
                % (occupied_status(stored), occupied_reason(stored)))
        c.check("sc09:blocked-item-is-not-a-delivered-receipt",
                ev_blocked.get("delivery_receipts_ok") is False
                and blocked_delivered is False
                and "destination delivery receipts not all successful"
                in (blocked_report.get("reasons") or []),
                "statuses=%s ok=%s delivered=%s"
                % (statuses(stored), ev_blocked.get("delivery_receipts_ok"),
                   blocked_delivered))

        mixed = write_run(tmp / "mixed", F)
        H.write_json(Path(mixed) / RECEIPTS, [DELIVERED, dict(BLOCKED)])
        mixed_delivered, mixed_report = F.evaluate_completion(mixed, got)
        c.check("sc09:delivered-plus-blocked-is-not-success",
                statuses([DELIVERED, BLOCKED]).count("delivered") == 1
                and statuses([DELIVERED, BLOCKED]).count("blocked") == 1
                and mixed_delivered is False,
                "statuses=%s delivered=%s"
                % (statuses([DELIVERED, BLOCKED]), mixed_delivered))

        # ---- the durable outbox: a blocked move must be named -----------
        ws = "ws-sc09"
        ob = CS.Outbox(db_path=str(tmp / "outbox.sqlite3"), workspace=ws,
                       base_url="http://127.0.0.1:1")
        try:
            names = []
            for reason in (None, "because"):
                try:
                    ob.enqueue_move("job9", "delivery", "blocked", "agent", ws,
                                    blocked_reason=reason,
                                    blocked_on_human="owner", ask="send it")
                    names.append("accepted")
                except CS.BlockedGateError as exc:
                    names.append(str(exc))
            c.check("sc09:blocked-move-requires-a-named-reason",
                    names == ["blocked requires blocked_reason"] * 2,
                    "refusals=%s" % (names,))

            # an EMPTY ask is the defect under test: it must be refused
            try:
                ob.enqueue_move("job9", "delivery", "blocked", "agent", ws,
                                blocked_reason="credential",
                                blocked_on_human="owner", ask="")
                ask_refusal = "accepted"
            except CS.BlockedGateError as exc:
                ask_refusal = str(exc)
            c.check("sc09:blocked-move-requires-an-ask",
                    ask_refusal == "blocked requires a non-empty ask",
                    "refusal=%s" % (ask_refusal,))

            ask = "" if "omit_ask" in muts \
                else "Name the delivery channel for this run."
            try:
                rid = ob.enqueue_move("job9", "delivery", "blocked", "agent",
                                      ws, blocked_reason="credential",
                                      blocked_on_human="owner", ask=ask)
                rec_err = None
            except CS.BlockedGateError as exc:
                rid, rec_err = None, str(exc)
            if rid is None:
                c.check("sc09:blocked-move-records-reason-and-ask", False,
                        "not recorded: %s" % (rec_err,))
            else:
                payload, state = ob.db.execute(
                    "SELECT payload, state FROM outbox WHERE id=?", (rid,)
                ).fetchone()
                payload = json.loads(payload)
                c.check("sc09:blocked-move-records-reason-and-ask",
                        state == "pending"
                        and payload.get("status") == "blocked"
                        and payload.get("blocked_reason") == "credential"
                        and payload.get("blocked_on_human") == "owner"
                        and payload.get("ask") == ask,
                        "state=%s blocked_reason=%s ask=%.24r"
                        % (state, payload.get("blocked_reason"),
                           payload.get("ask")))

            # ---- no channel target: review/done refused by name ---------
            if "register_deliverable" in muts:
                ob.enqueue_stage_deliverable(
                    "job9", "delivery", "https://example.invalid/run9",
                    "final cut", ws)
            refusals = []
            for status in ("review", "done"):
                try:
                    ob.enqueue_move("job9", "delivery", status, "agent", ws,
                                    evidence="fixture", reviewer="reviewer")
                    refusals.append("accepted")
                except CS.EvidenceError as exc:
                    refusals.append(str(exc))
            c.check("sc09:no-channel-target-refuses-review-and-done",
                    all("has no registered deliverable" in r
                        for r in refusals)
                    and len(refusals) == 2,
                    "refusals=%s" % ([r[:52] for r in refusals],))

            deliverable_rows = ob.db.execute(
                "SELECT COUNT(*) FROM outbox WHERE kind='deliverable'"
            ).fetchone()[0]
            acked = ob.counts().get("acked", 0)
            c.check("sc09:outbox-holds-no-deliverable-and-nothing-acked",
                    deliverable_rows == 0 and acked == 0,
                    "deliverables=%d acked=%d counts=%s"
                    % (deliverable_rows, acked, ob.counts()))
        finally:
            ob.db.close()
    return c

def occupied_status(receipts):
    return receipts[0].get("status") if receipts else None

def occupied_reason(receipts):
    return receipts[0].get("reason_code") if receipts else None

# --------------------------------------------------------------------------
# selftest — deliberate fixture defects must turn the named assertions RED
# --------------------------------------------------------------------------
MUTATIONS = {
    "fabricate_receipt": [
        "sc09:no-receipts-cannot-claim-delivered",
        "sc09:collector-does-not-fabricate-receipt",
    ],
    "blocked_as_delivered": [
        "sc09:blocked-item-recorded-by-name",
        "sc09:blocked-item-is-not-a-delivered-receipt",
    ],
    "omit_ask": [
        "sc09:blocked-move-records-reason-and-ask",
    ],
    "register_deliverable": [
        "sc09:no-channel-target-refuses-review-and-done",
        "sc09:outbox-holds-no-deliverable-and-nothing-acked",
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
        args = H.add_args(description="sc09 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))
    args = H.add_args(description=__doc__).parse_args(argv)
    return scenario(H.resolve_core(args)).finish(args.out)

if __name__ == "__main__":
    sys.exit(main())
