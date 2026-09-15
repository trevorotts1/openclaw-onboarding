"""PD-TEST-067 — the arc_allocation.json producer/consumer SHAPE contract.

THE LIVE DEFECT (run pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4).

P3-ARC reported `done` and its artifact `working/copy/arc_allocation.json` was
on disk (10,013 bytes, `slide_count: 8`) — the dependency HAD landed. But the
agent-authored phase wrote its 8 slides under `slide_allocations` with
per-slide `slide_number`, while every reader in this tree looked for
`slots` | `allocation` | `slides` with per-slide `slide`. `slide_allocations`
appeared NOWHERE else in the repository, so no reader could see it.

P3-ARC's verifier was `_verify_json_artifact("working/copy/arc_allocation.json")`
with no required_keys — valid JSON only — so a structurally valid but wholly
unconsumable artifact was blessed `done`. Downstream, `fanout._slides_for_units`
returned [] and `_dispatch_phase_fanout_units` emitted its zero-unit refusal;
because that refusal is byte-identical every tick, `record_outcome` folded 8 of
them into DISPATCH_REPEAT_CEILING and quarantined P-U-DESIGN-VSL,
P-U-DESIGN-SALES, P-U-DESIGN-CHECKOUT and P-STYLE-SPEC (43 error rows each,
paid_attempts 0). Five dependents then waited on those quarantines forever.

VERDICT: this is a genuine enumeration/contract BUG (hypothesis A), NOT a
truthful dependency-wait (B) — the upstream artifact was present and complete.

WHAT THESE TESTS PIN DOWN:
  (a) the EXACT live key shape enumerates its units and dispatches;
  (b) the canonical `slots`/`slide` shape still enumerates and dispatches;
  (c) a run whose arc has not landed enumerates zero, and RESUMES normally the
      moment the arc appears (the dependency lands and the phase goes through);
  (d) a recognised-but-EMPTY allocation, and a valid-JSON artifact carrying no
      readable slide array, both STILL fail loudly and park at the ceiling —
      the refusal is preserved byte-for-byte and no real bug may hide;
  (e) every reader agrees on ONE slide count for the SAME artifact, and P3-ARC's
      verifier now refuses an artifact its own consumers cannot read.

No test makes a network call, spends a token, or touches a live run directory.
The only stubbed seam is dispatcher.dispatch_complete; the manifest, the
FanoutSpec, the enumerator, the sweep loop, the ledger, the backoff and the
ceiling are all the real code.
"""
from __future__ import annotations

import json
import sys
import time as _real_time
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job import arc_slides as arc  # noqa: E402
from presentation_job import dispatcher as dj  # noqa: E402
from presentation_job import fanout as fo  # noqa: E402
import build_deck as bd  # noqa: E402
import craft_judgement as cj  # noqa: E402
import phase_verifiers as pv  # noqa: E402

PHASE = "P-STYLE-SPEC"
SPEC_ARTIFACT = "working/copy/style_preview_spec.json"
ARC_REL = "working/copy/arc_allocation.json"

CLUSTER_MANIFEST = (
    _scripts_dir.parent.parent.parent.parent.parent
    / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
)

#: The live shape, verbatim in its key names: a container `slide_allocations`
#: whose slots carry `slide_number` (NOT `slide`), plus `arc_sections`.
LIVE_KEYS = ("slide_allocations", "slide_number")
#: The repo's declared/canonical shape — the golden-quest reference artifact.
CANONICAL_KEYS = ("slots", "slide")
OTHER_ACCEPTED_KEYS = (("allocation", "slide"), ("slides", "slide"))


def _live_allocation(n: int = 8) -> dict:
    """An arc_allocation.json in the shape P3-ARC actually emitted live."""
    return {
        "artifact": ARC_REL,
        "phase": "P3-ARC",
        "owning_role": "offer-price-strategist",
        "slide_count": n,
        "arc_sections": [{"section_id": f"s{i}", "name": f"Section {i}",
                          "slides": [i]} for i in range(1, n + 1)],
        "slide_allocations": [
            {"slide_number": i, "move": i, "arc_section": f"s{i}",
             "move_tag": "PRIORITY_STACK", "slide_title": f"Title {i}",
             "content_summary": f"Summary {i}",
             "arc_marks": {"peak": False, "decision_climax": False,
                           "ending": False}}
            for i in range(1, n + 1)],
        "peak_apex_slide": 4, "ending_slide": n,
    }


