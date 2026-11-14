"""PD-201b — the door's test seam is an ENVIRONMENT variable, not a file.

Acceptance rows (from the unit text):

A1  A `.test-context` marker file is present and NONE of the three seam names
    (PRESENTATION_ALLOW_DEGRADED_VERIFIERS=1 / CI / OPENCLAW_TEST) is set:
    the dependency gate runs IN FULL — a missing required tool still exits 6 —
    and no `test_seam_used` row is written.

A2  PRESENTATION_ALLOW_DEGRADED_VERIFIERS=1: today's test behaviour (the
    dependency gate is bypassed) PLUS one
    `{"gate": "PRESENTATION_DEPS_MISSING", "result": "test_seam_used"}` row in
    working/checkpoints/gate_log.jsonl.

A3  every door test file passes — proved by the suite run, not by this file.

A1/A2 are a real pair: the same fixture flips only the environment name, so a
door that still honoured the marker file would pass A2 and FAIL A1 (exit 0
instead of 6), and a door with no seam at all would pass A1 and FAIL A2.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
_ENTRY_DEPLOYED = SCRIPTS / "presentation-canonical-entry.sh"
_ENTRY_REPO = SCRIPTS.parents[3] / "scripts" / "presentation-canonical-entry.sh"
ENTRY = _ENTRY_DEPLOYED if _ENTRY_DEPLOYED.is_file() else _ENTRY_REPO
assert ENTRY.is_file(), f"canonical entry script not found ({ENTRY})"

# Tools the door needs before (and inside) GATE 1. deliberately EXCLUDES
# soffice/pdftoppm/ffmpeg/tesseract so the dependency gate has something to be
# missing on every host.
_SHIM_TOOLS = (
    "bash", "date", "mkdir", "dirname", "tee", "sed", "cat", "printf", "grep",
    "env", "tr", "head", "cut", "wc", "sh", "python3", "rm", "mktemp", "cp",
    "mv", "sort", "uniq", "awk", "ln", "chmod", "tail", "sleep", "touch",
    "diff", "basename", "xargs", "find", "true", "false",
    "shasum", "sha256sum", "openssl",
)


def make_run_dir(base: Path) -> Path:
    """Same hermetic fixture contract as the other door tests."""
    run_dir = base / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    (run_dir / "working" / "interview").mkdir(parents=True)
    (run_dir / "working" / "copy").mkdir(parents=True)
    (run_dir / "working" / "interview" / "intake_ledger.json").write_text(
        json.dumps({"status": "complete", "complete": True}))
    (run_dir / "working" / "interview" / "intake_transcript.json").write_text(
        json.dumps({"format": "sp-intake-transcript-v1",
                    "driver": "deck-intake-driver",
                    "driver_signature": "fixture-signed",
                    "qid_sequence": ["q1", "q2"],
                    "turns": [{"q": "What topic?", "a": "A long enough answer " * 40}] * 10}))
    (run_dir / "slides.json").write_text("{}")
    return run_dir


def make_scripts_dir(base: Path) -> Path:
    d = base / "fake-scripts"
    d.mkdir(exist_ok=True)
    (d / "build_deck.py").write_text("import sys\nsys.exit(0)\n")
    (d / "run_signature_deck.py").write_text("import sys\nsys.exit(0)\n")
    (d / "presentation_job.py").write_text(
        "import sys\nif '--new' in sys.argv:\n    sys.exit(0)\nsys.exit(0)\n")
    (d / "presentation_job").mkdir(exist_ok=True)
    (d / "presentation_job" / "resolve_intake.py").write_text(
        "import argparse, json, sys\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--ledger'); p.add_argument('--out'); p.add_argument('--source')\n"
        "p.add_argument('--intake-depth', default=None)\n"
        "a = p.parse_args()\n"
        "json.dump({'presentation_type': 'signature_presentation'}, open(a.out, 'w'))\n"
        "print('intake resolved')\n"
        "sys.exit(0)\n")
    (d / "ghl_media.py").write_text(
        "def upload_media(*a, **k): pass\n"
        "def list_media(*a, **k): return {'data': []}\n"
        "def create_media_folder(*a, **k): pass\n")
    # PD-917/PD-010: GATE 1 reads its dependency LIST from the canon. Without
    # it the gate refuses with "dependency list unreadable" before it can name
    # a missing TOOL — this row is about the tool, so ship the real canon.
    shutil.copyfile(SCRIPTS / "presentation-deps.json",
                    d / "presentation-deps.json")
    (d / "sync_check.py").write_text(
        "import json, sys\n"
        "print(json.dumps({'in_sync': True, 'manifest_version': 39, 'drift': [],\n"
        "  'drift_summary': {'total': 0, 'render_path': 0, 'library_only': 0}}))\n"
        "sys.exit(0)\n")
    return d


def shim_path(base: Path) -> str:
    """A PATH with the door's own tools and none of the presentation deps."""
    bin_dir = base / "shim-bin"
    bin_dir.mkdir(exist_ok=True)
    for tool in _SHIM_TOOLS:
        real = shutil.which(tool)
        if real:
            (bin_dir / tool).symlink_to(real)
    return str(bin_dir)


