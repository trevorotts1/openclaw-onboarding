import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
QC_SCRIPT = ROOT / "qc-built-workflow.sh"
TWO_ORPHANS = ROOT / "tests/fixtures/graph/two_orphans.json"


def _linear_export():
    return {
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
        "triggers": [{"id": "T1", "type": "form_submitted", "targetActionId": "n1"}],
    }


def _wf24_export(target="n1", decoy=None):
    export = _linear_export()
    export["triggers"] = [{"id": "T1", "type": "form_submitted"}]
    if target is not None:
        export["triggers"][0]["targetActionId"] = target
    if decoy is not None:
        export["workflowData"]["templates"][0]["attributes"]["targetActionId"] = decoy
    return export


def _wf24_result(tmp_path, export):
    result = _run(tmp_path, export)
    return result, _items(result)["WF-24"]


def _setup(tmp_path, export):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
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
    return env, bin_dir


def _manifest(tmp_path):
    path = tmp_path / "deps.json"
    path.write_text("{}", encoding="utf-8")
    return path


def _fake_validator(tmp_path, payload, exit_code=0):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)

    json_file = tmp_path / "validator.json"
    json_file.write_text(payload, encoding="utf-8")

    validator = bin_dir / "fake-validator.py"
    validator.write_text(
        'import os, sys\n'
        'with open(os.environ["QC_GRAPH_JSON_FILE"], encoding="utf-8") as handle:\n'
        '    sys.stdout.write(handle.read())\n'
        'sys.exit(int(os.environ.get("QC_GRAPH_EXIT", "0")))\n',
        encoding="utf-8",
    )
    validator.chmod(0o755)

    return {
        "QC_GRAPH_VALIDATOR": str(validator),
        "QC_GRAPH_JSON_FILE": str(json_file),
        "QC_GRAPH_EXIT": str(exit_code),
    }


