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

# FIX-2 (Error 2): the four QC phases are STRUCTURALLY UNSKIPPABLE. A skip record
# (phase_skip_approvals.json) or an owner_skip_approval token can never waive a QC
# phase — the phase must be genuinely attested with a REAL report (see build_deck's
# check_qc_phase_report_real for the >256-byte / >=20-per-slide-verdict floor).
# This mirrors build_deck.UNSKIPPABLE_QC_PHASES exactly (kept in lockstep; the guard
# is intentionally import-free so it can never crash on a missing symbol).
UNSKIPPABLE_QC_PHASES = frozenset({
    "P1Q-COPY-QC",
    "P-PROMPT-QC",
    "P-TYPO-QC",
    "P-SHIFT-QC",
})

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
    # The ONE shared image-prompt gate every image-API path imports, and its standalone
    # CI-runnable prover. Allow-listed by basename so they pass even if copied into a run dir.
    "prompt_gate.py", "prove_pres_prompt_floor.py",
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
    phase record (which counts as P4-RENDER) are honored.

    F04: an attestation row counts ONLY when it is a COMPLETED,
    substance-verified one (status == 'done' AND substance_verified is True).
    Bare id-only rows — the shape a hand-edited manifest produces — do not
    satisfy the delivery boundary chain. The runner's attest_phase() always
    writes both fields; only forged/incomplete rows drop out here."""
    obj = _load_process_manifest(run_dir)
    ids = set()
    for att in obj.get("phase_attestations", []) or []:
        if not isinstance(att, dict):
            continue
        if str(att.get("status", "")).strip().lower() != "done":
            continue
        if att.get("substance_verified") is not True:
            continue
        if att.get("phase_id"):
            ids.add(att["phase_id"])
    for ph in obj.get("phases", []) or []:
        if isinstance(ph, dict) and ph.get("phase") == "render":
            ids.add("P4-RENDER")
    return ids


# The delivery phase id — mirrors run_signature_deck.DELIVERY_PHASE_ID exactly. Kept
# as a self-contained constant here (not imported) to avoid a guard<->runner import
# cycle: run_signature_deck imports THIS module as `guard`. Used as the default
# target_phase_id below because guard_pre_delivery, by construction, only ever gates
# the delivery phase.
DELIVERY_PHASE_ID = "P9-DELIVER"


def missing_attestations(run_dir: Path, phases: list, phase_skip_approvals=None,
                         target_phase_id=DELIVERY_PHASE_ID) -> list:
    """Return the ordered list of governed phase ids that are neither attested nor
    covered by a logged owner skip. phase_skip_approvals (from the runner's
    phase_skip_approvals.json) and process_manifest owner_skip_approval BOTH count.

    Only phases with `order` strictly LESS THAN target_phase_id's own order are
    swept — this mirrors check_phase_preconditions' `order < target_order` exclusion
    (run_signature_deck.py:855-857 / build_deck.py's shared check_phase_preconditions,
    called with prior_phase_ids only) exactly. Without this exclusion, the phase
    currently being dispatched (target_phase_id — e.g. P9-DELIVER itself, when this
    runs pre-delivery) appears in its OWN missing list: a phase structurally CANNOT
    attest itself before the guard gating its own dispatch has passed, so omitting
    the exclusion made every delivery an unconditional, unwinnable refusal. If
    target_phase_id is None or not present in `phases`, no phase is excluded by
    order and every phase is swept (the pre-fix behavior) — callers that know their
    target phase id should always pass it."""
    attested = attested_phase_ids(run_dir)
    owner_skips = load_owner_skip_approvals(run_dir)
    phase_skips = set(phase_skip_approvals or set())
    by_id = {ph.get("id"): ph for ph in phases if ph.get("id")}
    target = by_id.get(target_phase_id) if target_phase_id else None
    target_order = target.get("order", 0) if target is not None else None
    missing = []
    for ph in sorted(phases, key=lambda p: p.get("order", 0)):
        pid = ph.get("id")
        if not pid:
            continue
        if target_order is not None and ph.get("order", 0) >= target_order:
            continue
        # FIX-2 (Error 2): QC phases are STRUCTURALLY UNSKIPPABLE — neither a
        # phase_skip_approvals record NOR a process_manifest owner_skip_approval
        # token can waive a QC phase. The QC phase must be genuinely attested (with
        # a real report); a skip never satisfies it at pre-delivery. AF-QC-SKIP.
        if pid in UNSKIPPABLE_QC_PHASES:
            if pid not in attested:
                missing.append(pid)
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
# U023 — REPOINTED. The three names above never existed on build_deck: a live
# getattr proved all three present=False, so run_fix2_checks `continue`d on every
# iteration and this guard has never produced a Fix-2 finding. The REAL exported
# names are published in build_deck.py's own FIX-2 contract block at :604-609.
# The _chk_local_canvas entry is DELETED, not renamed: no local-canvas function
# has ever existed. AF-LOCAL-CANVAS is emitted from INSIDE
# check_canonical_render_path (see its docstring at build_deck.py:5070/5078) and
# from check_image_qc_vision (:5032), so the code is a RESULT of the two checks
# below and needs no wiring of its own.
_FIX2_SYMBOLS = [
    ("check_canonical_render_path", AF_CANONICAL_RENDER_BYPASS),
    ("check_image_qc_vision", AF_IMAGE_QC_VISION),
]


def run_fix2_checks(run_dir: Path, slides_path=None) -> list:
    """Call the Fix-2 exported check symbols on build_deck if present. Returns a list
    of (af_code, message) failures. Missing symbols are skipped (not failures)."""
    failures = []
    try:
        import build_deck as bd  # noqa: WPS433
    except ImportError:
        # U023 step 4: a genuinely ABSENT build_deck (standalone --mode pre-delivery
        # CLI run from a directory without the engine) still degrades
        return failures
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "canonical_render_guard: build_deck is present but not importable "
            f"({exc!r}) — the Fix-2 pre-delivery cross-check cannot run and must not "
            "pass silently. Fix the engine import before delivering.") from exc
    owner_skips = load_owner_skip_approvals(run_dir)
    for sym, af_code in _FIX2_SYMBOLS:
        fn = getattr(bd, sym, None)
        if not callable(fn):
            # U023 step 3: fail-CLOSED. Reaching here means build_deck no longer
            # exports a name this guard's contract requires (build_deck.py:604-609).
            # Silently continuing is how this guard produced zero findings for its
            # entire life. Raising is safe ONLY because step 2 proved both names
            # resolve before this line existed
            raise RuntimeError(
                f"{af_code}: canonical_render_guard requires build_deck.{sym}, and it is "
                f"not callable (present={fn is not None}). The FIX-2 export contract is "
                f"build_deck.py:604-609; the pre-delivery vision cross-check cannot run "
                f"fail-open. Restore the export or update _FIX2_SYMBOLS in the same commit.")
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


def _qc_generator_block(run_dir: Path) -> str:
    """Guard C (fix-8) wiring. Run the ungoverned-QC-report-generator neutralizer at
    this checkpoint and return its fatal block message ("" when clean). The hand-
    rolled QC generators (word-count prompt rubric, overlay-readiness/blank-canvas
    reward, out-of-scope escape, sub-8.5 threshold) are a DIFFERENT class than the
    hand-rolled renderers this guard detects, so they are enforced by the sibling
    qc_generator_guard. If that module is unavailable the surface degrades to
    renderer-only detection (never crashes)."""
    try:
        import qc_generator_guard as qcg  # noqa: WPS433
    except Exception:  # noqa: BLE001
        return ""
    try:
        return qcg.guard_qc_generators(run_dir)
    except Exception as exc:  # noqa: BLE001
        # Fail-closed on an unexpected error inside the QC-generator scan.
        return (f"AF-QC-GENERATOR-UNGOVERNED: qc_generator_guard raised {exc!r} — "
                "could not prove the run dir is free of ungoverned QC generators.")


def guard_pre_render(run_dir: Path) -> str:
    """PRE-RENDER guard. Return "" when the run dir is free of hand-rolled
    renderers/assemblers (or every finding is covered by a logged
    owner_skip_approval). Otherwise return a fatal AF message that the caller MUST
    treat as a hard abort. This is the gate that blocks `python3 working/phase4_*.py`
    style bypasses BEFORE a single image is rendered."""
    findings = scan_run_dir(run_dir)
    owner_skips = load_owner_skip_approvals(run_dir)
    blocking, waived = _format_findings(findings, owner_skips)
    qc_gen_reason = _qc_generator_block(run_dir)  # Guard C (fix-8): ungoverned QC generators.
    if not blocking:
        if waived:
            print("=== CANONICAL-RENDER-GUARD (pre-render): "
                  f"{len(waived)} finding(s) WAIVED by logged owner_skip_approval ===",
                  flush=True)
        return qc_gen_reason
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
    if qc_gen_reason:
        lines.append("")
        lines.append(qc_gen_reason)
    return "\n".join(lines)


def guard_pre_delivery(run_dir: Path, phases: list, slides_path=None,
                       phase_skip_approvals=None,
                       target_phase_id=DELIVERY_PHASE_ID) -> str:
    """PRE-DELIVERY guard. Return "" only when ALL of the following hold:
      1. The run dir is free of hand-rolled renderers (or waived by owner token).
      2. The full process_manifest attestation chain is present — every governed
         phase THAT SHOULD ALREADY BE COMPLETE (i.e. every phase with `order` <
         target_phase_id's own order — target_phase_id defaults to P9-DELIVER, the
         phase this checkpoint gates) is attested, or covered by a logged owner
         skip. target_phase_id itself is deliberately EXCLUDED from the sweep: it
         is the in-flight phase this very guard call is a precondition for, so it
         cannot possibly have attested itself yet — requiring that was the bug (see
         missing_attestations' docstring).
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

    # (2) full attestation chain for every phase that should already be complete —
    # excludes target_phase_id itself (see docstring above and missing_attestations).
    missing = missing_attestations(run_dir, phases, phase_skip_approvals, target_phase_id)
    if missing:
        problems.append("  [AF-PHASE-SKIPPED] incomplete attestation chain — these "
                        "governed phases are neither attested nor owner-skip-approved: "
                        + ", ".join(missing))

    # (3) Fix-2 pixel/vision checks. U023: these two checks ALSO run at preflight
    # (build_deck.py:7191, :7202) and postflight (:8412, :8428). Re-running them at
    # the delivery boundary is deliberate defence in depth, so the same finding can
    # legitimately appear up to three times in one run's output. Tag it so an
    # operator does not read one defect as three.
    for af_code, msg in run_fix2_checks(run_dir, slides_path):
        problems.append(f"  [{af_code}] (pre-delivery re-check) {msg}")

    # (4) Guard C (fix-8): no ungoverned QC-report generator / untrusted QC report
    # may be present at delivery — the governed path must never ship a deck blessed
    # by an inverted, false-pass QC layer.
    qc_gen_reason = _qc_generator_block(run_dir)
    if qc_gen_reason:
        problems.append("  [AF-QC-GENERATOR-UNGOVERNED] ungoverned QC generator / "
                        "untrusted QC report present — see detail below:\n"
                        + "\n".join("    " + ln for ln in qc_gen_reason.splitlines()))

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
