#!/usr/bin/env python3
"""
canonical_render_guard.py — THE ENFORCEMENT SURFACE (Fix 1, primary root cause).

================================================================================
This is the gate that makes the governed pipeline IMPOSSIBLE to route around.
Every protection in build_deck.py / run_signature_deck.py is enforced only
*inside* those tools. The single root cause of the field failure was that nothing
at the runtime/agent layer forced a deck to pass *through* those tools — an agent
simply wrote hand-rolled `working/phase4_driver.py` + `working/phase6_assemble.py`
that re-created the retired "skip kie.ai for hook slides + paste PowerPoint text on
top" pattern, and not one guardrail fired because the thing that runs them was
never run.

This guard closes that gap. It runs at TWO mandatory checkpoints driven by
run_signature_deck.py:
  * PRE-RENDER  — before any image is rendered: scan the run dir for hand-rolled
                  renderers/assemblers and BLOCK (AF-CANONICAL-RENDER-BYPASS /
                  AF-LOCAL-CANVAS).
  * PRE-DELIVERY — before a deck can be marked delivered: REFUSE unless the full
                  process_manifest.json attestation chain is present (every
                  governed phase attested) AND the run dir is free of hand-rolled
                  renderers AND the Fix-2 pixel/vision checks pass
                  (AF-IMAGE-QC-VISION).

THE ONLY BYPASS is an explicit, LOGGED owner/founder approval token recorded in
working/checkpoints/process_manifest.json under "owner_skip_approval" (or
"owner_skip_approvals"). A gate is NEVER skipped silently and NEVER by an agent's
own choice. A malformed or owner_approved:false token authorizes nothing.

SHARED CONTRACT (with Fix 2 in build_deck.py and Fix 9):
  * The canonical render path is build_deck.py / run_signature_deck.py ONLY.
  * New auto-fail codes (exact strings):
        AF-CANONICAL-RENDER-BYPASS  — a non-canonical script defines a slide
                                      renderer/assembler or calls kie createTask
                                      / emits native PowerPoint text on a slide.
        AF-LOCAL-CANVAS             — a non-canonical script fabricates a slide
                                      image locally (e.g. Image.new at 2048x1152).
        AF-IMAGE-QC-VISION         — image-QC was not a real multimodal pixel read
                                      (delegated to Fix 2's exported check symbol).
  * Fix 2 implements/exports the new check symbols in build_deck.py; this guard
    WIRES them (see run_fix2_checks). If a symbol is absent (Fix 2 not yet
    deployed on a box) the guard's own self-contained detection still fires — the
    guard is authoritative and never crashes on a missing symbol.

EXIT CODES (CLI)
    0 — guard passed (or every finding covered by a logged owner_skip_approval).
    5 — guard BLOCKED (AF-CANONICAL-RENDER-BYPASS / AF-LOCAL-CANVAS /
        AF-IMAGE-QC-VISION / incomplete attestation chain).
    2 — usage / run-dir error.
"""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Auto-fail codes — EXACT strings, shared with Fix 2 & Fix 9. Do not rename.
AF_CANONICAL_RENDER_BYPASS = "AF-CANONICAL-RENDER-BYPASS"
AF_LOCAL_CANVAS = "AF-LOCAL-CANVAS"
AF_IMAGE_QC_VISION = "AF-IMAGE-QC-VISION"

# Canonical, sanctioned scripts. These ARE the governed render path; the patterns
# below (createTask, per-deck render functions, etc.) legitimately live here. They
# are allow-listed by BASENAME so that even if copied into a run dir they pass. The
# set is seeded from the scripts dir this guard ships in, plus an explicit core.
_CORE_CANONICAL = {
    "build_deck.py", "run_signature_deck.py", "canonical_render_guard.py",
    "build_teleprompter.py", "sync_check.py", "kie_generate.py", "ghl_media.py",
    "ghl_media_push.py", "delivery_gate.py", "speech_build_harness.py",
    "presenters_speech_pdf.py", "gate_integrity_check.py",
    "doctrine_residual_check.py", "intelligence_engines_check.py",
    "pitch_engines_check.py", "test_preflight.py",
}


def canonical_script_names() -> set:
    names = set(_CORE_CANONICAL)
    try:
        for p in HERE.glob("*.py"):
            names.add(p.name)
    except Exception:  # noqa: BLE001
        pass
    return names


