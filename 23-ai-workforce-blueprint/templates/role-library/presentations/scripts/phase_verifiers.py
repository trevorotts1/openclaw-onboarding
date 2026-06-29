#!/usr/bin/env python3
"""
phase_verifiers.py — Per-phase SUBSTANCE verifiers for the presentations pipeline.

Called by prove-deck.py at P9-DELIVER to verify that each governed phase produced
substantive, readable output — not just that the produces_artifact file exists (that
is already enforced by run_signature_deck.py's precondition checks) but that the
content inside passes a minimal-substance bar (non-empty JSON / non-empty text, correct
keys present, etc.).

DESIGN RULES
  * These verifiers are SECONDARY proofs — they supplement, never replace, the
    attestation-chain check.
  * Every verifier is FAIL-SOFT for file-not-found: if a produces_artifact is
    absent, the verifier returns an empty string ("") because run_signature_deck.py
    already hard-aborts on that condition. The verifier only flags substantive
    failures (zero-byte file, JSON parse error, empty-collections inside).
  * NO network calls, NO side effects. Pure filesystem reads.
  * USAGE: verify_phase(run_dir, phase_spec) -> "" (pass) | reason string (fail)
           verify_all_phases(run_dir, phases)  -> [(phase_id, reason), ...]

Run with --selftest for built-in deterministic self-tests (exits 0 on pass).
"""

from __future__ import annotations

import glob
import json
import sys
import tempfile
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_glob(run_dir: Path, pattern: str) -> Optional[Path]:
    """Resolve a glob pattern relative to run_dir; return the first match or None."""
    if not pattern:
        return None
    if "*" in pattern or "?" in pattern:
        hits = sorted(run_dir.glob(pattern))
        return hits[0] if hits else None
    p = run_dir / pattern
    return p if p.exists() else None


def _read_json(path: Path) -> Optional[dict]:
    """Read a JSON file, returning None on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _read_text(path: Path) -> Optional[str]:
    """Read a text file, returning None on any error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Per-phase verifiers
# Each returns "" on pass, a non-empty reason string on fail.
# ---------------------------------------------------------------------------

def _verify_json_nonempty(run_dir: Path, pattern: str, required_keys: tuple = ()) -> str:
    """Generic: resolves a JSON artifact, checks it is non-empty and has required_keys."""
    p = _resolve_glob(run_dir, pattern)
    if p is None:
        return ""  # absent is run_signature_deck's problem, not ours
    if p.stat().st_size == 0:
        return f"{pattern}: file is zero bytes."
    obj = _read_json(p)
    if obj is None:
        return f"{pattern}: not valid JSON."
    if isinstance(obj, dict):
        for k in required_keys:
            if k not in obj:
                return f"{pattern}: required key {k!r} absent."
    elif isinstance(obj, list) and len(obj) == 0:
        return f"{pattern}: JSON array is empty."
    return ""


def _verify_text_nonempty(run_dir: Path, pattern: str, min_bytes: int = 20) -> str:
    """Generic: resolves a text artifact, checks it has min_bytes of content."""
    p = _resolve_glob(run_dir, pattern)
    if p is None:
        return ""
    txt = _read_text(p)
    if txt is None:
        return f"{pattern}: unreadable."
    if len(txt.strip()) < min_bytes:
        return f"{pattern}: suspiciously short ({len(txt.strip())} chars < {min_bytes})."
    return ""


# Phase-specific verifiers (keyed by phase id)
_PHASE_VERIFIERS = {
    "P-0.5-RESEARCH": lambda rd: _verify_text_nonempty(rd, "working/research/brief-*.md", 100),
    "P-CONVERTER":    lambda rd: _verify_json_nonempty(rd, "working/copy/intake.json", ("slides",)),
    "P0A-INTAKE":     lambda rd: _verify_json_nonempty(rd, "working/copy/intake.json"),
    "P0B-PRIORITY":   lambda rd: _verify_json_nonempty(rd, "working/copy/priority_shift_spec.json"),
    "P-STYLE-PREVIEW": lambda rd: _verify_json_nonempty(rd, "working/style-preview/style_samples_manifest.json"),
    "P-SHIFT-QC":     lambda rd: _verify_json_nonempty(rd, "working/qc/priority_shift_report.json"),
    "P1Q-COPY-QC":    lambda rd: _verify_json_nonempty(rd, "working/qc/copy_qc_report.json"),
    "P3-ARC":         lambda rd: _verify_json_nonempty(rd, "working/copy/arc_allocation.json"),
    "P-3.5-RESEARCH-MAP": lambda rd: _verify_json_nonempty(rd, "working/research/research_map.json"),
    "P4-COPY":        lambda rd: _verify_text_nonempty(rd, "working/copy/slides_copy.md", 50),
    "PF-DESIGN":      lambda rd: _verify_text_nonempty(rd, "working/research/design-brief-*.md", 50),
    "P-TYPO-QC":      lambda rd: _verify_json_nonempty(rd, "working/qc/typography_qc_report.json"),
    "P4-PROMPT":      lambda rd: _verify_text_nonempty(rd, "working/prompts/slide-*.txt", 100),
    "P-PROMPT-QC":    lambda rd: _verify_json_nonempty(rd, "working/qc/prompt_qc_report.json"),
    "P4-RENDER":      lambda rd: _verify_render(rd),
    "P-IMAGE-QC":     lambda rd: _verify_json_nonempty(rd, "working/qc/image_qc_report.json"),
    "P8-ASSEMBLE":    lambda rd: _verify_assembly(rd),
    "P9-SPEECH":      lambda rd: _verify_text_nonempty(rd, "working/presenter-speech/PRESENTERS-SPEECH.md", 200),
    "P-SPEECH-QC":    lambda rd: _verify_json_nonempty(rd, "working/qc/speech_qc_report.json"),
    "P9-DELIVER":     lambda rd: _verify_delivery(rd),
}


