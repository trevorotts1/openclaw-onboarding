"""Notify-transport preflight -- the FIX 22 / FIX 39 shared gate.

FIX 22 (presentation rev2 waves): an unset PRESENTATION_NOTIFY_CMD is a hard
configuration error at LAUNCH (fail-closed), not a warning. Before this, the
watchdog warned-and-continued (presentation-watchdog.sh:16-24) and the launcher
dispatched with no transport at all, so a stalled or blocked job could never
leave the box -- the operator heard nothing until someone happened to look.

THE CONTRACT (single-sourced here, consumed by three surfaces):

  1. launcher.py -- dispatch()'s preflight calls notify_gate() BEFORE any
     process is spawned; unset transport refuses with
     DISPATCH_NOTIFY_REFUSED (-7) / EXIT_NOTIFY_UNCONFIGURED (8).
  2. presentation-watchdog.sh -- the launchd entry hard-exits with the same
     code so the scan pass never runs silently transportless.
  3. FIX 39's pre-roll gate -- `python3 -m presentation_job.notify_preflight`
     per target box; a box with missing/invalid notify config prints
     NOT_READY_NOTIFY and exits non-zero, so it is NOT rolled until
     configured and rechecked (the batch cannot pass with it still in).

FAIL-CLOSED FLAG: PRESENTATION_NOTIFY_FAIL_CLOSED=1 (the rollout default).
=0 is the documented kill-switch for the new launch hard-stop ONLY: it
restores the pre-fix warn-and-continue behavior on both surfaces. It does
NOT restore direct Telegram (FIX 23 owns the transport; the legacy direct
Bot-API path stays behind its own opt-in flag) and it does NOT suppress
FIX 21 SYSTEM-block notifications. Per the rollout doctrine an emergency 0
must emit a severity-high local audit event, expire after one hour unless
renewed, and blocks fleet promotion -- the caller logs the flag state;
this module never performs network I/O.

Exit codes (CLI):
  0 -- transport configured (marker OK)
  0 -- NOT_READY_NOTIFY with PRESENTATION_NOTIFY_FAIL_CLOSED=0 (warn mode;
       still prints the NOT_READY_NOTIFY row -- a flag-0 box is not
       roll-eligible and FIX 39's pre-roll gate must be able to see that)
  8 -- NOT_READY_NOTIFY: transport unset/blank/unparseable (fail-closed)
  5 -- invalid invocation (usage)
"""
from __future__ import annotations

import json
import os
import shlex
import sys

# The rollout flag. Default ON ("1"): fail-closed is the shipped default per
# the fix spec's rollout strategy. Every reader of this value goes through
# fail_closed_enabled() so the flag has exactly one interpretation.
FAIL_CLOSED_ENV = "PRESENTATION_NOTIFY_FAIL_CLOSED"

#: The transport variable the whole notify chain (report.dispatch3,
#: watchdog.py, presentation-watchdog.sh) already keys on.
NOTIFY_CMD_ENV = "PRESENTATION_NOTIFY_CMD"

#: Rollout gate marker: a box in this state is NOT rolled (FIX 39 pre-roll).
NOT_READY_NOTIFY = "NOT_READY_NOTIFY"

#: The autofail code both launch surfaces refuse with.
AF_NOTIFY_UNCONFIGURED = "AF-NOTIFY-UNCONFIGURED"

#: CLI exit code for NOT_READY_NOTIFY (mirrors state.EXIT_GATE_BLOCKED = 3 in
#: spirit but distinct so a caller can tell "notify gate" from other gates).
EXIT_NOTIFY_UNCONFIGURED = 8


def fail_closed_enabled() -> bool:
    """PRESENTATION_NOTIFY_FAIL_CLOSED default ON ("1"); "0" is the documented
    emergency rollback to the pre-fix warn-and-continue behavior. Any value
    other than "0" is ON -- the safe default is fail-closed, never fail-open
    on a typo."""
    return os.environ.get(FAIL_CLOSED_ENV, "1").strip() != "0"


def _transport_value() -> str:
    return (os.environ.get(NOTIFY_CMD_ENV) or "").strip()


