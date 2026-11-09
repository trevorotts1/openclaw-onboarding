"""Graph validation for workflow exports (WF-23).

Termination: starting at the single root, every path must either reach a
terminal node (type in TERMINAL_TYPES) or enter a declared loop. A path
that ends at a node with no successor whose type is not terminal is
UNTERMINATED; a node with no successor never counts as an end by itself.

Loop semantics: a cycle is legal only when both conditions hold:
1. at least one node on the cycle has a type in LOOP_TYPES (the loop/goal
   allow-list), and
2. that loop node is reachable from the root (the existing BFS 'reached'
   set), i.e. entered by a non-cyclic root-to-node path before the cycle
   repeats.
Every other cycle is CYCLE. A designated loop type never exempts a cycle
on its own: an unreachable drip/goto/transition cycle is still CYCLE.
"""

import argparse
import json
import os
import sys

BRANCH_TYPES = {"if_else", "workflow_split", "goto", "transition"}
TERMINAL_TYPES = {"end", "workflow_goal", "goal", "exit"}
LOOP_TYPES = {"drip", "workflow_goal", "goto", "transition"}
KINDS = ("tags", "custom_fields", "custom_values", "calendars", "pipelines")


def _trigger_wired(contract):
    trigger = contract.get("trigger")
    return (
        isinstance(trigger, dict)
        and bool(trigger.get("kind") or trigger.get("tag"))
    )


def _tags_exist(contract):
    tags = contract.get("tags")
    return isinstance(tags, dict) and any(
        isinstance(tags.get(key), list) and bool(tags[key])
        for key in ("applies", "reads")
    )


def _applies_tags_present_as_nodes(contract):
    tags = contract.get("tags")
    return (
        isinstance(tags, dict)
        and isinstance(tags.get("applies"), list)
        and bool(tags["applies"])
    )


def _fields_exist(contract):
    return isinstance(contract.get("fields"), list) and bool(contract["fields"])


def _custom_values_exist(contract):
    return (
        isinstance(contract.get("custom_values"), list)
        and bool(contract["custom_values"])
    )


def _calendars_exist(contract):
    return (
        isinstance(contract.get("calendars"), list)
        and bool(contract["calendars"])
    )


def _pipeline_stages_exist(contract):
    pipeline = contract.get("pipeline")
    return (
        isinstance(pipeline, dict)
        and isinstance(pipeline.get("stages"), list)
        and bool(pipeline["stages"])
    )


MUST_PASS_CHECKS = {
    "trigger_wired": _trigger_wired,
    "tags_exist": _tags_exist,
    "applies_tags_present_as_nodes": _applies_tags_present_as_nodes,
    "fields_exist": _fields_exist,
    "custom_values_exist": _custom_values_exist,
    "calendars_exist": _calendars_exist,
    "pipeline_stages_exist": _pipeline_stages_exist,
}


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def templates(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("workflowData"), dict):
            value = templates(data["workflowData"])
            if value is not None:
                return value
        if isinstance(data.get("templates"), list):
            return data["templates"]
        if "data" in data:
            return templates(data["data"])
    return None


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def strings(value):
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (dict, list)):
        return [
            x
            for v in (value.values() if isinstance(value, dict) else value)
            for x in strings(v)
        ]
    return []


def merge_tags(value, prefix):
    found = []
    pos = 0
    while True:
        start = value.find("{{", pos)
        if start < 0:
            return found
        end = value.find("}}", start + 2)
        if end < 0:
            return found
        token = value[start + 2:end].strip()
        if token.startswith(prefix) and token[len(prefix):].strip():
            found.append(token[len(prefix):].strip())
        pos = end + 2


def dependencies(data):
    result = {k: [] for k in KINDS}

    def add(kind, value):
        for name in strings(value):
            if name not in result[kind]:
                result[kind].append(name)

    for item in walk(data):
        if not isinstance(item, dict):
            continue
        for key in ("tag", "tags"):
            if key in item:
                add("tags", item[key])
        if item.get("field") in ("tagsAdded", "tagsRemoved"):
            add("tags", item.get("value", item.get("values", [])))
        for key in ("customFieldId", "customFieldName"):
            if key in item:
                add("custom_fields", item[key])
        for key in ("calendarId", "calendar"):
            if key in item:
                add("calendars", item[key])
        for key in ("pipelineId", "pipeline"):
            if key in item:
                add("pipelines", item[key])
        for value in item.values():
            if isinstance(value, str):
                for name in merge_tags(value, "contact."):
                    add("custom_fields", name)
                for prefix in ("custom_values.", "customValue."):
                    for name in merge_tags(value, prefix):
                        add("custom_values", name)
    return result


