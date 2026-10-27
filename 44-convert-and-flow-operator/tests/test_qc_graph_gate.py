import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
QC_SCRIPT = ROOT / "qc-built-workflow.sh"
ORPHANED = ROOT / "tests/fixtures/graph/orphaned_export.json"


def _linear_export():
    return {
        "targetActionId": "n1",
        "workflowData": {
            "templates": [
                {
                    "id": "n1",
                    "type": "sms",
                    "name": "Send",
                    "parentKey": None,
                    "next": "n2",
                    "attributes": {
                        "body": "Test message",
                        "fromNumber": "+15555550100",
                    },
                },
                {
                    "id": "n2",
                    "type": "end",
                    "name": "Finish",
                    "parentKey": "n1",
                    "next": None,
                },
            ]
        },
    }


def _setup(tmp_path, export):
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fixture = tmp_path / "export.json"
    fixture.write_text(json.dumps(export), encoding="utf-8")
    caf = bin_dir / "caf"
    caf.write_text(
        '#!/bin/bash\n'
        'set -euo pipefail\n'
        '[[ "$1" == workflows && "$2" == export ]]\n'
        'while (($#)); do\n'
        '  if [[ "$1" == --out ]]; then cp "$QC_FIXTURE" "$2"; exit 0; fi\n'
        '  shift\n'
        'done\n'
        'exit 2\n',
        encoding="utf-8",
    )
    caf.chmod(0o755)
    env = os.environ.copy()
    env.update(
        PATH=str(bin_dir) + os.pathsep + env.get("PATH", ""),
        HOME=str(home),
        OPENCLAW_PLATFORM="mac",
        QC_FIXTURE=str(fixture),
    )
    return env