def _canonical_allocation(n: int = 8) -> dict:
    """The same allocation in the repo's canonical shape.

    PD-TEST-082 NOTE: this fixture now also carries the arc's explicit PEAK and
    ENDING declarations, because P3-ARC's verifier requires them (see
    phase_verifiers._verify_arc_allocation). This file's own subject — that
    every accepted container/ordinal spelling is READABLE and every reader
    agrees — is unchanged: every assertion and the full parametrization below
    are preserved.

    The genuine committed reference artifact
    (51-signature-presentation/examples/golden-quest/working/copy/
    arc_allocation.json, 103 slots) declares the beats in NO recognised form:
    its ``arc_section`` values are the four Signature-Presentation PHASES
    (Avatar / Signature Story / Transformational Teaching / Purpose Pitch),
    which match no PEAK_TAGS or ENDING_TAGS token. That is recorded as an open
    doctrine question in tests/test_pd082_peak_end_contract.py, not silently
    absorbed by this fixture.
    """
    return {
        "deck_type": "signature", "deck_slug": "pd067", "bands": {},
        "slots": [{"slide": i, "phase": "avatar", "arc_section": f"Section {i}",
                   "hook": False, "label_slide": False, "case_study": False}
                  for i in (range(1, n + 1))],
        "peak_apex_slide": 4, "ending_slide": n,
    }