def identity_failures(nodes):
    """Pre-write identity/authoring rules over a template list. Returns a list of failure dicts."""
    failures = []
    ids = [node.get("id") for node in nodes]
    existing = {node_id for node_id in ids if node_id is not None}
    by_id = {}

    for node in nodes:
        node_id = node.get("id")
        if node_id is None or node_id == "":
            failures.append({
                "kind": "ID_MISSING",
                "node_id": None,
                "reason": "missing_node_id",
            })
        else:
            by_id.setdefault(node_id, node)

    counts = {}
    for node_id in ids:
        if node_id is not None:
            counts[node_id] = counts.get(node_id, 0) + 1
    duplicates = sorted(
        (node_id for node_id, count in counts.items() if count > 1),
        key=str,
    )
    if duplicates:
        failures.append({
            "kind": "DUPLICATE_ID",
            "ids": duplicates,
            "reason": "duplicate_node_id",
        })

    def authored_targets(value):
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, (dict, list)):
            return [
                item
                for v in (value.values() if isinstance(value, dict) else value)
                for item in authored_targets(v)
            ]
        return []

    seen_targets = set()
    for node in nodes:
        node_id = node.get("id")
        for field in ("next", "branches"):
            value = node.get(field)
            for target in authored_targets(value):
                if target in existing or (node_id, target) in seen_targets:
                    continue
                seen_targets.add((node_id, target))
                failures.append({
                    "kind": "DANGLING",
                    "node_id": node_id,
                    "field": field,
                    "target": target,
                })

        if node.get("type") == "if_else":
            branches = node.get("branches")
            valid = (
                isinstance(branches, dict)
                and len(branches) == 2
                and len(set(branches.values())) == 2
                and all(target in existing for target in branches.values())
            )
            if not valid:
                failures.append({
                    "kind": "MALFORMED_BRANCH",
                    "node_id": node_id,
                    "branches": branches,
                    "reason": "if_else_requires_two_distinct_existing_targets",
                })

    roots = [
        node.get("id") for node in nodes
        if node.get("parentKey") in (None, "")
    ]
    if len(roots) != 1:
        failures.append({
            "kind": "ROOT",
            "roots": roots,
            "reason": "expected_exactly_one_root",
        })

    for node in nodes:
        node_id = node.get("id")
        parent = node.get("parentKey")
        if parent not in (None, "") and parent not in existing:
            failures.append({
                "kind": "PARENT_INVALID",
                "node_id": node_id,
                "parentKey": parent,
                "reason": "parent_not_found",
            })

    completed = set()
    for node in nodes:
        start = node.get("id")
        if start is None or start in completed:
            continue
        path = []
        positions = {}
        current = start

        while current not in (None, "") and current in by_id:
            if current in positions:
                cycle = path[positions[current]:] + [current]
                failures.append({
                    "kind": "PARENT_CYCLE",
                    "node_id": start,
                    "cycle": cycle,
                    "reason": "parent_cycle",
                })
                break
            if current in completed:
                break
            positions[current] = len(path)
            path.append(current)
            current = by_id[current].get("parentKey")

        completed.update(path)

    return failures


