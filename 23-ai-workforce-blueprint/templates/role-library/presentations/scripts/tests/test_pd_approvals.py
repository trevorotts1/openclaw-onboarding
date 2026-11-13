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


class TestAnApprovalNamesItsGateOnce:
    """PD-305 A1 — the owner message must name the gate, and one message
    approves exactly one gate.

    The stub oracle resolves the id and the stub resolver supplies the text, so
    no network and no live board are involved. Three rows, in the order the
    acceptance row states them: a message that approves nothing is refused; a
    message naming the gate is accepted once and refused for a second gate; an
    ids-only oracle is refused as undetermined."""

    def _stub(self, monkeypatch, text):
        monkeypatch.setattr(approvals, "_cc_board_oracle",
                            lambda run_dir: frozenset({"msg-a"}))
        monkeypatch.setattr(approvals, "_board_row",
                            lambda msg_id, run_dir: {
                                "msg_id": msg_id, "chat_id": "111",
                                "text": text, "received_at": "t"})
        monkeypatch.setattr(approvals, "_file_row", lambda msg_id, run_dir: None)

    def _approval(self, gate="AF-STYLE-UNPICKED"):
        return {
            "gate": gate,
            "approved_by": "Trevor",
            "owner_msg_id": "msg-a",
            "reason": "client said approve on the phone",
            "granted_at": "2026-11-12T10:04:05-05:00",
        }

    def test_a_message_that_approves_nothing_is_refused(self, tmp_path, monkeypatch):
        """'ok thanks' names no gate, so it approves no gate — even though the
        id resolves and the text is readable."""
        self._stub(monkeypatch, "ok thanks")
        with pytest.raises(approvals.ApprovalError) as exc:
            approvals.verify_with_gate_text(self._approval(), tmp_path)
        assert str(exc.value).startswith(approvals.AF_FORGED_APPROVAL)
        assert "does not name" in str(exc.value)

    def test_a_gate_naming_message_is_accepted_once(self, tmp_path, monkeypatch):
        self._stub(monkeypatch, "approve AF-STYLE-UNPICKED")
        got = approvals.verify_with_gate_text(self._approval(), tmp_path)
        assert got["gate"] == "AF-STYLE-UNPICKED"
        ledger = tmp_path / "working" / "checkpoints" / "approvals_used.json"
        assert json.loads(ledger.read_text())["uses"] == {
            "msg-a": "AF-STYLE-UNPICKED"}

    def test_the_same_message_is_refused_for_a_second_gate(self, tmp_path, monkeypatch):
        """One message approves one gate: the id is consumed by the first
        approval, so the second gate it claims is refused."""
        self._stub(monkeypatch, "approve AF-STYLE-UNPICKED and AF-OCR-READBACK")
        approvals.verify_with_gate_text(self._approval("AF-STYLE-UNPICKED"), tmp_path)
        with pytest.raises(approvals.ApprovalError) as exc:
            approvals.verify_with_gate_text(self._approval("AF-OCR-READBACK"), tmp_path)
        assert "one gate" in str(exc.value)
        assert str(exc.value).startswith(approvals.AF_FORGED_APPROVAL)

    def test_the_same_gate_twice_is_the_same_approval(self, tmp_path, monkeypatch):
        """Re-asserting the SAME gate is idempotent — a retry is not a forgery."""
        self._stub(monkeypatch, "approve AF-STYLE-UNPICKED")
        approvals.verify_with_gate_text(self._approval(), tmp_path)
        assert approvals.verify_with_gate_text(self._approval(), tmp_path)["gate"] \
            == "AF-STYLE-UNPICKED"

    def test_ids_only_oracle_is_refused_as_undetermined(self, tmp_path, monkeypatch):
        """The shape that used to pass: the id resolves, no text anywhere.
        An id proves a message exists, never what the owner approved."""
        monkeypatch.setattr(approvals, "_cc_board_oracle",
                            lambda run_dir: frozenset({"msg-a"}))
        monkeypatch.setattr(approvals, "_board_row", lambda msg_id, run_dir: None)
        monkeypatch.setattr(approvals, "_file_row", lambda msg_id, run_dir: None)
        with pytest.raises(approvals.ApprovalError) as exc:
            approvals.verify_with_gate_text(self._approval(), tmp_path)
        assert str(exc.value).startswith(approvals.AF_FORGED_APPROVAL)
        assert "ids-only" in str(exc.value)

    def test_an_unwritable_ledger_refuses_the_approval(self, tmp_path, monkeypatch):
        """An approval whose consumption cannot be recorded could be replayed
        forever, so a ledger that cannot be written refuses it."""
        self._stub(monkeypatch, "approve AF-STYLE-UNPICKED")
        monkeypatch.setattr(approvals, "_record_approval_used",
                            lambda run_dir, mid, gate: False)
        with pytest.raises(approvals.ApprovalError) as exc:
            approvals.verify_with_gate_text(self._approval(), tmp_path)
        assert "could not be recorded" in str(exc.value)


