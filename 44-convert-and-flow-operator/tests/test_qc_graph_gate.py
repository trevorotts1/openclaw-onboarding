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
