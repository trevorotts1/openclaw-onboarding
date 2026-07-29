"""U020 — test_upload_gate.py

Tests for gate_ghl_media_complete, the UPLOAD_GATE_WARN_ONLY staging in
_bundle_completeness, the _check_destinations plan-consistency check,
and the engine's _ghl_gate delegation. No network — every fixture is
files on disk. Never calls push_deck_media, which uploads.

Standard library plus pytest/tmp_path only."""

from __future__ import annotations

import json
import pathlib
import sys

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_media_library_json(base: pathlib.Path, media: dict) -> pathlib.Path:
    ck = base / "working" / "checkpoints"
    ck.mkdir(parents=True, exist_ok=True)
    p = ck / "media_library.json"
    p.write_text(json.dumps(media))
    return p


def _mk_intake_json(base: pathlib.Path, has_ghl: bool | None = None) -> None:
    cp = base / "working" / "copy"
    cp.mkdir(parents=True, exist_ok=True)
    intake = {}
    if has_ghl is not None:
        intake["has_ghl"] = has_ghl
    (cp / "intake.json").write_text(json.dumps(intake))


def _mk_process_manifest(base: pathlib.Path, owner_skip: dict | None) -> None:
    ck = base / "working" / "checkpoints"
    ck.mkdir(parents=True, exist_ok=True)
    pm = {}
    if owner_skip is not None:
        pm["owner_skip_approval"] = owner_skip
    (ck / "process_manifest.json").write_text(json.dumps(pm))


def _mk_complete_run_dir(base: pathlib.Path) -> None:
    """Assemble a run dir with client package, teleprompter, delivery_plan (no ghl)."""
    pkg = base / "delivery" / "demo-deck-FINAL"
    pkg.mkdir(parents=True, exist_ok=True)
    for nm in ("demo-deck-FINAL.pptx", "demo-deck-FINAL.pdf", "PRESENTER-GUIDE.pdf",
               "PRESENTERS-SPEECH.pdf", "PRESENTER-AUDIO.mp3"):
        (pkg / nm).write_bytes(b"x" * 4096)
    tp = base / "working" / "teleprompter"
    tp.mkdir(parents=True, exist_ok=True)
    (tp / "teleprompter.html").write_text("<html></html>")
    ck = base / "working" / "checkpoints"
    ck.mkdir(parents=True, exist_ok=True)
    (ck / "delivery_plan.json").write_text(json.dumps({
        "destinations": [{"type": "mac_downloads",
                          "verify_anchor": str(pkg / "demo-deck-FINAL.pptx")}]
    }))


# ---------------------------------------------------------------------------
# Test 1 — gate_ghl_media_complete on the producer's own fixture shape
# ---------------------------------------------------------------------------


