#!/usr/bin/env python3
"""S75-T16: the sync protocol for a client's shared character library.

Five things, and nothing else:

  * an OPERATION ID on every sync operation, derived from what the operation
    is about, so re-delivering the same operation is recognised instead of
    applied twice -- including after a restart, because the record is on disk;
  * a BOUNDED retry/backoff policy. A policy cannot ask for unbounded
    attempts: the attempt count is capped in the constructor and again in the
    loop, and running out raises instead of spinning;
  * a LAST-SEEN REVISION per object, so the store can say whether its copy is
    current, behind, or ahead of the remote side;
  * EXPLICIT CONFLICT HANDLING. A divergence is never resolved by silent
    last-writer-wins: it either fast-forwards (when the remote revision
    provably descends from the one we saw), refuses with a SyncConflict that
    carries a conflict record, or is resolved by a rule the caller named up
    front -- and every outcome other than IN_SYNC leaves a conflict record
    behind;
  * APPROVED OFFLINE SNAPSHOTS carrying their revision and a sync status. An
    offline snapshot is usable only with an approval bound to this client and
    with an intact digest, and a snapshot known to be out of sync is refused
    unless the caller says so out loud.

Transport is injected, exactly like :mod:`character_library.notion_adapter`:
``call(action, payload)`` maps onto the authorized connection's own operation
names. No network code, no credential, no second Notion client. Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time

__all__ = [
    "SyncError", "OperationRefused", "RetryExhausted", "SyncConflict",
    "SnapshotRefused", "RetryPolicy", "SyncState", "SyncEngine",
    "operation_id", "payload_digest", "build_offline_snapshot",
    "use_offline_snapshot", "write_snapshot", "load_snapshot",
    "SYNC_SCHEMA", "CONFLICT_SCHEMA", "OFFLINE_SNAPSHOT_SCHEMA",
    "SYNC_STATUSES", "OBJECT_STATUSES", "CONFLICT_POLICIES",
    "HARD_MAX_ATTEMPTS",
]

SYNC_SCHEMA = "s75.character-sync/v1"
CONFLICT_SCHEMA = "s75.character-sync-conflict/v1"
OFFLINE_SNAPSHOT_SCHEMA = "s75.character-offline-snapshot/v1"

#: The only forward order of "how current is my copy".
OBJECT_STATUSES = ("UNSEEN", "IN_SYNC", "STALE", "AHEAD")
#: Snapshot sync statuses. ``UNVERIFIED_OFFLINE`` is honest: nobody compared
#: the capture to the remote side, so the snapshot does not claim to be current.
SYNC_STATUSES = ("IN_SYNC", "OUT_OF_SYNC", "UNVERIFIED_OFFLINE")
#: Divergence policies. ``refuse`` is the default; the other two are only ever
#: reached when the caller named them when constructing the engine.
CONFLICT_POLICIES = ("refuse", "remote_wins", "local_wins")

#: Ceiling on retries. A policy above this is refused, so no call site can
#: configure an effectively unbounded loop.
HARD_MAX_ATTEMPTS = 8
MAX_BACKOFF_SECONDS = 30.0


class SyncError(ValueError):
    """Plain-English reason a sync step stopped."""


class OperationRefused(SyncError):
    """The operation itself is malformed, or its id was reused."""


class RetryExhausted(SyncError):
    """The bounded attempt budget ran out. Carries what was tried."""

    def __init__(self, message, *, operation, attempts, delays, reason):
        self.operation = operation
        self.attempts = attempts
        self.delays = list(delays)
        self.reason = reason
        SyncError.__init__(self, message)


class SyncConflict(SyncError):
    """A divergence that the engine refuses to resolve by itself."""

    def __init__(self, record):
        self.record = record
        SyncError.__init__(
            self, "Refusing to overwrite either copy of %r: the local copy is "
                  "at revision %r and the remote copy is at revision %r. The "
                  "conflict is recorded as %s; choose keep_local or take_remote."
                  % (record.get("object_id"), record.get("local_revision"),
                     record.get("remote_revision"), record.get("conflict_id")))


class SnapshotRefused(SyncError):
    """The offline snapshot is not approved, is tampered with, or is unusable."""


# --- plain values ---------------------------------------------------------
#
# Anything that answers a question about itself can lie: a dict subclass in
# get(), a str subclass in __eq__. Critical fields are therefore checked with
# an exact-type test and copied into a plain builtin before they are used.

def _plain_mapping(value, what):
    if type(value) is not dict:
        raise SyncError(
            "A %s must be a plain object, not %s." % (what, type(value).__name__))
    return dict(value)


def _plain_list(value, what):
    if type(value) is not list:
        raise SyncError(
            "A %s must be a plain list, not %s." % (what, type(value).__name__))
    return list(value)


def _text(value, what):
    if type(value) is not str or not value.strip():
        raise SyncError("A %s must be a non-empty plain string." % what)
    return value.strip()


def _positive_int(value, what):
    if type(value) is not int or value < 1:
        raise SyncError("A %s must be a positive whole number." % what)
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value):
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _atomic_json(path, value):
    folder = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".sync-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return None
    return loaded if type(loaded) is dict else None


# --- operation ids --------------------------------------------------------

def payload_digest(payload):
    """Digest of an operation's payload, independent of key order."""
    return _digest(_plain_mapping(payload, "operation payload"))


