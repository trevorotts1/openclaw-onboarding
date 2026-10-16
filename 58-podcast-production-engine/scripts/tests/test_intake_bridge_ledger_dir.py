"""Trigger-flow bridge must link the REAL intake ledger, and a test intake stays 'test'."""
import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "webhook"))
import intake_handler  # noqa: E402
import ledger  # noqa: E402


def _bridge(tmp_path, monkeypatch, state):
    for k, v in (("HOME", tmp_path), ("PODCAST_DB_PATH", tmp_path / "e.db"),
                 ("PODCAST_JOBINDEX_DIR", tmp_path / "job-index"),
                 ("PODCAST_ENGINE_STATE_DIR", tmp_path / "state")):
        monkeypatch.setenv(k, str(v))
    monkeypatch.chdir(tmp_path)
    canonical = {"mode": "interview_style_podcast", "style": "provocative",
                 "contact_id": "CNTbridge000001", "location_id": "LOCbridge0000000001"}
    jk = "pd-CNTbridge000001-0000000000000001"
    ledger.claim(jk, canonical, state=state)  # base=None, exactly like the CLI path
    ledger._write_private(ledger.payload_path(jk), json.dumps(canonical))
    ok, job_id = intake_handler._bridge_to_sqlite(
        jk, canonical, None, {"route_id": "podcast-intake-bridge"})
    assert ok, job_id
    return jk, job_id


def test_bridge_links_real_ledger_not_cwd_none(tmp_path, monkeypatch):
    jk, job_id = _bridge(tmp_path, monkeypatch, "received")
    index = json.loads((tmp_path / "job-index" / (job_id + ".jobkey")).read_text())
    assert index["ledger_dir"] == str(ledger.ledger_dir(None))
    assert not (tmp_path / "None").exists()
    assert ledger.read_record(jk)["sqlite_job_id"] == job_id


def test_bridge_keeps_test_intake_in_test_state(tmp_path, monkeypatch):
    jk, job_id = _bridge(tmp_path, monkeypatch, "test")
    rec = ledger.read_record(jk)
    assert rec["state"] == "test" and rec["sqlite_job_id"] == job_id


def test_intake_self_test_never_touches_home(tmp_path):
    import subprocess
    env = {"HOME": str(tmp_path), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    r = subprocess.run([sys.executable, str(SCRIPTS / "webhook" / "intake_handler.py"), "--self-test"],
                       cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-800:]
    leaked = [p for p in (tmp_path / ".openclaw").rglob("*") if p.is_file()] if (tmp_path / ".openclaw").exists() else []
    assert leaked == [], leaked
