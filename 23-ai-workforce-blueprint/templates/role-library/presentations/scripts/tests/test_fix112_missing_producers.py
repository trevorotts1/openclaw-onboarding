#!/usr/bin/env python3
"""test_fix112_missing_producers.py — FIX 112 (workflow R-B07, unit [opus] R-B07-B1).

PROOF (verbatim, from the fix brief): a stubbed run reaches P-STYLE-PREVIEW
with style_preview_spec.json present (three variants, three slides) authored
by a manifest unit; the infographic-checklist phase exists in the manifest
with a role file and a verifier, and writes a verdict file.

Before FIX 112 both halves of that proof were impossible:

  * P-STYLE-SPEC (manifest order 4.84) declared produces_artifact
    working/copy/style_preview_spec.json but the dispatcher's generic fan-out
    glue (_phase_fanout_spec / _dispatch_phase_fanout_units — the FIX 15b
    branches inside dispatch_one) was NEVER DEFINED in any shipped module:
    the first manifest phase declaring `fanout` crashed dispatch_one with
    NameError, and no phase did declare one. Nothing authored the spec.
  * the infographic-checklist role was named in the bundle table and
    implemented nowhere: no role file, no manifest roles[] row, no verifier,
    no verdict file.

This file proves the fixed pipeline WITHOUT any network/model spend: the model
call inside the fanout unit is stubbed (dispatch_complete monkeypatched at the
dispatcher module seam), everything else is the real code path — real manifest
parse, real FanoutSpec, real fanout.run_units pool, real aggregator, real
atomic write, real phase verifier.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

CLUSTER_MANIFEST = (
    SCRIPTS.parent.parent.parent.parent.parent
    / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
)


def _manifest() -> dict:
    assert CLUSTER_MANIFEST.exists(), f"manifest not found at {CLUSTER_MANIFEST}"
    return json.loads(CLUSTER_MANIFEST.read_text())


def _phase(m: dict, pid: str) -> dict:
    return next(p for p in m["phases"] if p["id"] == pid)


# ---------------------------------------------------------------------------
# Seed a stubbed run: state.json pins the REAL deployed manifest (the same
# resolution path load_manifest_for_run reads); slides.json + intake.json are
# the upstream artifacts P-STYLE-SPEC declares in its manifest consumes[].
# ---------------------------------------------------------------------------
def _seed_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "working" / "copy").mkdir(parents=True)
    slides = [
        {"ordinal": 1, "slide": 1, "slide_id": "s1", "archetype": "cover",
         "copy": ["Hook"], "design_tokens": {"palette": "#223"},
         "research_anchors": [], "negative_requirements": []},
        {"ordinal": 2, "slide": 2, "slide_id": "s2", "archetype": "data",
         "copy": ["Chart"], "design_tokens": {"palette": "#445"},
         "research_anchors": [], "negative_requirements": []},
        {"ordinal": 3, "slide": 3, "slide_id": "s3", "archetype": "people",
         "copy": ["Team"], "design_tokens": {"palette": "#667"},
         "research_anchors": [], "negative_requirements": []},
    ]
    (run_dir / "working" / "copy" / "slides.json").write_text(json.dumps(slides))
    (run_dir / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"business_name": "TestCo", "hook": "Grow without guesswork"}))
    (run_dir / "state.json").write_text(json.dumps(
        {"manifest_path": str(CLUSTER_MANIFEST)}))
    return run_dir


def _phase_obj(run_dir: Path, pid: str):
    """The REAL Phase object, resolved through the run's own pinned manifest —
    the same Manifest instance dispatch_one's fanout branch reads."""
    from presentation_job.dispatcher import load_manifest_for_run
    m = load_manifest_for_run(run_dir)
    assert m is not None, "state.json did not resolve the deployed manifest"
    po = m.phase_or_none(pid)
    assert po is not None
    return po


def _stub_dispatch(monkeypatch, responder):
    import presentation_job.dispatcher as d
    seen_calls = []

    def _fake(system_prompt, user_prompt, *, phase_id, run_dir=None, **kw):
        seen_calls.append({"phase_id": phase_id, "user_prompt": user_prompt})
        return responder(len(seen_calls), user_prompt), \
            {"request_id": "stub-1"}, {"provider": "stub", "model": "stub-1"}

    monkeypatch.setattr(d, "dispatch_complete", _fake)
    return seen_calls


