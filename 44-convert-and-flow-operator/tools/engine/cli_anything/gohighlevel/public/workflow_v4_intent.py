"""Pure full-graph intent helpers for the V4 workflow definition.

Frozen by the GHL modernization contract ledger, 2026-10-18 (GU-004 sections
1.1, 2.4 and 5.7, plus the workflows family record WF-04 .. WF-08). V4 scope and
Version come from the official workflows operation page
https://marketplace.gohighlevel.com/docs/ghl/workflows/<operation-slug>/.

Nothing here performs I/O, knows an HTTP endpoint, or invents a node schema.
The definition is treated as an opaque-but-structured graph:

* ``actions``, ``edges`` and ``triggers`` are collections of node mappings;
* a node is identified by its ``id`` or ``_id`` when one is present;
* a node without an identity is matched by exact canonical content only, so a
  modified id-less node is reported as ``removed`` + ``added`` -- it is never
  assumed to be the same node;
* every other top-level key is carried verbatim, including keys this module has
  never seen (unknown-but-supported nodes and settings).

``version`` is the workflow's own opaque revision.  It is never parsed, never
incremented, never coerced and never synthesised: ``extract_revision`` returns
the value it was given and ``carry_revision`` writes that exact value back.
A revision may be a non-integer string (the staging contract says it does not
always advance by one).

The one deliberate ceiling is node identity: the frozen evidence records
``id``/``_id`` for workflow list rows but does not publish the V4 action/edge
schema.  Id-less nodes therefore get content matching, not fuzzy matching.
"""

from __future__ import annotations

import hashlib
import math
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

from .errors import ContractViolation
from .result import canonical_json

COLLECTIONS: tuple[str, ...] = ("actions", "edges", "triggers")
REVISION_FIELD = "version"
IDENTITY_FIELDS: tuple[str, ...] = ("id", "_id")

UNTOUCHED = "untouched"
CHANGED = "changed"
ADDED = "added"
REMOVED = "removed"

_INTENT_KEYS: frozenset[str] = frozenset(
    {
        "set_fields",
        "upsert_actions",
        "upsert_edges",
        "upsert_triggers",
        "remove_actions",
        "remove_edges",
        "remove_triggers",
    }
)

_MISSING = object()


class RevisionError(ContractViolation):
    """A revision was missing or unusable.  Never a licence to invent one."""

    rule = "revision_invalid"


# ---------------------------------------------------------------------------
# revision echo helpers
# ---------------------------------------------------------------------------


def _revision_usable(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def extract_revision(definition: Mapping[str, Any]) -> Any:
    """Return the exact opaque revision unchanged.

    Accepted domains: non-empty string, integer, finite number.  The value is
    returned as-is; an int is never turned into a string, a float is never
    rounded, and a non-integer string such as ``"3.4"`` is returned verbatim.
    """

    if not isinstance(definition, Mapping):
        raise RevisionError(
            "definition_invalid", detail={"type": type(definition).__name__}
        )
    if REVISION_FIELD not in definition:
        raise RevisionError(
            "revision_missing", detail={"field": REVISION_FIELD}
        )
    value = definition[REVISION_FIELD]
    if not _revision_usable(value):
        raise RevisionError(
            "revision_invalid",
            detail={"field": REVISION_FIELD, "value_type": type(value).__name__},
        )
    return value


def carry_revision(
    definition: Mapping[str, Any], revision: Any
) -> dict[str, Any]:
    """Return a copy of ``definition`` carrying the exact ``revision``.

    Refuses to synthesise: a ``None``, boolean, empty string or non-finite
    number is rejected instead of being replaced by a plausible guess.
    """

    if not isinstance(definition, Mapping):
        raise RevisionError(
            "definition_invalid", detail={"type": type(definition).__name__}
        )
    if not _revision_usable(revision):
        raise RevisionError(
            "revision_invalid",
            detail={
                "field": REVISION_FIELD,
                "reason": "refusing_to_synthesise",
                "value_type": type(revision).__name__,
            },
        )
    out = deepcopy(dict(definition))
    out[REVISION_FIELD] = revision
    return out


def revision_equals(left: Any, right: Any) -> bool:
    """Exact comparison: no coercion between ``3``, ``3.0`` and ``"3"``."""

    if left is right:
        return True
    if type(left) is not type(right):
        return False
    return left == right


def extract_definition(payload: Any) -> Mapping[str, Any] | None:
    """Return the ``definition`` mapping from a read/create/update payload.

    The staging contract lists ``definition`` as a response field.  When it is
    absent the payload is unreadable for graph work -- ``None`` is returned,
    never a guess and never the whole payload.
    """

    if not isinstance(payload, Mapping):
        return None
    candidate = payload.get("definition")
    if isinstance(candidate, Mapping):
        return candidate
    data = payload.get("data")
    if isinstance(data, Mapping):
        candidate = data.get("definition")
        if isinstance(candidate, Mapping):
            return candidate
    return None


# ---------------------------------------------------------------------------
# node identity and canonical helpers
# ---------------------------------------------------------------------------


def node_identity(node: Any) -> str | None:
    """Stable identity from ``id`` / ``_id`` only.

    No other field is treated as an identity: inventing one would let a diff
    claim two nodes are the same step when the contract never said so.
    """

    if not isinstance(node, Mapping):
        return None
    for name in IDENTITY_FIELDS:
        if name not in node:
            continue
        value = node[name]
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value)
    return None


