"""Issues 64 + 1 (44 side): Skill 44 writes the export object and the deliveries file Skill 83 reads.

Fail-before: no Skill 44 code wrote ``produced_by`` or the ``skill44.workflow-export.v1`` contract
id, and nothing produced a deliveries file, so Skill 83 refused every real automation unit
(AF-LAUNCH-UNIT-AUTOMATION). Pass-after: a unit that built and read back clean is exported, Skill 83's
own ``automation_violations`` accepts the export, and a hand-made object is still refused.

Synthetic-local only (a fake provider client, no network). Run:
    python3 -m pytest 44-convert-and-flow-operator/tools/engine/tests/test_export_object.py -q
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

ENGINE = Path(__file__).resolve().parents[1]
SKILL = ENGINE.parents[1]
REPO = SKILL.parent
sys.path.insert(0, str(ENGINE))

from cli_anything.gohighlevel import gohighlevel_cli as cli_mod  # noqa: E402
from cli_anything.gohighlevel.gohighlevel_cli import cli  # noqa: E402
from cli_anything.gohighlevel.utils import delivery_export  # noqa: E402
from cli_anything.gohighlevel.utils.workflow_builder import BuildJournal, graph_hash  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# The same reader output and fake provider the other build tests use: one source each.
_l07 = _load("export_obj_l07", ENGINE / "tests" / "test_workflow_builder_l07.py")
LOC = _l07.LOC  # the fake provider answers on its own location id

# A saved graph that satisfies Skill 44's own WF-23 validator (root, reachable, terminated).
TEMPLATES = [
    {"id": "w1", "type": "wait", "name": "Wait", "parentKey": None, "next": "e1"},
    {"id": "e1", "type": "email", "name": "Email 1", "parentKey": "w1", "next": "g1"},
    {"id": "g1", "type": "workflow_goal", "name": "Goal", "parentKey": "e1", "next": None},
]
UNIT_HASH = "a" * 64


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    for key, value in {"CAF_DATA_DIR": str(tmp_path / "data"), "CAF_ALLOWED_LOCATION_IDS": LOC,
                       "CAF_APPROVAL_TOKEN": "t", "GHL_API_KEY": "fake-pit-token",
                       "GHL_LOCATION_ID": LOC}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CAF_DRY_RUN", raising=False)
    monkeypatch.delenv("CAF_BUILD_JOURNAL", raising=False)
    # WP-07 (issue 47): a real build needs a PLAN MODE run file the approval flow confirms. These tests give the real gate a real
    # plan-mode.json and a stub authority (same shape as test_build_requires_plan_mode.py); the gate itself is not patched out.
    plan_mode = tmp_path / "plan-mode.json"
    plan_mode.write_text(json.dumps({"approval_id": "appr-good-0001", "plan_hash": "abcd1234",
                                     "publish_intent": "DRAFT", "re_entry": "ONCE", "build_model": "build-model-a"}))

    class Authority:
        @staticmethod
        def verify(approval_id, kind, plan_hash, scope, **kw):
            assert (approval_id, kind, plan_hash) == ("appr-good-0001", "launch_plan_build", "abcd1234")
            assert set(scope) <= {"publish:DRAFT", "reentry:ONCE"}
            return {"ok": True}

    monkeypatch.setattr(cli_mod, "_approval_record", lambda: Authority)
    real_invoke = CliRunner.invoke

    def invoke(self, command, args=None, **kw):
        args = list(args or [])
        if "--from-automation-build" in args and "--dry-run" not in args and "--plan-mode-file" not in args:
            args += ["--plan-mode-file", str(plan_mode)]
        return real_invoke(self, command, args, **kw)

    monkeypatch.setattr(CliRunner, "invoke", invoke)


def _built(tmp_path, templates=None, read_ok=True):
    """A built + read-back unit, as CampaignBuilder.build leaves it (campaign, stats, doc)."""
    templates = TEMPLATES if templates is None else templates
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    plan = run_dir / "plan.json"
    plan.write_text(json.dumps({"launch_id": "lc-1"}))
    campaign = {"auto_one__flow": {
        "name": "Sequence One (DRAFT)", "status": "draft", "source_unit": "auto_one",
        "unit_key": "lc-1/auto_one/flow", "expected_source_hash": UNIT_HASH}}
    stats = {"workflow_ids": {"auto_one__flow": "wf-9"}, "needs_reconcile": [],
             "readback": {"auto_one__flow": {"workflow_id": "wf-9", "ok": read_ok,
                                             "readback_hash": graph_hash(templates)}}}
    doc = {"launch_id": "lc-1", "builds": [{"id": "auto_one", "unit_key": "lc-1/auto_one"}]}
    return run_dir, plan, campaign, stats, doc


def _export(tmp_path, templates=None, stats_edit=None, remote=None, read_ok=True):
    run_dir, plan, campaign, stats, doc = _built(tmp_path, templates, read_ok)
    if stats_edit:
        stats_edit(stats)
    remote = TEMPLATES if remote is None else remote
    summary = delivery_export.export_build(
        doc, campaign, stats, journal=BuildJournal(run_dir / "journal.jsonl"),
        read_templates=lambda wid: remote if wid == "wf-9" else None,
        deliveries_path=str(run_dir / "deliveries.json"), launch_plan=str(plan))
    return run_dir, plan, doc, summary


def _delivery_units_rule():
    """Skill 83's own automation check, imported from the repo (read-only)."""
    root = REPO / "83-black-friday-launcher"
    sys.path.insert(0, str(root))
    try:
        from launcher_core.check_rules import delivery_units
        return delivery_units
    finally:
        sys.path.remove(str(root))


def test_build_writes_the_export_object_with_its_required_keys(tmp_path):
    run_dir, _plan, _doc, summary = _export(tmp_path)
    assert summary["units"] == ["auto_one"] and summary["refused"] == {}
    export = json.loads((run_dir / "exports" / "lc-1__auto_one.export.json").read_text())
    assert export["contract"] == "skill44.workflow-export.v1"
    assert export["produced_by"] == "caf workflows build --from-automation-build"
    assert export["workflow_id"] == "wf-9" and export["status"] == "draft"
    assert export["unit_key"] == "lc-1/auto_one"
    assert export["expected_graph_hash"] == UNIT_HASH
    assert export["readback_hash"] == graph_hash(TEMPLATES)
    assert export["templates"] == TEMPLATES  # so the validator Skill 83 re-runs has a graph


