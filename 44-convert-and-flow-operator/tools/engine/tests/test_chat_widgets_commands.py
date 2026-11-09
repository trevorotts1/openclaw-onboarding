"""Offline tests for the WF31 command module (WF03 registers it)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from click.testing import CliRunner

_ENGINE = Path(__file__).resolve().parents[1]
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

from cli_anything.gohighlevel.public import chat_widgets_commands as commands  # noqa: E402

SNIPPET = (
    '<script src="https://widgets.example.test/loader.js" '
    'data-widget-id="wid_0001"></script>'
)


def _root():
    @click.group()
    def root():
        pass

    commands.register(root)
    return root


def _write(path: Path, value) -> str:
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def test_embed_plan_writes_install_and_rollback(tmp_path):
    page = {"sections": [{"id": "s"}], "trackingCode": {"footerCode": ""}}
    embed = {
        "widget_id": "wid_0001",
        "script_url": "https://widgets.example.test/loader.js",
        "snippet": SNIPPET,
        "provenance": "captured_ui",
        "evidence_ref": "evidence/WF31/embed.json",
    }
    out = tmp_path / "out.json"
    rollback = tmp_path / "rollback.json"
    result = CliRunner().invoke(
        _root(),
        [
            "widgets",
            "embed-plan",
            "--embed-file",
            _write(tmp_path / "embed.json", embed),
            "--page-file",
            _write(tmp_path / "page.json", page),
            "--out",
            str(out),
            "--rollback-out",
            str(rollback),
        ],
    )
    assert result.exit_code == 0, result.output
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert SNIPPET in saved["page_data"]["trackingCode"]["footerCode"]
    assert json.loads(rollback.read_text(encoding="utf-8")) == page


def test_embed_plan_refuses_a_duplicate(tmp_path):
    page = {"sections": [], "trackingCode": {"footerCode": SNIPPET}}
    embed = {
        "widget_id": "wid_0001",
        "script_url": "https://widgets.example.test/loader.js",
        "snippet": SNIPPET,
        "provenance": "captured_ui",
        "evidence_ref": "evidence/WF31/embed.json",
    }
    result = CliRunner().invoke(
        _root(),
        [
            "widgets",
            "embed-plan",
            "--embed-file",
            _write(tmp_path / "embed.json", embed),
            "--page-file",
            _write(tmp_path / "page.json", page),
            "--out",
            str(tmp_path / "out.json"),
            "--rollback-out",
            str(tmp_path / "rollback.json"),
        ],
    )
    assert result.exit_code != 0
    assert "widget_already_installed" in result.output


def test_verify_thread_fails_on_bubble_only(tmp_path):
    evidence = {
        "widget_id": "wid_0001",
        "location_id": "loc_test",
        "thread_id": "",
        "inbox_id": "",
        "responder_kind": "ai",
        "responder_id": "",
        "messages": [],
        "visible_bubble_observed": True,
    }
    result = CliRunner().invoke(
        _root(),
        [
            "widgets",
            "verify-thread",
            "--widget-id",
            "wid_0001",
            "--location-id",
            "loc_test",
            "--responder-kind",
            "ai",
            "--evidence-file",
            _write(tmp_path / "evidence.json", evidence),
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["passed"] is False
    assert "inbox_id_present" in payload["failed"]


def test_verify_thread_passes_when_thread_inbox_and_responder_match(tmp_path):
    evidence = {
        "widget_id": "wid_0001",
        "location_id": "loc_test",
        "thread_id": "thread_1",
        "inbox_id": "inbox_1",
        "responder_kind": "ai",
        "responder_id": "bot_1",
        "messages": [
            {"direction": "inbound", "body": "marker", "message_id": "m1"},
            {"direction": "outbound", "body": "reply", "message_id": "m2"},
        ],
    }
    result = CliRunner().invoke(
        _root(),
        [
            "widgets",
            "verify-thread",
            "--widget-id",
            "wid_0001",
            "--location-id",
            "loc_test",
            "--responder-kind",
            "ai",
            "--evidence-file",
            _write(tmp_path / "evidence.json", evidence),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["passed"] is True
