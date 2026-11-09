#!/usr/bin/env python3
"""S75-T37: correct-target incorporation, proven against the intended remote.

S75-T36 proved that a landing exists and that ``queue_ack`` binds a store to a
(full) target. It left one seam open, quoted by the T36 arbiter as a stated
limit: the *target itself* is a name a caller hands in. A transport can declare
``Target("openclaw-onboarding")`` while actually reading a different clone, and
a merge that exists only in local history is refused only as a generic
``merge-not-on-remote`` -- it is not named as the local-only landing it is.

This module closes that seam from the outside, without editing T36's files:

  * INTENDED TARGET. The caller states the target it means: a repository name,
    a remote, a branch, and the remote URL identities that repository is
    allowed to answer from. ``bind_target`` refuses unless the transport's own
    configured remote URL normalises to one of them -- so "the right repo" is
    proven from the URL, not asserted by a string.
  * REMOTE MAIN, NOT LOCAL MAIN. The landing is proven against the sha the
    REMOTE branch reports. A merge that is an ancestor of the local branch but
    not of the remote branch is refused as ``local-only`` -- a distinct reason
    from ``wrong-target`` and from a merge that never landed anywhere.
  * RECONCILE ONCE. An uncertain merge (landed, not yet acknowledged) is
    reconciled exactly once. A repeated reconciliation returns
    ``ALREADY_RECONCILED`` and writes nothing; a second, *different* landing for
    the same unit is refused rather than appended. One unit, one landing record.

Injected transport only -- no subprocess, no network, no credential, stdlib
only. The transport supplies four facts and nothing else::

    remote_urls(remote)         -> iterable of configured URL strings
    remote_head(remote, branch) -> 40-hex sha, or None when the branch is absent
    local_head(branch)          -> 40-hex sha, or None
    is_ancestor(a, b)           -> bool

Facts about N999 are supplied by an N999 transport; nothing here needs an ONB
fixture, which is the row's "N999 need not wait for ONB fixture facets" note.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

__all__ = [
    "TargetRefused",
    "IntendedTarget",
    "LandingProof",
    "bind_target",
    "normalise_remote_url",
    "prove_landing",
    "reconcile_once",
    "canonical_digest",
    "REASONS",
    "RECONCILED",
    "ALREADY_RECONCILED",
    "NOT_LANDED",
    "CONFLICT",
    "JOURNAL_SCHEMA",
    "PROOF_SCHEMA",
]

PROOF_SCHEMA = "s75.correct-target-proof/v1"
JOURNAL_SCHEMA = "s75.landing-journal/v1"

RECONCILED = "RECONCILED"
ALREADY_RECONCILED = "ALREADY_RECONCILED"
NOT_LANDED = "NOT_LANDED"
CONFLICT = "CONFLICT"

#: Every refusal is one of these. A caller asserts the reason; it never parses
#: prose, and ``wrong-target`` and ``local-only`` can never be confused.
REASONS = (
    "wrong-target",
    "local-only",
    "no-remote",
    "candidate-sha",
    "base-sha",
    "merge-sha",
    "remote-head-sha",
    "no-checks",
    "checks-failed",
    "proof-incomplete",
    "candidate-not-in-merge",
    "base-not-ancestor",
    "merge-not-on-remote",
    "journal-malformed",
    "landing-conflict",
)

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_SCP_LIKE = re.compile(r"^(?:[^@/]+@)?([^:/]+):(?!//)(.+)$")


class TargetRefused(Exception):
    """A landing that cannot be proven on the intended target."""

    def __init__(self, reason, detail=""):
        if reason not in REASONS:
            raise ValueError(f"unknown refusal reason: {reason!r}")
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)

    def __str__(self):
        return f"{self.reason}: {self.detail}" if self.detail else self.reason


def canonical_digest(document):
    """sha256 over canonical JSON, so the same landing digests alike everywhere."""
    body = json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def is_sha40(value):
    return isinstance(value, str) and bool(_SHA40.match(value))


def _sha40(value, reason):
    if not is_sha40(value):
        raise TargetRefused(reason, f"not a 40-hex sha: {value!r}")
    return value


def normalise_remote_url(url):
    """``host/path`` for any git remote spelling, or None when unparseable.

    Accepts ``https://host/owner/repo(.git)``, ``ssh://git@host/owner/repo``,
    ``git@host:owner/repo`` and a bare ``host/owner/repo``. Userinfo, scheme,
    a trailing ``.git`` and trailing slashes are dropped; case is folded. Two
    spellings of one repository therefore compare equal, and two repositories
    never do.
    """
    if not isinstance(url, str):
        return None
    text = url.strip()
    if not text:
        return None
    if _SCHEME.match(text):
        text = _SCHEME.sub("", text)
    else:
        scp = _SCP_LIKE.match(text)
        if scp and not text.startswith("/"):
            text = f"{scp.group(1)}/{scp.group(2)}"
    text = text.split("@", 1)[-1] if text.count("@") == 1 else text
    text = text.strip("/")
    if text.endswith(".git"):
        text = text[:-4]
    text = re.sub(r"/{2,}", "/", text)
    if "/" not in text:
        return None
    return text.lower()


class IntendedTarget:
    """The target the caller MEANS, including the URL identities it may answer from."""

    __slots__ = ("repository", "remote", "branch", "accepted_remotes")

    def __init__(self, repository, remote="origin", branch="main",
                 accepted_remotes=()):
        if not isinstance(repository, str) or not repository.strip():
            raise ValueError("repository is required")
        normalised = tuple(
            slug for slug in (normalise_remote_url(u) for u in accepted_remotes)
            if slug)
        if not normalised:
            raise ValueError(
                "at least one accepted remote URL is required: a repository "
                "name alone cannot prove which clone was read")
        self.repository = repository.strip()
        self.remote = remote or "origin"
        self.branch = branch or "main"
        self.accepted_remotes = normalised

    def as_dict(self):
        return {"repository": self.repository,
                "remote": self.remote,
                "branch": self.branch,
                "accepted_remotes": list(self.accepted_remotes)}

    def __eq__(self, other):
        return isinstance(other, IntendedTarget) and self.as_dict() == other.as_dict()

    def __hash__(self):
        return hash((self.repository, self.remote, self.branch,
                     self.accepted_remotes))

    def __repr__(self):
        return (f"IntendedTarget({self.repository!r}, {self.remote!r}, "
                f"{self.branch!r}, {list(self.accepted_remotes)!r})")


def bind_target(git, intended):
    """Refuse unless the transport's own remote URL IS the intended repository.

    Returns the observed ``host/path`` identity for the record. This is the
    step that makes "correct target" a fact instead of a claimed string.
    """
    if not isinstance(intended, IntendedTarget):
        raise TypeError("intended must be an IntendedTarget")
    try:
        urls = list(git.remote_urls(intended.remote))
    except Exception as exc:  # a transport that cannot say is not a witness
        raise TargetRefused("no-remote",
                            f"{intended.remote}: {type(exc).__name__}") from exc
    observed = tuple(slug for slug in (normalise_remote_url(u) for u in urls) if slug)
    if not observed:
        raise TargetRefused(
            "no-remote",
            f"remote {intended.remote!r} has no parseable URL (saw {urls!r})")
    for slug in observed:
        if slug in intended.accepted_remotes:
            return slug
    raise TargetRefused(
        "wrong-target",
        f"remote {intended.remote!r} points at {list(observed)!r}; the intended "
        f"repository {intended.repository!r} is {list(intended.accepted_remotes)!r}")


def _normalise_checks(checks):
    out = []
    try:
        iterator = list(checks)
    except TypeError:
        raise TargetRefused("no-checks", "checks is not a collection")
    if not iterator:
        raise TargetRefused("no-checks", "a landing needs at least one check")
    for item in iterator:
        if isinstance(item, dict):
            name, outcome = item.get("name"), item.get("outcome")
            cases = item.get("cases")
        else:
            name, outcome = getattr(item, "name", None), getattr(item, "outcome", None)
            cases = getattr(item, "cases", None)
        if not isinstance(name, str) or not name.strip():
            raise TargetRefused("proof-incomplete", f"check without a name: {item!r}")
        verdict = str(outcome).strip().upper()
        if verdict not in ("PASS", "FAIL"):
            raise TargetRefused("proof-incomplete",
                                f"check {name!r} outcome {outcome!r} is not PASS/FAIL")
        entry = {"name": name.strip(), "outcome": verdict}
        if isinstance(cases, int) and cases >= 0:
            entry["cases"] = cases
        out.append(entry)
    return out


class LandingProof:
    """One landing, proven on one intended target."""

    __slots__ = ("unit", "candidate", "base", "merge_commit", "checks",
                 "target", "remote_url", "remote_head", "local_head",
                 "observed_at", "clauses")

    def __init__(self, *, unit, candidate, base, merge_commit, checks, target,
                 remote_url, remote_head, local_head=None, observed_at=None):
        self.unit = unit
        self.candidate = candidate
        self.base = base
        self.merge_commit = merge_commit
        self.checks = checks
        self.target = target
        self.remote_url = remote_url
        self.remote_head = remote_head
        self.local_head = local_head
        self.observed_at = observed_at
        # Every clause is a fact that was tested here, not an assumption.
        self.clauses = {
            "intended_repository": True,
            "remote_main_contains_merge": True,
            "candidate_in_merge": True,
            "base_beneath_merge": True,
            "checks_present_passing": True,
            "not_local_only": True,
        }

    def as_dict(self):
        document = {
            "schema": PROOF_SCHEMA,
            "unit": self.unit,
            "candidate": self.candidate,
            "base": self.base,
            "merge_commit": self.merge_commit,
            "checks": [dict(c) for c in self.checks],
            "target": self.target.as_dict(),
            "remote_url": self.remote_url,
            "remote_head": self.remote_head,
            "clauses": dict(self.clauses),
        }
        if self.local_head is not None:
            document["local_head"] = self.local_head
        if self.observed_at is not None:
            document["observed_at"] = self.observed_at
        return document

    @property
    def digest(self):
        # observation time is deliberately excluded: identity is the landing.
        document = self.as_dict()
        document.pop("observed_at", None)
        return canonical_digest(document)

    def __repr__(self):
        return (f"LandingProof({self.unit!r}, {self.merge_commit!r}, "
                f"target={self.target.repository!r}, remote_head={self.remote_head!r})")


def prove_landing(git, intended, *, unit, candidate, base, merge_commit,
                  checks, observed_at=None):
    """Prove the merge landed on the INTENDED repository's REMOTE branch.

    Refusal order is deliberate: the target is proven first, so a wrong target
    is never reported as a landing problem. A merge present locally but absent
    from the remote branch is ``local-only`` -- the case this unit exists to
    name -- while a merge that is nowhere is ``merge-not-on-remote``.
    """
    remote_url = bind_target(git, intended)
    if not isinstance(unit, str) or not unit.strip():
        raise TargetRefused("proof-incomplete", "unit is required")
    candidate = _sha40(candidate, "candidate-sha")
    base = _sha40(base, "base-sha")
    merge_commit = _sha40(merge_commit, "merge-sha")
    normalised = _normalise_checks(checks)
    failed = [c["name"] for c in normalised if c["outcome"] != "PASS"]
    if failed:
        raise TargetRefused("checks-failed", f"not PASS: {failed!r}")

    remote_head = git.remote_head(intended.remote, intended.branch)
    if remote_head is None:
        raise TargetRefused(
            "local-only",
            f"{intended.remote}/{intended.branch} does not exist on the remote: "
            f"nothing has landed there")
    remote_head = _sha40(remote_head, "remote-head-sha")

    if not git.is_ancestor(candidate, merge_commit):
        raise TargetRefused(
            "candidate-not-in-merge",
            f"{candidate} is not contained by {merge_commit}")
    if not git.is_ancestor(base, merge_commit):
        raise TargetRefused(
            "base-not-ancestor",
            f"checks ran against {base}, which is not beneath {merge_commit}")

    local_head = git.local_head(intended.branch)
    if not git.is_ancestor(merge_commit, remote_head):
        # Local history can hold a merge the remote never received. That is a
        # distinct fact from "this is not the right repository", and distinct
        # from a merge that exists only in the caller's imagination.
        if local_head is not None and git.is_ancestor(merge_commit, local_head):
            raise TargetRefused(
                "local-only",
                f"{merge_commit} is in local {intended.branch} ({local_head}) but "
                f"not in {intended.remote}/{intended.branch} ({remote_head})")
        raise TargetRefused(
            "merge-not-on-remote",
            f"{merge_commit} is not an ancestor of "
            f"{intended.remote}/{intended.branch} ({remote_head})")

    return LandingProof(
        unit=unit.strip(), candidate=candidate, base=base,
        merge_commit=merge_commit, checks=normalised, target=intended,
        remote_url=remote_url, remote_head=remote_head, local_head=local_head,
        observed_at=observed_at)


def _read_journal(path):
    if not os.path.exists(path):
        return {"schema": JOURNAL_SCHEMA, "landings": []}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError) as exc:
        raise TargetRefused("journal-malformed", f"{path}: {exc}") from exc
    if (not isinstance(document, dict)
            or not isinstance(document.get("landings"), list)):
        raise TargetRefused("journal-malformed",
                            f"{path}: expected one 'landings' list")
    document.setdefault("schema", JOURNAL_SCHEMA)
    return document


def _write_journal(path, document):
    payload = json.dumps(document, indent=2, sort_keys=True,
                         ensure_ascii=True) + "\n"
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    temp = f"{path}.tmp-{os.getpid()}"
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def reconcile_once(path, proof):
    """Reconcile ONE uncertain merge/ack landing exactly once.

    An uncertain merge is a landing observed on the remote before its
    acknowledgement was written, or a retry after an interruption. Reconciliation
    must therefore be idempotent: the first call writes the single landing
    record, every later call with the SAME landing reports
    ``ALREADY_RECONCILED`` and leaves the file byte-identical. A different
    landing for a unit that already has one is ``CONFLICT`` -- the first record
    stands and nothing is written, so no duplicate landing can exist.

    Returns ``(status, record, wrote)``.
    """
    document = proof.as_dict() if isinstance(proof, LandingProof) else None
    if document is None:
        raise TargetRefused("proof-incomplete",
                            "reconcile_once needs a LandingProof, not a claim")
    unit = document["unit"]
    document = dict(document)
    document.pop("observed_at", None)
    document["digest"] = canonical_digest(document)

    journal = _read_journal(path)
    existing = [row for row in journal["landings"]
                if isinstance(row, dict) and row.get("unit") == unit]
    if existing:
        first = existing[0]
        same = (first.get("digest") == document["digest"]
                and first.get("merge_commit") == document["merge_commit"]
                and first.get("target") == document["target"])
        if same:
            return ALREADY_RECONCILED, first, False
        raise TargetRefused(
            "landing-conflict",
            f"{unit} already has landing {first.get('merge_commit')!r} on "
            f"target {first.get('target')!r}; refusing "
            f"{document['merge_commit']!r} on {document['target']!r}")

    if document["merge_commit"] is None:
        return NOT_LANDED, None, False
    journal["landings"].append(document)
    journal["landings"].sort(key=lambda row: (row.get("unit", ""),
                                              row.get("digest", "")))
    _write_journal(path, journal)
    return RECONCILED, document, True