def graph(data, nodes, trigger):
    ids = [n.get("id") for n in nodes]
    existing = set(ids)
    edges = {}
    # Identity checks were implemented and tested but never called from here, so
    # the gate that runs this function (WF-23) reported PASS on a graph with
    # duplicate node ids, malformed branch targets, ambiguous roots and invalid
    # parents — while its own PASS evidence claimed "integrity". A check the
    # gate never runs is not a check.
    failures = list(identity_failures(nodes))
    unverified = []
    roots = [n for n in nodes if n.get("parentKey") in (None, "")]
    root = roots[0].get("id") if len(roots) == 1 else None
    if len(roots) != 1:
        pass  # ROOT already emitted by identity_failures() above; do not re-emit.
    elif trigger and trigger != root:
        failures.append({
            "kind": "ROOT",
            "node_id": root,
            "reason": "trigger_target_mismatch",
            "trigger_target": trigger,
        })

    exposes_branches = any("branches" in n for n in nodes)
    for n in nodes:
        targets = []
        targets.extend(strings(n.get("next")))
        targets.extend(strings(n.get("branches")))
        edges[n.get("id")] = list(dict.fromkeys(targets))
    edge_count = len({
        (source, target)
        for source, targets in edges.items()
        for target in targets if target in existing
    })
    # No DANGLING re-emit here: identity_failures() above already emits one
    # DANGLING per missing authored target for both the next and branches
    # fields in every shape (str, list, dict). Re-emitting would report the
    # same missing target twice and inflate any count derived from failures.
    reached = set()
    if root is not None:
        queue = [root]
        while queue:
            current = queue.pop(0)
            if current in reached:
                continue
            reached.add(current)
            queue.extend(t for t in edges.get(current, []) if t in existing)
    for n in nodes:
        if n.get("id") not in reached:
            failures.append({
                "kind": "ORPHAN",
                "node_id": n.get("id"),
                "name": n.get("name"),
                "type": n.get("type"),
            })
    for n in nodes:
        targets = set(edges[n.get("id")])
        count = len(targets)
        if n.get("type") in BRANCH_TYPES and count < 2:
            if not exposes_branches and not strings(n.get("next")):
                unverified.append({
                    "node_id": n.get("id"),
                    "reason": "branch_targets_not_exposed",
                })
            else:
                failures.append({
                    "kind": "UNWIRED_BRANCH",
                    "node_id": n.get("id"),
                    "name": n.get("name"),
                    "type": n.get("type"),
                    "targets": count,
                })
        elif n.get("type") not in BRANCH_TYPES and count >= 2:
            failures.append({
                "kind": "DEAD_END",
                "node_id": n.get("id"),
                "name": n.get("name"),
                "type": n.get("type"),
                "targets": count,
                "reason": "ambiguous_fanout",
            })

    # Seventh structural condition: branch-body containment.
    by_id = {n.get("id"): n for n in nodes}
    parent_map = {n.get("id"): n.get("parentKey") for n in nodes}
    branch_members = {
        n.get("id"): n["branches"]
        for n in nodes
        if n.get("type") in BRANCH_TYPES
        and isinstance(n.get("branches"), dict)
        and n["branches"]
    }

    def _is_declared_join(node):
        # check_joins.py's EXACT predicate: attributes.join is True, nothing
        # else. A multi-parent without that attribute is an ERROR there, not
        # a join — so it must not exempt here either.
        return (
            isinstance(node.get("attributes"), dict)
            and node["attributes"].get("join") is True
        )

    def membership(node_id):
        # A declared join is the confluence, not a member of either arm: it
        # belongs to NO branch, whatever else is true of it (type, direction,
        # parent count). Without this, a join that is also a branch target
        # (e.g. the false-arm target that the true arm's body feeds) reads as
        # true-arm-into-false-arm and every real shipped join fails the gate.
        if _is_declared_join(by_id.get(node_id) or {}):
            return None
        path = []
        seen = set()
        current = node_id
        while current is not None and current not in seen:
            seen.add(current)
            path.append(current)
            current = parent_map.get(current)

        for branch_id in path[1:]:
            if _is_declared_join(by_id.get(branch_id) or {}):
                # A confluence seals every branch above it: the downward path
                # from any higher arm target to this node passes through this
                # join, so the node is post-confluence for all of them — it
                # belongs to no branch. This is exactly check_joins' model,
                # whose arm scopes stop expanding at joins. Without it, a
                # join's own continuation (join -> next) reads as
                # None-into-arm and every shipped join with a successor fails.
                return None
            if branch_id not in branch_members:
                continue
            branch = branch_members[branch_id]
            branch_index = path.index(branch_id)
            for path_node in path[:branch_index]:
                for branch_key, target_id in branch.items():
                    if target_id == path_node:
                        return "%s/%s" % (branch_id, branch_key)
            return None
        return None

    memberships = {node_id: membership(node_id) for node_id in by_id}
    cross_branch_seen = set()
    for n in nodes:
        source = n.get("id")
        for target in edges.get(source, []):
            if target not in existing or (source, target) in cross_branch_seen:
                continue
            cross_branch_seen.add((source, target))

            if (
                n.get("type") in BRANCH_TYPES
                and target in strings(n.get("branches"))
            ):
                continue

            from_set = memberships.get(source)
            to_set = memberships.get(target)
            if from_set == to_set:
                continue
            if from_set is not None and to_set is None:
                continue

            failures.append({
                "kind": "CROSS_BRANCH",
                "node_id": source,
                "target": target,
                "from_set": from_set,
                "to_set": to_set,
                "reason": "branch_body_flows_into_other_body",
            })

    colors, cycles = {}, set()
    loop_covered = set()

    def visit(node_id, stack):
        colors[node_id] = 1
        stack.append(node_id)
        for target in edges.get(node_id, []):
            if target not in existing:
                continue
            if colors.get(target) == 1:
                cycle = tuple(stack[stack.index(target):] + [target])
                if cycle in cycles:
                    continue
                cycles.add(cycle)
                cycle_nodes = cycle[:-1]
                legal_loop_nodes = {
                    cycle_id for cycle_id in cycle_nodes
                    if by_id[cycle_id].get("type") in LOOP_TYPES
                    and cycle_id in reached
                }
                if legal_loop_nodes:
                    loop_covered.update(cycle_nodes)
                else:
                    failures.append({
                        "kind": "CYCLE",
                        "node_id": node_id,
                        "cycle": list(cycle),
                    })
            elif colors.get(target, 0) == 0:
                visit(target, stack)
        stack.pop()
        colors[node_id] = 2

    for node_id in ids:
        if node_id is not None and not colors.get(node_id):
            visit(node_id, [])

    # Reachable paths must terminate or enter a legal loop.
    if root is not None:
        worklist = [root]
        seen = set()
        unverified_ids = {
            item.get("node_id") for item in unverified
        }
        while worklist:
            node_id = worklist.pop()
            if node_id in seen or node_id not in existing:
                continue
            seen.add(node_id)
            node = by_id[node_id]
            node_type = node.get("type")
            if node_type in TERMINAL_TYPES or node_id in loop_covered:
                continue
            successors = [
                target for target in edges.get(node_id, [])
                if target in existing
            ]
            if not successors:
                if node_id not in unverified_ids:
                    failures.append({
                        "kind": "UNTERMINATED",
                        "node_id": node_id,
                        "name": node.get("name"),
                        "type": node_type,
                        "reason": "no_terminal_successor",
                    })
                continue
            worklist.extend(successors)

    verdict = "FAIL" if failures else ("UNVERIFIED" if unverified else "PASS")
    return {
        "wf": "WF-23",
        "verdict": verdict,
        "failures": failures,
        "nodes": len(nodes),
        "edges": edge_count,
        "root": root,
        "orphans": sum(f["kind"] == "ORPHAN" for f in failures),
        # How many branch nodes the graph CONTAINS, not how many are broken.
        # The rubric grants D4 = N/A (=10) only on a count of zero, so deriving
        # that from `unwired` would hand a free 10 to a well-wired branching
        # workflow. These two numbers answer different questions.
        "branches": sum(
            1 for node in nodes if node.get("type") in BRANCH_TYPES
        ),
        "unverified": unverified,
    }


