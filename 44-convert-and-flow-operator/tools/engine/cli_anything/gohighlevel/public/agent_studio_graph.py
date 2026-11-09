"""Flow Agent graph and version document rules (offline, pure).

Split out of ``agent_studio`` so the document rules can be read, tested and
reviewed without the adapter's transport seams.  Nothing here calls the
network and nothing here invents an API field: the vocabulary it understands is
declared in ``StudioGraphSchema`` / ``StudioVersionSchema`` and anything it
cannot read is REPORTED, never blessed.

Document 1 section 26 requires, before a write: reference validation,
reachability, tool permissions and tenant-bound resource ids.  Section 26.2 also
requires preserving unknown/unmodified properties and avoiding deprecated
top-level graph fields when the contract is version-scoped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

#: Graph fields that belong to a VERSION-SCOPED document.  Finding one on the
#: agent envelope means the caller is using a deprecated top-level shape.
VERSION_SCOPED_FIELDS: tuple[str, ...] = (
    "nodes",
    "edges",
    "variables",
    "configuration",
)


@dataclass(frozen=True)
class StudioGraphSchema:
    """The graph vocabulary this validator understands.

    ``nodes``, ``edges``, ``variables`` and ``configuration`` are named by the
    source reference as the version-scoped document's fields.  The NESTED key
    names are not documented in this repository, so they are declared here and
    a graph this schema cannot read is reported, never blessed.
    """

    nodes_key: str = "nodes"
    edges_key: str = "edges"
    node_id_key: str = "id"
    edge_source_key: str = "source"
    edge_target_key: str = "target"
    entry_key: str = "entryNodeId"
    tool_keys: tuple[str, ...] = ("tool", "toolId", "tool_id")
    tenant_keys: tuple[str, ...] = (
        "locationId",
        "location_id",
        "tenantId",
        "tenant_id",
    )


@dataclass(frozen=True)
class StudioVersionSchema:
    """How to read a version record out of an agent payload."""

    versions_key: str = "versions"
    id_keys: tuple[str, ...] = ("id", "versionId", "version_id", "_id")
    state_keys: tuple[str, ...] = ("status", "type", "state")
    production_values: tuple[str, ...] = ("production", "published", "live")
    staging_values: tuple[str, ...] = ("staging", "draft")
    execution_id_keys: tuple[str, ...] = ("executionId", "execution_id", "id")


@dataclass(frozen=True)
class GraphFinding:
    code: str
    path: str
    detail: Mapping[str, Any]

    def as_mapping(self) -> dict[str, Any]:
        payload = {"code": self.code, "path": self.path}
        payload.update(dict(self.detail))
        return payload


@dataclass(frozen=True)
class GraphValidation:
    valid: bool
    findings: tuple[GraphFinding, ...]

    def codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.findings)

    def as_evidence(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "findings": [finding.as_mapping() for finding in self.findings],
        }


# ---------------------------------------------------------------------------
# graph validation
# ---------------------------------------------------------------------------


def validate_graph(
    graph: Any,
    *,
    tenant_id: str,
    schema: StudioGraphSchema | None = None,
    allowed_tools: Sequence[str] | None = None,
) -> GraphValidation:
    """Validate references, reachability, tool allowlisting and tenant ids.

    Pure, offline and total: it never raises for a malformed graph, it returns
    the findings.  A graph that declares tools without an allowlist gets
    ``tool_allowlist_required`` -- an unknown permission is never "allowed".
    """

    shape = schema or StudioGraphSchema()
    findings: list[GraphFinding] = []

    if not isinstance(graph, Mapping):
        return GraphValidation(False, (GraphFinding("graph_not_mapping", "$", {}),))

    raw_nodes = graph.get(shape.nodes_key)
    raw_edges = graph.get(shape.edges_key)
    if not isinstance(raw_nodes, (list, tuple)):
        findings.append(GraphFinding("nodes_missing", "$." + shape.nodes_key, {}))
        raw_nodes = ()
    if not isinstance(raw_edges, (list, tuple)):
        findings.append(GraphFinding("edges_missing", "$." + shape.edges_key, {}))
        raw_edges = ()

    node_ids: list[str] = []
    nodes: list[Mapping[str, Any]] = []
    for index, node in enumerate(raw_nodes):
        path = f"$.{shape.nodes_key}[{index}]"
        if not isinstance(node, Mapping):
            findings.append(GraphFinding("node_not_mapping", path, {}))
            continue
        nodes.append(node)
        node_id = node.get(shape.node_id_key)
        if not isinstance(node_id, str) or not node_id.strip():
            findings.append(GraphFinding("node_id_missing", path, {}))
            continue
        if node_id in node_ids:
            findings.append(GraphFinding("node_id_duplicate", path, {"node": node_id}))
            continue
        node_ids.append(node_id)

    known = set(node_ids)
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for index, edge in enumerate(raw_edges):
        path = f"$.{shape.edges_key}[{index}]"
        if not isinstance(edge, Mapping):
            findings.append(GraphFinding("edge_not_mapping", path, {}))
            continue
        source = edge.get(shape.edge_source_key)
        target = edge.get(shape.edge_target_key)
        if not isinstance(source, str) or not isinstance(target, str):
            findings.append(GraphFinding("edge_endpoint_missing", path, {}))
            continue
        dangling = [endpoint for endpoint in (source, target) if endpoint not in known]
        if dangling:
            findings.append(
                GraphFinding("edge_dangling", path, {"endpoint": dangling[0]})
            )
            continue
        adjacency[source].append(target)

    entry = graph.get(shape.entry_key)
    if entry is not None:
        if not isinstance(entry, str) or entry not in known:
            findings.append(GraphFinding("entry_node_absent", "$." + shape.entry_key, {}))
            entry = None
    start = entry or (node_ids[0] if node_ids else None)
    if start is not None:
        reached = _reachable(start, adjacency)
        for node_id in node_ids:
            if node_id not in reached:
                findings.append(
                    GraphFinding(
                        "unreachable_node",
                        "$." + shape.nodes_key,
                        {"node": node_id},
                    )
                )

    allow = None if allowed_tools is None else {str(tool) for tool in allowed_tools}
    for index, node in enumerate(nodes):
        declared = _declared_tools(node, shape)
        if not declared:
            continue
        if allow is None:
            findings.append(
                GraphFinding(
                    "tool_allowlist_required",
                    f"$.{shape.nodes_key}[{index}]",
                    {"tools": declared},
                )
            )
            continue
        for tool in declared:
            if tool not in allow:
                findings.append(
                    GraphFinding(
                        "tool_not_allowlisted",
                        f"$.{shape.nodes_key}[{index}]",
                        {"tool": tool},
                    )
                )

    findings.extend(_tenant_findings(graph, str(tenant_id), shape))
    return GraphValidation(not findings, tuple(findings))


def _reachable(start: str, adjacency: Mapping[str, Sequence[str]]) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, ()))
    return seen


def _declared_tools(node: Mapping[str, Any], schema: StudioGraphSchema) -> list[str]:
    declared: list[str] = []
    for key in schema.tool_keys:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            declared.append(value)
        elif isinstance(value, (list, tuple)):
            declared.extend(
                item for item in value if isinstance(item, str) and item.strip()
            )
    return sorted(set(declared))


def _tenant_findings(
    value: Any,
    tenant_id: str,
    schema: StudioGraphSchema,
    path: str = "$",
    depth: int = 0,
) -> list[GraphFinding]:
    # Detail never echoes the foreign value: it names the field and the path.
    findings: list[GraphFinding] = []
    if depth > 8:
        return findings
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key)
            if name in schema.tenant_keys and isinstance(item, str) and item != tenant_id:
                findings.append(
                    GraphFinding(
                        "foreign_tenant_resource", f"{path}.{name}", {"field": name}
                    )
                )
            findings.extend(
                _tenant_findings(item, tenant_id, schema, f"{path}.{name}", depth + 1)
            )
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            findings.extend(
                _tenant_findings(item, tenant_id, schema, f"{path}[{index}]", depth + 1)
            )
    return findings


# ---------------------------------------------------------------------------
# version selection helpers
# ---------------------------------------------------------------------------


def version_records(
    payload: Any, schema: StudioVersionSchema | None = None
) -> list[Mapping[str, Any]] | None:
    """Every readable version record, or None when the payload cannot be read."""

    shape = schema or StudioVersionSchema()
    if not isinstance(payload, Mapping):
        return None
    raw = payload.get(shape.versions_key)
    if not isinstance(raw, (list, tuple)):
        return None
    return [item for item in raw if isinstance(item, Mapping)]


def version_id_of(
    record: Mapping[str, Any], schema: StudioVersionSchema | None = None
) -> str | None:
    shape = schema or StudioVersionSchema()
    for key in shape.id_keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def version_state_of(
    record: Mapping[str, Any], schema: StudioVersionSchema | None = None
) -> str | None:
    shape = schema or StudioVersionSchema()
    for key in shape.state_keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def select_version(
    payload: Any,
    *,
    wanted: Sequence[str],
    schema: StudioVersionSchema | None = None,
) -> tuple[Mapping[str, Any] | None, str]:
    """Return ``(record, reason)``; reason is selected/absent/ambiguous/unreadable.

    Two matches are AMBIGUOUS, never "the first one".
    """

    shape = schema or StudioVersionSchema()
    records = version_records(payload, shape)
    if records is None:
        return None, "unreadable"
    matches = [
        record for record in records if version_state_of(record, shape) in tuple(wanted)
    ]
    if not matches:
        return None, "absent"
    if len(matches) > 1:
        return None, "ambiguous"
    return matches[0], "selected"


def version_by_id(
    payload: Any,
    version_id: str,
    schema: StudioVersionSchema | None = None,
) -> Mapping[str, Any] | None:
    shape = schema or StudioVersionSchema()
    for record in version_records(payload, shape) or ():
        if version_id_of(record, shape) == str(version_id):
            return record
    return None


# ---------------------------------------------------------------------------
# intent merge (preserve unknown/unmodified properties)
# ---------------------------------------------------------------------------


def merge_version(
    current: Mapping[str, Any],
    intent: Mapping[str, Any],
    *,
    allow_deletions: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    """Deep-merge an approved intent into the CURRENT complete version.

    Returns ``(merged, removed_paths)``.  A key present in the current document
    and absent from the intent is NOT a removal: it is preserved.  An explicit
    ``None`` value in the intent IS a removal request and is listed; the caller
    decides whether it may proceed.
    """

    removed: list[str] = []
    merged = _merge(current, intent, "", removed)
    del allow_deletions  # decision is the caller's; this function only reports
    return merged, removed


def _merge(current: Any, intent: Any, path: str, removed: list[str]) -> Any:
    if isinstance(intent, Mapping) and isinstance(current, Mapping):
        out: dict[str, Any] = {str(key): value for key, value in current.items()}
        for key, value in intent.items():
            name = str(key)
            child = f"{path}.{name}" if path else name
            if value is None:
                if name in out:
                    removed.append(child)
                out.pop(name, None)
                continue
            out[name] = _merge(out.get(name), value, child, removed)
        return out
    if isinstance(intent, Mapping):
        return _merge({}, intent, path, removed)
    if isinstance(intent, (list, tuple)):
        return _merge_list(current, intent, path, removed)
    return intent


def _merge_list(
    current: Any, intent: Sequence[Any], path: str, removed: list[str]
) -> Any:
    """Merge a list of id-bearing records by id; otherwise take the intent.

    A node (or any id-bearing record) OMITTED from the intent is PRESERVED, so
    an approved intent can never silently delete a node by forgetting it.  A
    list whose entries carry no id is the caller's complete approved list and
    replaces the current value.
    """

    if not isinstance(current, (list, tuple)):
        return list(intent)
    current_ids = [_record_id(item) for item in current]
    intent_ids = [_record_id(item) for item in intent]
    if None in current_ids or None in intent_ids:
        return list(intent)
    out: list[Any] = [_copy(item) for item in current]
    positions = {record_id: index for index, record_id in enumerate(current_ids)}
    for item in intent:
        record_id = str(item[_ID_KEY])
        child = f"{path}[{record_id}]" if path else f"[{record_id}]"
        index = positions.get(record_id)
        if index is None:
            positions[record_id] = len(out)
            out.append(_merge({}, item, child, removed))
        else:
            out[index] = _merge(out[index], item, child, removed)
    return out


_ID_KEY = "id"


def _record_id(item: Any) -> str | None:
    if not isinstance(item, Mapping):
        return None
    value = item.get(_ID_KEY)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy(item) for item in value]
    return value


def canonical(value: Any) -> str:
    """Deterministic JSON for an equality check (never for a secret)."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
