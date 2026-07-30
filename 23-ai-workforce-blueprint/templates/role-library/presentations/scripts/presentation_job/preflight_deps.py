"""U027 step 1 (start-up wiring) — runtime-dependency probe for the OCR readback,
called from Engine.run() (phases.py) before the phase loop and before a single
image is generated.

Audit D7(b) asks for tesseract + pytesseract as HARD runtime dependencies probed
before any paid generation. MASTER-SPEC 7.4 states it unconditionally: "The
missing OCR dependency fails at minute zero, before any paid generation, not
after 62 images." That is what this module now enforces.

History: this probe originally shipped WARN-MODE (Rule 3.5 stage 1) and always
returned 0. Measured on the operator box 2026-07-25: the tesseract BINARY was
present (5.5.2) but `pytesseract` was NOT importable from the interpreter the
pipeline uses (CPython 3.14). Flipping to fail-closed was staged as a SEPARATE
item whose stated prerequisite was `import pytesseract` succeeding under the
pipeline interpreter — enforcing it before that would have failed every build.

That prerequisite is now met on the operator box: verified 2026-07-30,
`import pytesseract` and `pytesseract.get_tesseract_version()` both succeed under
/opt/homebrew/bin/python3 (3.14.5). So this probe now enforces instead of only
warning — the same `_ocr_engine_available()` call the post-render readback
(`build_deck.py::_record_ocr_readback`) and the close()-time gate
(`gates.py::Gates._ocr_gate`, `NON_WAIVABLE_GATES`) already treat as fail-closed.
A box where the prerequisite is NOT met is exactly the case this exists to catch
— refusing there is the intended behaviour, not a regression. MASTER-SPEC's own
non-goals (§8, item 5, "Not a fleet rollout") scope rollout as operator machine,
then one client machine, then the fleet, precisely so this is proven
machine-by-machine rather than assumed fleet-wide; this change only proves the
operator machine.
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

    Fail-closed (MASTER-SPEC 7.4): returns 0 when the engine is available under
    THIS interpreter, 1 when it is not. The caller — Engine._preflight_ocr in
    phases.py — turns a non-zero return into a BLOCKED job before any phase runs
    and before a single image is generated or paid for.
    """
    # Lazy import so this module always loads even when prompt_gate is absent.
    try:
        from prompt_gate import _ocr_engine_available  # type: ignore[import-untyped]
    except ImportError:
        # prompt_gate is not importable at all — record honestly and refuse: without it,
        # the post-render readback and the close()-time gate can never run either.
        _record(run_dir, available=False, engine=None)
        _warn("prompt_gate is not importable — the OCR readback cannot run")
        return 1

    pytesseract_mod, _pil_image = _ocr_engine_available()
    available = pytesseract_mod is not None

    _record(run_dir, available=available, engine="pytesseract" if available else None)

    if not available:
        _warn(
            f"OCR engine NOT available under the pipeline interpreter "
            f"({sys.executable}, Python {sys.version.split()[0]}). "
            f"pytesseract is not importable and/or the tesseract binary is not on PATH. "
            f"MASTER-SPEC 7.4 requires this run to refuse now, before any paid image "
            f"generation — not after 62 images. Install pytesseract into the pipeline "
            f"interpreter: `{sys.executable} -m pip install pytesseract`. "
            f"The tesseract binary must also be installed and reachable on PATH "
            f"(e.g. `brew install tesseract`)."
        )
        return 1
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
    """Print one loud, unmissable block line."""
    bar = "=" * 78
    print(f"\n{bar}", file=sys.stderr)
    print("BLOCKED — OCR READBACK DEPENDENCY MISSING AT START-UP (U027)", file=sys.stderr)
    print(msg, file=sys.stderr)
    print(f"{bar}\n", file=sys.stderr)
