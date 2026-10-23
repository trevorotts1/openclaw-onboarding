"""
shared-utils/delivery/checkpoints.py — saved delivery state and logical/native
ID checkpoints for the GHL delivery stream (W4A, stream W4 DURABLE EXECUTION).

One writer for this file: assignment W4A. Contract source:
GHL-DELIVERY-SPEC.md "Durable execution (W4)" and "Delivery contract (W1)".

What this module guarantees:

1. Identity is the composite key (location, kind, parent, logical identity) —
   never a name alone. Names/slugs are stored as attributes only; there is no
   lookup path that treats a display name as identity. `find_by_name` exists
   for diagnostics and refuses to resolve when more than one record matches.
2. Read before create. `plan_create` returns reuse-vs-create, `record_create`
   refuses to re-create a key that already exists, so resuming a run never
   duplicates pages/forms/products.
3. Confirmed native IDs are persisted immediately (every mutation is an
   atomic write to the store file), keyed by the composite key. A confirmed
   identity is never silently rebound to a different native ID.
4. Reconcile after timeout; reject ambiguous matches. An operation with an
   unknown outcome holds a pending-op lock on its key until it is reconciled
   as confirmed / not_found / ambiguous. An ambiguous reconciliation raises
   and keeps the lock: retry is refused until a definite outcome exists.
5. Resume without deleting successful assets. There is no delete for
   confirmed records; `drop_unconfirmed` removes only pure scratch
   (PLANNED, never confirmed, no pending op).
6. New scratch vs reused business objects are distinct provenance values
   (PROVENANCE_NEW_SCRATCH vs PROVENANCE_REUSED).
7. Saving is never publishing. Nothing but `record_publish` sets a published
   URL, it requires an explicit authorization reference and an already
   CONFIGURED record, and states advance one step at a time through
   PLANNED -> CREATED -> CONFIGURED -> PUBLISHED -> VERIFIED.

PROVISIONAL integration seam (spec W4A is a provisional unit): the normative
delivery schema is owned by W1A in shared-utils/delivery/npage_contract.py,
which does not exist at this base. The state names above are taken verbatim
from the spec's contract section. When W1A lands, attach its record validator
with `set_contract_validator(fn)` — every create/adopt mutation then fails
closed against the normative schema without any change to this store.

Import pattern (from any script in the repo):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared-utils"))
    from delivery.checkpoints import CheckpointStore, CheckpointKey

(shared-utils/delivery needs no __init__.py; it imports as a namespace
package. Run the assert-based self-check:

    python3 -I shared-utils/delivery/checkpoints.py
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# States (GHL-DELIVERY-SPEC.md "Delivery contract"): distinct, ordered,
# forward-only. PUBLISHED is reachable only through record_publish.
# --------------------------------------------------------------------------
STATE_PLANNED = "PLANNED"
STATE_CREATED = "CREATED"
STATE_CONFIGURED = "CONFIGURED"
STATE_PUBLISHED = "PUBLISHED"
STATE_VERIFIED = "VERIFIED"
STATE_ORDER: Tuple[str, ...] = (
    STATE_PLANNED,
    STATE_CREATED,
    STATE_CONFIGURED,
    STATE_PUBLISHED,
    STATE_VERIFIED,
)

PROVENANCE_NEW_SCRATCH = "new-scratch"
PROVENANCE_REUSED = "reused"

_TOKEN_SEP = "\x1f"
_KIND_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_STORE_FORMAT = "ghl-delivery-checkpoints"
_STORE_VERSION = 1

# W4C restart/reconciliation consumes this list; keep statuses explicit.
OP_OPEN = "open"
OP_UNCERTAIN = "uncertain"
OP_DONE = "done"


class CheckpointError(ValueError):
    """Base class: checkpoint contract violation."""


class DuplicateCheckpointError(CheckpointError):
    """Key already checkpointed — a resume must never duplicate the object."""


class UnknownCheckpointError(CheckpointError):
    """No checkpoint for this key."""


class RevisionConflictError(CheckpointError):
    """Concurrent update: expected_revision does not match the stored record."""


class PendingOperationError(CheckpointError):
    """A prior operation on this key has no definite outcome yet — retry
    would risk creating the page/form/product twice."""


class AmbiguousMatchError(CheckpointError):
    """More than one record matches a non-identity query (name lookup).
    Ambiguous matches are rejected, never guessed."""


class AssetDeletionRefused(CheckpointError):
    """Successful assets are never deleted; only unconfirmed scratch may be
    dropped."""


class InvalidTransitionError(CheckpointError):
    """State change is not a legal forward step, or bypasses record_publish."""


class PublishNotAuthorized(CheckpointError):
    """Publication without an explicit authorization reference — saving is
    never publishing."""


def _require_text(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CheckpointError(f"{what} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class CheckpointKey:
    """Composite identity: (location, kind, parent, logical identity).

    `logical_id` is the caller-declared stable logical identity (e.g.
    "order-form", "hero-page"), NOT the platform name. `parent` is the
    logical identity of the owning node in the same location (None for
    roots). Two objects that share a name are never the same object.
    """

    location: str
    kind: str
    parent: Optional[str]
    logical_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "location", _require_text(self.location, "location"))
        kind = _require_text(self.kind, "kind")
        if not _KIND_RE.match(kind):
            raise CheckpointError(f"kind must match {_KIND_RE.pattern}: {kind!r}")
        object.__setattr__(self, "kind", kind)
        if self.parent is not None:
            object.__setattr__(self, "parent", _require_text(self.parent, "parent"))
        object.__setattr__(self, "logical_id", _require_text(self.logical_id, "logical_id"))

    def token(self) -> str:
        return _TOKEN_SEP.join((self.location, self.kind, self.parent or "-", self.logical_id))


@dataclass
class Checkpoint:
    """One saved delivery-state record. `revision` increments on every
    mutation and is the compare-and-swap token for concurrent writers."""

    key: CheckpointKey
    state: str = STATE_PLANNED
    name: Optional[str] = None
    slug: Optional[str] = None
    native_id: Optional[str] = None
    related_ids: Dict[str, str] = field(default_factory=dict)
    provenance: str = PROVENANCE_NEW_SCRATCH
    published_url: Optional[str] = None
    publish_authorization: Optional[str] = None
    revision: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_json(self) -> dict:
        return {
            "location": self.key.location,
            "kind": self.key.kind,
            "parent": self.key.parent,
            "logical_id": self.key.logical_id,
            "state": self.state,
            "name": self.name,
            "slug": self.slug,
            "native_id": self.native_id,
            "related_ids": dict(self.related_ids),
            "provenance": self.provenance,
            "published_url": self.published_url,
            "publish_authorization": self.publish_authorization,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_json(cls, blob: dict) -> "Checkpoint":
        return cls(
            key=CheckpointKey(blob["location"], blob["kind"], blob.get("parent"), blob["logical_id"]),
            state=blob["state"],
            name=blob.get("name"),
            slug=blob.get("slug"),
            native_id=blob.get("native_id"),
            related_ids=dict(blob.get("related_ids") or {}),
            provenance=blob.get("provenance", PROVENANCE_NEW_SCRATCH),
            published_url=blob.get("published_url"),
            publish_authorization=blob.get("publish_authorization"),
            revision=int(blob["revision"]),
            created_at=float(blob["created_at"]),
            updated_at=float(blob["updated_at"]),
        )


# Optional normative-schema seam (W1A npage_contract.py, not yet at HEAD).
_contract_validator: Optional[Callable[[dict], None]] = None


def set_contract_validator(fn: Optional[Callable[[dict], None]]) -> None:
    """Attach W1A's normative record validator (fail closed on its errors),
    or detach with None. The validator receives the record's JSON form."""
    global _contract_validator
    _contract_validator = fn


