#!/usr/bin/env python3
"""eight_gates.py - N-86: the eight gates of section 10C as step gates in code.

The plan names eight gates, and only MAJOR work stops at them (section 3J).
Each gate stands in front of one class of work; the code refuses that work
until every gate it needs has a recorded pass. The refusal code is
``GATE_NOT_PASSED``. A gate whose state cannot be read fails closed (section
3J item 15), never open.

Gate state lives at ``control/gates/eight-gates.json``:
  {"schema": "blackceo.eight-gates/v1",
   "gates": {"story-gate": {"passed": true, "at_unix": <float>, "by": "<who>"}}}

The eight gates (section 10C, binding order):
  1. pre-flight-look-lock    in front of anything paid
  2. story-gate              in front of every keyframe
  3. reference-gate          in front of any keyframe that uses a character
  4. picture-gate            in front of the video burst (incl. side-by-side)
  5. run-owner-approval      in front of the video burst
  6. spend-guard             in front of every burst
  7. take-gate               in front of the timeline
  8. delivery-gate           in front of anything sent to anyone
"""
import argparse
import json
import os
import sys

SCHEMA = "blackceo.eight-gates/v1"
CODE = "GATE_NOT_PASSED"
STATE_REL = os.path.join("control", "gates", "eight-gates.json")

GATES = (
    {"id": "pre-flight-look-lock", "number": 1, "stands_in_front_of": "anything paid"},
    {"id": "story-gate", "number": 2, "stands_in_front_of": "every keyframe"},
    {"id": "reference-gate", "number": 3,
     "stands_in_front_of": "any keyframe that uses a character"},
    {"id": "picture-gate", "number": 4,
     "stands_in_front_of": "the video burst, including the side-by-side pass"},
    {"id": "run-owner-approval", "number": 5, "stands_in_front_of": "the video burst"},
    {"id": "spend-guard", "number": 6, "stands_in_front_of": "every burst"},
    {"id": "take-gate", "number": 7, "stands_in_front_of": "the timeline"},
    {"id": "delivery-gate", "number": 8, "stands_in_front_of": "anything sent"},
)

#: Which gates an action needs. An unknown action fails closed on every gate.
ACTIONS = {
    "paid": ("pre-flight-look-lock", "spend-guard"),
    "reference-picture": ("pre-flight-look-lock", "story-gate", "spend-guard"),
    "keyframe": ("pre-flight-look-lock", "story-gate", "reference-gate", "spend-guard"),
    "video-burst": ("pre-flight-look-lock", "story-gate", "reference-gate",
                    "picture-gate", "run-owner-approval", "spend-guard"),
    "timeline": ("take-gate",),
    "delivery": ("delivery-gate",),
}


class GateRefused(Exception):
    def __init__(self, code, detail):
        super().__init__("%s: %s" % (code, detail))
        self.code, self.detail = code, detail


def _state_path(run_dir):
    return os.path.join(run_dir, STATE_REL)


def load_state(run_dir):
    path = _state_path(run_dir)
    if not os.path.isfile(path):
        return {"schema": SCHEMA, "gates": {}}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return {"schema": SCHEMA, "gates": {}}     # unreadable -> fail closed
    doc.setdefault("gates", {})
    return doc


def save_state(run_dir, state):
    path = _state_path(run_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def record_gate(run_dir, gate_id, passed, by=None, now=None):
    if gate_id not in {g["id"] for g in GATES}:
        raise GateRefused("GATE_UNKNOWN", gate_id)
    state = load_state(run_dir)
    state["gates"][gate_id] = {"passed": bool(passed),
                               "by": by,
                               "at_unix": float(now if now is not None else _now())}
    save_state(run_dir, state)
    return state["gates"][gate_id]


def missing_gates(run_dir, action, statuses=None):
    """Return the gate ids an action still lacks. Unknown action -> all eight."""
    needed = ACTIONS.get(action)
    if needed is None:
        needed = tuple(g["id"] for g in GATES)
    state = load_state(run_dir)
    passed = {gid: bool((state["gates"].get(gid) or {}).get("passed"))
              for gid in needed}
    if statuses:
        for gid in needed:
            if gid in statuses:
                passed[gid] = bool(statuses[gid])
    return [gid for gid in needed if not passed[gid]]


def require(run_dir, action, statuses=None):
    """Raise GATE_NOT_PASSED unless every gate the action needs has passed."""
    absent = missing_gates(run_dir, action, statuses)
    if absent:
        raise GateRefused(CODE, "cannot do %r until these gates pass: %s"
                          % (action, ", ".join(absent)))
    return {"action": action, "gates_passed": list(ACTIONS.get(action) or ())}


def _now():
    import time
    return time.time()


def selftest():
    import tempfile
    proofs = []
    with tempfile.TemporaryDirectory() as run:
        def refused(action, statuses=None):
            try:
                require(run, action, statuses)
            except GateRefused as exc:
                return exc.code == CODE
            return False
        proofs.append(("an unknown action fails closed on every gate",
                       len(missing_gates(run, "what")) == len(GATES)))
        proofs.append(("a paid job is refused with no gates passed",
                       refused("paid")))
        record_gate(run, "pre-flight-look-lock", True, by="b")
        proofs.append(("paid still needs the spend guard",
                       refused("paid")))
        record_gate(run, "spend-guard", True, by="b")
        proofs.append(("paid is allowed once both gates passed",
                       require(run, "paid")["action"] == "paid"))
        proofs.append(("a video burst is refused until the picture gate passes",
                       "picture-gate" in missing_gates(run, "video-burst")))
        for gid in ("story-gate", "reference-gate", "picture-gate",
                    "run-owner-approval"):
            record_gate(run, gid, True, by="b")
        proofs.append(("the video burst opens when all six gates passed",
                       require(run, "video-burst")["action"] == "video-burst"))
    for name, ok in proofs:
        print(("ok   " if ok else "FAIL ") + name)
    return 0 if all(ok for _, ok in proofs) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-dir", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_rec = sub.add_parser("record")
    p_rec.add_argument("--gate", required=True)
    p_rec.add_argument("--passed", choices=("yes", "no"), required=True)
    p_rec.add_argument("--by", default=None)
    p_check = sub.add_parser("check")
    p_check.add_argument("--action", required=True)
    sub.add_parser("status")
    sub.add_parser("selftest")
    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return selftest()
    try:
        if args.cmd == "record":
            out = record_gate(args.run_dir, args.gate, args.passed == "yes", args.by)
        elif args.cmd == "check":
            out = require(args.run_dir, args.action)
        else:
            state = load_state(args.run_dir)
            out = {"schema": SCHEMA, "order": [g["id"] for g in GATES],
                   "passed": {gid: bool((state["gates"].get(gid) or {}).get("passed"))
                              for gid in (g["id"] for g in GATES)}}
    except GateRefused as exc:
        print(json.dumps({"outcome": "rejected", "reason_code": exc.code,
                          "detail": exc.detail}, indent=2))
        return 4
    print(json.dumps({"outcome": "ok", "data": out}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
