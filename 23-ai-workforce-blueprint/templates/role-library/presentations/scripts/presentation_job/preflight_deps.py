"""U027 step 1 — runtime-dependency probe for the OCR readback.

Audit D7(b) asks for tesseract + pytesseract as HARD runtime dependencies probed
before any paid generation. Measured on the operator box 2026-07-25: the tesseract
BINARY is present (5.5.2) but `pytesseract` is NOT importable from the interpreter
the pipeline uses (CPython 3.14 — see the .cpython-314.pyc caches the engine
leaves in <dept>/scripts/__pycache__). prompt_gate._ocr_engine_available()
therefore returns (None, None) and the readback is silently off.

So this probe ships WARN-MODE (Rule 3.5 stage 1): it reports, it records, and it
returns success. Flipping it to fail-closed is a SEPARATE dated item that cannot
fire until pytesseract is importable from the pipeline interpreter on every
target box. Enforcing it today fails every build.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def probe_ocr(run_dir: Path) -> int:
    """Probe the OCR readback engine and record the result in state.json.

    Calls prompt_gate._ocr_engine_available() — the SAME function the readback
    uses — so the probe and the check can never disagree.  Records
    sys.executable and sys.version alongside the result; without those two facts
    the operator box failure is undiagnosable.

    WARN-MODE (Rule 3.5 stage 1): always returns 0.  Flipping to fail-closed is
    a SEPARATE dated item whose stated prerequisite is `import pytesseract`
    succeeding under the pipeline interpreter on every target box.
    """
    # Lazy import so this module always loads even when prompt_gate is absent.
    try:
        from prompt_gate import _ocr_engine_available  # type: ignore[import-untyped]
    except ImportError:
        # prompt_gate is not importable at all — record honestly.
        _record(run_dir, available=False, engine=None)
        _warn("prompt_gate is not importable — the OCR readback cannot run")
        return 0

    pytesseract_mod, _pil_image = _ocr_engine_available()
    available = pytesseract_mod is not None

    _record(run_dir, available=available, engine="pytesseract" if available else None)

    if not available:
        _warn(
            f"OCR engine NOT available under the pipeline interpreter "
            f"({sys.executable}, Python {sys.version.split()[0]}). "
            f"pytesseract is not importable. The postflight OCR readback gate "
            f"(check_ocr_readback) will block closeout until the binding is "
            f"installed. Install pytesseract into the pipeline interpreter: "
            f"`{sys.executable} -m pip install pytesseract`. "
            f"The tesseract binary must also be on PATH."
        )
    return 0


def _record(run_dir: Path, *, available: bool, engine: Optional[str]) -> None:
    """Write the probe result into state.json under runtime_deps.ocr."""
    state_path = run_dir / "state.json"
    try:
        existing = json.loads(state_path.read_text()) if state_path.exists() else {}
    except (json.JSONDecodeError, OSError):
        existing = {}
    existing.setdefault("runtime_deps", {})["ocr"] = {
        "available": available,
        "engine": engine,
        "python": sys.executable,
        "python_version": sys.version.split()[0],
        "probed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(existing, indent=2))
    except OSError:
        pass  # best-effort; the print is the primary alert


def _warn(msg: str) -> None:
    """Print one loud, unmissable warn line."""
    bar = "=" * 78
    print(f"\n{bar}", file=sys.stderr)
    print("WARNING — OCR READBACK DEPENDENCY MISSING (U027)", file=sys.stderr)
    print(msg, file=sys.stderr)
    print(f"{bar}\n", file=sys.stderr)