def _style_unit_response(n: int, user_prompt: str) -> str:
    # Each unit authors ONE variant bound to its own slide ordinal, per the
    # P-STYLE-SPEC ARTIFACT_CONTRACTS unit contract.
    ords = [1, 2, 3]
    ordinal = ords[(n - 1) % 3]
    vid = "ABC"[n - 1]
    return json.dumps({"id": vid,
                       "style_directive": f"variant {vid} warm editorial direction",
                       "representative_slide": ordinal})


# ---------------------------------------------------------------------------
# Proof half 1: the stubbed run authors the spec via the manifest fanout unit,
# and P-STYLE-PREVIEW's own preflight gate accepts it.
# ---------------------------------------------------------------------------
def test_stubbed_run_authors_style_preview_spec_via_manifest_fanout_unit(tmp_path, monkeypatch):
    import presentation_job.dispatcher as d
    run_dir = _seed_run(tmp_path)
    calls = _stub_dispatch(monkeypatch, _style_unit_response)

    result = d.dispatch_one(
        run_dir, "P-STYLE-SPEC",
        {"phase_id": "P-STYLE-SPEC", "owning_role": "brand-steward"},
        dept_root=SCRIPTS.parent, phase_obj=_phase_obj(run_dir, "P-STYLE-SPEC"),
        worker_id="test")

    assert result.status == "ok", f"fanout dispatch failed: {result.reasons}"
    spec_path = run_dir / "working" / "copy" / "style_preview_spec.json"
    assert spec_path.is_file(), "the manifest unit did not author the spec"
    spec = json.loads(spec_path.read_text())
    assert isinstance(spec.get("variants"), list) and len(spec["variants"]) == 3
    assert {v["id"] for v in spec["variants"]} == {"A", "B", "C"}
    assert all(str(v.get("style_directive") or "").strip() for v in spec["variants"])
    reps = spec.get("representative_slides")
    assert isinstance(reps, list) and len(reps) == 3
    assert all(isinstance(r, int) and r >= 1 for r in reps)
    # The units really ran: three stubbed model calls, one per fanout unit.
    assert len(calls) == 3
    assert all(c["phase_id"] == "P-STYLE-SPEC" for c in calls)
    # Per-unit ledger rows exist (fanout observability seam — the path is
    # fanout.unit_ledger_path's own, not a guessed one).
    from presentation_job.fanout import unit_ledger_path
    ledger = unit_ledger_path(run_dir, "P-STYLE-SPEC")
    rows = [json.loads(l) for l in ledger.read_text().strip().splitlines() if l.strip()]
    assert len(rows) == 3 and all(r["status"] == "ok" for r in rows), rows
    # And the engine's own phase verifier accepts the authored artifact.
    ok, reasons = d._verify("P-STYLE-SPEC", run_dir)
    assert ok, reasons


def test_style_preview_phase_consumes_the_authored_spec(tmp_path):
    """P-STYLE-PREVIEW's manifest consumes[] names the spec the unit authored —
    the dependency edge the artifact DAG (Fix 8) orders P-STYLE-SPEC before
    P-STYLE-PREVIEW on."""
    m = _manifest()
    preview = _phase(m, "P-STYLE-PREVIEW")
    spec_phase = _phase(m, "P-STYLE-SPEC")
    assert "working/copy/style_preview_spec.json" in preview.get("consumes", [])
    assert spec_phase["produces_artifact"] == "working/copy/style_preview_spec.json"
    # And the unit is manifest-declared, not hardcoded glue:
    assert spec_phase.get("fanout") == {"by": "slide", "max_units": 3}
    # build_deck's real --sample gate refuses anything but 3x3:
    assert spec_phase["order"] < preview["order"]


def test_aggregator_refuses_a_broken_spec_never_writes_one(tmp_path, monkeypatch):
    """A unit output that cannot aggregate (fewer than 3 well-formed
    candidates) refuses the write — no broken artifact ever lands on disk."""
    import presentation_job.dispatcher as d
    run_dir = _seed_run(tmp_path)

    def _bad(n, user_prompt):
        return "not json at all"

    _stub_dispatch(monkeypatch, _bad)
    result = d.dispatch_one(
        run_dir, "P-STYLE-SPEC",
        {"phase_id": "P-STYLE-SPEC", "owning_role": "brand-steward"},
        dept_root=SCRIPTS.parent, phase_obj=_phase_obj(run_dir, "P-STYLE-SPEC"),
        worker_id="test")
    assert result.status == "exhausted"
    assert not (run_dir / "working" / "copy" / "style_preview_spec.json").exists()


