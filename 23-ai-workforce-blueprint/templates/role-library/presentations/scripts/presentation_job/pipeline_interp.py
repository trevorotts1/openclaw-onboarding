"""PRES-035 — single authority for the presentation pipeline interpreter.

THE DEFECT. The updater validates and persists a department venv
(PRESENTATION_PIPELINE_INTERPRETER), while the scheduled wrappers invoke
bare ``python3``. The watchdog launchd PATH searches /usr/bin first and
omits Intel Homebrew; a tick may execute under a different interpreter or
lack tools, with nothing in the log to explain why. A cron run then
behaves differently from an interactive run — the same class as the F03
PATH defect, one layer up: not which PATH, but which interpreter the
validated engine was proven under.

THE FIX, in one place so every entry point resolves identically:

  resolve_pipeline_interpreter()
    One absolute executable. Precedence, first usable wins:

    1. PRESENTATION_PIPELINE_INTERPRETER when non-blank, absolute and
       executable — the per-client override an operator pinned. A set but
       unusable value is NEVER silently skipped: it is reported as the
       reason and resolution continues, so a stale pin is visible.
    2. The selected client's department venv:
       <client-root>/.venv-presentations/bin/python (FIX 71 shape).
    3. PATH ``python3`` (shutil.which) — the pre-fix behavior, last
       resort, reported as such.

    Inside a container the candidate is translated to the MOUNTED path,
    never the host path: a <host>/.openclaw/.venv-presentations/... pin
    recorded on a Mac becomes <container-root>/.venv-presentations/...
    (container root from oc_paths, honoring an explicit OPENCLAW_ROOT
    pin, so a custom client root survives the translation).

  validate_interpreter(path)
    Absolute, executable, and actually runs
    (``<path> -c 'import sys...'``) — a NAME resolving is never proof
    the program runs. Returns (ok, detail).

  check_readiness(scheduler, recorded, runs_root)
    The scheduler readiness receipt. Records the ACTUAL sys.executable
    and version of the interpreter running the check plus the required
    import proof (reportlab, pptx, pypdf, pytesseract — the FIX 71 core),
    and compares against the RENDERED (recorded) interpreter and the
    previous receipt's fingerprint (realpath + mtime_ns + version).
    READY only when all three agree. Any mismatch is DEGRADED with the
    exact reason and a BOUNDED remediation record (attempts/max_attempts;
    record-only, never an auto-reinstall loop from a scheduler tick).
    A changed venv after a green receipt therefore INVALIDATES the
    receipt instead of reusing stale proof.

ROLLBACK: PRESENTATION_PIPELINE_PIN=0 restores the pre-fix behavior
(PATH python3, no venv-first ordering, no readiness receipt).

REDACTION: receipts carry paths and versions only — never env values.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

#: Documented rollback. "0" -> pre-fix behavior (no pin, no receipt).
FLAG_ENV = "PRESENTATION_PIPELINE_PIN"

#: The override every consumer honors.
INTERPRETER_ENV = "PRESENTATION_PIPELINE_INTERPRETER"

#: Platform pin consumed for container detection (same name oc_paths uses).
PLATFORM_ENV = "OPENCLAW_PLATFORM"

#: Bounded remediation budget for a degraded scheduler receipt.
DEFAULT_MAX_ATTEMPTS = 3

#: Receipt filename stem, written under the scheduler's runs root.
RECEIPT_STEM = "scheduler-readiness"

#: The import proof a READY receipt requires (the FIX 71 core).
REQUIRED_IMPORTS: Tuple[str, ...] = ("reportlab", "pptx", "pypdf", "pytesseract")

#: Probe timeout for validating a candidate interpreter.
VALIDATE_TIMEOUT_S = 30


def enabled(environ: Optional[Dict[str, str]] = None) -> bool:
    """PRESENTATION_PIPELINE_PIN default ON; exactly "0" is the rollback."""
    view = os.environ if environ is None else environ
    raw = view.get(FLAG_ENV)
    if raw is None:
        return True
    return str(raw).strip().strip("'\"") != "0"


def _view(environ: Optional[Dict[str, str]]) -> Dict[str, str]:
    return dict(os.environ if environ is None else environ)


def in_container(view: Optional[Dict[str, str]] = None) -> bool:
    """True when path translation must use mounted (container) paths."""
    if Path("/.dockerenv").is_file() or Path("/run/.containerenv").is_file():
        return True
    v = _view(view)
    return str(v.get(PLATFORM_ENV, "") or "").strip() == "vps"


def container_root(view: Optional[Dict[str, str]] = None) -> Path:
    """The client root as seen from INSIDE the container.

    Honors an explicit OPENCLAW_ROOT/OC_ROOT/OC_CONFIG pin (a custom
    client root survives); otherwise the /data mount. Never a host path.
    """
    v = _view(view)
    for name in ("OPENCLAW_ROOT", "OC_ROOT", "OC_CONFIG"):
        raw = str(v.get(name, "") or "").strip()
        if raw:
            p = Path(raw)
            if p.is_absolute() and p != Path("/"):
                return p
    return Path("/data/.openclaw")


def translate_for_container(candidate: str,
                            view: Optional[Dict[str, str]] = None) -> str:
    """Map a host-recorded venv path onto the mounted container path.

    Only the .venv-presentations suffix is carried across: anything before
    it is host addressing and is dropped. A path already under the
    container root, or any path outside a container, passes through
    unchanged. A non-venv path passes through unchanged (nothing to map).
    """
    if not candidate or not in_container(view):
        return candidate
    marker = "/.venv-presentations/"
    if candidate.endswith("/.venv-presentations"):
        suffix = ""
    elif marker in candidate:
        suffix = candidate.split(marker, 1)[1]
    else:
        return candidate
    root = container_root(view)
    return str(root / ".venv-presentations" / suffix) if suffix else str(
        root / ".venv-presentations")


def client_root(view: Optional[Dict[str, str]] = None) -> Optional[Path]:
    """The selected client's root via oc_paths, or None when the
    selection is unusable (conflict/unreadable config). None is a fact
    about resolution, never a fallback to another client's root."""
    try:
        try:
            from . import oc_paths as _oc
        except ImportError:
            import oc_paths as _oc  # type: ignore[no-redef]
        return _oc.root(_view(view))
    except Exception:
        return None


