#!/usr/bin/env python3
"""S75-T36: incorporation proof bound to the correct repository target.

A merge cannot be claimed from a branch that merely exists. This module
correlates the three things that make a landing a fact and then proves it on
the right remote:

  * the CANDIDATE sha -- the head that was reviewed;
  * the BASE sha -- the exact commit those checks ran against;
  * the CHECKS -- at least one, each named and each PASS.

Through an injected git transport it then proves that the MERGE COMMIT contains
the candidate, that the base the checks ran against is beneath the landing, and
that the merge commit is an ancestor of THE TARGET's own remote branch. A proof
carries the identity of the target it was produced against, so one repository's
proof can never satisfy another: :func:`verify_incorporation` refuses a
transport bound to a different target, and :mod:`control.queue_ack` refuses a
proof whose target does not match the queue entry's repository.

Moving the remote branch makes an existing proof STALE, not wrong: the landing
happened, but the proof no longer describes the branch anyone reads today.
:func:`refresh_proof` re-proves ancestry against the new head and keeps the
superseded digest in ``refreshed_from``, so nothing is silently rewritten.
:func:`proofs_affected_by` names exactly the proofs a moved branch still needs
re-checked, and nothing else.

No network, no credential, no ``git`` invocation: the transport is injected,
exactly like :mod:`character_library.sync_protocol`. Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import re

__all__ = [
    "ProofRefused",
    "Target",
    "Check",
    "IncorporationProof",
    "verify_incorporation",
    "reverify",
    "validate_proof",
    "proof_is_current",
    "refresh_proof",
    "proofs_affected_by",
    "canonical_digest",
    "is_sha40",
    "PROOF_SCHEMA",
    "CHECK_OUTCOMES",
    "REASONS",
]

PROOF_SCHEMA = "s75.incorporation-proof/v1"

#: A check is a verdict, never a mood. Anything else is not a result.
CHECK_OUTCOMES = ("PASS", "FAIL")

#: Every refusal is one of these strings, so a caller (and a test) can assert
#: the exact reason instead of parsing prose.
REASONS = (
    "candidate-sha",
    "base-sha",
    "merge-sha",
    "remote-head-sha",
    "no-checks",
    "checks-failed",
    "wrong-target",
    "candidate-not-in-merge",
    "base-not-ancestor",
    "merge-not-on-remote",
    "proof-incomplete",
    "not-incorporated",
    "stale",
    "no-transport",
)

_SHA40 = re.compile(r"^[0-9a-f]{40}$")


class ProofRefused(Exception):
    """A landing that cannot be proven, with a stable machine-readable reason."""

    def __init__(self, reason, detail=""):
        if reason not in REASONS:
            raise ValueError(f"unknown refusal reason: {reason!r}")
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)

    def __str__(self):
        return f"{self.reason}: {self.detail}" if self.detail else self.reason


def _sha40(value, reason):
    if not isinstance(value, str) or not _SHA40.match(value):
        raise ProofRefused(reason, f"not a 40-hex sha: {value!r}")
    return value


def is_sha40(value):
    """True for a lowercase 40-hex git object name."""
    return isinstance(value, str) and bool(_SHA40.match(value))


def canonical_digest(document):
    """sha256 over a canonical JSON rendering, so the same proof digests alike."""
    body = json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


class Target:
    """One repository's remote branch. The proof is bound to this, not to a path."""

    __slots__ = ("repository", "remote", "branch")

    def __init__(self, repository, remote="origin", branch="main"):
        if not isinstance(repository, str) or not repository.strip():
            raise ValueError("repository is required")
        self.repository = repository.strip()
        self.remote = remote or "origin"
        self.branch = branch or "main"

    def as_dict(self):
        return {"repository": self.repository,
                "remote": self.remote,
                "branch": self.branch}

    def __eq__(self, other):
        return isinstance(other, Target) and self.as_dict() == other.as_dict()

    def __hash__(self):
        return hash((self.repository, self.remote, self.branch))

    def __repr__(self):
        return f"Target({self.repository!r}, {self.remote!r}, {self.branch!r})"


