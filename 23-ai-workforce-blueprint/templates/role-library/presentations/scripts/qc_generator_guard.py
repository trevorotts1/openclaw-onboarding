#!/usr/bin/env python3
"""
qc_generator_guard.py — GUARD C: UNGOVERNED QC-REPORT GENERATOR NEUTRALIZER.

================================================================================
THE GAP THIS CLOSES (deep-diagnosis item #8). The anti-bypass surface
(canonical_render_guard.py) catches hand-rolled *renderers/assemblers* — but it
has NO detection for hand-rolled *QC-report generators*. On the reference-case
client box a hand-authored `working/qc/_build_qc_report.py` scored prompts by a
WORD-COUNT rubric (80–180 words == 10/10) — so a sub-floor ~800-char prompt
scored "perfect" and a COMPLIANT 9,000-char prompt would have scored 3/10 and
FAILED. A hand-authored image-QC generator added a `typography_overlay_readiness`
criterion that REWARDED a blank overlay-ready canvas and an "out of scope" escape
that excused the three Pillow hook cards. These corrupt generators emitted
`*_qc_report.json` files the governed pipeline then trusted. That is an inverted,
false-pass QC layer.

The corrupt generators are HAND-AUTHORED at runtime on the client box — they are
never shipped from this repo. They therefore cannot be "deleted from the repo";
they must be NEUTRALIZED at run time. This guard does exactly that, two ways:

  1. GENERATOR DETECTION — scan the run dir for any non-canonical *.py that either
     writes a `*_qc_report*.json` (it is a hand-rolled QC-report generator) or
     carries an inverted/corrupt QC rubric signature (word-count prompt scoring,
     `typography_overlay_readiness`, a scope-exclusion escape, or a lowered
     pass-threshold below the governed 8.5). A finding BLOCKS the run. The ONLY
     thing allowed to produce a QC report is the governed build_deck.py path.

  2. REPORT FINGERPRINTING — scan every `*_qc_report*.json` in the run dir for the
     corrupt-rubric fingerprints above. A governed QC report (graded to the
     build_deck.py contract: independence-provenance block, average >= 8.5, real
     pixel/vision image read) never carries them. A report that does was produced
     by an ungoverned generator and is UNTRUSTED — the governed path must ignore
     it. This catches the bad report even if the generator script was deleted.

THE ONLY BYPASS is the same explicit, LOGGED owner/founder approval token the
canonical render guard honors — `owner_skip_approval` in
working/checkpoints/process_manifest.json naming the AF code it covers. A gate is
NEVER skipped silently and NEVER by an agent's own choice.

AUTO-FAIL CODES (exact strings — do not rename):
    AF-QC-GENERATOR-UNGOVERNED — a non-canonical script emits a *_qc_report.json
                                 (a hand-rolled QC-report generator). Only the
                                 governed build_deck.py path may produce QC reports.
    AF-QC-RUBRIC-CORRUPT       — a non-canonical script carries an inverted/corrupt
                                 QC rubric (word-count prompt scoring, overlay-
                                 readiness reward, scope-exclusion escape, or a
                                 sub-8.5 pass threshold).
    AF-QC-REPORT-UNTRUSTED     — a *_qc_report.json carries a corrupt-rubric
                                 fingerprint; it was not produced by the governed
                                 pipeline and must be ignored.

ZERO third-party deps (stdlib argparse / json / re / sys / pathlib only).

EXIT CODES (CLI)
    0 — clean: no ungoverned QC generator, no untrusted QC report (or every
        finding covered by a logged owner_skip_approval).
    5 — BLOCKED: an ungoverned QC generator and/or untrusted QC report is present.
    2 — usage / run-dir error.

USAGE
    python3 qc_generator_guard.py --run-dir <RUN_DIR>
    python3 qc_generator_guard.py --run-dir <RUN_DIR> --json
"""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Auto-fail codes — EXACT strings. Shared with the deep-diagnosis fix-set.
AF_QC_GENERATOR_UNGOVERNED = "AF-QC-GENERATOR-UNGOVERNED"
AF_QC_RUBRIC_CORRUPT = "AF-QC-RUBRIC-CORRUPT"
AF_QC_REPORT_UNTRUSTED = "AF-QC-REPORT-UNTRUSTED"

