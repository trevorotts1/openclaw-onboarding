"""RCA #7 -- dead-letter cap on cmd_sweep_undeliverable.

Before this fix, cmd_sweep_undeliverable() re-queued a failed notification
forever: it incremented an `attempts` counter and never checked it -- no cap,
no dead-letter, no quarantine. A single stale chat id (wrong id, deleted
chat) looped on every sweep indefinitely and burned tokens forever.

These tests prove:
  1. a permanently-undeliverable message stops being re-queued once it hits
     MAX_DELIVERY_ATTEMPTS, and lands in state["dead_letter"] (not
     state["undeliverable"]) with a findable log line;
  2. a message that succeeds on a later retry (before the cap) is still
     delivered normally -- the cap does not break legitimate retries.

Flat file beside the code it tests, following test_delivery_link.py's
convention for this scripts/ tree.
"""
import json
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.__main__ import cmd_sweep_undeliverable, MAX_DELIVERY_ATTEMPTS
from presentation_job.state import StateStore, STATE_SCHEMA_VERSION


def _seed_state(run_dir: Path, *, attempts: int, chat_id: str = "chat-stale-404") -> None:
    """Write a minimal, valid state.json with one queued undeliverable message."""
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "job_id": "pj_test0000000000000000000",
        "run_dir": str(run_dir),
        "created_at": "2026-08-17T00:00:00+00:00",
        "manifest_path": "unused",
        "manifest_version": 1,
        "manifest_sha256": "0" * 64,
        "presentation_type": "signature",
        "requester": {"chat_id": chat_id},
        "intake": {},
        "current_phase": None,
        "phases": [],
        "gates": {},
        "waivers": [],
        "events": [],
        "sent": {},
        "undeliverable": [{
            "at": "2026-08-17T00:00:00+00:00",
            "kind": "done",
            "message": "your deck is ready",
            "chat_id": chat_id,
            "attempts": attempts,
        }],
        "heartbeat": {},
        "terminal": None,
    }
    StateStore(run_dir).save(state)


class _Args:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir


class TestDeadLetterCap:
    def test_capped_message_dead_letters_and_stops_requeueing(self, tmp_path, monkeypatch, capsys):
        """A message already at attempts == MAX_DELIVERY_ATTEMPTS, whose retry
        also fails (unreachable chat id), must be dead-lettered this sweep --
        not re-queued to state['undeliverable'] -- and must print a findable
        DEAD-LETTERED line."""
        run_dir = tmp_path / "run"
        _seed_state(run_dir, attempts=MAX_DELIVERY_ATTEMPTS, chat_id="chat-stale-404")

        # dispatch() is imported into __main__'s namespace; patch it there so
        # every attempt fails, simulating a permanently-unreachable chat id.
        import presentation_job.__main__ as main_mod
        monkeypatch.setattr(main_mod, "dispatch", lambda chat_id, kind, message: False)

        rc = cmd_sweep_undeliverable(_Args(run_dir))
        out = capsys.readouterr().out

        state = StateStore(run_dir).load()
        assert state["undeliverable"] == [], "dead-lettered message must not stay queued"
        assert len(state.get("dead_letter", [])) == 1, "message must land in state['dead_letter']"
        dl = state["dead_letter"][0]
        assert dl["chat_id"] == "chat-stale-404"
        assert dl["attempts"] == MAX_DELIVERY_ATTEMPTS + 1
        assert "dead_letter_reason" in dl and dl["dead_letter_reason"]
        assert "DEAD-LETTERED" in out, "a dropped message must leave a findable log line"
        assert "chat-stale-404" in out
        assert rc != 0, "a sweep that dead-lettered something must not exit 0"

    def test_loop_actually_terminates_across_repeated_sweeps(self, tmp_path, monkeypatch):
        """Feed the same undeliverable message through the sweep repeatedly (as
        a cron would). Proves the queue drains to zero re-queues at the cap
        instead of growing/staying forever."""
        run_dir = tmp_path / "run"
        _seed_state(run_dir, attempts=0, chat_id="chat-stale-404")

        import presentation_job.__main__ as main_mod
        monkeypatch.setattr(main_mod, "dispatch", lambda chat_id, kind, message: False)

        seen_still_undeliverable = []
        for _ in range(MAX_DELIVERY_ATTEMPTS + 3):
            cmd_sweep_undeliverable(_Args(run_dir))
            state = StateStore(run_dir).load()
            seen_still_undeliverable.append(len(state["undeliverable"]))

        # it must have terminated (hit 0 and stayed at 0), not looped forever
        assert seen_still_undeliverable[-1] == 0
        assert seen_still_undeliverable[-1] == seen_still_undeliverable[-2] == 0
        final_state = StateStore(run_dir).load()
        assert len(final_state["dead_letter"]) == 1

    def test_success_on_retry_before_cap_still_delivers_normally(self, tmp_path, monkeypatch):
        """A message that succeeds on its 2nd attempt (well under the cap) must
        be delivered normally -- the cap must not interfere with legitimate
        retries."""
        run_dir = tmp_path / "run"
        _seed_state(run_dir, attempts=1, chat_id="chat-good-eventually")

        import presentation_job.__main__ as main_mod
        monkeypatch.setattr(main_mod, "dispatch", lambda chat_id, kind, message: True)

        rc = cmd_sweep_undeliverable(_Args(run_dir))

        state = StateStore(run_dir).load()
        assert state["undeliverable"] == [], "delivered message must be removed from the queue"
        assert state.get("dead_letter", []) == [], "a successful delivery must never be dead-lettered"
        assert state["sent"]["done"]["count"] == 1
        assert rc == 0

    def test_no_dead_letter_before_cap_is_reached(self, tmp_path, monkeypatch):
        """A failing message below the cap is re-queued as before -- normal
        retry behaviour is unchanged."""
        run_dir = tmp_path / "run"
        _seed_state(run_dir, attempts=1, chat_id="chat-transient")

        import presentation_job.__main__ as main_mod
        monkeypatch.setattr(main_mod, "dispatch", lambda chat_id, kind, message: False)

        rc = cmd_sweep_undeliverable(_Args(run_dir))

        state = StateStore(run_dir).load()
        assert len(state["undeliverable"]) == 1
        assert state["undeliverable"][0]["attempts"] == 2
        assert state.get("dead_letter", []) == []
        assert rc != 0
