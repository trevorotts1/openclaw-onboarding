#!/usr/bin/env python3
"""S75-T36 round 2: the two defects, each now refused, plus the preserved cases.

This is a runnable demonstration, not a verdict and not an approval. Every
assertion below is made against the repository's own modules; no git process,
no network, no credential, no client data.

Run:
    python3 -I CONTROL/tests/s75_t36_r2_repair_demo.py

Exit status is 0 only when every demonstration passes.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROL = os.path.dirname(HERE)
if CONTROL not in sys.path:
    sys.path.insert(0, CONTROL)

import incorporation_proof as IP  # noqa: E402
import queue_ack as QA  # noqa: E402

ONB = "openclaw-onboarding"
N999 = "999-setup"

SHA = lambda n: "%040x" % n  # noqa: E731
ROOT, BASE, CANDIDATE, MERGE, HEAD, HEAD2, STRANGER = (
    SHA(1), SHA(2), SHA(3), SHA(4), SHA(5), SHA(6), SHA(9))

PARENTS = {
    BASE: [ROOT],
    CANDIDATE: [ROOT],
    MERGE: [BASE, CANDIDATE],
    HEAD: [MERGE],
    HEAD2: [MERGE],
}

RESULTS = []


class Fixture:
    def __init__(self, target=ONB, parents=None, head=HEAD):
        self.target = IP.Target(target)
        self.parents = dict(parents if parents is not None else PARENTS)
        self.head = head

    def remote_head(self):
        return self.head

    def is_ancestor(self, ancestor, descendant):
        if ancestor == descendant:
            return True
        seen, stack = set(), [descendant]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            for parent in self.parents.get(node, ()):
                if parent == ancestor:
                    return True
                stack.append(parent)
        return False


def check(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print("[%s] %s: %s" % ("PASS" if ok else "FAIL", name, detail))
    return ok


def refuse(name, fn, wanted, detail=""):
    """Run fn, require a refusal, return its reason code."""
    try:
        outcome = fn()
    except (QA.AckRefused, IP.ProofRefused) as exc:
        reason = getattr(exc, "reason", None)
        return check(name, reason == wanted,
                     "%s reason=%s (wanted %s) %s"
                     % (type(exc).__name__, reason, wanted, detail))
    except Exception as exc:  # noqa: BLE001
        return check(name, False, "wrong exception %s: %s"
                     % (type(exc).__name__, exc))
    return check(name, False, "NOT refused; returned %r" % (outcome,))


def minted(transport=None, **overrides):
    kwargs = dict(unit="S75-T36", candidate=CANDIDATE, base=BASE,
                  merge_commit=MERGE,
                  checks=[IP.Check("gate-a", "PASS", cases=3),
                          IP.Check("gate-b", "PASS", cases=7)],
                  observed_at="2026-10-25T20:00:00Z")
    kwargs.update(overrides)
    return IP.verify_incorporation(transport or Fixture(), **kwargs)


def hand_minted(**overrides):
    """A proof that never went through a transport: numbers on a receipt."""
    kwargs = dict(unit="S75-T36", candidate=CANDIDATE, base=SHA(0x77),
                  merge_commit=SHA(0x88),
                  checks=[IP.Check("self-attested", "PASS")],
                  target=IP.Target(ONB), remote_head=HEAD,
                  observed_at="2026-10-25T21:00:00Z")
    kwargs.update(overrides)
    return IP.IncorporationProof(**kwargs)


def bytes_of(path):
    with open(path, "rb") as handle:
        return handle.read()


class Store:
    def __init__(self, directory, name, entries, repository=ONB):
        self.path = os.path.join(directory, name)
        self.queue = QA.QueueStore(self.path, repository)
        self.queue.seed(entries)

    def raw(self):
        return bytes_of(self.path)

    def ack_state(self, unit):
        document = json.loads(self.raw().decode("utf-8"))
        return document["entries"][unit].get("ack", {}).get("state")


def main():
    temp = tempfile.mkdtemp(prefix="s75-t36-r2-demo-")
    try:
        entries = {"S75-T36": {"verdict": "PASS", "head_commit": CANDIDATE}}
        store = Store(temp, "queue.json", entries)

        # ---------------------------------------------------------- DEFECT 1
        print("\n=== DEFECT 1: a merge that merely exists must not be acknowledged")
        before = store.raw()
        refuse("D1/hand-minted-unproven-proof", lambda: store.queue.ack(
            "S75-T36", hand_minted()), "no-transport",
            "(merge sha88 on no remote, base sha77 not beneath it)")
        check("D1/store-not-left-acknowledged",
              store.ack_state("S75-T36") == "PENDING",
              "ack state = %r" % store.ack_state("S75-T36"))
        check("D1/bytes-byte-identical", store.raw() == before,
              "sha256=%s" % hashlib.sha256(before).hexdigest()[:16])

        print("\n=== DEFECT 1b: the landing left the remote between mint and ack")
        transport = Fixture()
        proof = minted(transport)
        transport.head = STRANGER          # the merge is no longer on the branch
        refuse("D1b/merge-not-on-remote-at-ack",
               lambda: store.queue.ack("S75-T36", proof), "merge-not-on-remote")
        check("D1b/store-not-left-acknowledged",
              store.ack_state("S75-T36") == "PENDING",
              "ack state = %r" % store.ack_state("S75-T36"))

        # ---------------------------------------------------------- DEFECT 2
        print("\n=== DEFECT 2: candidate, base and checks are correlated at the ack")
        transport = Fixture()
        proof = minted(transport)
        proof.base = SHA(0x77)             # checks claim a base beneath no merge
        refuse("D2/base-not-beneath-landing", lambda: store.queue.ack(
            "S75-T36", proof), "base-not-ancestor",
            "(hand-edited base is not an ancestor of the merge)")
        check("D2/store-not-left-acknowledged",
              store.ack_state("S75-T36") == "PENDING",
              "ack state = %r" % store.ack_state("S75-T36"))

        print("\n=== DEFECT 2b: base and checks are tied to the ENTRY, not carried")
        tied = Store(temp, "tied.json", {"S75-T36": {
            "verdict": "PASS", "head_commit": CANDIDATE, "base_commit": ROOT}})
        refuse("D2b/base-mismatch", lambda: tied.queue.ack(
            "S75-T36", minted()), "base-mismatch")
        required = Store(temp, "required.json", {"S75-T36": {
            "verdict": "PASS", "head_commit": CANDIDATE,
            "required_checks": ["gate-a", "gate-z"]}})
        refuse("D2b/checks-mismatch", lambda: required.queue.ack(
            "S75-T36", minted()), "checks-mismatch")

        print("\n=== DEFECT 2c (round-1 DEFECT-3): differing base/checks are not "
              "silently idempotent")
        dup = Store(temp, "dup.json", entries)
        first = minted(Fixture(), base=BASE,
                       checks=[IP.Check("gate-a", "PASS"),
                               IP.Check("gate-b", "PASS")])
        second = minted(Fixture(), base=ROOT,
                        checks=[IP.Check("entirely-different-gate", "PASS")])
        check("D2c/first-acknowledged",
              dup.queue.ack("S75-T36", first) == QA.ACKNOWLEDGED, "ACKNOWLEDGED")
        settled = dup.raw()
        refuse("D2c/differing-base-and-checks-refused",
               lambda: dup.queue.ack("S75-T36", second), "ack-conflict")
        stored = json.loads(dup.raw().decode("utf-8"))["entries"]["S75-T36"]["ack"]["proof"]
        check("D2c/stored-correlation-untouched",
              stored["base"] == BASE
              and [c["name"] for c in stored["checks"]] == ["gate-a", "gate-b"]
              and dup.raw() == settled,
              "stored base=%s checks=%s bytes unchanged=True"
              % (stored["base"][:7], [c["name"] for c in stored["checks"]]))

        print("\n=== DEFECT 2d (round-1 DEFECT-4): a half acknowledgement is not "
              "readable")
        half = Store(temp, "half.json", {"HALF-1": {
            "verdict": "PASS", "head_commit": CANDIDATE,
            "ack": {"state": "ACKNOWLEDGED", "merge_commit": MERGE}}})
        check("D2d/acknowledgement-is-None",
              half.queue.acknowledgement("HALF-1") is None,
              "status = %r" % half.queue.status("HALF-1"))
        check("D2d/pending-lists-it", "HALF-1" in half.queue.pending(),
              "pending = %r" % half.queue.pending())
        refuse("D2d/ack-over-half-written-entry",
               lambda: half.queue.ack("HALF-1", minted()), "store-malformed")

        # --------------------------------------------------- preserved cases
        print("\n=== PRESERVED: everything round 1 passed still passes")
        preserve = Store(temp, "preserve.json", entries)
        before = preserve.raw()
        refuse("P/no-proof", lambda: preserve.queue.ack("S75-T36", None),
               "no-proof")
        check("P/no-proof-leaves-bytes-identical", preserve.raw() == before,
              "sha256=%s" % hashlib.sha256(before).hexdigest()[:16])
        check("P/no-proof-leaves-PENDING",
              preserve.ack_state("S75-T36") == "PENDING", "PENDING")

        good = minted()
        check("P/single-os.replace-writes-state-and-proof-together",
              preserve.queue.ack("S75-T36", good,
                                 observed_at="2026-10-25T20:05:00Z")
              == QA.ACKNOWLEDGED,
              "ACKNOWLEDGED")
        ack = json.loads(preserve.raw().decode("utf-8"))["entries"]["S75-T36"]["ack"]
        check("P/one-record-carries-landing-and-proof",
              ack["state"] == QA.ACKNOWLEDGED and ack["merge_commit"] == MERGE
              and ack["proof"]["candidate"] == CANDIDATE
              and ack["proof"]["base"] == BASE
              and ack["proof_digest"] == good.digest,
              "merge=%s proof.base=%s digest=%s"
              % (ack["merge_commit"][:7], ack["proof"]["base"][:7],
                 ack["proof_digest"][:19]))
        check("P/no-temp-file-left",
              sorted(os.listdir(temp))
              == sorted([n for n in os.listdir(temp) if ".tmp-" not in n]),
              "no .tmp- leftovers")

        settled = preserve.raw()
        check("P/idempotent-reack",
              preserve.queue.ack("S75-T36", minted()) == QA.ALREADY_ACKNOWLEDGED,
              "ALREADY_ACKNOWLEDGED")
        check("P/idempotent-reack-writes-nothing", preserve.raw() == settled,
              "bytes unchanged=True")

        refresh = IP.refresh_proof(Fixture(head=HEAD2), minted(),
                                   "2026-10-26T00:00:00Z")
        check("P/refreshed-proof-still-idempotent",
              refresh.remote_head == HEAD2
              and preserve.queue.ack("S75-T36", refresh)
              == QA.ALREADY_ACKNOWLEDGED and preserve.raw() == settled,
              "HEAD moved to %s; ALREADY_ACKNOWLEDGED, bytes unchanged=True"
              % HEAD2[:7])

        wrong = Store(temp, "wrong.json", entries)
        refuse("P/wrong-target", lambda: wrong.queue.ack(
            "S75-T36", minted(Fixture(target=N999))), "wrong-target")
        mismatch = Store(temp, "mismatch.json", {"S75-T36": {
            "verdict": "PASS", "head_commit": SHA(0xD1)}})
        refuse("P/candidate-mismatch",
               lambda: mismatch.queue.ack("S75-T36", minted()),
               "candidate-mismatch")
    finally:
        shutil.rmtree(temp, ignore_errors=True)

    failed = [name for name, ok, _ in RESULTS if not ok]
    print("\n=== SUMMARY ===")
    print("checks=%d pass=%d fail=%d" % (len(RESULTS),
                                         len(RESULTS) - len(failed),
                                         len(failed)))
    for name in failed:
        print("  FAIL %s" % name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
