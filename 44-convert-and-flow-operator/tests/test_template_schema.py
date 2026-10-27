"""Lock down template schema, graph integrity, manifest freshness, and fail-closed buildability."""
from __future__ import annotations

import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent
_TEMPLATE_ROOT = _REPO_ROOT / "automation-templates"
_MATCHER_DIR = _TEMPLATE_ROOT / "_matcher"
_INDEX_PATH = _MATCHER_DIR / "catalog-index.json"
_MANIFEST_PATH = _MATCHER_DIR / "buildable-templates.json"

if str(_MATCHER_DIR) not in sys.path:
    sys.path.insert(0, str(_MATCHER_DIR))

import automation_matcher as am  # noqa: E402
import buildable  # noqa: E402
import flex  # noqa: E402

# copied from tools/engine/cli_anything/gohighlevel/utils/workflow_builder.py:264-281
VERIFIED_ACTIONS = frozenset([
    "add_contact_tag", "remove_contact_tag", "update_contact_field",
    "create_update_contact", "assign_user", "remove_assigned_user",
    "edit_conversation", "dnd_contact", "add_notes", "task-notification",
    "find_contact", "sms", "email", "call", "voicemail", "messenger", "gmb",
    "internal_notification", "instagram-dm", "ig_interactive_messenger",
    "fb_interactive_messenger", "respond_on_comment", "review_request", "wait",
    "if_else", "goto", "transition", "workflow_split", "workflow_goal",
    "add_to_workflow", "remove_from_workflow", "remove_from_all_workflows",
    "update_custom_value", "drip", "chatgpt", "conversation_ai",
    "create_opportunity", "find_opportunity", "remove_opportunity",
    "webhook", "custom_webhook", "google_sheets", "slack_message", "custom_code",
    "math_operation", "text_formatter", "number_formatter", "datetime_formatter",
    "array_functions", "ivr_gather", "ivr_connect_call",
    "facebook_conversion_api", "stripe_one_time_charge",
    "update_appointment_status", "membership_grant_offer",
    "membership_revoke_offer",
])

EXPECTED_BUILDABLE_KEYS = {
    "launch-a/launch-a-reminder-confirm",
    "launch-a/launch-a-reminder-1wk",
    "launch-a/launch-a-reminder-3d",
    "launch-a/launch-a-reminder-1d",
    "launch-a/launch-a-reminder-morning",
    "launch-a/launch-a-reminder-1h",
    "launch-a/launch-a-reminder-15m",
    "launch-a/launch-a-reminder-live",
    "launch-a/launch-a-replay-and-no-show",
    "launch-a/launch-optin-register-login",
    "launch-a/launch-a-prelaunch-window",
    "launch-ai/customer-replied-conversation-ai",
}


def _template_files() -> list[Path]:
    files = []
    for group_dir in sorted(_TEMPLATE_ROOT.iterdir()):
        if not group_dir.is_dir() or group_dir.name.startswith("_"):
            continue
        for path in sorted(group_dir.glob("*.json")):
            relative = path.relative_to(_TEMPLATE_ROOT).as_posix()
            if relative in {
                "launch-c/automation-build.schema.json",
                "launch-text/text-sets.json",
            }:
                continue
            files.append(path)
    return files