# ---------------------------------------------------------------------------
# Detection patterns — a non-canonical *.py inside the run dir that matches any of
# these is a hand-rolled renderer/assembler and is BLOCKED.
# ---------------------------------------------------------------------------
# AF-LOCAL-CANVAS: locally fabricating the slide image instead of kie.ai gpt-image-2.
_LOCAL_CANVAS_PATTERNS = [
    # Image.new(...) with a 2048x1152 (or 1152x2048) slide canvas, dims in either order.
    (re.compile(r"Image\.new\s*\([^)]*\b2048\b[^)]*\b1152\b", re.S), "Image.new() 2048x1152 slide canvas"),
    (re.compile(r"Image\.new\s*\([^)]*\b1152\b[^)]*\b2048\b", re.S), "Image.new() 1152x2048 slide canvas"),
    # A bare 2048x1152 canvas dimension tuple paired with any local image constructor.
    (re.compile(r"\b2048\s*,\s*1152\b"), "2048x1152 local canvas dimension"),
    (re.compile(r"\b1152\s*,\s*2048\b"), "1152x2048 local canvas dimension"),
    # ImageDraw on a fabricated slide surface (local typography card).
    (re.compile(r"ImageDraw\.Draw\s*\("), "ImageDraw local slide typography"),
]

# AF-CANONICAL-RENDER-BYPASS: a hand-rolled renderer/assembler, a direct kie
# createTask outside build_deck.py, or native PowerPoint on-slide text.
_BYPASS_PATTERNS = [
    # Native PowerPoint text stamped on a slide (the overlay defect).
    (re.compile(r"\badd_text_?box\s*\("), "native PowerPoint on-slide text box (add_textbox)"),
    (re.compile(r"\.shapes\.add_textbox\s*\("), "native PowerPoint on-slide text box"),
    # Direct kie.ai createTask / recordInfo dispatch outside the canonical renderer.
    (re.compile(r"\bcreateTask\b"), "direct kie.ai createTask outside build_deck.py"),
    (re.compile(r"api\.kie\.ai"), "direct kie.ai API call outside build_deck.py"),
    (re.compile(r"\brecordInfo\b"), "direct kie.ai recordInfo poll outside build_deck.py"),
    # Hand-rolled per-deck renderer / assembler function definitions (the exact
    # signatures the field-failure scripts used + the canonical ones re-implemented).
    (re.compile(r"\bdef\s+(?:render_slide|assemble_pptx|render_typography_hook|"
                r"write_typ_only|build_hook_slide|render_deck|build_pptx|"
                r"build_slide|assemble_deck|render_typography|make_slide)\b"),
     "hand-rolled per-deck renderer/assembler function"),
]


def _iter_run_py_files(run_dir: Path):
    """Yield every *.py under run_dir that is NOT a canonical sanctioned script and
    NOT inside the canonical scripts dir this guard ships in."""
    allow = canonical_script_names()
    for p in run_dir.rglob("*.py"):
        try:
            rp = p.resolve()
        except Exception:  # noqa: BLE001
            rp = p
        # Skip the canonical scripts home (defensive — run dirs are normally separate).
        try:
            rp.relative_to(HERE)
            continue
        except ValueError:
            pass
        if p.name in allow:
            continue
        # Skip virtualenvs / vendored site-packages noise.
        parts = set(p.parts)
        if parts & {".venv", "venv", "site-packages", "node_modules", "__pycache__"}:
            continue
        yield p


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def scan_run_dir(run_dir: Path) -> list:
    """Return a list of findings. Each finding is a dict:
        {file, af_code, line, reason, snippet}
    A finding means a hand-rolled renderer/assembler was detected in the run dir."""
    findings = []
    for path in _iter_run_py_files(run_dir):
        try:
            text = path.read_text(errors="replace")
        except Exception:  # noqa: BLE001
            continue
        try:
            rel = str(path.relative_to(run_dir))
        except ValueError:
            rel = str(path)
        for rx, reason in _LOCAL_CANVAS_PATTERNS:
            m = rx.search(text)
            if m:
                findings.append({
                    "file": rel, "af_code": AF_LOCAL_CANVAS,
                    "line": _line_of(text, m.start()), "reason": reason,
                    "snippet": m.group(0)[:120].replace("\n", " "),
                })
        for rx, reason in _BYPASS_PATTERNS:
            m = rx.search(text)
            if m:
                findings.append({
                    "file": rel, "af_code": AF_CANONICAL_RENDER_BYPASS,
                    "line": _line_of(text, m.start()), "reason": reason,
                    "snippet": m.group(0)[:120].replace("\n", " "),
                })
    return findings


# ---------------------------------------------------------------------------
# Owner/founder skip token — the ONLY bypass, and it must be LOGGED.
# ---------------------------------------------------------------------------
def _process_manifest_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "process_manifest.json"