class CheckpointStore:
    """Durable JSON store of checkpoints and pending operations.

    Every mutation writes the whole store atomically (temp file in the same
    directory + os.replace + fsync) so a confirmed native ID survives a crash
    the moment the platform returned it.
    """

    def __init__(self, path) -> None:
        self.path = Path(path)
        self.checkpoints: Dict[str, Checkpoint] = {}
        self.ops: Dict[str, dict] = {}
        if self.path.exists():
            self._load()

    # ---- persistence ----------------------------------------------------
    def _load(self) -> None:
        blob = json.loads(self.path.read_text(encoding="utf-8"))
        if blob.get("format") != _STORE_FORMAT or blob.get("version") != _STORE_VERSION:
            raise CheckpointError(f"unsupported store format/version in {self.path}")
        self.checkpoints = {
            token: Checkpoint.from_json(rec) for token, rec in blob.get("checkpoints", {}).items()
        }
        for token, cp in self.checkpoints.items():
            if token != cp.key.token():
                raise CheckpointError(f"store key mismatch: {token}")
        self.ops = {op_id: dict(op) for op_id, op in blob.get("ops", {}).items()}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        blob = {
            "format": _STORE_FORMAT,
            "version": _STORE_VERSION,
            "checkpoints": {t: cp.to_json() for t, cp in sorted(self.checkpoints.items())},
            "ops": {i: op for i, op in sorted(self.ops.items())},
        }
        tmp = self.path.parent / f".{self.path.name}.tmp-{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(blob, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def _contract_validate(self, record: dict) -> None:
        if _contract_validator is not None:
            _contract_validator(record)

    def _bump(self, cp: Checkpoint, expected_revision: int) -> None:
        if expected_revision != cp.revision:
            raise RevisionConflictError(
                f"expected revision {expected_revision}, stored {cp.revision} for {cp.key.token()}"
            )
        cp.revision += 1
        cp.updated_at = time.time()

    def _open_op_for(self, token: str, exclude_op_id: Optional[str] = None) -> Optional[dict]:
        for op in self.ops.values():
            if op["op_id"] == exclude_op_id:
                continue
            if op["key"] == token and op["status"] in (OP_OPEN, OP_UNCERTAIN):
                return op
        return None

    # ---- read before create --------------------------------------------
    def read(self, key: CheckpointKey) -> Optional[Checkpoint]:
        return self.checkpoints.get(key.token())

    def plan_create(self, key: CheckpointKey) -> Tuple[str, Optional[Checkpoint]]:
        """Read before create: returns ("reuse", record) when the key is
        already checkpointed, ("blocked-pending", record-or-None) while an
        operation on it lacks a definite outcome, ("create", None) otherwise.
        Callers must branch on this before any platform create."""
        existing = self.read(key)
        if self._open_op_for(key.token()) is not None:
            return "blocked-pending", existing
        return ("reuse", existing) if existing is not None else ("create", None)

    def record_create(
        self,
        key: CheckpointKey,
        *,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        native_id: Optional[str] = None,
        related_ids: Optional[Dict[str, str]] = None,
        _resolving_op_id: Optional[str] = None,
    ) -> Checkpoint:
        """Checkpoint a newly created object. With `native_id` the confirmed
        ID is persisted immediately and the state becomes CREATED; without it
        the record stays PLANNED until `confirm_native`. Refuses to re-create
        an existing key (resume must never duplicate pages/forms/products)."""
        if self.read(key) is not None:
            raise DuplicateCheckpointError(f"already checkpointed: {key.token()}")
        if self._open_op_for(key.token(), _resolving_op_id) is not None:
            raise PendingOperationError(f"unresolved operation on {key.token()}")
        cp = Checkpoint(
            key=key,
            state=STATE_CREATED if native_id else STATE_PLANNED,
            name=name,
            slug=slug,
            native_id=native_id,
            related_ids=dict(related_ids or {}),
            provenance=PROVENANCE_NEW_SCRATCH,
        )
        self._contract_validate(cp.to_json())
        self.checkpoints[key.token()] = cp
        self._save()
        return cp

    def adopt(
        self,
        key: CheckpointKey,
        *,
        native_id: str,
        name: Optional[str] = None,
        slug: Optional[str] = None,
        related_ids: Optional[Dict[str, str]] = None,
    ) -> Checkpoint:
        """Checkpoint a REUSED business object (found by read-before-create).
        Always confirmed, always PROVENANCE_REUSED — never indistinguishable
        from new scratch."""
        _require_text(native_id, "native_id")
        if self.read(key) is not None:
            raise DuplicateCheckpointError(f"already checkpointed: {key.token()}")
        if self._open_op_for(key.token()) is not None:
            raise PendingOperationError(f"unresolved operation on {key.token()}")
        cp = Checkpoint(
            key=key,
            state=STATE_CREATED,
            name=name,
            slug=slug,
            native_id=native_id,
            related_ids=dict(related_ids or {}),
            provenance=PROVENANCE_REUSED,
        )
        self._contract_validate(cp.to_json())
        self.checkpoints[key.token()] = cp
        self._save()
        return cp

    # ---- confirmed IDs, persisted immediately ---------------------------
    def confirm_native(
        self, key: CheckpointKey, native_id: str, expected_revision: int
    ) -> Checkpoint:
        """Persist a confirmed native ID immediately (compare-and-swap on
        revision). Rebinding a confirmed identity to a DIFFERENT native ID is
        refused; re-confirming the same ID is an idempotent no-op."""
        _require_text(native_id, "native_id")
        cp = self.checkpoints.get(key.token())
        if cp is None:
            raise UnknownCheckpointError(f"no checkpoint for {key.token()}")
        if cp.native_id == native_id:
            return cp
        if cp.native_id is not None:
            raise DuplicateCheckpointError(
                f"{key.token()} already confirmed as {cp.native_id}; refusing rebind to {native_id}"
            )
        self._bump(cp, expected_revision)
        cp.native_id = native_id
        if cp.state == STATE_PLANNED:
            cp.state = STATE_CREATED
        self._contract_validate(cp.to_json())
        self._save()
        return cp

    def set_related_ids(
        self, key: CheckpointKey, related_ids: Dict[str, str], expected_revision: int
    ) -> Checkpoint:
        """Persist auxiliary native identities (folder/container/page ids)
        keyed by role, immediately."""
        cp = self.checkpoints.get(key.token())
        if cp is None:
            raise UnknownCheckpointError(f"no checkpoint for {key.token()}")
        self._bump(cp, expected_revision)
        cp.related_ids.update({str(k): _require_text(v, f"related_ids[{k}]") for k, v in related_ids.items()})
        self._save()
        return cp

    # ---- state: distinct, forward-only, saving != publishing -------------
    def set_state(self, key: CheckpointKey, new_state: str, expected_revision: int) -> Checkpoint:
        """Advance exactly one step in PLANNED -> CREATED -> CONFIGURED ->
        PUBLISHED -> VERIFIED. PUBLISHED is refused here: only
        `record_publish` publishes, and only with an authorization."""
        if new_state not in STATE_ORDER:
            raise InvalidTransitionError(f"unknown state: {new_state!r}")
        cp = self.checkpoints.get(key.token())
        if cp is None:
            raise UnknownCheckpointError(f"no checkpoint for {key.token()}")
        if new_state == STATE_PUBLISHED:
            raise InvalidTransitionError("use record_publish() to publish; saving is never publishing")
        current = STATE_ORDER.index(cp.state)
        target = STATE_ORDER.index(new_state)
        if target != current + 1:
            raise InvalidTransitionError(
                f"{cp.key.token()}: {cp.state} -> {new_state} is not one forward step"
            )
        if new_state == STATE_CREATED and cp.native_id is None:
            raise InvalidTransitionError("CREATED requires a confirmed native_id")
        if new_state == STATE_VERIFIED and cp.published_url is None:
            raise InvalidTransitionError("VERIFIED requires a recorded published_url")
        self._bump(cp, expected_revision)
        cp.state = new_state
        self._contract_validate(cp.to_json())
        self._save()
        return cp

    def record_publish(
        self,
        key: CheckpointKey,
        *,
        url: str,
        authorization: str,
        expected_revision: int,
    ) -> Checkpoint:
        """Publish exactly this checkpointed object, under an explicit
        authorization reference. One record published never implies the rest
        are. Requires state CONFIGURED; advances to PUBLISHED."""
        _require_text(url, "url")
        if not isinstance(authorization, str) or not authorization.strip():
            raise PublishNotAuthorized(
                "publication requires an explicit authorization reference; saving is never publishing"
            )
        authorization = authorization.strip()
        cp = self.checkpoints.get(key.token())
        if cp is None:
            raise UnknownCheckpointError(f"no checkpoint for {key.token()}")
        if cp.state != STATE_CONFIGURED:
            raise InvalidTransitionError(
                f"{cp.key.token()} is {cp.state}; publishing requires CONFIGURED"
            )
        self._bump(cp, expected_revision)
        cp.published_url = url
        cp.publish_authorization = authorization
        cp.state = STATE_PUBLISHED
        self._contract_validate(cp.to_json())
        self._save()
        return cp

    # ---- pending operations: reconcile after timeout --------------------
    def begin_op(
        self, key: CheckpointKey, op_id: str, *, action: str, timeout_s: float = 120.0
    ) -> dict:
        """Open an operation whose outcome may be uncertain (platform call
        that can time out or crash the run). While any op on the key is
        open/uncertain, another op or a create on that key is refused —
        retry without reconciliation would risk duplicates."""
        _require_text(op_id, "op_id")
        _require_text(action, "action")
        if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or timeout_s <= 0:
            raise CheckpointError("timeout_s must be a positive number")
        if op_id in self.ops:
            raise DuplicateCheckpointError(f"op_id already used: {op_id}")
        prior = self._open_op_for(key.token())
        if prior is not None:
            raise PendingOperationError(
                f"op {prior['op_id']} on {key.token()} is {prior['status']}; reconcile it first"
            )
        now = time.time()
        op = {
            "op_id": op_id,
            "key": key.token(),
            "action": action,
            "status": OP_OPEN,
            "started_at": now,
            "deadline": now + float(timeout_s),
            "outcome": None,
            "native_id": None,
        }
        self.ops[op_id] = op
        self._save()
        return dict(op)

    def resolve_op(self, op_id: str) -> dict:
        if op_id not in self.ops:
            raise UnknownCheckpointError(f"no operation {op_id}")
        return dict(self.ops[op_id])

    def stale_ops(self, now: Optional[float] = None) -> List[dict]:
        """Ops past their deadline with no definite outcome — the restart /
        reconciliation surface (W4C). Returns them as uncertain, durably."""
        now = time.time() if now is None else now
        due = []
        for op in self.ops.values():
            if op["status"] in (OP_OPEN, OP_UNCERTAIN) and op["deadline"] < now:
                op["status"] = OP_UNCERTAIN
                due.append(dict(op))
        if due:
            self._save()
        return due

    def complete_op(self, op_id: str, *, native_id: Optional[str] = None) -> dict:
        """Close an op whose outcome IS known. With `native_id` the confirmed
        ID is persisted immediately: it confirms an existing PLANNED record,
        or creates the record when the op was the create itself."""
        op = self._require_open_op(op_id)
        key = self._key_from_token(op["key"])
        if native_id is not None:
            _require_text(native_id, "native_id")
            existing = self.read(key)
            if existing is None:
                self.record_create(key, native_id=native_id, _resolving_op_id=op_id)
            else:
                self.confirm_native(key, native_id, existing.revision)
            op["native_id"] = native_id
            op["outcome"] = "confirmed"
        else:
            if self.read(key) is None:
                raise UnknownCheckpointError(
                    f"op {op_id} produced no native_id and {op['key']} is not checkpointed"
                )
            op["outcome"] = "completed"
        op["status"] = OP_DONE
        self._save()
        return dict(op)

    def reconcile_op(
        self, op_id: str, *, outcome: str, native_id: Optional[str] = None
    ) -> dict:
        """Resolve an op whose outcome was unknown (timeout/crash).

        confirmed  — the object exists: persist its native ID immediately.
        not_found  — the object was never created: release the lock so a
                     fresh attempt may run.
        ambiguous  — REJECTED: raises AmbiguousMatchError and keeps the lock;
                     retry stays refused until a definite outcome is proven.
        """
        op = self._require_open_op(op_id)
        if outcome == "ambiguous":
            raise AmbiguousMatchError(
                f"op {op_id} outcome ambiguous for {op['key']}; refusing to guess — "
                "reconcile with a definite match or not_found"
            )
        if outcome == "confirmed":
            return self.complete_op(op_id, native_id=native_id)
        if outcome != "not_found":
            raise CheckpointError(f"unknown reconcile outcome: {outcome!r}")
        op["outcome"] = "not_found"
        op["status"] = OP_DONE
        self._save()
        return dict(op)

    def _require_open_op(self, op_id: str) -> dict:
        if op_id not in self.ops:
            raise UnknownCheckpointError(f"no operation {op_id}")
        op = self.ops[op_id]
        if op["status"] == OP_DONE:
            raise CheckpointError(f"op {op_id} already closed ({op['outcome']})")
        return op

    def _key_from_token(self, token: str) -> CheckpointKey:
        location, kind, parent, logical_id = token.split(_TOKEN_SEP)
        return CheckpointKey(location, kind, None if parent == "-" else parent, logical_id)

    # ---- non-identity queries (diagnostics only) ------------------------
    def find_by_name(
        self, location: str, kind: str, parent: Optional[str], name: str
    ) -> Checkpoint:
        """Diagnostic lookup by display name. Names are never identity:
        zero matches raises UnknownCheckpointError, more than one raises
        AmbiguousMatchError. Use the composite key for all mutations."""
        _require_text(name, "name")
        hits = [
            cp
            for cp in self.checkpoints.values()
            if cp.key.location == location
            and cp.key.kind == kind
            and cp.key.parent == parent
            and cp.name == name
        ]
        if not hits:
            raise UnknownCheckpointError(
                f"no {kind} named {name!r} in {location!r}/{parent!r}; names are never identity"
            )
        if len(hits) > 1:
            ids = sorted(cp.key.logical_id for cp in hits)
            raise AmbiguousMatchError(
                f"{len(hits)} checkpoints named {name!r}: logical_ids {ids}; rejecting ambiguous match"
            )
        return hits[0]

    def list_checkpoints(
        self,
        *,
        location: Optional[str] = None,
        kind: Optional[str] = None,
        parent: Optional[str] = None,
    ) -> List[Checkpoint]:
        out = [
            cp
            for cp in self.checkpoints.values()
            if (location is None or cp.key.location == location)
            and (kind is None or cp.key.kind == kind)
            and (parent is None or cp.key.parent == parent)
        ]
        return sorted(out, key=lambda cp: cp.key.token())

    # ---- scratch cleanup only ------------------------------------------
    def drop_unconfirmed(self, key: CheckpointKey, expected_revision: int) -> None:
        """Drop PURE SCRATCH only: PLANNED, never confirmed, no pending op.
        Successful (confirmed) assets are never deleted — resuming a run must
        not remove anything the platform already holds."""
        cp = self.checkpoints.get(key.token())
        if cp is None:
            raise UnknownCheckpointError(f"no checkpoint for {key.token()}")
        if cp.native_id is not None or cp.state != STATE_PLANNED:
            raise AssetDeletionRefused(
                f"{key.token()} is {cp.state} (native_id={cp.native_id}); successful assets are never deleted"
            )
        if self._open_op_for(key.token()) is not None:
            raise AssetDeletionRefused(f"{key.token()} has an unresolved operation")
        self._bump(cp, expected_revision)
        del self.checkpoints[key.token()]
        self._save()


