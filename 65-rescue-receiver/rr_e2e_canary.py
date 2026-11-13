#!/usr/bin/env python3
"""rr_e2e_canary.py - the daily end-to-end test of the whole Rescue Rangers chain.

DRAFT. NOT scheduled by wire.sh and not installed by it. A real daily run is a
step for the operator, on the operator's own machine, after n8n units N-18 and
N-7 are deployed. Until then this file is a tool that nobody calls.

It walks the three steps a real case walks, on the operator's OWN box only:

  step 1  rr_escalate.py send      -> state accepted, ticket id recorded
  step 2  wait for the box's own poll cron to leave
          <openclaw root>/state/rr-receiver/case-outcomes/<ticket>.json
          (this script never runs the poll; the poll job on the box does)
  step 3  the outcome must carry owner_notified true and an owner_message
          containing "Rescue Rangers daily test message"

The marker file <openclaw root>/.operator-is-owner is what makes a machine the
operator's own. Without it this script refuses before sending anything.

File written: <openclaw root>/state/rr-receiver/canary/latest.json, exactly
  {"ok": true|false, "ticket_id": ..., "stage_reached": "sent"|"collected"|"owner_notified",
   "seconds": N, "at": <epoch>}

Exit codes: 0 all three steps passed; 10 a step failed (anything else, including
            an unresolvable root); 20 not the operator's own machine.

Usage:
  python3 rr_e2e_canary.py [--root <openclaw root>] [--origin-json '<json>']
  python3 rr_e2e_canary.py --selftest
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time

MARKER = ".operator-is-owner"
REFUSAL = "this test runs on the operator's own box only"
CANARY_TEXT = "Rescue Rangers daily test message"
CLIENT = "__CANARY__"
PERSON = "canary"
PROBLEM = "daily end-to-end test"
TRIED = "none"
INTERVAL = 20.0          # seconds between reads of the outcome file
TIMEOUT = 15 * 60.0      # how long a real run waits for the outcome file
TICKET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def resolve_root(cli_root: str | None) -> str | None:
    """--root, then OC_CONFIG_ROOT, then the two roots a box uses."""
    home = os.path.join(os.path.expanduser("~"), ".openclaw")
    for cand in (cli_root, os.environ.get("OC_CONFIG_ROOT"), "/data/.openclaw", home):
        if cand and os.path.isdir(cand):
            return cand
    return None


def operator_gate(root: str) -> bool:
    return os.path.isfile(os.path.join(root, MARKER))


def send_ticket(escalate: str, origin_json: str, root: str) -> tuple[str | None, str | None]:
    """Step 1. Returns (state, ticket_id). Any failure returns (state or None, None)."""
    cmd = [sys.executable, escalate, "send",
           "--client", CLIENT, "--person", PERSON,
           "--problem", PROBLEM, "--tried", TRIED]
    if origin_json:
        cmd += ["--origin-json", origin_json]
    env = dict(os.environ, OC_CONFIG_ROOT=root)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                           env=env, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    doc = None
    try:
        doc = json.loads(p.stdout.strip())
    except (TypeError, ValueError):
        for line in reversed(p.stdout.splitlines()):
            try:
                doc = json.loads(line)
                break
            except ValueError:
                continue
    if not isinstance(doc, dict):
        return None, None
    ticket = doc.get("ticket_id") or doc.get("ticketId")
    if not isinstance(ticket, str) or not TICKET_RE.match(ticket):
        ticket = None
    return doc.get("state"), ticket


def wait_for_outcome(root: str, ticket: str, interval: float, timeout: float) -> dict | None:
    """Step 2. Reads the file the poll writes; never runs the poll."""
    path = os.path.join(root, "state", "rr-receiver", "case-outcomes", ticket + ".json")
    deadline = time.monotonic() + timeout
    while True:
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    doc = json.load(fh)
                if isinstance(doc, dict):
                    return doc
            except (OSError, ValueError):
                pass    # half-written or unreadable; the poll writes atomically, keep waiting
        if time.monotonic() >= deadline:
            return None
        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))


def owner_confirmed(doc: dict) -> bool:
    """Step 3."""
    msg = doc.get("owner_message")
    return doc.get("owner_notified") is True and isinstance(msg, str) and CANARY_TEXT in msg


def write_verdict(root: str, verdict: dict) -> str:
    folder = os.path.join(root, "state", "rr-receiver", "canary")
    os.makedirs(folder, exist_ok=True)
    try:
        os.chmod(folder, 0o700)
    except OSError:
        pass
    path = os.path.join(folder, "latest.json")
    fd, tmp = tempfile.mkstemp(prefix=".new-", dir=folder)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(verdict, fh, sort_keys=True)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path


def run(root: str, origin_json: str, escalate: str,
        interval: float | None = None, timeout: float | None = None) -> dict:
    """The three steps. Writes and returns the verdict; ok true only on a full pass."""
    interval = INTERVAL if interval is None else interval
    timeout = TIMEOUT if timeout is None else timeout
    started = time.monotonic()
    verdict = {"ok": False, "ticket_id": None, "stage_reached": "sent",
               "seconds": 0, "at": int(time.time())}
    state, ticket = send_ticket(escalate, origin_json, root)
    if state == "accepted" and ticket:
        verdict["ticket_id"] = ticket
        doc = wait_for_outcome(root, ticket, interval, timeout)
        if doc is not None:
            verdict["stage_reached"] = "collected"
            if owner_confirmed(doc):
                verdict["stage_reached"] = "owner_notified"
                verdict["ok"] = True
    verdict["seconds"] = int(round(time.monotonic() - started))
    verdict["at"] = int(time.time())
    write_verdict(root, verdict)
    return verdict


# The simulated rr_escalate.py used by --selftest. It never touches the network.
_STUB = '''\
import json, os
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sent-flag"), "a"):
    pass
print(json.dumps({"state": "accepted", "ticket_id": "RR-000123", "say_to_owner": "ok"}))
'''


def selftest() -> int:
    global INTERVAL, TIMEOUT
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "root")
        outcomes = os.path.join(root, "state", "rr-receiver", "case-outcomes")
        os.makedirs(outcomes)
        stub = os.path.join(tmp, "rr_escalate.py")
        with open(stub, "w", encoding="utf-8") as fh:
            fh.write(_STUB)
        flag = os.path.join(tmp, "sent-flag")
        latest = os.path.join(root, "state", "rr-receiver", "canary", "latest.json")
        out, err = io.StringIO(), io.StringIO()

        def cli(*extra: str) -> tuple[int, str]:
            out.truncate(0), out.seek(0)
            err.truncate(0), err.seek(0)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = main(["--root", root, "--escalate", stub, *extra])
            return rc, out.getvalue() + err.getvalue()

        # 1. no marker: refuses with the exact message, exit 20, nothing sent.
        rc, text = cli()
        ok &= rc == 20 and REFUSAL + "\n" in text and not os.path.exists(flag)
        ok &= not os.path.exists(latest)

        # From here the machine is "the operator's own".
        with open(os.path.join(root, MARKER), "w", encoding="utf-8") as fh:
            fh.write("")

        INTERVAL, TIMEOUT = 0.01, 0.05
        # 2. send accepted, no outcome file: stage stops at sent, exit 10.
        rc, _ = cli("--origin-json", '{"channel":"telegram","account":"default","target":"123"}')
        doc = json.load(open(latest, encoding="utf-8"))
        ok &= (rc == 10 and doc["ok"] is False and doc["stage_reached"] == "sent"
               and doc["ticket_id"] == "RR-000123" and os.path.exists(flag))
        ok &= set(doc) == {"ok", "ticket_id", "stage_reached", "seconds", "at"}

        # 3. outcome present, owner_notified false: stage collected, exit 10.
        with open(os.path.join(outcomes, "RR-000123.json"), "w", encoding="utf-8") as fh:
            json.dump({"ticket_id": "RR-000123", "outcome": "specialist_follow_up",
                       "owner_message": CANARY_TEXT, "owner_notified": False}, fh)
        rc, _ = cli()
        doc = json.load(open(latest, encoding="utf-8"))
        ok &= rc == 10 and doc["stage_reached"] == "collected" and doc["ok"] is False

        # 4. owner_notified true but the wrong message: still not a pass.
        with open(os.path.join(outcomes, "RR-000123.json"), "w", encoding="utf-8") as fh:
            json.dump({"ticket_id": "RR-000123", "owner_message": "something else",
                       "owner_notified": True}, fh)
        rc, _ = cli()
        doc = json.load(open(latest, encoding="utf-8"))
        ok &= rc == 10 and doc["stage_reached"] == "collected" and doc["ok"] is False

        # 5. full pass.
        with open(os.path.join(outcomes, "RR-000123.json"), "w", encoding="utf-8") as fh:
            json.dump({"ticket_id": "RR-000123", "owner_message": "Rescue Rangers daily test message.",
                       "owner_notified": True}, fh)
        rc, _ = cli()
        doc = json.load(open(latest, encoding="utf-8"))
        ok &= rc == 0 and doc["ok"] is True and doc["stage_reached"] == "owner_notified"
        ok &= set(doc) == {"ok", "ticket_id", "stage_reached", "seconds", "at"}
        INTERVAL, TIMEOUT = 20.0, 15 * 60.0
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="daily end-to-end test of the Rescue Rangers chain")
    ap.add_argument("--root", help="openclaw root (default: OC_CONFIG_ROOT, then the box roots)")
    ap.add_argument("--origin-json", default="",
                    help="the operator test origin, passed straight to rr_escalate.py send")
    ap.add_argument("--escalate", help="default: rr_escalate.py beside this file")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()

    root = resolve_root(a.root)
    if root is None:
        sys.stderr.write("rr_e2e_canary.py: no openclaw root could be resolved\n")
        return 10
    if not operator_gate(root):
        sys.stderr.write(REFUSAL + "\n")
        return 20

    escalate = a.escalate or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "rr_escalate.py")
    verdict = run(root, a.origin_json, escalate)
    print(json.dumps(verdict, sort_keys=True))
    return 0 if verdict["ok"] else 10


if __name__ == "__main__":
    sys.exit(main())