def _node_hash(node: Any) -> str:
    return hashlib.sha256(canonical_json(node).encode("utf-8")).hexdigest()


def _content_identity(node: Any) -> str:
    return "content:" + _node_hash(node)[:12]


def _validate_definition(value: Any, label: str) -> None:
    if not isinstance(value, Mapping):
        raise ContractViolation(
            "definition_invalid", detail={"label": label, "type": type(value).__name__}
        )


def _nodes_of(kind: str, definition: Mapping[str, Any]) -> tuple[Any, ...]:
    if kind not in definition:
        return ()
    nodes = definition[kind]
    if nodes is None:
        return ()
    if not isinstance(nodes, (list, tuple)):
        raise ContractViolation(
            "definition_collection_invalid",
            detail={"field": kind, "type": type(nodes).__name__},
        )
    return tuple(nodes)


def _split_nodes(kind: str, nodes: tuple[Any, ...]) -> tuple[
    dict[str, Any], list[Any]
]:
    by_id: dict[str, Any] = {}
    unidentified: list[Any] = []
    for node in nodes:
        identity = node_identity(node)
        if identity is None:
            unidentified.append(node)
            continue
        if identity in by_id:
            raise ContractViolation(
                "duplicate_node_identity", detail={"kind": kind, "identity": identity}
            )
        by_id[identity] = node
    return by_id, unidentified


# ---------------------------------------------------------------------------
# structured diff
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeDiff:
    kind: str
    identity: str
    status: str
    before: Any = None
    after: Any = None

    @property
    def before_hash(self) -> str | None:
        return _node_hash(self.before) if self.before is not None else None

    @property
    def after_hash(self) -> str | None:
        return _node_hash(self.after) if self.after is not None else None

    def as_evidence(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "status": self.status,
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
        }


@dataclass(frozen=True)
class FieldDiff:
    name: str
    status: str
    before: Any = None
    after: Any = None

    def as_evidence(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status}


