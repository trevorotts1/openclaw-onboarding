#!/usr/bin/env python3
"""ST10A leftover 1 — a same-token resume cannot land twice.

Focused, self-contained check for the studio claim ledger. It runs against the
tree it lives in (`../studio_claim.py`), so the SAME file is the negative
control on the pre-repair bytes and the positive proof on the repaired bytes.

The hole this closes (U-GEN320, finding S75-018): before the repair the token
resume was a plain UPDATE, so two presenters of ONE stored poll line both
resumed — two materializers on one order.

`_proof` always presents the strongest continuity proof the ledger accepts: the
stored line's fence AND token on the repaired bytes, the token alone on the
pre-repair bytes (the only proof they had). So the negative control fails on the
double resume itself, not on a missing keyword.

Checks:
  R1  two presenters of the SAME stored line yield exactly one resume; the
      second is refused and leaves the row exactly as the first resume left it
      (fence, step, lease)
  R2  a presenter that carries the token but NO fence has no continuity proof
      and is refused, and the row is untouched
  R3  the presenter that re-reads the refreshed line (the row's new fence)
      still resumes: the fix orders the race without wedging a retry
  R4  control: the same-instance re-claim still resumes (T5's retry path is
      not weakened by the fence guard) and the fence advances with it

Run: python3 -I checks/test_st10a_token_resume_fence.py
Exit: 0 all pass, 1 any fail
"""
import importlib.util
import inspect
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
LEDGER = HERE.parent / "studio_claim.py"

WORK = pathlib.Path(tempfile.mkdtemp(prefix="st10a-rf-", dir=str(HERE)))
FAILS = []


def load_ledger():
    spec = importlib.util.spec_from_file_location("sc_st10a_rf", str(LEDGER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SC = load_ledger()


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail else ""))
    if not cond:
        FAILS.append(name)


def _proof(line, *, with_fence=True):
    """The strongest continuity proof this ledger accepts for `line`."""
    args = {"resume_token": line.get("claim_token")}
    if with_fence and "resume_fence" in inspect.signature(
            SC.ClaimLedger.claim_order).parameters:
        args["resume_fence"] = line.get("fence")
    return args


def _fresh(db, order, owner):
    """One fresh claim; return the stored line it hands the caller."""
    with SC.ClaimLedger(db) as led:
        won = led.claim_order(order, owner, now=1000.0, ttl_s=60.0)
        st = led.order_state(order) or {}
    return won, {"claim_token": st.get("claim_token"), "fence": st.get("fence"),
                 "step": st.get("step"),
                 "lease_expires_at": st.get("lease_expires_at")}


def r1_same_line_twice_one_resume():
    db = str(WORK / "r1.db")
    won, line = _fresh(db, "r_r1", "same-owner")
    with SC.ClaimLedger(db) as a:
        first = a.claim_order("r_r1", "same-owner", now=1001.0, ttl_s=60.0,
                              **_proof(line))
        st_a = a.order_state("r_r1") or {}
    with SC.ClaimLedger(db) as b:
        second = b.claim_order("r_r1", "same-owner", now=1002.0, ttl_s=60.0,
                               **_proof(line))
        st_b = b.order_state("r_r1") or {}
    ok = (won is True and first is True and second is False
          and st_a["fence"] == line["fence"] + 1
          and st_b["fence"] == st_a["fence"]
          and st_b["step"] == st_a["step"]
          and st_b["lease_expires_at"] == st_a["lease_expires_at"]
          and st_b["claim_token"] == line["claim_token"])
    return ok, ("fresh=%r first=%r second=%r fence %r->%r->%r step %r/%r "
                "lease %r/%r" % (
                    won, first, second, line["fence"], st_a["fence"],
                    st_b["fence"], st_a["step"], st_b["step"],
                    st_a["lease_expires_at"], st_b["lease_expires_at"]))


def r2_token_without_fence_refused():
    db = str(WORK / "r2.db")
    won, line = _fresh(db, "r_r2", "same-owner")
    with SC.ClaimLedger(db) as a:
        bare = a.claim_order("r_r2", "same-owner", now=1001.0, ttl_s=60.0,
                             **_proof(line, with_fence=False))
        st = a.order_state("r_r2") or {}
    ok = (won is True and bare is False
          and st["fence"] == line["fence"]
          and st["lease_expires_at"] == line["lease_expires_at"])
    return ok, ("fresh=%r token-only=%r fence %r->%r lease %r->%r" % (
        won, bare, line["fence"], st["fence"], line["lease_expires_at"],
        st["lease_expires_at"]))


def r3_refreshed_line_still_resumes():
    db = str(WORK / "r3.db")
    won, line = _fresh(db, "r_r3", "same-owner")
    with SC.ClaimLedger(db) as a:
        first = a.claim_order("r_r3", "same-owner", now=1001.0, ttl_s=60.0,
                              **_proof(line))
        refreshed = a.order_state("r_r3") or {}
    with SC.ClaimLedger(db) as b:
        second = b.claim_order("r_r3", "same-owner", now=1002.0, ttl_s=60.0,
                               **_proof(refreshed))
        st = b.order_state("r_r3") or {}
    ok = (won is True and first is True and second is True
          and st["fence"] == line["fence"] + 2)
    return ok, "fresh=%r first=%r refreshed=%r fence %r->%r" % (
        won, first, second, line["fence"], st.get("fence"))


def r4_same_instance_retry_kept():
    db = str(WORK / "r4.db")
    with SC.ClaimLedger(db) as led:
        first = led.claim_order("r_r4", "same-owner", now=1000.0, ttl_s=60.0)
        again = led.claim_order("r_r4", "same-owner", now=1001.0, ttl_s=60.0)
        st = led.order_state("r_r4") or {}
    ok = first is True and again is True and st.get("fence") == 2
    return ok, "fresh=%r same-instance=%r fence=%r" % (
        first, again, st.get("fence"))


CHECKS = (
    ("R1 one stored line, two presenters", r1_same_line_twice_one_resume),
    ("R2 token without fence refused", r2_token_without_fence_refused),
    ("R3 refreshed line still resumes", r3_refreshed_line_still_resumes),
    ("R4 same-instance retry kept", r4_same_instance_retry_kept),
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
