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


def test_graph_command_actually_runs_the_identity_checks(tmp_path):
    """The identity checks must be reachable from the gate that runs them.

    `identity_failures()` was implemented and covered by seven passing tests,
    but `graph()` — the function behind the `graph` subcommand and therefore
    behind QC item WF-23 — never called it. A graph with duplicate node ids was
    reported PASS with exit 0 while WF-23's evidence claimed "integrity".
    Testing identity_failures() in isolation could not catch that, so this test
    goes through the command.
    """
    export = tmp_path / "dup.json"
    export.write_text(json.dumps({
        "workflowData": {"templates": [
            {"id": "n1", "type": "sms", "name": "A", "parentKey": None, "next": "n1"},
            {"id": "n1", "type": "end", "name": "A again", "parentKey": "n1"},
        ]}
    }))
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "graph", "--export", str(export)],
        capture_output=True, text=True,
    )
    report = json.loads(result.stdout)
    kinds = {f["kind"] for f in report["failures"]}
    assert result.returncode == 1, (
        "duplicate node ids must fail the graph command; got exit %d %r"
        % (result.returncode, report.get("verdict"))
    )
    assert report["verdict"] == "FAIL"
    assert "DUPLICATE_ID" in kinds, kinds


def _write_export(tmp_path, name, templates):
    export = tmp_path / name
    export.write_text(json.dumps({"workflowData": {"templates": templates}}))
    return export


def _run_export(export):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "graph", "--export", str(export)],
        capture_output=True, text=True,
    )


def test_declared_join_convergence_is_not_cross_branch(tmp_path):
    """A declared join is the confluence, not a member of either arm.

    04-reminder-1d shape: the join is the false-arm target AND the true
    arm's body feeds it. Classifying the join by parentKey arm read that
    legitimate edge as true-arm-into-false-arm and failed every real
    shipped join. A node with attributes.join true belongs to NO branch.
    """
    export = _write_export(tmp_path, "join.json", [
        {"id": "root", "type": "sms", "name": "Root",
         "parentKey": None, "next": "if1"},
        {"id": "if1", "type": "if_else", "name": "Cond", "parentKey": "root",
         "branches": {"true": "then1", "false": "join1"}},
        {"id": "then1", "type": "sms", "name": "Then",
         "parentKey": "if1", "next": "join1"},
        {"id": "join1", "type": "workflow_goal", "name": "Join",
         "parentKey": "if1", "attributes": {"join": True}},
    ])
    result = _run_export(export)
    report = json.loads(result.stdout)
    assert result.returncode == 0, report["failures"]
    assert report["verdict"] == "PASS"
    assert report["failures"] == []


def test_join_seals_branches_above_it(tmp_path):
    """A confluence seals every branch above it: the join's own
    continuation is post-confluence for all higher arms, so it belongs
    to no branch. Without the seal, join -> next reads as
    None-into-arm and every shipped join with a successor fails.
    """
    export = _write_export(tmp_path, "join_next.json", [
        {"id": "root", "type": "sms", "name": "Root",
         "parentKey": None, "next": "if1"},
        {"id": "if1", "type": "if_else", "name": "Cond", "parentKey": "root",
         "branches": {"true": "then1", "false": "join1"}},
        {"id": "then1", "type": "sms", "name": "Then",
         "parentKey": "if1", "next": "join1"},
        {"id": "join1", "type": "workflow_goal", "name": "Join",
         "parentKey": "if1", "next": "after1",
         "attributes": {"join": True}},
        {"id": "after1", "type": "end", "name": "After",
         "parentKey": "join1"},
    ])
    result = _run_export(export)
    report = json.loads(result.stdout)
    assert result.returncode == 0, report["failures"]
    assert report["verdict"] == "PASS"
    assert report["failures"] == []