class Check:
    """One gate that ran, against the base this proof names."""

    __slots__ = ("name", "outcome", "cases", "command")

    def __init__(self, name, outcome, cases=None, command=None):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("check name is required")
        normalised = str(outcome).strip().upper()
        if normalised not in CHECK_OUTCOMES:
            raise ValueError(f"check {name!r} outcome must be one of {CHECK_OUTCOMES}")
        if cases is not None and (not isinstance(cases, int) or cases < 0):
            raise ValueError(f"check {name!r} cases must be a non-negative int")
        self.name = name.strip()
        self.outcome = normalised
        self.cases = cases
        self.command = command

    def as_dict(self):
        out = {"name": self.name, "outcome": self.outcome}
        if self.cases is not None:
            out["cases"] = self.cases
        if self.command:
            out["command"] = self.command
        return out

    def __repr__(self):
        return f"Check({self.name!r}, {self.outcome!r})"


def _normalise_checks(checks):
    if checks is None:
        raise ProofRefused("no-checks", "a proof without checks proves nothing")
    normalised = []
    for item in checks:
        if isinstance(item, Check):
            normalised.append(item)
        elif isinstance(item, dict):
            normalised.append(Check(item.get("name"), item.get("outcome"),
                                    item.get("cases"), item.get("command")))
        else:
            raise ProofRefused("no-checks", f"unusable check: {item!r}")
    if not normalised:
        raise ProofRefused("no-checks", "a proof without checks proves nothing")
    failed = [c.name for c in normalised if c.outcome != "PASS"]
    if failed:
        raise ProofRefused("checks-failed", "failing gates: " + ", ".join(failed))
    return normalised


class IncorporationProof:
    """The receipt: candidate + base + checks + the merge commit, on one target."""

    __slots__ = ("schema", "unit", "candidate", "base", "merge_commit", "checks",
                 "target", "remote_head", "observed_at", "refreshed_from",
                 "_transport")

    def __init__(self, *, unit, candidate, base, merge_commit, checks, target,
                 remote_head, observed_at, refreshed_from=None,
                 schema=PROOF_SCHEMA, _transport=None):
        self.schema = schema
        self.unit = unit
        self.candidate = candidate
        self.base = base
        self.merge_commit = merge_commit
        self.checks = tuple(checks)
        self.target = target
        self.remote_head = remote_head
        self.observed_at = observed_at
        self.refreshed_from = refreshed_from
        #: The transport that minted this proof, held so a consumer can re-prove
        #: it instead of trusting the numbers on the receipt. Never serialised:
        #: a proof read back from disk has no transport and cannot be re-proven.
        self._transport = _transport

    @property
    def transport(self):
        """The transport this proof was minted on, or None for a disk record."""
        return self._transport

    @property
    def incorporated(self):
        return True

    def as_dict(self):
        out = {
            "schema": self.schema,
            "unit": self.unit,
            "candidate": self.candidate,
            "base": self.base,
            "merge_commit": self.merge_commit,
            "checks": [c.as_dict() for c in self.checks],
            "target": self.target.as_dict(),
            "remote_head": self.remote_head,
            "observed_at": self.observed_at,
            "incorporated": True,
            "digest": self.digest,
        }
        if self.refreshed_from:
            out["refreshed_from"] = self.refreshed_from
        return out

    @property
    def digest(self):
        """Stable identity of THIS landing on THIS target.

        ``observed_at`` and ``refreshed_from`` are excluded: re-observing the
        same landing must not mint a new identity, or acknowledgement could not
        be idempotent.
        """
        return canonical_digest({
            "schema": self.schema,
            "unit": self.unit,
            "candidate": self.candidate,
            "base": self.base,
            "merge_commit": self.merge_commit,
            "checks": [c.as_dict() for c in self.checks],
            "target": self.target.as_dict(),
            "remote_head": self.remote_head,
        })

    def same_landing(self, other):
        """Same candidate merged to the same commit on the same target."""
        return (self.candidate == other.candidate
                and self.merge_commit == other.merge_commit
                and self.target.repository == other.target.repository)

    def __repr__(self):
        return (f"IncorporationProof({self.unit!r}, {self.candidate[:7]}.."
                f"->{self.merge_commit[:7]}, {self.target.repository!r})")

    @classmethod
    def from_dict(cls, document):
        """Rebuild a proof from disk form, or refuse as incomplete."""
        if not isinstance(document, dict):
            raise ProofRefused("proof-incomplete", "not a mapping")
        if document.get("incorporated") is not True:
            raise ProofRefused("not-incorporated",
                               "the record does not claim a proven landing")
        required = ("schema", "unit", "candidate", "base", "merge_commit",
                    "checks", "target", "remote_head")
        missing = [k for k in required if document.get(k) in (None, "", [], {})]
        if missing:
            raise ProofRefused("proof-incomplete", "missing " + ", ".join(missing))
        target_doc = document.get("target")
        if not isinstance(target_doc, dict) or not target_doc.get("repository"):
            raise ProofRefused("proof-incomplete", "missing target.repository")
        return cls(
            schema=document.get("schema", PROOF_SCHEMA),
            unit=document["unit"],
            candidate=document["candidate"],
            base=document["base"],
            merge_commit=document["merge_commit"],
            checks=_normalise_checks(document["checks"]),
            target=Target(target_doc["repository"],
                          target_doc.get("remote", "origin"),
                          target_doc.get("branch", "main")),
            remote_head=document["remote_head"],
            observed_at=document.get("observed_at"),
            refreshed_from=document.get("refreshed_from"),
        )


