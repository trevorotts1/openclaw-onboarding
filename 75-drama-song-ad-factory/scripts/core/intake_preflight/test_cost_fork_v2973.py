#!/usr/bin/env python3
"""L4.5 (v2.9.73): the cost/approval fork's safe default is bounded by the
remaining ledger balance and never above the run's declared budget.

Live proof: the Voyage To Virtue run sat for hours on small money questions
(fallback-model pricing, a paid redo) with no recorded default; the rule is a
DECISION — never a spend above the remaining ledger balance or above the
run's declared budget — recorded with cost, balance, budget, reason and UTC
time in $RUN/control/fork-decisions.json and carried on the envelope.

Proves, behaviourally (stdlib only, no network, no provider, real $0 ledgers
built with the real spend_ledger in a temp dir — costs are integers, no
floats):
  1. a cost that fits the remaining ledger balance records "proceed";
  2. a cost ABOVE the remaining balance records "wait", never a spend above
     the balance, with the reason naming both numbers;
  3. a cost that fits the balance but exceeds the run's DECLARED budget
     records "wait" (the budget bounds, exactly as the spec demands);
  4. no readable ledger -> "wait" is the safe default (never a guess);
  5. an UNKNOWN cost -> "wait", never auto-spent;
  6. every decision is recorded (appended) in fork-decisions.json with
     at_utc, decision, cost, remaining balance, budget, reason — and a
     second fork is APPENDED, never clobbered;
  7. the recorded decision carries "never above budget" in its structure:
     a proceed can never co-exist with cost > min(balance, budget).

Run: python3 scripts/core/intake_preflight/test_cost_fork_v2973.py
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = Path(HERE).parent
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(HERE))

import factory as F                # noqa: E402  (unit under test)
import spend_ledger as SL          # noqa: E402  (the real balance reader)

FAILS = []


def check(name, cond, detail=""):
    print("%s %s%s" % ("ok" if cond else "FAIL", name,
                       (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def ledger_with(run_dir, run_id, ceiling, committed=0):
    """A REAL $0 spend ledger: init_run with the given ceiling, plus
    `committed` of reconciled actual_cost via plan/reserve/mark_terminal/
    reconcile (still $0 costs)."""
    db = str(run_dir / "spend.sqlite3")
    SL.init_run(db, run_id, ceiling)
    for n in range(committed):
        key = "committed-%d" % n
        SL.plan(db, run_id, key, "a1", "digest", estimated_cost=0, stage="x")
        SL.reserve(db, run_id, key, "a1")
        SL.mark_terminal(db, run_id, key, "a1", "succeeded", actual_cost=0)
        SL.reconcile(db, run_id, key, "a1", "succeeded", actual_cost=0,
                     stage="x")
    return db


def main():
    tmp = Path(tempfile.mkdtemp(prefix="costfork-"))
    RID = "fork-test-run"

    # 1. fits the balance -> proceed
    run = tmp / "run1"
    (run / "control").mkdir(parents=True)
    ledger_with(run, RID, ceiling=10000)
    d = F.cost_fork(run, "f1", 2500, label="make 4 clips",
                    budget_minor=9000, now=1760000000.0)
    check("cost 25.00 under remaining 100.00 -> proceed",
          d["decision"] == "proceed", str(d))
    check("decision records the remaining balance",
          d["remaining_balance_minor"] == 10000)
    check("decision is recorded on disk",
          d["recorded"] is True and d["path"].endswith("fork-decisions.json"),
          str(d.get("path")))
    check("decided_at is a UTC ISO stamp",
          d["at_utc"] == "2025-10-09T08:53:20Z", d["at_utc"])

    # 2. above the remaining balance -> wait
    run2 = tmp / "run2"
    (run2 / "control").mkdir(parents=True)
    ledger_with(run2, RID, ceiling=1000)
    d2 = F.cost_fork(run2, "f2", 2500, budget_minor=9000,
                     now=1760000000.0)
    check("cost 25.00 over remaining 10.00 -> wait",
          d2["decision"] == "wait", str(d2))
    check("reason names the cost and the balance",
          "2500" in d2["reason"] and "1000" in d2["reason"], d2["reason"])

    # 3. fits the balance, over the declared budget -> wait
    run3 = tmp / "run3"
    (run3 / "control").mkdir(parents=True)
    ledger_with(run3, RID, ceiling=10000)
    d3 = F.cost_fork(run3, "f3", 9500, budget_minor=8000,
                     now=1760000000.0)
    check("cost under balance but over the declared budget -> wait",
          d3["decision"] == "wait", str(d3))
    check("reason names the declared budget",
          "declared budget" in d3["reason"], d3["reason"])

    # 4. no ledger -> wait
    run4 = tmp / "run4"
    (run4 / "control").mkdir(parents=True)
    d4 = F.cost_fork(run4, "f4", 2500, now=1760000000.0)
    check("no readable ledger -> wait (the safe default)",
          d4["decision"] == "wait", str(d4))
    check("the wait reason is the balance reason",
          "no readable ledger" in d4["reason"], d4["reason"])

    # 5. unknown cost -> wait
    run5 = tmp / "run5"
    (run5 / "control").mkdir(parents=True)
    ledger_with(run5, RID, ceiling=10000)
    d5 = F.cost_fork(run5, "f5", None, now=1760000000.0)
    check("unknown cost -> wait, never auto-spent",
          d5["decision"] == "wait" and "unknown cost" in d5["reason"],
          str(d5))
    d5b = F.cost_fork(run5, "f5b", 0, now=1760000000.0)
    check("cost 0 is not a spendable fork -> wait",
          d5b["decision"] == "wait", str(d5b))
    # a parked run's balance reads as not ok -> None -> wait
    run5b = tmp / "run5b"
    (run5b / "control").mkdir(parents=True)
    db5 = ledger_with(run5b, RID, ceiling=10000)
    SL.park_run(db5, RID)
    d5c = F.cost_fork(run5b, "f5c", 100, now=1760000000.0)
    check("a parked run (no spendable balance) -> wait",
          d5c["decision"] == "wait", str(d5c))

    # 6. recorded, appended, never clobbered
    doc = F._read_json(run / "control" / "fork-decisions.json", {})
    forks = [f for f in (doc.get("forks") or [])
             if f.get("fork_id") == "f1"]
    check("fork 1 recorded exactly once",
          len(forks) == 1 and forks[0]["decision"] == "proceed", str(forks))
    d6 = F.cost_fork(run, "f6", 2500, now=1760000100.0)
    doc2 = F._read_json(run / "control" / "fork-decisions.json", {})
    ids = [f.get("fork_id") for f in doc2.get("forks") or []]
    check("a second fork is appended, the first intact",
          ids == ["f1", "f6"] and d6["decision"] == "proceed", str(ids))

    # 7. the structural bound: proceed co-exists only with cost <= both
    d7 = F.cost_fork(run, "f7", 2500, budget_minor=20000, now=1760000200.0)
    ok = True
    if d7["decision"] == "proceed":
        bal = d7["remaining_balance_minor"]
        fit = (d7["cost_minor"] <= bal
               and (d7["budget_minor"] is None
                    or d7["cost_minor"] <= d7["budget_minor"]))
        ok = fit
    check("a proceed is bounded by min(remaining, budget)",
          ok, str(d7))
    over = F.cost_fork(run, "f8", 10 ** 9, now=1760000300.0)
    check("an over-budget fork never records proceed",
          over["decision"] == "wait", str(over))

    print()
    if FAILS:
        print("FAILED: %d: %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("test_cost_fork_v2973: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())