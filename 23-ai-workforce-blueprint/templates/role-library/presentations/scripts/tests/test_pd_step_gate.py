"""PD-030 -- the runner's mechanical step gate (scripts/pd_step_gate.py).

The gate exists because a running agent could "check" a step by matching text or
"report" a step by printing a success line. These tests exercise the real script
as a subprocess: they write the artifacts, the intake, the engine state.json and
the manifest, then assert on the exit code and the printed reasons. Nothing here
calls a model, a network service or the engine itself.

Acceptance rows A1-A7 of PD-030 map one-to-one onto the test_aN_* names.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
GATE = SCRIPTS / "pd_step_gate.py"
sys.path.insert(0, str(SCRIPTS))

# Same resolution the department's other tests use for the real manifest.
REAL_MANIFEST = (SCRIPTS.parent.parent.parent.parent.parent
                 / "universal-sops" / "presentation-slide-craft"
                 / "PIPELINE-MANIFEST.json")


def run_gate(*args):
    return subprocess.run([sys.executable, "-I", str(GATE)] + [str(a) for a in args],
                          capture_output=True, text=True, timeout=120)


def write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_json(path: Path, obj) -> Path:
    return write(path, json.dumps(obj))


def fixture_manifest(tmp_path: Path, phases: list, bundle=None, deliverables=None) -> Path:
    return write_json(tmp_path / "manifest.json", {
        "manifest_version": 1,
        "phases": phases,
        "deliverables_required": deliverables or [],
        "build_bundle_files": bundle or [],
    })


def phase(pid: str, order: float, produces=None, consumes=None, defers=None) -> dict:
    row = {"id": pid, "order": order, "name": pid,
           "produces_artifact": produces or [], "consumes": consumes or []}
    if defers:
        row["defers_unless"] = defers
    return row


# ---------------------------------------------------------------------------
# The two constants PD-030 orders verified against the engine (not guessed).
# ---------------------------------------------------------------------------
def test_constants_match_the_engine():
    from presentation_job import phases as engine_phases
    from presentation_job import state as engine_state
    import pd_step_gate as gate

    assert gate.DONE_STATES == {engine_phases.PHASE_STATUS_DONE}
    assert gate.SKIP_STATUSES == {engine_phases.PHASE_STATUS_DEFERRED,
                                  engine_phases.PHASE_STATUS_OBSOLETE}
    assert gate.STATE_FILENAME == engine_state.STATE_FILENAME == "state.json"
    # phases.py close() writes the literal "DONE" (lines 5651 and 5726).
    assert gate.CLOSED_TERMINALS == {"DONE"}


# ---------------------------------------------------------------------------
# A1 -- before PHASE with no receipts refuses, naming a missing earlier phase.
# ---------------------------------------------------------------------------
def test_a1_before_without_receipts_refuses(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    proc = run_gate("before", "P4-RENDER", "--run-dir", run, "--manifest", REAL_MANIFEST)
    assert proc.returncode == 5, proc.stdout + proc.stderr
    assert "REFUSED" in proc.stdout
    assert "no step-gate receipt for" in proc.stdout


# ---------------------------------------------------------------------------
# A2 -- after P4-PROMPT: 3 prompt files for a 5-slide deck is a refusal.
# ---------------------------------------------------------------------------
def test_a2_after_requires_one_prompt_per_slide(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    write_json(run / "working" / "copy" / "slides.json",
               [{"slide_number": n} for n in range(1, 6)])
    for n in (1, 2, 3):
        write(run / "working" / "prompts" / ("slide-%02d.txt" % n),
              "Prompt for slide %d, in plain words.\n" % n)
    proc = run_gate("after", "P4-PROMPT", "--run-dir", run, "--manifest", REAL_MANIFEST)
    assert proc.returncode == 5, proc.stdout + proc.stderr
    assert "matched 3 file(s) but the deck has 5 slides" in proc.stdout
    assert not (run / "working" / "checkpoints" / "step-gate" / "P4-PROMPT.json").exists()


# ---------------------------------------------------------------------------
# A3 -- a passing `after` writes a receipt; one byte changed afterwards is a
# refusal at the next `before`.
# ---------------------------------------------------------------------------
def test_a3_receipt_pins_the_bytes(tmp_path):
    manifest = fixture_manifest(tmp_path, [
        phase("P-A", 1, produces=["out/a.json"]),
        phase("P-B", 2, produces=["out/b.json"], consumes=["out/a.json"]),
    ])
    run = tmp_path / "run"
    a = write_json(run / "out" / "a.json", {"slides": 1})
    write_json(run / "out" / "b.json", {"ok": True})

    after = run_gate("after", "P-A", "--run-dir", run, "--manifest", manifest)
    assert after.returncode == 0, after.stdout + after.stderr
    receipt = run / "working" / "checkpoints" / "step-gate" / "P-A.json"
    assert receipt.is_file()

    ok = run_gate("before", "P-B", "--run-dir", run, "--manifest", manifest)
    assert ok.returncode == 0, ok.stdout + ok.stderr

    a.write_text(a.read_text(encoding="utf-8") + " ", encoding="utf-8")
    changed = run_gate("before", "P-B", "--run-dir", run, "--manifest", manifest)
    assert changed.returncode == 5, changed.stdout + changed.stderr
    assert "changed after its gate" in changed.stdout


# ---------------------------------------------------------------------------
# A4 -- a 5 KiB PNG is refused.
# ---------------------------------------------------------------------------
def test_a4_small_png_is_refused(tmp_path):
    manifest = fixture_manifest(tmp_path, [
        phase("P-IMG", 1, produces=["renders/slide-1.png"]),
    ])
    run = tmp_path / "run"
    png = run / "renders" / "slide-1.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024))
    proc = run_gate("after", "P-IMG", "--run-dir", run, "--manifest", manifest)
    assert proc.returncode == 5, proc.stdout + proc.stderr
    assert "PNG under 20 KiB" in proc.stdout


# ---------------------------------------------------------------------------
# A5 -- a JSON product holding {} is refused.
# ---------------------------------------------------------------------------
def test_a5_empty_json_is_refused(tmp_path):
    manifest = fixture_manifest(tmp_path, [
        phase("P-JSON", 1, produces=["working/copy/report.json"]),
    ])
    run = tmp_path / "run"
    write(run / "working" / "copy" / "report.json", "{}")
    proc = run_gate("after", "P-JSON", "--run-dir", run, "--manifest", manifest)
    assert proc.returncode == 5, proc.stdout + proc.stderr
    assert "JSON is empty" in proc.stdout


# ---------------------------------------------------------------------------
# A6 -- complete needs every receipt, every bundle floor AND a closed engine
# state; the unclosed state is the only thing wrong in the first half, and the
# closed state is the control that lets the same run pass.
# ---------------------------------------------------------------------------
def test_a6_complete_requires_a_closed_engine_state(tmp_path):
    manifest = fixture_manifest(
        tmp_path,
        [phase("P-A", 1, produces=["work/a.json"]),
         phase("P-B", 2, produces=["work/b.json"])],
        bundle=["deck"],
        deliverables=[{"key": "deck", "filename": "deck.txt", "min_bytes": 10}],
    )
    run = tmp_path / "run"
    write_json(run / "work" / "a.json", {"a": 1})
    write_json(run / "work" / "b.json", {"b": 1})
    write(run / "working" / "deck.txt", "0123456789")
    for pid in ("P-A", "P-B"):
        done = run_gate("after", pid, "--run-dir", run, "--manifest", manifest)
        assert done.returncode == 0, done.stdout + done.stderr

    write_json(run / "state.json", {"job_id": "j1", "schema_version": 1,
                                    "terminal": "BLOCKED"})
    blocked = run_gate("complete", "--run-dir", run, "--manifest", manifest)
    assert blocked.returncode == 5, blocked.stdout + blocked.stderr
    assert "not closed" in blocked.stdout

    write_json(run / "state.json", {"job_id": "j1", "schema_version": 1,
                                    "terminal": "DONE"})
    passed = run_gate("complete", "--run-dir", run, "--manifest", manifest)
    assert passed.returncode == 0, passed.stdout + passed.stderr


# ---------------------------------------------------------------------------
# A7 -- an unreadable intake is CANNOT DETERMINE (2), never a pass (0).
# ---------------------------------------------------------------------------
def test_a7_unreadable_intake_is_exit_2(tmp_path):
    run = tmp_path / "run"
    write(run / "working" / "copy" / "intake.json", "{ this is not json")
    proc = run_gate("before", "P4-RENDER", "--run-dir", run, "--manifest", REAL_MANIFEST)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "CANNOT DETERMINE" in proc.stdout