def run_entry(run_dir: Path, scripts_dir: Path, path_value: str, seam: bool):
    env = dict(os.environ)
    # Remove every ambient seam name so A1 is hermetic on a CI host.
    for name in ("PRESENTATION_ALLOW_DEGRADED_VERIFIERS", "CI", "OPENCLAW_TEST"):
        env.pop(name, None)
    if seam:
        env["PRESENTATION_ALLOW_DEGRADED_VERIFIERS"] = "1"
    env["QC_SKIP_PRESENTATION_DEPS"] = "1"
    env["PATH"] = path_value
    env["OPENCLAW_WORKSPACE"] = str(run_dir.parent / "no-ws")
    cmd = ["bash", str(ENTRY), "--run-dir", str(run_dir),
           "--scripts-dir", str(scripts_dir),
           "--slides", str(run_dir / "slides.json"),
           "--out", str(run_dir / "out.pptx")]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=180)


def gate_log_rows(run_dir: Path):
    log = run_dir / "working" / "checkpoints" / "gate_log.jsonl"
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# A1 — the marker FILE opens nothing; the dependency gate runs in full.
# ---------------------------------------------------------------------------
def test_a1_marker_file_alone_does_not_open_the_seam(tmp_path):
    run_dir = make_run_dir(tmp_path)
    # The old seam: a file any agent could create.
    (run_dir / "working" / "checkpoints" / ".test-context").write_text("")
    scripts = make_scripts_dir(tmp_path)

    r = run_entry(run_dir, scripts, shim_path(tmp_path), seam=False)

    assert r.returncode == 6, (
        "a `.test-context` file must NOT skip the dependency gate; expected "
        f"exit 6 (PRESENTATION_DEPS_MISSING), got {r.returncode}\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    assert "PRESENTATION_DEPS_MISSING" in r.stderr, r.stderr
    # "...the dependency gate AND the intake gates run in full": the intake
    # gates (0, 0b) ran and passed BEFORE the dependency gate refused.
    assert "GATE 0 PASSED" in r.stdout, r.stdout
    assert "GATE 0b PASSED" in r.stdout, r.stdout
    assert "soffice" in r.stderr, (
        "the dependency gate must name the missing required tool\nstderr:\n" + r.stderr)

    rows = gate_log_rows(run_dir)
    seam_rows = [row for row in rows if row.get("result") == "test_seam_used"]
    assert not seam_rows, (
        f"the seam must not be recorded when it was never used: {seam_rows}")


# ---------------------------------------------------------------------------
# A1b — static guard: the seam test in the door is the env test, and no code
# line still conditions on the marker file path.
# ---------------------------------------------------------------------------
def test_a1b_static_seam_is_the_environment_test(tmp_path):
    src = ENTRY.read_text(encoding="utf-8", errors="replace")
    literal = ('[ "${PRESENTATION_ALLOW_DEGRADED_VERIFIERS:-}" = "1" ] '
               '|| [ -n "${CI:-}" ] || [ -n "${OPENCLAW_TEST:-}" ]')
    assert literal in src, (
        "the door does not carry the exact three-name environment test")

    offenders = []
    for i, line in enumerate(src.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if ".test-context" in line:
            offenders.append((i, stripped))
    assert not offenders, (
        "the door still conditions on the marker file: "
        + "; ".join(f"line {i}: {t}" for i, t in offenders))


# ---------------------------------------------------------------------------
# A2 — the environment name opens the seam AND leaves the audit row.
# ---------------------------------------------------------------------------
def test_a2_env_seam_bypasses_the_gate_and_writes_the_row(tmp_path):
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path)

    r = run_entry(run_dir, scripts, shim_path(tmp_path), seam=True)

    assert r.returncode == 0, (
        "PRESENTATION_ALLOW_DEGRADED_VERIFIERS=1 must let the fixture door "
        f"reach its stub engine; got {r.returncode}\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    assert "test seam" in (r.stdout + r.stderr), (
        "the honored bypass must say it used the test seam\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")

    rows = gate_log_rows(run_dir)
    seam_rows = [row for row in rows if row.get("result") == "test_seam_used"]
    assert seam_rows, f"no test_seam_used row in the gate log: {rows}"
    assert seam_rows[0].get("gate") == "PRESENTATION_DEPS_MISSING", seam_rows[0]
