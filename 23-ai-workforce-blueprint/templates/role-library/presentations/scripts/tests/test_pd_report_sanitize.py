"""PD-018b -- the reporter's client guard and the milestone throttle.

Proves:
  * a message carrying a manifest phase id, or a token starting `AF-`, never
    reaches the client transport: one plain sentence is sent instead and
    `report.sanitized` records the withheld text (the id list comes from the
    loaded manifest, not from a pattern);
  * an ordinary message is untouched (control);
  * `_is_milestone` reads the phase id the caller passes, not id text inside
    the message.
"""
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.report import Reporter  # noqa: E402
from presentation_job.state import StateStore  # noqa: E402


class _FakeManifest:
    """The slice of Manifest the reporter reads: the raw phase entries."""

    def __init__(self) -> None:
        self.raw = {"phases": [
            {"id": "P4-RENDER", "client_label": "Creating your slide images",
             "client_visible": True},
            {"id": "P-STYLE-SPEC", "client_label": "Choosing your look",
             "client_visible": False},
        ]}


def _transport(tmp_path, monkeypatch) -> Path:
    sent = tmp_path / "sent.jsonl"
    notify = tmp_path / "notify.sh"
    notify.write_text("#!/bin/sh\ncat >> \"$PD018B_SENT\"\necho >> \"$PD018B_SENT\"\nexit 0\n")
    notify.chmod(0o755)
    # PRESENTATION_NOTIFY_CMD is an argument vector (shlex.split, shell=False).
    # The mandated TMPDIR contains spaces, so the path MUST be quoted or the
    # transport never starts and "received nothing" would pass vacuously.
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", shlex.quote(str(notify)))
    monkeypatch.setenv("PD018B_SENT", str(sent))
    return sent


def _reporter(tmp_path, manifest=True):
    run = tmp_path / "run"
    run.mkdir(exist_ok=True)
    store = StateStore(run)
    state = {"schema_version": 1, "job_id": "t", "run_dir": str(run),
             "created_at": "2026-01-01T00:00:00+00:00",
             "requester": {"chat_id": "tc"}, "phases": [], "events": [],
             "sent": {}, "undeliverable": [], "heartbeat": {}, "terminal": None}
    return Reporter(state, store, _FakeManifest() if manifest else None), state


def _sent_messages(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class TestSanitizer:
    def test_phase_id_is_replaced_and_recorded(self, tmp_path, monkeypatch):
        sent = _transport(tmp_path, monkeypatch)
        rep, state = _reporter(tmp_path)
        rep.to_requester("progress", "P4-RENDER failed: exit 1", phase_id="P4-RENDER")
        msgs = _sent_messages(sent)
        assert len(msgs) == 1
        assert msgs[0]["message"] == (
            "Your presentation is moving ahead: Creating your slide images."), msgs[0]
        evs = [e for e in state["events"] if e["kind"] == "report.sanitized"]
        assert len(evs) == 1
        assert "P4-RENDER failed" in evs[0]["message"], (
            "the withheld text must stay recorded for the operator")

    def test_af_token_is_replaced(self, tmp_path, monkeypatch):
        sent = _transport(tmp_path, monkeypatch)
        rep, state = _reporter(tmp_path)
        rep.to_requester("blocked", "AF-RENDER-BYPASS: deck not canonical",
                         phase_id="P4-RENDER")
        msgs = _sent_messages(sent)
        assert msgs and "AF-" not in msgs[0]["message"], msgs
        assert msgs[0]["message"].startswith("Your presentation is moving ahead")
        assert any(e["kind"] == "report.sanitized" for e in state["events"])

    def test_ordinary_message_is_untouched(self, tmp_path, monkeypatch):
        sent = _transport(tmp_path, monkeypatch)
        rep, state = _reporter(tmp_path)
        text = "Your presentation is paused. Nothing is needed from you."
        rep.to_requester("blocked", text)
        assert [m["message"] for m in _sent_messages(sent)] == [text]
        assert not [e for e in state["events"] if e["kind"] == "report.sanitized"]

    def test_reporter_without_a_manifest_still_refuses_af_tokens(self, tmp_path, monkeypatch):
        sent = _transport(tmp_path, monkeypatch)
        rep, _ = _reporter(tmp_path, manifest=False)
        rep.to_requester("progress", "AF-PROCESS-INTEGRITY: no")
        msgs = _sent_messages(sent)
        assert msgs and "AF-" not in msgs[0]["message"], msgs


class TestMilestoneThrottle:
    def test_is_milestone_reads_the_argument_not_the_message(self, tmp_path):
        rep, _ = _reporter(tmp_path)
        assert rep._is_milestone("P4-RENDER") is True
        assert rep._is_milestone("P8-ASSEMBLE") is True
        assert rep._is_milestone("P4-COPY") is False
        assert rep._is_milestone(None) is False

    def test_milestone_progress_passes_the_throttle_on_phase_id_alone(self, tmp_path, monkeypatch):
        _transport(tmp_path, monkeypatch)
        rep, state = _reporter(tmp_path)
        rep.to_requester("progress", "Step 19 of 46 — Creating your slide images — starting",
                         phase_id="P4-COPY")   # stamps the ten-minute window
        rep.to_requester("progress", "Step 20 of 46 — Assembling your deck — starting",
                         phase_id="P4-RENDER")  # a milestone: must not be throttled
        assert state["sent"]["progress"]["count"] == 2