def test_graph_emits_each_identity_problem_once(tmp_path):
    """graph() must not report the same problem twice.

    graph() seeds its failures from identity_failures(), which emits DANGLING
    (next and branches) and ROOT. Its own body used to append both again, so
    one missing target read as two DANGLINGs and two roots as two ROOTs —
    inflating any count derived from the failures list (e.g. WF-15 orphans).
    """
    from collections import Counter
    export = _write_export(tmp_path, "dup_emit.json", [
        {"id": "a", "type": "sms", "name": "A",
         "parentKey": None, "next": "ghost"},
        {"id": "b", "type": "end", "name": "B", "parentKey": ""},
    ])
    result = _run_export(export)
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["verdict"] == "FAIL"
    counts = Counter(
        (failure["kind"], failure.get("field"), failure.get("target"))
        for failure in report["failures"]
    )
    assert counts[("DANGLING", "next", "ghost")] == 1, report["failures"]
    assert sum(1 for f in report["failures"] if f["kind"] == "ROOT") == 1, (
        report["failures"]
    )
    assert sum(1 for f in report["failures"] if f["kind"] == "DANGLING") == 1, (
        report["failures"]
    )


def test_graph_flags_dangling_branches_dict_value(tmp_path):
    """A ghost reachable only via branches-as-dict must still fail.

    identity_failures() must cover the branches field, not just next: if
    branches handling were removed, nothing else in graph() reports this
    and the gate would PASS a graph pointing at a missing node. Uses a
    non-branch node type so no MALFORMED_BRANCH/UNWIRED_BRANCH noise.
    """
    export = _write_export(tmp_path, "branches_dict.json", [
        {"id": "a", "type": "sms", "name": "A",
         "parentKey": None, "branches": {"true": "ghost"}},
        {"id": "z", "type": "end", "name": "Z", "parentKey": "a"},
    ])
    result = _run_export(export)
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["verdict"] == "FAIL"
    dangling = [f for f in report["failures"] if f["kind"] == "DANGLING"]
    assert len(dangling) == 1, report["failures"]
    assert dangling[0]["node_id"] == "a"
    assert dangling[0]["field"] == "branches"
    assert dangling[0]["target"] == "ghost"


def test_graph_flags_dangling_branches_list_value(tmp_path):
    """A ghost reachable only via a branches list value must still fail.

    authored_targets() recurses into dict values AND list items: a
    {"true": ["ghost"]} shape must emit exactly one branches DANGLING. If
    branches coverage regressed to str-only dict values, this goes red
    while the dict-str case above stays green.
    """
    export = _write_export(tmp_path, "branches_list.json", [
        {"id": "a", "type": "sms", "name": "A",
         "parentKey": None, "branches": {"true": ["ghost"]}},
        {"id": "z", "type": "end", "name": "Z", "parentKey": "a"},
    ])
    result = _run_export(export)
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["verdict"] == "FAIL"
    dangling = [f for f in report["failures"] if f["kind"] == "DANGLING"]
    assert len(dangling) == 1, report["failures"]
    assert dangling[0]["node_id"] == "a"
    assert dangling[0]["field"] == "branches"
    assert dangling[0]["target"] == "ghost"


def test_graph_reports_shared_next_and_branches_target_once(tmp_path):
    """One missing id via both next and branches is one report, not two.

    identity_failures() dedupes on (node_id, target): the same ghost
    authored in two fields must not read as two DANGLINGs. This is the
    double-emit defect Step B removes — it must not return through the
    new branches coverage.
    """
    export = _write_export(tmp_path, "branches_both.json", [
        {"id": "a", "type": "sms", "name": "A",
         "parentKey": None, "next": "ghost",
         "branches": {"true": "ghost"}},
        {"id": "z", "type": "end", "name": "Z", "parentKey": "a"},
    ])
    result = _run_export(export)
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["verdict"] == "FAIL"
    dangling = [f for f in report["failures"] if f["kind"] == "DANGLING"]
    assert len(dangling) == 1, report["failures"]
    assert dangling[0]["node_id"] == "a"
    assert dangling[0]["target"] == "ghost"
