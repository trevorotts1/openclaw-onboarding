"""PD-009 — the door and the drift gate must not fail OPEN.

Every row here is one acceptance row from the unit text:

  A1  a resolved department interpreter with NO `python3` on PATH -> the GHL
      module check, the bypass scan and the lockstep check all RUN (their OK
      lines appear). Before PD-009 each of them was guarded by
      `command -v python3`, so a venv interpreter skipped all three.
  A2  no usable interpreter at all -> exit 2 BEFORE GATE 0 passes.
  A3  removing sync_check.py from the fixture -> exit 7 AF-CANONICAL-RENDER-BYPASS.
  A4  300 bytes of `x` as the transcript -> exit 5 INTAKE-TRACE-INVALID.
  A5  the four-key envelope -> GATE 0b passes.
  A6  drift-gate GATE 8: define-and-never-call fails, define-and-call passes,
      commented-out call fails.
  A7  (read-only) every remaining `grep` in the two edited scripts is listed in
      BUILD-REPORT.md with its line and why it is not a gate decision.

Stub trees only. Nothing here touches a live box.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
_ENTRY_DEPLOYED = SCRIPTS / "presentation-canonical-entry.sh"
_ENTRY_REPO = SCRIPTS.parents[3] / "scripts" / "presentation-canonical-entry.sh"
ENTRY = _ENTRY_DEPLOYED if _ENTRY_DEPLOYED.is_file() else _ENTRY_REPO
assert ENTRY.is_file(), f"canonical entry script not found ({ENTRY})"

DRIFT_GATE = SCRIPTS / "presentations-drift-gates.sh"
assert DRIFT_GATE.is_file(), f"drift gate not found ({DRIFT_GATE})"

ENVELOPE = {
    "format": "sp-intake-transcript-v1",
    "driver_signature": "fixture-signed",
    "qid_sequence": ["q1", "q2"],
    "turns": [{"q": "What topic?", "a": "A long answer " * 20},
              {"q": "Who for?", "a": "A fixture audience"}],
}


# ---------------------------------------------------------------------------
# Run-dir / scripts-dir fixtures (the same contract the door tests use).
# ---------------------------------------------------------------------------
def make_run_dir(base: Path, transcript=ENVELOPE) -> Path:
    run_dir = base / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    (run_dir / "working" / "interview").mkdir(parents=True)
    (run_dir / "working" / "interview" / "intake_ledger.json").write_text(
        json.dumps({"status": "complete", "complete": True}))
    (run_dir / "working" / "interview" / "intake_transcript.json").write_text(
        json.dumps(transcript))
    (run_dir / "slides.json").write_text("{}")
    return run_dir


def make_scripts_dir(base: Path, *, with_sync_check: bool = True) -> Path:
    d = base / "fake-scripts"
    d.mkdir(exist_ok=True)
    (d / "build_deck.py").write_text("import sys\nsys.exit(0)\n")
    (d / "run_signature_deck.py").write_text("import sys\nsys.exit(0)\n")
    (d / "ghl_media.py").write_text(
        "def upload_media(*a, **k): pass\n"
        "def list_media(*a, **k): return {'data': []}\n"
        "def create_media_folder(*a, **k): pass\n")
    if with_sync_check:
        (d / "sync_check.py").write_text(
            "import json, sys\n"
            "print(json.dumps({'in_sync': True, 'manifest_version': 39, 'drift': [],\n"
            "                  'drift_summary': {'total': 0, 'render_path': 0, 'library_only': 0}}))\n"
            "sys.exit(0)\n")
    return d


def _run(run_dir: Path, scripts: Path, *, plan: bool, env_extra=None):
    env = dict(os.environ)
    env["QC_SKIP_PRESENTATION_DEPS"] = "1"
    # PD-201b: the test seam is an environment name, not a marker file.
    env["PRESENTATION_ALLOW_DEGRADED_VERIFIERS"] = "1"
    env["OPENCLAW_WORKSPACE"] = str(run_dir.parent / "no-ws")
    env.update(env_extra or {})
    cmd = ["/bin/bash", str(ENTRY), "--run-dir", str(run_dir),
           "--scripts-dir", str(scripts)]
    if plan:
        cmd.append("--plan")
    else:
        cmd += ["--slides", str(run_dir / "slides.json"),
                "--out", str(run_dir / "out.pptx")]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)


def _minimal_bin(base: Path, *, with_python: str | None) -> Path:
    """A PATH holding only the utilities the door needs, and NO `python3`
    binary — the box shape A1 and A2 describe."""
    b = base / "bin"
    b.mkdir()
    for tool in ("shasum", "mkdir", "rm", "dirname", "cat", "sed", "tr",
                 "awk", "wc", "chmod", "date", "grep", "env", "basename", "cp",
                 "mv", "ls"):
        found = shutil.which(tool)
        if found:
            (b / tool).symlink_to(found)
    if with_python:
        (b / "dept-python").symlink_to(with_python)
    return b


# ---------------------------------------------------------------------------
# A1 — the interpreter the door resolved is enough; `python3` on PATH is not
# the question.
# ---------------------------------------------------------------------------
def test_a1_gates_run_with_department_interpreter_and_no_python3(tmp_path):
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path)
    bin_dir = _minimal_bin(tmp_path, with_python=sys.executable)
    env = {"PATH": str(bin_dir),
           "PRESENTATION_PIPELINE_INTERPRETER": str(Path(sys.executable).resolve())}
    r = _run(run_dir, scripts, plan=True, env_extra=env)

    assert "command not found" not in r.stderr, r.stderr
    assert "OK: ghl_media importable" in r.stdout, (
        f"GATE 1b did not RUN under the resolved interpreter\nstdout:{r.stdout}\nstderr:{r.stderr}")
    assert "OK: no hand-rolled renderer/assembler found" in r.stdout, (
        f"GATE 2 did not RUN under the resolved interpreter\nstdout:{r.stdout}\nstderr:{r.stderr}")
    assert "OK: sync_check.py — renderer in lockstep" in r.stdout, (
        f"GATE 3 did not RUN under the resolved interpreter\nstdout:{r.stdout}\nstderr:{r.stderr}")
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"


# ---------------------------------------------------------------------------
# A2 — no usable interpreter: refuse before GATE 0 can pass.
# ---------------------------------------------------------------------------
def test_a2_no_interpreter_exits_2_before_gate0_passes(tmp_path):
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path)
    bin_dir = _minimal_bin(tmp_path, with_python=None)
    env = {"PATH": str(bin_dir)}
    env.pop("PRESENTATION_PIPELINE_INTERPRETER", None)
    env.pop("PRESENTATION_PIPELINE_PIN", None)
    r = _run(run_dir, scripts, plan=True, env_extra=env)

    assert r.returncode == 2, f"expected exit 2, got {r.returncode}\n{r.stdout}\n{r.stderr}"
    assert "PRESENTATION_INTERPRETER_INVALID" in r.stderr, r.stderr
    assert "GATE 1 of 7" not in r.stdout and "GATE 0 PASSED" not in r.stdout, (
        f"GATE 0 ran before the interpreter was proven\nstdout:{r.stdout}")


# ---------------------------------------------------------------------------
# A3 — sync_check.py absent is a FAILED pin, never a skipped one.
# ---------------------------------------------------------------------------
def test_a3_missing_sync_check_exits_7(tmp_path):
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path, with_sync_check=False)
    r = _run(run_dir, scripts, plan=True)
    assert r.returncode == 7, f"expected exit 7, got {r.returncode}\n{r.stdout}\n{r.stderr}"
    assert "AF-CANONICAL-RENDER-BYPASS" in r.stderr, r.stderr
    assert "sync_check.py is missing beside the renderer" in r.stderr, r.stderr


# ---------------------------------------------------------------------------
# A4 / A5 — the trace gate checks the envelope, not a byte count.
# ---------------------------------------------------------------------------
def test_a4_300_bytes_of_x_is_invalid(tmp_path):
    run_dir = make_run_dir(tmp_path)
    (run_dir / "working" / "interview" / "intake_transcript.json").write_text("x" * 300)
    scripts = make_scripts_dir(tmp_path)
    r = _run(run_dir, scripts, plan=False)
    assert r.returncode == 5, f"expected exit 5, got {r.returncode}\n{r.stdout}\n{r.stderr}"
    assert "INTAKE-TRACE-INVALID" in r.stderr, r.stderr


def test_a5_four_key_envelope_passes_gate0b(tmp_path):
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path)
    r = _run(run_dir, scripts, plan=False)
    assert "GATE 0b PASSED (intake transcript envelope valid)" in r.stdout, (
        f"stdout:{r.stdout}\nstderr:{r.stderr}")


# ---------------------------------------------------------------------------
# A6 — drift-gate GATE 8: the call must exist OUTSIDE the definition.
# ---------------------------------------------------------------------------
VALID_INSTALL = """#!/usr/bin/env bash
install_intake_poll_schedule() {
    local tpl="presentation-intake-poll.plist.template"
    _FIX61_RC=0
    install_poll_from "$tpl" || _FIX61_RC=$?
    return "$_FIX61_RC"
}
install_intake_poll_schedule
"""

NEVER_CALLED_INSTALL = VALID_INSTALL.replace("\ninstall_intake_poll_schedule\n", "\n")

COMMENTED_INSTALL = VALID_INSTALL.replace(
    "\ninstall_intake_poll_schedule\n", "\n# install_intake_poll_schedule\n")


def _drift_tree(base: Path, install_text: str) -> subprocess.CompletedProcess:
    repo = base / "repo"
    rscripts = repo / "23-ai-workforce-blueprint/templates/role-library/presentations/scripts"
    rscripts.mkdir(parents=True)
    gate = rscripts / "presentations-drift-gates.sh"
    shutil.copy2(DRIFT_GATE, gate)
    (rscripts / "build_deck.py").write_text("# stub\n")
    (rscripts / "presentation-intake-poll.plist.template").write_text("<plist/>\n")
    (rscripts / "presentation-intake-poll.sh").write_text("#!/bin/sh\nexit 0\n")
    (repo / "install.sh").write_text(install_text)

    manifest_obj = {"manifest_version": 1, "phases": []}
    repo_manifest = (repo / "23-ai-workforce-blueprint/universal-sops"
                    / "presentation-slide-craft/PIPELINE-MANIFEST.json")
    repo_manifest.parent.mkdir(parents=True)
    repo_manifest.write_text(json.dumps(manifest_obj))

    ws = base / "ws"
    dept = ws / "departments/Presentations"
    dscripts = dept / "scripts"
    dsops = dept / "sops"
    dscripts.mkdir(parents=True)
    dsops.mkdir(parents=True)
    for f in rscripts.iterdir():
        shutil.copy2(f, dscripts / f.name)
    dept_manifest = dsops / "PIPELINE-MANIFEST.json"
    dept_manifest.write_text(json.dumps(manifest_obj))
    stamp = hashlib.sha256(dept_manifest.read_bytes()).hexdigest()
    (dsops / "MANIFEST-SOURCE.txt").write_text(f"content_sha256={stamp}\n")

    env = dict(os.environ)
    env["OPENCLAW_WORKSPACE"] = str(ws)
    return subprocess.run(["/bin/bash", str(gate)], env=env,
                          capture_output=True, text=True, timeout=120)


def test_a6_gate8_defined_and_called_passes(tmp_path):
    r = _drift_tree(tmp_path, VALID_INSTALL)
    assert "GATE8_PASS" in r.stdout, f"{r.stdout}\n{r.stderr}"
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"


def test_a6_gate8_defined_but_never_called_fails(tmp_path):
    r = _drift_tree(tmp_path, NEVER_CALLED_INSTALL)
    assert "GATE8_FAIL" in r.stdout, f"{r.stdout}\n{r.stderr}"
    assert "never CALLS install_intake_poll_schedule" in r.stdout, r.stdout
    assert r.returncode == 11, f"expected exit 11, got {r.returncode}\n{r.stdout}\n{r.stderr}"


def test_a6_gate8_commented_call_fails(tmp_path):
    r = _drift_tree(tmp_path, COMMENTED_INSTALL)
    assert "GATE8_FAIL" in r.stdout, f"{r.stdout}\n{r.stderr}"
    assert "never CALLS install_intake_poll_schedule" in r.stdout, r.stdout
    assert r.returncode == 11, f"expected exit 11, got {r.returncode}"


# ---------------------------------------------------------------------------
# Item 8 (not an acceptance row, but the parser it replaces was a gate
# decision): a content_sha256 that is a SUBSTRING of another key must not be
# taken as the stamp.
# ---------------------------------------------------------------------------
def test_stamp_parse_requires_the_exact_key(tmp_path):
    repo = tmp_path / "repo"
    rscripts = repo / "23-ai-workforce-blueprint/templates/role-library/presentations/scripts"
    rscripts.mkdir(parents=True)
    gate = rscripts / "presentations-drift-gates.sh"
    shutil.copy2(DRIFT_GATE, gate)
    (rscripts / "build_deck.py").write_text("# stub\n")
    (rscripts / "presentation-intake-poll.plist.template").write_text("<plist/>\n")
    (rscripts / "presentation-intake-poll.sh").write_text("#!/bin/sh\nexit 0\n")
    (repo / "install.sh").write_text(VALID_INSTALL)
    manifest_obj = {"manifest_version": 1, "phases": []}
    repo_manifest = (repo / "23-ai-workforce-blueprint/universal-sops"
                    / "presentation-slide-craft/PIPELINE-MANIFEST.json")
    repo_manifest.parent.mkdir(parents=True)
    repo_manifest.write_text(json.dumps(manifest_obj))
    ws = tmp_path / "ws"
    dept = ws / "departments/Presentations"
    dscripts = dept / "scripts"
    dsops = dept / "sops"
    dscripts.mkdir(parents=True)
    dsops.mkdir(parents=True)
    for f in rscripts.iterdir():
        shutil.copy2(f, dscripts / f.name)
    dept_manifest = dsops / "PIPELINE-MANIFEST.json"
    dept_manifest.write_text(json.dumps(manifest_obj))
    stamp = hashlib.sha256(dept_manifest.read_bytes()).hexdigest()
    # A decoy whose key merely CONTAINS the word, ahead of the real line.
    (dsops / "MANIFEST-SOURCE.txt").write_text(
        f"xcontent_sha256={'0' * 64}\ncontent_sha256={stamp}\n")
    env = dict(os.environ)
    env["OPENCLAW_WORKSPACE"] = str(ws)
    r = subprocess.run(["/bin/bash", str(gate)], env=env,
                       capture_output=True, text=True, timeout=120)
    assert "OK: provenance stamp matches the department manifest" in r.stdout, (
        f"{r.stdout}\n{r.stderr}")
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
