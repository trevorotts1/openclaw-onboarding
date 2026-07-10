#!/usr/bin/env python3
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: loop_backoff.py
# Exponential backoff WITH JITTER - the ONLY sanctioned retry shape (spec 5.2).
# -----------------------------------------------------------------------------
# base 2h (the never-stop doctrine's own number), doubling, capped at 24h, state
# PERSISTED ON DISK per job (survives restarts - a backoff that lives in memory
# resets to zero on the next crash, which is how "backoff" becomes a storm).
# Reconciles the never-stop doctrine (spec 5.4): the job is never "stopped"; each
# failure schedules the NEXT attempt at an ever-larger interval, and after K tries
# the retry breaker hands it up to Rescue Rangers parked-and-resumable. A tight
# retry storm is not persistence, it is arson.
#
# Deterministic: the interval sequence is pure arithmetic; jitter is bounded and,
# in the self-test, disabled (fraction 0) so the sequence is exactly 2h/4h/8h/16h.
# NO model call, NO network.
# =============================================================================
"""loop_backoff.py - persisted exponential backoff for redispatch/retry jobs."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import loop_common as C  # noqa: E402
from loop_ledger import Ledger  # noqa: E402


def interval_seconds(attempt, base, multiplier, cap):
    """The (un-jittered) interval BEFORE the given attempt (attempt is 1-based).
    attempt 1 -> base; 2 -> base*mult; ... capped at `cap`."""
    if attempt < 1:
        attempt = 1
    val = base * (multiplier ** (attempt - 1))
    return min(int(val), int(cap))


def jittered(seconds, fraction, rand=None):
    """Add +/- `fraction` jitter deterministically when `rand` is provided (a value in
    [0,1)); with fraction 0 the interval is returned exactly (used by the self-test)."""
    if fraction <= 0:
        return int(seconds)
    if rand is None:
        import random
        rand = random.random()
    delta = seconds * fraction
    return int(seconds - delta + (2 * delta * rand))


def register_failure(job, thresholds, ledger, max_tries=None, rand=None):
    """Record one more failure for `job`, advance the attempt counter, and compute the
    next-attempt time from the PERSISTED state. Returns a dict:
      {job, attempt, interval_seconds, next_at, escalate: bool}
    `escalate` is True once attempt > max_tries (the retry breaker converts try-K+1
    into parked-resumable + Rescue Rangers, spec 5.4). NEVER returns 'stop'."""
    bo = thresholds["backoff"]
    base, mult, cap, frac = (bo["base_seconds"], bo["multiplier"],
                             bo["cap_seconds"], bo["jitter_fraction"])
    max_tries = max_tries if max_tries is not None else \
        C.load_skill_config("breakers.json")["breakers"]["retry"]["max_consecutive"]
    prior = ledger.get_backoff(job)
    attempt = (prior["attempt"] if prior else 0) + 1
    interval = jittered(interval_seconds(attempt, base, mult, cap), frac, rand)
    next_at = (datetime.now(timezone.utc) + timedelta(seconds=interval)) \
        .replace(microsecond=0).isoformat()
    escalate = attempt > max_tries
    ledger.upsert_backoff(job, attempt=attempt, base_seconds=base, cap_seconds=cap,
                          next_at=next_at, escalated=1 if escalate else 0)
    return {"job": job, "attempt": attempt, "interval_seconds": interval,
            "next_at": next_at, "escalate": escalate}


def clear(job, ledger):
    """A real artifact of progress was observed -> reset the job's backoff (spec 5.4:
    progress measured by REAL artifacts, never 'cron ran ok')."""
    ledger.upsert_backoff(job, attempt=0, base_seconds=0, cap_seconds=0, next_at=None)


def self_test():
    import tempfile
    print("[loop_backoff] self-test: 2h/4h/8h/16h/24h(cap), persistence, escalate-after-K")
    th = C.load_skill_config("thresholds.json")
    b = th["backoff"]
    # pure sequence (jitter off): 2h, 4h, 8h, 16h, then capped at 24h.
    seq = [interval_seconds(a, b["base_seconds"], b["multiplier"], b["cap_seconds"])
           for a in range(1, 7)]
    assert seq[0] == 7200 and seq[1] == 14400 and seq[2] == 28800 and seq[3] == 57600
    assert seq[4] == 86400 and seq[5] == 86400  # capped at 24h
    print("  sequence case: PASS (2h,4h,8h,16h,cap 24h,cap 24h)")

    assert jittered(1000, 0.1, rand=0.5) == 1000     # midpoint = exact
    assert jittered(1000, 0.1, rand=0.0) == 900      # lower bound
    assert jittered(1000, 0.1, rand=0.9999) >= 1099  # upper bound
    assert jittered(1000, 0.0) == 1000               # fraction 0 = exact (self-test path)
    print("  jitter case: PASS (bounded; fraction 0 exact)")

    with tempfile.TemporaryDirectory() as td:
        led = Ledger(Path(td) / "loop-protection")
        r1 = register_failure("redispatch-x", th, led, max_tries=5, rand=0.5)
        assert r1["attempt"] == 1 and r1["interval_seconds"] == 7200 and not r1["escalate"]
        r2 = register_failure("redispatch-x", th, led, max_tries=5, rand=0.5)
        assert r2["attempt"] == 2 and r2["interval_seconds"] == 14400
        # advance to K+1 -> escalate flips True, but the job is NEVER stopped
        for _ in range(3):
            r = register_failure("redispatch-x", th, led, max_tries=5, rand=0.5)
        r6 = register_failure("redispatch-x", th, led, max_tries=5, rand=0.5)
        assert r6["attempt"] == 6 and r6["escalate"] is True
        assert led.get_backoff("redispatch-x")["escalated"] == 1
        print("  persist+escalate case: PASS (attempt persists; escalate after K, never stop)")

        clear("redispatch-x", led)
        assert led.get_backoff("redispatch-x")["attempt"] == 0
        print("  clear-on-progress case: PASS (real artifact resets backoff)")
        led.close()

    print("[loop_backoff] self-test: PASS")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Loop Protection exponential backoff.")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(self_test())
    ap.print_help()