def default_venv_python(view: Optional[Dict[str, str]] = None) -> Optional[str]:
    """<client-root>/.venv-presentations/bin/python (FIX 71 shape)."""
    root = client_root(view)
    if root is None:
        return None
    cand = root / ".venv-presentations" / "bin" / "python"
    return translate_for_container(str(cand), view)


def validate_interpreter(path: str,
                         timeout_s: int = VALIDATE_TIMEOUT_S
                         ) -> Tuple[bool, str]:
    """Absolute + executable + actually runs. Never trusts a bare name."""
    if not path or not str(path).strip():
        return False, "empty candidate"
    p = Path(str(path).strip())
    if not p.is_absolute():
        return False, f"not absolute: {p}"
    if not (p.is_file() and os.access(p, os.X_OK)):
        return False, f"not an executable file: {p}"
    try:
        proc = subprocess.run(
            [str(p), "-c", "import sys; print(sys.version.split()[0])"],
            capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return False, f"version probe timed out after {timeout_s}s: {p}"
    except OSError as exc:
        return False, f"could not execute {p}: {exc}"
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        return False, (f"version probe exited {proc.returncode}: {p}"
                       + (f" ({tail[-1]})" if tail else ""))
    version = (proc.stdout or "").strip().splitlines()
    return True, f"runs Python {version[0] if version else '?'}: {p}"


def resolve_pipeline_interpreter(
        environ: Optional[Dict[str, str]] = None
) -> Tuple[Optional[str], List[str], str]:
    """Resolve ONE absolute pipeline interpreter.

    Returns (path_or_None, notes, source) where source names the winning
    layer ("override" | "client-venv" | "path-python3" | "unresolved")
    and notes record every layer consulted — including a set-but-unusable
    override, which is reported, never silently skipped.
    """
    view = _view(environ)
    notes: List[str] = []

    if not enabled(view):
        # Documented rollback: PRESENTATION_PIPELINE_PIN=0 restores the
        # pre-fix behavior — PATH python3, no pin, no venv preference.
        which = shutil.which("python3")
        if which is None:
            notes.append("rollback=0 and no python3 on PATH")
            return None, notes, "unresolved"
        abs_which = str(Path(which).resolve())
        notes.append(f"PRESENTATION_PIPELINE_PIN=0 rollback: PATH python3 "
                     f"({abs_which}) — pre-fix behavior")
        return abs_which, notes, "path-python3"

    override = str(view.get(INTERPRETER_ENV, "") or "").strip()
    if override:
        translated = translate_for_container(override, view)
        if translated != override:
            notes.append(f"override translated for container: "
                         f"{override} -> {translated}")
        ok, detail = validate_interpreter(translated)
        if ok:
            notes.append(f"override usable ({detail})")
            return translated, notes, "override"
        notes.append(f"override unusable ({detail}); continuing to "
                     f"client venv, never substituting silently")

    venv = default_venv_python(view)
    if venv:
        ok, detail = validate_interpreter(venv)
        if ok:
            notes.append(f"client venv usable ({detail})")
            return venv, notes, "client-venv"
        notes.append(f"client venv unusable ({detail})")
    else:
        notes.append("client root unresolved; no venv candidate")

    which = shutil.which("python3")
    if which:
        abs_which = str(Path(which).resolve())
        ok, detail = validate_interpreter(abs_which)
        if ok:
            notes.append(f"last-resort PATH python3 ({detail}) — "
                         f"pre-fix behavior, not a validated venv")
            return abs_which, notes, "path-python3"
        notes.append(f"PATH python3 unusable ({detail})")
    else:
        notes.append("no python3 on PATH")

    return None, notes, "unresolved"


def fingerprint(interpreter: str) -> Dict[str, str]:
    """Identity a later check must match: realpath + binary mtime + version.

    A venv recreated in place keeps its path but changes its binary, so
    the path alone cannot be the binding — a green receipt must not
    survive the thing it measured being replaced.
    """
    out: Dict[str, str] = {"path": interpreter, "realpath": "",
                           "mtime_ns": "", "python_version": ""}
    try:
        real = os.path.realpath(interpreter)
        out["realpath"] = real
        try:
            out["mtime_ns"] = str(Path(real).stat().st_mtime_ns)
        except OSError:
            out["mtime_ns"] = ""
    except OSError:
        pass
    try:
        proc = subprocess.run(
            [interpreter, "-c", "import sys; print(sys.version.split()[0])"],
            capture_output=True, text=True, timeout=VALIDATE_TIMEOUT_S)
        if proc.returncode == 0:
            first = (proc.stdout or "").strip().splitlines()
            out["python_version"] = first[0] if first else ""
    except (OSError, subprocess.TimeoutExpired):
        pass
    return out


def import_proof(interpreter: str,
                 modules: Tuple[str, ...] = REQUIRED_IMPORTS,
                 timeout_s: int = VALIDATE_TIMEOUT_S) -> Dict[str, bool]:
    """Per-module import proof under the ACTUAL interpreter (subprocess,
    so the check measures the pipeline interpreter, not whoever imports
    this module). A failed probe marks every module False — a probe that
    cannot measure is UNDETERMINED, never a pass."""
    probe = ("import json,sys; out={}; "
             "exec('for m in sys.argv[1:]:\\n"
             " try:\\n  __import__(m)\\n  out[m]=True\\n"
             " except Exception:\\n  out[m]=False'); "
             "print(json.dumps(out))")
    try:
        proc = subprocess.run(
            [interpreter, "-c", probe, *modules],
            capture_output=True, text=True, timeout=timeout_s,
            cwd=str(Path(__file__).resolve().parent.parent))
    except (OSError, subprocess.TimeoutExpired):
        return {m: False for m in modules}
    if proc.returncode != 0:
        return {m: False for m in modules}
    try:
        data = json.loads((proc.stdout or "").strip().splitlines()[-1])
        return {m: bool(data.get(m, False)) for m in modules}
    except (ValueError, IndexError):
        return {m: False for m in modules}


def receipt_path(runs_root: Path, scheduler: str) -> Path:
    return Path(runs_root) / f"{RECEIPT_STEM}-{scheduler}.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_readiness(scheduler: str,
                    recorded: str,
                    runs_root: str,
                    max_attempts: int = DEFAULT_MAX_ATTEMPTS
                    ) -> Tuple[str, Dict]:
    """Validate this tick's interpreter, write the receipt, return
    (status, receipt). Status is READY or DEGRADED. Never raises for a
    measurement outcome — a failed measurement is a DEGRADED fact, not
    an exception; only tooling errors (unwritable runs root naming)
    raise. Writing the receipt is best-effort: a scheduler tick must
    never die on bookkeeping."""
    if not scheduler or not __import__("re").match(r"^[a-z0-9-]+$", scheduler):
        raise ValueError(f"invalid scheduler name: {scheduler!r}")
    root = Path(runs_root)
    actual = sys.executable or ""
    version = sys.version.split()[0] if sys.version else ""
    fp = fingerprint(actual) if actual else {
        "path": "", "realpath": "", "mtime_ns": "", "python_version": ""}
    proof = import_proof(actual) if actual else {
        m: False for m in REQUIRED_IMPORTS}

    reasons: List[str] = []
    rec = (recorded or "").strip()
    if not rec:
        reasons.append("no recorded interpreter rendered into this schedule "
                       "(pre-PRES-035 install); re-run update-skills.sh to "
                       "render PRESENTATION_PIPELINE_INTERPRETER")
    elif actual and os.path.realpath(rec) != os.path.realpath(actual) \
            if os.path.exists(rec) and os.path.exists(actual) else rec != actual:
        reasons.append(f"recorded interpreter {rec} is not the interpreter "
                       f"running this tick ({actual}); a different host "
                       f"interpreter must never silently substitute")
    missing = [m for m, ok in proof.items() if not ok]
    if missing:
        reasons.append(f"required import check failed under {actual}: "
                       f"{', '.join(missing)} (repair: {actual} -m pip "
                       f"install reportlab python-pptx pypdf pytesseract "
                       f"Pillow; on VPS: bash "
                       f"/data/.openclaw/scripts/reassert-presentation-deps.sh)")

    prev: Dict = {}
    dest = receipt_path(root, scheduler)
    try:
        if dest.is_file():
            prev = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    prev_fp = prev.get("fingerprint") or {}
    if prev_fp and fp.get("realpath") and prev_fp.get("realpath"):
        if (fp["realpath"] != prev_fp.get("realpath")
                or fp["mtime_ns"] != prev_fp.get("mtime_ns")
                or fp["python_version"] != prev_fp.get("python_version")):
            reasons.append("pipeline interpreter changed since the last "
                           "green receipt (realpath/mtime/version differ); "
                           "stale proof invalidated, not reused")

    attempts = 0
    if reasons:
        try:
            attempts = int((prev.get("remediation") or {}).get("attempts", 0))
        except (ValueError, TypeError):
            attempts = 0
        attempts = min(attempts + 1, max_attempts)
        if attempts >= max_attempts:
            action = ("remediation budget exhausted "
                      f"({attempts}/{max_attempts}): operator action required "
                      "— re-run update-skills.sh schedule re-assert and "
                      "verify the department venv")
        else:
            action = (f"bounded remediation scheduled "
                      f"(attempt {attempts}/{max_attempts}): next tick "
                      "re-checks; repair the venv or re-render the schedule")
        remediation: Optional[Dict] = {"action": action,
                                       "attempts": attempts,
                                       "max_attempts": max_attempts}
        status = "DEGRADED"
    else:
        remediation = None
        status = "READY"

    receipt = {
        "schema": 1,
        "scheduler": scheduler,
        "status": status,
        "recorded_interpreter": rec,
        "actual_executable": actual,
        "actual_realpath": fp.get("realpath", ""),
        "python_version": version,
        "fingerprint": fp,
        "imports": proof,
        "reasons": reasons,
        "remediation": remediation,
        "checked_at": _utcnow(),
    }
    try:
        root.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        os.replace(tmp, dest)
    except OSError:
        pass  # best-effort; the returned status is the primary signal
    return status, receipt


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="presentation_job.pipeline_interp",
        description="Resolve/validate the pipeline interpreter and "
                    "maintain scheduler readiness receipts (PRES-035).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--resolve", action="store_true",
                       help="print the resolved absolute interpreter")
    group.add_argument("--validate", metavar="PATH",
                       help="validate one interpreter path")
    group.add_argument("--check-readiness", action="store_true",
                       help="run the scheduler readiness check and write "
                            "the receipt (exit 0 READY, 3 DEGRADED)")
    parser.add_argument("--scheduler", default="",
                        help="scheduler name for --check-readiness "
                             "(e.g. intake-poll, watchdog)")
    parser.add_argument("--recorded", default="",
                        help="rendered PRESENTATION_PIPELINE_INTERPRETER "
                             "value for --check-readiness")
    parser.add_argument("--runs-root", default="",
                        help="runs root the receipt is written under")
    parser.add_argument("--max-attempts", type=int,
                        default=DEFAULT_MAX_ATTEMPTS)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.resolve:
        path, notes, source = resolve_pipeline_interpreter()
        for note in notes:
            print(f"[pipeline-interp] {note}", file=sys.stderr)
        if path is None:
            print("[pipeline-interp] UNRESOLVED", file=sys.stderr)
            return 2
        print(path)
        return 0

    if args.validate:
        ok, detail = validate_interpreter(args.validate)
        print(f"[pipeline-interp] {'OK' if ok else 'INVALID'}: {detail}",
              file=sys.stderr)
        return 0 if ok else 2

    # --check-readiness
    if not args.scheduler or not args.runs_root:
        print("[pipeline-interp] --check-readiness requires --scheduler "
              "and --runs-root", file=sys.stderr)
        return 2
    try:
        status, receipt = check_readiness(
            args.scheduler, args.recorded, args.runs_root,
            max_attempts=args.max_attempts)
    except ValueError as exc:
        print(f"[pipeline-interp] {exc}", file=sys.stderr)
        return 2
    where = receipt_path(Path(args.runs_root), args.scheduler)
    if status == "READY":
        print(f"[pipeline-interp] READY under {receipt['actual_executable']} "
              f"(Python {receipt['python_version']}; imports "
              f"{'/'.join(REQUIRED_IMPORTS)} OK; receipt {where})")
        return 0
    print(f"[pipeline-interp] DEGRADED ({len(receipt['reasons'])} reason(s)); "
          f"receipt {where}", file=sys.stderr)
    for reason in receipt["reasons"]:
        print(f"[pipeline-interp]   - {reason}", file=sys.stderr)
    if receipt.get("remediation"):
        print(f"[pipeline-interp]   remediation: "
              f"{receipt['remediation']['action']}", file=sys.stderr)
    return 3


if __name__ == "__main__":  # pragma: no cover -- CLI entry
    raise SystemExit(main())
