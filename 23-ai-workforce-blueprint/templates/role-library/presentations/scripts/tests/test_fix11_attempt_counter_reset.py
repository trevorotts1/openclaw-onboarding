"""Fix 11 — the canonical-entry attempt counter never resets, so a run locks out on its 4th call.

THE DEFECT
`presentation-canonical-entry.sh` incremented `.canonical-entry-attempts` on
every non-`--plan` call, including successful ones and resumes. Nothing reset
it, so the 4th invocation of a healthy run died with "canonical entry
attempted 4 times (>3)".

THE FIX
- After a successful engine run (`_ENGINE_RC=0`) and after a successful
  fallback run (`_rc=0`), the attempt file is removed.
- The increment is skipped when `RESUME=1` and `state.json` exists.
- Applied to both copies of the script.

THE TEST (per the fix order): 4 calls with a stub engine that exits 0.
The 4th must not die.

The test copies the canonical entry script into a sandbox with a stub
`presentation_job.py` (the engine) that exits 0, then invokes the entry
script 4 times. All 4 must exit 0; specifically the 4th must not fail with
the attempt-cap message.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

# Both copies of the script (the fix applies to both).
SCRIPT_COPIES = [
    "23-ai-workforce-blueprint/scripts/presentation-canonical-entry.sh",
    "23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation-canonical-entry.sh",
]

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent


@pytest.fixture(params=SCRIPT_COPIES, ids=["scripts-copy", "templates-copy"])
def entry_script(request, tmp_path):
    """Sandbox with the canonical entry script and a stub engine."""
    src = REPO_ROOT / request.param
    if not src.exists():
        pytest.skip(f"script not found: {src}")

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    # The entry script expects presentation_job.py in its own directory.
    dst_script = sandbox / "presentation-canonical-entry.sh"
    shutil.copy2(src, dst_script)
    dst_script.chmod(dst_script.stat().st_mode | stat.S_IEXEC)

    # Stub engine: --new creates state.json, --run exits 0.
    stub = sandbox / "presentation_job.py"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        'if "--new" in args:\n'
        "    idx = args.index(\"--run-dir\")\n"
        "    run_dir = Path(args[idx + 1])\n"
        "    (run_dir / \"state.json\").write_text(json.dumps({\"job\": \"stub\"}))\n"
        "    sys.exit(0)\n"
        'if "--run" in args:\n'
        "    sys.exit(0)\n"
        "sys.exit(2)\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

    return dst_script


def _make_run_dir(tmp_path: Path, tag: str) -> Path:
    """Minimal run dir with slides.json."""
    run_dir = tmp_path / f"run-{tag}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "slides.json").write_text('{"slides": []}')
    return run_dir


def test_four_successful_calls_do_not_lock_out(entry_script, tmp_path):
    """4 calls with a stub engine exiting 0. The 4th must not die."""
    run_dir = _make_run_dir(tmp_path, "four-calls")
    out_file = tmp_path / "out.pdf"

    for i in range(1, 5):
        result = subprocess.run(
            [
                str(entry_script),
                "--run-dir", str(run_dir),
                "--slides", str(run_dir / "slides.json"),
                "--out", str(out_file),
                "--phase", "test",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(tmp_path),
        )
        # The 4th call must not die with the attempt-cap message.
        assert "canonical entry attempted" not in result.stderr, (
            f"call {i}: attempt counter locked out a healthy run:\n{result.stderr[-2000:]}"
        )
        assert result.returncode == 0, (
            f"call {i}: expected exit 0, got {result.returncode}:\n"
            f"STDOUT: {result.stdout[-2000:]}\nSTDERR: {result.stderr[-2000:]}"
        )

    # After 4 successful runs, the attempt file must not exist (reset on success).
    attempt_file = run_dir / "working" / "checkpoints" / ".canonical-entry-attempts"
    assert not attempt_file.exists(), (
        "attempt file still exists after successful runs — counter was not reset"
    )


def test_resume_does_not_consume_attempt_budget(entry_script, tmp_path):
    """--resume with an existing state.json skips the increment."""
    run_dir = _make_run_dir(tmp_path, "resume")
    # Pre-create state.json so the --resume path is a continuation.
    (run_dir / "state.json").write_text('{"job": "existing"}')
    out_file = tmp_path / "out.pdf"

    for i in range(1, 5):
        result = subprocess.run(
            [
                str(entry_script),
                "--run-dir", str(run_dir),
                "--resume",
                "--slides", str(run_dir / "slides.json"),
                "--out", str(out_file),
                "--phase", "test",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(tmp_path),
        )
        assert "canonical entry attempted" not in result.stderr, (
            f"resume call {i}: attempt counter consumed by a resume:\n{result.stderr[-2000:]}"
        )
        # FIX 11 QC correction: a resume that skips the increment must still
        # exit 0 — this catches an unbound-variable crash in the reset path.
        assert result.returncode == 0, (
            f"resume call {i}: expected exit 0, got {result.returncode}:\n"
            f"STDOUT: {result.stdout[-2000:]}\nSTDERR: {result.stderr[-2000:]}"
        )