# The governed QC pass threshold. Any rubric that scores against a lower bar is
# corrupt by construction (the reference case quietly dropped image-QC to 8.0).
GOVERNED_QC_THRESHOLD = "8.5"

# Canonical, sanctioned scripts. These ARE the governed pipeline; build_deck.py
# legitimately writes qc_report.json. They are allow-listed by BASENAME so that
# even if copied into a run dir they are never flagged. Seeded from a hard core
# plus (best-effort) the canonical render guard's own allow-list and every *.py
# that ships in this scripts dir.
_CORE_CANONICAL = {
    "build_deck.py", "run_signature_deck.py", "canonical_render_guard.py",
    "qc_generator_guard.py", "build_teleprompter.py", "sync_check.py",
    "kie_generate.py", "ghl_media.py", "ghl_media_push.py", "delivery_gate.py",
    "speech_build_harness.py", "presenters_speech_pdf.py", "gate_integrity_check.py",
    "doctrine_residual_check.py", "intelligence_engines_check.py",
    "pitch_engines_check.py", "test_preflight.py",
}


def canonical_script_names() -> set:
    """The basenames that are the governed pipeline (never flagged). Reuses the
    canonical render guard's allow-list when importable, plus every *.py shipped in
    this scripts dir, plus the hard core."""
    names = set(_CORE_CANONICAL)
    try:
        import canonical_render_guard as crg  # noqa: WPS433
        names |= set(crg.canonical_script_names())
    except Exception:  # noqa: BLE001
        pass
    try:
        for p in HERE.glob("*.py"):
            names.add(p.name)
    except Exception:  # noqa: BLE001
        pass
    return names


# ---------------------------------------------------------------------------
# Detection patterns.
# ---------------------------------------------------------------------------
# A non-canonical *.py that NAMES a *_qc_report*.json filename is a hand-rolled QC
# report generator. (build_deck.py also names qc_report.json — but it is canonical
# and is skipped before we ever read it.)
_QC_REPORT_FILENAME_RX = re.compile(
    r"""['"][^'"]*qc[_-]?report[^'"]*\.json['"]""", re.IGNORECASE)

# Inverted / corrupt QC rubric signatures. Any one of these in a non-canonical
# script is a corrupt rubric (AF-QC-RUBRIC-CORRUPT).
_CORRUPT_RUBRIC_PATTERNS = [
    (re.compile(r"score_prompt_length", re.IGNORECASE),
     "word-count prompt-length rubric (scores SHORT prompts high, FAILS compliant ones)"),
    (re.compile(r"prompt[_ ]?word[_ ]?count", re.IGNORECASE),
     "prompt word-count scoring (length-by-words, not the 9,000-char floor)"),
    (re.compile(r"words?[_ ]?in[_ ]?band", re.IGNORECASE),
     "word-band scoring (e.g. 80-180 words == pass)"),
    (re.compile(r"\b80\s*[-–]\s*180\b"),
     "80-180 word band (the inverted prompt rubric)"),
    (re.compile(r"typography[_ ]?overlay[_ ]?readiness", re.IGNORECASE),
     "typography_overlay_readiness criterion (REWARDS a blank overlay-ready canvas)"),
    (re.compile(r"overlay[_ ]?read(?:y|iness)", re.IGNORECASE),
     "overlay-readiness criterion (rewards a blank canvas for post-production text)"),
    (re.compile(r"out[_ ]of[_ ]scope", re.IGNORECASE),
     "out-of-scope escape (excuses slides — e.g. the Pillow hook cards — from QC)"),
    (re.compile(r"(?:excluded?|skip)[_ ]?slides?", re.IGNORECASE),
     "slide scope-exclusion (no slide may be excused from QC scope)"),
    (re.compile(r"(?:threshold|pass[_ ]?mark|pass[_ ]?threshold|min[_ ]?score|cutoff)"
                r"\s*[:=]\s*8\.0\b", re.IGNORECASE),
     "lowered pass threshold 8.0 (governed bar is 8.5)"),
]

