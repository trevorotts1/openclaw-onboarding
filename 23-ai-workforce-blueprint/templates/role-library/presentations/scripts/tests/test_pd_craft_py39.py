#!/usr/bin/env python3
"""PD-302 — the craft modules must run on the department's Python 3.9.

The reviewed craft_judgement.py bound ``_INTAKE = staticmethod(slide_craft._intake)``
at module scope. On Python 3.9 a ``staticmethod`` object is NOT callable (it became
callable in 3.10), so the first enforced check that reads the intake raised
TypeError and ``build_deck._chk_slide_craft`` failed on EVERY deck on a 3.9 box.
PD-302 binds the plain function instead (``_INTAKE = _sc._intake``).

These tests drive the real gate on a two-slide fixture: clean deck -> "" and a
deck whose hook sits on a declared footer/band slide -> the AF-HOOK-2 reason, on
both the 3.9 interpreter and the interpreter running the suite. When no 3.9
interpreter is present the 3.9 leg SKIPS and says so; nothing here claims a 3.9
run that did not happen.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent

# Six words: under the AF-OBI-2 nine-word headline ceiling.
HOOK = "Small steps still cross big rooms"

# Runs the exact gate the acceptance row names, in a child interpreter.
_PROBE = r"""
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import build_deck
sys.stdout.write(build_deck._chk_slide_craft(Path(sys.argv[2])))
"""


def _python39():
    """A Python 3.9 interpreter, or None. $PD302_PY39, then /usr/bin/python3,
    then python3.9 on PATH — each verified by asking it its own version."""
    candidates = []
    env = (os.environ.get("PD302_PY39") or "").strip()
    if env:
        candidates.append(env)
    candidates.append("/usr/bin/python3")
    alt = shutil.which("python3.9")
    if alt:
        candidates.append(alt)
    for exe in candidates:
        try:
            out = subprocess.run(
                [exe, "-I", "-c", "import sys; print(sys.version_info[:2])"],
                capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        if out.returncode == 0 and out.stdout.strip() == "(3, 9)":
            return exe
    return None


def _require_python39():
    exe = _python39()
    if exe is None:
        pytest.skip(
            "no Python 3.9 interpreter present (tried $PD302_PY39, "
            "/usr/bin/python3, python3.9 on PATH); the 3.9 leg of PD-302 was "
            "not run")
    return exe


def _fixture(run_dir, *, hook_in_footer):
    """Two slides, two copy blocks each, one canonical hook. The probe case
    declares a footer band on the hook slide; the clean case declares none."""
    copy_dir = run_dir / "working" / "copy"
    copy_dir.mkdir(parents=True)
    slides = [
        {"slide": 1,
         "copy": ["Every real change starts quietly",
                  "One honest hour beats a loud month"]},
        {"slide": 2,
         "copy": [HOOK, "The room remembers what you showed it"]},
    ]
    if hook_in_footer:
        slides[1]["layout"] = "footer band"
    (copy_dir / "slides.json").write_text(json.dumps(slides), encoding="utf-8")
    (copy_dir / "intake.json").write_text(json.dumps({"hook": HOOK}),
                                          encoding="utf-8")


def _gate_on(interpreter, run_dir):
    """build_deck._chk_slide_craft under `interpreter`; returns its reason."""
    proc = subprocess.run(
        [interpreter, "-I", "-c", _PROBE, str(SCRIPTS_DIR), str(run_dir)],
        capture_output=True, text=True, timeout=180, cwd=str(run_dir))
    assert proc.returncode == 0, (
        "build_deck._chk_slide_craft crashed under " + interpreter + "\n"
        + proc.stdout + proc.stderr)
    return proc.stdout


def test_clean_two_slide_fixture_passes_on_python_39(tmp_path):
    """A clean two-slide deck must return "" (no gate failure) on 3.9."""
    interpreter = _require_python39()
    run_dir = tmp_path / "clean"
    _fixture(run_dir, hook_in_footer=False)
    assert _gate_on(interpreter, run_dir) == ""


def test_hook_in_footer_is_named_af_hook_2_on_both_pythons(tmp_path):
    """The probe fixture is caught on 3.9 AND on the suite's interpreter."""
    interpreter = _require_python39()
    run_dir = tmp_path / "probe"
    _fixture(run_dir, hook_in_footer=True)

    on_39 = _gate_on(interpreter, run_dir)
    assert "AF-HOOK-2" in on_39, on_39

    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import build_deck  # noqa: E402 — path setup above must precede the import

    newer = build_deck._chk_slide_craft(run_dir)
    assert "AF-HOOK-2" in newer, newer
