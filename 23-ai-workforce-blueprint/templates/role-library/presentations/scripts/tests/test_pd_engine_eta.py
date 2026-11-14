"""PD-031 -- tell the client roughly how long is left.

Acceptance A1, proven on a real Engine over a scratch manifest:
  * fixture history with medians 4, 6 and 10 minutes -> at the first step the
    start message says "About 20 minutes to go.";
  * empty history -> no sentence at all.

The number is the SUM OF THE MEDIANS of the remaining phases, read from the
box's own stage-timings history (`working/telemetry/stage-timings.jsonl`
`phase_exit` rows) -- the same source `eta` is filled from today.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import StateStore  # noqa: E402

PHASES = [("P-A", 1.0), ("P-B", 2.0), ("P-C", 3.0)]


def _manifest(tmp_path: Path) -> Path:
    mp = tmp_path / "PIPELINE-MANIFEST.json"
    mp.write_text(json.dumps({
        "manifest_version": 25,
        "phases": [{"id": pid, "order": order, "owning_role": "test",
                    "client_label": pid, "client_visible": True,
                    "produces_artifact": [f"working/{pid}.txt"],
                    "client_report": {"start_template": "Step {k} of {N} — {client_label} — starting"}}
                   for pid, order in PHASES],
    }), encoding="utf-8")
    return mp


def _engine(tmp_path: Path) -> Engine:
    rd = tmp_path / "run"
    (rd / "working" / "telemetry").mkdir(parents=True, exist_ok=True)
    manifest = Manifest(_manifest(tmp_path))
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00", "manifest_path": str(manifest.path),
        "manifest_version": 25, "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch", "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    return Engine(rd, manifest, store, state, dry_run=True)


def _record(eng: Engine, pid: str, seconds: float) -> None:
    path = eng._telemetry_dir() / "stage-timings.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "phase_exit", "phase_id": pid,
                             "duration_s": seconds}) + "\n")


class TestEtaFromRecordedDurations:
    def test_first_step_says_about_twenty_minutes_to_go(self, tmp_path):
        eng = _engine(tmp_path)
        # medians 4, 6, 10 minutes
        _record(eng, "P-A", 4 * 60)
        _record(eng, "P-B", 6 * 60)
        _record(eng, "P-C", 10 * 60)

        msg = eng._render_client_report_msg(eng.manifest.phase("P-A"), "start")
        assert msg == ("Step 1 of 3 — P-A — starting About 20 minutes to go."), msg

    def test_empty_history_says_nothing(self, tmp_path):
        eng = _engine(tmp_path)
        msg = eng._render_client_report_msg(eng.manifest.phase("P-A"), "start")
        assert "minutes to go" not in msg, msg
        assert msg == "Step 1 of 3 — P-A — starting", msg

    def test_the_median_is_the_median_not_the_sum_of_rows(self, tmp_path):
        # Three recorded rows for one phase: 1, 4 and 40 minutes. The median
        # is 4 -- not 45 (a sum) and not 15 (a mean).
        eng = _engine(tmp_path)
        _record(eng, "P-A", 1 * 60)
        _record(eng, "P-A", 4 * 60)
        _record(eng, "P-A", 40 * 60)

        msg = eng._render_client_report_msg(eng.manifest.phase("P-B"), "start")
        assert msg.endswith("About 4 minutes to go."), msg

    def test_done_message_carries_no_eta(self, tmp_path):
        eng = _engine(tmp_path)
        _record(eng, "P-A", 4 * 60)
        msg = eng._render_client_report_msg(eng.manifest.phase("P-A"), "done")
        assert "minutes to go" not in msg, msg
