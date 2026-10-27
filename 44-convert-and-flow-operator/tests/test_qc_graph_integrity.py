import json
import os
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
    assert "2 orphans" in evidence
    assert "0 orphans" not in items["WF-15"]["observed"]


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
    assert "1 orphans" in _evidence(items["WF-15"])


def test_pure_unverified_is_never_success(tmp_path):
    report = {
        "verdict": "UNVERIFIED",
        "nodes": 2,
        "edges": 1,
        "root": "n1",
        "failures": [],
        "orphans": 0,
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
    result, wf24 = _wf24_result(tmp_path, _wf24_export(target="n1"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert wf24["status"] == "PASS"


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
