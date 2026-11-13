"""Tests for the owner-message resolver (PD-004a) and the approvals validator.

An approval carries an `owner_msg_id`, and the owner-ids oracle proves that id
is REAL — but not what the client actually said. `resolve_owner_message` turns
the id back into the message, so a later gate can check the text against the
gate it claims to open (PD-305). Two sources, in order: the board (text arrives
with PD-305b) and `<RUN_DIR>/working/interview/inbound_messages.jsonl`.

No network, no live service: the board is a stub and the fixture file is
written into a temporary run folder.
"""

import json
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job import approvals  # noqa: E402

MSG_A = {
    "msg_id": "msg-a",
    "chat_id": "111",
    "text": "approve AF-STYLE-UNPICKED",
    "received_at": "2026-11-12T15:04:05+00:00",
}
MSG_OTHER_CHAT = {
    "msg_id": "msg-b",
    "chat_id": "999",
    "text": "ok thanks",
    "received_at": "2026-11-12T15:06:00+00:00",
}


def _write_inbound(run: Path, rows) -> Path:
    """Write the channel bridge's file shape: one JSON object per line."""
    path = run / "working" / "interview" / "inbound_messages.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def _valid_approval(owner_msg_id="msg-a", gate="AF-STYLE-UNPICKED"):
    return {
        "gate": gate,
        "approved_by": "Trevor",
        "owner_msg_id": owner_msg_id,
        "reason": "client said approve on the phone",
        "granted_at": "2026-11-12T10:04:05-05:00",
    }


class TestResolveFromFixture:
    """A1 — an id present in the fixture file returns its row."""

    def test_returns_the_row_for_a_known_id(self, tmp_path):
        _write_inbound(tmp_path, [MSG_A])
        row = approvals.resolve_owner_message("msg-a", tmp_path)
        assert row == MSG_A

    def test_skips_rows_without_text(self, tmp_path):
        _write_inbound(tmp_path, [
            {"msg_id": "msg-a", "chat_id": "111", "received_at": "t"},
        ])
        assert approvals.resolve_owner_message("msg-a", tmp_path) is None

    def test_skips_malformed_lines(self, tmp_path):
        path = tmp_path / "working" / "interview" / "inbound_messages.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "not json\n" + json.dumps(MSG_A) + "\n\n", encoding="utf-8")
        assert approvals.resolve_owner_message("msg-a", tmp_path) == MSG_A

    def test_never_writes_the_fixture(self, tmp_path):
        path = _write_inbound(tmp_path, [MSG_A])
        before = path.read_bytes()
        approvals.resolve_owner_message("msg-a", tmp_path)
        approvals.resolve_owner_message("nope", tmp_path)
        assert path.read_bytes() == before


class TestResolveFromBoard:
    """A2 — an id the stub board returns with text returns its row."""

    def test_board_row_wins_over_the_file(self, tmp_path, monkeypatch):
        _write_inbound(tmp_path, [MSG_OTHER_CHAT])
        board_row = dict(MSG_A, text="board text", received_at="2026-11-12T16:00:00+00:00")
        monkeypatch.setattr(
            approvals, "BOARD_TEXT_RESOLVER",
            lambda msg_id, run_dir: board_row if msg_id == "msg-a" else None)
        assert approvals.resolve_owner_message("msg-a", tmp_path) == board_row

    def test_board_without_row_falls_through_to_the_file(self, tmp_path, monkeypatch):
        _write_inbound(tmp_path, [MSG_A])
        monkeypatch.setattr(
            approvals, "BOARD_TEXT_RESOLVER", lambda msg_id, run_dir: None)
        assert approvals.resolve_owner_message("msg-a", tmp_path) == MSG_A

    def test_a_raising_board_is_not_fatal(self, tmp_path, monkeypatch):
        _write_inbound(tmp_path, [MSG_A])

        def _boom(msg_id, run_dir):
            raise RuntimeError("board down")

        monkeypatch.setattr(approvals, "BOARD_TEXT_RESOLVER", _boom)
        assert approvals.resolve_owner_message("msg-a", tmp_path) == MSG_A


