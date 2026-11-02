#!/usr/bin/env python3
"""ST10A — unique fenced recoverable claims.

Focused, self-contained check for the studio claim ledger and the bridge wake
path. It runs against the tree it lives in (`../studio_claim.py`,
`../studio_bridge.py`), so the SAME file is the negative control on the
pre-repair bytes and the positive proof on the repaired bytes.

Checks:
  T1  two SIMULTANEOUS callers naming themselves with the SAME owner yield
      exactly one current materializer (one True, one refused)
  T2  an expired claim is taken over ONCE, the same order survives, and the
      fence increments (a stale worker is fenced out)
  T3  a stale acknowledgement (old fence) is refused by the bridge and does
      NOT advance the claim; the current fence acknowledges normally
  T4  a live DIFFERENT owner is refused (control: the fix did not weaken it)
  T5  one ledger instance re-claims its own live claim; a second instance with
      the same owner name is refused while that claim is live
  T6  a claim whose process is DEAD is NOT taken over while its lease is
      live, and IS taken over — with a new fence — once that lease has
      expired (Option A: takeover turns on the lease, never on a pid probe)

Run: python3 -I checks/test_st10a_claim_fence.py
Exit: 0 all pass, 1 any fail
"""
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
BRIDGE_DIR = HERE.parent
LEDGER = BRIDGE_DIR / "studio_claim.py"
BRIDGE = BRIDGE_DIR / "studio_bridge.py"

WORK = pathlib.Path(tempfile.mkdtemp(prefix="st10a-", dir=str(HERE)))
FAILS = []


def load_ledger():
    spec = importlib.util.spec_from_file_location("sc_st10a", str(LEDGER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SC = load_ledger()


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail else ""))
    if not cond:
        FAILS.append(name)


WORKER = r'''
import importlib.util, json, os, sys, time
mod_path, db, order, owner, go, hold = sys.argv[1:7]
spec = importlib.util.spec_from_file_location("sc_worker", mod_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
while not os.path.exists(go):
    time.sleep(0.005)
led = m.ClaimLedger(db)
try:
    won = led.claim_order(order, owner)
    st = led.order_state(order) or {}
    print(json.dumps({"won": bool(won), "fence": st.get("fence")}))
    sys.stdout.flush()
except Exception as exc:                       # noqa: BLE001
    print(json.dumps({"won": None, "error": repr(exc)}))
    sys.stdout.flush()
    sys.exit(0)
if won and float(hold) > 0:
    time.sleep(float(hold))
led.close()
'''


def _worker(db, order, owner, hold="0"):
    return [sys.executable, "-I", str(WORK / "worker.py"),
            str(LEDGER), str(db), order, owner,
            str(WORK / "go"), hold]


