#!/usr/bin/env python3
"""S75-T39: per-repository hygiene facets.

Four things, and nothing else:

  * ONE FACET PER REPOSITORY EVENT. ``dispatch_event`` accepts a single
    ``(repo, event_id)`` pair and returns one action scoped to that repo. It
    never enumerates repositories, so an ONB event cannot start N999 or CC
    work, and no dispatch has to wait on a sibling facet;
  * NO GLOBAL SWEEP. A multi-repo event (a list, a comma join, ``*``, ``ALL``)
    is refused, and :func:`assert_single_facet` refuses an action set that
    spans repositories. A wave that touches every repository is a failure,
    not an optimisation;
  * CLASS-SPECIFIC PROOFS BEFORE REMOVAL. Each resource class names the proofs
    it needs; ``authorize_removal`` refuses an item whose class-specific
    proofs are absent, whose path escapes the owned disposable roots, or whose
    class is protected outright. There is no one blanket proof list;
  * COMPACT RECEIPTS OUTSIDE DISPOSABLE PATHS. ``record_receipt`` refuses a
    store inside (or equal to) a disposable root and refuses an oversized
    receipt, so the only durable record of a removal cannot itself be deleted
    by that removal.

Stdlib only. No network, no credentials, no filesystem mutation beyond the
receipt the caller asked for.
"""
from __future__ import annotations

import hashlib
import json
import os

__all__ = [
    "HygieneError", "GlobalSweepRefused", "EventRefused", "ProofMissing",
    "ProtectedResource", "ReceiptRefused", "DispositionRefused",
    "REPO_ALIASES", "EVENT_KINDS", "DISPOSITIONS", "REQUIRED_PROOFS",
    "PROTECTED_CLASSES", "MAX_RECEIPT_BYTES", "SCHEMA",
    "dispatch_event", "assert_single_facet", "authorize_removal",
    "record_receipt", "receipt_path",
]

SCHEMA = "s75.hygiene-facet/v1"
MAX_RECEIPT_BYTES = 4096

# The repository aliases the ledger binds this unit to. A facet is dispatched
# for one of these, never for all of them at once.
REPO_ALIASES = ("ONB", "N999", "CC", "CONTROL")

EVENT_KINDS = ("REMOTE_INCORPORATION", "CHECKED_NO_CHANGE")

DISPOSITIONS = ("REMOVED", "DEFERRED", "PROTECTED")

# Each class names the proofs its own disposition needs. The point of the
# table is that they differ: a reproducible temp directory does not owe
# incorporation proof, a delivered branch does.
REQUIRED_PROOFS = {
    "DELIVERED_BRANCH": ("ownership", "incorporation", "consumers"),
    "UNIQUE_CODE": ("ownership", "preservation", "consumers"),
    "CLIENT_PAID_MEDIA": ("ownership", "preservation", "consumers"),
    "TEMP_OUTPUT": ("ownership", "consumers", "approval"),
    "SENSITIVE_BUNDLE": ("ownership", "approval", "preservation"),
    "SERVICE_DIR": ("ownership", "consumers", "stop_authority"),
}

# Protected assets are retained under policy. They are not disposable clutter
# and no proof set makes them removable here.
PROTECTED_CLASSES = ("REQUIRED_RECEIPT", "REQUIRED_DOCUMENT")

_SWEEP_TOKENS = {"*", "ALL", "ANY", "EVERY", "GLOBAL"}


class HygieneError(Exception):
    """Base class for refusals."""


class GlobalSweepRefused(HygieneError):
    """A dispatch or action set crossed repository boundaries."""


class EventRefused(HygieneError):
    """The event itself is not a single, scoped repository event."""


class ProofMissing(HygieneError):
    """A class-specific ownership/consumer/approval proof is absent."""


class ProtectedResource(HygieneError):
    """The resource class is retained by policy, not disposed of."""


class ReceiptRefused(HygieneError):
    """The receipt would land inside a disposable path or be too large."""


class DispositionRefused(HygieneError):
    """The disposition record is not actionable."""


def _repo_of(event):
    """Return the single repository an event is about, or refuse it."""
    if not isinstance(event, dict):
        raise EventRefused("an event is a mapping, not %r" % (type(event).__name__,))
    if "repos" in event:
        raise GlobalSweepRefused(
            "event carries repos=%r: one event names one repository"
            % (event.get("repos"),)
        )
    repo = event.get("repo")
    if isinstance(repo, (list, tuple, set, frozenset)):
        raise GlobalSweepRefused(
            "event repo names %d repositories: one event, one facet"
            % (len(repo),)
        )
    if not isinstance(repo, str):
        raise EventRefused("event has no single string repo")
    candidate = repo.strip()
    if not candidate:
        raise EventRefused("event has an empty repo")
    if candidate.upper() in _SWEEP_TOKENS:
        raise GlobalSweepRefused("event repo %r is a sweep, not a facet" % (repo,))
    if "," in candidate or "|" in candidate or " " in candidate:
        raise GlobalSweepRefused(
            "event repo %r names more than one repository" % (repo,)
        )
    if candidate not in REPO_ALIASES:
        raise EventRefused("unknown repo alias %r" % (repo,))
    return candidate


def _event_id_of(event):
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id.strip():
        raise EventRefused("event has no non-empty event_id")
    return event_id.strip()


