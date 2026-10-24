#!/usr/bin/env python3
"""_proc_worker.py - real subprocess harness for the T-12 durability proofs.

Not a test itself: the test suite spawns this file so a crash happens in a
genuinely separate process that SQLite and the OS both see die, and so two
workers race on the same database as independent processes.

Modes
  admit      deliver one provider event; on admission record exactly one
             effect line in --effect-log
  dispatch   run outbound_gate.dispatch with a chosen gate
  reconcile  run reconciliation.resolve_unknown with a chosen resolver

A send is one line appended to --send-log and fsynced BEFORE the optional
crash, so the log is the provider's own record of what it accepted.

Run pattern used by the tests:
  python3 -I _proc_worker.py dispatch --db ... --action-id ... --worker w1 ...

Prints exactly one JSON line on success. Exit codes: 0 ok, 2 bad args.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from durable_store import DurableStore                      # noqa: E402
from outbound_gate import dispatch                          # noqa: E402
from reconciliation import resolve_unknown                   # noqa: E402


def _wait_for(path: str | None, timeout: float = 30.0) -> None:
    if not path:
        return
    deadline = time.time() + timeout
    while not Path(path).exists():
        if time.time() > deadline:
            raise SystemExit("barrier timeout")
        time.sleep(0.005)


def _append(path: str, action_id: str) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{action_id}\t{os.getpid()}\n")
        fh.flush()
        os.fsync(fh.fileno())


def _emit(payload: dict) -> int:
    print(json.dumps(payload, sort_keys=True))
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("admit", "dispatch", "reconcile"))
    ap.add_argument("--db", required=True)
    ap.add_argument("--go-file")
    ap.add_argument("--worker", default="w")
    ap.add_argument("--action-id")
    ap.add_argument("--provider", default="ghl")
    ap.add_argument("--tenant", default="t1")
    ap.add_argument("--event-id")
    ap.add_argument("--effect-log")
    ap.add_argument("--send-log")
    ap.add_argument("--gate", default="allow",
                    choices=("allow", "deny", "slow_allow"))
    ap.add_argument("--gate-marker")
    ap.add_argument("--gate-delay", type=float, default=0.5)
    ap.add_argument("--crash", default="none",
                    choices=("none", "after_send", "before_send"))
    ap.add_argument("--resolver", default="unknown",
                    choices=("applied", "not_applied", "unknown"))
    ap.add_argument("--lease-seconds", type=float, default=60.0)
    args = ap.parse_args(argv)

    _wait_for(args.go_file)
    store = DurableStore(args.db)

    if args.mode == "admit":
        res = store.admit_event(provider=args.provider, tenant_id=args.tenant,
                                provider_event_id=args.event_id,
                                payload_sha256="same-body-hash")
        effects = 0
        if res["admitted"]:
            if store.claim_decision(provider=args.provider,
                                    tenant_id=args.tenant,
                                    provider_event_id=args.event_id):
                if args.effect_log:
                    _append(args.effect_log, args.event_id or "")
                    effects = 1
                store.record_decision(provider=args.provider,
                                      tenant_id=args.tenant,
                                      provider_event_id=args.event_id,
                                      decision_ref="one_effect")
        store.close()
        return _emit({"mode": "admit", "admitted": res["admitted"],
                      "reason": res["reason"], "effects": effects})

    if args.mode == "dispatch":
        def evaluator(ctx):
            if args.gate == "deny":
                return {"verdict": "SUPPRESSED",
                        "evidence": {"reason": "global_stop"}}
            if args.gate == "slow_allow":
                if args.gate_marker:
                    Path(args.gate_marker).write_text("in_gate", encoding="utf-8")
                time.sleep(args.gate_delay)
            return {"verdict": "ALLOW", "evidence": {"checked": "fresh"}}

        def sender(ctx):
            if args.crash == "before_send":
                os.kill(os.getpid(), signal.SIGKILL)
            if args.send_log:
                _append(args.send_log, ctx["action_id"])
            if args.crash == "after_send":
                os.kill(os.getpid(), signal.SIGKILL)
            return {"provider": "ghl",
                    "provider_receipt_id": f"prov-{os.getpid()}"}

        out = dispatch(store, evaluator, sender, args.action_id, args.worker,
                       lease_seconds=args.lease_seconds)
        state = store.get_action(args.action_id)["state"]
        store.close()
        return _emit({"mode": "dispatch", "status": out.status,
                      "attempt_no": out.attempt_no, "verdict": out.verdict,
                      "state": state})

    if args.mode == "reconcile":
        def resolver(ctx):
            if args.resolver == "applied":
                return {"outcome": "applied",
                        "receipt": {"provider": "ghl",
                                    "provider_receipt_id": f"recon-{os.getpid()}"},
                        "evidence": {"source": "provider_history"}}
            return args.resolver

        out = resolve_unknown(store, args.action_id, resolver)
        state = store.get_action(args.action_id)["state"]
        store.close()
        return _emit({"mode": "reconcile", "status": out.status,
                      "state_after": state})

    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