def t1_same_owner_simultaneous():
    WORK.joinpath("worker.py").write_text(WORKER, encoding="utf-8")
    go = WORK / "go"
    if go.exists():
        go.unlink()
    db = str(WORK / "t1.db")
    a = subprocess.Popen(_worker(db, "r_t1", "same-owner", "3.0"),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    b = subprocess.Popen(_worker(db, "r_t1", "same-owner", "3.0"),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.3)
    go.write_text("go", encoding="utf-8")
    oa, ea = a.communicate(timeout=30)
    ob, eb = b.communicate(timeout=30)
    try:
        ra = json.loads(oa.strip().splitlines()[-1])
        rb = json.loads(ob.strip().splitlines()[-1])
    except Exception:                          # noqa: BLE001
        return False, "unreadable worker output a=%r b=%r err=%r/%r" % (
            oa, ob, ea[-200:], eb[-200:])
    wins = int(bool(ra.get("won"))) + int(bool(rb.get("won")))
    ok = wins == 1 and ra.get("won") is not None and rb.get("won") is not None
    return ok, "same-owner simultaneous winners=%d results=%r,%r" % (wins, ra, rb)


def t2_expired_takeover():
    db = str(WORK / "t2.db")
    with SC.ClaimLedger(db) as led:
        first = led.claim_order("r_t2", "same-owner", now=1000.0, ttl_s=5.0)
        st1 = led.order_state("r_t2")
    with SC.ClaimLedger(db) as led:
        second = led.claim_order("r_t2", "same-owner", now=1010.0, ttl_s=5.0)
        st2 = led.order_state("r_t2")
    ok = (first is True and second is True and st1 is not None
          and st2 is not None and st2["fence"] == st1["fence"] + 1
          and st2["step"] == st1["step"] and st2["order_id"] == "r_t2")
    return ok, "first=%r second=%r fence %r->%r step %r->%r" % (
        first, second, (st1 or {}).get("fence"), (st2 or {}).get("fence"),
        (st1 or {}).get("step"), (st2 or {}).get("step"))


def t3_stale_ack():
    db = str(WORK / "t3.db")
    with SC.ClaimLedger(db) as led:
        led.claim_order("r_t3", "same-owner", now=2000.0, ttl_s=5.0)
        st1 = led.order_state("r_t3")
        led.advance_step("r_t3", "same-owner", SC.STEP_WAKE_QUEUED,
                         now=2000.0, ttl_s=5.0, fence=st1["fence"])
    with SC.ClaimLedger(db) as led:
        led.claim_order("r_t3", "same-owner", now=2010.0, ttl_s=5.0)
        st2 = led.order_state("r_t3")
    stale = subprocess.run(
        [sys.executable, "-I", str(BRIDGE), "wake", "--ack",
         "--order", "r_t3", "--db", db, "--fence", str(st1["fence"])],
        capture_output=True, text=True)
    with SC.ClaimLedger(db) as led:
        after_stale = led.order_state("r_t3")
    try:
        stale_json = json.loads(stale.stdout)
    except Exception:                          # noqa: BLE001
        stale_json = {}
    fresh = subprocess.run(
        [sys.executable, "-I", str(BRIDGE), "wake", "--ack",
         "--order", "r_t3", "--db", db, "--fence", str(st2["fence"])],
        capture_output=True, text=True)
    try:
        fresh_json = json.loads(fresh.stdout)
    except Exception:                          # noqa: BLE001
        fresh_json = {}
    with SC.ClaimLedger(db) as led:
        after_fresh = led.order_state("r_t3")
    ok = (st2["fence"] == st1["fence"] + 1
          and stale.returncode == 2 and stale_json.get("code") == "STALE_ACK"
          and after_stale["step"] == SC.STEP_WAKE_QUEUED
          and fresh.returncode == 0
          and fresh_json.get("execution_accepted") is True
          and after_fresh["step"] == SC.STEP_EXECUTION_ACCEPTED)
    return ok, ("fence %r->%r stale(rc=%r code=%r step=%r) "
                "fresh(rc=%r code=%r step=%r)" % (
                    st1["fence"], st2["fence"], stale.returncode,
                    stale_json.get("code"), after_stale["step"],
                    fresh.returncode, fresh_json.get("code"),
                    after_fresh["step"]))


def t4_live_other_owner_refused():
    db = str(WORK / "t4.db")
    with SC.ClaimLedger(db) as led:
        a = led.claim_order("r_t4", "ownerA", now=3000.0, ttl_s=60.0)
    with SC.ClaimLedger(db) as led:
        b = led.claim_order("r_t4", "ownerB", now=3000.0, ttl_s=60.0)
        owner = led.claim_owner("r_t4")
    ok = a is True and b is False and owner == "ownerA"
    return ok, "ownerA=%r ownerB=%r stored=%r" % (a, b, owner)


def t5_same_instance_resume_other_instance_refused():
    db = str(WORK / "t5.db")
    with SC.ClaimLedger(db) as led:
        a = led.claim_order("r_t5", "same-owner", now=4000.0, ttl_s=60.0)
        again = led.claim_order("r_t5", "same-owner", now=4000.0, ttl_s=60.0)
    with SC.ClaimLedger(db) as other:
        b = other.claim_order("r_t5", "same-owner", now=4000.0, ttl_s=60.0)
    ok = a is True and again is True and b is False
    return ok, "same-instance first=%r again=%r other-instance=%r" % (
        a, again, b)


def t6_dead_holder_not_taken_over_until_expiry():
    """OPTION A (base contract changed by PR #2777).

    A claim outlives its process. A dead holder's claim is NOT recovered while
    its lease is live, and IS recovered — with a new fence and a new token —
    once the lease has expired. Two asserts, so neither half can pass alone:
    dropping the refusal would let a second materializer steal a live claim;
    dropping the expiry takeover would wedge the order forever.
    """
    WORK.joinpath("worker.py").write_text(WORKER, encoding="utf-8")
    go = WORK / "go6"
    if go.exists():
        go.unlink()
    go.write_text("go", encoding="utf-8")
    db = str(WORK / "t6.db")
    p = subprocess.Popen(_worker(db, "r_t6", "same-owner", "0"),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate(timeout=30)       # exits: its pid is now dead
    try:
        first = json.loads(out.strip().splitlines()[-1])
    except Exception:                          # noqa: BLE001
        return False, "worker output unreadable %r %r" % (out, err[-200:])
    if not first.get("won"):
        return False, "worker did not win the fresh claim: %r" % (first,)
    with SC.ClaimLedger(db) as led:
        st1 = led.order_state("r_t6") or {}
        # lease STILL LIVE, holder pid DEAD -> refused (no pid probe)
        refused = led.claim_order("r_t6", "same-owner")
        st2 = led.order_state("r_t6") or {}
        # lease EXPIRED -> taken over, new fence, new token
        taken = led.claim_order(
            "r_t6", "same-owner",
            now=st1["lease_expires_at"] + 1.0, ttl_s=60.0)
        st3 = led.order_state("r_t6") or {}
    ok = (int(first["fence"]) == st1.get("fence") == st2.get("fence")
          and refused is False
          and st2.get("claim_token") == st1.get("claim_token")
          and taken is True
          and st3.get("fence") == st1.get("fence") + 1
          and st3.get("claim_token") != st1.get("claim_token"))
    return ok, ("dead-holder live-lease refused=%r fence %r->%r->%r; "
                "expired-lease taken=%r token changed=%r"
                % (refused, first.get("fence"), st2.get("fence"),
                   st3.get("fence"), taken,
                   st3.get("claim_token") != st1.get("claim_token")))


CHECKS = (
    ("T1 simultaneous same-owner", t1_same_owner_simultaneous),
    ("T2 expired takeover", t2_expired_takeover),
    ("T3 stale ack refused", t3_stale_ack),
    ("T4 live other owner refused", t4_live_other_owner_refused),
    ("T5 same-instance resume", t5_same_instance_resume_other_instance_refused),
    ("T6 dead holder not taken over until expiry",
     t6_dead_holder_not_taken_over_until_expiry),
)


def main():
    try:
        for name, fn in CHECKS:
            try:
                ok, detail = fn()
            except Exception as exc:           # noqa: BLE001
                ok, detail = False, "raised %r" % (exc,)
            check(name, ok, detail)
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
    print("ALL PASS" if not FAILS else "%d CHECK(S) FAILED: %s"
          % (len(FAILS), ", ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
