"""Tests for AF-INTAKE-GATE (Ticket 6, presentation department fix campaign,
2026-08-27) -- Engine._intake_gate_applies / Engine._check_intake_gate in
presentation_job/phases.py.

THE DEFECT THIS FILE PROVES FIXED:

Nothing in the phase-execution loop (Engine.run_phase) checked that
working/copy/intake.json existed before dispatching a content-authoring phase
(P0B-PRIORITY's priority-shift spec, P3-ARC's arc allocation, P4-COPY's slide
copy, and everything after them). A run that reached one of those phases
before intake ever completed would author content with no real client data
behind it -- garbage in, garbage delivered, with no mechanical gate catching
it before the fact (only after-the-fact substance verifiers, which check the
CONTENT of what a phase produced, never whether an upstream prerequisite
existed at all).

This suite proves: (1) a content-authoring phase blocks with the
AF-INTAKE-GATE reason when intake.json is absent, unreadable, or empty;
(2) the SAME phase proceeds past the gate once a valid intake.json exists;
(3) the intake-establishing phases themselves (P0A-INTAKE / P-CONVERTER --
P-SP-CLAIM left this set in manifest v67, see the note above test 4) and the
phases the manifest runs ahead of them (P-0.5-RESEARCH) are exempt -- the gate
must never deadlock the pipeline against its own intake step; (4) a manifest that declares no intake-producing phase at all
(the narrow single-phase fixtures every other test file in this directory
already relies on) is untouched -- the gate is a no-op there, never a false
block.

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory (test_f16_agent_phase_wait_race.py, test_gates.py,
etc.).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import StateStore, EXIT_GATE_BLOCKED  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _canonical_manifest() -> Path:
    """Same resolution order as test_f16_agent_phase_wait_race.py's
    _canonical_manifest() / test_engine_client_report.py's own copy."""
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
    raise FileNotFoundError("PIPELINE-MANIFEST.json not found")


def _manifest() -> Manifest:
    return Manifest(_canonical_manifest())