def operation_id(action, object_id, base_revision, payload):
    """The id of one sync operation. Same operation, same id, every time.

    Derived from the client namespace is deliberately NOT done here: the state
    a journal is bound to already carries the namespace, and an id that is
    stable across two stores of the same client is what lets a retry be
    recognised after a restart. Two different clients never share a journal.
    """
    action = _text(action, "operation action")
    object_id = _text(object_id, "operation object id")
    base_revision = _positive_int(base_revision, "operation base revision")
    return "op-" + _digest({
        "action": action,
        "object_id": object_id,
        "base_revision": base_revision,
        "payload": _plain_mapping(payload, "operation payload"),
    })[len("sha256:"):][:32]


# --- bounded retry/backoff ------------------------------------------------

class RetryPolicy:
    """A finite attempt budget with exponential backoff. Bounded by design."""

    def __init__(self, *, max_attempts=5, base_delay=0.5, factor=2.0,
                 max_delay=8.0):
        attempts = _positive_int(max_attempts, "max_attempts")
        if attempts > HARD_MAX_ATTEMPTS:
            raise SyncError(
                "Refusing %d attempts: the ceiling is %d. Retries are bounded, "
                "so a policy cannot ask for an unbounded loop."
                % (attempts, HARD_MAX_ATTEMPTS))
        for name, value in (("base_delay", base_delay), ("factor", factor),
                            ("max_delay", max_delay)):
            if type(value) not in (int, float) or value < 0:
                raise SyncError("A %s must be a non-negative number." % name)
        if factor < 1:
            raise SyncError("A factor below 1 would shorten every retry.")
        self.max_attempts = attempts
        self.base_delay = float(base_delay)
        self.factor = float(factor)
        self.max_delay = min(float(max_delay), MAX_BACKOFF_SECONDS)

    def delay_for(self, attempt):
        """Seconds to wait after failed attempt ``attempt`` (1-based)."""
        attempt = _positive_int(attempt, "attempt number")
        return min(self.base_delay * (self.factor ** (attempt - 1)),
                   self.max_delay)

    def run(self, call, *, sleep=time.sleep):
        """Call until it returns, or raise RetryExhausted at the ceiling.

        Returns ``(value, log)`` where the log holds the attempt count and the
        delays actually slept, so a caller can show the backoff was bounded.
        """
        if not callable(call):
            raise SyncError("A retry needs something to call.")
        delays = []
        reason = ""
        for attempt in range(1, self.max_attempts + 1):
            try:
                return call(), {"attempts": attempt, "delays": delays}
            except Exception as exc:            # transport-shaped; surfaced next
                reason = "%s: %s" % (type(exc).__name__, exc)
                if attempt == self.max_attempts:
                    break
                wait = self.delay_for(attempt)
                delays.append(wait)
                if wait:
                    sleep(wait)
        raise RetryExhausted(
            "Gave up after %d bounded attempts; last failure was %s."
            % (self.max_attempts, reason),
            operation=None, attempts=self.max_attempts, delays=delays,
            reason=reason)


