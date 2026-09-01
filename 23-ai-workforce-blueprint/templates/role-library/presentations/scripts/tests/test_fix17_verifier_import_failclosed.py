"""FIX 17 proof — a phase_verifiers IMPORT failure aborts the run (fail-closed).

Spec (PRESENTATION-DEPT-FIX-SPEC.md, FIX 17):
    phases.py:485-487 — if phase_verifiers fails to import, the engine warns and
    SKIPS substance verification for every phase. FIX: a verifier import failure
    aborts the run (exit non-zero) instead of proceeding unverified.
    PROOF: simulate the import failure -> run aborts, does not mint attestations.

Ground truth pinned here (the code landed in 92dcd47a0 as
presentation_job/phases.py::VerifierImportError, raised out of Engine.run_phase):

  * run_phase() catches ImportError from `import phase_verifiers` and re-raises
    a named VerifierImportError (a RuntimeError) after recording the
    "phase.verifier_unavailable" event — the exception propagates OUT of
    run_phase (and out of run_phase_timed, which emits a crashed phase_exit
    telemetry row on its way up), so the caller's run loop never continues.
  * The done checkpoint below the verifier block — the attestation that mints
    attested_at/sha256/artifacts and reports "complete" to the client — is
    NEVER reached. state.json carries no status="done", no attested_at.
  * The known-good control: the same phase, same fixture, with phase_verifiers
    importable, DOES mint the done attestation. That proves the abort below is
    caused by the import failure alone and not by some other gate (intake gate,
    artifact presence, persona, board).

Flat file inside tests/, manages its own import path — matching every sibling
in this directory (test_engine_client_report.py, test_client_step_count.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine, VerifierImportError  # noqa: E402
from presentation_job.state import StateStore  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (same shapes as test_engine_client_report.py)
# ---------------------------------------------------------------------------
def _canonical_manifest() -> Path:
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = SCRIPTS
    for _ in range(12):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    raise FileNotFoundError(
        "PIPELINE-MANIFEST.json not found (looked in scripts/../sops/ and the "
        "universal-sops/presentation-slide-craft walk-up)")


def _manifest() -> Manifest:
    return Manifest(_canonical_manifest())


def _run_dir(tmp_path: Path) -> Path:
    """A scratch run_dir with the completed intake P8.1's AF-INTAKE-GATE demands."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "intake.json").write_text(
        json.dumps({"deck_type": "webinar", "creation_mode": "from_scratch"}))
    return rd


def _engine(tmp_path: Path) -> Engine:
    """A real Engine on the canonical manifest, dry_run so the P8.1 script
    executor exits EXIT_OK without invoking pdf_export.py — the test isolates
    exactly the verifier-import branch."""
    rd = _run_dir(tmp_path)
    manifest = _manifest()
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00", "manifest_path": str(manifest.path),
        "manifest_version": manifest.version, "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch", "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    return Engine(rd, manifest, store, state, dry_run=True)


def _phase(engine: Engine):
    ph = engine.manifest.phase_or_none("P8.1-PDF-EXPORT")
    assert ph is not None
    return ph


def _mint_artifact(engine: Engine) -> None:
    """Satisfy P8.1's produces_artifact glob AND its registered substance
    verifier (_verify_text_artifact("working/deliverables/*-FINAL.pdf", 51200))
    so the ONLY thing that can stop the phase is the verifier import."""
    out = engine.run_dir / "working" / "deliverables"
    out.mkdir(parents=True, exist_ok=True)
    (out / "DECK-FINAL.pdf").write_bytes(b"%PDF-1.4 fixture " + (b"x" * 60000))


def _block_verifier_import(monkeypatch) -> None:
    """Simulate phase_verifiers failing to import: a None module object in
    sys.modules makes every subsequent `import phase_verifiers` raise
    ImportError — the exact failure mode FIX 17 covers (a broken/partial
    install where the verifier module is unreadable)."""
    monkeypatch.setitem(sys.modules, "phase_verifiers", None)


def _phase_state(engine: Engine, pid: str) -> dict:
    for ps in engine.state["phases"]:
        if ps["id"] == pid:
            return ps
    return {}