def _target_of(git):
    target = getattr(git, "target", None)
    if not isinstance(target, Target):
        raise ProofRefused("wrong-target",
                           "the transport is not bound to a Target")
    return target


def verify_incorporation(git, *, unit, candidate, base, merge_commit,
                         checks, observed_at=None):
    """Prove one landing on the transport's own target, or refuse.

    ``git`` supplies two structured facts and nothing else:
    ``remote_head()`` -> the target branch's current sha, and
    ``is_ancestor(ancestor, descendant)`` -> bool. No parsing, no prose.
    """
    target = _target_of(git)
    if not isinstance(unit, str) or not unit.strip():
        raise ProofRefused("proof-incomplete", "unit is required")
    candidate = _sha40(candidate, "candidate-sha")
    base = _sha40(base, "base-sha")
    merge_commit = _sha40(merge_commit, "merge-sha")
    normalised = _normalise_checks(checks)

    if not git.is_ancestor(candidate, merge_commit):
        raise ProofRefused("candidate-not-in-merge",
                           f"{candidate} is not contained by {merge_commit}")
    if not git.is_ancestor(base, merge_commit):
        raise ProofRefused("base-not-ancestor",
                           f"checks ran against {base}, which is not beneath "
                           f"{merge_commit}")
    remote_head = _sha40(git.remote_head(), "remote-head-sha")
    if not git.is_ancestor(merge_commit, remote_head):
        raise ProofRefused("merge-not-on-remote",
                           f"{merge_commit} is not an ancestor of "
                           f"{target.remote}/{target.branch} ({remote_head})")

    return IncorporationProof(
        unit=unit.strip(), candidate=candidate, base=base,
        merge_commit=merge_commit, checks=normalised, target=target,
        remote_head=remote_head, observed_at=observed_at, _transport=git)