class TestNoText:
    """A3 / A4 — no text anywhere is None, with the reason logged."""

    def test_board_knows_the_id_but_has_no_text(self, tmp_path, monkeypatch, capsys):
        def _ids_only(msg_id, run_dir):
            return {"msg_id": msg_id, "chat_id": "111", "received_at": "t"}

        monkeypatch.setattr(approvals, "BOARD_TEXT_RESOLVER", _ids_only)
        _write_inbound(tmp_path, [MSG_OTHER_CHAT])
        assert approvals.resolve_owner_message("msg-a", tmp_path) is None
        err = capsys.readouterr().err
        assert approvals.RESOLVE_BOARD_HAS_NO_TEXT in err
        assert approvals.RESOLVE_NO_TEXT_SOURCE in err

    def test_unknown_id_returns_none(self, tmp_path):
        _write_inbound(tmp_path, [MSG_A])
        assert approvals.resolve_owner_message("msg-zzz", tmp_path) is None

    def test_no_cc_address_and_no_file_returns_none(self, tmp_path, capsys):
        assert approvals.BOARD_TEXT_RESOLVER is None
        assert approvals.resolve_owner_message("msg-a", tmp_path) is None
        assert approvals.RESOLVE_NO_TEXT_SOURCE in capsys.readouterr().err

    def test_empty_or_missing_id_returns_none(self, tmp_path):
        _write_inbound(tmp_path, [MSG_A])
        assert approvals.resolve_owner_message("", tmp_path) is None
        assert approvals.resolve_owner_message(None, tmp_path) is None


class TestChatIsReportedAsIs:
    """A5 — a message from another chat is returned with its real chat id."""

    def test_other_chat_id_is_not_rewritten(self, tmp_path):
        _write_inbound(tmp_path, [MSG_A, MSG_OTHER_CHAT])
        row = approvals.resolve_owner_message("msg-b", tmp_path)
        assert row is not None
        assert row["chat_id"] == "999"
        assert row["text"] == "ok thanks"


class TestVerifyStillWorks:
    """A6 — the existing `verify()` contract is unchanged (stub oracle)."""

    def _stub_requester_lookup(self, monkeypatch, ids):
        monkeypatch.setattr(
            approvals, "_cc_board_oracle",
            lambda run_dir: frozenset(ids) if ids is not None else None)

    def test_accepts_a_well_formed_approval_whose_id_resolves(self, tmp_path, monkeypatch):
        self._stub_requester_lookup(monkeypatch, {"msg-a"})
        assert approvals.verify(_valid_approval(), tmp_path)["gate"] == "AF-STYLE-UNPICKED"

    def test_rejects_an_id_the_oracle_does_not_know(self, tmp_path, monkeypatch):
        self._stub_requester_lookup(monkeypatch, {"msg-other"})
        with pytest.raises(approvals.ApprovalError) as exc:
            approvals.verify(_valid_approval(), tmp_path)
        assert str(exc.value).startswith(approvals.AF_FORGED_APPROVAL)

    def test_rejects_a_record_with_no_owner_msg_id(self, tmp_path, monkeypatch):
        self._stub_requester_lookup(monkeypatch, {"msg-a"})
        rec = _valid_approval()
        rec.pop("owner_msg_id")
        with pytest.raises(approvals.ApprovalError) as exc:
            approvals.verify(rec, tmp_path)
        assert str(exc.value).startswith(approvals.AF_FORGED_APPROVAL)

    def test_undetermined_oracle_denies(self, tmp_path, monkeypatch):
        self._stub_requester_lookup(monkeypatch, None)
        monkeypatch.delenv("OPENCLAW_GATEWAY_URL", raising=False)
        monkeypatch.delenv("GATEWAY_URL", raising=False)
        with pytest.raises(approvals.ApprovalError) as exc:
            approvals.verify(_valid_approval(), tmp_path)
        assert str(exc.value).startswith(approvals.AF_FORGED_APPROVAL)