def check_notify_config() -> dict:
    """The one structural check every surface shares. Returns a dict, never
    raises, never touches the network, never prints a secret (the transport
    command itself is reported only as present/absent -- it can carry args,
    and PRESENTATION_NOTIFY_CMD is an argv, not a credential, but the report
    stays shape-only so no call site can accidentally log a boxed token it
    was passed through shell history).

    Keys:
      ready          -- True iff a non-blank, shlex-parseable transport argv
                       exists. "Parseable" is required because
                       report.dispatch3() runs it through shlex.split() at
                       dispatch time (U069: tokenise, refuse on unparseable)
       -- a value
                       that is set but unparseable would refuse AT SEND TIME,
                       which is the same silence this fix exists to kill.
      marker         -- "OK" when ready, NOT_READY_NOTIFY when not.
      code           -- AF-NOTIFY-UNCONFIGURED when not ready, None when ready.
      fail_closed    -- whether the hard-stop is armed (flag state).
      reason         -- human-readable, names the variable and the remedy.
      env            -- the environment variable checked.
    """
    raw = _transport_value()
    if not raw:
        return {
            "ready": False,
            "marker": NOT_READY_NOTIFY,
            "code": AF_NOTIFY_UNCONFIGURED,
            "fail_closed": fail_closed_enabled(),
            "reason": (f"{NOTIFY_CMD_ENV} is unset or blank -- watchdog stall "
                       f"notifications and job progress/blocked/done messages "
                       f"cannot leave this box. Configure the gateway "
                       f"transport (e.g. PRESENTATION_NOTIFY_CMD pointing at "
                       f"presentation-notify.py) before launching."),
            "env": NOTIFY_CMD_ENV,
        }
    try:
        argv = shlex.split(raw)
    except ValueError as exc:
        return {
            "ready": False,
            "marker": NOT_READY_NOTIFY,
            "code": AF_NOTIFY_UNCONFIGURED,
            "fail_closed": fail_closed_enabled(),
            "reason": (f"{NOTIFY_CMD_ENV} is set but not a parseable argument "
                       f"vector ({exc}) -- report.dispatch3 would refuse it "
                       f"at send time, which is the same silence. Fix the "
                       f"variable."),
            "env": NOTIFY_CMD_ENV,
        }
    if not argv:
        return {
            "ready": False,
            "marker": NOT_READY_NOTIFY,
            "code": AF_NOTIFY_UNCONFIGURED,
            "fail_closed": fail_closed_enabled(),
            "reason": (f"{NOTIFY_CMD_ENV} is set but tokenises to an empty "
                       f"argv -- no transport to run."),
            "env": NOTIFY_CMD_ENV,
        }
    return {
        "ready": True,
        "marker": "OK",
        "code": None,
        "fail_closed": fail_closed_enabled(),
        "reason": f"{NOTIFY_CMD_ENV} is configured ({argv[0]}).",
        "env": NOTIFY_CMD_ENV,
    }


def refusal_payload() -> dict:
    """The JSON payload every refusing surface prints -- one shape, three
    call sites, so the log line a fleet operator greps for is identical
    whether it came from the launcher, the watchdog, or the pre-roll gate."""
    result = check_notify_config()
    return {
        "code": result["code"],
        "marker": result["marker"],
        "fail_closed": result["fail_closed"],
        "env": result["env"],
        "flag": FAIL_CLOSED_ENV,
        "detail": result["reason"],
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv:
        print(f"notify_preflight: unknown argument(s): {' '.join(argv)}", file=sys.stderr)
        return 5
    result = check_notify_config()
    print(json.dumps(result, indent=2))
    if result["ready"]:
        return 0
    # Fail-closed is the default. =0 (the documented emergency kill-switch)
    # downgrades the CLI verdict to the old warn state but still prints the
    # NOT_READY_NOTIFY row -- the pre-roll gate (FIX 39) treats a flag-0 box
    # as unshipped and must be able to SEE that, not have it hidden.
    if not result["fail_closed"]:
        print("notify_preflight: fail-closed DISABLED "
              f"({FAIL_CLOSED_ENV}=0) -- warn-only mode, NOT roll-eligible",
              file=sys.stderr)
        return 0
    print(f"notify_preflight: {NOT_READY_NOTIFY} -- {result['reason']}", file=sys.stderr)
    return EXIT_NOTIFY_UNCONFIGURED


if __name__ == "__main__":
    sys.exit(main())