def reverify(proof, observed_at=None):
    """Re-prove an existing proof, now, on the transport that minted it.

    This is the difference between a receipt and a fact. The carried candidate,
    base and checks are fed back through :func:`verify_incorporation`, which
    re-reads the target branch and re-tests ancestry, so a hand-minted proof (no
    transport, therefore never proven) is refused, and a base that is not
    beneath the landing is refused, at the moment of consumption rather than
    only at minting time. A moved branch is fine here: the merge only has to
    still be an ancestor of the branch as it stands now.
    """
    obj = validate_proof(proof)
    transport = obj.transport
    if transport is None:
        raise ProofRefused(
            "no-transport",
            "the proof carries no transport, so its landing cannot be re-proven")
    fresh = verify_incorporation(
        transport, unit=obj.unit, candidate=obj.candidate, base=obj.base,
        merge_commit=obj.merge_commit, checks=obj.checks,
        observed_at=observed_at)
    if fresh.target != obj.target:
        raise ProofRefused(
            "wrong-target",
            f"proof names {obj.target.repository!r}, its transport is bound to "
            f"{fresh.target.repository!r}")
    return fresh


def validate_proof(proof):
    """Structural check for a proof object OR its on-disk mapping form.

    Returns the proof object. Refuses ``not-incorporated`` for a record that
    does not claim a proven landing, so a caller can never mistake an
    intention for evidence.
    """
    if isinstance(proof, IncorporationProof):
        obj = proof
    elif isinstance(proof, dict):
        obj = IncorporationProof.from_dict(proof)
    else:
        raise ProofRefused("proof-incomplete", f"unusable proof: {proof!r}")
    if obj.incorporated is not True:  # defensive: from_dict already holds the line
        raise ProofRefused("not-incorporated", "the record does not claim a landing")
    _sha40(obj.candidate, "candidate-sha")
    _sha40(obj.base, "base-sha")
    _sha40(obj.merge_commit, "merge-sha")
    _sha40(obj.remote_head, "remote-head-sha")
    _normalise_checks(obj.checks)
    if not isinstance(obj.target, Target):
        raise ProofRefused("wrong-target", "proof has no target identity")
    return obj


def proof_is_current(proof, remote_head_now):
    """False once the target branch moved; the landing is older than the branch."""
    validate_proof(proof)
    return proof.remote_head == _sha40(remote_head_now, "remote-head-sha")


def refresh_proof(git, proof, observed_at=None):
    """Re-prove an existing proof against the transport's current branch head.

    Keeps candidate/base/checks exactly as they were -- the checks did run
    against that base, and rewriting that would be inventing evidence. Only the
    branch observation is updated, and the superseded digest is retained.
    """
    obj = validate_proof(proof)
    target = _target_of(git)
    if target != obj.target:
        raise ProofRefused("wrong-target",
                           f"proof is for {obj.target.repository!r}, transport "
                           f"is bound to {target.repository!r}")
    remote_head = _sha40(git.remote_head(), "remote-head-sha")
    if not git.is_ancestor(obj.merge_commit, remote_head):
        raise ProofRefused("merge-not-on-remote",
                           f"{obj.merge_commit} is no longer an ancestor of "
                           f"{target.remote}/{target.branch} ({remote_head})")
    return IncorporationProof(
        unit=obj.unit, candidate=obj.candidate, base=obj.base,
        merge_commit=obj.merge_commit, checks=obj.checks, target=target,
        remote_head=remote_head, observed_at=observed_at,
        refreshed_from=obj.digest, _transport=git)


def proofs_affected_by(proofs, remote_heads):
    """The proofs a moved branch invalidates -- only the ones whose target moved.

    ``remote_heads`` maps repository name -> current branch sha. A proof whose
    repository is absent from that mapping is left alone: nobody observed its
    target, so there is nothing to refresh it against.
    """
    affected = []
    for proof in proofs:
        obj = validate_proof(proof)
        current = remote_heads.get(obj.target.repository)
        if current is None:
            continue
        if not proof_is_current(obj, current):
            affected.append(obj)
    return affected