@dataclass(frozen=True)
class DefinitionDiff:
    revision_before: Any
    revision_after: Any
    actions: tuple[NodeDiff, ...]
    edges: tuple[NodeDiff, ...]
    triggers: tuple[NodeDiff, ...]
    fields: tuple[FieldDiff, ...]

    # -- selectors -------------------------------------------------------
    @staticmethod
    def _pick(
        nodes: tuple[NodeDiff, ...], status: str
    ) -> tuple[NodeDiff, ...]:
        return tuple(node for node in nodes if node.status == status)

    def untouched_actions(self) -> tuple[NodeDiff, ...]:
        return self._pick(self.actions, UNTOUCHED)

    def changed_actions(self) -> tuple[NodeDiff, ...]:
        return self._pick(self.actions, CHANGED)

    def added_actions(self) -> tuple[NodeDiff, ...]:
        return self._pick(self.actions, ADDED)

    def removed_actions(self) -> tuple[NodeDiff, ...]:
        return self._pick(self.actions, REMOVED)

    def untouched_edges(self) -> tuple[NodeDiff, ...]:
        return self._pick(self.edges, UNTOUCHED)

    def changed_edges(self) -> tuple[NodeDiff, ...]:
        return self._pick(self.edges, CHANGED)

    def added_edges(self) -> tuple[NodeDiff, ...]:
        return self._pick(self.edges, ADDED)

    def removed_edges(self) -> tuple[NodeDiff, ...]:
        return self._pick(self.edges, REMOVED)

    def untouched_triggers(self) -> tuple[NodeDiff, ...]:
        return self._pick(self.triggers, UNTOUCHED)

    def changed_triggers(self) -> tuple[NodeDiff, ...]:
        return self._pick(self.triggers, CHANGED)

    def added_triggers(self) -> tuple[NodeDiff, ...]:
        return self._pick(self.triggers, ADDED)

    def removed_triggers(self) -> tuple[NodeDiff, ...]:
        return self._pick(self.triggers, REMOVED)

    # -- deletion detection ---------------------------------------------
    def deletion_requests(self) -> tuple[NodeDiff, ...]:
        """Every step present in ``current`` and absent from ``proposed``.

        This is the omission detector: the caller must see these as explicit
        deletion requests.  They are never silently dropped and no writer in
        this package deletes without one.
        """

        return (
            self.removed_actions()
            + self.removed_edges()
            + self.removed_triggers()
        )

    @property
    def has_deletions(self) -> bool:
        return bool(self.deletion_requests())

    # -- emptiness -------------------------------------------------------
    def content_is_empty(self) -> bool:
        """No node or field changed; revisions are ignored.

        Used after a write, where the server assigns a new revision but the
        graph content must match what was sent.
        """

        for nodes in (self.actions, self.edges, self.triggers):
            if any(node.status != UNTOUCHED for node in nodes):
                return False
        return all(item.status == UNTOUCHED for item in self.fields)

    def is_empty(self) -> bool:
        return self.content_is_empty() and revision_equals(
            self.revision_before, self.revision_after
        )

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for kind, nodes in (
            ("actions", self.actions),
            ("edges", self.edges),
            ("triggers", self.triggers),
        ):
            for status in (UNTOUCHED, CHANGED, ADDED, REMOVED):
                out[f"{status}_{kind}"] = sum(
                    1 for node in nodes if node.status == status
                )
        for status in (UNTOUCHED, CHANGED, ADDED, REMOVED):
            out[f"{status}_fields"] = sum(
                1 for item in self.fields if item.status == status
            )
        return out

    def as_evidence(self) -> dict[str, Any]:
        """Receipt-safe summary: identities and statuses, never payloads."""

        return {
            "revision_before": self.revision_before,
            "revision_after": self.revision_after,
            "counts": self.counts(),
            "actions": [node.as_evidence() for node in self.actions],
            "edges": [node.as_evidence() for node in self.edges],
            "triggers": [node.as_evidence() for node in self.triggers],
            "fields": [item.as_evidence() for item in self.fields],
            "deletion_requests": [
                {"kind": node.kind, "identity": node.identity}
                for node in self.deletion_requests()
            ],
            "content_empty": self.content_is_empty(),
            "empty": self.is_empty(),
        }


def _diff_collection(
    kind: str, current: tuple[Any, ...], proposed: tuple[Any, ...]
) -> tuple[NodeDiff, ...]:
    current_by_id, current_loose = _split_nodes(kind, current)
    proposed_by_id, proposed_loose = _split_nodes(kind, proposed)

    out: list[NodeDiff] = []
    for identity in sorted(current_by_id):
        before = current_by_id[identity]
        after = proposed_by_id.get(identity, _MISSING)
        if after is _MISSING:
            out.append(NodeDiff(kind, identity, REMOVED, before, None))
        elif _node_hash(before) == _node_hash(after):
            out.append(NodeDiff(kind, identity, UNTOUCHED, before, after))
        else:
            out.append(NodeDiff(kind, identity, CHANGED, before, after))
    for identity in sorted(set(proposed_by_id) - set(current_by_id)):
        out.append(
            NodeDiff(kind, identity, ADDED, None, proposed_by_id[identity])
        )

    # Id-less nodes: exact canonical content, greedy in input order.
    matched_proposed = [False] * len(proposed_loose)
    for before in current_loose:
        before_hash = _node_hash(before)
        index = None
        for position, candidate in enumerate(proposed_loose):
            if matched_proposed[position]:
                continue
            if _node_hash(candidate) == before_hash:
                index = position
                break
        if index is None:
            out.append(
                NodeDiff(kind, _content_identity(before), REMOVED, before, None)
            )
            continue
        matched_proposed[index] = True
        out.append(
            NodeDiff(
                kind,
                _content_identity(before),
                UNTOUCHED,
                before,
                proposed_loose[index],
            )
        )
    for position, after in enumerate(proposed_loose):
        if matched_proposed[position]:
            continue
        out.append(NodeDiff(kind, _content_identity(after), ADDED, None, after))
    return tuple(out)


