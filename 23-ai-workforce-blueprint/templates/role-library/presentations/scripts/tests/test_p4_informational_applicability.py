import json
from pathlib import Path

import pitch_engines_check as pitch
from presentation_job import dispatcher
import phase_verifiers


def _run(tmp_path: Path, intake: dict):
    copy = tmp_path / "working" / "copy"
    copy.mkdir(parents=True, exist_ok=True)
    (copy / "intake.json").write_text(json.dumps(intake))
    (copy / "slides_copy.md").write_text("SLIDE 1\n[ARC:HOOK] An informational walkthrough.\n")
    return pitch.run(tmp_path, "1Q")


def test_explicit_informational_non_pitch_skips_commercial_requirements(tmp_path):
    assert _run(tmp_path, {"deck_type": "from_scratch", "pitch_included": False}) == []


def test_selected_signature_still_enforces_pitch_requirements(tmp_path):
    codes = {x["code"] for x in _run(tmp_path, {"deck_type": "signature_presentation"})}
    assert "AF-NO-BRANDED-METHOD" in codes
    assert "AF-NO-TIME-TO-RESULT" in codes


def test_missing_or_conflicting_selection_fails_closed(tmp_path):
    missing = _run(tmp_path, {"deck_type": "from_scratch"})
    assert missing[0]["code"] == "AF-PITCH-APPLICABILITY-UNSET"
    conflict = _run(tmp_path, {"deck_type": "signature_presentation", "pitch_included": False})
    assert conflict[0]["code"] == "AF-PITCH-APPLICABILITY-CONFLICT"


def test_signature_claim_contract_cannot_instruct_mutation():
    text = dispatcher.ARTIFACT_CONTRACTS["P-SP-CLAIM"]
    assert "Never change intake.json" in text
    assert "only if" in text


def test_sp_claim_must_mirror_selected_non_signature_type(tmp_path):
    copy = tmp_path / "working" / "copy"
    copy.mkdir(parents=True)
    (copy / "intake.json").write_text(json.dumps({"deck_type": "from_scratch"}))
    (copy / "sp_claims.json").write_text(json.dumps({"deck_type": "signature_presentation", "claimed": True}))
    ok, notes = phase_verifiers._sp_claim_matches_intake(tmp_path)
    assert not ok
    assert notes[0].startswith("AF-SP-CLAIM-INTAKE-MISMATCH")

def test_sp_claim_preserves_signature_enforcement(tmp_path):
    copy = tmp_path / "working" / "copy"
    copy.mkdir(parents=True)
    (copy / "intake.json").write_text(json.dumps({"deck_type": "signature_presentation"}))
    (copy / "sp_claims.json").write_text(json.dumps({"deck_type": "signature_presentation", "claimed": True}))
    assert phase_verifiers._sp_claim_matches_intake(tmp_path) == (True, [])


def _signature_conflict_run(tmp_path: Path) -> Path:
    copy = tmp_path / "working" / "copy"
    copy.mkdir(parents=True)
    (copy / "intake.json").write_text(json.dumps({
        "deck_type": "signature_presentation", "pitch_included": False,
    }))
    (copy / "slides_copy.md").write_text("Informational copy " * 8)
    return tmp_path


def test_canonical_copy_wrappers_do_not_skip_signature_pitch_conflict(tmp_path):
    """Every wrapper consumes the shared resolver before deciding to skip."""
    import build_deck
    import run_signature_deck

    run_dir = _signature_conflict_run(tmp_path)
    assert "AF-PITCH-APPLICABILITY-CONFLICT" in build_deck.check_pitch_engines(run_dir)

    ok, verifier_notes = phase_verifiers._verify_copy(run_dir)
    assert not ok
    assert any("AF-PITCH-APPLICABILITY-CONFLICT" in note for note in verifier_notes)

    measured = run_signature_deck._measure_copy_qc(run_dir)
    assert not measured["pass"]
    assert any(p["code"] == "AF-PITCH-APPLICABILITY-CONFLICT"
               for p in measured["problems"])

    deterministic = build_deck.check_copy_qc_deterministic(run_dir)
    assert not deterministic["pass"]
    assert any(d["code"] == "AF-PITCH-APPLICABILITY-CONFLICT"
               for d in deterministic["deficiencies"])
