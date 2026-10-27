#!/usr/bin/env python3
"""Check launch build-graph branch joins or sync graphs to the schema sidecar."""

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parent
GROUPS = (
    "launch-a",
    "launch-ai",
    "launch-b",
    "launch-c",
    "launch-text",
    "engagement-broadcast",
    "funnel-specific-followups",
    "multichannel-automation",
    "sales-close-sequences",
    "welcome-indoctrination",
)
SIDECAR = BASE / "_schema" / "build-graphs.launch.json"


def declared_join(node):
    return isinstance(node.get("attributes"), dict) and (
        node["attributes"].get("join") is True
    )


def inspect(path, document):
    graph = document.get("build_graph")
    if not isinstance(graph, list) or not graph:
        return None

    errors = []
    by_id = {}
    for node in graph:
        if isinstance(node, dict) and isinstance(node.get("id"), str):
            by_id[node["id"]] = node

    ids = set(by_id)
    triggers = [node for node in graph if node.get("type") == "trigger"]
    if len(triggers) != 1:
        errors.append(f"trigger count={len(triggers)} (expected 1)")
    elif "after" in triggers[0]:
        errors.append(f"trigger {triggers[0]['id']} has after")

    predecessors = {node_id: set() for node_id in ids}
    owners = {node_id: set() for node_id in ids}
    edges = {node_id: set() for node_id in ids}

    for node_id, node in by_id.items():
        after = node.get("after")
        if isinstance(after, str):
            targets = [after]
        elif isinstance(after, list):
            targets = after
            if not targets or not all(isinstance(item, str) for item in targets):
                errors.append(f"node {node_id}: invalid after array")
        elif "after" in node:
            errors.append(f"node {node_id}: invalid after")
            targets = []
        else:
            targets = []

        for target in targets:
            if target not in ids:
                errors.append(f"node {node_id}: unresolved after target {target}")
            else:
                predecessors[node_id].add(target)
                edges[target].add(node_id)

        branches = node.get("branches", {})
        if not isinstance(branches, dict):
            errors.append(f"node {node_id}: branches must be an object")
            continue
        for target in branches.values():
            if not isinstance(target, str) or target not in ids:
                errors.append(f"node {node_id}: unresolved branches target {target}")
                continue
            owners[target].add(node_id)
            predecessors[target].add(node_id)
            edges[node_id].add(target)

    for node_id, node in by_id.items():
        if len(predecessors[node_id]) > 1 and not declared_join(node):
            errors.append(f"node {node_id}: multiple predecessors without join")
        if len(owners[node_id]) > 1 and not declared_join(node):
            errors.append(f"node {node_id}: multiple branch owners without join")

    if len(triggers) == 1:
        start = triggers[0].get("id")
        reached = set()
        pending = [start]
        while pending:
            current = pending.pop()
            if current in reached:
                continue
            reached.add(current)
            pending.extend(edges.get(current, set()))
        for node_id in sorted(ids - reached):
            errors.append(f"node {node_id}: unreachable from trigger")

    for node_id, node in by_id.items():
        if node.get("type") != "if_else":
            continue
        branches = node.get("branches", {})
        if not isinstance(branches, dict):
            continue

        arm_scopes = []
        for arm_name, target in branches.items():
            scope = set()
            pending = [target] if isinstance(target, str) else []
            while pending:
                current = pending.pop()
                if current in scope or current not in ids:
                    continue
                scope.add(current)
                current_node = by_id[current]
                if declared_join(current_node):
                    continue
                pending.extend(edges[current])
            arm_scopes.append(scope)

            if not any(declared_join(by_id[item]) for item in scope):
                terminals = {
                    item for item in scope if not edges[item]
                }
                if not terminals or any(
                    by_id[item].get("type") != "workflow_goal"
                    for item in terminals
                ):
                    errors.append(
                        f"arm {arm_name} of if_else {node_id} "
                        "dead-ends without a workflow_goal"
                    )

        for candidate in sorted(ids):
            if candidate in arm_scopes[0] if arm_scopes else False:
                count = sum(candidate in scope for scope in arm_scopes)
                if count >= 2 and not declared_join(by_id[candidate]):
                    errors.append(
                        f"node {candidate}: reached by {count} arms of if_else {node_id}"
                    )

    return len(graph), sum(declared_join(node) for node in graph), errors


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="check graphs (default)")
    mode.add_argument("--sync", action="store_true", help="write graph sidecar")
    args = parser.parse_args()

    files = []
    for group in GROUPS:
        directory = BASE / group
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"{path.relative_to(ROOT).as_posix()}: invalid JSON: {exc}")
                continue
            if isinstance(document, dict):
                graph = document.get("build_graph")
                if isinstance(graph, list) and graph:
                    files.append((path, document))

    if args.sync:
        sidecar = {}
        for path, document in files:
            key = path.relative_to(ROOT).as_posix()
            sidecar[key] = {
                "kind": document.get("kind"),
                "build_graph": document["build_graph"],
            }
        SIDECAR.parent.mkdir(parents=True, exist_ok=True)
        SIDECAR.write_text(
            json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {len(sidecar)} graphs to {SIDECAR.relative_to(ROOT).as_posix()}")
        return 0

    total_nodes = total_joins = total_violations = 0
    for path, document in files:
        result = inspect(path, document)
        if result is None:
            continue
        nodes, joins, errors = result
        total_nodes += nodes
        total_joins += joins
        total_violations += len(errors)
        relative = path.relative_to(ROOT).as_posix()
        status = "OK" if not errors else "; ".join(errors)
        print(f"{relative} nodes={nodes} joins={joins} {status}")

    print(
        f"TOTAL files={len(files)} nodes={total_nodes} "
        f"joins={total_joins} violations={total_violations}"
    )
    return 1 if total_violations else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