# --- durable sync state ---------------------------------------------------

class SyncState:
    """One client's durable sync state: operations, revisions, conflicts.

    On disk so a retry after a restart is still recognised as the same
    operation. One file per client; never shared between clients.
    """

    def __init__(self, path, client_namespace):
        self.path = os.path.abspath(str(path))
        self.client_namespace = _text(client_namespace, "client namespace")
        self._doc = self._load()

    def _blank(self):
        return {
            "schema": SYNC_SCHEMA,
            "client_namespace": self.client_namespace,
            "operations": {},
            "revisions": {},
            "conflicts": {},
            "snapshot_revision": 0,
        }

    def _load(self):
        loaded = _read_json(self.path)
        if loaded is None:
            return self._blank()
        if loaded.get("client_namespace") != self.client_namespace:
            raise SyncError(
                "This sync state belongs to a different client namespace.")
        doc = self._blank()
        doc.update({key: loaded[key] for key in doc
                    if key in loaded and type(loaded[key]) is type(doc[key])})
        return doc

    def _save(self):
        _atomic_json(self.path, self._doc)

    # operations ----------------------------------------------------------
    def operation(self, op_id):
        """The recorded delivery of one operation id, or None."""
        found = self._doc["operations"].get(str(op_id))
        return dict(found) if type(found) is dict else None

    def remember_operation(self, op_id, record):
        self._doc["operations"][str(op_id)] = _plain_mapping(
            record, "operation record")
        self._save()

    def operations(self):
        return {key: dict(value) for key, value in self._doc["operations"].items()}

    # last-seen revisions -------------------------------------------------
    def last_seen(self, object_id):
        """The revision this store last saw for one object, or None."""
        found = self._doc["revisions"].get(str(object_id))
        return None if type(found) is not dict else found.get("revision")

    def stamp(self, object_id, revision, *, catalog_revision=""):
        """Record the revision this store has now seen for one object."""
        object_id = _text(object_id, "object id")
        revision = _positive_int(revision, "revision")
        self._doc["revisions"][object_id] = {
            "revision": revision,
            "catalog_revision": str(catalog_revision),
        }
        self._save()
        return revision

    def status(self, object_id, remote_revision):
        """UNSEEN, IN_SYNC, STALE or AHEAD against the remote revision."""
        remote_revision = _positive_int(remote_revision, "remote revision")
        seen = self.last_seen(object_id)
        if seen is None:
            return "UNSEEN"
        if seen == remote_revision:
            return "IN_SYNC"
        return "STALE" if seen < remote_revision else "AHEAD"

    def revisions(self):
        return {key: dict(value) for key, value in self._doc["revisions"].items()}

    # conflicts -----------------------------------------------------------
    def record_conflict(self, record):
        record = _plain_mapping(record, "conflict record")
        conflict_id = _text(record.get("conflict_id"), "conflict id")
        self._doc["conflicts"][conflict_id] = record
        self._save()
        return record

    def conflict(self, conflict_id):
        found = self._doc["conflicts"].get(str(conflict_id))
        return dict(found) if type(found) is dict else None

    def conflicts(self):
        return [dict(value) for _key, value in sorted(self._doc["conflicts"].items())]

    def resolve_conflict(self, conflict_id, choice):
        """Close a recorded conflict with the caller's named choice."""
        found = self.conflict(conflict_id)
        if found is None:
            raise SyncError("No conflict %r is recorded." % (conflict_id,))
        if choice not in ("keep_local", "take_remote"):
            raise SyncError("Choose keep_local or take_remote.")
        found["resolution"] = ("RESOLVED_LOCAL" if choice == "keep_local"
                               else "RESOLVED_REMOTE")
        found["resolved_by"] = choice
        self._doc["conflicts"][conflict_id] = found
        self._save()
        if choice == "take_remote":
            self.stamp(found["object_id"], found["remote_revision"])
        return found

    # offline snapshots ---------------------------------------------------
    def next_snapshot_revision(self):
        self._doc["snapshot_revision"] = int(self._doc["snapshot_revision"]) + 1
        self._save()
        return self._doc["snapshot_revision"]