# ---------------------------------------------------------------------------
# 1. THE PROOF — import failure aborts, no attestation minted
# ---------------------------------------------------------------------------
class TestVerifierImportFailureAborts:
    def test_run_phase_raises_verifier_import_error(self, tmp_path, monkeypatch):
        eng = _engine(tmp_path)
        _mint_artifact(eng)
        _block_verifier_import(monkeypatch)
        with pytest.raises(VerifierImportError) as ei:
            eng.run_phase(_phase(eng))
        assert "FIX 17" in str(ei.value)

    def test_verifier_import_error_is_runtime_error(self):
        # the run loop's crash handling keys off BaseException/RuntimeError
        # semantics; the named error must stay in that family.
        assert issubclass(VerifierImportError, RuntimeError)

    def test_no_done_attestation_minted(self, tmp_path, monkeypatch):
        eng = _engine(tmp_path)
        _mint_artifact(eng)
        _block_verifier_import(monkeypatch)
        with pytest.raises(VerifierImportError):
            eng.run_phase(_phase(eng))
        ps = _phase_state(eng, "P8.1-PDF-EXPORT")
        assert ps.get("status") != "done", (
            "FIX 17: a verifier import failure must never mint the done "
            "checkpoint (the attestation) — the phase was never substance-verified")
        assert not ps.get("attested_at"), (
            "attested_at is the attestation timestamp — it must be absent when "
            "the verifier never ran")
        assert not ps.get("sha256"), "no artifact sha256 ledger on an aborted phase"

    def test_persisted_state_has_no_attestation(self, tmp_path, monkeypatch):
        eng = _engine(tmp_path)
        _mint_artifact(eng)
        _block_verifier_import(monkeypatch)
        with pytest.raises(VerifierImportError):
            eng.run_phase(_phase(eng))
        saved = eng.store.load()
        saved_ps = next((p for p in saved.get("phases", [])
                         if p.get("id") == "P8.1-PDF-EXPORT"), None)
        assert saved_ps is not None
        assert saved_ps.get("status") != "done"
        assert not saved_ps.get("attested_at")

    def test_verifier_unavailable_event_recorded(self, tmp_path, monkeypatch):
        eng = _engine(tmp_path)
        _mint_artifact(eng)
        _block_verifier_import(monkeypatch)
        with pytest.raises(VerifierImportError):
            eng.run_phase(_phase(eng))
        events = [e.get("kind") for e in eng.state.get("events", [])]
        assert "phase.verifier_unavailable" in events

    def test_propagates_through_run_phase_timed(self, tmp_path, monkeypatch):
        # run_phase_timed is the run loop's entry: it must re-raise (aborting the
        # run) after recording the crashed phase_exit telemetry row.
        eng = _engine(tmp_path)
        _mint_artifact(eng)
        _block_verifier_import(monkeypatch)
        with pytest.raises(VerifierImportError):
            eng.run_phase_timed(_phase(eng))
        # telemetry lands in working/telemetry/stage-timings.jsonl (durable
        # source of truth), not in state.json — read the row back from there.
        tfile = eng.run_dir / "working" / "telemetry" / "stage-timings.jsonl"
        assert tfile.is_file(), "run_phase_timed must emit phase_exit telemetry"
        rows = [json.loads(line) for line in tfile.read_text().splitlines()
                if line.strip()]
        exits = [r for r in rows
                 if r.get("event") == "phase_exit" and r.get("phase_id") == "P8.1-PDF-EXPORT"]
        assert exits, "no phase_exit telemetry row for the aborted phase"
        assert exits[-1].get("status") == "crashed"
        assert exits[-1].get("error_class") == "VerifierImportError"


# ---------------------------------------------------------------------------
# 2. THE KNOWN-GOOD CONTROL — same fixture, verifier importable: attests.
#    (Negative-result contract: the abort above must be attributable to the
#    import failure alone, not to the intake gate, artifact presence, or any
#    other gate on this phase.)
# ---------------------------------------------------------------------------
class TestKnownGoodControl:
    def test_same_fixture_passes_and_attests_when_verifier_importable(
            self, tmp_path, monkeypatch):
        eng = _engine(tmp_path)
        _mint_artifact(eng)
        # guarantee the module is freshly importable for the control — never
        # a poisoned entry left over from the abort tests
        monkeypatch.delitem(sys.modules, "phase_verifiers", raising=False)
        import phase_verifiers  # noqa: F401 — must be importable on the control
        rc = eng.run_phase(_phase(eng))
        assert rc == 0, f"control run_phase must succeed, got rc={rc}"
        ps = _phase_state(eng, "P8.1-PDF-EXPORT")
        assert ps.get("status") == "done"
        assert ps.get("attested_at")
        assert ps.get("verifier_ok") is True