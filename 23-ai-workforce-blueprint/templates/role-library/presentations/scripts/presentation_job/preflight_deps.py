"""U027 step 1 + FIX 33 — runtime-dependency probe for the OCR readback.

FIX 33 (presentation rev2 waves) replaces the old "if true" handling of the
2026-07-25 observation ("pytesseract not importable from the pipeline
interpreter") with the Step 0 VERIFY-THEN-FIX protocol, in
presentation_job/ocr_verify.py:

  Step 0 (VERIFY): a read-only, 5-minute-timeboxed probe through the EXACT
  interpreter the canonical entry (FIX 31) resolves for the pipeline,
  recording interpreter path/version, pytesseract import + module path,
  tesseract binary discovery/version, and a REAL one-line fixture OCR. It
  writes a redacted JSON receipt.

  Branch A (present + functional — the measured state on this box
  2026-08-31): NO package/system change. The observed compatible versions are
  pinned in the portable dependency manifest (ocr-deps.json); the launcher
  preflight (launcher.ocr_launch_preflight) invokes the same interpreter and
  a one-line smoke; the stale on-box warning below is REPLACED by the green
  receipt. A different interpreter later selected fails launch rather than
  borrowing this receipt.

  Branch B (missing or broken): install the pinned pytesseract into the
  pipeline's DEDICATED venv (never global Python) and point the canonical
  entry at that venv, or provision the native tesseract binary with an
  explicit path; then re-run the same probe. Launch stays a hard failure
  naming the exact failed layer until import, binary version, and real OCR
  all pass.

FLAG: PRESENTATION_OCR_VERIFY (default ON) selects the Step 0 protocol.
=0 restores the pre-fix warn-mode probe (documented rollback; see
legacy_probe_ocr).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import ocr_verify


def probe_ocr(run_dir: Path) -> int:
    """FIX 33 probe entry: run Step 0 verify, record the receipt in state.json,
    and print the branch verdict. Warn-mode on Branch B / undetermined (never a
    silent pass, never an install) — the LAUNCH refusal is launcher.ocr_launch_
    preflight()'s job, and the Phase-0 hard-abort is run_signature_deck's
    ocr_engine_preflight; this probe REPORTS and RECORDS.

    With PRESENTATION_OCR_VERIFY=0 this routes to legacy_probe_ocr (the exact
    pre-fix behavior — documented rollback path).
    """
    if not ocr_verify.verify_enabled():
        return legacy_probe_ocr(run_dir)

    receipt = ocr_verify.step0_verify(run_dir=run_dir)
    _record_receipt(run_dir, receipt)
    branch = receipt.get("branch")

    if branch == "A":
        drift = ocr_verify.check_against_pins(receipt)
        print(
            f"=== OCR Step 0 (FIX 33): BRANCH A — dependency present and functional "
            f"under the pipeline interpreter ({receipt.get('interpreter')}, "
            f"Python {receipt.get('python_version')}) ===",
            file=sys.stderr)
        print(
            f"    pytesseract {receipt.get('pytesseract_module')} importable; "
            f"tesseract {receipt.get('tesseract_version')} at "
            f"{receipt.get('tesseract_binary')}; real fixture OCR read back "
            f"'{receipt.get('fixture_ocr_text', '').strip()}'",
            file=sys.stderr)
        if drift:
            for d in drift:
                print(f"    PIN DRIFT (recorded, not fatal): {d}", file=sys.stderr)
        print(
            "    No package/system change made (Branch A). The green receipt is "
            "written under working/checkpoints/ocr-step0-receipt.json; the "
            "2026-07-25 'pytesseract not importable' warning no longer applies.",
            file=sys.stderr)
        return 0

    layers = ocr_verify.failed_layers(receipt) or ["probe could not measure the OCR stack"]
    _branch_b_banner(receipt, layers)
    return 0


def _branch_b_banner(receipt, layers) -> None:
    """The Branch B / undetermined report — loud, actionable, never an install."""
    bar = "=" * 78
    print(f"\n{bar}", file=sys.stderr)
    print("OCR Step 0 (FIX 33) — BRANCH B / NOT VERIFIED", file=sys.stderr)
    print(
        f"Pipeline interpreter: {receipt.get('interpreter')} "
        f"(Python {receipt.get('python_version', '?')}), "
        f"probe_status={receipt.get('probe_status')}", file=sys.stderr)
    print("Failed layer(s):", file=sys.stderr)
    for layer in layers:
        print(f"  - {layer}", file=sys.stderr)
    print(
        "Branch B fix (explicit, never implicit): install the pinned pytesseract "
        "(ocr-deps.json) into the pipeline's DEDICATED venv — never global Python — "
        "and point PRESENTATION_PIPELINE_INTERPRETER at that venv; or provision the "
        "native tesseract binary with an explicit path. Then re-run this probe. "
        "Launch stays a hard failure until import, binary version, and real OCR "
        "all pass.", file=sys.stderr)
    print(f"{bar}\n", file=sys.stderr)


def _record_receipt(run_dir: Path, receipt: dict) -> None:
    """Write the Step 0 result into state.json under runtime_deps.ocr —
    the full redacted receipt plus the derived branch, so a run's state
    outlives the launch log line."""
    state_path = Path(run_dir) / "state.json"
    try:
        existing = json.loads(state_path.read_text()) if state_path.exists() else {}
    except (json.JSONDecodeError, OSError):
        existing = {}
    entry = dict(receipt)
    entry["available"] = receipt.get("branch") == "A"
    entry["engine"] = "pytesseract" if entry["available"] else None
    entry["probed_at"] = receipt.get("probed_at") or datetime.now(timezone.utc).isoformat()
    existing.setdefault("runtime_deps", {})["ocr"] = entry
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(existing, indent=2))
    except OSError:
        pass  # best-effort; the print is the primary alert


# ---------------------------------------------------------------------------
# LEGACY (pre-FIX-33) probe — retained verbatim as the PRESENTATION_OCR_VERIFY=0
# rollback path. Do not extend; the Step 0 protocol above is the live path.
# ---------------------------------------------------------------------------
def legacy_probe_ocr(run_dir: Path) -> int:
    """Pre-FIX-33 warn-mode probe (rollback path, PRESENTATION_OCR_VERIFY=0).

    Calls prompt_gate._ocr_engine_available() — the SAME function the readback
    uses — so the probe and the check can never disagree. Records sys.executable
    and sys.version alongside the result.

    WARN-MODE (Rule 3.5 stage 1): always returns 0.
    """
    try:
        from prompt_gate import _ocr_engine_available  # type: ignore[import-untyped]
    except ImportError:
        _legacy_record(run_dir, available=False, engine=None)
        _legacy_warn("prompt_gate is not importable — the OCR readback cannot run")
        return 0

    pytesseract_mod, _pil_image = _ocr_engine_available()
    available = pytesseract_mod is not None

    _legacy_record(run_dir, available=available, engine="pytesseract" if available else None)

    if not available:
        _legacy_warn(
            f"OCR engine NOT available under the pipeline interpreter "
            f"({sys.executable}, Python {sys.version.split()[0]}). "
            f"pytesseract is not importable. The postflight OCR readback gate "
            f"(check_ocr_readback) will block closeout until the binding is "
            f"installed. Install pytesseract into the pipeline interpreter: "
            f"`{sys.executable} -m pip install pytesseract`. "
            f"The tesseract binary must also be on PATH."
        )
    return 0

def _legacy_record(run_dir: Path, *, available: bool, engine: Optional[str]) -> None:
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

def _legacy_warn(msg: str) -> None:
    """Print one loud, unmissable warn line."""
    bar = "=" * 78
    print(f"\n{bar}", file=sys.stderr)
    print("WARNING — OCR READBACK DEPENDENCY MISSING (U027)", file=sys.stderr)
    print(msg, file=sys.stderr)
    print(f"{bar}\n", file=sys.stderr)
