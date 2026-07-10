#!/usr/bin/env python3
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: loop_breaker.py
# Circuit breakers - the headline protection (spec Section 5.1).
# -----------------------------------------------------------------------------
# A breaker = (unit, window, max-events, trip-action). Five breakers ship:
#   process  D1 restart velocity   -> STOP + park the unit (visible-red, never respawn)
#   turn     D2 paid-token burn    -> heartbeat allowlist enforce + park cron (never model)
#   retry    D3 identical-signature -> park resumable + escalate (doctrine step 4)
#   cron     D4 re-fire storm      -> disable cron (not delete)
#   healer   the watchdog's OWN fixes -> stop fixing that target, escalate (session-health law)
#
# Every ceiling is a SAFETY CAP under Skill 60 Signal S4: a raise without an operator
# stamp is a P1 (spec 5.1). A tripped breaker PARKS its unit; a parked unit is
# visible-red until fixed and NEVER silently respawns. The healer breaker is what
# stops a healer that loops - the session-health.sh lesson encoded in the machine.
#
# State lives in the ledger (breaker_state / fix_actions). Deterministic, stdlib
# only, NO model call, NO network.
# =============================================================================
"""loop_breaker.py - circuit breakers for the Loop Protection System."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import loop_common as C  # noqa: E402
from loop_ledger import Ledger  # noqa: E402


def load_breakers():
    return C.load_skill_config("breakers.json")["breakers"]


def process_breaker_trips(unit, delta_restarts, day_restarts, breakers):
    """True when the process breaker should trip for `unit`."""
    b = breakers["process"]
    return (delta_restarts >= b["max_events_per_window"]
            or day_restarts >= b["max_events_per_day"])


def retry_breaker_trips(consecutive_identical, breakers):
    b = breakers["retry"]
    return consecutive_identical >= b["max_consecutive"]


def cron_breaker_trips(actual_per_day, declared_per_day, breakers):
    b = breakers["cron"]
    if not declared_per_day:
        return False
    return actual_per_day > declared_per_day * b["overfire_multiple_of_declared"]


def healer_breaker_trips(unit, ledger, breakers, verify_failed=False):
    """The healer's self-breaker: > N fixes on the SAME target / 24h OR any fix-verify
    failure = STOP fixing that target (spec 5.1). Returns (tripped, reason)."""
    b = breakers["healer"]
    if verify_failed and b.get("trip_on_any_verify_failure", True):
        return True, "a fix-verify failed once on '%s' (healer breaker: never a second auto-attempt)" % unit
    n = ledger.fixes_for_target_since(unit, 24)
    if n >= b["max_fixes_per_target_per_day"]:
        return True, ("%d fixes on '%s' in 24h >= %d (healer-loop suspected)"
                      % (n, unit, b["max_fixes_per_target_per_day"]))
    return False, ""


def trip(unit, breaker_name, ledger, park=True):
    """Record a breaker trip in the ledger and (optionally) park the unit. A parked
    unit is visible-red; the watchdog will never auto-restart it."""
    return ledger.upsert_breaker(unit, breaker_name, tripped=1,
                                 parked=1 if park else 0)


def park(unit, ledger):
    return ledger.upsert_breaker(unit, "manual", parked=1, tripped=0)


def unpark(unit, ledger):
    """Clear the parked/tripped state on EVERY breaker row for a unit (operator
    'unpark' after the boot cause is fixed)."""
    cleared = 0
    for row in ledger.parked_units():
        if row["unit"] == unit:
            ledger.upsert_breaker(unit, row["breaker"], parked=0, tripped=0, event_count=0)
            cleared += 1
    # also clear a tripped-but-unparked row
    for row in ledger.tripped_breakers():
        if row["unit"] == unit:
            ledger.upsert_breaker(unit, row["breaker"], parked=0, tripped=0)
            cleared += 1
    return cleared


def cap_raise_without_stamp(current_ceiling, shipped_ceiling):
    """A Loop Protection ceiling loosened beyond its shipped default WITHOUT an
    operator stamp is itself a P1 (spec 5.1/5.2: the system watches the watcher).
    Returns True when current > shipped (a raise)."""
    try:
        return float(current_ceiling) > float(shipped_ceiling)
    except (TypeError, ValueError):
        return False


def self_test():
    import tempfile
    print("[loop_breaker] self-test: process/retry/cron/healer trips, park/unpark, cap-raise")
    br = load_breakers()

    assert process_breaker_trips("cc-app", 12, 900, br) is True   # 12/tick >= 10
    assert process_breaker_trips("cc-app", 3, 40, br) is True      # 40/day >= 40
    assert process_breaker_trips("cc-app", 2, 5, br) is False
    print("  process case: PASS (trips at 10/tick or 40/day)")

    assert retry_breaker_trips(5, br) is True and retry_breaker_trips(4, br) is False
    assert cron_breaker_trips(96, 1, br) is True   # 96/day vs @daily bound 1, > 2x
    assert cron_breaker_trips(2, 96, br) is False  # firing at declared rate
    print("  retry+cron case: PASS")

    with tempfile.TemporaryDirectory() as td:
        led = Ledger(Path(td) / "loop-protection")
        # healer: a single verify failure trips immediately
        t1, why1 = healer_breaker_trips("cc-app", led, br, verify_failed=True)
        assert t1 and "verify" in why1
        # healer: 3 fixes on the same target in 24h trips
        for _ in range(3):
            led.record_fix(None, "LF-6", unit="cc-app", what="park", dry_run=False)
        t2, why2 = healer_breaker_trips("cc-app", led, br)
        assert t2 and "healer-loop suspected" in why2
        t3, _ = healer_breaker_trips("fresh-unit", led, br)
        assert t3 is False
        print("  healer case: PASS (verify-fail OR >3 fixes/24h trips; fresh unit safe)")

        trip("cc-app", "process", led, park=True)
        assert any(r["unit"] == "cc-app" for r in led.parked_units())
        n = unpark("cc-app", led)
        assert n >= 1 and not any(r["unit"] == "cc-app" for r in led.parked_units())
        print("  park/unpark case: PASS (trip parks; unpark clears)")
        led.close()

    assert cap_raise_without_stamp(20, 10) is True     # loosened ceiling
    assert cap_raise_without_stamp(10, 10) is False
    print("  cap-raise case: PASS (a loosened ceiling without a stamp = P1 signal)")

    print("[loop_breaker] self-test: PASS")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Loop Protection circuit breakers.")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(self_test())
    ap.print_help()
