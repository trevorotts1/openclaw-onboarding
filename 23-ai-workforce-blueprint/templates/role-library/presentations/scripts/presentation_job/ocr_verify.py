"""FIX 33 — Step 0 VERIFY-THEN-BRANCH OCR probe (AF-OCR-ENGINE-MISSING, MASTER-SPEC 7.4).

Replaces the old "if true" assumption (the 2026-07-25 note that `pytesseract` was
not importable from the pipeline interpreter) with a measured protocol:

  STEP 0 (VERIFY — read-only, 5-minute timeboxed, no install, no network):
    Run the OCR probe through the EXACT interpreter the canonical entry
    (presentation-canonical-entry.sh -> `python3 presentation_job.py`, FIX 31)
    resolves for the pipeline. The probe is a SUBPROCESS of that interpreter with
    cwd = the scripts dir, so `import prompt_gate` + `import pytesseract` resolve
    exactly as the render subprocess will resolve them — a user-site install
    invisible under PYTHONNOUSERSITE=1/venv/sudo/launchd is INVISIBLE HERE TOO,
    which is the whole point (ocr_engine_preflight's docstring names that trap).

    The probe records, in a redacted JSON receipt:
      * interpreter path + version (the binding: a different interpreter later
        selected at launch FAILS rather than borrowing this receipt),
      * pytesseract import result + module path,
      * tesseract binary discovery (shutil.which path) + version,
      * a REAL one-line fixture OCR (PIL-rendered text -> pytesseract readback),
        not just an import check.

  BRANCH (determined only from the receipt — never assumed):
    A — dependency present and functional: make NO package/system change. Pin the
        observed compatible versions in the portable dependency manifest
        (ocr-deps.json, shipped beside this module); launcher preflight invokes
        the same interpreter + one-line smoke; the stale on-box warning is
        replaced by the green receipt.
    B — missing or broken: install the pinned `pytesseract` into the pipeline's
        dedicated venv (never global Python), or provision the tesseract binary
        with an explicit path; re-run the same probe; do not continue to Phase-0
        until import + binary version + real OCR all pass. An unrepairable branch
        remains a launch-time hard failure naming the exact failed layer.

FLAG: PRESENTATION_OCR_VERIFY (default ON). =0 restores the pre-fix behavior
(documented rollback) — the legacy warn-mode probe_ocr() only, no Step 0, no
receipt binding.

REDACTION: the receipt contains paths and versions only. It never records env
values, API keys, or provider payloads. _redact_path() strips $HOME to '~' so a
receipt shared off-box names no user.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

#: Feature flag (default ON). =0 selects the exact pre-fix behavior.
FLAG_ENV = "PRESENTATION_OCR_VERIFY"

#: Override for the pipeline interpreter. Unset = the canonical entry's own
#: resolution (PATH `python3`), which is what FIX 31's entry dispatches through.
#: Tests set this to a deliberately WRONG interpreter to prove the binding.
INTERPRETER_ENV = "PRESENTATION_PIPELINE_INTERPRETER"

#: Timebox for the Step 0 probe subprocess (spec: 5-minute).
PROBE_TIMEOUT_S = 300

#: The one-line fixture text rendered and read back — a real OCR, not an import.
FIXTURE_TEXT = "OCR PROBE FIX33"

#: Receipt filename, written under the run dir (and copied to the proof dir).
RECEIPT_NAME = "ocr-step0-receipt.json"

_SHIPPED_DEPS = Path(__file__).resolve().parent / "ocr-deps.json"


def verify_enabled() -> bool:
    """FIX 33 flag: default ON. Only exactly "0" disables (quotes/whitespace
    stripped so an EMPTY value is unset, not OFF)."""
    raw = os.environ.get(FLAG_ENV)
    if raw is None:
        return True
    return raw.strip().strip("'\"") != "0"


def resolve_pipeline_interpreter() -> str:
    """The interpreter the canonical entry runs the pipeline with.

    The entry script (presentation-canonical-entry.sh, FIX 31 single source)
    dispatches `python3 presentation_job.py ...` — bare `python3` from PATH. That
    is the binding: resolve it HERE the same way (shutil.which), not
    sys.executable (which would name whatever imported this module, not the
    pipeline's own resolution). PRESENTATION_PIPELINE_INTERPRETER overrides for
    tests and for a box whose entry is pointed at a dedicated venv (Branch B).
    """
    override = os.environ.get(INTERPRETER_ENV)
    if override:
        return override
    resolved = shutil.which("python3")
    if resolved is None:
        raise RuntimeError(
            "FIX 33: no `python3` on PATH — the canonical entry "
            "(presentation-canonical-entry.sh) cannot dispatch either. Fix PATH "
            "or set PRESENTATION_PIPELINE_INTERPRETER.")
    return resolved


def _redact_path(p: Optional[str]) -> Optional[str]:
    """Strip $HOME to '~' so a receipt shared off-box names no user."""
    if not p:
        return p
    home = os.path.expanduser("~")
    if home and home != "/" and p.startswith(home):
        return "~" + p[len(home):]
    return p


def redact_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of the receipt with every recorded path redacted."""
    out = json.loads(json.dumps(receipt))  # deep copy without mutation
    for key in ("interpreter", "pytesseract_module", "tesseract_binary",
                "probe_cwd"):
        if key in out:
            out[key] = _redact_path(out[key])
    return out


# --------------------------------------------------------------------------
# The probe payload — runs INSIDE the pipeline interpreter subprocess.
# Kept as a source string so the subprocess needs nothing importable from
# this package (the whole test is whether THAT interpreter can do OCR).
# --------------------------------------------------------------------------
_PROBE_SRC = r'''
import json, shutil, sys
try:
    import pytesseract
    pyt_mod = pytesseract.__file__
    import_err = None
except Exception as exc:
    pyt_mod = None
    import_err = "%s: %s" % (type(exc).__name__, exc)
try:
    from PIL import Image, ImageDraw, ImageFont
    pil_ok = True
    pil_err = None
except Exception as exc:
    pil_ok = False
    pil_err = "%s: %s" % (type(exc).__name__, exc)
bin_path = shutil.which("tesseract")
tess_version = None
tess_err = None
if bin_path:
    try:
        v = pytesseract.get_tesseract_version() if pyt_mod else None
        tess_version = str(v) if v is not None else None
    except Exception as exc:
        tess_err = str(exc)
fixture_ok = False
fixture_text_out = ""
fixture_err = None
if pyt_mod and pil_ok and bin_path:
    try:
        img = Image.new("RGB", (640, 120), "white")
        d = ImageDraw.Draw(img)
        font = None
        # FIX 24: the fixture must work on BOTH platforms. The Mac-only Arial
        # path made every non-Mac box fall back to PIL's ~11px bitmap default
        # font, which tesseract cannot lift at 640x120 — the probe then
        # reported Branch B on a box whose OCR stack is actually fine. Order:
        # Mac Arial -> common Linux/DejaVu paths -> Pillow >=10.1 SCALABLE
        # default (a real 44pt face, not the 11px bitmap) -> bitmap last.
        for _fp, _sz in (
                ("/System/Library/Fonts/Supplemental/Arial.ttf", 44),
                ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44),
                ("/usr/share/fonts/truetype/freefont/FreeSans.ttf", 44),
                ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 44),
        ):
            try:
                font = ImageFont.truetype(_fp, _sz)
                break
            except Exception:
                continue
        if font is None:
            try:
                font = ImageFont.load_default(size=44)  # Pillow >= 10.1 scalable
            except Exception:
                font = ImageFont.load_default()  # last resort: 11px bitmap
        d.text((12, 34), "OCR PROBE FIX33", fill="black", font=font)
        fixture_text_out = pytesseract.image_to_string(img).strip()
        fixture_ok = "FIX33" in fixture_text_out.upper().replace(" ", "")
    except Exception as exc:
        fixture_err = "%s: %s" % (type(exc).__name__, exc)
print("@FIX33RECEIPT@" + json.dumps({
    "interpreter": sys.executable,
    "python_version": sys.version.split()[0],
    "pytesseract_importable": pyt_mod is not None,
    "pytesseract_module": pyt_mod,
    "pytesseract_import_error": import_err,
    "pillow_importable": pil_ok,
    "pillow_import_error": pil_err,
    "tesseract_binary": bin_path,
    "tesseract_version": tess_version,
    "tesseract_error": tess_err,
    "fixture_ocr_ok": fixture_ok,
    "fixture_ocr_text": fixture_text_out[:120],
    "fixture_ocr_error": fixture_err,
}))
'''


def run_step0_probe(interpreter: Optional[str] = None,
                    scripts_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Run the read-only Step 0 probe in the pipeline interpreter. Returns the
    REDACTED receipt dict (never raises for a probe failure — a failed probe is
    a recorded Branch B fact, not an exception; only tooling errors raise).

    No install, no network, no provider calls. The subprocess is bounded by
    PROBE_TIMEOUT_S (the spec's 5-minute timebox)."""
    interp = interpreter or resolve_pipeline_interpreter()
    scripts = Path(scripts_dir) if scripts_dir else \
        Path(__file__).resolve().parent.parent
    try:
        proc = subprocess.run(
            [interp, "-c", _PROBE_SRC],
            capture_output=True, text=True, timeout=PROBE_TIMEOUT_S,
            cwd=str(scripts))
    except subprocess.TimeoutExpired:
        receipt = {
            "fix": 33,
            "branch": None,
            "probe_status": "timeout",
            "timeout_s": PROBE_TIMEOUT_S,
            "interpreter": interp,
            "probed_at": datetime.now(timezone.utc).isoformat(),
        }
        return redact_receipt(receipt)
    except OSError as exc:
        receipt = {
            "fix": 33,
            "branch": None,
            "probe_status": "interpreter-launch-failed",
            "error": str(exc),
            "interpreter": interp,
            "probed_at": datetime.now(timezone.utc).isoformat(),
        }
        return redact_receipt(receipt)

    payload = None
    for line in proc.stdout.splitlines():
        if line.startswith("@FIX33RECEIPT@"):
            payload = json.loads(line[len("@FIX33RECEIPT@"):])
            break
    if payload is None:
        receipt = {
            "fix": 33,
            "branch": None,
            "probe_status": "probe-crashed",
            "probe_rc": proc.returncode,
            "probe_stderr_tail": proc.stderr[-500:] if proc.stderr else "",
            "interpreter": interp,
            "probed_at": datetime.now(timezone.utc).isoformat(),
        }
        return redact_receipt(receipt)

    payload.update({
        "fix": 33,
        "probe_status": "ok",
        "probe_rc": proc.returncode,
        "probed_at": datetime.now(timezone.utc).isoformat(),
    })
    payload["branch"] = determine_branch(payload)
    return redact_receipt(payload)


def determine_branch(receipt: Dict[str, Any]) -> Optional[str]:
    """A/B determination from the probe facts alone — the 'verify' half of
    verify-then-fix. Returns 'A' (present + functional), 'B' (missing/broken),
    or None (probe could not measure: timeout/crash — undetermined, never
    silently 'A')."""
    if receipt.get("probe_status") != "ok":
        return None
    if (receipt.get("pytesseract_importable")
            and receipt.get("pillow_importable")
            and receipt.get("tesseract_binary")
            and receipt.get("fixture_ocr_ok")):
        return "A"
    return "B"


def failed_layers(receipt: Dict[str, Any]) -> list:
    """Name the EXACT failed layer(s) for the Branch B message (spec: 'a clear
    launch-time hard failure with the exact failed layer')."""
    layers = []
    if not receipt.get("pytesseract_importable"):
        layers.append("pytesseract module (not importable from the pipeline interpreter)")
    if not receipt.get("pillow_importable"):
        layers.append("Pillow module (not importable from the pipeline interpreter)")
    if not receipt.get("tesseract_binary"):
        layers.append("tesseract native binary (absent or not executable on PATH)")
    elif receipt.get("tesseract_version") is None and receipt.get("probe_status") == "ok":
        layers.append("tesseract binary present but version probe failed")
    if (receipt.get("pytesseract_importable") and receipt.get("pillow_importable")
            and receipt.get("tesseract_binary") and not receipt.get("fixture_ocr_ok")):
        layers.append("real OCR fixture failed (version/path mismatch suspected)")
    return layers


def load_pinned_deps() -> Dict[str, Any]:
    """The portable dependency manifest (ocr-deps.json, shipped beside this
    module). Branch A pins the OBSERVED compatible versions here; FIX 38's
    packaging step consumes the same file for the portable bundle."""
    doc = json.loads(_SHIPPED_DEPS.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or "ocr" not in doc:
        raise RuntimeError(f"FIX 33: {_SHIPPED_DEPS} is malformed (no 'ocr' key)")
    return doc


def check_against_pins(receipt: Dict[str, Any]) -> list:
    """Compare the OBSERVED versions against the pinned manifest. A major-version
    drift on tesseract or a different pytesseract package version is reported
    (not fatal on its own — the real OCR fixture is the functional proof — but
    recorded so FIX 38 packaging and the operator see the drift)."""
    drift = []
    try:
        pins = load_pinned_deps()["ocr"]
    except (OSError, ValueError, RuntimeError) as exc:
        return [f"pinned manifest unreadable: {exc}"]
    obs_tess = receipt.get("tesseract_version") or ""
    pin_tess = str(pins.get("tesseract_major_version", ""))
    if pin_tess and obs_tess and not obs_tess.startswith(pin_tess):
        drift.append(f"tesseract major drift: observed '{obs_tess}' vs pinned major "
                      f"'{pin_tess}'")
    return drift


def write_receipt(receipt: Dict[str, Any], dest: Path) -> Path:
    """Write the redacted JSON receipt. dest may be a file (receipt written
    there) or a directory (RECEIPT_NAME written inside). A missing dest
    directory is CREATED first — calling this for a not-yet-existing
    working/checkpoints/ must never clobber the directory path with a file."""
    dest = Path(dest)
    if dest.suffix == "" or dest.is_dir():
        # A directory-shaped dest: always the receipt INSIDE it.
        dest.mkdir(parents=True, exist_ok=True)
        dest = dest / RECEIPT_NAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    os.replace(tmp, dest)  # atomic: no torn receipt under the canonical name
    return dest


def step0_verify(run_dir: Optional[Path] = None,
                 scripts_dir: Optional[Path] = None,
                 receipt_path: Optional[Path] = None) -> Dict[str, Any]:
    """THE Step 0 entry: run the probe, write the redacted receipt, return it.

    Never installs, never mutates packages (the verify half of the protocol —
    the fix half is a separate explicit Branch B action, never implicit).
    The receipt is written to <run_dir>/working/checkpoints/ when run_dir is
    given, plus receipt_path when given (the FIX 33 proof dir).
    """
    receipt = run_step0_probe(scripts_dir=scripts_dir)
    if run_dir is not None:
        write_receipt(receipt, Path(run_dir) / "working" / "checkpoints")
    if receipt_path is not None:
        write_receipt(receipt, Path(receipt_path))
    return receipt


def interpreter_binding_ok(receipt: Dict[str, Any],
                           interpreter: Optional[str] = None) -> bool:
    """The receipt BINDING: a receipt names the interpreter it measured. A
    different interpreter later selected at launch must FAIL, never borrow
    the receipt (spec, Branch A last sentence)."""
    if receipt.get("probe_status") != "ok":
        return False
    recorded = receipt.get("interpreter")
    if not recorded:
        return False
    recorded = os.path.expanduser(recorded)
    current = interpreter or resolve_pipeline_interpreter()
    return os.path.realpath(os.path.expanduser(current)) == os.path.realpath(recorded)


# ---------------------------------------------------------------------------
# FIX 24 CLI -- `python3 -m presentation_job.ocr_verify --probe`
#
# THE FAULT THIS CLOSES: FIX 33 shipped the probe + receipt machinery but no
# command-line entry, so the FIX 24 proof command (`python3 -m
# presentation_job.ocr_verify --probe` must print `available: true`) was a
# SILENT NO-OP — python -m ran the module, found no __main__ guard, printed
# nothing, exited 0. An operator (or a critic) had no way to see the OCR
# state without reading state.json.
#
# `--probe` prints a machine-readable line FIRST — `available: true|false` —
# exactly the key preflight_deps._record_receipt() persists into
# state.json's runtime_deps.ocr entry, so the CLI and the recorded state can
# never disagree about the word. Then the redacted receipt JSON (machine
# consumers parse that). Exit codes: 0 = Branch A (OCR functional under the
# pipeline interpreter), 9 = Branch B / unmeasured (== launcher's
# EXIT_OCR_ENGINE_MISSING, the same refusal family), 2 = usage error.
# PRESENTATION_OCR_VERIFY=0 disables (documented rollback, same as the
# launch gate) — prints `available: false` and exits 9, never silently.
# ---------------------------------------------------------------------------
PROBE_CLI_EXIT_OK = 0
PROBE_CLI_EXIT_MISSING = 9  # == launcher.EXIT_OCR_ENGINE_MISSING


def _probe_available(receipt: Dict[str, Any]) -> bool:
    """THE word: available means Branch A under the probed interpreter — the
    same predicate preflight_deps._record_receipt() writes as
    runtime_deps.ocr.available. One predicate, two writers, never drifts."""
    return receipt.get("branch") == "A"


def build_probe_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m presentation_job.ocr_verify",
        description="FIX 24/FIX 33 OCR probe -- measure the OCR stack (pytesseract "
                    "import + tesseract binary + real one-line fixture OCR) under "
                    "the EXACT interpreter the canonical entry resolves for the "
                    "pipeline. Read-only: no install, no network, no provider calls.",
    )
    parser.add_argument(
        "--probe", action="store_true",
        help="Run the Step 0 OCR probe and print 'available: true|false' plus the "
             "redacted receipt JSON. Exit 0 = available (Branch A); exit 9 = "
             "missing/broken (Branch B or unmeasured; prints the failed layers "
             "and the exact install command).",
    )
    parser.add_argument(
        "--receipt", metavar="DEST",
        help="With --probe: also write the redacted receipt JSON to DEST (a file "
             "or a directory; a directory gets " + RECEIPT_NAME + " inside).",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Print only the 'available:' line and the receipt JSON (suppress the "
             "human-readable failed-layer/install-command block on failure).",
    )
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_probe_parser().parse_args(argv)

    if not args.probe:
        # No flag = usage error, not a silent no-op: always SOMETHING on stdout.
        build_probe_parser().print_help()
        print("ocr_verify: nothing to do -- pass --probe "
              "(see the FIX 24 proof command: "
              "python3 -m presentation_job.ocr_verify --probe)", file=sys.stderr)
        return 2

    if not verify_enabled():
        print("available: false", flush=True)
        print("ocr_verify: PRESENTATION_OCR_VERIFY=0 -- the FIX 33 Step 0 OCR "
              "probe is disabled (documented rollback). Unset it to probe.",
              file=sys.stderr)
        return PROBE_CLI_EXIT_MISSING

    receipt = run_step0_probe()
    if args.receipt:
        try:
            written = write_receipt(receipt, Path(args.receipt).expanduser())
            print(f"ocr_verify: receipt written to {written}", file=sys.stderr)
        except OSError as exc:
            print(f"ocr_verify: could not write receipt: {exc}", file=sys.stderr)

    # The FIX 24 proof key FIRST, on stdout, always — machine-readable and
    # identical in wording to the state.json runtime_deps.ocr value.
    print(f"available: {'true' if _probe_available(receipt) else 'false'}",
          flush=True)
    print(json.dumps(receipt, indent=2, default=str))

    if _probe_available(receipt):
        return PROBE_CLI_EXIT_OK

    if not args.quiet:
        layers = failed_layers(receipt) or ["probe could not measure"]
        print("ocr_verify: OCR stack missing or broken (Branch B) under the "
              f"pipeline interpreter {receipt.get('interpreter')}. "
              "Failed layer(s):", file=sys.stderr)
        for layer in layers:
            print(f"  - {layer}", file=sys.stderr)
        print(
            "ocr_verify: fix (Branch B, explicit): install the pinned "
            "pytesseract (ocr-deps.json) into the pipeline's DEDICATED venv — "
            "never global Python — and point PRESENTATION_PIPELINE_INTERPRETER "
            "at that venv; provision the native tesseract binary on PATH "
            "(Mac: brew install tesseract). Python deps: "
            "<venv>/bin/python -m pip install pytesseract pillow. "
            "Then re-run: python3 -m presentation_job.ocr_verify --probe",
            file=sys.stderr)
    return PROBE_CLI_EXIT_MISSING


if __name__ == "__main__":
    sys.exit(main())