# Corrupt fingerprints in an emitted *_qc_report.json (text scan — JSON or not).
_CORRUPT_REPORT_PATTERNS = [
    (re.compile(r"typography[_ ]?overlay[_ ]?readiness", re.IGNORECASE),
     "typography_overlay_readiness criterion (blank-canvas reward)"),
    (re.compile(r"overlay[_ ]?read(?:y|iness)", re.IGNORECASE),
     "overlay-readiness criterion"),
    (re.compile(r"out[_ ]of[_ ]scope", re.IGNORECASE),
     "out-of-scope exclusion (a slide was excused from QC)"),
    (re.compile(r"prompt[_ ]?word[_ ]?count", re.IGNORECASE),
     "prompt word-count field (inverted prompt rubric)"),
    (re.compile(r"words?[_ ]?in[_ ]?band", re.IGNORECASE),
     "word-band field"),
    (re.compile(r"score_prompt_length", re.IGNORECASE),
     "word-count rubric field"),
    (re.compile(r'"(?:threshold|pass_threshold|pass_mark|min_score|cutoff)"'
                r'\s*:\s*8\.0\b', re.IGNORECASE),
     "lowered pass threshold 8.0 (governed bar is 8.5)"),
]

_SKIP_DIR_PARTS = {".venv", "venv", "site-packages", "node_modules", "__pycache__",
                   ".git", ".pytest_cache"}


def _iter_non_canonical_py(run_dir: Path):
    """Yield every *.py under run_dir that is NOT a canonical sanctioned script and
    NOT inside the canonical scripts dir this guard ships in."""
    allow = canonical_script_names()
    for p in run_dir.rglob("*.py"):
        try:
            rp = p.resolve()
        except Exception:  # noqa: BLE001
            rp = p
        try:
            rp.relative_to(HERE)  # never flag the canonical scripts home
            continue
        except ValueError:
            pass
        if p.name in allow:
            continue
        if set(p.parts) & _SKIP_DIR_PARTS:
            continue
        yield p


def _iter_qc_report_json(run_dir: Path):
    """Yield every *_qc_report*.json under run_dir (case-insensitive)."""
    seen = set()
    for p in run_dir.rglob("*.json"):
        if set(p.parts) & _SKIP_DIR_PARTS:
            continue
        if re.search(r"qc[_-]?report", p.name, re.IGNORECASE):
            rp = str(p.resolve())
            if rp not in seen:
                seen.add(rp)
                yield p


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def scan_run_dir(run_dir: Path) -> list:
    """Return a list of findings. Each finding is a dict:
        {file, af_code, line, reason, snippet}

    Findings:
      * AF-QC-GENERATOR-UNGOVERNED — a non-canonical .py names a *_qc_report.json.
      * AF-QC-RUBRIC-CORRUPT       — a non-canonical .py carries a corrupt rubric.
      * AF-QC-REPORT-UNTRUSTED     — a *_qc_report.json carries a corrupt fingerprint.
    """
    findings = []

    # (1/2) ungoverned QC-report generators + corrupt rubrics.
    for path in _iter_non_canonical_py(run_dir):
        try:
            text = path.read_text(errors="replace")
        except Exception:  # noqa: BLE001
            continue
        try:
            rel = str(path.relative_to(run_dir))
        except ValueError:
            rel = str(path)

        m = _QC_REPORT_FILENAME_RX.search(text)
        if m:
            findings.append({
                "file": rel, "af_code": AF_QC_GENERATOR_UNGOVERNED,
                "line": _line_of(text, m.start()),
                "reason": ("non-canonical script emits a QC report — only the "
                           "governed build_deck.py path may produce QC reports"),
                "snippet": m.group(0)[:120].replace("\n", " "),
            })
        for rx, reason in _CORRUPT_RUBRIC_PATTERNS:
            mm = rx.search(text)
            if mm:
                findings.append({
                    "file": rel, "af_code": AF_QC_RUBRIC_CORRUPT,
                    "line": _line_of(text, mm.start()), "reason": reason,
                    "snippet": mm.group(0)[:120].replace("\n", " "),
                })

    # (3) untrusted QC reports — corrupt fingerprints inside an emitted report.
    for path in _iter_qc_report_json(run_dir):
        try:
            text = path.read_text(errors="replace")
        except Exception:  # noqa: BLE001
            continue
        try:
            rel = str(path.relative_to(run_dir))
        except ValueError:
            rel = str(path)
        for rx, reason in _CORRUPT_REPORT_PATTERNS:
            mm = rx.search(text)
            if mm:
                findings.append({
                    "file": rel, "af_code": AF_QC_REPORT_UNTRUSTED,
                    "line": _line_of(text, mm.start()), "reason": reason,
                    "snippet": mm.group(0)[:120].replace("\n", " "),
                })

    return findings


