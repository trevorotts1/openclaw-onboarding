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
  * ONE WRITE. The acknowledged entry and its proof are serialised into a
    single document and installed with one atomic ``os.replace``. A reader can
    never observe an acknowledgement without its proof.
  * IDEMPOTENT. Re-acknowledging the same landing with the same candidate and
    merge commit returns ``ALREADY_ACKNOWLEDGED`` and writes nothing at all.
  * CONFLICT IS REFUSED. A second, different landing for an acknowledged entry
    is refused; the first acknowledgement stands and the store is untouched.
  * CORRECT TARGET. A proof whose target is not this entry's repository is
    refused, so ONB can never be acknowledged from an N999 proof.
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
    "not-incorporated",
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


class QueueStore:
    """One repository's queue. Entries are acknowledged in place, atomically."""

    def __init__(self, path, repository):
        if not isinstance(repository, str) or not repository.strip():
            raise ValueError("repository is required")
        self.path = os.path.abspath(path)
        self.repository = repository.strip()

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
        return ack if isinstance(ack, dict) and ack.get("state") == ACKNOWLEDGED else None

    def pending(self):
        return sorted(unit for unit, entry in self.entries().items()
                      if not (isinstance(entry.get("ack"), dict)
                              and entry["ack"].get("state") == ACKNOWLEDGED))

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
        if valid.target.repository != self.repository:
            raise AckRefused("wrong-target",
                             f"proof is for {valid.target.repository!r}, queue "
                             f"is {self.repository!r}")
        if valid.candidate != head:
            raise AckRefused("candidate-mismatch",
                             f"proof candidate {valid.candidate} is not the "
                             f"reviewed head {head}")

        existing = entry.get("ack") if isinstance(entry.get("ack"), dict) else {}
        if existing.get("state") == ACKNOWLEDGED:
            current = IP.IncorporationProof.from_dict(existing.get("proof") or {})
            if current.same_landing(valid):
                return ALREADY_ACKNOWLEDGED
            raise AckRefused("ack-conflict",
                             f"{unit} is already acknowledged at "
                             f"{current.merge_commit}; refusing a second landing")

        entry["ack"] = {
            "state": ACKNOWLEDGED,
            "unit": unit,
            "repository": self.repository,
            "candidate": valid.candidate,
            "merge_commit": valid.merge_commit,
            "ancestor_of_main": f"proven {observed_at or valid.observed_at or ''}".strip(),
            "proof_digest": valid.digest,
            "proof": valid.as_dict(),
        }
        document["entries"][unit] = entry
        document["schema"] = ACK_SCHEMA
        document["repository"] = self.repository
        _write_atomic(self.path, document)
        return ACKNOWLEDGED