# --- the engine -----------------------------------------------------------

class SyncEngine:
    """Pushes operations and reconciles remote revisions against local state."""

    def __init__(self, state, call, *, policy=None, on_conflict="refuse",
                 sleep=time.sleep):
        if not isinstance(state, SyncState):
            raise SyncError("A sync engine needs a SyncState.")
        if not callable(call):
            raise SyncError(
                "A sync engine needs an injected transport: call(action, payload).")
        if on_conflict not in CONFLICT_POLICIES:
            raise SyncError("on_conflict must be one of %s." % (CONFLICT_POLICIES,))
        self.state = state
        self.call = call
        self.policy = policy or RetryPolicy()
        self.on_conflict = on_conflict
        self.sleep = sleep

    # push ----------------------------------------------------------------
    def apply(self, operation):
        """Send one operation. Repeated delivery is recognised, not re-applied."""
        plain = _plain_mapping(operation, "sync operation")
        action = _text(plain.get("action"), "operation action")
        object_id = _text(plain.get("object_id"), "operation object id")
        base_revision = _positive_int(plain.get("base_revision"),
                                      "operation base revision")
        payload = _plain_mapping(plain.get("payload"), "operation payload")
        op_id = operation_id(action, object_id, base_revision, payload)
        digest = payload_digest(payload)

        prior = self.state.operation(op_id)
        if prior is not None:
            if prior.get("payload_digest") != digest:
                raise OperationRefused(
                    "Operation id %s was already used for a different payload. "
                    "An id names one operation; refusing to reuse it."
                    % op_id)
            if prior.get("status") == "APPLIED":
                return {
                    "operation_id": op_id, "object_id": object_id,
                    "status": "DUPLICATE", "duplicate": True, "applied": False,
                    "revision": prior.get("revision"), "attempts": 0,
                }

        self.state.remember_operation(op_id, {
            "operation_id": op_id, "object_id": object_id, "action": action,
            "base_revision": base_revision, "payload_digest": digest,
            "status": "IN_FLIGHT", "revision": None,
        })

        envelope = {
            "operation_id": op_id, "object_id": object_id,
            "base_revision": base_revision, "payload": payload,
        }
        try:
            value, log = self.policy.run(
                lambda: self.call(action, envelope), sleep=self.sleep)
        except RetryExhausted as exhausted:
            self.state.remember_operation(op_id, {
                "operation_id": op_id, "object_id": object_id, "action": action,
                "base_revision": base_revision, "payload_digest": digest,
                "status": "FAILED", "revision": None,
                "reason": exhausted.reason,
            })
            exhausted.operation = op_id
            raise

        try:
            reply = _plain_mapping(value, "transport reply")
            revision = reply.get("revision")
            if type(revision) is not int or revision < 1:
                raise SyncError(
                    "The transport accepted %s but returned no revision, so the "
                    "operation cannot be recorded as applied." % op_id)
        except SyncError as bad:
            # Nothing is recorded as applied, and the id is NOT left IN_FLIGHT:
            # a retry may try again with this same id, and the remote dedupes on
            # that id if it did in fact apply the first time.
            self.state.remember_operation(op_id, {
                "operation_id": op_id, "object_id": object_id, "action": action,
                "base_revision": base_revision, "payload_digest": digest,
                "status": "FAILED", "revision": None, "reason": str(bad),
            })
            raise
        self.state.remember_operation(op_id, {
            "operation_id": op_id, "object_id": object_id, "action": action,
            "base_revision": base_revision, "payload_digest": digest,
            "status": "APPLIED", "revision": revision,
            "attempts": log["attempts"], "delays": log["delays"],
        })
        self.state.stamp(object_id, revision,
                         catalog_revision=str(reply.get("catalog_revision", "")))
        return {
            "operation_id": op_id, "object_id": object_id, "status": "APPLIED",
            "duplicate": False, "applied": True, "revision": revision,
            "attempts": log["attempts"], "delays": list(log["delays"]),
        }

    # pull ----------------------------------------------------------------
    def receive(self, object_id, *, remote_revision, remote_parent_revision=None,
                local_dirty=False, detected_at=""):
        """Reconcile one remote revision against what this store last saw.

        Outcomes, all explicit:
          UNSEEN       no local copy; adopt the remote revision (ADOPTED)
          IN_SYNC      same revision; nothing to do
          FAST_FORWARD the remote revision is newer AND declares the revision we
                       saw as its parent, and nothing local is pending
        Anything else is a divergence. A newer remote revision whose parent is
        unknown is a divergence too: descent that was not declared is not
        proved, so it is surfaced rather than assumed. Divergence is recorded as
        a conflict record and refused, unless the engine was built with a rule
        that names the winner.
        """
        object_id = _text(object_id, "object id")
        remote_revision = _positive_int(remote_revision, "remote revision")
        if remote_parent_revision is not None:
            remote_parent_revision = _positive_int(
                remote_parent_revision, "remote parent revision")
        if type(local_dirty) is not bool:
            raise SyncError("local_dirty must be a plain True or False.")
        seen = self.state.last_seen(object_id)

        if seen is None:
            self.state.stamp(object_id, remote_revision)
            return {"object_id": object_id, "status": "ADOPTED",
                    "revision": remote_revision, "conflict": None}
        if seen == remote_revision:
            return {"object_id": object_id, "status": "IN_SYNC",
                    "revision": seen, "conflict": None}
        if not local_dirty and remote_revision > seen \
                and remote_parent_revision == seen:
            self.state.stamp(object_id, remote_revision)
            return {"object_id": object_id, "status": "FAST_FORWARD",
                    "revision": remote_revision, "conflict": None}

        if not local_dirty and remote_revision > seen \
                and remote_parent_revision is None:
            reason = "REMOTE_PARENT_UNKNOWN"
        elif not local_dirty and remote_revision > seen:
            reason = "REMOTE_REWRITTEN_BASE"
        elif not local_dirty:
            reason = "REMOTE_ROLLED_BACK"
        else:
            reason = "LOCAL_EDIT_UNPUSHED"
        record = {
            "schema": CONFLICT_SCHEMA,
            "conflict_id": "cf-" + _digest({
                "client": self.state.client_namespace, "object_id": object_id,
                "local": seen, "remote": remote_revision,
                "parent": remote_parent_revision})[len("sha256:"):][:16],
            "client_namespace": self.state.client_namespace,
            "object_id": object_id,
            "local_revision": seen,
            "remote_revision": remote_revision,
            "remote_parent_revision": remote_parent_revision,
            "reason_code": reason,
            "detected_at": str(detected_at),
            "rule": ("No silent last-writer-wins. A divergence is refused "
                     "unless the caller named a winner before it happened."),
        }

        if self.on_conflict == "refuse":
            record["resolution"] = "REFUSED_PENDING_CLIENT_CHOICE"
            self.state.record_conflict(record)
            raise SyncConflict(record)
        if self.on_conflict == "remote_wins":
            record["resolution"] = "RESOLVED_REMOTE"
            record["resolved_by"] = "remote_wins"
            self.state.record_conflict(record)
            self.state.stamp(object_id, remote_revision)
            return {"object_id": object_id, "status": "CONFLICT_RESOLVED_REMOTE",
                    "revision": remote_revision, "conflict": record}
        record["resolution"] = "RESOLVED_LOCAL"
        record["resolved_by"] = "local_wins"
        self.state.record_conflict(record)
        return {"object_id": object_id, "status": "CONFLICT_KEPT_LOCAL",
                "revision": seen, "conflict": record}


