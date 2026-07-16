#!/usr/bin/env python3
"""Offline tests for the n8n plaintext-secret guard and vault transformer."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
SCANNER = REPO_ROOT / "scripts" / "qc-assert-no-n8n-plaintext-secrets.sh"
TRANSFORMER = (
    REPO_ROOT
    / "58-podcast-production-engine"
    / "scripts"
    / "vault_n8n_credential.py"
)
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "n8n-plaintext-secrets.fixture.json"

FAKE_LITERALS = {
    "FAKE_TEST_CLIENT_ID_000",
    "sk_test_FAKE_0000000000",
    "FAKE_TEST_SET_CLIENT_ID_000",
    "FAKE_TEST_HTTP_CLIENT_ID_000",
    "sk_test_FAKE_HTTP_0000000000",
}


def run_scanner(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCANNER), "--repo-root", str(root)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_scanner_fails_on_fake_plaintext_fixture_without_printing_values(tmp_path: Path) -> None:
    planted = tmp_path / "planted.workflow.json"
    shutil.copyfile(FIXTURE, planted)

    result = run_scanner(tmp_path)
    report = result.stdout + result.stderr

    assert result.returncode == 1
    assert "planted.workflow.json" in report
    assert "Fixture Code Node" in report
    assert "client_id" in report
    assert "client_secret" in report
    for fake_literal in FAKE_LITERALS:
        assert fake_literal not in report


def test_scanner_passes_both_real_broker_workflows(tmp_path: Path) -> None:
    real_workflows = (
        REPO_ROOT
        / "58-podcast-production-engine"
        / "config"
        / "n8n"
        / "podbean-broker.workflow.json",
        REPO_ROOT
        / "59-anthology-engine"
        / "config"
        / "n8n"
        / "anthology-drive-broker.workflow.json",
    )
    for workflow in real_workflows:
        shutil.copyfile(workflow, tmp_path / workflow.name)

    result = run_scanner(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 workflow file(s) checked" in result.stdout


def test_transformer_rewrites_fixture_and_rewritten_workflow_passes_scanner(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.fixture.json"
    output = tmp_path / "vaulted.workflow.json"
    shutil.copyfile(FIXTURE, source)

    transformed = subprocess.run(
        [
            sys.executable,
            str(TRANSFORMER),
            str(source),
            "Podbean BlackCEO (client_credentials)",
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    report = transformed.stdout + transformed.stderr
    assert transformed.returncode == 0, report
    assert "Fixture Code Node" in report
    assert "Fixture Set Node" in report
    assert "Fixture HTTP Request Node" in report
    assert "PODBEAN_CLIENT_ID" in report
    assert "PODBEAN_CLIENT_SECRET" in report
    for fake_literal in FAKE_LITERALS:
        assert fake_literal not in report

    rewritten_text = output.read_text(encoding="utf-8")
    for fake_literal in FAKE_LITERALS:
        assert fake_literal not in rewritten_text

    rewritten = json.loads(rewritten_text)
    nodes = {node["name"]: node for node in rewritten["nodes"]}
    code = nodes["Fixture Code Node"]["parameters"]["jsCode"]
    assert "const client_id = $env.PODBEAN_CLIENT_ID" in code
    assert "clientSecret = $env.PODBEAN_CLIENT_SECRET" in code

    set_assignment = nodes["Fixture Set Node"]["parameters"]["assignments"]["assignments"][0]
    assert set_assignment["value"] == "={{ $env.PODBEAN_CLIENT_ID }}"

    http_node = nodes["Fixture HTTP Request Node"]
    remaining_names = {
        parameter["name"]
        for parameter in http_node["parameters"]["bodyParameters"]["parameters"]
    }
    assert remaining_names == {"grant_type"}
    assert http_node["parameters"]["authentication"] == "predefinedCredentialType"
    assert http_node["parameters"]["nodeCredentialType"] == "httpBasicAuth"
    assert http_node["credentials"]["httpBasicAuth"] == {
        "id": "REPLACE_WITH_PODBEAN_CREDENTIAL_ID",
        "name": "Podbean BlackCEO (client_credentials)",
    }

    clean = run_scanner(tmp_path)
    assert clean.returncode == 0, clean.stdout + clean.stderr


def test_scanner_allows_expressions_env_references_and_credential_placeholders(
    tmp_path: Path,
) -> None:
    workflow = {
        "name": "Safe references fixture",
        "nodes": [
            {
                "name": "Safe Node",
                "type": "n8n-nodes-base.set",
                "parameters": {
                    "client_id": "={{ $env.PODBEAN_CLIENT_ID }}",
                    "clientSecret": "REPLACE_WITH_PODBEAN_CREDENTIAL_ID",
                },
            }
        ],
        "active": False,
    }
    (tmp_path / "safe.workflow.json").write_text(json.dumps(workflow), encoding="utf-8")

    result = run_scanner(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