def validate_build_contract(contract, manifest, manifest_missing, contract_path):
    """Validate build-contract schema and verify declared dependencies."""
    required = (
        "playbook_structure_hash", "tags", "fields", "calendars", "pipeline"
    )
    schema_errors = []
    for key in required:
        if not isinstance(contract, dict) or key not in contract or contract[key] is None:
            schema_errors.append("missing_key:%s" % key)

    if not isinstance(contract, dict):
        contract = {}

    acceptance = contract.get("acceptance")
    if (
        not isinstance(acceptance, dict)
        or not isinstance(acceptance.get("must_pass"), list)
        or not acceptance["must_pass"]
    ):
        schema_errors.append("contract_must_pass_empty")
    else:
        for index, entry in enumerate(acceptance["must_pass"]):
            if not isinstance(entry, str) or not entry.strip():
                schema_errors.append(
                    "invalid_entry:acceptance.must_pass[%d]" % index
                )
            elif entry not in MUST_PASS_CHECKS:
                schema_errors.append("unknown_must_pass_check:" + entry)
            elif not MUST_PASS_CHECKS[entry](contract):
                schema_errors.append("must_pass_check_unresolved:" + entry)

    structure_hash = contract.get("playbook_structure_hash")
    if not isinstance(structure_hash, str) or not structure_hash.strip():
        schema_errors.append("empty_or_invalid:playbook_structure_hash")

    declared = []

    def add(kind, name):
        entry = {"kind": kind, "name": name}
        if entry not in declared:
            declared.append(entry)

    tags = contract.get("tags")
    if not isinstance(tags, dict):
        schema_errors.append("invalid_type:tags")
    else:
        applies = tags.get("applies")
        if not isinstance(applies, list):
            schema_errors.append("invalid_type:tags.applies")
        else:
            for item in applies:
                if not isinstance(item, str) or not item.strip():
                    schema_errors.append("invalid_entry:tags.applies")
                else:
                    add("tags", item.strip())

    fields = contract.get("fields")
    if not isinstance(fields, list):
        schema_errors.append("invalid_type:fields")
    else:
        for index, item in enumerate(fields):
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not item["name"].strip()
            ):
                schema_errors.append("invalid_entry:fields[%d].name" % index)
            else:
                add("custom_fields", item["name"].strip())

    calendars = contract.get("calendars")
    if not isinstance(calendars, list):
        schema_errors.append("invalid_type:calendars")
    else:
        for index, item in enumerate(calendars):
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or not item["id"].strip()
            ):
                schema_errors.append("invalid_entry:calendars[%d].id" % index)
            else:
                add("calendars", item["id"].strip())

    pipeline = contract.get("pipeline")
    if not isinstance(pipeline, dict):
        schema_errors.append("invalid_type:pipeline")
    else:
        stages = pipeline.get("stages")
        if not isinstance(stages, list):
            schema_errors.append("invalid_type:pipeline.stages")
        else:
            for index, item in enumerate(stages):
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("name"), str)
                    or not item["name"].strip()
                ):
                    schema_errors.append(
                        "invalid_entry:pipeline.stages[%d].name" % index
                    )
                else:
                    add("pipelines", item["name"].strip())

    report = {
        "wf": "WF-18",
        "verdict": "FAIL",
        "present": [],
        "missing": [],
        "schema_errors": schema_errors,
        "contract_path": contract_path,
    }
    if "contract_must_pass_empty" in schema_errors:
        report["reason"] = "contract_must_pass_empty"

    if manifest_missing:
        if schema_errors:
            report["verdict"] = "FAIL"
            report.setdefault(
                "reason",
                "schema errors present; reachability also unproven",
            )
        else:
            report["verdict"] = "UNVERIFIED"
            report["reason"] = "no dependency manifest supplied; reachability unproven"
        if declared:
            report["declared"] = declared
        return report

    for entry in declared:
        kind, name = entry["kind"], entry["name"]
        if name in strings(manifest.get(kind)):
            report["present"].append(entry)
        else:
            report["missing"].append(entry)

    report["verdict"] = (
        "FAIL" if schema_errors or report["missing"] else "PASS"
    )
    if declared:
        report["declared"] = declared
    return report


