"""DEFECT 4 -- the no-collision invariant: no artifact may have more than one
declared producer in PIPELINE-MANIFEST.json.

WHY THIS IS A REAL DEFECT AND NOT A STYLE RULE -- the mechanism is already
documented in this repo's own history (v24.2.0, commit edff696de,
"P-SP-P3-HYGIENE writes its own QC verdict, not the structure phase's
artifact"). Two phases declaring the same produces_artifact breaks the pipeline
in three independent places:

  1. execution_plan.build_edges rule 2 -- a phase that both consumes and
     produces a pattern belongs to that artifact's producing STAGE and takes no
     edge from the other producers. With two producers, the edge that would
     have ordered the second phase is discarded, and it level-schedules into
     wave 1, ahead of the phase whose output it exists to consume.
  2. dispatcher.py's already_satisfied pre-check -- keyed on produces_artifact
     FILE EXISTENCE. Once producer A writes the path, producer B is reported
     "skipped_satisfied" and never dispatched at all.
  3. phases.py Engine._artifacts_present -- likewise literal file existence, so
     the engine also completes B on A's file.

All three are silent: no error, no park, no autofail. In the live 2026-09-04
run this cost the signature deck its entire P-SP-STRUCTURE phase.

THE FIVE COLLISIONS THIS TEST WAS WRITTEN AGAINST (manifest v66):

    build_receipt.json           P-U-GHL-SALES        + P-U-GHL-VSL
    design/sales-design.png      P-U-DESIGN-SALES     + P-U-DESIGN-RENDER-SALES
    design/checkout-design.png   P-U-DESIGN-CHECKOUT  + P-U-DESIGN-RENDER-CHECKOUT
    design/vsl-design.png        P-U-DESIGN-VSL       + P-U-DESIGN-RENDER-VSL
    working/copy/intake.json     P-CONVERTER + P0A-INTAKE + P-SP-CLAIM

Resolved in manifest v67 by pointing each phase at the artifact it actually
produces (see the commit message for the per-artifact evidence).
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from manifest_source import resolve_manifest  # noqa: E402
from presentation_job import execution_plan as ep  # noqa: E402


def _manifest_path() -> Path:
    path, provenance = resolve_manifest(SCRIPTS)
    assert path.is_file(), f"resolve_manifest returned {path} ({provenance})"
    return path


def _producers_by_artifact():
    manifest = json.loads(_manifest_path().read_text(encoding="utf-8"))
    producers = collections.defaultdict(list)
    for phase in manifest["phases"]:
        for artifact in ep._as_artifact_list(phase.get("produces_artifact")):
            producers[artifact].append(phase["id"])
    return producers


# ---------------------------------------------------------------------------
# 1. THE INVARIANT.
# ---------------------------------------------------------------------------
def test_no_artifact_has_more_than_one_declared_producer():
    collisions = {a: p for a, p in _producers_by_artifact().items() if len(p) > 1}
    assert not collisions, (
        "same-artifact multi-producer collision(s) in PIPELINE-MANIFEST.json — "
        "the second producer's ordering edge is discarded (build_edges rule 2) "
        "and its dispatch is suppressed by the already_satisfied presence "
        "check, silently: "
        + "; ".join(f"{a} <- {', '.join(p)}" for a, p in sorted(collisions.items())))


# ---------------------------------------------------------------------------
# 2. The five specific repairs, named, so a revert is loud rather than a
#    silent return to the shape above.
# ---------------------------------------------------------------------------
def test_the_five_repaired_artifacts_have_their_true_single_producer():
    producers = _producers_by_artifact()
    expected = {
        # The render script executor is the PNG producer; the agent phase
        # authors the prompt only (already stated verbatim in each render
        # phase's own manifest `name`: "FIX 28: the PNG producer").
        "design/sales-design.png":    ["P-U-DESIGN-RENDER-SALES"],
        "design/checkout-design.png": ["P-U-DESIGN-RENDER-CHECKOUT"],
        "design/vsl-design.png":      ["P-U-DESIGN-RENDER-VSL"],
        # phase_verifiers._verify_converter: "P-CONVERTER produces a source
        # brief, per its own SOP 9.8 ... P0A-INTAKE ... is what actually
        # writes intake.json".
        "working/copy/intake.json":   ["P0A-INTAKE"],
        "working/copy/source_brief.json": ["P-CONVERTER"],
        # dispatcher.ARTIFACT_TARGET_OVERRIDE + the phase's OUTPUT CONTRACT
        # both already named sp_claims.json; only the manifest disagreed.
        "working/copy/sp_claims.json": ["P-SP-CLAIM"],
        # One receipt per funnel. Deliberately NOT
        # working/<funnel>/build_receipt.json: those two paths already belong
        # to sales_checkout_builder.py and vsl_builder.py.
        "working/sales-checkout/ghl_build_receipt.json": ["P-U-GHL-SALES"],
        "working/vsl/ghl_build_receipt.json":            ["P-U-GHL-VSL"],
    }
    for artifact, want in expected.items():
        assert producers.get(artifact) == want, (
            f"{artifact}: expected producer(s) {want}, got "
            f"{producers.get(artifact)}")
    assert "build_receipt.json" not in producers, (
        "the bare, un-namespaced build_receipt.json is back: two funnels "
        "writing one path is the collision this repair removed")


# ---------------------------------------------------------------------------
# 3. The repair must not have cost the DAG its shape: no cycle, no phase left
#    without the prerequisites it had, no new dangling consumed artifact.
# ---------------------------------------------------------------------------
def test_the_dag_still_topologically_sorts_with_every_phase_present():
    phases = ep._load_raw_phases(_manifest_path())
    dag = ep.build_edges(phases)
    order = ep.topological_sort(dag)  # raises ValueError on a cycle
    assert len(order) == len(phases), (
        f"topological_sort dropped phases: {len(order)} of {len(phases)}")


def test_the_claim_gate_now_waits_for_the_intake_it_gates():
    """P-SP-CLAIM used to declare AND consume intake.json, so build_edges rule
    2 discarded its only ordering edge and it level-scheduled into wave 1 --
    alongside the intake phase whose output it is supposed to gate. It now
    declares its own artifact, so the edge survives."""
    dag = ep.build_edges(ep._load_raw_phases(_manifest_path()))
    assert "P-SP-CLAIM" in dag.get("P0A-INTAKE", []), (
        "P-SP-CLAIM must depend on P0A-INTAKE — it reads the intake.json that "
        "phase writes")


def test_no_new_consumed_artifact_lost_its_producer():
    """The only unproduced-consumed pattern is the one that was already there
    on origin/main; this repair introduced none."""
    phases = ep._load_raw_phases(_manifest_path())
    assert ep.find_unproduced_consumed_artifacts(phases) == [
        "working/copy/slides.json"], (
        "the set of consumed-but-unproduced artifacts changed; a collision "
        "repair must never leave a consumer without a producer")


def test_the_claim_gate_is_now_intake_gated_and_that_cannot_deadlock():
    """The companion to the edit this repair forced on
    tests/test_af_intake_gate.py.

    P-SP-CLAIM used to be EXEMPT from AF-INTAKE-GATE, because it declared
    intake.json as its own produces_artifact. That declaration was the
    collision. With it gone the phase is gated like any other consumer -- and
    that is safe precisely BECAUSE the collision is gone: it now carries a real
    P0A-INTAKE -> P-SP-CLAIM edge and schedules strictly after the phase that
    writes the file, so the gate can never fire on a run that would otherwise
    have succeeded. Pinned here so the two halves can never drift apart.
    """
    phases = ep._load_raw_phases(_manifest_path())
    dag = ep.build_edges(phases)
    waves = ep._wave_schedule_dag(dag, 8)
    pos = {n: w for w, names in enumerate(waves, 1) for n in names}

    assert "P-SP-CLAIM" in dag.get("P0A-INTAKE", []), (
        "the ordering edge that makes gating P-SP-CLAIM safe is missing")
    assert pos["P-SP-CLAIM"] > pos["P0A-INTAKE"], (
        f"P-SP-CLAIM (wave {pos['P-SP-CLAIM']}) must run AFTER P0A-INTAKE "
        f"(wave {pos['P0A-INTAKE']}) — being in the same wave is the "
        "collision-era schedule this repair removed")

    ceiling = max(p["order"] for p in phases
                  if "working/copy/intake.json"
                  in ep._as_artifact_list(p.get("produces_artifact")))
    claim_order = next(p["order"] for p in phases if p["id"] == "P-SP-CLAIM")
    assert claim_order > ceiling, (
        "tests/test_af_intake_gate.py::test_every_phase_after_intake_cluster_"
        "is_gated derives its exempt ceiling from the manifest and therefore "
        "requires P-SP-CLAIM to be gated; if this ever stops holding, the "
        "exemption list in that file must be revisited in the same commit")