class TestGateTokenMatching:
    """PD-305 — the gate name matches as ONE whole token, and so do the
    self-grant markers (whole words, not substrings)."""

    def test_gate_matches_whole_token_case_insensitively(self):
        assert approvals.text_names_gate("please approve af-style-unpicked now",
                                         "AF-STYLE-UNPICKED")

    def test_gate_does_not_match_a_longer_identifier(self):
        assert not approvals.text_names_gate("approve AF-STYLE-UNPICKED-TOO",
                                             "AF-STYLE-UNPICKED")

    def test_an_honest_name_containing_self_is_not_a_self_grant(self):
        """A substring test refused 'Herself Ordonez' for containing 'self'."""
        assert approvals._self_grant_marker("Herself Ordonez") is None

    def test_the_marker_itself_is_still_refused(self):
        assert approvals._self_grant_marker("builder (executive strategy)") == \
            "executive strategy"


class TestTaskIdSource:
    """PD-305 item 3 — state.json board.task_id first; the manifest only when
    the two agree."""

    def _write(self, path: Path, obj) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj), encoding="utf-8")

    def test_state_json_wins_when_it_is_the_only_source(self, tmp_path):
        self._write(tmp_path / "state.json", {"board": {"task_id": "from-state"}})
        assert approvals.resolve_cc_task_id(tmp_path) == "from-state"

    def test_manifest_is_used_when_state_has_no_task_id(self, tmp_path):
        self._write(tmp_path / "working" / "checkpoints" / "process_manifest.json",
                    {"cc_task_id": "from-manifest"})
        assert approvals.resolve_cc_task_id(tmp_path) == "from-manifest"

    def test_agreeing_sources_resolve(self, tmp_path):
        self._write(tmp_path / "state.json", {"board": {"task_id": "same"}})
        self._write(tmp_path / "working" / "checkpoints" / "process_manifest.json",
                    {"cc_task_id": "same"})
        assert approvals.resolve_cc_task_id(tmp_path) == "same"

    def test_disagreeing_sources_are_undetermined(self, tmp_path, capsys):
        """Approving against the wrong task's messages is exactly what this
        ordering prevents, so a disagreement fails closed."""
        self._write(tmp_path / "state.json", {"board": {"task_id": "state-task"}})
        self._write(tmp_path / "working" / "checkpoints" / "process_manifest.json",
                    {"cc_task_id": "manifest-task"})
        assert approvals.resolve_cc_task_id(tmp_path) == ""
        assert approvals.TASK_ID_DISAGREEMENT in capsys.readouterr().err


class TestGatewayOracle:
    """PD-305 item 4 — the gateway fallback accepts `is_owner: true` only.

    The old `role` branch accepted the strings "owner"/"user"/"client", a field
    the message's own writer can set. A gateway that answers with a role and no
    is_owner flag is UNDETERMINED, never an approval."""

    def _stub_gateway(self, monkeypatch, payload):
        class _Resp:
            def __init__(self, body): self._body = body
            def getcode(self): return 200
            def read(self): return self._body
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setenv("OPENCLAW_GATEWAY_URL", "http://gateway.test")
        monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "test-token")
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda req, timeout=None: _Resp(json.dumps(payload).encode("utf-8")))

    def test_is_owner_true_is_accepted(self, monkeypatch):
        self._stub_gateway(monkeypatch, {"is_owner": True})
        assert approvals._gateway_owner_oracle("msg-a") is True

    def test_is_owner_false_is_refused(self, monkeypatch):
        self._stub_gateway(monkeypatch, {"is_owner": False})
        assert approvals._gateway_owner_oracle("msg-a") is False

    def test_a_role_without_is_owner_is_undetermined(self, monkeypatch):
        """The removed branch: this answer used to read as an approval."""
        self._stub_gateway(monkeypatch, {"role": "owner"})
        assert approvals._gateway_owner_oracle("msg-a") is None

    def test_no_gateway_configured_is_undetermined(self, monkeypatch):
        monkeypatch.delenv("OPENCLAW_GATEWAY_URL", raising=False)
        monkeypatch.delenv("GATEWAY_URL", raising=False)
        assert approvals._gateway_owner_oracle("msg-a") is None