def _run(tmp_path, export, args):
    env = _setup(tmp_path, export)
    return subprocess.run(
        ["bash", str(QC_SCRIPT)] + args,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _items(result):
    assert result.stdout, result.stderr
    return json.loads(result.stdout)["items"]


def _manifest(tmp_path, value):
    path = tmp_path / "deps.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def test_orphaned_export_fails_graph_and_linkage_without_manifest(tmp_path):
    result = _run(tmp_path, json.loads(ORPHANED.read_text()), ["WFTEST009", "--json"])
    items = _items(result)
    assert result.returncode == 1
    assert items["WF-23"]["status"] == "FAIL"
    assert items["WF-15"]["status"] == "FAIL"
    evidence = (items["WF-15"]["observed"] + items["WF-15"]["notes"]).upper()
    assert "ORPHAN" in evidence or "UNWIRED_BRANCH" in evidence
    assert items["WF-18"]["status"] == "FAIL"


def test_linear_export_passes_graph_and_linkage(tmp_path):
    manifest = _manifest(tmp_path, {})
    result = _run(
        tmp_path, _linear_export(),
        ["WFTEST009", "--deps", manifest, "--json"],
    )
    items = _items(result)
    assert items["WF-15"]["status"] == "PASS"
    assert items["WF-23"]["status"] == "PASS"
    observed = items["WF-15"]["observed"]
    assert "nodes" in observed and "root=" in observed


def test_missing_dependency_fails_manifest_gate(tmp_path):
    export = _linear_export()
    export["workflowData"]["templates"][0]["attributes"]["tags"] = ["ZHC-missing"]
    manifest = _manifest(tmp_path, {})
    result = _run(
        tmp_path, export,
        ["WFTEST009", "--deps", manifest, "--json"],
    )
    item = _items(result)["WF-18"]
    assert item["status"] == "FAIL"
    assert "ZHC-missing" in item["observed"] + item["notes"]


def test_declared_dependency_passes_manifest_gate(tmp_path):
    export = _linear_export()
    export["workflowData"]["templates"][0]["attributes"]["tags"] = ["ZHC-missing"]
    manifest = _manifest(tmp_path, {"tags": ["ZHC-missing"]})
    result = _run(
        tmp_path, export,
        ["WFTEST009", "--deps", manifest, "--json"],
    )
    assert _items(result)["WF-18"]["status"] == "PASS"


def _branching_export():
    """Two if_else nodes, both arms wired, every arm reaching the goal.

    This is the case that matters for rubric D4: the graph CONTAINS branches,
    so D4 must not be scored N/A, while nothing is actually broken.
    """
    return {
        "targetActionId": "n1",
        "workflowData": {
            "templates": [
                {"id": "n1", "type": "if_else", "name": "First",
                 "parentKey": None, "branches": {"true": "n2", "false": "n3"}},
                {"id": "n2", "type": "if_else", "name": "Second",
                 "parentKey": "n1", "branches": {"true": "n4", "false": "n5"}},
                {"id": "n3", "type": "workflow_goal", "name": "Goal A",
                 "parentKey": "n1"},
                {"id": "n4", "type": "workflow_goal", "name": "Goal B",
                 "parentKey": "n2"},
                {"id": "n5", "type": "workflow_goal", "name": "Goal C",
                 "parentKey": "n2"},
            ]
        },
    }


def test_wf23_reports_branch_count_separately_from_unwired(tmp_path):
    """`branches=` counts branch nodes PRESENT; `unwired=` counts broken ones.

    Deriving the rubric's D4 N/A rule from `unwired` would hand a free 10 to
    this graph, because nothing here is unwired.
    """
    manifest = _manifest(tmp_path, {})
    result = _run(
        tmp_path, _branching_export(),
        ["WFTEST009", "--deps", manifest, "--json"],
    )
    items = _items(result)
    wf23 = items["WF-23"]
    assert wf23["status"] == "PASS", wf23["observed"] + wf23["notes"]
    observed = wf23["observed"]
    assert "branches=2" in observed, observed
    assert "unwired=0" in observed, observed


def test_wf23_fails_when_branch_count_is_absent(tmp_path):
    """A validator report without `branches` must FAIL, not default to zero."""
    export = _branching_export()
    env = _setup(tmp_path, export)
    stub = tmp_path / "stub_validator.py"
    stub.write_text(
        "import json, sys\n"
        "print(json.dumps({'wf': 'WF-23', 'verdict': 'PASS', 'failures': [],\n"
        "                  'nodes': 4, 'edges': 4, 'root': 'n1', 'orphans': 0,\n"
        "                  'unverified': []}))\n",
        encoding="utf-8",
    )
    env["QC_GRAPH_VALIDATOR"] = str(stub)
    manifest = _manifest(tmp_path, {})
    result = subprocess.run(
        ["bash", str(QC_SCRIPT), "WFTEST009", "--deps", manifest, "--json"],
        env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    wf23 = _items(result)["WF-23"]
    assert wf23["status"] == "FAIL", (
        "a report missing `branches` must fail closed; got %r" % (wf23,)
    )
    assert "branches" in wf23["observed"] + wf23["notes"]


def _dispatch_validator(tmp_path, graph_report, deps_report):
    """Stub that answers the `graph` and `deps` subcommands separately."""
    stub = tmp_path / "dispatch_validator.py"
    stub.write_text(
        "import json, sys\n"
        "GRAPH = json.loads(%r)\n"
        "DEPS = json.loads(%r)\n"
        "cmd = sys.argv[1] if len(sys.argv) > 1 else 'graph'\n"
        "print(json.dumps(DEPS if cmd == 'deps' else GRAPH))\n" % (
            json.dumps(graph_report), json.dumps(deps_report)
        ),
        encoding="utf-8",
    )
    return str(stub)


def test_wf18_pass_label_cannot_clear_a_measured_missing_list(tmp_path):
    """A deps report claiming PASS while listing a missing object is a
    contradiction: the measured list governs, never the label."""
    graph = {
        "wf": "WF-23", "verdict": "PASS", "failures": [],
        "nodes": 2, "edges": 1, "root": "n1", "orphans": 0, "branches": 0,
        "unverified": [],
    }
    deps = {
        "wf": "WF-18", "verdict": "PASS", "referenced": 1,
        "missing": [{"kind": "tags", "name": "ZHC-lie"}],
    }
    export = _linear_export()
    env = _setup(tmp_path, export)
    env["QC_GRAPH_VALIDATOR"] = _dispatch_validator(tmp_path, graph, deps)
    manifest = _manifest(tmp_path, {"tags": ["ZHC-lie"]})
    result = subprocess.run(
        ["bash", str(QC_SCRIPT), "WFTEST009", "--deps", manifest, "--json"],
        env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    wf18 = _items(result)["WF-18"]
    assert wf18["status"] == "FAIL", (
        "verdict=PASS with a non-empty missing list must FAIL; got %r" % (wf18,)
    )
    assert "ZHC-lie" in wf18["observed"] + wf18["notes"], wf18


def test_wf18_fails_when_report_omits_its_own_fields(tmp_path):
    """A dependency report that omits `referenced` must not default to zero.

    Absent field -> 0 used to read as "nothing referenced, everything present",
    which is a pass granted for proving nothing.
    """
    graph = {
        "wf": "WF-23", "verdict": "PASS", "failures": [],
        "nodes": 2, "edges": 1, "root": "n1", "orphans": 0, "branches": 0,
        "unverified": [],
    }
    deps = {"verdict": "PASS", "missing": []}          # no `referenced`
    env = _setup(tmp_path, _linear_export())
    env["QC_GRAPH_VALIDATOR"] = _dispatch_validator(tmp_path, graph, deps)
    manifest = _manifest(tmp_path, {})
    result = subprocess.run(
        ["bash", str(QC_SCRIPT), "WFTEST009", "--deps", manifest, "--json"],
        env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    wf18 = _items(result)["WF-18"]
    assert wf18["status"] == "FAIL", (
        "a report with no `referenced` field must fail, not default to a pass; "
        "got %r" % (wf18,)
    )
    assert "malformed" in (wf18["observed"] + wf18["notes"]).lower(), wf18


def test_wf24_fails_when_validator_and_local_root_disagree(tmp_path):
    """WF-24 must not certify a trigger against a root the validator rejected."""
    graph = {
        "wf": "WF-23", "verdict": "PASS", "failures": [],
        "nodes": 2, "edges": 1, "root": "somewhere-else", "orphans": 0,
        "branches": 0, "unverified": [],
    }
    deps = {"wf": "WF-18", "verdict": "PASS", "referenced": 0, "missing": []}
    export = _linear_export()          # local root is n1
    export["triggers"] = [
        {"id": "T1", "type": "form_submitted", "targetActionId": "n1"}
    ]
    env = _setup(tmp_path, export)
    env["QC_GRAPH_VALIDATOR"] = _dispatch_validator(tmp_path, graph, deps)
    manifest = _manifest(tmp_path, {})
    result = subprocess.run(
        ["bash", str(QC_SCRIPT), "WFTEST009", "--deps", manifest, "--json"],
        env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    wf24 = _items(result)["WF-24"]
    assert wf24["status"] == "FAIL", (
        "a trigger matching only the locally inferred root must not pass when "
        "the validator names a different root; got %r" % (wf24,)
    )
    assert "root_disagrees_with_validator" in (
        wf24["observed"] + wf24["notes"]
    ), wf24


def test_wf23_fails_when_pass_report_carries_unverified_entries(tmp_path):
    """"Could not verify" must never be recorded as a pass.

    The verdict expression in the validator makes PASS imply no unverified
    nodes, but the shell trusts the report it is handed. A report claiming PASS
    while listing an unverified node was recorded as PASS/PASS with rc 0.
    """
    graph = {
        "wf": "WF-23", "verdict": "PASS", "failures": [],
        "nodes": 2, "edges": 1, "root": "n1", "orphans": 0, "branches": 0,
        "unverified": [{"node_id": "b1", "reason": "branch_targets_not_exposed"}],
    }
    deps = {"wf": "WF-18", "verdict": "PASS", "referenced": 0, "missing": []}
    export = _linear_export()
    export["triggers"] = [
        {"id": "T1", "type": "form_submitted", "targetActionId": "n1"}
    ]
    env = _setup(tmp_path, export)
    env["QC_GRAPH_VALIDATOR"] = _dispatch_validator(tmp_path, graph, deps)
    manifest = _manifest(tmp_path, {})
    result = subprocess.run(
        ["bash", str(QC_SCRIPT), "WFTEST009", "--deps", manifest, "--json"],
        env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    items = _items(result)
    assert items["WF-23"]["status"] == "FAIL", (
        "verdict=PASS with an unverified entry must fail; got %r" % (items["WF-23"],)
    )
    assert "pass_with_unverified" in items["WF-23"]["observed"], items["WF-23"]