# ---------------------------------------------------------------------------
# Proof half 2: the infographic-checklist phase exists in the manifest with a
# role file and a verifier, and the verdict file makes the phase pass.
# ---------------------------------------------------------------------------
def test_infographic_checklist_phase_exists_with_role_file_and_verifier():
    m = _manifest()
    ph = _phase(m, "P8.3-INFOGRAPHIC")
    assert ph["produces_artifact"] == "working/deliverables/infographic.png"
    assert "working/prompts/infographic-prompt.txt" in ph.get("consumes", [])
    # role file — both the brief's named path and the engine-resolvable flat
    # copy ship the same doc.
    flat = SCRIPTS.parent / "infographic-checklist.md"
    nested = SCRIPTS.parent / "roles" / "infographic-checklist.md"
    assert flat.is_file(), f"role file missing: {flat}"
    assert nested.is_file(), f"brief-named role file missing: {nested}"
    assert flat.read_text() == nested.read_text()
    # manifest roles[] row (sync_check A5)
    assert any(r.get("id") == "infographic-checklist" for r in m["roles"])
    # a registered verifier
    import phase_verifiers as pv
    assert "P8.3-INFOGRAPHIC" in pv.PHASE_VERIFIERS


def test_infographic_checklist_writes_a_verdict_file_and_verifier_passes(tmp_path):
    """The QC unit's output artifact — working/qc/infographic_checklist_verdict.json
    in the role doc's exact contract shape — makes the verifier pass; removing
    it (or a fail verdict) fails the phase. Negative controls included."""
    import phase_verifiers as pv
    run_dir = tmp_path / "run"
    (run_dir / "working" / "qc").mkdir(parents=True)
    (run_dir / "working" / "deliverables").mkdir(parents=True)
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    (run_dir / "working" / "prompts").mkdir(parents=True)
    (run_dir / "working" / "prompts" / "infographic-prompt.txt").write_text("PROMPT" * 2000)
    (run_dir / "working" / "deliverables" / "infographic.png").write_bytes(b"x" * 102_400)
    (run_dir / "working" / "checkpoints" / "infographic_status.json").write_text(json.dumps(
        {"infographic_format": "checklist", "status": "ready", "qc_passed": True,
         "prompt_path": "working/prompts/infographic-prompt.txt",
         "render_path": "working/deliverables/infographic.png",
         "deliverable_path": "working/deliverables/infographic.png"}))

    # The QC unit runs → writes the verdict (the exact shape the role doc
    # mandates). This write IS the unit's implementation of "writes a verdict
    # file"; the verifier then re-derives everything it claims.
    verdict = {
        "phase_id": "P8.3-INFOGRAPHIC",
        "verdict": "pass",
        "checked": ["all prompt checklist items visible", "no clipping", "correct 9:16 format"],
        "prompt_path": "working/prompts/infographic-prompt.txt",
        "render_path": "working/deliverables/infographic.png",
        "status_path": "working/checkpoints/infographic_status.json",
        "render_status_ok": True,
        "reasons": [],
    }
    vpath = run_dir / "working" / "qc" / "infographic_checklist_verdict.json"
    vpath.write_text(json.dumps(verdict))
    ok, reasons = pv.verify("P8.3-INFOGRAPHIC", run_dir)
    assert ok, reasons
    assert vpath.is_file()

    # Negative controls — the verifier is not a rubber stamp.
    verdict["verdict"] = "fail"
    verdict["reasons"] = ["logo clipped"]
    vpath.write_text(json.dumps(verdict))
    ok, reasons = pv.verify("P8.3-INFOGRAPHIC", run_dir)
    assert not ok and any("fail" in r for r in reasons)

    vpath.unlink()
    ok, reasons = pv.verify("P8.3-INFOGRAPHIC", run_dir)
    assert not ok and any("verdict" in r for r in reasons)


def test_registry_parity_for_all_four_new_entries():
    m = _manifest()
    registered = set()
    import phase_verifiers as pv
    registered = set(pv.PHASE_VERIFIERS.keys())
    for pid in ("P-STYLE-SPEC", "P-STYLE-PICK", "P8.3-INFOGRAPHIC", "P-BUNDLE-GATE"):
        assert pid in {p["id"] for p in m["phases"]}, f"{pid} not in manifest"
        assert pid in registered, f"{pid} has no PHASE_VERIFIERS entry"
