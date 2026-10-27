import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
VALIDATOR = ROOT.parent / "tools" / "validate_graph.py"
FIXTURES = ROOT / "fixtures" / "graph"


def run_graph(name):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "graph", "--export",
         str(FIXTURES / name)], capture_output=True, text=True
    )


@pytest.mark.parametrize("fixture,code,verdict,kind", [
    ("linear_ok.json", 0, "PASS", None),
    ("orphan_node.json", 1, "FAIL", "ORPHAN"),
    ("unwired_branch.json", 1, "FAIL", "UNWIRED_BRANCH"),
    ("dangling_next.json", 1, "FAIL", "DANGLING"),
    ("unparseable.json", 2, "UNVERIFIED", None),
    ("cross_branch.json", 1, "FAIL", "CROSS_BRANCH"),
    ("unterminated.json", 1, "FAIL", "UNTERMINATED"),
    ("cycle_illegal.json", 1, "FAIL", "CYCLE"),
    ("loop_legal.json", 0, "PASS", None),
    ("cycle_unreached_loop.json", 1, "FAIL", "CYCLE"),
])
def test_graph(fixture, code, verdict, kind):
    result = run_graph(fixture)
    report = json.loads(result.stdout)
    assert result.returncode == code
    assert report["verdict"] == verdict
    if fixture in ("linear_ok.json", "unparseable.json", "loop_legal.json"):
        assert report["failures"] == []
    if kind:
        failures = [f for f in report["failures"] if f["kind"] == kind]
        assert failures
        if kind == "ORPHAN":
            assert failures[0]["node_id"] == "n3"
        if kind == "UNWIRED_BRANCH":
            assert failures[0]["targets"] == 1
        if kind == "CROSS_BRANCH":
            assert failures[0]["node_id"] == "then1"
            assert failures[0]["target"] == "else1"
        if fixture == "unterminated.json":
            assert failures[0]["node_id"] == "u3"
        if fixture == "cycle_illegal.json":
            assert failures[0]["cycle"]
        if fixture == "cycle_unreached_loop.json":
            kinds = {failure["kind"] for failure in report["failures"]}
            assert "CYCLE" in kinds
            assert "ORPHAN" in kinds


def test_unverified_is_never_pass():
    report = json.loads(run_graph("unparseable.json").stdout)
    assert report["verdict"] != "PASS"


def test_deps(tmp_path):
    export = tmp_path / "export.json"
    export.write_text(json.dumps({"templates": [
        {"id": "n1", "tag": "ZHC-demo", "pipelineId": "PIPE-1"}
    ]}))
    manifest = tmp_path / "deps.json"

    def run(path):
        return subprocess.run(
            [sys.executable, str(VALIDATOR), "deps", "--export",
             str(export), "--deps", str(path)],
            capture_output=True, text=True
        )

    manifest.write_text(json.dumps({"tags": ["ZHC-demo"], "pipelines": ["PIPE-1"]}))
    result = run(manifest)
    assert result.returncode == 0
    assert json.loads(result.stdout)["verdict"] == "PASS"

    manifest.write_text(json.dumps({"tags": [], "pipelines": ["PIPE-1"]}))
    result = run(manifest)
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert {"kind": "tags", "name": "ZHC-demo"} in report["missing"]

    result = run(tmp_path / "missing.json")
    assert result.returncode == 1
    assert json.loads(result.stdout)["verdict"] == "FAIL"


def test_failure_wins_over_unverified(tmp_path):
    export = tmp_path / "export.json"
    export.write_text(json.dumps({"templates": [
        {"id": "r1", "type": "tag", "parentKey": None, "next": "b1"},
        {"id": "b1", "type": "if_else", "parentKey": "r1"},
        {"id": "n3", "type": "wait", "parentKey": "r1", "next": None},
    ]}))
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "graph", "--export", str(export)],
        capture_output=True, text=True,
    )
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["verdict"] == "FAIL"
    assert report["orphans"] == 1
    assert report["unverified"]


def test_invalid_contract_with_missing_manifest_fails(tmp_path):
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({
        "playbook_structure_hash": "",
        "tags": {"applies": []},
        "fields": [],
        "calendars": [],
    }))
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "deps", "--build-contract",
         str(contract)],
        capture_output=True, text=True,
    )
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["verdict"] == "FAIL"
    assert report["schema_errors"]


def load_identity_failures():
    spec = importlib.util.spec_from_file_location("validate_graph", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.identity_failures


def test_identity_failures_duplicate_id():
    identity_failures = load_identity_failures()
    failures = identity_failures([
        {"id": "a", "parentKey": None},
        {"id": "a", "parentKey": "a"},
    ])
    assert any(f["kind"] == "DUPLICATE_ID" for f in failures)


def test_identity_failures_dangling_next():
    identity_failures = load_identity_failures()
    failures = identity_failures([
        {"id": "a", "parentKey": None, "next": "missing"},
    ])
    assert any(
        f["kind"] == "DANGLING" and f["field"] == "next"
        for f in failures
    )


def test_identity_failures_malformed_if_else():
    identity_failures = load_identity_failures()
    failures = identity_failures([
        {"id": "a", "type": "if_else", "parentKey": None,
         "branches": {"yes": "b"}},
        {"id": "b", "parentKey": "a"},
    ])
    assert sum(f["kind"] == "MALFORMED_BRANCH" for f in failures) == 1


def test_identity_failures_two_roots():
    identity_failures = load_identity_failures()
    failures = identity_failures([
        {"id": "a", "parentKey": None},
        {"id": "b", "parentKey": ""},
    ])
    assert any(f["kind"] == "ROOT" for f in failures)


def test_identity_failures_invalid_parent():
    identity_failures = load_identity_failures()
    failures = identity_failures([
        {"id": "a", "parentKey": "missing"},
    ])
    assert any(f["kind"] == "PARENT_INVALID" for f in failures)


def test_identity_failures_parent_cycle():
    identity_failures = load_identity_failures()
    failures = identity_failures([
        {"id": "a", "parentKey": "b"},
        {"id": "b", "parentKey": "a"},
    ])
    assert any(f["kind"] == "PARENT_CYCLE" for f in failures)


def test_identity_failures_clean_linear_graph():
    identity_failures = load_identity_failures()
    assert identity_failures([
        {"id": "a", "parentKey": None, "next": "b"},
        {"id": "b", "parentKey": "a", "next": "c"},
        {"id": "c", "parentKey": "b"},
    ]) == []