def test_gate_ghl_media_complete_complete_ledger(tmp_path):
    """Complete fixture — folder, two slides, pptx — returns (True, [])."""
    import ghl_media_push as gmp
    base = tmp_path / "complete"
    _mk_intake_json(base, has_ghl=True)
    _mk_media_library_json(base, {
        "ghl_folder_id": "folder-abc",
        "slides": [
            {"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
            {"slide_number": 2, "ghl_media_id": "m2", "ghl_upload_status": "complete"},
        ],
        "pptx_ghl_media_id": "pptx-def",
    })
    ok, reasons = gmp.gate_ghl_media_complete(base)
    assert ok is True
    assert reasons == []


def test_gate_ghl_media_complete_missing_pptx(tmp_path):
    """pptx_ghl_media_id removed -> False, reason names pptx_ghl_media_id."""
    import ghl_media_push as gmp
    base = tmp_path / "nopptx"
    _mk_intake_json(base, has_ghl=True)
    _mk_media_library_json(base, {
        "ghl_folder_id": "folder-abc",
        "slides": [
            {"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
        ],
    })
    ok, reasons = gmp.gate_ghl_media_complete(base)
    assert ok is False
    assert any("pptx_ghl_media_id" in r for r in reasons)


def test_gate_ghl_media_complete_pending_slide(tmp_path):
    """One slide at ghl_upload_status:'pending' -> False — per-asset proven."""
    import ghl_media_push as gmp
    base = tmp_path / "pending"
    _mk_intake_json(base, has_ghl=True)
    _mk_media_library_json(base, {
        "ghl_folder_id": "folder-abc",
        "slides": [
            {"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
            {"slide_number": 2, "ghl_media_id": "", "ghl_upload_status": "pending"},
        ],
        "pptx_ghl_media_id": "pptx-def",
    })
    ok, reasons = gmp.gate_ghl_media_complete(base)
    assert ok is False


def test_gate_ghl_media_complete_null_folder(tmp_path):
    """ghl_folder_id: None -> False, reason names ghl_folder_id."""
    import ghl_media_push as gmp
    base = tmp_path / "nofolder"
    _mk_intake_json(base, has_ghl=True)
    _mk_media_library_json(base, {
        "slides": [
            {"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
        ],
        "pptx_ghl_media_id": "pptx-def",
    })
    ok, reasons = gmp.gate_ghl_media_complete(base)
    assert ok is False
    assert any("ghl_folder_id" in r for r in reasons)


def test_agent_cannot_opt_out(tmp_path):
    """has_ghl:false without owner token -> False — agent cannot self-opt-out."""
    import ghl_media_push as gmp
    base = tmp_path / "agentopt"
    _mk_intake_json(base, has_ghl=False)
    ok, reasons = gmp.gate_ghl_media_complete(base)
    assert ok is False
    assert any("has_ghl:false" in r for r in reasons)


def test_valid_owner_skip_authorizes(tmp_path):
    """Valid owner_skip_approval -> (True, [])."""
    import ghl_media_push as gmp
    base = tmp_path / "ownerok"
    _mk_intake_json(base, has_ghl=False)
    _mk_process_manifest(base, {
        "owner_approved": True,
        "approved_by": "operator",
        "reason": "client has no GHL account",
        "gate": "ghl_upload",
    })
    ok, reasons = gmp.gate_ghl_media_complete(base)
    assert ok is True
    assert reasons == []


def test_owner_skip_missing_reason_fails(tmp_path):
    """owner_skip missing reason -> does NOT authorize."""
    import ghl_media_push as gmp
    base = tmp_path / "noreason"
    _mk_intake_json(base, has_ghl=False)
    _mk_process_manifest(base, {
        "owner_approved": True,
        "approved_by": "operator",
        "gate": "ghl_upload",
    })
    ok, _ = gmp.gate_ghl_media_complete(base)
    assert ok is False


def test_owner_skip_missing_approved_by_fails(tmp_path):
    """owner_skip missing approved_by -> does NOT authorize."""
    import ghl_media_push as gmp
    base = tmp_path / "noapprover"
    _mk_intake_json(base, has_ghl=False)
    _mk_process_manifest(base, {
        "owner_approved": True,
        "reason": "client has no account",
        "gate": "ghl_upload",
    })
    ok, _ = gmp.gate_ghl_media_complete(base)
    assert ok is False


def test_owner_skip_not_approved_fails(tmp_path):
    """owner_skip with owner_approved:false -> does NOT authorize."""
    import ghl_media_push as gmp
    base = tmp_path / "notapproved"
    _mk_intake_json(base, has_ghl=False)
    _mk_process_manifest(base, {
        "owner_approved": False,
        "approved_by": "operator",
        "reason": "client has no account",
        "gate": "ghl_upload",
    })
    ok, _ = gmp.gate_ghl_media_complete(base)
    assert ok is False


# ---------------------------------------------------------------------------
# Tests for the UPLOAD_GATE_WARN_ONLY staging in delivery_gate._bundle_completeness
# ---------------------------------------------------------------------------


def test_bundle_completeness_silent_plan_stage3_rejects(tmp_path):
    """A run dir with silent plan + NO media_library.json reports upload
    finding at stage 3 (warn=False). This is the C2 defect fixed."""
    import delivery_gate as dg
    base = tmp_path / "silent_s3"
    _mk_complete_run_dir(base)
    dg.UPLOAD_GATE_WARN_ONLY = False
    reasons = dg._bundle_completeness(base, verify_destinations=True)
    upload_related = [r for r in reasons
                      if "upload" in r.lower() or "AF-DELIVERY-COMPLETE" in r]
    assert len(upload_related) >= 1, f"Expected upload finding at stage 3, got reasons={reasons}"


def test_bundle_completeness_silent_plan_stage1_passes(tmp_path):
    """Same fixture under stage 1 (warn=True) passes — findings go to count,
    NOT to reasons. The gate runs but does not block delivery."""
    import delivery_gate as dg
    base = tmp_path / "silent_s1"
    _mk_complete_run_dir(base)
    dg.UPLOAD_GATE_WARN_ONLY = True
    reasons = dg._bundle_completeness(base, verify_destinations=True)
    upload_related = [r for r in reasons
                      if "upload" in r.lower() or "AF-DELIVERY-COMPLETE" in r]
    assert len(upload_related) == 0, (
        f"Stage 1 should not add upload findings to reasons, got: {upload_related}")


def test_bundle_completeness_pre_transport_no_upload_finding(tmp_path):
    """verify_destinations=False reports ZERO upload findings — the deadlock guard."""
    import delivery_gate as dg
    base = tmp_path / "pre_transport"
    _mk_complete_run_dir(base)
    for warn in (True, False):
        dg.UPLOAD_GATE_WARN_ONLY = warn
        reasons = dg._bundle_completeness(base, verify_destinations=False)
        upload_related = [r for r in reasons
                          if "upload" in r.lower() or "AF-DELIVERY-COMPLETE" in r]
        assert len(upload_related) == 0, (
            f"Pre-transport with UPLOAD_GATE_WARN_ONLY={warn} should have zero "
            f"upload findings, got: {upload_related}")


# ---------------------------------------------------------------------------
# _check_destinations plan-consistency check — must still fire (not deleted)
# ---------------------------------------------------------------------------


def test_check_destinations_ghl_plan_consistency_still_fires(tmp_path):
    """A plan that declares a ghl destination with no pptx_ghl_media_id must still
    produce the AF-DELIVER/GHL plan-consistency reason."""
    import delivery_gate as dg
    base = tmp_path / "declared"
    _mk_complete_run_dir(base)
    ck = base / "working" / "checkpoints"
    (ck / "delivery_plan.json").write_text(json.dumps({
        "destinations": [
            {"type": "mac_downloads",
             "verify_anchor": str(base / "delivery" / "demo-deck-FINAL" / "demo-deck-FINAL.pptx")},
            {"type": "ghl"},
        ]
    }))
    plan = json.loads((ck / "delivery_plan.json").read_text())
    reasons = dg._check_destinations(base, plan)
    ghl_reasons = [r for r in reasons if "GHL" in r or "ghl" in r]
    assert len(ghl_reasons) >= 1, f"Plan-consistency check should fire, got: {ghl_reasons}"


# ---------------------------------------------------------------------------
# Circular import proof — both import orders must succeed
# ---------------------------------------------------------------------------


def test_import_order_A_delivery_gate_first():
    """import delivery_gate then ghl_media_push — both must resolve."""
    mods = [m for m in sys.modules
            if m.startswith(("delivery_gate", "ghl_media_push", "ghl_media"))]
    for m in mods:
        del sys.modules[m]
    import delivery_gate as dg
    import ghl_media_push as gmp
    assert hasattr(dg, '_bundle_completeness')
    assert hasattr(gmp, 'gate_ghl_media_complete')


def test_import_order_B_ghl_media_push_first():
    """import ghl_media_push then delivery_gate — both must resolve."""
    mods = [m for m in sys.modules
            if m.startswith(("delivery_gate", "ghl_media_push", "ghl_media"))]
    for m in mods:
        del sys.modules[m]
    import ghl_media_push as gmp
    import delivery_gate as dg
    assert hasattr(dg, '_bundle_completeness')
    assert hasattr(gmp, 'gate_ghl_media_complete')


# ---------------------------------------------------------------------------
# Fail-closed on exception — a raising gate is a rejection
# ---------------------------------------------------------------------------


def test_raising_gate_is_rejection(monkeypatch, tmp_path):
    """gate_ghl_media_complete that raises produces fail-closed rejection."""
    import delivery_gate as dg
    base = tmp_path / "raising"
    _mk_complete_run_dir(base)
    dg.UPLOAD_GATE_WARN_ONLY = False

    def boom(run_dir, *args, **kwargs):
        raise RuntimeError("simulated ledger corruption")

    import ghl_media_push
    monkeypatch.setattr(ghl_media_push, "gate_ghl_media_complete", boom)
    reasons = dg._bundle_completeness(base, verify_destinations=True)
    fail_closed = [r for r in reasons if "fail-closed" in r.lower()]
    assert len(fail_closed) >= 1, (
        f"Raising gate must produce fail-closed reason, got: {reasons}")


# ---------------------------------------------------------------------------
# Waivers.json end-to-end — client waiver for ghl_upload
# ---------------------------------------------------------------------------


def test_waiver_ghl_upload_valid_quote_passes(tmp_path):
    """waivers.json naming rule:ghl_upload with valid client quote validates."""
    from presentation_job.waivers import validate_waiver
    base = tmp_path / "waiver_ok"
    client_words = "I do not want the GoHighLevel upload, skip it entirely"
    # Use intake_field path since TRANSCRIPT_WAIVERS_ACCEPTED=False per U013 step 6
    cp = base / "working" / "copy"
    cp.mkdir(parents=True, exist_ok=True)
    (cp / "intake.json").write_text(json.dumps({"has_ghl": True, "skip_ghl": client_words}))
    waiver = {
        "rule": "ghl_upload",
        "source": "intake_field",
        "client_request_quote": client_words,
        "captured_at": "2026-07-27T12:00:00Z",
        "intake_field": "skip_ghl",
    }
    validate_waiver(waiver, base)


def test_waiver_ghl_upload_short_quote_fails(tmp_path):
    """waivers.json naming ghl_upload with <3 char quote raises WaiverError."""
    from presentation_job.waivers import WaiverError, validate_waiver
    base = tmp_path / "waiver_short"
    _mk_intake_json(base, has_ghl=True)
    waiver = {
        "rule": "ghl_upload",
        "source": "intake_field",
        "client_request_quote": "ok",
        "captured_at": "2026-07-27T12:00:00Z",
        "intake_field": "skip_ghl",
    }
    with pytest.raises(WaiverError, match="client_request_quote"):
        validate_waiver(waiver, base)


# ---------------------------------------------------------------------------
# No phantom key 'media_ids' in changed files
# ---------------------------------------------------------------------------


def test_no_media_ids_phantom_key_in_delivery_gate():
    """delivery_gate.py has no literal 'media_ids' or 'folder_id' string constant."""
    import ast
    p = pathlib.Path(__file__).resolve().parent.parent / "delivery_gate.py"
    t = ast.parse(p.read_text())
    hits = [n.lineno for n in ast.walk(t)
            if isinstance(n, ast.Constant) and n.value in ("media_ids", "folder_id")]
    assert hits == [], f"Phantom key literals at lines: {hits}"


def test_no_media_ids_phantom_key_in_gates():
    """presentation_job/gates.py has no literal 'media_ids' or 'folder_id'."""
    import ast
    p = pathlib.Path(__file__).resolve().parent.parent / "presentation_job" / "gates.py"
    if not p.exists():
        pytest.skip("presentation_job/gates.py not present")
    t = ast.parse(p.read_text())
    hits = [n.lineno for n in ast.walk(t)
            if isinstance(n, ast.Constant) and n.value in ("media_ids", "folder_id")]
    assert hits == [], f"Phantom key literals at lines: {hits}"
