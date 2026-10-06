#!/usr/bin/env python3
"""social_cycle_cli.py — ONE-step CLI runner for the durable weekly cycle
service (F21 / WF13 portable deployment contract).

WHY: register-weekly-cron.sh's forwarding-adapter message and the service
managers (launchd / systemd, installed by social-service.sh) both need to run
"one bounded advance step" from a NON-INTERACTIVE context. The service module
(social_cycle_service.py) is a library with no entrypoint — this CLI is the
thin, stateless runner so a service manager, a cron trigger or an operator
can all execute the SAME bounded step.

SHORT JOB LAW (unchanged): every invocation performs ONE operation per company
(advance = ensure/invite/cutoff/roll, exactly one transition) and exits. No
sleeps, no waits, no multi-hour prompt. A timer/service re-invokes it.

SUBCOMMANDS:
  advance   [--company ID] [--timezone IANA]   one advance step; --company
            omitted = every company with a state dir (row-at-a-time, still
            one transition per company per invocation)
  status    [--company ID]                     print durable cycle state JSON
  verify-ownership                             print engine-ownership verdict
            JSON (exactly one active owner per company)

Delivery: the invitation/reminder send callable writes one JSON line per
message to <state_dir>/outbox.jsonl (the durable outbox — an agent/consumer
delivers it; nothing here opens a network socket). Set SOCIAL_CYCLE_SEND=none
to run with delivery disabled (state machine only).

Environment (all overridable, all safe defaults):
  SOCIAL_CYCLE_STATE_DIR   durable state root (default ~/.openclaw/data/social-cycle,
                           /data/.openclaw/... when HOME points into the
                           container profile — the module resolves this)

EXIT: 0 ok / 1 degraded (a company step could not complete; state untouched)
      / 2 unhealthy (ownership invariant violated on verify) / 3 usage.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

EXIT_OK = 0
EXIT_DEGRADED = 1
EXIT_UNHEALTHY = 2
EXIT_USAGE = 3


def _load_service():
    """Load social_cycle_service.py from alongside this file (or the fleet
    shared-utils locations). Returns the module or None."""
    here = Path(__file__).resolve().parent
    candidates = [
        here,
        here.parent / "shared-utils",
        Path.home() / ".openclaw" / "skills" / "shared-utils",
        Path("/data/.openclaw/skills/shared-utils"),
        Path("/data/.openclaw/skills/_shared/shared-utils"),
    ]
    for cand in candidates:
        target = cand / "social_cycle_service.py"
        if target.is_file():
            spec = importlib.util.spec_from_file_location("social_cycle_service_cli", target)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["social_cycle_service_cli"] = mod
            spec.loader.exec_module(mod)
            return mod
    return None


def _outbox_sender(state_dir: str):
    """Durable outbox sender: one JSON line per message. Never raises; a
    write failure reports delivered=False so cycle state stays retryable."""

    def send(payload: Dict[str, Any]) -> bool:
        try:
            os.makedirs(state_dir, exist_ok=True)
            with open(os.path.join(state_dir, "outbox.jsonl"), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, sort_keys=True) + "\n")
            return True
        except OSError:
            return False

    return send


def _companies(scs, state_dir: str, only: Optional[str]) -> List[str]:
    if only:
        return [only]
    root = Path(state_dir)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "cycles.json").is_file())


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="social_cycle_cli", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd")

    adv = sub.add_parser("advance", help="one SHORT advance step per company")
    adv.add_argument("--company", default=None, help="company_id (default: all)")
    adv.add_argument("--timezone", default="America/New_York", help="IANA zone for week math")
    adv.add_argument("--now-ms", type=int, default=None, help="fake clock (tests only)")

    stat = sub.add_parser("status", help="print durable cycle state as JSON")
    stat.add_argument("--company", default=None)

    sub.add_parser("verify-ownership", help="engine-ownership invariant JSON")

    args = parser.parse_args(argv)
    scs = _load_service()
    if scs is None:
        print("ERROR: social_cycle_service.py not found — install shared-utils first.", file=sys.stderr)
        return EXIT_USAGE

    state_dir = scs.state_dir()
    sender_enabled = (os.environ.get("SOCIAL_CYCLE_SEND") or "").strip().lower() != "none"
    send = _outbox_sender(state_dir) if sender_enabled else None

    if args.cmd == "advance":
        now_ms = args.now_ms if args.now_ms is not None else int(
            __import__("time").time() * 1000)
        results = []
        unhealthy = False
        for company in _companies(scs, state_dir, args.company):
            try:
                r = scs.advance_cycle(company, now_ms, send=send,
                                      timezone_name=args.timezone)
            except Exception as exc:  # noqa: BLE001 — one bad company never stops the row-at-a-time sweep
                results.append({"company_id": company, "action": "error", "detail": str(exc)})
                unhealthy = True
                continue
            results.append({"company_id": company, **r})
        print(json.dumps({"cmd": "advance", "companies": len(results), "results": results},
                         sort_keys=True))
        return EXIT_UNHEALTHY if unhealthy else EXIT_OK

    if args.cmd == "status":
        rows: Dict[str, Any] = {}
        for company in _companies(scs, state_dir, args.company):
            rows[company] = scs._load_cycles(company)  # noqa: SLF001 — read-only twin access
        print(json.dumps({"cmd": "status", "state_dir": state_dir, "cycles": rows},
                         sort_keys=True))
        return EXIT_OK

    if args.cmd == "verify-ownership":
        verdict = scs.verify_engine_ownership()
        print(json.dumps({"cmd": "verify-ownership", **verdict}, sort_keys=True))
        return EXIT_OK if verdict.get("ok") else EXIT_UNHEALTHY

    parser.print_usage(sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
