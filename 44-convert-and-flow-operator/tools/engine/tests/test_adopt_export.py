"""SWB-081: ``caf workflows adopt`` gives an existing DRAFT workflow an honest export and delivery row.

Fail-before: nothing in Skill 44 could export a workflow it did not build (``build
--from-automation-build`` refuses an SMS-only unit with no_buildable_workflow and a browser-built
if/else with MALFORMED_BRANCH), so a live workflow could never be delivered. Pass-after: the adopt path
reads the saved graph, validates it with Skill 44's own validator, records its REAL hash with
``produced_by: adopt``, and writes a delivery row only with a signed passing QC of that exact graph.
Negative twins: graph edited after QC, failed validation, missing QC, failing QC, wrong unit key.

Synthetic-local only. Run:
    python3 -m pytest 44-convert-and-flow-operator/tools/engine/tests/test_adopt_export.py -q
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ENGINE = Path(__file__).resolve().parents[1]
SKILL = ENGINE.parents[1]
VALIDATOR = SKILL / "tools" / "validate_graph.py"
sys.path.insert(0, str(ENGINE))

from cli_anything.gohighlevel.utils import adopt_export  # noqa: E402
from cli_anything.gohighlevel.utils.workflow_builder import graph_hash  # noqa: E402

TEMPLATES = [
    {"id": "w1", "type": "wait", "name": "Wait", "parentKey": None, "next": "e1"},
    {"id": "e1", "type": "email", "name": "Email 1", "parentKey": "w1", "next": "g1"},
    {"id": "g1", "type": "workflow_goal", "name": "Goal", "parentKey": "e1", "next": None},
]
ORPHANED = TEMPLATES[:2] + [{"id": "x9", "type": "end", "name": "Lost", "parentKey": None}]
UNIT = "black-friday-2026/auto_opt_in"


def live(wid, templates=TEMPLATES, status="draft", name="wf"):
    return {"id": wid, "name": name + "-" + wid, "status": status,
            "workflowData": {"templates": copy.deepcopy(templates)}}


def reader(docs):
    return lambda wid: docs.get(wid)


def passing_qc(wid, ghash, **override):
    doc = {"workflow_id": wid, "overall_mechanical": "PASS", "exit_gate": "PASS", "exit_code": 0,
           "plan_mode_gate": {"status": "PASS"}, "graph_hash": ghash}
    doc.update(override)
    return doc


def put_qc(qc_dir, doc):
    Path(qc_dir).mkdir(parents=True, exist_ok=True)
    (Path(qc_dir) / ("qc-%s.json" % doc["workflow_id"])).write_text(json.dumps(doc))


def adopt(tmp_path, docs, wids, unit=UNIT):
    return adopt_export.adopt_unit(unit, wids, reader(docs), graph_hash, tmp_path / "out")


def test_adopt_records_the_real_graph_hash_and_an_honest_producer(tmp_path):
    path, members, reasons = adopt(tmp_path, {"wf-a": live("wf-a")}, ["wf-a"])
    assert reasons == []
    export = json.loads(path.read_text())
    assert export["contract"] == "skill44.workflow-export.v1"
    assert export["produced_by"] == "adopt" != "caf workflows build --from-automation-build"
    assert export["status"] == "draft" and export["unit_key"] == UNIT
    assert export["expected_graph_hash"] == graph_hash(TEMPLATES) == members[0]["graph_hash"]
    assert export["workflow_id"] == "wf-a" and export["templates"] == TEMPLATES


def test_the_validator_hash_command_and_the_builder_hash_agree(tmp_path):
    for graph in (TEMPLATES, [dict(t, order=i, attributes={"b": 1, "a": "é"}) for i, t in enumerate(TEMPLATES)]):
        (tmp_path / "g.json").write_text(json.dumps({"workflowData": {"templates": graph}}))
        done = subprocess.run([sys.executable, "-I", str(VALIDATOR), "hash", "--export", str(tmp_path / "g.json")],
                              capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        assert done.stdout.strip() == graph_hash(graph)


def test_hash_command_refuses_an_export_with_no_graph(tmp_path):
    (tmp_path / "g.json").write_text(json.dumps({"nothing": 1}))
    done = subprocess.run([sys.executable, "-I", str(VALIDATOR), "hash", "--export", str(tmp_path / "g.json")],
                          capture_output=True, text=True)
    assert done.returncode == 2 and done.stdout == ""


@pytest.mark.parametrize("docs,why", [
    ({"wf-a": live("wf-a", status="archived")}, "not a draft or published"),
    ({"wf-a": live("wf-a", status=None)}, "not a draft or published"),
    ({"wf-a": live("wf-a", templates=ORPHANED)}, "saved graph refused"),
    ({}, "cannot be read back"),
    ({"wf-a": live("wf-other")}, "cannot be read back"),
    ({"wf-a": live("wf-a", templates=[])}, "no saved graph"),
])
def test_a_workflow_that_is_not_a_passing_draft_is_refused_by_name(tmp_path, docs, why):
    if "wf-other" in json.dumps(docs):
        docs = {"wf-a": live("wf-other")}
    path, members, reasons = adopt(tmp_path, docs, ["wf-a"])
    assert path is None and members == []
    assert len(reasons) == 1 and "wf-a" in reasons[0]
    if why != "cannot be read back":
        assert why in reasons[0]
    assert not (tmp_path / "out").exists()


def test_a_published_workflow_is_adopted_with_its_true_status(tmp_path):
    path, members, reasons = adopt(tmp_path, {"wf-a": live("wf-a", status="published")}, ["wf-a"])
    assert reasons == []
    export = json.loads(path.read_text())
    assert export["status"] == "published" and export["workflows"][0]["status"] == "published"


@pytest.mark.parametrize("unit", ["auto_opt_in", "a/b/c", "/auto", "launch/"])
def test_a_wrong_unit_key_is_refused(tmp_path, unit):
    path, _members, reasons = adopt(tmp_path, {"wf-a": live("wf-a")}, ["wf-a"], unit=unit)
    assert path is None and "unit key" in reasons[0]


def row_for(tmp_path, members, export, qc_dir):
    return adopt_export.adopt_row(export, members, qc_dir, tmp_path, launch_id="black-friday-2026",
                                  unit_id="auto_opt_in", plan_sha256="p" * 64)


def test_a_row_needs_a_passing_signed_qc_of_this_exact_graph(tmp_path):
    export, members, _ = adopt(tmp_path, {"wf-a": live("wf-a"), "wf-b": live("wf-b")}, ["wf-a", "wf-b"])
    qc_dir = tmp_path / "out"
    for m in members:
        put_qc(qc_dir, passing_qc(m["workflow_id"], m["graph_hash"]))
    row, reasons = row_for(tmp_path, members, export, qc_dir)
    assert reasons == []
    assert row["state"] == "complete"
    assert row["lane_validation"] == {"lane": "skill44", "contract": "skill44.workflow-export.v1",
                                      "state": "passed"}
    assert [a["role"] for a in row["artifacts"]] == ["workflow_export", "qc", "qc"]
    assert [Path(a["path"]).name for a in row["artifacts"][1:]] == ["qc-wf-a.json", "qc-wf-b.json"]
    assert row["request"] == {"launch_id": "black-friday-2026", "unit_id": "auto_opt_in",
                              "plan_sha256": "p" * 64}


def test_negative_twin_graph_changed_after_qc_gets_no_row(tmp_path):
    export, members, _ = adopt(tmp_path, {"wf-a": live("wf-a")}, ["wf-a"])
    edited = copy.deepcopy(TEMPLATES)
    edited[1]["name"] = "Email 1 (edited after QC)"
    put_qc(tmp_path / "out", passing_qc("wf-a", graph_hash(edited)))  # QC graded the OLD graph
    row, reasons = row_for(tmp_path, members, export, tmp_path / "out")
    assert row is None and "edited since QC" in reasons[0]


def test_negative_twin_missing_qc_gets_no_row(tmp_path):
    export, members, _ = adopt(tmp_path, {"wf-a": live("wf-a")}, ["wf-a"])
    row, reasons = row_for(tmp_path, members, export, tmp_path / "out")
    assert row is None and "qc-wf-a.json" in reasons[0]


@pytest.mark.parametrize("override", [{"exit_code": 1}, {"exit_gate": "FAIL"}, {"overall_mechanical": "FAIL"},
                                      {"plan_mode_gate": {"status": "FAIL"}}, {"workflow_id": "wf-zzz"},
                                      {"exit_code": "0"}, {"graph_hash": ""}])
def test_negative_twin_a_failing_or_foreign_qc_gets_no_row(tmp_path, override):
    export, members, _ = adopt(tmp_path, {"wf-a": live("wf-a")}, ["wf-a"])
    qc = passing_qc("wf-a", members[0]["graph_hash"], **override)
    (tmp_path / "out" / "qc-wf-a.json").write_text(json.dumps(qc))
    row, reasons = row_for(tmp_path, members, export, tmp_path / "out")
    assert row is None and "did not pass" in reasons[0]


def test_one_member_without_a_qc_refuses_the_whole_unit(tmp_path):
    export, members, _ = adopt(tmp_path, {"wf-a": live("wf-a"), "wf-b": live("wf-b")}, ["wf-a", "wf-b"])
    put_qc(tmp_path / "out", passing_qc("wf-a", members[0]["graph_hash"]))
    row, reasons = row_for(tmp_path, members, export, tmp_path / "out")
    assert row is None and "wf-b" in reasons[0]


def test_cli_adopt_refuses_without_the_qc_and_writes_nothing_to_the_provider(tmp_path, monkeypatch):
    pytest.importorskip("click")
    from click.testing import CliRunner
    from cli_anything.gohighlevel import gohighlevel_cli as cli_mod
    from cli_anything.gohighlevel.utils import workflow_builder as wb

    for key, value in {"CAF_DATA_DIR": str(tmp_path / "data"), "CAF_ALLOWED_LOCATION_IDS": "loc1",
                       "GHL_API_KEY": "fake", "GHL_LOCATION_ID": "loc1"}.items():
        monkeypatch.setenv(key, value)
    plan = tmp_path / "plan.json"
    plan.write_text("{}")
    out = tmp_path / "run" / "skill83"
    with patch.object(cli_mod, "_get_internal_client", lambda ctx: object()), \
            patch.object(wb, "_readback_workflow", lambda client, loc, wid: live(wid)):
        args = ["--json", "--location-id", "loc1", "workflows", "adopt", "--unit", UNIT,
                "--workflow-id", "wf-a", "--out-dir", str(out)]
        done = CliRunner().invoke(cli_mod.cli, args)
        assert done.exit_code == 0, done.output
        report = json.loads(done.output)
        assert report["workflows"][0]["graph_hash"] == graph_hash(TEMPLATES) and report["row"] is None
        # With a row requested but no QC staged: refused, exit 1, no deliveries file.
        qc_dir = tmp_path / "qc"
        qc_dir.mkdir()
        deliveries = out / "deliveries.json"
        refused = CliRunner().invoke(cli_mod.cli, args + ["--qc-dir", str(qc_dir), "--deliveries-out",
                                                           str(deliveries), "--launch-plan", str(plan)])
        assert refused.exit_code == 1 and not deliveries.exists()
        put_qc(qc_dir, passing_qc("wf-a", graph_hash(TEMPLATES)))
        ok = CliRunner().invoke(cli_mod.cli, args + ["--qc-dir", str(qc_dir), "--deliveries-out",
                                                      str(deliveries), "--launch-plan", str(plan)])
        assert ok.exit_code == 1, "the QC file lives outside the run directory tree: refused by name"
        put_qc(out, passing_qc("wf-a", graph_hash(TEMPLATES)))
        ok = CliRunner().invoke(cli_mod.cli, args + ["--qc-dir", str(out), "--deliveries-out",
                                                      str(deliveries), "--launch-plan", str(plan)])
        assert ok.exit_code == 0, ok.output
        assert json.loads(deliveries.read_text())["auto_opt_in"]["state"] == "complete"