def diff_definition(
    current: Mapping[str, Any], proposed: Mapping[str, Any]
) -> DefinitionDiff:
    """Structured diff of two complete definition graphs.

    Untouched / changed / added / removed are reported per action, edge and
    trigger.  A current step missing from ``proposed`` is a ``removed`` entry
    (a deletion request), never an omission.  Top-level fields other than the
    three collections and ``version`` are diffed by name.
    """

    _validate_definition(current, "current")
    _validate_definition(proposed, "proposed")

    revision_before = (
        current.get(REVISION_FIELD) if REVISION_FIELD in current else None
    )
    revision_after = (
        proposed.get(REVISION_FIELD) if REVISION_FIELD in proposed else None
    )

    actions = _diff_collection(
        "actions", _nodes_of("actions", current), _nodes_of("actions", proposed)
    )
    edges = _diff_collection(
        "edges", _nodes_of("edges", current), _nodes_of("edges", proposed)
    )
    triggers = _diff_collection(
        "triggers", _nodes_of("triggers", current), _nodes_of("triggers", proposed)
    )

    reserved = set(COLLECTIONS) | {REVISION_FIELD}
    current_fields = {
        str(key): value
        for key, value in current.items()
        if str(key) not in reserved
    }
    proposed_fields = {
        str(key): value
        for key, value in proposed.items()
        if str(key) not in reserved
    }
    field_diffs: list[FieldDiff] = []
    for name in sorted(set(current_fields) | set(proposed_fields)):
        in_current = name in current_fields
        in_proposed = name in proposed_fields
        if in_current and not in_proposed:
            field_diffs.append(
                FieldDiff(name, REMOVED, current_fields[name], None)
            )
        elif in_proposed and not in_current:
            field_diffs.append(FieldDiff(name, ADDED, None, proposed_fields[name]))
        elif canonical_json(current_fields[name]) == canonical_json(
            proposed_fields[name]
        ):
            field_diffs.append(
                FieldDiff(
                    name, UNTOUCHED, current_fields[name], proposed_fields[name]
                )
            )
        else:
            field_diffs.append(
                FieldDiff(name, CHANGED, current_fields[name], proposed_fields[name])
            )

    return DefinitionDiff(
        revision_before=revision_before,
        revision_after=revision_after,
        actions=actions,
        edges=edges,
        triggers=triggers,
        fields=tuple(field_diffs),
    )


# ---------------------------------------------------------------------------
# intent application
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Intent:
    """Approved change request expressed against a complete graph.

    ``set_fields`` touches top-level keys (``name``, ``source``, ``settings``
    and any unknown-but-supported key).  The three collections upsert by node
    identity and remove only by explicit identity.  ``version`` can be neither
    set nor removed: it is system-owned.
    """

    set_fields: Mapping[str, Any] = field(default_factory=dict)
    upsert_actions: tuple[Mapping[str, Any], ...] = ()
    upsert_edges: tuple[Mapping[str, Any], ...] = ()
    upsert_triggers: tuple[Mapping[str, Any], ...] = ()
    remove_actions: tuple[str, ...] = ()
    remove_edges: tuple[str, ...] = ()
    remove_triggers: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Intent":
        if not isinstance(value, Mapping):
            raise ContractViolation(
                "intent_invalid", detail={"type": type(value).__name__}
            )
        unknown = sorted(str(key) for key in value if str(key) not in _INTENT_KEYS)
        if unknown:
            raise ContractViolation("intent_field_unknown", detail={"fields": unknown})
        return cls(
            set_fields=dict(value.get("set_fields") or {}),
            upsert_actions=tuple(value.get("upsert_actions") or ()),
            upsert_edges=tuple(value.get("upsert_edges") or ()),
            upsert_triggers=tuple(value.get("upsert_triggers") or ()),
            remove_actions=tuple(value.get("remove_actions") or ()),
            remove_edges=tuple(value.get("remove_edges") or ()),
            remove_triggers=tuple(value.get("remove_triggers") or ()),
        )

    def as_mapping(self) -> dict[str, Any]:
        return {
            "set_fields": dict(self.set_fields),
            "upsert_actions": list(self.upsert_actions),
            "upsert_edges": list(self.upsert_edges),
            "upsert_triggers": list(self.upsert_triggers),
            "remove_actions": list(self.remove_actions),
            "remove_edges": list(self.remove_edges),
            "remove_triggers": list(self.remove_triggers),
        }