def main():
    argv = sys.argv[1:]
    if argv and argv[0] not in ("graph", "deps") and "--export" in argv:
        argv.insert(0, "graph")
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("graph")
    g.add_argument("--export", required=True)
    g.add_argument("--trigger-target")
    d = sub.add_parser("deps")
    d.add_argument("--export", default=None)
    d.add_argument("--deps", default=None)
    d.add_argument("--build-contract", default=None)
    d.add_argument("--master-files", default=None)
    args = parser.parse_args(argv)
    if args.command == "deps" and not args.export and not args.build_contract:
        report = {
            "wf": "WF-18",
            "verdict": "UNVERIFIED",
            "present": [],
            "missing": [],
            "referenced": 0,
        }
        print(json.dumps(report))
        print("UNVERIFIED: deps needs --export or --build-contract", file=sys.stderr)
        return 2
    try:
        if args.command == "deps" and args.build_contract:
            value = args.build_contract
            if value.endswith(".json") or "/" in value:
                contract_path = os.path.abspath(value)
            else:
                base = args.master_files or os.environ.get("MASTER_FILES_DIR")
                if not base:
                    pointer = os.path.expanduser(
                        "~/.openclaw/.skill-38-master-files-dir")
                    if os.path.isfile(pointer):
                        try:
                            with open(pointer, encoding="utf-8") as handle:
                                base = handle.readline().strip()
                        except OSError:
                            base = None
                if not base:
                    base = os.path.join(os.path.expanduser("~"), ".openclaw")
                contract_path = os.path.abspath(os.path.join(
                    base, "conversation-workflows", value + "--build-contract.json"
                ))

            if not os.path.isfile(contract_path):
                report = {
                    "wf": "WF-18", "verdict": "UNVERIFIED",
                    "present": [], "missing": [], "schema_errors": [],
                    "contract_path": contract_path,
                    "reason": "build contract not found",
                }
                print(json.dumps(report))
                print("UNVERIFIED: build contract not found: " + contract_path, file=sys.stderr)
                return 2

            try:
                contract = read_json(contract_path)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                report = {
                    "wf": "WF-18", "verdict": "UNVERIFIED",
                    "present": [], "missing": [],
                    "schema_errors": ["unparseable_contract"],
                    "contract_path": contract_path,
                }
                print(json.dumps(report))
                print("UNVERIFIED: unparseable build contract: " + contract_path, file=sys.stderr)
                return 2

            if not isinstance(contract, dict):
                report = {
                    "wf": "WF-18", "verdict": "UNVERIFIED",
                    "present": [], "missing": [],
                    "schema_errors": ["unparseable_contract"],
                    "contract_path": contract_path,
                }
                print(json.dumps(report))
                print("UNVERIFIED: unparseable build contract: " + contract_path, file=sys.stderr)
                return 2

            if not args.deps or not os.path.exists(args.deps):
                manifest = {}
                manifest_missing = True
            else:
                manifest = read_json(args.deps)
                if not isinstance(manifest, dict):
                    raise ValueError("invalid manifest")
                manifest_missing = False

            report = validate_build_contract(
                contract, manifest, manifest_missing, contract_path
            )
            print(json.dumps(report))
            print(report["verdict"], file=sys.stderr)
            if report["verdict"] == "UNVERIFIED":
                return 2
            if report["verdict"] == "FAIL":
                return 1
            return 0

        data = read_json(args.export)
        if not isinstance(data, (dict, list)):
            raise ValueError("invalid export top level")
        if args.command == "graph":
            nodes = templates(data)
            if nodes is None or any(not isinstance(n, dict) for n in nodes):
                raise ValueError("missing or invalid template list")
            trigger = args.trigger_target
            if not trigger:
                for item in walk(data):
                    if isinstance(item, dict):
                        trigger = item.get("targetActionId") or item.get("target_action_id")
                        if trigger:
                            break
            report = graph(data, nodes, trigger)
        else:
            refs = dependencies(data)
            if not os.path.exists(args.deps):
                manifest = {}
                manifest_missing = True
            else:
                manifest = read_json(args.deps)
                if not isinstance(manifest, dict):
                    raise ValueError("invalid manifest")
                manifest_missing = False
            present, missing = [], []
            for kind in KINDS:
                for name in refs[kind]:
                    entry = {"kind": kind, "name": name}
                    if manifest_missing or name not in strings(manifest.get(kind)):
                        missing.append(entry)
                    else:
                        present.append(entry)
            report = {
                "wf": "WF-18",
                "verdict": "FAIL" if missing else "PASS",
                "present": present,
                "missing": missing,
                "referenced": sum(map(len, refs.values())),
            }
            if manifest_missing:
                report = {
                    "wf": "WF-18", "verdict": "FAIL",
                    "present": [], "missing": missing,
                    "referenced": sum(map(len, refs.values())),
                    "reason": "dependency manifest not found: " + args.deps,
                }
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        if args.command == "deps" and args.deps and os.path.exists(args.deps):
            try:
                read_json(args.deps)
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            else:
                report = {
                    "wf": "WF-18", "verdict": "UNVERIFIED",
                    "present": [], "missing": [], "referenced": 0,
                }
                print(json.dumps(report))
                print("UNVERIFIED: export unreadable", file=sys.stderr)
                return 2
        report = (
            {
                "wf": "WF-18", "verdict": "UNVERIFIED",
                "present": [], "missing": [], "referenced": 0,
            }
            if args.command == "deps" else
            {
                "wf": "WF-23", "verdict": "UNVERIFIED", "failures": [],
                "nodes": 0, "edges": 0, "root": None, "orphans": 0,
                "branches": 0,
                "unverified": [{"reason": str(exc)}],
            }
        )
        print(json.dumps(report))
        print("UNVERIFIED: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report))
    print(report["verdict"], file=sys.stderr)
    if report["verdict"] == "UNVERIFIED":
        return 2
    if report["verdict"] == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