def dispatch_event(event, existing=()):
    """Start exactly one hygiene facet for exactly one repository event.

    ``existing`` is the action list already queued. A re-delivered
    ``(repo, event_id)`` returns the queued action unchanged (``duplicate``
    True) instead of starting a second one. Nothing here reads another
    repository, so sibling facets neither block nor are created by this call.
    """
    repo = _repo_of(event)
    event_id = _event_id_of(event)
    kind = event.get("kind", "REMOTE_INCORPORATION")
    if kind not in EVENT_KINDS:
        raise EventRefused("unknown event kind %r" % (kind,))

    for action in existing:
        if not isinstance(action, dict):
            raise EventRefused("existing actions are mappings")
        if action.get("repo") != repo:
            continue
        if action.get("event_id") == event_id and action.get("kind") == kind:
            duplicate = dict(action)
            duplicate["duplicate"] = True
            return duplicate

    digest = hashlib.sha256(
        ("%s|%s|%s" % (repo, kind, event_id)).encode("utf-8")
    ).hexdigest()
    return {
        "schema": SCHEMA,
        "action_id": "hyg-%s" % digest[:16],
        "repo": repo,
        "event_id": event_id,
        "kind": kind,
        "state": "QUEUED",
        "duplicate": False,
    }


def assert_single_facet(actions):
    """Refuse an action set that leaves one repository (a global wave)."""
    repos = set()
    for action in actions:
        if not isinstance(action, dict):
            raise EventRefused("actions are mappings")
        repo = action.get("repo")
        repos.add(repo)
    if any(not isinstance(r, str) or r.strip().upper() in _SWEEP_TOKENS
           or "," in str(r) or "|" in str(r) for r in repos):
        raise GlobalSweepRefused("action set contains a sweep action")
    if len(repos) > 1:
        raise GlobalSweepRefused(
            "action set spans %d repositories: %s"
            % (len(repos), ",".join(sorted(str(r) for r in repos)))
        )
    return True


def _real(path):
    return os.path.realpath(os.path.abspath(path))


def _inside(path, roots):
    """True when ``path`` is one of ``roots`` or lives under one of them."""
    target = _real(path)
    for root in roots:
        base = _real(root)
        try:
            if os.path.commonpath([target, base]) == base:
                return True
        except ValueError:  # different drives / mixed absolute-relative
            continue
    return False


def authorize_removal(item, disposable_roots):
    """Return a receipt for an authorized removal, or refuse it.

    Refusal happens before anything is touched: an escape from the owned
    disposable roots, a protected class, or any missing class-specific proof.
    """
    if not isinstance(item, dict):
        raise DispositionRefused("an item is a mapping")
    resource_id = item.get("resource_id")
    if not isinstance(resource_id, str) or not resource_id.strip():
        raise DispositionRefused("item has no stable resource_id")
    klass = item.get("class")
    if klass in PROTECTED_CLASSES:
        raise ProtectedResource("%s is retained by policy" % (klass,))
    if klass not in REQUIRED_PROOFS:
        raise DispositionRefused("unknown resource class %r" % (klass,))

    path = item.get("path")
    if not isinstance(path, str) or not path.strip():
        raise DispositionRefused("item has no exact real path")
    if not disposable_roots:
        raise DispositionRefused("no owned disposable roots were supplied")
    if not _inside(path, disposable_roots):
        raise DispositionRefused(
            "path %r escapes the owned disposable roots" % (path,)
        )

    proofs = item.get("proofs") or {}
    if not isinstance(proofs, dict):
        raise DispositionRefused("proofs must be a mapping")
    missing = [
        name for name in REQUIRED_PROOFS[klass]
        if not isinstance(proofs.get(name), str) or not proofs[name].strip()
    ]
    if missing:
        raise ProofMissing(
            "%s needs %s" % (klass, ",".join(missing))
        )

    return {
        "schema": SCHEMA,
        "resource_id": resource_id.strip(),
        "class": klass,
        "path": _real(path),
        "disposition": "REMOVED",
        "proofs": {name: proofs[name] for name in REQUIRED_PROOFS[klass]},
    }


def receipt_path(store_root, repo, event_id):
    """Deterministic compact receipt location, one file per event."""
    if not isinstance(repo, str) or not repo.strip():
        raise ReceiptRefused("receipt needs a repo")
    if not isinstance(event_id, str) or not event_id.strip():
        raise ReceiptRefused("receipt needs an event_id")
    name = hashlib.sha256(
        ("%s|%s" % (repo.strip(), event_id.strip())).encode("utf-8")
    ).hexdigest()[:16]
    return os.path.join(_real(store_root), "%s-%s.json"
                        % (repo.strip(), name))


def record_receipt(store_root, disposable_roots, receipt):
    """Write a compact receipt that cannot live inside what it describes."""
    if not isinstance(store_root, str) or not store_root.strip():
        raise ReceiptRefused("receipt store root is required")
    if not disposable_roots:
        raise ReceiptRefused("disposable roots are required")
    if _inside(store_root, disposable_roots):
        raise ReceiptRefused(
            "receipt store %r is inside a disposable path" % (store_root,)
        )
    if not isinstance(receipt, dict):
        raise ReceiptRefused("receipt is a mapping")
    try:
        body = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ReceiptRefused("receipt is not serialisable: %s" % (exc,))
    encoded = body.encode("utf-8")
    if len(encoded) > MAX_RECEIPT_BYTES:
        raise ReceiptRefused(
            "receipt is %d bytes, over the %d-byte compact cap"
            % (len(encoded), MAX_RECEIPT_BYTES)
        )

    path = receipt_path(store_root, receipt.get("repo", ""),
                        receipt.get("event_id", ""))
    if _inside(path, disposable_roots):  # store_root checked, keep it explicit
        raise ReceiptRefused("receipt path is inside a disposable path")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
    return path
