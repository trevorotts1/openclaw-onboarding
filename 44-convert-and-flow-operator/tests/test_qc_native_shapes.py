"""SWB-062: the QC tool reads GoHighLevel's real saved shapes.

Synthetic fixtures only (no client names or ids). Each positive case has a
negative twin showing a truly broken workflow still fails.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
SMS = ROOT / "automation-templates" / "launch-text" / "sms_eligibility.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


vg = _load(TOOLS / "validate_graph.py", "vg_swb062")
sms = _load(SMS, "sms_swb062")
dm = _load(TOOLS / "build_deps_manifest.py", "dm_swb062")


def cond(cid, kids, name="if_else", parent=None):
    n = {"id": cid, "type": "if_else", "name": name, "next": kids,
         "advanceCanvasMeta": {}, "attributes": {"branches": [{"id": kids[0], "name": "Not bought"}]}}
    if parent:
        n["parentKey"] = parent
    return n


def arm(aid, parent, nxt=None, else_arm=False):
    n = {"id": aid, "type": "if_else", "name": "None" if else_arm else "Not bought",
         "parent": parent, "parentKey": parent, "advanceCanvasMeta": {},
         "attributes": {"else": True} if else_arm else {"if": True, "branches": []}}
    if nxt:
        n["next"] = nxt
    return n


def action(aid, parent, typ="email", nxt=None):
    n = {"id": aid, "type": typ, "name": typ, "parentKey": parent, "advanceCanvasMeta": {}}
    if nxt:
        n["next"] = nxt
    return n


def native_good():
    return [
        cond("c1", ["a1", "a2"]),
        arm("a1", "c1", nxt="e1"),
        arm("a2", "c1", else_arm=True),  # empty None arm: a branch end
        action("e1", "a1", "email", nxt="g1"),
        {"id": "g1", "type": "workflow_goal", "name": "goal", "parentKey": "e1",
         "advanceCanvasMeta": {}},
    ]


def run_graph(nodes, tmp_path):
    f = tmp_path / "wf.json"
    f.write_text(json.dumps({"workflowData": {"templates": nodes}}))
    proc = subprocess.run([sys.executable, "-I", str(TOOLS / "validate_graph.py"), "graph",
                           "--export", str(f)], capture_output=True, text=True, timeout=60)
    return json.loads(proc.stdout)


def kinds(report):
    return sorted({f["kind"] for f in report["failures"]})


def test_native_condition_with_arms_passes(tmp_path):
    r = run_graph(native_good(), tmp_path)
    assert r["verdict"] == "PASS", r["failures"]


def test_native_chain_ending_in_an_action_is_a_workflow_end(tmp_path):
    nodes = [action("e1", None, "email", nxt="e2"), action("e2", "e1", "sms")]
    assert run_graph(nodes, tmp_path)["verdict"] == "PASS"


def test_native_trailing_wait_is_still_unterminated(tmp_path):
    nodes = [action("e1", None, "email", nxt="w1"), action("w1", "e1", "wait")]
    assert "UNTERMINATED" in kinds(run_graph(nodes, tmp_path))


def test_native_condition_with_one_arm_still_fails(tmp_path):
    nodes = native_good()
    nodes[0]["next"] = ["a1"]
    k = kinds(run_graph(nodes, tmp_path))
    assert "MALFORMED_BRANCH" in k and "UNWIRED_BRANCH" in k


def test_native_condition_pointing_at_a_missing_arm_still_fails(tmp_path):
    nodes = native_good()
    nodes[0]["next"] = ["a1", "ghost"]
    assert "DANGLING" in kinds(run_graph(nodes, tmp_path))


def test_native_condition_arm_owned_by_another_node_still_fails(tmp_path):
    nodes = native_good()
    nodes[2]["parent"] = nodes[2]["parentKey"] = "e1"
    assert "MALFORMED_BRANCH" in kinds(run_graph(nodes, tmp_path))


def test_plain_export_leaf_without_canvas_is_still_unterminated(tmp_path):
    nodes = [{"id": "e1", "type": "email", "name": "x", "parentKey": None, "next": "e2"},
             {"id": "e2", "type": "email", "name": "y", "parentKey": "e1"}]
    assert "UNTERMINATED" in kinds(run_graph(nodes, tmp_path))


def test_legacy_two_entry_branches_map_still_validated(tmp_path):
    nodes = [{"id": "i", "type": "if_else", "name": "i", "parentKey": None,
              "branches": {"yes": "a"}}, {"id": "a", "type": "end", "parentKey": "i"}]
    assert "MALFORMED_BRANCH" in kinds(run_graph(nodes, tmp_path))


# ---- WF-25 / WF-16 read the saved window, Stop on Response and native tag conditions ----

def export(window=None, stop=False, tz="account", conds=None):
    steps = [{"id": "s1", "type": "sms", "name": "Send", "attributes": {"body": "hi"}}]
    if conds:
        steps.insert(0, {"id": "c1", "type": "if_else", "attributes": {"branches": [
            {"segments": [{"conditions": conds}]}]}})
    return {"stopOnResponse": stop, "window": window, "timezone": tz,
            "workflowData": {"templates": steps}}


WIN = {"condition": "when", "start": "09:00", "end": "21:00", "days": [0, 1, 2, 3, 4, 5, 6]}


def test_saved_window_and_stop_on_response_are_read():
    r = sms.verify_saved_export(export(WIN, True), "operational")
    assert r["found"]["quiet_hours"] is True and r["stop_on_response"] is True


def test_no_window_is_still_missing():
    r = sms.verify_saved_export(export(None, False), "operational")
    assert r["found"]["quiet_hours"] is False and r["stop_on_response"] is False


def test_window_wider_than_quiet_hours_is_rejected():
    wide = dict(WIN, start="06:00")
    assert sms.verify_saved_export(export(wide), "operational")["found"]["quiet_hours"] is False
    late = dict(WIN, end="23:00")
    assert sms.verify_saved_export(export(late), "operational")["found"]["quiet_hours"] is False


def test_window_not_in_when_mode_is_rejected():
    assert sms.verify_saved_export(
        export(dict(WIN, condition="except")), "operational")["found"]["quiet_hours"] is False


def test_native_tag_conditions_satisfy_suppression_only_when_absent():
    absent = {"conditionType": "contact_detail", "conditionSubType": "tags",
              "conditionOperator": "index-of-false", "conditionValue": ["sms-opted-out"]}
    present = dict(absent, conditionOperator="index-of-true")
    assert sms.verify_saved_export(export(conds=[absent]), "operational")["found"]["suppression"] is True
    assert sms.verify_saved_export(export(conds=[present]), "operational")["found"]["suppression"] is False
    other = dict(absent, conditionValue=["some-other-tag"])
    assert sms.verify_saved_export(export(conds=[other]), "operational")["found"]["suppression"] is False


def test_legacy_attribute_conditions_still_read():
    legacy = {"steps": [{"id": "g", "type": "filter", "attributes": {"conditions": [
        {"type": "tag_absent", "value": "sms-opted-out"}]}},
        {"id": "s", "type": "sms", "attributes": {}}]}
    assert sms.verify_saved_export(legacy, "operational")["found"]["suppression"] is True


# ---- WF-18: the manifest generator reads the location, never the export ----

def test_manifest_built_from_live_reads_and_includes_names_and_ids():
    data = {
        "tags": {"tags": [{"id": "t1", "name": "buyer"}]},
        "custom_fields": {"customFields": [{"id": "f1", "name": "Plan", "fieldKey": "contact.plan"}]},
        "custom_values": [{"id": "v1", "name": "Link"}],
        "calendars": {"calendars": [{"id": "c1", "name": "Call"}]},
        "pipelines": {"pipelines": [{"id": "p1", "name": "Sales"}]},
    }
    m = dm.build_manifest(lambda label, argv: data[label])
    assert {"buyer", "t1"} <= set(m["tags"])
    assert {"Plan", "plan", "f1"} <= set(m["custom_fields"])
    assert m["source"] == "live-read"


def test_manifest_refuses_when_a_live_read_fails():
    def fetch(label, argv):
        if label == "calendars":
            raise RuntimeError("read failed")
        return []
    try:
        dm.build_manifest(fetch)
    except RuntimeError:
        return
    raise AssertionError("a failed read must not yield a manifest")


def test_deps_gate_still_fails_for_a_tag_the_location_lacks(tmp_path):
    export_file = tmp_path / "e.json"
    export_file.write_text(json.dumps({"workflowData": {"templates": [
        {"id": "c", "type": "if_else", "attributes": {"branches": [{"segments": [{"conditions": [
            {"conditionType": "contact_detail", "conditionSubType": "tags",
             "conditionOperator": "index-of-false", "conditionValue": ["ghost-tag"]}]}]}]}}]}}))
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"tags": ["buyer"]}))
    proc = subprocess.run([sys.executable, "-I", str(TOOLS / "validate_graph.py"), "deps",
                           "--export", str(export_file), "--deps", str(manifest)],
                          capture_output=True, text=True, timeout=60)
    report = json.loads(proc.stdout)
    assert report["verdict"] == "FAIL" and {"kind": "tags", "name": "ghost-tag"} in report["missing"]
    manifest.write_text(json.dumps({"tags": ["ghost-tag"]}))
    proc = subprocess.run([sys.executable, "-I", str(TOOLS / "validate_graph.py"), "deps",
                           "--export", str(export_file), "--deps", str(manifest)],
                          capture_output=True, text=True, timeout=60)
    assert json.loads(proc.stdout)["verdict"] == "PASS"
