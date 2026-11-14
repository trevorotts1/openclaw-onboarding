"""PD-005 — the legacy fallback must not return success.

When presentation_job.py is absent the door used to announce the fallback and
return run_signature_deck.py's exit code, so a 2-of-~20-phase legacy run that
happened to exit 0 looked exactly like a finished deck.

  A1  engine stub absent, no owner token -> exit 9, the fallback marker file
      exists, and the legacy runner stub was NEVER executed.
  A2  engine absent, owner token present, legacy stub exits 0 -> exit 10 and
      the operator is told this is a legacy build only.
  A3  engine present -> the engine stub's own exit code is returned unchanged.

Every test stubs the transport: the fake scripts dir holds no real runner and
no real engine, nothing is installed, downloaded or called.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent  # .../presentations/scripts
_ENTRY_DEPLOYED = SCRIPTS / "presentation-canonical-entry.sh"
_ENTRY_REPO = SCRIPTS.parents[3] / "scripts" / "presentation-canonical-entry.sh"
ENTRY = _ENTRY_DEPLOYED if _ENTRY_DEPLOYED.is_file() else _ENTRY_REPO

SYNC_OK = json.dumps({
    "in_sync": True, "manifest_version": 39, "drift": [],
    "drift_summary": {"total": 0, "render_path": 0, "library_only": 0},
})

ENGINE_RC = 7  # a distinctive engine exit code, so A3 cannot pass by accident


def _fake_scripts(tmp_path: Path, *, engine: bool) -> tuple[Path, Path]:
    """Fake SCRIPTS_DIR. `engine=False` leaves presentation_job.py absent (the
    legitimate fallback case). Returns (scripts_dir, legacy_marker)."""
    d = tmp_path / "fake-scripts"
    d.mkdir()
    (d / "build_deck.py").write_text("# stub build_deck\n")
    (d / "ghl_media.py").write_text(
        "def upload_media(*a, **k): pass\n"
        "def list_media(*a, **k): return {'data': []}\n"
        "def create_media_folder(*a, **k): pass\n"
    )
    (d / "_payload.json").write_text(SYNC_OK)
    (d / "sync_check.py").write_text(
        "import json, sys\n"
        "_P = json.load(open(%r))\n"
        "print(json.dumps(_P))\n"
        "sys.exit(0 if _P['in_sync'] else 4)\n" % str(d / "_payload.json")
    )
    legacy_marker = tmp_path / "legacy-ran.marker"
    # The legacy runner stub writes a file the instant it is executed, so A1 can
    # prove the stub never ran rather than only reading an exit code.
    (d / "run_signature_deck.py").write_text(
        "import os, pathlib, sys\n"
        "pathlib.Path(os.environ['PD005_LEGACY_MARKER']).write_text('ran')\n"
        "sys.exit(0)\n"
    )
    if engine:
        (d / "presentation_job").mkdir()
        (d / "presentation_job" / "__init__.py").write_text("")
        (d / "presentation_job" / "resolve_intake.py").write_text(
            "import json, sys\n"
            "a = sys.argv[1:]\n"
            "out = a[a.index('--out') + 1]\n"
            "json.dump({'presentation_type': 'signature_presentation'}, open(out, 'w'))\n"
            "print('resolved intake')\n"
            "sys.exit(0)\n"
        )
        (d / "presentation_job.py").write_text(
            "import sys\n"
            "a = sys.argv[1:]\n"
            "if '--new' in a:\n"
            "    sys.exit(0)\n"
            "if '--run' in a:\n"
            "    sys.exit(%d)\n"
            "sys.exit(0)\n" % ENGINE_RC
        )
    return d, legacy_marker


def _run_dir(tmp_path: Path, *, owner_token: bool) -> Path:
    run = tmp_path / "run"
    ckpt = run / "working" / "checkpoints"
    ckpt.mkdir(parents=True)
    (run / "working" / "interview").mkdir(parents=True)
    (run / "working" / "interview" / "intake_ledger.json").write_text(json.dumps({
        "status": "complete", "complete": True, "turns": 6,
        "entries": {
            "representation_mix": {"validated": True, "answer": "no people at all"},
            "grounded_content": {"validated": True, "answer": "the Momentum Method"},
        },
    }))
    (run / "working" / "interview" / "intake_transcript.json").write_text(json.dumps({
        "format": "sp-intake-transcript-v1",
        "driver_signature": "fixture-signed",
        "qid_sequence": ["interview_choice", "q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8"],
        "turns": [{"qid": "interview_choice", "answer": "A long enough fixture answer " * 8},
                  {"qid": "q1", "answer": "A grounded fixture answer " * 4}],
    }))
    if owner_token:
        (ckpt / "process_manifest.json").write_text(json.dumps({
            "owner_skip_approvals": [{
                "gate": "LEGACY-RUNNER-FALLBACK",
                "approved": True,
                "approved_by": "founder",
                "reason": "PD-005 test fixture",
            }],
        }))
    return run


def _run_entry(run: Path, scripts: Path, marker: Path):
    env = dict(os.environ)
    env["QC_SKIP_PRESENTATION_DEPS"] = "1"
    # PD-201b: the test seam is an environment name, not a marker file.
    env["PRESENTATION_ALLOW_DEGRADED_VERIFIERS"] = "1"
    env["OPENCLAW_WORKSPACE"] = str(run.parent / "no-such-workspace")
    env["PD005_LEGACY_MARKER"] = str(marker)
    slides = run / "slides.json"
    slides.write_text("{}")
    cmd = ["bash", str(ENTRY), "--run-dir", str(run), "--slides", str(slides),
           "--out", str(run / "out.pptx"), "--scripts-dir", str(scripts)]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)


def test_a1_engine_absent_without_owner_token_refuses(tmp_path):
    """A1: no engine, no owner token -> exit 9, marker recorded, legacy never run."""
    scripts, marker = _fake_scripts(tmp_path, engine=False)
    run = _run_dir(tmp_path, owner_token=False)
    r = _run_entry(run, scripts, marker)
    assert r.returncode == 9, f"expected exit 9, got {r.returncode}\n{r.stderr}"
    assert "AF-ENGINE-ABSENT" in r.stderr, r.stderr
    assert (run / "working" / "checkpoints" / ".fallback-legacy-runner-used").is_file()
    assert not marker.exists(), (
        "the legacy runner was executed without an owner token\n" + r.stdout + r.stderr)


def test_a2_owner_token_runs_legacy_but_never_exits_zero(tmp_path):
    """A2: engine absent, owner token present, legacy stub exits 0 -> exit 10."""
    scripts, marker = _fake_scripts(tmp_path, engine=False)
    run = _run_dir(tmp_path, owner_token=True)
    r = _run_entry(run, scripts, marker)
    assert marker.is_file(), (
        "the owner-approved legacy fallback must actually run\n" + r.stdout + r.stderr)
    assert r.returncode == 10, f"legacy success must exit 10, got {r.returncode}\n{r.stderr}"
    assert "LEGACY BUILD ONLY" in r.stderr, r.stderr
    assert "not a full deliverable bundle" in r.stderr, r.stderr


def test_a3_engine_present_is_unchanged(tmp_path):
    """A3: engine present -> the engine stub's own exit code is returned."""
    scripts, marker = _fake_scripts(tmp_path, engine=True)
    run = _run_dir(tmp_path, owner_token=False)
    r = _run_entry(run, scripts, marker)
    assert r.returncode == ENGINE_RC, (
        f"engine path must return the engine's exit code {ENGINE_RC}, got {r.returncode}\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    assert "AF-ENGINE-ABSENT" not in r.stderr, r.stderr
    assert "LEGACY BUILD ONLY" not in r.stderr, r.stderr
    assert not marker.exists(), "the engine path must never reach the legacy runner"


def test_header_documents_exit_10_and_the_gate_code():
    """The door's header must document exit 10 and AF-ENGINE-ABSENT (PD-005)."""
    src = ENTRY.read_text(encoding="utf-8", errors="replace")
    head = src.split("set -uo pipefail", 1)[0]
    assert "AF-ENGINE-ABSENT" in head
    assert "LEGACY BUILD ONLY" in head
    assert "10 —" in head