class _Clock:
    """Fake wall clock for should_dispatch/record_outcome, as the sibling
    zero-units suite uses: everything but time() delegates to the real module
    so try_claim's CLOCK_BOOTTIME liveness probe keeps working."""

    def __init__(self, t0: float) -> None:
        self._t = float(t0)

    def time(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        self._t += dt

    def __getattr__(self, name):  # pragma: no cover - pure delegation
        return getattr(_real_time, name)


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    c = _Clock(_real_time.time())
    monkeypatch.setattr(dj, "time", c)
    return c


def _seed_run(tmp_path: Path, *, allocation: dict | None = None,
              slides_json: list | None = None) -> Path:
    """A run whose only work order is the fan-out phase.

    `allocation` is written to working/copy/arc_allocation.json; with both
    arguments None the run carries NEITHER source, so the real enumerator
    legitimately returns zero units and nothing is monkeypatched to force it.
    """
    run_dir = tmp_path / "run"
    (run_dir / "working" / "work-orders").mkdir(parents=True)
    (run_dir / "working" / "copy").mkdir(parents=True)
    (run_dir / "state.json").write_text(json.dumps({
        "manifest_path": str(CLUSTER_MANIFEST),
        "phases": [{"id": PHASE, "status": "running"}],
    }), encoding="utf-8")
    (run_dir / "working" / "work-orders" / f"{PHASE}.json").write_text(json.dumps({
        "phase_id": PHASE, "owning_role": "brand-steward",
        "produces_artifact": SPEC_ARTIFACT,
    }), encoding="utf-8")
    (run_dir / "working" / "copy" / "intake.json").write_text(
        json.dumps({"business_name": "TestCo"}), encoding="utf-8")
    if allocation is not None:
        (run_dir / ARC_REL).write_text(json.dumps(allocation), encoding="utf-8")
    if slides_json is not None:
        (run_dir / "working" / "copy" / "slides.json").write_text(
            json.dumps(slides_json), encoding="utf-8")
    return run_dir


def _fake_model(monkeypatch) -> list:
    """A model stub producing one well-formed style variant per call."""
    seen: list = []

    def _fake(system_prompt, user_prompt, *, phase_id, run_dir=None, **kw):
        seen.append(phase_id)
        n = len(seen)
        return (json.dumps({"id": "ABC"[n - 1],
                            "style_directive": f"variant {'ABC'[n - 1]} editorial",
                            "representative_slide": n}),
                {"request_id": f"stub-{n}"}, {"provider": "stub", "model": "stub-1"})

    monkeypatch.setattr(dj, "dispatch_complete", _fake)
    return seen


def _no_model(monkeypatch) -> list:
    calls: list = []

    def _boom(*a, **kw):  # pragma: no cover - reaching this IS the failure
        calls.append(kw.get("phase_id"))
        raise AssertionError("the zero-units refusal must never call the model")

    monkeypatch.setattr(dj, "dispatch_complete", _boom)
    return calls


def _sweep_n(run_dir: Path, clock: _Clock, n: int) -> list:
    out = []
    for _ in range(n):
        out.extend(dj.sweep_run_dir(run_dir, worker_id="test-sweeper", max_workers=3))
        clock.advance(10.0)
    return out


def _marker(run_dir: Path) -> Path:
    return run_dir / "working" / "work-orders" / f"{PHASE}.dispatch-blocked.txt"


# ===========================================================================
# (a) THE LIVE CONDITION: the exact P3-ARC key shape enumerates + dispatches.
# ===========================================================================
def test_live_slide_allocations_shape_enumerates_its_units(tmp_path):
    """The premise, unstubbed: the real enumerator reads the live shape.

    Before the fix this returned zero units for a present, complete 8-slide
    allocation — the single fact every quarantine in PD-TEST-067 followed from.
    """
    run_dir = _seed_run(tmp_path, allocation=_live_allocation(8))
    assert not (run_dir / "working" / "copy" / "slides.json").exists(), \
        "the live run had no slides.json; the arc must carry the enumeration alone"
    assert (run_dir / ARC_REL).is_file()

    spec = dj._phase_fanout_spec(PHASE, run_dir)
    assert spec is not None and spec.by == "slide"
    items = fo.enumerate_fanout_items(run_dir, spec, phase_id=PHASE,
                                      produces_artifact=[SPEC_ARTIFACT])
    assert [i["key"] for i in items] == [f"slide-{n:02d}" for n in range(1, 9)], \
        f"the live arc shape must enumerate its 8 slides, got {items!r}"
    assert [i["ordinal"] for i in items] == list(range(1, 9))


def test_live_shape_dispatches_and_aggregates(tmp_path, clock, monkeypatch):
    """(a) end to end: the live condition now produces real units and a real
    artifact instead of 8 identical errors and a quarantine."""
    seen = _fake_model(monkeypatch)
    run_dir = _seed_run(tmp_path, allocation=_live_allocation(8))

    results = dj.sweep_run_dir(run_dir, worker_id="test-sweeper", max_workers=3)

    assert len(results) == 1 and results[0].status == "ok", \
        f"the live arc shape did not dispatch: {results and results[0].reasons}"
    # desired_count=3 bounds the phase's desired work count to three variants.
    assert len(seen) == 3, f"expected one model call per wanted unit, got {seen!r}"

    spec = json.loads((run_dir / SPEC_ARTIFACT).read_text(encoding="utf-8"))
    assert len(spec["variants"]) == 3
    assert {v["id"] for v in spec["variants"]} == {"A", "B", "C"}

    led = dj._read_ledger(run_dir, PHASE)
    assert led["status"] == "ok" and led["blocked"] is False
    assert not _marker(run_dir).exists(), "a successful phase must not be parked"


# ===========================================================================
# (b) The canonical shape is not regressed.
# ===========================================================================
@pytest.mark.parametrize("label,allocation", [
    ("canonical-slots", _canonical_allocation(8)),
    ("live-slide_allocations", _live_allocation(8)),
])
def test_both_real_shapes_enumerate_the_same_units(tmp_path, label, allocation):
    run_dir = _seed_run(tmp_path, allocation=allocation)
    spec = dj._phase_fanout_spec(PHASE, run_dir)
    items = fo.enumerate_fanout_items(run_dir, spec, phase_id=PHASE,
                                      produces_artifact=[SPEC_ARTIFACT])
    assert len(items) == 8, f"{label}: expected 8 units, got {len(items)}"


def test_canonical_shape_still_dispatches(tmp_path, clock, monkeypatch):
    seen = _fake_model(monkeypatch)
    run_dir = _seed_run(tmp_path, allocation=_canonical_allocation(8))
    results = dj.sweep_run_dir(run_dir, worker_id="test-sweeper", max_workers=3)
    assert len(results) == 1 and results[0].status == "ok"
    assert len(seen) == 3


def test_slides_json_still_wins_over_the_arc(tmp_path):
    """The established priority is unchanged: slides.json, when it exists, is
    the file the renderer itself renders and stays first."""
    run_dir = _seed_run(tmp_path, allocation=_live_allocation(8),
                        slides_json=[{"ordinal": n, "slide": n} for n in (1, 2, 3)])
    assert arc.load_slide_count(run_dir) == 3, \
        "slides.json (3) must win over arc_allocation.json (8)"


# ===========================================================================
# (e) ONE contract: every reader agrees, for every accepted spelling.
# ===========================================================================
@pytest.mark.parametrize("container,ordinal_key", [
    LIVE_KEYS, CANONICAL_KEYS, *OTHER_ACCEPTED_KEYS,
])
def test_every_reader_agrees_on_one_slide_count(tmp_path, container, ordinal_key):
    """The divergence itself was the defect: five readers with five private
    key lists let one blessed artifact be readable by none of them. Whatever
    spelling is accepted, every reader must see the SAME number.

    PD-TEST-082: the allocation also declares the arc's PEAK and ENDING, which
    P3-ARC's verifier now additionally requires. The parametrization over every
    accepted container/ordinal spelling — this test's actual subject — is
    untouched."""
    n = 8
    alloc = {container: [{ordinal_key: i, "arc_section": f"s{i}"}
                         for i in range(1, n + 1)],
             "peak_apex_slide": 4, "ending_slide": n}
    run_dir = _seed_run(tmp_path, allocation=alloc)

    from_slides = len(fo._slides_for_units(run_dir))
    from_dispatcher = dj._prompt_slide_count(run_dir)
    from_build_deck = bd._count_output_slides(run_dir)
    from_craft = len(cj._arc_slots(run_dir))
    from_shared = arc.load_slide_count(run_dir)
    verifier_ok, verifier_reasons = pv._verify_arc_allocation(run_dir)

    assert {from_slides, from_dispatcher, from_build_deck, from_craft,
            from_shared} == {n}, (
        f"{container}/{ordinal_key}: readers disagree -> enumerator={from_slides} "
        f"dispatcher={from_dispatcher} build_deck={from_build_deck} "
        f"craft_judgement={from_craft} shared={from_shared}")
    assert verifier_ok, f"P3-ARC's verifier refused a readable allocation: {verifier_reasons}"


def test_craft_judgement_reads_real_ordinals_from_the_live_shape(tmp_path):
    """AF-DEN's checks read `slot["slide"]`. On the live shape they used to get
    [] and silently DEFER every density auto-fail on a deck that did declare an
    allocation — a silent QC weakening, not just a stall."""
    run_dir = _seed_run(tmp_path, allocation=_live_allocation(8))
    slots = cj._arc_slots(run_dir)
    assert [s["slide"] for s in slots] == list(range(1, 9))
    assert [s["ordinal"] for s in slots] == list(range(1, 9))


def test_non_contiguous_ordinals_are_not_renumbered(tmp_path):
    """A declared ordinal is authoritative: position must never overwrite it,
    or a gap in the allocation would silently renumber the deck."""
    run_dir = _seed_run(tmp_path, allocation={
        "slide_allocations": [{"slide_number": n} for n in (2, 5, 9)]})
    assert [s["ordinal"] for s in arc.load_slots(run_dir)] == [2, 5, 9]
    assert dj._prompt_slide_count(run_dir) == 3


def test_parse_error_sentinel_is_not_an_empty_allocation(tmp_path):
    """build_deck._read_json substitutes a sentinel for an unparseable file;
    that must read as NOT DETERMINABLE, never as zero slides — otherwise a
    corrupt artifact would look like a deck with no slides instead of a
    broken file."""
    assert arc.slots_from_obj({"__parse_error__": "boom"}) is None
    assert arc.slide_count_from_obj({"__parse_error__": "boom"}) is None
    run_dir = _seed_run(tmp_path / "corrupt")
    assert bd._count_output_slides(run_dir) is None
    (run_dir / ARC_REL).write_text("{ not json", encoding="utf-8")
    assert bd._count_output_slides(run_dir) is None


# ===========================================================================
# (c) The absent dependency waits, then resumption goes through.
# ===========================================================================
def test_absent_allocation_enumerates_zero_then_resumes_when_it_lands(
        tmp_path, clock, monkeypatch):
    """(c) A run whose arc has not landed yet must not fabricate units, and
    must go straight through on a later tick once the dependency lands."""
    seen = _fake_model(monkeypatch)
    run_dir = _seed_run(tmp_path)  # neither source present

    spec = dj._phase_fanout_spec(PHASE, run_dir)
    assert fo.enumerate_fanout_items(run_dir, spec, phase_id=PHASE,
                                     produces_artifact=[SPEC_ARTIFACT]) == []

    first = dj.sweep_run_dir(run_dir, worker_id="test-sweeper", max_workers=3)
    assert len(first) == 1 and first[0].status == "error"
    assert "enumerated zero units" in " ".join(first[0].reasons)
    assert seen == [], "no unit may be invented while the input is absent"
    assert not _marker(run_dir).exists(), "one refusal must not park the phase"

    # The dependency lands (the real P3-ARC shape), and the very next tick runs.
    (run_dir / ARC_REL).write_text(json.dumps(_live_allocation(8)), encoding="utf-8")
    clock.advance(10.0)
    again = dj.sweep_run_dir(run_dir, worker_id="test-sweeper", max_workers=3)

    assert len(again) == 1 and again[0].status == "ok", \
        f"the phase did not resume once its input landed: {again and again[0].reasons}"
    assert len(seen) == 3
    assert (run_dir / SPEC_ARTIFACT).is_file()


def test_design_phases_still_enumerate_once_the_arc_exists(tmp_path):
    """The three design phases fan out by=slide, so each reads the deck's slide
    list from P3-ARC's artifact. This pins the CODE half of that dependency:
    given the arc, they enumerate; the manifest DAG edge that would make an
    ABSENT arc a withheld admission is NOT part of this change (see the PR body
    -- adding it edits the sha-pinned manifest and would force a gated
    `--repin` of any in-flight run, which this fix deliberately avoids).

    The refusal for a genuinely absent input is unchanged and is covered by
    test_absent_allocation_enumerates_zero_then_resumes_when_it_lands above.
    """
    from presentation_job import execution_plan as ep

    manifest = json.loads(CLUSTER_MANIFEST.read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in manifest["phases"]}
    dag = ep.load_phase_dag(CLUSTER_MANIFEST)

    for pid in ("P-U-DESIGN-SALES", "P-U-DESIGN-CHECKOUT", "P-U-DESIGN-VSL"):
        spec = by_id[pid].get("fanout")
        assert spec and spec.get("by") == "slide", \
            f"{pid} is expected to fan out over the deck's slide list"

    run_dir = _seed_run(tmp_path, allocation=_live_allocation(8))
    for pid in ("P-U-DESIGN-SALES", "P-U-DESIGN-CHECKOUT", "P-U-DESIGN-VSL"):
        items = fo.enumerate_fanout_items(
            run_dir, fo.parse_fanout_field(by_id[pid].get("fanout")), phase_id=pid,
            produces_artifact=by_id[pid].get("produces_artifact"))
        assert len(items) == 8, f"{pid} enumerated {len(items)} units from the live arc"
    # P3-ARC's existing declared dependents are not disturbed by this change.
    assert "P4-COPY" in (dag.get("P3-ARC") or [])
    assert "P-STYLE-SPEC" in (dag.get("P3-ARC") or [])


# ===========================================================================
# (d) A REAL enumeration bug still fails loudly. The refusal is preserved.
# ===========================================================================
@pytest.mark.parametrize("label,artifact", [
    ("recognised-but-empty", {"slots": []}),
    ("live-shape-but-empty", {"slide_allocations": []}),
    ("no-readable-array", {"rows": [{"n": 1}], "schema": "v2"}),
    ("scalar", {"slide_count": 8}),
])
def test_unusable_present_allocation_still_fails_loudly_and_parks(
        tmp_path, clock, monkeypatch, label, artifact):
    """(d) The input IS present. Zero units here is a real bug, so it must
    still refuse loudly, still never invent a unit, and still park at the
    ceiling — a fix that turned this into a wait would hide a true defect."""
    calls = _no_model(monkeypatch)
    run_dir = _seed_run(tmp_path, allocation=artifact)

    results = _sweep_n(run_dir, clock, n=200)

    assert len(results) == dj.DISPATCH_REPEAT_CEILING == 8, (
        f"{label}: expected exactly {dj.DISPATCH_REPEAT_CEILING} dispatches, "
        f"got {len(results)}")
    assert {r.status for r in results} == {"error"}, label
    assert all("enumerated zero units" in " ".join(r.reasons) for r in results)
    assert all("no unit is ever invented" in " ".join(r.reasons) for r in results)
    assert calls == [], "no model call may be made for an unreadable allocation"

    led = dj._read_ledger(run_dir, PHASE)
    assert led["status"] == "error" and led["blocked"] is True
    assert "retry ceiling DISPATCH_REPEAT_CEILING=8" in led["blocked_reason"]
    assert _marker(run_dir).is_file(), f"{label}: a real bug must park visibly"
    # Nothing was fabricated to make the symptom go away.
    assert not (run_dir / SPEC_ARTIFACT).exists()


# ===========================================================================
# The producer-side guarantee: P3-ARC's verifier validates the shape it promises.
# ===========================================================================
def test_p3_arc_verifier_accepts_every_readable_shape(tmp_path):
    for label, alloc in (("live", _live_allocation(8)),
                         ("canonical", _canonical_allocation(8))):
        run_dir = _seed_run(tmp_path / label, allocation=alloc)
        ok, reasons = pv._verify_arc_allocation(run_dir)
        assert ok, f"{label}: a readable allocation must pass, got {reasons}"


def test_p3_arc_verifier_refuses_what_its_consumers_cannot_read(tmp_path):
    """The valid-JSON-only gate is what blessed the live artifact `done` while
    four downstream phases starved. It must now fail at the PRODUCER, loudly,
    where the defect can still be fixed — not silently, four phases later."""
    run_dir = _seed_run(tmp_path / "unreadable",
                        allocation={"rows": [{"n": 1}], "schema": "v2"})
    ok, reasons = pv._verify_arc_allocation(run_dir)
    assert not ok, "an artifact no consumer can read must not verify"
    joined = " ".join(reasons)
    assert "no slide allocation array" in joined
    # The refusal names the accepted spellings, so the owning role can converge.
    for key in arc.SLIDE_LIST_KEYS:
        assert key in joined, f"the refusal must name the accepted key {key!r}"


def test_p3_arc_verifier_refuses_an_empty_allocation(tmp_path):
    run_dir = _seed_run(tmp_path / "empty", allocation={"slots": []})
    ok, reasons = pv._verify_arc_allocation(run_dir)
    assert not ok and "EMPTY" in " ".join(reasons)


def test_p3_arc_verifier_still_refuses_a_missing_or_invalid_file(tmp_path):
    """Strictly stronger than before, never weaker: absence, zero bytes and
    unparseable JSON keep failing exactly as they did."""
    run_dir = _seed_run(tmp_path / "absent")
    ok, reasons = pv._verify_arc_allocation(run_dir)
    assert not ok and "file not found" in " ".join(reasons)

    (run_dir / ARC_REL).write_text("{not valid json", encoding="utf-8")
    ok, reasons = pv._verify_arc_allocation(run_dir)
    assert not ok and "not valid JSON" in " ".join(reasons)

    (run_dir / ARC_REL).write_text("", encoding="utf-8")
    ok, reasons = pv._verify_arc_allocation(run_dir)
    assert not ok and "zero bytes" in " ".join(reasons)


def test_p3_arc_verifier_is_registered_not_bypassed():
    assert pv.PHASE_VERIFIERS["P3-ARC"] is pv._verify_arc_allocation, \
        "P3-ARC must not fall back to the validity-only JSON gate"


# ===========================================================================
# The normalizer's own contract table.
# ===========================================================================
def test_bare_list_allocation_is_read_positionally():
    slots = arc.slots_from_obj([{"arc_section": "a"}, {"arc_section": "b"}])
    assert [(s["ordinal"], s["slide"]) for s in slots] == [(1, 1), (2, 2)]


def test_ordinal_precedence_prefers_ordinal_then_slide_then_slide_number():
    assert arc.slots_from_obj([{"ordinal": 7, "slide": 3, "slide_number": 5}])[0]["ordinal"] == 7
    assert arc.slots_from_obj([{"slide": 3, "slide_number": 5}])[0]["ordinal"] == 3
    assert arc.slots_from_obj([{"slide_number": 5}])[0]["ordinal"] == 5
    # A boolean is never an ordinal (True is an int in Python).
    assert arc.slots_from_obj([{"slide": True}])[0]["ordinal"] == 1


def test_unknown_shapes_are_not_determinable_rather_than_empty():
    """None and [] mean different things and must never be conflated: None is
    "no artifact", [] is "an artifact that declares zero slides"."""
    for obj in (None, 42, "text", {}, {"foo": []}, {"__parse_error__": "x"},
                {"slots": "not-a-list"}):
        assert arc.slots_from_obj(obj) is None, f"{obj!r} must be NOT determinable"
        assert arc.slide_count_from_obj(obj) is None
    assert arc.slots_from_obj({"slots": []}) == []
    assert arc.slide_count_from_obj({"slots": []}) == 0