def _engine(tmp_path, write_intake: bool = False, manifest: Manifest = None) -> Engine:
    """Mirrors test_f16_agent_phase_wait_race.py's _engine(), except intake.json
    is written only when the test asks for it -- the whole point here is
    exercising the gate on a run dir that has NOT completed intake yet."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    if write_intake:
        (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
            {"deck_type": "webinar", "creation_mode": "from_scratch"}))
    manifest = manifest or _manifest()
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00", "manifest_path": str(manifest.path),
        "manifest_version": manifest.version, "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch", "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    return Engine(rd, manifest, store, state, dry_run=False)


# ---------------------------------------------------------------------------
# 1. Core defect proof: a real content-authoring phase must not even start
#    (never mind produce anything) while intake.json is missing.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("phase_id", ["P0B-PRIORITY", "P3-ARC", "P4-COPY"])
def test_content_phase_blocks_when_intake_missing(tmp_path, phase_id):
    eng = _engine(tmp_path, write_intake=False)
    phase = eng.manifest.phase(phase_id)

    rc = eng.run_phase(phase)

    assert rc == EXIT_GATE_BLOCKED
    reason = (eng.state.get("blocked") or {}).get("reason") or ""
    assert "AF-INTAKE-GATE" in reason, f"expected the AF-INTAKE-GATE reason, got: {reason!r}"
    assert "intake.json missing" in reason
    assert eng.state.get("blocked", {}).get("phase") == phase_id


# ---------------------------------------------------------------------------
# 2. The same phase must clear the gate (proceed past _check_intake_gate)
#    once a valid intake.json exists -- proven at the unit level so this test
#    is not coupled to persona/agent-executor mechanics.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("phase_id", ["P0B-PRIORITY", "P3-ARC", "P4-COPY"])
def test_content_phase_gate_clears_with_valid_intake(tmp_path, phase_id):
    eng = _engine(tmp_path, write_intake=True)
    phase = eng.manifest.phase(phase_id)

    assert eng._check_intake_gate(phase) is None, (
        "a valid intake.json on disk must let the gate pass (return None)")
    assert not eng.state.get("blocked"), "the gate must not have recorded a block"


# ---------------------------------------------------------------------------
# 3. Unreadable / invalid JSON and an empty object are treated the same as
#    "missing" -- a syntactically-present but useless file must not satisfy
#    the gate.
# ---------------------------------------------------------------------------
def test_content_phase_blocks_on_invalid_json(tmp_path):
    eng = _engine(tmp_path, write_intake=False)
    (Path(eng.run_dir) / "working" / "copy" / "intake.json").write_text("{not valid json")
    phase = eng.manifest.phase("P4-COPY")

    rc = eng.run_phase(phase)

    assert rc == EXIT_GATE_BLOCKED
    reason = (eng.state.get("blocked") or {}).get("reason") or ""
    assert "AF-INTAKE-GATE" in reason
    assert "not valid JSON" in reason


def test_content_phase_blocks_on_empty_intake(tmp_path):
    eng = _engine(tmp_path, write_intake=False)
    (Path(eng.run_dir) / "working" / "copy" / "intake.json").write_text("{}")
    phase = eng.manifest.phase("P4-COPY")

    rc = eng.run_phase(phase)

    assert rc == EXIT_GATE_BLOCKED
    reason = (eng.state.get("blocked") or {}).get("reason") or ""
    assert "AF-INTAKE-GATE" in reason
    assert "empty" in reason


# ---------------------------------------------------------------------------
# 4. No-deadlock proof: the phases that CREATE intake.json (and the phase the
#    manifest runs ahead of them) must be exempt, or the pipeline could never
#    get past its own first phase.
#
#    P-SP-CLAIM WAS IN THIS LIST AND IS NO LONGER (manifest v67). It was here
#    because it DECLARED working/copy/intake.json as its produces_artifact --
#    but that declaration was the same-artifact collision repaired in v67:
#    build_deck._chk_sp_claim only READS intake.json (it is the routing/claim
#    GATE), and dispatcher.ARTIFACT_TARGET_OVERRIDE already redirected the
#    phase to its real output, working/copy/sp_claims.json.
#
#    The collision is exactly what created the deadlock this exemption guarded
#    against: because P-SP-CLAIM both produced and consumed intake.json,
#    execution_plan.build_edges rule 2 discarded its ordering edge and it
#    level-scheduled into WAVE 1, alongside the very phase that writes the file
#    it reads. With the collision gone there is a real P0A-INTAKE ->
#    P-SP-CLAIM edge and the phase schedules into WAVE 2, so intake.json always
#    exists by the time it runs -- and test 5 below, which derives the exempt
#    ceiling FROM THE MANIFEST rather than hardcoding it, now requires this
#    phase to be gated (order 0.14 > ceiling 0.1). Gating a phase that consumes
#    intake.json and runs after its producer is correct, not a false block.
#
#    The two assertions cannot both hold; the self-deriving one wins.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("phase_id", ["P0A-INTAKE", "P-CONVERTER", "P-0.5-RESEARCH"])
def test_pre_intake_phases_are_exempt(tmp_path, phase_id):
    eng = _engine(tmp_path, write_intake=False)
    phase = eng.manifest.phase(phase_id)

    assert eng._check_intake_gate(phase) is None, (
        f"{phase_id} must be exempt from the intake gate -- gating it would "
        "deadlock the pipeline against its own intake step")
    assert eng._intake_gate_applies(phase) is False


# ---------------------------------------------------------------------------
# 5. Every phase past the exempt cluster IS gated -- not just the three
#    spot-checked above. Proves the gate covers "anything downstream", not a
#    hand-picked allowlist.
# ---------------------------------------------------------------------------
def test_every_phase_after_intake_cluster_is_gated():
    manifest = _manifest()
    exempt_ceiling = max(
        p.order for p in manifest.phases if "working/copy/intake.json" in p.produces_artifact)
    downstream = [p for p in manifest.phases if p.order > exempt_ceiling]
    assert downstream, "sanity: the canonical manifest must have phases after the intake cluster"

    import tempfile
    from presentation_job.state import StateStore as _SS
    rd = Path(tempfile.mkdtemp()) / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    store = _SS(rd)
    state = {"schema_version": 1, "job_id": "t", "run_dir": str(rd), "phases": [],
             "events": [], "sent": {}, "requester": {"chat_id": "tc"}, "heartbeat": {}}
    eng = Engine(rd, manifest, store, state, dry_run=True)
    for phase in downstream:
        assert eng._intake_gate_applies(phase) is True, (
            f"{phase.id} (order {phase.order}) is downstream of the intake cluster "
            f"(ceiling {exempt_ceiling}) and must be gated")


# ---------------------------------------------------------------------------
# 6. A manifest that declares no intake-producing phase at all (the shape
#    every narrow synthetic-manifest test elsewhere in this directory uses)
#    must be completely untouched by this gate.
# ---------------------------------------------------------------------------
def test_gate_is_noop_on_manifest_without_intake_producer(tmp_path):
    mf = tmp_path / "manifest.json"
    mf.write_text(json.dumps({"manifest_version": 37, "phases": [
        {"id": "PT", "order": 1.0, "owning_role": "r",
         "produces_artifact": "working/prompts/slide-01.txt",
         "heartbeat_minutes": 1, "client_report": {}}],
        "deliverables_required": []}))
    manifest = Manifest(mf)
    eng = _engine(tmp_path, write_intake=False, manifest=manifest)
    phase = manifest.phase("PT")

    assert eng._intake_gate_applies(phase) is False, (
        "a manifest with no declared intake producer must never trigger this gate")
    assert eng._check_intake_gate(phase) is None
