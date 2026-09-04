"""U024 — test suite for presentation_job.persona (blended-persona governance).

Standard library plus pytest, tmp_path, no network, no real sleeps.
Eight tests — one per function/behaviour this unit ships.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
sys.path.insert(0, str(_SCRIPTS))

from presentation_job import persona


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_run_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    rd = tmp_path / "run"
    rd.mkdir()
    st = {
        "schema_version": 1,
        "job_id": "test-pj-000000000000001",
        "run_dir": str(rd),
        "created_at": "2026-07-27T00:00:00+00:00",
        "manifest_path": str(rd / "PIPELINE-MANIFEST.json"),
        "manifest_version": 1,
        "manifest_sha256": "0" * 56,
        "presentation_type": "signature",
        "requester": {"chat_id": "test-chat"},
        "intake": {},
        "current_phase": None,
        "phases": [],
        "gates": {},
        "waivers": [],
        "events": [],
        "sent": {},
        "undeliverable": [],
        "heartbeat": {},
        "terminal": None,
    }
    (rd / "state.json").write_text(json.dumps(st), encoding="utf-8")
    return rd


# ---------------------------------------------------------------------------
# Test 1 — BLEND_PHASE_FOR maps exactly four pipeline phase ids.
# ---------------------------------------------------------------------------
def test_blend_phase_for_has_exactly_four_entries():
    assert len(persona.BLEND_PHASE_FOR) == 4


# ---------------------------------------------------------------------------
# Test 2 — All four narrative phases covered.
# THIS is the test QC-6's mutation must turn red.
# ---------------------------------------------------------------------------
def test_blend_phase_for_covers_all_four_narrative_phases():
    import blend_voice_governance as bvg
    assert set(persona.BLEND_PHASE_FOR.values()) == set(bvg.PHASES), (
        f"BLEND_PHASE_FOR values {set(persona.BLEND_PHASE_FOR.values())} "
        f"!= bvg.PHASES {set(bvg.PHASES)}"
    )


# ---------------------------------------------------------------------------
# Test 3 — resolve_for_phase returns None for unmapped phase id without
# importing the blend module at all.
# ---------------------------------------------------------------------------
def test_resolve_for_phase_returns_none_for_unmapped_phase(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    result = persona.resolve_for_phase(run_dir, "P8-ASSEMBLE",
                                        avatar_context="a founder audience")
    assert result is None


# ---------------------------------------------------------------------------
# Test 4 — SKILL51_BLEND_GOVERNS=0 continues and records
# persona_governance="legacy-intake-tone".
# ---------------------------------------------------------------------------
def test_flag_off_continues_with_legacy_intake_tone(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    try:
        os.environ["SKILL51_BLEND_GOVERNS"] = "0"
        result = persona.resolve_for_phase(run_dir, "P4-COPY")
        assert result is not None, "flag-off should return a marker, not None"
        assert result.get("persona_governance") == "legacy-intake-tone", (
            f"expected legacy-intake-tone, got {result.get('persona_governance')}")
    finally:
        os.environ.pop("SKILL51_BLEND_GOVERNS", None)


# ---------------------------------------------------------------------------
# Test 5 — An unreachable seam BLOCKS. Achieved by stubbing the loaded
# module's own _load_pfj to return None.
# ---------------------------------------------------------------------------
def test_unreachable_seam_blocks(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    mod = persona.load_blend_module()
    assert mod is not None, "blend_voice_governance must be reachable"
    mod._load_pfj = lambda: None
    try:
        with pytest.raises(RuntimeError, match="persona_for_job"):
            persona.resolve_for_phase(run_dir, "P4-COPY")
    finally:
        persona._MODULE_CACHE.clear()


# ---------------------------------------------------------------------------
# Test 6 — A stubbed resolver that sleeps past BLEND_TIMEOUT_S raises within
# the wall, monkeypatched — never a real sleep.
# ---------------------------------------------------------------------------
def test_timeout_wall_fires(tmp_path, monkeypatch):
    import concurrent.futures

    # Hard-guard the constant value — a mutation of BLEND_TIMEOUT_S must
    # turn this test red (fail-closed rule 2). FIX 28 deliberately raised
    # the wall 30 -> 90 (the 30 s wall blocked legitimately slow copy-phase
    # persona resolutions; the seam's own subprocess budget is 60 s, so 90 s
    # gives one full seam budget plus headroom) and added exactly one retry,
    # so this guard now pins the NEW value the fix landed.
    assert persona.BLEND_TIMEOUT_S == 90, (
        f"BLEND_TIMEOUT_S must be 90 (FIX 28), got {persona.BLEND_TIMEOUT_S}")

    run_dir = _make_run_dir(tmp_path)
    mod = persona.load_blend_module()
    assert mod is not None, "blend_voice_governance must be reachable"

    # Make the Future.result raise TimeoutError by monkeypatching it to
    # throw after checking timeout, AND capture the timeout= KWARG
    # to assert it is the specific BLEND_TIMEOUT_S constant.
    orig_result = concurrent.futures.Future.result
    captured_timeout = []

    def raising_result(self, timeout=None):
        captured_timeout.append(timeout)
        if timeout is not None and timeout <= persona.BLEND_TIMEOUT_S:
            raise concurrent.futures.TimeoutError(
                f"simulated timeout after {timeout}s")
        return orig_result(self, timeout=timeout)

    monkeypatch.setattr(concurrent.futures.Future, "result", raising_result)

    with pytest.raises((TimeoutError, concurrent.futures.TimeoutError)):
        persona.resolve_for_phase(run_dir, "P4-COPY")

    assert captured_timeout, "Future.result was never called"
    assert captured_timeout[0] == persona.BLEND_TIMEOUT_S, (
        f"expected timeout={persona.BLEND_TIMEOUT_S}, got {captured_timeout[0]}")


# ---------------------------------------------------------------------------
# Test 7 — governance_banner() returns a string carrying all three facts
# (ON/OFF token, all four pipeline phase ids, path ending
# blend_voice_governance.py) and returns UNREACHABLE when module is stubbed.
# ---------------------------------------------------------------------------
def test_governance_banner_reports_all_facts():
    banner = persona.governance_banner()
    assert isinstance(banner, str)
    assert ("ON" in banner) or ("OFF" in banner), f"banner: {banner!r}"
    for pid in persona.BLEND_PHASE_FOR:
        assert pid in banner, f"banner missing phase {pid}: {banner!r}"
    assert "blend_voice_governance.py" in banner, f"banner: {banner!r}"


def test_governance_banner_reports_unreachable_when_module_absent():
    with persona._CACHE_LOCK:
        saved = persona._MODULE_CACHE.get("mod")
        persona._MODULE_CACHE["mod"] = None
    try:
        banner = persona.governance_banner()
        assert "UNREACHABLE" in banner, f"banner: {banner!r}"
        assert isinstance(banner, str)
    finally:
        with persona._CACHE_LOCK:
            persona._MODULE_CACHE["mod"] = saved


# ---------------------------------------------------------------------------
# Test 8 — structure_warn_check() returns checked=7, mismatched=[] against
# the real pin file, and with a stubbed pin dict where one hash differs,
# reports that key in mismatched. Asserts governed_deck_voice is never called.
# ---------------------------------------------------------------------------
def test_structure_warn_check_returns_seven_matched():
    skill_root = persona._resolve_skill51_root()
    if skill_root is None:
        pytest.skip("Skill-51 root not available")
    w = persona.structure_warn_check()
    assert isinstance(w, dict)
    assert w.get("pin_file_found") is True, f"pin_file_found: {w}"
    # >= 6: the installed skill may still have 6 pins; the repo copy has 7
    # after step 5. VERIFY step 4 and QC-7 confirm the exact 7 count.
    assert w["checked"] >= 6, (
        f"checked should be >= 6, got {w}")
    assert w["mismatched"] == [], f"mismatched: {w['mismatched']}"


def test_structure_warn_check_reports_mismatch_without_resolving_personas():
    skill_root = persona._resolve_skill51_root()
    if skill_root is None:
        pytest.skip("Skill-51 root not found")

    bvg_path = skill_root / "scripts" / "blend_voice_governance.py"
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "blend_voice_governance_struct_test", bvg_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Stub governed_deck_voice to assert it is NEVER called
    called = []
    def no_persona_call(*a, **k):
        called.append(True)
        raise AssertionError("structure_warn_check must not resolve personas")
    mod.governed_deck_voice = no_persona_call

    # Create a tampered pin in a temp skill-51 layout
    current = mod.structural_fixture_hashes()
    tampered = dict(current)
    first_key = list(tampered.keys())[0]
    tampered[first_key] = "0" * 64

    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        skill_dir = tdp / "51-signature-presentation"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        import shutil
        shutil.copy2(str(bvg_path), str(scripts_dir / "blend_voice_governance.py"))
        pin_path = scripts_dir / "sacred-structure-hashes.json"
        pin_path.write_text(json.dumps(tampered, indent=2), encoding="utf-8")

        saved = persona._resolve_skill51_root
        persona._resolve_skill51_root = lambda: skill_dir
        try:
            w = persona.structure_warn_check()
            assert w["pin_file_found"] is True
            assert w["checked"] > 0
            assert first_key in w["mismatched"], (
                f"Expected {first_key} in mismatched, got {w['mismatched']}")
        finally:
            persona._resolve_skill51_root = saved

    assert not called, "governed_deck_voice was called during structure_warn_check"