def _branch_targets(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _branch_targets(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _branch_targets(nested)


def _edge_targets(node: dict) -> set[str]:
    targets = set()
    after = node.get("after")
    if isinstance(after, str):
        targets.add(after)
    elif isinstance(after, list):
        targets.update(value for value in after if isinstance(value, str))
    branches = node.get("branches")
    if isinstance(branches, (dict, list, str)):
        targets.update(_branch_targets(branches))
    return targets


def _manifest_from_disk(files: list[Path]) -> dict[str, dict]:
    expected = {}
    for path in files:
        document = json.loads(path.read_text(encoding="utf-8"))
        graph = document.get("build_graph")
        if isinstance(graph, list) and graph:
            group = path.parent.name
            key = f"{group}/{document['id']}"
            expected[key] = {
                "path": path.relative_to(_TEMPLATE_ROOT).as_posix(),
                "kind": document["kind"],
            }
    return expected


def test_template_schema_version_and_kind():
    files = _template_files()
    assert len(files) == 49

    kinds = Counter()
    for path in files:
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document.get("schema_version") == "2.0.0", path
        assert document.get("kind") in {"single_message", "sequence_stack"}, path
        kinds[document["kind"]] += 1

    assert kinds == {"single_message": 17, "sequence_stack": 32}


def test_build_graph_integrity_and_exact_complement():
    files = _template_files()
    graph_count = 0
    prose_count = 0

    for path in files:
        document = json.loads(path.read_text(encoding="utf-8"))
        if "build_graph" not in document:
            prose_count += 1
            continue

        graph_count += 1
        graph = document["build_graph"]
        assert isinstance(graph, list) and graph, path

        ids = [node.get("id") for node in graph]
        assert all(isinstance(node_id, str) and node_id for node_id in ids), path
        assert len(ids) == len(set(ids)), path
        node_ids = set(ids)

        triggers = [node for node in graph if node.get("type") == "trigger"]
        assert len(triggers) == 1, path
        trigger = triggers[0]
        assert "after" not in trigger, path

        successors = {node_id: set() for node_id in node_ids}
        for node in graph:
            node_type = node.get("type")
            assert node_type == "trigger" or node_type in VERIFIED_ACTIONS, (
                path, node.get("id"), node_type
            )
            if node is not trigger:
                assert "after" in node, (path, node.get("id"))

            predecessors = _edge_targets(node)
            assert predecessors <= node_ids, (
                path, node.get("id"), predecessors - node_ids
            )
            for predecessor in predecessors:
                assert predecessor in node_ids
                successors[predecessor].add(node["id"])

        reached = set()
        pending = [trigger["id"]]
        while pending:
            current = pending.pop()
            if current in reached:
                continue
            reached.add(current)
            pending.extend(successors[current] - reached)

        assert reached == node_ids, (path, node_ids - reached)

    assert graph_count == 16
    assert prose_count == 33


def test_buildable_manifest_matches_disk_exactly():
    files = _template_files()
    expected = _manifest_from_disk(files)
    actual = buildable.load_manifest(_MANIFEST_PATH)

    assert len(expected) == 16
    assert len(actual) == 16
    assert set(actual) == set(expected)
    assert actual == expected

    manifest_document = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest_document["count"] == len(expected)


def test_matcher_only_describes_manifest_templates_as_buildable():
    catalog = am.Catalog.from_index(str(_INDEX_PATH))
    manifest = buildable.load_manifest()
    buildable.annotate(catalog.templates, manifest)

    actual_buildable = set()
    for template in catalog.templates:
        key = f"{template['group']}/{template['id']}"
        description = buildable.describe(template)
        assert description["buildable"] is (key in manifest), key
        if description["buildable"]:
            assert isinstance(description["build_graph"], list)
            assert description["build_graph"], key
            actual_buildable.add(key)

    assert len(actual_buildable) == 16
    assert EXPECTED_BUILDABLE_KEYS <= actual_buildable

    prose = catalog.get("soap-opera-sequence", group="sales-close-sequences")
    assert prose is not None
    assert buildable.describe(prose) == {
        "buildable": False,
        "build_graph": None,
    }


def test_describe_fails_closed_when_buildable_graph_is_missing(tmp_path):
    manifest_data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    entry = manifest_data["templates"][0]
    source = _TEMPLATE_ROOT / entry["path"]
    copied_tree = tmp_path / "automation-templates"
    copied_file = copied_tree / entry["path"]
    copied_file.parent.mkdir(parents=True)
    shutil.copy2(source, copied_file)

    copied_manifest = tmp_path / "buildable-templates.json"
    copied_manifest.write_text(
        json.dumps(manifest_data, indent=2),
        encoding="utf-8",
    )

    document = json.loads(copied_file.read_text(encoding="utf-8"))
    del document["build_graph"]
    copied_file.write_text(json.dumps(document, indent=2), encoding="utf-8")

    manifest = buildable.load_manifest(str(copied_manifest))
    template = {
        "id": entry["key"].split("/", 1)[1],
        "group": entry["key"].split("/", 1)[0],
        "sourcePath": str(copied_file),
        "buildable": True,
    }
    assert f"{template['group']}/{template['id']}" in manifest

    with pytest.raises(
        ValueError,
        match=r"buildable template without build_graph: " + str(copied_file),
    ):
        buildable.describe(template)


def test_cli_and_matcher_never_call_a_graph_backed_template_prose_only():
    cat = am.Catalog.from_index(str(_INDEX_PATH))
    buildable.annotate(cat.templates)

    record = cat.get(
        "customer-replied-conversation-ai",
        group="launch-ai",
    )
    assert record is not None
    assert record["buildable"] is True
    assert buildable.graph_for(record)

    decision = am.match_automation(
        "customer replied conversation ai for launch texts",
        cat,
        intent_mode=None,
    )
    assert decision["decision"] == flex.DEC_SUGGEST
    assert decision["matched_template"] == "customer-replied-conversation-ai"

    if decision.get("buildable") is not True:
        # Decision key is plan-derived; CLI now reads record because plan attaches on USE_TEMPLATE.
        assert record["buildable"] is True
    else:
        assert decision["buildable"] is True

    prose = cat.get(
        "soap-opera-sequence",
        group="sales-close-sequences",
    )
    assert prose is not None
    assert prose["buildable"] is False
