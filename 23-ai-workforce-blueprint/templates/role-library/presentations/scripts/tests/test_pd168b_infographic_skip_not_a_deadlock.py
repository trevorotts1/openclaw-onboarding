"""PD-TEST-168 part B -- a legitimately SKIPPED infographic must not deadlock P8.3.

THE DEFECT. `phases.py` parks a phase on `waiting_for = list(produces_artifact)`,
and `P8.3-INFOGRAPHIC` produces `working/deliverables/infographic.png`. But
`sops/slide-image-creator-sops.md` step 1 tells the role to SKIP the infographic
-- recording `infographic_skipped: true` -- when the deck does not require one:

    "Confirm the run requires an infographic by checking
     `deliverable_bundle.checklist_items` in intake.json. If the key is absent
     or empty and the run is NOT a converter origin, skip this SOP and record
     `infographic_skipped: true` ... Do NOT produce the file speculatively."

`build_infographic.py:702-711` already honours that marker, but the WALK did
not: the phase stayed scheduled, the script exited 0 having produced nothing,
and `phase_verifiers` has NO skip path -- it hard-requires the PNG (>=102,400
bytes), `status: "ready"`, `qc_passed: true` and a passing QC verdict. So a
correctly-skipped infographic parked the phase forever, exactly as `P4-PROMPT`
parked on the prompt the copywriter was never tasked to write.

WHAT THESE TESTS PIN
  * a deck that POSITIVELY does not require an infographic does not WALK the
    phase -- so it can never be dispatched, and so it can never park;
  * a deck that requires one still walks it (the extra is not silently dropped);
  * the decision FAILS OPEN: an absent or unreadable intake.json, or an
    unconfirmed creation_mode, keeps the phase exactly as before;
  * the routing is not disguised as a verified execution -- status=done for
    accounting, but verifier_ok is None, artifacts is empty, and
    routed_around/routed_around_reason are recorded.

NO HAND-BUILT MANIFEST: every case drives the REAL on-disk manifest, so the
`infographic_path` flag is exercised where it actually ships.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import StateStore  # noqa: E402

PHASE = "P8.3-INFOGRAPHIC"


def _repo_root() -> Path:
    for p in [SCRIPTS] + list(SCRIPTS.parents):
        if (p / "universal-sops").is_dir():
            return p
    raise AssertionError("repo root not found from %s" % SCRIPTS)


def _real_manifest_path() -> Path:
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    return _repo_root() / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"


def _engine(tmp_path: Path, intake) -> Engine:
    """An Engine over a temp run dir. `intake=None` leaves intake.json ABSENT."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    if intake is not None:
        (rd / "working" / "copy" / "intake.json").write_text(
            json.dumps(intake), encoding="utf-8")
    manifest = Manifest(_real_manifest_path())
    state = {
        "schema_version": 1, "job_id": "pd168b", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00",
        "manifest_path": str(manifest.path), "manifest_version": manifest.version,
        "manifest_sha256": manifest.sha256,
        "presentation_type": (intake or {}).get("presentation_type"),
        "requester": {"chat_id": "tc"}, "phases": [], "gates": {}, "waivers": [],
        "events": [], "sent": {}, "undeliverable": [], "heartbeat": {},
        "terminal": None,
    }
    return Engine(rd, manifest, StateStore(rd), state, dry_run=False)


def _walked(eng: Engine) -> set:
    return {p.id for p in eng._phases_applicable_to_this_deck(eng.manifest.phases)}


def _row(eng: Engine):
    for p in eng.state.get("phases") or []:
        if p.get("id") == PHASE:
            return p
    return None


# ---------------------------------------------------------------------------
# The flag must actually ship on the phase
# ---------------------------------------------------------------------------

def test_the_shipped_manifest_marks_the_infographic_stage():
    m = json.loads(_real_manifest_path().read_text(encoding="utf-8"))
    ph = next(p for p in m["phases"] if p["id"] == PHASE)
    assert ph.get("infographic_path") is True, (
        "P8.3-INFOGRAPHIC is not marked infographic_path -- part B cannot route "
        "it around and the skip deadlock remains")
    # and the marker must be READ into the Phase object, not merely present
    eng_ph = None
    eng = None
    for p in Manifest(_real_manifest_path()).phases:
        if p.id == PHASE:
            eng_ph = p
    assert getattr(eng_ph, "infographic_path", None) is True, (
        "manifest.py does not read the infographic_path flag into Phase")