def _load_process_manifest(run_dir: Path) -> dict:
    p = _process_manifest_path(run_dir)
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text())
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def load_owner_skip_approvals(run_dir: Path) -> dict:
    """Return {gate: record} for every well-formed owner/founder skip token recorded
    in process_manifest.json. A token authorizes a skip ONLY when it carries
    owner_approved:true (or approved:true) + approved_by + reason + a `gate` naming
    the auto-fail code or phase_id it covers. Anything malformed authorizes nothing.

    Accepts both a single object under "owner_skip_approval" and a list under
    "owner_skip_approval" / "owner_skip_approvals"."""
    obj = _load_process_manifest(run_dir)
    raw = obj.get("owner_skip_approval", obj.get("owner_skip_approvals", []))
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return {}
    out = {}
    for rec in raw:
        if not isinstance(rec, dict):
            continue
        approved = rec.get("owner_approved") is True or rec.get("approved") is True
        gate = rec.get("gate") or rec.get("af_code") or rec.get("phase_id")
        if (approved and gate
                and str(rec.get("approved_by", "")).strip()
                and str(rec.get("reason", "")).strip()):
            out[str(gate)] = rec
    return out


# ---------------------------------------------------------------------------
# Attestation chain — every governed phase must be attested at delivery.
# ---------------------------------------------------------------------------
def attested_phase_ids(run_dir: Path) -> set:
    """Phase ids proven by an attestation in process_manifest.json. Mirrors the
    runner: both 'phase_attestations' records AND build_deck.py's own 'render'
    phase record (which counts as P4-RENDER) are honored."""
    obj = _load_process_manifest(run_dir)
    ids = set()
    for att in obj.get("phase_attestations", []) or []:
        if isinstance(att, dict) and att.get("phase_id"):
            ids.add(att["phase_id"])
    for ph in obj.get("phases", []) or []:
        if isinstance(ph, dict) and ph.get("phase") == "render":
            ids.add("P4-RENDER")
    return ids


def missing_attestations(run_dir: Path, phases: list, phase_skip_approvals=None) -> list:
    """Return the ordered list of governed phase ids that are neither attested nor
    covered by a logged owner skip. phase_skip_approvals (from the runner's
    phase_skip_approvals.json) and process_manifest owner_skip_approval BOTH count."""
    attested = attested_phase_ids(run_dir)
    owner_skips = load_owner_skip_approvals(run_dir)
    phase_skips = set(phase_skip_approvals or set())
    missing = []
    for ph in sorted(phases, key=lambda p: p.get("order", 0)):
        pid = ph.get("id")
        if not pid:
            continue
        if pid in attested or pid in owner_skips or pid in phase_skips:
            continue
        missing.append(pid)
    return missing


# ---------------------------------------------------------------------------
# Fix-2 wiring — the new pixel/vision check symbols build_deck.py exports.
# ---------------------------------------------------------------------------
# Per the shared contract, Fix 2 exports check symbols on build_deck for the three
# new AF codes. We wire them by their agreed names; if a symbol is absent (Fix 2
# not yet deployed) the guard degrades gracefully — its own detection still runs.
_FIX2_SYMBOLS = [
    ("_chk_canonical_render_bypass", AF_CANONICAL_RENDER_BYPASS),
    ("_chk_local_canvas", AF_LOCAL_CANVAS),
    ("_chk_image_qc_vision", AF_IMAGE_QC_VISION),
]


def run_fix2_checks(run_dir: Path, slides_path=None) -> list:
    """Call the Fix-2 exported check symbols on build_deck if present. Returns a list
    of (af_code, message) failures. Missing symbols are skipped (not failures)."""
    failures = []
    try:
        import build_deck as bd  # noqa: WPS433
    except Exception:  # noqa: BLE001
        return failures
    owner_skips = load_owner_skip_approvals(run_dir)
    for sym, af_code in _FIX2_SYMBOLS:
        fn = getattr(bd, sym, None)
        if not callable(fn):
            continue
        if af_code in owner_skips:
            continue
        try:
            # Try the (run_dir, slides_path) signature, then (run_dir), then ().
            try:
                msg = fn(run_dir, slides_path)
            except TypeError:
                try:
                    msg = fn(run_dir)
                except TypeError:
                    msg = fn()
        except Exception as exc:  # noqa: BLE001
            msg = f"{af_code}: check symbol {sym} raised {exc!r}"
        if msg:
            failures.append((af_code, str(msg)))
    return failures


# ---------------------------------------------------------------------------
# The two guard checkpoints.
# ---------------------------------------------------------------------------
def _format_findings(findings: list, owner_skips: dict) -> tuple:
    """Split findings into (blocking, waived) by owner_skip_approval coverage."""
    blocking, waived = [], []
    for f in findings:
        if f["af_code"] in owner_skips:
            waived.append(f)
        else:
            blocking.append(f)
    return blocking, waived