# --- approved offline snapshots -------------------------------------------

def _approval(approval, client_namespace):
    """A plain approval bound to THIS client, or a refusal."""
    plain = _plain_mapping(approval, "offline approval")
    approver = _text(plain.get("approver"), "approver")
    approval_id = _text(plain.get("approval_id"), "approval id")
    scope = _text(plain.get("scope"), "approval scope")
    if scope != client_namespace:
        raise SnapshotRefused(
            "This offline approval is bound to %r, not to %r."
            % (scope, client_namespace))
    return {"approver": approver, "approval_id": approval_id, "scope": scope}


def build_offline_snapshot(state, *, objects, approval, remote_revisions=None,
                           captured_at=""):
    """Build an APPROVED offline snapshot carrying revision and sync status.

    ``objects`` maps object id to the revision the local copy holds.
    ``remote_revisions`` is optional: when it is given the snapshot states
    whether it is in sync; when it is not, the snapshot says so instead of
    claiming freshness.
    """
    if not isinstance(state, SyncState):
        raise SyncError("An offline snapshot needs a SyncState.")
    given = _plain_mapping(objects, "offline object map")
    if not given:
        raise SnapshotRefused(
            "An offline snapshot with no objects is not usable.")
    captured = {}
    for object_id, revision in given.items():
        captured[_text(object_id, "object id")] = _positive_int(
            revision, "object revision")
    bound = _approval(approval, state.client_namespace)

    if remote_revisions is None:
        sync_status = "UNVERIFIED_OFFLINE"
        compared = []
    else:
        remote = _plain_mapping(remote_revisions, "remote revision map")
        compared = []
        in_sync = True
        for object_id in sorted(captured):
            if object_id not in remote:
                in_sync = False
                continue
            if _positive_int(remote[object_id], "remote revision") != captured[object_id]:
                in_sync = False
            compared.append(object_id)
        sync_status = "IN_SYNC" if in_sync else "OUT_OF_SYNC"

    body = {
        "schema": OFFLINE_SNAPSHOT_SCHEMA,
        "client_namespace": state.client_namespace,
        "revision": state.next_snapshot_revision(),
        "catalog_revision": _digest(captured),
        "objects": [{"object_id": key, "revision": captured[key]}
                    for key in sorted(captured)],
        "sync_status": sync_status,
        "offline": True,
        "approval": bound,
        "captured_at": str(captured_at),
        "compared_objects": compared,
    }
    body["digest"] = _digest(body)
    return body


