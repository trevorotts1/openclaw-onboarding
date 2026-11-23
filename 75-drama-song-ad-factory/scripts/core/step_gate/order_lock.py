#!/usr/bin/env python3
"""order_lock.py - N-38: reference pictures, then keyframes, then clips.

A step refuses to start until every item of the step before it has passed the
style check. Section 3B.4. The refusal code is ``ORDER_SKIPPED`` (fixed by the
plan). Stdlib only.

State lives at ``control/order-lock.json``:
  {"schema": "blackceo.order-lock/v1",
   "steps": {"reference-pictures": {"opened": bool,
                                    "items": {"<id>": {"style_passed": bool}}},
             "keyframes": {...}, "clips": {...}}}

Rules:
  * The order is fixed: reference-pictures -> keyframes -> clips.
  * ``start_step`` records the open and refuses with ORDER_SKIPPED when the
    previous step has no items or any item has not passed its style check.
  * A step may be opened again (a retake) once it was open before; it never
    skips the previous step's gate.
"""
import argparse
import json
import os
import sys

SCHEMA = "blackceo.order-lock/v1"
ORDER = ("reference-pictures", "keyframes", "clips")
CODE = "ORDER_SKIPPED"
STATE_REL = os.path.join("control", "order-lock.json")


class OrderRefused(Exception):
    def __init__(self, code, detail):
        super().__init__("%s: %s" % (code, detail))
        self.code, self.detail = code, detail


def _state_path(run_dir):
    return os.path.join(run_dir, STATE_REL)


def load_state(run_dir):
    path = _state_path(run_dir)
    if not os.path.isfile(path):
        return {"schema": SCHEMA, "steps": {s: {"opened": False, "items": {}}
                                            for s in ORDER}}
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc.setdefault("steps", {})
    for step in ORDER:
        row = doc["steps"].setdefault(step, {"opened": False, "items": {}})
        row.setdefault("opened", False)
        row.setdefault("items", {})
    return doc


def _save(run_dir, state):
    path = _state_path(run_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def previous(step):
    if step not in ORDER:
        raise OrderRefused("STEP_UNKNOWN", "%r is not one of %s" % (step, list(ORDER)))
    at = ORDER.index(step)
    return ORDER[at - 1] if at else None


def _previous_gap(state, step):
    """Return None when the previous step is complete, else the refusal detail."""
    prev = previous(step)
    if prev is None:
        return None
    row = state["steps"].get(prev) or {}
    items = row.get("items") or {}
    if not row.get("opened"):
        return "step %r was never opened" % prev
    if not items:
        return "step %r has no pictures recorded" % prev
    failed = sorted(i for i, v in items.items() if not v.get("style_passed"))
    if failed:
        return "step %r has %d picture(s) without a passed style check: %s" % (
            prev, len(failed), ", ".join(failed))
    return None


def start_step(run_dir, step):
    """Open ``step``; refuse ORDER_SKIPPED unless the previous step fully passed."""
    state = load_state(run_dir)
    gap = _previous_gap(state, step)
    if gap:
        raise OrderRefused(CODE, "cannot start %r: %s" % (step, gap))
    state["steps"][step]["opened"] = True
    _save(run_dir, state)
    return {"opened": step, "previous": previous(step)}


def record_item(run_dir, step, item_id, style_passed):
    """Record one picture/item and whether it passed the style check."""
    if step not in ORDER:
        raise OrderRefused("STEP_UNKNOWN", step)
    state = load_state(run_dir)
    state["steps"][step]["items"][str(item_id)] = {"style_passed": bool(style_passed)}
    _save(run_dir, state)
    return {"step": step, "item": str(item_id), "style_passed": bool(style_passed)}


def status(run_dir):
    state = load_state(run_dir)
    rows = {}
    for step in ORDER:
        row = state["steps"][step]
        items = row.get("items") or {}
        rows[step] = {"opened": bool(row.get("opened")),
                      "items": len(items),
                      "style_passed": sum(1 for v in items.values()
                                          if v.get("style_passed")),
                      "ready_to_start": _previous_gap(state, step) is None}
    return {"schema": SCHEMA, "order": list(ORDER), "steps": rows}


def selftest():
    import tempfile
    proofs = []
    with tempfile.TemporaryDirectory() as run:
        def refused(fn, *a):
            try:
                fn(*a)
            except OrderRefused as exc:
                return exc.code == CODE
            return False
        proofs.append(("keyframes cannot start before references are recorded",
                       refused(start_step, run, "keyframes")))
        start_step(run, "reference-pictures")
        proofs.append(("a step opened with no pictures still blocks the next step",
                       refused(start_step, run, "keyframes")))
        record_item(run, "reference-pictures", "lead", True)
        record_item(run, "reference-pictures", "extra", False)
        proofs.append(("one failed style check still blocks keyframes",
                       refused(start_step, run, "keyframes")))
        record_item(run, "reference-pictures", "extra", True)
        proofs.append(("all references passed lets keyframes start",
                       start_step(run, "keyframes")["opened"] == "keyframes"))
        proofs.append(("clips cannot start before every keyframe passed",
                       refused(start_step, run, "clips")))
        record_item(run, "keyframes", "shot-1", True)
        proofs.append(("all keyframes passed lets clips start",
                       start_step(run, "clips")["opened"] == "clips"))
    for name, ok in proofs:
        print(("ok   " if ok else "FAIL ") + name)
    return 0 if all(ok for _, ok in proofs) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-dir", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_start = sub.add_parser("start")
    p_start.add_argument("--step", required=True)
    p_rec = sub.add_parser("record")
    p_rec.add_argument("--step", required=True)
    p_rec.add_argument("--item", required=True)
    p_rec.add_argument("--style-passed", choices=("yes", "no"), required=True)
    sub.add_parser("status")
    sub.add_parser("selftest")
    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return selftest()
    try:
        if args.cmd == "start":
            out = start_step(args.run_dir, args.step)
        elif args.cmd == "record":
            out = record_item(args.run_dir, args.step, args.item,
                              args.style_passed == "yes")
        else:
            out = status(args.run_dir)
    except OrderRefused as exc:
        print(json.dumps({"outcome": "rejected", "reason_code": exc.code,
                          "detail": exc.detail}, indent=2))
        return 4
    print(json.dumps({"outcome": "ok", "data": out}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