def _run(tmp_path, export, validator_env=None):
    env, _ = _setup(tmp_path, export)
    env["PATH"] = str(tmp_path / "bin") + os.pathsep + env["PATH"]
    env.update(validator_env or {})

    result = subprocess.run(
        [
            "bash",
            str(QC_SCRIPT),
            "WFTEST009",
            "--deps",
            str(_manifest(tmp_path)),
            "--json",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result


def _with_sms_guard(export):
    """Put the SMS compliance rules (S44-32) in front of the graph as saved native conditions, so a
    fixture that carries an SMS step can reach exit 0. The old root keeps its id; the guard becomes the root."""
    templates = export["workflowData"]["templates"]
    root = next(t for t in templates if t.get("parentKey") in (None, ""))
    guard = {"id": "g1", "type": "filter", "name": "Compliance guard", "parentKey": None, "next": root["id"],
             "attributes": {"conditions": [
                 {"type": "tag_present", "value": "sms-subscribed"},
                 {"type": "tag_absent", "value": "sms-opted-out"},
                 {"type": "field_lt", "field": "contact_marketing_sends", "value": 5},
                 {"type": "time_window", "start": "08:00", "end": "21:00", "timezone": "recipient_local"},
                 {"type": "deadline", "anchor": "doors_close_at"}]}}
    out = json.loads(json.dumps(export))
    out["workflowData"]["templates"] = [guard] + out["workflowData"]["templates"]
    for t in out["workflowData"]["templates"][1:]:
        if t["id"] == root["id"]:
            t["parentKey"] = "g1"
    for trig in out.get("triggers", []):
        if trig.get("targetActionId") == root["id"]:
            trig["targetActionId"] = "g1"
    return out


def _gated_run(tmp_path, export):
    """Run QC with everything the S44-24 exit gate requires: signed PLAN MODE file, signed QC session, grades."""
    # draft/inactive/no-re-entry state so WF-4/5/6 machine-assert against DRAFT + ONCE
    export = {"status": "draft", "active": False, "allowMultiple": False, **_with_sms_guard(export)}
    env, _ = _setup(tmp_path, export)
    tree = tmp_path / "tree"
    skill = tree / "44-convert-and-flow-operator"
    verifier_dir = tree / "shared-utils" / "signature_launch_contract"
    skill.mkdir(parents=True)
    verifier_dir.mkdir(parents=True)
    script = skill / "qc-built-workflow.sh"
    shutil.copy2(QC_SCRIPT, script)
    (skill / "tools").symlink_to(ROOT / "tools")
    (skill / "automation-templates").symlink_to(ROOT / "automation-templates")
    (verifier_dir / "approval_record.py").write_text(
        "class ApprovalRefused(Exception):\n"
        "    def __init__(self, code, message=''):\n"
        "        super().__init__(code + ': ' + message)\n"
        "        self.code = code\n"
        "\n"
        "GOOD = {'appr-good-0001': ('launch_plan_build', {'publish:DRAFT', 'reentry:ONCE'}),\n"
        "        'appr-qc-b-0001': ('qc_session', {'qc_model:qc-model-b', 'qc_session:sess-b-0001'})}\n"
        "\n"
        "def verify(approval_id, kind, plan_hash, scope, **kw):\n"
        "    entry = GOOD.get(approval_id)\n"
        "    if entry is None or kind != entry[0] or plan_hash != 'abcd1234':\n"
        "        raise ApprovalRefused('APPROVAL-NOT-FROM-AUTHORITY', 'unknown approval')\n"
        "    if not set(scope) <= entry[1]:\n"
        "        raise ApprovalRefused('APPROVAL-SCOPE', 'scope not covered')\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "approval_id": "appr-good-0001",
                "plan_hash": "abcd1234",
                "publish_intent": "DRAFT",
                "re_entry": "ONCE",
                "build_model": "build-model-a",
            }
        ),
        encoding="utf-8",
    )
    qc_session = tmp_path / "qc-session.json"
    qc_session.write_text(
        json.dumps({"approval_id": "appr-qc-b-0001", "plan_hash": "abcd1234",
                    "qc_model": "qc-model-b", "session_id": "sess-b-0001"}),
        encoding="utf-8",
    )
    items = "WF-1 WF-2 WF-8 WF-9 WF-10 WF-11 WF-13 WF-14 WF-16 WF-17 WF-19 WF-20".split()
    grades = tmp_path / "grades.json"
    grades.write_text(
        json.dumps(
            {
                "workflow_id": "WFTEST009",
                "grades": {i: {"grade": "PASS", "observed": "read from export"} for i in items},
            }
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        [
            "bash", str(script), "WFTEST009",
            "--deps", str(_manifest(tmp_path)), "--json",
            "--publish-intent", "DRAFT", "--re-entry", "ONCE",
            "--plan-mode-file", str(plan), "--qc-session", str(qc_session),
            "--grades", str(grades),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _items(result):
    assert result.stdout, f"empty stdout; stderr={result.stderr}"
    try:
        return json.loads(result.stdout)["items"]
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"QC stdout is not valid JSON: {exc}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )


def _evidence(item):
    return item["observed"] + " " + item["notes"]


def test_wf15_reports_real_orphan_count_and_fails(tmp_path):
    export = json.loads(TWO_ORPHANS.read_text(encoding="utf-8"))
    result = _run(tmp_path, export)
    items = _items(result)

    assert result.returncode == 1, result.stdout + result.stderr
    assert items["WF-15"]["status"] == "FAIL"
    evidence = _evidence(items["WF-15"])
    assert "orphans=2" in evidence
    assert "orphans=0" not in items["WF-15"]["observed"]


def test_wf15_fails_on_truncated_validator_json(tmp_path):
    validator_env = _fake_validator(
        tmp_path,
        "{not valid json",
        exit_code=0,
    )
    result = _run(tmp_path, _linear_export(), validator_env)
    items = _items(result)

    assert result.returncode == 1, result.stdout + result.stderr
    assert items["WF-15"]["status"] == "FAIL"
    assert "malformed" in _evidence(items["WF-15"]).lower()
    assert items["WF-15"]["status"] != "PASS"


def test_wf15_fails_when_orphans_field_missing(tmp_path):
    report = {
        "verdict": "PASS",
        "nodes": 1,
        "edges": 0,
        "root": "n1",
        "failures": [],
        # Present so this test isolates the MISSING `orphans` case rather than
        # tripping over two absent required fields at once.
        "branches": 0,
        "unverified": [],
    }
    validator_env = _fake_validator(
        tmp_path,
        json.dumps(report),
        exit_code=0,
    )
    result = _run(tmp_path, _linear_export(), validator_env)
    items = _items(result)

    assert result.returncode == 1, result.stdout + result.stderr
    assert items["WF-15"]["status"] == "FAIL"
    evidence = _evidence(items["WF-15"]).lower()
    assert "orphans" in evidence
    assert items["WF-15"]["status"] != "PASS"


def test_failures_plus_unverified_is_overall_fail(tmp_path):
    report = {
        "verdict": "UNVERIFIED",
        "nodes": 2,
        "edges": 0,
        "root": "n1",
        "failures": [
            {
                "kind": "ORPHAN",
                "node_id": "n2",
                "name": "Orphan",
                "type": "wait",
            }
        ],
        "orphans": 1,
        "branches": 1,
        "unverified": [
            {
                "node_id": "b1",
                "reason": "branch_targets_not_exposed",
            }
        ],
    }
    validator_env = _fake_validator(
        tmp_path,
        json.dumps(report),
        exit_code=2,
    )
    result = _run(tmp_path, _linear_export(), validator_env)
    items = _items(result)

    assert result.returncode == 1, result.stdout + result.stderr
    assert items["WF-15"]["status"] == "FAIL"
    assert "orphans=1" in _evidence(items["WF-15"])


def test_pure_unverified_is_never_success(tmp_path):
    report = {
        "verdict": "UNVERIFIED",
        "nodes": 2,
        "edges": 1,
        "root": "n1",
        "failures": [],
        "orphans": 0,
        "branches": 1,
        "unverified": [
            {
                "node_id": "b1",
                "reason": "branch_targets_not_exposed",
            }
        ],
    }
    validator_env = _fake_validator(
        tmp_path,
        json.dumps(report),
        exit_code=2,
    )
    result = _run(tmp_path, _linear_export(), validator_env)
    items = _items(result)

    # This stub export has no trigger and the fake validator also serves the deps
    # subcommand, so WF-3/WF-18 fail mechanically and exit 1 pre-empts the graph
    # UNVERIFIED exit-2. The contract proved here is that UNVERIFIED is never 0;
    # with a clean export the graph gate alone returns 2.
    assert result.returncode != 0, result.stdout + result.stderr
    assert items["WF-23"]["status"] == "REQUIRES_HUMAN_REVIEW"
    assert items["WF-15"]["status"] == "REQUIRES_HUMAN_REVIEW"


def test_wf24_passes_when_trigger_targets_root(tmp_path):
    result = _gated_run(tmp_path, _wf24_export(target="n1"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert _items(result)["WF-24"]["status"] == "PASS"
    assert json.loads(result.stdout)["exit_gate"] == "PASS"


def test_wf24_fails_when_trigger_targets_non_root(tmp_path):
    result, wf24 = _wf24_result(tmp_path, _wf24_export(target="n2"))
    evidence = _evidence(wf24)
    assert result.returncode == 1, result.stdout + result.stderr
    assert wf24["status"] == "FAIL"
    assert "n2" in evidence and "n1" in evidence
    assert "trigger_target_mismatch" in evidence


def test_wf24_fails_when_trigger_has_no_target(tmp_path):
    result, wf24 = _wf24_result(tmp_path, _wf24_export(target=None))
    assert result.returncode == 1, result.stdout + result.stderr
    assert wf24["status"] == "FAIL"
    assert "trigger_evidence_absent" in _evidence(wf24)


def test_wf24_ignores_decoy_target_outside_trigger(tmp_path):
    # The decoy lives in a template, which WF-24 never scans. WF-23 (another
    # lane's validator) still deep-scans and reports ROOT, so only WF-24 is
    # asserted here; the exit code is not this test's contract.
    result, wf24 = _wf24_result(
        tmp_path, _wf24_export(target="n1", decoy="n9")
    )
    assert wf24["status"] == "PASS", result.stdout + result.stderr
    assert wf24["observed"].endswith("targetActionId=n1 root=n1 trigger=$.triggers[0]")


def test_wf24_missing_trigger_target_fails_despite_decoy(tmp_path):
    result, wf24 = _wf24_result(
        tmp_path, _wf24_export(target=None, decoy="n9")
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert wf24["status"] == "FAIL"
    assert "trigger_evidence_absent" in _evidence(wf24)
