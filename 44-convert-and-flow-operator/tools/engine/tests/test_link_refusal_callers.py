"""Verify workflow CLI refuses structurally broken graphs before writes."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from cli_anything.gohighlevel.gohighlevel_cli import cli
from cli_anything.gohighlevel.internal.adapter_types import AdapterResult


class RecordingClient:
    def __init__(self):
        self.location_id = "LOC001"
        self.write_calls = []
        self._step_index = 0

    def put_workflow(self, workflow_id, body):
        self.write_calls.append(("put_workflow", workflow_id, body))
        return AdapterResult(ok=True, data={"id": workflow_id})

    def get_workflow(self, workflow_id):
        return AdapterResult(
            ok=True,
            data={
                "id": workflow_id,
                "name": "Existing workflow",
                "version": 1,
                "workflowData": {"templates": []},
            },
        )

    def request(
        self, method, path, body=None, workflow_name="",
        _apply_step_backoff=False,
    ):
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            self.write_calls.append((method, path, body))
        if method.upper() == "GET":
            return {
                "id": "WF1",
                "name": "Existing workflow",
                "version": 1,
                "workflowData": {"templates": []},
            }
        return {"id": "WF1"}

    def reset_step_index(self):
        self._step_index = 0

    def create_location_tag(self, *args, **kwargs):
        self.write_calls.append(("create_location_tag", args, kwargs))
        return AdapterResult(ok=True, data={"id": "TAG1"})


def _invoke(tmp_path, monkeypatch, client, args):
    monkeypatch.setenv("GHL_FIREBASE_REFRESH_TOKEN", "fake-refresh")
    monkeypatch.setenv("CAF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAF_ALLOWED_LOCATION_IDS", "LOC001")
    monkeypatch.setenv("CAF_APPROVAL_TOKEN", "test-token")
    monkeypatch.delenv("CAF_DRY_RUN", raising=False)

    monkeypatch.setattr(
        "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
        lambda *args, **kwargs: client,
    )
    return CliRunner().invoke(
        cli,
        ["--experimental", "--location-id", "LOC001", *args],
    )


def test_create_step_refuses_unlinked_branch(tmp_path, monkeypatch):
    client = RecordingClient()
    output_file = tmp_path / "steps.json"
    original = json.dumps(
        [
            {
                "id": "if1",
                "type": "if_else",
                "name": "Branch",
                "order": 0,
                "attributes": {},
            }
        ],
        indent=2,
    ).encode()
    output_file.write_bytes(original)

    result = _invoke(
        tmp_path,
        monkeypatch,
        client,
        [
            "workflows", "create-step",
            "--type", "email",
            "--name", "X",
            "--subject", "S",
            "--body", "B",
            "--output-file", str(output_file),
        ],
    )

    assert result.exit_code != 0, result.output
    assert 'no authored branch targets' in result.output
    assert "if1" in result.output
    assert client.write_calls == []
    assert output_file.read_bytes() == original


def test_create_n8n_refuses_and_writes_nothing(tmp_path, monkeypatch):
    client = RecordingClient()
    monkeypatch.setattr(
        "cli_anything.gohighlevel.utils.workflow_builder.link_steps",
        lambda steps: ([], ["if1"]),
    )

    result = _invoke(
        tmp_path,
        monkeypatch,
        client,
        [
            "workflows", "create-n8n",
            "--name", "N",
            "--webhook-url", "https://example.com/h",
        ],
    )

    assert result.exit_code != 0, result.output
    assert 'no authored branch targets' in result.output
    assert "if1" in result.output
    assert client.write_calls == []


def test_update_refuses_broken_graph_before_put(tmp_path, monkeypatch):
    client = RecordingClient()
    input_file = tmp_path / "update.json"
    input_file.write_text(
        json.dumps(
            {
                "name": "Broken workflow",
                "version": 1,
                "workflowData": {
                    "templates": [
                        {
                            "id": "if1",
                            "type": "if_else",
                            "name": "Branch",
                            "parentKey": None,
                            "order": 0,
                            "attributes": {},
                            "branches": {
                                "true": "missing-node",
                                "false": "missing-node-2",
                            },
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = _invoke(
        tmp_path,
        monkeypatch,
        client,
        [
            "workflows", "update",
            "--workflow-id", "WF1",
            "--from-json", str(input_file),
        ],
    )

    assert result.exit_code != 0, result.output
    assert client.write_calls == []
    assert 'refusing to write workflow' in result.output
