#!/usr/bin/env python3
"""Validate and apply template schema v2.0.0. Run from skill root."""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
SIDECAR = Path("automation-templates/_schema/build-graphs.launch.json")
MATCHER = Path("automation-templates/_matcher/buildable-templates.json")
VERSION = "2.0.0"

ACTIONS = set("""
trigger add_contact_tag remove_contact_tag update_contact_field
create_update_contact assign_user remove_assigned_user edit_conversation
dnd_contact add_notes task-notification find_contact sms email call voicemail
messenger gmb internal_notification instagram-dm ig_interactive_messenger
fb_interactive_messenger respond_on_comment review_request wait if_else goto
transition workflow_split workflow_goal add_to_workflow remove_from_workflow
remove_from_all_workflows update_custom_value drip chatgpt conversation_ai
create_opportunity find_opportunity remove_opportunity webhook custom_webhook
google_sheets slack_message custom_code math_operation text_formatter
number_formatter datetime_formatter array_functions ivr_gather ivr_connect_call
facebook_conversion_api stripe_one_time_charge update_appointment_status
membership_grant_offer membership_revoke_offer
""".split())

EXCLUDED_NAMES = {
    "automation-build.schema.json",
    "text-sets.json",
}
EXCLUDED_DIRS = {"fixtures", "tests", "__pycache__"}


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def template_paths():
    base = ROOT / "automation-templates"
    if not base.is_dir():
        raise ValueError("automation-templates directory not found")

    result = []
    for group in sorted(base.iterdir()):
        if not group.is_dir() or group.name.startswith("_"):
            continue
        for path in sorted(group.glob("*.json")):
            if path.name in EXCLUDED_NAMES:
                continue
            if any(part in EXCLUDED_DIRS for part in path.parts):
                continue
            try:
                document = read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(document, dict) and (
                "id" in document or "name" in document
            ):
                result.append(path.relative_to(ROOT))
    return result


def derived_kind(document):
    build = document.get("ghl_build", {})
    if isinstance(build, dict):
        actions = build.get("actions_in_order")
        if isinstance(actions, list) and len(actions) >= 2:
            return "sequence_stack"

        workflow = build.get("workflow")
        if isinstance(workflow, dict):
            nodes = workflow.get("nodes")
            if isinstance(nodes, list) and len(nodes) >= 2:
                return "sequence_stack"

            branches = workflow.get("if_else_branches")
            if isinstance(branches, (list, dict)) and branches:
                return "sequence_stack"

    if any(
        key in document
        for key in (
            "the_4_paths",
            "schedule",
            "branches",
            "indoctrination_sequence",
        )
    ):
        return "sequence_stack"

    sequence = document.get("sequence")
    markers = {
        "phase",
        "day",
        "at",
        "action",
        "actions",
        "when",
        "order",
        "timing",
        "channels",
        "type",
        "sends",
    }
    if isinstance(sequence, list) and len(sequence) >= 2:
        sequence_keys = set()
        for item in sequence:
            if isinstance(item, dict):
                sequence_keys.update(item.keys())
        if sequence_keys & markers:
            return "sequence_stack"

    return "single_message"


