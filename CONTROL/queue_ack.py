#!/usr/bin/env python3
"""S75-T36: atomic queue acknowledgement.

The merge-writer's queue is ``QUALITY-CONTROL/tickets/`` and an entry is
acknowledged by gaining its merge block. The failure this module exists to
prevent is a HALF acknowledgement -- a merge commit written while ancestry is
still ``pending push``, or a merge commit written against a proof that belongs
to a different repository. So an entry is either acknowledged together with a
valid incorporation proof, in one write, or it is not acknowledged at all.

Guarantees, each one testable:

  * VALIDATE THEN WRITE. Every precondition -- the entry exists, it belongs to
    this store's repository, it carries a PASS verdict, its reviewed head is
    the proof's candidate, and the proof validates -- is checked before a byte
    of the store is touched.
  * RE-PROVE, NEVER TRUST. The proof is re-run through
    :func:`incorporation_proof.reverify` on the transport that minted it, so its
    candidate, base and checks are correlated against the landing again at the
    moment of acknowledgement. A hand-minted proof carries no transport and is
    refused; a base that is not beneath the merge is refused. A proof read back
    from disk cannot be re-proven and is refused for the same reason.
  * ONE WRITE. The acknowledged entry and its proof are serialised into a
    single document and installed with one atomic ``os.replace``. A reader can
    never observe an acknowledgement without its proof.
  * IDEMPOTENT. Re-acknowledging the same landing with the same candidate,
    base, checks and merge commit returns ``ALREADY_ACKNOWLEDGED`` and writes
    nothing at all.
  * CONFLICT IS REFUSED. A second, different landing -- or a different base or
    check set for the same merge -- is refused; the first acknowledgement
    stands and the store is untouched.
  * CORRECT TARGET. The store is bound to one full target -- repository,
    remote and branch. A proof whose target is not that exact target is
    refused, so ONB can never be acknowledged from an N999 proof, and a
    main-bound queue cannot acknowledge a landing proven on a side branch.
  * TRUE STAMP. A proof proves ancestry of ONE branch. The acknowledgement
    always records which target was actually proven (``proven_target``), and
    asserts ``ancestor_of_main`` only when the proven branch WAS
    ``origin/main``. A queue bound to a side branch records that branch and
    makes no ancestry claim about main.
  * NO CROSS-FLAVOR GATE. Acknowledging an ONB entry requires nothing from
    N999. The store holds one repository's entries; another flavor's absence is
    not this entry's business.

No network, no credential, no client data. Stdlib only.
"""
from __future__ import annotations

import json
import os

try:  # imported as part of the ``control`` package
    from . import incorporation_proof as IP
except ImportError:  # imported as a flat module with control/ on sys.path
    import incorporation_proof as IP

__all__ = [
    "AckRefused",
    "QueueStore",
    "ACKNOWLEDGED",
    "ALREADY_ACKNOWLEDGED",
    "ACK_PENDING",
    "ACK_SCHEMA",
    "ACK_REASONS",
]

ACK_SCHEMA = "s75.queue-ack/v1"

#: The two states a queue entry can be in. There is no third, partial state.
ACK_PENDING = "PENDING"
ACKNOWLEDGED = "ACKNOWLEDGED"
ALREADY_ACKNOWLEDGED = "ALREADY_ACKNOWLEDGED"

ACK_REASONS = (
    "unknown-unit",
    "foreign-entry",
    "not-pass",
    "head-missing",
    "no-proof",
    "wrong-target",
    "candidate-mismatch",
    "base-mismatch",
    "checks-mismatch",
    "not-incorporated",
    "no-transport",
    "candidate-not-in-merge",
    "base-not-ancestor",
    "merge-not-on-remote",
    "checks-failed",
    "no-checks",
    "ack-conflict",
    "store-malformed",
)


class AckRefused(Exception):
    """An acknowledgement that did not happen, with a stable reason."""

    def __init__(self, reason, detail=""):
        if reason not in ACK_REASONS:
            raise ValueError(f"unknown refusal reason: {reason!r}")
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)

    def __str__(self):
        return f"{self.reason}: {self.detail}" if self.detail else self.reason


