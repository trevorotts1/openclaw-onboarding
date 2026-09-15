"""PD-TEST-010 / PD-TEST-011 -- signature-only stages must be gated OUT of the
phase WALK on a non-signature deck (presentation_job/phases.py).

THE DEFECT THIS FILE PROVES FIXED (live run
pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4, 2026-09-14, the first run
that ever walked this manifest's full phase list):

  _SP_ONLY_PHASE_IDS was consumed ONLY by _client_visible_phases -- whose own
  docstring says it "Does NOT change `phases` itself, the attestation chain,
  the DAG, or anything the phase walk/dispatch loop iterates ... display-only".
  So the walk still dispatched P-SP-INTAKE onto a webinar deck
  (presentation_type=from_scratch, deck_type=webinar, pitch_included=false);
  the executor CORRECTLY refused to author a signature artifact for a
  non-signature deck ("driver_only: build_deck._chk_sp_intake -> Skill 51's
  prove_sp_intake..."), and after DISPATCH_REPEAT_CEILING=8 identical
  'declined' outcomes the dispatcher retry ceiling failed the phase -- taking
  the WHOLE run to terminal=BLOCKED behind a stage that never applied to it.

THE FIX (the pattern P-CONVERTER already used): the walk's applicability
selection routes the four signature-only stages around a positively-confirmed
non-signature deck -- status=done + routed_around=true, NO executor, NO
verifier, explicit routed_around_reason -- exactly as
_route_around_converter_phase already does for P-CONVERTER on a non-content-
first deck. The executor's refusal is NOT weakened; the phase simply never
reaches it.

NO HAND-BUILT FIXTURES: every case below drives the REAL on-disk manifest
(universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json, the same file
the department installs to sops/PIPELINE-MANIFEST.json) with REAL saved intake
records -- the live run's own sealed intake.json, and the golden-quest
signature example's sealed intake.json (deck_type=signature_presentation,
presentation_type=signature). The harness copies those read-only records into a
temp run dir; it never writes to the live run directory or the installed
department.

Flat file inside tests/, manages its own import path -- matching every sibling
in this directory (test_af_intake_gate.py, test_defers.py, etc.).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import StateStore  # noqa: E402


# The four signature-presentation-only stages (phases.py _SP_ONLY_PHASE_IDS).
SP_ONLY = ("P-SP-INTAKE", "P-SP-INTAKE-TRACE", "P-SP-STRUCTURE", "P-SP-P3-HYGIENE")
# The phase the fix deliberately does NOT touch: P-SP-CLAIM is the router.
SP_CLAIM = "P-SP-CLAIM"
CONVERTER = "P-CONVERTER"

# The live run whose intake deadlocked the pipeline (read-only source).
LIVE_RUN_INTAKE = Path(
    "/Users/blackceomacmini/.openclaw/workspace/departments/Presentations/runs/"
    "pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4/working/copy/intake.json")


# ---------------------------------------------------------------------------
# Real-artifact resolution (never a hand-authored fixture)
# ---------------------------------------------------------------------------
def _repo_root() -> Path:
    """The checkout root that holds universal-sops/ (the manifest SOURCE)."""
    cur = SCRIPTS
    for _ in range(12):
        if (cur / "universal-sops" / "presentation-slide-craft"
                / "PIPELINE-MANIFEST.json").is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise FileNotFoundError(
        "universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json not "
        f"found above {SCRIPTS}")


def _real_manifest_path() -> Path:
    """The canonical manifest, preferring the DEPLOYED copy when one sits
    beside the scripts (mirrors test_af_intake_gate.py's resolution order)."""
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    return _repo_root() / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"


def _live_intake() -> dict:
    """The live run's own sealed intake (deck_type=webinar). Env override
    PD010_LIVE_INTAKE lets a reviewer point at an archived copy; the live path
    itself is only ever READ."""
    p = Path(os.environ.get("PD010_LIVE_INTAKE") or LIVE_RUN_INTAKE)
    if not p.is_file():
        pytest.skip(f"live non-signature intake not available at {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _signature_intake() -> dict:
    """The repository's real signature-deck intake (golden-quest example:
    deck_type=signature_presentation, presentation_type=signature)."""
    p = (_repo_root() / "51-signature-presentation" / "examples" / "golden-quest"
         / "working" / "copy" / "intake.json")
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    env = os.environ.get("PD010_SIGNATURE_INTAKE")
    if env and Path(env).is_file():
        return json.loads(Path(env).read_text(encoding="utf-8"))
    pytest.skip("no real signature intake record available")


def _engine(tmp_path: Path, intake: dict | None) -> Engine:
    """An Engine over a temp run dir whose working/copy/intake.json is the REAL
    saved record (or absent, for the fail-open cases)."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    if intake is not None:
        (rd / "working" / "copy" / "intake.json").write_text(
            json.dumps(intake), encoding="utf-8")
    manifest = Manifest(_real_manifest_path())
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "pd010", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00",
        "manifest_path": str(manifest.path), "manifest_version": manifest.version,
        "manifest_sha256": manifest.sha256,
        "presentation_type": intake.get("presentation_type") if intake else None,
        "requester": {"chat_id": "tc"}, "phases": [], "gates": {}, "waivers": [],
        "events": [], "sent": {}, "undeliverable": [], "heartbeat": {},
        "terminal": None,
    }
    return Engine(rd, manifest, store, state, dry_run=False)


def _walk(eng: Engine, only: str | None = None):
    """Run THE walk's applicability selection -- the exact method Engine.run
    calls before it builds the execution plan, the waves and the ready queue."""
    return eng._phases_applicable_to_this_deck(eng.manifest.phases, only=only)


def _walked_ids(eng: Engine, phases) -> set:
    return {p.id for p in phases}


# ---------------------------------------------------------------------------
# 1. Direction A: a NON-signature deck must not walk (therefore cannot
#    dispatch) any of the four signature-only stages -- using the LIVE run's
#    own intake, the exact record that deadlocked the real pipeline.
# ---------------------------------------------------------------------------
def test_live_non_signature_deck_does_not_walk_signature_only_stages(tmp_path):
    intake = _live_intake()
    assert intake["deck_type"] == "webinar"            # the real record, pinned
    assert intake["presentation_type"] == "from_scratch"
    assert intake["pitch_included"] is False
    eng = _engine(tmp_path, intake)

    phases = _walk(eng)
    walked = _walked_ids(eng, phases)

    absent = [pid for pid in SP_ONLY if pid not in walked]
    assert absent == list(SP_ONLY), (
        f"every signature-only stage must be routed out of this deck's walk; "
        f"still walked: {sorted(set(SP_ONLY) & walked)}")
    # The rest of the pipeline is untouched -- in particular P-SP-CLAIM, the
    # router, MUST still walk (it runs for real on EVERY deck).
    assert SP_CLAIM in walked
    assert CONVERTER not in walked  # the original converter routing, unchanged
    assert len(phases) == len(eng.manifest.phases) - 5  # 4 SP-only + P-CONVERTER


def test_non_signature_route_around_is_honest_not_a_fake_pass(tmp_path):
    """Each routed stage is marked done-with-routed_around, with NO artifact,
    NO verifier result, and a reason that names the real deck_type -- the
    auditable distinction from a genuine execution."""
    eng = _engine(tmp_path, _live_intake())
    _walk(eng)

    for pid in SP_ONLY:
        ps = eng._phase_state(pid)
        assert ps["status"] == "done", f"{pid} should be routed around, got {ps['status']}"
        assert ps.get("routed_around") is True
        assert ps.get("verifier_ok") is None, (
            f"{pid} must never be 'checked and passed' -- it was never checked")
        assert ps.get("artifacts") == [], f"{pid} produced nothing"
        assert ps.get("owner_skip_approval") is None, (
            "routing around is not an owner skip approval")
        reason = ps.get("routed_around_reason") or ""
        assert "deck_type='webinar'" in reason
        assert pid in reason

    events = [e for e in (eng.state.get("events") or [])
              if e.get("kind") == "phase.routed_around"
              or e.get("event") == "phase.routed_around"]
    emitted = " ".join(json.dumps(e) for e in events)
    for pid in SP_ONLY:
        assert pid in emitted, f"no phase.routed_around event recorded for {pid}"


def test_non_signature_route_around_forwards_nothing_to_the_executor(tmp_path, monkeypatch):
    """Regression proof at the dispatch seam: an executor that would be called
    for every walked phase is NEVER called for a routed-around stage, and no
    agent step is spent on it."""
    eng = _engine(tmp_path, _live_intake())

    dispatched: list[str] = []

    def _recording_run_phase(phase):
        dispatched.append(phase.id)
        raise AssertionError(
            f"{phase.id} reached the executor on a non-signature deck -- this "
            "is exactly the deadlock PD-TEST-010 reports")

    monkeypatch.setattr(eng, "run_phase", _recording_run_phase)
    monkeypatch.setattr(eng, "run_phase_timed",
                        lambda p, wave=0: _recording_run_phase(p))

    phases = _walk(eng)
    for p in phases:                      # what Engine.run would hand the pool
        if p.id in SP_ONLY:
            eng.run_phase_timed(p, wave=1)

    assert dispatched == []
    for pid in SP_ONLY:
        assert eng._phase_state(pid)["routed_around"] is True


# ---------------------------------------------------------------------------
# 2. Direction B: a GENUINE signature presentation must STILL walk all four.
# ---------------------------------------------------------------------------
def test_genuine_signature_deck_walks_all_four_stages(tmp_path):
    intake = _signature_intake()
    assert intake["deck_type"] == "signature_presentation"   # real record, pinned
    assert intake["presentation_type"] == "signature"
    eng = _engine(tmp_path, intake)

    phases = _walk(eng)
    walked = _walked_ids(eng, phases)

    missing = [pid for pid in SP_ONLY if pid not in walked]
    assert not missing, (
        f"a genuine signature presentation must still walk all four stages; "
        f"missing: {missing}")
    assert SP_CLAIM in walked

    for pid in SP_ONLY:
        ps = eng._phase_state(pid)
        assert ps == {} or ps.get("routed_around") is not True, (
            f"{pid} must NOT be routed around on a signature deck")
    # No signature-only routing event -- the only routing this deck gets is the
    # untouched converter one (asserted separately below).
    sp_events = [e for e in (eng.state.get("events") or [])
                 if (e.get("kind") or e.get("event")) == "phase.routed_around"
                 and any(pid in json.dumps(e) for pid in SP_ONLY)]
    assert not sp_events


def test_signature_deck_still_routes_the_converter_around(tmp_path):
    """Direction B's control: on the real signature intake the ONLY routing is
    the untouched converter one (creation_mode=from_scratch), so the fix is not
    a blanket skip of the P-SP cluster."""
    eng = _engine(tmp_path, _signature_intake())
    walked = _walked_ids(eng, _walk(eng))

    assert CONVERTER not in walked            # converter routing still applies
    assert eng._phase_state(CONVERTER).get("routed_around") is True
    assert all(pid in walked for pid in SP_ONLY)


# ---------------------------------------------------------------------------
# 3. Fail-open: an unknown/absent deck_type must WIDEN to full enforcement --
#    never skip a stage on missing information (the same direction
#    _client_visible_phases already documents).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("intake,label", [
    (None, "no intake.json at all"),
    ({}, "empty intake object"),
    ({"deck_type": ""}, "empty deck_type"),
    ({"deck_type": "   "}, "whitespace deck_type"),
])
def test_unknown_deck_type_widens_to_full_enforcement(tmp_path, intake, label):
    eng = _engine(tmp_path, intake)
    walked = _walked_ids(eng, _walk(eng))
    assert all(pid in walked for pid in SP_ONLY), (
        f"{label} must not narrow the walk -- unknown widens")
    sp_events = [e for e in (eng.state.get("events") or [])
                 if (e.get("kind") or e.get("event")) == "phase.routed_around"
                 and any(pid in json.dumps(e) for pid in SP_ONLY)]
    assert not sp_events


def test_unparseable_intake_widens_to_full_enforcement(tmp_path):
    eng = _engine(tmp_path, None)
    (Path(eng.run_dir) / "working" / "copy" / "intake.json").write_text(
        "{not json", encoding="utf-8")
    walked = _walked_ids(eng, _walk(eng))
    assert all(pid in walked for pid in SP_ONLY)


# ---------------------------------------------------------------------------
# 4. `only` (an operator naming ONE phase by id) is still honored as-is --
#    identical to the converter branch's long-standing contract.
# ---------------------------------------------------------------------------
def test_explicit_single_phase_request_is_not_silently_rerouted(tmp_path):
    eng = _engine(tmp_path, _live_intake())
    forced = [eng.manifest.phase("P-SP-INTAKE")]
    out = eng._phases_applicable_to_this_deck(forced, only="P-SP-INTAKE")

    assert [p.id for p in out] == ["P-SP-INTAKE"]
    assert eng._phase_state("P-SP-INTAKE").get("routed_around") is not True


# ---------------------------------------------------------------------------
# 5. Parity: the walk's decision and the client-facing step count are driven
#    by the same real deck_type -- they can never disagree.
# ---------------------------------------------------------------------------
def test_walk_and_client_visible_phase_filter_agree(tmp_path):
    for intake in (_live_intake(), _signature_intake()):
        eng = _engine(tmp_path / (intake["deck_type"] or "x"), intake)
        walked = _walked_ids(eng, _walk(eng))
        visible = {p.id for p in eng._client_visible_phases(eng.manifest.phases)}
        for pid in SP_ONLY:
            assert (pid in walked) == (pid in visible), (
                f"{pid}: walk says {pid in walked}, client step count says "
                f"{pid in visible} for deck_type={intake['deck_type']!r}")


# ---------------------------------------------------------------------------
# 6. The predicate itself: deck_type is the axis, and signature_source /
#    creation_mode cannot substitute for it.
# ---------------------------------------------------------------------------
def test_predicate_is_deck_type_not_creation_mode_or_signature_source(tmp_path):
    """The live non-signature run and the real signature example share
    creation_mode=from_scratch -- proving creation_mode can never be the
    predicate. signature_source in the live run is ALSO from_scratch."""
    live, sig = _live_intake(), _signature_intake()
    assert live["creation_mode"] == sig["creation_mode"] == "from_scratch"
    assert live.get("signature_source") == "from_scratch"
    assert live["deck_type"] != sig["deck_type"]

    eng_live = _engine(tmp_path / "live", live)
    eng_sig = _engine(tmp_path / "sig", sig)
    assert [p.id for p in _walk(eng_live) if p.id in SP_ONLY] == []
    assert {p.id for p in _walk(eng_sig) if p.id in SP_ONLY} == set(SP_ONLY)
