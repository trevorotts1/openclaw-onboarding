"""FIX-13 (M12) — OWNER DELIVERY LINK tests.

After registration the OWNER must receive the deck LOCATION via the CC report-back
loop. This test proves the send-log record carries BOTH the deck link and the
confirmed gateway message id (the QC gate: "the deck link is in the sent-message
record"), and the honest-undeliverable fallback when no owner target resolves.

Standard library + pytest, no network. Flat file beside the code it tests (same
convention as test_client_report_confirmation.py). The runner module is loaded by
file path and never executes main() (SystemExit guarded).
"""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.join(_HERE, "..")
sys.path.insert(0, _SCRIPTS)
_spec = importlib.util.spec_from_file_location(
    "rsd", os.path.join(_SCRIPTS, "run_signature_deck.py"))
rsd = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(rsd)  # type: ignore[union-attr]
except SystemExit:
    pass


def _mk_run(tmp_path: Path, *, tele_url: str = "", ghl_url: str = "") -> Path:
    """Build a governed run dir with optional deck-location sources."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "checkpoints").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text(
        json.dumps({"deck_slug": "sig-deck", "title": "Signature Deck"}))
    if tele_url:
        bundle = tmp_path / "bundle"
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / "teleprompter_publish.json").write_text(json.dumps(
            {"status": "published", "public_url": tele_url}))
        (rd / "working" / "checkpoints" / "process_manifest.json").write_text(
            json.dumps({"bundleDir": str(bundle)}))
    if ghl_url:
        (rd / "working" / "checkpoints" / "media_library.json").write_text(
            json.dumps({"pptx_ghl_url": ghl_url}))
    return rd


def _records(rd: Path) -> list:
    p = rd / "working" / "checkpoints" / "client_reports.json"
    if not p.exists():
        return []
    return json.loads(p.read_text())


# --- SUCCESS PATH: the send is confirmed, the record carries the deck link + msg id ---

def test_delivery_link_success_teleprompter_url(monkeypatch, tmp_path):
    """A confirmed send with a teleprompter public_url records a delivery_link row
    whose text contains the deck link and whose gateway_msg_id is the confirmed id."""
    rd = _mk_run(tmp_path, tele_url="https://teleprompter.zerohumanworkforce.com/x/sig-deck/teleprompter.html")
    monkeypatch.setattr(rsd, "_resolve_owner_route", lambda: ("telegram", "12345"))
    monkeypatch.setattr(rsd, "_send_owner_message",
                        lambda _text: ("msg-42", True))
    mid = rsd.emit_delivery_link(rd)
    assert mid == "msg-42"
    recs = _records(rd)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["phase_id"] == "P9-DELIVER"
    assert rec["kind"] == "delivery_link"
    assert rec["sent"] is True
    assert rec["gateway_msg_id"] == "msg-42"
    # The deck link IS in the sent-message record (the QC gate).
    assert "https://teleprompter.zerohumanworkforce.com/x/sig-deck/teleprompter.html" in rec["text"]
    assert "Deck link:" in rec["text"]
    assert rec["undeliverable"] == ""


def test_delivery_link_success_ghl_url(monkeypatch, tmp_path):
    """When no teleprompter record exists, the GHL deck public URL is the link."""
    rd = _mk_run(tmp_path, ghl_url="https://storage.googleapis.com/msgsndr/x/deck.pptx")
    monkeypatch.setattr(rsd, "_resolve_owner_route", lambda: ("telegram", "12345"))
    monkeypatch.setattr(rsd, "_send_owner_message",
                        lambda _text: ("msg-99", True))
    rsd.emit_delivery_link(rd)
    rec = _records(rd)[0]
    assert "https://storage.googleapis.com/msgsndr/x/deck.pptx" in rec["text"]
    assert rec["gateway_msg_id"] == "msg-99"
    assert rec["sent"] is True


def test_delivery_link_route_prefers_teleprompter_over_ghl(monkeypatch, tmp_path):
    """The teleprompter live URL wins over the GHL URL (most owner-actionable)."""
    rd = _mk_run(tmp_path, tele_url="https://teleprompter.zerohumanworkforce.com/a.html",
                 ghl_url="https://storage.googleapis.com/msgsndr/y/deck.pptx")
    monkeypatch.setattr(rsd, "_resolve_owner_route", lambda: ("telegram", "12345"))
    monkeypatch.setattr(rsd, "_send_owner_message",
                        lambda _text: ("msg-1", True))
    rsd.emit_delivery_link(rd)
    rec = _records(rd)[0]
    assert "https://teleprompter.zerohumanworkforce.com/a.html" in rec["text"]
    assert "Deck link: https://teleprompter.zerohumanworkforce.com/a.html" in rec["text"]


def test_delivery_link_local_fallback(monkeypatch, tmp_path):
    """No URL sources -> the local delivery/*-FINAL package path is named."""
    rd = _mk_run(tmp_path)
    pkg = rd / "delivery" / "sig-deck-FINAL"
    pkg.mkdir(parents=True)
    (pkg / "sig-deck-FINAL.pptx").write_bytes(b"x")
    monkeypatch.setattr(rsd, "_resolve_owner_route", lambda: ("telegram", "12345"))
    monkeypatch.setattr(rsd, "_send_owner_message",
                        lambda _text: ("msg-7", True))
    rsd.emit_delivery_link(rd)
    rec = _records(rd)[0]
    assert str(pkg) in rec["text"]
    assert rec["gateway_msg_id"] == "msg-7"


def test_delivery_link_sends_through_report_back_transport(monkeypatch, tmp_path):
    """The send MUST go through openclaw message send (never a hardcoded chat)."""
    rd = _mk_run(tmp_path, tele_url="https://teleprompter.zerohumanworkforce.com/a.html")
    sent_to = []
    monkeypatch.setattr(rsd, "_resolve_owner_route",
                        lambda: ("telegram", "operator-target"))
    monkeypatch.setattr(rsd, "_send_owner_message",
                        lambda text: sent_to.append(text) or ("op-1", True))
    rsd.emit_delivery_link(rd)
    assert len(sent_to) == 1
    # No hardcoded client chat id anywhere in the composed message.
    assert "8384606872" not in sent_to[0]


# --- UNDELIVERABLE PATHS: no owner target / send failure -> honest record, no raise ---

def test_delivery_link_no_owner_target(monkeypatch, tmp_path):
    rd = _mk_run(tmp_path, ghl_url="https://storage.googleapis.com/msgsndr/z/deck.pptx")
    monkeypatch.setattr(rsd, "_resolve_owner_route", lambda: (None, None))
    monkeypatch.setattr(rsd, "_send_owner_message", lambda _text: ("", False))
    mid = rsd.emit_delivery_link(rd)  # must never raise
    assert mid is None
    rec = _records(rd)[0]
    assert rec["sent"] is False
    assert rec["undeliverable"] == "no owner target configured"
    assert rec["gateway_msg_id"] == ""


def test_delivery_link_send_failed(monkeypatch, tmp_path):
    rd = _mk_run(tmp_path, tele_url="https://teleprompter.zerohumanworkforce.com/a.html")
    monkeypatch.setattr(rsd, "_resolve_owner_route", lambda: ("telegram", "12345"))
    monkeypatch.setattr(rsd, "_send_owner_message", lambda _text: ("", False))
    mid = rsd.emit_delivery_link(rd)
    assert mid is None
    rec = _records(rd)[0]
    assert rec["sent"] is False
    assert rec["undeliverable"] == "gateway send did not confirm"


# --- REAL JSON-PARSE PATH (NOT MOCKED) ---
# The 8 tests above all mock _send_owner_message, so they never exercise the
# real subprocess -> JSON-parse path. The gateway CLI (`openclaw message send
# --json`) returns a camelCase TOP-LEVEL `messageId` (never snake_case
# `message_id`). Prior to the FIX-13 defect fix, `_send_owner_message` parsed
# `.get("message_id")`, which is always None, so the WHOLE raw JSON blob was
# stored in gateway_msg_id instead of the clean confirmed id. These tests call
# the REAL _send_owner_message with a fake `subprocess.run` returning the exact
# gateway schema and prove the clean id is extracted AND lands in the
# delivery_link send-log row.

class _FakeSendProc:
    """Minimal stand-in for subprocess.CompletedProcess on the send path."""
    returncode = 0

    def __init__(self, stdout: str):
        self.stdout = stdout
        self.stderr = ""


def _real_send_owner_message(monkeypatch, raw_stdout: str):
    """Run the REAL _send_owner_message with a fake subprocess returning
    raw_stdout (the exact `openclaw message send --json` response)."""
    monkeypatch.setattr(rsd, "_resolve_owner_route",
                        lambda: ("telegram", "operator-test-target"))
    monkeypatch.setattr(rsd.subprocess, "run",
                        lambda *a, **k: _FakeSendProc(raw_stdout))
    return rsd._send_owner_message("the deck is ready")


def test_real_parse_top_level_camelcase_message_id(monkeypatch):
    """The gateway's actual response shape — a camelCase TOP-LEVEL `messageId`
    — must yield the clean confirmed id (not the whole JSON blob)."""
    raw = json.dumps({
        "action": "send", "channel": "telegram", "dryRun": False,
        "handledBy": "gateway", "messageId": "64828",
        "payload": {"ok": True},
    })
    msg_id, sent = _real_send_owner_message(monkeypatch, raw)
    assert sent is True
    assert msg_id == "64828"
    assert msg_id != raw  # never the whole JSON blob


def test_real_parse_payload_message_id(monkeypatch):
    """The gateway also nests the id as payload.messageId; it must resolve too."""
    raw = json.dumps({"action": "send", "payload": {"messageId": "9001"}})
    msg_id, sent = _real_send_owner_message(monkeypatch, raw)
    assert sent is True
    assert msg_id == "9001"


def test_real_parse_result_message_id(monkeypatch):
    """The gateway's nested result.messageId shape (per register.message
    extractMessageId) must resolve."""
    raw = json.dumps({"action": "send", "payload": {"result": {"messageId": "77"}}})
    msg_id, sent = _real_send_owner_message(monkeypatch, raw)
    assert sent is True
    assert msg_id == "77"


def test_real_parse_plain_text_passthrough(monkeypatch):
    """A non-JSON stdout (older gateway) preserves the raw evidence unchanged."""
    msg_id, sent = _real_send_owner_message(monkeypatch, "raw non-json line")
    assert sent is True
    assert msg_id == "raw non-json line"


def test_real_parse_delivery_link_records_clean_id(monkeypatch, tmp_path):
    """END-TO-END over the real parse path: emit_delivery_link with a fake
    subprocess returning the camelCase response stores the CLEAN id (64828) in
    the delivery_link send-log row — not the raw JSON blob."""
    rd = _mk_run(tmp_path, tele_url="https://teleprompter.zerohumanworkforce.com/a.html")
    raw = json.dumps({
        "action": "send", "channel": "telegram", "dryRun": False,
        "handledBy": "gateway", "messageId": "64828",
        "payload": {"ok": True},
    })
    monkeypatch.setattr(rsd, "_resolve_owner_route",
                        lambda: ("telegram", "operator-test-target"))
    monkeypatch.setattr(rsd.subprocess, "run",
                        lambda *a, **k: _FakeSendProc(raw))
    mid = rsd.emit_delivery_link(rd)
    assert mid == "64828"
    recs = _records(rd)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["kind"] == "delivery_link"
    assert rec["sent"] is True
    assert rec["gateway_msg_id"] == "64828"
    assert rec["gateway_msg_id"] != raw  # QC defect: raw blob must never be stored
    # The deck link is still in the sent-message record (the FIX-13 QC gate).
    assert "Deck link: https://teleprompter.zerohumanworkforce.com/a.html" in rec["text"]


# --- deck-slug passthrough ---

def test_delivery_link_uses_slug(monkeypatch, tmp_path):
    rd = _mk_run(tmp_path, tele_url="https://teleprompter.zerohumanworkforce.com/a.html")
    monkeypatch.setattr(rsd, "_resolve_owner_route", lambda: ("telegram", "12345"))
    monkeypatch.setattr(rsd, "_send_owner_message",
                        lambda _text: ("msg-5", True))
    rsd.emit_delivery_link(rd, deck_slug="my-signature-deck")
    rec = _records(rd)[0]
    assert "my-signature-deck" in rec["text"]
