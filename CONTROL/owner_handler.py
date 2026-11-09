#!/usr/bin/env python3
"""Owner bridge handler for the Purple Billboard ENG-LOOP adapter (T-05).

Synthetic scope only: no customer, no provider, no network, no client message.
The handler is the OWNER side of the bridge:
  1. validates owner generation + run id against the action record,
  2. writes the ACK receipt (accepted/rejected precondition),
  3. performs the idempotent effect guarded by the idempotency key,
  4. writes the COMPLETION receipt (separate from ACK).

Every state transition and receipt is written through eng_loop.py's own CLI so the
handler never invents a second state store.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import uuid

CONTROL = os.path.dirname(os.path.abspath(__file__))
STATE = os.environ.get("PB_STATE_DIR") or os.path.join(CONTROL, "state")
EFFECTS = os.path.join(STATE, "effects")
TMP = os.environ.get("PB_TMP", "/Volumes/mac mini m4/Downloads/git trees and automations/tmp/purple-billboard/pb-skill38-20261024")


def call(adapter, argv):
    env = dict(os.environ)
    env.update({"TMPDIR": TMP, "TMP": TMP, "TEMP": TMP})
    p = subprocess.run([sys.executable, "-I", adapter] + argv, capture_output=True, text=True, env=env)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def effect_once(idempotency_key, action_id, run_id):
    """O_EXCL creation is the duplicate guard: same key executes exactly once."""
    os.makedirs(EFFECTS, exist_ok=True)
    path = os.path.join(EFFECTS, idempotency_key.replace(":", "_").replace("/", "_") + ".json")
    body = {"action_id": action_id, "idempotency_key": idempotency_key,
            "run_id": run_id, "execution_count": 1,
            "pid": os.getpid(), "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            with open(path) as f:
                prior = json.load(f)
        except (OSError, ValueError):
            # The first writer created the artifact and died mid-write. The effect
            # still happened exactly once, so it is never re-executed to "repair"
            # the record; the repeat reports the torn prior instead.
            prior = {"action_id": None, "idempotency_key": idempotency_key, "pid": None,
                     "execution_count": 1, "partial": True,
                     "note": "prior effect artifact unreadable; effect NOT re-executed"}
        return False, prior, path
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(body, sort_keys=True) + "\n")
    with open(os.path.join(STATE, "effects.log"), "a") as log:
        log.write(json.dumps(body, sort_keys=True) + "\n")
    return True, body, path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--action-id", required=True)
    ap.add_argument("--idempotency-key", required=True)
    ap.add_argument("--action-type", required=True)
    ap.add_argument("--owner-generation", type=int, required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--payload", default="{}")
    ap.add_argument("--adapter", required=True)
    args = ap.parse_args()

    if args.action_type == "eng_loop.shutdown":
        # Shutdown is executed only by the conductor-side owner bridge
        # (dispatch-stop), never by the in-job observer.
        print(json.dumps({"result": "rejected_in_job", "reason": "shutdown_requires_conductor_bridge"}))
        return 7

    ack_body = {
        "handler": "owner_handler.py",
        "action_id": args.action_id,
        "action_type": args.action_type,
        "owner_generation": args.owner_generation,
        "run_id": args.run_id,
        "host_pid": os.getpid(),
        "precondition": "owner generation and run id match the action record",
    }
    rc, out, err = call(args.adapter, ["record-ack", "--action-id", args.action_id,
                                       "--owner-generation", str(args.owner_generation),
                                       "--body", json.dumps(ack_body, sort_keys=True)])
    if rc != 0:
        print(json.dumps({"result": "ack_failed", "rc": rc, "out": out, "err": err}))
        return 5
    ack = json.loads(out)
    if not ack.get("accepted"):
        print(json.dumps({"result": "ack_rejected", "ack": ack}))
        return 5

    first, effect, path = effect_once(args.idempotency_key, args.action_id, args.run_id)
    completion_body = {
        "handler": "owner_handler.py",
        "action_id": args.action_id,
        "idempotency_key": args.idempotency_key,
        "executed": first,
        "execution_count": effect["execution_count"],
        "effect_path": path,
        "effect_pid": effect["pid"],
        "ack_receipt_id": ack["receipt_id"],
        "note": "no customer, no provider, no network; local synthetic effect only",
    }
    rc, out2, err2 = call(args.adapter, ["record-complete", "--action-id", args.action_id,
                                        "--body", json.dumps(completion_body, sort_keys=True)])
    if rc != 0:
        print(json.dumps({"result": "completion_failed", "rc": rc, "out": out2, "err": err2}))
        return 5
    print(json.dumps({"result": "handled", "ack_receipt_id": ack["receipt_id"],
                      "completion": json.loads(out2), "effect_executed": first,
                      "effect_path": path}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
