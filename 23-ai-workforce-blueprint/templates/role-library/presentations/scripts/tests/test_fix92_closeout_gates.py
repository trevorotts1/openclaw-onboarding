#!/usr/bin/env python3
"""
test_fix92_closeout_gates.py — FIX 92 behavioral proof: the grounding and
representation artifacts are REGISTERED AS GATES, not merely listed.

FIX 92 (2026-09-02) registers the FIX 16 sub-verdicts —
phase_verifiers._verify_image_grounding (image-grounding-steward, owns
P-IMAGE-QC) and phase_verifiers._verify_representation_casting
(representation-casting-director, owns P-PROMPT-QC) — as closeout gates:

  - PIPELINE-MANIFEST.autofails rows AF-IMAGE-GROUNDING(-PARK) /
    AF-CASTING(-PARK / -MIX-PARITY), enforced_by "closeout_gate", each
    carrying a py_symbol that RESOLVES on build_deck
    (_chk_image_grounding_verdict / _chk_representation_casting_verdict).
  - build_deck's postflight closeout runs both wrappers and a PARK flips
    deck_pptx to failed (AF-BUNDLE-COMPLETE).

THE PROOF (what this module pins, behaviorally, per the FIX 92 brief):

  PRESENT fixtures pass — a run dir whose image_qc_report.json carries an
  image_grounding={pass: true, reviewed_by: <independent>} sub-verdict and
  whose prompt_qc_report.json carries representation_casting={pass: true,
  reviewed_by: <independent>} is passed by BOTH closeout wrappers ("").

  ABSENT fixtures fail — the SAME run dir with the sub-verdicts deleted is
  failed by BOTH wrappers with AF-IMAGE-GROUNDING-PARK / AF-CASTING-PARK
  (a parked verdict cannot ship: fail-closed unless the explicit
  test/CI degraded signals are present, so the fixtures run with the
  degraded env CLEAR).

Run:  python3 -m pytest tests/test_fix92_closeout_gates.py -q
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import build_deck  # noqa: E402
import phase_verifiers  # noqa: E402

REVIEWER = "human-vision-reviewer-7"


def _clean_degraded_env(monkeypatch):
    """FIX 92 closeout gates fail CLOSED on a missing sub-verdict unless an
    explicit test/CI degraded signal is present. The fixtures must exercise the
    PRODUCTION teeth, so every degraded signal is cleared (the A3/registry
    invariants are pinned in test_autofail_registry.py; this module proves the
    gate's PASS/FAIL behavior)."""
    for var in ("PRESENTATION_ALLOW_DEGRADED_VERIFIERS", "CI", "OPENCLAW_TEST"):
        monkeypatch.delenv(var, raising=False)


def _make_closeout_run_dir() -> Path:
    """A minimal closeout-stage run dir: no render prompts, no research map,
    no intake mix (P0A-INTAKE owns capture absence) — only the two QC reports
    the closeout verdict gates read. With no prompts to judge, the sub-verdict
    block is the ONLY live input, which is exactly the artifact FIX 92 gates."""
    d = Path(tempfile.mkdtemp(prefix="fix92_closeout_"))
    qc = d / "working" / "qc"
    qc.mkdir(parents=True, exist_ok=True)
    return d


def _write_reports(d: Path, image_grounding: dict, representation_casting: dict):
    qc = d / "working" / "qc"
    qc.mkdir(parents=True, exist_ok=True)
    (qc / "image_qc_report.json").write_text(
        json.dumps({"image_grounding": image_grounding}))
    (qc / "prompt_qc_report.json").write_text(
        json.dumps({"representation_casting": representation_casting}))


# ===========================================================================
# PRESENT fixtures pass
# ===========================================================================
def test_present_image_grounding_verdict_passes(tmp_path, monkeypatch):
    _clean_degraded_env(monkeypatch)
    d = tmp_path
    _write_reports(d, {"pass": True, "reviewed_by": REVIEWER}, {})
    reason = build_deck._chk_image_grounding_verdict(d)
    assert reason == "", (
        "a run dir whose image_qc_report.json carries image_grounding="
        f"{{pass:true, reviewed_by:{REVIEWER!r}}} must PASS the AF-IMAGE-GROUNDING-PARK "
        f"closeout gate (''), got: {reason!r}")
    ok, _ = phase_verifiers._verify_image_grounding(d)
    assert ok, "the delegated FIX 16 sub-verifier must agree with the closeout wrapper"


def test_present_representation_casting_verdict_passes(tmp_path, monkeypatch):
    _clean_degraded_env(monkeypatch)
    d = tmp_path
    _write_reports(d, {}, {"pass": True, "reviewed_by": REVIEWER})
    reason = build_deck._chk_representation_casting_verdict(d)
    assert reason == "", (
        "a run dir whose prompt_qc_report.json carries representation_casting="
        f"{{pass:true, reviewed_by:{REVIEWER!r}}} must PASS the AF-CASTING-PARK "
        f"closeout gate (''), got: {reason!r}")
    ok, _ = phase_verifiers._verify_representation_casting(d)
    assert ok, "the delegated FIX 16 sub-verifier must agree with the closeout wrapper"


# ===========================================================================
# ABSENT fixtures fail
# ===========================================================================
def test_absent_image_grounding_verdict_parks(tmp_path, monkeypatch):
    _clean_degraded_env(monkeypatch)
    d = tmp_path
    _write_reports(d, {}, {})  # both reports exist, verdicts absent
    reason = build_deck._chk_image_grounding_verdict(d)
    assert reason, "an image_qc_report.json with NO image_grounding verdict must FAIL the closeout gate"
    assert "AF-IMAGE-GROUNDING-PARK" in reason, (
        f"expected AF-IMAGE-GROUNDING-PARK in the park reason, got: {reason!r}")


def test_absent_representation_casting_verdict_parks(tmp_path, monkeypatch):
    _clean_degraded_env(monkeypatch)
    d = tmp_path
    _write_reports(d, {}, {})
    reason = build_deck._chk_representation_casting_verdict(d)
    assert reason, "a prompt_qc_report.json with NO representation_casting verdict must FAIL the closeout gate"
    assert "AF-CASTING-PARK" in reason, (
        f"expected AF-CASTING-PARK in the park reason, got: {reason!r}")


def test_failing_image_grounding_verdict_parks(tmp_path, monkeypatch):
    _clean_degraded_env(monkeypatch)
    d = tmp_path
    _write_reports(d, {"pass": False, "reviewed_by": REVIEWER}, {})
    reason = build_deck._chk_image_grounding_verdict(d)
    assert "AF-IMAGE-GROUNDING" in reason, (
        f"a pass!=true image_grounding verdict must park the run, got: {reason!r}")


def test_failing_representation_casting_verdict_parks(tmp_path, monkeypatch):
    _clean_degraded_env(monkeypatch)
    d = tmp_path
    _write_reports(d, {}, {"pass": False, "reviewed_by": REVIEWER})
    reason = build_deck._chk_representation_casting_verdict(d)
    assert "AF-CASTING" in reason, (
        f"a pass!=true representation_casting verdict must park the run, got: {reason!r}")


def test_builder_self_reviewed_by_is_refused(tmp_path, monkeypatch):
    """A builder/self identity cannot clear its own verdict — same rule the
    phase attestation enforces; the closeout wrapper must not be weaker."""
    _clean_degraded_env(monkeypatch)
    d = tmp_path
    _write_reports(d, {"pass": True, "reviewed_by": "builder"},
                   {"pass": True, "reviewed_by": "self"})
    g = build_deck._chk_image_grounding_verdict(d)
    c = build_deck._chk_representation_casting_verdict(d)
    assert g and "AF-IMAGE-GROUNDING" in g, f"builder-graded grounding verdict must park, got: {g!r}"
    assert c and "AF-CASTING" in c, f"self-graded casting verdict must park, got: {c!r}"


# ===========================================================================
# The registered closeout_gate rows point at these wrappers (lockstep)
# ===========================================================================
def test_manifest_rows_resolve_on_build_deck():
    manifest = json.loads(
        (SCRIPTS.parent.parent.parent.parent.parent
         / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
         ).read_text())
    rows = {a["code"]: a for a in manifest["autofails"]}
    for code, sym in (
        ("AF-IMAGE-GROUNDING-PARK", "_chk_image_grounding_verdict"),
        ("AF-CASTING-PARK", "_chk_representation_casting_verdict"),
    ):
        assert code in rows, f"{code} missing from PIPELINE-MANIFEST.autofails"
        assert rows[code].get("enforced_by") == "closeout_gate", (
            f"{code} must be enforced_by closeout_gate, got {rows[code].get('enforced_by')!r}")
        assert rows[code].get("py_symbol") == sym
        assert hasattr(build_deck, sym), f"{sym} does not resolve on build_deck"


def test_closeout_wiring_runs_both_wrappers():
    src = (SCRIPTS / "build_deck.py").read_text(encoding="utf-8")
    assert "_chk_image_grounding_verdict(run_dir)" in src
    assert "_chk_representation_casting_verdict(run_dir)" in src


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-v"]))