def use_offline_snapshot(snapshot, *, allow_out_of_sync=False):
    """Return what an approved offline snapshot holds, or refuse it.

    The digest is recomputed, the approval must be intact and bound to this
    snapshot's client, and a snapshot that is known to be out of sync is
    refused unless the caller asked for it explicitly.
    """
    plain = _plain_mapping(snapshot, "offline snapshot")
    if plain.get("schema") != OFFLINE_SNAPSHOT_SCHEMA:
        raise SnapshotRefused(
            "This is not an offline character snapshot (%r)."
            % (plain.get("schema"),))
    if plain.get("offline") is not True:
        raise SnapshotRefused("This snapshot does not declare itself offline.")
    body = {key: value for key, value in plain.items() if key != "digest"}
    if plain.get("digest") != _digest(body):
        raise SnapshotRefused(
            "The snapshot digest does not match its contents, so it was "
            "edited or truncated after it was approved.")
    client = _text(plain.get("client_namespace"), "snapshot client namespace")
    _approval(plain.get("approval"), client)
    _positive_int(plain.get("revision"), "snapshot revision")
    status = plain.get("sync_status")
    if status not in SYNC_STATUSES:
        raise SnapshotRefused("Unknown snapshot sync status %r." % (status,))
    if type(allow_out_of_sync) is not bool:
        raise SnapshotRefused("allow_out_of_sync must be a plain True or False.")
    if status == "OUT_OF_SYNC" and not allow_out_of_sync:
        raise SnapshotRefused(
            "This snapshot is out of sync with the shared library. Use it only "
            "by asking for it explicitly (allow_out_of_sync=True).")
    objects = _plain_list(plain.get("objects"), "snapshot object list")
    return {
        "usable": True,
        "client_namespace": client,
        "revision": plain["revision"],
        "catalog_revision": plain.get("catalog_revision"),
        "sync_status": status,
        "objects": [dict(item) for item in objects if type(item) is dict],
        "approved_by": plain["approval"].get("approver"),
        "approval_id": plain["approval"].get("approval_id"),
    }


def write_snapshot(path, snapshot):
    """Persist one snapshot atomically. Returns its path."""
    plain = _plain_mapping(snapshot, "offline snapshot")
    _atomic_json(str(path), plain)
    return os.path.abspath(str(path))


def load_snapshot(path):
    """Read one snapshot back. Returns None when it is missing."""
    return _read_json(str(path))