# --------------------------------------------------------------------------
# Assert-based self-check. Run: python3 -I shared-utils/delivery/checkpoints.py
# --------------------------------------------------------------------------
def _self_check() -> int:
    import tempfile

    checks = 0

    def ok(cond: bool, what: str) -> None:
        nonlocal checks
        assert cond, f"FAIL: {what}"
        checks += 1

    def raised(fn, exc, what: str) -> None:
        nonlocal checks
        try:
            fn()
        except exc:
            checks += 1
            return
        except Exception as other:  # noqa: BLE001 - self-check honesty
            raise AssertionError(f"FAIL: {what}: raised {type(other).__name__} not {exc.__name__}")
        raise AssertionError(f"FAIL: {what}: nothing raised")

    with tempfile.TemporaryDirectory(prefix="operator-W4A-U1-") as td:
        path = Path(td) / "checkpoints.json"

        # -- composite identity, never name alone ------------------------
        hero_a = CheckpointKey("acc1/funnelA", "page", "home", "hero")
        hero_b = CheckpointKey("acc1/funnelA", "page", "home-alt", "hero")
        hero_c = CheckpointKey("acc1/funnelB", "page", "home", "hero")
        ok(hero_a.token() != hero_b.token(), "same logical_id, different parent = distinct")
        ok(hero_a.token() != hero_c.token(), "same logical_id, different location = distinct")
        raised(lambda: CheckpointKey("", "page", None, "hero"), CheckpointError, "empty location")
        raised(lambda: CheckpointKey("acc1", "Page!", None, "hero"), CheckpointError, "bad kind")
        raised(lambda: CheckpointKey("acc1", "page", "  ", "hero"), CheckpointError, "blank parent")
        raised(lambda: CheckpointKey("acc1", "page", None, ""), CheckpointError, "empty logical_id")

        store = CheckpointStore(path)

        # -- read before create ------------------------------------------
        arm, existing = store.plan_create(hero_a)
        ok(arm == "create" and existing is None, "plan_create: absent key -> create")
        cp1 = store.record_create(hero_a, name="Hero", slug="hero")
        ok(cp1.native_id is None and cp1.state == STATE_PLANNED, "record_create without native_id stays PLANNED")
        arm, existing = store.plan_create(hero_a)
        ok(arm == "reuse" and existing is not None, "plan_create: existing key -> reuse")
        raised(lambda: store.record_create(hero_a, name="Hero"), DuplicateCheckpointError,
               "record_create refuses duplicate key (resume never duplicates)")

        # -- confirmed IDs persisted immediately -------------------------
        cp1 = store.confirm_native(hero_a, "page_1001", cp1.revision)
        ok(cp1.state == STATE_CREATED and cp1.native_id == "page_1001", "confirm_native persists and moves to CREATED")
        reopened = CheckpointStore(path)
        ok(reopened.read(hero_a).native_id == "page_1001", "confirmed ID durable across store reload")
        cas_key = CheckpointKey("acc1/funnelA", "page", "home", "cas")
        store.record_create(cas_key)
        raised(lambda: store.confirm_native(cas_key, "page_2002", 99), RevisionConflictError,
               "confirm_native CAS rejects stale revision")
        ok(store.confirm_native(cas_key, "page_2002", store.read(cas_key).revision).native_id
           == "page_2002", "confirm_native with current revision persists immediately")
        raised(lambda: store.confirm_native(hero_a, "page_OTHER", cp1.revision), DuplicateCheckpointError,
               "confirmed identity never rebound to a different native ID")
        ok(store.confirm_native(hero_a, "page_1001", 99).native_id == "page_1001",
           "same-ID re-confirm is a non-mutating no-op even at a stale revision")

        # -- name is not identity ---------------------------------------
        other = CheckpointKey("acc1/funnelA", "page", "home", "hero-2")
        store.record_create(other, name="Hero", slug="hero-2")
        store.record_create(hero_b, name="Alt Hero", slug="alt-hero")
        raised(lambda: store.find_by_name("acc1/funnelA", "page", "home", "Hero"),
               AmbiguousMatchError, "two same-named records: ambiguous match rejected")
        solo = store.find_by_name("acc1/funnelA", "page", "home-alt", "Alt Hero")
        ok(solo.key == hero_b, "diagnostic name lookup resolves exactly one")
        raised(lambda: store.find_by_name("acc1/funnelA", "page", "home", "Nope"),
               UnknownCheckpointError, "name lookup with zero hits fails closed")

        # -- provenance: new scratch vs reused ---------------------------
        reused_key = CheckpointKey("acc1/funnelA", "form", "home", "order-form")
        reused = store.adopt(reused_key, native_id="form_77", name="Order Form")
        ok(reused.provenance == PROVENANCE_REUSED and reused.state == STATE_CREATED,
           "adopt marks reused business object")
        ok(store.read(hero_a).provenance == PROVENANCE_NEW_SCRATCH, "record_create marks new scratch")
        raised(lambda: store.adopt(reused_key, native_id="form_78"), DuplicateCheckpointError,
               "adopt refuses existing key")

        # -- states: forward-only, saving != publishing ------------------
        rev = store.read(hero_a).revision
        raised(lambda: store.set_state(hero_a, STATE_PLANNED, rev), InvalidTransitionError,
               "no backward state step")
        raised(lambda: store.set_state(hero_a, STATE_VERIFIED, rev), InvalidTransitionError,
               "no skipped state steps")
        cp = store.set_state(hero_a, STATE_CONFIGURED, rev)
        ok(cp.state == STATE_CONFIGURED and cp.published_url is None,
           "CONFIGURED record saved but not published")
        rev = cp.revision
        raised(lambda: store.set_state(hero_a, STATE_PUBLISHED, rev), InvalidTransitionError,
               "set_state cannot publish; only record_publish does")
        raised(lambda: store.record_publish(hero_a, url="https://x.example/hero", authorization="",
                                            expected_revision=rev), PublishNotAuthorized,
               "publish without authorization refused")
        cp = store.record_publish(hero_a, url="https://x.example/hero",
                                  authorization="approval-2026-10-23#hero", expected_revision=rev)
        ok(cp.state == STATE_PUBLISHED and cp.published_url == "https://x.example/hero",
           "authorized publish records real URL")
        ok(cp.publish_authorization.startswith("approval-"), "authorization reference recorded")
        ok(store.read(other).state == STATE_PLANNED,
           "one page published never implies the rest are")
        rev2 = store.read(reused_key).revision
        raised(lambda: store.record_publish(reused_key, url="https://x.example/f", authorization="a1",
                                            expected_revision=rev2), InvalidTransitionError,
               "publish requires CONFIGURED first")
        cp = store.set_state(hero_a, STATE_VERIFIED, cp.revision)
        ok(cp.state == STATE_VERIFIED, "VERIFIED reachable only after PUBLISHED")

        # -- pending ops: reconcile after timeout, reject ambiguous -------
        op_key = CheckpointKey("acc1/funnelA", "product", None, "coaching")
        op = store.begin_op(op_key, "op-1", action="create", timeout_s=60)
        ok(op["status"] == OP_OPEN, "begin_op opens")
        raised(lambda: store.begin_op(op_key, "op-2", action="create"), PendingOperationError,
               "second op on same key refused while first unresolved")
        raised(lambda: store.record_create(op_key), PendingOperationError,
               "create refused while op outcome unknown")
        arm, _ = store.plan_create(op_key)
        ok(arm == "blocked-pending", "plan_create reports blocked-pending")
        due = store.stale_ops(now=op["deadline"] + 1)
        ok(len(due) == 1 and due[0]["op_id"] == "op-1" and due[0]["status"] == OP_UNCERTAIN,
           "past deadline without outcome -> uncertain, surfaced for reconcile")
        raised(lambda: store.reconcile_op("op-1", outcome="ambiguous"), AmbiguousMatchError,
               "ambiguous reconciliation rejected")
        raised(lambda: store.begin_op(op_key, "op-3", action="create"), PendingOperationError,
               "still locked after ambiguous reconcile")
        raised(lambda: store.reconcile_op("op-1", outcome="maybe"), CheckpointError,
               "unknown reconcile outcome refused")
        store.reconcile_op("op-1", outcome="not_found")
        arm, _ = store.plan_create(op_key)
        ok(arm == "create", "not_found reconciliation releases lock for a clean retry")

        # confirmed-after-timeout path persists the ID immediately
        op = store.begin_op(op_key, "op-4", action="create", timeout_s=60)
        store.stale_ops(now=op["deadline"] + 1)
        store.reconcile_op("op-4", outcome="confirmed", native_id="prod_9")
        ok(CheckpointStore(path).read(op_key).native_id == "prod_9",
           "reconciled-confirmed native ID durable across reload")
        raised(lambda: store.complete_op("op-4"), CheckpointError, "closed op cannot close twice")

        # complete_op on a PLANNED record confirms it
        conf_key = CheckpointKey("acc1/funnelA", "survey", "home", "intake")
        store.record_create(conf_key, name="Intake")
        store.begin_op(conf_key, "op-5", action="configure", timeout_s=30)
        store.complete_op("op-5", native_id="survey_5")
        ok(store.read(conf_key).native_id == "survey_5" and store.read(conf_key).state == STATE_CREATED,
           "complete_op confirms PLANNED record and persists immediately")

        # -- resume without duplicating or deleting successful assets ----
        resumed = CheckpointStore(path)
        ok(len(resumed.list_checkpoints(location="acc1/funnelA")) == 7, "resume sees all seven checkpoints")
        raised(lambda: resumed.record_create(hero_a, name="Hero"), DuplicateCheckpointError,
               "resume cannot re-create confirmed page")
        raised(lambda: resumed.drop_unconfirmed(hero_a, resumed.read(hero_a).revision),
               AssetDeletionRefused, "confirmed asset never deleted")
        scratch = CheckpointKey("acc1/funnelA", "page", "home", "scratch-draft")
        resumed.record_create(scratch)
        raised(lambda: resumed.drop_unconfirmed(scratch, 99), RevisionConflictError,
               "scratch drop is CAS-guarded")
        resumed.drop_unconfirmed(scratch, resumed.read(scratch).revision)
        ok(resumed.read(scratch) is None, "pure scratch (PLANNED, unconfirmed) droppable")
        locked = CheckpointKey("acc1/funnelA", "page", "home", "locked-draft")
        resumed.record_create(locked)
        resumed.begin_op(locked, "op-6", action="configure", timeout_s=30)
        raised(lambda: resumed.drop_unconfirmed(locked, resumed.read(locked).revision),
               AssetDeletionRefused, "record with unresolved op never dropped")

        # -- related identities persisted immediately --------------------
        cp = resumed.set_related_ids(hero_a, {"container_id": "cont_3", "folder_id": "fld_3"},
                                     resumed.read(hero_a).revision)
        ok(cp.related_ids["container_id"] == "cont_3", "related native identities stored")
        ok(CheckpointStore(path).read(hero_a).related_ids["folder_id"] == "fld_3",
           "related identities durable across reload")

        # -- normative-schema seam is detachable and fail-closed ----------
        def bad_validator(record: dict) -> None:
            raise CheckpointError("normative schema rejected record")

        set_contract_validator(bad_validator)
        raised(lambda: resumed.record_create(CheckpointKey("acc1/funnelA", "page", "home", "seam")),
               CheckpointError, "attached W1 validator fails closed")
        set_contract_validator(None)
        ok(resumed.record_create(CheckpointKey("acc1/funnelA", "page", "home", "seam")).state
           == STATE_PLANNED, "validator detached -> built-in validation only")

    return checks


if __name__ == "__main__":
    n = _self_check()
    print(f"self-check OK ({n} assertions)")
