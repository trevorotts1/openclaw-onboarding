#!/usr/bin/env python3
"""S75-T36 r3: what a queue acknowledges when the landing was proven on a SIDE branch.

Round 2 stamped ``ancestor_of_main`` unconditionally and bound a queue to a
repository string only, so a genuine proof minted on
``Target('openclaw-onboarding', branch='side')`` was acknowledged by a main queue
and the block asserted an ancestry claim about main that nothing tested. Run this
against any CONTROL directory:

  --expect old   r2 base: the side-branch landing is ACKNOWLEDGED and stamped
                 ancestor_of_main, with no branch recorded
  --expect new   r3: the main-bound queue refuses it, a side-bound queue records
                 the branch really proven and makes no claim about main

Fixture only -- no git process, no network, no credential, no client data. Run:

  python3 -I s75_t36_r3_side_branch_demo.py                    # own tree, expects new
  python3 -I s75_t36_r3_side_branch_demo.py --control <dir> --expect old
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

S = lambda n: "%040x" % n  # noqa: E731
ROOT, L, R, MRGE, MHEAD = S(0xA1), S(0xB2), S(0xC3), S(0xD4), S(0xE5)
GRAPH = {L: [ROOT], R: [ROOT], MRGE: [L, R], MHEAD: [MRGE]}
ONB = "openclaw-onboarding"


def run(control, expect):
    sys.path.insert(0, control)
    import incorporation_proof as IP
    import queue_ack as QA

    class Git:
        """A transport bound to one target, answering the two facts a proof needs."""

        def __init__(self, branch="main", remote="origin"):
            self.target = IP.Target(ONB, remote, branch)

        def remote_head(self):
            return MHEAD

        def is_ancestor(self, ancestor, descendant):
            if ancestor == descendant:
                return True
            seen, stack = set(), [descendant]
            while stack:
                node = stack.pop()
                if node in seen:
                    continue
                seen.add(node)
                for parent in GRAPH.get(node, ()):
                    if parent == ancestor:
                        return True
                    stack.append(parent)
            return False

    def mint(branch="main", remote="origin"):
        # A GENUINE proof: nothing is forged, the landing really is on that branch.
        return IP.verify_incorporation(
            Git(branch, remote), unit="S75-T36", candidate=R, base=L,
            merge_commit=MRGE,
            checks=[IP.Check("unit-suite", "PASS", cases=53)],
            observed_at="2026-10-25T23:00:00Z")

    def digest(path):
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()

    def ack_of(store):
        with open(store.path, "r", encoding="utf-8") as handle:
            return json.load(handle)["entries"]["S75-T36"]["ack"]

    checks = []
    temp = tempfile.mkdtemp(prefix="s75t36r3-demo-")
    try:
        side = mint("side")
        print("side proof minted on target:", side.target.as_dict())

        main_path = os.path.join(temp, "main.json")
        main_queue = QA.QueueStore(main_path, ONB)
        main_queue.seed({"S75-T36": {"verdict": "PASS", "head_commit": R}})

        if expect == "old":
            before = digest(main_path)
            outcome = main_queue.ack("S75-T36", side)
            ack = ack_of(main_queue)
            print("main queue ack      :", outcome)
            print("ack.ancestor_of_main:", ack.get("ancestor_of_main"))
            print("ack.proven_target   :", ack.get("proven_target"))
            print("store bytes changed :", digest(main_path) != before)
            checks = [
                ("side-branch landing acknowledged", outcome == QA.ACKNOWLEDGED),
                ("block asserts ancestor_of_main for a side branch",
                 ack.get("ancestor_of_main") is not None),
                ("no branch is recorded", ack.get("proven_target") is None),
            ]
        else:
            before = digest(main_path)
            try:
                outcome = main_queue.ack("S75-T36", side)
                reason, detail = repr(outcome), ""
            except QA.AckRefused as exc:
                outcome, reason, detail = None, exc.reason, exc.detail
            after_refusal = digest(main_path)
            print("main-bound queue    : outcome=%r reason=%r" % (outcome, reason))
            print("                      detail=%s" % detail)
            print("store bytes unchanged: %s" % (after_refusal == before))

            side_path = os.path.join(temp, "side.json")
            side_queue = QA.QueueStore(side_path, ONB, branch="side")
            side_queue.seed({"S75-T36": {"verdict": "PASS", "head_commit": R}})
            side_outcome = side_queue.ack("S75-T36", side,
                                          observed_at="2026-10-25T23:00:00Z")
            side_ack = ack_of(side_queue)
            print("side-bound queue    : outcome=%r" % (side_outcome,))
            print("                      ancestor_of_main=%r proven_target=%r"
                  % (side_ack.get("ancestor_of_main"),
                     side_ack.get("proven_target")))

            main_queue.ack("S75-T36", mint("main"),
                           observed_at="2026-10-25T23:00:00Z")
            main_ack = ack_of(main_queue)
            print("main landing        : ancestor_of_main=%r proven_target=%r"
                  % (main_ack.get("ancestor_of_main"),
                     main_ack.get("proven_target")))

            checks = [
                ("side-branch landing refused by a main queue",
                 reason == "wrong-target"),
                ("refusal wrote nothing", after_refusal == before),
                ("a side-bound queue records the branch really proven",
                 side_outcome == QA.ACKNOWLEDGED
                 and side_ack.get("proven_target") == {
                     "repository": ONB, "remote": "origin", "branch": "side"}),
                ("a side-bound queue makes no claim about main",
                 side_ack.get("ancestor_of_main") is None),
                ("a main landing still carries a true main ancestry claim",
                 main_ack.get("ancestor_of_main") == "proven 2026-10-25T23:00:00Z"
                 and main_ack.get("proven_target", {}).get("branch") == "main"),
            ]
    finally:
        shutil.rmtree(temp, ignore_errors=True)

    print()
    for name, ok in checks:
        print(("PASS " if ok else "FAIL ") + name)
    failures = [name for name, ok in checks if not ok]
    print("\nmode=%s checks=%d pass=%d fail=%d"
          % (expect, len(checks), len(checks) - len(failures), len(failures)))
    return 0 if not failures else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", default=os.path.dirname(HERE),
                        help="CONTROL directory to exercise")
    parser.add_argument("--expect", choices=("old", "new"), default="new")
    args = parser.parse_args()
    print("CONTROL:", os.path.abspath(args.control))
    return run(os.path.abspath(args.control), args.expect)


if __name__ == "__main__":
    sys.exit(main())
