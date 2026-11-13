"""PD-002a — --slides/--out are required by the LEGACY runner only.

The door used to demand --slides and --out before any gate ran, so the sanctioned
path forced a slides.json to be invented before copywriting, while the engine it
actually dispatches reads and writes inside --run-dir.

  A1  engine stub present, no --slides, no --out -> the engine stub IS dispatched.
  A2  engine absent, owner token present, no --slides -> exit 2 with the existing
      "--slides is required" message (the requirement moved into the fallback).
  A3  engine present WITH --slides/--out -> the NOTE is printed and the engine
      still runs.

Every test stubs the transport: the fake scripts dir holds no real runner, no
real engine, and nothing is installed, downloaded or called.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent  # .../presentations/scripts
_ENTRY_DEPLOYED = SCRIPTS / "presentation-canonical-entry.sh"
_ENTRY_REPO = SCRIPTS.parents[3] / "scripts" / "presentation-canonical-entry.sh"
ENTRY = _ENTRY_DEPLOYED if _ENTRY_DEPLOYED.is_file() else _ENTRY_REPO

SYNC_OK = json.dumps({
    "in_sync": True, "manifest_version": 39, "drift": [],
    "drift_summary": {"total": 0, "render_path": 0, "library_only": 0},
})

ENGINE_RC = 7  # distinctive, so A1 cannot pass by accident
NOTE = ("NOTE: --slides/--out are used only by the legacy runner; the engine "
        "reads and writes inside --run-dir")


def _fake_scripts(tmp_path: Path, *, engine: bool):
    """Fake SCRIPTS_DIR. `engine=False` leaves presentation_job.py absent (the one
    legitimate fallback). Returns (scripts_dir, engine_dispatched_marker)."""
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
    marker = tmp_path / "engine-ran.marker"
    (d / "run_signature_deck.py").write_text(
        "import os, pathlib\n"
        "pathlib.Path(os.environ['PD002A_LEGACY_MARKER']).write_text('ran')\n"
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
            "import os, pathlib, sys\n"
            "a = sys.argv[1:]\n"
            "if '--new' in a:\n"
            "    sys.exit(0)\n"
            "if '--run' in a:\n"
            "    pathlib.Path(os.environ['PD002A_ENGINE_MARKER']).write_text('ran')\n"
            "    sys.exit(%d)\n"
            "sys.exit(0)\n" % ENGINE_RC
        )
    return d, marker


def _run_dir(tmp_path: Path, *, owner_token: bool) -> Path:
    run = tmp_path / "run"
    ckpt = run / "working" / "checkpoints"
    ckpt.mkdir(parents=True)
    # The deps gate honors QC_SKIP_PRESENTATION_DEPS=1 only with this marker.
    (ckpt / ".test-context").write_text("")
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
                "reason": "PD-002a test fixture",
            }],
        }))
    return run


def _run_entry(run: Path, scripts: Path, *, with_slides: bool):
    env = dict(os.environ)
    env["QC_SKIP_PRESENTATION_DEPS"] = "1"
    env["OPENCLAW_WORKSPACE"] = str(run.parent / "no-such-workspace")
    env["PD002A_LEGACY_MARKER"] = str(run.parent / "legacy-ran.marker")
    env["PD002A_ENGINE_MARKER"] = str(run.parent / "engine-ran.marker")
    cmd = ["bash", str(ENTRY), "--run-dir", str(run), "--scripts-dir", str(scripts)]
    if with_slides:
        slides = run / "slides.json"
        slides.write_text("{}")
        cmd += ["--slides", str(slides), "--out", str(run / "out.pptx")]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)


def test_a1_engine_dispatched_without_slides_or_out(tmp_path):
    """A1: engine present, no --slides and no --out -> the engine runs."""
    scripts, _ = _fake_scripts(tmp_path, engine=True)
    run = _run_dir(tmp_path, owner_token=False)
    r = _run_entry(run, scripts, with_slides=False)
    assert r.returncode == ENGINE_RC, (
        f"the engine must be dispatched without --slides/--out; got {r.returncode}\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    assert (tmp_path / "engine-ran.marker").is_file(), "the engine stub never ran"
    assert not (tmp_path / "legacy-ran.marker").exists(), "the legacy runner must not run"
    assert NOTE not in r.stdout, "no --slides/--out were supplied, so no NOTE"


def test_a2_legacy_fallback_still_requires_slides(tmp_path):
    """A2: engine absent, owner token, no --slides -> exit 2, same message as before."""
    scripts, _ = _fake_scripts(tmp_path, engine=False)
    run = _run_dir(tmp_path, owner_token=True)
    r = _run_entry(run, scripts, with_slides=False)
    assert r.returncode == 2, (
        f"the legacy fallback must require --slides; got {r.returncode}\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    assert "--slides is required" in r.stderr, r.stderr
    assert not (tmp_path / "legacy-ran.marker").exists(), (
        "the legacy runner must not be dispatched without --slides")


def test_a3_note_printed_when_supplied_on_the_engine_path(tmp_path):
    """A3: engine present WITH --slides/--out -> NOTE printed, engine still runs."""
    scripts, _ = _fake_scripts(tmp_path, engine=True)
    run = _run_dir(tmp_path, owner_token=False)
    r = _run_entry(run, scripts, with_slides=True)
    assert r.returncode == ENGINE_RC, f"got {r.returncode}\n{r.stdout}\n{r.stderr}"
    assert NOTE in r.stdout, f"expected the NOTE; stdout:\n{r.stdout}"
    assert (tmp_path / "engine-ran.marker").is_file(), "the engine stub never ran"
