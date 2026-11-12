"""PD-206b -- an operator review is an operator message, not a client alarm.

The defect: a failed prompt check whose only missing input is a PERSON's verdict
(PD-206a writes `OPERATOR-REVIEW:` as the first reason) classified as an owner
decision and went through `_block`, which sent the client the raw checker
verdict -- AF- codes, phase ids and file paths included. The client was told its
presentation was "paused" over something they cannot act on.

What these tests pin:
  * the client receives EXACTLY one plain sentence, and nothing internal;
  * the operator event and the board carry the FULL reason;
  * an ordinary park reason still takes today's path (no client message);
  * the sentence is sent once per phase;
  * a board-less engine records `report.operator_review_needed` and reports
    `BLOCKED-FOLLOWUP: no operator channel`;
  * the park is re-admittable by the existing resume path, so the check RUNS
    AGAIN once the human verdict file exists -- nothing is skipped.

No model, no server, no live service: the transport is stubbed at `_dispatch3`.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from presentation_job import phases  # noqa: E402
from presentation_job.report import Reporter  # noqa: E402
from presentation_job.result import CheckResult  # noqa: E402
from presentation_job.state import EXIT_GATE_BLOCKED, StateStore  # noqa: E402

# What the engine actually builds for the substance park: the verdict prefix,
# the verifier's notes, then the engine's own boilerplate sentence.
_VERDICT = (
    "substance check failed: OPERATOR-REVIEW: P-PROMPT-QC slide-3: "
    "AF-FACE-PROMPT-MISSING -- awaiting a human verdict on the casting report.")
_REASON = (_VERDICT + " An owner_skip_approval token for this phase is "
                       "required to advance it to done.")


class _Phase:
    def __init__(self, pid="P-PROMPT-QC", role="prompt-writer"):
        self.id = pid
        self.owning_role = role
        self.produces_artifact = ["working/qc/prompt_report.json"]


class _Manifest:
    def phase_or_none(self, pid):  # noqa: ARG002 - engine only needs no crash
        return None


class _Board:
    def __init__(self):
        self.blocked = []
        self.cards = []

    def mark_blocked(self, pid, reason):
        self.blocked.append((pid, reason))

    def child_report(self, pid, title, description, status, reason):
        self.cards.append((pid, title, description, status, reason))


def _engine(tmp_path, monkeypatch, *, board=None):
    sent = []

    def _fake_dispatch(self, chat_id, kind, message):  # noqa: ARG001
        sent.append((kind, message))
        return CheckResult.PASS

    monkeypatch.setattr(Reporter, "_dispatch3", _fake_dispatch)
    eng = phases.Engine.__new__(phases.Engine)
    eng.run_dir = tmp_path
    eng.state = {
        "job_id": "test-pd206b", "schema_version": 1,
        "run_dir": str(tmp_path), "requester": {"chat_id": "123"},
        "phases": [],
    }
    eng.store = StateStore(tmp_path)
    eng.report = Reporter(eng.state, eng.store)
    eng.board = board
    eng.manifest = _Manifest()
    eng.dry_run = True
    eng._state_lock = threading.RLock()
    return eng, sent


def test_first_check_reason_reads_the_head_of_the_engine_string():
    """RD-05: the call path carries one reason string, not a list."""
    assert phases._first_check_reason(_REASON).startswith(phases.OPERATOR_REVIEW_PREFIX)
    assert phases._first_check_reason(
        "substance check failed: AF-NO-VILLAIN: x; AF-OTHER: y") == "AF-NO-VILLAIN: x"
    assert phases._first_check_reason("produced nothing") == "produced nothing"


def test_client_gets_one_plain_sentence_and_nothing_internal(tmp_path, monkeypatch):
    board = _Board()
    eng, sent = _engine(tmp_path, monkeypatch, board=board)

    rc = eng._fail_unit(_Phase(), _REASON)

    assert rc == EXIT_GATE_BLOCKED
    assert [m for _k, m in sent] == [phases.OPERATOR_REVIEW_CLIENT_SENTENCE]
    for _kind, message in sent:
        assert "AF-" not in message
        assert "P-" not in message
        assert "/" not in message
        assert "OPERATOR-REVIEW" not in message
    ps = eng._phase_state("P-PROMPT-QC")
    assert ps["status"] == "blocked"
    assert ps["blocked_reason"] == _REASON


def test_operator_event_and_board_carry_the_full_reason(tmp_path, monkeypatch):
    board = _Board()
    eng, _sent = _engine(tmp_path, monkeypatch, board=board)

    eng._fail_unit(_Phase(), _REASON)

    events = [e for e in eng.state["events"]
              if e.get("kind") == "report.operator_review_needed"]
    assert [e["message"] for e in events] == [_REASON]
    assert board.blocked == [("P-PROMPT-QC", _REASON)]
    assert board.cards[-1][3:] == ("blocked", _REASON)


def test_ordinary_park_takes_todays_path(tmp_path, monkeypatch):
    """Control (A3): no operator prefix, no operator-review routing."""
    eng, sent = _engine(tmp_path, monkeypatch, board=_Board())

    eng._fail_unit(_Phase(), "produced no artifact after 2 regeneration attempt(s): "
                             "missing working/copy/copy.json")

    assert eng._phase_state("P-PROMPT-QC")["status"] == "quarantined"
    assert sent == []


def test_sentence_is_sent_once_per_phase(tmp_path, monkeypatch):
    eng, sent = _engine(tmp_path, monkeypatch, board=_Board())

    eng._park_operator_review(_Phase(), _REASON)
    eng._park_operator_review(_Phase(), _REASON)

    assert [m for _k, m in sent] == [phases.OPERATOR_REVIEW_CLIENT_SENTENCE]


def test_no_operator_channel_is_reported(tmp_path, monkeypatch, capsys):
    eng, _sent = _engine(tmp_path, monkeypatch, board=None)

    eng._fail_unit(_Phase(), _REASON)

    assert any(e.get("kind") == "report.operator_review_needed"
               for e in eng.state["events"])
    assert "BLOCKED-FOLLOWUP: no operator channel" in capsys.readouterr().err


def test_the_park_is_readmitted_so_the_check_runs_again(tmp_path, monkeypatch):
    """The substance branch ledgers the verifier's own reason before _fail_unit;
    that is what makes the park a verifier park the resume path re-opens."""
    eng, _sent = _engine(tmp_path, monkeypatch, board=_Board())
    eng._fail_unit(_Phase(), _REASON)
    eng._phase_state("P-PROMPT-QC")["heal_events"] = [
        {"class": "verifier_substance", "reason": _VERDICT}]

    recs = phases.readmit_retryable_phases(eng.state)

    assert [r["phase"] for r in recs] == ["P-PROMPT-QC"]
    assert eng._phase_state("P-PROMPT-QC")["status"] == "pending"


if __name__ == "__main__":  # pragma: no cover - manual run only
    raise SystemExit(pytest.main([__file__, "-q"]))