def _write_atomic(path, document):
    """Serialise in full, then install in one rename. Never a partial file."""
    payload = json.dumps(document, indent=2, sort_keys=True,
                         ensure_ascii=True) + "\n"
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    temp = f"{path}.tmp-{os.getpid()}"
    try:
        with open(temp, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    try:
        dirlock = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dirlock)
    except OSError:
        pass
    finally:
        os.close(dirlock)


def _complete_ack(ack):
    """The proof carried by an ack block, or None when the ack is not complete.

    A block that says ACKNOWLEDGED without a valid, self-describing proof is a
    half acknowledgement: it is not readable as an acknowledgement at all.
    """
    if not isinstance(ack, dict) or ack.get("state") != ACKNOWLEDGED:
        return None
    try:
        return IP.validate_proof(ack.get("proof"))
    except IP.ProofRefused:
        return None


def _same_proof(current, fresh):
    """One landing means the same candidate, base, checks, merge and target.

    ``remote_head`` is deliberately excluded: a refreshed proof of the same
    landing must still be idempotent.
    """
    return (current.candidate == fresh.candidate
            and current.base == fresh.base
            and current.merge_commit == fresh.merge_commit
            and current.target == fresh.target
            and [c.as_dict() for c in current.checks]
            == [c.as_dict() for c in fresh.checks])