def _removal_ids(values: tuple[Any, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for value in values:
        if isinstance(value, bool) or value is None:
            raise ContractViolation(
                "intent_removal_invalid", detail={"type": type(value).__name__}
            )
        if not isinstance(value, (str, int)) or not str(value).strip():
            raise ContractViolation(
                "intent_removal_invalid", detail={"type": type(value).__name__}
            )
        out.append(str(value))
    return tuple(out)


def _validate_intent(plan: Intent) -> None:
    forbidden = sorted(set(map(str, plan.set_fields)) & (set(COLLECTIONS) | {REVISION_FIELD}))
    if forbidden:
        raise ContractViolation(
            "intent_field_forbidden", detail={"fields": forbidden}
        )
    for kind in COLLECTIONS:
        upserts = tuple(getattr(plan, "upsert_" + kind))
        removals = _removal_ids(tuple(getattr(plan, "remove_" + kind)))
        seen: set[str] = set()
        for node in upserts:
            if not isinstance(node, Mapping):
                raise ContractViolation(
                    "intent_node_invalid", detail={"kind": kind}
                )
            identity = node_identity(node)
            if identity is None:
                raise ContractViolation(
                    "intent_node_identity_missing", detail={"kind": kind}
                )
            if identity in seen:
                raise ContractViolation(
                    "intent_duplicate_node", detail={"kind": kind, "identity": identity}
                )
            if identity in removals:
                raise ContractViolation(
                    "intent_node_conflict", detail={"kind": kind, "identity": identity}
                )
            seen.add(identity)


def _index_of(
    nodes: list[Any], kind: str, identity: str
) -> int | None:
    found: int | None = None
    for position, node in enumerate(nodes):
        if node_identity(node) != identity:
            continue
        if found is not None:
            raise ContractViolation(
                "duplicate_node_identity", detail={"kind": kind, "identity": identity}
            )
        found = position
    return found


def apply_intent(
    current: Mapping[str, Any], intent: Intent | Mapping[str, Any]
) -> dict[str, Any]:
    """Return a complete proposed graph built from ``current`` + ``intent``.

    Every untouched node, edge, trigger, unknown-but-supported key and the
    opaque revision is preserved verbatim.  Nothing is dropped without an
    explicit ``remove_*`` identity; a removal that names an absent node is
    refused rather than ignored.
    """

    _validate_definition(current, "current")
    plan = intent if isinstance(intent, Intent) else Intent.from_mapping(intent)
    if not isinstance(plan, Intent):
        raise ContractViolation("intent_invalid")
    _validate_intent(plan)

    proposed: dict[str, Any] = deepcopy(dict(current))
    for key in sorted(map(str, plan.set_fields)):
        proposed[key] = deepcopy(plan.set_fields[key])

    for kind in COLLECTIONS:
        upserts = tuple(getattr(plan, "upsert_" + kind))
        removals = _removal_ids(tuple(getattr(plan, "remove_" + kind)))
        if kind not in proposed and not upserts and not removals:
            continue
        nodes = list(deepcopy(list(_nodes_of(kind, proposed))))
        for node in upserts:
            identity = node_identity(node)
            assert identity is not None  # validated
            position = _index_of(nodes, kind, identity)
            if position is None:
                nodes.append(deepcopy(dict(node)))
            else:
                nodes[position] = deepcopy(dict(node))
        for identity in removals:
            position = _index_of(nodes, kind, identity)
            if position is None:
                raise ContractViolation(
                    "removal_target_unknown",
                    detail={"kind": kind, "identity": identity},
                )
            del nodes[position]
        proposed[kind] = nodes

    return proposed


__all__ = [
    "COLLECTIONS",
    "REVISION_FIELD",
    "UNTOUCHED",
    "CHANGED",
    "ADDED",
    "REMOVED",
    "NodeDiff",
    "FieldDiff",
    "DefinitionDiff",
    "Intent",
    "RevisionError",
    "extract_revision",
    "carry_revision",
    "revision_equals",
    "extract_definition",
    "node_identity",
    "diff_definition",
    "apply_intent",
]