def validate_graph(path, graph):
    if not isinstance(graph, dict):
        return "graph must be an object"
    if set(graph) != {"kind", "build_graph"}:
        return "graph must contain exactly kind and build_graph"
    if graph["kind"] not in {"single_message", "sequence_stack"}:
        return "invalid kind"
    nodes = graph["build_graph"]
    if not isinstance(nodes, list) or not nodes:
        return "build_graph must be a non-empty array"

    by_id = {}
    triggers = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            return f"node {index} must be an object"
        allowed_keys = {"id", "type", "after", "branches", "attributes"}
        if set(node) - allowed_keys:
            return f"node {index} has extra keys"
        if not {"id", "type", "attributes"} <= set(node):
            return f"node {index} missing required keys"
        node_id = node["id"]
        if not isinstance(node_id, str) or not node_id:
            return f"node {index} has invalid id"
        if node_id in by_id:
            return f"duplicate id {node_id}"
        if node["type"] not in ACTIONS:
            return f"node {node_id} has invalid type {node['type']!r}"
        if not isinstance(node["attributes"], dict):
            return f"node {node_id} attributes must be an object"
        if "branches" in node:
            if node["type"] != "if_else":
                return f"node {node_id}: branches require if_else"
            if not isinstance(node["branches"], dict) or not node["branches"]:
                return f"node {node_id}: branches must be a non-empty object"
        if node["type"] == "trigger":
            triggers.append(node)
            if "after" in node:
                return f"trigger {node_id} must not have after"
        elif "after" not in node:
            return f"non-trigger {node_id} missing after"
        by_id[node_id] = node

    if len(triggers) != 1:
        return f"expected exactly one trigger, found {len(triggers)}"

    edges = {node_id: [] for node_id in by_id}
    for node_id, node in by_id.items():
        if "after" in node:
            target = node["after"]
            if not isinstance(target, str) or target not in by_id:
                return f"node {node_id} references missing target {target!r}"
            edges[target].append(node_id)
        if "branches" in node:
            for target in node["branches"].values():
                if not isinstance(target, str) or target not in by_id:
                    return f"node {node_id} references missing target {target!r}"
                edges[node_id].append(target)

    start = triggers[0]["id"]
    reached = set()
    pending = [start]
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(edges[current])

    missing = set(by_id) - reached
    if missing:
        return "unreachable nodes: " + ", ".join(sorted(missing))
    return None


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=".schema-", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def ordered_document(document, kind, graph=None):
    result = {"schema_version": VERSION, "kind": kind}
    result.update(
        (key, value)
        for key, value in document.items()
        if key not in {"schema_version", "kind", "build_graph"}
    )
    if graph is not None:
        result["build_graph"] = graph["build_graph"]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true",
        help="validate without writing files",
    )
    args = parser.parse_args()

    try:
        sidecar = read_json(ROOT / SIDECAR)
        if not isinstance(sidecar, dict):
            raise ValueError("sidecar must be a JSON object")
        paths = template_paths()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"INVALID {SIDECAR}: {exc}", file=sys.stderr)
        return 1

    errors = []
    for relative, graph in sidecar.items():
        error = validate_graph(relative, graph)
        if error:
            errors.append((relative, error))
        if not isinstance(relative, str):
            errors.append((str(relative), "template path must be a string"))
            continue
        candidate = Path(relative)
        if (
            candidate.is_absolute()
            or ".." in candidate.parts
            or candidate.parts[:1] != ("automation-templates",)
        ):
            errors.append((relative, "invalid relative template path"))
        elif not (ROOT / candidate).is_file():
            errors.append((relative, "sidecar template file not found"))

    documents = {}
    for relative in paths:
        try:
            documents[relative] = read_json(ROOT / relative)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append((relative.as_posix(), f"cannot read JSON: {exc}"))

    for relative, graph in sidecar.items():
        candidate = Path(relative) if isinstance(relative, str) else None
        if candidate in documents and isinstance(graph, dict):
            kind = graph.get("kind")
            if kind not in {"single_message", "sequence_stack"}:
                continue

    if args.check:
        for relative, document in documents.items():
            if document.get("schema_version") != VERSION:
                errors.append((relative.as_posix(), "schema_version missing or outdated"))
            if document.get("kind") not in {"single_message", "sequence_stack"}:
                errors.append((relative.as_posix(), "kind missing or invalid"))

    for relative, error in errors:
        print(f"INVALID {relative}: {error}", file=sys.stderr)
    if errors:
        return 1

    plans = []
    buildable = []
    for relative in paths:
        document = documents[relative]
        key = relative.as_posix()
        graph = sidecar.get(key)
        kind = graph["kind"] if graph else derived_kind(document)
        updated = ordered_document(document, kind, graph)
        plans.append((relative, updated, kind, graph))

        if graph:
            template_id = updated.get("id", updated.get("name", relative.stem))
            buildable.append({
                "key": f"{relative.parent.name}/{template_id}",
                "path": f"{relative.parent.name}/{relative.name}",
                "kind": kind,
            })

    buildable.sort(key=lambda item: item["key"])
    matcher = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "count": len(buildable),
        "templates": buildable,
    }

    if not args.check:
        for relative, updated, _, _ in plans:
            atomic_write(
                ROOT / relative,
                json.dumps(updated, indent=2, ensure_ascii=False),
            )
        atomic_write(
            ROOT / MATCHER,
            json.dumps(matcher, indent=2, ensure_ascii=False),
        )

    for relative, _, kind, graph in plans:
        nodes = len(graph["build_graph"]) if graph else "-"
        verb = "CHECKED" if args.check else "WROTE"
        print(f"{verb} {relative.as_posix()} kind={kind} nodes={nodes}")
    print(f"TOTAL templates={len(plans)} graphs={len(buildable)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
