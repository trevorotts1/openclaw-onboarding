"""FAULT-14 -- undeliverable messages must be surfaced LOUDLY, not silently
tallied only into state["undeliverable"].

ROOT CAUSE (evidence): Reporter.to_requester()'s FAIL/UNDETERMINED branch
(presentation_job/report.py) used to ONLY append to state["undeliverable"] --
no self.event() call -- unlike the "no chat_id" early-return a few lines
above it in the SAME function, which DOES call
self.event("report.undeliverable", ...). That silently violated this very
package's own transport doctrine, documented in presentation_job/result.py:

    "message / alert transport -> UNDETERMINED behaves like 'not yet
    delivered': keep retrying, never discard. Losing an alert is the failure
    this project exists to eliminate."
    "health / status report -> UNDETERMINED is reported AS UNDETERMINED, out
    loud, never silently folded into 'healthy'."

A live run's engine stderr reported "undeliverable messages: 174 of 2001
total events -- the requester was NOT told about these", later growing to
549 of 2001 -- with ZERO real-time signal along the way: nothing printed by
Reporter.event() (which flushes to stdout on every OTHER report kind),
nothing recorded in state["events"]. The only way to discover it was to
either read state["undeliverable"] directly, or via
presentation_job.diagnose.describe_park() -- itself only invoked by
__main__.py on --resume, i.e. only AFTER the job has already parked. A job
that keeps running phase to phase without ever parking could silently drop
hundreds of client-facing notices with no operator ever finding out.

THE FIX: to_requester()'s FAIL/UNDETERMINED branch now also calls
self.event("report.undeliverable", ..., outcome=result.value) -- through the
exact same self.event() path every other report kind already uses -- so a
failed delivery prints immediately and lands in state["events"], greppable
and timestamped the moment it happens. The existing state["undeliverable"]
queue entry (the sweeper's only input) is unchanged.

NON-VACUOUS PROOF: this test's core assertion --
`"report.undeliverable" in kinds` after a FAIL/UNDETERMINED dispatch --
FAILS against the pre-fix report.py (verified against a scratch copy of the
original file; see the unit's final report for the transcript). It does not
merely assert on state["undeliverable"], which was already correct before
this change.
"""
import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.state import StateStore
from presentation_job.report import Reporter


def _mkstate(tmp_path, chat_id="tc"):
    rd = tmp_path / "r"
    rd.mkdir()
    store = StateStore(rd)
    s = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00", "manifest_path": "/x.json",
        "manifest_version": 25, "manifest_sha256": "0" * 64,
        "presentation_type": "from_scratch", "requester": {"chat_id": chat_id},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    return s, store


class TestUndeliverableSurfacedLoudly:
    def test_transport_unconfigured_fail_logs_a_report_undeliverable_event(self, tmp_path, monkeypatch):
        """FAIL path (PRESENTATION_NOTIFY_CMD unset). The message must still
        land in state["events"] as a "report.undeliverable" entry, not just
        silently in state["undeliverable"]."""
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        s, st = _mkstate(tmp_path)
        r = Reporter(s, st)
        r.to_requester("done", "your deck is ready")

        # Existing (unchanged) behaviour: still queued for the sweeper.
        assert len(s.get("undeliverable", [])) == 1

        # THE FIX: a loud, real-time record in state["events"] too.
        kinds = [e.get("kind") for e in s.get("events", [])]
        assert "report.undeliverable" in kinds, (
            f"a failed delivery produced no report.undeliverable event -- "
            f"silently tallied only into state['undeliverable']; events "
            f"kinds seen: {kinds}"
        )
        ev = next(e for e in s["events"] if e.get("kind") == "report.undeliverable")
        assert ev.get("outcome") == "fail"

    def test_transport_nonzero_exit_undetermined_also_logs_loudly(self, tmp_path, monkeypatch):
        """UNDETERMINED path (non-zero exit -- not FAIL) must be surfaced the
        same way. This is the far more common live-run failure mode (a
        configured but flaky/rate-limited transport), not just the
        never-configured case."""
        n = tmp_path / "n"
        n.mkdir()
        ns = n / "s.sh"
        ns.write_text("#!/bin/sh\nexit 7\n")
        ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        s, st = _mkstate(tmp_path)
        r = Reporter(s, st)
        r.to_requester("blocked", "phase failed", phase_id="P4-RENDER", reason="exit 1")

        kinds = [e.get("kind") for e in s.get("events", [])]
        assert "report.undeliverable" in kinds, (
            f"an UNDETERMINED delivery produced no report.undeliverable "
            f"event; events kinds seen: {kinds}"
        )
        ev = next(e for e in s["events"] if e.get("kind") == "report.undeliverable")
        assert ev.get("outcome") == "undetermined"

    def test_confirmed_delivery_never_logs_undeliverable(self, tmp_path, monkeypatch):
        """Control: a message that DOES get through must never produce a
        report.undeliverable event -- the fix must not fire on the happy
        path."""
        n = tmp_path / "n"
        n.mkdir()
        ns = n / "s.sh"
        ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n")
        ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        s, st = _mkstate(tmp_path)
        r = Reporter(s, st)
        r.to_requester("done", "your deck is ready")

        kinds = [e.get("kind") for e in s.get("events", [])]
        assert "report.undeliverable" not in kinds
        assert len(s.get("undeliverable", [])) == 0

    def test_growing_backlog_is_now_fully_accounted_in_events(self, tmp_path, monkeypatch):
        """Reproduces the live-run shape at small scale: a burst of messages
        where the transport is broken. Every failed one must have a matching
        report.undeliverable event -- proving a diagnostic that greps
        state["events"] would no longer miss any of them (unlike before the
        fix, where state["events"] carried zero record of ANY of them)."""
        n = tmp_path / "n"
        n.mkdir()
        ns = n / "s.sh"
        ns.write_text("#!/bin/sh\nexit 1\n")
        ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        s, st = _mkstate(tmp_path)
        r = Reporter(s, st)
        for i in range(20):
            r.to_requester("progress", f"phase {i} update",
                            phase_id=f"P{i}", reason="tick")

        n_undeliverable = len(s.get("undeliverable", []))
        n_events_logged = sum(
            1 for e in s.get("events", []) if e.get("kind") == "report.undeliverable"
        )
        assert n_undeliverable > 0, "test setup problem -- nothing failed"
        assert n_events_logged == n_undeliverable, (
            f"{n_undeliverable} messages went undeliverable but only "
            f"{n_events_logged} were logged loudly as report.undeliverable "
            f"events -- some failures are still silent"
        )