# ---------------------------------------------------------------------------
# Owner/founder skip token — the ONLY bypass, and it must be LOGGED. Mirrors
# canonical_render_guard so the two guards share one bypass contract.
# ---------------------------------------------------------------------------
def load_owner_skip_approvals(run_dir: Path) -> dict:
    """Return {gate: record} for every well-formed owner/founder skip token. Delegates
    to canonical_render_guard when importable (single source of truth); falls back to
    a self-contained read of process_manifest.json otherwise."""
    try:
        import canonical_render_guard as crg  # noqa: WPS433
        return crg.load_owner_skip_approvals(run_dir)
    except Exception:  # noqa: BLE001
        pass
    p = run_dir / "working" / "checkpoints" / "process_manifest.json"
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}
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


def _format_findings(findings: list, owner_skips: dict) -> tuple:
    blocking, waived = [], []
    for f in findings:
        if f["af_code"] in owner_skips:
            waived.append(f)
        else:
            blocking.append(f)
    return blocking, waived


def guard_qc_generators(run_dir: Path) -> str:
    """Return "" when the run dir is free of ungoverned QC generators and untrusted
    QC reports (or every finding is covered by a logged owner_skip_approval).
    Otherwise return a fatal AF message the caller MUST treat as a hard abort.

    This is callable from both the canonical render guard's pre-render and
    pre-delivery checkpoints (defense in depth): block the generator before it can
    emit a report, and refuse to trust any corrupt report at delivery."""
    findings = scan_run_dir(run_dir)
    owner_skips = load_owner_skip_approvals(run_dir)
    blocking, waived = _format_findings(findings, owner_skips)
    if not blocking:
        if waived:
            print("=== QC-GENERATOR-GUARD: "
                  f"{len(waived)} finding(s) WAIVED by logged owner_skip_approval ===",
                  flush=True)
        return ""
    lines = [
        "QC-GENERATOR GUARD — BLOCK.",
        "An ungoverned QC-report generator and/or an untrusted QC report was found "
        "in the run dir. The ONLY thing allowed to produce a QC report is the "
        "governed build_deck.py path. Hand-rolled QC generators (word-count prompt "
        "rubrics, overlay-readiness/blank-canvas rewards, out-of-scope escapes, "
        "sub-8.5 thresholds) produce INVERTED, false-pass reports and are FORBIDDEN.",
        "",
    ]
    for f in blocking:
        lines.append(f"  [{f['af_code']}] {f['file']}:{f['line']} — {f['reason']}  "
                     f"(`{f['snippet']}`)")
    lines.append("")
    lines.append("To proceed you must DELETE the hand-rolled QC generator(s) and any "
                 "report they emitted, and let the governed build_deck.py path produce "
                 "the QC reports — OR record an explicit owner_skip_approval token "
                 "(owner_approved:true + approved_by + reason + gate=<AF code>) in "
                 "working/checkpoints/process_manifest.json. An agent may NOT waive "
                 "this on its own.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Ungoverned QC-report generator neutralizer (Guard C, fix-8).")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"FATAL: --run-dir not found: {run_dir}", file=sys.stderr)
        return 2

    findings = scan_run_dir(run_dir)
    owner_skips = load_owner_skip_approvals(run_dir)
    blocking, waived = _format_findings(findings, owner_skips)

    if args.as_json:
        print(json.dumps({
            "clean": not blocking,
            "blocking": blocking,
            "waived": waived,
        }, indent=2))
        return 5 if blocking else 0

    if not blocking:
        print("=== qc_generator_guard: UNGOVERNED QC-GENERATOR NEUTRALIZER (Guard C) ===")
        print(f"run-dir: {run_dir}")
        if waived:
            print(f"{len(waived)} finding(s) WAIVED by logged owner_skip_approval.")
        print("CLEAN — no ungoverned QC-report generator, no untrusted QC report. "
              "QC reports may be produced only by the governed build_deck.py path.")
        return 0

    bar = "!" * 78
    print("\n" + bar, file=sys.stderr)
    print(guard_qc_generators(run_dir), file=sys.stderr)
    print(bar + "\n", file=sys.stderr)
    return 5


if __name__ == "__main__":
    sys.exit(main())
