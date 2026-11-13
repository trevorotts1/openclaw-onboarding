"""PD-018b -- the client sees plain labels, and nothing internal.

Proves, on the REAL manifest and the REAL engine:
  * every one of the 112 client_report templates (56 start + 56 done) renders
    with its own {client_label} filled -- no empty token, no phase id, no role;
  * a phase declared `client_visible: false` sends nothing (render is "");
  * a script step that fails once and then passes sends the client NOTHING and
    puts the retry line in the event log as `report.internal` (row A4).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import phases as phases_mod  # noqa: E402
from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import StateStore, EXIT_OK  # noqa: E402


def _canonical_manifest() -> Path:
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = SCRIPTS
    for _ in range(12):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    raise FileNotFoundError("PIPELINE-MANIFEST.json not found")


def _engine(tmp_path, intake=None) -> Engine:
    run = tmp_path / "run"
    (run / "working" / "copy").mkdir(parents=True, exist_ok=True)
    if intake is not None:
        (run / "working" / "copy" / "intake.json").write_text(json.dumps(intake))
    manifest = Manifest(_canonical_manifest())
    store = StateStore(run)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(run),
        "created_at": "2026-01-01T00:00:00+00:00", "manifest_path": str(manifest.path),
        "manifest_version": manifest.version, "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch", "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    return Engine(run, manifest, store, state, dry_run=True), manifest


class TestEveryTemplateFillsItsOwnLabel:
    def test_all_112_templates_render_with_the_manifest_label(self, tmp_path):
        eng, manifest = _engine(tmp_path)  # no intake -> unknown deck, full N
        rendered = 0
        for ph in manifest.phases:
            label, visible = eng._phase_client_meta(ph)
            assert label, f"{ph.id} has no client_label"
            for kind in ("start", "done"):
                msg = eng._render_client_report_msg(ph, kind)
                rendered += 1
                if not visible:
                    assert msg == "", f"{ph.id} is hidden but rendered {msg!r}"
                    continue
                assert msg, f"{ph.id} ({kind}) rendered nothing for a visible phase"
                assert label in msg, f"{ph.id} ({kind}) lost its label: {msg!r}"
                assert "{" not in msg and "}" not in msg
                assert ph.id not in msg, f"{ph.id} ({kind}) leaked the phase id: {msg!r}"
                assert ph.owning_role not in msg
        assert rendered == 2 * len(manifest.phases)

    def test_the_rendered_step_line_reads_as_a_step(self, tmp_path):
        eng, manifest = _engine(tmp_path)
        msg = eng._render_client_report_msg(manifest.phase("P4-RENDER"), "start")
        assert msg == "Step 19 of 46 — Creating your slide images — starting", msg

    def test_hidden_phase_is_silent_whatever_its_step_number(self, tmp_path):
        eng, manifest = _engine(tmp_path)  # unknown deck: every phase has a k
        ph = manifest.phase("P-STYLE-SPEC")
        assert eng._client_phase_index(ph.id, manifest.phases)[0] is not None
        assert eng._render_client_report_msg(ph, "start") == ""


class TestScriptRetryIsInternal:
    def test_fail_once_then_pass_sends_nothing_and_logs_the_retry(self, tmp_path, monkeypatch):
        eng, manifest = _engine(tmp_path)
        eng.dry_run = False
        sent = tmp_path / "sent.jsonl"
        notify = tmp_path / "notify.sh"
        notify.write_text("#!/bin/sh\ncat >> \"$PD018B_SENT\"\necho >> \"$PD018B_SENT\"\nexit 0\n")
        notify.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(notify))
        monkeypatch.setenv("PD018B_SENT", str(sent))
        marker = tmp_path / "attempted"
        script = tmp_path / "flaky.sh"
        script.write_text(
            "#!/bin/sh\n"
            f"if [ -f '{marker}' ]; then exit 0; fi\n"
            f"touch '{marker}'\n"
            "exit 1\n")
        script.chmod(0o755)
        monkeypatch.setattr(phases_mod.time, "sleep", lambda *_: None)

        ph = manifest.phase("P4-RENDER")
        ph.executor_cmd = f"/bin/sh {script}"
        checkpoints = eng.run_dir / "working" / "checkpoints"
        checkpoints.mkdir(parents=True, exist_ok=True)
        rc = eng._run_script_phase_locked(ph, ["/bin/sh", str(script)], checkpoints,
                                          None, None)
        assert rc == EXIT_OK
        assert not sent.exists() or sent.read_text() == "", (
            "the client transport received the retry line")
        internal = [e for e in eng.state["events"] if e["kind"] == "report.internal"]
        assert internal, "the retry line is missing from the event log"
        assert any("Retrying" in e["message"] for e in internal)
        assert not [e for e in eng.state["events"] if e["kind"] == "report.blocked"]