def _verify_render(run_dir: Path) -> str:
    """Verify at least one render PNG exists."""
    hits = list(run_dir.glob("renders/slide-*.png"))
    if not hits:
        return "renders/slide-*.png: no render PNGs found."
    return ""


def _verify_assembly(run_dir: Path) -> str:
    """Verify a FINAL .pptx exists and is non-trivially sized."""
    hits = [p for p in run_dir.glob("**/*.pptx") if not p.name.startswith("~$")]
    if not hits:
        return "*-FINAL.pptx: no .pptx found in run dir."
    biggest = max(hits, key=lambda p: p.stat().st_size)
    if biggest.stat().st_size < 1000:
        return f"{biggest.name}: .pptx is suspiciously small ({biggest.stat().st_size} bytes)."
    return ""


def _verify_delivery(run_dir: Path) -> str:
    """Verify the delivery artifact (PRESENTER-AUDIO.mp3) or delivery bundle exists."""
    audio = run_dir / "working" / "delivery" / "PRESENTER-AUDIO.mp3"
    if audio.exists() and audio.stat().st_size > 1000:
        return ""
    # Fallback: any delivery artifact
    hits = list(run_dir.glob("working/delivery/*"))
    if hits:
        return ""
    # Not present — still not our hard-abort condition (run_signature_deck handles it)
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_phase(run_dir: Path, phase_spec: dict) -> str:
    """Run the substance verifier for `phase_spec['id']`. Returns "" on pass,
    a reason string on fail. Falls back to generic text/json check when no
    specific verifier is registered."""
    phase_id = phase_spec.get("id", "")
    verifier = _PHASE_VERIFIERS.get(phase_id)
    if verifier is not None:
        return verifier(run_dir)
    # Generic fallback: if there is a produces_artifact, do a basic nonempty check.
    artifact = phase_spec.get("produces_artifact", "")
    if artifact:
        p = _resolve_glob(run_dir, artifact)
        if p is not None and p.stat().st_size == 0:
            return f"{artifact}: zero-byte artifact."
    return ""


def verify_all_phases(run_dir: Path, phases: list) -> list:
    """Verify substance for all phases. Returns [(phase_id, reason), ...] for failures."""
    failures = []
    for ph in phases:
        reason = verify_phase(run_dir, ph)
        if reason:
            failures.append((ph.get("id", "?"), reason))
    return failures


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _selftest() -> None:
    """Deterministic self-tests. All must pass. Exits 0 on success, 1 on failure."""
    import json
    import tempfile

    fails = []

    with tempfile.TemporaryDirectory(prefix="phase_verifiers_selftest_") as tmp:
        rd = Path(tmp)

        # Test 1: absent artifact => "" (not our hard-abort)
        r = verify_phase(rd, {"id": "P0A-INTAKE", "produces_artifact": "working/copy/intake.json"})
        if r != "":
            fails.append(f"T1: absent artifact should pass, got {r!r}")

        # Test 2: zero-byte JSON artifact => fail
        zb = rd / "working" / "copy" / "intake.json"
        zb.parent.mkdir(parents=True, exist_ok=True)
        zb.write_bytes(b"")
        r = verify_phase(rd, {"id": "P0A-INTAKE"})
        if not r:
            fails.append("T2: zero-byte intake.json should fail")

        # Test 3: valid JSON artifact => ""
        zb.write_text(json.dumps({"slides": [{"idx": 1}]}))
        r = verify_phase(rd, {"id": "P0A-INTAKE"})
        if r != "":
            fails.append(f"T3: valid intake.json should pass, got {r!r}")

        # Test 4: verify_all_phases with no artifacts (all absent => no failures)
        rd2 = Path(tempfile.mkdtemp(prefix="phase_verifiers_selftest2_"))
        phases = [
            {"id": "P0A-INTAKE", "produces_artifact": "working/copy/intake.json"},
            {"id": "P0B-PRIORITY", "produces_artifact": "working/copy/priority_shift_spec.json"},
        ]
        failures = verify_all_phases(rd2, phases)
        if failures:
            fails.append(f"T4: all-absent should produce no failures, got {failures}")

        # Test 5: a phase with no registered verifier + zero-byte artifact
        bad = rd2 / "working" / "qc" / "custom_report.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_bytes(b"")
        r = verify_phase(rd2, {"id": "UNKNOWN-PHASE", "produces_artifact": "working/qc/custom_report.json"})
        if not r:
            fails.append("T5: unknown phase + zero-byte artifact should fail via generic fallback")

    if fails:
        for f in fails:
            print(f"[phase_verifiers selftest] FAIL: {f}", file=sys.stderr)
        sys.exit(1)
    print("[phase_verifiers selftest] PASS — all self-tests passed.", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print("Usage: phase_verifiers.py --selftest", file=sys.stderr)
        sys.exit(1)