def test_deliveries_file_row_is_the_shape_83_assemble_reads(tmp_path):
    run_dir, plan, _doc, _summary = _export(tmp_path)
    row = json.loads((run_dir / "deliveries.json").read_text())["auto_one"]
    assert row["state"] == "complete"
    assert row["lane_validation"] == {"lane": "skill44", "contract": "skill44.workflow-export.v1",
                                      "state": "passed"}
    art = row["artifacts"][0]
    assert art["path"] == "exports/lc-1__auto_one.export.json"
    data = (run_dir / art["path"]).read_bytes()
    assert art["sha256"] == hashlib.sha256(data).hexdigest() and art["size"] == len(data)
    assert row["request"] == {"launch_id": "lc-1", "unit_id": "auto_one",
                              "plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest()}


def _with_qc_result(run_dir, row):
    """The independent QC step runs after the build (SKILL.md, Launch mode): it saves qc-<workflow_id>.json
    and that file joins the unit's artifacts. Skill 83's rule (issue 33) requires it, so these tests add it."""
    export = json.loads((run_dir / row["artifacts"][0]["path"]).read_text())
    name = "qc-%s.json" % export["workflow_id"]
    (run_dir / name).write_text(json.dumps({
        "workflow_id": export["workflow_id"], "exit_code": 0, "exit_gate": "PASS", "overall_mechanical": "PASS",
        "plan_mode_gate": {"status": "PASS"}}))
    data = (run_dir / name).read_bytes()
    row["artifacts"].append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})


def test_83_accepts_real_producer_output_and_still_refuses_a_hand_made_object(tmp_path):
    rule = _delivery_units_rule()
    run_dir, _plan, _doc, _summary = _export(tmp_path)
    row = json.loads((run_dir / "deliveries.json").read_text())["auto_one"]
    _with_qc_result(run_dir, row)
    assert rule.automation_violations("auto_one", row, "lc-1", {"auto_one": UNIT_HASH},
                                      run_dir) == []
    fake = run_dir / "exports" / "lc-1__auto_one.export.json"
    fake.write_text(json.dumps({"workflow_id": "x", "status": "draft", "unit_key": "lc-1/auto_one",
                                "produced_by": "me", "expected_graph_hash": UNIT_HASH}))
    row["artifacts"][0]["sha256"] = hashlib.sha256(fake.read_bytes()).hexdigest()
    row["artifacts"][0]["size"] = len(fake.read_bytes())
    assert rule.automation_violations("auto_one", row, "lc-1", {"auto_one": UNIT_HASH}, run_dir)


@pytest.mark.parametrize("label,kwargs,reason", [
    ("readback did not match", {"read_ok": False}, "read-back did not match"),
    ("graph changed after the read-back", {"remote": TEMPLATES[:-1] + [
        {"id": "x", "type": "email", "name": "x", "parentKey": "e1", "next": None}]},
     "changed since its verified read-back"),
    ("needs reconcile", {"stats_edit": lambda s: s["needs_reconcile"].append("lc-1/auto_one/flow")},
     "needs reconcile"),
    ("never built", {"stats_edit": lambda s: s["workflow_ids"].clear()}, "was not built"),
    ("no read-back receipt", {"stats_edit": lambda s: s["readback"].clear()},
     "no verified read-back receipt"),
])
def test_an_unproven_unit_is_refused_by_name_and_absent(tmp_path, label, kwargs, reason):
    run_dir, _plan, _doc, summary = _export(tmp_path, **kwargs)
    assert summary["units"] == [], label
    assert any(reason in why for why in summary["refused"]["auto_one"]), summary
    assert json.loads((run_dir / "deliveries.json").read_text()) == {}
    assert not (run_dir / "exports").exists()


def test_a_saved_graph_the_validator_refuses_is_never_exported(tmp_path):
    unterminated = TEMPLATES[:2]  # ends on an email with no terminal: WF-23 UNTERMINATED
    run_dir, _plan, _doc, summary = _export(tmp_path, templates=unterminated, remote=unterminated)
    assert summary["units"] == []
    assert any("saved graph refused" in why for why in summary["refused"]["auto_one"])
    assert not (run_dir / "exports").exists()