# ---------------------------------------------------------------------------
# Direction A: a deck that does NOT need an infographic must not walk it
# ---------------------------------------------------------------------------

def test_deck_without_checklist_items_does_not_walk_the_infographic(tmp_path):
    """The live shape: deliverable_bundle absent, creation_mode from_scratch."""
    eng = _engine(tmp_path, {"creation_mode": "from_scratch",
                             "presentation_type": "from_scratch"})
    assert PHASE not in _walked(eng), (
        "a deck that positively does not require an infographic still walks "
        "P8.3-INFOGRAPHIC -- it will park on a PNG that nothing will ever "
        "produce (phase_verifiers has no skip path)")
    row = _row(eng)
    assert row is not None, "the routed-around phase left no auditable row"
    assert row.get("routed_around") is True
    assert row.get("routed_around_reason")
    assert row.get("verifier_ok") is None, (
        "routing-around must NOT be disguised as a verified pass")
    assert not row.get("artifacts"), "nothing was produced, so artifacts must be empty"


def test_empty_checklist_items_also_skips(tmp_path):
    eng = _engine(tmp_path, {"creation_mode": "from_scratch",
                             "deliverable_bundle": {"checklist_items": []}})
    assert PHASE not in _walked(eng)


# ---------------------------------------------------------------------------
# Direction B: a deck that DOES need one still walks it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("intake", [
    {"creation_mode": "from_scratch",
     "deliverable_bundle": {"checklist_items": ["Book the call", "Send the brief"]}},
    {"creation_mode": "from_scratch", "checklist_items": ["One item"]},
    {"creation_mode": "content_general"},   # converter origin -> required
    {"creation_mode": "content_personal"},
])
def test_a_deck_that_requires_an_infographic_still_walks_it(tmp_path, intake):
    eng = _engine(tmp_path, intake)
    assert PHASE in _walked(eng), (
        f"the infographic extra was silently dropped for {intake!r} -- it is "
        "required, so the phase must run and earn its pass normally")


# ---------------------------------------------------------------------------
# FAIL OPEN -- the property the whole mechanism rests on
# ---------------------------------------------------------------------------

def test_absent_intake_fails_open(tmp_path):
    """No intake.json at all: we cannot prove the deck lacks an infographic."""
    eng = _engine(tmp_path, None)
    assert PHASE in _walked(eng), (
        "an ABSENT intake.json routed the infographic around -- the decision "
        "must never be made on missing information")


def test_unparseable_intake_fails_open(tmp_path):
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "intake.json").write_text("{not json", encoding="utf-8")
    manifest = Manifest(_real_manifest_path())
    state = {"schema_version": 1, "job_id": "pd168b", "run_dir": str(rd),
             "created_at": "2026-01-01T00:00:00+00:00",
             "manifest_path": str(manifest.path), "manifest_version": manifest.version,
             "manifest_sha256": manifest.sha256, "presentation_type": None,
             "requester": {"chat_id": "tc"}, "phases": [], "gates": {}, "waivers": [],
             "events": [], "sent": {}, "undeliverable": [], "heartbeat": {},
             "terminal": None}
    eng = Engine(rd, manifest, StateStore(rd), state, dry_run=False)
    assert PHASE in _walked(eng), "an UNPARSEABLE intake routed the phase around"


def test_unconfirmed_creation_mode_fails_open(tmp_path):
    """checklist_items absent but creation_mode NOT positively read -> enforce."""
    eng = _engine(tmp_path, {"presentation_type": "from_scratch"})
    assert PHASE in _walked(eng), (
        "the phase was routed around without a positively-read creation_mode")


def test_only_the_infographic_stage_is_affected(tmp_path):
    """The predicate must be scoped by the flag, never by id-matching alone."""
    eng = _engine(tmp_path, {"creation_mode": "from_scratch"})
    walked = _walked(eng)
    # a densely-scheduled neighbouring stage must be untouched
    for other in ("P4-PROMPT", "P-BUNDLE-GATE", "P8.25-WORKBOOK"):
        assert other in walked, f"{other} was collaterally routed around"