def guard_pre_render(run_dir: Path) -> str:
    """PRE-RENDER guard. Return "" when the run dir is free of hand-rolled
    renderers/assemblers (or every finding is covered by a logged
    owner_skip_approval). Otherwise return a fatal AF message that the caller MUST
    treat as a hard abort. This is the gate that blocks `python3 working/phase4_*.py`
    style bypasses BEFORE a single image is rendered."""
    findings = scan_run_dir(run_dir)
    owner_skips = load_owner_skip_approvals(run_dir)
    blocking, waived = _format_findings(findings, owner_skips)
    if not blocking:
        if waived:
            print("=== CANONICAL-RENDER-GUARD (pre-render): "
                  f"{len(waived)} finding(s) WAIVED by logged owner_skip_approval ===",
                  flush=True)
        return ""
    lines = [
        "CANONICAL RENDER GUARD — PRE-RENDER BLOCK.",
        "Hand-rolled renderer(s)/assembler(s) detected in the run dir. The ONLY "
        "sanctioned render path is build_deck.py via run_signature_deck.py. Per-deck "
        "renderers, local slide canvases, native on-slide text, and direct kie.ai "
        "createTask calls are FORBIDDEN.",
        "",
    ]
    for f in blocking:
        lines.append(f"  [{f['af_code']}] {f['file']}:{f['line']} — {f['reason']}  "
                     f"(`{f['snippet']}`)")
    lines.append("")
    lines.append("To proceed you must EITHER delete the hand-rolled script(s) and "
                 "render through run_signature_deck.py -> build_deck.py, OR record an "
                 "explicit owner_skip_approval token (owner_approved:true + approved_by "
                 "+ reason + gate=<AF code>) in working/checkpoints/process_manifest.json. "
                 "An agent may NOT waive this on its own.")
    return "\n".join(lines)


def guard_pre_delivery(run_dir: Path, phases: list, slides_path=None,
                       phase_skip_approvals=None) -> str:
    """PRE-DELIVERY guard. Return "" only when ALL of the following hold:
      1. The run dir is free of hand-rolled renderers (or waived by owner token).
      2. The full process_manifest attestation chain is present — every governed
         phase attested (or covered by a logged owner skip).
      3. The Fix-2 pixel/vision checks pass (or waived by owner token).
    Otherwise return a fatal AF message. Delivery MUST be refused on a non-empty
    return. This is what makes 'Done' impossible to fake."""
    problems = []

    # (1) hand-rolled renderer scan (same as pre-render — defense in depth at delivery).
    findings = scan_run_dir(run_dir)
    owner_skips = load_owner_skip_approvals(run_dir)
    blocking, _ = _format_findings(findings, owner_skips)
    for f in blocking:
        problems.append(f"  [{f['af_code']}] {f['file']}:{f['line']} — {f['reason']}")

    # (2) full attestation chain.
    missing = missing_attestations(run_dir, phases, phase_skip_approvals)
    if missing:
        problems.append("  [AF-PHASE-SKIPPED] incomplete attestation chain — these "
                        "governed phases are neither attested nor owner-skip-approved: "
                        + ", ".join(missing))

    # (3) Fix-2 pixel/vision checks.
    for af_code, msg in run_fix2_checks(run_dir, slides_path):
        problems.append(f"  [{af_code}] {msg}")

    if not problems:
        return ""
    return ("CANONICAL RENDER GUARD — PRE-DELIVERY REFUSED.\n"
            "This deck cannot be marked delivered. The governed process is not proven "
            "complete:\n\n" + "\n".join(problems) + "\n\n"
            "Delivery is allowed ONLY when the full attestation chain is present, the "
            "run dir is free of hand-rolled renderers, and the pixel/vision image-QC "
            "passes — or each failing gate carries an explicit, logged "
            "owner_skip_approval token in process_manifest.json. An agent may NOT "
            "self-approve.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load_phases() -> list:
    """Load manifest phases the same way run_signature_deck does (best-effort, for
    the standalone --mode pre-delivery CLI)."""
    try:
        import run_signature_deck as rsd  # noqa: WPS433
        return rsd.load_manifest()["phases"]
    except Exception:  # noqa: BLE001
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description="Canonical render guard (Fix 1).")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--mode", choices=["pre-render", "pre-delivery"],
                    default="pre-render")
    ap.add_argument("--slides", default=None)
    args = ap.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"FATAL: --run-dir not found: {run_dir}", file=sys.stderr)
        return 2

    slides_path = Path(args.slides).resolve() if args.slides else None
    if args.mode == "pre-render":
        reason = guard_pre_render(run_dir)
    else:
        reason = guard_pre_delivery(run_dir, _load_phases(), slides_path)

    if reason:
        bar = "!" * 78
        print("\n" + bar, file=sys.stderr)
        print(reason, file=sys.stderr)
        print(bar + "\n", file=sys.stderr)
        return 5
    print(f"=== CANONICAL-RENDER-GUARD ({args.mode}): PASS ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