def test_the_artifact_must_sit_under_the_deliveries_directory(tmp_path):
    run_dir, _plan, campaign, stats, doc = _built(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    summary = delivery_export.export_build(
        doc, campaign, stats, journal=BuildJournal(run_dir / "journal.jsonl"),
        read_templates=lambda wid: TEMPLATES,
        deliveries_path=str(elsewhere / "deliveries.json"), launch_plan=str(run_dir / "plan.json"))
    assert summary["units"] == [] and "outside" in summary["refused"]["auto_one"][0]


def test_compiled_graphs_terminate_for_promo_and_non_promo_flows():
    """The compiler ends every path on a verified workflow_goal, so the real output passes the
    same WF-23 validator Skill 83 re-runs (before this, every compiled graph ended on an email)."""
    campaign = _l07.wb.compile_launch_builds(_l07.synthetic_document())
    assert {wf["promotional"] for wf in campaign.values()} == {True, False}
    for key, wf in campaign.items():
        ok, detail = delivery_export.graph_passes(wf["templates"])
        assert ok, (key, detail)
        assert wf["templates"][-1]["type"] == "workflow_goal"


def test_abandoned_checkout_build_with_sms_bound_passes_the_graph_validator(tmp_path):
    """The launch-b abandoned-checkout graph (text_abandoned_checkout bound) keeps the template's
    declared joins, so Skill 44's own validate_graph.py accepts it. Before, the compiler dropped
    ``attributes.join`` and the validator refused it with 5 CROSS_BRANCH failures."""
    sets = _load("export_obj_text_sets", SKILL / "automation-templates" / "launch-c"
                 / "tests" / "test_plan_reader_text_sets.py")
    rc, document = sets.read(tmp_path, copy_dir=sets.skill50_copy(tmp_path))
    assert rc == 0, [b["blocked_by"] for b in document["builds"]]
    campaign = _l07.wb.compile_launch_builds(document)
    flows = [wf for wf in campaign.values() if wf["source_unit"] == "auto_abandoned_checkout"]
    assert flows and any(s["type"] == "sms" for wf in flows for s in wf["templates"])
    for wf in flows:
        ok, detail = delivery_export.graph_passes(wf["templates"])
        assert ok, detail


def test_cli_real_build_exports_every_unit_and_83_accepts_it(tmp_path):
    """Skill 50-shaped plans -> reader -> compile -> build -> read-back -> export, through the real CLI
    and the fake provider; Skill 83's own automation rule accepts each row."""
    rule = _delivery_units_rule()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    document = _l07.synthetic_document()
    doc = run_dir / "automation-builds.json"
    doc.write_text(json.dumps(document))
    client = _l07.FakeClient()
    with patch.object(cli_mod, "_get_internal_client", return_value=client), \
            patch.object(cli_mod, "_get_public_v4", return_value=(None, "off")):
        result = CliRunner().invoke(cli, [
            "--experimental", "--json", "--location-id", LOC, "workflows", "build",
            "--from-automation-build", str(doc), "--journal", str(run_dir / "journal.jsonl"),
            "--deliveries-out", str(run_dir / "deliveries.json")])
    assert result.exit_code == 0, result.output
    rows = json.loads((run_dir / "deliveries.json").read_text())
    assert sorted(rows) == ["auto_post_sale", "auto_pre_launch"]
    expected = rule.reader_hashes(document, "l07-build")
    for unit, row in rows.items():
        _with_qc_result(run_dir, row)
        assert rule.automation_violations(unit, row, "l07-build", expected, run_dir) == [], unit


def test_deliveries_out_needs_a_real_automation_build(tmp_path):
    doc = tmp_path / "automation-builds.json"
    doc.write_text(json.dumps(_l07.synthetic_document()))
    result = CliRunner().invoke(cli, [
        "--json", "--location-id", LOC, "workflows", "build", "--from-automation-build",
        str(doc), "--journal", str(tmp_path / "j"), "--deliveries-out", str(tmp_path / "d.json"),
        "--dry-run"])
    assert result.exit_code == 2, result.output
    assert "belongs to a real --from-automation-build run" in result.stderr
    result = CliRunner().invoke(cli, [
        "--experimental", "--json", "--location-id", LOC, "workflows", "build", "--from-plan",
        str(doc), "--deliveries-out", str(tmp_path / "d.json")])
    assert result.exit_code == 2, result.output


def test_a_dry_run_without_deliveries_out_is_not_told_the_option_does_not_belong(tmp_path):
    doc = tmp_path / "automation-builds.json"
    doc.write_text(json.dumps(_l07.synthetic_document()))
    result = CliRunner().invoke(cli, [
        "--json", "--location-id", LOC, "workflows", "build", "--from-automation-build", str(doc), "--dry-run"])
    assert "--deliveries-out belongs" not in result.output + result.stderr
    result = CliRunner().invoke(cli, [
        "--json", "--location-id", LOC, "workflows", "build", "--from-plan", str(doc), "--dry-run"])
    assert "--deliveries-out belongs" not in result.output + result.stderr


# ---- one test per enforcement line of the export, so none hides another -----------------------------

def _sets():
    return _load("export_obj_text_sets", SKILL / "automation-templates" / "launch-c"
                 / "tests" / "test_plan_reader_text_sets.py")


def test_a_workflow_that_is_not_a_draft_is_never_exported(tmp_path):
    run_dir, plan, campaign, stats, doc = _built(tmp_path)
    campaign["auto_one__flow"]["status"] = "live"
    summary = delivery_export.export_build(
        doc, campaign, stats, journal=BuildJournal(run_dir / "journal.jsonl"),
        read_templates=lambda wid: TEMPLATES, deliveries_path=str(run_dir / "deliveries.json"),
        launch_plan=str(plan))
    assert summary["units"] == [] and any("is not a draft" in why for why in summary["refused"]["auto_one"])
    assert json.loads((run_dir / "deliveries.json").read_text()) == {}
    assert not (run_dir / "exports").exists()


def _two_workflow_unit(tmp_path, second_hash):
    """One unit that built two workflows, both read back clean; only their expected hashes differ."""
    run_dir, plan, campaign, stats, doc = _built(tmp_path)
    campaign["auto_one__other"] = dict(campaign["auto_one__flow"], unit_key="lc-1/auto_one/other",
                                       expected_source_hash=second_hash)
    stats["workflow_ids"]["auto_one__other"] = "wf-10"
    stats["readback"]["auto_one__other"] = dict(stats["readback"]["auto_one__flow"], workflow_id="wf-10")
    return delivery_export.export_build(
        doc, campaign, stats, journal=BuildJournal(run_dir / "journal.jsonl"),
        read_templates=lambda wid: TEMPLATES if wid in ("wf-9", "wf-10") else None,
        deliveries_path=str(run_dir / "deliveries.json"), launch_plan=str(plan)), run_dir


def test_a_unit_whose_workflows_disagree_on_the_expected_graph_hash_is_refused(tmp_path):
    summary, run_dir = _two_workflow_unit(tmp_path, second_hash="b" * 64)
    assert summary["units"] == []
    assert any("no single expected_graph_hash" in why for why in summary["refused"]["auto_one"])
    assert not (run_dir / "exports").exists()


def test_a_unit_whose_workflows_carry_no_expected_graph_hash_is_refused(tmp_path):
    run_dir, plan, campaign, stats, doc = _built(tmp_path)
    campaign["auto_one__flow"]["expected_source_hash"] = None
    summary = delivery_export.export_build(
        doc, campaign, stats, journal=BuildJournal(run_dir / "journal.jsonl"),
        read_templates=lambda wid: TEMPLATES, deliveries_path=str(run_dir / "deliveries.json"),
        launch_plan=str(plan))
    assert summary["units"] == []
    assert any("no single expected_graph_hash" in why for why in summary["refused"]["auto_one"])


def test_two_workflows_that_agree_on_the_expected_hash_are_exported(tmp_path):
    summary, run_dir = _two_workflow_unit(tmp_path, second_hash=UNIT_HASH)
    assert summary["units"] == ["auto_one"], summary
    export = json.loads((run_dir / "exports" / "lc-1__auto_one.export.json").read_text())
    assert export["expected_graph_hash"] == UNIT_HASH and len(export["workflows"]) == 2


def test_a_set_whose_only_sms_steps_are_copy_pending_is_not_delivered(tmp_path):
    sets = _sets()
    _rc, doc = sets.read(tmp_path, copy_dir=sets.skill50_copy(tmp_path))
    proven = sets._proven(doc)
    for step in proven["auto_abandoned_checkout"][0]["templates"]:
        if step["type"] == "sms":
            step["attributes"]["copy_pending"] = True  # the body is still the approved one
    path, reasons = delivery_export.export_text_set(doc["text_builds"][0], "txt-1", proven,
                                                    tmp_path / "exports")
    assert path is None and any("not the body of any saved SMS step" in r for r in reasons)
    assert not (tmp_path / "exports").exists()


def test_a_set_whose_approved_body_sits_only_in_a_step_that_is_not_an_sms_step_is_not_delivered(tmp_path):
    sets = _sets()
    _rc, doc = sets.read(tmp_path, copy_dir=sets.skill50_copy(tmp_path))
    proven = sets._proven(doc)
    for step in proven["auto_abandoned_checkout"][0]["templates"]:
        if step["type"] == "sms":
            step["type"] = "internal_notification"  # the body is still the approved one, but no step sends it
    path, reasons = delivery_export.export_text_set(doc["text_builds"][0], "txt-1", proven,
                                                    tmp_path / "exports")
    assert path is None and reasons
    assert all(r.endswith("is not the body of any saved SMS step") for r in reasons)
    assert any(r.startswith("message auto_abandoned_checkout-n9 ") for r in reasons)
    assert not (tmp_path / "exports").exists()


def test_a_build_whose_stats_name_no_workflow_ids_is_refused_as_not_built_not_a_crash(tmp_path):
    run_dir, plan, campaign, stats, doc = _built(tmp_path)
    del stats["workflow_ids"]
    summary = delivery_export.export_build(
        doc, campaign, stats, journal=BuildJournal(run_dir / "journal.jsonl"),
        read_templates=lambda wid: TEMPLATES, deliveries_path=str(run_dir / "deliveries.json"),
        launch_plan=str(plan))
    assert summary["units"] == [] and summary["refused"]["auto_one"] == ["workflow auto_one__flow was not built"]


def test_campaign_entries_that_are_not_workflows_never_join_a_unit_and_never_crash_it(tmp_path):
    run_dir, plan, campaign, stats, doc = _built(tmp_path)
    campaign["folder"] = "a bare string"
    campaign["_meta"] = None
    campaign["stray"] = ["source_unit", "auto_one"]
    summary = delivery_export.export_build(
        doc, campaign, stats, journal=BuildJournal(run_dir / "journal.jsonl"),
        read_templates=lambda wid: TEMPLATES, deliveries_path=str(run_dir / "deliveries.json"),
        launch_plan=str(plan))
    assert summary["units"] == ["auto_one"] and summary["refused"] == {}


def test_a_document_with_no_builds_or_no_text_builds_exports_nothing_and_does_not_crash(tmp_path):
    run_dir, plan, campaign, stats, doc = _built(tmp_path)
    for kept in ({}, {"text_builds": []}, {"builds": None, "text_builds": None}):
        summary = delivery_export.export_build(
            dict(launch_id="lc-1", **kept), campaign, stats,
            journal=BuildJournal(run_dir / "journal.jsonl"), read_templates=lambda wid: TEMPLATES,
            deliveries_path=str(run_dir / "deliveries.json"), launch_plan=str(plan))
        assert summary["units"] == [] and summary["refused"] == {}, kept
    assert json.loads((run_dir / "deliveries.json").read_text()) == {}


def test_a_text_set_missing_optional_fields_is_judged_by_what_it_carries_not_crashed_on(tmp_path):
    sets = _sets()
    _rc, doc = sets.read(tmp_path, copy_dir=sets.skill50_copy(tmp_path))
    whole = doc["text_builds"][0]
    exports = tmp_path / "exports"
    # no electing automations listed at all
    path, reasons = delivery_export.export_text_set({k: v for k, v in whole.items() if k != "automations"},
                                                    "txt-1", sets._proven(doc), exports)
    assert path is None
    assert reasons == ["no delivered automation carries the set (elected by: none; not delivered: none)"]
    # no bindings at all
    path, reasons = delivery_export.export_text_set({k: v for k, v in whole.items() if k != "bindings"},
                                                    "txt-1", sets._proven(doc), exports)
    assert path is None and reasons
    # no categories and no declared message count: every approved body is still saved, so it is delivered
    bare = {k: v for k, v in whole.items() if k not in ("categories", "messages")}
    path, reasons = delivery_export.export_text_set(bare, "txt-1", sets._proven(doc), exports)
    assert reasons == [] and path is not None
    assert [m["category"] for m in json.loads(path.read_text())["messages"]] == [None, None]


def test_stats_without_reconcile_or_readback_lists_are_read_as_empty_not_crashed_on(tmp_path):
    run_dir, plan, campaign, stats, doc = _built(tmp_path)
    del stats["needs_reconcile"]
    summary = delivery_export.export_build(
        doc, campaign, stats, journal=BuildJournal(run_dir / "journal.jsonl"),
        read_templates=lambda wid: TEMPLATES, deliveries_path=str(run_dir / "deliveries.json"),
        launch_plan=str(plan))
    assert summary["units"] == ["auto_one"] and summary["refused"] == {}
    (tmp_path / "second").mkdir()
    run_dir, plan, campaign, stats, doc = _built(tmp_path / "second")
    del stats["readback"]  # nothing reported and no journal entry: no receipt, named, not a crash
    proof, why = delivery_export._workflow_proof("auto_one__flow", campaign["auto_one__flow"], stats, None,
                                                 lambda wid: TEMPLATES, graph_hash)
    assert proof is None and why == "workflow auto_one__flow has no verified read-back receipt in the journal"


def test_a_text_set_that_is_blocked_is_refused_with_its_own_reasons_or_a_plain_one(tmp_path):
    sets = _sets()
    _rc, doc = sets.read(tmp_path, copy_dir=sets.skill50_copy(tmp_path))
    whole = doc["text_builds"][0]
    path, reasons = delivery_export.export_text_set(dict(whole, state="blocked", blocked_by=["no copy yet"]),
                                                    "txt-1", sets._proven(doc), tmp_path / "exports")
    assert path is None and reasons == ["no copy yet"]
    path, reasons = delivery_export.export_text_set({k: v for k, v in dict(whole, state="blocked").items()
                                                     if k != "blocked_by"},
                                                    "txt-1", sets._proven(doc), tmp_path / "exports")
    assert path is None and reasons == ["text set is blocked"]
    assert not (tmp_path / "exports").exists()


def test_the_refusal_for_an_undelivered_electing_automation_names_it_exactly(tmp_path):
    sets = _sets()
    _rc, doc = sets.read(tmp_path, copy_dir=sets.skill50_copy(tmp_path))
    path, reasons = delivery_export.export_text_set(doc["text_builds"][0], "txt-1", {}, tmp_path / "exports")
    assert path is None and reasons == [
        "no delivered automation carries the set (elected by: auto_abandoned_checkout; "
        "not delivered: auto_abandoned_checkout)"]


def test_saved_steps_that_are_not_objects_or_carry_no_attributes_are_skipped_not_crashed_on(tmp_path):
    sets = _sets()
    _rc, doc = sets.read(tmp_path, copy_dir=sets.skill50_copy(tmp_path))
    proven = sets._proven(doc)
    steps = proven["auto_abandoned_checkout"][0]["templates"]
    steps[:0] = ["junk", None, {"id": "bare-sms", "type": "sms", "attributes": None},
                 {"id": "no-attrs", "type": "sms"}]  # first, so every body search walks past them
    path, reasons = delivery_export.export_text_set(doc["text_builds"][0], "txt-1", proven,
                                                    tmp_path / "exports")
    assert reasons == [] and path is not None  # the real sms steps still carry every approved body
    text = dict(doc["text_builds"][0], bindings={"sms_copy": {}})
    path, reasons = delivery_export.export_text_set(text, "txt-1", proven, tmp_path / "other")
    assert path is None and reasons == ["the set carries 2 message(s), 0 are saved"]


def test_a_set_with_fewer_saved_messages_than_the_plan_promises_is_not_delivered(tmp_path):
    sets = _sets()
    _rc, doc = sets.read(tmp_path, copy_dir=sets.skill50_copy(tmp_path))
    text = dict(doc["text_builds"][0], messages=3)  # the plan says 3; the copy and the saved steps are 2
    path, reasons = delivery_export.export_text_set(text, "txt-1", sets._proven(doc), tmp_path / "exports")
    assert path is None and reasons == ["the set carries 3 message(s), 2 are saved"]
    assert not (tmp_path / "exports").exists()
    path, reasons = delivery_export.export_text_set(doc["text_builds"][0], "txt-1", sets._proven(doc),
                                                    tmp_path / "exports")
    assert reasons == [] and path is not None


def test_a_set_with_no_saved_message_is_not_delivered_whether_the_count_is_absent_or_zero(tmp_path):
    sets = _sets()
    _rc, doc = sets.read(tmp_path, copy_dir=sets.skill50_copy(tmp_path))
    for declared in ({}, {"messages": 0}):
        text = {k: v for k, v in doc["text_builds"][0].items() if k != "messages"}
        text.update(declared, bindings={"sms_copy": {}})
        path, reasons = delivery_export.export_text_set(text, "txt-1", sets._proven(doc), tmp_path / "exports")
        assert path is None and reasons, declared
    assert not (tmp_path / "exports").exists()


def test_compile_build_alone_ends_every_path_on_a_terminal(tmp_path):
    """compile_build (the document-level compiler) terminates by itself, not through compile_installable."""
    steps_mod = _load("export_obj_step_compiler_tests", ENGINE / "tests" / "test_launch_step_compiler.py")
    lsc = steps_mod.lsc
    result = lsc.compile_launch_document(steps_mod.make_document(), bindings=steps_mod.BINDINGS)
    assert result["campaign"], result["blocked"]
    assert {wf["promotional"] for wf in result["campaign"].values()} == {True, False}
    for key, wf in result["campaign"].items():
        steps = wf["templates"]
        assert steps[-1]["type"] == "workflow_goal", key
        assert not [s["id"] for s in steps if not s.get("next") and not s.get("branches")
                    and s["type"] != "workflow_goal"], key


def test_compile_build_alone_terminates_a_template_graph_that_ends_on_an_action(tmp_path, monkeypatch):
    """Only compile_build's own _terminate call can end a graph whose template has no terminal node."""
    steps_mod = _load("export_obj_step_compiler_tests", ENGINE / "tests" / "test_launch_step_compiler.py")
    lsc = steps_mod.lsc
    real = lsc.resolve_template

    def headless(build, **kw):
        spec, key, reason = real(build, **kw)
        return dict(spec, build_graph=[n for n in spec["build_graph"]
                                       if n.get("type") != "workflow_goal"]), key, reason

    monkeypatch.setattr(lsc, "resolve_template", headless)
    result = lsc.compile_build(steps_mod.build_of(steps_mod.make_document(), "auto_post_sale"),
                               bindings=steps_mod.BINDINGS)
    assert result["status"] == "ok", result["blocked_by"]
    steps = result["workflows"]["auto_post_sale__flow"]["templates"]
    assert steps[-1]["type"] == "workflow_goal" and steps[-1]["id"] == "auto_post_sale-end"
    assert not [s["id"] for s in steps if not s.get("next") and not s.get("branches")
                and s["type"] != "workflow_goal"]
    ok, detail = delivery_export.graph_passes(steps)
    assert ok, detail


def _cli_build(tmp_path, document, *extra):
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    doc = run_dir / "automation-builds.json"
    doc.write_text(json.dumps(document))
    client = _l07.FakeClient()
    with patch.object(cli_mod, "_get_internal_client", return_value=client), \
            patch.object(cli_mod, "_get_public_v4", return_value=(None, "off")):
        result = CliRunner().invoke(cli, [
            "--experimental", "--json", "--location-id", LOC, "workflows", "build",
            "--from-automation-build", str(doc), "--journal", str(run_dir / "journal.jsonl"),
            "--deliveries-out", str(run_dir / "deliveries.json"), *extra])
    return result, client, run_dir


def test_deliveries_out_without_a_readable_launch_plan_exits_2_before_anything_is_built(tmp_path):
    document = _l07.synthetic_document()
    document["sources"]["launch_plan"] = str(tmp_path / "no-such-plan.json")
    result, client, run_dir = _cli_build(tmp_path, document)
    assert result.exit_code == 2, result.output
    assert "needs the launch plan" in result.output
    assert not client.workflows, "nothing may be written to the provider without the plan to hash"
    assert not (run_dir / "deliveries.json").exists()


def test_a_unit_refused_for_delivery_fails_the_build_and_is_named_among_the_errors(tmp_path):
    document = _l07.synthetic_document()
    document["text_builds"] = [{"id": "text_never_copied", "state": "blocked",
                                "blocked_by": ["text_set:text_never_copied copy"], "automations": []}]
    result, _client, run_dir = _cli_build(tmp_path, document)
    assert result.exit_code == 1, result.output
    stats = json.loads(result.output[result.output.index("{"):result.output.rindex("}") + 1])
    assert any("text_never_copied" in e and "not exported for delivery" in e for e in stats["errors"]), stats
    assert not any("not exported for delivery" in n for n in stats.get("notes") or [])
    assert sorted(json.loads((run_dir / "deliveries.json").read_text())) == [
        "auto_post_sale", "auto_pre_launch"]


def test_terminate_links_every_tail_to_the_one_terminal_and_the_graph_passes(tmp_path):
    """A graph with two dangling tails: BOTH point at the new terminal (linking only the last one
    leaves the other path unterminated, which Skill 44's own validator refuses)."""
    lsc = _load("export_obj_step_compiler_tails", ENGINE / "tests" / "test_launch_step_compiler.py").lsc
    steps = [
        {"id": "w1", "type": "wait", "name": "Wait", "parentKey": None, "next": "branch"},
        {"id": "branch", "type": "if_else", "name": "Split", "parentKey": "w1", "next": None,
         "branches": {"yes": "e1", "no": "e2"}},
        {"id": "e1", "type": "email", "name": "One", "parentKey": "branch", "next": None},
        {"id": "e2", "type": "email", "name": "Two", "parentKey": "branch", "next": None},
    ]
    lsc._terminate(steps, "b1")
    goal = steps[-1]
    assert goal == {"id": "b1-end", "type": "workflow_goal", "name": "Goal: sequence complete",
                    "attributes": {"goal": "sequence_complete", "scope": "this_campaign_only"},
                    "parentKey": "e2", "next": None}
    assert [s["next"] for s in steps if s["id"] in ("e1", "e2")] == ["b1-end", "b1-end"]
    assert [s["id"] for s in steps].count("b1-end") == 1
    lsc._terminate(steps, "b1")  # already terminated: nothing more is added
    assert len(steps) == 5


def test_the_build_reports_the_deliveries_summary_in_its_stats(tmp_path):
    result, _client, run_dir = _cli_build(tmp_path, _l07.synthetic_document())
    assert result.exit_code == 0, result.output
    stats = json.loads(result.output[result.output.index("{"):result.output.rindex("}") + 1])
    summary = stats["deliveries"]
    assert set(summary) == {"deliveries", "units", "refused"}
    assert summary["units"] == ["auto_post_sale", "auto_pre_launch"] and summary["refused"] == {}
    assert summary["deliveries"] == str(run_dir / "deliveries.json")


def _adopted(tmp_path, entries, readback=None):
    """An adopted unit (a re-run: no fresh read-back in stats) judged from the journal alone."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    run_dir, plan, campaign, stats, doc = _built(tmp_path)
    stats["readback"] = {} if readback is None else readback
    journal = BuildJournal(run_dir / "journal.jsonl")
    for entry in entries:
        journal.append(**{"unit_key": "lc-1/auto_one/flow", "remote_id": "wf-9",
                          "readback_hash": graph_hash(TEMPLATES), **entry})
    return delivery_export.export_build(
        doc, campaign, stats, journal=journal, read_templates=lambda wid: TEMPLATES,
        deliveries_path=str(run_dir / "deliveries.json"), launch_plan=str(plan))


def test_an_adopted_workflow_is_proven_by_an_ok_readback_or_an_adopted_reconcile_entry(tmp_path):
    assert _adopted(tmp_path / "a", [{"phase": "readback", "status": "ok"}])["units"] == ["auto_one"]
    assert _adopted(tmp_path / "b", [{"phase": "reconcile", "status": "adopted"}])["units"] == ["auto_one"]
    # a failed read-back does not mask an adopted reconcile entry
    both = [{"phase": "readback", "status": "mismatch"}, {"phase": "reconcile", "status": "adopted"}]
    assert _adopted(tmp_path / "c", both)["units"] == ["auto_one"]


@pytest.mark.parametrize("entries", [
    [{"phase": "readback", "status": "mismatch"}],
    [{"phase": "readback", "status": "failed"}],
    [{"phase": "reconcile", "status": "created"}],
    [{"phase": "reconcile", "status": "failed"}],
    [{"phase": "readback", "status": "mismatch"}, {"phase": "reconcile", "status": "failed"}],
])
def test_an_adopted_workflow_whose_journal_entry_is_not_ok_or_adopted_is_refused(tmp_path, entries):
    # the hash and the remote id agree with the saved graph: only the entry's status is wrong
    summary = _adopted(tmp_path, entries)
    assert summary["units"] == []
    assert any("no verified read-back receipt in the journal" in why
               for why in summary["refused"]["auto_one"]), summary


def test_the_text_set_export_carries_the_readers_profile_sha256_end_to_end(tmp_path):
    sets = _sets()
    copy_dir = sets.skill50_copy(tmp_path)
    sha = json.loads((copy_dir / ("%s.sms.json" % sets.SET_ID)).read_text())["profile_sha256"]
    assert len(sha) == 64
    _rc, doc = sets.read(tmp_path, copy_dir=copy_dir)
    assert doc["text_builds"][0]["profile_sha256"] == sha
    path, reasons = delivery_export.export_text_set(doc["text_builds"][0], "txt-1", sets._proven(doc),
                                                    tmp_path / "exports")
    assert reasons == [] and json.loads(path.read_text())["profile_sha256"] == sha


# ---- sweep round 1: the reason named for each refusal ------------------------------------------------

def test_a_workflow_that_cannot_be_read_back_now_is_refused_as_such(tmp_path):
    run_dir, plan, campaign, stats, doc = _built(tmp_path)
    summary = delivery_export.export_build(
        doc, campaign, stats, journal=BuildJournal(run_dir / "journal.jsonl"),
        read_templates=lambda wid: None,
        deliveries_path=str(run_dir / "deliveries.json"), launch_plan=str(plan))
    assert summary["units"] == []
    assert summary["refused"]["auto_one"] == ["workflow auto_one__flow cannot be read back now"]


def test_a_build_with_no_compiled_workflow_is_refused_as_such(tmp_path):
    run_dir, plan, campaign, stats, doc = _built(tmp_path)
    campaign.clear()
    summary = delivery_export.export_build(
        doc, campaign, stats, journal=BuildJournal(run_dir / "journal.jsonl"),
        read_templates=lambda wid: TEMPLATES,
        deliveries_path=str(run_dir / "deliveries.json"), launch_plan=str(plan))
    assert summary["refused"] == {"auto_one": ["no workflow compiled for the unit"]}


def test_a_text_set_that_no_automation_elected_is_refused_as_such(tmp_path):
    sets = _sets()
    _rc, doc = sets.read(tmp_path, copy_dir=sets.skill50_copy(tmp_path))
    text = dict(doc["text_builds"][0], automations=[])
    path, reasons = delivery_export.export_text_set(text, "txt-1", sets._proven(doc), tmp_path / "exports")
    assert path is None
    assert reasons == ["no delivered automation carries the set (elected by: none; not delivered: none)"]
    path, reasons = delivery_export.export_text_set(doc["text_builds"][0], "txt-1", {}, tmp_path / "exports")
    assert path is None and "not delivered: auto_abandoned_checkout" in reasons[0]


def test_an_adopted_workflow_whose_journal_receipt_names_another_remote_id_is_refused(tmp_path):
    summary = _adopted(tmp_path, [{"phase": "readback", "status": "ok", "remote_id": "wf-OTHER"}])
    assert summary["units"] == []
    assert any("no verified read-back receipt in the journal" in why for why in summary["refused"]["auto_one"])


def test_without_a_journal_an_unreported_readback_has_no_receipt(tmp_path):
    _run_dir, _plan, campaign, stats, _doc = _built(tmp_path)
    stats["readback"] = {}
    proof, why = delivery_export._workflow_proof("auto_one__flow", campaign["auto_one__flow"], stats, None,
                                                 lambda wid: TEMPLATES, graph_hash)
    assert proof is None and why == "workflow auto_one__flow has no verified read-back receipt in the journal"


def test_a_set_with_one_message_that_is_in_no_saved_step_is_refused_even_when_the_rest_are_saved(tmp_path):
    sets = _sets()
    _rc, doc = sets.read(tmp_path, copy_dir=sets.skill50_copy(tmp_path))
    text = {k: v for k, v in doc["text_builds"][0].items() if k != "messages"}  # no declared count
    text["bindings"] = {"sms_copy": dict(text["bindings"]["sms_copy"], ghost="a body no saved step carries")}
    path, reasons = delivery_export.export_text_set(text, "txt-1", sets._proven(doc), tmp_path / "exports")
    assert path is None and reasons == ["message ghost is not the body of any saved SMS step"]
    assert not (tmp_path / "exports").exists()


def test_the_text_set_export_object_is_exactly_what_83_reads(tmp_path):
    sets = _sets()
    _rc, doc = sets.read(tmp_path, copy_dir=sets.skill50_copy(tmp_path))
    path, reasons = delivery_export.export_text_set(doc["text_builds"][0], "txt-1", sets._proven(doc),
                                                    tmp_path / "exports")
    export = json.loads(path.read_text())
    assert path.name == "txt-1__%s.sms-set.json" % sets.SET_ID
    assert {k: export[k] for k in ("contract", "set_id", "status", "unit_key", "produced_by",
                                   "electing_units")} == {
        "contract": "skill44.sms-set.v1", "set_id": sets.SET_ID, "status": "draft",
        "unit_key": "txt-1/" + sets.SET_ID, "produced_by": "caf workflows build --from-automation-build",
        "electing_units": ["auto_abandoned_checkout"]}
    message = export["messages"][0]
    assert message["bound_in"] == {"unit": "auto_abandoned_checkout", "workflow_id": "wf-1",
                                   "saved_step_id": message["bound_in"]["saved_step_id"]}
    assert message["bound_in"]["saved_step_id"]
    assert len(message["body_sha256"]) == 64


def test_entries_in_the_document_that_are_not_units_are_skipped_not_crashed_on(tmp_path):
    run_dir, plan, campaign, stats, doc = _built(tmp_path)
    doc["builds"] = ["junk", {"state": "ready"}, {"id": ""}] + doc["builds"]
    doc["text_builds"] = ["junk", {"state": "ready"}, {"id": ""}]
    summary = delivery_export.export_build(
        doc, campaign, stats, journal=BuildJournal(run_dir / "journal.jsonl"),
        read_templates=lambda wid: TEMPLATES,
        deliveries_path=str(run_dir / "deliveries.json"), launch_plan=str(plan))
    assert summary["units"] == ["auto_one"] and summary["refused"] == {}


def test_write_json_creates_missing_parent_directories_and_sorts_keys(tmp_path):
    target = delivery_export.write_json(tmp_path / "a" / "b" / "c.json", {"z": 1, "a": 2})
    assert target.read_text() == '{\n  "a": 2,\n  "z": 1\n}\n'


def _sms(step_id, body, pending=False):
    return {"id": step_id, "type": "sms", "attributes": {"body": body, "copy_pending": pending}}


def _launch(unit_workflows, document):
    """A CompiledLaunch holding `unit_workflows` ({key: (source_unit, steps)}), as the compiler returns it."""
    from cli_anything.gohighlevel.utils.workflow_builder import CompiledLaunch
    campaign = CompiledLaunch({key: {"source_unit": unit, "templates": steps}
                               for key, (unit, steps) in unit_workflows.items()})
    from cli_anything.gohighlevel.utils import launch_text
    return launch_text.enforce_sms_copy(campaign, document)


def _elected(unit="u1", copy=None):
    return {"builds": [{"id": unit, "unit_key": "lc/" + unit, "text_sets": ["t1"],
                        "bindings": {"sms_copy": copy or {}}}]}


def test_enforce_sms_copy_names_a_pending_step_with_its_code_state_and_detail():
    campaign = _launch({"u1__flow": ("u1", [_sms("s1", "hello", pending=True), _sms("s2", "bye")])},
                       _elected(copy={"s2": "bye"}))
    assert dict(campaign) == {}
    (refusal,) = campaign.refusals
    assert refusal["code"] == "SMS-COPY-PENDING" and refusal["state"] == "blocked"
    assert refusal["id"] == "u1" and refusal["unit_key"] == "lc/u1"
    assert refusal["detail"] == {"pending": ["s1"], "unbound": []}
    assert refusal["reason"] == "elected text set(s) t1: SMS step(s) s1 are still copy_pending"


def test_enforce_sms_copy_names_approved_copy_that_landed_in_no_step():
    campaign = _launch({"u1__flow": ("u1", [_sms("s1", "hello")])},
                       _elected(copy={"s1": "hello", "s9": "never compiled"}))
    assert dict(campaign) == {}
    (refusal,) = campaign.refusals
    assert refusal["code"] == "SMS-COPY-UNBOUND" and refusal["state"] == "blocked"
    assert refusal["detail"] == {"pending": [], "unbound": ["s9"]}
    assert refusal["reason"] == "elected text set(s) t1: approved copy for step(s) s9 landed in no SMS step"


def test_enforce_sms_copy_refuses_a_build_that_compiles_no_sms_step_at_all():
    campaign = _launch({"u1__flow": ("u1", [{"id": "e1", "type": "email", "attributes": {}}])}, _elected())
    assert dict(campaign) == {}
    (refusal,) = campaign.refusals
    assert refusal["code"] == "SMS-COPY-UNBOUND"
    assert refusal["reason"] == ("elected text set(s) t1: the build compiles no SMS step "
                                 "to carry the approved copy")


def test_enforce_sms_copy_leaves_a_build_whose_copy_all_landed_untouched():
    campaign = _launch({"u1__flow": ("u1", [_sms("s1", "hello")])}, _elected(copy={"s1": "hello"}))
    assert list(campaign) == ["u1__flow"] and campaign.refusals == []


def test_enforce_sms_copy_leaves_a_build_that_elected_no_text_alone():
    document = {"builds": [{"id": "u1", "unit_key": "lc/u1", "text_sets": []}]}
    campaign = _launch({"u1__flow": ("u1", [_sms("s1", "x", pending=True)])}, document)
    assert list(campaign) == ["u1__flow"] and campaign.refusals == []


def test_enforce_sms_copy_adds_no_refusal_for_a_build_that_is_not_in_the_campaign():
    # u1 was refused earlier (so it has no workflow left); only u2's workflow is in the campaign.
    campaign = _launch({"u2__flow": ("u2", [_sms("s1", "hello")])}, _elected(unit="u1", copy={"s1": "nope"}))
    assert list(campaign) == ["u2__flow"] and campaign.refusals == []


def test_enforce_sms_copy_removes_only_the_refused_units_workflows():
    document = _elected(unit="u1", copy={"s1": "never compiled"})
    campaign = _launch({"u1__flow": ("u1", [_sms("s0", "x")]), "u2__flow": ("u2", [_sms("s1", "y")])}, document)
    assert list(campaign) == ["u2__flow"] and [r["id"] for r in campaign.refusals] == ["u1"]


def test_only_the_nodes_a_template_declares_as_joins_carry_the_join_attribute(tmp_path):
    sets = _sets()
    rc, document = sets.read(tmp_path, copy_dir=sets.skill50_copy(tmp_path))
    assert rc == 0
    template = json.loads((SKILL / "automation-templates" / "launch-b"
                           / "abandoned-checkout-recovery.json").read_text())
    declared = {"auto_abandoned_checkout-" + n["id"] for n in template["build_graph"]
                if (n.get("attributes") or {}).get("join") is True}
    assert declared == {"auto_abandoned_checkout-" + n for n in ("n10", "n12", "n19", "n21", "x1")}
    campaign = _l07.wb.compile_launch_builds(document)
    steps = [s for wf in campaign.values() if wf["source_unit"] == "auto_abandoned_checkout"
             for s in wf["templates"]]
    carried = {s["id"] for s in steps if (s.get("attributes") or {}).get("join") is True}
    assert carried == declared
    assert len(steps) > len(carried)


def test_a_set_that_cannot_be_written_as_a_delivery_row_is_refused_by_name(tmp_path, monkeypatch):
    run_dir, plan, campaign, stats, doc = _built(tmp_path)
    doc["text_builds"] = [{"id": "text_one", "state": "ready"}]
    elsewhere = tmp_path / "elsewhere" / "lc-1__text_one.sms-set.json"
    elsewhere.parent.mkdir()
    elsewhere.write_text("{}")  # an export written outside the deliveries directory tree
    monkeypatch.setattr(delivery_export, "export_text_set", lambda *a, **kw: (elsewhere, []))
    summary = delivery_export.export_build(
        doc, campaign, stats, journal=BuildJournal(run_dir / "journal.jsonl"),
        read_templates=lambda wid: TEMPLATES, deliveries_path=str(run_dir / "deliveries.json"),
        launch_plan=str(plan))
    assert summary["units"] == ["auto_one"]
    assert len(summary["refused"]["text_one"]) == 1 and "is outside" in summary["refused"]["text_one"][0]
    assert sorted(json.loads((run_dir / "deliveries.json").read_text())) == ["auto_one"]


def test_a_launch_plan_option_that_names_no_file_is_a_usage_error_before_anything_is_built(tmp_path):
    result, client, run_dir = _cli_build(tmp_path, _l07.synthetic_document(),
                                         "--launch-plan", str(tmp_path / "no-such-plan.json"))
    assert result.exit_code == 2, result.output
    assert "does not exist" in result.stderr
    assert not client.workflows and not (run_dir / "deliveries.json").exists()


def test_an_explicit_launch_plan_option_is_the_plan_whose_hash_the_rows_echo(tmp_path):
    other = tmp_path / "other-plan.json"
    other.write_text(json.dumps({"launch_id": "l07-build", "note": "a different plan"}))
    result, _client, run_dir = _cli_build(tmp_path, _l07.synthetic_document(), "--launch-plan", str(other))
    assert result.exit_code == 0, result.output
    rows = json.loads((run_dir / "deliveries.json").read_text())
    assert {r["request"]["plan_sha256"] for r in rows.values()} == {
        hashlib.sha256(other.read_bytes()).hexdigest()}


def test_deliveries_out_with_an_automation_build_that_is_not_an_object_exits_2_naming_the_plan(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    doc = run_dir / "automation-builds.json"
    doc.write_text("[]")
    result = CliRunner().invoke(cli, [
        "--experimental", "--json", "--location-id", LOC, "workflows", "build", "--from-automation-build",
        str(doc), "--journal", str(run_dir / "journal.jsonl"), "--deliveries-out", str(run_dir / "d.json")])
    assert result.exit_code == 2, result.output
    assert "needs the launch plan" in result.stderr
    assert not (run_dir / "d.json").exists()


def test_deliveries_out_with_a_null_sources_block_exits_2_naming_the_plan_not_a_traceback(tmp_path):
    document = _l07.synthetic_document()
    document["sources"] = None
    result, client, run_dir = _cli_build(tmp_path, document)
    assert result.exit_code == 2, result.output
    assert isinstance(result.exception, SystemExit), repr(result.exception)
    assert "needs the launch plan" in result.stderr
    assert not client.workflows and not (run_dir / "deliveries.json").exists()


def test_the_plan_message_and_the_option_message_go_to_stderr(tmp_path):
    document = _l07.synthetic_document()
    document["sources"]["launch_plan"] = str(tmp_path / "no-such-plan.json")
    result, _client, _run_dir = _cli_build(tmp_path, document)
    assert result.exit_code == 2 and "needs the launch plan" in result.stderr


def test_a_graph_validator_that_is_not_installed_refuses_every_graph_by_name(monkeypatch, tmp_path):
    assert delivery_export.graph_passes(TEMPLATES) == (True, "graph validator exit 0")
    monkeypatch.setattr(delivery_export, "VALIDATOR", tmp_path / "no-such-validate_graph.py")
    assert delivery_export.graph_passes(TEMPLATES) == (False, "tools/validate_graph.py is not installed")


def test_a_graph_validator_that_cannot_run_refuses_the_graph_by_name(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("no interpreter")

    monkeypatch.setattr(delivery_export.subprocess, "run", boom)
    assert delivery_export.graph_passes(TEMPLATES) == (False, "graph validator could not run (OSError)")