class QueueStore:
    """One repository's queue, on one branch. Entries are acknowledged atomically."""

    def __init__(self, path, repository, branch="main", remote="origin"):
        #: The one target this queue receives landings for. A proof is only
        #: evidence about the target it was minted on, so anything else -- a
        #: different repository, remote or branch -- is refused rather than
        #: acknowledged with a claim the verification never tested.
        self.target = IP.Target(repository, remote=remote, branch=branch)
        self.path = os.path.abspath(path)
        self.repository = self.target.repository

    # -- reading ---------------------------------------------------------
    def load(self):
        if not os.path.exists(self.path):
            return {"schema": ACK_SCHEMA, "repository": self.repository,
                    "entries": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, ValueError) as exc:
            raise AckRefused("store-malformed", str(exc))
        if not isinstance(document, dict) or not isinstance(document.get("entries"), dict):
            raise AckRefused("store-malformed", "entries must be a mapping")
        return document

    def entries(self):
        return self.load()["entries"]

    def entry(self, unit):
        return self.load()["entries"].get(unit)

    def acknowledgement(self, unit):
        """The ack record, or None. An unacked entry never returns a partial."""
        entry = self.entry(unit)
        if not entry:
            return None
        ack = entry.get("ack")
        return ack if _complete_ack(ack) is not None else None

    def pending(self):
        return sorted(unit for unit, entry in self.entries().items()
                      if _complete_ack(entry.get("ack")) is None)

    def status(self, unit):
        ack = self.acknowledgement(unit)
        return ack["state"] if ack else ACK_PENDING

    # -- writing ---------------------------------------------------------
    def seed(self, entries, *, replace=False):
        """Load the queue this store will acknowledge. Test/driver entry point."""
        document = self.load() if not replace else {
            "schema": ACK_SCHEMA, "repository": self.repository, "entries": {}}
        for unit, entry in entries.items():
            record = dict(entry)
            record.setdefault("unit", unit)
            record.setdefault("repository", self.repository)
            record.setdefault("ack", {"state": ACK_PENDING})
            document["entries"][unit] = record
        document["schema"] = ACK_SCHEMA
        document["repository"] = self.repository
        _write_atomic(self.path, document)
        return document["entries"]

    def ack(self, unit, proof, *, observed_at=None):
        """Acknowledge one entry with one proof, or refuse and write nothing.

        Returns ``ACKNOWLEDGED`` (a write happened) or ``ALREADY_ACKNOWLEDGED``
        (the same landing was already acknowledged; nothing was written).
        """
        if proof is None:
            raise AckRefused("no-proof", "an acknowledgement requires its proof")
        try:
            valid = IP.validate_proof(proof)
        except IP.ProofRefused as exc:
            reason = "not-incorporated" if exc.reason in (
                "not-incorporated", "proof-incomplete") else str(exc.reason)
            raise AckRefused(reason, exc.detail)

        document = self.load()
        entry = document["entries"].get(unit)
        if entry is None:
            raise AckRefused("unknown-unit", f"{unit} is not in this queue")
        if entry.get("repository") != self.repository:
            raise AckRefused("foreign-entry",
                             f"{unit} belongs to {entry.get('repository')!r}")
        if str(entry.get("verdict", "")).strip().upper() != "PASS":
            raise AckRefused("not-pass",
                             f"{unit} verdict is {entry.get('verdict')!r}")
        head = entry.get("head_commit")
        if not IP.is_sha40(head):
            raise AckRefused("head-missing", f"{unit} has no reviewed head sha")
        if valid.target != self.target:
            raise AckRefused(
                "wrong-target",
                f"proof is for {valid.target.repository!r} on "
                f"{valid.target.remote}/{valid.target.branch}; this queue is "
                f"{self.target.repository!r} on {self.target.remote}/"
                f"{self.target.branch}")
        if valid.candidate != head:
            raise AckRefused("candidate-mismatch",
                             f"proof candidate {valid.candidate} is not the "
                             f"reviewed head {head}")

        # Re-prove the landing now, on the transport that minted the proof. A
        # structurally valid receipt is not evidence: without this the queue
        # would acknowledge a merge that merely exists, or a base that is not
        # beneath it, because nothing correlated those fields to the landing.
        try:
            fresh = IP.reverify(valid, observed_at=observed_at)
        except IP.ProofRefused as exc:
            reason = exc.reason if exc.reason in ACK_REASONS else "not-incorporated"
            raise AckRefused(reason, exc.detail)

        # ... and tie base and checks to the entry, not only to the landing.
        declared_base = entry.get("base_commit")
        if declared_base is not None and declared_base != fresh.base:
            raise AckRefused("base-mismatch",
                             f"{unit} was reviewed against base {declared_base}, "
                             f"the proof names {fresh.base}")
        required = entry.get("required_checks")
        if required is not None:
            passing = {c.name for c in fresh.checks if c.outcome == "PASS"}
            missing = [name for name in required if name not in passing]
            if missing:
                raise AckRefused("checks-mismatch",
                                 f"{unit} requires {', '.join(missing)}, which "
                                 f"the proof does not carry as PASS")

        existing = entry.get("ack") if isinstance(entry.get("ack"), dict) else {}
        if existing.get("state") == ACKNOWLEDGED:
            current = _complete_ack(existing)
            if current is None:
                raise AckRefused(
                    "store-malformed",
                    f"{unit} claims an acknowledgement without its proof")
            if _same_proof(current, fresh):
                return ALREADY_ACKNOWLEDGED
            raise AckRefused("ack-conflict",
                             f"{unit} is already acknowledged for base "
                             f"{current.base} and checks "
                             f"{[c.name for c in current.checks]}; refusing a "
                             f"different proof of {current.merge_commit}")

        entry["ack"] = {
            "state": ACKNOWLEDGED,
            "unit": unit,
            "repository": self.repository,
            "candidate": fresh.candidate,
            "base": fresh.base,
            "merge_commit": fresh.merge_commit,
            "checks": [c.as_dict() for c in fresh.checks],
            "proven_target": fresh.target.as_dict(),
            "proof_digest": fresh.digest,
            "proof": fresh.as_dict(),
        }
        # reverify() tested the merge against ONE branch. Write the ancestry
        # claim about main only when that branch was the one proven; otherwise
        # ``proven_target`` is the whole truth and no main claim is asserted.
        if (fresh.target.remote, fresh.target.branch) == ("origin", "main"):
            entry["ack"]["ancestor_of_main"] = (
                f"proven {observed_at or fresh.observed_at or ''}".strip())
        document["entries"][unit] = entry
        document["schema"] = ACK_SCHEMA
        document["repository"] = self.repository
        _write_atomic(self.path, document)
        return ACKNOWLEDGED
